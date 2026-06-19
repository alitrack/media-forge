# Spec: Render

## Purpose

将脚本和音频合成为带画面帧的 MP4 视频。非必选——音频优先。

## Contract

### `render(script: Script, audio_path: str, frame_count: int = 4) -> str`

- **Output**: .mp4 文件路径
- **Process**: 
  1. 按 frame_count 均分 segments
  2. 每组 segment → 生成 HTML 帧（标题 + 要点）
  3. Playwright 截图每帧
  4. 按音频时长分配每帧显示时间
  5. ffmpeg: frames → video → +audio → final .mp4

### Frame Templates

```python
TEMPLATES = {
    "title": "<div class='frame'><h1>{title}</h1><p>{subtitle}<p></div>",
    "bullet": "<div class='frame'><h2>{title}</h2><ul>{items}</ul></div>",
    "code": "<div class='frame'><h2>{title}</h2><pre>{code}</pre></div>",
    "comparison": "<div class='frame'><h2>{title}</h2><table>{rows}</table></div>",
}
```

### Video Spec

- Resolution: 1920×1080
- FPS: 1（静态帧）
- Codec: H.264 (libx264)
- Audio: AAC from source MP3
- Background: 深色 (#1a1a2e) + 紫金点缀

### Requirements

- Chromium 可执行（`PUPPETEER_EXECUTABLE_PATH` 或 snap chromium）
- ffmpeg 6.0+

## Boundary Cases

- frame_count=0 → 只返回音频，不渲染
- 单 segment → 多帧用同一内容的不同排版
- 超长音频 → 帧均分，最小帧长 3s
- Chromium 不可用 → 抛 RenderError
