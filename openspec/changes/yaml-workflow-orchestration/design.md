# Design: YAML-Driven Workflow Orchestration

## Architecture Layers

```
┌────────────────────────────────────────────────────┐
│                  Skill Layer (Hermes)               │
│  mediaforge-workflow  ← 读 YAML，路由后端            │
│       ↓           ↓           ↓                     │
│  tts-edge    tts-azure   publish-wechat  ...        │
│  (per-backend skills, 热插拔)                        │
├────────────────────────────────────────────────────┤
│              Execution Layer (MediaForge)            │
│  MCP Server (generate_podcast, generate_video)      │
│  CLI (mediaforge podcast --url ...)                  │
│  Python API (Synthesizer, RenderEngine, ...)         │
├────────────────────────────────────────────────────┤
│              Engine Layer (unchanged)                │
│  synthesize.py  render/  compose.py  ingest.py       │
│  publish.py  cli.py  mcp_server.py                   │
└────────────────────────────────────────────────────┘
```

**关键决策**：Skill 层和 Engine 层之间只有调用关系，没有代码耦合。
MediaForge 不知道 Hermes skills 的存在；skills 通过 MCP/CLI 调用 MediaForge。

## YAML Schema

对齐 SwanFlow v1 格式（`workflow:` / `version:` / `nodes:` / `inputs:` / `config:`）：

```yaml
workflow: <name>          # 唯一标识
version: v1               # Schema 版本
description: "..."        # 人类可读描述
nodes:
  - id: <node-id>         # 节点 ID，下游用 inputs 引用
    type: <node-type>     # media_ingest | media_compose | media_synthesize | media_render | media_publish
    inputs: [<upstream>]  # DAG 依赖（可选，第一个节点无 inputs）
    config:               # 节点参数 + backend 选择
      backend: <name>     # 后端名称
      ...                 # 后端特定参数
```

### Node Type Reference

| type | 职责 | 输入 | 输出 | 生命周期 |
|------|------|------|------|---------|
| `media_ingest` | 提取文本 | URL/文件路径/原始文本 | 文本文件 (.txt/.md) | 一次性 |
| `media_compose` | LLM 脚本 | 文本 | 脚本文件 (.json) | 一次性 |
| `media_synthesize` | TTS 音频 | 脚本 | 分段 MP3 → 合并 MP3 | 分段并行 |
| `media_render` | 视频渲染 | 音频 + 脚本 | MP4 视频 | 逐帧捕获 |
| `media_publish` | 分发 | 媒体文件 | 本地路径 / URL / 素材库 ID | 一次性 |

### Dependency Graph Detection

```
ingest ──→ compose ──→ synthesize ──→ render ──→ publish
                              └──→ publish (audio-only)
```

Skill 通过 `inputs:` 数组自动检测：
- 有 `render` → 视频管线
- 无 `render` → 纯音频管线

## Backend Routing

`mediaforge-workflow` skill 根据 `config.backend` 路由到对应 per-backend skill：

```python
# Pseudo-code (skill logic, not actual code)
def execute_node(node, inputs):
    router = {
        ("media_synthesize", "edge"):       "mediaforge-tts-edge",
        ("media_synthesize", "azure"):      "mediaforge-tts-azure",
        ("media_synthesize", "elevenlabs"): "mediaforge-tts-elevenlabs",
        ("media_synthesize", "cosyvoice"):  "mediaforge-tts-cosyvoice",
        ("media_ingest", "mineru"):         "mediaforge-ingest-mineru",
        ("media_publish", "wechat"):        "mediaforge-publish-wechat",
    }
    key = (node["type"], node["config"].get("backend", "default"))
    skill_name = router.get(key)

    if skill_name:
        # Route to dedicated skill
        return skill_view(skill_name).execute(inputs, node["config"])
    else:
        # Fallback: call MediaForge MCP/CLI directly
        return call_mediaforge_mcp(node, inputs)
```

**未匹配的后端**：回退到 MediaForge MCP 直接调用（如 `backend: edge` → `generate_podcast`）。

### Per-Backend Skill Contract

每个 per-backend skill 暴露统一的接口：

```
输入：
  - text: str            # 要合成的文本
  - voice: str           # 语音 ID（如 zh-CN-XiaoxiaoNeural）
  - output_path: str     # 输出文件路径
  - config: dict         # 后端特定参数（proxy, region, key, etc.）

输出：
  - output_path: str     # 生成的文件路径
  - duration: float      # 音频/视频时长（秒）
  - metadata: dict       # 后端特定元数据（voice, format, etc.）

错误：
  - 3 次重试，指数退避
  - 失败时保留中间产物用于调试
```

## SwanFlow Interop Design

**独立项目，外部调用。** 不融合代码。

```yaml
# SwanFlow workflow 中的 MediaForge 节点
- id: to_video
  type: mediaforge           # SwanFlow 新节点类型（未来）
  inputs: [ai_agent]         # 上游数据流
  config:
    workflow: "references/example-video.yaml"  # MediaForge workflow YAML
    params:
      source: "{{ai_agent.report}}"            # 文本注入到 ingest.source
```

**执行模型**：
1. SwanFlow engine 遇到 `type: mediaforge` 节点
2. 启动外部进程：`hermes run workflow references/example-video.yaml --param source="<text>"`
3. 阻塞等待完成，收集输出路径
4. 继续下游 SwanFlow 节点

**为什么不是代码融合**：
- SwanFlow = Rust + DuckDB，瓶颈在 CPU
- MediaForge = Python + Playwright + ffmpeg，瓶颈在 IO
- 两套依赖图谱完全不重叠
- 融合代价 >> 独立调用代价

## Error Handling

```
Node N 开始执行
  ├─ 尝试 1: 失败 (网络超时)
  │    └─ 等待 2s
  ├─ 尝试 2: 失败 (API 限流)
  │    └─ 等待 4s
  └─ 尝试 3: 成功 ✓
       └─ 保存输出路径 → 传给 Node N+1

Node N+1 开始执行
  └─ 尝试 1-3: 全部失败 ✗
       └─ 保留 Node 1..N 的输出（不清理）
       └─ 报告失败节点 + 错误信息
       └─ 用户可修复 YAML 后从失败节点恢复
```

## File Layout

```
~/.hermes/skills/media/
├── mediaforge-workflow/          ← 编排引擎（已完成）
│   ├── SKILL.md
│   └── references/
│       ├── example-podcast.yaml
│       └── example-video.yaml
│
├── mediaforge-tts-edge/          ← Edge TTS backend（待建）
│   └── SKILL.md
├── mediaforge-tts-azure/         ← Azure TTS backend（待建）
│   └── SKILL.md
├── mediaforge-tts-elevenlabs/    ← ElevenLabs backend（待建）
│   └── SKILL.md
├── mediaforge-tts-cosyvoice/     ← CosyVoice backend（待建）
│   └── SKILL.md
├── mediaforge-ingest-mineru/     ← MinerU ingest backend（待建）
│   └── SKILL.md
├── mediaforge-publish-wechat/    ← WeChat publish backend（待建）
│   └── SKILL.md
└── mediaforge-publish-jianying/  ← JianYing publish backend（待建）
    └── SKILL.md

/mnt/d/wsl2/media-forge/           ← 代码不变
├── openspec/changes/
│   └── yaml-workflow-orchestration/  ← 本 openspec
│       ├── proposal.md
│       ├── design.md
│       ├── specs/
│       └── tasks.md
└── (其余文件不变)
```
