"""MediaForge MCP Server — exposes pipeline as Hermes-callable tools.

Tools:
  - generate_podcast  : URL/PDF/text → interview MP3
  - generate_video    : URL/PDF/text → video MP4
  - list_voices       : Available TTS voices
  - publish           : Expose file via cloudflared
"""

import os
import sys
import yaml
from mcp.server.fastmcp import FastMCP

# ── Config ────────────────────────────────────────────────

mcp = FastMCP("mediaforge")

# Lazy imports to keep startup fast


def _get_composer():
    """Create Composer with credentials from Hermes config."""
    from mediaforge.compose import Composer

    config_path = os.path.expanduser("~/.hermes/config.yaml")
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    for p in cfg.get("custom_providers", []):
        if "deepseek" in p.get("name", "").lower():
            return Composer(
                model="deepseek-chat",
                api_key=p["api_key"],
                base_url=p["base_url"] + "/v1",
            )

    # Fallback: try env vars
    return Composer(model="deepseek-chat")


# ── Tools ─────────────────────────────────────────────────

@mcp.tool()
async def generate_podcast(
    text: str = "",
    url: str = "",
    style: str = "interview",
    host_voice: str = "xiaoxiao",
    expert_voice: str = "yunyang",
    output_path: str = "/tmp/podcast.mp3",
    publish: bool = False,
) -> str:
    """Generate an audio podcast from text or URL.

    Args:
        text: Raw text content (use if no URL).
        url: URL to fetch content from (overrides text).
        style: 'interview', 'tutorial', 'explainer', or 'debate'.
        host_voice: Voice for host (xiaoxiao/yunyang).
        expert_voice: Voice for expert.
        output_path: Where to save the MP3.
        publish: If True, return public cloudflared URL.

    Returns:
        Path to generated MP3, or public URL if publish=True.
    """
    from mediaforge import Ingester, Synthesizer
    from mediaforge.types import Source, SourceType, ContentStyle

    # 1. Ingest
    if url.strip():
        ingester = Ingester()
        result = ingester.ingest([Source(type=SourceType.URL, content=url)])
        content = result.content
    elif text.strip():
        content = text
    else:
        return "Error: provide either text= or url="

    # 2. Compose
    composer = _get_composer()
    style_map = {
        "interview": ContentStyle.INTERVIEW,
        "tutorial": ContentStyle.TUTORIAL,
        "explainer": ContentStyle.EXPLAINER,
        "debate": ContentStyle.DEBATE,
    }
    script = composer.compose(
        content,
        style=style_map.get(style, ContentStyle.INTERVIEW),
        voice_map={"host": host_voice, "expert": expert_voice},
    )

    # 3. Synthesize
    synth = Synthesizer(backend="edge")
    path = synth.synthesize(script, output_path)
    sz = os.path.getsize(path)

    # 4. Publish (optional)
    if publish:
        try:
            from mediaforge.publish import Publisher
            pub = Publisher()
            url = pub.publish(path)
            return f"Podcast: {url} ({len(script.segments)} segments, {sz//1024}KB)"
        except Exception as e:
            return f"Podcast saved: {path} ({len(script.segments)} segments, {sz//1024}KB). Publish failed: {e}"

    return f"Podcast saved: {path} ({len(script.segments)} segments, {sz//1024}KB)"


@mcp.tool()
async def generate_video(
    text: str = "",
    url: str = "",
    style: str = "interview",
    host_voice: str = "xiaoxiao",
    expert_voice: str = "yunyang",
    frame_count: int = 4,
    audio_path: str = "/tmp/podcast.mp3",
    video_path: str = "/tmp/video.mp4",
    render: str = "default",
    fps: int = 30,
    watermark_text: str = "",
    qrcode_url: str = "",
    progress_bar: bool = False,
) -> str:
    """Generate a video with visual frames from text or URL.

    Args:
        text: Raw text content.
        url: URL to fetch content from.
        style: 'interview', 'tutorial', 'explainer', or 'debate'.
        host_voice: Voice for host.
        expert_voice: Voice for expert.
        frame_count: Number of visual frames (2-8, default engine only).
        audio_path: Intermediate audio file path.
        video_path: Output MP4 path.
        render: Render engine — 'default' (static) or 'hyperframes' (animated, 30fps).
        fps: Frames per second for hyperframes engine (default: 30).
        watermark_text: Watermark text overlay (hyperframes only).
        qrcode_url: QR code URL to overlay on frames (hyperframes only).
        progress_bar: Show animated progress bar (hyperframes only).

    Returns:
        Path to generated MP4.
    """
    from mediaforge import Ingester, Synthesizer
    from mediaforge.render import get_render_engine
    from mediaforge.render.hooks import HookRegistry
    from mediaforge.render.builtin_hooks import watermark_hook, progress_bar_hook, qrcode_hook
    from mediaforge.types import Source, SourceType, ContentStyle

    # 1. Ingest
    if url.strip():
        ingester = Ingester()
        result = ingester.ingest([Source(type=SourceType.URL, content=url)])
        content = result.content
    elif text.strip():
        content = text
    else:
        return "Error: provide either text= or url="

    # 2. Compose
    composer = _get_composer()
    style_map = {
        "interview": ContentStyle.INTERVIEW,
        "tutorial": ContentStyle.TUTORIAL,
        "explainer": ContentStyle.EXPLAINER,
        "debate": ContentStyle.DEBATE,
    }
    script = composer.compose(
        content,
        style=style_map.get(style, ContentStyle.INTERVIEW),
        voice_map={"host": host_voice, "expert": expert_voice},
    )

    # 3. Synthesize audio
    synth = Synthesizer(backend="edge")
    synth.synthesize(script, audio_path)

    # 4. Build hooks
    hooks = HookRegistry()
    if watermark_text.strip():
        hooks.register("post-frame", watermark_hook(watermark_text))
    if progress_bar:
        hooks.register("post-frame", progress_bar_hook())
    if qrcode_url.strip():
        hooks.register("pre-ffmpeg", qrcode_hook(qrcode_url))

    # 5. Render video
    engine_kwargs = {}
    if render == "hyperframes":
        engine_kwargs["fps"] = fps
        if hooks.count() > 0:
            engine_kwargs["hooks"] = hooks
    elif render == "default":
        engine_kwargs["frame_count"] = frame_count

    engine = get_render_engine(render, **engine_kwargs)
    engine.render(script, audio_path, video_path)
    sz = os.path.getsize(video_path)

    info = f"{sz//1024}KB, {len(script.segments)} segments"
    if render == "hyperframes":
        info += f", {fps}fps"
    else:
        info += f", {frame_count} frames"

    return f"Video saved: {video_path} ({info})"


@mcp.tool()
async def list_voices() -> str:
    """List available TTS voices by backend.

    Returns:
        Voice list grouped by backend.
    """
    from mediaforge.synthesize import VOICE_REGISTRY

    lines = ["Available TTS voices:"]
    for backend, voices in VOICE_REGISTRY.items():
        lines.append(f"\n  [{backend}]:")
        for short, full in voices.items():
            lines.append(f"    {short} → {full}")
    return "\n".join(lines)


@mcp.tool()
async def publish(path: str) -> str:
    """Publish a local file via cloudflared tunnel.

    Args:
        path: Absolute path to the file to publish.

    Returns:
        Public URL to access the file.
    """
    from mediaforge.publish import Publisher

    pub = Publisher()
    url = pub.publish(path)
    return f"Published: {url}"


@mcp.tool()
async def serve_dir(path: str) -> str:
    """Serve an entire directory via cloudflared tunnel.

    Args:
        path: Absolute path to the directory.

    Returns:
        Public base URL.
    """
    from mediaforge.publish import Publisher

    pub = Publisher()
    url = pub.serve_dir(path)
    return f"Serving: {url}"


# ── Entry Point ───────────────────────────────────────────

def main():
    mcp.run()


if __name__ == "__main__":
    main()
