# Proposal: MediaForge MVP

## Why

Google NotebookLM 证明了 AI 生成双主持播客的需求，但它封闭、仅音频、无 API。开源替代品（Podcastfy、Open Notebook）或用云端 TTS 或绑定 Docker 全栈，没有一个做到「随便喂个 URL，出来一段可以直接发的视频或音频」。

我们的已有管线已覆盖核心能力——Playwright 渲染、edge-tts 双声交替、ffmpeg 合成、cloudflared 分发。缺的是一个统一入口和产品化封装。

## What Changes

新建 **MediaForge** 项目——内容到多格式媒体的自动化管线。

```
输入层               处理层                  输出层
URL ─┐           ┌─→ 脚本生成(LLM)      ┌─→ 音频播客(.mp3)
PDF ─┤           │                      │
文本─┼─→ 内容提取─┼─→ 角色分配 ──→ TTS ─┼─→ 视频(.mp4 + 画面帧)
CUA ─┘           │                      │
                 └─→ 帧模板(HTML)       └─→ CUA 录屏教程
```

### 交付物

1. **`mediaforge-core`** — Python 包，核心管线
2. **`mediaforge-mcp`** — MCP Server，Hermes 原生工具调用
3. **Hermes Skill** — Prompt 模板库 + 编排规则

## Capabilities

### New Capabilities

- **`ingest`** — 从 URL/PDF/文本/CUA 会话提取结构化内容
- **`compose`** — LLM 生成多角色对话脚本（访谈/教程/解说/辩论四种风格）
- **`synthesize`** — 多角色 TTS 合成 + ffmpeg 拼接
- **`render`** — 音频 + HTML 帧画面 → MP4 视频
- **`record-cua`** — CUA 操作录屏转教程视频
- **`publish`** — cloudflared 隧道分发 + 本地文件输出

### Modified Capabilities

- edge-tts 双声交替已验证，封装为 `VoiceCast` 抽象支持切换后端（Azure/CosyVoice）
- Playwright 渲染链路已验证，抽象为 `SceneRenderer` 接口

### Non-Goals

- 不做 Web UI——通过 Hermes 对话交互 + MCP 工具调用
- 不做实时流媒体——只做文件生成
- 不做 LLM 训练/微调——只用现成 API
- 不做用户管理系统——单人使用

## Impact

- 新增项目 `/mnt/d/wsl2/media-forge/`
- MCP Server 注册到 Hermes 配置
- Skill 添加到 `~/.hermes/skills/`
- 复用现有 cloudflared、ffmpeg、Playwright 基础设施
