# Implementation Plan: Tool Discovery Index

**Branch**: `001-tool-discovery-index` | **Date**: 2026-02-21 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-tool-discovery-index/spec.md`

## Summary

Extend CLImax YAML config schema with optional `category` and `tags` fields, and add a `ToolIndex` class that provides in-memory search, summary, and exact-lookup of tools across all loaded configs. This enables progressive tool discovery — agents can search/browse instead of loading all tool definitions into context.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: mcp>=1.7, pyyaml>=6.0, pydantic>=2.0, rich>=13.0 (no new deps — FR-015)
**Storage**: N/A — in-memory index built at construction time
**Testing**: pytest + pytest-asyncio (`asyncio_mode = "auto"`)
**Target Platform**: Cross-platform (macOS, Linux) — stdio MCP transport
**Project Type**: CLI / MCP server library (single-file core: `climax.py`)
**Performance Goals**: Search across 50+ tools in <50ms (SC-003)
**Constraints**: No new external dependencies; single-file core; no shell execution
**Scale/Scope**: Currently 76 tools across 5 bundled configs; index designed for ~hundreds

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Single-File Core | **PASS** | All new code added to `climax.py`. Constitution explicitly allows "Supporting utilities (index, search) MAY live in separate files" but the feature is small enough (~120 lines) to keep in the single file. |
| II. YAML-Driven | **PASS** | `category` and `tags` are YAML config metadata. No hardcoded CLI knowledge introduced. |
| III. Multi-Config | **PASS** | `ToolIndex` is built from multiple configs. Duplicate tool name handling follows existing behavior (last wins with warning). |
| IV. Secure by Default | **PASS** | No new subprocess execution vectors. Index is read-only in-memory data. |

**Gate result: PASS** — No violations. No entries needed in Complexity Tracking.

### Post-Phase 1 Re-check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Single-File Core | **PASS** | 3 new Pydantic models + 1 class with 3 methods added to `climax.py`. Total file grows from ~530 to ~650 lines. |
| II. YAML-Driven | **PASS** | New fields are optional YAML config metadata only. |
| III. Multi-Config | **PASS** | `ToolIndex.from_configs()` accepts a list of configs and merges all tools. |
| IV. Secure by Default | **PASS** | Case-insensitive substring matching via `in` operator — no regex used (R3). No subprocess changes. |

## Project Structure

### Documentation (this feature)

```text
specs/001-tool-discovery-index/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── tool-index-api.md
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
climax.py                # Extended: +3 Pydantic models, +1 ToolIndex class
tests/
├── conftest.py          # Extended: fixtures with category/tags
├── test_config.py       # Extended: category/tags loading tests
└── test_index.py        # New: ToolIndex search/summary/get tests
examples/
└── coreutils.yaml       # Unchanged (backward compat)
configs/
├── git.yaml             # Optionally add category/tags (non-breaking)
└── ...                  # Other bundled configs unchanged
```

**Structure Decision**: Single-file project. All new production code goes into `climax.py` per Constitution Principle I. New test file `test_index.py` covers the ToolIndex class. Existing test files get minor extensions for schema changes.

## Complexity Tracking

> No violations — table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
