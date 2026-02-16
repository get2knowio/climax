You are generating a YAML configuration file for CLImax, a tool that
exposes CLI commands as MCP (Model Context Protocol) tools.

Given the CLI help output below, create a YAML config that maps the most useful
commands to MCP tools. Follow this schema:

```yaml
name: "<short-name>-tools"
description: "MCP tools for <what this CLI does>"
command: "<base-command>"

tools:
  - name: <tool_name>              # snake_case, prefix with CLI name
    description: "<what it does>"   # clear description for an LLM to understand
    command: "<subcommand>"         # appended to base command
    args:
      - name: <arg_name>           # snake_case
        type: string|integer|number|boolean
        description: "<what this arg does>"
        required: true|false
        flag: "--flag-name"         # the CLI flag (omit for positional args)
        positional: true|false      # true = no flag, value placed directly
        default: <value>            # optional default
        enum: [val1, val2]          # optional allowed values
```

Rules:
1. Use snake_case for all names, prefixed with the CLI name (e.g. git_status)
2. Boolean args map to flags that are present/absent (no value)
3. Positional args have `positional: true` and no `flag`
4. Flag args have `flag: "--something"`
5. Include the most commonly useful commands — not every obscure subcommand
6. Write descriptions that help an LLM understand WHEN and WHY to use each tool
7. Mark truly required args as `required: true`
8. For destructive commands (delete, remove, etc.), note the risk in the description

Here is the CLI help output:

---
{PASTE CLI HELP OUTPUT HERE}
---

Generate the YAML config:
