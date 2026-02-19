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
└──────────────┘         ▲         ▲          └─────────────┘
                         │         │
                ┌────────┴───┐ ┌───┴──────────┐
                │ config.yaml│ │ policy.yaml  │
                │ (tool defs)│ │ (optional)   │
                └────────────┘ └──────────────┘
```

You need three things:
1. **CLImax** — this program
2. **A YAML config** — describes which commands to expose and how
3. **The CLI** — the actual tool you want to call (must be on PATH)

Optionally, a **policy file** controls which tools are enabled, constrains argument values, overrides descriptions, and can route execution through Docker containers.

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

# Apply a policy to restrict tools and arguments
climax --policy my-project.policy.yaml examples/git.yaml

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
climax run --policy readonly.policy.yaml examples/git.yaml
```

For backward compatibility, you can omit `run`:

```bash
climax examples/git.yaml                # equivalent to: climax run examples/git.yaml
climax --policy policy.yaml examples/git.yaml
```

**Options:**

| Flag | Values | Default | Description |
|------|--------|---------|-------------|
| `--policy` | path to YAML | *(none)* | Policy file to restrict tools and constrain arguments |
| `--log-level` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `WARNING` | Log verbosity (logs go to stderr) |
| `--transport` | `stdio` | `stdio` | MCP transport protocol |

#### `climax validate` — Check config files

Validates YAML configs against the schema and checks that the referenced CLI binary exists on PATH. If `--policy` is provided, the policy file is also validated.

```bash
climax validate examples/git.yaml
#   ✓ git-tools — 6 tool(s)
# All 1 config(s) valid

climax validate --policy policy.yaml examples/git.yaml
#   ✓ git-tools — 6 tool(s)
#   ✓ policy — 3 tool rule(s)
# All 1 config(s) valid
```

If a config or policy has errors, `validate` prints them and exits with code 1:

```bash
climax validate bad-config.yaml
#   ✗ bad-config.yaml
#     command: Field required
# 0 valid, 1 invalid
```

#### `climax list` — Show available tools

Displays a table of all tools defined across the given configs. If `--policy` is provided, the list is filtered to show only enabled tools, with any policy constraints and description overrides applied.

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

climax list --policy readonly.policy.yaml examples/git.yaml
# git-tools — 2 tool(s)
# ...only the tools enabled by the policy are shown...
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

#### With a policy file

```json
{
  "mcpServers": {
    "git-readonly": {
      "command": "climax",
      "args": ["--policy", "/path/to/readonly.policy.yaml", "/path/to/git.yaml"]
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

## Policies

A policy file separates **what tools exist** (the config, shareable) from **what's allowed** (the policy, per-user or per-deployment). This lets you share comprehensive tool configs while restricting access per environment.

**No policy = today's behavior** — all tools enabled, local execution, no constraints.

### Why use a policy?

- Share a full `git.yaml` covering every subcommand, but only enable read-only tools for a particular deployment
- Constrain argument values (e.g., file paths must match `^src/`, max count of 100)
- Override tool descriptions for a specific context
- Route all command execution through a Docker container for sandboxing

### Policy YAML schema

```yaml
executor:                           # optional — execution environment
  type: docker                      # "local" (default) or "docker"
  image: "alpine/git:latest"        # required when type is docker
  volumes:                          # bind mounts (env vars expanded)
    - "${PROJECT_DIR}:/workspace"
  working_dir: /workspace           # -w flag for docker run
  network: none                     # --network flag for docker run

default: disabled                   # "disabled" (default) or "enabled"
                                    # disabled = only listed tools are exposed
                                    # enabled  = all tools exposed, listed ones get constraints

tools:
  git_status: {}                    # enabled with no constraints
  git_log:
    description: "Show recent log (max 100)"   # overrides the config's description
    args:
      max_count:
        max: 100                    # inclusive maximum for numeric args
  git_add:
    args:
      path:
        pattern: "^src/.*"          # regex (fullmatch) for string args
  git_diff:
    args:
      commits:
        min: 0                      # inclusive minimum for numeric args
        max: 5
```

### Policy fields reference

#### Top-level

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `executor` | object | `{type: "local"}` | Execution environment configuration |
| `default` | string | `"disabled"` | Whether unmentioned tools are enabled or disabled |
| `tools` | map | `{}` | Per-tool policies keyed by tool name |

#### `executor`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `type` | string | `"local"` | `"local"` or `"docker"` |
| `image` | string | *(required for docker)* | Docker image to use |
| `volumes` | list | `[]` | Bind mounts (`-v` flags). Environment variables are expanded. |
| `working_dir` | string | `null` | Working directory inside the container (`-w` flag) |
| `network` | string | `null` | Docker network mode (`--network` flag) |

#### `tools.<name>`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `description` | string | `null` | Override the tool's description (shown to the LLM) |
| `args` | map | `{}` | Per-argument constraints keyed by argument name |

#### `tools.<name>.args.<arg>`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `pattern` | string | `null` | Regex pattern — value must fullmatch (for string args) |
| `min` | number | `null` | Inclusive minimum (for numeric args) |
| `max` | number | `null` | Inclusive maximum (for numeric args) |

### Examples

**Read-only Git policy** — only expose status, log, and diff:

```yaml
default: disabled
tools:
  git_status: {}
  git_log:
    args:
      max_count:
        max: 100
  git_diff: {}
```

**Docker-sandboxed execution:**

```yaml
executor:
  type: docker
  image: alpine/git:latest
  volumes:
    - "${PROJECT_DIR}:/workspace"
  working_dir: /workspace
  network: none
default: disabled
tools:
  git_status: {}
  git_log: {}
```

**Allow all tools but constrain one:**

```yaml
default: enabled
tools:
  git_add:
    args:
      path:
        pattern: "^src/.*"
```

### Behavior details

- Unknown tool names in the policy are warned about and skipped (not an error)
- Unknown argument names in a tool's policy are warned about and skipped
- When `default: disabled`, only tools explicitly listed in `tools` are exposed
- When `default: enabled`, all tools are exposed; listed tools get constraints/overrides applied
- Argument validation happens before command execution — rejected calls never run the subprocess
- Docker executor prepends `docker run --rm` with the configured flags to every command

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
- Use a **policy file** to restrict which tools are enabled and constrain argument values
- Use the **Docker executor** to sandbox command execution in a container
- Policy argument constraints use `re.fullmatch` — patterns must match the entire value

## License

MIT
