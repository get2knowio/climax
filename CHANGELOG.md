# Changelog

## 0.5.0 — 2026-08-07

### Highlights

- **Tool-call approval dialogs** — Tools can declare a `risk` level (`read`, `write`, `destructive`), and CLImax shows a native confirmation dialog before running the risky ones. Uses `osascript` on macOS, `zenity`/`kdialog` on Linux, and a PowerShell `MessageBox` on Windows, falling back to a `/dev/tty` prompt so the prompt survives MCP's occupied stdin. Add `confirm_message` to a tool for a templated prompt (`"Delete {path}?"`), and a `resolve` block to turn opaque IDs into human-readable context before asking.
- **`climax test-dialog`** — Shows a synthetic approval dialog so you can confirm your system can display one before relying on it.
- **Paginated discovery** — `climax_search` accepts `offset` and returns `total_matches` and `has_more`, so agents can page through large tool sets instead of truncating.
- **Bundled `gh` and `aws` configs** — 47 GitHub CLI tools and 76 AWS CLI v2 tools, risk-annotated out of the box. Reference by bare name: `climax gh`.
- **Supply-chain cooldown** — Dependency resolution ignores distributions uploaded in the last 7 days, so a compromised release has time to be detected and yanked before it can be pulled in.

### Breaking changes

- **Approval dialogs are on by default.** The default policy is `approval.global: write`, so every tool marked `risk: write` or `risk: destructive` now prompts before running. Across the bundled configs that's 46 write and 6 destructive tools — notably all 4 tools in `claude.yaml`, and 14 in `obsidian.yaml`. To restore 0.4.0 behavior, pass a policy file with `approval.global: none`.
- **Headless environments deny by default.** When no GUI and no TTY are available, the default `approval.headless: deny` refuses the call rather than running it unprompted. If CLImax runs unattended (CI, containers, a remote MCP client with no display), write and destructive tools will now fail closed. Pass `--headless-approve`, or set `approval.headless: approve`, to auto-approve instead. This is the most likely upgrade break for existing automated setups.
- **`mcp` is constrained to `>=1.7,<2`.** mcp 2.0 replaced the low-level `Server` decorator API with constructor-based handler registration, which CLImax cannot run against. Installs previously resolved mcp 2.0.0 and crashed on startup ([#18](https://github.com/get2knowio/climax/issues/18)).

### Features

- `RiskLevel` (`read` / `write` / `destructive`) and `ApprovalLevel` (`none` / `destructive` / `write` / `all`) policy models
- Per-tool approval overrides via `approval.tools.<name>` or a tool policy's `require_approval`
- `resolve` blocks run a secondary CLI command to expand `{variables}` in `confirm_message`
- `--headless-approve` CLI flag to override `approval.headless` without editing a policy file
- Denied calls return `Tool execution denied by user: <tool>` rather than raising
- Config-generator skill documents risk levels and approval behavior
- 373 tests across 18 test modules
- Ruff pinned in CI so lint results don't drift with new releases

## 0.4.0 — 2026-03-16

### Highlights

- **HTTP transports** — Run CLImax as a standalone HTTP server with SSE (`--transport sse`) or Streamable HTTP (`--transport streamable-http`) in addition to the default stdio transport. Same tool registration, discovery modes, and policies apply regardless of transport.
- **Rich request logging** — All incoming MCP requests in HTTP mode are logged to stdout with color-coded, Rich-formatted output showing method, ID, tool name, and arguments.
- **Bundled configs as positional args** — Bundled config names (`git`, `docker`, etc.) are now first-class positional arguments. Custom config files use `--config`. Mix both freely: `climax git --config my-tools.yaml`.

### Breaking changes

- Custom config file paths must now use `--config <path>` instead of being passed as bare positional arguments. Bundled config names (`git`, `docker`, `claude`, `obsidian`) continue to work as positional args.

## 0.2.0 — 2026-02-22

Initial public release on PyPI as `climax-mcp`.

### Highlights

- **Progressive discovery** — By default, CLImax registers two meta-tools (`climax_search` and `climax_call`) instead of exposing every tool at once. Agents discover tools on-demand, keeping LLM context focused. Use `--classic` to register all tools directly.
- **Policy files** — Separate what tools exist from what's allowed. Filter tools, constrain argument values (`pattern`, `min`, `max`), override descriptions, and route execution through Docker containers.
- **Config generation skill** — `climax skill --install` adds a slash command that teaches coding agents to read `--help` output and produce valid YAML configs automatically.
- **Bundled configs** — Ship with ready-to-use configs for git (6 tools), docker (5 tools), obsidian (53 tools), and claude (4 tools). Reference by bare name: `climax git`.

### Features

- Single-file architecture — all logic in `climax.py`
- YAML config → Pydantic validation → MCP tool registration → subprocess execution
- `climax run` / `climax validate` / `climax list` / `climax skill` subcommands
- Argument types: string, integer, number, boolean
- Argument modes: flags, inline flags (`key=value`), positional, auto-flag
- Per-tool timeouts (default 30s)
- Multi-config merge — combine multiple CLIs into one MCP server
- Docker executor for sandboxed command execution
- Stdin piping for large argument values
- `~` and `$HOME` expansion in command paths
- No shell injection — all commands run via `asyncio.create_subprocess_exec`
- 309 tests across 15 test modules
