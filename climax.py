"""
CLImax: Expose any CLI as MCP tools via YAML configuration.

Point an LLM at your CLI's --help output, have it generate a YAML config,
and instantly get an MCP server for that CLI. No custom code needed.

Usage:
    climax config.yaml
    climax jj.yaml git.yaml docker.yaml
    climax config.yaml --log-level DEBUG
"""

import asyncio
import logging
import sys
import time
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from rich.console import Console
from rich.logging import RichHandler

import mcp.server.stdio
import mcp.types as types
from mcp.server.lowlevel import Server

# Rich logging to stderr (stdout is reserved for MCP stdio transport)
console = Console(stderr=True)

logging.basicConfig(
    level=logging.WARNING,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
)
logger = logging.getLogger("climax")


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
    description: str = ""
    command: str = ""                # subcommand(s) appended to base, e.g. "users list"
    args: list[ToolArg] = Field(default_factory=list)


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
    import os

    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=full_env,
            cwd=working_dir,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        return (
            proc.returncode or 0,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )
    except asyncio.TimeoutError:
        proc.kill()  # type: ignore
        return (-1, "", f"Command timed out after {timeout}s")
    except FileNotFoundError:
        return (-1, "", f"Command not found: {cmd[0]}")


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

def create_server(
    server_name: str,
    tool_map: dict[str, ResolvedTool],
) -> Server:
    """Create and configure the MCP server from resolved tools."""

    server = Server(server_name)

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        """Return all tools from all loaded configs."""
        result = []
        for name, resolved in tool_map.items():
            td = resolved.tool
            result.append(
                types.Tool(
                    name=td.name,
                    description=td.description or f"Run: {resolved.base_command} {td.command}",
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
        cmd = build_command(resolved.base_command, resolved.tool, arguments)
        cmd_str = " ".join(cmd)

        logger.info("▶ %s", cmd_str)
        t0 = time.monotonic()

        returncode, stdout, stderr = await run_command(
            cmd,
            env=resolved.env or None,
            working_dir=resolved.working_dir,
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
# Entry point
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="CLImax: expose any CLI as MCP tools via YAML config"
    )
    parser.add_argument(
        "configs",
        nargs="+",
        metavar="CONFIG",
        help="Path(s) to YAML configuration file(s)",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio"],
        default="stdio",
        help="MCP transport (default: stdio)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="WARNING",
        help="Logging level",
    )

    args = parser.parse_args()

    # Update log level from CLI arg
    logger.setLevel(getattr(logging, args.log_level))

    server_name, tool_map = load_configs(args.configs)
    server = create_server(server_name, tool_map)

    async def run():
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    asyncio.run(run())


if __name__ == "__main__":
    main()
