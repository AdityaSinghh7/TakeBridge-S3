from __future__ import annotations

from langchain_core.messages import ToolMessage
from langchain_core.tools import StructuredTool

from computer_use_agent.grounding.agent_tools import (
    GroundingActionToolExecutor,
    _status_signal_from_exec_code,
)
from computer_use_agent.orchestrator.llm_adapter import (
    convert_langchain_tools_to_responses_api,
    extract_tool_calls_from_response,
)
from computer_use_agent.orchestrator.runner import _tool_payload_from_messages


def test_extract_tool_calls_from_responses_items() -> None:
    response = {
        "output": [
            {
                "type": "function_call",
                "id": "fc_1",
                "call_id": "call_abc",
                "name": "click",
                "arguments": "{\"element_description\":\"Submit button\"}",
            }
        ]
    }
    calls = extract_tool_calls_from_response(response)
    assert len(calls) == 1
    assert calls[0]["name"] == "click"
    assert calls[0]["id"] == "call_abc"
    assert calls[0]["args"]["element_description"] == "Submit button"


def test_convert_langchain_tools_to_openai_responses_schema() -> None:
    def done() -> dict:
        return {"ok": True}

    tool = StructuredTool.from_function(
        func=done,
        name="done",
        description="Mark task complete.",
    )
    payload = convert_langchain_tools_to_responses_api([tool])
    assert len(payload) == 1
    assert payload[0]["type"] == "function"
    assert payload[0]["name"] == "done"
    assert payload[0]["parameters"]["type"] == "object"


def test_status_signal_normalization() -> None:
    assert _status_signal_from_exec_code("DONE") == "DONE"
    assert _status_signal_from_exec_code("FAIL") == "FAIL"
    assert _status_signal_from_exec_code("HANDBACK_TO_HUMAN:please login") == "HANDBACK"
    assert _status_signal_from_exec_code("WAIT") == "WAIT"
    assert _status_signal_from_exec_code("import pyautogui; pyautogui.click(1,2)") == "CONTINUE"


def test_agent_tools_have_described_parameters() -> None:
    executor = GroundingActionToolExecutor(
        grounding_agent=object(),  # type: ignore[arg-type]
        controller=object(),
        remote_execute_fn=lambda *_args, **_kwargs: {},
        post_action_worker_delay=0.0,
    )
    tools = executor.build_tools()
    payloads = convert_langchain_tools_to_responses_api(tools)

    assert [tool.name for tool in tools] == [
        "click",
        "switch_applications",
        "open",
        "type",
        "save_to_knowledge",
        "drag_and_drop",
        "highlight_text_span",
        "set_cell_values",
        "call_code_agent",
        "scroll",
        "hotkey",
        "hold_and_press",
        "wait",
        "done",
        "fail",
        "handback_to_human",
    ]
    for payload in payloads:
        properties = payload.get("parameters", {}).get("properties", {})
        for prop in properties.values():
            assert prop.get("description"), f"missing description for {payload['name']}"


def test_runner_tool_payload_prefers_artifact() -> None:
    msg = ToolMessage(
        content="not-json",
        tool_call_id="call_1",
        name="click",
        artifact={"tool_name": "click", "status_signal": "CONTINUE", "exec_code": "abc"},
    )
    payload = _tool_payload_from_messages([msg])
    assert payload["tool_name"] == "click"
    assert payload["exec_code"] == "abc"


def test_runner_tool_payload_fallback_json_content() -> None:
    msg = ToolMessage(
        content='{"tool_name":"done","status_signal":"DONE","exec_code":"DONE"}',
        tool_call_id="call_2",
        name="done",
    )
    payload = _tool_payload_from_messages([msg])
    assert payload["tool_name"] == "done"
    assert payload["status_signal"] == "DONE"
