# Data Model: MCP Meta-Tools for Progressive Discovery

**Feature Branch**: `002-mcp-meta-tools`
**Date**: 2026-02-21

## Entities

### Existing (no changes)

| Entity | Location | Role |
|--------|----------|------|
| `ToolIndexEntry` | `climax.py:174` | Searchable tool entry with metadata and input_schema. Frozen Pydantic model. |
| `CLISummary` | `climax.py:201` | High-level CLI overview (name, description, tool_count, category, tags). |
| `ToolIndex` | `climax.py:226` | In-memory index with `search()`, `summary()`, `get()` methods. |
| `ResolvedTool` | `climax.py:112` | Tool definition + parent config (base_command, env, working_dir, constraints). |
| `ToolDef` | `climax.py:87` | Tool definition from YAML (name, description, command, args, timeout). |
| `ToolArg` | `climax.py:73` | Argument definition (name, type, required, default, flag, positional, etc.). |

### New

No new Pydantic models are introduced. The meta-tools use existing models exclusively:

- `climax_search` queries `ToolIndex.search()` → returns `list[ToolIndexEntry]` serialized via `model_dump()`
- `climax_search` (summary mode) queries `ToolIndex.summary()` → returns `list[CLISummary]` serialized via `model_dump()`
- `climax_call` uses `ToolIndex.get()` → returns `ResolvedTool` → delegates to `build_command` + `run_command`

### New Function: `validate_tool_args`

A new validation function that checks `climax_call` arguments against `ToolArg` definitions:

```
validate_tool_args(args: dict[str, Any], tool_def: ToolDef) -> tuple[dict[str, Any], list[str]]
```

**Input**: Raw arguments dict from MCP call, ToolDef with arg definitions.
**Output**: Tuple of (coerced arguments dict, list of error messages). Empty error list = valid.

**Validation rules**:
1. Required args: error if missing from args dict
2. Type coercion:
   - string → integer: `int(value)`, error if not numeric
   - string → number: `float(value)`, error if not numeric
   - string → boolean: `"true"` → `True`, `"false"` → `False`, error otherwise
   - int/float → string: `str(value)` (always succeeds)
3. Enum constraints: error if value not in `arg.enum` list
4. Extra keys: silently ignored (not an error)

### Server Mode

The `create_server` function gains a new parameter:

```
create_server(
    server_name: str,
    tool_map: dict[str, ResolvedTool],
    executor: ExecutorConfig | None = None,
    index: ToolIndex | None = None,    # NEW — required for default mode
    classic: bool = False,              # NEW — False = meta-tools, True = direct
) -> Server
```

**Mode behavior**:
- `classic=True`: Current behavior. `list_tools` returns all individual tools. `call_tool` dispatches to individual tools.
- `classic=False` (default): `list_tools` returns only `climax_search` and `climax_call`. `call_tool` dispatches to these two meta-tools. Individual tool execution happens inside `climax_call`.

## State Transitions

No state transitions — all operations are stateless request/response:

```
Agent → climax_search (query) → JSON results
Agent → climax_call (tool_name, args) → validate → build_command → run_command → text response
```

## Relationships

```
ToolIndex ──owns──→ list[ToolIndexEntry]
         ──owns──→ dict[str, ResolvedTool]
         ──owns──→ list[CLISummary]

climax_search ──queries──→ ToolIndex.search() / ToolIndex.summary()
climax_call   ──queries──→ ToolIndex.get()
              ──delegates──→ validate_tool_args() → build_command() → run_command()
```
