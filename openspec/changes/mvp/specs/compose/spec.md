# Spec: Compose

## Purpose

将提取的文本通过 LLM 转化为结构化的多角色对话脚本。支持四种风格。

## Contract

### `compose(text: str, style: str, voice_map: dict[str,str]) -> Script`

- **Input**:
  - `text`: 清洁文本（来自 ingest）
  - `style`: "interview" | "tutorial" | "explainer" | "debate"
  - `voice_map`: {"speaker_name": "voice_id"} 如 `{"host": "xiaoxiao", "expert": "yunyang"}`
- **Output**: Script 对象，含 segments 列表
- **LLM**: 默认使用当前 Hermes provider；支持 `model` 参数覆盖

### Style 定义

| Style | 角色数 | 模式 | Prompt 要点 |
|-------|--------|------|-------------|
| interview | 2 | 一问一答 | 主持人引导，专家深度解答。语气自然，"嗯""对"等过渡 |
| tutorial | 1 | 步骤讲解 | 单人教学，清晰节奏。每步一个 segment |
| explainer | 1 | 概念拆解 | 单人解说，由浅入深 |
| debate | 2 | 正反交锋 | 两方论点交替，有来有回 |

### Output 约束

- 每个 segment ≤ 500 字符（确保单次 TTS 不超时）
- 总段数 6-12 段
- 每段标注 speaker 和 voice
- estimated_duration = text_length / 4（中文字符/秒）

## Boundary Cases

- 空文本 → 返回单段 "没有足够内容生成脚本"
- 单角色 voice_map → 自动降级为单人模式
- 超长文本 → 自动分段处理，摘要后再生成
- LLM 返回非 JSON → 重试 3 次，失败抛 ComposeError
