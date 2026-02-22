# Quickstart: Progressive Discovery Tests & Token Benchmark

## Prerequisites

```bash
# Install with test dependencies
uv sync --extra test

# Install with benchmark dependencies (for token counting)
uv sync --extra benchmark
```

## Running the Tests

### All tests (including new discovery tests)

```bash
uv run pytest -v
```

### Only discovery gap tests (FR-019 enriched error, FR-021 timeout parity)

```bash
uv run pytest tests/test_discovery_gaps.py -v
```

### Only integration tests with real configs (FR-022 through FR-026)

```bash
uv run pytest tests/test_integration_discovery.py -v
```

### Only existing ToolIndex and meta-tool tests

```bash
uv run pytest tests/test_index.py tests/test_meta_tools.py -v
```

## Running the Benchmark

```bash
# Install benchmark deps first
uv sync --extra benchmark

# Run the benchmark script
uv run python scripts/benchmark_tokens.py
```

Expected output:

```
Token Savings: Progressive Discovery vs Classic Mode
=====================================================

Configs loaded: 5 (git-tools, docker-tools, claude-tools, jj-tools, obsidian-tools)
Total tools across all configs: 61

| Mode      | Tools | Tokens | Savings |
|-----------|-------|--------|---------|
| Classic   | 61    | ~XXXX  |         |
| Discovery | 2     | ~YYYY  | ~ZZ.Z%  |
```

## Key Files

| File | Purpose |
|------|---------|
| `tests/test_index.py` | Existing ToolIndex unit tests (43 tests) |
| `tests/test_meta_tools.py` | Existing meta-tool unit tests (~50 tests) |
| `tests/test_discovery_gaps.py` | **NEW**: Gap tests for FR-019, FR-021 |
| `tests/test_integration_discovery.py` | **NEW**: Integration tests with real YAML configs |
| `scripts/benchmark_tokens.py` | **NEW**: Token savings benchmark |
| `climax.py` | Implementation fix: FR-019 unknown-tool error enrichment |
| `pyproject.toml` | Add `benchmark` optional extra |

## Verifying the Implementation Fix (FR-019)

The unknown-tool error message in `climax_call` now includes available tool names:

```
Before: "Unknown tool: nonexistent_tool"
After:  "Unknown tool: nonexistent_tool. Available tools: docker_build, docker_images, ..."
```

Test this interactively:

```bash
# Start the server in discovery mode
uv run climax git docker

# In another terminal, send an MCP call_tool request for a nonexistent tool
# The error response should list available tools
```
