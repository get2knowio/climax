"""Tests for the approval dialog system."""

import textwrap
from unittest.mock import AsyncMock, patch

from climax_mcp import (
    ApprovalConfig,
    ApprovalLevel,
    HeadlessPolicy,
    PolicyConfig,
    ResolvedTool,
    RiskLevel,
    ToolArg,
    ToolDef,
    ToolPolicy,
    ResolveConfig,
    _requires_approval,
    _run_resolves,
    _show_approval_dialog,
    cmd_test_dialog,
    create_server,
    load_policy,
)
import mcp.types as types
from io import StringIO
from rich.console import Console


# ---------------------------------------------------------------------------
# _requires_approval logic
# ---------------------------------------------------------------------------


class TestRequiresApproval:
    """Test all combinations of global level x risk level x per-tool override."""

    def test_no_approval_config(self):
        tool = ToolDef(name="t", description="t", risk=RiskLevel.destructive)
        assert _requires_approval(tool, None, None) is False

    def test_global_none_allows_all(self):
        cfg = ApprovalConfig(global_level=ApprovalLevel.none)
        for risk in RiskLevel:
            tool = ToolDef(name="t", description="t", risk=risk)
            assert _requires_approval(tool, cfg, None) is False

    def test_global_all_requires_all(self):
        cfg = ApprovalConfig(global_level=ApprovalLevel.all)
        for risk in RiskLevel:
            tool = ToolDef(name="t", description="t", risk=risk)
            assert _requires_approval(tool, cfg, None) is True

    def test_global_destructive_only_destructive(self):
        cfg = ApprovalConfig(global_level=ApprovalLevel.destructive)
        assert _requires_approval(ToolDef(name="t", description="t", risk=RiskLevel.read), cfg, None) is False
        assert _requires_approval(ToolDef(name="t", description="t", risk=RiskLevel.write), cfg, None) is False
        assert _requires_approval(ToolDef(name="t", description="t", risk=RiskLevel.destructive), cfg, None) is True

    def test_global_write_catches_write_and_destructive(self):
        cfg = ApprovalConfig(global_level=ApprovalLevel.write)
        assert _requires_approval(ToolDef(name="t", description="t", risk=RiskLevel.read), cfg, None) is False
        assert _requires_approval(ToolDef(name="t", description="t", risk=RiskLevel.write), cfg, None) is True
        assert _requires_approval(ToolDef(name="t", description="t", risk=RiskLevel.destructive), cfg, None) is True

    def test_default_global_is_write(self):
        """Default ApprovalConfig should require approval for write+destructive."""
        cfg = ApprovalConfig()
        assert cfg.global_level == ApprovalLevel.write
        assert _requires_approval(ToolDef(name="t", description="t", risk=RiskLevel.read), cfg, None) is False
        assert _requires_approval(ToolDef(name="t", description="t", risk=RiskLevel.write), cfg, None) is True

    def test_tool_policy_override_true(self):
        """Per-tool require_approval=True overrides global none."""
        cfg = ApprovalConfig(global_level=ApprovalLevel.none)
        policy = ToolPolicy(require_approval=True)
        tool = ToolDef(name="t", description="t", risk=RiskLevel.read)
        assert _requires_approval(tool, cfg, policy) is True

    def test_tool_policy_override_false(self):
        """Per-tool require_approval=False overrides global all."""
        cfg = ApprovalConfig(global_level=ApprovalLevel.all)
        policy = ToolPolicy(require_approval=False)
        tool = ToolDef(name="t", description="t", risk=RiskLevel.destructive)
        assert _requires_approval(tool, cfg, policy) is False

    def test_tool_policy_none_defers_to_global(self):
        """Per-tool require_approval=None defers to global."""
        cfg = ApprovalConfig(global_level=ApprovalLevel.all)
        policy = ToolPolicy(require_approval=None)
        tool = ToolDef(name="t", description="t", risk=RiskLevel.read)
        assert _requires_approval(tool, cfg, policy) is True

    def test_approval_tools_dict_override(self):
        """Per-tool override in approval.tools dict."""
        cfg = ApprovalConfig(global_level=ApprovalLevel.none, tools={"my_tool": True})
        tool = ToolDef(name="my_tool", description="t", risk=RiskLevel.read)
        assert _requires_approval(tool, cfg, None) is True

    def test_approval_tools_dict_skip(self):
        """Per-tool skip in approval.tools dict."""
        cfg = ApprovalConfig(global_level=ApprovalLevel.all, tools={"my_tool": False})
        tool = ToolDef(name="my_tool", description="t", risk=RiskLevel.destructive)
        assert _requires_approval(tool, cfg, None) is False

    def test_tool_policy_takes_precedence_over_approval_tools(self):
        """ToolPolicy.require_approval takes precedence over approval.tools dict."""
        cfg = ApprovalConfig(global_level=ApprovalLevel.none, tools={"my_tool": True})
        policy = ToolPolicy(require_approval=False)
        tool = ToolDef(name="my_tool", description="t", risk=RiskLevel.read)
        assert _requires_approval(tool, cfg, policy) is False


# ---------------------------------------------------------------------------
# _run_resolves
# ---------------------------------------------------------------------------


class TestRunResolves:
    async def test_successful_resolve(self):
        tool = ToolDef(
            name="t", description="t",
            resolve={
                "_name": ResolveConfig(
                    command="describe-thing",
                    args={"id": "{thing_id}"},
                ),
            },
        )
        with patch("climax_mcp.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "My Thing Name\n", "")
            result = await _run_resolves(tool, {"thing_id": "123"}, "mycli")
            assert result == {"_name": "My Thing Name"}
            # Verify the command was constructed correctly
            cmd = mock_run.call_args[0][0]
            assert cmd[0] == "mycli"
            assert "describe-thing" in cmd
            assert "--id" in cmd
            assert "123" in cmd

    async def test_failed_resolve_returns_placeholder(self):
        tool = ToolDef(
            name="t", description="t",
            resolve={"_name": ResolveConfig(command="fail")},
        )
        with patch("climax_mcp.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (1, "", "not found")
            result = await _run_resolves(tool, {}, "mycli")
            assert result == {"_name": "<unresolved:_name>"}

    async def test_empty_output_returns_placeholder(self):
        tool = ToolDef(
            name="t", description="t",
            resolve={"_name": ResolveConfig(command="empty")},
        )
        with patch("climax_mcp.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "  \n", "")
            result = await _run_resolves(tool, {}, "mycli")
            assert result == {"_name": "<unresolved:_name>"}

    async def test_timeout_passed_through(self):
        tool = ToolDef(
            name="t", description="t",
            resolve={"_x": ResolveConfig(command="slow", timeout=5.0)},
        )
        with patch("climax_mcp.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "ok", "")
            await _run_resolves(tool, {}, "mycli")
            assert mock_run.call_args[1]["timeout"] == 5.0

    async def test_missing_template_var_skipped(self):
        tool = ToolDef(
            name="t", description="t",
            resolve={
                "_name": ResolveConfig(
                    command="describe",
                    args={"id": "{missing_var}"},
                ),
            },
        )
        with patch("climax_mcp.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "ok", "")
            # Should not raise even though {missing_var} not in arguments
            await _run_resolves(tool, {}, "mycli")


# ---------------------------------------------------------------------------
# Dialog functions (mocked)
# ---------------------------------------------------------------------------


class TestShowApprovalDialog:
    async def test_macos_approve(self):
        with patch("climax_mcp._dialog_macos", new_callable=AsyncMock) as mock:
            mock.return_value = True
            with patch("climax_mcp.platform.system", return_value="Darwin"):
                # Import inside to get the patched version
                result = await _show_approval_dialog("test?")
                assert result is True

    async def test_macos_deny(self):
        with patch("climax_mcp._dialog_macos", new_callable=AsyncMock) as mock:
            mock.return_value = False
            with patch("climax_mcp.platform.system", return_value="Darwin"):
                result = await _show_approval_dialog("test?")
                assert result is False

    async def test_macos_fallback_to_terminal(self):
        """When macOS dialog returns None, falls back to terminal."""
        with patch("climax_mcp._dialog_macos", new_callable=AsyncMock) as mock_mac:
            mock_mac.return_value = None
            with patch("climax_mcp._dialog_terminal", new_callable=AsyncMock) as mock_term:
                mock_term.return_value = True
                with patch("climax_mcp.platform.system", return_value="Darwin"):
                    result = await _show_approval_dialog("test?")
                    assert result is True
                    mock_term.assert_called_once()

    async def test_linux_approve(self):
        with patch("climax_mcp._dialog_linux", new_callable=AsyncMock) as mock:
            mock.return_value = True
            with patch("climax_mcp.platform.system", return_value="Linux"):
                result = await _show_approval_dialog("test?")
                assert result is True

    async def test_windows_deny(self):
        with patch("climax_mcp._dialog_windows", new_callable=AsyncMock) as mock:
            mock.return_value = False
            with patch("climax_mcp.platform.system", return_value="Windows"):
                result = await _show_approval_dialog("test?")
                assert result is False

    async def test_unknown_platform_uses_terminal(self):
        with patch("climax_mcp._dialog_terminal", new_callable=AsyncMock) as mock_term:
            mock_term.return_value = False
            with patch("climax_mcp.platform.system", return_value="FreeBSD"):
                result = await _show_approval_dialog("test?", HeadlessPolicy.deny)
                assert result is False


class TestDialogTerminal:
    async def test_headless_deny(self):
        """When no TTY and headless=deny, should return False."""
        from climax_mcp import _dialog_terminal

        def fake_open(*args, **kwargs):
            raise OSError("no tty")

        with patch("builtins.open", side_effect=fake_open):
            result = await _dialog_terminal("test?", HeadlessPolicy.deny)
            assert result is False

    async def test_headless_approve(self):
        """When no TTY and headless=approve, should return True."""
        from climax_mcp import _dialog_terminal

        def fake_open(*args, **kwargs):
            raise OSError("no tty")

        with patch("builtins.open", side_effect=fake_open):
            result = await _dialog_terminal("test?", HeadlessPolicy.approve)
            assert result is True


# ---------------------------------------------------------------------------
# Integration: approval in _execute_tool
# ---------------------------------------------------------------------------


def _unwrap(result):
    """Unwrap ServerResult wrapper if present."""
    return result.root if hasattr(result, "root") else result


class TestApprovalIntegration:
    """Test approval flow integrated into the MCP server."""

    def _make_tool_map(self, risk=RiskLevel.destructive, confirm_message=None, resolve=None):
        tool = ToolDef(
            name="danger_tool",
            description="A dangerous tool",
            command="destroy",
            risk=risk,
            confirm_message=confirm_message,
            resolve=resolve or {},
            args=[
                ToolArg(name="target", type="string", required=True, positional=True),
            ],
        )
        return {
            "danger_tool": ResolvedTool(
                tool=tool,
                base_command="echo",
            ),
        }

    async def test_approved_tool_executes(self):
        """When user approves, the tool should execute normally."""
        policy = PolicyConfig(
            default="enabled",
            approval=ApprovalConfig(global_level=ApprovalLevel.destructive),
        )
        tool_map = self._make_tool_map()
        server = create_server("test", tool_map, classic=True, policy=policy)
        handlers = server.request_handlers

        with patch("climax_mcp._show_approval_dialog", new_callable=AsyncMock) as mock_dialog:
            mock_dialog.return_value = True
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(name="danger_tool", arguments={"target": "world"}),
            )
            result = _unwrap(await handlers[types.CallToolRequest](request))
            assert len(result.content) == 1
            # echo destroy world → "destroy world"
            assert "destroy world" in result.content[0].text
            mock_dialog.assert_called_once()

    async def test_denied_tool_returns_denial(self):
        """When user denies, should return denial message."""
        policy = PolicyConfig(
            default="enabled",
            approval=ApprovalConfig(global_level=ApprovalLevel.destructive),
        )
        tool_map = self._make_tool_map()
        server = create_server("test", tool_map, classic=True, policy=policy)
        handlers = server.request_handlers

        with patch("climax_mcp._show_approval_dialog", new_callable=AsyncMock) as mock_dialog:
            mock_dialog.return_value = False
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(name="danger_tool", arguments={"target": "world"}),
            )
            result = _unwrap(await handlers[types.CallToolRequest](request))
            assert "denied" in result.content[0].text.lower()
            mock_dialog.assert_called_once()

    async def test_no_approval_for_read_tools(self):
        """Read tools should not trigger approval even with write policy."""
        policy = PolicyConfig(
            default="enabled",
            approval=ApprovalConfig(global_level=ApprovalLevel.write),
        )
        tool_map = self._make_tool_map(risk=RiskLevel.read)
        server = create_server("test", tool_map, classic=True, policy=policy)
        handlers = server.request_handlers

        with patch("climax_mcp._show_approval_dialog", new_callable=AsyncMock) as mock_dialog:
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(name="danger_tool", arguments={"target": "world"}),
            )
            result = _unwrap(await handlers[types.CallToolRequest](request))
            # Should execute without asking
            mock_dialog.assert_not_called()
            assert "destroy world" in result.content[0].text

    async def test_no_policy_means_no_approval(self):
        """Without a policy, no approval should be required."""
        tool_map = self._make_tool_map(risk=RiskLevel.destructive)
        server = create_server("test", tool_map, classic=True, policy=None)
        handlers = server.request_handlers

        with patch("climax_mcp._show_approval_dialog", new_callable=AsyncMock) as mock_dialog:
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(name="danger_tool", arguments={"target": "world"}),
            )
            result = _unwrap(await handlers[types.CallToolRequest](request))
            mock_dialog.assert_not_called()
            assert "destroy world" in result.content[0].text

    async def test_confirm_message_template(self):
        """Confirm message should be rendered with argument values."""
        policy = PolicyConfig(
            default="enabled",
            approval=ApprovalConfig(global_level=ApprovalLevel.destructive),
        )
        tool_map = self._make_tool_map(
            confirm_message="Delete {target}?",
        )
        server = create_server("test", tool_map, classic=True, policy=policy)
        handlers = server.request_handlers

        with patch("climax_mcp._show_approval_dialog", new_callable=AsyncMock) as mock_dialog:
            mock_dialog.return_value = True
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(name="danger_tool", arguments={"target": "important-file"}),
            )
            await handlers[types.CallToolRequest](request)
            # Check the message passed to the dialog
            assert mock_dialog.call_args[0][0] == "Delete important-file?"

    async def test_confirm_message_with_resolve(self):
        """Confirm message should include resolved variables."""
        policy = PolicyConfig(
            default="enabled",
            approval=ApprovalConfig(global_level=ApprovalLevel.destructive),
        )
        tool_map = self._make_tool_map(
            confirm_message="Delete {target} ({_friendly_name})?",
            resolve={
                "_friendly_name": ResolveConfig(
                    command="describe",
                    args={"id": "{target}"},
                ),
            },
        )
        server = create_server("test", tool_map, classic=True, policy=policy)
        handlers = server.request_handlers

        with patch("climax_mcp._show_approval_dialog", new_callable=AsyncMock) as mock_dialog, \
             patch("climax_mcp._run_resolves", new_callable=AsyncMock) as mock_resolve:
            mock_dialog.return_value = True
            mock_resolve.return_value = {"_friendly_name": "My Important File"}
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(name="danger_tool", arguments={"target": "abc123"}),
            )
            await handlers[types.CallToolRequest](request)
            assert mock_dialog.call_args[0][0] == "Delete abc123 (My Important File)?"


# ---------------------------------------------------------------------------
# Policy YAML parsing with approval section
# ---------------------------------------------------------------------------


class TestApprovalPolicyLoading:
    def test_policy_with_approval_section(self, tmp_path):
        content = textwrap.dedent("""\
            default: enabled
            approval:
              global: destructive
              headless: approve
              tools:
                my_tool: true
                safe_tool: false
            tools:
              my_tool:
                require_approval: true
        """)
        p = tmp_path / "policy.yaml"
        p.write_text(content)
        policy = load_policy(p)
        assert policy.approval.global_level == ApprovalLevel.destructive
        assert policy.approval.headless == HeadlessPolicy.approve
        assert policy.approval.tools == {"my_tool": True, "safe_tool": False}
        assert policy.tools["my_tool"].require_approval is True

    def test_policy_without_approval_section(self, tmp_path):
        """Backward compat: policy without approval section should use defaults."""
        content = textwrap.dedent("""\
            default: enabled
            tools:
              my_tool: {}
        """)
        p = tmp_path / "policy.yaml"
        p.write_text(content)
        policy = load_policy(p)
        assert policy.approval.global_level == ApprovalLevel.write
        assert policy.approval.headless == HeadlessPolicy.deny
        assert policy.approval.tools == {}

    def test_policy_global_alias(self, tmp_path):
        """The 'global' YAML key should map to global_level."""
        content = textwrap.dedent("""\
            approval:
              global: all
            tools: {}
        """)
        p = tmp_path / "policy.yaml"
        p.write_text(content)
        policy = load_policy(p)
        assert policy.approval.global_level == ApprovalLevel.all


# ---------------------------------------------------------------------------
# Config YAML parsing with risk / confirm_message / resolve
# ---------------------------------------------------------------------------


class TestRiskConfigLoading:
    def test_tool_with_risk_and_confirm(self, tmp_path):
        from climax_mcp import load_config
        content = textwrap.dedent("""\
            name: test
            command: echo
            tools:
              - name: rm_tool
                description: Remove something
                command: rm
                risk: destructive
                confirm_message: "Delete {path}?"
                args:
                  - name: path
                    type: string
                    required: true
                    positional: true
        """)
        p = tmp_path / "test.yaml"
        p.write_text(content)
        config = load_config(p)
        tool = config.tools[0]
        assert tool.risk == RiskLevel.destructive
        assert tool.confirm_message == "Delete {path}?"

    def test_tool_without_risk_defaults_to_read(self, tmp_path):
        from climax_mcp import load_config
        content = textwrap.dedent("""\
            name: test
            command: echo
            tools:
              - name: ls_tool
                description: List things
        """)
        p = tmp_path / "test.yaml"
        p.write_text(content)
        config = load_config(p)
        assert config.tools[0].risk == RiskLevel.read
        assert config.tools[0].confirm_message is None
        assert config.tools[0].resolve == {}

    def test_tool_with_resolve(self, tmp_path):
        from climax_mcp import load_config
        content = textwrap.dedent("""\
            name: test
            command: mycli
            tools:
              - name: delete_thing
                description: Delete a thing
                risk: destructive
                confirm_message: "Delete {id} ({_name})?"
                resolve:
                  _name:
                    command: describe
                    args:
                      id: "{id}"
                    timeout: 5
                args:
                  - name: id
                    type: string
                    required: true
                    positional: true
        """)
        p = tmp_path / "test.yaml"
        p.write_text(content)
        config = load_config(p)
        tool = config.tools[0]
        assert "_name" in tool.resolve
        assert tool.resolve["_name"].command == "describe"
        assert tool.resolve["_name"].args == {"id": "{id}"}
        assert tool.resolve["_name"].timeout == 5.0


# ---------------------------------------------------------------------------
# cmd_test_dialog
# ---------------------------------------------------------------------------


class TestCmdTestDialog:
    def test_approve_path(self):
        """Test that cmd_test_dialog runs and reports approval."""
        buf = StringIO()
        test_console = Console(file=buf, force_terminal=True)
        with patch("climax_mcp._dialog_linux", new_callable=AsyncMock, return_value=True):
            with patch("climax_mcp.platform.system", return_value="Linux"):
                rc = cmd_test_dialog(console=test_console)
        assert rc == 0
        output = buf.getvalue()
        assert "Approve" in output

    def test_deny_path(self):
        """Test that cmd_test_dialog runs and reports denial."""
        buf = StringIO()
        test_console = Console(file=buf, force_terminal=True)
        with patch("climax_mcp._dialog_linux", new_callable=AsyncMock, return_value=False):
            with patch("climax_mcp.platform.system", return_value="Linux"):
                rc = cmd_test_dialog(console=test_console)
        assert rc == 0
        output = buf.getvalue()
        assert "Deny" in output

    def test_fallback_to_terminal(self):
        """When no GUI available, falls through to terminal dialog."""
        buf = StringIO()
        test_console = Console(file=buf, force_terminal=True)
        with patch("climax_mcp._dialog_linux", new_callable=AsyncMock, return_value=None):
            with patch("climax_mcp._dialog_terminal", new_callable=AsyncMock, return_value=False):
                with patch("climax_mcp.platform.system", return_value="Linux"):
                    rc = cmd_test_dialog(console=test_console)
        assert rc == 0
        output = buf.getvalue()
        assert "terminal" in output.lower() or "Deny" in output
