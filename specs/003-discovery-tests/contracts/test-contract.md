# Test Contract: Progressive Discovery Tests

## Test Organization

### Naming Convention

All test files follow the existing pattern: `test_<module_or_feature>.py` in `tests/`.

| File | Scope | Fixture Source |
|------|-------|----------------|
| `test_discovery_gaps.py` | Unit tests for spec gaps not covered by existing tests | Inline Pydantic fixtures + mocked subprocess |
| `test_integration_discovery.py` | Integration tests with real YAML configs | Real `configs/*.yaml` files + mocked subprocess |

### Test Class Naming

Classes follow the pattern `Test<Feature><Aspect>`:

- `TestClimaxCallUnknownToolEnriched` — FR-019 enriched error message
- `TestTimeoutErrorParity` — FR-021 timeout/error parity
- `TestDiscoveryModeIntegration` — FR-022, FR-024, FR-025
- `TestClassicModeIntegration` — FR-023
- `TestOutputEquivalence` — FR-026

### Test Method Naming

Methods follow `test_<what>_<condition>_<expected>` or `test_<scenario>`:

```python
# Good
def test_unknown_tool_error_lists_available_tools(self): ...
def test_timeout_error_same_in_both_modes(self): ...

# Bad
def test_1(self): ...
def test_it_works(self): ...
```

## Helper Functions

### Shared Helpers (reused from existing tests)

| Helper | Defined In | Purpose |
|--------|-----------|---------|
| `_unwrap(result)` | `test_meta_tools.py` | Unwrap MCP `ServerResult` wrapper |
| `_call_tool(server, name, args)` | `test_meta_tools.py` | Invoke `call_tool` handler |
| `_list_tools(server)` | `test_meta_tools.py` | Invoke `list_tools` handler |
| `_build_tool_map(configs)` | `test_meta_tools.py` | Build tool_map from configs |

These helpers should be duplicated in each new test file (or moved to `conftest.py` if the duplication becomes burdensome). The existing pattern is to define helpers per-file.

## Mock Boundaries

### Unit Tests (`test_discovery_gaps.py`)

- `climax.run_command` is mocked via `unittest.mock.patch` + `AsyncMock`
- ToolIndex and tool_map are built from inline Pydantic fixtures
- No file I/O, no real subprocess calls

### Integration Tests (`test_integration_discovery.py`)

- Real YAML configs loaded from `configs/` directory via `load_config()`
- `climax.run_command` is mocked for all subprocess calls
- MCP handlers invoked directly via `server.request_handlers`
- No MCP stdio transport involved

## Response Format Contract

### climax_search Response

```json
{
  "mode": "search",
  "results": [
    {
      "tool_name": "string",
      "description": "string",
      "cli_name": "string",
      "category": "string|null",
      "tags": ["string"],
      "input_schema": { "type": "object", "properties": {...} }
    }
  ]
}
```

Summary mode:
```json
{
  "mode": "summary",
  "summary": [
    {
      "name": "string",
      "description": "string",
      "tool_count": 0,
      "category": "string|null",
      "tags": ["string"]
    }
  ]
}
```

### climax_call Error Responses

Unknown tool (after FR-019 fix):
```
Unknown tool: {tool_name}. Available tools: {sorted comma-separated list}
```

Validation error:
```
Argument validation failed:
  - Missing required argument: {arg_name}
  - ...
```

## Benchmark Script Contract

### Input
- All YAML files from `configs/` directory

### Output
- Markdown-formatted table to stdout
- Exit code 0 on success
- Exit code 1 if no configs found

### Determinism
- Same configs → same token counts (no randomness, no timestamp-dependent data)
