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

### Installation

```bash
pip install mediaforge
# Optional: for video rendering
pip install playwright && playwright install chromium
```

### 15-Second Demo

```python
from mediaforge import Ingester, Composer, Synthesizer, Renderer
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

# 4. Render — video with visual frames
renderer = Renderer()
video = renderer.render(script, audio, "/tmp/video.mp4", frame_count=6)
```

### CLI

```bash
# Podcast from URL
mediaforge podcast --url https://example.com/article

# Video from text
mediaforge video --text "$(cat notes.md)" --frames 6

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

HTML frames → Playwright screenshots → ffmpeg video compositing.

```python
renderer = Renderer(
    chromium_path="/usr/bin/chromium",  # auto-detected if omitted
    width=1920, height=1080, fps=1,
)
video = renderer.render(script, audio_path, "output.mp4", frame_count=6)
```

Customize frame appearance by modifying `FRAME_TEMPLATE` in `mediaforge/render.py`.

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

5 tools registered, callable from any Hermes session:

| Tool | Description |
|---|---|
| `mediaforge__generate_podcast` | URL/text → interview MP3 |
| `mediaforge__generate_video` | URL/text → MP4 with frames |
| `mediaforge__list_voices` | Available TTS voices |
| `mediaforge__publish` | Expose file via cloudflared |
| `mediaforge__serve_dir` | Serve entire directory |

Add to `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  mediaforge:
    command: python
    args: ["-m", "mcp.server", "--path", "/path/to/media-forge/mcp/server.py"]
```

### Skill (UX layer)

The `media-forge` Hermes skill provides trigger words and style guidance:

- Trigger: "生成播客" / "做一期播客" / "转成访谈" / "MediaForge"
- Maps 4 content styles to Chinese descriptions
- Orchestrates the full pipeline via MCP tools

## MediaForge as Standalone Agent

The MCP server is self-contained — any MCP-compatible client (Claude Desktop, Cursor, etc.) can use MediaForge tools. No Hermes dependency.

```json
// claude_desktop_config.json
{
  "mcpServers": {
    "mediaforge": {
      "command": "python",
      "args": ["-m", "mcp.server", "--path", "/path/to/media-forge/mcp/server.py"]
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
│   ├── types.py         # Source, Script, Segment, ContentStyle
│   ├── ingest.py        # Plugin-based content extraction
│   ├── compose.py       # LLM script generation (4 styles)
│   ├── synthesize.py    # TTS backends (edge/Azure/CosyVoice)
│   ├── render.py        # HTML frames → Playwright → ffmpeg
│   └── publish.py       # cloudflared tunnel serving
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