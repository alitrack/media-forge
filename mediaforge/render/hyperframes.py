"""Hyperframes render engine — CSS-animated video rendering.

Renders podcast scripts as smooth 30fps animation videos using:
  1. Character-count-based segment timing estimation
  2. LLM-generated animated HTML (CSS @keyframes + JS playback control)
  3. Playwright per-frame screenshot capture
  4. FFmpeg frame→video assembly + audio mux
"""

from __future__ import annotations

import json
import os
import glob
import re
import subprocess
import tempfile
from typing import ClassVar

from mediaforge.types import Script, Segment, SegmentTiming
from mediaforge.render.base import RenderError, register_engine


# ── Animation HTML Template ───────────────────────────────

ANIMATION_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    width: {width}px; height: {height}px;
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    color: #e0e0e0;
    font-family: 'PingFang SC', 'Microsoft YaHei', system-ui, sans-serif;
    overflow: hidden;
    position: relative;
  }}
  .accent {{ position:absolute; top:0; left:0; width:6px; height:100%;
    background: linear-gradient(180deg, #e94560, #f5a623); }}
  .title-bar {{
    position: absolute; top: 40px; left: 80px; right: 80px;
    font-size: 24px; color: #f5a623; opacity: 0.6;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }}
  .progress {{
    position: absolute; bottom: 24px; left: 80px; right: 80px;
    height: 3px; background: rgba(255,255,255,0.1); border-radius: 2px;
  }}
  .progress-bar {{
    height: 100%; background: #e94560; border-radius: 2px;
    transition: width 0.1s linear;
  }}
  .timeline {{
    position: absolute; top: 90px; left: 80px; right: 80px;
    display: flex; gap: 4px; height: 4px;
  }}
  .timeline-dot {{
    flex: 1; background: rgba(255,255,255,0.15); border-radius: 2px;
    transition: background 0.3s;
  }}
  .timeline-dot.active {{ background: #e94560; }}
  .timeline-dot.past {{ background: rgba(233,69,96,0.4); }}
  .seg-container {{
    position: absolute; top: 120px; left: 80px; right: 80px; bottom: 60px;
    display: flex; flex-direction: column; justify-content: center;
  }}
  .seg {{
    position: absolute; width: 100%;
    opacity: 0; transform: translateY(24px);
    transition: all 0.5s cubic-bezier(0.16, 1, 0.3, 1);
    pointer-events: none;
  }}
  .seg.active {{
    opacity: 1; transform: translateY(0); pointer-events: auto;
  }}
  .seg.past {{
    opacity: 0.3; transform: translateY(-12px);
  }}
  .speaker {{
    font-size: 22px; margin-bottom: 20px; opacity: 0.85;
  }}
  .text {{
    font-size: 36px; line-height: 1.6; max-width: 90%;
  }}
  .text .highlight {{
    color: #e94560; font-weight: 700;
    animation: pulse 0.6s ease-in-out infinite alternate;
  }}
  @keyframes pulse {{
    from {{ opacity: 0.8; }} to {{ opacity: 1; }}
  }}
  .counter {{
    position: absolute; bottom: 32px; right: 40px;
    font-size: 16px; color: rgba(255,255,255,0.3);
  }}
</style>
</head>
<body>
  <div class="accent"></div>
  <div class="title-bar">{title}</div>
  <div class="timeline">{timeline_dots}</div>
  <div class="seg-container">
{segments_html}
  </div>
  <div class="progress"><div class="progress-bar" id="progressBar"></div></div>
  <div class="counter"><span id="segIdx">0</span> / {total_segs}</div>

<script>
const segments = {segment_data};
const totalDuration = {total_duration};

function advanceAnimation(currentTime) {{
    let activeIdx = -1;
    for (let i = 0; i < segments.length; i++) {{
        const seg = document.getElementById('seg' + i);
        if (!seg) continue;
        if (currentTime >= segments[i].start && currentTime < segments[i].end) {{
            seg.classList.add('active');
            seg.classList.remove('past');
            activeIdx = i;
        }} else if (currentTime >= segments[i].end) {{
            seg.classList.add('past');
            seg.classList.remove('active');
        }} else {{
            seg.classList.remove('active', 'past');
        }}
    }}
    // Progress bar
    const pct = Math.min(100, (currentTime / totalDuration) * 100);
    document.getElementById('progressBar').style.width = pct + '%';
    // Segment counter
    if (activeIdx >= 0) {{
        document.getElementById('segIdx').textContent = activeIdx + 1;
    }}
    // Timeline dots
    for (let i = 0; i < segments.length; i++) {{
        const dot = document.getElementById('td' + i);
        if (!dot) continue;
        dot.className = 'timeline-dot';
        if (currentTime >= segments[i].end) dot.classList.add('past');
        else if (currentTime >= segments[i].start) dot.classList.add('active');
    }}
}}
</script>
</body>
</html>"""


# ── Speaker Labels ─────────────────────────────────────────

SPEAKER_LABELS = {
    "host": "🎤 主持人",
    "expert": "🎙️ 专家",
    "pro": "⏺️ 正方",
    "con": "⏺️ 反方",
}


# ── Hyperframes Engine ─────────────────────────────────────

class Hyperframes:
    """CSS-animated video render engine."""

    name: ClassVar[str] = "hyperframes"

    def __init__(
        self,
        fps: int = 30,
        width: int = 1920,
        height: int = 1080,
        chromium_path: str | None = None,
    ):
        self.fps = max(15, min(60, fps))
        self.width = width
        self.height = height
        self.chromium_path = chromium_path or self._find_chromium()

    @staticmethod
    def _find_chromium() -> str:
        playwright_dirs = glob.glob(
            os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome")
        )
        if playwright_dirs:
            return sorted(playwright_dirs, reverse=True)[0]
        snap = "/snap/bin/chromium"
        if os.path.isfile(snap):
            return snap
        raise RenderError("No chromium found. Run: playwright install chromium")

    @classmethod
    def available(cls) -> bool:
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
            return True
        except Exception:
            return False

    # ── Public API ──────────────────────────────────────

    def render(
        self,
        script: Script,
        audio_path: str,
        output_path: str,
        **kwargs,
    ) -> str:
        """Render script + audio into animated video."""
        if not script.segments:
            raise RenderError("Script has no segments")

        # 1. Timing estimation
        audio_duration = self._get_audio_duration(audio_path)
        timings = self._estimate_timing(script.segments, audio_duration)

        # 2. Build animation HTML
        html = self._build_animation_html(script, timings)

        # 3. Capture frames
        total_frames = int(audio_duration * self.fps)
        work_dir = tempfile.mkdtemp(prefix="mediaforge_hyperframes_")
        frames = self._capture_frames(html, total_frames, work_dir)

        # 4. Frames → silent video
        silent_mp4 = os.path.join(work_dir, "silent.mp4")
        self._frames_to_video(frames, silent_mp4)

        # 5. Mux audio
        self._mux_audio(silent_mp4, audio_path, output_path)

        return output_path

    # ── Step 1: Timing ──────────────────────────────────

    def _estimate_timing(
        self, segments: list[Segment], audio_duration: float
    ) -> list[SegmentTiming]:
        """Distribute audio duration across segments by character count."""
        chars = [len(s.text) for s in segments]
        total = max(1, sum(chars))
        elapsed = 0.0
        timings = []
        for seg, n_chars in zip(segments, chars):
            dur = (n_chars / total) * audio_duration
            timings.append(SegmentTiming(segment=seg, start=elapsed, duration=dur))
            elapsed += dur
        return timings

    # ── Step 2: Animation HTML ──────────────────────────

    def _build_animation_html(self, script: Script, timings: list[SegmentTiming]) -> str:
        """Generate self-contained animated HTML page."""
        total_duration = timings[-1].start + timings[-1].duration if timings else 0

        # Build segment HTML blocks
        segments_html_parts = []
        for i, t in enumerate(timings):
            speaker = t.segment.speaker
            label = SPEAKER_LABELS.get(speaker, f"🎙️ {speaker}")
            text = t.segment.text[:200]
            segments_html_parts.append(
                f'  <div class="seg" id="seg{i}" '
                f'data-start="{t.start:.2f}" data-end="{t.start + t.duration:.2f}">\n'
                f'    <div class="speaker">{label}</div>\n'
                f'    <div class="text">{self._highlight_text(text)}</div>\n'
                f'  </div>'
            )

        # Timeline dots
        dots = "".join(
            f'<div class="timeline-dot" id="td{i}"></div>'
            for i in range(len(timings))
        )

        # Segment data for JS
        import json
        seg_data = json.dumps([
            {"start": t.start, "end": t.start + t.duration}
            for t in timings
        ])

        return ANIMATION_TEMPLATE.format(
            width=self.width,
            height=self.height,
            title=script.title or "MediaForge",
            timeline_dots=dots,
            segments_html="\n".join(segments_html_parts),
            total_segs=len(timings),
            segment_data=seg_data,
            total_duration=total_duration,
        )

    @staticmethod
    def _highlight_text(text: str) -> str:
        """Wrap key terms in highlight spans."""
        import re
        # Highlight quoted terms and bold markers
        text = re.sub(r'「(.+?)」', r'<span class="highlight">\1</span>', text)
        text = re.sub(r'\*\*(.+?)\*\*', r'<span class="highlight">\1</span>', text)
        return text

    # ── Step 3: Frame Capture ───────────────────────────

    def _capture_frames(
        self, html: str, total_frames: int, work_dir: str
    ) -> list[str]:
        """Capture each frame via Playwright at specified FPS."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RenderError("Playwright not installed. Run: pip install playwright && playwright install chromium")

        # Write HTML to file so Playwright can load it
        html_path = os.path.join(work_dir, "animation.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

        frames_dir = os.path.join(work_dir, "frames")
        os.makedirs(frames_dir, exist_ok=True)

        frame_paths = []
        frame_interval = max(0.016, 1.0 / self.fps)  # min 16ms

        with sync_playwright() as p:
            browser = p.chromium.launch(
                executable_path=self.chromium_path,
                headless=True,
            )
            page = browser.new_page(
                viewport={"width": self.width, "height": self.height},
            )

            try:
                page.goto(f"file://{html_path}", wait_until="networkidle")
                # Wait for initial render
                page.wait_for_timeout(200)

                for i in range(total_frames):
                    t = i / self.fps
                    page.evaluate(f"advanceAnimation({t})")
                    page.wait_for_timeout(int(frame_interval * 1000))
                    png_path = os.path.join(frames_dir, f"frame_{i:06d}.png")
                    page.screenshot(path=png_path, full_page=False)
                    frame_paths.append(png_path)
            finally:
                browser.close()

        return frame_paths

    # ── Step 4-5: FFmpeg Assembly ───────────────────────

    def _frames_to_video(self, frames: list[str], output_path: str) -> None:
        """Convert frame sequence to MP4 video."""
        if not frames:
            raise RenderError("No frames captured")

        # Use ffmpeg image sequence input
        frames_dir = os.path.dirname(frames[0])
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-framerate", str(self.fps),
                "-i", os.path.join(frames_dir, "frame_%06d.png"),
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                output_path,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
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

    @staticmethod
    def _get_audio_duration(audio_path: str) -> float:
        """Get audio duration via ffprobe."""
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
            return 30.0
        try:
            return float(result.stdout.strip())
        except ValueError:
            return 30.0


register_engine(Hyperframes)
