# MCP Tool Contracts: Meta-Tools for Progressive Discovery

**Feature Branch**: `002-mcp-meta-tools`
**Date**: 2026-02-21

## Tool: `climax_search`

### MCP Registration

```json
{
  "name": "climax_search",
  "description": "Search for available CLI tools by keyword, category, or CLI name. Call with no filters to get a summary of all available CLIs.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Search keyword (matched against tool name, description, CLI name, category, tags)"
      },
      "category": {
        "type": "string",
        "description": "Filter by CLI category (exact match, case-insensitive)"
      },
      "cli": {
        "type": "string",
        "description": "Filter by CLI name (exact match, case-insensitive)"
      },
      "limit": {
        "type": "integer",
        "description": "Maximum number of results to return (default: 10)",
        "default": 10
      }
    }
  }
}
```

### Response Format

**Search mode** (when `query`, `category`, or `cli` is provided):

```json
{
  "mode": "search",
  "results": [
    {
      "tool_name": "git_commit",
      "description": "Record changes to the repository",
      "cli_name": "git-tools",
      "category": "vcs",
      "tags": ["version-control", "commits"],
      "input_schema": {
        "type": "object",
        "properties": {
          "message": {
            "type": "string",
            "description": "Commit message"
          }
        },
        "required": ["message"]
      }
    }
  ]
}
```

**Summary mode** (when `query`, `category`, and `cli` are all absent):

```json
{
  "mode": "summary",
  "summary": [
    {
      "name": "git-tools",
      "description": "MCP tools for Git",
      "tool_count": 15,
      "category": "vcs",
      "tags": ["version-control", "commits"]
    }
  ]
}
```

### Behavior Rules

1. **Mode selection**: Summary when `query`, `category`, and `cli` are all absent; search otherwise.
2. **Filter logic**: All provided filters use AND logic.
3. **`query`**: Case-insensitive substring match against tool name, description, CLI name, category, tags.
4. **`category`** and **`cli`**: Case-insensitive exact match.
5. **`limit`**: Caps results in both search and summary mode. Default 10.
6. **No matches**: Returns `{"mode": "search", "results": []}` (not an error).

---

## Tool: `climax_call`

### MCP Registration

```json
{
  "name": "climax_call",
  "description": "Execute a CLI tool by name. Use climax_search first to discover available tools and their argument schemas.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "tool_name": {
        "type": "string",
        "description": "The exact name of the tool to execute (as returned by climax_search)"
      },
      "args": {
        "type": "object",
        "description": "Arguments to pass to the tool (see tool's input_schema from climax_search)"
      }
    },
    "required": ["tool_name"]
  }
}
```

### Response Format

Same plain-text format as direct tool calls:

**Success (exit 0)**:
```
output from command
```

**Success with stderr**:
```
output from command

[stderr]
warning message
```

**Failure (non-zero exit)**:
```
[stderr]
error message

[exit code: 1]
```

**No output**:
```
(no output)
```

### Error Responses

**Unknown tool**:
```
Unknown tool: nonexistent_tool
```

**Missing required argument**:
```
Argument validation failed:
  - Missing required argument 'message'
```

**Type mismatch**:
```
Argument validation failed:
  - Argument 'count': cannot convert 'hello' to integer
```

**Invalid enum value**:
```
Argument validation failed:
  - Argument 'format' must be one of: json, text, csv
```

**Policy validation** (when policy is loaded):
```
Policy validation failed:
  - Argument 'name': value 'INVALID123' does not match pattern '^[a-z]+$'
```

### Behavior Rules

1. **Tool lookup**: Uses `ToolIndex.get(tool_name)` for exact name match.
2. **Arg validation order**: (a) Required args check, (b) type coercion, (c) enum validation, (d) policy constraints.
3. **Type coercion**: String "42" → int 42, string "3.14" → float 3.14, string "true"/"false" → bool. Incompatible conversions produce validation errors.
4. **Extra keys**: Silently ignored (not an error).
5. **`args=None`**: Treated as empty dict `{}`.
6. **Execution**: Delegates to `build_command()` + `run_command()` with the same timeout, env, working_dir, stdin, cwd, and docker-prefix logic as direct calls.
7. **Policy**: If policy constraints exist on the resolved tool, `validate_arguments()` is applied after `validate_tool_args()`.

---

## Mode Switching

### Default Mode (no flags)

- `tools/list` returns: `[climax_search, climax_call]` (exactly 2 tools)
- Individual tool names are NOT registered in the MCP handler
- Calling an individual tool name directly returns "Unknown tool"

### Classic Mode (`--classic`)

- `tools/list` returns: all individual tools (current behavior)
- `climax_search` and `climax_call` do NOT appear
- ToolIndex is still built internally but not exposed
