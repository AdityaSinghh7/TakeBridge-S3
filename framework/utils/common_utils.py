"""Shared utility helpers for agent coordination and formatting."""

from __future__ import annotations

import logging
import re
import time
from io import BytesIO
from typing import Dict, Iterable, Tuple

from PIL import Image

from framework.memory.procedural_memory import PROCEDURAL_MEMORY

logger = logging.getLogger("desktopenv.agent")


def create_pyautogui_code(agent, code: str, obs: Dict) -> str:
    """
    Evaluate plan code into a grounded pyautogui snippet using the current observation.
    """
    agent.assign_screenshot(obs)
    exec_env = {"agent": agent}
    return eval(code, exec_env)


def call_llm_safe(agent, temperature: float = 0.0, use_thinking: bool = False, **kwargs) -> str:
    """Invoke an LMMAgent with basic retry and logging."""
    max_retries = 3
    attempt = 0
    response = ""
    while attempt < max_retries:
        try:
            kwargs.pop("use_thinking", None)  # Ensure engines without support do not receive this flag
            response = agent.get_response(
                temperature=temperature, **kwargs
            )
            assert response is not None, "Response from agent should not be None"
            logger.debug("LLM response succeeded on attempt %d", attempt + 1)
            break
        except Exception as exc:
            attempt += 1
            logger.warning("LLM call attempt %d failed: %s", attempt, exc)
            if attempt == max_retries:
                logger.error("Max retries reached while calling LLM.")
        time.sleep(1.0)
    return response if response is not None else ""


def call_llm_formatted(generator, format_checkers, **kwargs) -> str:
    """
    Call an LMMAgent and enforce response formatting via formatter callbacks.
    """
    max_retries = 3
    attempt = 0
    response = ""
    messages = kwargs.pop("messages", generator.messages.copy())

    while attempt < max_retries:
        response = call_llm_safe(generator, messages=messages, **kwargs)

        feedback_msgs = []
        for format_checker in format_checkers:
            success, feedback = format_checker(response)
            if not success:
                feedback_msgs.append(feedback)

        if not feedback_msgs:
            return response

        logger.error(
            "Response formatting error on attempt %d for %s: %s",
            attempt + 1,
            getattr(generator.engine, "model", "unknown"),
            response,
        )
        messages.append(
            {
                "role": "assistant",
                "content": [{"type": "text", "text": response}],
            }
        )
        formatting_feedback = "- " + "\n- ".join(feedback_msgs)
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": PROCEDURAL_MEMORY.FORMATTING_FEEDBACK_PROMPT.replace(
                            "FORMATTING_FEEDBACK", formatting_feedback
                        ),
                    }
                ],
            }
        )
        logger.info("Provided formatting feedback:\n%s", formatting_feedback)
        attempt += 1

    logger.error("Failed to obtain correctly formatted response after retries.")
    return response


def split_thinking_response(full_response: str) -> Tuple[str, str]:
    try:
        thoughts = full_response.split("<thoughts>")[-1].split("</thoughts>")[0].strip()
        answer = full_response.split("<answer>")[-1].split("</answer>")[0].strip()
        return answer, thoughts
    except Exception:
        return full_response, ""


def parse_code_from_string(input_string: str) -> str:
    input_string = input_string.strip()
    pattern = r"```(?:\w+\s+)?(.*?)```"
    matches = re.findall(pattern, input_string, re.DOTALL)
    if not matches:
        return ""
    return matches[-1].strip()


def extract_agent_functions(code: str):
    pattern = r"(agent\.\w+\(\s*.*\))"
    return re.findall(pattern, code)


def compress_image(image_bytes: bytes = None, image: Image.Image = None) -> bytes:
    if not image:
        image = Image.open(BytesIO(image_bytes))
    output = BytesIO()
    image.save(output, format="WEBP")
    return output.getvalue()
