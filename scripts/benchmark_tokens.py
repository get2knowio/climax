"""
Benchmark: Token savings of progressive discovery mode vs classic mode.

Loads all YAML configs from configs/, builds both classic-mode and
discovery-mode tool lists, serializes to JSON, and counts tokens with
tiktoken to show the savings from progressive discovery.

Usage:
    uv sync --extra benchmark
    uv run python scripts/benchmark_tokens.py
"""

import json
import sys

from climax import (
    CONFIGS_DIR,
    CLImaxConfig,
    ToolIndex,
    build_input_schema,
    load_config,
    create_server,
    ResolvedTool,
)

try:
    import tiktoken
except ImportError:
    print("Error: tiktoken is not installed.")
    print("Install it with: uv sync --extra benchmark")
    sys.exit(1)


def main() -> int:
    # Load all YAML configs from configs/
    config_paths = sorted(CONFIGS_DIR.glob("*.yaml"))
    if not config_paths:
        print(f"Error: no YAML configs found in {CONFIGS_DIR}")
        return 1

    configs: list[CLImaxConfig] = []
    for path in config_paths:
        configs.append(load_config(path))

    config_names = [c.name for c in configs]

    # Build classic tool list (all individual tools)
    tools_classic = []
    for config in configs:
        for tool_def in config.tools:
            tools_classic.append({
                "name": tool_def.name,
                "description": tool_def.description,
                "inputSchema": build_input_schema(tool_def.args),
            })

    # Build discovery tool list (exactly 2 meta-tools)
    tools_discovery = [
        {
            "name": "climax_search",
            "description": "Search for available CLI tools by keyword, category, or CLI name. Call with no filters to get a summary of all available CLIs.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword (matched against tool name, description, CLI name, category, tags)"},
                    "category": {"type": "string", "description": "Filter by CLI category (exact match, case-insensitive)"},
                    "cli": {"type": "string", "description": "Filter by CLI name (exact match, case-insensitive)"},
                    "limit": {"type": "integer", "description": "Maximum number of results to return (default: 10)", "default": 10},
                },
            },
        },
        {
            "name": "climax_call",
            "description": "Execute a CLI tool by name. Use climax_search first to discover available tools and their argument schemas.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "tool_name": {"type": "string", "description": "The exact name of the tool to execute (as returned by climax_search)"},
                    "args": {"type": "object", "description": "Arguments to pass to the tool (see tool's input_schema from climax_search)"},
                },
                "required": ["tool_name"],
            },
        },
    ]

    # Token counting
    enc = tiktoken.get_encoding("cl100k_base")
    classic_json = json.dumps(tools_classic)
    discovery_json = json.dumps(tools_discovery)
    classic_tokens = len(enc.encode(classic_json))
    discovery_tokens = len(enc.encode(discovery_json))
    savings_pct = ((classic_tokens - discovery_tokens) / classic_tokens) * 100

    # Output
    print("Token Savings: Progressive Discovery vs Classic Mode")
    print("=====================================================")
    print()
    print(f"Configs loaded: {len(configs)} ({', '.join(config_names)})")
    print(f"Total tools across all configs: {len(tools_classic)}")
    print()
    print("| Mode      | Tools | Tokens | Savings |")
    print("|-----------|-------|--------|---------|")
    print(f"| Classic   | {len(tools_classic):<5} | {classic_tokens:<6} |         |")
    print(f"| Discovery | {len(tools_discovery):<5} | {discovery_tokens:<6} | {savings_pct:.1f}%   |")

    return 0


if __name__ == "__main__":
    sys.exit(main())
