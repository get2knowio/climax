# Feature Specification: Tool Discovery Index

**Feature Branch**: `001-tool-discovery-index`
**Created**: 2026-02-21
**Status**: Draft
**Input**: User description: "Extend CLImax YAML config schema and add a ToolIndex for progressive tool discovery"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Config Author Adds Metadata to YAML Config (Priority: P1)

A config author adding a new CLI to CLImax wants to annotate their YAML config with a category and tags so that downstream discovery tools can classify and filter tools without reading every tool definition.

**Why this priority**: Without category and tags in the config schema, no discovery metadata exists. This is the foundational data that all other stories depend on.

**Independent Test**: Can be fully tested by writing a YAML config with `category` and `tags` fields, loading it, and verifying the parsed Pydantic model contains those values. Delivers value by enabling categorized tool registries.

**Acceptance Scenarios**:

1. **Given** a YAML config with `category: "vcs"` and `tags: ["version-control", "commits"]`, **When** the config is loaded, **Then** the resulting config model contains `category="vcs"` and `tags=["version-control", "commits"]`
2. **Given** a YAML config with no `category` or `tags` fields, **When** the config is loaded, **Then** it loads successfully with `category=None` and `tags=[]` (backward compatible)
3. **Given** a YAML config with only `category` set (no `tags`), **When** the config is loaded, **Then** it loads successfully with the category populated and tags defaulting to empty list

---

### User Story 2 - Agent Searches for Relevant Tools by Keyword (Priority: P1)

An AI agent connected to a CLImax MCP server needs to find relevant tools across dozens of configured CLIs without loading every tool definition into context. The agent searches the tool index by keyword and receives a ranked subset of matching tools with full schemas.

**Why this priority**: This is the core value proposition — enabling progressive disclosure by letting agents search instead of loading all tools. Equally critical as Story 1 since it delivers the searchable index.

**Independent Test**: Can be fully tested by building a ToolIndex from multiple configs, calling `search(query="commit")`, and verifying results contain commit-related tools with complete arg schemas. Delivers value by reducing context token usage for agents.

**Acceptance Scenarios**:

1. **Given** an index built from git and docker configs, **When** searching with `query="commit"`, **Then** results include tools with "commit" in their name, description, or tags, and each result contains the full arg schema
2. **Given** an index with 50+ tools, **When** searching with `query="status"` and `limit=5`, **Then** at most 5 results are returned
3. **Given** an index, **When** searching with `query="COMMIT"` (uppercase), **Then** results match case-insensitively and return the same results as lowercase
4. **Given** an index, **When** searching with `category="vcs"`, **Then** only tools from configs with `category="vcs"` are returned
5. **Given** an index, **When** searching with `cli="git-tools"`, **Then** only tools from the config named "git-tools" are returned
6. **Given** an index, **When** searching with `query="branch"` and `category="vcs"`, **Then** results match both filters (AND logic)

---

### User Story 3 - Agent Gets Index Overview Without Searching (Priority: P2)

An AI agent wants to understand what CLIs and capabilities are available before performing a targeted search. The agent calls the summary method to get a high-level inventory of loaded CLIs with tool counts, categories, and tags.

**Why this priority**: Provides orientation before search. Less critical than search itself but important for agent usability — an agent that doesn't know what categories exist can't filter effectively.

**Independent Test**: Can be fully tested by building a ToolIndex from multiple configs and calling `summary()`, verifying each CLI name, tool count, category, and tags are returned. Delivers value by enabling agents to ask "what's available?" before searching.

**Acceptance Scenarios**:

1. **Given** an index built from 3 configs (git with 5 tools, docker with 8 tools, obsidian with 3 tools), **When** calling `summary()`, **Then** a list of 3 entries is returned, each containing the CLI name, tool count, category (if set), and tags (if set)
2. **Given** an index built from configs where some have categories and some don't, **When** calling `summary()`, **Then** entries without categories show `None` for category and `[]` for tags

---

### User Story 4 - Agent Retrieves Exact Tool by Name (Priority: P2)

An AI agent has identified a tool from search results and needs to retrieve its full definition (including parent config details) to execute it. The agent calls `get()` with the exact tool name.

**Why this priority**: Complements search by providing exact lookup. Essential for the full discovery-to-execution workflow but secondary to search itself.

**Independent Test**: Can be fully tested by building a ToolIndex and calling `get("git_status")`, verifying the returned object contains the complete tool definition including base command, args, env, and working directory. Delivers value by enabling tool resolution after discovery.

**Acceptance Scenarios**:

1. **Given** an index containing `git_status`, **When** calling `get("git_status")`, **Then** the existing `ResolvedTool` is returned with the tool's full definition, base command, env, and working directory
2. **Given** an index, **When** calling `get("nonexistent_tool")`, **Then** `None` is returned

---

### Edge Cases

- What happens when two configs define tools with the same name? The existing duplicate-handling behavior (last config wins with a warning) carries through to the index.
- What happens when `search()` is called with all parameters as `None`? It returns up to `limit` tools from the full index (effectively a browse).
- What happens when no tools match a search? An empty list is returned.
- What happens when `limit=0`? An empty list is returned.
- What happens with very long query strings? Substring matching still works correctly.
- What happens with special regex characters in queries? They are treated as literal strings, not regex patterns.

## Clarifications

### Session 2026-02-21

- Q: When `search()` returns more matches than `limit`, what order should results follow? → A: Insertion order (config load order)
- Q: Should `category` and `cli` filter parameters in `search()` use exact match or substring match? → A: Exact match, case-insensitive

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST accept an optional `category` field (string) at the top level of each YAML config
- **FR-002**: System MUST accept an optional `tags` field (list of strings) at the top level of each YAML config
- **FR-003**: System MUST load configs with or without `category` and `tags` fields without error (backward compatible)
- **FR-004**: System MUST build an in-memory searchable index from all loaded configs via a `ToolIndex` class
- **FR-005**: Each index entry MUST contain: tool name, description, parent CLI name, category, tags, and full tool schema (args with types, flags, required status, defaults, enums)
- **FR-006**: `ToolIndex` MUST provide a `search()` method accepting optional `query`, `category`, `cli`, and `limit` parameters
- **FR-007**: The `query` parameter MUST match against tool name, tool description, CLI name, category, and tags using case-insensitive substring matching. The `category` and `cli` filter parameters MUST use exact match (case-insensitive).
- **FR-008**: Search MUST apply all provided filters with AND logic (results must match all specified criteria)
- **FR-009**: Search MUST return at most `limit` results (default 10), ordered by insertion order (config load order)
- **FR-010**: `ToolIndex` MUST provide a `summary()` method that returns loaded CLIs with their tool counts, categories, and tags
- **FR-011**: `ToolIndex` MUST provide a `get()` method that returns the existing `ResolvedTool` for an exact tool name match, or `None` if not found
- **FR-012**: `ToolIndexEntry` MUST be a Pydantic model containing all fields needed for an agent to construct a tool call after discovery
- **FR-013**: Search MUST treat special characters in queries as literal text, not regex patterns
- **FR-014**: The existing tool registration path (direct MCP `tools/list`) MUST NOT be modified
- **FR-015**: The feature MUST NOT introduce any new external dependencies

### Key Entities

- **CLImaxConfig (extended)**: Top-level config model, now with optional `category` (string, default None) and `tags` (list of strings, default empty list)
- **ToolIndex**: In-memory index built from all loaded configs. Provides `search()`, `summary()`, and `get()` methods. Contains a flat list of `ToolIndexEntry` objects and a mapping of CLI names to `CLISummary` objects.
- **ToolIndexEntry**: Pydantic model representing a single searchable tool. Contains: tool name, description, CLI name, category, tags, and full arg schema (matching the JSON Schema structure produced by the existing `build_input_schema` function)
- **CLISummary**: Pydantic model representing a CLI overview. Contains: CLI name, description, tool count, category, and tags.
- **ResolvedTool (existing)**: Already pairs a ToolDef with its parent config. Used by `get()` to return the full execution-ready tool definition.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All existing YAML configs load without modification after the schema extension (100% backward compatibility)
- **SC-002**: All existing tests continue to pass without changes
- **SC-003**: A search across an index of 50+ tools returns matching results in under 50ms on standard hardware
- **SC-004**: An agent can discover a relevant tool and retrieve its full schema in at most 2 interactions (one search + one get, or a single search with full schema in results)
- **SC-005**: Index entries contain all information needed to construct a valid tool call (tool name, all args with types, required flags, defaults, and enums) without additional lookups
- **SC-006**: New feature has test coverage for all public methods (`search`, `summary`, `get`) including edge cases

## Assumptions

- The `ToolIndex` is built once at startup from the same configs passed to `load_configs()`. It does not support dynamic reloading.
- Search relevance is best-effort with simple substring matching. No ranking algorithm or fuzzy matching is needed for the initial implementation.
- The `ToolIndexEntry` includes the full arg schema as a structured representation (matching the JSON Schema that `build_input_schema()` produces) so agents have everything needed for tool invocation.
- Category and tags are purely metadata for discovery — they do not affect tool execution behavior.
- The `ToolIndex` is designed to be used by future MCP meta-tools but this spec does not cover meta-tool registration.
