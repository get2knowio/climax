# Quickstart: Tool Discovery Index

## What's Changing

1. **YAML schema extension**: Optional `category` and `tags` fields on configs
2. **ToolIndex class**: In-memory search/browse/lookup for tools across configs

## Step 1: Add Metadata to YAML Configs (Optional)

```yaml
name: git-tools
description: "MCP tools for Git version control"
command: git
category: "vcs"                        # NEW — optional
tags: ["version-control", "commits"]   # NEW — optional
tools:
  - name: git_status
    description: "Show the working tree status"
    command: status
```

Existing configs work without changes — both fields default to `None`/`[]`.

## Step 2: Build a ToolIndex

```python
from climax import load_config, ToolIndex

# Load configs (existing function)
configs = [load_config("git"), load_config("docker"), load_config("obsidian")]

# Build searchable index
index = ToolIndex.from_configs(configs)
```

## Step 3: Search for Tools

```python
# Keyword search — matches name, description, category, tags
results = index.search(query="commit")
for entry in results:
    print(f"{entry.tool_name}: {entry.description}")
    print(f"  Schema: {entry.input_schema}")

# Filter by category
vcs_tools = index.search(category="vcs")

# Combine filters (AND logic)
results = index.search(query="branch", category="vcs", limit=5)
```

## Step 4: Browse Available CLIs

```python
# Get overview of all loaded CLIs
for cli in index.summary():
    print(f"{cli.name}: {cli.tool_count} tools ({cli.category or 'uncategorized'})")
```

## Step 5: Get a Specific Tool

```python
# Exact lookup for execution
resolved = index.get("git_status")
if resolved:
    print(f"Command: {resolved.base_command} {resolved.tool.command}")
    print(f"Args: {[a.name for a in resolved.tool.args]}")
```

## Running Tests

```bash
# All tests (existing + new)
uv run pytest -v

# Just the index tests
uv run pytest tests/test_index.py -v

# Just the config schema tests (category/tags)
uv run pytest tests/test_config.py -v
```
