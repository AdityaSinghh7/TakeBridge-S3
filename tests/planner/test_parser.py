from __future__ import annotations

import pytest

from mcp_agent.planner.parser import parse_planner_command


def test_parse_planner_command_valid_finish():
    command = parse_planner_command('{"type":"finish","summary":"done","reasoning":"done"}')
    assert command["type"] == "finish"
    assert command["summary"] == "done"


def test_parse_planner_command_invalid_json():
    with pytest.raises(ValueError):
        parse_planner_command("not json")


def test_parse_planner_command_missing_type():
    with pytest.raises(ValueError):
        parse_planner_command('{"foo":"bar"}')


def test_parse_planner_command_requires_tool_fields():
    with pytest.raises(ValueError):
        parse_planner_command('{"type":"tool","tool":"send","reasoning":"x"}')
    with pytest.raises(ValueError):
        parse_planner_command('{"type":"tool","provider":"slack","reasoning":"x"}')
    with pytest.raises(ValueError):
        parse_planner_command('{"type":"tool","provider":"slack","tool":"send","payload":123,"reasoning":"x"}')


def test_parse_planner_command_validates_sandbox_and_search():
    with pytest.raises(ValueError):
        parse_planner_command('{"type":"sandbox","code":"","reasoning":"x"}')
    with pytest.raises(ValueError):
        parse_planner_command('{"type":"search","query":"","reasoning":"x"}')
    with pytest.raises(ValueError):
        parse_planner_command('{"type":"search","query":"gmail","limit":200,"reasoning":"x"}')


def test_parse_planner_command_requires_reasoning():
    with pytest.raises(ValueError):
        parse_planner_command('{"type":"search","query":"gmail"}')
    with pytest.raises(ValueError):
        parse_planner_command('{"type":"tool","provider":"slack","tool":"send","payload":{},"reasoning":""}')
