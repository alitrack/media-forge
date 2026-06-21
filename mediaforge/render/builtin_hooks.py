"""Built-in render hooks for common post-processing effects.

Each function is a factory that returns a RenderHook closure.
Closures capture their configuration at factory-call time, so they're
safe to register multiple times with different parameters.

Available hooks:
    watermark_hook    — CSS overlay watermark text on video frames
    progress_bar_hook — Animated progress bar at the bottom of frames
    qrcode_hook       — Overlay a QR code image on captured frames
"""

from __future__ import annotations

import logging
from pathlib import Path

try:
    import qrcode as _qrcode_lib
    from qrcode.image.styledpil import StyledPilImage
    from qrcode.image.styles.moduledrawers import RoundedModuleDrawer
except ImportError:
    _qrcode_lib = None

from mediaforge.render.hooks import RenderContext, RenderHook

logger = logging.getLogger(__name__)


# ── Watermark ──────────────────────────────────────────────

def watermark_hook(text: str, position: str = "bottom-right") -> RenderHook:
    """Create a hook that injects a CSS watermark overlay into the HTML.

    Injects at the post-frame stage (after HTML generation, before capture).

    Args:
        text: Watermark text (e.g. "MediaForge").
        position: 'bottom-right' | 'bottom-left' | 'top-right' | 'top-left'.

    Returns:
        A RenderHook that adds a CSS overlay to ctx.html_content.
    """
    if not text.strip():
        return lambda ctx: None  # no-op

    positions = {
        "bottom-right": "bottom: 20px; right: 40px;",
        "bottom-left": "bottom: 20px; left: 40px;",
        "top-right": "top: 20px; right: 40px;",
        "top-left": "top: 20px; left: 40px;",
    }
    pos_css = positions.get(position, positions["bottom-right"])

    # HTML-escape the text for safe CSS content injection
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')

    watermark_css = f"""
/* Injected by mediaforge watermark_hook */
.watermark-overlay {{
  position: absolute;
  {pos_css}
  font-size: 18px;
  font-family: 'PingFang SC', 'Microsoft YaHei', system-ui, sans-serif;
  color: rgba(255, 255, 255, 0.35);
  z-index: 9999;
  pointer-events: none;
  user-select: none;
}}
"""

    def _hook(ctx: RenderContext) -> None:
        """post-frame: inject watermark CSS + element into HTML."""
        # Inject CSS before </style> or </head>
        if "</style>" in ctx.html_content:
            ctx.html_content = ctx.html_content.replace(
                "</style>", f"{watermark_css}</style>", 1
            )
        elif "</head>" in ctx.html_content:
            ctx.html_content = ctx.html_content.replace(
                "</head>",
                f"<style>{watermark_css}</style></head>",
                1,
            )
        else:
            logger.warning("watermark_hook: could not find <style> or <head> in HTML")
            return

        # Inject the watermark element before </body>
        watermark_div = f'<div class="watermark-overlay">{text}</div>'
        if "</body>" in ctx.html_content:
            ctx.html_content = ctx.html_content.replace(
                "</body>", f"{watermark_div}\n</body>", 1
            )
        else:
            ctx.html_content += f"\n{watermark_div}"

    return _hook


# ── Progress Bar ───────────────────────────────────────────

def progress_bar_hook() -> RenderHook:
    """Create a hook that adds an animated progress bar at the bottom of frames.

    The bar width is driven by CSS animation tied to the video duration,
    so it smoothly advances from 0% to 100% over the course of the video.

    Returns:
        A RenderHook for the post-frame stage.
    """
    progress_css = """
/* Injected by mediaforge progress_bar_hook */
.mf-progress-bar {
  position: absolute;
  bottom: 0;
  left: 0;
  height: 3px;
  background: linear-gradient(90deg, #e94560, #f5a623);
  z-index: 9998;
  animation: mf-progress {duration}s linear forwards;
  transform-origin: left center;
}
@keyframes mf-progress {
  from { width: 0%; }
  to   { width: 100%; }
}
"""

    def _hook(ctx: RenderContext) -> None:
        """post-frame: inject progress bar CSS + element into HTML."""
        total_seconds = ctx.frame_count / ctx.fps if ctx.fps > 0 else 60
        css_with_duration = progress_css.replace("{duration}", str(int(total_seconds)))

        if "</style>" in ctx.html_content:
            ctx.html_content = ctx.html_content.replace(
                "</style>", f"{css_with_duration}</style>", 1
            )
        elif "</head>" in ctx.html_content:
            ctx.html_content = ctx.html_content.replace(
                "</head>",
                f"<style>{css_with_duration}</style></head>",
                1,
            )
        else:
            logger.warning(
                "progress_bar_hook: could not find <style> or <head> in HTML"
            )
            return

        progress_div = '<div class="mf-progress-bar"></div>'
        if "</body>" in ctx.html_content:
            ctx.html_content = ctx.html_content.replace(
                "</body>", f"{progress_div}\n</body>", 1
            )
        else:
            ctx.html_content += f"\n{progress_div}"

    return _hook


# ── QR Code ────────────────────────────────────────────────

def qrcode_hook(
    url: str,
    position: str = "bottom-right",
    size: int = 120,
) -> RenderHook:
    """Create a hook that overlays a QR code onto captured frame images.

    Runs at the pre-ffmpeg stage (after frames are captured, before assembly).
    Uses the `qrcode` library to generate a PIL Image, then composites it
    onto each captured PNG frame.

    Args:
        url: The URL to encode in the QR code.
        position: 'bottom-right' | 'bottom-left' | 'top-right' | 'top-left'.
        size: QR code pixel size (square).

    Returns:
        A RenderHook for the pre-ffmpeg stage.
    """
    if not url.strip():
        return lambda ctx: None

    if _qrcode_lib is None:
        logger.warning("qrcode_hook: 'qrcode[pil]' not installed, hook is no-op")
        return lambda ctx: None

    try:
        from PIL import Image
    except ImportError:
        logger.warning("qrcode_hook: Pillow not available, hook is no-op")
        return lambda ctx: None

    # Pre-generate the QR code image once
    qr = _qrcode_lib.QRCode(
        version=None,  # auto
        error_correction=_qrcode_lib.constants.ERROR_CORRECT_H,
        box_size=10,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    qr_img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=RoundedModuleDrawer(),
        fill_color="white",
        back_color=(255, 255, 255, 50),  # semi-transparent white
    ).convert("RGBA")
    qr_img = qr_img.resize((size, size), Image.LANCZOS)

    margin = 30

    def _hook(ctx: RenderContext) -> None:
        """pre-ffmpeg: overlay QR code onto each frame image."""
        if ctx.frames_dir is None:
            logger.warning("qrcode_hook: frames_dir is None, skipping")
            return

        frame_files = sorted(ctx.frames_dir.glob("frame_*.png"))
        if not frame_files:
            logger.warning("qrcode_hook: no frame files found in %s", ctx.frames_dir)
            return

        for frame_path in frame_files:
            try:
                frame = Image.open(frame_path).convert("RGBA")
                fw, fh = frame.size

                # Calculate position
                if position == "bottom-right":
                    px, py = fw - size - margin, fh - size - margin
                elif position == "bottom-left":
                    px, py = margin, fh - size - margin
                elif position == "top-right":
                    px, py = fw - size - margin, margin
                elif position == "top-left":
                    px, py = margin, margin
                else:
                    px, py = fw - size - margin, fh - size - margin

                frame.paste(qr_img, (px, py), qr_img)  # use alpha mask
                frame.save(frame_path, "PNG")
            except Exception:
                logger.warning(
                    "qrcode_hook: failed to process frame %s",
                    frame_path.name,
                    exc_info=True,
                )

    return _hook
