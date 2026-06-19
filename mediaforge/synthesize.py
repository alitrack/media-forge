"""Audio synthesis layer — TTS per segment + ffmpeg concatenation.

Supports multiple backends via VoiceCast abstraction.
Default: edge-tts (free, no registration).
"""

import asyncio
import os
import subprocess
import tempfile
from typing import Optional

import edge_tts

from mediaforge.types import Script, Segment, TTSBackend


class SynthesizeError(Exception):
    """Audio generation failed."""
    pass


# ── Voice Registry ────────────────────────────────────────

VOICE_REGISTRY: dict[str, dict[str, str]] = {
    "edge": {
        "xiaoxiao": "zh-CN-XiaoxiaoNeural",
        "yunyang": "zh-CN-YunyangNeural",
        "xiaoxiao_multilingual": "zh-CN-XiaoxiaoMultilingualNeural",
        "yunyang_multilingual": "zh-CN-YunyangMultilingualNeural",
    },
    # Future: azure, cosyvoice
}


# ── Synthesizer ───────────────────────────────────────────

class Synthesizer:
    """Generate audio from scripts using TTS + ffmpeg."""

    def __init__(
        self,
        backend: str = "edge",
        proxy: Optional[str] = None,
    ):
        self.backend = backend
        self.proxy = proxy or _default_proxy()

    def synthesize(self, script: Script, output_path: str) -> str:
        """Generate MP3 from script. Returns output_path."""
        if not script.segments:
            raise SynthesizeError("Script has no segments")

        # Generate each segment as MP3
        segment_files = asyncio.run(self._generate_segments(script.segments, output_path))

        # Concatenate
        if len(segment_files) == 1:
            # Single segment — just copy
            import shutil
            shutil.copy(segment_files[0], output_path)
        else:
            self._concat(segment_files, output_path)

        # Cleanup temp files
        for f in segment_files:
            try:
                os.unlink(f)
            except OSError:
                pass

        return output_path

    async def _generate_segments(
        self, segments: list[Segment], output_path: str
    ) -> list[str]:
        """Generate MP3 for each segment in parallel batches."""
        out_dir = os.path.dirname(output_path) or "."
        files = []

        # Generate sequentially to respect rate limits
        for i, seg in enumerate(segments):
            voice_id = self._resolve_voice(seg.voice_id)
            segment_path = os.path.join(out_dir, f".seg_{i:03d}.mp3")
            await self._speak(seg.text, voice_id, segment_path)
            files.append(segment_path)

        return files

    async def _speak(self, text: str, voice: str, output_path: str) -> None:
        """Generate audio for a single text segment."""
        if self.backend == "edge":
            await self._speak_edge(text, voice, output_path)
        else:
            raise SynthesizeError(f"Unknown backend: {self.backend}")

    async def _speak_edge(self, text: str, voice: str, output_path: str) -> None:
        """edge-tts: retry 3x with exponential backoff."""
        last_error = None
        for attempt in range(3):
            try:
                comm = edge_tts.Communicate(text, voice, proxy=self.proxy)
                await comm.save(output_path)
                if os.path.getsize(output_path) > 0:
                    return
                raise SynthesizeError("Zero-byte audio generated")
            except Exception as e:
                last_error = e
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)

        raise SynthesizeError(f"edge-tts failed after 3 attempts: {last_error}")

    def _resolve_voice(self, voice_id: str) -> str:
        """Resolve short name → full voice ID via registry."""
        registry = VOICE_REGISTRY.get(self.backend, {})
        return registry.get(voice_id, voice_id)

    def _concat(self, files: list[str], output_path: str) -> None:
        """Concatenate MP3 files using ffmpeg concat demuxer."""
        concat_list = os.path.join(
            os.path.dirname(output_path) or ".",
            ".concat.txt",
        )
        with open(concat_list, "w") as f:
            for path in files:
                f.write(f"file '{path}'\n")

        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", concat_list,
                "-c", "copy",
                output_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        try:
            os.unlink(concat_list)
        except OSError:
            pass

        if result.returncode != 0:
            raise SynthesizeError(f"ffmpeg concat failed: {result.stderr[:200]}")

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise SynthesizeError("ffmpeg produced empty output")


def _default_proxy() -> Optional[str]:
    """Detect default proxy from environment."""
    for var in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        val = os.environ.get(var)
        if val:
            return val
    return None
