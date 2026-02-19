"""End-to-end tests with policy filtering and constraints.

Uses real subprocess execution (echo/printf) to test the full pipeline
with policy applied.
"""

import textwrap
from pathlib import Path

import pytest

import mcp.types as types

from climax import (
    apply_policy,
    create_server,
    load_configs,
    load_policy,
    PolicyConfig,
    DefaultPolicy,
    ToolPolicy,
    ArgConstraint,
)


COREUTILS_YAML = Path(__file__).parent.parent / "examples" / "coreutils.yaml"


def _unwrap(result):
    """Unwrap ServerResult wrapper if present."""
    return result.root if hasattr(result, "root") else result


async def _call_tool(server, name, arguments=None):
    handlers = server.request_handlers
    request = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(name=name, arguments=arguments),
    )
    return _unwrap(await handlers[types.CallToolRequest](request))


async def _list_tools(server):
    handlers = server.request_handlers
    request = types.ListToolsRequest(method="tools/list")
    return _unwrap(await handlers[types.ListToolsRequest](request))


class TestE2EPolicyFiltering:
    """E2E: policy filters out tools, remaining tools still work."""

    @pytest.fixture
    def server(self):
        server_name, tool_map = load_configs([COREUTILS_YAML])
        # Allow only coreutils_echo
        policy = PolicyConfig(
            default=DefaultPolicy.disabled,
            tools={
                "coreutils_echo": ToolPolicy(),
            },
        )
        filtered = apply_policy(tool_map, policy)
        return create_server(server_name, filtered)

    async def test_filtered_tools_list(self, server):
        result = await _list_tools(server)
        names = {t.name for t in result.tools}
        assert names == {"coreutils_echo"}

    async def test_filtered_tool_not_callable(self, server):
        """Tools not in policy should return unknown."""
        result = await _call_tool(server, "coreutils_hello", {})
        assert "Unknown tool" in result.content[0].text

    async def test_allowed_tool_works(self, server):
        result = await _call_tool(server, "coreutils_echo", {"message": "policy test"})
        assert "policy test" in result.content[0].text


class TestE2EPolicyConstraints:
    """E2E: argument constraints enforced on real commands."""

    @pytest.fixture
    def server(self):
        server_name, tool_map = load_configs([COREUTILS_YAML])
        policy = PolicyConfig(
            default=DefaultPolicy.disabled,
            tools={
                "coreutils_echo": ToolPolicy(
                    args={"message": ArgConstraint(pattern=r"^[a-z\s]+$")},
                ),
            },
        )
        filtered = apply_policy(tool_map, policy)
        return create_server(server_name, filtered)

    async def test_constraint_pass(self, server):
        result = await _call_tool(server, "coreutils_echo", {"message": "hello world"})
        assert "hello world" in result.content[0].text

    async def test_constraint_reject(self, server):
        result = await _call_tool(server, "coreutils_echo", {"message": "INVALID!!!"})
        text = result.content[0].text
        assert "Policy validation failed" in text
        assert "pattern" in text


class TestE2EPolicyDescriptionOverride:
    """E2E: description override visible in list_tools."""

    @pytest.fixture
    def server(self):
        server_name, tool_map = load_configs([COREUTILS_YAML])
        policy = PolicyConfig(
            default=DefaultPolicy.disabled,
            tools={
                "coreutils_echo": ToolPolicy(
                    description="Custom echo description",
                ),
            },
        )
        filtered = apply_policy(tool_map, policy)
        return create_server(server_name, filtered)

    async def test_description_visible(self, server):
        result = await _list_tools(server)
        tool = result.tools[0]
        assert tool.description == "Custom echo description"


class TestE2EPolicyDefaultEnabled:
    """E2E: default=enabled exposes all tools."""

    @pytest.fixture
    def server(self):
        server_name, tool_map = load_configs([COREUTILS_YAML])
        policy = PolicyConfig(
            default=DefaultPolicy.enabled,
            tools={},
        )
        filtered = apply_policy(tool_map, policy)
        return create_server(server_name, filtered)

    async def test_all_tools_visible(self, server):
        result = await _list_tools(server)
        names = {t.name for t in result.tools}
        assert names == {"coreutils_echo", "coreutils_echo_flag", "coreutils_hello"}

    async def test_all_tools_callable(self, server):
        result = await _call_tool(server, "coreutils_hello", {})
        assert "hello from CLImax" in result.content[0].text
