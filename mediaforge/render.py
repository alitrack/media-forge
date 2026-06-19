"""Video render layer — HTML frames + Playwright screenshots + ffmpeg compositing.

Takes a Script + audio path, generates visual frames synced to audio.
"""

import os
import subprocess
from pathlib import Path

from mediaforge.types import Script, Segment


class RenderError(Exception):
    """Video rendering failed."""
    pass


# ── Frame Templates ───────────────────────────────────────

FRAME_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    width: 1920px; height: 1080px;
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    color: #e0e0e0;
    font-family: 'PingFang SC', 'Microsoft YaHei', system-ui, sans-serif;
    display: flex; flex-direction: column;
    justify-content: center; align-items: center;
    overflow: hidden;
    position: relative;
  }}
  .accent {{ position:absolute; top:0; left:0; width:6px; height:100%;
    background: linear-gradient(180deg, #e94560, #f5a623); }}
  h1 {{ font-size: 48px; color: #e94560; margin-bottom: 24px; max-width: 85%; text-align: center; }}
  .speaker {{ font-size: 22px; color: #f5a623; margin-bottom: 16px; }}
  p {{ font-size: 32px; line-height: 1.6; max-width: 80%; text-align: center; opacity: 0.9; }}
  .counter {{ position:absolute; bottom:32px; right:40px;
    font-size: 18px; color:#555; }}
  .dots {{ position:absolute; top:32px; right:40px; display:flex; gap:8px; }}
  .dot {{ width:10px; height:10px; border-radius:50%; background:#333; }}
  .dot.active {{ background:#e94560; }}
</style>
</head>
<body>
  <div class="accent"></div>
  <div class="dots">{dots}</div>
  <h1>{title}</h1>
  <div class="speaker">{speaker}</div>
  <p>{text}</p>
  <div class="counter">{current}/{total}</div>
</body>
</html>"""


# ── Renderer ──────────────────────────────────────────────

class Renderer:
    """Render Script + audio into MP4 video with HTML frames."""

    def __init__(
        self,
        chromium_path: str | None = None,
        width: int = 1920,
        height: int = 1080,
        fps: int = 1,
    ):
        self.width = width
        self.height = height
        self.fps = fps
        self.chromium_path = chromium_path or self._find_chromium()

    @staticmethod
    def _find_chromium() -> str:
        """Auto-detect Playwright-bundled or system chromium."""
        import glob
        # Playwright bundled chromium (preferred – no sandbox issues)
        playwright_dirs = glob.glob(
            os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")
        )
        if playwright_dirs:
            return sorted(playwright_dirs, reverse=True)[0]
        # Fallback to snap chromium
        snap = "/snap/bin/chromium"
        if os.path.isfile(snap):
            return snap
        raise RenderError("No chromium found. Run: playwright install chromium")

    def render(
        self,
        script: Script,
        audio_path: str,
        output_path: str,
        frame_count: int = 4,
    ) -> str:
        """Generate video from script and audio. Returns output_path."""
        if not script.segments:
            raise RenderError("Script has no segments")

        work_dir = os.path.join(
            os.path.dirname(output_path) or "/tmp",
            ".mediaforge_frames",
        )
        os.makedirs(work_dir, exist_ok=True)

        # 1. Group segments into frame_count groups
        groups = self._group_segments(script.segments, frame_count)

        # 2. Generate HTML for each group
        html_files = []
        for i, group in enumerate(groups):
            html = self._build_frame_html(script, group, i, frame_count)
            html_path = os.path.join(work_dir, f"frame_{i:02d}.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            html_files.append(html_path)

        # 3. Screenshot each frame via Playwright
        screenshot_paths = self._screenshot_frames(html_files, work_dir)

        # 4. Calculate frame durations from audio
        audio_duration = self._get_audio_duration(audio_path)
        frame_duration = audio_duration / frame_count

        # 5. Build video from frames
        frames_video = os.path.join(work_dir, "frames.mp4")
        self._frames_to_video(screenshot_paths, frame_duration, frames_video)

        # 6. Mux video + audio
        self._mux_audio(frames_video, audio_path, output_path)

        return output_path

    def _group_segments(
        self, segments: list[Segment], frame_count: int
    ) -> list[list[Segment]]:
        """Distribute segments evenly across frame_count groups."""
        if frame_count <= 0:
            frame_count = 1
        if frame_count >= len(segments):
            # Each segment gets its own frame
            return [[s] for s in segments]

        # Even distribution
        groups: list[list[Segment]] = [[] for _ in range(frame_count)]
        for i, seg in enumerate(segments):
            idx = i * frame_count // len(segments)
            groups[min(idx, frame_count - 1)].append(seg)

        return [g for g in groups if g]

    def _build_frame_html(
        self,
        script: Script,
        group: list[Segment],
        idx: int,
        total: int,
    ) -> str:
        """Build HTML for one frame from a group of segments."""
        # Combine segment texts
        if len(group) == 1:
            text = group[0].text
            speaker = self._speaker_label(group[0].speaker)
        else:
            text = " ".join(s.text for s in group)
            speaker = self._speaker_label(group[0].speaker)

        title = script.title or "MediaForge"

        # Build navigation dots
        dots = "".join(
            f'<div class="dot{" active" if i == idx else ""}"></div>'
            for i in range(total)
        )

        return FRAME_TEMPLATE.format(
            title=title,
            speaker=speaker,
            text=text[:200],  # keep frame text short
            dots=dots,
            current=idx + 1,
            total=total,
        )

    def _speaker_label(self, speaker: str) -> str:
        """Map speaker ID to display label."""
        labels = {
            "host": "🎤 主持人",
            "expert": "🎙️ 专家",
            "pro": "⏺️ 正方",
            "con": "⏺️ 反方",
        }
        return labels.get(speaker, f"🎙️ {speaker}")

    def _screenshot_frames(self, html_files: list[str], work_dir: str) -> list[str]:
        """Take Playwright screenshots of each HTML frame."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RenderError(
                "Playwright not installed. Run: pip install playwright && playwright install chromium"
            )

        screenshot_paths = []

        with sync_playwright() as p:
            browser = p.chromium.launch(
                executable_path=self.chromium_path,
                headless=True,
            )
            page = browser.new_page(
                viewport={"width": self.width, "height": self.height},
            )

            for i, html_file in enumerate(html_files):
                page.goto(f"file://{html_file}", wait_until="networkidle")
                screenshot_path = os.path.join(work_dir, f"frame_{i:02d}.png")
                page.screenshot(path=screenshot_path, full_page=False)
                screenshot_paths.append(screenshot_path)

            browser.close()

        return screenshot_paths

    def _get_audio_duration(self, audio_path: str) -> float:
        """Get audio duration in seconds using ffprobe."""
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                audio_path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return 30.0  # conservative default
        try:
            return float(result.stdout.strip())
        except ValueError:
            return 30.0

    def _frames_to_video(
        self, frames: list[str], duration_per_frame: float, output_path: str
    ) -> None:
        """Convert frame images to video with per-frame duration."""
        # Write ffmpeg concat file with duration per image
        concat_file = os.path.join(
            os.path.dirname(output_path), ".frame_concat.txt"
        )
        with open(concat_file, "w") as f:
            for frame in frames:
                f.write(f"file '{frame}'\n")
                f.write(f"duration {duration_per_frame:.3f}\n")
            # Last frame needs to be repeated for ffmpeg concat
            f.write(f"file '{frames[-1]}'\n")

        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", concat_file,
                "-vsync", "vfr",
                "-pix_fmt", "yuv420p",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                output_path,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        try:
            os.unlink(concat_file)
        except OSError:
            pass

        if result.returncode != 0:
            raise RenderError(f"ffmpeg frames→video failed: {result.stderr[:300]}")

    def _mux_audio(
        self, video_path: str, audio_path: str, output_path: str
    ) -> None:
        """Mux audio track into video."""
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", video_path,
                "-i", audio_path,
                "-c:v", "copy",
                "-c:a", "aac",
                "-shortest",
                "-map", "0:v:0",
                "-map", "1:a:0",
                output_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            raise RenderError(f"ffmpeg mux failed: {result.stderr[:300]}")

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RenderError("ffmpeg produced empty video")
