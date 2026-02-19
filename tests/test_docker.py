"""Tests for build_docker_prefix — Docker executor command building."""

from unittest.mock import patch

import pytest

from climax import (
    ExecutorConfig,
    ExecutorType,
    build_docker_prefix,
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
