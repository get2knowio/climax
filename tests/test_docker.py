"""Tests for build_docker_prefix — Docker executor command building."""

import textwrap
from unittest.mock import patch, AsyncMock

import pytest

import mcp.types as types

from climax import (
    ArgConstraint,
    ArgType,
    DefaultPolicy,
    ExecutorConfig,
    ExecutorType,
    PolicyConfig,
    ResolvedTool,
    ToolArg,
    ToolDef,
    ToolPolicy,
    apply_policy,
    build_docker_prefix,
    create_server,
    load_configs,
)


class TestBuildDockerPrefix:
    def test_minimal(self):
        """Minimal docker config: just type + image."""
        executor = ExecutorConfig(type=ExecutorType.docker, image="alpine:latest")
        prefix = build_docker_prefix(executor)
        assert prefix == ["docker", "run", "--rm", "alpine:latest"]

    def test_volumes(self):
        executor = ExecutorConfig(
            type=ExecutorType.docker,
            image="myimage",
            volumes=["/host/path:/container/path"],
        )
        prefix = build_docker_prefix(executor)
        assert "-v" in prefix
        idx = prefix.index("-v")
        assert prefix[idx + 1] == "/host/path:/container/path"

    def test_multiple_volumes(self):
        executor = ExecutorConfig(
            type=ExecutorType.docker,
            image="myimage",
            volumes=["/a:/a", "/b:/b"],
        )
        prefix = build_docker_prefix(executor)
        vol_indices = [i for i, x in enumerate(prefix) if x == "-v"]
        assert len(vol_indices) == 2
        assert prefix[vol_indices[0] + 1] == "/a:/a"
        assert prefix[vol_indices[1] + 1] == "/b:/b"

    def test_network(self):
        executor = ExecutorConfig(
            type=ExecutorType.docker,
            image="myimage",
            network="none",
        )
        prefix = build_docker_prefix(executor)
        assert "--network" in prefix
        idx = prefix.index("--network")
        assert prefix[idx + 1] == "none"

    def test_working_dir(self):
        executor = ExecutorConfig(
            type=ExecutorType.docker,
            image="myimage",
            working_dir="/workspace",
        )
        prefix = build_docker_prefix(executor)
        assert "-w" in prefix
        idx = prefix.index("-w")
        assert prefix[idx + 1] == "/workspace"

    def test_full_config(self):
        executor = ExecutorConfig(
            type=ExecutorType.docker,
            image="alpine/git:latest",
            volumes=["/project:/workspace"],
            working_dir="/workspace",
            network="none",
        )
        prefix = build_docker_prefix(executor)
        assert prefix[0:3] == ["docker", "run", "--rm"]
        assert "-v" in prefix
        assert "--network" in prefix
        assert "-w" in prefix
        # Image should be last
        assert prefix[-1] == "alpine/git:latest"

    def test_env_var_expansion(self):
        """Volume strings should have environment variables expanded."""
        executor = ExecutorConfig(
            type=ExecutorType.docker,
            image="myimage",
            volumes=["${HOME}:/home"],
        )
        with patch.dict("os.environ", {"HOME": "/Users/test"}):
            prefix = build_docker_prefix(executor)
        idx = prefix.index("-v")
        assert prefix[idx + 1] == "/Users/test:/home"

    def test_prefix_plus_command(self):
        """Verify prefix can be concatenated with a tool command."""
        executor = ExecutorConfig(
            type=ExecutorType.docker,
            image="alpine/git:latest",
        )
        prefix = build_docker_prefix(executor)
        full_cmd = prefix + ["git", "status"]
        assert full_cmd == ["docker", "run", "--rm", "alpine/git:latest", "git", "status"]


def _unwrap(result):
    """Unwrap ServerResult wrapper if present."""
    return result.root if hasattr(result, "root") else result


class TestDockerE2E:
    """End-to-end: YAML config → policy with Docker executor → server → call_tool."""

    async def test_docker_e2e_full_pipeline(self, tmp_path):
        """Load config + Docker policy, call tool, verify docker prefix in command."""
        config_file = tmp_path / "tools.yaml"
        config_file.write_text(textwrap.dedent("""\
            name: mytools
            command: git
            tools:
              - name: git_status
                description: Show git status
                command: status
        """))

        _, tool_map = load_configs([str(config_file)])
        policy = PolicyConfig(
            executor=ExecutorConfig(type=ExecutorType.docker, image="alpine/git:latest"),
            default=DefaultPolicy.disabled,
            tools={"git_status": ToolPolicy()},
        )
        tool_map = apply_policy(tool_map, policy)
        server = create_server("mytools", tool_map, executor=policy.executor)

        with patch("climax.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "On branch main\n", "")

            handlers = server.request_handlers
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(name="git_status", arguments={}),
            )
            result = _unwrap(await handlers[types.CallToolRequest](request))

        cmd = mock_run.call_args[0][0]
        assert cmd[:4] == ["docker", "run", "--rm", "alpine/git:latest"]
        assert "git" in cmd[4:]
        assert "status" in cmd
        assert "On branch main" in result.content[0].text

    async def test_docker_e2e_volumes_and_network(self, tmp_path):
        """Docker executor with volumes, network, working_dir — all flags in command."""
        config_file = tmp_path / "tools.yaml"
        config_file.write_text(textwrap.dedent("""\
            name: mytools
            command: ls
            tools:
              - name: list_files
                description: List files
        """))

        _, tool_map = load_configs([str(config_file)])
        policy = PolicyConfig(
            executor=ExecutorConfig(
                type=ExecutorType.docker,
                image="alpine:latest",
                volumes=["/host:/container"],
                network="none",
                working_dir="/workspace",
            ),
            default=DefaultPolicy.disabled,
            tools={"list_files": ToolPolicy()},
        )
        tool_map = apply_policy(tool_map, policy)
        server = create_server("mytools", tool_map, executor=policy.executor)

        with patch("climax.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "file1\nfile2\n", "")

            handlers = server.request_handlers
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(name="list_files", arguments={}),
            )
            _unwrap(await handlers[types.CallToolRequest](request))

        cmd = mock_run.call_args[0][0]
        assert "-v" in cmd
        assert "/host:/container" in cmd
        assert "--network" in cmd
        assert "none" in cmd
        assert "-w" in cmd
        assert "/workspace" in cmd

    async def test_docker_e2e_policy_constraints_with_docker(self, tmp_path):
        """Docker + arg constraints — constraint rejection happens before run_command."""
        config_file = tmp_path / "tools.yaml"
        config_file.write_text(textwrap.dedent("""\
            name: mytools
            command: echo
            tools:
              - name: greet
                description: Greet
                args:
                  - name: name
                    type: string
                    positional: true
        """))

        _, tool_map = load_configs([str(config_file)])
        policy = PolicyConfig(
            executor=ExecutorConfig(type=ExecutorType.docker, image="alpine:latest"),
            default=DefaultPolicy.disabled,
            tools={"greet": ToolPolicy(args={"name": ArgConstraint(pattern="^[a-z]+$")})},
        )
        tool_map = apply_policy(tool_map, policy)
        server = create_server("mytools", tool_map, executor=policy.executor)

        with patch("climax.run_command", new_callable=AsyncMock) as mock_run:
            handlers = server.request_handlers
            request = types.CallToolRequest(
                method="tools/call",
                params=types.CallToolRequestParams(name="greet", arguments={"name": "INVALID"}),
            )
            result = _unwrap(await handlers[types.CallToolRequest](request))

        assert "Policy validation failed" in result.content[0].text
        mock_run.assert_not_called()

    async def test_docker_e2e_multiple_tools(self, tmp_path):
        """Multiple tools through Docker executor — each gets the prefix."""
        config_file = tmp_path / "tools.yaml"
        config_file.write_text(textwrap.dedent("""\
            name: mytools
            command: app
            tools:
              - name: tool_a
                description: Tool A
                command: alpha
              - name: tool_b
                description: Tool B
                command: beta
        """))

        _, tool_map = load_configs([str(config_file)])
        policy = PolicyConfig(
            executor=ExecutorConfig(type=ExecutorType.docker, image="myimg:1.0"),
            default=DefaultPolicy.disabled,
            tools={"tool_a": ToolPolicy(), "tool_b": ToolPolicy()},
        )
        tool_map = apply_policy(tool_map, policy)
        server = create_server("mytools", tool_map, executor=policy.executor)

        handlers = server.request_handlers

        for tool_name, expected_subcmd in [("tool_a", "alpha"), ("tool_b", "beta")]:
            with patch("climax.run_command", new_callable=AsyncMock) as mock_run:
                mock_run.return_value = (0, "ok\n", "")

                request = types.CallToolRequest(
                    method="tools/call",
                    params=types.CallToolRequestParams(name=tool_name, arguments={}),
                )
                _unwrap(await handlers[types.CallToolRequest](request))

            cmd = mock_run.call_args[0][0]
            assert cmd[:4] == ["docker", "run", "--rm", "myimg:1.0"]
            assert expected_subcmd in cmd
