# Spec: CLI Template Selection & Export

## Purpose

为 CLI 新增 `--engine` / `--template` 参数和 `list-templates` 子命令，让用户从命令行切换渲染引擎和选择模板。

## Contract

1. `mediaforge render --engine html-video-templates --template warm-grain --audio x.mp3 --output y.mp4` 正常工作
2. `mediaforge render --engine hyperframes` 行为不变（向后兼容）
3. `mediaforge list-templates` 返回所有可用模板名和描述
4. 不传 `--engine` 时默认 `hyperframes`（向后兼容）

## Details

### CLI 参数

```python
@app.command()
def render(
    engine: str = "hyperframes",          # 新增，默认保持兼容
    template: str = "warm-grain",         # 新增，仅 html-video-templates 引擎使用
    audio: str = "audio.mp3",
    output: str = "output.mp4",
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
):
    """Render a video from audio and script."""
```

### list-templates 子命令

```python
@app.command()
def list_templates():
    """List all available html-video templates."""
    from mediaforge.render.html_video_templates import HtmlVideoTemplateEngine
    templates = HtmlVideoTemplateEngine.list_templates()
    for name, desc in templates.items():
        print(f"  {name:20s}  {desc}")
```

## Boundary Cases

| 场景 | 行为 |
|---|---|
| `--engine hyperframes --template warm-grain` | `--template` 被忽略（hyperframes 不需要），不报错 |
| `--engine html-video-templates` 不传 `--template` | 默认 `warm-grain` |
| 模板离线化未完成时 `list-templates` | 仍列出模板名（不检查离线化状态），渲染时若缺字体用 fallback |
