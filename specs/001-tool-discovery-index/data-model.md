# Data Model: Tool Discovery Index

## Entity Diagram

```text
CLImaxConfig (extended)          ToolIndex
┌──────────────────────┐        ┌──────────────────────────────┐
│ name: str            │        │ _entries: list[ToolIndexEntry]│
│ description: str     │  builds │ _resolved: dict[str, RT]     │
│ command: str         │───────>│ _summaries: list[CLISummary]  │
│ env: dict            │        │                              │
│ working_dir: str?    │        │ + from_configs(cls, configs)  │
│ tools: list[ToolDef] │        │ + search(query, cat, cli, lim)│
│ + category: str?  ←NEW       │ + summary() -> list[CLIS]    │
│ + tags: list[str] ←NEW       │ + get(name) -> RT | None     │
└──────────────────────┘        └──────────────────────────────┘
         │                                    │
         │ has many                           │ contains
         ▼                                    ▼
    ToolDef                          ToolIndexEntry
┌──────────────────┐            ┌──────────────────────────┐
│ name: str        │            │ tool_name: str           │
│ description: str │            │ description: str         │
│ command: str     │            │ cli_name: str            │
│ args: list[Arg]  │            │ category: str | None     │
│ timeout: float?  │            │ tags: list[str]          │
└──────────────────┘            │ input_schema: dict       │
                                │ _search_text: str (priv) │
                                └──────────────────────────┘

    ResolvedTool (existing)          CLISummary
┌──────────────────────┐        ┌──────────────────────┐
│ tool: ToolDef        │        │ name: str             │
│ base_command: str    │        │ description: str      │
│ env: dict            │        │ tool_count: int       │
│ working_dir: str?    │        │ category: str | None  │
│ description_override │        │ tags: list[str]       │
│ arg_constraints: dict│        └───────────────────────┘
└──────────────────────┘
```

## Entity Definitions

### CLImaxConfig (extended)

Existing top-level YAML config model. Two new optional fields added.

| Field | Type | Default | Validation | Notes |
|-------|------|---------|------------|-------|
| name | str | "climax" | — | Existing |
| description | str | "" | — | Existing |
| command | str | *required* | — | Existing |
| env | dict[str, str] | {} | — | Existing |
| working_dir | str \| None | None | — | Existing |
| tools | list[ToolDef] | *required* | — | Existing |
| **category** | **str \| None** | **None** | **— (free text)** | **NEW** |
| **tags** | **list[str]** | **[]** | **— (free text)** | **NEW** |

**Backward compatibility**: Both new fields are optional with sensible defaults. Existing YAML configs load without modification (FR-003, SC-001).

### ToolIndexEntry

Pydantic model representing a single searchable tool in the index.

| Field | Type | Default | Source | Notes |
|-------|------|---------|--------|-------|
| tool_name | str | *required* | `ToolDef.name` | Unique within index |
| description | str | *required* | `ToolDef.description` | Tool description |
| cli_name | str | *required* | `CLImaxConfig.name` | Parent CLI name |
| category | str \| None | None | `CLImaxConfig.category` | Inherited from parent config |
| tags | list[str] | [] | `CLImaxConfig.tags` | Inherited from parent config |
| input_schema | dict[str, Any] | *required* | `build_input_schema(tool.args)` | Full JSON Schema for tool arguments |

**Private field**: `_search_text: str` — Pre-computed lowercased concatenation of all searchable fields (tool_name, description, cli_name, category, tags). Built at construction time. Not exposed in serialization.

### CLISummary

Pydantic model representing a CLI overview in the index.

| Field | Type | Default | Source | Notes |
|-------|------|---------|--------|-------|
| name | str | *required* | `CLImaxConfig.name` | CLI name |
| description | str | *required* | `CLImaxConfig.description` | CLI description |
| tool_count | int | *required* | `len(config.tools)` | Number of tools in this CLI |
| category | str \| None | None | `CLImaxConfig.category` | CLI category |
| tags | list[str] | [] | `CLImaxConfig.tags` | CLI tags |

### ToolIndex (not a Pydantic model — plain class)

In-memory searchable index built from loaded configs. Holds entries, resolved tools, and summaries.

| Internal State | Type | Notes |
|----------------|------|-------|
| `_entries` | list[ToolIndexEntry] | Ordered by insertion (config load order) |
| `_resolved` | dict[str, ResolvedTool] | Keyed by tool name, for `get()` |
| `_summaries` | list[CLISummary] | One per loaded config |

## Relationships

- **CLImaxConfig → ToolIndexEntry**: One config produces N entries (one per tool). Each entry inherits `category` and `tags` from its parent config.
- **CLImaxConfig → CLISummary**: One config produces exactly one summary.
- **ToolIndex → ResolvedTool**: The index stores the same `ResolvedTool` objects that `load_configs()` produces. `get()` returns these directly.
- **ToolIndexEntry ↔ ResolvedTool**: Linked by `tool_name`. An entry is for search/discovery; a resolved tool is for execution. Together they enable the discover-then-execute workflow.

## State Transitions

No state transitions. The ToolIndex is immutable after construction — built once from configs, then only queried. No mutation methods exist.

## Validation Rules

1. `category` and `tags` in `CLImaxConfig`: No validation beyond type checking (Pydantic handles str/list[str]). Free-text values.
2. `ToolIndexEntry.input_schema`: Generated by `build_input_schema()` — always valid JSON Schema by construction.
3. Duplicate tool names: Last config wins. Previous entry is removed from `_entries` list and replaced in `_resolved` dict. Warning logged (same behavior as existing `load_configs()`).
4. `search()` parameters:
   - `query=None` and all filters `None` → returns up to `limit` entries from full index
   - `limit=0` → returns empty list
   - `limit` default: 10
