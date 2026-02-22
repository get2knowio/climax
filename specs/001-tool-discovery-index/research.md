# Research: Tool Discovery Index

## R1: Code Placement — climax.py vs Separate File

**Decision**: Keep all new code in `climax.py`

**Rationale**: The feature adds ~120 lines (3 Pydantic models + 1 class with 3 methods). The file grows from ~530 to ~650 lines, well within reasonable single-file size. Constitution Principle I says "Supporting utilities (index, search) MAY live in separate files" but does not require it. Keeping everything in one file avoids import complexity and aligns with the project's single-file philosophy.

**Alternatives considered**:
- Separate `tool_index.py` module — Allowed by constitution but adds file management overhead for a small feature. Would require updating `hatchling` build config and imports.

## R2: ToolIndex Construction — How to Build from Configs

**Decision**: `ToolIndex.from_configs(configs: list[CLImaxConfig])` class method

**Rationale**: The ToolIndex needs `category` and `tags` from the `CLImaxConfig` level, which the current `load_configs()` return type (`tool_map: dict[str, ResolvedTool]`) does not carry. A class method taking config objects gives full access to metadata. Callers use `load_config()` (singular) to get config objects, then pass them to `from_configs()`.

**Alternatives considered**:
- `ToolIndex.from_paths(paths)` — Hides config loading but duplicates load logic. Less composable.
- `ToolIndex.from_tool_map(tool_map)` — Loses category/tags metadata. Would need to be reconstructed from resolved tools.
- Modify `load_configs()` return type — Works but changes existing API surface unnecessarily. FR-014 says existing paths must not be modified.

## R3: Search Implementation — Substring vs Regex vs Fuzzy

**Decision**: Case-insensitive substring matching using Python's `in` operator with `str.lower()`

**Rationale**: The spec explicitly requires "case-insensitive substring matching" for the `query` parameter (FR-007) and "special characters in queries as literal text, not regex patterns" (FR-013). Python's `str.__contains__` with lowercased strings satisfies both requirements with zero overhead and no regex edge cases.

For `category` and `cli` filters: exact match using `str.lower() ==` comparison (per spec clarification).

**Alternatives considered**:
- `re.search()` with `re.escape()` — Unnecessary complexity. `in` operator is simpler and has the same semantics for literal substring matching.
- Fuzzy matching (difflib, rapidfuzz) — Explicitly out of scope per assumptions: "No ranking algorithm or fuzzy matching is needed for the initial implementation."

## R4: Search Target Fields

**Decision**: The `query` parameter matches against 5 fields: tool name, tool description, CLI name, category, and tags

**Rationale**: FR-007 specifies exactly these fields. For tags (a list), the query checks against each tag individually. A tool matches if the query substring appears in any of these fields.

**Implementation detail**: Build a single searchable text blob per entry by joining all fields with spaces, lowercased. This avoids repeated comparisons and keeps the search loop simple.

## R5: Index Entry Schema — What to Store

**Decision**: `ToolIndexEntry` stores the full JSON Schema dict produced by `build_input_schema(tool_def.args)`

**Rationale**: FR-005 and FR-012 require entries to contain "all information needed to construct a valid tool call." SC-005 states "Index entries contain all information needed to construct a valid tool call without additional lookups." Reusing the existing `build_input_schema()` function ensures the schema format is identical to what MCP `tools/list` returns, so agents get consistent data.

**Alternatives considered**:
- Store raw `ToolArg` list — Would require consumers to call `build_input_schema()` themselves. Less convenient and duplicates logic.
- Store a subset of schema — Violates FR-012 completeness requirement.

## R6: Result Ordering

**Decision**: Insertion order (config load order), capped by `limit`

**Rationale**: Spec clarification explicitly states: "When `search()` returns more matches than `limit`, what order should results follow? → Insertion order (config load order)". This is trivially achieved since entries are stored in a list appended in config processing order.

## R7: Duplicate Tool Name Handling in Index

**Decision**: Follow existing behavior — last config wins, previous entry is replaced

**Rationale**: Edge case section of spec states: "The existing duplicate-handling behavior (last config wins with a warning) carries through to the index." The ToolIndex should mirror what `load_configs()` does: overwrite the previous entry and emit a warning.

**Implementation detail**: Use a dict keyed by tool name for resolved tools (same as `tool_map`), and maintain a list for ordered entries. When a duplicate is detected, remove the old entry from the list and append the new one at the end.

## R8: Performance Characteristics

**Decision**: Linear scan is sufficient for the initial implementation

**Rationale**: SC-003 requires search across 50+ tools in <50ms. A linear scan of ~100 entries with string operations takes microseconds in Python. The largest bundled config (obsidian) has 53 tools; the full suite has 76. Even at 500 tools, linear scan would be well under 1ms.

**Alternatives considered**:
- Inverted index — Over-engineered for the current scale. Would add complexity without measurable benefit.
- Pre-computed search text — Yes, this optimization is worthwhile: compute a lowercased concatenation of all searchable fields at index build time, so search only does `query_lower in entry.search_text`. Trivial to implement and avoids repeated string operations.
