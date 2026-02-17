"""Tests for run_command — async subprocess execution."""

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from climax import run_command


def _make_proc(returncode=0, stdout=b"", stderr=b""):
    """Create a mock process with the given outputs."""
    proc = AsyncMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.kill = MagicMock()
    return proc


class TestRunCommand:
    async def test_success(self):
        proc = _make_proc(returncode=0, stdout=b"hello\n")
        with patch("climax.asyncio.create_subprocess_exec", return_value=proc):
            rc, out, err = await run_command(["echo", "hello"])
        assert rc == 0
        assert out == "hello\n"
        assert err == ""

    async def test_failure_exit_code(self):
        proc = _make_proc(returncode=1, stderr=b"error\n")
        with patch("climax.asyncio.create_subprocess_exec", return_value=proc):
            rc, out, err = await run_command(["false"])
        assert rc == 1
        assert err == "error\n"

    async def test_stderr_captured(self):
        proc = _make_proc(returncode=0, stdout=b"out\n", stderr=b"warn\n")
        with patch("climax.asyncio.create_subprocess_exec", return_value=proc):
            rc, out, err = await run_command(["cmd"])
        assert rc == 0
        assert out == "out\n"
        assert err == "warn\n"

    async def test_env_merge(self):
        proc = _make_proc(returncode=0, stdout=b"")
        with patch("climax.asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            await run_command(["cmd"], env={"MY_VAR": "42"})
        call_kwargs = mock_exec.call_args
        env = call_kwargs.kwargs.get("env") or call_kwargs[1].get("env")
        assert env["MY_VAR"] == "42"
        # Should also contain inherited env vars
        assert "PATH" in env

    async def test_working_dir(self):
        proc = _make_proc(returncode=0, stdout=b"")
        with patch("climax.asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            await run_command(["cmd"], working_dir="/tmp")
        call_kwargs = mock_exec.call_args
        cwd = call_kwargs.kwargs.get("cwd") or call_kwargs[1].get("cwd")
        assert cwd == "/tmp"

    async def test_timeout_kills_process(self):
        proc = _make_proc()
        proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        with patch("climax.asyncio.create_subprocess_exec", return_value=proc):
            rc, out, err = await run_command(["sleep", "100"], timeout=0.1)
        assert rc == -1
        assert "timed out" in err.lower()
        proc.kill.assert_called_once()

    async def test_command_not_found(self):
        with patch(
            "climax.asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError,
        ):
            rc, out, err = await run_command(["nonexistent_cmd_xyz"])
        assert rc == -1
        assert "not found" in err.lower()

    async def test_integration_echo(self):
        """Integration test with a real command."""
        rc, out, err = await run_command(["echo", "integration test"])
        assert rc == 0
        assert "integration test" in out
