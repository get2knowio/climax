"""Tests for build_command — CLI command list construction."""

from climax import ArgType, ToolArg, ToolDef, build_command


class TestBuildCommand:
    def test_base_command_only(self):
        tool = ToolDef(name="t", description="test")
        cmd = build_command("git", tool, {})
        assert cmd == ["git"]

    def test_subcommand(self):
        tool = ToolDef(name="t", description="test", command="status")
        cmd = build_command("git", tool, {})
        assert cmd == ["git", "status"]

    def test_multi_word_subcommand(self):
        tool = ToolDef(name="t", description="test", command="bookmark list")
        cmd = build_command("app", tool, {})
        assert cmd == ["app", "bookmark", "list"]

    def test_multi_word_base_command(self):
        tool = ToolDef(name="t", description="test", command="serve")
        cmd = build_command("python -m myapp", tool, {})
        assert cmd == ["python", "-m", "myapp", "serve"]

    def test_positional_arg(self):
        tool = ToolDef(
            name="t",
            description="test",
            command="add",
            args=[ToolArg(name="path", positional=True, required=True)],
        )
        cmd = build_command("git", tool, {"path": "README.md"})
        assert cmd == ["git", "add", "README.md"]

    def test_flag_arg(self):
        tool = ToolDef(
            name="t",
            description="test",
            command="log",
            args=[ToolArg(name="count", type=ArgType.integer, flag="-n")],
        )
        cmd = build_command("git", tool, {"count": 5})
        assert cmd == ["git", "log", "-n", "5"]

    def test_boolean_true(self):
        tool = ToolDef(
            name="t",
            description="test",
            command="status",
            args=[ToolArg(name="short", type=ArgType.boolean, flag="--short")],
        )
        cmd = build_command("git", tool, {"short": True})
        assert cmd == ["git", "status", "--short"]

    def test_boolean_false_omitted(self):
        tool = ToolDef(
            name="t",
            description="test",
            command="status",
            args=[ToolArg(name="short", type=ArgType.boolean, flag="--short")],
        )
        cmd = build_command("git", tool, {"short": False})
        assert cmd == ["git", "status"]

    def test_auto_flag_generation(self):
        tool = ToolDef(
            name="t",
            description="test",
            args=[ToolArg(name="my_arg", type=ArgType.string)],
        )
        cmd = build_command("app", tool, {"my_arg": "val"})
        assert cmd == ["app", "--my-arg", "val"]

    def test_default_used_when_not_provided(self):
        tool = ToolDef(
            name="t",
            description="test",
            command="log",
            args=[ToolArg(name="count", type=ArgType.integer, flag="-n", default=10)],
        )
        cmd = build_command("git", tool, {})
        assert cmd == ["git", "log", "-n", "10"]

    def test_default_overridden(self):
        tool = ToolDef(
            name="t",
            description="test",
            command="log",
            args=[ToolArg(name="count", type=ArgType.integer, flag="-n", default=10)],
        )
        cmd = build_command("git", tool, {"count": 3})
        assert cmd == ["git", "log", "-n", "3"]

    def test_positional_before_flags(self):
        tool = ToolDef(
            name="t",
            description="test",
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
            description="test",
            args=[ToolArg(name="opt", type=ArgType.string, flag="--opt")],
        )
        cmd = build_command("app", tool, {})
        assert cmd == ["app"]

    def test_inline_flag_with_equals(self):
        """Flags ending with '=' concatenate flag and value as one token."""
        tool = ToolDef(
            name="t",
            description="test",
            command="search",
            args=[ToolArg(name="query", type=ArgType.string, flag="query=")],
        )
        cmd = build_command("obsidian", tool, {"query": "hello world"})
        assert cmd == ["obsidian", "search", "query=hello world"]

    def test_inline_flag_boolean_unaffected(self):
        """Boolean flags are not affected by the inline flag logic."""
        tool = ToolDef(
            name="t",
            description="test",
            command="files",
            args=[ToolArg(name="total", type=ArgType.boolean, flag="total")],
        )
        cmd = build_command("obsidian", tool, {"total": True})
        assert cmd == ["obsidian", "files", "total"]

    def test_inline_flag_mixed_with_regular(self):
        """Inline flags and regular flags can coexist."""
        tool = ToolDef(
            name="t",
            description="test",
            command="search",
            args=[
                ToolArg(name="query", type=ArgType.string, flag="query="),
                ToolArg(name="verbose", type=ArgType.boolean, flag="--verbose"),
                ToolArg(name="limit", type=ArgType.integer, flag="limit="),
            ],
        )
        cmd = build_command("app", tool, {"query": "test", "verbose": True, "limit": 5})
        assert cmd == ["app", "search", "query=test", "--verbose", "limit=5"]

    def test_inline_flag_default_value(self):
        """Inline flags work with default values."""
        tool = ToolDef(
            name="t",
            description="test",
            command="search",
            args=[ToolArg(name="fmt", type=ArgType.string, flag="format=", default="json")],
        )
        cmd = build_command("app", tool, {})
        assert cmd == ["app", "search", "format=json"]

    def test_cwd_arg_excluded_from_command(self):
        """Args with cwd=True should not appear in the command list."""
        tool = ToolDef(
            name="t",
            description="test",
            command="hello",
            args=[
                ToolArg(name="directory", type=ArgType.string, cwd=True),
                ToolArg(name="name", type=ArgType.string, positional=True, required=True),
            ],
        )
        cmd = build_command("echo", tool, {"directory": "/tmp/mydir", "name": "world"})
        assert cmd == ["echo", "hello", "world"]
        assert "/tmp/mydir" not in cmd

    def test_cwd_arg_with_flag_excluded(self):
        """A cwd arg that also has a flag should still be excluded."""
        tool = ToolDef(
            name="t",
            description="test",
            args=[
                ToolArg(name="workdir", type=ArgType.string, flag="--workdir", cwd=True),
                ToolArg(name="verbose", type=ArgType.boolean, flag="--verbose"),
            ],
        )
        cmd = build_command("app", tool, {"workdir": "/home/user", "verbose": True})
        assert cmd == ["app", "--verbose"]
        assert "--workdir" not in cmd

    def test_enum_value_passed_through(self):
        tool = ToolDef(
            name="t",
            description="test",
            args=[
                ToolArg(name="fmt", type=ArgType.string, flag="--format", enum=["json", "table"]),
            ],
        )
        cmd = build_command("app", tool, {"fmt": "json"})
        assert cmd == ["app", "--format", "json"]

    def test_stdin_arg_excluded_from_command(self):
        """Args with stdin=True should not appear in the command list."""
        tool = ToolDef(
            name="t",
            description="test",
            command="create",
            args=[
                ToolArg(name="path", type=ArgType.string, flag="path="),
                ToolArg(name="content", type=ArgType.string, stdin=True),
            ],
        )
        cmd = build_command("obsidian", tool, {"path": "notes/test.md", "content": "Hello world"})
        assert cmd == ["obsidian", "create", "path=notes/test.md"]
        assert "Hello world" not in cmd

    def test_stdin_positional_arg_excluded(self):
        """A stdin arg that is also positional should still be excluded."""
        tool = ToolDef(
            name="t",
            description="test",
            args=[
                ToolArg(name="data", type=ArgType.string, positional=True, stdin=True),
                ToolArg(name="verbose", type=ArgType.boolean, flag="--verbose"),
            ],
        )
        cmd = build_command("app", tool, {"data": "some content", "verbose": True})
        assert cmd == ["app", "--verbose"]
        assert "some content" not in cmd
