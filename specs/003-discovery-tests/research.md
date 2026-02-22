# Research: Progressive Discovery Tests & Token Benchmark

## R-001: Existing Test Coverage Gap Analysis

**Decision**: Most FR requirements are already covered by existing tests; only targeted gaps need new test code.

**Rationale**: A thorough review of `test_index.py` (43 tests across 6 classes) and `test_meta_tools.py` (~50 tests across 8 classes) shows the following coverage:

| Requirement | Covered By | Status |
|-------------|-----------|--------|
| FR-001 (multi-config indexing) | `test_index.py::TestFromConfigs` | COVERED |
| FR-002 (category/tags parsing) | `test_index.py::TestSearch::test_entry_fields_populated`, `test_plain_config_no_category` | COVERED |
| FR-003 (keyword search across fields) | `test_index.py::TestSearch` (5+ tests) | COVERED |
| FR-004 (category filter) | `test_index.py::TestSearch::test_category_exact_filter` | COVERED |
| FR-005 (CLI name filter) | `test_index.py::TestSearch::test_cli_exact_filter` | COVERED |
| FR-006 (combined AND logic) | `test_index.py::TestSearch::test_combined_*` (4 tests) | COVERED |
| FR-007 (no-filter → summary path) | `test_meta_tools.py::TestClimaxSearch::test_no_filter_returns_summary` | COVERED |
| FR-008 (summary content) | `test_index.py::TestSummary` (8 tests) | COVERED |
| FR-009 (get exact/unknown) | `test_index.py::TestGet` (5 tests) | COVERED |
| FR-010 (limit parameter) | `test_index.py::TestSearch::test_limit_*` (3 tests) | COVERED |
| FR-011 (case-insensitivity) | `test_index.py::TestSearch::test_case_insensitive_query`, `test_category_case_insensitive`, `test_cli_case_insensitive` | COVERED |
| FR-012 (search result structure) | `test_meta_tools.py::TestClimaxSearch::test_search_by_query_returns_matching_tools` | COVERED |
| FR-013 (no-filter → summary) | `test_meta_tools.py::TestClimaxSearch::test_no_filter_returns_summary` | COVERED |
| FR-014 (empty results, not error) | `test_meta_tools.py::TestClimaxSearch::test_no_match_returns_empty_results` | COVERED |
| FR-015 (limit in climax_search) | `test_meta_tools.py::TestClimaxSearch::test_limit_caps_results` | COVERED |
| FR-016 (routing by name) | `test_meta_tools.py::TestClimaxCall::test_call_tool_no_args_returns_stdout`, `test_call_tool_with_valid_args` | COVERED |
| FR-017 (missing required arg error) | `test_meta_tools.py::TestClimaxCall::test_missing_required_arg_returns_validation_error` | COVERED |
| FR-018 (invalid enum error) | `test_meta_tools.py::TestClimaxCall::test_invalid_enum_value_returns_error` | COVERED |
| FR-019 (unknown tool → list tools) | `test_meta_tools.py::TestClimaxCall::test_unknown_tool_name_returns_error` | **GAP** — tests for "Unknown tool" text but not for listing available tools |
| FR-020 (subprocess delegation) | `test_meta_tools.py::TestClimaxCall::test_call_tool_with_valid_args` | COVERED |
| FR-021 (timeout/error parity) | *(none)* | **GAP** — no explicit parity test |
| FR-022–FR-026 (integration tests) | *(none)* | **GAP** — no real-config integration tests exist |
| FR-027–FR-030 (benchmark) | *(none)* | **GAP** — no benchmark script exists |

**Alternatives considered**: Writing all tests from scratch was rejected — it would duplicate ~90 existing tests and waste effort.

## R-002: FR-019 Unknown-Tool Error Enrichment

**Decision**: Modify `_handle_climax_call` in `climax.py` (line 1007) to include a sorted list of available tool names in the error message.

**Rationale**: The current implementation returns `f"Unknown tool: {tool_name}"` without context. The spec requires listing available tools to help LLMs recover. The implementation change is minimal:

```python
# Current (line 1007):
return [types.TextContent(type="text", text=f"Unknown tool: {tool_name}")]

# Proposed:
available = sorted(tool_map.keys())
return [types.TextContent(
    type="text",
    text=f"Unknown tool: {tool_name}. Available tools: {', '.join(available)}"
)]
```

This keeps the existing prefix for backward compatibility (existing test `test_unknown_tool_name_returns_error` checks for `"Unknown tool: nonexistent_tool"` via `in` assertion) while adding the tool list.

**Alternatives considered**:
- Returning a JSON structure instead of plain text: Rejected — `climax_call` error responses are plain text throughout; changing format would be inconsistent.
- Including tool descriptions in the list: Rejected — too verbose; tool names alone are sufficient for the LLM to retry with `climax_search`.

## R-003: FR-021 Timeout/Error Parity Testing

**Decision**: Add a test that verifies `climax_call` and classic-mode `call_tool` produce equivalent output when `run_command` returns a non-zero exit code or raises `TimeoutError`.

**Rationale**: Both code paths share `_execute_tool` (lines 879-966), so parity is architecturally guaranteed. However, the spec explicitly requires a test to guard against regression if the paths diverge in the future.

**Approach**: Mock `run_command` to return `(1, "", "error output")` and verify both modes produce the same response text. Repeat with a `TimeoutError` raise.

**Alternatives considered**:
- Testing with real slow subprocess + timeout: Rejected — would add >30s to test suite, violating SC-006.

## R-004: Integration Test Strategy (FR-022 through FR-026)

**Decision**: Create `test_integration_discovery.py` that loads real bundled YAML configs from `configs/` directory and exercises the full MCP handler chain.

**Rationale**: Existing unit tests use inline fixtures which don't catch config-loading bugs. Integration tests with real configs verify the full path: YAML file → Pydantic validation → ToolIndex construction → MCP handler response.

**Approach**:
- Load `configs/git.yaml`, `configs/docker.yaml`, `configs/jj.yaml` via `load_config()`
- FR-022: Build default-mode server, verify `list_tools` returns exactly 2 meta-tools
- FR-023: Build classic-mode server, verify `list_tools` returns all individual tools
- FR-024: Search for "version control" and "vcs", verify git and jj tools surface
- FR-025: Filter by CLI name "git-tools", verify only git tools returned
- FR-026: Call a tool via `climax_call` with mocked subprocess, then call same tool in classic mode — verify same response structure
- Only `git` is assumed available in CI; all subprocess calls are mocked

**Alternatives considered**:
- Using example configs (coreutils.yaml) instead of bundled configs: Rejected — spec explicitly names git.yaml, docker.yaml; bundled configs have richer category/tags metadata.

## R-005: Token Benchmark Script (FR-027 through FR-030)

**Decision**: Create `scripts/benchmark_tokens.py` using tiktoken (`cl100k_base` encoding) as an optional `benchmark` extra.

**Rationale**: tiktoken provides accurate OpenAI-compatible token counting. Using `cl100k_base` (GPT-4 encoding) gives a reasonable proxy for Claude tokenization since exact Claude tokenizer is not publicly available. The key metric is the *ratio* of discovery vs classic tokens, which is encoding-independent.

**Approach**:
1. Load all configs from `configs/` directory
2. Build both classic-mode and default-mode server tool lists
3. Serialize both to JSON (matching MCP tools/list response format)
4. Count tokens with tiktoken
5. Print a markdown-formatted comparison table

**Output format**:
```
| Mode      | Tools | Tokens | Savings |
|-----------|-------|--------|---------|
| Classic   | N     | XXXX   |         |
| Discovery | 2     | YYYY   | ZZ.Z%   |
```

**Alternatives considered**:
- Word-count or character-count proxy: Rejected — spec clarification explicitly chose tiktoken.
- Making tiktoken a runtime dependency: Rejected — spec says test/optional extra only.
- Adding benchmark to pytest suite: Rejected — spec says standalone script, not part of test suite.

## R-006: pyproject.toml Benchmark Extra

**Decision**: Add a `benchmark` optional dependency group with `tiktoken`.

**Rationale**: Keeps tiktoken out of the runtime dependency tree while making it easily installable via `uv sync --extra benchmark`.

```toml
[project.optional-dependencies]
test = ["pytest>=8.0", "pytest-asyncio>=0.24"]
benchmark = ["tiktoken>=0.7"]
```

**Alternatives considered**:
- Adding to `test` extra: Rejected — tiktoken is heavy and not needed for regular test runs.
- No extra, just `pip install tiktoken` manually: Rejected — not reproducible.
