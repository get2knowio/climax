# Tasks: Tool Discovery Index

**Input**: Design documents from `/specs/001-tool-discovery-index/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/tool-index-api.md, quickstart.md

**Tests**: Included — SC-006 requires test coverage for all public methods including edge cases.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

- **Single-file core**: All production code in `climax.py` at repository root (Constitution Principle I)
- **Tests**: `tests/` at repository root
- **Configs**: `configs/` at repository root

---

## Phase 1: Setup

**Purpose**: Verify baseline before making changes

- [X] T001 Run full existing test suite (`uv run pytest -v`) to confirm all tests pass before modifications

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: No foundational phase needed — project already exists with established infrastructure. All new code goes into existing files per single-file architecture.

**Checkpoint**: Skipped — proceed directly to User Story 1.

---

## Phase 3: User Story 1 — Config Author Adds Metadata to YAML Config (Priority: P1) MVP

**Goal**: Extend CLImaxConfig Pydantic model with optional `category` and `tags` fields so config authors can annotate YAML configs with discovery metadata.

**Independent Test**: Write a YAML config with `category` and `tags` fields, load it, and verify the parsed Pydantic model contains those values. Also verify configs without these fields still load (backward compatible).

### Implementation for User Story 1

- [X] T002 [US1] Add `category: str | None = None` and `tags: list[str] = Field(default_factory=list)` fields to `CLImaxConfig` model in climax.py
- [X] T003 [P] [US1] Add test fixtures with category/tags YAML data (configs with both fields, neither field, and partial) to tests/conftest.py
- [X] T004 [US1] Add tests for category/tags config loading in tests/test_config.py — cover: both fields present, no fields (backward compat defaults), category-only, tags-only, verify existing configs still load

**Checkpoint**: CLImaxConfig accepts `category` and `tags` in YAML. All existing configs load without modification. Run `uv run pytest tests/test_config.py -v` to verify.

---

## Phase 4: User Story 2 — Agent Searches for Relevant Tools by Keyword (Priority: P1) MVP

**Goal**: Build the ToolIndex class with `from_configs()` constructor and `search()` method so agents can find relevant tools across all loaded configs via keyword, category, and CLI filters.

**Independent Test**: Build a ToolIndex from multiple configs with category/tags, call `search(query="commit")`, and verify results contain commit-related tools with full arg schemas. Test all filter combinations and edge cases.

### Implementation for User Story 2

- [X] T005 [P] [US2] Add `ToolIndexEntry` Pydantic model to climax.py — fields: `tool_name`, `description`, `cli_name`, `category`, `tags`, `input_schema` (dict). Include private `_search_text: str` field pre-computed as lowercased join of all searchable fields (per research R4/R8). Use `model_config = ConfigDict(...)` to exclude `_search_text` from serialization. Add Google-style docstring per constitution Code Style.
- [X] T006 [P] [US2] Add `CLISummary` Pydantic model to climax.py — fields: `name`, `description`, `tool_count`, `category`, `tags` (per data-model.md). Needed by `from_configs()`; also used by US3 `summary()`. Add Google-style docstring per constitution Code Style.
- [X] T007 [US2] Implement `ToolIndex` class with `from_configs(configs: list[CLImaxConfig]) -> ToolIndex` class method in climax.py — iterate configs, build `ToolIndexEntry` per tool using `build_input_schema()` for `input_schema`, build `CLISummary` per config, store `ResolvedTool` in `_resolved` dict. Handle duplicate tool names: last wins, remove old entry from `_entries` list, log warning (per research R7). Add Google-style docstrings on class and all public methods per constitution Code Style.
- [X] T008 [US2] Implement `search(query=None, category=None, cli=None, limit=10) -> list[ToolIndexEntry]` method on ToolIndex in climax.py — use `query_lower in entry._search_text` for substring matching (per research R3), exact case-insensitive match for `category` and `cli` filters, AND logic for combined filters (FR-008), return up to `limit` results in insertion order (FR-009).
- [X] T009 [US2] Create tests/test_index.py with search tests — cover: keyword match (name, description, tags), case-insensitive query, category exact filter, cli exact filter, combined filters (AND logic), limit parameter, limit=0, no matches (empty list), all-None browse mode, special characters in query treated as literal (FR-013), duplicate tool name handling, performance timing assertion: search across all bundled configs (76+ tools) completes in <50ms (SC-003)

**Checkpoint**: ToolIndex builds from configs and search works with all filter combinations. Run `uv run pytest tests/test_index.py -v` to verify.

---

## Phase 5: User Story 3 — Agent Gets Index Overview Without Searching (Priority: P2)

**Goal**: Add `summary()` method to ToolIndex so agents can see what CLIs and capabilities are available before performing a targeted search.

**Independent Test**: Build a ToolIndex from multiple configs and call `summary()`, verify each CLI name, tool count, category, and tags are returned correctly.

### Implementation for User Story 3

- [X] T010 [US3] Implement `summary() -> list[CLISummary]` method on ToolIndex in climax.py — return the pre-built `_summaries` list
- [X] T011 [US3] Add summary tests to tests/test_index.py — cover: multiple CLIs with correct tool counts, configs with and without category/tags, verify description field populated

**Checkpoint**: Summary provides complete CLI overview. Run `uv run pytest tests/test_index.py::test_summary -v` (or equivalent) to verify.

---

## Phase 6: User Story 4 — Agent Retrieves Exact Tool by Name (Priority: P2)

**Goal**: Add `get()` method to ToolIndex so agents can retrieve a full `ResolvedTool` by exact name for execution after discovery.

**Independent Test**: Build a ToolIndex and call `get("git_status")`, verify the returned ResolvedTool contains the complete tool definition including base command, args, env, and working directory.

### Implementation for User Story 4

- [X] T012 [US4] Implement `get(tool_name: str) -> ResolvedTool | None` method on ToolIndex in climax.py — lookup in `_resolved` dict, return `None` if not found
- [X] T013 [US4] Add get tests to tests/test_index.py — cover: exact name returns ResolvedTool with correct base_command/tool/env/working_dir, nonexistent name returns None

**Checkpoint**: Get returns execution-ready tool definitions. Run `uv run pytest tests/test_index.py -v` to verify all index methods work.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and optional enhancements across all user stories

- [X] T014 [P] Optionally add `category` and `tags` metadata to bundled configs (e.g., configs/git.yaml, configs/docker.yaml) for richer discovery out of the box
- [X] T015 Run full test suite (`uv run pytest -v`) and validate all acceptance scenarios from spec.md (SC-001 through SC-006)
- [X] T016 Run quickstart.md code examples manually to verify end-to-end workflow (build index, search, summary, get)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — run first to establish baseline
- **US1 (Phase 3)**: Depends on Setup — extends CLImaxConfig model
- **US2 (Phase 4)**: Depends on US1 — ToolIndex uses category/tags from CLImaxConfig
- **US3 (Phase 5)**: Depends on US2 — summary() uses ToolIndex built by from_configs()
- **US4 (Phase 6)**: Depends on US2 — get() uses ToolIndex built by from_configs()
- **US3 and US4 are independent of each other** — can run in parallel after US2
- **Polish (Phase 7)**: Depends on all user stories being complete

### Within Each User Story

- Models/schemas before methods that use them
- Implementation before tests (tests verify the implementation)
- Core logic before edge case handling

### Parallel Opportunities

- T003 (conftest fixtures) can run in parallel with T002 (model changes) — different files
- T005 (ToolIndexEntry) and T006 (CLISummary) can run in parallel — independent models
- **US3 and US4 can run in parallel** after US2 completes — independent methods on the same class
- T014 (bundled config metadata) can run in parallel with T015/T016

---

## Parallel Example: User Story 2

```bash
# Launch both Pydantic models in parallel (independent additions to climax.py):
Task: "Add ToolIndexEntry Pydantic model to climax.py"
Task: "Add CLISummary Pydantic model to climax.py"

# Then sequentially:
Task: "Implement ToolIndex class with from_configs() in climax.py"
Task: "Implement search() method on ToolIndex in climax.py"
Task: "Create tests/test_index.py with search tests"
```

## Parallel Example: US3 + US4 After US2

```bash
# These two stories can run in parallel after US2:
# Stream A:
Task: "Implement summary() method on ToolIndex in climax.py"
Task: "Add summary tests to tests/test_index.py"

# Stream B (parallel):
Task: "Implement get() method on ToolIndex in climax.py"
Task: "Add get tests to tests/test_index.py"
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2)

1. Complete Phase 1: Setup (verify baseline)
2. Complete Phase 3: US1 (config metadata)
3. Complete Phase 4: US2 (index + search)
4. **STOP and VALIDATE**: Agents can search tools with metadata — core value delivered
5. Demo: `ToolIndex.from_configs(configs).search(query="commit")`

### Incremental Delivery

1. Setup → Baseline confirmed
2. US1 → Config authors can annotate with category/tags → Test independently
3. US2 → Agents can search tools by keyword/category/CLI → Test independently (MVP!)
4. US3 → Agents can browse available CLIs → Test independently
5. US4 → Agents can resolve tools for execution → Test independently
6. Polish → Bundled configs enriched, full validation

### Single Developer Strategy

1. Complete phases sequentially: Setup → US1 → US2 → US3 → US4 → Polish
2. Each user story is a natural commit point
3. US1 + US2 together form the MVP — stop here if needed

---

## Notes

- All production code goes in `climax.py` (Constitution Principle I — single-file core)
- No new external dependencies allowed (FR-015)
- Use `build_input_schema()` to generate `input_schema` for ToolIndexEntry (reuse existing function per research R5)
- Use `str.__contains__` with lowercased strings for search — no regex (research R3)
- Pre-compute `_search_text` at index build time for performance (research R4/R8)
- Existing `load_configs()` and MCP tool registration paths must not be modified (FR-014)
