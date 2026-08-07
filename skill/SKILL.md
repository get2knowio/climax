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

**Flag destructive commands** clearly in the description if you do include them: "⚠️ DESTRUCTIVE: Permanently deletes..." — and set `risk: destructive`, which triggers an approval dialog at runtime. See [Approval Dialogs](#approval-dialogs).

### Step 3: Generate the YAML

Follow the schema and rules below precisely.

## YAML Schema Reference

```yaml
# --- Top-level (CLImaxConfig) ---
name: "<cli>-tools"                  # Short identifier, conventionally <cli>-tools
description: "MCP tools for <X>"     # What this collection of tools does
command: "<cli>"                     # Base command (must be on PATH or absolute path)
env:                                 # Optional: extra env vars for all commands
  KEY: "value"
working_dir: "/some/path"            # Optional: working directory for all commands

# --- Tools list (ToolDef) ---
tools:
  - name: <cli>_<action>             # snake_case, MUST be prefixed with CLI name
    description: "<what and why>"     # Explain WHEN and WHY to use this, not just what
    command: "<subcommand>"           # Appended to base command (can be multi-word)
    timeout: 30                      # Optional: seconds before killing (default 30)
    risk: read                       # Optional: read (default) | write | destructive
                                     # write/destructive PROMPT the user by default
    confirm_message: "Delete {path}?" # Optional: approval dialog template (uses arg names)
    resolve:                         # Optional: resolve opaque IDs for confirm_message
      _friendly_name:                # Variable name available in confirm_message
        command: "describe-thing"    # Subcommand (inherits base command)
        args:                        # Arg templates using {arg_name} from tool args
          id: "{thing_id}"
        timeout: 10                  # Short timeout (default 10s)

    # --- Arguments (ToolArg) ---
    args:                            # Optional — omit entirely for no-arg commands
      - name: <arg_name>            # snake_case
        type: string                 # string | integer | number | boolean
        description: "<what>"        # Clear, concise
        required: false              # true if command fails without it
        flag: "--flag-name"          # CLI flag (omit for positional args)
        positional: false            # true = no flag, placed directly on command line
        default: <value>             # Optional default value
        enum: [val1, val2]           # Optional: restrict to specific values
        cwd: false                   # true = value sets working directory, not passed to CLI
        stdin: false                 # true = value piped via stdin, not passed to CLI
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

### Special Arg Modes
10. **`cwd: true`** — the arg value sets the subprocess working directory instead of being passed on the command line. Use for tools that need to run in a user-specified directory.
11. **`stdin: true`** — the arg value is piped to the process via stdin instead of passed as a CLI argument. Use for large text content (note bodies, file contents, patches) that would be unwieldy or fragile as command-line args.
12. **`timeout`** (on `ToolDef`, not `ToolArg`) — per-tool timeout in seconds, overriding the default 30s. Set higher for write operations or commands that talk to slow APIs.

### Multi-word Subcommands
13. The `command` field supports multi-word subcommands: `command: "bookmark list"` produces `jj bookmark list`
14. Nest logically: `jj_bookmark_list` with `command: "bookmark list"`, not a separate `bookmark` tool

### Descriptions
15. Write descriptions for an **LLM audience** — explain when and why to use the tool, not just what it does
16. Bad: `"Run git log"` — Good: `"Show recent commit history with optional filtering by author or count"`
17. For args, describe the **effect**: Bad: `"The format flag"` — Good: `"Output format — use 'json' for structured data, 'table' for human reading"`

### Defaults and Required
18. Mark `required: true` only for args the command genuinely fails without
19. Use `default` for sensible defaults that save the LLM from always specifying them (e.g. `default: 10` for log limits)
20. Don't mark everything required — let the LLM call tools with minimal args

### Safety & Risk Levels
21. Never expose args that allow arbitrary shell execution (e.g. `--exec`, `--command`)
22. Set `risk: write` for tools that modify state; `risk: destructive` for irreversible operations
23. Add `confirm_message` to destructive tools with a clear description of what will happen
24. Use `resolve` blocks when tool arguments contain opaque IDs that need human-readable context in the approval dialog
25. Prefer read-only tool sets for untrusted environments
26. **`risk` is load-bearing, not documentation** — it decides whether the user gets an approval dialog at runtime. Read the next section before assigning it.

## Approval Dialogs

Since 0.5.0, the `risk` field controls real runtime behavior. **By default, every tool marked `risk: write` or `risk: destructive` shows a native confirmation dialog before it runs**, and the call does not proceed until the user approves it.

This makes `risk` the highest-stakes field in the config. Getting it wrong fails in both directions:

- **Too high** (marking a read-only tool `write`) — the user gets a popup on every routine call. A `git_log` or `aws_s3_ls` that prompts is worse than useless; people disable approvals entirely, losing protection on the tools that needed it.
- **Too low** (leaving a destructive tool at the default `read`) — it executes silently with no confirmation. This is the dangerous direction.

### How the level is decided

The default policy is `approval.global: write`. Levels, from a policy file:

| `approval.global` | Prompts for |
|---|---|
| `none` | nothing |
| `destructive` | `risk: destructive` only |
| `write` *(default)* | `risk: write` and `risk: destructive` |
| `all` | every tool call, including reads |

Per-tool overrides win over the global level — `approval.tools.<tool_name>: false` in a policy file, or `require_approval` on a tool policy entry.

### Assigning risk

- **`read`** (default) — inspects state and returns it. Listing, showing, searching, diffing, describing, logs. Safe to run repeatedly.
- **`write`** — changes state, but the change is recoverable or routine. Creating a note, committing, tagging, adding a label, uploading a file.
- **`destructive`** — irreversible, or destroys work. Deleting, force-pushing, hard-resetting, terminating instances, overwriting without backup. **Always pair with `confirm_message`.**

The dividing line for `destructive` is *"could the user get this back if they clicked Approve by mistake?"* — not how alarming the verb sounds.

### Writing `confirm_message`

Without one, the user sees the raw assembled command. That's fine for simple tools and poor for anything with opaque arguments. Name the specific thing being affected:

```yaml
  - name: gh_pr_close
    description: "Close a pull request without merging it"
    command: pr close
    risk: write
    confirm_message: "Close PR #{number} in {repo}?"
```

When the argument is an ID the user won't recognize, use a `resolve` block to look up something human-readable first. The resolve command runs *before* the dialog, and its output becomes a template variable:

```yaml
  - name: aws_ec2_terminate
    description: "⚠️ DESTRUCTIVE: Permanently terminate an EC2 instance"
    command: ec2 terminate-instances
    risk: destructive
    resolve:
      _instance_name:
        command: "ec2 describe-instances"
        args:
          instance-ids: "{instance_id}"
          query: "Reservations[0].Instances[0].Tags[?Key=='Name']|[0].Value"
        timeout: 10
    confirm_message: "Terminate instance {_instance_name} ({instance_id})? This cannot be undone."
```

`Terminate instance web-prod-01 (i-0abc123)?` is a decision the user can actually make. `Terminate instance i-0abc123?` is not.

Template variables come from the tool's own arg names plus any `resolve` keys. A name that doesn't resolve degrades to a generic message rather than failing the call, so verify every `{placeholder}` matches a real arg or resolve key.

### Headless environments

If no GUI **and** no TTY is available, the default `approval.headless: deny` refuses the call rather than running it unprompted. Anything marked `write` or `destructive` will fail closed when CLImax runs unattended — CI, a container, a remote MCP client with no display.

That is the correct default, but it means risk annotations decide whether a config works at all in automation. If a config is meant for unattended use, say so, and point at `--headless-approve` or `approval.global: none` rather than downgrading honest risk levels to make prompts go away.

Users can verify dialogs display on their system with `climax test-dialog`.

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

### Stdin for large content
```yaml
  - name: obsidian_create
    description: "Create a new note in the vault"
    command: create
    timeout: 120
    args:
      - name: path
        type: string
        flag: "path="
      - name: content
        type: string
        description: "Note content"
        stdin: true
```
The `content` value is piped via stdin; only `path=` appears on the command line.

### Working directory arg
```yaml
  - name: git_status
    description: "Show working tree status for a specific repo"
    command: status
    args:
      - name: directory
        type: string
        description: "Repository path to run in"
        cwd: true
```
The `directory` value sets the subprocess working directory — it never appears on the command line.

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
- [ ] Destructive tools have `risk: destructive` and a `confirm_message`
- [ ] Write tools have `risk: write`
- [ ] Read-only tools are **not** marked `write` — they would prompt on every call
- [ ] Every `{placeholder}` in a `confirm_message` matches a real arg name or `resolve` key
- [ ] `confirm_message` names the specific thing affected, not just the action
- [ ] `resolve` blocks reference valid argument names in their templates
- [ ] If the config targets unattended use, the approval implications are called out

## Output

Save the generated config as `<cli>.yaml`. If the user has an existing CLImax project, save to the `configs/` directory. The file should be immediately usable:

```bash
climax <cli>.yaml --log-level INFO
```

## Iterating

After the first pass, offer to:
- Expand coverage by capturing more `--help` subcommand output
- Add missing args that the user frequently uses
- Split a large config into read-only vs read-write tool sets
- Test the config by running `climax <cli>.yaml --log-level DEBUG` and checking the tool list
