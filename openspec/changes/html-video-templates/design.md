# Design: html-video Template Engine

## Architecture

```
render/
├── base.py                     ← Protocol，不动
├── hyperframes.py              ← 现有引擎，不动
├── _default.py                 ← 现有引擎，不动
├── __init__.py                 ← +1 import
├── html_video_templates.py     ← NEW: 核心引擎
└── hooks.py                    ← 不动
```

## Data Flow

```
Script + audio_path
       │
       ▼
┌─────────────────────────────────────┐
│  HtmlVideoTemplateEngine.render()   │
│                                     │
│  1. 选模板 ──► templates/{name}/    │
│  2. 注入内容 ──► 占位符替换          │
│  3. Playwright recordVideo ──► webm │
│  4. ffmpeg webm→mp4 + mux audio    │
│                                     │
│  → output.mp4                       │
└─────────────────────────────────────┘
```

## Template Adapter Design

### 占位符映射

每套模板标注 3-5 个变量槽，引擎根据 `Script` 结构自动填充：

| 占位符 | 来源 | 说明 |
|---|---|---|
| `{{TITLE}}` | `script.title` | 视频标题 |
| `{{BODY}}` | `segments[n].text` 合并 | 正文内容 |
| `{{SEGMENT_n_TEXT}}` | `segments[n].text` | 第 n 段文本 |
| `{{SEGMENT_n_SPEAKER}}` | `segments[n].speaker` | 说话人 |
| `{{TIMESTAMP}}` | 生成时间 | 装饰性时间戳 |

### 首批 3 套模板适配

| 模板 | 适用场景 | 变量槽 |
|---|---|---|
| `warm-grain` | 访谈/叙事 | TITLE + SEGMENT_n_TEXT × 3 |
| `swiss-grid` | 产品发布/结构化内容 | TITLE + BODY |
| `kinetic-type` | 短文案/金句 | SEGMENT_n_TEXT（逐字动画） |

### 模板目录结构

```
templates/
├── warm-grain/
│   ├── index.html          ← 原始模板（含占位符）
│   └── assets/             ← 离线化后的字体/JS
├── swiss-grid/
│   └── ...
└── kinetic-type/
    └── ...
```

模板来源：从 `/tmp/html-video/templates/frame-warm-grain/` 等复制，注入占位符。

## Asset Offline Script

```bash
# scripts/offline_html_video_assets.sh
# 1. 扫描所有模板 HTML 中的外部资源引用
# 2. 下载 Google Fonts CSS + 字体文件 → templates/<name>/assets/fonts/
# 3. 下载 GSAP → templates/<name>/assets/js/
# 4. 替换 HTML 中的 CDN URL → 本地相对路径
```

## Engine API

```python
# mediaforge/render/html_video_templates.py

class HtmlVideoTemplateEngine:
    name: ClassVar[str] = "html-video-templates"

    def __init__(self, template: str = "warm-grain", **kwargs):
        self.template = template
        self.width = kwargs.get("width", 1920)
        self.height = kwargs.get("height", 1080)
        self.fps = kwargs.get("fps", 30)

    def render(self, script: Script, audio_path: str,
               output_path: str, **kwargs) -> str:
        """1. 加载模板 → 2. 注入内容 → 3. Playwright 录制 → 4. ffmpeg 混音"""
        ...

    @classmethod
    def available(cls) -> bool:
        """检查 Playwright + ffmpeg + 模板目录是否存在"""
        ...

    @staticmethod
    def list_templates() -> dict[str, str]:
        """返回 {name: description}"""
        ...

# 注册
register_engine(HtmlVideoTemplateEngine)
```

## CLI Changes

```bash
# 现有（不变）
mediaforge render --engine hyperframes --audio podcast.mp3 --output video.mp4

# 新增
mediaforge render --engine html-video-templates --template warm-grain \
    --audio podcast.mp3 --output video.mp4

# 列出可用模板
mediaforge list-templates
```

## Edge Cases

1. **模板目录缺失**: `available()` 返回 `False`，`render()` 抛出 `RenderError` with helpful message
2. **模板名无效**: 检查 `template in list_templates()`，否则 `RenderError`
3. **字体下载失败**: 预处理脚本报错但继续（fallback 系统字体栈）
4. **Playwright 超时**: 与 hyperframes.py 一致的 120s 超时 + 错误信息
5. **空 Script**: 占位符填默认文本 "No content"
