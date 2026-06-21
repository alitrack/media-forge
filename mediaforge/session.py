"""Session management — .mediaforge project files for pipeline resumption.

Saves full pipeline state (source → script → style → export → output)
to a YAML file so users can resume from any intermediate stage without
re-running earlier stages.

Inspired by Recordly's .recordly project files.

Usage:
    from mediaforge.session import save_session, load_session, PipelineState

    state = PipelineState(stage="synthesized", script={...})
    save_session(state, "demo.mediaforge")

    state2 = load_session("demo.mediaforge")
    assert state2.stage == "synthesized"
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class PipelineState:
    """Complete state of a MediaForge pipeline run."""

    stage: str = "new"  # new | ingested | composed | synthesized | rendered | published
    source: Optional[dict] = None  # {"type": "url", "content": "..."}
    script: Optional[dict] = None  # {"title": "...", "segments": [...]}
    style: Optional[dict] = None  # FrameStyle.to_dict()
    export: Optional[dict] = None  # {"engine": "ffmpeg", "fps": 30, ...}
    output: Optional[dict] = None  # {"audio_path": "...", "video_path": "..."}
    created_at: str = ""
    updated_at: str = ""

    meta: dict = field(default_factory=dict)


# Pipeline stage ordering (for resumption logic)
_STAGE_ORDER = [
    "new",
    "ingested",
    "composed",
    "synthesized",
    "rendered",
    "published",
]


def save_session(state: PipelineState, path: str) -> str:
    """Save pipeline state to a .mediaforge YAML file.

    Returns the resolved absolute path.
    """
    abs_path = os.path.abspath(path)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if not state.created_at:
        state.created_at = now
    state.updated_at = now

    data = {
        "version": 1,
        "created_at": state.created_at,
        "updated_at": state.updated_at,
        "pipeline": {
            "stage": state.stage,
        },
    }

    if state.source:
        data["source"] = state.source
    if state.script:
        data["script"] = state.script
    if state.style:
        data["style"] = state.style
    if state.export:
        data["export"] = state.export
    if state.output:
        data["output"] = state.output
    if state.meta:
        data["meta"] = state.meta

    with open(abs_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, default_flow_style=False)

    return abs_path


def load_session(path: str) -> PipelineState:
    """Load pipeline state from a .mediaforge YAML file."""
    abs_path = os.path.abspath(path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"Session file not found: {abs_path}")

    with open(abs_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Invalid session file: {abs_path} — not a YAML dict")

    pipeline = data.get("pipeline", {})
    stage = pipeline.get("stage", "new")
    if stage not in _STAGE_ORDER:
        raise ValueError(
            f"Invalid stage '{stage}' in {abs_path}. "
            f"Valid stages: {_STAGE_ORDER}"
        )

    return PipelineState(
        stage=stage,
        source=data.get("source"),
        script=data.get("script"),
        style=data.get("style"),
        export=data.get("export"),
        output=data.get("output"),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
        meta=data.get("meta", {}),
    )


def resume_session(path: str) -> dict:
    """Determine what to do next when resuming a session.

    Returns a dict with:
        action: "render" | "publish" | "done"
        state: the loaded PipelineState
        message: human-readable description
    """
    state = load_session(path)

    if state.stage == "new":
        raise ValueError(
            f"Cannot resume from '{state.stage}' stage. "
            f"Run the full pipeline first."
        )

    stage_idx = _STAGE_ORDER.index(state.stage)

    if stage_idx >= _STAGE_ORDER.index("published"):
        return {
            "action": "done",
            "state": state,
            "message": "Pipeline already completed.",
        }
    elif stage_idx >= _STAGE_ORDER.index("rendered"):
        return {
            "action": "publish",
            "state": state,
            "message": "Resuming from rendered stage — will publish.",
        }
    elif stage_idx >= _STAGE_ORDER.index("synthesized"):
        return {
            "action": "render",
            "state": state,
            "message": "Resuming from synthesized stage — will render.",
        }
    elif stage_idx >= _STAGE_ORDER.index("composed"):
        return {
            "action": "synthesize",
            "state": state,
            "message": "Resuming from composed stage — will synthesize + render + publish.",
        }
    else:
        return {
            "action": "compose",
            "state": state,
            "message": "Resuming from ingested stage — will compose + synthesize + render + publish.",
        }
