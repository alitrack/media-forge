# Tasks: html-video Template Engine

## 1. 资产准备
- [ ] 1.1 写 `scripts/offline_html_video_assets.sh` — 下载字体/GSAP，替换 CDN 引用
- [ ] 1.2 跑脚本，验证 3 套模板离线化成功（无网络下 Playwright 渲染无外网请求）
- [ ] 1.3 模板占位符注入：warm-grain/swiss-grid/kinetic-type 各标 `{{TITLE}}`/`{{BODY}}`/`{{SEGMENT_n_TEXT}}`

## 2. 核心引擎
- [ ] 2.1 实现 `HtmlVideoTemplateEngine` 类（`render/`, `~200 行`）
  - `name`, `__init__(template, width, height, fps)`
  - `render(script, audio_path, output_path)` — Playwright recordVideo + ffmpeg mux
  - `available()` — 检查 Playwright + ffmpeg + 模板目录
  - `list_templates()` — 扫描模板目录返回 {name: description}
- [ ] 2.2 `render/__init__.py` 加 `import html_video_templates` 触发注册
- [ ] 2.3 字体 FOUT 处理（复用 hyperframes.py 的 freeze→fonts.ready→unfreeze 逻辑）

## 3. CLI
- [ ] 3.1 `cli.py` render 命令加 `--engine` / `--template` 参数
- [ ] 3.2 新增 `list-templates` 子命令
- [ ] 3.3 默认 `--engine hyperframes` 向后兼容验证

## 4. 测试
- [ ] 4.1 引擎注册测试：`list_engines()` 包含 `"html-video-templates"`
- [ ] 4.2 工厂测试：`get_render_engine("html-video-templates", template="warm-grain")`
- [ ] 4.3 无效模板名 → `RenderError`
- [ ] 4.4 `list_templates()` 返回首批 3 套
- [ ] 4.5 端到端：用最小 Script + 离线化模板生成 MP4，ffprobe 验证
- [ ] 4.6 `available()` 在模板目录缺失时返回 `False`

## 5. 文档
- [ ] 5.1 更新 wiki: [[mediaforge-html-video-integration]] 标注路线一/二完成状态
- [ ] 5.2 README 加模板切换示例
