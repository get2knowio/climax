# Quickstart: MCP Meta-Tools for Progressive Discovery

**Feature Branch**: `002-mcp-meta-tools`
**Date**: 2026-02-21

## What Changed

CLImax now exposes **two meta-tools** (`climax_search` and `climax_call`) by default instead of registering every individual CLI tool directly. This means an MCP client sees only 2 tools regardless of how many CLI tools are configured, dramatically reducing context pollution for AI agents.

## Usage

### Default Mode (progressive discovery)

Start CLImax as usual — progressive discovery is now the default:

```bash
climax run git docker               # 2 meta-tools exposed
climax git docker                   # backward compat — also 2 meta-tools
```

An agent's workflow:

1. **Discover**: Call `climax_search` with a keyword → get matching tools with full schemas
2. **Execute**: Call `climax_call` with the tool name and args → get command output

### Classic Mode (direct registration)

For debugging or clients that don't support multi-step discovery:

```bash
climax run git docker --classic     # all individual tools exposed
climax git docker --classic         # backward compat — also all tools
```

## Agent Interaction Examples

### Example 1: Search then call

```
Agent → climax_search(query="commit")
Server → {"mode": "search", "results": [{"tool_name": "git_commit", "description": "Record changes...", "input_schema": {"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]}}]}

Agent → climax_call(tool_name="git_commit", args={"message": "fix: resolve timeout bug"})
Server → "fix: resolve timeout bug"  (stdout from git commit)
```

### Example 2: Summary overview

```
Agent → climax_search()
Server → {"mode": "summary", "summary": [{"name": "git-tools", "tool_count": 15, "category": "vcs", ...}, {"name": "docker-tools", "tool_count": 8, "category": "containers", ...}]}
```

### Example 3: Filtered search

```
Agent → climax_search(category="vcs", query="branch")
Server → {"mode": "search", "results": [{"tool_name": "git_branch", ...}]}
```

## Testing

```bash
# Run all tests
uv run pytest -v

# Run only meta-tool tests
uv run pytest tests/test_meta_tools.py -v

# Run existing tests to verify backward compatibility
uv run pytest tests/test_server.py -v
```
