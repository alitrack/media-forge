"""html-video template render engine.

Renders MediaForge scripts using html-video's open-source HTML/CSS/GSAP
template gallery (Apache-2.0). Uses Playwright recordVideo + ffmpeg mux.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import ClassVar

from mediaforge.types import Script
from mediaforge.render.base import RenderError, register_engine

# ── Template directory ────────────────────────────────────

TEMPLATE_DIR = "/tmp/mediaforge-html-templates"

# ── Template descriptions ──────────────────────────────────

TEMPLATE_DESCRIPTIONS: dict[str, str] = {
    "swiss-grid": "Swiss grid layout, bold typography. Best for: structured content, presentations.",
    "kinetic-type": "Kinetic text animations with multiple scenes. Best for: short punchy scripts.",
    "warm-grain": "Warm paper texture, narrative A-roll style. Best for: storytelling, interviews.",
}


class HtmlVideoTemplateEngine:
    """Render using html-video's template gallery.

    Usage:
        engine = HtmlVideoTemplateEngine(template="swiss-grid")
        engine.render(script, "audio.mp3", "output.mp4")
    """

    name: ClassVar[str] = "html-video-templates"

    def __init__(
        self,
        template: str = "swiss-grid",
        fps: int = 30,
        width: int = 1920,
        height: int = 1080,
        chromium_path: str | None = None,
    ):
        self.template = template
        self.fps = max(15, min(60, fps))
        self.width = width
        self.height = height
        self.chromium_path = chromium_path or self._find_chromium()

    # ── Engine Protocol ─────────────────────────────────

    def render(
        self,
        script: Script,
        audio_path: str,
        output_path: str,
        **kwargs,
    ) -> str:
        """Render script + audio into video using the selected template.

        Steps:
        1. Load template HTML, inject script content
        2. Playwright recordVideo (FOUT-safe)
        3. ffmpeg webm→mp4 + audio mux
        """
        if not os.path.exists(audio_path):
            raise RenderError(f"Audio file not found: {audio_path}")

        template_html = self._load_template()
        injected_html = self._inject_content(template_html, script)
        audio_duration = self._get_audio_duration(audio_path)
        on_progress = kwargs.get("on_progress")

        work_dir = tempfile.mkdtemp(prefix="mediaforge_html_video_")
        html_path = os.path.join(work_dir, "template.html")

        # Copy template assets (fonts, GSAP) so relative paths resolve.
        # The template HTML references "assets/gsap.min.js" etc.
        tmpl_dir = os.path.join(TEMPLATE_DIR, self.template)
        assets_src = os.path.join(tmpl_dir, "assets")
        if os.path.isdir(assets_src):
            import shutil
            shutil.copytree(assets_src, os.path.join(work_dir, "assets"))

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(injected_html)

        # Playwright: record animation for the full audio duration
        webm_path = os.path.join(work_dir, "render.webm")
        try:
            self._record_video(html_path, webm_path, audio_duration, on_progress)
        except Exception as e:
            raise RenderError(f"Playwright recording failed: {e}") from e

        # ffmpeg: webm → mp4 + mux audio
        temp_video = os.path.join(work_dir, "video_no_audio.mp4")
        self._webm_to_mp4(webm_path, temp_video)
        self._mux_audio(temp_video, audio_path, output_path)

        if on_progress:
            try:
                on_progress("done", 1, 1, f"Render complete: {output_path}")
            except Exception:
                pass

        return output_path

    @classmethod
    def available(cls) -> bool:
        """Check Playwright, ffmpeg, and templates are available."""
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
            return os.path.isdir(TEMPLATE_DIR)
        except Exception:
            return False

    # ── Template discovery ──────────────────────────────

    @staticmethod
    def list_templates() -> dict[str, str]:
        """Return {name: description} for available templates."""
        result = {}
        if not os.path.isdir(TEMPLATE_DIR):
            return result
        for name in os.listdir(TEMPLATE_DIR):
            tmpl_dir = os.path.join(TEMPLATE_DIR, name)
            index = os.path.join(tmpl_dir, "index.html")
            if os.path.isfile(index):
                result[name] = TEMPLATE_DESCRIPTIONS.get(
                    name, name.replace("frame-", "").replace("-", " ").title()
                )
        return result

    # ── Internal: template loading ──────────────────────

    def _load_template(self) -> str:
        """Load and validate a template HTML file."""
        tmpl_dir = os.path.join(TEMPLATE_DIR, self.template)
        if not os.path.isdir(tmpl_dir):
            available = list(self.list_templates().keys())
            raise RenderError(
                f"Template not found: '{self.template}'. "
                f"Available: {available or ['(none)']}"
            )
        index = os.path.join(tmpl_dir, "index.html")
        if not os.path.isfile(index):
            raise RenderError(f"Template index.html missing: {index}")
        return Path(index).read_text(encoding="utf-8")

    def _inject_content(self, html: str, script: Script) -> str:
        """Replace template placeholders with script content."""
        # Replace placeholder video elements with gradient divs.
        # Warm-grain and other templates have A-roll video frames
        # that animate via GSAP. Without a real video source, the
        # frame is empty — fill it with a gradient so it looks intentional.
        html = re.sub(
            r'<video\s+id="a-roll"[^>]*>',
            '<div id="a-roll" style="background:linear-gradient(135deg,#2d1b69,#e94560,#f5a623);border-radius:16px;width:100%;height:100%"></div>',
            html,
        )
        html = re.sub(
            r'<audio\s+id="a-roll-audio"[^>]*>',
            '',
            html,
        )

        # {{TITLE}} → script title
        title = script.title or "MediaForge"
        html = html.replace("{{TITLE}}", title)

        # {{SUBTITLE}} → first short segment
        subtitle = script.segments[0].text[:80] if script.segments else ""
        html = html.replace("{{SUBTITLE}}", subtitle)

        # {{SEGMENT_N_TEXT}} → individual segments
        for i, seg in enumerate(script.segments):
            html = html.replace(f"{{{{SEGMENT_{i}_TEXT}}}}", seg.text[:200])
            speaker = getattr(seg, "speaker", "")
            html = html.replace(f"{{{{SEGMENT_{i}_SPEAKER}}}}", speaker)

        # {{BODY}} → all segments joined
        if script.segments:
            body = "\n".join(s.text[:200] for s in script.segments)
        else:
            body = "No content"
        html = html.replace("{{BODY}}", body)

        # Clean up any remaining unused placeholders
        html = re.sub(r"\{\{SEGMENT_\d+_\w+\}\}", "", html)

        return html

    # ── Internal: video recording ──────────────────────

    def _record_video(
        self,
        html_path: str,
        output_path: str,
        duration: float,
        on_progress=None,
    ) -> None:
        """Record animation via Playwright recordVideo."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RenderError(
                "Playwright not installed. Run: pip install playwright && "
                "playwright install chromium"
            )

        # FOUT prevention script — injected before any page content loads
        fout_prevent = """
        // Freeze all animations at document parse time
        const style = document.createElement('style');
        style.id = 'mf-freeze';
        style.textContent = '* { animation-play-state: paused !important; }';
        document.documentElement.appendChild(style);

        // Wait for fonts, then unfreeze
        async function waitForFonts() {
            try {
                await document.fonts.ready;
                const sheet = document.getElementById('mf-freeze');
                if (sheet) sheet.remove();
            } catch(e) {
                const sheet = document.getElementById('mf-freeze');
                if (sheet) sheet.remove();
            }
        }
        waitForFonts();
        """

        with sync_playwright() as p:
            browser = p.chromium.launch(
                executable_path=self.chromium_path,
                headless=True,
            )
            context = browser.new_context(
                viewport={"width": self.width, "height": self.height},
                record_video_dir=os.path.dirname(output_path),
                record_video_size={"width": self.width, "height": self.height},
            )
            page = context.new_page()

            # Inject FOUT prevention before navigation
            page.add_init_script(fout_prevent)

            page_errors = []

            def on_error(err):
                page_errors.append(str(err))

            page.on("pageerror", on_error)

            try:
                page.goto(f"file://{html_path}", wait_until="load", timeout=15000)

                # Wait for fonts to load (FOUT guard)
                try:
                    page.evaluate("document.fonts.ready")
                except Exception:
                    pass
                page.wait_for_timeout(500)

                # Unfreeze animations if they weren't auto-unfrozen
                page.evaluate("""
                    const sheet = document.getElementById('mf-freeze');
                    if (sheet) sheet.remove();
                """)

                # Trigger GSAP timelines (hyperframes convention)
                page.evaluate("""
                    if (window.__timelines) {
                        for (const [name, tl] of Object.entries(window.__timelines)) {
                            if (tl && typeof tl.play === 'function') {
                                tl.play();
                            }
                        }
                    }
                """)

                if on_progress:
                    try:
                        on_progress("record", 0, 1, "Recording video...")
                    except Exception:
                        pass

                # Wait for full duration + buffer
                wait_ms = int((duration + 0.5) * 1000)
                page.wait_for_timeout(wait_ms)

                # Template JS errors are non-fatal — the visual animation
                # still renders. Only log them for debugging.
                if page_errors:
                    import sys
                    print(f"Template JS warnings (non-fatal): {page_errors[:3]}", file=sys.stderr)

            finally:
                context.close()
                browser.close()

            # Playwright writes video to a temp file in record_video_dir
            # Rename to our target output_path
            video_dir = os.path.dirname(output_path)
            videos = list(Path(video_dir).glob("*.webm"))
            if not videos:
                raise RenderError("Playwright did not produce a video file")
            # Find the most recent .webm
            latest = max(videos, key=lambda p: p.stat().st_mtime)
            if str(latest) != output_path:
                os.rename(str(latest), output_path)

    # ── Internal: ffmpeg ────────────────────────────────

    def _webm_to_mp4(self, input_path: str, output_path: str) -> None:
        """Convert webm to MP4 (h264)."""
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", input_path,
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-an",  # strip audio from webm
                output_path,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RenderError(f"ffmpeg webm→mp4 failed: {result.stderr[:300]}")

    def _mux_audio(
        self, video_path: str, audio_path: str, output_path: str
    ) -> None:
        """Mux audio into video."""
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", audio_path,
                "-c:v", "copy",
                "-c:a", "aac",
                "-shortest",
                "-map", "0:v:0",
                "-map", "1:a:0",
                output_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RenderError(f"ffmpeg mux failed: {result.stderr[:300]}")

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RenderError("ffmpeg produced empty video")

    # ── Internal: utilities ─────────────────────────────

    @staticmethod
    def _find_chromium() -> str:
        import glob
        playwright_dirs = glob.glob(
            os.path.expanduser(
                "~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome"
            )
        )
        if playwright_dirs:
            return sorted(playwright_dirs, reverse=True)[0]
        snap = "/snap/bin/chromium"
        if os.path.isfile(snap):
            return snap
        raise RenderError("No chromium found. Run: playwright install chromium")

    @staticmethod
    def _get_audio_duration(audio_path: str) -> float:
        """Get audio duration via ffprobe."""
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return 10.0  # default 10s
        try:
            return float(result.stdout.strip())
        except ValueError:
            return 10.0


register_engine(HtmlVideoTemplateEngine)
