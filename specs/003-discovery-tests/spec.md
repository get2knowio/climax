# Feature Specification: Progressive Discovery Tests & Token Benchmark

**Feature Branch**: `003-discovery-tests`
**Created**: 2026-02-21
**Status**: Draft
**Input**: User description: "Create a spec for testing CLImax's progressive discovery feature and benchmarking token savings."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - ToolIndex Unit Test Suite (Priority: P1)

A developer modifying the ToolIndex (search, summary, get) needs confidence that index construction, querying, and filtering all behave correctly. Unit tests for ToolIndex verify that multiple YAML configs are indexed, category and tags are parsed (including when absent), keyword search matches across tool name/description/CLI name/tags, filters combine with AND logic, and edge cases like case-insensitivity and result capping work as expected.

**Why this priority**: ToolIndex is the foundation of progressive discovery. If search or get is broken, both meta-tools fail. Testing this first provides the base layer of confidence everything else depends on.

**Independent Test**: Can be fully tested with in-memory Pydantic fixtures (no YAML files, no subprocess, no MCP server) and delivers verified correctness of all ToolIndex query paths.

**Acceptance Scenarios**:

1. **Given** multiple tool configs with varying category and tags values (including absent ones), **When** the ToolIndex is built, **Then** all tools are indexed and retrievable
2. **Given** a populated ToolIndex, **When** search() is called with a keyword, **Then** results include tools whose name, description, CLI name, or tags contain that keyword (case-insensitive)
3. **Given** a populated ToolIndex, **When** search() is called with a category filter, **Then** only tools in that category are returned
4. **Given** a populated ToolIndex, **When** search() is called with a CLI name filter, **Then** only that CLI's tools are returned
5. **Given** a populated ToolIndex, **When** search() is called with both a keyword and a category filter, **Then** results satisfy both conditions (AND logic)
6. **Given** a populated ToolIndex, **When** search() is called with no filters, **Then** the summary path is invoked (returning CLI-level overviews, not individual tools)
7. **Given** a populated ToolIndex, **When** summary() is called, **Then** it returns CLI names with tool counts, categories, and tags
8. **Given** a populated ToolIndex, **When** get() is called with a valid tool name, **Then** the exact tool is returned; when called with an unknown name, **Then** None is returned
9. **Given** a populated ToolIndex with more results than the limit, **When** search() is called with a limit, **Then** results are capped at that limit
10. **Given** tool names and descriptions in mixed case, **When** search() is called with a differently-cased keyword, **Then** matching results are still returned

---

### User Story 2 - Meta-Tool Unit Test Suite (Priority: P1)

A developer modifying the climax_search or climax_call meta-tools needs confidence that the MCP-facing wrappers correctly delegate to ToolIndex and command execution, validate inputs, and produce well-structured responses. Unit tests for these two tools verify JSON response structure, argument validation, error messages, and subprocess delegation.

**Why this priority**: The meta-tools are the user-facing interface of progressive discovery. They must validate inputs, route calls correctly, and return clear errors. This is co-priority with ToolIndex because both are required for a working system.

**Independent Test**: Can be fully tested with mocked ToolIndex and mocked subprocess calls, verifying input validation and response formatting without real CLIs or YAML files.

**Acceptance Scenarios**:

1. **Given** a climax_search call with filters, **When** results exist, **Then** the response is well-structured JSON containing tool names, descriptions, and full argument schemas
2. **Given** a climax_search call with no filters, **When** invoked, **Then** the response is a CLI summary (not individual tools)
3. **Given** a climax_search call with filters matching nothing, **When** invoked, **Then** the response is an empty list (not an error)
4. **Given** a climax_search call with a limit parameter, **When** invoked, **Then** results respect that limit
5. **Given** a climax_call with a valid tool name and valid args, **When** invoked, **Then** the call is routed to the correct tool and subprocess execution proceeds
6. **Given** a climax_call with a valid tool name but a missing required arg, **When** invoked, **Then** a clear error message identifies the missing argument
7. **Given** a climax_call with a valid tool name but an invalid enum value, **When** invoked, **Then** a clear error message lists the allowed values
8. **Given** a climax_call with an unknown tool name, **When** invoked, **Then** a helpful error message indicates the tool was not found and lists available tools
9. **Given** a climax_call, **When** the underlying subprocess times out or errors, **Then** the behavior matches what the same tool would produce in classic mode

---

### User Story 3 - Integration Tests with Real Configs (Priority: P2)

A developer making changes to the overall system (config loading, mode switching, tool registration) needs end-to-end confidence that progressive discovery works with real YAML configurations. Integration tests load actual example configs and verify mode switching (default vs --classic), cross-CLI search relevance, and output equivalence between discovery mode and classic mode.

**Why this priority**: Integration tests catch issues that unit tests miss — schema mismatches, config loading bugs, and mode-switching regressions. They are second priority because they depend on the features being individually correct first.

**Independent Test**: Can be tested by loading real example YAML configs (jj.yaml, git.yaml, docker.yaml) and exercising the MCP tools/list handler and meta-tool handlers directly, delivering verified end-to-end correctness.

**Acceptance Scenarios**:

1. **Given** multiple example configs loaded in default (discovery) mode, **When** tools/list is called, **Then** exactly 2 tools appear: climax_search and climax_call
2. **Given** multiple example configs loaded with --classic flag, **When** tools/list is called, **Then** all individual tools from all configs appear (not the meta-tools)
3. **Given** configs loaded in discovery mode, **When** climax_search is called with a query like "version control" or "vcs", **Then** jj and git tools surface in results
4. **Given** configs loaded in discovery mode, **When** climax_search is called with a specific CLI name filter, **Then** only that CLI's tools are returned
5. **Given** a specific tool, **When** called via climax_call in discovery mode and directly in classic mode, **Then** the output is equivalent

---

### User Story 4 - Token Savings Benchmark (Priority: P2)

A project maintainer preparing documentation or evaluating the value of progressive discovery needs a reproducible measurement of token savings. A benchmark script loads all example configs, serializes the tools/list response for both classic mode (all tool definitions) and discovery mode (just 2 meta-tools), counts tokens, and prints a comparison table showing absolute and percentage savings.

**Why this priority**: Quantifying the token savings is essential for communicating the value proposition of progressive discovery to users and in project documentation. It is second priority because it is a measurement tool, not a correctness gate.

**Independent Test**: Can be tested by running the benchmark script against example configs and verifying it produces a readable comparison table with plausible numbers (discovery tokens < classic tokens).

**Acceptance Scenarios**:

1. **Given** all example configs are available, **When** the benchmark script runs, **Then** it loads all configs and serializes both classic and discovery mode tool lists
2. **Given** serialized tool lists, **When** token counting is performed, **Then** a comparison table is printed showing: classic token count, discovery token count, absolute savings, and percentage reduction
3. **Given** the benchmark script, **When** run multiple times, **Then** results are deterministic and reproducible
4. **Given** the benchmark output, **When** reviewed, **Then** it is formatted clearly enough to include directly in the README

---

### Edge Cases

- What happens when a ToolIndex is built from configs where no tools have category or tags set?
- What happens when climax_search is called with a query that matches zero tools?
- What happens when climax_call receives an empty args dict for a tool that has required arguments?
- What happens when climax_call receives extra/unknown argument names not defined in the tool schema? → Extra args are silently ignored; test verifies no error is raised and execution proceeds normally
- What happens when --classic flag is combined with configs that have category and tags fields?
- What happens when a tool name passed to climax_call contains special characters or casing differences?
- What happens when the benchmark script encounters configs with no tools defined?
- How does search behave when the query is an empty string vs. not provided at all?

## Requirements *(mandatory)*

### Approach

Tests are **test-driven**: they verify the expected behavior described in this spec. Where current implementation diverges from spec expectations (e.g., FR-019 unknown-tool error message), the implementation MUST be updated to match before or alongside the test. Tests do not enshrine known gaps.

### Functional Requirements

**ToolIndex Unit Tests**

- **FR-001**: Test suite MUST verify that ToolIndex builds correctly from multiple config sources, indexing all tools from all configs
- **FR-002**: Test suite MUST verify that category and tags fields are parsed and included in the index, including when these fields are absent (defaults to no category, empty tags)
- **FR-003**: Test suite MUST verify that search() matches against tool name, description, CLI name, and tags using keyword substring matching
- **FR-004**: Test suite MUST verify that search() filters by category, returning only tools in the specified category
- **FR-005**: Test suite MUST verify that search() filters by CLI name, returning only tools from the specified CLI
- **FR-006**: Test suite MUST verify that combined filters (query + category + cli) intersect correctly using AND logic
- **FR-007**: Test suite MUST verify that search() with no filters delegates to the summary path, returning CLI-level overviews rather than individual tools
- **FR-008**: Test suite MUST verify that summary() returns a list of CLI names with their tool counts, categories, and tags
- **FR-009**: Test suite MUST verify that get() returns the exact tool for a known name and None for an unknown name
- **FR-010**: Test suite MUST verify that the limit parameter caps the number of search results
- **FR-011**: Test suite MUST verify that search is case-insensitive across all searchable fields

**climax_search Unit Tests**

- **FR-012**: Test suite MUST verify that climax_search returns well-structured results including tool names, descriptions, and full argument schemas
- **FR-013**: Test suite MUST verify that climax_search with no filters returns a CLI summary, not individual tools
- **FR-014**: Test suite MUST verify that climax_search returns an empty list (not an error) when no tools match
- **FR-015**: Test suite MUST verify that the limit parameter is respected in climax_search results

**climax_call Unit Tests**

- **FR-016**: Test suite MUST verify that climax_call routes to the correct tool by name
- **FR-017**: Test suite MUST verify that climax_call returns a clear error when required arguments are missing, identifying which arguments are needed
- **FR-018**: Test suite MUST verify that climax_call returns a clear error when enum arguments have invalid values, listing the allowed values
- **FR-019**: Test suite MUST verify that climax_call returns a helpful error when an unknown tool name is provided, including a list of available tools
- **FR-020**: Test suite MUST verify that climax_call passes through to subprocess execution correctly for valid calls
- **FR-021**: Test suite MUST verify that climax_call timeout and error handling matches classic mode behavior

**Integration Tests**

- **FR-022**: Test suite MUST load real example configs (jj.yaml, git.yaml, docker.yaml) and verify default mode exposes exactly 2 tools (climax_search, climax_call)
- **FR-023**: Test suite MUST verify that --classic flag causes all individual tools to appear in tools/list instead of the meta-tools
- **FR-024**: Test suite MUST verify that searching for domain terms (e.g., "version control", "vcs") surfaces relevant tools from the correct CLIs
- **FR-025**: Test suite MUST verify that filtering by CLI name returns only that CLI's tools
- **FR-026**: Test suite MUST verify that calling a tool via climax_call produces output equivalent to calling the same tool in classic mode

**Token Benchmark**

- **FR-027**: Benchmark script MUST load all available example configs and serialize the tools/list response for both classic and discovery modes
- **FR-028**: Benchmark script MUST count tokens for both serialized responses and print a comparison table with classic tokens, discovery tokens, absolute savings, and percentage reduction
- **FR-029**: Benchmark results MUST be deterministic and reproducible across runs
- **FR-030**: Benchmark output MUST be formatted clearly for inclusion in project documentation

### Key Entities

- **ToolIndex**: The in-memory index of all loaded tools, supporting search by keyword, category, and CLI name, plus summary and exact-match retrieval
- **ToolIndexEntry**: A single search result containing tool name, description, CLI name, category, tags, and full argument schema
- **CLISummary**: A CLI-level overview containing CLI name, description, tool count, categories, and tags
- **Meta-Tool (climax_search)**: The MCP tool that queries the ToolIndex and returns structured results
- **Meta-Tool (climax_call)**: The MCP tool that validates arguments and dispatches to the appropriate CLI tool for execution
- **Benchmark Report**: A comparison table showing token counts for classic vs discovery modes with savings metrics

## Clarifications

### Session 2026-02-21

- Q: How should the benchmark count tokens — tiktoken as runtime dep, test/optional extra, word-count only, or character-count proxy? → A: Add tiktoken as a test/optional extra only (`uv sync --extra benchmark`), keeping the runtime dependency-free
- Q: Should tests verify current behavior only, or also drive implementation changes where spec expectations differ from current code? → A: Tests verify expected behavior per spec (test-driven); implementation updated where needed (e.g., enriching climax_call unknown-tool error to list available tools)
- Q: Where should the benchmark script live and how should it be invoked? → A: `scripts/benchmark_tokens.py`, invoked via `uv run python scripts/benchmark_tokens.py`
- Q: Which external CLIs should integration tests assume are available in CI? → A: Only `git`; mock subprocess for docker, jj, and other CLIs
- Q: How should climax_call handle extra/unknown arguments not defined in the tool schema? → A: Silently ignore (current behavior); tests verify no error is raised

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All ToolIndex unit tests pass, covering 100% of the search, summary, and get code paths (build, keyword search, category filter, CLI filter, combined filters, no-filter summary, limit, case-insensitivity, missing fields)
- **SC-002**: All climax_search unit tests pass, verifying response structure, summary mode, empty results, and limit enforcement
- **SC-003**: All climax_call unit tests pass, verifying routing, required arg validation, enum validation, unknown tool handling, subprocess delegation, and timeout/error parity with classic mode
- **SC-004**: All integration tests pass using real example YAML configs, verifying mode switching (default 2 tools vs --classic all tools), cross-CLI search relevance, and output equivalence between modes
- **SC-005**: The benchmark script runs successfully and reports discovery mode token count at least 70% lower than classic mode token count across all example configs
- **SC-006**: The complete test suite runs in under 30 seconds (unit tests under 5 seconds, integration tests under 25 seconds)
- **SC-007**: Zero test flakiness — all tests produce identical pass/fail results across 10 consecutive runs

### Assumptions

- Specs 001 (ToolIndex) and 002 (MCP Meta-Tools) are implemented before this test suite is written
- Example YAML configs (jj.yaml, git.yaml, docker.yaml) exist in the configs directory and include representative category and tags fields
- The existing test infrastructure (pytest, pytest-asyncio, conftest.py fixtures) is reused and extended
- Token counting uses tiktoken (cl100k_base encoding) added as a test/optional extra (`uv sync --extra benchmark`), not a runtime dependency
- Unit tests use inline Pydantic fixtures and mocked subprocess calls, consistent with existing test patterns
- Integration tests use real YAML configs; only `git` is assumed available in CI — subprocess calls for docker, jj, and other CLIs are mocked
- The benchmark script lives at `scripts/benchmark_tokens.py` and is invoked via `uv run python scripts/benchmark_tokens.py` (standalone, not part of the pytest suite)
