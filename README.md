# CLImax

Expose **any CLI** as MCP tools via a YAML configuration file.

Instead of writing a custom MCP server for every CLI tool, write a YAML file that describes the CLI's interface and CLImax does the rest.

## Contents

- [How It Works](#how-it-works)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Connecting to MCP Clients](#connecting-to-mcp-clients)
- [Discovery Modes](#discovery-modes)
- [Creating Configs](#creating-configs)
- [CLI Reference](#cli-reference)
- [Bundled Configs](#bundled-configs)
- [Config Reference](#config-reference)
- [Meta-Tools Reference](#meta-tools-reference)
- [Policies](#policies)
- [Security](#security)
- [License](#license)

## How It Works

```
┌──────────────┐     ┌──────────────────┐     ┌─────────────┐
│  MCP Client  │────▶│     CLImax       │────▶│ Target CLI  │
│  (Claude,    │ MCP │  (reads YAML,    │ sub │  (git,      │
│   Cursor,    │◀────│   runs commands) │◀────│   docker..) │
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
# Install as a CLI tool (adds `climax` to PATH)
uv tool install climax-mcp

# Or run directly without installing
uvx --from climax-mcp climax list
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
# Run with a bundled config by name — starts an MCP server with progressive discovery (default)
climax git

# Combine multiple CLIs into one server
climax git docker

# Use classic mode — register all tools directly instead of meta-tools
climax --classic git

# Apply a policy to restrict tools and arguments
climax --policy my-project.policy.yaml git

# Enable logging to see commands being executed
climax git --log-level INFO

# Use a custom config file (path or .yaml extension)
climax my-config.yaml
```

CLImax ships with ready-to-use configs for git, docker, claude, and obsidian — see [`configs/README.md`](configs/README.md) for details on each config, including available tools and environment variables.

## Connecting to MCP Clients

Add a CLImax server to your MCP client's config file. The JSON structure is the same everywhere — only the file location differs:

| Client | Config file |
|--------|-------------|
| Claude Desktop | `claude_desktop_config.json` |
| Claude Code | `.mcp.json` (project root) |
| Cursor | `.cursor/mcp.json` |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` |

### Basic setup

```json
{
  "mcpServers": {
    "git": {
      "command": "climax",
      "args": ["git"]
    }
  }
}
```

Run `climax list` to see available [bundled config](#bundled-configs) names. Custom config files work too — pass a path instead of a name.

By default, MCP clients will see two meta-tools (`climax_search` and `climax_call`) for on-demand tool discovery. See [Discovery Modes](#discovery-modes) for details.

### Variations

Change the `"args"` array to customize behavior:

| Variation | `"args"` value |
|-----------|---------------|
| Classic mode (all tools directly) | `["--classic", "git"]` |
| Multiple CLIs in one server | `["git", "docker"]` |
| With a policy file | `["--policy", "/path/to/policy.yaml", "git"]` |
| Custom config file | `["/path/to/my-config.yaml"]` |

To run without installing, use `uvx` as the command:

```json
"command": "uvx",
"args": ["climax-mcp", "git"]
```

## Discovery Modes

### Progressive Discovery (Default)

By default, CLImax registers only two meta-tools in the MCP `tools/list` response:

- **`climax_search`** — Find tools by keyword, category, CLI name, or browse all available CLIs
- **`climax_call`** — Execute a discovered tool by name

Instead of seeing hundreds of tools at once, the agent discovers what's available on-demand:

```
Agent: "Search for git commit tools"
  ↓
climax_search(query="commit")
  → Returns tools with names, descriptions, arguments, and types
  ↓
Agent: "Call git_commit with message='fix bug'"
  ↓
climax_call(tool_name="git_commit", args={message: "fix bug"})
  → Executes the command and returns stdout/stderr/exit code
```

This is ideal for:
- Large tool sets (hundreds of subcommands across multiple CLIs)
- LLMs with tight context windows
- Dynamic tool discovery workflows

See [Meta-Tools Reference](#meta-tools-reference) for full parameter details.

### Classic Mode

If you prefer all tools registered directly in the MCP response, use the `--classic` flag:

```bash
climax --classic git docker
```

In classic mode, `tools/list` returns all individual tools directly. Meta-tools (`climax_search` and `climax_call`) are not registered. This matches the behavior of versions prior to `002-mcp-meta-tools`.

## Creating Configs

The easiest way to create a config is to let an LLM generate it. CLImax ships with a skill ([`skill/SKILL.md`](skill/SKILL.md)) that teaches agents how to read `--help` output and produce valid YAML configs automatically.

### With Claude Code (recommended)

Install the CLImax skill into your project, then ask Claude to generate configs:

```bash
climax skill --install   # copies skill to .claude/commands/climax-config.md
```

Now just ask:

```
> Create a CLImax config for kubectl
```

The agent will run `kubectl --help`, inspect relevant subcommands, and generate a ready-to-use YAML config. No manual YAML writing required.

### With other coding agents

For Cursor, Windsurf, Copilot, or any agent that supports custom instructions, run `climax skill` to print the skill text and paste it into your agent's system prompt or rules file.

### With any LLM

Capture your CLI's help output and paste it into any LLM along with the contents of [`skill/SKILL.md`](skill/SKILL.md):

```bash
# Capture help output
my-cli --help > /tmp/help.txt
my-cli subcommand --help >> /tmp/help.txt

# Paste both into ChatGPT, Claude, etc.
```

The skill covers the full YAML schema, naming conventions, argument mapping patterns, and a validation checklist — everything the LLM needs to produce a correct config.

### Validate the result

After generating a config, verify it:

```bash
climax validate my-config.yaml
climax list my-config.yaml
```

### Writing configs by hand

If you prefer to write configs manually, see the [Config Reference](#config-reference) section below.

## CLI Reference

CLImax provides four subcommands for working with configs:

### `climax run` — Start the MCP server

Starts the MCP stdio server. This is what MCP clients connect to. Configs can be referenced by bare name (resolves to bundled configs) or by file path.

By default, the server uses [progressive discovery mode](#discovery-modes) — `climax_search` and `climax_call` meta-tools are registered instead of individual CLI tools.

```bash
climax run git
climax run git docker --log-level INFO
climax run --policy readonly.policy.yaml git
climax run --classic git                    # use classic mode instead
```

For backward compatibility, you can omit `run`:

```bash
climax git                        # equivalent to: climax run git
climax --policy policy.yaml git
climax --classic git              # use classic mode
```

**Options:**

| Flag | Values | Default | Description |
|------|--------|---------|-------------|
| `--classic` | *(flag)* | disabled | Register all individual tools directly instead of using meta-tools ([progressive discovery](#discovery-modes) is default) |
| `--policy` | path to YAML | *(none)* | Policy file to restrict tools and constrain arguments |
| `--log-level` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `WARNING` | Log verbosity (logs go to stderr) |
| `--transport` | `stdio` | `stdio` | MCP transport protocol |

**Environment variables:**

| Variable | Description |
|----------|-------------|
| `CLIMAX_LOG_FILE` | Path to a log file for persistent logging (in addition to stderr). Useful for debugging MCP servers where stderr may not be visible. Always logs at DEBUG level. |

### `climax validate` — Check config files

Validates YAML configs against the schema and checks that the referenced CLI binary exists on PATH. If `--policy` is provided, the policy file is also validated.

```bash
climax validate git
#   ✓ git-tools — 6 tool(s)
# All 1 config(s) valid

climax validate --policy policy.yaml git
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

### `climax list` — Show available tools

Displays a table of all tools defined across the given configs. If `--policy` is provided, the list is filtered to show only enabled tools, with any policy constraints and description overrides applied.

With no arguments, lists the available bundled config names:

```bash
climax list
# Bundled configs:
#   claude
#   docker
#   git
#   obsidian
```

With a config name or path, shows the tools table:

```bash
climax list git
# git-tools — 6 tool(s)
#
# ┌────────────┬──────────────────────────────┬─────────────┬──────────────┐
# │ Tool       │ Description                  │ Command     │ Arguments    │
# ├────────────┼──────────────────────────────┼─────────────┼──────────────┤
# │ git_status │ Show the working tree status │ git status  │ short ...    │
# │ git_log    │ Show recent commit history   │ git log     │ max_count .. │
# │ ...        │                              │             │              │
# └────────────┴──────────────────────────────┴─────────────┴──────────────┘

climax list --policy readonly.policy.yaml git
# git-tools — 2 tool(s)
# ...only the tools enabled by the policy are shown...
```

This is useful for reviewing what a config exposes before connecting it to an LLM.

### `climax skill` — Config generation skill

Outputs or installs the CLImax config-generation skill for use with coding agents.

```bash
climax skill              # print skill text to stdout
climax skill --path       # print path to SKILL.md
climax skill --install    # install to .claude/commands/climax-config.md
```

See [Creating Configs](#creating-configs) for usage details.

## Bundled Configs

CLImax ships with bundled configs in [`configs/`](configs/) — usable by bare name (`climax git`, `climax list docker`):

| Config | CLI | Tools | Description |
|--------|-----|------:|-------------|
| [`git`](configs/git.yaml) | `git` | 6 | Common Git operations (status, log, diff, branch, add, commit) |
| [`docker`](configs/docker.yaml) | `docker` | 5 | Container/image inspection (ps, images, logs, inspect, compose ps) |
| [`obsidian`](configs/obsidian.yaml) | Obsidian CLI | 53 | Vault management — read, write, search, tags, links, tasks, daily notes, properties. Uses inline flags for `key=value` argument style. |
| [`claude`](configs/claude.yaml) | `claude` | 4 | Claude Code integration — ask, ask with model, JSON output, custom system prompt |

The `examples/` directory contains test-only configs:

- [`coreutils.yaml`](examples/coreutils.yaml) — Simple echo-based tools (used by e2e tests)

## Config Reference

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

### Full config schema

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
    timeout: 120                   # optional per-tool timeout in seconds (default: 30)
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

- **Flag args**: Have `flag: "--something"`. The value follows the flag as a separate token.
- **Inline flags**: Have `flag: "key="` (ending with `=`). The flag and value are joined as a single token (`key=value`). Useful for CLIs that use `key=value` syntax instead of `--key value` (e.g., Obsidian CLI).
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

## Meta-Tools Reference

CLImax exposes two meta-tools by default that enable [progressive discovery](#discovery-modes):

### `climax_search` — Discover tools

Search for tools by keyword, category, or CLI name. Returns matching tools with their full argument schemas.

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | string | *(optional)* | Search by tool name or description (substring match) |
| `category` | string | *(optional)* | Filter by tool category (e.g., "vcs", "container") |
| `cli` | string | *(optional)* | Filter by CLI name (e.g., "git-tools", "docker-tools") |
| `limit` | integer | 10 | Maximum number of results to return |

**Behavior:**

- If `query`, `category`, or `cli` are provided, returns matching tools with full details (name, description, CLI, category, tags, argument schema)
- If none of these are provided (only `limit` or no parameters), returns a summary of all loaded CLIs with tool counts, categories, and tags

**Example request:**

```json
{
  "tool": "climax_search",
  "input": {
    "query": "commit",
    "limit": 5
  }
}
```

**Example response:**

```json
{
  "mode": "search",
  "results": [
    {
      "tool_name": "git_commit",
      "description": "Create a new commit",
      "cli_name": "git-tools",
      "category": "vcs",
      "tags": ["git"],
      "args": [
        {
          "name": "message",
          "type": "string",
          "description": "Commit message",
          "required": true,
          "flag": "-m"
        },
        {
          "name": "all",
          "type": "boolean",
          "description": "Stage all changes",
          "flag": "-a"
        }
      ]
    }
  ]
}
```

### `climax_call` — Execute a tool

Execute a discovered tool by name with optional arguments.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `tool_name` | string | The name of the tool to execute (e.g., "git_commit") |
| `args` | object | Arguments to pass to the tool (keys match tool's argument names) |

**Validation:**

- Required arguments are checked before execution
- Argument types are coerced where compatible (e.g., string "42" → integer 42)
- Enum values are validated against allowed values
- Extra arguments are ignored

**Example request:**

```json
{
  "tool": "climax_call",
  "input": {
    "tool_name": "git_commit",
    "args": {
      "message": "Add user authentication",
      "all": true
    }
  }
}
```

**Example response:**

```
Creating commit with message: Add user authentication

[exit code: 0]
```

**Example error response (missing required argument):**

```
Error: Argument 'message' is required
```

## Policies

A policy file restricts which tools are enabled and constrains argument values — separating **what tools exist** (the config) from **what's allowed** (the policy).

**No policy = all tools enabled, no constraints.**

### Quick example

Read-only Git — only expose status, log, and diff, with a cap on log entries:

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

```bash
climax --policy readonly.policy.yaml git
```

### When to use policies

| Goal | How |
|------|-----|
| Restrict to read-only tools | `default: disabled`, list only safe tools |
| Constrain argument values | Add `pattern`, `min`, `max` under `args` |
| Override tool descriptions | Add `description` per tool |
| Sandbox execution in Docker | Add `executor` with `type: docker` |
| Share configs, vary access | Same config YAML + different policy per environment |

### Full schema

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

### Field reference

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

### More examples

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

## Security

- Commands are executed via `asyncio.create_subprocess_exec` (no shell injection)
- Commands time out after 30 seconds by default — override per-tool with `timeout:` in the config
- The YAML author controls what commands are exposed — review configs before use
- Use a **policy file** to restrict which tools are enabled and constrain argument values
- Use the **Docker executor** to sandbox command execution in a container
- Policy argument constraints use `re.fullmatch` — patterns must match the entire value

## License

MIT
