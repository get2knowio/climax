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
import json
import logging
import os
import platform
import re
import shutil
import sys
import time
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError
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

CONFIGS_DIR = Path(__file__).parent / "configs"

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


class RiskLevel(str, Enum):
    read = "read"
    write = "write"
    destructive = "destructive"


class ToolArg(BaseModel):
    """A single argument for a CLI tool."""
    name: str
    description: str = ""
    type: ArgType = ArgType.string
    required: bool = False
    default: Any = None
    flag: str | None = None          # e.g. "--format", "-f"
    positional: bool = False         # if True, value is placed positionally (no flag)
    cwd: bool = False                # if True, value sets subprocess working directory (not passed to command)
    stdin: bool = False              # if True, value is piped via stdin (not passed as CLI arg)
    enum: list[str] | None = None    # restrict to specific values


class ResolveConfig(BaseModel):
    """Resolve an opaque argument value to a human-readable string for approval dialogs."""
    command: str                     # subcommand to run (inherits base command)
    args: dict[str, str] = Field(default_factory=dict)  # arg templates using {arg_name}
    timeout: float = 10.0            # short timeout — must not block long


class ToolDef(BaseModel):
    """A single tool that maps to a CLI subcommand."""
    name: str
    description: str                 # required — shown to the LLM, avoids leaking command details
    command: str = ""                # subcommand(s) appended to base, e.g. "users list"
    args: list[ToolArg] = Field(default_factory=list)
    timeout: float | None = None     # per-tool timeout in seconds (overrides default 30s)
    risk: RiskLevel = RiskLevel.read  # risk level: read (default), write, or destructive
    confirm_message: str | None = None  # approval dialog template, e.g. "Delete {path}?"
    resolve: dict[str, ResolveConfig] = Field(default_factory=dict)  # resolve opaque IDs


class CLImaxConfig(BaseModel):
    """Top-level configuration for a single CLI."""
    name: str = "climax"
    description: str = ""
    command: str                     # base command, e.g. "docker" or "/usr/bin/my-app"
    env: dict[str, str] = Field(default_factory=dict)  # extra env vars for subprocess
    working_dir: str | None = None
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    global_args: list[ToolArg] = Field(default_factory=list)
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
    global_args: list[ToolArg] = Field(default_factory=list)
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
    """Per-tool policy: description override, arg constraints, and approval override."""
    description: str | None = None
    args: dict[str, ArgConstraint] = Field(default_factory=dict)
    require_approval: bool | None = None  # None = defer to global, True/False = override


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


class ApprovalLevel(str, Enum):
    none = "none"                  # never require approval
    destructive = "destructive"    # only destructive tools
    write = "write"                # write + destructive
    all = "all"                    # every tool call


class HeadlessPolicy(str, Enum):
    deny = "deny"                  # deny if no GUI/TTY available (fail-safe)
    approve = "approve"            # auto-approve if no GUI/TTY (for CI/automation)


class ApprovalConfig(BaseModel):
    """Global and per-tool approval policy."""
    model_config = ConfigDict(populate_by_name=True)

    global_level: ApprovalLevel = Field(default=ApprovalLevel.write, alias="global")
    headless: HeadlessPolicy = HeadlessPolicy.deny
    tools: dict[str, bool] = Field(default_factory=dict)  # per-tool override


class PolicyConfig(BaseModel):
    """Top-level policy configuration."""
    executor: ExecutorConfig = Field(default_factory=ExecutorConfig)
    default: DefaultPolicy = DefaultPolicy.disabled
    tools: dict[str, ToolPolicy] = Field(default_factory=dict)
    approval: ApprovalConfig = Field(default_factory=ApprovalConfig)


# ---------------------------------------------------------------------------
# Tool discovery index models
# ---------------------------------------------------------------------------


class ToolIndexEntry(BaseModel):
    """A single searchable tool entry in the discovery index.

    Represents a tool with all metadata needed for search and display.
    The ``input_schema`` contains the full JSON Schema for tool arguments,
    enabling agents to construct valid tool calls without additional lookups.
    """

    model_config = ConfigDict(frozen=True)

    tool_name: str
    description: str
    cli_name: str
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    _search_text: str = ""

    def model_post_init(self, __context: Any) -> None:
        """Pre-compute lowercased search text from all searchable fields."""
        parts = [self.tool_name, self.description, self.cli_name]
        if self.category:
            parts.append(self.category)
        parts.extend(self.tags)
        object.__setattr__(self, "_search_text", " ".join(parts).lower())


class CLISummary(BaseModel):
    """Summary of a CLI available in the discovery index.

    Provides a high-level overview of a loaded CLI config, including
    its name, description, tool count, and optional discovery metadata.
    """

    name: str
    description: str
    tool_count: int
    category: str | None = None
    tags: list[str] = Field(default_factory=list)

    @classmethod
    def from_config(cls, config: "CLImaxConfig") -> "CLISummary":
        """Build a summary from a loaded config object."""
        return cls(
            name=config.name,
            description=config.description,
            tool_count=len(config.tools),
            category=config.category,
            tags=list(config.tags),
        )


class ToolIndex:
    """In-memory searchable index of MCP tools across loaded configs.

    Provides search, summary, and exact-lookup methods for progressive
    tool discovery. Built once from configs via ``from_configs()`` and
    then only queried — no mutation methods exist.
    """

    def __init__(
        self,
        entries: list[ToolIndexEntry],
        resolved: dict[str, ResolvedTool],
        summaries: list[CLISummary],
    ) -> None:
        self._entries = entries
        self._resolved = resolved
        self._summaries = summaries

    @classmethod
    def from_configs(cls, configs: list[CLImaxConfig]) -> "ToolIndex":
        """Build a searchable index from a list of loaded config objects.

        Args:
            configs: List of validated CLImaxConfig objects.

        Returns:
            A fully constructed ToolIndex ready for querying.
        """
        entries: list[ToolIndexEntry] = []
        resolved: dict[str, ResolvedTool] = {}
        summaries: list[CLISummary] = []

        for config in configs:
            summaries.append(CLISummary.from_config(config))

            for tool_def in config.tools:
                if tool_def.name in resolved:
                    logger.warning(
                        "Duplicate tool name [bold]%s[/bold] in index — overwriting",
                        tool_def.name,
                        extra={"markup": True},
                    )

                entry = ToolIndexEntry(
                    tool_name=tool_def.name,
                    description=tool_def.description,
                    cli_name=config.name,
                    category=config.category,
                    tags=list(config.tags),
                    input_schema=build_input_schema(tool_def.args),
                )
                entries.append(entry)
                resolved[tool_def.name] = ResolvedTool(
                    # model_dump() ensures compatibility when module is reloaded (e.g. in tests)
                    tool=tool_def.model_dump(),
                    base_command=config.command,
                    env=dict(config.env),
                    working_dir=config.working_dir,
                )

        # Deduplicate entries: keep last occurrence of each tool name
        seen: set[str] = set()
        deduped: list[ToolIndexEntry] = []
        for entry in reversed(entries):
            if entry.tool_name not in seen:
                seen.add(entry.tool_name)
                deduped.append(entry)
        deduped.reverse()

        return cls(deduped, resolved, summaries)

    def search(
        self,
        query: str | None = None,
        category: str | None = None,
        cli: str | None = None,
        limit: int = 10,
    ) -> list[ToolIndexEntry]:
        """Search the index with optional filters.

        Args:
            query: Case-insensitive substring matched against tool name,
                description, CLI name, category, and tags.
            category: Case-insensitive exact match against config category.
            cli: Case-insensitive exact match against config name.
            limit: Maximum number of results to return.

        Returns:
            Matching entries in insertion order, up to ``limit``.
        """
        if limit <= 0:
            return []

        query_lower = query.lower() if query else None
        category_lower = category.lower() if category else None
        cli_lower = cli.lower() if cli else None

        results: list[ToolIndexEntry] = []
        for entry in self._entries:
            if query_lower and query_lower not in entry._search_text:
                continue
            if category_lower:
                if not entry.category or entry.category.lower() != category_lower:
                    continue
            if cli_lower and entry.cli_name.lower() != cli_lower:
                continue
            results.append(entry)
            if len(results) >= limit:
                break
        return results

    def summary(self) -> list[CLISummary]:
        """Get a high-level overview of all loaded CLIs.

        Returns:
            One CLISummary per loaded config, in config load order.
        """
        return list(self._summaries)

    def get(self, tool_name: str) -> ResolvedTool | None:
        """Retrieve a tool by exact name for execution.

        Args:
            tool_name: Exact tool name to look up.

        Returns:
            The ResolvedTool if found, None otherwise.
        """
        return self._resolved.get(tool_name)


# ---------------------------------------------------------------------------
# YAML → Config
# ---------------------------------------------------------------------------

def _resolve_config(name_or_path: str | Path) -> Path:
    """Resolve a config name or path to an actual file path.

    If the string contains '/' or ends with '.yaml'/'.yml', treat as a file path.
    Otherwise, look up a bundled config by name in CONFIGS_DIR.
    """
    s = str(name_or_path)
    if "/" in s or s.endswith(".yaml") or s.endswith(".yml"):
        return Path(s)
    bundled = CONFIGS_DIR / f"{s}.yaml"
    if bundled.exists():
        return bundled
    return Path(s)


def load_config(path: str | Path) -> CLImaxConfig:
    """Load and validate a YAML config file."""
    raw = _resolve_config(path).read_text()
    data = yaml.safe_load(raw)
    return CLImaxConfig(**data)


def load_configs(paths: list[str | Path]) -> tuple[str, dict[str, ResolvedTool], list[CLImaxConfig]]:
    """
    Load one or more YAML configs and merge their tools.

    Returns (server_name, tool_map, configs) where tool_map maps
    tool name → ResolvedTool with the correct base command, and
    configs is the list of loaded CLImaxConfig objects.
    """
    tool_map: dict[str, ResolvedTool] = {}
    names: list[str] = []
    configs: list[CLImaxConfig] = []

    for path in paths:
        config = load_config(path)
        configs.append(config)
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
                global_args=config.global_args,
            )

    # Server name: use the single config name, or combine them
    server_name = names[0] if len(names) == 1 else "climax"

    logger.info(
        "Server [bold]%s[/bold] ready with %d tools",
        server_name, len(tool_map),
        extra={"markup": True},
    )

    return server_name, tool_map, configs


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


def validate_tool_args(
    args: dict[str, Any],
    tool_def: ToolDef,
) -> tuple[dict[str, Any], list[str]]:
    """Validate and coerce climax_call arguments against ToolArg definitions.

    Returns (coerced_args, error_messages). Empty error list = valid.
    """
    errors: list[str] = []
    coerced = dict(args)
    known_args = {a.name: a for a in tool_def.args}

    # Check required args
    for arg_def in tool_def.args:
        if arg_def.required and arg_def.name not in args:
            errors.append(f"Missing required argument '{arg_def.name}'")

    # Type coercion and enum validation for provided args
    for arg_name, value in list(coerced.items()):
        if arg_name not in known_args:
            # Extra keys silently ignored
            continue

        arg_def = known_args[arg_name]

        # Type coercion (check bool before int since bool is a subclass of int)
        if arg_def.type == ArgType.boolean and not isinstance(value, bool):
            if isinstance(value, str):
                if value.lower() == "true":
                    coerced[arg_name] = True
                elif value.lower() == "false":
                    coerced[arg_name] = False
                else:
                    errors.append(
                        f"Argument '{arg_name}': cannot convert '{value}' to boolean"
                    )
                    continue
            elif isinstance(value, int):
                coerced[arg_name] = bool(value)
            else:
                errors.append(
                    f"Argument '{arg_name}': cannot convert '{value}' to boolean"
                )
                continue
        elif arg_def.type == ArgType.integer and not isinstance(value, int):
            try:
                coerced[arg_name] = int(value)
            except (ValueError, TypeError):
                errors.append(
                    f"Argument '{arg_name}': cannot convert '{value}' to integer"
                )
                continue
        elif arg_def.type == ArgType.integer and isinstance(value, bool):
            coerced[arg_name] = int(value)
        elif arg_def.type == ArgType.number and not isinstance(value, (int, float)):
            try:
                coerced[arg_name] = float(value)
            except (ValueError, TypeError):
                errors.append(
                    f"Argument '{arg_name}': cannot convert '{value}' to number"
                )
                continue
        elif arg_def.type == ArgType.number and isinstance(value, bool):
            coerced[arg_name] = float(value)
        elif arg_def.type == ArgType.string and not isinstance(value, str):
            coerced[arg_name] = str(value)

        # Enum validation
        if arg_def.enum and coerced.get(arg_name) is not None:
            str_value = str(coerced[arg_name])
            if str_value not in arg_def.enum:
                errors.append(
                    f"Argument '{arg_name}' must be one of: {', '.join(arg_def.enum)}"
                )

    return coerced, errors


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
    global_args: list[ToolArg] | None = None,
) -> list[str]:
    """
    Build a subprocess-safe command list from the base command,
    tool subcommand, and provided arguments.
    """
    # Start with base command (split to handle e.g. "python -m myapp")
    # Expand ~ and $HOME so configs can use portable paths
    cmd = os.path.expandvars(os.path.expanduser(base_cmd)).split()

    # Add subcommand parts
    if tool_def.command:
        cmd.extend(tool_def.command.split())

    # First pass: positional args (in definition order)
    for arg_def in tool_def.args:
        if arg_def.cwd or arg_def.stdin:
            continue
        if arg_def.positional and arg_def.name in arguments:
            cmd.append(str(arguments[arg_def.name]))

    # Second pass: flag args
    for arg_def in tool_def.args:
        if arg_def.positional or arg_def.cwd or arg_def.stdin:
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

    # Third pass: global args (config-level args appended to every tool)
    for ga in global_args or []:
        if ga.default is None:
            continue
        raw = str(ga.default)
        resolved_val = os.path.expandvars(raw)
        # If still contains $ after expansion → env var unset → skip
        if resolved_val == raw and "$" in raw:
            continue
        if not resolved_val:
            continue

        flag = ga.flag
        if not flag:
            flag = f"--{ga.name.replace('_', '-')}"

        if ga.type == ArgType.boolean:
            if resolved_val in ("true", "True", "1"):
                cmd.append(flag)
        elif flag.endswith("="):
            cmd.append(f"{flag}{resolved_val}")
        else:
            cmd.append(flag)
            cmd.append(resolved_val)

    return cmd


# ---------------------------------------------------------------------------
# Execute CLI command
# ---------------------------------------------------------------------------

async def run_command(
    cmd: list[str],
    env: dict[str, str] | None = None,
    working_dir: str | None = None,
    timeout: float = 30.0,
    stdin_data: str | None = None,
) -> tuple[int, str, str]:
    """Run a command asynchronously and return (returncode, stdout, stderr)."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    try:
        logger.debug("Spawning: %s (cwd=%s)", cmd[0], working_dir or "<inherited>")
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE if stdin_data else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=full_env,
            cwd=working_dir,
        )
        logger.debug("Process started (pid=%s)", proc.pid)
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=stdin_data.encode("utf-8") if stdin_data else None),
            timeout=timeout,
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
# Approval dialogs
# ---------------------------------------------------------------------------

def _requires_approval(
    tool_def: ToolDef,
    approval_config: ApprovalConfig | None,
    tool_policy: ToolPolicy | None,
) -> bool:
    """Determine if a tool call requires user approval."""
    if approval_config is None:
        return False

    # Per-tool override in ToolPolicy takes highest precedence
    if tool_policy is not None and tool_policy.require_approval is not None:
        return tool_policy.require_approval

    # Per-tool override in approval.tools
    if tool_def.name in approval_config.tools:
        return approval_config.tools[tool_def.name]

    # Fall back to global level
    level = approval_config.global_level
    if level == ApprovalLevel.none:
        return False
    if level == ApprovalLevel.all:
        return True
    if level == ApprovalLevel.destructive:
        return tool_def.risk == RiskLevel.destructive
    if level == ApprovalLevel.write:
        return tool_def.risk in (RiskLevel.write, RiskLevel.destructive)

    return False


async def _run_resolves(
    tool_def: ToolDef,
    arguments: dict[str, Any],
    base_command: str,
    env: dict[str, str] | None = None,
    working_dir: str | None = None,
) -> dict[str, str]:
    """Run resolve commands and return {var_name: resolved_value} dict."""
    resolved_vars: dict[str, str] = {}

    for var_name, resolve_cfg in tool_def.resolve.items():
        # Build the resolve command using the base command + resolve subcommand
        cmd_parts = os.path.expandvars(os.path.expanduser(base_command)).split()
        if resolve_cfg.command:
            cmd_parts.extend(resolve_cfg.command.split())

        # Substitute argument values into resolve args and add as flags
        for arg_name, arg_template in resolve_cfg.args.items():
            try:
                value = arg_template.format_map(arguments)
            except KeyError:
                continue
            flag = f"--{arg_name.replace('_', '-')}"
            cmd_parts.extend([flag, value])

        returncode, stdout, stderr = await run_command(
            cmd_parts,
            env=env,
            working_dir=working_dir,
            timeout=resolve_cfg.timeout,
        )

        if returncode == 0 and stdout.strip():
            resolved_vars[var_name] = stdout.strip()
        else:
            resolved_vars[var_name] = f"<unresolved:{var_name}>"
            logger.warning(
                "Resolve for %s failed (exit %d): %s",
                var_name, returncode, stderr.strip()[:100],
            )

    return resolved_vars


async def _show_approval_dialog(
    message: str,
    headless: HeadlessPolicy = HeadlessPolicy.deny,
) -> bool:
    """Show a native confirmation dialog. Returns True if approved."""
    system = platform.system()

    if system == "Darwin":
        result = await _dialog_macos(message)
        if result is not None:
            return result
    elif system == "Linux":
        result = await _dialog_linux(message)
        if result is not None:
            return result
    elif system == "Windows":
        result = await _dialog_windows(message)
        if result is not None:
            return result

    return await _dialog_terminal(message, headless)


async def _dialog_macos(message: str) -> bool | None:
    """macOS native dialog via osascript. Returns None if osascript unavailable."""
    escaped = message.replace("\\", "\\\\").replace('"', '\\"')
    script = (
        f'display dialog "{escaped}" '
        f'buttons {{"Deny", "Approve"}} default button "Deny" '
        f'with title "CLImax Approval"'
    )
    try:
        proc = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=120.0)
        # osascript returns non-zero if user clicks Cancel/Deny
        if proc.returncode != 0:
            return False
        return "Approve" in stdout.decode()
    except (asyncio.TimeoutError, FileNotFoundError, OSError):
        return None


async def _dialog_linux(message: str) -> bool | None:
    """Linux dialog via zenity or kdialog. Returns None if neither available."""
    import shutil
    if shutil.which("zenity"):
        try:
            proc = await asyncio.create_subprocess_exec(
                "zenity", "--question", "--title=CLImax Approval",
                f"--text={message}", "--ok-label=Approve", "--cancel-label=Deny",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=120.0)
            return proc.returncode == 0
        except (asyncio.TimeoutError, OSError):
            pass

    if shutil.which("kdialog"):
        try:
            proc = await asyncio.create_subprocess_exec(
                "kdialog", "--title", "CLImax Approval",
                "--yesno", message, "--yes-label", "Approve", "--no-label", "Deny",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=120.0)
            return proc.returncode == 0
        except (asyncio.TimeoutError, OSError):
            pass

    return None


async def _dialog_windows(message: str) -> bool | None:
    """Windows dialog via PowerShell. Returns None if PowerShell unavailable."""
    escaped = message.replace("'", "''")
    ps_script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        f"$result = [System.Windows.Forms.MessageBox]::Show('{escaped}', 'CLImax Approval', "
        "[System.Windows.Forms.MessageBoxButtons]::YesNo, "
        "[System.Windows.Forms.MessageBoxIcon]::Warning); "
        "if ($result -eq 'Yes') { exit 0 } else { exit 1 }"
    )
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell", "-NoProfile", "-Command", ps_script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=120.0)
        return proc.returncode == 0
    except (asyncio.TimeoutError, FileNotFoundError, OSError):
        return None


async def _dialog_terminal(
    message: str,
    headless: HeadlessPolicy = HeadlessPolicy.deny,
) -> bool:
    """Prompt on stderr, read from /dev/tty (bypasses MCP's stdin)."""
    import sys

    def _prompt() -> bool:
        sys.stderr.write(f"\n{'=' * 60}\n")
        sys.stderr.write("CLImax Approval Required\n")
        sys.stderr.write(f"{'=' * 60}\n")
        sys.stderr.write(f"{message}\n\n")
        sys.stderr.write("Approve? [y/N] ")
        sys.stderr.flush()
        try:
            with open("/dev/tty", "r") as tty:
                answer = tty.readline().strip().lower()
        except OSError:
            sys.stderr.write("(no TTY available, auto-")
            if headless == HeadlessPolicy.approve:
                sys.stderr.write("approving)\n")
                return True
            sys.stderr.write("denying)\n")
            return False
        return answer in ("y", "yes")

    return await asyncio.to_thread(_prompt)


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

def create_server(
    server_name: str,
    tool_map: dict[str, ResolvedTool],
    executor: ExecutorConfig | None = None,
    index: "ToolIndex | None" = None,
    classic: bool = False,
    policy: PolicyConfig | None = None,
) -> Server:
    """Create and configure the MCP server from resolved tools."""

    server = Server(server_name)

    # Meta-tool definitions for default (progressive discovery) mode
    _META_TOOLS = [
        types.Tool(
            name="climax_search",
            description="Search for available CLI tools by keyword, category, or CLI name. Call with no filters to get a summary of all available CLIs.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search keyword (matched against tool name, description, CLI name, category, tags)",
                    },
                    "category": {
                        "type": "string",
                        "description": "Filter by CLI category (exact match, case-insensitive)",
                    },
                    "cli": {
                        "type": "string",
                        "description": "Filter by CLI name (exact match, case-insensitive)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 50)",
                        "default": 50,
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Number of results to skip for pagination (default: 0). Use with limit to page through large result sets.",
                        "default": 0,
                    },
                },
            },
        ),
        types.Tool(
            name="climax_call",
            description="Execute a CLI tool by name. Use climax_search first to discover available tools and their argument schemas.",
            inputSchema={
                "type": "object",
                "properties": {
                    "tool_name": {
                        "type": "string",
                        "description": "The exact name of the tool to execute (as returned by climax_search)",
                    },
                    "args": {
                        "type": "object",
                        "description": "Arguments to pass to the tool (see tool's input_schema from climax_search)",
                    },
                },
                "required": ["tool_name"],
            },
        ),
    ]

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        """Return tools based on mode: meta-tools (default) or all individual tools (classic)."""
        if not classic and index is not None:
            return list(_META_TOOLS)

        # Classic mode: return all individual tools
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

    async def _execute_tool(
        resolved: ResolvedTool,
        arguments: dict[str, Any],
        executor_cfg: ExecutorConfig | None = executor,
    ) -> list[types.TextContent]:
        """Execute a resolved tool with validated arguments.

        Shared by both classic call_tool and climax_call meta-tool.
        """
        # Validate arguments against policy constraints
        if resolved.arg_constraints:
            errors = validate_arguments(arguments, resolved.tool, resolved.arg_constraints)
            if errors:
                error_text = "Policy validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
                logger.warning("Policy rejected %s: %s", resolved.tool.name, "; ".join(errors))
                return [types.TextContent(type="text", text=error_text)]

        cmd = build_command(resolved.base_command, resolved.tool, arguments, global_args=resolved.global_args)

        # Extract stdin arg value if present
        stdin_data = None
        for arg_def in resolved.tool.args:
            if arg_def.stdin and arg_def.name in arguments:
                stdin_data = str(arguments[arg_def.name])
                break

        # Extract cwd arg value if present
        working_dir = resolved.working_dir
        for arg_def in resolved.tool.args:
            if arg_def.cwd and arg_def.name in arguments:
                working_dir = arguments[arg_def.name]
                break

        # Prepend docker prefix if executor is docker type
        if executor_cfg and executor_cfg.type == ExecutorType.docker:
            cmd = build_docker_prefix(executor_cfg) + cmd

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

        # --- Approval check ---
        if policy is not None:
            tool_policy_entry = policy.tools.get(resolved.tool.name)
            if _requires_approval(resolved.tool, policy.approval, tool_policy_entry):
                # Build confirmation message
                if resolved.tool.confirm_message:
                    template_vars: dict[str, Any] = dict(arguments)
                    if resolved.tool.resolve:
                        resolved_vars = await _run_resolves(
                            resolved.tool, arguments,
                            resolved.base_command, resolved.env or None, working_dir,
                        )
                        template_vars.update(resolved_vars)
                    try:
                        message = resolved.tool.confirm_message.format_map(template_vars)
                    except KeyError as exc:
                        message = f"Approve execution of {resolved.tool.name}? (template error: {exc})"
                else:
                    message = f"Approve execution: {cmd_display}"

                logger.info("🔒 Approval required for %s", resolved.tool.name)
                approved = await _show_approval_dialog(message, policy.approval.headless)

                if not approved:
                    logger.warning("✗ User denied %s", resolved.tool.name)
                    return [types.TextContent(
                        type="text",
                        text=f"Tool execution denied by user: {resolved.tool.name}",
                    )]
                logger.info("✓ User approved %s", resolved.tool.name)

        t0 = time.monotonic()

        tool_timeout = resolved.tool.timeout or 30.0
        returncode, stdout, stderr = await run_command(
            cmd,
            env=resolved.env or None,
            working_dir=working_dir,
            timeout=tool_timeout,
            stdin_data=stdin_data,
        )

        elapsed = time.monotonic() - t0

        if returncode == 0:
            logger.info(
                "✓ %s completed in %.1fs (%d bytes)",
                resolved.tool.name, elapsed, len(stdout),
            )
        else:
            logger.warning(
                "✗ %s failed (exit %d) in %.1fs",
                resolved.tool.name, returncode, elapsed,
            )
            if stderr.strip():
                logger.debug("stderr: %s", stderr.strip()[:200])

        # Build response — only include stderr on failure to avoid
        # noisy warnings (e.g. Obsidian CLI) confusing the agent
        parts = []
        if stdout.strip():
            parts.append(stdout.strip())
        if returncode != 0:
            if stderr.strip():
                parts.append(f"[stderr]\n{stderr.strip()}")
            parts.append(f"[exit code: {returncode}]")

        text = "\n\n".join(parts) if parts else "(no output)"

        return [types.TextContent(type="text", text=text)]

    async def _handle_climax_search(arguments: dict[str, Any]) -> list[types.TextContent]:
        """Handle climax_search meta-tool calls."""
        query = arguments.get("query")
        category = arguments.get("category")
        cli = arguments.get("cli")
        try:
            limit = int(arguments.get("limit", 50))
        except (ValueError, TypeError):
            limit = 50
        try:
            offset = int(arguments.get("offset", 0))
        except (ValueError, TypeError):
            offset = 0

        # Summary mode when all filter params are absent
        if query is None and category is None and cli is None:
            summaries = index.summary()[offset : offset + limit]
            response = {
                "mode": "summary",
                "summary": [s.model_dump() for s in summaries],
            }
        else:
            # Filter results to only include policy-allowed tools
            all_matches = index.search(query=query, category=category, cli=cli, limit=sys.maxsize)
            filtered = [e for e in all_matches if e.tool_name in tool_map]
            total = len(filtered)
            page = filtered[offset : offset + limit]
            response = {
                "mode": "search",
                "results": [e.model_dump() for e in page],
                "total_matches": total,
                "offset": offset,
                "returned": len(page),
                "has_more": (offset + len(page)) < total,
            }

        return [types.TextContent(type="text", text=json.dumps(response))]

    async def _handle_climax_call(arguments: dict[str, Any]) -> list[types.TextContent]:
        """Handle climax_call meta-tool calls."""
        tool_name = arguments.get("tool_name")
        if tool_name is None:
            return [types.TextContent(type="text", text="Missing required argument 'tool_name'")]

        call_args = arguments.get("args") or {}

        # Resolve from tool_map (policy-filtered) to enforce policy constraints
        resolved = tool_map.get(tool_name)
        if not resolved:
            available = sorted(tool_map.keys())
            return [types.TextContent(
                type="text",
                text=f"Unknown tool: {tool_name}. Available tools: {', '.join(available)}",
            )]

        # Validate and coerce arguments
        coerced_args, errors = validate_tool_args(call_args, resolved.tool)
        if errors:
            error_text = "Argument validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            return [types.TextContent(type="text", text=error_text)]

        return await _execute_tool(resolved, coerced_args)

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[types.TextContent]:
        """Execute the CLI command for the given tool."""
        arguments = arguments or {}

        # Default mode: dispatch to meta-tool handlers
        if not classic and index is not None:
            if name == "climax_search":
                return await _handle_climax_search(arguments)
            elif name == "climax_call":
                return await _handle_climax_call(arguments)
            else:
                logger.warning("Unknown tool called: %s", name)
                return [types.TextContent(
                    type="text",
                    text=f"Unknown tool: {name}. Available tools: climax_search, climax_call",
                )]

        # Classic mode: dispatch to individual tools
        resolved = tool_map.get(name)
        if not resolved:
            logger.warning("Unknown tool called: %s", name)
            available = sorted(tool_map.keys())
            return [types.TextContent(
                type="text",
                text=f"Unknown tool: {name}. Available tools: {', '.join(available)}",
            )]

        return await _execute_tool(resolved, arguments)

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
            binary = os.path.expandvars(os.path.expanduser(config.command)).split()[0]
            if not shutil.which(binary):
                console.print(f"    [yellow]⚠ '{binary}' not found on PATH[/yellow]")

            valid += 1
        except ValidationError as e:
            console.print(f"  [red]✗[/red] {path}")
            for err in e.errors():
                loc = " → ".join(str(part) for part in err["loc"])
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
                loc = " → ".join(str(part) for part in err["loc"])
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
    """List all tools from the given config files, or list bundled configs."""
    console = console or Console()

    if not args.configs:
        # No configs given — list available bundled config names
        names = sorted(p.stem for p in CONFIGS_DIR.glob("*.yaml"))
        if names:
            console.print("[bold]Bundled configs:[/bold]\n")
            for name in names:
                console.print(f"  {name}")
        else:
            console.print("[dim]No bundled configs found.[/dim]")
        return 0

    try:
        server_name, tool_map, _configs = load_configs(args.configs)
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


def cmd_skill(args, console: Console | None = None) -> int:
    """Print, locate, or install the CLImax skill file."""
    console = console or Console()
    skill_path = Path(__file__).parent / "skill" / "SKILL.md"

    if not skill_path.exists():
        console.print("[red]Skill file not found:[/red] expected at " + str(skill_path))
        return 1

    if getattr(args, "path", False):
        console.print(str(skill_path.resolve()))
        return 0

    if getattr(args, "install", False):
        dest = Path.cwd() / ".claude" / "commands" / "climax-config.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(skill_path, dest)
        console.print(f"Installed to {dest}")
        return 0

    # Default: print contents
    console.print(skill_path.read_text(), highlight=False)
    return 0


class _RequestLoggingMiddleware:
    """ASGI middleware that logs MCP JSON-RPC requests to stdout with Rich formatting."""

    # Soft colors: dim timestamp, accent on method/tool, muted params
    _STYLE_TS = "dim"
    _STYLE_METHOD = "bold cyan"
    _STYLE_TOOL = "bold green"
    _STYLE_ID = "dim"
    _STYLE_PARAMS = "dim white"
    _STYLE_WARN = "yellow"

    def __init__(self, app):
        self.app = app
        self._out = Console(file=sys.stdout, highlight=False)

    def _log(self, method: str, req_id: Any = "-", **fields: str) -> None:
        ts = time.strftime("%H:%M:%S")
        parts = [
            f"[{self._STYLE_TS}]{ts}[/]",
            f"[{self._STYLE_METHOD}]{method}[/]",
            f"[{self._STYLE_ID}]id={req_id}[/]",
        ]
        for key, val in fields.items():
            if key == "tool":
                parts.append(f"[{self._STYLE_TOOL}]{val}[/]")
            else:
                parts.append(f"[{self._STYLE_PARAMS}]{key}={val}[/]")
        self._out.print("  ".join(parts))

    def _log_warn(self, message: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self._out.print(f"[{self._STYLE_TS}]{ts}[/]  [{self._STYLE_WARN}]{message}[/]")

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] == "POST":
            # Peek at the first receive to capture the body for logging
            first = await receive()
            if first["type"] == "http.request":
                body = first.get("body", b"")
                try:
                    payload = json.loads(body)
                    method = payload.get("method", "?")
                    params = payload.get("params", {})
                    req_id = payload.get("id", "-")
                    if method == "tools/call":
                        tool_name = params.get("name", "?")
                        tool_args = json.dumps(params.get("arguments", {}), separators=(",", ":"))
                        self._log(method, req_id, tool=tool_name, args=tool_args)
                    elif method in ("initialize", "ping"):
                        self._log(method, req_id)
                    else:
                        self._log(method, req_id, params=json.dumps(params, separators=(",", ":")))
                except (json.JSONDecodeError, AttributeError):
                    self._log_warn(f"POST {scope.get('path', '?')} (non-JSON body)")

                # Replay the already-consumed message
                replayed = False

                async def replay_receive():
                    nonlocal replayed
                    if not replayed:
                        replayed = True
                        return first
                    return await receive()

                await self.app(scope, replay_receive, send)
                return

        await self.app(scope, receive, send)


def _resolve_run_configs(args) -> list[str]:
    """Resolve bundled names + --config paths into a config path list.

    Raises SystemExit with a helpful message if no configs are specified
    or if a bundled name is not recognized.
    """
    bundled_names = getattr(args, "bundled", None) or []
    config_files = getattr(args, "config", None) or []

    # Also support legacy args.configs for backward compat with tests
    if not bundled_names and not config_files and hasattr(args, "configs"):
        return args.configs

    if not bundled_names and not config_files:
        available = _available_bundled()
        console.print("[red]No configs specified.[/red] Provide bundled names and/or --config paths.\n")
        console.print("[bold]Available bundled configs:[/bold]")
        for name in available:
            console.print(f"  {name}")
        console.print(f"\n[dim]Example: climax run {available[0]}[/dim]")
        sys.exit(1)

    # Validate bundled names
    available = _available_bundled()
    resolved: list[str] = []
    for name in bundled_names:
        if name not in available:
            console.print(
                f"[red]Unknown bundled config:[/red] '{name}'\n"
                f"[bold]Available:[/bold] {', '.join(available)}"
            )
            sys.exit(1)
        resolved.append(name)

    resolved.extend(config_files)
    return resolved


def cmd_run(args) -> None:
    """Start the MCP server."""
    logger.setLevel(getattr(logging, args.log_level))

    server_name, tool_map, configs = load_configs(_resolve_run_configs(args))

    executor = None
    policy_path = getattr(args, "policy", None)
    if policy_path:
        policy = load_policy(policy_path)
        tool_map = apply_policy(tool_map, policy)
        executor = policy.executor
    else:
        # Default policy: all tools enabled, write/destructive require approval
        policy = PolicyConfig(default=DefaultPolicy.enabled)

    # CLI override for headless approval behavior
    if policy and getattr(args, "headless_approve", False):
        policy.approval.headless = HeadlessPolicy.approve

    is_classic = getattr(args, "classic", False)
    index = ToolIndex.from_configs(configs)
    server = create_server(server_name, tool_map, executor=executor, index=index, classic=is_classic, policy=policy)

    transport = getattr(args, "transport", "stdio")

    if transport == "stdio":
        async def run():
            async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
                await server.run(
                    read_stream,
                    write_stream,
                    server.create_initialization_options(),
                )

        asyncio.run(run())

    elif transport == "sse":
        from mcp.server.sse import SseServerTransport
        from starlette.applications import Starlette
        from starlette.routing import Mount, Route
        import uvicorn

        host = getattr(args, "host", "127.0.0.1")
        port = getattr(args, "port", 8000)
        sse = SseServerTransport("/messages/")

        async def handle_sse(request):
            async with sse.connect_sse(request.scope, request.receive, request._send) as (read_stream, write_stream):
                await server.run(
                    read_stream,
                    write_stream,
                    server.create_initialization_options(),
                )

        starlette_app = Starlette(routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ])
        app = _RequestLoggingMiddleware(starlette_app)
        console.print(f"CLImax SSE server listening on http://{host}:{port}/sse")
        uvicorn.run(app, host=host, port=port, log_level=args.log_level.lower())

    elif transport == "streamable-http":
        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
        from starlette.applications import Starlette
        from starlette.routing import Mount
        import uvicorn

        host = getattr(args, "host", "127.0.0.1")
        port = getattr(args, "port", 8000)

        session_manager = StreamableHTTPSessionManager(app=server)

        async def run():
            starlette_app = Starlette(routes=[
                Mount("/mcp", app=session_manager.handle_request),
            ])
            app = _RequestLoggingMiddleware(starlette_app)
            config = uvicorn.Config(app, host=host, port=port, log_level=args.log_level.lower())
            uv_server = uvicorn.Server(config)
            console.print(f"CLImax Streamable HTTP server listening on http://{host}:{port}/mcp")
            await uv_server.serve()

        asyncio.run(run())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _add_policy_arg(parser):
    """Add the --policy argument to a parser."""
    parser.add_argument("--policy", metavar="POLICY", default=None, help="Policy YAML file")


def _available_bundled() -> list[str]:
    """Return sorted list of available bundled config names."""
    return sorted(p.stem for p in CONFIGS_DIR.glob("*.yaml"))


def _build_run_parser(parser=None):
    """Build the 'run' argument parser (reused for backward compat)."""
    import argparse

    if parser is None:
        parser = argparse.ArgumentParser()
    parser.add_argument("bundled", nargs="*", metavar="NAME", help="Bundled config names (e.g. git, docker, obsidian)")
    parser.add_argument("--config", action="append", default=[], metavar="FILE", help="Custom config file path(s) — can be repeated")
    _add_policy_arg(parser)
    parser.add_argument("--headless-approve", action="store_true", default=False, help="Auto-approve tool calls when no GUI/TTY is available (overrides policy headless=deny)")
    parser.add_argument("--classic", action="store_true", default=False, help="Classic mode: register all tools directly")
    parser.add_argument("--transport", choices=["stdio", "sse", "streamable-http"], default="stdio", help="MCP transport (default: stdio)")
    parser.add_argument("--host", default="127.0.0.1", help="Host for HTTP transports (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port for HTTP transports (default: 8000)")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="WARNING", help="Logging level")
    return parser


def cmd_test_dialog(args=None, console: Console | None = None) -> int:
    """Show a synthetic approval dialog so the user can verify their system shows it."""
    console = console or globals()["console"]
    message = "This is a test approval dialog from CLImax.\nIf you can see this, approvals will work on your system."

    console.print("\n[bold]CLImax Approval Dialog Test[/bold]")
    console.print("Attempting to show a native approval dialog...\n")

    system = platform.system()
    console.print(f"  Platform: [cyan]{system}[/cyan]")

    async def _test():
        # Try platform-specific dialog first
        result = None
        method = "unknown"

        if system == "Darwin":
            result = await _dialog_macos(message)
            if result is not None:
                method = "macOS (osascript)"
        elif system == "Linux":
            result = await _dialog_linux(message)
            if result is not None:
                import shutil
                method = "zenity" if shutil.which("zenity") else "kdialog"
        elif system == "Windows":
            result = await _dialog_windows(message)
            if result is not None:
                method = "Windows (PowerShell)"

        if result is not None:
            return result, method

        # Fall back to terminal
        result = await _dialog_terminal(message, HeadlessPolicy.deny)
        return result, "terminal (/dev/tty)"

    result, method = asyncio.run(_test())

    console.print(f"  Method:   [cyan]{method}[/cyan]")

    if result:
        console.print("\n  [bold green]✓ You clicked Approve[/bold green] — approval dialogs are working!")
    else:
        console.print("\n  [bold yellow]✗ You clicked Deny (or dialog was unavailable)[/bold yellow]")
        console.print("    This is expected if you wanted to test the deny path.")
        console.print("    If you never saw a dialog, ensure zenity/kdialog is installed (Linux)")
        console.print("    or that osascript is available (macOS).")

    return 0


def main():
    import argparse

    SUBCOMMANDS = {"validate", "list", "run", "skill", "test-dialog"}

    # Check if the first positional arg is a known subcommand
    argv = sys.argv[1:]
    first_positional = next((a for a in argv if not a.startswith("-")), None)

    if first_positional not in SUBCOMMANDS:
        # Shorthand: climax git [--transport sse ...]  →  climax run git [...]
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
    p_list.add_argument("configs", nargs="*", metavar="CONFIG")
    _add_policy_arg(p_list)

    # --- run ---
    _build_run_parser(subparsers.add_parser("run", help="Start MCP server"))

    # --- test-dialog ---
    subparsers.add_parser("test-dialog", help="Test that approval dialogs display on your system")

    # --- skill ---
    p_skill = subparsers.add_parser("skill", help="Print or install the CLImax skill file")
    skill_group = p_skill.add_mutually_exclusive_group()
    skill_group.add_argument("--path", action="store_true", help="Print the path to SKILL.md")
    skill_group.add_argument("--install", action="store_true", help="Install to .claude/commands/climax-config.md")

    args = parser.parse_args(argv)

    if args.subcommand == "validate":
        sys.exit(cmd_validate(args))
    elif args.subcommand == "list":
        sys.exit(cmd_list(args))
    elif args.subcommand == "run":
        cmd_run(args)
    elif args.subcommand == "skill":
        sys.exit(cmd_skill(args))
    elif args.subcommand == "test-dialog":
        sys.exit(cmd_test_dialog(args))


if __name__ == "__main__":
    main()
