"""Tests for MCP server integration — list_tools and call_tool."""

from unittest.mock import patch, AsyncMock

import pytest

import mcp.types as types

from climax import (
    ArgType,
    ResolvedTool,
    ToolArg,
    ToolDef,
    create_server,
)


def _build_tool_map():
    """Build a small tool map for testing."""
    return {
        "greet": ResolvedTool(
            tool=ToolDef(
                name="greet",
                description="Say hello",
                command="hello",
                args=[
                    ToolArg(name="name", type=ArgType.string, required=True, positional=True),
                ],
            ),
            base_command="echo",
        ),
        "status": ResolvedTool(
            tool=ToolDef(name="status", description="Show status"),
            base_command="git",
        ),
    }


def _unwrap(result):
    """Unwrap ServerResult wrapper if present."""
    return result.root if hasattr(result, "root") else result


class TestMCPServer:
    async def test_list_tools_count(self):
        tool_map = _build_tool_map()
        server = create_server("test", tool_map)

        handlers = server.request_handlers
        request = types.ListToolsRequest(method="tools/list")
        result = _unwrap(await handlers[types.ListToolsRequest](request))
        assert len(result.tools) == 2

    async def test_list_tools_schemas(self):
        tool_map = _build_tool_map()
        server = create_server("test", tool_map)

        handlers = server.request_handlers
        request = types.ListToolsRequest(method="tools/list")
        result = _unwrap(await handlers[types.ListToolsRequest](request))

        tool_names = {t.name for t in result.tools}
        assert tool_names == {"greet", "status"}

        greet_tool = next(t for t in result.tools if t.name == "greet")
        assert greet_tool.description == "Say hello"
        assert "name" in greet_tool.inputSchema["properties"]
        assert greet_tool.inputSchema["required"] == ["name"]

    async def test_call_tool_success(self):
        tool_map = _build_tool_map()
        server = create_server("test", tool_map)

        with patch("climax.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "Hello World\n", "")

            handlers = server.request_handlers
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(name="greet", arguments={"name": "World"}),
            )
            result = _unwrap(await handlers[types.CallToolRequest](request))

        assert len(result.content) == 1
        assert "Hello World" in result.content[0].text
        mock_run.assert_called_once()

    async def test_call_tool_failure(self):
        tool_map = _build_tool_map()
        server = create_server("test", tool_map)

        with patch("climax.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (1, "", "command failed\n")

            handlers = server.request_handlers
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(name="greet", arguments={"name": "World"}),
            )
            result = _unwrap(await handlers[types.CallToolRequest](request))

        text = result.content[0].text
        assert "command failed" in text
        assert "exit code: 1" in text

    async def test_call_tool_unknown(self):
        tool_map = _build_tool_map()
        server = create_server("test", tool_map)

        with patch("climax.run_command", new_callable=AsyncMock):
            handlers = server.request_handlers
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(name="nonexistent", arguments={}),
            )
            result = _unwrap(await handlers[types.CallToolRequest](request))

        assert "Unknown tool" in result.content[0].text

    async def test_call_tool_no_args(self):
        tool_map = _build_tool_map()
        server = create_server("test", tool_map)

        with patch("climax.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "ok\n", "")

            handlers = server.request_handlers
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(name="status", arguments=None),
            )
            result = _unwrap(await handlers[types.CallToolRequest](request))

        assert "ok" in result.content[0].text

    async def test_call_tool_stderr_formatting(self):
        tool_map = _build_tool_map()
        server = create_server("test", tool_map)

        with patch("climax.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "output\n", "warning msg\n")

            handlers = server.request_handlers
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(name="status", arguments={}),
            )
            result = _unwrap(await handlers[types.CallToolRequest](request))

        text = result.content[0].text
        assert "output" in text
        assert "[stderr]" in text
        assert "warning msg" in text

    async def test_call_tool_no_output(self):
        tool_map = _build_tool_map()
        server = create_server("test", tool_map)

        with patch("climax.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "", "")

            handlers = server.request_handlers
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(name="status", arguments={}),
            )
            result = _unwrap(await handlers[types.CallToolRequest](request))

        assert "(no output)" in result.content[0].text
