from __future__ import annotations

from pathlib import Path


def test_planner_modules_do_not_reference_computer_use_agent():
    planner_dir = Path(__file__).resolve().parents[2] / "mcp_agent" / "planner"
    for path in planner_dir.rglob("*.py"):
        contents = path.read_text(encoding="utf-8")
        assert "computer_use_agent" not in contents, f"Found forbidden reference in {path}"
