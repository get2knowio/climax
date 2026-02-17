# CLImax

Expose **any CLI** as MCP tools via a YAML configuration file.

Instead of writing a custom MCP server for every CLI tool, write a YAML file that describes the CLI's interface and CLImax does the rest.

## Quick Start

```bash
# Install
pip install -e .
# or with uv
uv pip install -e .

# Run with a single config
climax examples/git.yaml

# Or combine multiple CLIs into one server
climax examples/jj.yaml examples/git.yaml examples/docker.yaml

# Enable Rich logging to see what's happening
climax examples/jj.yaml --log-level INFO
```

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

## YAML Config Format

```yaml
name: my-tools                    # server name
description: "What these tools do"
command: my-cli                   # base command (on PATH or absolute path)
env:                              # optional extra env vars
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
```

### Argument Types

| Type | JSON Schema | CLI Behavior |
|------|------------|--------------|
| `string` | `"string"` | `--flag value` |
| `integer` | `"integer"` | `--flag 42` |
| `number` | `"number"` | `--flag 3.14` |
| `boolean` | `"boolean"` | `--flag` (present) or omitted |

### Argument Modes

- **Flag args**: Have `flag: "--something"`. Value follows the flag.
- **Positional args**: Have `positional: true`. Value placed directly in command.
- **Auto-flag**: If neither `flag` nor `positional` is set, a flag is auto-generated from the arg name (`my_arg` → `--my-arg`).

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

## Connecting to Claude Desktop / Cursor

Add to your `claude_desktop_config.json` or MCP client config:

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

Multiple CLIs in one server:

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

## Examples

See [`examples/`](examples/) for ready-to-use configs:
- [`git.yaml`](examples/git.yaml) — Common Git operations
- [`jj.yaml`](examples/jj.yaml) — Jujutsu version control
- [`docker.yaml`](examples/docker.yaml) — Docker container/image inspection

## Security Notes

- Commands are executed via `asyncio.create_subprocess_exec` (no shell injection)
- Commands time out after 30 seconds by default
- The YAML author controls what commands are exposed — review configs before use
- Consider read-only tool sets for untrusted environments
