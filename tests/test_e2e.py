"""End-to-end tests: MCP tool call → real subprocess → response.

These tests use examples/coreutils.yaml (echo-based) and an inline expr
config to exercise the full CLImax pipeline with real commands.
"""

import textwrap
from pathlib import Path

import pytest

import mcp.types as types

from climax import create_server, load_config, load_configs, ResolvedTool, ToolDef, ToolArg, ArgType


COREUTILS_YAML = Path(__file__).parent.parent / "examples" / "coreutils.yaml"


def _unwrap(result):
    """Unwrap ServerResult wrapper if present."""
    return result.root if hasattr(result, "root") else result


async def _call_tool(server, name, arguments=None):
    """Helper to call a tool and return the unwrapped result."""
    handlers = server.request_handlers
    request = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(name=name, arguments=arguments),
    )
    return _unwrap(await handlers[types.CallToolRequest](request))


async def _list_tools(server):
    """Helper to list tools and return the unwrapped result."""
    handlers = server.request_handlers
    request = types.ListToolsRequest(method="tools/list")
    return _unwrap(await handlers[types.ListToolsRequest](request))


class TestEndToEndCoreutils:
    """E2E tests using examples/coreutils.yaml with real echo commands."""

    @pytest.fixture
    def server(self):
        server_name, tool_map, _configs = load_configs([COREUTILS_YAML])
        return create_server(server_name, tool_map)

    async def test_list_tools(self, server):
        result = await _list_tools(server)
        names = {t.name for t in result.tools}
        assert names == {"coreutils_echo", "coreutils_echo_flag", "coreutils_hello"}

    async def test_echo_message(self, server):
        result = await _call_tool(server, "coreutils_echo", {"message": "hello world"})
        assert result.content[0].text.strip() == "hello world"

    async def test_echo_special_characters(self, server):
        result = await _call_tool(server, "coreutils_echo", {"message": "foo bar baz"})
        assert "foo bar baz" in result.content[0].text

    async def test_echo_no_newline_flag(self, server):
        result = await _call_tool(server, "coreutils_echo_flag", {
            "message": "test",
            "no_newline": True,
        })
        assert "test" in result.content[0].text

    async def test_hello_no_args(self, server):
        result = await _call_tool(server, "coreutils_hello", {})
        assert "hello from CLImax" in result.content[0].text

    async def test_unknown_tool(self, server):
        result = await _call_tool(server, "nonexistent_tool", {})
        assert "Unknown tool" in result.content[0].text


class TestEndToEndExpr:
    """E2E tests using expr for arithmetic — validates multi-positional args."""

    @pytest.fixture
    def server(self, tmp_path):
        content = textwrap.dedent("""\
            name: expr-tools
            command: expr
            tools:
              - name: expr_calc
                description: Evaluate arithmetic
                args:
                  - name: left
                    type: integer
                    required: true
                    positional: true
                  - name: operator
                    type: string
                    required: true
                    positional: true
                  - name: right
                    type: integer
                    required: true
                    positional: true
        """)
        p = tmp_path / "expr.yaml"
        p.write_text(content)
        server_name, tool_map, _configs = load_configs([p])
        return create_server(server_name, tool_map)

    async def test_addition(self, server):
        result = await _call_tool(server, "expr_calc", {
            "left": 2, "operator": "+", "right": 3,
        })
        assert result.content[0].text.strip() == "5"

    async def test_subtraction(self, server):
        result = await _call_tool(server, "expr_calc", {
            "left": 10, "operator": "-", "right": 4,
        })
        assert result.content[0].text.strip() == "6"

    async def test_multiplication(self, server):
        # expr uses \* for multiplication on most systems
        result = await _call_tool(server, "expr_calc", {
            "left": 6, "operator": "*", "right": 7,
        })
        assert result.content[0].text.strip() == "42"

    async def test_division(self, server):
        result = await _call_tool(server, "expr_calc", {
            "left": 15, "operator": "/", "right": 3,
        })
        assert result.content[0].text.strip() == "5"


class TestEndToEndMultiConfig:
    """E2E test loading multiple configs and calling tools from each."""

    async def test_merged_tools(self, tmp_path):
        echo_cfg = tmp_path / "echo.yaml"
        echo_cfg.write_text(textwrap.dedent("""\
            name: echo-tools
            command: echo
            tools:
              - name: echo_say
                description: Say something
                args:
                  - name: msg
                    positional: true
                    required: true
        """))

        printf_cfg = tmp_path / "printf.yaml"
        printf_cfg.write_text(textwrap.dedent("""\
            name: printf-tools
            command: printf
            tools:
              - name: printf_format
                description: Formatted output
                args:
                  - name: template
                    positional: true
                    required: true
        """))

        server_name, tool_map, _configs = load_configs([echo_cfg, printf_cfg])
        server = create_server(server_name, tool_map)

        # Call tool from first config
        echo_result = await _call_tool(server, "echo_say", {"msg": "multi-config works"})
        assert "multi-config works" in echo_result.content[0].text

        # Call tool from second config
        printf_result = await _call_tool(server, "printf_format", {"template": "hello"})
        assert "hello" in printf_result.content[0].text
