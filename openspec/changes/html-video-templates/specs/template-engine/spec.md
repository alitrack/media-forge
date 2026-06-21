# Spec: html-video Template Engine

## Purpose

实现一个新的 `RenderEngine`，消费 html-video 开源项目的 23 套 HTML/CSS/GSAP 模板，让 MediaForge 用户可以选择不同视觉风格生成视频。

## Contract

1. `HtmlVideoTemplateEngine` 实现 `RenderEngine` Protocol (`name`, `render()`, `available()`)
2. `render(script, audio_path, output_path)` 返回有效 MP4 文件路径
3. `get_render_engine("html-video-templates", template="warm-grain")` 返回引擎实例
4. 模板名无效/不可用 → `RenderError`
5. 生成的 MP4 可被 ffprobe 解析，时长 ≥ 0.5s

## Details

### 模板加载
- 从 `TEMPLATE_DIR` 加载 `{template}/index.html`
- 注入 `script.title` / `segments[n].text` 到占位符
- HTML 完整自包含（离线字体 + 本地 JS）

### Playwright 渲染
- 启动 headless Chromium
- 加载注入后的 HTML
- `recordVideo` 录制 → webm
- 等待 `document.fonts.ready` + GSAP 动画完成
- 裁切 FOUT 死区（与 hyperframes.py 的 freeze→wait→unfreeze 逻辑一致）

### FFmpeg 后处理
- webm → mp4 转码
- mux 音频轨道
- 输出到 `output_path`

### 模板发现
```python
@staticmethod
def list_templates() -> dict[str, str]:
    """扫描 TEMPLATE_DIR，返回 {name: description}"""
```

## Boundary Cases

| 场景 | 行为 |
|---|---|
| 模板目录不存在 | `available()` → `False` |
| 模板名不存在 | `render()` → `RenderError("Unknown template: 'xxx'")` |
| 模板 HTML 有 JS 错误 | Playwright `pageerror` 事件 → `RenderError` with JS 错误信息 |
| 音频文件不存在 | `RenderError("Audio file not found: ...")` |
| 空 Script (0 segments) | 占位符填默认文本，正常渲染 |
| Playwright 进程僵死 | 120s 超时 → `RenderError("Render timed out")` |
| 字体离线化未完成 | 模板使用系统字体栈 fallback，正常渲染但样式退化 |
