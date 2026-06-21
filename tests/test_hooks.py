"""Tests for the render hook pipeline."""

import pytest
from mediaforge.render.hooks import HookRegistry, RenderContext


class TestHookRegistry:
    """HookRegistry core functionality."""

    def test_register_and_run_single_hook(self):
        """A registered hook should execute when its stage is run."""
        reg = HookRegistry()
        called = []

        def my_hook(ctx):
            called.append(ctx.meta.get("key", "none"))

        reg.register("post-frame", my_hook)
        ctx = RenderContext(meta={"key": "value"})
        reg.run_stage("post-frame", ctx)

        assert called == ["value"]

    def test_hooks_execute_in_registration_order(self):
        """Multiple hooks in the same stage execute in registration order."""
        reg = HookRegistry()
        order = []

        reg.register("pre-ffmpeg", lambda ctx: order.append(1))
        reg.register("pre-ffmpeg", lambda ctx: order.append(2))
        reg.register("pre-ffmpeg", lambda ctx: order.append(3))

        reg.run_stage("pre-ffmpeg", RenderContext())
        assert order == [1, 2, 3]

    def test_stages_are_independent(self):
        """Hooks in different stages do not interfere."""
        reg = HookRegistry()
        pre_called = []
        post_called = []

        reg.register("pre-frame", lambda ctx: pre_called.append(1))
        reg.register("post-output", lambda ctx: post_called.append(1))

        reg.run_stage("pre-frame", RenderContext())
        assert pre_called == [1]
        assert post_called == []

        reg.run_stage("post-output", RenderContext())
        assert post_called == [1]

    def test_empty_registry_noop(self):
        """An empty registry runs stages without error."""
        reg = HookRegistry()
        ctx = RenderContext(audio_path="/tmp/test.mp3")

        for stage in HookRegistry.VALID_STAGES:
            reg.run_stage(stage, ctx)

        assert ctx.audio_path == "/tmp/test.mp3"  # unchanged

    def test_hook_exception_does_not_block_others(self):
        """An exception in one hook does not prevent subsequent hooks."""
        reg = HookRegistry()
        results = []

        def failing_hook(ctx):
            raise RuntimeError("boom")

        reg.register("post-frame", failing_hook)
        reg.register("post-frame", lambda ctx: results.append("survived"))

        reg.run_stage("post-frame", RenderContext())
        assert results == ["survived"]

    def test_invalid_stage_register(self):
        """Registering to an invalid stage raises ValueError."""
        reg = HookRegistry()
        with pytest.raises(ValueError, match="Invalid stage"):
            reg.register("nonexistent", lambda ctx: None)

    def test_invalid_stage_run(self):
        """Running an invalid stage raises ValueError."""
        reg = HookRegistry()
        with pytest.raises(ValueError, match="Invalid stage"):
            reg.run_stage("nonexistent", RenderContext())

    def test_hook_can_mutate_context(self):
        """Hooks can modify RenderContext fields for downstream hooks."""
        reg = HookRegistry()

        def set_meta(ctx):
            ctx.meta["step"] = 1

        def read_meta(ctx):
            ctx.meta["step"] += 1

        reg.register("post-frame", set_meta)
        reg.register("post-frame", read_meta)

        ctx = RenderContext()
        reg.run_stage("post-frame", ctx)
        assert ctx.meta["step"] == 2

    def test_count(self):
        """count() returns correct hook counts."""
        reg = HookRegistry()
        assert reg.count() == 0

        reg.register("pre-frame", lambda ctx: None)
        reg.register("post-frame", lambda ctx: None)
        reg.register("post-frame", lambda ctx: None)

        assert reg.count() == 3
        assert reg.count("pre-frame") == 1
        assert reg.count("post-frame") == 2
        assert reg.count("pre-ffmpeg") == 0

    def test_list_hooks(self):
        """list_hooks returns hook representations."""
        reg = HookRegistry()

        def my_hook(ctx):
            pass

        reg.register("post-output", my_hook)

        listing = reg.list_hooks()
        assert "post-output" in listing
        assert len(listing["post-output"]) == 1


class TestRenderContext:
    """RenderContext dataclass."""

    def test_defaults(self):
        ctx = RenderContext()
        assert ctx.fps == 30
        assert ctx.width == 1920
        assert ctx.height == 1080
        assert ctx.html_content == ""
        assert ctx.frames_dir is None
        assert ctx.meta == {}

    def test_custom_values(self):
        ctx = RenderContext(
            audio_path="/tmp/audio.mp3",
            output_path="/tmp/video.mp4",
            fps=60,
            width=3840,
            height=2160,
            meta={"style": "gradient"},
        )
        assert ctx.fps == 60
        assert ctx.width == 3840
        assert ctx.meta["style"] == "gradient"
