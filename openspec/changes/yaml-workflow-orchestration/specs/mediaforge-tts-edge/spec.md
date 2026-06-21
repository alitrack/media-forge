# Spec: MediaForge TTS — Edge Backend

## Purpose

Default TTS backend for MediaForge. Free, no API key, uses Microsoft Edge TTS service via `edge-tts` Python library. Called through MediaForge MCP `generate_podcast` or CLI `mediaforge podcast --tts-backend edge`.

## Contract

### Basic Synthesis

**Given** a script with segments `[{speaker: "host", voice_id: "xiaoxiao", text: "你好"}]`
**When** `mediaforge-workflow` routes `media_synthesize` with `backend: edge`
**Then**:
1. Calls MediaForge MCP `generate_podcast` with the script
2. Returns MP3 file at `output_path`
3. Audio duration matches estimated duration (±20%)

### Voice Resolution

**Given** `voice_id: "xiaoxiao"` and `backend: edge`
**When** resolving voice
**Then** maps to `zh-CN-XiaoxiaoNeural`

**Given** `voice_id: "zh-CN-XiaoxiaoNeural"` (full name)
**When** resolving voice
**Then** uses as-is (passthrough)

### Proxy Handling

**Given** WSL environment with `proxy: "http://172.19.112.1:7897"` in YAML config
**When** synthesizing
**Then** edge-tts uses the specified proxy (not system default)

### Error Retry

**Given** edge-tts fails with network error
**When** on 1st attempt
**Then** retries after 2s delay
**When** on 2nd attempt
**Then** retries after 4s delay
**When** all 3 attempts fail
**Then** raises `SynthesizeError` with details

### Zero-Byte Guard

**Given** edge-tts returns but produces 0-byte file
**When** checking output
**Then** treats as failure and retries

## Details

### Implementation: No dedicated skill needed

Edge TTS is the default — no `mediaforge-tts-edge` skill required.
`mediaforge-workflow` routes it directly to MediaForge MCP:

```
media_synthesize + backend: edge → MCP generate_podcast(...)
```

### MCP asyncio Deadlock Workaround

Hermes event loop conflicts with MCP's `asyncio.run()`. Fallback:

```
terminal(background=true, notify_on_complete=true,
    command="uv run mediaforge podcast --text-file /tmp/script.json --output /tmp/podcast.mp3")
```

### Proxy Configuration

Auto-detected from YAML `config.proxy`. WSL default: `172.19.112.1:7897`.

## Boundary Cases

- **Empty script** → Reject before calling edge-tts
- **Very long segment (>5000 chars)** → Split into sub-segments, synthesize separately
- **SSML in text** → edge-tts strips most SSML; use Azure backend for SSML
- **Network down** → All 3 retries fail, report error, preserve intermediate files
