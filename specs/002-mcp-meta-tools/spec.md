# Feature Specification: MCP Meta-Tools for Progressive Discovery

**Feature Branch**: `002-mcp-meta-tools`
**Created**: 2026-02-21
**Status**: Draft
**Input**: User description: "Create a spec for the two MCP meta-tools that replace direct tool registration as CLImax's default mode."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Agent Searches for Tools via MCP (Priority: P1)

An AI agent connected to a CLImax MCP server wants to discover available tools without having hundreds of tools in its context. The agent calls `climax_search` with a keyword or category filter and receives structured JSON results containing tool names, descriptions, categories, tags, and full argument schemas — everything needed to construct a `climax_call` invocation.

**Why this priority**: This is the primary entry point for progressive discovery. Without a search tool exposed over MCP, agents have no way to discover tools dynamically.

**Independent Test**: Can be fully tested by starting a CLImax server with multiple configs, calling `climax_search` via the MCP `call_tool` handler with various filter combinations, and verifying the JSON response contains matching tools with complete schemas.

**Acceptance Scenarios**:

1. **Given** a server loaded with git and docker configs, **When** `climax_search` is called with `query="commit"`, **Then** JSON results include tools matching "commit" with name, description, CLI name, category, tags, and full arg schema (types, flags, required, defaults, enums)
2. **Given** a server loaded with multiple configs, **When** `climax_search` is called with `category="vcs"`, **Then** only tools from CLIs categorized as "vcs" are returned
3. **Given** a server loaded with multiple configs, **When** `climax_search` is called with `cli="git-tools"`, **Then** only tools from the "git-tools" CLI are returned
4. **Given** a server loaded with multiple configs, **When** `climax_search` is called with `query="branch"` and `category="vcs"`, **Then** results match both filters (AND logic)
5. **Given** a server loaded with configs, **When** `climax_search` is called with `limit=3`, **Then** at most 3 tool results are returned
6. **Given** a server loaded with multiple configs, **When** `climax_search` is called with no arguments, **Then** a summary is returned listing each loaded CLI with its tool count, category, and tags — not individual tools

---

### User Story 2 - Agent Executes a Discovered Tool via MCP (Priority: P1)

An AI agent has discovered a tool via `climax_search` and wants to execute it. The agent calls `climax_call` with the tool name and arguments. The system validates the arguments against the tool's schema, executes the underlying CLI command, and returns stdout, stderr, and exit code.

**Why this priority**: Equally critical as search — without an execution tool, discovery has no value. Together, search and call form the complete progressive discovery workflow.

**Independent Test**: Can be fully tested by calling `climax_call` with a known tool name and valid arguments, verifying the subprocess runs and returns output in the expected format (stdout, stderr, exit code).

**Acceptance Scenarios**:

1. **Given** a server with a tool `echo_hello` that runs `echo hello`, **When** `climax_call` is called with `tool_name="echo_hello"`, **Then** the response contains stdout "hello", empty stderr, and exit code 0
2. **Given** a server with a tool requiring arguments, **When** `climax_call` is called with valid `args`, **Then** the arguments are passed to the subprocess correctly and the response contains the command output
3. **Given** a server with a tool, **When** `climax_call` is called with a missing required argument, **Then** a validation error is returned specifying which argument is required
4. **Given** a server with a tool that has an enum-constrained argument, **When** `climax_call` is called with an invalid enum value, **Then** a validation error is returned listing the valid enum values
5. **Given** a server, **When** `climax_call` is called with `tool_name="nonexistent_tool"`, **Then** an error response indicates the tool was not found
6. **Given** a server with a tool that has a timeout, **When** `climax_call` is called and the command exceeds the timeout, **Then** the response includes the timeout error, matching existing direct-call behavior

---

### User Story 3 - Progressive Discovery Is the Default Mode (Priority: P1)

A user starts CLImax without any special flags. The MCP `tools/list` response contains only `climax_search` and `climax_call` — not the individual CLI tools. The agent uses these two meta-tools to discover and execute any of the underlying CLI tools.

**Why this priority**: Making progressive discovery the default is essential to the value proposition. Without this, agents still see hundreds of tools in their context.

**Independent Test**: Can be fully tested by starting a CLImax server with a config containing multiple tools, calling `list_tools`, and verifying only `climax_search` and `climax_call` appear.

**Acceptance Scenarios**:

1. **Given** a config with 10 tools, **When** CLImax starts in default mode, **Then** `tools/list` returns exactly 2 tools: `climax_search` and `climax_call`
2. **Given** a config with 10 tools, **When** CLImax starts in default mode, **Then** all 10 tools are still accessible via `climax_call`

---

### User Story 4 - Classic Mode Registers All Tools Directly (Priority: P2)

A user wants all CLI tools registered directly in the MCP `tools/list` response for debugging, simple setups, or MCP clients that don't handle multi-step discovery. The user passes `--classic` and all tools appear directly.

**Why this priority**: Important for backward compatibility and debugging but not the primary workflow. Users who need the old behavior should have a clear opt-in path.

**Independent Test**: Can be fully tested by starting CLImax with `--classic` and a config containing multiple tools, calling `list_tools`, and verifying all individual tools appear (no meta-tools).

**Acceptance Scenarios**:

1. **Given** a config with 10 tools, **When** CLImax starts with `--classic`, **Then** `tools/list` returns all 10 individual tools (same as current behavior)
2. **Given** a config with 10 tools, **When** CLImax starts with `--classic`, **Then** `climax_search` and `climax_call` do NOT appear in `tools/list`
3. **Given** a config with 10 tools, **When** CLImax starts with `--classic`, **Then** the ToolIndex is still built internally (it's cheap) but is not exposed via meta-tools

---

### Edge Cases

- What happens when `climax_call` receives an `args` dict with extra keys not in the tool's schema? Extra keys are ignored (matching typical JSON Schema behavior).
- What happens when `climax_call` receives `args` with wrong types (e.g., string where integer expected)? Compatible types are coerced (e.g., string "42" → int 42). Incompatible types (e.g., string "hello" for integer) return a validation error indicating the type mismatch and expected type.
- What happens when `climax_search` returns no matches? An empty results list is returned (not an error).
- What happens when `climax_call` is called with `args=None` and the tool has no required arguments? The tool executes successfully with no arguments.
- What happens when `climax_call` is called for a tool that has policy constraints? The existing policy validation logic (via `validate_arguments`) is applied before execution.
- What happens in default mode when a client tries to call an individual tool name directly (not via `climax_call`)? The call returns "Unknown tool" since individual tools are not registered in the MCP handler.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST register a `climax_search` MCP tool that accepts optional `query` (string), `category` (string), `cli` (string), and `limit` (integer, default 10) parameters
- **FR-002**: When `climax_search` is called with at least one filter parameter, system MUST return matching tools with name, description, CLI name, category, tags, and full argument schema
- **FR-003**: When `climax_search` is called with `query`, `category`, and `cli` all absent (regardless of `limit`), system MUST return a summary listing each loaded CLI with tool count, category, and tags (not individual tools), capped at `limit` entries
- **FR-004**: `climax_search` results MUST be structured JSON: `{"mode": "search", "results": [...]}` (each result is a ToolIndexEntry dict) for search mode, or `{"mode": "summary", "summary": [...]}` (each item is a CLISummary dict) for summary mode
- **FR-005**: System MUST register a `climax_call` MCP tool that accepts `tool_name` (string, required) and `args` (object, optional) parameters
- **FR-006**: `climax_call` MUST look up the tool by name using the ToolIndex `get()` method
- **FR-007**: `climax_call` MUST validate args against the tool's schema before execution: required args present, types coerced where compatible (e.g., string "42" → int 42) or rejected when incompatible (e.g., string "hello" for int), enum values valid
- **FR-008**: `climax_call` MUST return clear validation errors when args are invalid, including what was expected (e.g., "Argument 'format' must be one of: json, text, csv")
- **FR-009**: `climax_call` MUST delegate to existing command execution logic (build_command, run_command with timeout handling)
- **FR-010**: `climax_call` MUST return output in the same format as direct tool calls: stdout, stderr, exit code
- **FR-011**: In default mode, `tools/list` MUST return only `climax_search` and `climax_call`
- **FR-012**: The `--classic` flag MUST cause all individual tools to be registered directly (current behavior), with no meta-tools registered
- **FR-013**: Both modes MUST share the same underlying ToolIndex and command execution logic
- **FR-014**: In classic mode, the ToolIndex MUST still be built (but not exposed via meta-tools)
- **FR-015**: `climax_call` MUST apply existing policy constraints (arg validation via `validate_arguments`) when a policy is loaded
- **FR-016**: `climax_call` MUST support all existing argument features: positional args, flags, boolean flags, stdin piping, cwd override, defaults, and enums
- **FR-017**: The YAML config schema MUST NOT be modified beyond what Spec 1 introduced

### Key Entities

- **`climax_search` (MCP tool)**: Meta-tool for discovering available CLI tools. Wraps the ToolIndex `search()` and `summary()` methods. Returns structured JSON over MCP.
- **`climax_call` (MCP tool)**: Meta-tool for executing a discovered tool by name. Performs schema validation, then delegates to `build_command` + `run_command`. Returns stdout/stderr/exit code over MCP.
- **ToolIndex (from Spec 1)**: In-memory searchable index built from loaded configs. Provides `search()`, `summary()`, and `get()` methods. Used by both meta-tools.
- **ResolvedTool (existing)**: Pairs a ToolDef with its parent config. Retrieved via `ToolIndex.get()` for execution in `climax_call`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An agent can discover a relevant tool and execute it in exactly 2 tool calls (`climax_search` then `climax_call`)
- **SC-002**: In default mode, `tools/list` returns exactly 2 tools regardless of how many CLI tools are configured
- **SC-003**: All existing tests continue to pass without modification (backward compatibility)
- **SC-004**: `climax_call` produces identical output to direct tool calls for the same tool and arguments
- **SC-005**: Validation errors from `climax_call` contain enough information for the caller to correct the invocation without additional lookups
- **SC-006**: `--classic` mode produces the same `tools/list` response as the current (pre-feature) behavior
- **SC-007**: New feature has test coverage for both meta-tools including search with filters, search with no filters (summary), call with valid args, call with invalid args, call with unknown tool, and mode selection

## Clarifications

### Session 2026-02-21

- Q: What triggers summary mode vs search mode in `climax_search`? → A: Summary when `query`, `category`, and `cli` are all absent (regardless of `limit`)
- Q: Should `climax_call` return plain text or structured JSON? → A: Same plain-text format as current direct calls (stdout, `[stderr]`, `[exit code: N]`)
- Q: How should `climax_call` handle type mismatches? → A: Coerce compatible types (e.g., string "42" → int 42), reject incompatible (e.g., string "hello" for int)
- Q: What is the `climax_search` JSON response structure? → A: `{"mode": "search", "results": [...]}` for search; `{"mode": "summary", "summary": [...]}` for summary
- Q: Should `climax_search` summary mode respect the `limit` parameter? → A: Yes, cap summaries at `limit`

## Assumptions

- The `climax_search` response format is a JSON object serialized as an MCP text content response. Search mode returns `{"mode": "search", "results": [...]}` with ToolIndexEntry dicts; summary mode returns `{"mode": "summary", "summary": [...]}` with CLISummary dicts.
- `climax_call` argument validation is done in-process before subprocess execution. It checks required args, type compatibility, and enum constraints using the tool's arg definitions — not the JSON Schema itself.
- The `--classic` flag is added to the `run` subcommand (and backward-compat mode). It is a simple boolean flag with no additional configuration.
- Docker executor support carries through to `climax_call` — if a policy specifies a docker executor, `climax_call` prepends the docker prefix just as direct calls do today.
- The default mode change is not gated by a config file setting — it is the built-in default, overridable only via `--classic`.
