from __future__ import annotations

import os
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


DEFAULT_CONTROLLER_CONFIG: Dict[str, Any] = {
    "base_url": None,
    "host": "127.0.0.1",
    "port": 5000,
    "timeout": 30.0,
}

DEFAULT_WORKER_CONFIG: Dict[str, Any] = {
    "engine_params": {
        "engine_type": "openai",
        "model": "o4-mini",
        "reasoning_effort": "medium",
        "reasoning_summary": "auto",
        "max_output_tokens": 12288,
    },
    "max_steps": 15,
    "max_trajectory_length": 8,
    "enable_reflection": True,
}

_RUNPOD_ID = os.getenv("RUNPOD_ID")
_RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY")
_DEFAULT_GROUNDING_BASE_URL = (
    f"https://{_RUNPOD_ID}-3005.proxy.runpod.net" if _RUNPOD_ID else None
)


DEFAULT_GROUNDING_CONFIG: Dict[str, Any] = {
    "engine_params_for_generation": {
        "engine_type": "openai",
        "model": "o4-mini",
    },
    "engine_params_for_grounding": {
        "engine_type": "openai",
        "model": "o4-mini",
        "grounding_width": 1920,
        "grounding_height": 1080,
    },
    "code_agent_engine_params": {
        "engine_type": "openai",
        "model": "o4-mini",
        "reasoning_effort": "high",
        "reasoning_summary": "auto",
        "max_output_tokens": 12288,
    },
    "code_agent_budget": 20,
    "grounding_base_url": _DEFAULT_GROUNDING_BASE_URL,
    "grounding_system_prompt": None,
    "grounding_timeout": 10.0,
    "grounding_max_retries": 3,
    "grounding_api_key": _RUNPOD_API_KEY,
}


def _coerce_dict(value: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return dict(value) if value else {}


def _merge_with_defaults(defaults: Dict[str, Any], overrides: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = deepcopy(defaults)
    if overrides:
        for key, value in overrides.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = _merge_with_defaults(merged[key], value)
            else:
                merged[key] = value
    return merged


@dataclass
class ControllerConfig:
    base_url: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    timeout: float = 30.0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ControllerConfig":
        merged = _merge_with_defaults(DEFAULT_CONTROLLER_CONFIG, data)
        return cls(
            base_url=merged.get("base_url"),
            host=merged.get("host"),
            port=merged.get("port"),
            timeout=merged.get("timeout", 30.0),
        )


@dataclass
class WorkerConfig:
    engine_params: Dict[str, Any]
    max_steps: int = 15
    max_trajectory_length: int = 8
    enable_reflection: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkerConfig":
        merged = _merge_with_defaults(DEFAULT_WORKER_CONFIG, data)
        return cls(
            engine_params=_coerce_dict(merged.get("engine_params")),
            max_steps=merged.get("max_steps", 15),
            max_trajectory_length=merged.get("max_trajectory_length", 8),
            enable_reflection=merged.get("enable_reflection", True),
        )


@dataclass
class GroundingConfig:
    engine_params_for_generation: Dict[str, Any]
    engine_params_for_grounding: Dict[str, Any]
    code_agent_engine_params: Optional[Dict[str, Any]] = None
    code_agent_budget: int = 20
    grounding_base_url: Optional[str] = None
    grounding_system_prompt: Optional[str] = None
    grounding_timeout: float = 10.0
    grounding_max_retries: int = 3
    grounding_api_key: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GroundingConfig":
        merged = _merge_with_defaults(DEFAULT_GROUNDING_CONFIG, data)
        return cls(
            engine_params_for_generation=_coerce_dict(
                merged.get("engine_params_for_generation")
            ),
            engine_params_for_grounding=_coerce_dict(
                merged.get("engine_params_for_grounding")
            ),
            code_agent_engine_params=_coerce_dict(
                merged.get("code_agent_engine_params")
            )
            or None,
            code_agent_budget=merged.get("code_agent_budget", 20),
            grounding_base_url=merged.get("grounding_base_url"),
            grounding_system_prompt=merged.get("grounding_system_prompt"),
            grounding_timeout=merged.get("grounding_timeout", 10.0),
            grounding_max_retries=merged.get("grounding_max_retries", 3),
            grounding_api_key=merged.get("grounding_api_key"),
        )


@dataclass
class OrchestrateRequest:
    task: str
    worker: WorkerConfig
    grounding: GroundingConfig
    controller: ControllerConfig
    platform: Optional[str] = None
    enable_code_execution: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OrchestrateRequest":
        if "task" not in data:
            raise ValueError("Missing required field 'task'")
        worker_data = data.get("worker") or {}
        grounding_data = data.get("grounding") or {}
        controller_data = data.get("controller") or {}
        return cls(
            task=data["task"],
            worker=WorkerConfig.from_dict(worker_data),
            grounding=GroundingConfig.from_dict(grounding_data),
            controller=ControllerConfig.from_dict(controller_data),
            platform=data.get("platform"),
            enable_code_execution=data.get("enable_code_execution", False),
        )


@dataclass
class RunnerStep:
    step_index: int
    plan: str
    action: str
    exec_code: str
    execution_result: Dict[str, Any] = field(default_factory=dict)
    reflection: Optional[str] = None
    reflection_thoughts: Optional[str] = None
    info: Dict[str, Any] = field(default_factory=dict)
    behavior_fact_thoughts: Optional[str] = None
    behavior_fact_answer: Optional[str] = None


@dataclass
class RunnerResult:
    task: str
    status: str
    completion_reason: str
    steps: List[RunnerStep] = field(default_factory=list)
    grounding_prompts: Dict[str, Any] = field(default_factory=dict)
