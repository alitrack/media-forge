"""Composable render hook pipeline.

Four-stage hook system for injecting custom logic into the render pipeline
without modifying the core engine. Inspired by Recordly's 7-stage extension
render pipeline, adapted for MediaForge's offline batch rendering model.

Stages:
    pre-frame    — Before HTML generation (modify context metadata)
    post-frame   — After HTML generation, before Playwright capture
                   (inject CSS/JS into HTML content)
    pre-ffmpeg   — After frame capture, before FFmpeg assembly
                   (modify frame images, overlay graphics)
    post-output  — After final output file written
                   (metadata, cleanup, notifications)

Usage:
    from mediaforge.render.hooks import HookRegistry, RenderContext

    reg = HookRegistry()
    reg.register("post-frame", watermark_hook("MediaForge"))
    reg.register("post-output", lambda ctx: print(f"Done: {ctx.output_path}"))

    ctx = RenderContext(...)
    reg.run_stage("post-frame", ctx)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# ── Types ──────────────────────────────────────────────────

RenderHook = Callable[["RenderContext"], None]
"""A single render hook: receives RenderContext, may mutate it."""


@dataclass
class RenderContext:
    """Shared mutable state passed through all render hook stages.

    Hooks can read and write any field. The context is the single source
    of truth for the current render pipeline state.
    """

    # Input
    audio_path: str = ""
    output_path: str = ""

    # Configuration
    fps: int = 30
    width: int = 1920
    height: int = 1080

    # Intermediate (populated by the render engine as it progresses)
    html_content: str = ""
    frames_dir: Optional[Path] = None
    frame_count: int = 0
    temp_video_path: Optional[str] = None

    # Free-form metadata — hooks can store/retrieve arbitrary data
    meta: dict = field(default_factory=dict)


# ── Registry ───────────────────────────────────────────────

class HookRegistry:
    """Ordered registry of hooks for four render stages.

    Hooks within a stage execute in registration order.
    Errors in one hook do not block subsequent hooks in the same stage.
    """

    VALID_STAGES = frozenset({"pre-frame", "post-frame", "pre-ffmpeg", "post-output"})

    def __init__(self) -> None:
        self._hooks: dict[str, list[RenderHook]] = {
            stage: [] for stage in self.VALID_STAGES
        }

    def register(self, stage: str, hook: RenderHook) -> None:
        """Register a hook at a specific stage.

        Args:
            stage: One of 'pre-frame', 'post-frame', 'pre-ffmpeg', 'post-output'.
            hook: A callable that takes a RenderContext and returns None.

        Raises:
            ValueError: If stage is not a valid stage name.
        """
        if stage not in self.VALID_STAGES:
            raise ValueError(
                f"Invalid stage: '{stage}'. Valid stages: {sorted(self.VALID_STAGES)}"
            )
        self._hooks[stage].append(hook)

    def run_stage(self, stage: str, ctx: RenderContext) -> None:
        """Execute all hooks registered for a stage in registration order.

        Hook exceptions are caught and logged, but do not abort the stage.
        Subsequent hooks in the same stage continue executing.

        Args:
            stage: Which stage to run.
            ctx: The shared render context, mutated in-place by hooks.
        """
        if stage not in self.VALID_STAGES:
            raise ValueError(
                f"Invalid stage: '{stage}'. Valid stages: {sorted(self.VALID_STAGES)}"
            )

        for i, hook in enumerate(self._hooks[stage]):
            try:
                hook(ctx)
            except Exception:
                logger.warning(
                    "Hook %d in stage '%s' raised an exception",
                    i,
                    stage,
                    exc_info=True,
                )

    def count(self, stage: Optional[str] = None) -> int:
        """Count registered hooks.

        Args:
            stage: If provided, count only hooks in that stage.
                   If None, count all hooks across all stages.
        """
        if stage is not None:
            if stage not in self.VALID_STAGES:
                raise ValueError(
                    f"Invalid stage: '{stage}'. Valid stages: {sorted(self.VALID_STAGES)}"
                )
            return len(self._hooks[stage])
        return sum(len(hooks) for hooks in self._hooks.values())

    def list_hooks(self, stage: Optional[str] = None) -> dict[str, list[str]]:
        """List registered hook names (repr) by stage.

        Args:
            stage: If provided, return only that stage's hooks.
        """
        if stage is not None:
            if stage not in self.VALID_STAGES:
                raise ValueError(
                    f"Invalid stage: '{stage}'. Valid stages: {sorted(self.VALID_STAGES)}"
                )
            return {stage: [repr(h) for h in self._hooks[stage]]}
        return {
            s: [repr(h) for h in hooks]
            for s, hooks in self._hooks.items()
            if hooks
        }

    def __repr__(self) -> str:
        counts = {s: len(hooks) for s, hooks in self._hooks.items()}
        total = sum(counts.values())
        return f"HookRegistry({total} hooks: {counts})"
