"""Tests for CLI subcommands (validate, list, backward compat)."""

import argparse
import textwrap
from io import StringIO
from unittest.mock import patch

import pytest
from rich.console import Console

from climax import cmd_validate, cmd_list, main


def _make_args(configs, policy=None):
    """Create a minimal args namespace with configs list and optional policy."""
    return argparse.Namespace(configs=configs, policy=policy)


def _capture_console():
    """Create a Console that captures output to a StringIO buffer."""
    buf = StringIO()
    return Console(file=buf, force_terminal=False, width=200), buf


class TestCmdValidate:
    def test_valid_config(self, valid_yaml):
        console, buf = _capture_console()
        rc = cmd_validate(_make_args([str(valid_yaml)]), console=console)
        output = buf.getvalue()
        assert rc == 0
        assert "✓" in output
        assert "1 tool(s)" in output
        assert "All 1 config(s) valid" in output

    def test_invalid_config_missing_command(self, missing_command_yaml):
        console, buf = _capture_console()
        rc = cmd_validate(_make_args([str(missing_command_yaml)]), console=console)
        output = buf.getvalue()
        assert rc == 1
        assert "✗" in output
        assert "command" in output.lower()

    def test_invalid_config_bad_syntax(self, invalid_yaml_syntax):
        console, buf = _capture_console()
        rc = cmd_validate(_make_args([str(invalid_yaml_syntax)]), console=console)
        assert rc == 1

    def test_file_not_found(self, tmp_path):
        console, buf = _capture_console()
        rc = cmd_validate(_make_args([str(tmp_path / "nope.yaml")]), console=console)
        assert rc == 1

    def test_multiple_configs_mixed(self, valid_yaml, missing_command_yaml):
        console, buf = _capture_console()
        rc = cmd_validate(_make_args([str(valid_yaml), str(missing_command_yaml)]), console=console)
        output = buf.getvalue()
        assert rc == 1
        assert "1 valid, 1 invalid" in output

    def test_multiple_configs_all_valid(self, valid_yaml, minimal_yaml):
        console, buf = _capture_console()
        rc = cmd_validate(_make_args([str(valid_yaml), str(minimal_yaml)]), console=console)
        output = buf.getvalue()
        assert rc == 0
        assert "All 2 config(s) valid" in output

    def test_command_not_on_path_warning(self, tmp_path):
        content = textwrap.dedent("""\
            name: test
            command: definitely_not_a_real_binary_xyz
            tools:
              - name: t
                description: Test tool
        """)
        p = tmp_path / "notfound.yaml"
        p.write_text(content)

        console, buf = _capture_console()
        rc = cmd_validate(_make_args([str(p)]), console=console)
        output = buf.getvalue()
        assert rc == 0  # still valid, just a warning
        assert "⚠" in output or "not found on PATH" in output


class TestCmdList:
    def test_list_output(self, valid_yaml):
        console, buf = _capture_console()
        rc = cmd_list(_make_args([str(valid_yaml)]), console=console)
        output = buf.getvalue()
        assert rc == 0
        assert "test-tools" in output
        assert "hello" in output
        assert "1 tool(s)" in output

    def test_list_multiple_configs(self, valid_yaml, second_yaml):
        console, buf = _capture_console()
        rc = cmd_list(_make_args([str(valid_yaml), str(second_yaml)]), console=console)
        output = buf.getvalue()
        assert rc == 0
        assert "hello" in output
        assert "greet" in output
        assert "2 tool(s)" in output

    def test_list_shows_args_metadata(self, tmp_path):
        content = textwrap.dedent("""\
            name: meta-test
            command: app
            tools:
              - name: search
                description: Search things
                command: search
                args:
                  - name: query
                    type: string
                    required: true
                    positional: true
                  - name: limit
                    type: integer
                    default: 10
                    flag: --limit
                  - name: format
                    type: string
                    enum: ["json", "table"]
                    flag: --format
        """)
        p = tmp_path / "meta.yaml"
        p.write_text(content)

        console, buf = _capture_console()
        rc = cmd_list(_make_args([str(p)]), console=console)
        output = buf.getvalue()
        assert rc == 0
        assert "query" in output
        assert "required" in output
        assert "positional" in output
        assert "limit" in output
        assert "default=10" in output

    def test_list_invalid_config(self, missing_command_yaml):
        console, buf = _capture_console()
        rc = cmd_list(_make_args([str(missing_command_yaml)]), console=console)
        assert rc == 1

    def test_list_sorted_by_name(self, tmp_path):
        content = textwrap.dedent("""\
            name: sorted
            command: app
            tools:
              - name: zebra
                description: Z tool
              - name: alpha
                description: A tool
              - name: middle
                description: M tool
        """)
        p = tmp_path / "sorted.yaml"
        p.write_text(content)

        console, buf = _capture_console()
        rc = cmd_list(_make_args([str(p)]), console=console)
        output = buf.getvalue()
        assert rc == 0
        # alpha should appear before middle, middle before zebra
        assert output.index("alpha") < output.index("middle") < output.index("zebra")


class TestBackwardCompat:
    def test_no_subcommand_runs_as_run(self, valid_yaml):
        """climax config.yaml should work the same as climax run config.yaml."""
        with patch("climax.cmd_run") as mock_run:
            with patch("sys.argv", ["climax", str(valid_yaml)]):
                main()
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert str(valid_yaml) in args.configs

    def test_no_subcommand_with_log_level(self, valid_yaml):
        """climax config.yaml --log-level DEBUG should still work."""
        with patch("climax.cmd_run") as mock_run:
            with patch("sys.argv", ["climax", str(valid_yaml), "--log-level", "DEBUG"]):
                main()
            args = mock_run.call_args[0][0]
            assert args.log_level == "DEBUG"


class TestCmdValidatePolicy:
    def test_validate_with_valid_policy(self, valid_yaml, minimal_policy_yaml):
        console, buf = _capture_console()
        rc = cmd_validate(
            _make_args([str(valid_yaml)], policy=str(minimal_policy_yaml)),
            console=console,
        )
        output = buf.getvalue()
        assert rc == 0
        assert "policy" in output
        assert "1 tool rule(s)" in output

    def test_validate_with_invalid_policy(self, valid_yaml, invalid_policy_yaml):
        console, buf = _capture_console()
        rc = cmd_validate(
            _make_args([str(valid_yaml)], policy=str(invalid_policy_yaml)),
            console=console,
        )
        output = buf.getvalue()
        assert rc == 1
        assert "✗" in output

    def test_validate_with_missing_policy(self, valid_yaml, tmp_path):
        console, buf = _capture_console()
        rc = cmd_validate(
            _make_args([str(valid_yaml)], policy=str(tmp_path / "nope.yaml")),
            console=console,
        )
        assert rc == 1

    def test_validate_no_policy(self, valid_yaml):
        """Without --policy, validate works as before."""
        console, buf = _capture_console()
        rc = cmd_validate(_make_args([str(valid_yaml)]), console=console)
        output = buf.getvalue()
        assert rc == 0
        assert "policy" not in output.lower()


class TestCmdListPolicy:
    def test_list_filtered_by_policy(self, tmp_path):
        """Policy with default=disabled should filter tools in list."""
        config = tmp_path / "tools.yaml"
        config.write_text(textwrap.dedent("""\
            name: test-tools
            command: echo
            tools:
              - name: allowed
                description: Allowed tool
              - name: blocked
                description: Blocked tool
        """))
        policy = tmp_path / "policy.yaml"
        policy.write_text(textwrap.dedent("""\
            default: disabled
            tools:
              allowed: {}
        """))

        console, buf = _capture_console()
        rc = cmd_list(_make_args([str(config)], policy=str(policy)), console=console)
        output = buf.getvalue()
        assert rc == 0
        assert "allowed" in output
        assert "blocked" not in output
        assert "1 tool(s)" in output

    def test_list_shows_constraints(self, tmp_path):
        config = tmp_path / "tools.yaml"
        config.write_text(textwrap.dedent("""\
            name: test-tools
            command: echo
            tools:
              - name: search
                description: Search
                args:
                  - name: query
                    type: string
                  - name: limit
                    type: integer
        """))
        policy = tmp_path / "policy.yaml"
        policy.write_text(textwrap.dedent("""\
            default: disabled
            tools:
              search:
                args:
                  query:
                    pattern: "^[a-z]+$"
                  limit:
                    max: 100
        """))

        console, buf = _capture_console()
        rc = cmd_list(_make_args([str(config)], policy=str(policy)), console=console)
        output = buf.getvalue()
        assert rc == 0
        assert "pattern=" in output
        assert "max=" in output

    def test_list_shows_executor(self, tmp_path):
        config = tmp_path / "tools.yaml"
        config.write_text(textwrap.dedent("""\
            name: test-tools
            command: echo
            tools:
              - name: hello
                description: Hello
        """))
        policy = tmp_path / "policy.yaml"
        policy.write_text(textwrap.dedent("""\
            executor:
              type: docker
              image: alpine:latest
            default: disabled
            tools:
              hello: {}
        """))

        console, buf = _capture_console()
        rc = cmd_list(_make_args([str(config)], policy=str(policy)), console=console)
        output = buf.getvalue()
        assert rc == 0
        assert "docker" in output.lower()
        assert "alpine:latest" in output

    def test_backward_compat_with_policy(self, valid_yaml, minimal_policy_yaml):
        """--policy with backward compat run mode."""
        with patch("climax.cmd_run") as mock_run:
            with patch("sys.argv", [
                "climax", "--policy", str(minimal_policy_yaml), str(valid_yaml),
            ]):
                main()
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args.policy == str(minimal_policy_yaml)
