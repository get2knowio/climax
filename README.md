# CLImax

Expose **any CLI** as MCP tools via a YAML configuration file.

Instead of writing a custom MCP server for every CLI tool, write a YAML file that describes the CLI's interface and CLImax does the rest.

## Quick Start

```bash
# Install
pip install -e .
# or with uv
uv pip install -e .

# Run with a config
python climax.py examples/git.yaml

# Or as installed script
climax examples/jj.yaml
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

The fastest way to create a config is to paste your CLI's `--help` output into an LLM along with the prompt template in [`generate-config-prompt.md`](generate-config-prompt.md):

```bash
# Capture help output
my-cli --help > /tmp/help.txt
my-cli subcommand --help >> /tmp/help.txt

# Then paste into an LLM with the prompt template
```

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

Or with uv:

```json
{
  "mcpServers": {
    "my-cli": {
      "command": "uv",
      "args": ["run", "--with", "climax", "climax", "/path/to/config.yaml"],
      "env": {}
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
