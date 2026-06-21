# Tasks: YAML-Driven Workflow Orchestration

## 1. Workflow Engine (已完成)

- [x] 1.1 Create `mediaforge-workflow` skill with YAML schema docs
- [x] 1.2 Create example-podcast.yaml
- [x] 1.3 Create example-video.yaml
- [x] 1.4 Update skill with SwanFlow interop rationale (not fusion)

## 2. Per-Backend Skills

- [x] 2.1 Create `mediaforge-tts-edge` skill
- [x] 2.2 Create `mediaforge-tts-azure` skill
- [x] 2.3 Test edge skill: end-to-end podcast (492KB MP3, 1:23, 9 segments) ✓
- [ ] 2.4 Test azure skill: run with valid credentials, verify audio output (needs AZURE_SPEECH_KEY)
- [x] 2.5 Create `mediaforge-tts-elevenlabs` skill
- [x] 2.6 Create `mediaforge-publish-epidemicsound` skill
- [x] 2.7 Create `mediaforge-compose-shots` skill

## 3. Workflow Execution (Core Logic)

- [x] 3.1 Add step-by-step execution instructions to mediaforge-workflow — per-node sequence
- [x] 3.2 DAG dependency resolution built into execution sequence
- [x] 3.3 Backend routing: node type+config.backend → correct skill/MCP/CLI call
- [x] 3.4 Workflow orchestration tested: 4-node pipeline completed end-to-end
- [ ] 3.5 Add dry-run mode (validate YAML only, no execution)

## 4. Integration

- [x] 4.1 Wire workflow execution into mediaforge-workflow skill trigger
- [x] 4.2 Test full pipeline: ingest → compose → synthesize → publish (audio-only) ✓
- [ ] 4.3 Test full pipeline with render: ingest → compose → synthesize → render → publish
- [ ] 4.4 Test backend switching: change `backend: edge` → `backend: azure` in YAML

## 5. Documentation & Polish

- [x] 5.1 Update mediaforge-workflow SKILL.md with step-by-step execution instructions
- [ ] 5.2 Add error recovery guide (how to resume from failed node)
- [ ] 5.3 Verify all 5 specs have matching acceptance criteria
