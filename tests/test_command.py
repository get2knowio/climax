"""Tests for build_command — CLI command list construction."""

from climax import ArgType, ToolArg, ToolDef, build_command


class TestBuildCommand:
    def test_base_command_only(self):
        tool = ToolDef(name="t")
        cmd = build_command("git", tool, {})
        assert cmd == ["git"]

    def test_subcommand(self):
        tool = ToolDef(name="t", command="status")
        cmd = build_command("git", tool, {})
        assert cmd == ["git", "status"]

    def test_multi_word_subcommand(self):
        tool = ToolDef(name="t", command="bookmark list")
        cmd = build_command("jj", tool, {})
        assert cmd == ["jj", "bookmark", "list"]

    def test_multi_word_base_command(self):
        tool = ToolDef(name="t", command="serve")
        cmd = build_command("python -m myapp", tool, {})
        assert cmd == ["python", "-m", "myapp", "serve"]

    def test_positional_arg(self):
        tool = ToolDef(
            name="t",
            command="add",
            args=[ToolArg(name="path", positional=True, required=True)],
        )
        cmd = build_command("git", tool, {"path": "README.md"})
        assert cmd == ["git", "add", "README.md"]

    def test_flag_arg(self):
        tool = ToolDef(
            name="t",
            command="log",
            args=[ToolArg(name="count", type=ArgType.integer, flag="-n")],
        )
        cmd = build_command("git", tool, {"count": 5})
        assert cmd == ["git", "log", "-n", "5"]

    def test_boolean_true(self):
        tool = ToolDef(
            name="t",
            command="status",
            args=[ToolArg(name="short", type=ArgType.boolean, flag="--short")],
        )
        cmd = build_command("git", tool, {"short": True})
        assert cmd == ["git", "status", "--short"]

    def test_boolean_false_omitted(self):
        tool = ToolDef(
            name="t",
            command="status",
            args=[ToolArg(name="short", type=ArgType.boolean, flag="--short")],
        )
        cmd = build_command("git", tool, {"short": False})
        assert cmd == ["git", "status"]

    def test_auto_flag_generation(self):
        tool = ToolDef(
            name="t",
            args=[ToolArg(name="my_arg", type=ArgType.string)],
        )
        cmd = build_command("app", tool, {"my_arg": "val"})
        assert cmd == ["app", "--my-arg", "val"]

    def test_default_used_when_not_provided(self):
        tool = ToolDef(
            name="t",
            command="log",
            args=[ToolArg(name="count", type=ArgType.integer, flag="-n", default=10)],
        )
        cmd = build_command("git", tool, {})
        assert cmd == ["git", "log", "-n", "10"]

    def test_default_overridden(self):
        tool = ToolDef(
            name="t",
            command="log",
            args=[ToolArg(name="count", type=ArgType.integer, flag="-n", default=10)],
        )
        cmd = build_command("git", tool, {"count": 3})
        assert cmd == ["git", "log", "-n", "3"]

    def test_positional_before_flags(self):
        tool = ToolDef(
            name="t",
            command="search",
            args=[
                ToolArg(name="verbose", type=ArgType.boolean, flag="--verbose"),
                ToolArg(name="query", positional=True, required=True),
            ],
        )
        cmd = build_command("app", tool, {"query": "hello", "verbose": True})
        # positional should come before flags regardless of definition order
        assert cmd == ["app", "search", "hello", "--verbose"]

    def test_missing_optional_arg_omitted(self):
        tool = ToolDef(
            name="t",
            args=[ToolArg(name="opt", type=ArgType.string, flag="--opt")],
        )
        cmd = build_command("app", tool, {})
        assert cmd == ["app"]

    def test_enum_value_passed_through(self):
        tool = ToolDef(
            name="t",
            args=[
                ToolArg(name="fmt", type=ArgType.string, flag="--format", enum=["json", "table"]),
            ],
        )
        cmd = build_command("app", tool, {"fmt": "json"})
        assert cmd == ["app", "--format", "json"]
