# Proposal: YAML-Driven Workflow Orchestration

## Why

MediaForge 目前是**单体 Python 包**：5 阶段管线硬编码在 `cli.py` → `compose.py` → `synthesize.py` → `render/` → `publish.py`。加一个新 TTS 后端要改代码 + 加依赖 + 发版。`ecosystem-8-tools` 的路线是对的（Azure TTS、剪映导出有价值），但**架构层面走错了**——不该把每个工具塞进 MediaForge 代码里。

**问题**：用户在 YAML 里声明 `backend: azure` 后，MediaForge 内部应该能做到——但不需要 MediaForge 代码知道 Azure SDK 的存在。

**答案**：Skill 层编排 + YAML 定义工作流 + MediaForge 保持独立。

## What Changes

### 1. 新增：Hermes skill `mediaforge-workflow`（已完成）

位置：`~/.hermes/skills/media/mediaforge-workflow/`

YAML-driven pipeline orchestration。Skill 读取 YAML → 按依赖顺序执行节点 → 每个节点调用 MediaForge MCP/CLI 或外部工具。

YAML 格式对齐 SwanFlow v1 schema（`workflow:` / `version:` / `nodes:` / `inputs:`），用户学一种格式写两种工作流。

含两个示例：`references/example-podcast.yaml`（纯音频）、`references/example-video.yaml`（视频+渲染）。

### 2. 新增：Per-backend Hermes skills

每个 TTS/Ingest/Render 后端拆成独立 skill，`mediaforge-workflow` 按 YAML `config.backend` 路由：

| Skill | 触发条件 | 调用方式 |
|-------|---------|---------|
| `mediaforge-tts-edge` | `backend: edge` | MediaForge MCP `generate_podcast` |
| `mediaforge-tts-azure` | `backend: azure` | Azure SDK via `uv run` + env vars |
| `mediaforge-tts-elevenlabs` | `backend: elevenlabs` | ElevenLabs REST API via curl |
| `mediaforge-tts-cosyvoice` | `backend: cosyvoice` | CosyVoice MCP on Mac (10.10.10.121) |
| `mediaforge-ingest-mineru` | `backend: mineru` | MinerU MCP |
| `mediaforge-publish-wechat` | `target: wechat` | wechat-publisher skill |

每个 skill 封装一个后端的调用细节（认证、重试、错误处理），`mediaforge-workflow` 只看 YAML 路由，不关心实现。

### 3. 新增：SwanFlow `mediaforge` 节点类型（后续，不现在做）

SwanFlow 加一个 `type: mediaforge` 节点，将 MediaForge workflow YAML 作为外部子流程调用：

```yaml
- id: to_video
  type: mediaforge
  inputs: [ai_agent]
  config:
    workflow: "references/example-video.yaml"
    params:
      source: "{{ai_agent.report}}"
```

MediaForge 和 SwanFlow **不融合**——独立项目，独立仓库，独立技术栈。SwanFlow 只是通过外部调用来触发 MediaForge 管线。

### 4. 保留：MediaForge Python 包不变

`synthesize.py` 中已写的 Azure TTS 代码保留——作为后端能力之一，供直接 CLI 调用。但架构上不再把"加新后端 = 改 MediaForge 代码"作为唯一路径。

## Capabilities

### New Capabilities
- **YAML 工作流定义**：用户写 `example-podcast.yaml` 即可跑完整管线，不动 Python 代码
- **热插拔后端**：改 YAML 一行 `backend: azure` 切换 TTS 引擎，不需要 `pip install` 新依赖（skill 自己处理）
- **Skill 级复用**：`mediaforge-tts-azure` 技能被 MediaForge 工作流和其他 Hermes 场景复用
- **格式统一**：YAML schema 对齐 SwanFlow，降低认知成本

### Modified Capabilities
- **MediaForge MCP server**：仍然是音频/视频生成的后端，但不再是唯一入口
- **`ecosystem-8-tools` 集成**：Azure TTS、JianYing、HeyGen 从"改 MediaForge 代码"变为"写 skill + YAML 声明"

### Non-Goals
- ❌ 不修改 SwanFlow 代码（融合留待后续深度调研）
- ❌ 不重构 MediaForge 内部架构（Python 包保持原样）
- ❌ 不做可视化工作流编辑器（NPP 集成留待以后）
- ❌ 不替换现有 MediaForge CLI（CLI 仍可用，skill 是额外入口）
- ❌ ElevenLabs / EpidemicSound / Remotion 具体集成（本 openspec 只建框架，不写具体后端代码）

## Impact

| 系统 | 影响 |
|------|------|
| Hermes skills | 新增 `mediaforge-workflow` + 6 个 per-backend skills |
| MediaForge Python | synthesize.py 已有 Azure 代码保留，无其他改动 |
| MediaForge MCP | 无变化（仍是底层执行引擎） |
| SwanFlow | 无代码变化（格式对齐纯属约定，不依赖 SwanFlow） |
| 用户体验 | 写 YAML → 跑管线，替代了记 CLI 参数 |
| 开发体验 | 加新后端 = 写 skill，不改 MediaForge 代码 |
