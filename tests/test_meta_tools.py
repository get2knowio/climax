"""Tests for MCP meta-tools: climax_search, climax_call, default/classic modes, and validate_tool_args."""

import json
from unittest.mock import patch, AsyncMock

import pytest

import mcp.types as types

from climax import (
    ArgConstraint,
    ArgType,
    CLImaxConfig,
    ResolvedTool,
    ToolArg,
    ToolDef,
    ToolIndex,
    apply_policy,
    create_server,
    DefaultPolicy,
    PolicyConfig,
    ToolPolicy,
    validate_tool_args,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unwrap(result):
    """Unwrap ServerResult wrapper if present."""
    return result.root if hasattr(result, "root") else result


def _build_multi_config():
    """Build a multi-CLI config set for testing meta-tools.

    Returns two configs (git-tools with 6 tools, docker-tools with 5 tools)
    for a total of 11 tools across 2 CLIs with different categories.
    """
    git_config = CLImaxConfig(
        name="git-tools",
        command="git",
        description="Git version control",
        category="vcs",
        tags=["version-control", "commits"],
        tools=[
            ToolDef(
                name="git_commit",
                description="Record changes to the repository",
                command="commit",
                args=[ToolArg(name="message", type=ArgType.string, required=True, flag="-m")],
            ),
            ToolDef(name="git_branch", description="List or create branches", command="branch"),
            ToolDef(name="git_status", description="Show working tree status", command="status"),
            ToolDef(name="git_log", description="Show commit logs", command="log"),
            ToolDef(name="git_diff", description="Show changes between commits", command="diff"),
            ToolDef(name="git_push", description="Update remote refs", command="push"),
        ],
    )
    docker_config = CLImaxConfig(
        name="docker-tools",
        command="docker",
        description="Container management",
        category="containers",
        tags=["docker", "containerization"],
        tools=[
            ToolDef(name="docker_ps", description="List containers", command="ps"),
            ToolDef(
                name="docker_build",
                description="Build an image",
                command="build",
                args=[
                    ToolArg(name="tag", type=ArgType.string, flag="-t"),
                    ToolArg(name="context", type=ArgType.string, positional=True, required=True),
                ],
            ),
            ToolDef(name="docker_run", description="Run a container", command="run"),
            ToolDef(name="docker_stop", description="Stop running containers", command="stop"),
            ToolDef(name="docker_images", description="List images", command="images"),
        ],
    )
    return [git_config, docker_config]


def _build_tool_map(configs):
    """Build a tool_map from a list of CLImaxConfig objects."""
    tool_map = {}
    for config in configs:
        for tool_def in config.tools:
            tool_map[tool_def.name] = ResolvedTool(
                tool=tool_def,
                base_command=config.command,
                env=dict(config.env),
                working_dir=config.working_dir,
            )
    return tool_map


def _make_default_server():
    """Create a server in default (meta-tool) mode with multi-config setup."""
    configs = _build_multi_config()
    tool_map = _build_tool_map(configs)
    index = ToolIndex.from_configs(configs)
    server = create_server("test-meta", tool_map, index=index, classic=False)
    return server, index


def _make_classic_server():
    """Create a server in classic mode with multi-config setup."""
    configs = _build_multi_config()
    tool_map = _build_tool_map(configs)
    index = ToolIndex.from_configs(configs)
    server = create_server("test-classic", tool_map, index=index, classic=True)
    return server, index


async def _list_tools(server):
    """Invoke list_tools on a server and return the unwrapped result."""
    handlers = server.request_handlers
    request = types.ListToolsRequest(method="tools/list")
    return _unwrap(await handlers[types.ListToolsRequest](request))


async def _call_tool(server, name, arguments=None):
    """Invoke call_tool on a server and return the unwrapped result."""
    handlers = server.request_handlers
    request = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(name=name, arguments=arguments or {}),
    )
    return _unwrap(await handlers[types.CallToolRequest](request))


# ---------------------------------------------------------------------------
# T006: climax_search tests
# ---------------------------------------------------------------------------


class TestClimaxSearch:
    """Tests for the climax_search meta-tool."""

    async def test_search_by_query_returns_matching_tools(self):
        """Search by query 'commit' returns matching tools with full schema."""
        server, _ = _make_default_server()
        result = await _call_tool(server, "climax_search", {"query": "commit"})

        data = json.loads(result.content[0].text)
        assert data["mode"] == "search"
        assert len(data["results"]) > 0

        tool_names = [r["tool_name"] for r in data["results"]]
        assert "git_commit" in tool_names

        # Verify full schema is included
        commit_entry = next(r for r in data["results"] if r["tool_name"] == "git_commit")
        assert "input_schema" in commit_entry
        assert "properties" in commit_entry["input_schema"]
        assert "message" in commit_entry["input_schema"]["properties"]

    async def test_filter_by_category(self):
        """Filter by category returns only matching category."""
        server, _ = _make_default_server()
        result = await _call_tool(server, "climax_search", {"category": "containers"})

        data = json.loads(result.content[0].text)
        assert data["mode"] == "search"
        assert len(data["results"]) > 0

        # All results should be from the containers category
        for entry in data["results"]:
            assert entry["category"] == "containers"

        tool_names = [r["tool_name"] for r in data["results"]]
        assert "docker_ps" in tool_names
        assert "git_commit" not in tool_names

    async def test_filter_by_cli_name(self):
        """Filter by cli name returns only that CLI's tools."""
        server, _ = _make_default_server()
        result = await _call_tool(server, "climax_search", {"cli": "git-tools"})

        data = json.loads(result.content[0].text)
        assert data["mode"] == "search"
        assert len(data["results"]) > 0

        # All results should be from git-tools
        for entry in data["results"]:
            assert entry["cli_name"] == "git-tools"

        tool_names = [r["tool_name"] for r in data["results"]]
        assert "docker_ps" not in tool_names

    async def test_combined_query_and_category_uses_and_logic(self):
        """Combined query+category uses AND logic."""
        server, _ = _make_default_server()
        # "list" appears in docker_ps ("List containers") and docker_images ("List images")
        # but also in git_branch ("List or create branches")
        # With category="containers", only docker tools should match
        result = await _call_tool(
            server, "climax_search", {"query": "list", "category": "containers"}
        )

        data = json.loads(result.content[0].text)
        assert data["mode"] == "search"

        for entry in data["results"]:
            assert entry["category"] == "containers"
        tool_names = [r["tool_name"] for r in data["results"]]
        assert "git_branch" not in tool_names

    async def test_limit_caps_results(self):
        """Limit caps results."""
        server, _ = _make_default_server()
        result = await _call_tool(server, "climax_search", {"cli": "git-tools", "limit": 2})

        data = json.loads(result.content[0].text)
        assert data["mode"] == "search"
        assert len(data["results"]) == 2

    async def test_no_filter_returns_summary(self):
        """No-filter call returns summary with CLI names/tool counts/categories."""
        server, _ = _make_default_server()
        result = await _call_tool(server, "climax_search", {})

        data = json.loads(result.content[0].text)
        assert data["mode"] == "summary"
        assert len(data["summary"]) == 2

        cli_names = {s["name"] for s in data["summary"]}
        assert cli_names == {"git-tools", "docker-tools"}

        # Verify summary includes tool_count and category
        for s in data["summary"]:
            assert "tool_count" in s
            assert "category" in s
            assert s["tool_count"] > 0

        git_summary = next(s for s in data["summary"] if s["name"] == "git-tools")
        assert git_summary["tool_count"] == 6
        assert git_summary["category"] == "vcs"

        docker_summary = next(s for s in data["summary"] if s["name"] == "docker-tools")
        assert docker_summary["tool_count"] == 5
        assert docker_summary["category"] == "containers"

    async def test_no_match_returns_empty_results(self):
        """No-match query returns empty results list (not error)."""
        server, _ = _make_default_server()
        result = await _call_tool(
            server, "climax_search", {"query": "zzz_nonexistent_xyz"}
        )

        data = json.loads(result.content[0].text)
        assert data["mode"] == "search"
        assert data["results"] == []


# ---------------------------------------------------------------------------
# T008: climax_call tests
# ---------------------------------------------------------------------------


class TestClimaxCall:
    """Tests for the climax_call meta-tool."""

    async def test_call_tool_no_args_returns_stdout(self):
        """Call tool with no args returns stdout."""
        server, _ = _make_default_server()

        with patch("climax.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "On branch main\n", "")
            result = await _call_tool(
                server, "climax_call", {"tool_name": "git_status"}
            )

        assert "On branch main" in result.content[0].text
        mock_run.assert_called_once()

    async def test_call_tool_with_valid_args(self):
        """Call tool with valid args passes them correctly."""
        server, _ = _make_default_server()

        with patch("climax.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "committed\n", "")
            result = await _call_tool(
                server,
                "climax_call",
                {"tool_name": "git_commit", "args": {"message": "initial commit"}},
            )

        assert "committed" in result.content[0].text
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "-m" in cmd
        assert "initial commit" in cmd

    async def test_missing_required_arg_returns_validation_error(self):
        """Missing required arg returns validation error with arg name."""
        server, _ = _make_default_server()

        result = await _call_tool(
            server, "climax_call", {"tool_name": "git_commit", "args": {}}
        )

        text = result.content[0].text
        assert "Argument validation failed" in text
        assert "message" in text

    async def test_invalid_enum_value_returns_error(self):
        """Invalid enum value returns error listing valid values."""
        # Build a config with an enum arg
        config = CLImaxConfig(
            name="fmt-tools",
            command="fmt",
            description="Formatter",
            category="dev",
            tools=[
                ToolDef(
                    name="fmt_output",
                    description="Format output",
                    command="output",
                    args=[
                        ToolArg(
                            name="format",
                            type=ArgType.string,
                            flag="--format",
                            enum=["json", "table", "csv"],
                        ),
                    ],
                ),
            ],
        )
        configs = [config]
        tool_map = _build_tool_map(configs)
        index = ToolIndex.from_configs(configs)
        server = create_server("test-enum", tool_map, index=index, classic=False)

        result = await _call_tool(
            server, "climax_call", {"tool_name": "fmt_output", "args": {"format": "xml"}}
        )

        text = result.content[0].text
        assert "Argument validation failed" in text
        assert "json" in text
        assert "table" in text
        assert "csv" in text

    async def test_unknown_tool_name_returns_error(self):
        """Unknown tool_name returns 'Unknown tool' error."""
        server, _ = _make_default_server()

        result = await _call_tool(
            server, "climax_call", {"tool_name": "nonexistent_tool"}
        )

        assert "Unknown tool: nonexistent_tool" in result.content[0].text

    async def test_type_coercion_string_to_int(self):
        """Type coercion (string '42' -> int) works."""
        config = CLImaxConfig(
            name="num-tools",
            command="num",
            description="Numeric tools",
            tools=[
                ToolDef(
                    name="num_count",
                    description="Count items",
                    command="count",
                    args=[ToolArg(name="n", type=ArgType.integer, flag="-n")],
                ),
            ],
        )
        configs = [config]
        tool_map = _build_tool_map(configs)
        index = ToolIndex.from_configs(configs)
        server = create_server("test-coerce", tool_map, index=index, classic=False)

        with patch("climax.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "42 items\n", "")
            result = await _call_tool(
                server, "climax_call", {"tool_name": "num_count", "args": {"n": "42"}}
            )

        assert "42 items" in result.content[0].text
        mock_run.assert_called_once()
        # Verify the coerced value was passed (as int, converted to str for CLI)
        cmd = mock_run.call_args[0][0]
        assert "-n" in cmd
        assert "42" in cmd

    async def test_incompatible_type_returns_error(self):
        """Incompatible type (string 'hello' for int) returns error."""
        config = CLImaxConfig(
            name="num-tools",
            command="num",
            description="Numeric tools",
            tools=[
                ToolDef(
                    name="num_count",
                    description="Count items",
                    command="count",
                    args=[ToolArg(name="n", type=ArgType.integer, flag="-n")],
                ),
            ],
        )
        configs = [config]
        tool_map = _build_tool_map(configs)
        index = ToolIndex.from_configs(configs)
        server = create_server("test-bad-type", tool_map, index=index, classic=False)

        result = await _call_tool(
            server, "climax_call", {"tool_name": "num_count", "args": {"n": "hello"}}
        )

        text = result.content[0].text
        assert "Argument validation failed" in text
        assert "n" in text
        assert "integer" in text.lower() or "convert" in text.lower()

    async def test_extra_keys_in_args_silently_ignored(self):
        """Extra keys in args are silently ignored."""
        server, _ = _make_default_server()

        with patch("climax.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "ok\n", "")
            result = await _call_tool(
                server,
                "climax_call",
                {
                    "tool_name": "git_status",
                    "args": {"extra_key": "should_be_ignored", "another": 123},
                },
            )

        assert "ok" in result.content[0].text
        mock_run.assert_called_once()

    async def test_args_none_with_no_required_args_succeeds(self):
        """args=None with no required args succeeds."""
        server, _ = _make_default_server()

        with patch("climax.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "branch list\n", "")
            # Do not include "args" key at all -- handler defaults to {}
            result = await _call_tool(
                server, "climax_call", {"tool_name": "git_branch"}
            )

        assert "branch list" in result.content[0].text
        mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# T011: Default mode tests
# ---------------------------------------------------------------------------


class TestDefaultMode:
    """Tests for default (progressive discovery) mode."""

    async def test_list_tools_returns_exactly_two_meta_tools(self):
        """list_tools returns exactly 2 tools named climax_search and climax_call when config has 10+ tools."""
        server, _ = _make_default_server()
        result = await _list_tools(server)

        assert len(result.tools) == 2
        tool_names = {t.name for t in result.tools}
        assert tool_names == {"climax_search", "climax_call"}

    async def test_all_configured_tools_accessible_via_climax_call(self):
        """All configured tools are still accessible via climax_call."""
        server, index = _make_default_server()

        # Gather all tool names from the index
        configs = _build_multi_config()
        all_tool_names = []
        for config in configs:
            for tool_def in config.tools:
                all_tool_names.append(tool_def.name)

        assert len(all_tool_names) == 11  # 6 git + 5 docker

        # Each tool should be resolvable via the index
        for name in all_tool_names:
            resolved = index.get(name)
            assert resolved is not None, f"Tool '{name}' not found in index"

        # And calling via climax_call should not return "Unknown tool"
        with patch("climax.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "output\n", "")
            for name in all_tool_names:
                result = await _call_tool(
                    server, "climax_call", {"tool_name": name}
                )
                text = result.content[0].text
                assert "Unknown tool" not in text, f"Tool '{name}' was not found via climax_call"

    async def test_calling_individual_tool_directly_returns_unknown(self):
        """Calling an individual tool name directly returns 'Unknown tool' in default mode."""
        server, _ = _make_default_server()

        with patch("climax.run_command", new_callable=AsyncMock):
            result = await _call_tool(server, "git_status", {})

        assert "Unknown tool: git_status" in result.content[0].text


# ---------------------------------------------------------------------------
# T013: Classic mode tests
# ---------------------------------------------------------------------------


class TestClassicMode:
    """Tests for classic mode."""

    async def test_classic_list_tools_returns_all_individual_tools(self):
        """With classic=True, list_tools returns all individual tools."""
        server, _ = _make_classic_server()
        result = await _list_tools(server)

        tool_names = {t.name for t in result.tools}

        # All 11 individual tools should be present
        configs = _build_multi_config()
        expected_names = set()
        for config in configs:
            for tool_def in config.tools:
                expected_names.add(tool_def.name)

        assert tool_names == expected_names
        assert len(result.tools) == 11

    async def test_classic_meta_tools_do_not_appear(self):
        """climax_search and climax_call do NOT appear in classic list_tools."""
        server, _ = _make_classic_server()
        result = await _list_tools(server)

        tool_names = {t.name for t in result.tools}
        assert "climax_search" not in tool_names
        assert "climax_call" not in tool_names

    async def test_classic_mode_index_still_built(self):
        """ToolIndex is still built internally in classic mode (verify by checking index is not None)."""
        configs = _build_multi_config()
        index = ToolIndex.from_configs(configs)

        # The index should be valid and non-empty
        assert index is not None
        assert len(index.summary()) == 2
        assert index.get("git_commit") is not None
        assert index.get("docker_ps") is not None


# ---------------------------------------------------------------------------
# TestValidateToolArgs: unit tests for validate_tool_args
# ---------------------------------------------------------------------------


class TestValidateToolArgs:
    """Unit tests for the validate_tool_args function."""

    def test_valid_args_no_errors(self):
        """Valid args produce no errors."""
        tool_def = ToolDef(
            name="test",
            description="test",
            args=[
                ToolArg(name="name", type=ArgType.string, required=True),
                ToolArg(name="count", type=ArgType.integer, flag="-n"),
            ],
        )
        coerced, errors = validate_tool_args({"name": "hello", "count": 5}, tool_def)
        assert errors == []
        assert coerced["name"] == "hello"
        assert coerced["count"] == 5

    def test_missing_required_arg(self):
        """Missing required arg produces an error mentioning the arg name."""
        tool_def = ToolDef(
            name="test",
            description="test",
            args=[ToolArg(name="message", type=ArgType.string, required=True)],
        )
        coerced, errors = validate_tool_args({}, tool_def)
        assert len(errors) == 1
        assert "message" in errors[0]
        assert "required" in errors[0].lower() or "Missing" in errors[0]

    def test_string_to_int_coercion(self):
        """String '42' is coerced to int 42."""
        tool_def = ToolDef(
            name="test",
            description="test",
            args=[ToolArg(name="n", type=ArgType.integer)],
        )
        coerced, errors = validate_tool_args({"n": "42"}, tool_def)
        assert errors == []
        assert coerced["n"] == 42
        assert isinstance(coerced["n"], int)

    def test_string_to_float_coercion(self):
        """String '3.14' is coerced to float."""
        tool_def = ToolDef(
            name="test",
            description="test",
            args=[ToolArg(name="val", type=ArgType.number)],
        )
        coerced, errors = validate_tool_args({"val": "3.14"}, tool_def)
        assert errors == []
        assert coerced["val"] == pytest.approx(3.14)

    def test_incompatible_int_coercion(self):
        """Non-numeric string for integer arg produces error."""
        tool_def = ToolDef(
            name="test",
            description="test",
            args=[ToolArg(name="n", type=ArgType.integer)],
        )
        coerced, errors = validate_tool_args({"n": "hello"}, tool_def)
        assert len(errors) == 1
        assert "n" in errors[0]

    def test_incompatible_number_coercion(self):
        """Non-numeric string for number arg produces error."""
        tool_def = ToolDef(
            name="test",
            description="test",
            args=[ToolArg(name="val", type=ArgType.number)],
        )
        coerced, errors = validate_tool_args({"val": "abc"}, tool_def)
        assert len(errors) == 1
        assert "val" in errors[0]

    def test_boolean_string_true(self):
        """String 'true' is coerced to bool True."""
        tool_def = ToolDef(
            name="test",
            description="test",
            args=[ToolArg(name="verbose", type=ArgType.boolean)],
        )
        coerced, errors = validate_tool_args({"verbose": "true"}, tool_def)
        assert errors == []
        assert coerced["verbose"] is True

    def test_boolean_string_false(self):
        """String 'false' is coerced to bool False."""
        tool_def = ToolDef(
            name="test",
            description="test",
            args=[ToolArg(name="verbose", type=ArgType.boolean)],
        )
        coerced, errors = validate_tool_args({"verbose": "false"}, tool_def)
        assert errors == []
        assert coerced["verbose"] is False

    def test_boolean_invalid_string(self):
        """Non-boolean string for boolean arg produces error."""
        tool_def = ToolDef(
            name="test",
            description="test",
            args=[ToolArg(name="verbose", type=ArgType.boolean)],
        )
        coerced, errors = validate_tool_args({"verbose": "maybe"}, tool_def)
        assert len(errors) == 1
        assert "verbose" in errors[0]

    def test_enum_valid_value(self):
        """Valid enum value passes."""
        tool_def = ToolDef(
            name="test",
            description="test",
            args=[ToolArg(name="fmt", type=ArgType.string, enum=["json", "csv"])],
        )
        coerced, errors = validate_tool_args({"fmt": "json"}, tool_def)
        assert errors == []
        assert coerced["fmt"] == "json"

    def test_enum_invalid_value(self):
        """Invalid enum value produces error listing valid options."""
        tool_def = ToolDef(
            name="test",
            description="test",
            args=[ToolArg(name="fmt", type=ArgType.string, enum=["json", "csv"])],
        )
        coerced, errors = validate_tool_args({"fmt": "xml"}, tool_def)
        assert len(errors) == 1
        assert "json" in errors[0]
        assert "csv" in errors[0]

    def test_extra_keys_ignored(self):
        """Extra keys not in the tool definition are kept but produce no errors."""
        tool_def = ToolDef(
            name="test",
            description="test",
            args=[ToolArg(name="name", type=ArgType.string)],
        )
        coerced, errors = validate_tool_args(
            {"name": "hello", "bogus": "ignored"}, tool_def
        )
        assert errors == []
        assert coerced["name"] == "hello"
        # Extra key is still in coerced dict (silently ignored, not removed)
        assert coerced["bogus"] == "ignored"

    def test_empty_args_no_required(self):
        """Empty args with no required args produces no errors."""
        tool_def = ToolDef(
            name="test",
            description="test",
            args=[ToolArg(name="opt", type=ArgType.string)],
        )
        coerced, errors = validate_tool_args({}, tool_def)
        assert errors == []

    def test_non_string_coerced_to_string(self):
        """Non-string value for a string arg is coerced to string."""
        tool_def = ToolDef(
            name="test",
            description="test",
            args=[ToolArg(name="label", type=ArgType.string)],
        )
        coerced, errors = validate_tool_args({"label": 42}, tool_def)
        assert errors == []
        assert coerced["label"] == "42"
        assert isinstance(coerced["label"], str)

    def test_multiple_errors_reported(self):
        """Multiple validation failures are all reported."""
        tool_def = ToolDef(
            name="test",
            description="test",
            args=[
                ToolArg(name="a", type=ArgType.string, required=True),
                ToolArg(name="b", type=ArgType.integer),
            ],
        )
        coerced, errors = validate_tool_args({"b": "notanumber"}, tool_def)
        assert len(errors) == 2
        error_text = " ".join(errors)
        assert "a" in error_text
        assert "b" in error_text

    def test_bool_true_coerced_to_int(self):
        """Boolean True for an integer arg is coerced to int 1."""
        tool_def = ToolDef(
            name="test",
            description="test",
            args=[ToolArg(name="n", type=ArgType.integer)],
        )
        coerced, errors = validate_tool_args({"n": True}, tool_def)
        assert errors == []
        assert coerced["n"] == 1
        assert type(coerced["n"]) is int

    def test_bool_false_coerced_to_int(self):
        """Boolean False for an integer arg is coerced to int 0."""
        tool_def = ToolDef(
            name="test",
            description="test",
            args=[ToolArg(name="n", type=ArgType.integer)],
        )
        coerced, errors = validate_tool_args({"n": False}, tool_def)
        assert errors == []
        assert coerced["n"] == 0
        assert type(coerced["n"]) is int

    def test_int_coerced_to_bool(self):
        """Integer 1 for a boolean arg is coerced to True."""
        tool_def = ToolDef(
            name="test",
            description="test",
            args=[ToolArg(name="verbose", type=ArgType.boolean)],
        )
        coerced, errors = validate_tool_args({"verbose": 1}, tool_def)
        assert errors == []
        assert coerced["verbose"] is True

    def test_int_zero_coerced_to_bool_false(self):
        """Integer 0 for a boolean arg is coerced to False."""
        tool_def = ToolDef(
            name="test",
            description="test",
            args=[ToolArg(name="verbose", type=ArgType.boolean)],
        )
        coerced, errors = validate_tool_args({"verbose": 0}, tool_def)
        assert errors == []
        assert coerced["verbose"] is False

    def test_non_string_non_int_for_bool_returns_error(self):
        """Non-string, non-int, non-bool value for boolean arg returns error."""
        tool_def = ToolDef(
            name="test",
            description="test",
            args=[ToolArg(name="verbose", type=ArgType.boolean)],
        )
        coerced, errors = validate_tool_args({"verbose": [1, 2, 3]}, tool_def)
        assert len(errors) == 1
        assert "verbose" in errors[0]


# ---------------------------------------------------------------------------
# Policy enforcement via climax_call in default mode
# ---------------------------------------------------------------------------


class TestClimaxCallPolicy:
    """Tests for policy enforcement through climax_call meta-tool."""

    async def test_policy_constraint_enforced_via_climax_call(self):
        """climax_call enforces policy arg constraints (pattern)."""
        config = CLImaxConfig(
            name="test-cli",
            command="echo",
            description="Test CLI",
            tools=[
                ToolDef(
                    name="test_echo",
                    description="Echo a message",
                    args=[ToolArg(name="message", type=ArgType.string, required=True, flag="-m")],
                ),
            ],
        )
        configs = [config]
        tool_map = _build_tool_map(configs)

        # Apply policy with pattern constraint
        policy = PolicyConfig(
            default=DefaultPolicy.enabled,
            tools={
                "test_echo": ToolPolicy(
                    args={"message": ArgConstraint(pattern=r"^hello.*")}
                )
            },
        )
        tool_map = apply_policy(tool_map, policy)

        index = ToolIndex.from_configs(configs)
        server = create_server("test-policy", tool_map, index=index, classic=False)

        # Valid pattern: should succeed
        with patch("climax.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "hello world\n", "")
            result = await _call_tool(
                server, "climax_call",
                {"tool_name": "test_echo", "args": {"message": "hello world"}},
            )
        assert "hello world" in result.content[0].text

        # Invalid pattern: should be rejected by policy
        result = await _call_tool(
            server, "climax_call",
            {"tool_name": "test_echo", "args": {"message": "goodbye"}},
        )
        assert "Policy validation failed" in result.content[0].text

    async def test_policy_disabled_tool_not_callable_via_climax_call(self):
        """Tools filtered out by policy are not callable via climax_call."""
        config = CLImaxConfig(
            name="test-cli",
            command="echo",
            description="Test CLI",
            tools=[
                ToolDef(name="allowed_tool", description="Allowed", command="allowed"),
                ToolDef(name="blocked_tool", description="Blocked", command="blocked"),
            ],
        )
        configs = [config]
        tool_map = _build_tool_map(configs)

        # Policy disables all tools except allowed_tool
        policy = PolicyConfig(
            default=DefaultPolicy.disabled,
            tools={"allowed_tool": ToolPolicy()},
        )
        tool_map = apply_policy(tool_map, policy)

        index = ToolIndex.from_configs(configs)
        server = create_server("test-policy", tool_map, index=index, classic=False)

        # blocked_tool should return "Unknown tool"
        result = await _call_tool(
            server, "climax_call", {"tool_name": "blocked_tool"}
        )
        assert "Unknown tool: blocked_tool" in result.content[0].text

    async def test_policy_filtered_search_excludes_blocked_tools(self):
        """climax_search only returns tools allowed by policy."""
        config = CLImaxConfig(
            name="test-cli",
            command="echo",
            description="Test CLI",
            category="test",
            tools=[
                ToolDef(name="allowed_tool", description="Allowed tool", command="allowed"),
                ToolDef(name="blocked_tool", description="Blocked tool", command="blocked"),
            ],
        )
        configs = [config]
        tool_map = _build_tool_map(configs)

        policy = PolicyConfig(
            default=DefaultPolicy.disabled,
            tools={"allowed_tool": ToolPolicy()},
        )
        tool_map = apply_policy(tool_map, policy)

        index = ToolIndex.from_configs(configs)
        server = create_server("test-policy", tool_map, index=index, classic=False)

        result = await _call_tool(
            server, "climax_search", {"cli": "test-cli"}
        )
        data = json.loads(result.content[0].text)
        tool_names = [r["tool_name"] for r in data["results"]]
        assert "allowed_tool" in tool_names
        assert "blocked_tool" not in tool_names


# ---------------------------------------------------------------------------
# Summary mode with explicit limit
# ---------------------------------------------------------------------------


class TestClimaxSearchEdgeCases:
    """Edge case tests for climax_search."""

    async def test_summary_mode_with_explicit_limit(self):
        """Calling climax_search with only limit returns summary mode capped at limit."""
        server, _ = _make_default_server()
        result = await _call_tool(server, "climax_search", {"limit": 1})

        data = json.loads(result.content[0].text)
        assert data["mode"] == "summary"
        assert len(data["summary"]) == 1

    async def test_summary_mode_no_args(self):
        """Calling climax_search with empty args returns summary mode."""
        server, _ = _make_default_server()
        result = await _call_tool(server, "climax_search", {})

        data = json.loads(result.content[0].text)
        assert data["mode"] == "summary"
        assert len(data["summary"]) == 2
