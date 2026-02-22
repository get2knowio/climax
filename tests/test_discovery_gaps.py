"""Tests filling gaps in meta-tool coverage: unknown-tool enrichment and error parity."""

import json
from unittest.mock import patch, AsyncMock

import pytest

import mcp.types as types

from climax import (
    ArgType,
    CLImaxConfig,
    ResolvedTool,
    ToolArg,
    ToolDef,
    ToolIndex,
    create_server,
)


# ---------------------------------------------------------------------------
# Helpers (duplicated from test_meta_tools.py)
# ---------------------------------------------------------------------------


def _unwrap(result):
    """Unwrap ServerResult wrapper if present."""
    return result.root if hasattr(result, "root") else result


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


async def _call_tool(server, name, arguments=None):
    """Invoke call_tool on a server and return the unwrapped result."""
    handlers = server.request_handlers
    request = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(name=name, arguments=arguments or {}),
    )
    return _unwrap(await handlers[types.CallToolRequest](request))


# ---------------------------------------------------------------------------
# Shared fixture configs
# ---------------------------------------------------------------------------


def _build_minimal_multi_config():
    """Build a multi-CLI config set with multiple tools for testing.

    Returns two configs (git-tools with 3 tools, docker-tools with 2 tools).
    """
    git_config = CLImaxConfig(
        name="git-tools",
        command="git",
        description="Git version control",
        category="vcs",
        tags=["version-control"],
        tools=[
            ToolDef(
                name="git_commit",
                description="Record changes to the repository",
                command="commit",
                args=[ToolArg(name="message", type=ArgType.string, required=True, flag="-m")],
            ),
            ToolDef(name="git_log", description="Show commit logs", command="log"),
            ToolDef(name="git_status", description="Show working tree status", command="status"),
        ],
    )
    docker_config = CLImaxConfig(
        name="docker-tools",
        command="docker",
        description="Container management",
        category="containers",
        tags=["docker"],
        tools=[
            ToolDef(name="docker_ps", description="List containers", command="ps"),
            ToolDef(name="docker_images", description="List images", command="images"),
        ],
    )
    return [git_config, docker_config]


def _make_default_server(configs=None):
    """Create a server in default (meta-tool/discovery) mode."""
    configs = configs or _build_minimal_multi_config()
    tool_map = _build_tool_map(configs)
    index = ToolIndex.from_configs(configs)
    server = create_server("test-default", tool_map, index=index, classic=False)
    return server, tool_map


def _make_classic_server(configs=None):
    """Create a server in classic mode."""
    configs = configs or _build_minimal_multi_config()
    tool_map = _build_tool_map(configs)
    index = ToolIndex.from_configs(configs)
    server = create_server("test-classic", tool_map, index=index, classic=True)
    return server, tool_map


# ---------------------------------------------------------------------------
# T003: TestClimaxCallUnknownToolEnriched (FR-019)
# ---------------------------------------------------------------------------


class TestClimaxCallUnknownToolEnriched:
    """Verify that climax_call with an unknown tool name returns an error
    message that includes the sorted list of available tool names."""

    async def test_unknown_tool_error_lists_available_tools(self):
        """Call climax_call with unknown tool_name; response contains 'Unknown tool',
        'Available tools', and every real tool name from the fixture."""
        server, tool_map = _make_default_server()

        result = await _call_tool(
            server, "climax_call", {"tool_name": "nonexistent_tool"}
        )
        text = result.content[0].text

        assert "Unknown tool: nonexistent_tool" in text
        assert "Available tools:" in text

        # Every tool in the map must appear in the response
        for name in tool_map:
            assert name in text, f"Expected tool '{name}' to appear in error message"

        # Verify alphabetical order: extract the portion after "Available tools: "
        after_prefix = text.split("Available tools: ", 1)[1]
        listed_names = [n.strip() for n in after_prefix.split(",")]
        assert listed_names == sorted(listed_names)

    async def test_unknown_tool_error_with_single_tool(self):
        """When only one tool exists, the error still lists it."""
        config = CLImaxConfig(
            name="solo",
            command="echo",
            description="Solo tool",
            tools=[
                ToolDef(name="solo_echo", description="Echo something", command="echo"),
            ],
        )
        server, tool_map = _make_default_server(configs=[config])

        result = await _call_tool(
            server, "climax_call", {"tool_name": "missing"}
        )
        text = result.content[0].text

        assert "Unknown tool: missing" in text
        assert "solo_echo" in text

    async def test_unknown_tool_error_format(self):
        """Verify exact format: 'Unknown tool: {name}. Available tools: {comma-separated sorted}'."""
        server, tool_map = _make_default_server()
        sorted_names = sorted(tool_map.keys())
        expected = f"Unknown tool: nope. Available tools: {', '.join(sorted_names)}"

        result = await _call_tool(
            server, "climax_call", {"tool_name": "nope"}
        )
        text = result.content[0].text

        assert text == expected


# ---------------------------------------------------------------------------
# T004: TestTimeoutErrorParity (FR-021)
# ---------------------------------------------------------------------------


class TestTimeoutErrorParity:
    """Verify that climax_call and classic-mode call_tool produce equivalent
    output for non-zero exits, timeout results, and successful runs."""

    @pytest.fixture
    def paired_servers(self):
        configs = _build_minimal_multi_config()
        default_server, _ = _make_default_server(configs)
        classic_server, _ = _make_classic_server(configs)
        return default_server, classic_server

    async def test_nonzero_exit_same_in_both_modes(self, paired_servers):
        """Mock run_command returning exit-code 1; both modes produce the same text."""
        default_server, classic_server = paired_servers

        with patch("climax.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (1, "", "error output")

            # Default mode via climax_call
            default_result = await _call_tool(
                default_server,
                "climax_call",
                {"tool_name": "git_status"},
            )

            # Classic mode via direct call_tool
            classic_result = await _call_tool(
                classic_server,
                "git_status",
                {},
            )

        default_text = default_result.content[0].text
        classic_text = classic_result.content[0].text

        assert default_text == classic_text
        assert "error output" in default_text
        assert "[exit code: 1]" in default_text

    async def test_timeout_error_same_in_both_modes(self, paired_servers):
        """Mock run_command returning a timeout result; both modes produce the same text."""
        default_server, classic_server = paired_servers

        with patch("climax.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (-1, "", "Command timed out after 30s")

            default_result = await _call_tool(
                default_server,
                "climax_call",
                {"tool_name": "git_status"},
            )

            classic_result = await _call_tool(
                classic_server,
                "git_status",
                {},
            )

        default_text = default_result.content[0].text
        classic_text = classic_result.content[0].text

        assert default_text == classic_text
        assert "timed out" in default_text.lower()
        assert "[exit code: -1]" in default_text

    async def test_success_output_same_in_both_modes(self, paired_servers):
        """Mock run_command returning success; both modes produce the same text."""
        default_server, classic_server = paired_servers

        with patch("climax.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "output\n", "")

            default_result = await _call_tool(
                default_server,
                "climax_call",
                {"tool_name": "git_status"},
            )

            classic_result = await _call_tool(
                classic_server,
                "git_status",
                {},
            )

        default_text = default_result.content[0].text
        classic_text = classic_result.content[0].text

        assert default_text == classic_text
        assert "output" in default_text


# ---------------------------------------------------------------------------
# T005: Edge case tests for climax_search and climax_call (FR-019, FR-020)
# ---------------------------------------------------------------------------


class TestClimaxSearchEdgeCases:
    """Verify edge cases in climax_search: empty-string query vs absent query."""

    async def test_empty_string_query_returns_search_mode_with_all_tools(self):
        """climax_search with query="" returns search mode and all tools,
        since empty string matches everything."""
        server, tool_map = _make_default_server()

        result = await _call_tool(server, "climax_search", {"query": ""})
        text = result.content[0].text
        response = json.loads(text)

        assert response["mode"] == "search"
        result_names = {r["tool_name"] for r in response["results"]}
        assert result_names == set(tool_map.keys())

    async def test_absent_query_returns_summary_mode(self):
        """climax_search with {} (no query) returns summary mode."""
        server, _ = _make_default_server()

        result = await _call_tool(server, "climax_search", {})
        text = result.content[0].text
        response = json.loads(text)

        assert response["mode"] == "summary"
        assert "summary" in response
        # Should have summaries for each CLI config
        cli_names = {s["name"] for s in response["summary"]}
        assert "git-tools" in cli_names
        assert "docker-tools" in cli_names


class TestClimaxCallEdgeCases:
    """Verify edge cases in climax_call: casing sensitivity and missing arguments (FR-019)."""

    async def test_tool_name_case_mismatch_returns_unknown_tool_error(self):
        """climax_call with wrong-case tool name (e.g. 'Git_Status') returns
        unknown-tool error listing available tools."""
        server, tool_map = _make_default_server()

        result = await _call_tool(
            server, "climax_call", {"tool_name": "Git_Status"}
        )
        text = result.content[0].text

        assert "Unknown tool: Git_Status" in text
        assert "Available tools:" in text
        # The correctly-cased tool name should appear in the available list
        assert "git_status" in text

    async def test_missing_tool_name_argument(self):
        """climax_call with {} (no tool_name) returns a validation error.

        MCP validates the input schema (which marks tool_name as required)
        before the handler runs, so the error comes from schema validation
        rather than the handler's own check."""
        server, _ = _make_default_server()

        result = await _call_tool(server, "climax_call", {})
        text = result.content[0].text

        assert "tool_name" in text
        assert "required" in text.lower()
