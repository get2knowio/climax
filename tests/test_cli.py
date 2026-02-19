"""Tests for CLI subcommands (validate, list, backward compat)."""

import argparse
import textwrap
from io import StringIO
from unittest.mock import patch

import pytest
from rich.console import Console

from climax import cmd_validate, cmd_list, main


def _make_args(configs):
    """Create a minimal args namespace with configs list."""
    return argparse.Namespace(configs=configs)


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
