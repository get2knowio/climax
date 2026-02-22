# Implementation Plan: Progressive Discovery Tests & Token Benchmark

**Branch**: `003-discovery-tests` | **Date**: 2026-02-21 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/003-discovery-tests/spec.md`

## Summary

Add comprehensive test coverage for CLImax's progressive discovery feature (ToolIndex, climax_search, climax_call) and create a token savings benchmark script. This involves:

1. **Gap analysis**: Existing `test_index.py` (43 tests) and `test_meta_tools.py` (~50 tests) already cover most FR-001 through FR-021. New tests fill remaining gaps.
2. **Implementation fix**: Enrich `climax_call` unknown-tool error to list available tools (FR-019).
3. **Integration tests**: New `test_integration_discovery.py` exercises real bundled YAML configs in both default and classic modes (FR-022 through FR-026).
4. **Benchmark script**: New `scripts/benchmark_tokens.py` measures token savings using tiktoken as an optional extra (FR-027 through FR-030).

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: mcp>=1.7, pyyaml>=6.0, pydantic>=2.0, rich>=13.0 (runtime); pytest>=8.0, pytest-asyncio>=0.24 (test); tiktoken (benchmark only)
**Storage**: N/A — in-memory ToolIndex
**Testing**: pytest + pytest-asyncio (`asyncio_mode = "auto"`)
**Target Platform**: macOS / Linux (CI: GitHub Actions across Python 3.11, 3.12, 3.13)
**Project Type**: CLI / MCP server library
**Performance Goals**: Unit tests < 5s, integration tests < 25s, full suite < 30s (SC-006)
**Constraints**: No new runtime dependencies; tiktoken is benchmark-only optional extra
**Scale/Scope**: ~15 new tests + 1 implementation fix + 1 benchmark script

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Single-File Core | PASS | Implementation fix (FR-019) modifies `climax.py` inline. No new modules. |
| II. YAML-Driven | PASS | Tests consume existing YAML configs. No hardcoded CLI knowledge added. |
| III. Multi-Config | PASS | Integration tests exercise multi-config loading (git + docker + jj). |
| IV. Secure by Default | PASS | No changes to subprocess execution or shell handling. |
| Technology Stack | PASS | tiktoken added as optional benchmark extra only — not a runtime dependency. |
| Code Style | PASS | Tests follow existing patterns (inline fixtures, mock subprocess, class-based). |

**Post-Phase 1 re-check**: PASS — No violations introduced. The benchmark extra (`tiktoken`) is test/benchmark-scoped, consistent with the constitution's "no new runtime deps" stance.

## Project Structure

### Documentation (this feature)

```text
specs/003-discovery-tests/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── test-contract.md # Test organization and naming contract
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
climax.py                           # Implementation fix: FR-019 unknown-tool error enrichment
tests/
├── conftest.py                     # Existing (no changes needed — fixtures reused)
├── test_index.py                   # Existing (43 tests — already covers FR-001 through FR-011)
├── test_meta_tools.py              # Existing (~50 tests — covers most FR-012 through FR-020)
├── test_discovery_gaps.py          # NEW: Gap tests for FR-019 enriched error, FR-021 timeout parity
└── test_integration_discovery.py   # NEW: Integration tests with real configs (FR-022 through FR-026)
scripts/
└── benchmark_tokens.py             # NEW: Token savings benchmark (FR-027 through FR-030)
pyproject.toml                      # Add `benchmark` optional extra with tiktoken
```

**Structure Decision**: Single-project layout matching existing repository structure. Tests live in `tests/` alongside existing test files. Benchmark script lives in new `scripts/` directory per spec clarification.

## Complexity Tracking

> No constitution violations. Table intentionally left empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| *(none)* | | |
