# Spec: MediaForge TTS — Azure Backend

## Purpose

Commercial-quality TTS via Azure Cognitive Services Speech SDK. Activated by `backend: azure` in workflow YAML. Implemented as Hermes skill `mediaforge-tts-azure`, not embedded in MediaForge Python code.

## Contract

### Basic Synthesis

**Given** text "你好世界" and voice "zh-CN-XiaoxiaoNeural"
**When** `mediaforge-tts-azure` skill is invoked with valid AZURE_SPEECH_KEY + AZURE_SPEECH_REGION
**Then**:
1. Produces MP3 file at output_path
2. File size > 0 bytes
3. Audio is intelligible Chinese speech

### Credential Validation

**Given** missing AZURE_SPEECH_KEY env var
**When** skill invoked
**Then** immediately fails with clear error: "Azure TTS requires AZURE_SPEECH_KEY environment variable"

**Given** invalid AZURE_SPEECH_KEY
**When** Azure API called
**Then** fails with auth error, no retry (auth errors are not transient)

### SSML Support

**Given** text containing special characters `<>&"'`
**When** synthesizing
**Then** characters are XML-escaped before SSML injection

### Voice Resolution

**Given** `voice: "xiaoxiao"` with backend azure
**When** resolving
**Then** maps to `zh-CN-XiaoxiaoNeural`

**Given** `voice: "aria"` (English)
**When** resolving
**Then** maps to `en-US-AriaNeural`

### Retry

**Given** transient network error
**When** on attempts 1-2
**Then** retries with exponential backoff (2s, 4s)
**When** all 3 fail
**Then** raises error with attempt details

### Proxy

**Given** `config.proxy: "http://172.19.112.1:7897"`
**When** initializing Azure SpeechConfig
**Then** proxy is set via `speech_config.set_proxy()`

## Details

### Implementation Path

1. Create `~/.hermes/skills/media/mediaforge-tts-azure/SKILL.md`
2. Skill uses `uv run --with azure-cognitiveservices-speech python script.py` to avoid requiring pip install
3. Skill script:
   - Reads text from temp file (avoids command-line length limit)
   - Initializes SpeechConfig with env vars
   - Calls `speak_ssml_async().get()`
   - Writes audio_data to output_path

### Dependency Management

Azure SDK is heavy (~50MB). Never require `pip install` — use `uv run --with`:

```bash
uv run --with azure-cognitiveservices-speech python /tmp/azure_tts.py \
  --text "你好" --voice zh-CN-XiaoxiaoNeural --output /tmp/seg_000.mp3
```

This isolates the dependency and avoids polluting MediaForge's environment.

### Existing Code (MediaForge synthesize.py)

`synthesize.py` already has `_speak_azure()` method (written during P0 exploration).
This code stays in MediaForge for direct CLI usage (`mediaforge podcast --tts-backend azure`).
The skill provides an ALTERNATIVE entry point that doesn't require modifying MediaForge.

## Boundary Cases

- **Very long text (>5000 chars)** → Write to temp file, pass file path
- **SSML injection** → XML-escape user text before wrapping in SSML
- **Azure region latency** → Use `eastasia` for China, `eastus` for global
- **SDK not installed** → `uv run --with` auto-installs; if fails, report clear error
