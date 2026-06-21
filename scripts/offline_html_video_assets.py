#!/usr/bin/env python3
"""Offline html-video template assets for MediaForge.

Downloads external resources (GSAP, Google Fonts) and inlines sub-composition
references into self-contained HTML files for Playwright rendering.
"""
import hashlib
import os
import re
import shutil
import sys
import urllib.request
from pathlib import Path

TEMPLATES_IN = {
    "frame-swiss-grid": "swiss-grid",
    "frame-kinetic-type": "kinetic-type",
    "frame-warm-grain": "warm-grain",
}
SRC_DIR = Path("/tmp/html-video/templates")
OUT_DIR = Path("/tmp/mediaforge-html-templates")
GSAP_URL = "https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"


def log(msg: str) -> None:
    print(f"  {msg}", file=sys.stderr)


def download(url: str, dest: Path) -> bool:
    """Download URL to dest. Returns True on success."""
    if dest.exists():
        log(f"skip (exists): {dest}")
        return True
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "MediaForge/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            dest.write_bytes(resp.read())
        log(f"downloaded: {url} -> {dest}")
        return True
    except Exception as e:
        log(f"FAILED: {url} -> {e}")
        return False


def download_google_font_css(fonts_url: str, font_dir: Path) -> str | None:
    """Download Google Fonts CSS and all referenced .woff2 files.
    Returns local CSS path or None on failure.
    """
    try:
        req = urllib.request.Request(fonts_url, headers={"User-Agent": "MediaForge/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            css_text = resp.read().decode("utf-8")
    except Exception as e:
        log(f"FAILED Google Fonts CSS: {e}")
        return None

    # Replace remote font URLs with local paths
    def replace_font_url(m: re.Match) -> str:
        font_url = m.group(1)
        # Derive a stable filename
        fname = hashlib.md5(font_url.encode()).hexdigest()[:8] + ".woff2"
        local = font_dir / fname
        download(font_url, local)
        return f"url({fname})"

    css_text = re.sub(r"url\((https://fonts\.gstatic\.com/[^)]+)\)", replace_font_url, css_text)

    # Save the modified CSS
    css_path = font_dir / "fonts.css"
    css_path.write_text(css_text)
    return str(css_path)


def inline_compositions(html: str, template_dir: Path) -> str:
    """Replace data-composition-src references with inline template content."""
    comp_dir = template_dir / "compositions"
    if not comp_dir.exists():
        return html

    def replace_composition(m: re.Match) -> str:
        src = m.group(1)
        comp_path = comp_dir / Path(src).name
        if not comp_path.exists():
            log(f"WARN: composition not found: {comp_path}")
            return m.group(0)

        content = comp_path.read_text()
        # Extract template body (inside <template> tag)
        # Composition files contain <template id="xxx">...</template> with
        # visual HTML, <style>, and <script> blocks inside.
        template_match = re.search(r"<template[^>]*>(.*?)</template>", content, re.DOTALL)
        if template_match:
            inner = template_match.group(1)
            # Strip <style> and <script> from inner to avoid duplication
            inner = re.sub(r"<style[^>]*>.*?</style>", "", inner, flags=re.DOTALL)
            inner = re.sub(r"<script[^>]*>.*?</script>", "", inner, flags=re.DOTALL)
        else:
            inner = content

        # Extract style blocks from the FULL content (inside OR outside template)
        styles = re.findall(r"<style[^>]*>(.*?)</style>", content, re.DOTALL)

        # Extract script blocks (non-GSAP-CDN ones) from the FULL content
        scripts = re.findall(
            r"<script(?!\s+src=[\"']https?://cdn\.jsdelivr)[^>]*>(.*?)</script>",
            content,
            re.DOTALL,
        )

        # Build replacement: visual HTML + styles + scripts (wrapped in IIFE)
        result = inner
        for s in styles:
            result += f"\n<style>{s}</style>"
        for s in scripts:
            # Wrap in IIFE to isolate variable declarations (prevents
            # conflicts like duplicate `const tl` across compositions)
            result += f"\n<script>(function(){{{s}}})();</script>"

        return result

    html = re.sub(
        r'data-composition-src="([^"]+)"[^>]*>',
        lambda m: replace_composition(m) + "<!-- end inline comp -->",
        html,
    )
    return html


def process_template(src_name: str, dest_name: str) -> bool:
    """Process one template: copy, offline assets, inline compositions."""
    src = SRC_DIR / src_name
    if not src.exists():
        log(f"MISSING: {src}")
        return False

    dest = OUT_DIR / dest_name
    dest.mkdir(parents=True, exist_ok=True)
    assets = dest / "assets"
    assets.mkdir(exist_ok=True)

    html = src.joinpath("index.html").read_text()

    # --- Step 1: Download GSAP ---
    gsap_local = assets / "gsap.min.js"
    download(GSAP_URL, gsap_local)
    html = html.replace(GSAP_URL, "assets/gsap.min.js")
    # Also replace GSAP in any inline scripts that reference it
    html = re.sub(
        r'src="https://cdn\.jsdelivr\.net/npm/gsap[^"]*"',
        'src="assets/gsap.min.js"',
        html,
    )

    # --- Step 2: Download Google Fonts ---
    fonts_match = re.search(
        r'<link[^>]*href="(https://fonts\.googleapis\.com/[^"]+)"[^>]*>', html
    )
    if fonts_match:
        font_url = fonts_match.group(1)
        font_dir = assets / "fonts"
        font_dir.mkdir(exist_ok=True)
        css_path = download_google_font_css(font_url, font_dir)
        if css_path:
            # Replace the Google Fonts <link> with local CSS link
            html = re.sub(
                r'<link[^>]*href="https://fonts\.googleapis\.com/[^"]*"[^>]*>',
                f'<link rel="stylesheet" href="assets/fonts/fonts.css">',
                html,
                count=1,
            )
            # Also replace preconnect hints
            html = re.sub(
                r'<link rel="preconnect"[^>]*fonts\.googleapis\.com[^>]*>',
                "",
                html,
            )
            html = re.sub(
                r'<link rel="preconnect"[^>]*fonts\.gstatic\.com[^>]*>',
                "",
                html,
            )

    # --- Step 3: Inline sub-compositions ---
    html = inline_compositions(html, src)

    # --- Step 4: Remove remaining external references ---
    # transparenttextures.com pattern (warm-grain)
    html = re.sub(
        r'url\("https://www\.transparenttextures\.com/[^"]*"\)',
        "none",
        html,
    )

    # Write the processed HTML
    dest.joinpath("index.html").write_text(html)
    log(f"OK: {dest_name} ({len(html)} chars)")
    return True


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = 0
    total = len(TEMPLATES_IN)
    for src_name, dest_name in TEMPLATES_IN.items():
        print(f"Processing: {src_name} → {dest_name}")
        if process_template(src_name, dest_name):
            ok += 1
    print(f"\nDone: {ok}/{total} templates processed -> {OUT_DIR}")
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
