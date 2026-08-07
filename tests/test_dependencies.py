"""Guards on declared dependencies that the rest of the suite can't catch.

Regression coverage for #18: `mcp>=1.7` had no upper bound, so a fresh install
resolved mcp 2.0.0 — which replaced the low-level `Server` decorator API with
constructor-based handler registration — and `climax` crashed on startup with
`AttributeError: 'Server' object has no attribute 'list_tools'`.
"""

import tomllib
from pathlib import Path

from mcp.server.lowlevel import Server

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _requirement(name: str) -> str:
    deps = tomllib.loads(PYPROJECT.read_text())["project"]["dependencies"]
    matches = [d for d in deps if d.split(">=")[0].split("<")[0].strip() == name]
    assert len(matches) == 1, f"expected exactly one {name!r} dependency, got {matches}"
    return matches[0]


class TestMcpConstraint:
    def test_mcp_excludes_2x(self):
        """The pin must keep resolution off the incompatible 2.x API."""
        assert "<2" in _requirement("mcp")

    def test_lowlevel_decorator_api_present(self):
        """The registration API create_server() relies on must exist.

        This is the check that actually fails if the upper bound is ever
        widened to a major that dropped the decorators.
        """
        for method in ("list_tools", "call_tool"):
            assert hasattr(Server, method), (
                f"mcp low-level Server is missing {method!r}; "
                "create_server() cannot register handlers against this version"
            )
