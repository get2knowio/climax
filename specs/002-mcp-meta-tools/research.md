# Research: MCP Meta-Tools for Progressive Discovery

**Feature Branch**: `002-mcp-meta-tools`
**Date**: 2026-02-21

## Research Tasks

### R1: MCP SDK tool registration pattern for dual-mode server

**Decision**: Use a single `create_server` function with a `classic` boolean parameter. In default mode, register only `climax_search` and `climax_call` as MCP tools. In classic mode, register all individual tools (current behavior).

**Rationale**: The MCP low-level `Server` class supports registering `@server.list_tools()` and `@server.call_tool()` handlers. These handlers are closures that capture the tool_map and ToolIndex. The mode just changes which tools the `list_tools` handler returns and which names the `call_tool` handler recognizes.

**Alternatives considered**:
- Two separate `create_server` functions: rejected because both modes share 90% of the same logic (ToolIndex construction, command execution, policy validation).
- A wrapper server that delegates: rejected as over-engineering for a single boolean difference.

### R2: Argument validation strategy for `climax_call`

**Decision**: Validate arguments in-process using `ToolArg` definitions before calling `build_command`. Check: (1) required args present, (2) type coercion where compatible (string→int, string→number, string→bool), (3) enum constraints, (4) extra keys silently ignored.

**Rationale**: The spec explicitly states arg validation is done in-process using tool arg definitions, not JSON Schema. Type coercion matches typical MCP client behavior where all values may arrive as strings. The existing `build_command` already handles type conversion for booleans, so validation just needs to happen earlier and more explicitly.

**Alternatives considered**:
- Use jsonschema library for validation: rejected (adds a new dependency, violates FR-015 spirit of no new deps).
- Validate via JSON Schema from `build_input_schema()`: rejected because the spec says to validate against arg definitions directly, and JSON Schema doesn't handle coercion.

### R3: `climax_call` integration with existing execution pipeline

**Decision**: `climax_call` reuses the exact same code path as the current direct `call_tool` handler: policy validation → `build_command` → `run_command` → format response. The only new step is looking up the `ResolvedTool` via `ToolIndex.get()` and performing arg validation.

**Rationale**: SC-004 requires identical output between `climax_call` and direct calls. Sharing the execution code path guarantees this. The existing `call_tool` handler logic (lines 743-831 in climax.py) becomes a shared helper function.

**Alternatives considered**:
- Duplicate the execution logic in `climax_call`: rejected because it would diverge over time and violate SC-004.

### R4: `--classic` flag placement in CLI

**Decision**: Add `--classic` to both the `run` subcommand parser and the backward-compat parser (for `climax config.yaml --classic`). It's a simple `store_true` flag.

**Rationale**: The spec says `--classic` is added to the `run` subcommand. Backward compatibility mode should also support it since users may use either invocation style.

**Alternatives considered**:
- Environment variable `CLIMAX_CLASSIC=1`: rejected as primary mechanism (could be added later as convenience).
- Config file setting: rejected per spec assumption ("not gated by a config file setting").

### R5: `climax_search` response format

**Decision**: Return a JSON string as MCP `TextContent`. Search mode returns `{"mode": "search", "results": [...]}` where each result is a `ToolIndexEntry.model_dump()` dict. Summary mode returns `{"mode": "summary", "summary": [...]}` where each item is a `CLISummary.model_dump()` dict.

**Rationale**: The spec explicitly defines this format. Using `model_dump()` on Pydantic models ensures consistent JSON-serializable output. The `limit` parameter caps both search results and summary entries.

**Alternatives considered**:
- Return structured MCP content (multiple TextContent blocks): rejected because the spec says structured JSON.
- Return tools as MCP Tool objects: rejected because this is a discovery mechanism, not a tool registration.
