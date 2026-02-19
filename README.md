# CLImax

Expose **any CLI** as MCP tools via a YAML configuration file.

Instead of writing a custom MCP server for every CLI tool, write a YAML file that describes the CLI's interface and CLImax does the rest.

## How It Works

```
┌──────────────┐     ┌──────────────────┐     ┌─────────────┐
│  LLM Client  │────▶│     CLImax       │────▶│  Your CLI   │
│  (Claude,    │ MCP │  (reads YAML,    │ sub │  (git, jj,  │
│   Cursor,    │◀────│   runs commands)  │◀────│   docker..) │
│   etc.)      │     └──────────────────┘proc │             │
└──────────────┘              ▲                └─────────────┘
                              │
                     ┌────────┴────────┐
                     │   config.yaml   │
                     │  (tool defs +   │
                     │   arg mappings) │
                     └─────────────────┘
```

You need three things:
1. **CLImax** — this program
2. **A YAML file** — describes which commands to expose and how
3. **The CLI** — the actual tool you want to call (must be on PATH)

## Installation

**Requirements:** Python 3.11+

### With uv (recommended)

```bash
uv pip install climax-mcp
```

### With pip

```bash
pip install climax-mcp
```

### From source

```bash
git clone https://github.com/get2know-io/climax.git
cd climax
uv sync       # or: pip install -e .
```

## Quick Start

```bash
# Run with a config file — starts an MCP server over stdio
climax examples/git.yaml

# Combine multiple CLIs into one server
climax examples/jj.yaml examples/git.yaml examples/docker.yaml

# Enable logging to see commands being executed
climax examples/git.yaml --log-level INFO
```

## Usage

### CLI Subcommands

CLImax provides three subcommands for working with configs:

#### `climax run` — Start the MCP server

Starts the MCP stdio server. This is what MCP clients connect to.

```bash
climax run examples/git.yaml
climax run examples/git.yaml examples/docker.yaml --log-level INFO
```

For backward compatibility, you can omit `run`:

```bash
climax examples/git.yaml                # equivalent to: climax run examples/git.yaml
climax examples/git.yaml --log-level DEBUG
```

**Options:**

| Flag | Values | Default | Description |
|------|--------|---------|-------------|
| `--log-level` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `WARNING` | Log verbosity (logs go to stderr) |
| `--transport` | `stdio` | `stdio` | MCP transport protocol |

#### `climax validate` — Check config files

Validates YAML configs against the schema and checks that the referenced CLI binary exists on PATH.

```bash
climax validate examples/git.yaml
#   ✓ git-tools — 6 tool(s)
# All 1 config(s) valid

climax validate examples/git.yaml examples/docker.yaml examples/jj.yaml
#   ✓ git-tools — 6 tool(s)
#   ✓ docker-tools — 5 tool(s)
#   ✓ jj-tools — 8 tool(s)
# All 3 config(s) valid
```

If a config has errors, `validate` prints them and exits with code 1:

```bash
climax validate bad-config.yaml
#   ✗ bad-config.yaml
#     command: Field required
# 0 valid, 1 invalid
```

#### `climax list` — Show available tools

Displays a table of all tools defined across the given configs.

```bash
climax list examples/git.yaml
# git-tools — 6 tool(s)
#
# ┌────────────┬──────────────────────────────┬─────────────┬──────────────┐
# │ Tool       │ Description                  │ Command     │ Arguments    │
# ├────────────┼──────────────────────────────┼─────────────┼──────────────┤
# │ git_status │ Show the working tree status │ git status  │ short ...    │
# │ git_log    │ Show recent commit history   │ git log     │ max_count .. │
# │ ...        │                              │             │              │
# └────────────┴──────────────────────────────┴─────────────┴──────────────┘
```

This is useful for reviewing what a config exposes before connecting it to an LLM.

### Connecting to MCP Clients

#### Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "my-cli": {
      "command": "climax",
      "args": ["/path/to/config.yaml"]
    }
  }
}
```

#### Claude Code

Add to your `.mcp.json`:

```json
{
  "mcpServers": {
    "my-cli": {
      "command": "climax",
      "args": ["/path/to/config.yaml"]
    }
  }
}
```

#### Multiple CLIs in one server

```json
{
  "mcpServers": {
    "dev-tools": {
      "command": "climax",
      "args": ["/path/to/jj.yaml", "/path/to/git.yaml", "/path/to/docker.yaml"]
    }
  }
}
```

#### Running from source

If you haven't installed the package, use `python` directly:

```json
{
  "mcpServers": {
    "my-cli": {
      "command": "python",
      "args": ["/path/to/climax.py", "/path/to/config.yaml"],
      "env": {}
    }
  }
}
```

## Writing a Config

A YAML config describes one CLI and the tools (subcommands) to expose.

### Minimal example

```yaml
name: my-tools
description: "My CLI tools"
command: my-cli

tools:
  - name: my_cli_status
    description: "Show status"
    command: status
```

This exposes a single MCP tool `my_cli_status` that runs `my-cli status`.

### Full config reference

```yaml
name: my-tools                    # server name (used in logs and client UI)
description: "What these tools do"
command: my-cli                   # base command (on PATH or absolute path)
env:                              # optional extra env vars for subprocess
  MY_VAR: "value"
working_dir: /some/path           # optional working directory

tools:
  - name: my_cli_action           # tool name (snake_case)
    description: "What this does"  # shown to the LLM
    command: "sub command"         # appended to base → `my-cli sub command`
    args:
      - name: target
        type: string              # string | integer | number | boolean
        description: "The target"
        required: true
        positional: true          # no flag, value placed directly

      - name: format
        type: string
        flag: "--format"          # becomes `--format <value>`
        enum: ["json", "table"]   # restrict values

      - name: verbose
        type: boolean
        flag: "--verbose"         # boolean: flag present if true, absent if false

      - name: count
        type: integer
        flag: "-n"
        default: 10               # used when the argument is not provided
```

### Argument types

| Type | JSON Schema | CLI Behavior |
|------|------------|--------------|
| `string` | `"string"` | `--flag value` |
| `integer` | `"integer"` | `--flag 42` |
| `number` | `"number"` | `--flag 3.14` |
| `boolean` | `"boolean"` | `--flag` (present) or omitted |

### Argument modes

- **Flag args**: Have `flag: "--something"`. The value follows the flag.
- **Positional args**: Have `positional: true`. The value is placed directly in the command, in definition order.
- **Auto-flag**: If neither `flag` nor `positional` is set, a flag is auto-generated from the arg name (`my_arg` → `--my-arg`).

### Argument fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | *(required)* | Argument name (used as the JSON property name) |
| `description` | string | `""` | Shown to the LLM to explain the argument |
| `type` | string | `"string"` | One of `string`, `integer`, `number`, `boolean` |
| `required` | bool | `false` | Whether the LLM must provide this argument |
| `default` | any | `null` | Default value used when argument is not provided |
| `flag` | string | `null` | CLI flag (e.g. `"--format"`, `"-n"`) |
| `positional` | bool | `false` | Place value directly in the command (no flag) |
| `enum` | list | `null` | Restrict values to this set |

## Generating Configs with an LLM

The fastest way to create a config is to have an LLM generate it from your CLI's `--help` output. CLImax ships with a skill ([`skill/SKILL.md`](skill/SKILL.md)) that teaches LLMs exactly how to produce valid configs.

**With Claude Code or any skill-aware agent:**

Point the agent at the skill and ask it to generate a config for your CLI. It will capture the help output, select the right commands, and produce a ready-to-use YAML file.

**Manually:**

```bash
# Capture help output
my-cli --help > /tmp/help.txt
my-cli subcommand --help >> /tmp/help.txt

# Paste into any LLM along with the contents of skill/SKILL.md
```

The skill covers the full YAML schema, naming conventions, argument mapping patterns, and a validation checklist.

## Examples

See [`examples/`](examples/) for ready-to-use configs:

- [`git.yaml`](examples/git.yaml) — Common Git operations (status, log, diff, branch, add, commit)
- [`jj.yaml`](examples/jj.yaml) — Jujutsu version control (status, log, diff, describe, new, bookmarks, push)
- [`docker.yaml`](examples/docker.yaml) — Docker container/image inspection (ps, images, logs, inspect, compose ps)
- [`coreutils.yaml`](examples/coreutils.yaml) — Simple echo-based tools (useful for testing)

## Security Notes

- Commands are executed via `asyncio.create_subprocess_exec` (no shell injection)
- Commands time out after 30 seconds by default
- The YAML author controls what commands are exposed — review configs before use
- Consider read-only tool sets for untrusted environments

## License

MIT
