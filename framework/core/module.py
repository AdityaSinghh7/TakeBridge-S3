from __future__ import annotations

from typing import Dict, Optional

from framework.core.mllm import LMMAgent


class BaseModule:
    """Base module that provides a configured LMMAgent factory."""

    def __init__(self, engine_params: Dict, platform: str):
        self.engine_params = dict(engine_params)
        self.engine_params.setdefault("engine_type", "openai")
        self.engine_params.setdefault("model", "o4-mini")
        self.platform = platform

    def _create_agent(
        self,
        system_prompt: Optional[str] = None,
        engine_params: Optional[Dict] = None,
    ) -> LMMAgent:
        agent = LMMAgent(engine_params or self.engine_params)
        if system_prompt:
            agent.add_system_prompt(system_prompt)
        return agent
