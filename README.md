# MediaForge

**Content → Multi-Format Media Pipeline**

Turn any URL, PDF, or text into a professional podcast or video — **fully offline**, no NotebookLM required.

```
┌────────┐    ┌──────────┐    ┌─────────────┐    ┌──────────┐    ┌──────────┐
│ Ingest │ →  │ Compose  │ →  │ Synthesize  │ →  │ Render   │ →  │ Publish  │
│ URL/PDF│    │ LLM      │    │ edge-tts    │    │Playwright│    │cloudflared│
│ /text  │    │ script   │    │ MP3 concat  │    │+ ffmpeg  │    │tunnel    │
└────────┘    └──────────┘    └─────────────┘    └──────────┘    └──────────┘
   plugins         4 styles        3 backends        HTML frames       public URL
```

**5-stage pipeline, each layer independently swappable.**

## Why MediaForge?

| | NotebookLM | Remotion | MediaForge |
|---|---|---|---|
| **Offline** | ❌ Cloud-only | ✅ | ✅ |
| **License** | Proprietary | Company license required | MIT |
| **Inputs** | URL/PDF/text | N/A (video SDK) | URL/PDF/text/image/Office |
| **Outputs** | Audio + Video | Video (React) | Audio + Video |
| **TTS** | Google voices | N/A | edge-tts / Azure / CosyVoice |
| **Video render** | AI-generated overviews | React component | Playwright + ffmpeg |
| **Programmable** | ❌ Frontend only | ❌ Own SDK | ✅ MCP + CLI + Python API |

MediaForge gives you the podcast-generation power of NotebookLM, the video rendering of Remotion, and the extensibility of a modular pipeline — all as open-source MIT software.

## Quick Start

### Zero-install (uv)

```bash
# Generate a podcast — no pip install needed
uv run --with mediaforge mediaforge podcast --url https://example.com/article

# Or from GitHub directly
uv run --with git+https://github.com/alitrack/media-forge mediaforge podcast --url https://example.com
```

### pip install

```bash
pip install mediaforge
```

### 15-Second Demo

```python
from mediaforge import Ingester, Composer, Synthesizer
from mediaforge.render import get_render_engine
from mediaforge.types import Source, SourceType, ContentStyle

# 1. Ingest — URL, PDF, or raw text
ingester = Ingester()
result = ingester.ingest([Source(type=SourceType.URL, content="https://example.com/article")])

# 2. Compose — LLM generates dialogue script
composer = Composer(model="deepseek-chat", api_key="...", base_url="...")
script = composer.compose(result.content, style=ContentStyle.INTERVIEW)

# 3. Synthesize — TTS generates MP3
synth = Synthesizer(backend="edge")
audio = synth.synthesize(script, "/tmp/podcast.mp3")

# 4. Render — choose your engine
# Static frames (default):
engine = get_render_engine("default")
video = engine.render(script, audio, "/tmp/video.mp4", frame_count=6)

# Animated 30fps (hyperframes):
engine = get_render_engine("hyperframes", fps=30)
video = engine.render(script, audio, "/tmp/video.mp4")
```

### CLI

```bash
# Podcast from URL
mediaforge podcast --url https://example.com/article

# Video — static frames (default engine)
mediaforge video --text "$(cat notes.md)" --frames 8

# Video — animated hyperframes with hooks
mediaforge video --text "$(cat notes.md)" \
    --render hyperframes --fps 30 \
    --frame-style gradient \
    --watermark "MediaForge" \
    --progress-bar

# Video — vertical shorts (9:16)
mediaforge video --text "$(cat notes.md)" \
    --render hyperframes \
    --output-preset 9:16 \
    --frame-style clean

# Serve generated media
mediaforge serve /tmp/output/
```

## Architecture

### Stage 1: Ingest

Plugin-based content extraction. Add backends by implementing `IngesterBackend`.

| Source Type | Default Backend | Fallback Chain |
|---|---|---|
| URL | trafilatura | → readability → browser |
| PDF | pdfplumber | → MinerU OCR |
| Text | passthrough | — |
| Office | _(planned)_ | MarkItDown → python-docx |
| Image | _(planned)_ | MinerU OCR → Tesseract |

```python
# Register a custom backend
from mediaforge.ingest import IngesterBackend, BACKEND_REGISTRY, SourceType

class MyBackend(IngesterBackend):
    name = "my-backend"
    def ingest(self, source): ...

BACKEND_REGISTRY[SourceType.PDF].insert(0, MyBackend())
```

### Stage 2: Compose

LLM-driven script generation. 4 built-in styles, configurable prompt templates.

| Style | Speakers | Format | Best For |
|---|---|---|---|
| `INTERVIEW` | Host + Expert | Q&A dialogue | Blog posts, papers |
| `TUTORIAL` | Single narrator | Step-by-step | How-to guides |
| `EXPLAINER` | Single narrator | Concept deep-dive | Technical docs |
| `DEBATE` | Pro + Con | Point-counterpoint | Opinion pieces |

```python
script = composer.compose(
    text,
    style=ContentStyle.DEBATE,
    voice_map={"pro": "xiaoxiao", "con": "yunyang"},
)
```

### Stage 3: Synthesize

Multi-backend TTS with per-segment voice assignment.

| Backend | Quality | Cost | License |
|---|---|---|---|
| **edge-tts** | Good | Free | Microsoft (gratis) |
| **Azure Speech** | Excellent | Paid | Commercial |
| **CosyVoice 3** | Excellent | Free (local GPU) | Apache 2.0 |

```python
synth = Synthesizer(backend="azure", azure_key="...", azure_region="eastus")
```

### Stage 4: Render

**Pluggable render engines.** Choose static or animated output.

#### Default Engine (static frames)

HTML frames → Playwright screenshots → ffmpeg video compositing.

```python
from mediaforge.render import get_render_engine
engine = get_render_engine("default")
video = engine.render(script, audio, "output.mp4", frame_count=8)
```

#### Hyperframes Engine (CSS-animated, 30fps)

LLM-generated animated HTML → Playwright per-frame capture → ffmpeg compositing.
Smooth transitions between dialogue segments with fade-in, slide, and highlight effects.

**New in v2: Render hooks, frame styling, export engine selection.**

```python
from mediaforge.render import get_render_engine
from mediaforge.render.hooks import HookRegistry
from mediaforge.render.builtin_hooks import watermark_hook, progress_bar_hook

# Build hooks
hooks = HookRegistry()
hooks.register("post-frame", watermark_hook("MediaForge"))
hooks.register("post-frame", progress_bar_hook())

# Animated 30fps with watermark + progress bar + gradient style
engine = get_render_engine(
    "hyperframes",
    fps=30,
    hooks=hooks,
    style="gradient",        # clean | dark | gradient
    export_engine="ffmpeg",  # ffmpeg | webcodecs
)
video = engine.render(script, audio, "output.mp4")
```

**Render hooks** inject effects at 4 pipeline stages:
`pre-frame` → `post-frame` (modify HTML) → `pre-ffmpeg` (overlay images) → `post-output`

Built-in hooks: `watermark_hook()`, `progress_bar_hook()`, `qrcode_hook()`.

**Frame styles** (inspired by Recordly) via `style=` parameter:
`clean`, `dark`, `gradient` — or pass a `FrameStyle` object with custom gradients, shadows, rounded corners, and aspect ratios (16:9/1:1/9:16/4:3).

**Export engines**: `ffmpeg` (stable, default) or `webcodecs` (fast preview via Chromium WebCodecs).

**Session files**: Save pipeline state as `.mediaforge` YAML — resume from any stage.

```python
from mediaforge.session import save_session, load_session

state = PipelineState(stage="synthesized", script={...})
save_session(state, "demo.mediaforge")
```

#### Engine Registry

| Engine | `name` | Output | Best For |
|--------|--------|--------|----------|
| `DefaultEngine` | `"default"` | Static frames (30s) | Quick drafts, low CPU |
| `Hyperframes` | `"hyperframes"` | 30fps animation (90s) | Final publish, demos |

#### Rendering Quality

For crisp, ghost-free text in hyperframes output, the engine applies these optimizations by default:

| Fix | Detail |
|-----|--------|
| Font size | 48px body text on 1920×1080 canvas |
| Font smoothing | `-webkit-font-smoothing: antialiased` + `text-rendering: optimizeLegibility` |
| Text contrast | Pure white (`#ffffff`) on dark gradient background |
| Segment transitions | `opacity` + `transform` only (no `all`), past segments fully hidden (opacity 0) |
| Encoding | FFmpeg `-preset medium -crf 18` preserves text detail |

If you encounter blurry text or ghosting, check: nested `<style>` tags, font size below 48px, missing font smoothing, low contrast text colors, or aggressive encoding presets (`-preset fast -crf 23`).

Add custom engines by implementing the `RenderEngine` protocol:

```python
from mediaforge.render import RenderEngine, register_engine

class MyEngine:
    name = "my-engine"
    def render(self, script, audio_path, output_path, **kwargs): ...
    @classmethod
    def available(cls): return True

register_engine(MyEngine)
```

### Stage 5: Publish

Expose generated media via cloudflared tunnel — get a public URL instantly.

```python
from mediaforge import Publisher
pub = Publisher()
url = pub.publish("/tmp/podcast.mp3")
# → https://xxx.trycloudflare.com/podcast.mp3
```

## Hermes Agent Integration

MediaForge ships as both a **standalone tool** and a **Hermes MCP server**:

### MCP Server (primary integration)

5 tools registered, callable from any Hermes session.

**Zero-install via uv (recommended):**

```yaml
# ~/.hermes/config.yaml
mcp_servers:
  mediaforge:
    command: uvx
    args: ["mediaforge-mcp"]
```

**Or pip install:**

```bash
pip install mediaforge
```

```yaml
mcp_servers:
  mediaforge:
    command: mediaforge-mcp
```

| Tool | Description |
|---|---|
| `mediaforge__generate_podcast` | URL/text → interview MP3 |
| `mediaforge__generate_video` | URL/text → MP4 with frames |
| `mediaforge__list_voices` | Available TTS voices |
| `mediaforge__publish` | Expose file via cloudflared |
| `mediaforge__serve_dir` | Serve entire directory |

### Skill (UX layer)

The `media-forge` Hermes skill provides trigger words and style guidance:

- Trigger: "生成播客" / "做一期播客" / "转成访谈" / "MediaForge"
- Maps 4 content styles to Chinese descriptions
- Orchestrates the full pipeline via MCP tools

## MediaForge as Standalone Agent

The MCP server is self-contained — any MCP-compatible client (Claude Desktop, Cursor, etc.) can use MediaForge tools. No Hermes dependency, no pip install:

```json
// claude_desktop_config.json
{
  "mcpServers": {
    "mediaforge": {
      "command": "uvx",
      "args": ["mediaforge-mcp"]
    }
  }
}
```

## Development

```bash
git clone https://github.com/your-org/media-forge.git
cd media-forge
pip install -e ".[dev]"
pytest
```

### Project Structure

```
media-forge/
├── mediaforge/          # Core pipeline package
│   ├── __init__.py      # Public API surface
│   ├── types.py         # Source, Script, FrameStyle, ContentStyle
│   ├── ingest.py        # Plugin-based content extraction
│   ├── compose.py       # LLM script generation (4 styles)
│   ├── synthesize.py    # TTS backends (edge/Azure/CosyVoice)
│   ├── session.py       # .mediaforge session files (save/resume)
│   ├── publish.py       # cloudflared tunnel serving
│   └── render/          # Pluggable render engines
│       ├── base.py          # RenderEngine Protocol + registry
│       ├── hyperframes.py   # Hyperframes engine (CSS animation)
│       ├── hooks.py         # 4-stage render hook pipeline
│       ├── builtin_hooks.py # Watermark, progress bar, QR code hooks
│       ├── export.py        # ExportEngine (FFmpeg + WebCodecs)
│       ├── styling.py       # FrameStyle CSS generator + squircle
│       └── _default_impl.py # Default static-frame engine
├── mcp/
│   └── server.py        # Hermes MCP server (5 tools)
├── demo/
│   └── index.html       # Demo page template
├── openspec/            # Design docs & specs
├── pyproject.toml
└── README.md
```

## License

MIT — use it for anything. Commercial, personal, open-source — no restrictions.

## FAQ

**Q: Does this require a NotebookLM subscription?**
No. Completely offline — use your own LLM API key for script generation, edge-tts for voice synthesis. NotebookLM's Video Overviews are AI-generated and can't be customized or exported; MediaForge gives you full control over every frame.

**Q: Can I use my own voices?**
Yes. The Synthesizer supports edge-tts (free), Azure Speech (paid), and CosyVoice 3 (local GPU, open-source).

**Q: How is this different from Remotion?**
Remotion renders React components to video and requires a company license for commercial use. MediaForge uses Playwright + ffmpeg (both MIT/LGPL) with no license fees. MediaForge also handles content ingestion and TTS, which Remotion doesn't.

**Q: Can I customize the video frames?**
Edit `FRAME_TEMPLATE` in `mediaforge/render.py` — it's just HTML/CSS. Change colors, layout, fonts, add logos.

**Q: What LLM providers work?**
Any OpenAI-compatible API. Tested with DeepSeek, OpenAI, and local Ollama models.

## Cost Note

The MediaForge pipeline itself is MIT-licensed and free. However, the **Compose** stage requires an LLM to generate the dialogue script — that's your cost:

| Stage | Cost |
|-------|------|
| Ingest (document parsing) | Free |
| **Compose (LLM script generation)** | **Your LLM (API or local GPU)** |
| Synthesize (edge-tts) | Free |
| Render (Playwright + ffmpeg) | Free |
| Publish | Free |

Use a local model (Ollama / LlamaCpp) for zero-cost operation, or any OpenAI-compatible API.

## Author

Created by [alitrack](https://github.com/alitrack). Follow on WeChat: **alitrack**（微信搜一搜）

[Demo videos →](https://github.com/alitrack/media-forge/tree/main/output)