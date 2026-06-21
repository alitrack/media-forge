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


# ── Progress Callback ──────────────────────────────────────

from typing import Protocol, runtime_checkable  # noqa: E402


@runtime_checkable
class ProgressCallback(Protocol):
    """Callback for long-running operation progress.

    Called during TTS generation, frame capture, and export encoding.
    """

    def __call__(
        self, stage: str, current: int, total: int, message: str = ""
    ) -> None:
        """Report progress.

        Args:
            stage: 'tts' | 'capture' | 'ffmpeg' | 'export'
            current: Items completed so far.
            total: Total items. May be 0 if unknown.
            message: Human-readable description (optional).
        """
        ...


# ── Frame Styling ──────────────────────────────────────────

@dataclass
class FrameStyle:
    """Visual styling for rendered video frames.

    Injected as CSS variables into Hyperframes HTML templates.
    Inspired by Recordly's frame styling system (gradients, shadows, corners).
    """

    # Background
    background_type: str = "solid"  # "solid" | "gradient" | "image"
    background_color: str = "#1a1a2e"
    gradient_colors: list = field(default_factory=lambda: ["#1a1a2e", "#16213e"])
    gradient_angle: int = 135  # degrees

    # Frame geometry
    aspect_ratio: str = "16:9"  # "16:9" | "1:1" | "9:16" | "4:3"
    border_radius: int = 0  # px, 0 = square corners
    use_squircle: bool = False  # iOS-style continuous curve
    padding: int = 40  # px around content

    # Shadow
    shadow_enabled: bool = False
    shadow_color: str = "rgba(0,0,0,0.4)"
    shadow_blur: int = 20
    shadow_offset_x: int = 0
    shadow_offset_y: int = 8

    # Blur
    background_blur: int = 0  # px, 0 = no blur

    def to_dict(self) -> dict:
        """Serialize for session files."""
        return {
            "background_type": self.background_type,
            "background_color": self.background_color,
            "gradient_colors": self.gradient_colors,
            "gradient_angle": self.gradient_angle,
            "aspect_ratio": self.aspect_ratio,
            "border_radius": self.border_radius,
            "use_squircle": self.use_squircle,
            "padding": self.padding,
            "shadow_enabled": self.shadow_enabled,
            "shadow_color": self.shadow_color,
            "shadow_blur": self.shadow_blur,
            "shadow_offset_x": self.shadow_offset_x,
            "shadow_offset_y": self.shadow_offset_y,
            "background_blur": self.background_blur,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FrameStyle":
        """Deserialize from session file."""
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# Aspect ratio presets: name → (width, height)
ASPECT_RATIOS: dict[str, tuple[int, int]] = {
    "16:9": (1920, 1080),
    "1:1": (1080, 1080),
    "9:16": (1080, 1920),
    "4:3": (1440, 1080),
}

# Pre-built style presets
STYLE_PRESETS: dict[str, FrameStyle] = {
    "clean": FrameStyle(
        background_color="#ffffff",
        shadow_enabled=False,
        border_radius=0,
        padding=60,
    ),
    "dark": FrameStyle(
        background_color="#1a1a2e",
        shadow_enabled=True,
        shadow_blur=30,
        border_radius=16,
        padding=40,
    ),
    "gradient": FrameStyle(
        background_type="gradient",
        gradient_colors=["#1a1a2e", "#e94560"],
        gradient_angle=135,
        shadow_enabled=True,
        shadow_blur=20,
        border_radius=16,
        padding=40,
    ),
}

