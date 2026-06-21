# Spec: Backend Routing

## Purpose

`mediaforge-workflow` skill routes each workflow node to the correct backend: a dedicated Hermes skill, MediaForge MCP call, or CLI fallback. New backends are added as new skills without modifying the orchestrator.

## Contract

### Route Table

**Given** a node `{type: "media_synthesize", config: {backend: "azure"}}`
**When** routed
**Then** the orchestrator dispatches to `mediaforge-tts-azure` skill

**Given** a node `{type: "media_synthesize", config: {backend: "edge"}}`
**When** routed
**Then** the orchestrator calls MediaForge MCP `generate_podcast` (default, no dedicated skill)

**Given** a node `{type: "media_publish", config: {target: "wechat"}}`
**When** routed
**Then** the orchestrator dispatches to `mediaforge-publish-wechat` skill

**Given** a node `{type: "media_ingest", config: {backend: "trafilatura"}}`
**When** routed
**Then** the orchestrator calls MediaForge MCP directly (default, no dedicated skill)

### Unknown Backend Fallback

**Given** a node with `config.backend: "unknown"`
**When** routed
**Then** the orchestrator attempts MediaForge MCP call with the backend name
**And** if MCP rejects the backend, reports error with supported values

### Per-Backend Skill Interface

Every per-backend skill MUST:
1. Accept `{text, voice, output_path, config}` as input
2. Return `{output_path, duration, metadata}` on success
3. Retry 3x with exponential backoff on failure
4. Preserve intermediate files on failure for debugging

### Skill Discovery

**Given** the orchestrator loads
**When** scanning available skills
**Then** it builds a route table from skills matching pattern `mediaforge-<stage>-<backend>`
**And** skills loaded at runtime are auto-discovered (no restart needed)

## Details

### Route Table Definition

```python
# Maintained in mediaforge-workflow SKILL.md, not code
ROUTES = {
    "media_synthesize": {
        "azure":      "mediaforge-tts-azure",
        "elevenlabs": "mediaforge-tts-elevenlabs",
        "cosyvoice":  "mediaforge-tts-cosyvoice",
        # "edge" missing → fallback to MCP
    },
    "media_ingest": {
        "mineru": "mediaforge-ingest-mineru",
    },
    "media_publish": {
        "wechat":    "mediaforge-publish-wechat",
        "jianying":  "mediaforge-publish-jianying",
    },
}
```

### Routing Decision Tree

```
Is there a dedicated skill for (node_type, backend)?
  ├─ YES → skill_view(skill_name), execute with node config
  └─ NO  → MediaForge MCP fallback
              ├─ MCP accepted → execute
              └─ MCP rejected → report error with supported values
```

### Execution Flow per Node

```
1. Resolve inputs from upstream node outputs
2. Look up route table
3. Call backend skill OR MCP fallback
4. Wait for completion
5. Store output path + metadata in execution context
6. Report progress
```

## Boundary Cases

- **No per-backend skills installed** → All nodes fall through to MCP/CLI (graceful degradation)
- **Skill installed but broken** → MCP fallback after skill fails
- **Multiple backends for same node type** → First match in route table wins (deterministic)
- **Backend name case sensitivity** → Lowercase normalize before lookup
