# Tasks: Progressive Discovery Tests & Token Benchmark

**Input**: Design documents from `/specs/003-discovery-tests/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/test-contract.md

**Tests**: This feature IS a test suite. Tests are the primary deliverable, written test-driven per the spec's Approach section.

**Organization**: Tasks are grouped by user story. US1 (ToolIndex Unit Tests) is fully covered by existing `test_index.py` (43 tests) — no new tasks needed. US2 has two gaps (FR-019, FR-021). US3 and US4 are entirely new.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US2, US3, US4)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add benchmark dependency configuration

- [X] T001 Add `benchmark` optional extra with `tiktoken>=0.7` to pyproject.toml

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Implementation fix required before gap tests can be written

**Why blocking**: The FR-019 test (Phase 3) verifies that `climax_call` lists available tools in the unknown-tool error message. The implementation must be updated first so the test passes.

- [X] T002 Enrich `_handle_climax_call` unknown-tool error in climax.py to include sorted list of available tool names (FR-019 implementation fix per research.md R-002)

**Checkpoint**: Implementation fix verified manually — gap tests can now be written

---

## Phase 3: User Story 2 - Meta-Tool Gap Tests (Priority: P1)

> **Note**: User Story 1 (ToolIndex Unit Tests) is fully covered by existing `test_index.py` (43 tests across 6 classes). FR-001 through FR-011 all have passing tests. No new tasks needed. See research.md R-001 for the complete coverage matrix.

**Goal**: Fill the two remaining test gaps in the meta-tool test coverage: FR-019 enriched unknown-tool error and FR-021 timeout/error parity between discovery and classic modes.

**Independent Test**: `uv run pytest tests/test_discovery_gaps.py -v` — all tests pass with mocked subprocess, no external dependencies.

- [X] T003 [P] [US2] Create tests/test_discovery_gaps.py with TestClimaxCallUnknownToolEnriched class verifying unknown-tool error lists available tools (FR-019)
- [X] T004 [US2] Add TestTimeoutErrorParity class to tests/test_discovery_gaps.py verifying climax_call and classic-mode call_tool produce equivalent output on subprocess error and TimeoutError (FR-021)

**Checkpoint**: `uv run pytest tests/test_discovery_gaps.py -v` passes — meta-tool coverage gaps closed

---

## Phase 4: User Story 3 - Integration Tests with Real Configs (Priority: P2)

**Goal**: End-to-end confidence that progressive discovery works with real YAML configurations, covering mode switching (default vs --classic), cross-CLI search relevance, and output equivalence.

**Independent Test**: `uv run pytest tests/test_integration_discovery.py -v` — loads real configs from `configs/`, all subprocess calls mocked.

- [X] T005 [P] [US3] Create tests/test_integration_discovery.py with test helpers (_unwrap, _call_tool, _list_tools, _build_tool_map), config loading fixtures for git.yaml/docker.yaml/jj.yaml, and TestDiscoveryModeIntegration class (FR-022: default mode exposes exactly 2 meta-tools, FR-024: domain term search surfaces relevant CLIs, FR-025: CLI name filter returns only that CLI's tools)
- [X] T006 [US3] Add TestClassicModeIntegration class to tests/test_integration_discovery.py verifying --classic flag exposes all individual tools instead of meta-tools (FR-023)
- [X] T007 [US3] Add TestOutputEquivalence class to tests/test_integration_discovery.py verifying climax_call output matches classic-mode call_tool output for the same tool with mocked subprocess (FR-026)

**Checkpoint**: `uv run pytest tests/test_integration_discovery.py -v` passes — integration coverage complete

---

## Phase 5: User Story 4 - Token Savings Benchmark (Priority: P2)

**Goal**: Reproducible measurement of token savings comparing progressive discovery mode (2 meta-tools) vs classic mode (all individual tools) across all example configs.

**Independent Test**: `uv run python scripts/benchmark_tokens.py` produces a deterministic markdown-formatted comparison table with discovery tokens < classic tokens.

- [X] T008 [P] [US4] Create scripts/benchmark_tokens.py that loads all configs from configs/, serializes tools/list responses for both classic and discovery modes, counts tokens with tiktoken cl100k_base encoding, and prints a markdown comparison table with classic tokens, discovery tokens, absolute savings, and percentage reduction (FR-027, FR-028, FR-029, FR-030)

**Checkpoint**: Benchmark runs successfully, reports discovery mode at least 70% lower token count than classic mode (SC-005)

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Validate full suite performance and documentation accuracy

- [X] T009 Run full test suite (`uv run pytest -v`) and verify: all tests pass, unit tests < 5s, integration tests < 25s, full suite < 30s (SC-006). Run 10 consecutive times to verify zero flakiness (SC-007)
- [X] T010 Run quickstart.md validation: execute all commands from quickstart.md and verify expected outputs match

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (pyproject.toml updated) — BLOCKS Phase 3 (T003 tests FR-019 which requires the implementation fix in T002)
- **US2 Gap Tests (Phase 3)**: Depends on Phase 2 (FR-019 fix must exist)
- **US3 Integration Tests (Phase 4)**: Depends on Phase 2 (FR-019 fix affects climax_call behavior tested in integration)
- **US4 Benchmark (Phase 5)**: Depends on Phase 1 (benchmark extra must be available) — independent of Phases 3 and 4
- **Polish (Phase 6)**: Depends on all prior phases being complete

### User Story Dependencies

- **US1 (ToolIndex Unit Tests)**: Fully covered — no new work
- **US2 (Meta-Tool Gap Tests)**: Depends on T002 (FR-019 implementation fix) — independent of US3, US4
- **US3 (Integration Tests)**: Depends on T002 (FR-019 fix) — independent of US2, US4
- **US4 (Benchmark)**: Depends on T001 (benchmark extra) — independent of US2, US3

### Within Each User Story

- T003 creates test_discovery_gaps.py → T004 adds to it (sequential)
- T005 creates test_integration_discovery.py → T006, T007 add to it (sequential)
- T008 is a single self-contained task

### Parallel Opportunities

After Phase 2 (Foundational) completes:
- **US2 (Phase 3)** and **US3 (Phase 4)** and **US4 (Phase 5)** can all proceed in parallel — they operate on different files with no cross-dependencies

---

## Parallel Example: After Foundational Phase

```bash
# These three can run simultaneously:
Agent A: "Create tests/test_discovery_gaps.py (US2 - T003, T004)"
Agent B: "Create tests/test_integration_discovery.py (US3 - T005, T006, T007)"
Agent C: "Create scripts/benchmark_tokens.py (US4 - T008)"
```

---

## Implementation Strategy

### MVP First (US2 Gap Tests Only)

1. Complete Phase 1: Setup (T001)
2. Complete Phase 2: Foundational (T002)
3. Complete Phase 3: US2 Gap Tests (T003, T004)
4. **STOP and VALIDATE**: `uv run pytest tests/test_discovery_gaps.py -v` passes
5. All critical meta-tool coverage gaps are closed

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add US2 gap tests → Validate → Core coverage complete
3. Add US3 integration tests → Validate → End-to-end confidence
4. Add US4 benchmark → Validate → Token savings quantified
5. Polish → Full suite validated

### Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- US1 is intentionally omitted from task phases — research.md R-001 confirms full coverage
- Existing test helpers should be duplicated per-file per the contract (not moved to conftest.py)
- Only `git` CLI is assumed available in CI; subprocess calls for docker/jj are mocked
- Commit after each task or logical group
