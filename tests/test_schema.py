"""Tests for build_input_schema — JSON Schema generation."""

from climax import ArgType, ToolArg, build_input_schema


class TestBuildInputSchema:
    def test_empty_args(self):
        schema = build_input_schema([])
        assert schema == {"type": "object", "properties": {}}

    def test_string_arg(self):
        args = [ToolArg(name="path", type=ArgType.string, description="A path")]
        schema = build_input_schema(args)
        assert schema["properties"]["path"] == {"type": "string", "description": "A path"}
        assert "required" not in schema

    def test_integer_arg(self):
        args = [ToolArg(name="count", type=ArgType.integer)]
        schema = build_input_schema(args)
        assert schema["properties"]["count"]["type"] == "integer"

    def test_number_arg(self):
        args = [ToolArg(name="ratio", type=ArgType.number)]
        schema = build_input_schema(args)
        assert schema["properties"]["ratio"]["type"] == "number"

    def test_boolean_arg(self):
        args = [ToolArg(name="verbose", type=ArgType.boolean)]
        schema = build_input_schema(args)
        assert schema["properties"]["verbose"]["type"] == "boolean"

    def test_all_four_types(self):
        args = [
            ToolArg(name="s", type=ArgType.string),
            ToolArg(name="i", type=ArgType.integer),
            ToolArg(name="n", type=ArgType.number),
            ToolArg(name="b", type=ArgType.boolean),
        ]
        schema = build_input_schema(args)
        assert set(schema["properties"].keys()) == {"s", "i", "n", "b"}
        assert schema["properties"]["s"]["type"] == "string"
        assert schema["properties"]["i"]["type"] == "integer"
        assert schema["properties"]["n"]["type"] == "number"
        assert schema["properties"]["b"]["type"] == "boolean"

    def test_required_list(self):
        args = [
            ToolArg(name="a", required=True),
            ToolArg(name="b", required=False),
            ToolArg(name="c", required=True),
        ]
        schema = build_input_schema(args)
        assert schema["required"] == ["a", "c"]

    def test_default_value(self):
        args = [ToolArg(name="count", type=ArgType.integer, default=10)]
        schema = build_input_schema(args)
        assert schema["properties"]["count"]["default"] == 10

    def test_enum_values(self):
        args = [ToolArg(name="fmt", enum=["json", "csv"])]
        schema = build_input_schema(args)
        assert schema["properties"]["fmt"]["enum"] == ["json", "csv"]

    def test_description_omitted_when_empty(self):
        args = [ToolArg(name="x")]
        schema = build_input_schema(args)
        assert "description" not in schema["properties"]["x"]

    def test_cwd_arg_appears_in_schema(self):
        """Args with cwd=True should still appear in the JSON schema."""
        args = [
            ToolArg(name="directory", type=ArgType.string, description="Working directory", cwd=True),
            ToolArg(name="name", type=ArgType.string, required=True),
        ]
        schema = build_input_schema(args)
        assert "directory" in schema["properties"]
        assert schema["properties"]["directory"]["type"] == "string"
        assert schema["properties"]["directory"]["description"] == "Working directory"
        assert schema["required"] == ["name"]

    def test_combined_properties(self):
        args = [
            ToolArg(
                name="format",
                type=ArgType.string,
                description="Output format",
                required=True,
                default="json",
                enum=["json", "table"],
            )
        ]
        schema = build_input_schema(args)
        prop = schema["properties"]["format"]
        assert prop["type"] == "string"
        assert prop["description"] == "Output format"
        assert prop["default"] == "json"
        assert prop["enum"] == ["json", "table"]
        assert schema["required"] == ["format"]
