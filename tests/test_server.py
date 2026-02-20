"""Tests for MCP server integration — list_tools and call_tool."""

from unittest.mock import patch, AsyncMock

import pytest

import mcp.types as types

from climax import (
    ArgConstraint,
    ArgType,
    ExecutorConfig,
    ExecutorType,
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


    async def test_call_tool_long_arg_truncation(self, caplog):
        """Long positional args should be truncated in log display but not in actual command."""
        tool_map = {
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
        }
        server = create_server("test", tool_map)

        long_value = "x" * 200

        with patch("climax.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "ok\n", "")

            import logging
            with caplog.at_level(logging.INFO, logger="climax"):
                handlers = server.request_handlers
                request = types.CallToolRequest(
                    method="tools/call",
                    params=types.CallToolRequestParams(name="greet", arguments={"name": long_value}),
                )
                result = _unwrap(await handlers[types.CallToolRequest](request))

        # Full value should reach run_command (not truncated)
        cmd = mock_run.call_args[0][0]
        assert long_value in cmd

        # Log should contain truncation marker
        assert any("bytes]" in record.message for record in caplog.records)


class TestMCPServerPolicy:
    """Tests for policy-aware server behavior."""

    async def test_description_override_in_list(self):
        """description_override should be used in list_tools."""
        tool_map = {
            "greet": ResolvedTool(
                tool=ToolDef(name="greet", description="Original desc"),
                base_command="echo",
                description_override="Custom desc",
            ),
        }
        server = create_server("test", tool_map)

        handlers = server.request_handlers
        request = types.ListToolsRequest(method="tools/list")
        result = _unwrap(await handlers[types.ListToolsRequest](request))

        assert result.tools[0].description == "Custom desc"

    async def test_no_override_uses_original(self):
        """Without description_override, original description is used."""
        tool_map = {
            "greet": ResolvedTool(
                tool=ToolDef(name="greet", description="Original desc"),
                base_command="echo",
            ),
        }
        server = create_server("test", tool_map)

        handlers = server.request_handlers
        request = types.ListToolsRequest(method="tools/list")
        result = _unwrap(await handlers[types.ListToolsRequest](request))

        assert result.tools[0].description == "Original desc"

    async def test_arg_validation_rejection(self):
        """call_tool should reject arguments that violate constraints."""
        tool_map = {
            "greet": ResolvedTool(
                tool=ToolDef(
                    name="greet",
                    description="Say hello",
                    command="hello",
                    args=[ToolArg(name="name", type=ArgType.string, positional=True)],
                ),
                base_command="echo",
                arg_constraints={"name": ArgConstraint(pattern="^[a-z]+$")},
            ),
        }
        server = create_server("test", tool_map)

        with patch("climax.run_command", new_callable=AsyncMock) as mock_run:
            handlers = server.request_handlers
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(name="greet", arguments={"name": "INVALID123"}),
            )
            result = _unwrap(await handlers[types.CallToolRequest](request))

        text = result.content[0].text
        assert "Policy validation failed" in text
        assert "pattern" in text
        mock_run.assert_not_called()

    async def test_arg_validation_pass(self):
        """call_tool should allow arguments that pass constraints."""
        tool_map = {
            "greet": ResolvedTool(
                tool=ToolDef(
                    name="greet",
                    description="Say hello",
                    command="hello",
                    args=[ToolArg(name="name", type=ArgType.string, positional=True)],
                ),
                base_command="echo",
                arg_constraints={"name": ArgConstraint(pattern="^[a-z]+$")},
            ),
        }
        server = create_server("test", tool_map)

        with patch("climax.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "hello world\n", "")

            handlers = server.request_handlers
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(name="greet", arguments={"name": "world"}),
            )
            result = _unwrap(await handlers[types.CallToolRequest](request))

        assert "hello world" in result.content[0].text
        mock_run.assert_called_once()

    async def test_docker_prefix_in_call(self):
        """Docker executor should prepend docker run prefix to command."""
        tool_map = {
            "greet": ResolvedTool(
                tool=ToolDef(name="greet", description="Say hello"),
                base_command="echo",
            ),
        }
        executor = ExecutorConfig(type=ExecutorType.docker, image="alpine:latest")
        server = create_server("test", tool_map, executor=executor)

        with patch("climax.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "hi\n", "")

            handlers = server.request_handlers
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(name="greet", arguments={}),
            )
            result = _unwrap(await handlers[types.CallToolRequest](request))

        cmd = mock_run.call_args[0][0]
        assert cmd[:4] == ["docker", "run", "--rm", "alpine:latest"]
        assert "echo" in cmd

    async def test_no_executor_backward_compat(self):
        """Without executor, command should not have docker prefix."""
        tool_map = _build_tool_map()
        server = create_server("test", tool_map)

        with patch("climax.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "ok\n", "")

            handlers = server.request_handlers
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(name="status", arguments={}),
            )
            result = _unwrap(await handlers[types.CallToolRequest](request))

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "git"
        assert "docker" not in cmd
