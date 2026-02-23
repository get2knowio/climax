"""Integration tests for progressive discovery with real YAML configurations.

Exercises the full MCP handler chain (list_tools, climax_search, climax_call)
against real configs loaded from the configs/ directory. All subprocess calls
are mocked — only the handler chain is tested.
"""

import json
from unittest.mock import patch, AsyncMock

import pytest

import mcp.types as types

from climax import (
    CLImaxConfig,
    ResolvedTool,
    ToolIndex,
    create_server,
    load_config,
)


# ---------------------------------------------------------------------------
# Helpers (duplicated per-file per contract)
# ---------------------------------------------------------------------------


def _unwrap(result):
    """Unwrap ServerResult wrapper if present."""
    return result.root if hasattr(result, "root") else result


def _build_tool_map(configs):
    """Build a tool_map from a list of CLImaxConfig objects.

    Uses model_dump() to avoid Pydantic model_type validation errors
    when configs are loaded from YAML (model identity can differ).
    """
    tool_map = {}
    for config in configs:
        for tool_def in config.tools:
            tool_map[tool_def.name] = ResolvedTool(
                tool=tool_def.model_dump(),
                base_command=config.command,
                env=dict(config.env),
                working_dir=config.working_dir,
            )
    return tool_map


async def _list_tools(server):
    handlers = server.request_handlers
    request = types.ListToolsRequest(method="tools/list")
    return _unwrap(await handlers[types.ListToolsRequest](request))


async def _call_tool(server, name, arguments=None):
    handlers = server.request_handlers
    request = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(name=name, arguments=arguments or {}),
    )
    return _unwrap(await handlers[types.CallToolRequest](request))


# ---------------------------------------------------------------------------
# Fixtures — load real configs from configs/ directory
# ---------------------------------------------------------------------------


@pytest.fixture
def real_configs():
    """Load real configs from the configs directory."""
    return [
        load_config("git"),
        load_config("docker"),
        load_config("claude"),
    ]


@pytest.fixture
def default_server(real_configs):
    """Server in default (discovery) mode with real configs."""
    tool_map = _build_tool_map(real_configs)
    index = ToolIndex.from_configs(real_configs)
    return create_server("test-integration", tool_map, index=index, classic=False)


@pytest.fixture
def classic_server(real_configs):
    """Server in classic mode with real configs."""
    tool_map = _build_tool_map(real_configs)
    index = ToolIndex.from_configs(real_configs)
    return create_server("test-integration-classic", tool_map, index=index, classic=True)


# ---------------------------------------------------------------------------
# T005: TestDiscoveryModeIntegration
# ---------------------------------------------------------------------------


class TestDiscoveryModeIntegration:
    """Integration tests for default (progressive discovery) mode with real configs."""

    async def test_default_mode_exposes_exactly_two_meta_tools(self, default_server):
        """FR-022: Default mode exposes exactly 2 meta-tools: climax_search and climax_call."""
        result = await _list_tools(default_server)

        assert len(result.tools) == 2
        tool_names = {t.name for t in result.tools}
        assert tool_names == {"climax_search", "climax_call"}

    async def test_search_version_control_surfaces_git(self, default_server):
        """FR-024: Domain term search surfaces relevant CLIs.

        git.yaml has category='vcs' and tag 'version-control',
        so searching for 'version-control' should surface git tools.
        The search is a substring match against the pre-computed search text,
        so the hyphenated tag form is required.
        """
        result = await _call_tool(
            default_server, "climax_search", {"query": "version-control", "limit": 50}
        )

        data = json.loads(result.content[0].text)
        assert data["mode"] == "search"
        assert len(data["results"]) > 0

        cli_names = {r["cli_name"] for r in data["results"]}
        assert "git-tools" in cli_names, (
            f"Expected 'git-tools' in search results, got CLIs: {cli_names}"
        )
        # docker-tools and claude-tools should NOT appear (no 'version-control' tag)
        assert "docker-tools" not in cli_names
        assert "claude-tools" not in cli_names

    async def test_cli_filter_returns_only_that_cli_tools(self, default_server, real_configs):
        """FR-025: CLI name filter returns only that CLI's tools.

        Filter by cli='git-tools' (the name field in git.yaml) and verify
        all returned entries have cli_name == 'git-tools'.
        """
        result = await _call_tool(
            default_server, "climax_search", {"cli": "git-tools", "limit": 50}
        )

        data = json.loads(result.content[0].text)
        assert data["mode"] == "search"
        assert len(data["results"]) > 0

        for entry in data["results"]:
            assert entry["cli_name"] == "git-tools", (
                f"Expected cli_name='git-tools', got '{entry['cli_name']}'"
            )

        # Derive expected tool names from the loaded git config
        git_config = next(c for c in real_configs if c.name == "git-tools")
        expected_git_tools = {t.name for t in git_config.tools}
        tool_names = {r["tool_name"] for r in data["results"]}
        assert tool_names == expected_git_tools

    async def test_search_text_not_in_serialized_output(self, default_server):
        """_search_text internal field must not leak to MCP clients."""
        result = await _call_tool(
            default_server, "climax_search", {"query": "git", "limit": 50}
        )

        data = json.loads(result.content[0].text)
        assert data["mode"] == "search"
        assert len(data["results"]) > 0

        for entry in data["results"]:
            assert "_search_text" not in entry, (
                f"Internal field '_search_text' leaked in result for {entry['tool_name']}"
            )


# ---------------------------------------------------------------------------
# T006: TestClassicModeIntegration
# ---------------------------------------------------------------------------


class TestClassicModeIntegration:
    """Integration tests for classic mode with real configs."""

    async def test_classic_mode_exposes_all_individual_tools(self, classic_server):
        """FR-023: Classic flag exposes all individual tools instead of meta-tools."""
        result = await _list_tools(classic_server)

        tool_names = {t.name for t in result.tools}

        # Verify we get individual tool names, not meta-tools
        assert "git_status" in tool_names
        assert "docker_ps" in tool_names
        assert "claude_ask" in tool_names

    async def test_classic_mode_tool_count_matches_config_total(self, classic_server, real_configs):
        """Total tools count matches sum of tools across all loaded configs."""
        result = await _list_tools(classic_server)

        expected_count = sum(len(config.tools) for config in real_configs)
        assert len(result.tools) == expected_count, (
            f"Expected {expected_count} tools, got {len(result.tools)}"
        )

    async def test_classic_no_meta_tools(self, classic_server):
        """Verify climax_search and climax_call are NOT in the classic tool list."""
        result = await _list_tools(classic_server)

        tool_names = {t.name for t in result.tools}
        assert "climax_search" not in tool_names
        assert "climax_call" not in tool_names


# ---------------------------------------------------------------------------
# T007: TestOutputEquivalence
# ---------------------------------------------------------------------------


class TestOutputEquivalence:
    """Tests that climax_call output matches classic-mode call_tool output."""

    async def test_climax_call_output_matches_classic_call_tool(self, real_configs):
        """FR-026: climax_call output matches classic-mode call_tool for the same tool.

        Pick git_status (no required args), mock run_command to return fixed output,
        and verify both modes produce the same response text.
        """
        tool_map = _build_tool_map(real_configs)
        index = ToolIndex.from_configs(real_configs)

        discovery_server = create_server(
            "test-equiv-discovery", tool_map, index=index, classic=False,
        )
        classic_server = create_server(
            "test-equiv-classic", tool_map, index=index, classic=True,
        )

        mock_output = (0, "mock output\n", "")

        # Call via discovery mode (climax_call)
        with patch("climax.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_output
            discovery_result = await _call_tool(
                discovery_server,
                "climax_call",
                {"tool_name": "git_status", "args": {}},
            )

        # Call via classic mode (direct call_tool)
        with patch("climax.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_output
            classic_result = await _call_tool(classic_server, "git_status", {})

        discovery_text = discovery_result.content[0].text
        classic_text = classic_result.content[0].text

        assert discovery_text == classic_text, (
            f"Output mismatch:\n  discovery: {discovery_text!r}\n  classic: {classic_text!r}"
        )

    async def test_error_output_matches_between_modes(self, real_configs):
        """Mock run_command to return non-zero exit, verify both modes produce equivalent error output."""
        tool_map = _build_tool_map(real_configs)
        index = ToolIndex.from_configs(real_configs)

        discovery_server = create_server(
            "test-equiv-err-discovery", tool_map, index=index, classic=False,
        )
        classic_server = create_server(
            "test-equiv-err-classic", tool_map, index=index, classic=True,
        )

        mock_error_output = (1, "", "fatal: not a git repository\n")

        # Call via discovery mode (climax_call)
        with patch("climax.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_error_output
            discovery_result = await _call_tool(
                discovery_server,
                "climax_call",
                {"tool_name": "git_status", "args": {}},
            )

        # Call via classic mode (direct call_tool)
        with patch("climax.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_error_output
            classic_result = await _call_tool(classic_server, "git_status", {})

        discovery_text = discovery_result.content[0].text
        classic_text = classic_result.content[0].text

        assert discovery_text == classic_text, (
            f"Error output mismatch:\n  discovery: {discovery_text!r}\n  classic: {classic_text!r}"
        )
        # Verify it actually contains the error markers
        assert "fatal: not a git repository" in discovery_text
        assert "exit code: 1" in discovery_text
