"""Audio synthesis layer — TTS per segment + ffmpeg concatenation.

Supports multiple backends via backend dispatch.
Default: edge-tts (free, no registration).
Azure: commercial-quality TTS with SSML support.
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
    "azure": {
        "xiaoxiao": "zh-CN-XiaoxiaoNeural",
        "yunyang": "zh-CN-YunyangNeural",
        "xiaoxiao_multilingual": "zh-CN-XiaoxiaoMultilingualNeural",
        "yunxi": "zh-CN-YunxiNeural",
        "xiaoyi": "zh-CN-XiaoyiNeural",
        "yunjian": "zh-CN-YunjianNeural",
        # English voices
        "aria": "en-US-AriaNeural",
        "jenny": "en-US-JennyNeural",
        "guy": "en-US-GuyNeural",
    },
    # Future: cosyvoice
}


# ── Synthesizer ───────────────────────────────────────────

class Synthesizer:
    """Generate audio from scripts using TTS + ffmpeg."""

    def __init__(
        self,
        backend: str = "edge",
        proxy: Optional[str] = None,
        azure_speech_key: Optional[str] = None,
        azure_speech_region: Optional[str] = None,
    ):
        self.backend = backend
        self.proxy = proxy or _default_proxy()
        # Azure credentials: constructor arg > env var
        self.azure_speech_key = azure_speech_key or os.environ.get(
            "AZURE_SPEECH_KEY", ""
        )
        self.azure_speech_region = azure_speech_region or os.environ.get(
            "AZURE_SPEECH_REGION", ""
        )

    def synthesize(self, script: Script, output_path: str, on_progress=None) -> str:
        """Generate MP3 from script. Returns output_path."""
        if not script.segments:
            raise SynthesizeError("Script has no segments")

        # Generate each segment as MP3
        segment_files = asyncio.run(
            self._generate_segments(script.segments, output_path, on_progress)
        )

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
        self, segments: list[Segment], output_path: str, on_progress=None
    ) -> list[str]:
        """Generate MP3 for each segment in parallel batches."""
        out_dir = os.path.dirname(output_path) or "."
        files = []
        total = len(segments)

        # Generate sequentially to respect rate limits
        for i, seg in enumerate(segments):
            voice_id = self._resolve_voice(seg.voice_id)
            segment_path = os.path.join(out_dir, f".seg_{i:03d}.mp3")
            await self._speak(seg.text, voice_id, segment_path)
            files.append(segment_path)
            if on_progress:
                try:
                    on_progress("tts", i + 1, total,
                               f"Generating voice {i+1}/{total}")
                except Exception:
                    pass  # don't let progress callback break generation

        return files

    async def _speak(self, text: str, voice: str, output_path: str) -> None:
        """Generate audio for a single text segment."""
        if self.backend == "edge":
            await self._speak_edge(text, voice, output_path)
        elif self.backend == "azure":
            await self._speak_azure(text, voice, output_path)
        else:
            raise SynthesizeError(f"Unknown backend: {self.backend}")

    async def _speak_azure(self, text: str, voice: str, output_path: str) -> None:
        """Azure Cognitive Services TTS with SSML + retry."""
        if not self.azure_speech_key or not self.azure_speech_region:
            raise SynthesizeError(
                "Azure TTS requires AZURE_SPEECH_KEY and "
                "AZURE_SPEECH_REGION environment variables"
            )

        try:
            import azure.cognitiveservices.speech as speechsdk  # noqa: E402
        except ImportError:
            raise SynthesizeError(
                "Azure TTS requires azure-cognitiveservices-speech. "
                "Install: pip install azure-cognitiveservices-speech"
            )

        speech_config = speechsdk.SpeechConfig(
            subscription=self.azure_speech_key,
            region=self.azure_speech_region,
        )
        speech_config.speech_synthesis_voice_name = voice
        # Apply proxy if configured
        if self.proxy:
            speech_config.set_proxy(self.proxy, None, None)

        # Use SSML for better quality control
        ssml = (
            f'<speak version="1.0" '
            f'xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xml:lang="zh-CN">'
            f'<voice name="{voice}">{_escape_xml(text)}</voice>'
            f"</speak>"
        )

        synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=speech_config, audio_config=None
        )

        last_error = None
        for attempt in range(3):
            try:
                result = synthesizer.speak_ssml_async(ssml).get()
                if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                    with open(output_path, "wb") as f:
                        f.write(result.audio_data)
                    if os.path.getsize(output_path) > 0:
                        return
                    raise SynthesizeError("Azure produced zero-byte audio")
                elif result.reason == speechsdk.ResultReason.Canceled:
                    cancellation = result.cancellation_details
                    raise SynthesizeError(
                        f"Azure TTS canceled: "
                        f"{cancellation.cancellation_reason} — "
                        f"{cancellation.error_details}"
                    )
                else:
                    raise SynthesizeError(
                        f"Azure TTS unexpected result: {result.reason}"
                    )
            except Exception as e:
                last_error = e
                if attempt < 2:
                    await asyncio.sleep(2**attempt)
                # Retry on next iteration

        raise SynthesizeError(f"Azure TTS failed after 3 attempts: {last_error}")

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


def _escape_xml(text: str) -> str:
    """Escape special XML characters for SSML safety."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _default_proxy() -> Optional[str]:
    """Detect default proxy from environment."""
    for var in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        val = os.environ.get(var)
        if val:
            return val
    return None
