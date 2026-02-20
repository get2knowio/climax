"""
CLImax: Expose any CLI as MCP tools via YAML configuration.

Point an LLM at your CLI's --help output, have it generate a YAML config,
and instantly get an MCP server for that CLI. No custom code needed.

Usage:
    climax validate config.yaml [config2.yaml ...]
    climax list config.yaml [config2.yaml ...]
    climax run config.yaml [config2.yaml ...]
    climax config.yaml [--log-level ...]         # backward compat
"""

import asyncio
import logging
import os
import re
import shutil
import sys
import time
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

import mcp.server.stdio
import mcp.types as types
from mcp.server.lowlevel import Server

# Rich logging to stderr (stdout is reserved for MCP stdio transport)
console = Console(stderr=True)

# Default handler: Rich to stderr (visible in MCP client logs)
_stderr_handler = RichHandler(console=console, rich_tracebacks=True, show_path=False)

logging.basicConfig(
    level=logging.WARNING,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[_stderr_handler],
)
logger = logging.getLogger("climax")

# Optional file log: set CLIMAX_LOG_FILE to enable persistent logging
_log_file = os.environ.get("CLIMAX_LOG_FILE")
if _log_file:
    _file_handler = logging.FileHandler(_log_file)
    _file_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-8s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    ))
    _file_handler.setLevel(logging.DEBUG)
    logger.addHandler(_file_handler)


# ---------------------------------------------------------------------------
# Configuration models
# ---------------------------------------------------------------------------

class ArgType(str, Enum):
    string = "string"
    integer = "integer"
    number = "number"
    boolean = "boolean"


class ToolArg(BaseModel):
    """A single argument for a CLI tool."""
    name: str
    description: str = ""
    type: ArgType = ArgType.string
    required: bool = False
    default: Any = None
    flag: str | None = None          # e.g. "--format", "-f"
    positional: bool = False         # if True, value is placed positionally (no flag)
    enum: list[str] | None = None    # restrict to specific values


class ToolDef(BaseModel):
    """A single tool that maps to a CLI subcommand."""
    name: str
    description: str                 # required — shown to the LLM, avoids leaking command details
    command: str = ""                # subcommand(s) appended to base, e.g. "users list"
    args: list[ToolArg] = Field(default_factory=list)
    timeout: float | None = None     # per-tool timeout in seconds (overrides default 30s)


class CLImaxConfig(BaseModel):
    """Top-level configuration for a single CLI."""
    name: str = "climax"
    description: str = ""
    command: str                     # base command, e.g. "docker" or "/usr/bin/my-app"
    env: dict[str, str] = Field(default_factory=dict)  # extra env vars for subprocess
    working_dir: str | None = None
    tools: list[ToolDef]


# ---------------------------------------------------------------------------
# Resolved tool: a ToolDef + the config it came from
# ---------------------------------------------------------------------------

class ResolvedTool(BaseModel):
    """A tool definition paired with its parent CLI config."""
    tool: ToolDef
    base_command: str
    env: dict[str, str] = Field(default_factory=dict)
    working_dir: str | None = None
    description_override: str | None = None
    arg_constraints: dict[str, "ArgConstraint"] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Policy models
# ---------------------------------------------------------------------------

class ArgConstraint(BaseModel):
    """Constraint on a single tool argument."""
    pattern: str | None = None     # regex (fullmatch) for string args
    min: float | None = None       # inclusive minimum for numeric args
    max: float | None = None       # inclusive maximum for numeric args


class ToolPolicy(BaseModel):
    """Per-tool policy: description override and arg constraints."""
    description: str | None = None
    args: dict[str, ArgConstraint] = Field(default_factory=dict)


class ExecutorType(str, Enum):
    local = "local"
    docker = "docker"


class ExecutorConfig(BaseModel):
    """Execution environment configuration."""
    type: ExecutorType = ExecutorType.local
    image: str | None = None
    volumes: list[str] = Field(default_factory=list)
    working_dir: str | None = None
    network: str | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.type == ExecutorType.docker and not self.image:
            raise ValueError("Docker executor requires 'image' to be set")


class DefaultPolicy(str, Enum):
    enabled = "enabled"
    disabled = "disabled"


class PolicyConfig(BaseModel):
    """Top-level policy configuration."""
    executor: ExecutorConfig = Field(default_factory=ExecutorConfig)
    default: DefaultPolicy = DefaultPolicy.disabled
    tools: dict[str, ToolPolicy] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# YAML → Config
# ---------------------------------------------------------------------------

def load_config(path: str | Path) -> CLImaxConfig:
    """Load and validate a YAML config file."""
    raw = Path(path).read_text()
    data = yaml.safe_load(raw)
    return CLImaxConfig(**data)


def load_configs(paths: list[str | Path]) -> tuple[str, dict[str, ResolvedTool]]:
    """
    Load one or more YAML configs and merge their tools.

    Returns (server_name, tool_map) where tool_map maps
    tool name → ResolvedTool with the correct base command.
    """
    tool_map: dict[str, ResolvedTool] = {}
    names: list[str] = []

    for path in paths:
        config = load_config(path)
        names.append(config.name)
        logger.info(
            "Loaded [bold]%s[/bold] from %s (%d tools)",
            config.name, path, len(config.tools),
            extra={"markup": True},
        )

        for tool_def in config.tools:
            if tool_def.name in tool_map:
                logger.warning(
                    "Duplicate tool name [bold]%s[/bold] — overwriting (from %s)",
                    tool_def.name, path,
                    extra={"markup": True},
                )
            tool_map[tool_def.name] = ResolvedTool(
                tool=tool_def,
                base_command=config.command,
                env=config.env,
                working_dir=config.working_dir,
            )

    # Server name: use the single config name, or combine them
    server_name = names[0] if len(names) == 1 else "climax"

    logger.info(
        "Server [bold]%s[/bold] ready with %d tools",
        server_name, len(tool_map),
        extra={"markup": True},
    )

    return server_name, tool_map


# ---------------------------------------------------------------------------
# Policy loading and application
# ---------------------------------------------------------------------------

def load_policy(path: str | Path) -> PolicyConfig:
    """Load and validate a policy YAML file."""
    raw = Path(path).read_text()
    data = yaml.safe_load(raw)
    return PolicyConfig(**data)


def apply_policy(
    tool_map: dict[str, ResolvedTool],
    policy: PolicyConfig,
) -> dict[str, ResolvedTool]:
    """
    Apply a policy to a tool map: filter tools, set overrides and constraints.

    Returns a new filtered tool_map.
    """
    # Warn about unknown tool names in policy
    for tool_name in policy.tools:
        if tool_name not in tool_map:
            logger.warning(
                "Policy references unknown tool [bold]%s[/bold] — skipping",
                tool_name,
                extra={"markup": True},
            )

    result: dict[str, ResolvedTool] = {}

    for name, resolved in tool_map.items():
        tool_policy = policy.tools.get(name)

        if policy.default == DefaultPolicy.disabled:
            # Only tools explicitly listed survive
            if tool_policy is None:
                continue
        # default=enabled: all tools survive

        # Clone the resolved tool with overrides
        new_resolved = resolved.model_copy()

        if tool_policy is not None:
            if tool_policy.description is not None:
                new_resolved.description_override = tool_policy.description
            if tool_policy.args:
                # Warn about unknown arg names
                known_args = {a.name for a in resolved.tool.args}
                for arg_name in tool_policy.args:
                    if arg_name not in known_args:
                        logger.warning(
                            "Policy tool [bold]%s[/bold] references unknown arg "
                            "[bold]%s[/bold] — skipping",
                            name, arg_name,
                            extra={"markup": True},
                        )
                new_resolved.arg_constraints = {
                    k: v for k, v in tool_policy.args.items()
                    if k in known_args
                }

        result[name] = new_resolved

    return result


def validate_arguments(
    arguments: dict[str, Any],
    tool_def: ToolDef,
    constraints: dict[str, ArgConstraint],
) -> list[str]:
    """
    Validate argument values against policy constraints.

    Returns a list of error messages (empty = valid).
    """
    errors: list[str] = []

    for arg_name, constraint in constraints.items():
        if arg_name not in arguments:
            continue

        value = arguments[arg_name]

        if constraint.pattern is not None and isinstance(value, str):
            if not re.fullmatch(constraint.pattern, value):
                errors.append(
                    f"Argument '{arg_name}': value '{value}' does not match "
                    f"pattern '{constraint.pattern}'"
                )

        if constraint.min is not None:
            try:
                num = float(value)
                if num < constraint.min:
                    errors.append(
                        f"Argument '{arg_name}': value {value} is below "
                        f"minimum {constraint.min}"
                    )
            except (TypeError, ValueError):
                pass

        if constraint.max is not None:
            try:
                num = float(value)
                if num > constraint.max:
                    errors.append(
                        f"Argument '{arg_name}': value {value} exceeds "
                        f"maximum {constraint.max}"
                    )
            except (TypeError, ValueError):
                pass

    return errors


def build_docker_prefix(executor: ExecutorConfig) -> list[str]:
    """Build a docker run prefix command list from executor config."""
    cmd = ["docker", "run", "--rm"]

    for vol in executor.volumes:
        cmd.extend(["-v", os.path.expandvars(vol)])

    if executor.network:
        cmd.extend(["--network", executor.network])

    if executor.working_dir:
        cmd.extend(["-w", executor.working_dir])

    cmd.append(executor.image)  # type: ignore[arg-type]

    return cmd


# ---------------------------------------------------------------------------
# Config → JSON Schema (for MCP tool input schemas)
# ---------------------------------------------------------------------------

TYPE_MAP = {
    ArgType.string: "string",
    ArgType.integer: "integer",
    ArgType.number: "number",
    ArgType.boolean: "boolean",
}


def build_input_schema(args: list[ToolArg]) -> dict:
    """Convert a list of ToolArg into a JSON Schema object."""
    properties: dict[str, Any] = {}
    required: list[str] = []

    for arg in args:
        prop: dict[str, Any] = {
            "type": TYPE_MAP[arg.type],
        }
        if arg.description:
            prop["description"] = arg.description
        if arg.default is not None:
            prop["default"] = arg.default
        if arg.enum:
            prop["enum"] = arg.enum

        properties[arg.name] = prop

        if arg.required:
            required.append(arg.name)

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required

    return schema


# ---------------------------------------------------------------------------
# Arguments → CLI command list
# ---------------------------------------------------------------------------

def build_command(
    base_cmd: str,
    tool_def: ToolDef,
    arguments: dict[str, Any],
) -> list[str]:
    """
    Build a subprocess-safe command list from the base command,
    tool subcommand, and provided arguments.
    """
    # Start with base command (split to handle e.g. "python -m myapp")
    cmd = base_cmd.split()

    # Add subcommand parts
    if tool_def.command:
        cmd.extend(tool_def.command.split())

    # First pass: positional args (in definition order)
    for arg_def in tool_def.args:
        if arg_def.positional and arg_def.name in arguments:
            cmd.append(str(arguments[arg_def.name]))

    # Second pass: flag args
    for arg_def in tool_def.args:
        if arg_def.positional:
            continue

        value = arguments.get(arg_def.name)

        # If not provided and has a default, use it
        if value is None and arg_def.default is not None:
            value = arg_def.default
        if value is None:
            continue

        flag = arg_def.flag
        if not flag:
            # Auto-generate flag from name
            flag = f"--{arg_def.name.replace('_', '-')}"

        if arg_def.type == ArgType.boolean:
            # Boolean: include flag if True, omit if False
            if value is True or value == "true":
                cmd.append(flag)
        elif flag.endswith("="):
            # Inline flag: concatenate flag and value as one token (e.g. "file=myfile")
            cmd.append(f"{flag}{value}")
        else:
            cmd.append(flag)
            cmd.append(str(value))

    return cmd


# ---------------------------------------------------------------------------
# Execute CLI command
# ---------------------------------------------------------------------------

async def run_command(
    cmd: list[str],
    env: dict[str, str] | None = None,
    working_dir: str | None = None,
    timeout: float = 30.0,
) -> tuple[int, str, str]:
    """Run a command asynchronously and return (returncode, stdout, stderr)."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    try:
        logger.debug("Spawning: %s (cwd=%s)", cmd[0], working_dir or "<inherited>")
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=full_env,
            cwd=working_dir,
        )
        logger.debug("Process started (pid=%s)", proc.pid)
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        return (
            proc.returncode or 0,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )
    except asyncio.TimeoutError:
        logger.warning(
            "⏱ Timeout after %.1fs (pid=%s, cmd=%s) — killing process",
            timeout, getattr(proc, 'pid', '?'), cmd[0],
        )
        proc.kill()  # type: ignore
        return (-1, "", f"Command timed out after {timeout}s")
    except FileNotFoundError:
        logger.error("Command not found: %s", cmd[0])
        return (-1, "", f"Command not found: {cmd[0]}")


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

def create_server(
    server_name: str,
    tool_map: dict[str, ResolvedTool],
    executor: ExecutorConfig | None = None,
) -> Server:
    """Create and configure the MCP server from resolved tools."""

    server = Server(server_name)

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        """Return all tools from all loaded configs."""
        result = []
        for name, resolved in tool_map.items():
            td = resolved.tool
            description = resolved.description_override or td.description
            result.append(
                types.Tool(
                    name=td.name,
                    description=description,
                    inputSchema=build_input_schema(td.args),
                )
            )
        return result

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[types.TextContent]:
        """Execute the CLI command for the given tool."""
        resolved = tool_map.get(name)
        if not resolved:
            logger.warning("Unknown tool called: %s", name)
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]

        arguments = arguments or {}

        # Validate arguments against policy constraints
        if resolved.arg_constraints:
            errors = validate_arguments(arguments, resolved.tool, resolved.arg_constraints)
            if errors:
                error_text = "Policy validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
                logger.warning("Policy rejected %s: %s", name, "; ".join(errors))
                return [types.TextContent(type="text", text=error_text)]

        cmd = build_command(resolved.base_command, resolved.tool, arguments)

        # Prepend docker prefix if executor is docker type
        if executor and executor.type == ExecutorType.docker:
            cmd = build_docker_prefix(executor) + cmd

        cmd_str = " ".join(cmd)

        # Build a display-friendly version that truncates large values
        display_parts = []
        for token in cmd:
            if len(token) > 120:
                display_parts.append(f"{token[:60]}…[{len(token)} bytes]")
            else:
                display_parts.append(token)
        cmd_display = " ".join(display_parts)

        logger.info("▶ %s", cmd_display)
        logger.debug("▶ full command: %s", cmd_str)
        t0 = time.monotonic()

        tool_timeout = resolved.tool.timeout or 30.0
        returncode, stdout, stderr = await run_command(
            cmd,
            env=resolved.env or None,
            working_dir=resolved.working_dir,
            timeout=tool_timeout,
        )

        elapsed = time.monotonic() - t0

        if returncode == 0:
            logger.info(
                "✓ %s completed in %.1fs (%d bytes)",
                name, elapsed, len(stdout),
            )
        else:
            logger.warning(
                "✗ %s failed (exit %d) in %.1fs",
                name, returncode, elapsed,
            )
            if stderr.strip():
                logger.debug("stderr: %s", stderr.strip()[:200])

        # Build response
        parts = []
        if stdout.strip():
            parts.append(stdout.strip())
        if stderr.strip():
            parts.append(f"[stderr]\n{stderr.strip()}")
        if returncode != 0:
            parts.append(f"[exit code: {returncode}]")

        text = "\n\n".join(parts) if parts else "(no output)"

        return [types.TextContent(type="text", text=text)]

    return server


# ---------------------------------------------------------------------------
# CLI subcommands
# ---------------------------------------------------------------------------

def cmd_validate(args, console: Console | None = None) -> int:
    """Validate one or more YAML config files. Returns 0 if all valid, 1 otherwise."""
    console = console or Console()
    valid = 0
    invalid = 0

    for path in args.configs:
        try:
            config = load_config(path)
            console.print(f"  [green]✓[/green] {config.name} — {len(config.tools)} tool(s)")

            # Deep check: warn if command binary is not on PATH
            binary = config.command.split()[0]
            if not shutil.which(binary):
                console.print(f"    [yellow]⚠ '{binary}' not found on PATH[/yellow]")

            valid += 1
        except ValidationError as e:
            console.print(f"  [red]✗[/red] {path}")
            for err in e.errors():
                loc = " → ".join(str(l) for l in err["loc"])
                console.print(f"    {loc}: {err['msg']}")
            invalid += 1
        except Exception as e:
            console.print(f"  [red]✗[/red] {path}: {e}")
            invalid += 1

    # Validate policy file if provided
    policy_path = getattr(args, "policy", None)
    if policy_path:
        try:
            policy = load_policy(policy_path)
            console.print(f"  [green]✓[/green] policy — {len(policy.tools)} tool rule(s)")
        except ValidationError as e:
            console.print(f"  [red]✗[/red] {policy_path} (policy)")
            for err in e.errors():
                loc = " → ".join(str(l) for l in err["loc"])
                console.print(f"    {loc}: {err['msg']}")
            invalid += 1
        except Exception as e:
            console.print(f"  [red]✗[/red] {policy_path} (policy): {e}")
            invalid += 1

    if invalid == 0:
        console.print(f"\nAll {valid} config(s) valid")
    else:
        console.print(f"\n{valid} valid, {invalid} invalid")

    return 0 if invalid == 0 else 1


def cmd_list(args, console: Console | None = None) -> int:
    """List all tools from the given config files."""
    console = console or Console()

    try:
        server_name, tool_map = load_configs(args.configs)
    except Exception as e:
        console.print(f"[red]Error loading configs:[/red] {e}")
        return 1

    # Apply policy filtering if provided
    policy_path = getattr(args, "policy", None)
    policy = None
    if policy_path:
        try:
            policy = load_policy(policy_path)
            tool_map = apply_policy(tool_map, policy)
        except Exception as e:
            console.print(f"[red]Error loading policy:[/red] {e}")
            return 1

    console.print(f"[bold]{server_name}[/bold] — {len(tool_map)} tool(s)\n")

    # Show executor info if non-local
    if policy and policy.executor.type != ExecutorType.local:
        console.print(
            f"[dim]Executor: {policy.executor.type.value} "
            f"(image={policy.executor.image})[/dim]\n"
        )

    table = Table(show_header=True, header_style="bold")
    table.add_column("Tool")
    table.add_column("Description")
    table.add_column("Command")
    table.add_column("Arguments")

    for name in sorted(tool_map):
        resolved = tool_map[name]
        td = resolved.tool
        description = resolved.description_override or td.description

        # Format arguments column
        arg_parts = []
        for a in td.args:
            parts = [f"[bold]{a.name}[/bold]"]
            meta = []
            if a.type != ArgType.string:
                meta.append(a.type.value)
            if a.required:
                meta.append("required")
            if a.positional:
                meta.append("positional")
            if a.default is not None:
                meta.append(f"default={a.default}")
            if a.enum:
                meta.append(f"enum={a.enum}")
            # Show constraints from policy
            constraint = resolved.arg_constraints.get(a.name)
            if constraint:
                if constraint.pattern is not None:
                    meta.append(f"pattern={constraint.pattern}")
                if constraint.min is not None:
                    meta.append(f"min={constraint.min}")
                if constraint.max is not None:
                    meta.append(f"max={constraint.max}")
            if meta:
                parts.append(f"({', '.join(meta)})")
            arg_parts.append(" ".join(parts))

        args_str = "\n".join(arg_parts) if arg_parts else "[dim]none[/dim]"
        full_cmd = f"{resolved.base_command} {td.command}".strip()

        table.add_row(name, description, full_cmd, args_str)

    console.print(table)
    return 0


def cmd_run(args) -> None:
    """Start the MCP server (stdio transport)."""
    logger.setLevel(getattr(logging, args.log_level))

    server_name, tool_map = load_configs(args.configs)

    executor = None
    policy_path = getattr(args, "policy", None)
    if policy_path:
        policy = load_policy(policy_path)
        tool_map = apply_policy(tool_map, policy)
        executor = policy.executor

    server = create_server(server_name, tool_map, executor=executor)

    async def run():
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    asyncio.run(run())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _add_policy_arg(parser):
    """Add the --policy argument to a parser."""
    parser.add_argument("--policy", metavar="POLICY", default=None, help="Policy YAML file")


def _build_run_parser(parser=None):
    """Build the 'run' argument parser (reused for backward compat)."""
    import argparse

    if parser is None:
        parser = argparse.ArgumentParser()
    parser.add_argument("configs", nargs="+", metavar="CONFIG")
    _add_policy_arg(parser)
    parser.add_argument("--transport", choices=["stdio"], default="stdio", help="MCP transport (default: stdio)")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="WARNING", help="Logging level")
    return parser


def main():
    import argparse

    SUBCOMMANDS = {"validate", "list", "run"}

    # Check if the first positional arg is a known subcommand
    argv = sys.argv[1:]
    first_positional = next((a for a in argv if not a.startswith("-")), None)

    if first_positional not in SUBCOMMANDS:
        # Backward compat: climax config.yaml [--log-level ...]
        run_parser = _build_run_parser()
        args = run_parser.parse_args(argv)
        cmd_run(args)
        return

    parser = argparse.ArgumentParser(
        description="CLImax: expose any CLI as MCP tools via YAML config"
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    # --- validate ---
    p_validate = subparsers.add_parser("validate", help="Validate config file(s)")
    p_validate.add_argument("configs", nargs="+", metavar="CONFIG")
    _add_policy_arg(p_validate)

    # --- list ---
    p_list = subparsers.add_parser("list", help="List tools from config file(s)")
    p_list.add_argument("configs", nargs="+", metavar="CONFIG")
    _add_policy_arg(p_list)

    # --- run ---
    _build_run_parser(subparsers.add_parser("run", help="Start MCP server"))

    args = parser.parse_args(argv)

    if args.subcommand == "validate":
        sys.exit(cmd_validate(args))
    elif args.subcommand == "list":
        sys.exit(cmd_list(args))
    elif args.subcommand == "run":
        cmd_run(args)


if __name__ == "__main__":
    main()
