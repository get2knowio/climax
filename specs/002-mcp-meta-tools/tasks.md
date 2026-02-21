# Tasks: MCP Meta-Tools for Progressive Discovery

**Input**: Design documents from `/specs/002-mcp-meta-tools/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/mcp-tools.md

**Tests**: Explicitly requested via SC-007 and plan.md (`tests/test_meta_tools.py`).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single-file core**: All production code in `climax.py` at repository root
- **Tests**: `tests/test_meta_tools.py` (new), `tests/test_server.py` (existing, unchanged)

---

## Phase 1: Setup

**Purpose**: Verify baseline before making changes

- [x] T001 Run existing test suite (`uv run pytest -v`) to confirm all tests pass before changes

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared building blocks that MUST be complete before any user story implementation

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T002 Implement `validate_tool_args(args: dict[str, Any], tool_def: ToolDef) -> tuple[dict[str, Any], list[str]]` function in `climax.py` — validates and coerces `climax_call` arguments against `ToolArg` definitions: (1) required args present, (2) type coercion (string→int via `int()`, string→float via `float()`, string→bool for "true"/"false", numeric→string via `str()`), (3) enum constraints, (4) extra keys silently ignored. Returns (coerced_args, error_messages). Error messages must follow the format in `contracts/mcp-tools.md` (e.g., "Missing required argument 'message'", "Argument 'count': cannot convert 'hello' to integer", "Argument 'format' must be one of: json, text, csv").
- [x] T003 Extract the execution logic from the current `call_tool` handler (lines 743-831) in `climax.py` into a reusable async helper function `_execute_tool(resolved: ResolvedTool, arguments: dict[str, Any], executor: ExecutorConfig | None) -> list[types.TextContent]` — this helper handles policy validation, `build_command`, stdin/cwd extraction, docker prefix, `run_command`, logging, and response formatting. The existing classic `call_tool` handler must call this helper (zero behavior change). This ensures SC-004 (identical output between `climax_call` and direct calls).
- [x] T004 Modify `load_configs()` in `climax.py` to also return the list of `CLImaxConfig` objects — change return type to `tuple[str, dict[str, ResolvedTool], list[CLImaxConfig]]` so that `cmd_run` can build a `ToolIndex` from the configs. Update all callers (`cmd_run`, `cmd_list`, backward-compat path).

**Checkpoint**: Foundation ready — `validate_tool_args`, `_execute_tool` helper, and config-returning `load_configs` are available for meta-tool implementation

---

## Phase 3: User Story 1 — Agent Searches for Tools via MCP (Priority: P1)

**Goal**: An agent calls `climax_search` with keyword/category/cli filters and receives structured JSON results with full tool schemas, or a CLI summary when called with no filters.

**Independent Test**: Start a CLImax server with multiple configs, call `climax_search` via the MCP `call_tool` handler with various filter combinations, and verify JSON responses.

### Implementation for User Story 1

- [x] T005 [US1] Add `index: ToolIndex | None = None` parameter to `create_server()` in `climax.py` and implement `climax_search` handler inside the `call_tool` dispatcher — when `call_tool` receives name `"climax_search"`, parse arguments (`query`, `category`, `cli`, `limit` with default 10), determine mode (summary when all three filter params absent per FR-003, search otherwise), call `index.search()` or `index.summary()`, serialize results via `model_dump()`, return JSON string as `TextContent` with format `{"mode": "search", "results": [...]}` or `{"mode": "summary", "summary": [...]}` per FR-004. Cap summary results at `limit`. Register `climax_search` in `list_tools` with inputSchema from `contracts/mcp-tools.md`.
- [x] T006 [US1] Write `climax_search` tests in `tests/test_meta_tools.py` — create test file with fixtures (multi-config ToolIndex with git/docker-like tools, mock `create_server` in default mode). Test cases per acceptance scenarios: (1) search by query "commit" returns matching tools with full schema, (2) filter by category returns only matching category, (3) filter by cli name returns only that CLI's tools, (4) combined query+category uses AND logic, (5) limit caps results, (6) no-filter call returns summary with CLI names/tool counts/categories, (7) no-match query returns empty results list (not error). Use the `_unwrap()` pattern from `test_server.py`.

**Checkpoint**: `climax_search` is functional and tested — agents can discover tools

---

## Phase 4: User Story 2 — Agent Executes a Discovered Tool via MCP (Priority: P1)

**Goal**: An agent calls `climax_call` with a tool name and arguments. The system validates args, executes the CLI command, and returns stdout/stderr/exit code.

**Independent Test**: Call `climax_call` with known tool names and arguments, verify subprocess runs and returns expected output format.

### Implementation for User Story 2

- [x] T007 [US2] Implement `climax_call` handler inside the `call_tool` dispatcher in `climax.py` — when `call_tool` receives name `"climax_call"`, extract `tool_name` (required) and `args` (optional, default `{}`), look up tool via `index.get(tool_name)` per FR-006, return "Unknown tool: {name}" if not found, call `validate_tool_args()` for arg validation per FR-007/FR-008, return formatted validation errors if any, then delegate to `_execute_tool()` helper for execution per FR-009/FR-010. Apply policy constraints via `validate_arguments()` if `resolved.arg_constraints` exist per FR-015. Register `climax_call` in `list_tools` with inputSchema from `contracts/mcp-tools.md`.
- [x] T008 [US2] Write `climax_call` tests in `tests/test_meta_tools.py` — test cases per acceptance scenarios: (1) call tool with no args returns stdout, (2) call tool with valid args passes them correctly, (3) missing required arg returns validation error with arg name, (4) invalid enum value returns error listing valid values, (5) unknown tool_name returns "Unknown tool" error, (6) type coercion (string "42" → int) works, (7) incompatible type (string "hello" for int) returns error, (8) extra keys in args are silently ignored, (9) args=None with no required args succeeds. Use real `echo`/`expr` for integration tests or mock subprocess.

**Checkpoint**: `climax_call` is functional and tested — agents can execute discovered tools

---

## Phase 5: User Story 3 — Progressive Discovery Is the Default Mode (Priority: P1)

**Goal**: When CLImax starts without `--classic`, `tools/list` returns only `climax_search` and `climax_call`. All configured tools remain accessible via `climax_call`.

**Independent Test**: Start CLImax with a multi-tool config, call `list_tools`, verify only 2 tools appear.

### Implementation for User Story 3

- [x] T009 [US3] Add `classic: bool = False` parameter to `create_server()` in `climax.py` and implement mode-based dispatch — in default mode (`classic=False`): `list_tools` returns exactly 2 tools (`climax_search`, `climax_call`), `call_tool` dispatches to meta-tool handlers for these names and returns "Unknown tool" for any other name per FR-011. In classic mode (`classic=True`): `list_tools` returns all individual tools (current behavior), `call_tool` dispatches to individual tools via `_execute_tool()` per FR-012. Both modes share the same ToolIndex and execution logic per FR-013.
- [x] T010 [US3] Wire up ToolIndex and mode selection in `cmd_run()` in `climax.py` — after `load_configs()`, build `ToolIndex.from_configs(configs)` from the returned config list, pass `index` and `classic=False` (default) to `create_server()`. Also update the backward-compat path (when first positional arg is not a subcommand) to build ToolIndex and pass it through. ToolIndex is always built per FR-014.
- [x] T011 [US3] Write default mode tests in `tests/test_meta_tools.py` — test cases: (1) `list_tools` returns exactly 2 tools named `climax_search` and `climax_call` when config has 10+ tools, (2) all configured tools are still accessible via `climax_call`, (3) calling an individual tool name directly returns "Unknown tool" in default mode.

**Checkpoint**: Progressive discovery is the default — agents see only 2 meta-tools

---

## Phase 6: User Story 4 — Classic Mode Registers All Tools Directly (Priority: P2)

**Goal**: When `--classic` is passed, all individual tools appear in `tools/list` and meta-tools do not.

**Independent Test**: Start CLImax with `--classic` and a multi-tool config, call `list_tools`, verify all individual tools appear.

### Implementation for User Story 4

- [x] T012 [US4] Add `--classic` flag to `run` subcommand parser and backward-compat parser in `climax.py` — add `parser.add_argument("--classic", action="store_true", default=False)` to both `_build_run_parser()` and the backward-compat parser. Pass `args.classic` to `create_server()` in `cmd_run()`.
- [x] T013 [US4] Write classic mode tests in `tests/test_meta_tools.py` — test cases per acceptance scenarios: (1) with `classic=True`, `list_tools` returns all individual tools, (2) `climax_search` and `climax_call` do NOT appear in classic `list_tools`, (3) ToolIndex is still built internally in classic mode (verify by checking `index` is not None).

**Checkpoint**: Classic mode preserves backward compatibility — users can opt in to direct registration

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Verify everything works together

- [x] T014 [P] Run full test suite (`uv run pytest -v`) — all existing tests must pass unchanged (SC-003) plus all new `test_meta_tools.py` tests
- [x] T015 [P] Run quickstart.md validation — manually verify the agent interaction examples from `specs/002-mcp-meta-tools/quickstart.md` work with the implemented meta-tools

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — run immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Foundational (T005 needs `create_server` `index` param)
- **US2 (Phase 4)**: Depends on Foundational (T007 needs `validate_tool_args` and `_execute_tool`)
- **US3 (Phase 5)**: Depends on US1 + US2 (T009 needs both meta-tool handlers implemented)
- **US4 (Phase 6)**: Depends on US3 (T012 needs mode switching to exist)
- **Polish (Phase 7)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (P1)**: Can start after Foundational — no dependency on other stories
- **US2 (P1)**: Can start after Foundational — no dependency on US1 (US1 and US2 can run in parallel)
- **US3 (P1)**: Depends on US1 + US2 — integrates both meta-tools into mode switching
- **US4 (P2)**: Depends on US3 — classic mode is the alternative to default mode

### Within Each User Story

- Implementation before tests (tests validate the implementation)
- Core handler logic before integration wiring
- Story complete before moving to next priority

### Parallel Opportunities

- **US1 and US2 can run in parallel** after Foundational phase (different handler logic, both editing `climax.py` but different sections)
- T005 and T007 (implementations) target different handlers — parallelizable
- T006 and T008 (tests) both write to `test_meta_tools.py` — serialize if single developer, parallelize if multiple
- T014 and T015 (polish) are independent

---

## Parallel Example: US1 + US2

```
# After Foundational phase completes, launch in parallel:
Task A: "Implement climax_search handler in climax.py" (T005)
Task B: "Implement climax_call handler in climax.py" (T007)

# Then write tests (can parallelize if different developers):
Task C: "Write climax_search tests in tests/test_meta_tools.py" (T006)
Task D: "Write climax_call tests in tests/test_meta_tools.py" (T008)
```

---

## Implementation Strategy

### MVP First (US1 + US2 + US3)

1. Complete Phase 1: Setup (verify baseline)
2. Complete Phase 2: Foundational (`validate_tool_args`, `_execute_tool`, `load_configs` return)
3. Complete Phase 3: US1 — `climax_search` works
4. Complete Phase 4: US2 — `climax_call` works
5. Complete Phase 5: US3 — default mode exposes only 2 meta-tools
6. **STOP and VALIDATE**: Run full test suite, test US1-US3 independently
7. Deploy/demo with progressive discovery as default

### Incremental Delivery

1. Setup + Foundational → building blocks ready
2. Add US1 → agents can search for tools (partial value)
3. Add US2 → agents can execute tools (full search+call workflow)
4. Add US3 → progressive discovery is the default (MVP complete!)
5. Add US4 → classic mode for backward compat (full feature)
6. Polish → final validation

---

## Notes

- All production code goes in `climax.py` (~100-150 new lines per plan.md)
- All new tests go in `tests/test_meta_tools.py` (~200-300 lines per plan.md)
- Existing `tests/test_server.py` must NOT be modified (SC-003)
- No new dependencies allowed (FR-017 / constitution)
- No YAML schema changes (FR-017)
- `_execute_tool` extraction (T003) is critical for SC-004 (identical output)
