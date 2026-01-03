from __future__ import annotations

import base64
from io import BytesIO
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
from PIL import Image

from computer_use_agent.core.engine import LMMEngineOpenAI


class LMMAgent:
    """Minimal multimodal agent wrapper built on top of the shared LLM facade."""

    def __init__(
        self,
        engine_params: Optional[Dict[str, Any]] = None,
        system_prompt: Optional[str] = None,
        engine: Optional[LMMEngineOpenAI] = None,
    ) -> None:
        if engine is None:
            if engine_params is None:
                raise ValueError("engine_params must be provided when engine is None")
            engine_type = engine_params.get("engine_type", "openai")
            if engine_type not in {"openai", "deepseek", "openrouter"}:
                raise ValueError(f"engine_type '{engine_type}' is not supported")
            self.engine = LMMEngineOpenAI(**engine_params)
        else:
            self.engine = engine

        self.messages: List[Dict[str, Any]] = []
        if system_prompt:
            self.add_system_prompt(system_prompt)
        else:
            self.add_system_prompt("You are a helpful assistant.")

    def encode_image(self, image_content: Any) -> str:
        if isinstance(image_content, str):
            with open(image_content, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode("utf-8")
        if isinstance(image_content, np.ndarray):
            image = Image.fromarray(image_content)
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            return base64.b64encode(buffer.getvalue()).decode("utf-8")
        if isinstance(image_content, bytes):
            return base64.b64encode(image_content).decode("utf-8")
        raise TypeError(f"Unsupported image content type: {type(image_content)}")

    def reset(self) -> None:
        self.messages = [
            {
                "role": "developer",
                "content": [{"type": "text", "text": self.system_prompt}],
            }
        ]

    def add_system_prompt(self, system_prompt: str) -> None:
        self.system_prompt = system_prompt
        if self.messages:
            self.messages[0] = {
                "role": "developer",
                "content": [{"type": "text", "text": self.system_prompt}],
            }
        else:
            self.messages.append(
                {
                    "role": "developer",
                    "content": [{"type": "text", "text": self.system_prompt}],
                }
            )

    def _resolve_role(self, explicit_role: Optional[str]) -> str:
        if explicit_role == "user":
            return "user"
        if not self.messages:
            return "user"
        last_role = self.messages[-1]["role"]
        if last_role == "developer":
            return "user"
        if last_role == "user":
            return "assistant"
        return "user"

    def add_message(
        self,
        text_content: str,
        image_content: Optional[Any] = None,
        role: Optional[str] = None,
        image_detail: str = "high",
        put_text_last: bool = False,
    ) -> None:
        resolved_role = self._resolve_role(role)
        message: Dict[str, Any] = {
            "role": resolved_role,
            "content": [{"type": "text", "text": text_content}],
        }

        if image_content is not None:
            images = image_content if isinstance(image_content, list) else [image_content]
            for image in images:
                encoded = self.encode_image(image)
                message["content"].append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{encoded}",
                            "detail": image_detail,
                        },
                    }
                )

        if put_text_last:
            text_payload = message["content"].pop(0)
            message["content"].append(text_payload)

        self.messages.append(message)

    def get_response(
        self,
        user_message: Optional[str] = None,
        messages: Optional[Iterable[Dict[str, Any]]] = None,
        temperature: float = 0.0,
        max_new_tokens: Optional[int] = None,
        cost_source: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        if messages is None:
            messages = list(self.messages)
        else:
            messages = list(messages)

        if user_message:
            messages.append(
                {"role": "user", "content": [{"type": "text", "text": user_message}]}
            )

        stream_requested = bool(kwargs.pop("stream", False))
        stream_handler = kwargs.pop("stream_handler", None)
        if stream_handler is not None:
            stream_requested = True

        return self.engine.generate(
            messages,
            temperature=temperature,
            max_new_tokens=max_new_tokens,
            cost_source=cost_source,
            stream=stream_requested,
            stream_handler=stream_handler,
            **kwargs,
        )
