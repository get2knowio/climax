"""Tests for CLI subcommands (validate, list, backward compat)."""

import argparse
import importlib
import logging
import os
import textwrap
from io import StringIO
from unittest.mock import patch, MagicMock

import pytest
from rich.console import Console

import climax
from climax import cmd_validate, cmd_list, cmd_run, main


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

    def test_list_with_invalid_policy_file(self, valid_yaml, tmp_path):
        """Invalid policy YAML should return 1 with error message."""
        policy = tmp_path / "bad_policy.yaml"
        policy.write_text("executor:\n  type: docker\ntools:\n  hello: {}\n")

        console, buf = _capture_console()
        rc = cmd_list(_make_args([str(valid_yaml)], policy=str(policy)), console=console)
        output = buf.getvalue()
        assert rc == 1
        assert "Error loading policy" in output

    def test_list_with_nonexistent_policy_file(self, valid_yaml, tmp_path):
        """Missing policy file should return 1 with error message."""
        console, buf = _capture_console()
        rc = cmd_list(
            _make_args([str(valid_yaml)], policy=str(tmp_path / "nope.yaml")),
            console=console,
        )
        output = buf.getvalue()
        assert rc == 1
        assert "Error loading policy" in output

    def test_list_shows_min_constraint(self, tmp_path):
        """Policy with min constraint should show min= in list output."""
        config = tmp_path / "tools.yaml"
        config.write_text(textwrap.dedent("""\
            name: test-tools
            command: echo
            tools:
              - name: search
                description: Search
                args:
                  - name: count
                    type: integer
        """))
        policy = tmp_path / "policy.yaml"
        policy.write_text(textwrap.dedent("""\
            default: disabled
            tools:
              search:
                args:
                  count:
                    min: 1
        """))

        console, buf = _capture_console()
        rc = cmd_list(_make_args([str(config)], policy=str(policy)), console=console)
        output = buf.getvalue()
        assert rc == 0
        assert "min=" in output

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


class TestCmdRun:
    def test_cmd_run_basic(self, valid_yaml):
        """cmd_run loads configs, creates server, and calls asyncio.run."""
        args = argparse.Namespace(
            configs=[str(valid_yaml)],
            policy=None,
            log_level="WARNING",
        )
        with patch("climax.asyncio.run") as mock_arun:
            cmd_run(args)
        mock_arun.assert_called_once()

    def test_cmd_run_with_policy(self, valid_yaml, minimal_policy_yaml):
        """cmd_run with --policy loads and applies the policy."""
        args = argparse.Namespace(
            configs=[str(valid_yaml)],
            policy=str(minimal_policy_yaml),
            log_level="WARNING",
        )
        with patch("climax.asyncio.run") as mock_arun:
            with patch("climax.create_server") as mock_create:
                mock_create.return_value = MagicMock()
                cmd_run(args)
        mock_create.assert_called_once()
        # executor kwarg should be passed (from the policy)
        assert "executor" in mock_create.call_args.kwargs

    def test_cmd_run_sets_log_level(self, valid_yaml):
        """cmd_run should set logger level from args."""
        args = argparse.Namespace(
            configs=[str(valid_yaml)],
            policy=None,
            log_level="DEBUG",
        )
        with patch("climax.asyncio.run"):
            cmd_run(args)
        assert climax.logger.level == logging.DEBUG
        # Reset to avoid affecting other tests
        climax.logger.setLevel(logging.WARNING)


class TestMainSubcommands:
    def test_main_validate_subcommand(self, valid_yaml):
        """main() with 'validate' dispatches to cmd_validate."""
        with patch("climax.cmd_validate", return_value=0) as mock_validate:
            with patch("sys.argv", ["climax", "validate", str(valid_yaml)]):
                with pytest.raises(SystemExit) as exc_info:
                    main()
            assert exc_info.value.code == 0
            mock_validate.assert_called_once()

    def test_main_list_subcommand(self, valid_yaml):
        """main() with 'list' dispatches to cmd_list."""
        with patch("climax.cmd_list", return_value=0) as mock_list:
            with patch("sys.argv", ["climax", "list", str(valid_yaml)]):
                with pytest.raises(SystemExit) as exc_info:
                    main()
            assert exc_info.value.code == 0
            mock_list.assert_called_once()

    def test_main_run_subcommand(self, valid_yaml):
        """main() with 'run' dispatches to cmd_run."""
        with patch("climax.cmd_run") as mock_run:
            with patch("sys.argv", ["climax", "run", str(valid_yaml)]):
                main()
            mock_run.assert_called_once()

    def test_main_validate_with_policy(self, valid_yaml, minimal_policy_yaml):
        """main() passes --policy flag through to cmd_validate."""
        with patch("climax.cmd_validate", return_value=0) as mock_validate:
            with patch("sys.argv", [
                "climax", "validate", "--policy", str(minimal_policy_yaml), str(valid_yaml),
            ]):
                with pytest.raises(SystemExit):
                    main()
            args = mock_validate.call_args[0][0]
            assert args.policy == str(minimal_policy_yaml)


class TestLogFileEnvVar:
    def test_log_file_env_creates_handler(self, tmp_path):
        """Setting CLIMAX_LOG_FILE should add a FileHandler at DEBUG level."""
        log_file = tmp_path / "climax_test.log"

        with patch.dict(os.environ, {"CLIMAX_LOG_FILE": str(log_file)}):
            importlib.reload(climax)

        logger = climax.logger
        file_handlers = [
            h for h in logger.handlers if isinstance(h, logging.FileHandler)
        ]
        assert len(file_handlers) >= 1
        fh = file_handlers[-1]
        assert fh.level == logging.DEBUG

        # Clean up: remove the handler and reload without env var
        logger.removeHandler(fh)
        fh.close()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLIMAX_LOG_FILE", None)
            importlib.reload(climax)
