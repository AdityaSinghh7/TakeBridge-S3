"""Formatting checks to enforce agent response structure."""

from __future__ import annotations

import ast
import re
from typing import Iterable, Optional, Tuple

from computer_use_agent.utils.common_utils import (
    create_pyautogui_code,
    extract_agent_functions,
    parse_code_from_string,
    split_thinking_response,
)

single_action_check = (
    lambda response: len(extract_agent_functions(parse_code_from_string(response))) == 1
)
single_action_error_msg = (
    "Incorrect code: There must be a single agent action in the code response."
)
SINGLE_ACTION_FORMATTER = lambda response: (
    single_action_check(response),
    single_action_error_msg,
)

_AGENT_ACTION_NAMES = {
    "call_code_agent",
    "click",
    "done",
    "drag_and_drop",
    "fail",
    "handback_to_human",
    "highlight_text_span",
    "hold_and_press",
    "hotkey",
    "open",
    "save_to_knowledge",
    "scroll",
    "set_cell_values",
    "switch_applications",
    "type",
    "wait",
}

_CODE_BLOCK_RE = re.compile(r"```(?:\w+\s+)?(.*?)```", re.DOTALL)


def _iter_code_blocks(text: str) -> Iterable[str]:
    for match in _CODE_BLOCK_RE.finditer(text):
        block = match.group(1).strip()
        if block:
            yield block


def _strip_partial_code_fence_markers(text: str) -> str:
    if _CODE_BLOCK_RE.search(text):
        return text
    stripped = text.strip()
    if not stripped:
        return text
    stripped = re.sub(r"^\s*`{1,3}(?:\w+)?\s*\n?", "", stripped)
    stripped = re.sub(r"\n?\s*`{1,3}\s*$", "", stripped)
    return stripped


def _parse_agent_action_call(code: str) -> Optional[Tuple[str, str]]:
    code = code.strip()
    if not code:
        return None
    try:
        node = ast.parse(code, mode="eval").body
    except Exception:
        return None
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if not (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "agent"
    ):
        return None
    return func.attr, code


def parse_agent_action(output: str) -> Optional[Tuple[str, str]]:
    """Parse the first agent.<action>(...) call from an output or its code blocks."""
    for block in _iter_code_blocks(output):
        parsed = _parse_agent_action_call(block)
        if parsed:
            return parsed
    sanitized = _strip_partial_code_fence_markers(output)
    return _parse_agent_action_call(sanitized)


def is_agent_action_spelled_correctly(action_name: Optional[str]) -> bool:
    return bool(action_name) and action_name in _AGENT_ACTION_NAMES


def is_agent_action_wrapped_in_code_block(output: str) -> bool:
    for block in _iter_code_blocks(output):
        if _parse_agent_action_call(block):
            return True
    return False


def auto_wrap_agent_action_output(output: str) -> Tuple[str, bool]:
    if is_agent_action_wrapped_in_code_block(output):
        return output, False
    sanitized = _strip_partial_code_fence_markers(output)
    parsed = _parse_agent_action_call(sanitized)
    if not parsed:
        return output, False
    action_name, call_text = parsed
    if not is_agent_action_spelled_correctly(action_name):
        return output, False
    wrapped = f"```python\n{call_text}\n```"
    return wrapped, True


def normalize_agent_action_response(output: str) -> Tuple[str, bool]:
    """Normalize unfenced agent.<action> outputs by adding code fences when safe."""
    return auto_wrap_agent_action_output(output)


def _attempt_code_creation(agent, code, obs):
    """Attempt to create executable code without triggering side effects.

    We set a transient flag on the agent so agent actions can detect validation
    mode and avoid heavyweight side effects (e.g., invoking the code agent)
    during formatting checks.
    """
    had_flag = hasattr(agent, "_validation_only")
    prev_value = getattr(agent, "_validation_only", False)
    setattr(agent, "_validation_only", True)
    try:
        return create_pyautogui_code(agent, code, obs)
    except Exception as e:
        # Log the actual error for debugging
        import logging
        logger = logging.getLogger("desktopenv.agent")
        error_msg = str(e).lower()
        if "tesseract" in error_msg or "pytesseract" in error_msg:
            logger.warning(
                "Code validation failed due to missing tesseract: %s", str(e)
            )
        else:
            logger.debug("Code validation failed: %s", str(e))
        return None
    finally:
        # Restore prior state
        if had_flag:
            setattr(agent, "_validation_only", prev_value)
        else:
            try:
                delattr(agent, "_validation_only")
            except Exception:
                pass


code_valid_check = (
    lambda agent, obs, response: _attempt_code_creation(
        agent, parse_code_from_string(response), obs
    )
    is not None
)
code_valid_error_msg = "Incorrect code: The agent action must be a valid function and use valid parameters from the docstring list."
CODE_VALID_FORMATTER = lambda agent, obs, response: (
    code_valid_check(agent, obs, response),
    code_valid_error_msg,
)


def _call_code_agent_requires_subtask(code: str) -> bool:
    """
    Return True if code does not call call_code_agent, or calls it with a non-empty
    string subtask argument.
    """
    if "call_code_agent" not in code:
        return True
    try:
        node = ast.parse(code, mode="eval").body
    except Exception:
        # Let other formatters handle non-parseable code.
        return True

    if not isinstance(node, ast.Call):
        return True
    func = node.func
    if not (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "agent"
        and func.attr == "call_code_agent"
    ):
        return True

    # Disallow empty call to call_code_agent (missing subtask).
    if not node.args and not node.keywords:
        return False

    # Disallow legacy keyword name to avoid runtime TypeError after signature change.
    for kw in node.keywords:
        if kw.arg == "task":
            return False

    # Accept exactly one positional string literal.
    if node.args:
        if len(node.args) != 1 or node.keywords:
            return False
        arg0 = node.args[0]
        return (
            isinstance(arg0, ast.Constant)
            and isinstance(arg0.value, str)
            and bool(arg0.value.strip())
        )

    # Accept exactly one keyword `subtask="..."`.
    if len(node.keywords) != 1:
        return False
    kw = node.keywords[0]
    if kw.arg != "subtask":
        return False
    return (
        isinstance(kw.value, ast.Constant)
        and isinstance(kw.value.value, str)
        and bool(kw.value.value.strip())
    )


call_code_agent_subtask_required_check = lambda response: _call_code_agent_requires_subtask(
    parse_code_from_string(response)
)
call_code_agent_subtask_required_error_msg = (
    "Incorrect code: call_code_agent requires a non-empty subtask string, e.g. agent.call_code_agent(\"...\")."
)
CALL_CODE_AGENT_SUBTASK_REQUIRED_FORMATTER = lambda response: (
    call_code_agent_subtask_required_check(response),
    call_code_agent_subtask_required_error_msg,
)

thoughts_answer_tag_check = lambda response: split_thinking_response(response)[1] != ""
thoughts_answer_error_msg = "Incorrect response: The response must contain both <thoughts>...</thoughts> and <answer>...</answer> tags."
THOUGHTS_ANSWER_TAG_FORMATTER = lambda response: (
    thoughts_answer_tag_check(response),
    thoughts_answer_error_msg,
)

integer_answer_check = (
    lambda response: split_thinking_response(response)[0].strip().isdigit()
)
integer_answer_error_msg = (
    "Incorrect response: The <answer>...</answer> tag must contain a single integer."
)
INTEGER_ANSWER_FORMATTER = lambda response: (
    integer_answer_check(response),
    integer_answer_error_msg,
)
