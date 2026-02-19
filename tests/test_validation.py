"""Tests for validate_arguments — policy constraint checking."""

import pytest

from climax import (
    ArgConstraint,
    ArgType,
    ToolArg,
    ToolDef,
    validate_arguments,
)


def _make_tool(*args_list):
    """Helper to build a ToolDef with given ToolArgs."""
    return ToolDef(name="test", description="Test", args=list(args_list))


class TestValidateArguments:
    def test_pattern_match(self):
        tool = _make_tool(ToolArg(name="path", type=ArgType.string))
        constraints = {"path": ArgConstraint(pattern="^src/.*")}
        errors = validate_arguments({"path": "src/main.py"}, tool, constraints)
        assert errors == []

    def test_pattern_mismatch(self):
        tool = _make_tool(ToolArg(name="path", type=ArgType.string))
        constraints = {"path": ArgConstraint(pattern="^src/.*")}
        errors = validate_arguments({"path": "lib/evil.py"}, tool, constraints)
        assert len(errors) == 1
        assert "pattern" in errors[0]
        assert "lib/evil.py" in errors[0]

    def test_fullmatch_semantics(self):
        """Pattern must match the entire string, not just a substring."""
        tool = _make_tool(ToolArg(name="name", type=ArgType.string))
        constraints = {"name": ArgConstraint(pattern="[a-z]+")}
        # fullmatch: "abc" should match, "abc123" should not
        assert validate_arguments({"name": "abc"}, tool, constraints) == []
        errors = validate_arguments({"name": "abc123"}, tool, constraints)
        assert len(errors) == 1

    def test_min_pass(self):
        tool = _make_tool(ToolArg(name="count", type=ArgType.integer))
        constraints = {"count": ArgConstraint(min=1)}
        errors = validate_arguments({"count": 5}, tool, constraints)
        assert errors == []

    def test_min_fail(self):
        tool = _make_tool(ToolArg(name="count", type=ArgType.integer))
        constraints = {"count": ArgConstraint(min=1)}
        errors = validate_arguments({"count": 0}, tool, constraints)
        assert len(errors) == 1
        assert "minimum" in errors[0]

    def test_max_pass(self):
        tool = _make_tool(ToolArg(name="count", type=ArgType.integer))
        constraints = {"count": ArgConstraint(max=100)}
        errors = validate_arguments({"count": 50}, tool, constraints)
        assert errors == []

    def test_max_fail(self):
        tool = _make_tool(ToolArg(name="count", type=ArgType.integer))
        constraints = {"count": ArgConstraint(max=100)}
        errors = validate_arguments({"count": 150}, tool, constraints)
        assert len(errors) == 1
        assert "maximum" in errors[0]

    def test_min_max_combined(self):
        tool = _make_tool(ToolArg(name="count", type=ArgType.integer))
        constraints = {"count": ArgConstraint(min=1, max=100)}
        assert validate_arguments({"count": 50}, tool, constraints) == []
        assert validate_arguments({"count": 1}, tool, constraints) == []
        assert validate_arguments({"count": 100}, tool, constraints) == []
        assert len(validate_arguments({"count": 0}, tool, constraints)) == 1
        assert len(validate_arguments({"count": 101}, tool, constraints)) == 1

    def test_missing_arg_skipped(self):
        """Args not present in the arguments dict should be skipped."""
        tool = _make_tool(ToolArg(name="path", type=ArgType.string))
        constraints = {"path": ArgConstraint(pattern="^src/")}
        errors = validate_arguments({}, tool, constraints)
        assert errors == []

    def test_multiple_errors(self):
        tool = _make_tool(
            ToolArg(name="path", type=ArgType.string),
            ToolArg(name="count", type=ArgType.integer),
        )
        constraints = {
            "path": ArgConstraint(pattern="^src/"),
            "count": ArgConstraint(max=10),
        }
        errors = validate_arguments({"path": "lib/x", "count": 20}, tool, constraints)
        assert len(errors) == 2

    def test_pattern_on_non_string_skipped(self):
        """Pattern constraint on a non-string value should be skipped."""
        tool = _make_tool(ToolArg(name="count", type=ArgType.integer))
        constraints = {"count": ArgConstraint(pattern="^\\d+$")}
        errors = validate_arguments({"count": 42}, tool, constraints)
        assert errors == []

    def test_min_on_non_numeric_skipped(self):
        """Min/max on non-numeric value should be skipped."""
        tool = _make_tool(ToolArg(name="name", type=ArgType.string))
        constraints = {"name": ArgConstraint(min=1)}
        errors = validate_arguments({"name": "hello"}, tool, constraints)
        assert errors == []

    def test_boundary_values(self):
        """Exact boundary values should pass."""
        tool = _make_tool(ToolArg(name="n", type=ArgType.number))
        constraints = {"n": ArgConstraint(min=0.0, max=1.0)}
        assert validate_arguments({"n": 0.0}, tool, constraints) == []
        assert validate_arguments({"n": 1.0}, tool, constraints) == []
        assert validate_arguments({"n": 0.5}, tool, constraints) == []
