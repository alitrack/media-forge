# Proposal: html-video Template Engine

## Why

MediaForge 的 Hyperframes 渲染引擎目前只有一套暗色主题 HTML 模板（`ANIMATION_TEMPLATE` 约 150 行）。用户生成视频时视觉风格单一，无法满足不同内容类型的审美需求。

开源项目 [html-video](https://github.com/nexu-io/html-video) (Apache-2.0, 3.4k⭐) 有 **23 套专业级 HTML/CSS/GSAP 视频模板**（warm-grain、swiss-grid、kinetic-type、data-chart-nyt 等），覆盖访谈、数据叙事、产品发布、学术讲解等场景。其渲染底层与 MediaForge 一致（Playwright + ffmpeg），协议天然兼容。

**不整合也能各自跑，但整合后：**
- MediaForge 视觉表现力：1 套暗色主题 → 23 套专业模板
- 零新增云依赖（html-video 模板也是纯 HTML/CSS/JS，无 API 调用）

## What Changes

### 新增
1. **`HtmlVideoTemplateEngine`** — 新的 `RenderEngine` 实现，消费 html-video 模板库
2. **资产预处理脚本** — 下载 Google Fonts / GSAP 到本地，替换 CDN 引用
3. **模板变量化** — 3 套首批模板提取 `{{TITLE}}` `{{BODY}}` `{{DATA}}` 占位符
4. **CLI `--engine html-video-templates --template warm-grain`** — 用户可选模板

### 不动
- `RenderEngine` Protocol（`**kwargs` 天然支持引擎专属参数）
- 现有 `hyperframes.py` / `_default.py` 引擎
- 5 阶段流水线（ingest → compose → synthesize → render → publish）

## Capabilities

### New Capabilities
- **多模板渲染**: `get_render_engine("html-video-templates", template="swiss-grid")`
- **模板发现**: `list_templates()` → 返回可用模板名和适用场景
- **资产离线化**: 预处理脚本一键下载字体/GSAP，解决中国网络环境 CDN 超时问题

### Modified Capabilities
- `list_engines()` 返回新增 `"html-video-templates"`
- CLI `mediaforge render` 新增 `--engine` / `--template` 参数

### Non-goals
- ❌ 不实现 html-video 的 agent loop / 编码代理（那是 html-video 的核心竞争力，不在 MediaForge 范围内）
- ❌ 不改造 html-video 的模板格式（模板原样消费，预处理脚本只做下载+替换引用，不改结构）
- ❌ 不在一期做统一 MCP（远期路线四，等前三条稳定）
- ❌ 不做 Remotion / Motion Canvas 引擎适配（只做 html-video 的纯 HTML/CSS/GSAP 模板）

## Impact

| 系统 | 影响 |
|---|---|
| `mediaforge.render.base` | 零改动 |
| `mediaforge.render.__init__` | +1 import 触发注册 |
| `mediaforge.render.hyperframes` | 零改动 |
| `mediaforge.render.html_video_templates` | 新增 ~300 行 |
| `mediaforge/cli.py` | +2 参数 `--engine` `--template` |
| `scripts/` | +1 预处理脚本 `offline_assets.sh` |
| 测试 | +8-12 新测试（引擎注册、模板选择、资产离线化） |
| 依赖 | 零新增（Playwright + ffmpeg 已存在） |
