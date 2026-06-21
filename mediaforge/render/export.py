"""Pluggable export engines for video rendering.

Two backends:
    FFmpegEngine     — Stable, universal (current default)
    WebCodecsEngine  — Fast preview via Chromium WebCodecs API

Usage:
    from mediaforge.render.export import get_export_engine

    engine = get_export_engine("ffmpeg")
    engine.export(frames_dir, audio_path, output_path, fps=30)

Inspired by Recordly's three-tier export strategy (Lightning/Legacy/GPU),
simplified to two tiers for MediaForge's offline batch rendering model.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from typing import ClassVar

logger = logging.getLogger(__name__)


class ExportError(Exception):
    """Video export failed."""


# ── Abstract Engine ────────────────────────────────────────

class ExportEngine(ABC):
    """Abstract export engine.

    Each engine handles: frames_dir/*.png → output MP4 with audio.
    """

    name: ClassVar[str]

    @abstractmethod
    def export(
        self,
        frames_dir: str,
        audio_path: str,
        output_path: str,
        fps: int = 30,
        width: int = 1920,
        height: int = 1080,
    ) -> str:
        """Export frames + audio to video. Returns output_path."""
        ...

    @classmethod
    @abstractmethod
    def available(cls) -> bool:
        """Check if engine dependencies are available."""
        ...


# ── Registry ───────────────────────────────────────────────

_registry: dict[str, type[ExportEngine]] = {}


def register_export_engine(engine_cls: type[ExportEngine]) -> None:
    """Register an export engine class."""
    _registry[engine_cls.name] = engine_cls


def get_export_engine(name: str = "ffmpeg") -> ExportEngine:
    """Factory: get an export engine instance by name.

    Raises ExportError if engine unknown or unavailable.
    """
    if name not in _registry:
        raise ExportError(
            f"Unknown export engine: '{name}'. "
            f"Available: {list(_registry) or ['(none registered)']}"
        )
    engine_cls = _registry[name]
    if not engine_cls.available():
        raise ExportError(
            f"Export engine '{name}' is not available. Check its dependencies."
        )
    return engine_cls()


def list_export_engines() -> list[str]:
    """Return names of all registered export engines."""
    return list(_registry.keys())


# ── FFmpeg Engine ──────────────────────────────────────────

class FFmpegEngine(ExportEngine):
    """Stable export using ffmpeg image sequence + audio mux.

    This is the current default and most reliable path.
    """

    name: ClassVar[str] = "ffmpeg"

    def export(
        self,
        frames_dir: str,
        audio_path: str,
        output_path: str,
        fps: int = 30,
        width: int = 1920,
        height: int = 1080,
    ) -> str:
        """Export frames → silent video → mux audio → output_path."""
        # Check frames exist
        frame_pattern = os.path.join(frames_dir, "frame_%06d.png")
        first_frame = os.path.join(frames_dir, "frame_000000.png")
        if not os.path.isfile(first_frame):
            raise ExportError(f"No frames found in {frames_dir}")

        # Step 1: Frames → silent MP4
        work_dir = os.path.dirname(output_path) or tempfile.mkdtemp()
        silent_mp4 = os.path.join(work_dir, ".export_silent.mp4")

        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-framerate", str(fps),
                "-i", frame_pattern,
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                silent_mp4,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise ExportError(f"ffmpeg frames→video failed: {result.stderr[:300]}")

        # Step 2: Mux audio
        if os.path.isfile(audio_path):
            result = subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", silent_mp4,
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
                timeout=60,
            )
            if result.returncode != 0:
                raise ExportError(f"ffmpeg mux failed: {result.stderr[:300]}")
        else:
            logger.warning("Audio file not found: %s, exporting video only", audio_path)
            shutil.copy(silent_mp4, output_path)

        # Cleanup
        try:
            os.unlink(silent_mp4)
        except OSError:
            pass

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise ExportError("ffmpeg produced empty video")

        return output_path

    @classmethod
    def available(cls) -> bool:
        return shutil.which("ffmpeg") is not None


# ── WebCodecs Engine ────────────────────────────────────────

class WebCodecsEngine(ExportEngine):
    """Fast preview export using Chromium WebCodecs API.

    Launches Playwright Chromium, loads a self-contained muxer.html page
    that encodes frames + audio directly in the browser via WebCodecs,
    bypassing FFmpeg entirely.

    Trade-offs:
        + 3-5x faster than FFmpeg for short clips (< 60s)
        + No FFmpeg dependency
        - Chromium only (not Firefox/Safari)
        - H.264 + AAC only (no VP9, no Opus)
        - Audio decode requires Web Audio API (MP3 only via decodeAudioData)
    """

    name: ClassVar[str] = "webcodecs"

    def export(
        self,
        frames_dir: str,
        audio_path: str,
        output_path: str,
        fps: int = 30,
        width: int = 1920,
        height: int = 1080,
    ) -> str:
        """Export frames + audio to MP4 via Chromium WebCodecs."""
        import json
        import os as _os
        import http.server
        import socketserver
        import threading
        from pathlib import Path

        frames_abs = Path(frames_dir).resolve()
        if not frames_abs.is_dir():
            raise ExportError(f"Frames directory not found: {frames_dir}")

        # List frames
        frame_files = sorted(
            f.name for f in frames_abs.glob("frame_*.png")
        )
        if not frame_files:
            raise ExportError(f"No frame files found in {frames_dir}")

        # Start HTTP server on random port
        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(frames_abs), **kwargs)

            def log_message(self, format, *args):
                pass  # suppress logs

            def do_GET(self):
                # Handle ?list query for frame discovery
                if self.path.endswith("?list"):
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps(frame_files).encode())
                    return
                # Handle /frame_000000.png
                return super().do_GET()

        server = socketserver.TCPServer(("127.0.0.1", 0), QuietHandler)
        port = server.server_address[1]
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        frames_base_url = f"http://127.0.0.1:{port}"

        # Build muxer URL
        muxer_path = Path(__file__).parent / "webcodecs" / "muxer.html"
        if not muxer_path.is_file():
            muxer_path = (
                Path(__file__).parent.parent.parent / "render" / "webcodecs" / "muxer.html"
            )

        muxer_params = f"frames={frames_base_url}&fps={fps}&width={width}&height={height}"
        audio_abs = Path(audio_path).resolve() if audio_path else None
        if audio_abs and audio_abs.is_file():
            # Audio needs its own server or we reference it directly
            muxer_params += f"&audio=file://{audio_abs}"

        muxer_url = f"file://{muxer_path}?{muxer_params}"

        # Launch Playwright
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            server.shutdown()
            raise ExportError("Playwright not installed")

        try:
            with sync_playwright() as p:
                # Find Chromium executable
                import glob
                chromium_dirs = glob.glob(
                    _os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")
                )
                chromium_path = sorted(chromium_dirs, reverse=True)[0] if chromium_dirs else None

                browser = p.chromium.launch(
                    executable_path=chromium_path,
                    headless=True,
                    args=["--disable-web-security"],  # allow file:// to fetch localhost
                )
                context = browser.new_context(
                    viewport={"width": 800, "height": 600},
                    accept_downloads=True,
                )
                page = context.new_page()

                # Listen for download
                download_complete = []
                download_path = [None]

                def on_download(download):
                    suggested = download.suggested_filename
                    dest = output_path
                    download.save_as(dest)
                    download_path[0] = dest
                    download_complete.append(True)

                page.on("download", on_download)

                try:
                    page.goto(muxer_url, wait_until="domcontentloaded", timeout=10000)
                    # Wait for download to start (max 5 minutes)
                    page.wait_for_function(
                        "document.title === 'DONE'",
                        timeout=300_000,
                    )
                    # Give download a moment to save
                    page.wait_for_timeout(2000)
                except Exception as e:
                    error_text = ""
                    try:
                        error_text = page.evaluate(
                            "document.getElementById('error')?.textContent || ''"
                        )
                    except Exception:
                        pass
                    raise ExportError(
                        f"WebCodecs export failed: {e}. Page error: {error_text}"
                    )
                finally:
                    browser.close()

        finally:
            server.shutdown()
            server.server_close()

        if not download_path[0] or not _os.path.isfile(download_path[0]):
            raise ExportError("WebCodecs export completed but no file was saved")

        file_size = _os.path.getsize(download_path[0])
        if file_size == 0:
            raise ExportError("WebCodecs produced empty video")

        logger.info(
            "WebCodecs export: %s (%.1f MB, %d frames)",
            download_path[0],
            file_size / (1024 * 1024),
            len(frame_files),
        )
        return download_path[0]

    @classmethod
    def available(cls) -> bool:
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
            return True
        except ImportError:
            return False


# ── Auto-register ──────────────────────────────────────────

register_export_engine(FFmpegEngine)
register_export_engine(WebCodecsEngine)
