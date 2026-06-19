"""Core types for the MediaForge pipeline."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SourceType(str, Enum):
    URL = "url"
    PDF = "pdf"
    TEXT = "text"
    OFFICE = "office"
    IMAGE = "image"
    CUA_SESSION = "cua_session"


class ContentStyle(str, Enum):
    INTERVIEW = "interview"      # 双主持一问一答
    TUTORIAL = "tutorial"        # 单人步骤教学
    EXPLAINER = "explainer"      # 单人概念解说
    DEBATE = "debate"            # 双人正反辩论


class TTSBackend(str, Enum):
    EDGE = "edge"                # edge-tts (default, free)
    AZURE = "azure"              # Azure Speech (commercial license)
    COSYVOICE = "cosyvoice"      # CosyVoice 3 (Apache 2.0, local)


@dataclass
class Source:
    """Content input source."""
    type: SourceType
    content: str  # URL string, file path, or raw text

    def __post_init__(self):
        if isinstance(self.type, str):
            self.type = SourceType(self.type)


@dataclass
class VoiceConfig:
    """Voice configuration for a speaker."""
    speaker: str       # e.g. "host", "expert"
    voice_id: str      # e.g. "zh-CN-XiaoxiaoNeural"
    backend: TTSBackend = TTSBackend.EDGE


@dataclass
class Segment:
    """One segment of the generated conversation script."""
    speaker: str          # speaker name
    voice_id: str         # TTS voice ID
    text: str             # spoken text
    estimated_duration: float = 0.0  # seconds, estimated as len(text)/4

    def __post_init__(self):
        if self.estimated_duration <= 0:
            # Chinese: ~4 chars/second
            self.estimated_duration = max(len(self.text) / 4.0, 1.0)


@dataclass
class Script:
    """Full generated conversation script."""
    title: str
    style: ContentStyle
    segments: list[Segment] = field(default_factory=list)
    source_summary: str = ""  # LLM summary of source content

    @property
    def total_duration(self) -> float:
        return sum(s.estimated_duration for s in self.segments)

    @property
    def segment_count(self) -> int:
        return len(self.segments)

    def add_segment(self, speaker: str, voice_id: str, text: str) -> Segment:
        seg = Segment(speaker=speaker, voice_id=voice_id, text=text)
        self.segments.append(seg)
        return seg


@dataclass
class MediaOutput:
    """Final generated media output."""
    audio_path: str                   # .mp3 file path
    video_path: Optional[str] = None  # .mp4 file path (if rendered)
    public_url: Optional[str] = None  # cloudflared URL (if published)
    script: Optional[Script] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class IngestResult:
    """Result from the ingest stage."""
    content: str                        # Markdown content
    backend_used: str                   # e.g. "pdfmux", "trafilatura"
    confidence: float = 1.0             # 0.0-1.0
    warnings: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)  # page_count, language, etc.


@dataclass
class SegmentTiming:
    """Per-segment timing information for animation rendering."""
    segment: Segment
    start: float        # start time in seconds
    duration: float     # duration in seconds

