"""Render Engine Protocol — unified abstraction for video rendering backends.

Usage:
    from mediaforge.render import get_render_engine
    engine = get_render_engine("hyperframes", fps=30)
    engine.render(script, "audio.mp3", "output.mp4")
"""

from __future__ import annotations

from typing import ClassVar, Protocol, runtime_checkable

from mediaforge.types import Script


class RenderError(Exception):
    """Video rendering failed."""


@runtime_checkable
class RenderEngine(Protocol):
    """Protocol that all render engines must implement."""

    name: ClassVar[str]

    def render(
        self,
        script: Script,
        audio_path: str,
        output_path: str,
        **kwargs,
    ) -> str:
        """Render script + audio into video. Returns output_path."""
        ...

    @classmethod
    def available(cls) -> bool:
        """Check if engine dependencies are installed."""
        ...


# ── Registry ──────────────────────────────────────────────

_registry: dict[str, type[RenderEngine]] = {}


def register_engine(engine_cls: type[RenderEngine]) -> None:
    """Register a render engine class."""
    _registry[engine_cls.name] = engine_cls


def get_render_engine(name: str = "default", **kwargs) -> RenderEngine:
    """Factory: get a render engine instance by name.

    Raises RenderError if engine unknown or unavailable.
    """
    if name not in _registry:
        raise RenderError(
            f"Unknown render engine: '{name}'. "
            f"Available: {list(_registry) or ['(none registered)']}"
        )
    engine_cls = _registry[name]
    if not engine_cls.available():
        raise RenderError(
            f"Render engine '{name}' is not available. "
            f"Check its dependencies."
        )
    return engine_cls(**kwargs)


def list_engines() -> list[str]:
    """Return names of all registered engines."""
    return list(_registry.keys())
