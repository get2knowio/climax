"""Tests for policy loading and apply_policy filtering."""

import textwrap

import pytest
from pydantic import ValidationError

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
    load_policy,
)


def _build_tool_map():
    """Build a tool map with two tools for testing."""
    return {
        "hello": ResolvedTool(
            tool=ToolDef(
                name="hello",
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


class TestLoadPolicy:
    def test_minimal(self, minimal_policy_yaml):
        policy = load_policy(minimal_policy_yaml)
        assert "hello" in policy.tools
        assert policy.default == DefaultPolicy.disabled
        assert policy.executor.type == ExecutorType.local

    def test_full(self, full_policy_yaml):
        policy = load_policy(full_policy_yaml)
        assert policy.executor.type == ExecutorType.docker
        assert policy.executor.image == "alpine/git:latest"
        assert policy.executor.network == "none"
        assert policy.default == DefaultPolicy.disabled
        assert "hello" in policy.tools
        assert policy.tools["hello"].description == "Overridden description"
        assert policy.tools["hello"].args["name"].pattern == "^[a-z]+$"

    def test_docker_requires_image(self, invalid_policy_yaml):
        with pytest.raises((ValidationError, ValueError)):
            load_policy(invalid_policy_yaml)

    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_policy(tmp_path / "nonexistent.yaml")

    def test_empty_policy(self, tmp_path):
        p = tmp_path / "empty.yaml"
        p.write_text("tools: {}\n")
        policy = load_policy(p)
        assert len(policy.tools) == 0
        assert policy.default == DefaultPolicy.disabled

    def test_enabled_default(self, tmp_path):
        p = tmp_path / "enabled.yaml"
        p.write_text(textwrap.dedent("""\
            default: enabled
            tools:
              hello:
                description: Custom
        """))
        policy = load_policy(p)
        assert policy.default == DefaultPolicy.enabled


class TestApplyPolicy:
    def test_filter_disabled_default(self, minimal_policy):
        """With default=disabled, only listed tools survive."""
        tool_map = _build_tool_map()
        result = apply_policy(tool_map, minimal_policy)
        assert "hello" in result
        assert "status" not in result

    def test_enable_all_default(self):
        """With default=enabled, all tools survive."""
        tool_map = _build_tool_map()
        policy = PolicyConfig(
            default=DefaultPolicy.enabled,
            tools={},
        )
        result = apply_policy(tool_map, policy)
        assert "hello" in result
        assert "status" in result

    def test_description_override(self):
        tool_map = _build_tool_map()
        policy = PolicyConfig(
            default=DefaultPolicy.disabled,
            tools={
                "hello": ToolPolicy(description="Custom hello"),
            },
        )
        result = apply_policy(tool_map, policy)
        assert result["hello"].description_override == "Custom hello"

    def test_arg_constraints(self):
        tool_map = _build_tool_map()
        policy = PolicyConfig(
            default=DefaultPolicy.disabled,
            tools={
                "hello": ToolPolicy(
                    args={"name": ArgConstraint(pattern="^[a-z]+$")},
                ),
            },
        )
        result = apply_policy(tool_map, policy)
        assert "name" in result["hello"].arg_constraints
        assert result["hello"].arg_constraints["name"].pattern == "^[a-z]+$"

    def test_unknown_tool_warning(self, caplog):
        """Unknown tool names in policy should warn but not error."""
        tool_map = _build_tool_map()
        policy = PolicyConfig(
            default=DefaultPolicy.disabled,
            tools={
                "nonexistent": ToolPolicy(),
                "hello": ToolPolicy(),
            },
        )
        import logging
        with caplog.at_level(logging.WARNING, logger="climax"):
            result = apply_policy(tool_map, policy)
        assert "hello" in result
        assert "nonexistent" not in result
        assert any("nonexistent" in r.message for r in caplog.records)

    def test_unknown_arg_warning(self, caplog):
        """Unknown arg names in tool policy should warn but not error."""
        tool_map = _build_tool_map()
        policy = PolicyConfig(
            default=DefaultPolicy.disabled,
            tools={
                "hello": ToolPolicy(
                    args={"bogus_arg": ArgConstraint(pattern=".*")},
                ),
            },
        )
        import logging
        with caplog.at_level(logging.WARNING, logger="climax"):
            result = apply_policy(tool_map, policy)
        assert "hello" in result
        assert "bogus_arg" not in result["hello"].arg_constraints
        assert any("bogus_arg" in r.message for r in caplog.records)

    def test_empty_policy_disables_all(self):
        """Empty tools dict with default=disabled leaves nothing."""
        tool_map = _build_tool_map()
        policy = PolicyConfig(
            default=DefaultPolicy.disabled,
            tools={},
        )
        result = apply_policy(tool_map, policy)
        assert len(result) == 0

    def test_no_mutation_of_original(self):
        """apply_policy should not mutate the original tool_map."""
        tool_map = _build_tool_map()
        policy = PolicyConfig(
            default=DefaultPolicy.disabled,
            tools={"hello": ToolPolicy(description="Override")},
        )
        result = apply_policy(tool_map, policy)
        assert result["hello"].description_override == "Override"
        assert tool_map["hello"].description_override is None

    def test_enabled_default_with_constraints(self):
        """default=enabled + constraints on specific tools."""
        tool_map = _build_tool_map()
        policy = PolicyConfig(
            default=DefaultPolicy.enabled,
            tools={
                "hello": ToolPolicy(
                    args={"name": ArgConstraint(pattern="^test$")},
                ),
            },
        )
        result = apply_policy(tool_map, policy)
        assert "hello" in result
        assert "status" in result
        assert result["hello"].arg_constraints["name"].pattern == "^test$"
        assert len(result["status"].arg_constraints) == 0
