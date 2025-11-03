"""Formatting checks to enforce agent response structure."""

from __future__ import annotations

from framework.utils.common_utils import (
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


def _attempt_code_creation(agent, code, obs):
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
