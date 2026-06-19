# Design: MediaForge Architecture

## Pipeline Flow

```
┌─────────────────────────────────────────────────────────────┐
│                      MediaForge Pipeline                      │
│                                                               │
│  ┌─────────┐   ┌──────────┐   ┌──────────┐   ┌───────────┐ │
│  │ Ingest  │──▶│ Compose  │──▶│Synthesize│──▶│  Publish  │ │
│  │         │   │  (LLM)   │   │  (TTS)   │   │           │ │
│  └─────────┘   └──────────┘   └──────────┘   └───────────┘ │
│       │              │               │              │        │
│       ▼              ▼               ▼              ▼        │
│  ┌─────────┐   ┌──────────┐   ┌──────────┐   ┌───────────┐ │
│  │URL/PDF  │   │Interview │   │Xiaoxiao  │   │.mp3 .mp4  │ │
│  │Text/CUA │   │Tutorial  │   │Yunyang   │   │cloudflare │ │
│  │Session  │   │Explainer │   │Azure/CV3 │   │local file │ │
│  └─────────┘   │Debate    │   └──────────┘   └───────────┘ │
│                └──────────┘                                  │
│                     │                                        │
│                     ▼                                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Optional: Video Render                    │   │
│  │  Script → HTML frames → Playwright → ffmpeg → .mp4   │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Core Types

```python
@dataclass
class Source:
    """Input source"""
    type: Literal["url", "pdf", "text", "cua_session"]
    content: str  # URL, file path, or raw text

@dataclass 
class Segment:
    """One segment of the generated script"""
    speaker: str      # "host" | "guest" | custom name
    voice: str        # TTS voice ID
    text: str         # spoken text
    duration: float   # estimated duration in seconds

@dataclass
class Script:
    """Full generated conversation script"""
    title: str
    style: Literal["interview", "tutorial", "explainer", "debate"]
    segments: list[Segment]
    total_duration: float

@dataclass
class MediaOutput:
    """Final output"""
    audio_path: str      # .mp3
    video_path: str | None  # .mp4 (optional)
    public_url: str | None  # cloudflared URL
    script: Script
    metadata: dict
```

## Component Interfaces

### 1. Ingest Layer

```python
class Ingester:
    def ingest(self, sources: list[Source]) -> str:
        """Extract clean text from sources. Returns concatenated text."""
    
    def ingest_url(self, url: str) -> str:
        """Fetch + extract text from URL (trafilatura)"""
    
    def ingest_pdf(self, path: str) -> str:
        """Extract text from PDF (pdfplumber)"""
```

### 2. Compose Layer (LLM)

```python
class Composer:
    PROMPTS = {
        "interview": "双主持访谈，一人提问一人深度解答...",
        "tutorial": "单人教学，步骤式讲解...",
        "explainer": "单人解说，概念拆解...",
        "debate": "双人辩论，正反方交替...",
    }
    
    def compose(self, text: str, style: str, voice_map: dict) -> Script:
        """Generate script from source text using LLM"""
    
    def _chunk_text(self, text: str) -> list[str]:
        """Split long text into LLM-friendly chunks"""
```

### 3. Synthesize Layer (TTS)

```python
class Synthesizer:
    VOICES = {
        "xiaoxiao": "zh-CN-XiaoxiaoNeural",
        "yunyang": "zh-CN-YunyangNeural",
        # extensible: Azure, CosyVoice, etc.
    }
    
    def synthesize(self, script: Script) -> str:
        """Generate audio for all segments → concat → return .mp3 path"""
    
    def _speak_segment(self, text: str, voice: str) -> bytes:
        """Generate audio for single segment"""
    
    def _concat_audio(self, segments: list[bytes]) -> bytes:
        """ffmpeg concat demuxer"""
```

### 4. Render Layer (Video)

```python
class Renderer:
    TEMPLATES = {
        "title": "<h1>{text}</h1>",
        "code": "<pre>{text}</pre>",
        "bullet": "<ul>{items}</ul>",
    }
    
    def render(self, script: Script, audio_path: str) -> str:
        """Generate video: frames rendered per segment, synced to audio"""
    
    def _render_frames(self, segments: list[Segment]) -> list[str]:
        """Playwright screenshots of HTML frames"""
    
    def _compose_video(self, frames: list[str], audio_path: str) -> str:
        """ffmpeg: frames → video + audio → .mp4"""
```

### 5. Publish Layer

```python
class Publisher:
    def publish(self, output: MediaOutput) -> MediaOutput:
        """Start cloudflared tunnel, return public URL"""
    
    def serve_dir(self, dir_path: str) -> str:
        """HTTP server + cloudflared → public URL"""
```

## MCP Server Tools

```yaml
tools:
  - generate_podcast:
      description: "Generate audio podcast from content"
      parameters:
        sources: list[Source]
        style: "interview" | "tutorial" | "explainer" | "debate"
        voices: dict  # speaker → voice mapping
  
  - generate_video:
      description: "Generate video with frames from content"
      parameters:
        sources: list[Source]
        style: str
        voices: dict
        frame_count: int = 4
  
  - list_voices:
      description: "List available TTS voices"
  
  - record_tutorial:
      description: "Record CUA session as tutorial video"
      parameters:
        task: str  # What the CUA should do
        narration_style: str = "tutorial"

  - publish:
      description: "Publish output via cloudflared"
      parameters:
        path: str
```

## Directory Structure

```
media-forge/
├── openspec/
│   └── changes/mvp/
│       ├── proposal.md
│       ├── design.md
│       ├── specs/
│       │   ├── ingest/spec.md
│       │   ├── compose/spec.md
│       │   ├── synthesize/spec.md
│       │   ├── render/spec.md
│       │   └── publish/spec.md
│       └── tasks.md
├── mediaforge/
│   ├── __init__.py
│   ├── ingest.py
│   ├── compose.py
│   ├── synthesize.py
│   ├── render.py
│   ├── publish.py
│   └── types.py
├── mcp/
│   └── server.py
├── skills/
│   └── media-forge/SKILL.md
├── pyproject.toml
└── README.md
```

## Dependencies

```toml
[project]
dependencies = [
    "trafilatura>=2.0",      # URL text extraction
    "pdfplumber>=0.11",      # PDF text extraction
    "edge-tts>=6.1",         # TTS (default backend)
    "mcp>=1.0",              # MCP server framework
]

[project.optional-dependencies]
azure = ["azure-cognitiveservices-speech>=1.50"]
```

## Data Flow Example

```
User: "把这篇文章做成访谈播客"  [url: https://example.com/post]
  │
  ▼
Ingester.ingest_url(url)
  → trafilatura extracts clean text (~3000 words)
  │
  ▼
Composer.compose(text, style="interview", voices={"host":"xiaoxiao","expert":"yunyang"})
  → LLM generates 8-segment interview script
  → Script object: [Segment(speaker="host", voice="xiaoxiao", text="..."), ...]
  │
  ▼
Synthesizer.synthesize(script)
  → edge-tts generates 8 MP3 segments
  → ffmpeg concat → podcast.mp3 (524KB, 90s)
  │
  ▼
Publisher.publish(output)
  → HTTP server + cloudflared → https://xxx.trycloudflare.com/podcast.mp3
  │
  ▼
Output: MediaOutput(audio_path="/tmp/podcast.mp3", public_url="https://...")
```
