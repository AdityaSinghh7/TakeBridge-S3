from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from computer_use_agent.utils.common_utils import (
    parse_code_agent_response,
    split_thinking_response,
)


def test_parse_code_agent_json_python():
    raw = (
        '{'
        '"thoughts":"t",'
        '"answer":"",'
        '"python":{"code":"print(\\"hi\\")"},'
        '"bash":{"code":""}'
        '}'
    )
    parsed = parse_code_agent_response(raw)
    assert parsed is not None
    assert parsed["thoughts"] == "t"
    assert parsed["answer"] == ""
    assert parsed["code_type"] == "python"
    assert parsed["code"] == 'print("hi")'


def test_parse_code_agent_json_bash_fenced():
    raw = (
        "```json\n"
        '{'
        '"thoughts":"t",'
        '"answer":"",'
        '"python":{"code":""},'
        '"bash":{"code":"ls -la"}'
        '}'
        "\n```"
    )
    parsed = parse_code_agent_response(raw)
    assert parsed is not None
    assert parsed["code_type"] == "bash"
    assert parsed["code"] == "ls -la"


def test_parse_code_agent_json_done():
    raw = (
        '{'
        '"thoughts":"done",'
        '"answer":"DONE",'
        '"python":{"code":""},'
        '"bash":{"code":""}'
        '}'
    )
    parsed = parse_code_agent_response(raw)
    assert parsed is not None
    assert parsed["answer"] == "DONE"
    assert parsed["code_type"] == ""
    assert parsed["code"] == ""


def test_parse_code_agent_json_both_code_prefers_python():
    raw = (
        '{'
        '"thoughts":"t",'
        '"answer":"",'
        '"python":{"code":"print(1)"},'
        '"bash":{"code":"echo hi"}'
        '}'
    )
    parsed = parse_code_agent_response(raw)
    assert parsed is not None
    assert parsed["code_type"] == "python"
    assert parsed["code"] == "print(1)"


def test_parse_code_agent_json_invalid_returns_none():
    parsed = parse_code_agent_response("not json")
    assert parsed is None


def test_split_thinking_response_legacy_tags():
    raw = "<thoughts>t</thoughts><answer>DONE</answer>"
    answer, thoughts = split_thinking_response(raw)
    assert answer == "DONE"
    assert thoughts == "t"
