"""Shared fixtures for CLImax tests."""

import textwrap

import pytest

from climax import (
    ArgConstraint,
    ArgType,
    CLImaxConfig,
    DefaultPolicy,
    ExecutorConfig,
    ExecutorType,
    PolicyConfig,
    ToolArg,
    ToolDef,
    ToolPolicy,
)


# ---------------------------------------------------------------------------
# Inline model fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def string_arg():
    return ToolArg(name="path", description="File path", type=ArgType.string, required=True, positional=True)


@pytest.fixture
def int_arg():
    return ToolArg(name="count", description="Number of items", type=ArgType.integer, flag="-n")


@pytest.fixture
def bool_arg():
    return ToolArg(name="verbose", description="Verbose output", type=ArgType.boolean, flag="--verbose")


@pytest.fixture
def cwd_arg():
    return ToolArg(name="directory", description="Working directory", type=ArgType.string, cwd=True)


@pytest.fixture
def stdin_arg():
    return ToolArg(name="content", description="Content to pipe via stdin", type=ArgType.string, stdin=True)


@pytest.fixture
def enum_arg():
    return ToolArg(name="format", description="Output format", type=ArgType.string, flag="--format", enum=["json", "table", "csv"])


@pytest.fixture
def simple_tool(string_arg, bool_arg):
    return ToolDef(name="my_tool", description="A test tool", command="do stuff", args=[string_arg, bool_arg])


@pytest.fixture
def simple_config(simple_tool):
    return CLImaxConfig(name="test-cli", description="Test CLI", command="testcmd", tools=[simple_tool])


# ---------------------------------------------------------------------------
# YAML file fixtures (use tmp_path)
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_yaml(tmp_path):
    content = textwrap.dedent("""\
        name: test-tools
        command: echo
        tools:
          - name: hello
            description: Say hello
            command: hello
            args:
              - name: name
                type: string
                required: true
                positional: true
    """)
    p = tmp_path / "valid.yaml"
    p.write_text(content)
    return p


@pytest.fixture
def minimal_yaml(tmp_path):
    content = textwrap.dedent("""\
        command: echo
        tools:
          - name: ping
            description: Ping
    """)
    p = tmp_path / "minimal.yaml"
    p.write_text(content)
    return p


@pytest.fixture
def second_yaml(tmp_path):
    """A second config for multi-config merge tests."""
    content = textwrap.dedent("""\
        name: extra-tools
        command: printf
        tools:
          - name: greet
            description: Greet someone
            command: "%s"
            args:
              - name: msg
                type: string
                positional: true
    """)
    p = tmp_path / "second.yaml"
    p.write_text(content)
    return p


@pytest.fixture
def duplicate_tool_yaml(tmp_path):
    """Config that defines a tool with the same name as valid_yaml's 'hello'."""
    content = textwrap.dedent("""\
        name: dup-tools
        command: printf
        tools:
          - name: hello
            description: Duplicate hello
    """)
    p = tmp_path / "dup.yaml"
    p.write_text(content)
    return p


@pytest.fixture
def invalid_yaml_syntax(tmp_path):
    p = tmp_path / "bad_syntax.yaml"
    p.write_text("name: foo\n  bad indent: [")
    return p


@pytest.fixture
def missing_command_yaml(tmp_path):
    content = textwrap.dedent("""\
        name: broken
        tools:
          - name: oops
            description: This should fail
    """)
    p = tmp_path / "no_command.yaml"
    p.write_text(content)
    return p


@pytest.fixture
def invalid_arg_type_yaml(tmp_path):
    content = textwrap.dedent("""\
        name: broken
        command: echo
        tools:
          - name: oops
            description: This should fail
            args:
              - name: x
                type: banana
    """)
    p = tmp_path / "bad_type.yaml"
    p.write_text(content)
    return p


@pytest.fixture
def global_args_yaml(tmp_path):
    """Config with global_args defined at config level."""
    content = textwrap.dedent("""\
        name: vault-cli
        command: mycli
        global_args:
          - name: vault
            type: string
            flag: "vault="
            default: "$MY_VAULT"
        tools:
          - name: do_thing
            description: Do a thing
            args:
              - name: query
                type: string
                flag: "query="
    """)
    p = tmp_path / "global_args.yaml"
    p.write_text(content)
    return p


@pytest.fixture
def category_tags_yaml(tmp_path):
    """Config with both category and tags fields."""
    content = textwrap.dedent("""\
        name: tagged-cli
        command: echo
        category: vcs
        tags: ["version-control", "commits"]
        tools:
          - name: do_thing
            description: Do a thing
    """)
    p = tmp_path / "category_tags.yaml"
    p.write_text(content)
    return p


@pytest.fixture
def category_only_yaml(tmp_path):
    """Config with category but no tags."""
    content = textwrap.dedent("""\
        name: cat-only
        command: echo
        category: devops
        tools:
          - name: deploy
            description: Deploy something
    """)
    p = tmp_path / "category_only.yaml"
    p.write_text(content)
    return p


@pytest.fixture
def tags_only_yaml(tmp_path):
    """Config with tags but no category."""
    content = textwrap.dedent("""\
        name: tags-only
        command: echo
        tags: ["automation", "ci"]
        tools:
          - name: build
            description: Build something
    """)
    p = tmp_path / "tags_only.yaml"
    p.write_text(content)
    return p


@pytest.fixture
def no_category_tags_yaml(tmp_path):
    """Config without category or tags (backward compat)."""
    content = textwrap.dedent("""\
        name: plain-cli
        command: echo
        tools:
          - name: plain_tool
            description: A plain tool
    """)
    p = tmp_path / "no_category_tags.yaml"
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# Policy model fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_policy():
    return PolicyConfig(
        tools={"hello": ToolPolicy()},
    )


@pytest.fixture
def full_policy():
    return PolicyConfig(
        executor=ExecutorConfig(
            type=ExecutorType.docker,
            image="alpine/git:latest",
            volumes=["${HOME}:/workspace"],
            working_dir="/workspace",
            network="none",
        ),
        default=DefaultPolicy.disabled,
        tools={
            "hello": ToolPolicy(
                description="Overridden description",
                args={"name": ArgConstraint(pattern="^[a-z]+$")},
            ),
        },
    )


@pytest.fixture
def enabled_default_policy():
    return PolicyConfig(
        default=DefaultPolicy.enabled,
        tools={
            "hello": ToolPolicy(
                description="Custom desc",
                args={"name": ArgConstraint(pattern="^\\w+$")},
            ),
        },
    )


# ---------------------------------------------------------------------------
# Policy YAML file fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_policy_yaml(tmp_path):
    content = textwrap.dedent("""\
        tools:
          hello: {}
    """)
    p = tmp_path / "minimal_policy.yaml"
    p.write_text(content)
    return p


@pytest.fixture
def full_policy_yaml(tmp_path):
    content = textwrap.dedent("""\
        executor:
          type: docker
          image: alpine/git:latest
          volumes:
            - "${HOME}:/workspace"
          working_dir: /workspace
          network: none
        default: disabled
        tools:
          hello:
            description: "Overridden description"
            args:
              name:
                pattern: "^[a-z]+$"
    """)
    p = tmp_path / "full_policy.yaml"
    p.write_text(content)
    return p


@pytest.fixture
def invalid_policy_yaml(tmp_path):
    """Policy with docker executor but no image — should fail validation."""
    content = textwrap.dedent("""\
        executor:
          type: docker
        tools:
          hello: {}
    """)
    p = tmp_path / "invalid_policy.yaml"
    p.write_text(content)
    return p


@pytest.fixture
def constraint_policy_yaml(tmp_path):
    """Policy with argument constraints for testing validation."""
    content = textwrap.dedent("""\
        default: disabled
        tools:
          hello:
            args:
              name:
                pattern: "^[a-z]+$"
          coreutils_echo:
            args:
              message:
                pattern: "^[\\\\w\\\\s]+$"
    """)
    p = tmp_path / "constraint_policy.yaml"
    p.write_text(content)
    return p
