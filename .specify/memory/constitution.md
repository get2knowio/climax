<\!--
Sync Impact Report
==================
- Version change: (new) → 1.0.0
- Added principles:
  - I. Single-File Core
  - II. YAML-Driven
  - III. Multi-Config
  - IV. Secure by Default
- Added sections:
  - Technology Stack (Non-Negotiable)
  - Code Style & Conventions
  - Governance
- Templates requiring updates:
  - .specify/templates/plan-template.md — ✅ no changes needed
    (Constitution Check section is already generic)
  - .specify/templates/spec-template.md — ✅ no changes needed
  - .specify/templates/tasks-template.md — ✅ no changes needed
  - .specify/templates/commands/*.md — ✅ no command files exist
- Follow-up TODOs: none
-->

# CLImax Constitution

## Core Principles

### I. Single-File Core

CLImax is intentionally a single-file MCP server (`climax.py`).
All core logic — config loading, Pydantic validation, MCP tool
registration, and subprocess execution — MUST remain in this
single file.

- The core MUST NOT be split into multiple modules.
- Supporting utilities (index, search) MAY live in separate files,
  but the runtime server stays monolithic.
- Rationale: one file is easy to vendor, easy to read, and easy
  to reason about. Complexity creep is the primary risk; keeping
  everything in one file makes that creep visible.

### II. YAML-Driven

All tool definitions MUST come from YAML configuration files.
CLImax itself MUST have zero hardcoded knowledge of any CLI.

- The YAML author controls what is exposed — CLImax is the runtime.
- Adding support for a new CLI MUST NOT require changes to
  `climax.py`; it MUST only require a new or updated YAML config.
- Rationale: the value proposition is "YAML configs in, MCP tools
  out." If CLImax itself needs code changes per CLI, the
  abstraction has failed.

### III. Multi-Config

Multiple YAML configs MUST be loadable into a single CLImax
instance, merging all tools into one MCP server.

- Name collisions MUST produce warnings; last-loaded wins.
- Each config is self-contained: its own `command`, `env`,
  `working_dir`, and `timeout` apply only to its tools.
- Rationale: users run `climax jj git docker` to get one server
  covering multiple CLIs. This is a core workflow and MUST NOT
  regress.

### IV. Secure by Default

Commands MUST execute via `asyncio.create_subprocess_exec` — never
through a shell.

- Default timeout per command: 30 seconds. Per-tool overrides are
  allowed via the `timeout` field in config YAML.
- Boolean arguments are flags (present/absent); their values MUST
  NOT be user-controlled strings passed to the subprocess.
- The YAML author controls the attack surface. CLImax MUST NOT
  introduce its own command-injection vectors.
- Policy files provide an additional layer: tool enable/disable,
  argument constraints (`pattern`, `min`, `max`), and Docker
  sandboxing.
- Rationale: MCP servers bridge LLMs to local commands. A shell
  injection in this layer would be catastrophic.

## Technology Stack (Non-Negotiable)

The following stack is fixed. Changes require a MAJOR version bump
to this constitution and explicit justification.

- **Language**: Python 3.11+ with full type hints
- **MCP SDK**: `mcp>=1.7` (Python SDK, stdio transport)
- **Config parsing**: PyYAML (`pyyaml>=6.0`)
- **Validation**: Pydantic (`pydantic>=2.0`) for config models
- **Logging**: Rich (`rich>=13.0`) to stderr — stdout is reserved
  for MCP stdio transport and MUST NOT be written to by logging
- **Async**: `asyncio.create_subprocess_exec` for subprocess
  execution (no shell)
- **Testing**: pytest + pytest-asyncio (`asyncio_mode = "auto"`)
- **CI**: GitHub Actions across Python 3.11, 3.12, 3.13 via `uv`
- **Build**: Hatchling (`hatchling`) as the build backend

## Code Style & Conventions

- Type hints on all public functions.
- Pydantic models for all config parsing and validation.
- Google-style docstrings on public classes and functions.
- `snake_case` for functions and variables; `PascalCase` for
  classes.
- Log to stderr via Rich — stdout is reserved for MCP stdio
  transport.
- Tool names are `snake_case`, prefixed with CLI name
  (e.g., `jj_log`, `git_status`).
- `ResolvedTool` pairs a tool definition with its parent config's
  `command`, `env`, and `working_dir`.
- Args can be: flag-based (`--flag value`), inline flag
  (`key=value`), positional, boolean (flag present/absent), or
  auto-generated from name (`my_arg` → `--my-arg`).
- Config schema supports: `name`, `description`, `command`, `env`,
  `working_dir`, `timeout`, `tools` with nested `args`.

## Governance

This constitution supersedes all other development practices for
CLImax. All changes to the codebase MUST be consistent with these
principles.

- **Amendments**: Any change to this constitution MUST be
  documented with a version bump, rationale, and updated
  `LAST_AMENDED_DATE`.
- **Versioning**: This constitution follows semantic versioning:
  - MAJOR: Backward-incompatible principle removals or
    redefinitions.
  - MINOR: New principle or section added, or materially expanded
    guidance.
  - PATCH: Clarifications, wording, typo fixes.
- **Compliance**: Pull requests SHOULD be checked against these
  principles. Violations MUST be justified in the PR description
  and tracked in the plan's Complexity Tracking table.
- **Runtime guidance**: See `CLAUDE.md` for development commands,
  test patterns, and CI details.

**Version**: 1.0.0 | **Ratified**: 2026-02-21 | **Last Amended**: 2026-02-21
