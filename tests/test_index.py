"""Tests for ToolIndex: search, summary, and get methods."""

import time

import pytest

from climax import (
    CLImaxConfig,
    ToolArg,
    ArgType,
    ToolDef,
    ToolIndex,
    load_config,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def git_config():
    """A git-like config with category and tags."""
    return CLImaxConfig(
        name="git-tools",
        description="MCP tools for Git",
        command="git",
        category="vcs",
        tags=["version-control", "commits"],
        tools=[
            ToolDef(
                name="git_status",
                description="Show the working tree status",
                command="status",
            ),
            ToolDef(
                name="git_commit",
                description="Record changes to the repository",
                command="commit",
                args=[
                    ToolArg(name="message", description="Commit message", type=ArgType.string, required=True, flag="-m"),
                ],
            ),
            ToolDef(
                name="git_branch",
                description="List, create, or delete branches",
                command="branch",
            ),
        ],
    )


@pytest.fixture
def docker_config():
    """A docker-like config with a different category."""
    return CLImaxConfig(
        name="docker-tools",
        description="MCP tools for Docker",
        command="docker",
        category="containers",
        tags=["devops", "deployment"],
        tools=[
            ToolDef(
                name="docker_ps",
                description="List running containers",
                command="ps",
            ),
            ToolDef(
                name="docker_build",
                description="Build an image from a Dockerfile",
                command="build",
            ),
        ],
    )


@pytest.fixture
def plain_config():
    """A config without category or tags."""
    return CLImaxConfig(
        name="plain-cli",
        description="A plain CLI",
        command="echo",
        tools=[
            ToolDef(
                name="echo_msg",
                description="Echo a message",
                command="",
            ),
        ],
    )


@pytest.fixture
def index(git_config, docker_config, plain_config):
    """A ToolIndex built from multiple configs."""
    return ToolIndex.from_configs([git_config, docker_config, plain_config])


@pytest.fixture
def git_only_index(git_config):
    """A ToolIndex built from a single git config."""
    return ToolIndex.from_configs([git_config])


# ---------------------------------------------------------------------------
# TestSearch
# ---------------------------------------------------------------------------


class TestSearch:
    """Tests for ToolIndex.search()."""

    def test_keyword_match_name(self, index):
        results = index.search(query="git_status")
        assert len(results) == 1
        assert results[0].tool_name == "git_status"

    def test_keyword_match_description(self, index):
        results = index.search(query="dockerfile")
        assert len(results) == 1
        assert results[0].tool_name == "docker_build"

    def test_keyword_match_tags(self, index):
        results = index.search(query="version-control")
        assert len(results) == 3  # All git tools inherit the tag
        for r in results:
            assert r.cli_name == "git-tools"

    def test_keyword_match_category(self, index):
        results = index.search(query="vcs")
        assert len(results) == 3  # All git tools have category "vcs"

    def test_keyword_match_cli_name(self, index):
        results = index.search(query="docker-tools")
        assert len(results) == 2

    def test_case_insensitive_query(self, index):
        lower = index.search(query="git_status")
        upper = index.search(query="GIT_STATUS")
        mixed = index.search(query="Git_Status")
        assert len(lower) == len(upper) == len(mixed) == 1
        assert lower[0].tool_name == upper[0].tool_name == mixed[0].tool_name

    def test_category_exact_filter(self, index):
        results = index.search(category="vcs")
        assert len(results) == 3
        for r in results:
            assert r.category == "vcs"

    def test_category_case_insensitive(self, index):
        results = index.search(category="VCS")
        assert len(results) == 3

    def test_category_no_match(self, index):
        results = index.search(category="nonexistent")
        assert results == []

    def test_cli_exact_filter(self, index):
        results = index.search(cli="docker-tools")
        assert len(results) == 2
        for r in results:
            assert r.cli_name == "docker-tools"

    def test_cli_case_insensitive(self, index):
        results = index.search(cli="DOCKER-TOOLS")
        assert len(results) == 2

    def test_cli_no_match(self, index):
        results = index.search(cli="nonexistent")
        assert results == []

    def test_combined_filters_and_logic(self, index):
        # query matches git tools, category filters to vcs
        results = index.search(query="branch", category="vcs")
        assert len(results) == 1
        assert results[0].tool_name == "git_branch"

    def test_combined_query_and_cli(self, index):
        results = index.search(query="build", cli="docker-tools")
        assert len(results) == 1
        assert results[0].tool_name == "docker_build"

    def test_combined_all_filters(self, index):
        results = index.search(query="record changes", category="vcs", cli="git-tools")
        assert len(results) == 1
        assert results[0].tool_name == "git_commit"

    def test_combined_filters_no_match(self, index):
        # query matches docker, but category filters to vcs — no overlap
        results = index.search(query="docker", category="vcs")
        assert results == []

    def test_limit_parameter(self, index):
        results = index.search(limit=2)
        assert len(results) == 2

    def test_limit_zero(self, index):
        results = index.search(limit=0)
        assert results == []

    def test_limit_larger_than_results(self, index):
        results = index.search(limit=100)
        assert len(results) == 6  # total tools in index

    def test_no_matches(self, index):
        results = index.search(query="zzzznonexistent")
        assert results == []

    def test_browse_mode_all_none(self, index):
        results = index.search()
        assert len(results) == 6  # all tools, default limit=10

    def test_special_characters_literal(self, index):
        # Special regex characters should be treated as literal
        results = index.search(query=".*")
        assert results == []

    def test_special_characters_brackets(self, index):
        results = index.search(query="[a-z]")
        assert results == []

    def test_very_long_query_no_match(self, index):
        """Edge case: very long query strings still work correctly."""
        long_query = "x" * 10000
        results = index.search(query=long_query)
        assert results == []

    def test_long_query_substring_matches(self, index):
        """Edge case: long query containing a valid substring still matches."""
        results = index.search(query="Show the working tree status")
        assert len(results) == 1
        assert results[0].tool_name == "git_status"

    def test_insertion_order(self, index):
        results = index.search(limit=6)
        expected_order = [
            "git_status", "git_commit", "git_branch",
            "docker_ps", "docker_build",
            "echo_msg",
        ]
        assert [r.tool_name for r in results] == expected_order

    def test_entry_has_input_schema(self, index):
        results = index.search(query="git_commit")
        assert len(results) == 1
        schema = results[0].input_schema
        assert schema["type"] == "object"
        assert "message" in schema["properties"]
        assert "message" in schema["required"]

    def test_entry_fields_populated(self, index):
        results = index.search(query="git_status")
        entry = results[0]
        assert entry.tool_name == "git_status"
        assert entry.description == "Show the working tree status"
        assert entry.cli_name == "git-tools"
        assert entry.category == "vcs"
        assert entry.tags == ["version-control", "commits"]

    def test_plain_config_no_category(self, index):
        results = index.search(query="echo_msg")
        assert len(results) == 1
        assert results[0].category is None
        assert results[0].tags == []

    def test_category_filter_excludes_none(self, index):
        # plain_config has category=None, should not match category filter
        results = index.search(category="containers")
        assert all(r.cli_name == "docker-tools" for r in results)

    def test_category_rejects_substring(self, index):
        """FR-007: category filter uses exact match, not substring."""
        results = index.search(category="vc")  # substring of "vcs"
        assert results == []

    def test_cli_rejects_substring(self, index):
        """FR-007: cli filter uses exact match, not substring."""
        results = index.search(cli="docker")  # substring of "docker-tools"
        assert results == []


class TestSearchDuplicates:
    """Tests for duplicate tool name handling in the index."""

    def test_duplicate_last_wins(self):
        config1 = CLImaxConfig(
            name="first",
            command="echo",
            tools=[ToolDef(name="shared", description="First version")],
        )
        config2 = CLImaxConfig(
            name="second",
            command="printf",
            tools=[ToolDef(name="shared", description="Second version")],
        )
        index = ToolIndex.from_configs([config1, config2])
        results = index.search(query="shared")
        assert len(results) == 1
        assert results[0].description == "Second version"
        assert results[0].cli_name == "second"

    def test_duplicate_old_entry_removed(self):
        config1 = CLImaxConfig(
            name="first",
            command="echo",
            tools=[
                ToolDef(name="unique_a", description="A"),
                ToolDef(name="shared", description="First version"),
            ],
        )
        config2 = CLImaxConfig(
            name="second",
            command="printf",
            tools=[ToolDef(name="shared", description="Second version")],
        )
        index = ToolIndex.from_configs([config1, config2])
        all_results = index.search(limit=100)
        names = [r.tool_name for r in all_results]
        assert names.count("shared") == 1
        # shared should be at the end (last inserted)
        assert names[-1] == "shared"

    def test_duplicate_resolved_tool_updated(self):
        config1 = CLImaxConfig(
            name="first",
            command="echo",
            tools=[ToolDef(name="shared", description="First")],
        )
        config2 = CLImaxConfig(
            name="second",
            command="printf",
            tools=[ToolDef(name="shared", description="Second")],
        )
        index = ToolIndex.from_configs([config1, config2])
        resolved = index.get("shared")
        assert resolved is not None
        assert resolved.base_command == "printf"


class TestSearchPerformance:
    """Performance tests for ToolIndex.search()."""

    def test_bundled_configs_search_under_50ms(self):
        """SC-003: Search across all bundled configs completes in <50ms."""
        from pathlib import Path

        configs_dir = Path(__file__).parent.parent / "configs"
        config_files = sorted(configs_dir.glob("*.yaml"))
        if not config_files:
            pytest.skip("No bundled configs found")

        configs = [load_config(p) for p in config_files]
        index = ToolIndex.from_configs(configs)

        # Verify we have a reasonable number of tools
        total_tools = sum(c.tool_count for c in index.summary())
        assert total_tools >= 50, f"Expected 50+ tools, got {total_tools}"

        # Time the search
        start = time.monotonic()
        for _ in range(100):  # 100 iterations for more stable timing
            index.search(query="status")
        elapsed = (time.monotonic() - start) / 100

        assert elapsed < 0.050, f"Search took {elapsed:.4f}s, expected <50ms"


# ---------------------------------------------------------------------------
# TestSummary
# ---------------------------------------------------------------------------


class TestSummary:
    """Tests for ToolIndex.summary()."""

    def test_summary_count(self, index):
        summaries = index.summary()
        assert len(summaries) == 3  # git, docker, plain

    def test_summary_tool_counts(self, index):
        summaries = index.summary()
        by_name = {s.name: s for s in summaries}
        assert by_name["git-tools"].tool_count == 3
        assert by_name["docker-tools"].tool_count == 2
        assert by_name["plain-cli"].tool_count == 1

    def test_summary_with_category(self, index):
        summaries = index.summary()
        by_name = {s.name: s for s in summaries}
        assert by_name["git-tools"].category == "vcs"
        assert by_name["docker-tools"].category == "containers"
        assert by_name["plain-cli"].category is None

    def test_summary_with_tags(self, index):
        summaries = index.summary()
        by_name = {s.name: s for s in summaries}
        assert by_name["git-tools"].tags == ["version-control", "commits"]
        assert by_name["docker-tools"].tags == ["devops", "deployment"]
        assert by_name["plain-cli"].tags == []

    def test_summary_description(self, index):
        summaries = index.summary()
        by_name = {s.name: s for s in summaries}
        assert by_name["git-tools"].description == "MCP tools for Git"

    def test_summary_returns_copy(self, index):
        """Summary returns a new list, not a reference to internal state."""
        s1 = index.summary()
        s2 = index.summary()
        assert s1 is not s2

    def test_summary_empty_index(self):
        index = ToolIndex.from_configs([])
        assert index.summary() == []

    def test_summary_order_matches_config_order(self, git_config, docker_config, plain_config):
        index = ToolIndex.from_configs([docker_config, git_config, plain_config])
        summaries = index.summary()
        assert [s.name for s in summaries] == ["docker-tools", "git-tools", "plain-cli"]


# ---------------------------------------------------------------------------
# TestGet
# ---------------------------------------------------------------------------


class TestGet:
    """Tests for ToolIndex.get()."""

    def test_get_existing_tool(self, index):
        resolved = index.get("git_status")
        assert resolved is not None
        assert resolved.base_command == "git"
        assert resolved.tool.name == "git_status"
        assert resolved.tool.command == "status"

    def test_get_returns_correct_env(self):
        config = CLImaxConfig(
            name="env-test",
            command="echo",
            env={"FOO": "bar"},
            working_dir="/tmp",
            tools=[ToolDef(name="test_tool", description="test")],
        )
        index = ToolIndex.from_configs([config])
        resolved = index.get("test_tool")
        assert resolved is not None
        assert resolved.env == {"FOO": "bar"}
        assert resolved.working_dir == "/tmp"

    def test_get_returns_args(self, index):
        resolved = index.get("git_commit")
        assert resolved is not None
        assert len(resolved.tool.args) == 1
        assert resolved.tool.args[0].name == "message"

    def test_get_nonexistent_returns_none(self, index):
        assert index.get("nonexistent_tool") is None

    def test_get_empty_string_returns_none(self, index):
        assert index.get("") is None


# ---------------------------------------------------------------------------
# TestFromConfigs
# ---------------------------------------------------------------------------


class TestFromConfigs:
    """Tests for ToolIndex.from_configs() construction."""

    def test_empty_configs_list(self):
        index = ToolIndex.from_configs([])
        assert index.search() == []
        assert index.summary() == []
        assert index.get("anything") is None

    def test_single_config(self, git_config):
        index = ToolIndex.from_configs([git_config])
        assert len(index.search(limit=100)) == 3
        assert len(index.summary()) == 1

    def test_multiple_configs(self, git_config, docker_config):
        index = ToolIndex.from_configs([git_config, docker_config])
        assert len(index.search(limit=100)) == 5
        assert len(index.summary()) == 2
