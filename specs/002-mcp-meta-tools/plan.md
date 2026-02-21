# Implementation Plan: MCP Meta-Tools for Progressive Discovery

**Branch**: `002-mcp-meta-tools` | **Date**: 2026-02-21 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-mcp-meta-tools/spec.md`

## Summary

Add two MCP meta-tools (`climax_search` and `climax_call`) that replace direct tool registration as CLImax's default mode. In default mode, `tools/list` returns only these two meta-tools; agents discover and execute CLI tools through them via the existing `ToolIndex`. A `--classic` flag preserves the current direct-registration behavior. All changes live in `climax.py` (single-file core) with no new dependencies.

## Technical Context

**Language/Version**: Python 3.11+ with full type hints
**Primary Dependencies**: mcp>=1.7, pyyaml>=6.0, pydantic>=2.0, rich>=13.0 (no new deps)
**Storage**: N/A — in-memory ToolIndex built at startup
**Testing**: pytest + pytest-asyncio (`asyncio_mode = "auto"`)
**Target Platform**: CLI tool, MCP stdio transport
**Project Type**: CLI / MCP server (single-file)
**Performance Goals**: Meta-tool responses <50ms (ToolIndex search already meets this)
**Constraints**: Single-file core (`climax.py`), no new external dependencies, no YAML schema changes
**Scale/Scope**: ~100-150 new lines in climax.py, ~200-300 lines of new tests

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Single-File Core** | ✅ PASS | All new logic (meta-tool handlers, arg validation, mode switching) goes in `climax.py`. No new modules. |
| **II. YAML-Driven** | ✅ PASS | YAML schema is NOT modified (FR-017). Meta-tools are built-in CLImax behavior, not per-CLI config. |
| **III. Multi-Config** | ✅ PASS | Meta-tools operate on the shared ToolIndex which already handles multi-config merge. |
| **IV. Secure by Default** | ✅ PASS | `climax_call` delegates to existing `build_command` + `run_command` (no shell). Adds in-process arg validation before execution. |
| **Technology Stack** | ✅ PASS | No new dependencies. Uses existing Pydantic, MCP SDK, asyncio patterns. |
| **Code Style** | ✅ PASS | Type hints, Pydantic models, Google-style docstrings, snake_case. |

**Pre-design gate: PASSED** — no violations.

## Project Structure

### Documentation (this feature)

```text
specs/002-mcp-meta-tools/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── mcp-tools.md     # Meta-tool MCP contracts
└── tasks.md             # Phase 2 output (NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
climax.py                # All new logic added here (~100-150 new lines)
tests/
├── test_server.py       # Extended with meta-tool handler tests
└── test_meta_tools.py   # New: dedicated meta-tool test file (search, call, mode switching)
```

**Structure Decision**: Single-file project — all production code stays in `climax.py`. Tests are split: existing `test_server.py` keeps classic-mode tests unchanged, new `test_meta_tools.py` covers meta-tool behavior.

## Complexity Tracking

> No violations — table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
