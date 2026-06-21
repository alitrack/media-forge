# Abogen + Kokoro: 英文有声书 TTS 后端

## 概述

[Abogen](https://github.com/denizsafak/abogen) 是一款开源有声书生成工具（MIT，4.9k Star），能将 EPUB/PDF/TXT 转为音频 + 同步字幕。底层 TTS 引擎是 [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M)，一个 82M 参数的开源模型（Apache 2.0），CPU 可跑，GPU 上可达 200× 实时速度。

MediaForge 可以将 Kokoro/Abogen 作为 **英文内容的 TTS 后端**，替代云端 API（Edge-TTS/Azure/OpenAI TTS），实现完全离线的音频生成。

## 适用场景

| 场景 | 推荐 | 说明 |
|------|:----:|------|
| 英文有声书 + 字幕 | ✅ | 最佳场景。54 种音色，SRT/ASS 多粒度字幕 |
| 英文播客/旁白 | ✅ | 发音自然，速度极快 |
| 纯中文内容 | ⚠️ | Kokoro v1.1-zh 可用但不如 Edge-TTS 晓晓自然 |
| 中英混读 | ❌ | 不支持。两个模型分家，无法同一句内混读 |
| 古文/文言文 | ❌ | 训练数据无文言文语料，多音字错误率高 |

## 快速开始

### 安装

```bash
# 安装系统依赖
sudo apt install espeak-ng    # Linux
brew install espeak-ng        # macOS

# 安装 Python 包（推荐 uv）
uv tool install --python 3.12 abogen

# 或直接装 Kokoro（如果只需 TTS，不需要 Abogen GUI）
pip install kokoro "misaki[zh]" soundfile
```

### 基础用法（Python）

```python
from kokoro import KPipeline
import soundfile as sf
import numpy as np

# 英文管线
pipeline = KPipeline(lang_code='a')
text = "The quick brown fox jumps over the lazy dog."

segments = list(pipeline(text, voice='af_heart'))
audio = np.concatenate([seg.audio for seg in segments])
sf.write('output.wav', audio, 24000)
```

### 可选音色

英文 54 个音色，常用：

| 代号 | 描述 |
|------|------|
| `af_heart` | 美式女声，温暖 |
| `af_bella` | 美式女声，清亮 |
| `af_nicole` | 美式女声，沉稳 |
| `am_adam` | 美式男声 |
| `bf_emma` | 英式女声 |
| `bm_george` | 英式男声 |

完整列表：[Kokoro VOICES.md](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)

### 生成有声书（Abogen CLI）

```bash
# GUI
abogen

# Web UI（含 Supertonic TTS、LLM 文本预处理）
abogen-web
```

## 在 MediaForge 中的集成位置

```
MediaForge 五段管线:

ingest → compose → synthesize → render → publish
                         ↑
                    Kokoro 可作为此层的 TTS 后端
```

### 集成方式

```python
# synthesize/kokoro_backend.py
from kokoro import KPipeline
import numpy as np
import soundfile as sf

class KokoroTTS:
    """Kokoro TTS backend for English content."""

    def __init__(self, lang_code='a', voice='af_heart'):
        self.pipeline = KPipeline(lang_code=lang_code)
        self.voice = voice

    def synthesize(self, text: str, output_path: str) -> dict:
        segments = list(self.pipeline(text, voice=self.voice))
        audio = np.concatenate([seg.audio for seg in segments])
        duration = len(audio) / 24000
        sf.write(output_path, audio, 24000)
        return {
            'path': output_path,
            'duration': duration,
            'sample_rate': 24000,
            'segments': len(segments)
        }
```

## 性能

| 环境 | 实时倍数 | 备注 |
|------|----------|------|
| CPU (WSL, no GPU) | ~5× | 82M 参数，内存 < 3GB |
| RTX 2060 Mobile | ~50× | 3,000 字 → 3.5 分钟音频，11 秒生成 |
| RTX 4090 | ~200× | 官方数据 |
| Mac M3 Ultra | ~20×+ | Apple Silicon MPS 加速 |

## 局限性

1. **不支持中英混读**：技术文章里中英混排的常见场景无法处理
2. **安装门槛**：需手动装 espeak-ng，Windows/macOS 踩坑多
3. **中文不如 Edge-TTS**：Kokoro v1.1-zh 的自然度和情感逊于晓晓/云扬
4. **无音色克隆**：不支持从参考音频克隆音色
5. **GPU 检测不稳定**：部分环境 CUDA 检测失败回退 CPU（GitHub Issue #32）

## 替代方案对比

| 方案 | 离线 | 中文 | 中英混 | 音色克隆 | 字幕 |
|------|:----:|:----:|:------:|:--------:|:----:|
| **Kokoro** | ✅ | ⚠️ | ❌ | ❌ | ✅ |
| Edge-TTS | ❌ | ✅ | ✅ | ❌ | ❌ |
| CosyVoice 3 | ✅ | ✅ | ⚠️ | ✅ | ❌ |
| Chatterbox | ✅ | ⚠️ | ✅ | ✅ | ❌ |
| ElevenLabs | ❌ | ✅ | ✅ | ✅ | ❌ |
| Fish Audio S2 | ❌ | ✅ | ✅ | ✅ | ❌ |

## 相关链接

- [Abogen GitHub](https://github.com/denizsafak/abogen)
- [Kokoro-82M Model Card](https://huggingface.co/hexgrad/Kokoro-82M)
- [Kokoro v1.1-zh (中文版)](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh)
- [Kokoro Python SDK](https://github.com/hexgrad/kokoro)
- [中文 TTS 对比实测](tts-zh-comparison-2026.md)
