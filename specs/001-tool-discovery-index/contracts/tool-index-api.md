# Contract: ToolIndex Python API

## Overview

The ToolIndex class provides an in-memory searchable index of MCP tools loaded from CLImax YAML configs. It is the primary interface for progressive tool discovery — agents search instead of loading all tool definitions.

This contract defines the public API. Future MCP meta-tools will wrap these methods as MCP tool handlers.

## Extended YAML Schema

Two new optional fields at the top level of each YAML config:

```yaml
name: git-tools
description: "MCP tools for Git"
command: git
category: "vcs"              # NEW — optional, free-text string
tags: ["version-control"]    # NEW — optional, list of strings
tools:
  - name: git_status
    # ... (unchanged)
```

**Backward compatibility**: Configs without `category`/`tags` load with `category=None` and `tags=[]`.

## ToolIndex API

### Constructor: `ToolIndex.from_configs(configs: list[CLImaxConfig]) -> ToolIndex`

Build an index from a list of loaded config objects.

```python
configs = [load_config("git"), load_config("docker")]
index = ToolIndex.from_configs(configs)
```

**Behavior**:
- Iterates configs in order, building entries and summaries
- Duplicate tool names: last config wins, previous entry removed, warning logged
- Returns a fully constructed, immutable index

---

### `search(query=None, category=None, cli=None, limit=10) -> list[ToolIndexEntry]`

Search the index with optional filters.

**Parameters**:

| Parameter | Type | Default | Matching |
|-----------|------|---------|----------|
| `query` | str \| None | None | Case-insensitive **substring** against: tool_name, description, cli_name, category, tags |
| `category` | str \| None | None | Case-insensitive **exact** match against config category |
| `cli` | str \| None | None | Case-insensitive **exact** match against config name |
| `limit` | int | 10 | Maximum results returned |

**Filter logic**: AND — results must match ALL provided filters.

**Result ordering**: Insertion order (config load order).

**Return type**: `list[ToolIndexEntry]` — each entry contains:
```python
class ToolIndexEntry(BaseModel):
    tool_name: str          # e.g. "git_status"
    description: str        # e.g. "Show the working tree status"
    cli_name: str           # e.g. "git-tools"
    category: str | None    # e.g. "vcs"
    tags: list[str]         # e.g. ["version-control"]
    input_schema: dict      # Full JSON Schema for tool arguments
```

**Edge cases**:
- All parameters `None` → returns first `limit` entries (browse mode)
- `limit=0` → empty list
- No matches → empty list
- Special characters in `query` → treated as literal text (not regex)

**Examples**:
```python
# Keyword search
results = index.search(query="commit")

# Category filter
results = index.search(category="vcs")

# Combined
results = index.search(query="branch", category="vcs", limit=5)

# Browse
results = index.search(limit=20)
```

---

### `summary() -> list[CLISummary]`

Get a high-level overview of all loaded CLIs.

**Return type**: `list[CLISummary]` — one entry per loaded config:
```python
class CLISummary(BaseModel):
    name: str               # e.g. "git-tools"
    description: str        # e.g. "MCP tools for Git"
    tool_count: int         # e.g. 6
    category: str | None    # e.g. "vcs"
    tags: list[str]         # e.g. ["version-control"]
```

---

### `get(tool_name: str) -> ResolvedTool | None`

Retrieve a tool by exact name for execution.

**Parameters**:
- `tool_name`: Exact tool name (e.g. `"git_status"`)

**Return type**: `ResolvedTool | None` — the existing model containing:
- `tool: ToolDef` — full tool definition with args
- `base_command: str` — e.g. `"git"`
- `env: dict[str, str]` — environment variables
- `working_dir: str | None` — working directory

**Edge cases**:
- Tool not found → `None`
