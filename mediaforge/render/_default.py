"""Default render engine — static frame screenshots.

Backward-compatible wrapper around the original Renderer class.
"""

from __future__ import annotations

from mediaforge.render.base import register_engine
from mediaforge.render._default_impl import DefaultRenderer


class DefaultEngine:
    """Static HTML frame render engine (original implementation)."""

    name = "default"

    def __init__(self, **kwargs):
        self._frame_count = kwargs.pop("frame_count", 6)
        self._renderer = DefaultRenderer(**kwargs)

    def render(self, script, audio_path, output_path, **kwargs):
        frame_count = kwargs.pop("frame_count", self._frame_count)
        return self._renderer.render(
            script, audio_path, output_path, frame_count=frame_count
        )

    @classmethod
    def available(cls) -> bool:
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
            import subprocess
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
            return True
        except Exception:
            return False


register_engine(DefaultEngine)
