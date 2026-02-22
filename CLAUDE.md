# CLImax

CLImax is a single-file Python app (`climax.py`) that exposes any CLI as MCP tools via YAML configuration. YAML configs in, MCP tools out over stdio. It is **not** a network server — it communicates via stdin/stdout using the MCP stdio transport.

## Architecture

- **Single source file**: All logic lives in `climax.py` (~530 lines)
- **Config models**: Pydantic models (`CLImaxConfig`, `ToolDef`, `ToolArg`) validate YAML
- **Flow**: YAML config → Pydantic validation → MCP tool registration → subprocess execution on tool call
- **No shell**: Commands run via `asyncio.create_subprocess_exec` (no shell injection)

## Development

```bash
# Install with test deps
uv sync --extra test

# Run tests
uv run pytest -v

# CLI subcommands
uv run climax validate git                  # check config validity (bundled name)
uv run climax list                          # list available bundled configs
uv run climax list git                      # show tools table
uv run climax run git                       # start MCP stdio (explicit)
uv run climax git                           # start MCP stdio (backward compat)
```

## Testing

Tests live in `tests/` and use pytest + pytest-asyncio (`asyncio_mode = "auto"`).

| File | What it covers |
|------|---------------|
| `test_config.py` | YAML loading, Pydantic validation, multi-config merge, example smoke tests |
| `test_schema.py` | `build_input_schema` → JSON Schema correctness |
| `test_command.py` | `build_command` — positional/flag ordering, booleans, auto-flags, defaults |
| `test_run.py` | `run_command` — async subprocess with mocked/real processes |
| `test_server.py` | MCP handler integration — `list_tools`/`call_tool` via direct handler invocation |
| `test_cli.py` | CLI subcommands (validate, list) and backward compatibility |
| `test_e2e.py` | End-to-end: MCP tool call → real subprocess → response, using `examples/coreutils.yaml` |

Key patterns:
- **Inline fixtures** in `conftest.py` — tests don't depend on example YAML files
- **Mock subprocess** for unit tests, real `echo`/`expr` for integration
- **`_unwrap()` helper** in `test_server.py` for MCP's `ServerResult` wrapper
- **`Console(file=StringIO())`** for capturing CLI output in tests

## Key design decisions

- Backward compat: `climax config.yaml` still works (detected by checking if first positional arg is a known subcommand)
- `cmd_validate` and `cmd_list` accept an optional `console` parameter for testability
- MCP handler tests invoke handlers directly via `server.request_handlers` — no stdio needed

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs pytest across Python 3.11, 3.12, 3.13 using `uv`.

## Active Technologies
- Python 3.11+ + mcp>=1.7, pyyaml>=6.0, pydantic>=2.0, rich>=13.0 (no new deps — FR-015) (001-tool-discovery-index)
- N/A — in-memory index built at construction time (001-tool-discovery-index)
- Python 3.11+ with full type hints + mcp>=1.7, pyyaml>=6.0, pydantic>=2.0, rich>=13.0 (no new deps) (002-mcp-meta-tools)
- N/A — in-memory ToolIndex built at startup (002-mcp-meta-tools)
- Python 3.11+ + mcp>=1.7, pyyaml>=6.0, pydantic>=2.0, rich>=13.0 (runtime); pytest>=8.0, pytest-asyncio>=0.24 (test); tiktoken (benchmark only) (003-discovery-tests)

## Recent Changes
- 001-tool-discovery-index: Added Python 3.11+ + mcp>=1.7, pyyaml>=6.0, pydantic>=2.0, rich>=13.0 (no new deps — FR-015)
