# Spec: Workflow YAML Schema

## Purpose

Define the YAML schema for MediaForge workflow files, aligned with SwanFlow v1 format. Any `.yaml` file conforming to this schema can be executed by `mediaforge-workflow` skill and, eventually, SwanFlow engine.

## Contract

### Schema Validation

**Given** a YAML file at `<path>`
**When** `mediaforge-workflow` loads it
**Then**:
1. Top-level keys `workflow`, `version`, `nodes` MUST exist
2. `version` MUST be `"v1"`
3. `nodes` MUST be a non-empty array
4. Each node MUST have `id` (string), `type` (valid node type), `config` (object)
5. `inputs` (optional) MUST reference valid upstream `id` values
6. Circular dependencies MUST be rejected
7. Unknown `type` values MUST be rejected with suggestions

### Valid Node Types

- `media_ingest` — text extraction
- `media_compose` — LLM script generation
- `media_synthesize` — TTS audio
- `media_render` — video rendering
- `media_publish` — output distribution

### Dependency Resolution

**Given** a workflow with nodes A→B→C
**When** executed
**Then**:
- A runs first (no inputs)
- B runs after A completes (inputs: [A])
- C runs after B completes (inputs: [B])
- If B fails, C is skipped, A's output preserved

### Audio-Only Detection

**Given** a workflow without `media_render` node
**When** executed
**Then** `media_publish` outputs audio-only (MP3), not video (MP4)

### Variable Substitution

**Given** a config value `"{{input.url}}"` in `media_ingest.source`
**When** executed with `--param input.url=https://example.com`
**Then** the value is resolved to `"https://example.com"`

### Dry Run

**Given** `--dry-run` flag
**When** executed
**Then** schema validation runs, but no node execution occurs

## Details

### Implementation Path

1. Create `~/.hermes/skills/media/mediaforge-workflow/references/schema.yaml` — JSON Schema for validation
2. Add `_validate_workflow(yaml_dict)` → `(valid, errors)` function in skill logic
3. Add `_topological_sort(nodes)` → `ordered_nodes` for execution order
4. Add `_substitute_vars(config, params)` → `resolved_config` for variable injection

### Schema Reference (full)

```yaml
workflow: string       # Required, unique name
version: "v1"          # Required, fixed
description: string    # Optional, human-readable
params:                # Optional, declared parameters
  - name: string
    default: string
nodes:                 # Required, non-empty
  - id: string         # Required, unique within workflow
    type: enum         # Required: media_ingest | media_compose | media_synthesize | media_render | media_publish
    inputs: [string]   # Optional, references upstream node ids
    config: object     # Required, node-specific parameters
```

## Boundary Cases

- **Empty nodes array** → Reject with "workflow must have at least one node"
- **Missing inputs reference** → Reject with "node <id> references unknown input <ref>"
- **Self-referencing inputs** → Reject with "node <id> cannot depend on itself"
- **Duplicate node ids** → Reject with "duplicate node id: <id>"
- **Missing top-level key** → Reject with specific error ("workflow.name is required")
- **Extra unknown keys in config** → Warn but don't reject (forward-compatible)
