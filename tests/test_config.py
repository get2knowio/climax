"""Tests for YAML config loading and validation."""

import pytest
from pydantic import ValidationError

from climax import CLImaxConfig, load_config, load_configs


class TestLoadConfig:
    def test_valid_config(self, valid_yaml):
        config = load_config(valid_yaml)
        assert config.name == "test-tools"
        assert config.command == "echo"
        assert len(config.tools) == 1
        assert config.tools[0].name == "hello"

    def test_minimal_config(self, minimal_yaml):
        config = load_config(minimal_yaml)
        assert config.name == "climax"  # default name
        assert config.command == "echo"
        assert len(config.tools) == 1

    def test_missing_command_raises(self, missing_command_yaml):
        with pytest.raises(ValidationError, match="command"):
            load_config(missing_command_yaml)

    def test_invalid_arg_type_raises(self, invalid_arg_type_yaml):
        with pytest.raises(ValidationError):
            load_config(invalid_arg_type_yaml)

    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.yaml")

    def test_yaml_syntax_error(self, invalid_yaml_syntax):
        with pytest.raises(Exception):
            load_config(invalid_yaml_syntax)


class TestLoadConfigs:
    def test_single_config(self, valid_yaml):
        server_name, tool_map, _configs = load_configs([valid_yaml])
        assert server_name == "test-tools"
        assert "hello" in tool_map
        assert tool_map["hello"].base_command == "echo"

    def test_multi_config_merge(self, valid_yaml, second_yaml):
        server_name, tool_map, _configs = load_configs([valid_yaml, second_yaml])
        assert server_name == "climax"  # combined name
        assert "hello" in tool_map
        assert "greet" in tool_map

    def test_duplicate_tool_overwrites(self, valid_yaml, duplicate_tool_yaml):
        _, tool_map, _configs = load_configs([valid_yaml, duplicate_tool_yaml])
        assert "hello" in tool_map
        # The second config's tool should overwrite the first
        assert tool_map["hello"].base_command == "printf"

    def test_tool_timeout_preserved(self, tmp_path):
        import textwrap

        content = textwrap.dedent("""\
            name: timeout-test
            command: echo
            tools:
              - name: slow_tool
                description: "A slow tool"
                timeout: 120
              - name: fast_tool
                description: "A fast tool"
        """)
        p = tmp_path / "timeout.yaml"
        p.write_text(content)

        _, tool_map, _configs = load_configs([p])
        assert tool_map["slow_tool"].tool.timeout == 120
        assert tool_map["fast_tool"].tool.timeout is None

    def test_env_and_working_dir_preserved(self, tmp_path):
        import textwrap

        content = textwrap.dedent("""\
            name: env-test
            command: echo
            env:
              FOO: bar
            working_dir: /tmp
            tools:
              - name: test_tool
                description: test
        """)
        p = tmp_path / "env.yaml"
        p.write_text(content)

        _, tool_map, _configs = load_configs([p])
        resolved = tool_map["test_tool"]
        assert resolved.env == {"FOO": "bar"}
        assert resolved.working_dir == "/tmp"


class TestCategoryTags:
    """Tests for optional category and tags fields on CLImaxConfig."""

    def test_both_fields(self, category_tags_yaml):
        config = load_config(category_tags_yaml)
        assert config.category == "vcs"
        assert config.tags == ["version-control", "commits"]

    def test_no_fields_backward_compat(self, no_category_tags_yaml):
        config = load_config(no_category_tags_yaml)
        assert config.category is None
        assert config.tags == []

    def test_category_only(self, category_only_yaml):
        config = load_config(category_only_yaml)
        assert config.category == "devops"
        assert config.tags == []

    def test_tags_only(self, tags_only_yaml):
        config = load_config(tags_only_yaml)
        assert config.category is None
        assert config.tags == ["automation", "ci"]

    def test_bundled_configs_have_metadata(self):
        from pathlib import Path

        bundled = Path(__file__).parent.parent / "configs" / "git.yaml"
        if not bundled.exists():
            pytest.skip("git.yaml not found")
        config = load_config(bundled)
        assert config.category == "vcs"
        assert config.tags == ["version-control", "commits", "branches"]


class TestBundledConfigs:
    """Smoke tests for bundled YAML configs shipped with the package."""

    @pytest.mark.parametrize("filename", ["git.yaml", "jj.yaml", "docker.yaml", "obsidian.yaml"])
    def test_bundled_loads(self, filename):
        from pathlib import Path

        bundled = Path(__file__).parent.parent / "configs" / filename
        if not bundled.exists():
            pytest.skip(f"{filename} not found")
        config = load_config(bundled)
        assert len(config.tools) > 0
        assert config.command
