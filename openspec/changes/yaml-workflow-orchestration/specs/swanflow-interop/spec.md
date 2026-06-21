# Spec: SwanFlow Interop (Design Only)

## Purpose

Define how SwanFlow calls MediaForge as an external node. This spec is **design-only** — no implementation in this openspec cycle. Included for architecture completeness and to validate the YAML format alignment.

## Contract

### SwanFlow Node Type

**Given** a SwanFlow workflow with node `{type: "mediaforge"}`
**When** SwanFlow engine encounters it
**Then**:
1. Reads `config.workflow` — path to MediaForge workflow YAML
2. Resolves `{{variable}}` substitutions from upstream node outputs
3. Spawns external process: `hermes run workflow <yaml-path> --param key=value`
4. Blocks until process exits
5. Reads output paths from stdout/stderr
6. Passes output to downstream SwanFlow nodes

### Input/Output Contract

```
SwanFlow → MediaForge:
  - workflow: path to YAML
  - params: {key: value} map for variable substitution

MediaForge → SwanFlow:
  - output_path: str        # MP3 or MP4 file path
  - duration: float         # seconds
  - metadata: dict          # {format, resolution, size_bytes, ...}
  - exit_code: int          # 0 = success
```

### YAML Format Compatibility

**Given** a MediaForge workflow YAML
**When** loaded by SwanFlow's YAML parser
**Then** `workflow`, `version`, `nodes` keys parse without error
**And** SwanFlow ignores unknown node types (`media_*`) but validates structure

### Non-Goals (This Cycle)

- ❌ No SwanFlow code changes
- ❌ No `mediaforge` node type implementation in SwanFlow
- ❌ No NPP visual editor integration
- ❌ No DuckDB state persistence for MediaForge runs
- ❌ No workflow scheduling via SwanFlow cron

## Details

### Why External Process, Not Library Import

| Approach | SwanFlow (Rust) → MediaForge (Python) |
|----------|--------------------------------------|
| Library import | ❌ Rust can't import Python directly |
| FFI/PyO3 | ❌ Requires GIL management, fragile |
| HTTP API | ⚠️ Needs server lifecycle management |
| **Subprocess** | ✅ Simple, isolated, no dependency coupling |

```rust
// Future SwanFlow code (pseudo)
fn execute_mediaforge_node(config: &MediaForgeConfig) -> Result<MediaOutput> {
    let yaml_path = &config.workflow;
    let params = serde_json::to_string(&config.params)?;
    
    let output = Command::new("hermes")
        .args(["run", "workflow", yaml_path, "--param", &params])
        .output()?;
    
    serde_json::from_slice(&output.stdout)
}
```

### When to Implement

When SwanFlow gains support for external node types (likely Phase 3-4 of SwanFlow roadmap).
This spec serves as the integration contract — MediaForge YAML format won't change,
so the implementation is a single `Command::new("hermes")` call when ready.
