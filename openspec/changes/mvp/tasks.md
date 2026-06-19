# Tasks: MediaForge MVP

## Phase 1: 核心包 (mediaforge-core)

- [ ] 1.1 项目骨架：pyproject.toml, mediaforge/__init__.py, types.py（Source, Segment, Script, MediaOutput）
- [ ] 1.2 安装依赖：trafilatura, pdfplumber, edge-tts, ffmpeg-python, mcp
- [ ] 1.3 Ingest: URL 提取 (trafilatura) + PDF 提取 (pdfplumber) + CUA 会话解析
- [ ] 1.4 Compose: LLM 对话脚本生成（interview 风格 + Prompt 模板）
- [ ] 1.5 Compose: 支持 tutorial/explainer/debate 三种额外风格
- [ ] 1.6 Synthesize: edge-tts 单 segment 生成 + ffmpeg concat 拼接
- [ ] 1.7 Synthesize: VoiceCast 抽象层，支持 backend 切换
- [ ] 1.8 Render: HTML 帧模板 + Playwright 截图 + ffmpeg 视频合成
- [ ] 1.9 Publish: HTTP server + cloudflared 隧道管理
- [ ] 1.10 集成测试：URL → 访谈播客 端到端

## Phase 2: MCP Server

- [ ] 2.1 MCP server 骨架（FastMCP）
- [ ] 2.2 `generate_podcast` 工具
- [ ] 2.3 `generate_video` 工具
- [ ] 2.4 `list_voices` 工具
- [ ] 2.5 `publish` 工具
- [ ] 2.6 注册到 Hermes config.yaml

## Phase 3: Hermes Skill

- [ ] 3.1 SKILL.md：触发词 + 使用指南
- [ ] 3.2 Prompt 模板库：interview/tutorial/explainer/debate 四种风格
- [ ] 3.3 中文优化：多音字策略 + 过渡词语气 Prompt
- [ ] 3.4 视频生成编排规则

## Phase 4: 增强

- [ ] 4.1 CUA 录屏转教程（record_tutorial 工具）
- [ ] 4.2 Azure Speech backend 支持
- [ ] 4.3 CosyVoice 3 backend 支持（Mac Studio 远程推理）
- [ ] 4.4 进度回调（长任务 streaming status）
- [ ] 4.5 多语言支持（英文优先）

## Phase 5: 文档 & 分发

- [ ] 5.1 README + 快速开始
- [ ] 5.2 Wiki 文档（/mnt/d/wsl2/claw/wiki/）
- [ ] 5.3 示例脚本 + 试听页面
- [ ] 5.4 pip 打包发布
