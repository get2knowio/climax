# Data Model: Progressive Discovery Tests & Token Benchmark

## Overview

This feature is primarily a test and benchmark effort. No new persistent data models are introduced. This document describes the existing models under test and the transient benchmark data structures.

## Existing Models Under Test

### ToolIndexEntry (frozen Pydantic model)

The primary unit of search results. Already implemented in `climax.py`.

| Field | Type | Description |
|-------|------|-------------|
| `tool_name` | `str` | Unique tool identifier (e.g., `git_status`) |
| `description` | `str` | Human-readable tool description |
| `cli_name` | `str` | Parent config name (e.g., `git-tools`) |
| `category` | `str \| None` | Optional category from config (e.g., `vcs`) |
| `tags` | `list[str]` | Tags inherited from config (default: `[]`) |
| `input_schema` | `dict[str, Any]` | JSON Schema for tool arguments |
| `_search_text` | `str` (private) | Pre-computed lowercase text for substring matching |

**Validation**: Immutable (`frozen=True`). `_search_text` is computed in `model_post_init`.

### CLISummary (Pydantic model)

Summary-level view of a loaded CLI configuration.

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Config name (e.g., `git-tools`) |
| `description` | `str` | Config description |
| `tool_count` | `int` | Number of tools in this config |
| `category` | `str \| None` | Optional category |
| `tags` | `list[str]` | Tags from config |

### ResolvedTool (Pydantic model)

A tool definition paired with its parent config's execution context.

| Field | Type | Description |
|-------|------|-------------|
| `tool` | `ToolDef` | The tool definition with args |
| `base_command` | `str` | Parent config's `command` field |
| `env` | `dict[str, str]` | Environment variables |
| `working_dir` | `str \| None` | Working directory override |

### ToolIndex (class)

The in-memory index built from loaded configs.

| Method | Signature | Returns |
|--------|-----------|---------|
| `from_configs` | `(configs: list[CLImaxConfig]) -> ToolIndex` | Class method constructor |
| `search` | `(query?, category?, cli?, limit=10) -> list[ToolIndexEntry]` | Filtered results |
| `summary` | `() -> list[CLISummary]` | CLI-level overviews |
| `get` | `(tool_name: str) -> ResolvedTool \| None` | Exact match lookup |

## Benchmark Data Structures (transient, script-only)

### BenchmarkResult (not a Pydantic model — plain dict or namedtuple in script)

| Field | Type | Description |
|-------|------|-------------|
| `mode` | `str` | `"classic"` or `"discovery"` |
| `tool_count` | `int` | Number of tools in tools/list response |
| `token_count` | `int` | Token count of serialized tools/list JSON |
| `json_chars` | `int` | Character count (secondary metric) |

### Comparison Table (printed output)

| Column | Description |
|--------|-------------|
| Mode | "Classic" or "Discovery" |
| Tools | Number of tools exposed |
| Tokens | tiktoken cl100k_base token count |
| Savings | Percentage reduction (discovery vs classic) |

## State Transitions

N/A — This feature introduces no stateful entities. The ToolIndex is built once at startup and is read-only thereafter. The benchmark script runs to completion and exits.

## Relationships

```text
CLImaxConfig (1) ──builds──▸ CLISummary (1)
CLImaxConfig (1) ──builds──▸ ToolIndexEntry (many)
CLImaxConfig (1) ──builds──▸ ResolvedTool (many)
ToolIndex    (1) ──contains──▸ ToolIndexEntry (many)
ToolIndex    (1) ──contains──▸ CLISummary (many)
ToolIndex    (1) ──contains──▸ ResolvedTool (many, via _resolved dict)
```
