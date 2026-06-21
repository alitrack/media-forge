"""MediaForge — Content-to-multi-format media pipeline.

Five-stage pipeline:
    Ingest → Compose → Synthesize → Render → Publish

Input: URL, PDF, text, CUA sessions
Output: MP3 podcasts, MP4 videos, cloudflared URLs
"""

__version__ = "0.1.0"

from mediaforge.types import Source, Segment, Script, MediaOutput, ContentStyle, FrameStyle, STYLE_PRESETS, ASPECT_RATIOS, ProgressCallback
from mediaforge.ingest import Ingester, IngestError
from mediaforge.compose import Composer, ComposeError
from mediaforge.synthesize import Synthesizer, SynthesizeError
from mediaforge.render import Renderer, RenderError
from mediaforge.publish import Publisher, PublishError

__all__ = [
    "Source", "Segment", "Script", "MediaOutput", "ContentStyle",
    "FrameStyle", "STYLE_PRESETS", "ASPECT_RATIOS",
    "Ingester", "IngestError",
    "Composer", "ComposeError",
    "Synthesizer", "SynthesizeError",
    "Renderer", "RenderError",
    "Publisher", "PublishError",
]
