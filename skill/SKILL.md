---
name: climax-config-generator
description: "Generate CLImax YAML configuration files that expose CLI tools as MCP servers. Use when someone wants to create a new CLImax config for a CLI tool, or update an existing one. Trigger on: 'create a config for <CLI>', 'add <CLI> to CLImax', 'generate MCP tools for <CLI>', or when the user provides --help output and wants it turned into a YAML config."
---

# CLImax Config Generator

Generate YAML configuration files for CLImax — a tool that exposes any CLI as MCP (Model Context Protocol) tools via a simple YAML mapping.

## What CLImax Does

CLImax reads a YAML file that describes a CLI's commands and arguments, then runs as an MCP server that exposes those commands as tools. An LLM client (Claude Desktop, Cursor, etc.) can then discover and invoke those CLI commands directly.

The YAML config is the only thing you need to write. CLImax handles the MCP protocol, subprocess execution, argument assembly, timeouts, and error handling.

## Workflow

### Step 1: Gather CLI Information

You need the CLI's help output to generate a good config. Ask the user to provide it, or if you have shell access, capture it directly:

```bash
# Top-level help
<cli> --help

# Subcommand help (repeat for each important subcommand)
<cli> <subcommand> --help
```

If the user provides only top-level help, that's fine for a first pass. You can note which subcommands would benefit from deeper `--help` inspection and offer to expand later.

### Step 2: Decide Which Commands to Expose

Not every subcommand should be a tool. Apply this filter:

**Include:**
- Commands an LLM would reasonably want to call (status, list, show, diff, create, describe)
- Read operations that provide context (logs, inspect, search)
- Common write operations with clear semantics (commit, push, tag)

**Exclude:**
- Interactive commands (edit, rebase -i, shell) — they require a TTY
- Dangerous low-level operations (force-push, hard-reset, drop) unless specifically requested
- Setup/init commands that are run once (init, clone, install)
- Commands that produce binary output (export archives, dump databases)

**Flag destructive commands** clearly in the description if you do include them: "⚠️ DESTRUCTIVE: Permanently deletes..."

### Step 3: Generate the YAML

Follow the schema and rules below precisely.

## YAML Schema Reference

```yaml
# Required top-level fields
name: "<cli>-tools"                  # Short identifier, conventionally <cli>-tools
description: "MCP tools for <X>"     # What this collection of tools does
command: "<cli>"                     # Base command (must be on PATH or absolute path)

# Optional top-level fields
env:                                 # Extra environment variables for all commands
  KEY: "value"
working_dir: "/some/path"            # Working directory for all commands

# Tools list — one entry per exposed command
tools:
  - name: <cli>_<action>             # snake_case, MUST be prefixed with CLI name
    description: "<what and why>"     # Explain WHEN and WHY to use this, not just what
    command: "<subcommand>"           # Appended to base command (can be multi-word)
    args:                            # Optional — omit entirely for no-arg commands
      - name: <arg_name>            # snake_case
        type: string                 # string | integer | number | boolean
        description: "<what>"        # Clear, concise
        required: false              # true if command fails without it
        flag: "--flag-name"          # CLI flag (omit for positional args)
        positional: false            # true = no flag, placed directly on command line
        default: <value>             # Optional default value
        enum: [val1, val2]           # Optional allowed values
```

## Rules

### Naming
1. Tool names are **snake_case**, always prefixed with the CLI name: `git_status`, `docker_ps`, `jj_log`
2. Arg names are **snake_case**: `max_count`, `output_format`, `no_graph`
3. The `name` field must be unique across all tools (this matters when multiple configs are merged)

### Argument Mapping
4. **Flag args** have `flag: "--something"` — value follows the flag: `--format json`
5. **Boolean args** have `type: boolean` — the flag is present when true, absent when false: `--verbose`
6. **Positional args** have `positional: true` and NO `flag` — value placed directly: `git clone <url>`
7. **Auto-flag fallback** — if neither `flag` nor `positional` is set, CLImax generates `--<arg-name>` from the arg name (underscores → hyphens)
8. **Short flags** are fine: `flag: "-n"` works
9. **Enum** restricts values and helps the LLM pick valid options — use when the CLI has a known set of choices

### Multi-word Subcommands
10. The `command` field supports multi-word subcommands: `command: "bookmark list"` produces `jj bookmark list`
11. Nest logically: `jj_bookmark_list` with `command: "bookmark list"`, not a separate `bookmark` tool

### Descriptions
12. Write descriptions for an **LLM audience** — explain when and why to use the tool, not just what it does
13. Bad: `"Run git log"` — Good: `"Show recent commit history with optional filtering by author or count"`
14. For args, describe the **effect**: Bad: `"The format flag"` — Good: `"Output format — use 'json' for structured data, 'table' for human reading"`

### Defaults and Required
15. Mark `required: true` only for args the command genuinely fails without
16. Use `default` for sensible defaults that save the LLM from always specifying them (e.g. `default: 10` for log limits)
17. Don't mark everything required — let the LLM call tools with minimal args

### Safety
18. Never expose args that allow arbitrary shell execution (e.g. `--exec`, `--command`)
19. Flag destructive tools in the description
20. Prefer read-only tool sets for untrusted environments

## Patterns and Examples

### No-arg command (simplest case)
```yaml
  - name: jj_status
    description: "Show the working copy status and repo state"
    command: status
```

### Boolean flags
```yaml
    args:
      - name: verbose
        type: boolean
        description: "Show detailed output"
        flag: "--verbose"
```
Produces: `<cmd> --verbose` when true, nothing when false.

### Positional then flags
```yaml
  - name: git_add
    description: "Stage files for the next commit"
    command: add
    args:
      - name: path
        type: string
        description: "File or directory to stage (use '.' for all)"
        required: true
        positional: true
```
Positional args are placed before flag args in the assembled command.

### Multi-word subcommand
```yaml
  - name: docker_compose_ps
    description: "List containers managed by Docker Compose"
    command: compose ps
```
Produces: `docker compose ps`

### Enum-restricted values
```yaml
      - name: format
        type: string
        description: "Output format"
        flag: "--format"
        enum: ["json", "table", "csv"]
```

## Validation Checklist

After generating a config, mentally verify:

- [ ] Every tool name is prefixed with the CLI name and is snake_case
- [ ] Every tool name is unique
- [ ] `command` at top level is just the base command (e.g. `git`, not `git status`)
- [ ] Tool-level `command` is the subcommand only (e.g. `status`, not `git status`)
- [ ] Required args are truly required (the command errors without them)
- [ ] Boolean args have `type: boolean` (not string "true"/"false")
- [ ] Positional args have `positional: true` and no `flag`
- [ ] Flag args have an explicit `flag` or a name that auto-converts cleanly (underscores → hyphens)
- [ ] Descriptions explain when/why, not just what
- [ ] No interactive or TTY-dependent commands are exposed
- [ ] Destructive commands are flagged in their description

## Output

Save the generated config as `<cli>.yaml`. If the user has an existing CLImax project, save to the `examples/` directory. The file should be immediately usable:

```bash
climax <cli>.yaml --log-level INFO
```

## Iterating

After the first pass, offer to:
- Expand coverage by capturing more `--help` subcommand output
- Add missing args that the user frequently uses
- Split a large config into read-only vs read-write tool sets
- Test the config by running `climax <cli>.yaml --log-level DEBUG` and checking the tool list
