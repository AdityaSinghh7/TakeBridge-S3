"""Hierarchical logging system for multi-agent observability.

This module provides a structured logging system that:
- Organizes logs hierarchically by agent, step, and sub-component
- Truncates large payloads for readability in console/main logs
- Preserves full payloads in raw/ subdirectories for debugging
- Uses context variables for implicit logger propagation
- Supports async-safe concurrent execution
"""

from __future__ import annotations

import hashlib
import json
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


# Context variable for current hierarchical logger instance
_current_hierarchical_logger: ContextVar[Optional["HierarchicalLogger"]] = ContextVar(
    "hierarchical_logger", default=None
)

# Context variable for current step_id
_current_step_id: ContextVar[Optional[str]] = ContextVar("step_id", default=None)


def set_hierarchical_logger(logger: "HierarchicalLogger") -> None:
    """Set the hierarchical logger for the current context.

    Args:
        logger: The HierarchicalLogger instance to set for this context
    """
    _current_hierarchical_logger.set(logger)


def get_hierarchical_logger() -> Optional["HierarchicalLogger"]:
    """Get the hierarchical logger from the current context.

    Returns:
        The current HierarchicalLogger instance, or None if not set
    """
    return _current_hierarchical_logger.get()


def set_step_id(step_id: str) -> None:
    """Set the step_id for the current context.

    Args:
        step_id: The step identifier to bind to this execution context
    """
    _current_step_id.set(step_id)


def get_step_id() -> Optional[str]:
    """Get the step_id from the current context.

    Returns:
        The current step_id, or None if not set
    """
    return _current_step_id.get()


class HierarchicalLogger:
    """Manages hierarchical log files for multi-agent systems.

    Creates a directory structure like:
        logs/{timestamp}_{task_hash}/
            orchestrator/main.jsonl
            mcp/{step_id}/main.jsonl
            computer_use/{step_id}/main.jsonl

    Each agent/step gets its own directory with:
    - main.jsonl: Truncated event log (readable)
    - raw/: Full payloads without truncation (debugging)
    - {sub_component}/: Nested directories for sub-agents
    """

    def __init__(
        self,
        task: str,
        base_dir: str = "logs",
        timestamp: Optional[str] = None,
    ):
        """Initialize hierarchical logger.

        Args:
            task: The task description (used to generate hash for directory name)
            base_dir: Base directory for logs (default: "logs")
            timestamp: Optional ISO timestamp override (default: current time)
        """
        # Generate short hash from task description
        task_hash = hashlib.sha256(task.encode()).hexdigest()[:8]

        self.task = task
        self.task_hash = task_hash
        self.timestamp = timestamp or datetime.utcnow().isoformat()
        self.run_dir = Path(base_dir) / f"{self.timestamp}_{task_hash}"
        self.run_dir.mkdir(parents=True, exist_ok=True)

        # Create metadata file
        self._write_metadata()

    def _write_metadata(self) -> None:
        """Write run metadata to metadata.json."""
        metadata = {
            "task": self.task,
            "task_hash": self.task_hash,
            "timestamp": self.timestamp,
            "started_at": datetime.utcnow().isoformat(),
        }
        metadata_path = self.run_dir / "metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

    def get_agent_logger(
        self, agent: str, step_id: Optional[str] = None
    ) -> "AgentLogger":
        """Get logger for a specific agent/step.

        Args:
            agent: Agent name (e.g., "orchestrator", "mcp", "computer_use")
            step_id: Optional step identifier for per-step logging

        Returns:
            AgentLogger instance for the specified agent/step
        """
        if step_id:
            agent_dir = self.run_dir / agent / step_id
        else:
            agent_dir = self.run_dir / agent
        agent_dir.mkdir(parents=True, exist_ok=True)
        return AgentLogger(agent_dir, agent, step_id)


class AgentLogger:
    """Logger for a specific agent or sub-agent.

    Handles:
    - Event logging to main.jsonl (with truncation)
    - Full payload logging to raw/ directory
    - Sub-component loggers via get_sub_logger()
    - Console output with truncation
    """

    def __init__(
        self, log_dir: Path, agent: str, step_id: Optional[str] = None
    ):
        """Initialize agent logger.

        Args:
            log_dir: Directory for this agent's logs
            agent: Agent name
            step_id: Optional step identifier
        """
        self.log_dir = log_dir
        self.agent = agent
        self.step_id = step_id
        self.main_log = log_dir / "main.jsonl"
        self.raw_dir = log_dir / "raw"
        self.raw_dir.mkdir(exist_ok=True)

    def log_event(
        self,
        event: str,
        data: Dict[str, Any],
        *,
        truncate: bool = True,
        max_value_len: int = 500,
    ) -> None:
        """Log an event to main.jsonl and console.

        Args:
            event: Event name (e.g., "task.started", "execution.completed")
            data: Event data dictionary
            truncate: Whether to truncate values (default: True)
            max_value_len: Maximum value length before truncation (default: 500)
        """
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event": event,
            "agent": self.agent,
            "step_id": self.step_id,
            "data": self._truncate_payload(data, max_value_len) if truncate else data,
        }

        # Append to JSONL file
        with open(self.main_log, "a") as f:
            f.write(json.dumps(entry) + "\n")

        # Also emit to server logs (truncated for readability)
        truncated_data = self._truncate_payload(data, max_value_len=500)
        print(f"[{self.agent}] {event}: {json.dumps(truncated_data)}")

    def log_full_payload(self, name: str, data: Any) -> None:
        """Log full payload without truncation to raw/ directory.

        Args:
            name: Filename (without extension)
            data: Data to log (will be JSON serialized)
        """
        raw_file = self.raw_dir / f"{name}.json"
        with open(raw_file, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def get_sub_logger(self, component: str) -> "AgentLogger":
        """Get logger for a sub-component.

        Args:
            component: Sub-component name (e.g., "planner", "executor", "worker")

        Returns:
            AgentLogger instance for the sub-component
        """
        sub_dir = self.log_dir / component
        sub_dir.mkdir(exist_ok=True)
        return AgentLogger(sub_dir, f"{self.agent}.{component}", self.step_id)

    @staticmethod
    def _truncate_payload(
        data: Dict[str, Any],
        max_value_len: int = 500,
    ) -> Dict[str, Any]:
        """Truncate values while preserving keys.

        Args:
            data: Data dictionary to truncate
            max_value_len: Maximum length for string/list values

        Returns:
            Truncated data dictionary
        """
        if not isinstance(data, dict):
            return data

        truncated = {}
        for key, value in data.items():
            if isinstance(value, str) and len(value) > max_value_len:
                truncated[key] = (
                    value[:max_value_len]
                    + f"... [truncated, {len(value)} chars total]"
                )
            elif isinstance(value, (list, tuple)) and len(value) > 10:
                truncated[key] = list(value[:10]) + [
                    f"... [truncated, {len(value)} items total]"
                ]
            elif isinstance(value, dict):
                truncated[key] = AgentLogger._truncate_payload(value, max_value_len)
            else:
                truncated[key] = value
        return truncated


__all__ = [
    "HierarchicalLogger",
    "AgentLogger",
    "set_hierarchical_logger",
    "get_hierarchical_logger",
    "set_step_id",
    "get_step_id",
]
