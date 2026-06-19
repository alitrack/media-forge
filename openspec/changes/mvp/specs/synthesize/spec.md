# Spec: Synthesize

## Purpose

将脚本的所有 segment 用指定 TTS 后端合成音频，拼接为单一 MP3 文件。

## Contract

### `synthesize(script: Script, backend: str = "edge") -> str`

- **Output**: 单一 .mp3 文件路径
- **Backend**: "edge"（默认）, "azure", "cosyvoice"
- **Process**: segment → TTS → .mp3 segments → ffmpeg concat → final .mp3

### Voice Mapping

```python
VOICE_REGISTRY = {
    "edge": {
        "xiaoxiao": "zh-CN-XiaoxiaoNeural",
        "yunyang": "zh-CN-YunyangNeural",
    },
    "azure": {
        "xiaoxiao": "zh-CN-XiaoxiaoNeural",
        "yunyang": "zh-CN-YunyangNeural",
    },
    "cosyvoice": {
        # Dynamically loaded from voice library
    }
}
```

### Audio Spec

- Format: MP3, 24kHz, 48kbps mono
- Segment gap: 500ms silence between speakers
- Max segment duration: 60s（超过自动拆分）

### Edge-TTS Limitations

- 不支持 SSML phoneme 标签（消费端点静默拒绝）
- 多音字使用 Prompt 层面的同义替换策略
- 重试：单 segment 失败重试 3 次，间隔 2s

## Boundary Cases

- 空段 → 跳过不报错
- backend 不可用 → 自动 fallback "edge"
- ffmpeg 未安装 → 抛 SynthesizeError
- 单 segment → 跳过合并不复制
