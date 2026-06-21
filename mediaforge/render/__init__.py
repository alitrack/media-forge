"""MediaForge render layer.

Engine registry:

    from mediaforge.render import get_render_engine

    engine = get_render_engine("hyperframes", fps=30)
    engine.render(script, "audio.mp3", "output.mp4")

Backward-compatible:
    from mediaforge.render import Renderer  # still works
"""

from mediaforge.render.base import (
    RenderEngine,
    RenderError,
    get_render_engine,
    list_engines,
    register_engine,
)

# Backward-compat: Renderer alias
from mediaforge.render._default_impl import DefaultRenderer as Renderer  # noqa: F401

# Export engine
from mediaforge.render.export import get_export_engine, list_export_engines  # noqa: F401

# Hooks
from mediaforge.render.hooks import HookRegistry, RenderContext  # noqa: F401

# Auto-register engines
from mediaforge.render import _default  # noqa: F401 — registers "default"
from mediaforge.render import hyperframes  # noqa: F401 — registers "hyperframes"

__all__ = [
    "RenderEngine",
    "Renderer",
    "RenderError",
    "get_render_engine",
    "list_engines",
    "register_engine",
    "get_export_engine",
    "list_export_engines",
    "HookRegistry",
    "RenderContext",
]
