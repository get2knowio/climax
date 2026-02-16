"""
CLImax: Expose any CLI as MCP tools via YAML configuration.

Point an LLM at your CLI's --help output, have it generate a YAML config,
and instantly get an MCP server for that CLI. No custom code needed.

Usage:
    python climax.py config.yaml
    climax config.yaml --log-level DEBUG
"""

import asyncio
import logging
import sys
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

import mcp.server.stdio
import mcp.types as types
from mcp.server.lowlevel import Server

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
    """Top-level configuration for CLImax."""
    name: str = "climax"
    description: str = ""
    command: str                     # base command, e.g. "docker" or "/usr/bin/my-app"
    env: dict[str, str] = Field(default_factory=dict)  # extra env vars for subprocess
    working_dir: str | None = None
    tools: list[ToolDef]


# ---------------------------------------------------------------------------
# YAML → Config
# ---------------------------------------------------------------------------

def load_config(path: str | Path) -> CLImaxConfig:
    """Load and validate a YAML config file."""
    raw = Path(path).read_text()
    data = yaml.safe_load(raw)
    return CLImaxConfig(**data)


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

def create_server(config: CLImaxConfig) -> Server:
    """Create and configure the MCP server from a CLImaxConfig."""

    server = Server(config.name)

    # Build a lookup table: tool_name → ToolDef
    tool_map: dict[str, ToolDef] = {t.name: t for t in config.tools}

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        """Return all tools defined in the YAML config."""
        result = []
        for tool_def in config.tools:
            result.append(
                types.Tool(
                    name=tool_def.name,
                    description=tool_def.description or f"Run: {config.command} {tool_def.command}",
                    inputSchema=build_input_schema(tool_def.args),
                )
            )
        return result

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[types.TextContent]:
        """Execute the CLI command for the given tool."""
        tool_def = tool_map.get(name)
        if not tool_def:
            return [types.TextContent(
                type="text",
                text=f"Unknown tool: {name}",
            )]

        arguments = arguments or {}
        cmd = build_command(config.command, tool_def, arguments)

        logger.info(f"Executing: {' '.join(cmd)}")

        returncode, stdout, stderr = await run_command(
            cmd,
            env=config.env or None,
            working_dir=config.working_dir,
        )

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
        "config",
        help="Path to YAML configuration file",
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

    logging.basicConfig(level=getattr(logging, args.log_level), stream=sys.stderr)

    config = load_config(args.config)
    logger.info(f"Loaded config: {config.name} with {len(config.tools)} tools")

    server = create_server(config)

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
