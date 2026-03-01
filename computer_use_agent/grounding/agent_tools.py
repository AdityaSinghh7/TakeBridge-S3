from __future__ import annotations

import base64
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from computer_use_agent.grounding.grounding_agent import OSWorldACI
from shared import agent_signal

logger = logging.getLogger(__name__)


def _action_kind_for_name(action_name: str) -> str:
    if action_name == "call_code_agent":
        return "code_agent"
    if action_name == "save_to_knowledge":
        return "knowledge"
    if action_name == "handback_to_human":
        return "handback"
    if action_name in {"done", "fail"}:
        return "termination"
    return "gui"


def _status_signal_from_exec_code(exec_code: str) -> str:
    normalized = (exec_code or "").strip()
    upper = normalized.upper()
    if upper == "DONE":
        return "DONE"
    if upper == "FAIL":
        return "FAIL"
    if normalized.startswith("HANDBACK_TO_HUMAN:"):
        return "HANDBACK"
    if upper == "WAIT" or upper.startswith("WAIT;") or upper.startswith("WAIT("):
        return "WAIT"
    return "CONTINUE"


def _to_base64(image_bytes: Optional[bytes]) -> Optional[str]:
    if not image_bytes:
        return None
    return base64.b64encode(image_bytes).decode("utf-8")


def _tool_content(payload: Dict[str, Any]) -> str:
    summary = {
        "tool_name": payload.get("tool_name"),
        "status_signal": payload.get("status_signal"),
        "exec_code": payload.get("exec_code"),
        "handback_request": payload.get("handback_request"),
        "execution_result": payload.get("execution_result") or {},
    }
    return json.dumps(summary, ensure_ascii=False, default=str)


class ClickArgs(BaseModel):
    element_description: str = Field(
        description=(
            "Detailed description of the UI element to click. "
            "Include enough context to uniquely identify it on screen."
        )
    )
    num_clicks: int = Field(
        default=1,
        description="Number of mouse clicks to perform.",
    )
    button_type: str = Field(
        default="left",
        description='Mouse button to use: "left", "middle", or "right".',
    )
    hold_keys: Optional[List[str]] = Field(
        default=None,
        description="Optional modifier keys to hold while clicking.",
    )


class SwitchApplicationsArgs(BaseModel):
    app_code: str = Field(
        description="Name/code of the already-open application to switch to."
    )


class OpenArgs(BaseModel):
    app_or_filename: str = Field(
        description=(
            "Application name or file name/path to open via OS launcher "
            "(do not manually navigate the UI to open items)."
        )
    )


class TypeArgs(BaseModel):
    element_description: Optional[str] = Field(
        default=None,
        description=(
            "Detailed target element description to click before typing. "
            "Use null only when typing into the currently focused field."
        ),
    )
    text: str = Field(
        default="",
        description="Text content to type or paste.",
    )
    overwrite: bool = Field(
        default=False,
        description="Whether to select existing text and overwrite it.",
    )
    enter: bool = Field(
        default=False,
        description="Whether to press Enter after typing.",
    )


class SaveToKnowledgeArgs(BaseModel):
    text: List[str] = Field(
        description="List of reusable facts/snippets to save in task-local knowledge."
    )


class DragAndDropArgs(BaseModel):
    starting_description: str = Field(
        description="Detailed description of drag start element/location."
    )
    ending_description: str = Field(
        description="Detailed description of drag end element/location."
    )
    hold_keys: Optional[List[str]] = Field(
        default=None,
        description="Optional modifier keys to hold during drag.",
    )


class HighlightTextSpanArgs(BaseModel):
    starting_phrase: str = Field(
        description="Phrase marking the start of the text span to highlight."
    )
    ending_phrase: str = Field(
        description="Phrase marking the end of the text span to highlight."
    )
    button: str = Field(
        default="left",
        description='Mouse button to use for highlighting ("left", "right", "middle").',
    )


class SetCellValuesArgs(BaseModel):
    cell_values: Dict[str, Any] = Field(
        description=(
            'Mapping of spreadsheet cells to values, e.g. {"A2": "hello", "B3": 42}.'
        )
    )
    app_name: str = Field(
        description='Spreadsheet application/document title, e.g. "Budget.xlsx".'
    )
    sheet_name: str = Field(
        description='Target sheet/tab name, e.g. "Sheet1".'
    )


class CallCodeAgentArgs(BaseModel):
    subtask: str = Field(
        description=(
            "Concrete code-executable subtask for the code agent. "
            "Must be specific and bounded; no GUI instructions."
        )
    )


class ScrollArgs(BaseModel):
    element_description: str = Field(
        description="Detailed description of scroll target element/region."
    )
    clicks: int = Field(
        description=(
            "Scroll magnitude; positive scrolls up and negative scrolls down. "
            "Use larger magnitudes when movement is too small."
        )
    )
    shift: bool = Field(
        default=False,
        description="Whether to use horizontal scrolling via shift+scroll behavior.",
    )


class HotkeyArgs(BaseModel):
    keys: List[str] = Field(
        description="Hotkey combination keys, e.g. ['ctrl', 'c']."
    )


class HoldAndPressArgs(BaseModel):
    hold_keys: List[str] = Field(description="Keys to hold down.")
    press_keys: List[str] = Field(description="Keys to press in sequence while held.")


class WaitArgs(BaseModel):
    time: float = Field(description="Seconds to wait.")


class DoneArgs(BaseModel):
    pass


class FailArgs(BaseModel):
    pass


class HandbackToHumanArgs(BaseModel):
    request: str = Field(
        description=(
            "Specific, actionable request for human intervention including expected outcome."
        )
    )


class GroundingActionToolExecutor:
    def __init__(
        self,
        *,
        grounding_agent: OSWorldACI,
        controller: Any,
        remote_execute_fn: Any,
        post_action_worker_delay: float,
    ) -> None:
        self.grounding_agent = grounding_agent
        self.controller = controller
        self.remote_execute_fn = remote_execute_fn
        self.post_action_worker_delay = max(float(post_action_worker_delay), 0.0)
        self._current_before_screenshot_b64: Optional[str] = None
        self._current_step_index: int = 0

    def update_step_context(
        self,
        *,
        before_screenshot_b64: Optional[str],
        step_index: int,
    ) -> None:
        self._current_before_screenshot_b64 = before_screenshot_b64
        self._current_step_index = step_index

    def _execute_action(self, action_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        method = getattr(self.grounding_agent, action_name)

        before_screenshot_bytes: Optional[bytes] = None
        if self._current_before_screenshot_b64:
            try:
                before_screenshot_bytes = base64.b64decode(self._current_before_screenshot_b64)
            except Exception:
                before_screenshot_bytes = None
        if before_screenshot_bytes is None:
            before_screenshot_bytes = self.controller.capture_screenshot()

        self.grounding_agent.assign_screenshot({"screenshot": before_screenshot_bytes})

        exec_code = method(**args)
        status_signal = _status_signal_from_exec_code(exec_code)
        handback_request = None
        if status_signal == "HANDBACK":
            handback_request = exec_code[len("HANDBACK_TO_HUMAN:") :].strip()

        execution_result: Dict[str, Any] = {}
        did_click = False
        if status_signal == "CONTINUE":
            execution_result = self.remote_execute_fn(self.controller, exec_code)
            did_click = "pyautogui.click" in (exec_code or "").lower()
            agent_signal.sleep_with_interrupt(1.0)
        elif status_signal == "WAIT":
            agent_signal.sleep_with_interrupt(1.5)

        after_screenshot_bytes = self.controller.capture_screenshot()
        delayed_after_screenshot_bytes = after_screenshot_bytes
        if status_signal == "CONTINUE" and did_click and self.post_action_worker_delay > 0:
            agent_signal.sleep_with_interrupt(self.post_action_worker_delay)
            delayed_after_screenshot_bytes = self.controller.capture_screenshot()

        payload: Dict[str, Any] = {
            "tool_name": action_name,
            "args": args,
            "action_kind": _action_kind_for_name(action_name),
            "exec_code": exec_code,
            "execution_result": execution_result,
            "status_signal": status_signal,
            "handback_request": handback_request,
            "before_screenshot_b64": _to_base64(before_screenshot_bytes),
            "after_screenshot_b64": _to_base64(after_screenshot_bytes),
            "delayed_after_screenshot_b64": _to_base64(delayed_after_screenshot_bytes),
            "did_click": did_click,
            "step_index": self._current_step_index,
        }

        if action_name == "call_code_agent":
            payload["code_agent_output"] = self.grounding_agent.last_code_agent_result
        payload["knowledge"] = list(getattr(self.grounding_agent, "knowledge", []) or [])
        payload["code_agent_history"] = list(
            getattr(self.grounding_agent, "code_agent_history", []) or []
        )
        return payload

    def click(
        self,
        element_description: str,
        num_clicks: int = 1,
        button_type: str = "left",
        hold_keys: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return self._execute_action(
            "click",
            {
                "element_description": element_description,
                "num_clicks": num_clicks,
                "button_type": button_type,
                "hold_keys": hold_keys or [],
            },
        )

    def switch_applications(self, app_code: str) -> Dict[str, Any]:
        return self._execute_action("switch_applications", {"app_code": app_code})

    def open(self, app_or_filename: str) -> Dict[str, Any]:
        return self._execute_action("open", {"app_or_filename": app_or_filename})

    def type(
        self,
        element_description: Optional[str] = None,
        text: str = "",
        overwrite: bool = False,
        enter: bool = False,
    ) -> Dict[str, Any]:
        return self._execute_action(
            "type",
            {
                "element_description": element_description,
                "text": text,
                "overwrite": overwrite,
                "enter": enter,
            },
        )

    def save_to_knowledge(self, text: List[str]) -> Dict[str, Any]:
        return self._execute_action("save_to_knowledge", {"text": text})

    def drag_and_drop(
        self,
        starting_description: str,
        ending_description: str,
        hold_keys: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return self._execute_action(
            "drag_and_drop",
            {
                "starting_description": starting_description,
                "ending_description": ending_description,
                "hold_keys": hold_keys or [],
            },
        )

    def highlight_text_span(
        self,
        starting_phrase: str,
        ending_phrase: str,
        button: str = "left",
    ) -> Dict[str, Any]:
        return self._execute_action(
            "highlight_text_span",
            {
                "starting_phrase": starting_phrase,
                "ending_phrase": ending_phrase,
                "button": button,
            },
        )

    def set_cell_values(
        self,
        cell_values: Dict[str, Any],
        app_name: str,
        sheet_name: str,
    ) -> Dict[str, Any]:
        return self._execute_action(
            "set_cell_values",
            {
                "cell_values": cell_values,
                "app_name": app_name,
                "sheet_name": sheet_name,
            },
        )

    def call_code_agent(self, subtask: str) -> Dict[str, Any]:
        return self._execute_action("call_code_agent", {"subtask": subtask})

    def scroll(
        self,
        element_description: str,
        clicks: int,
        shift: bool = False,
    ) -> Dict[str, Any]:
        return self._execute_action(
            "scroll",
            {
                "element_description": element_description,
                "clicks": clicks,
                "shift": shift,
            },
        )

    def hotkey(self, keys: List[str]) -> Dict[str, Any]:
        return self._execute_action("hotkey", {"keys": keys})

    def hold_and_press(
        self,
        hold_keys: List[str],
        press_keys: List[str],
    ) -> Dict[str, Any]:
        return self._execute_action(
            "hold_and_press",
            {"hold_keys": hold_keys, "press_keys": press_keys},
        )

    def wait(self, time: float) -> Dict[str, Any]:
        return self._execute_action("wait", {"time": time})

    def done(self) -> Dict[str, Any]:
        return self._execute_action("done", {})

    def fail(self) -> Dict[str, Any]:
        return self._execute_action("fail", {})

    def handback_to_human(self, request: str) -> Dict[str, Any]:
        return self._execute_action("handback_to_human", {"request": request})

    def _build_click_tool(self) -> BaseTool:
        @tool(
            "click",
            description=(
                "Click a specific UI element identified by a detailed natural-language description."
            ),
            args_schema=ClickArgs,
            response_format="content_and_artifact",
        )
        def click(
            element_description: str,
            num_clicks: int = 1,
            button_type: str = "left",
            hold_keys: Optional[List[str]] = None,
        ) -> Tuple[str, Dict[str, Any]]:
            payload = self.click(
                element_description=element_description,
                num_clicks=num_clicks,
                button_type=button_type,
                hold_keys=hold_keys,
            )
            return _tool_content(payload), payload

        return click

    def _build_switch_applications_tool(self) -> BaseTool:
        @tool(
            "switch_applications",
            description="Switch to an already-open application window.",
            args_schema=SwitchApplicationsArgs,
            response_format="content_and_artifact",
        )
        def switch_applications(app_code: str) -> Tuple[str, Dict[str, Any]]:
            payload = self.switch_applications(app_code=app_code)
            return _tool_content(payload), payload

        return switch_applications

    def _build_open_tool(self) -> BaseTool:
        @tool(
            "open",
            description="Open an application or file through the OS launcher.",
            args_schema=OpenArgs,
            response_format="content_and_artifact",
        )
        def open(app_or_filename: str) -> Tuple[str, Dict[str, Any]]:
            payload = self.open(app_or_filename=app_or_filename)
            return _tool_content(payload), payload

        return open

    def _build_type_tool(self) -> BaseTool:
        @tool(
            "type",
            description="Type text into an element, with optional overwrite and Enter behavior.",
            args_schema=TypeArgs,
            response_format="content_and_artifact",
        )
        def type(
            element_description: Optional[str] = None,
            text: str = "",
            overwrite: bool = False,
            enter: bool = False,
        ) -> Tuple[str, Dict[str, Any]]:
            payload = self.type(
                element_description=element_description,
                text=text,
                overwrite=overwrite,
                enter=enter,
            )
            return _tool_content(payload), payload

        return type

    def _build_save_to_knowledge_tool(self) -> BaseTool:
        @tool(
            "save_to_knowledge",
            description="Store reusable facts in the task-local knowledge buffer.",
            args_schema=SaveToKnowledgeArgs,
            response_format="content_and_artifact",
        )
        def save_to_knowledge(text: List[str]) -> Tuple[str, Dict[str, Any]]:
            payload = self.save_to_knowledge(text=text)
            return _tool_content(payload), payload

        return save_to_knowledge

    def _build_drag_and_drop_tool(self) -> BaseTool:
        @tool(
            "drag_and_drop",
            description="Drag from a start element to an end element on screen.",
            args_schema=DragAndDropArgs,
            response_format="content_and_artifact",
        )
        def drag_and_drop(
            starting_description: str,
            ending_description: str,
            hold_keys: Optional[List[str]] = None,
        ) -> Tuple[str, Dict[str, Any]]:
            payload = self.drag_and_drop(
                starting_description=starting_description,
                ending_description=ending_description,
                hold_keys=hold_keys,
            )
            return _tool_content(payload), payload

        return drag_and_drop

    def _build_highlight_text_span_tool(self) -> BaseTool:
        @tool(
            "highlight_text_span",
            description="Highlight text between a starting phrase and ending phrase.",
            args_schema=HighlightTextSpanArgs,
            response_format="content_and_artifact",
        )
        def highlight_text_span(
            starting_phrase: str,
            ending_phrase: str,
            button: str = "left",
        ) -> Tuple[str, Dict[str, Any]]:
            payload = self.highlight_text_span(
                starting_phrase=starting_phrase,
                ending_phrase=ending_phrase,
                button=button,
            )
            return _tool_content(payload), payload

        return highlight_text_span

    def _build_set_cell_values_tool(self) -> BaseTool:
        @tool(
            "set_cell_values",
            description="Set multiple spreadsheet cell values in a target sheet.",
            args_schema=SetCellValuesArgs,
            response_format="content_and_artifact",
        )
        def set_cell_values(
            cell_values: Dict[str, Any],
            app_name: str,
            sheet_name: str,
        ) -> Tuple[str, Dict[str, Any]]:
            payload = self.set_cell_values(
                cell_values=cell_values,
                app_name=app_name,
                sheet_name=sheet_name,
            )
            return _tool_content(payload), payload

        return set_cell_values

    def _build_call_code_agent_tool(self) -> BaseTool:
        @tool(
            "call_code_agent",
            description=(
                "Delegate a bounded, code-executable subtask to the code agent (non-GUI)."
            ),
            args_schema=CallCodeAgentArgs,
            response_format="content_and_artifact",
        )
        def call_code_agent(subtask: str) -> Tuple[str, Dict[str, Any]]:
            payload = self.call_code_agent(subtask=subtask)
            return _tool_content(payload), payload

        return call_code_agent

    def _build_scroll_tool(self) -> BaseTool:
        @tool(
            "scroll",
            description="Scroll within a specific target element or region.",
            args_schema=ScrollArgs,
            response_format="content_and_artifact",
        )
        def scroll(
            element_description: str,
            clicks: int,
            shift: bool = False,
        ) -> Tuple[str, Dict[str, Any]]:
            payload = self.scroll(
                element_description=element_description,
                clicks=clicks,
                shift=shift,
            )
            return _tool_content(payload), payload

        return scroll

    def _build_hotkey_tool(self) -> BaseTool:
        @tool(
            "hotkey",
            description="Press a key combination simultaneously.",
            args_schema=HotkeyArgs,
            response_format="content_and_artifact",
        )
        def hotkey(keys: List[str]) -> Tuple[str, Dict[str, Any]]:
            payload = self.hotkey(keys=keys)
            return _tool_content(payload), payload

        return hotkey

    def _build_hold_and_press_tool(self) -> BaseTool:
        @tool(
            "hold_and_press",
            description="Hold keys and press another key sequence.",
            args_schema=HoldAndPressArgs,
            response_format="content_and_artifact",
        )
        def hold_and_press(
            hold_keys: List[str],
            press_keys: List[str],
        ) -> Tuple[str, Dict[str, Any]]:
            payload = self.hold_and_press(
                hold_keys=hold_keys,
                press_keys=press_keys,
            )
            return _tool_content(payload), payload

        return hold_and_press

    def _build_wait_tool(self) -> BaseTool:
        @tool(
            "wait",
            description="Pause execution for a short duration.",
            args_schema=WaitArgs,
            response_format="content_and_artifact",
        )
        def wait(time: float) -> Tuple[str, Dict[str, Any]]:
            payload = self.wait(time=time)
            return _tool_content(payload), payload

        return wait

    def _build_done_tool(self) -> BaseTool:
        @tool(
            "done",
            description="Mark task completion when the objective is fully satisfied.",
            args_schema=DoneArgs,
            response_format="content_and_artifact",
        )
        def done() -> Tuple[str, Dict[str, Any]]:
            payload = self.done()
            return _tool_content(payload), payload

        return done

    def _build_fail_tool(self) -> BaseTool:
        @tool(
            "fail",
            description="End the task as failed when completion is impossible.",
            args_schema=FailArgs,
            response_format="content_and_artifact",
        )
        def fail() -> Tuple[str, Dict[str, Any]]:
            payload = self.fail()
            return _tool_content(payload), payload

        return fail

    def _build_handback_to_human_tool(self) -> BaseTool:
        @tool(
            "handback_to_human",
            description=(
                "Request human intervention for credentials, confirmation, or unavailable information."
            ),
            args_schema=HandbackToHumanArgs,
            response_format="content_and_artifact",
        )
        def handback_to_human(request: str) -> Tuple[str, Dict[str, Any]]:
            payload = self.handback_to_human(request=request)
            return _tool_content(payload), payload

        return handback_to_human

    def build_tools(self) -> List[BaseTool]:
        return [
            self._build_click_tool(),
            self._build_switch_applications_tool(),
            self._build_open_tool(),
            self._build_type_tool(),
            self._build_save_to_knowledge_tool(),
            self._build_drag_and_drop_tool(),
            self._build_highlight_text_span_tool(),
            self._build_set_cell_values_tool(),
            self._build_call_code_agent_tool(),
            self._build_scroll_tool(),
            self._build_hotkey_tool(),
            self._build_hold_and_press_tool(),
            self._build_wait_tool(),
            self._build_done_tool(),
            self._build_fail_tool(),
            self._build_handback_to_human_tool(),
        ]


__all__ = [
    "GroundingActionToolExecutor",
    "_action_kind_for_name",
    "_status_signal_from_exec_code",
]
