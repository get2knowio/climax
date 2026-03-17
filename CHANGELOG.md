# Changelog

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
