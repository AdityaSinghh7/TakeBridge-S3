#!/usr/bin/env python3
"""Verify hierarchical logging structure and demonstrate usage."""

import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from shared.hierarchical_logger import (
    HierarchicalLogger,
    set_hierarchical_logger,
    get_hierarchical_logger,
    set_step_id,
    get_step_id,
)


def demonstrate_logging_structure():
    """Demonstrate the hierarchical logging structure."""
    print("="*70)
    print("DEMONSTRATING HIERARCHICAL LOGGING STRUCTURE")
    print("="*70)

    # Create a logger for a sample task
    task = "Send an email to John about the quarterly report and schedule a follow-up meeting"
    logger = HierarchicalLogger(task, base_dir="demo_logs")

    print(f"\n✓ Created hierarchical logger for task:")
    print(f"  \"{task}\"")
    print(f"\n  Log directory: {logger.run_dir}")
    print(f"  Task hash: {logger.task_hash}")

    # Set in context
    set_hierarchical_logger(logger)

    # Simulate orchestrator agent logging
    print("\n" + "-"*70)
    print("ORCHESTRATOR AGENT LOGGING")
    print("-"*70)

    orch_logger = logger.get_agent_logger("orchestrator")
    orch_logger.log_event("task.started", {
        "task": task,
        "max_steps": 10,
        "tenant_id": "demo-tenant",
        "request_id": "demo-request-001",
    })

    orch_logger.log_event("planning.started", {
        "step_number": 1,
        "last_failed": False,
    })

    orch_logger.log_event("planning.completed", {
        "decision_type": "next_step",
        "target": "mcp",
        "task_preview": task,
    })

    print("✓ Logged orchestrator events:")
    print(f"  - task.started")
    print(f"  - planning.started")
    print(f"  - planning.completed")

    # Simulate MCP agent logging with step_id
    print("\n" + "-"*70)
    print("MCP AGENT LOGGING (step-001)")
    print("-"*70)

    step_id = "step-mcp-001"
    set_step_id(step_id)

    mcp_logger = logger.get_agent_logger("mcp", step_id)
    mcp_logger.log_event("task.started", {
        "task": "Send email to John",
        "user_id": "demo-user",
        "step_id": step_id,
        "tool_constraints": {"mode": "auto"},
    })

    mcp_logger.log_event("tool.search", {
        "query": "gmail actions",
        "top_k": 5,
    })

    mcp_logger.log_event("tool.selected", {
        "tool": "gmail.send_email",
        "provider": "gmail",
    })

    # Long payload to test truncation
    long_message = "This is a very long email message that will be truncated. " * 20
    mcp_logger.log_event("tool.execution", {
        "tool": "gmail.send_email",
        "params": {
            "to": "john@example.com",
            "subject": "Quarterly Report",
            "body": long_message,
        },
        "success": True,
    })

    print("✓ Logged MCP events:")
    print(f"  - task.started")
    print(f"  - tool.search")
    print(f"  - tool.selected")
    print(f"  - tool.execution (with truncated payload)")

    # Simulate planner sub-logger
    print("\n" + "-"*70)
    print("MCP PLANNER SUB-LOGGER")
    print("-"*70)

    planner_logger = mcp_logger.get_sub_logger("planner")
    planner_logger.log_event("iteration.started", {
        "iteration": 1,
        "state": "planning",
    })

    planner_logger.log_event("iteration.completed", {
        "iteration": 1,
        "action": "use_tool",
        "tool": "gmail.send_email",
    })

    print("✓ Logged planner events:")
    print(f"  - iteration.started")
    print(f"  - iteration.completed")

    # Simulate computer_use agent logging
    print("\n" + "-"*70)
    print("COMPUTER USE AGENT LOGGING (step-002)")
    print("-"*70)

    step_id_2 = "step-cu-002"
    set_step_id(step_id_2)

    cu_logger = logger.get_agent_logger("computer_use", step_id_2)
    cu_logger.log_event("task.started", {
        "task": "Schedule follow-up meeting",
        "step_id": step_id_2,
    })

    worker_logger = cu_logger.get_sub_logger("worker")
    worker_logger.log_event("step.started", {
        "step": 1,
        "turn_count": 0,
    })

    worker_logger.log_event("step.completed", {
        "step": 1,
        "plan": "Open calendar app",
        "has_reflection": False,
    })

    code_logger = cu_logger.get_sub_logger("code_agent")
    code_logger.log_event("session.started", {
        "task": "Add calendar event",
        "budget": 20,
    })

    code_logger.log_event("session.completed", {
        "completion_reason": "DONE",
        "steps_executed": 3,
        "summary": "Successfully created calendar event",
    })

    print("✓ Logged computer_use events:")
    print(f"  - task.started")
    print(f"  - worker.step.started")
    print(f"  - worker.step.completed")
    print(f"  - code_agent.session.started")
    print(f"  - code_agent.session.completed")

    # Display directory structure
    print("\n" + "="*70)
    print("GENERATED LOG DIRECTORY STRUCTURE")
    print("="*70)

    def print_tree(directory, prefix="", max_files=3):
        """Print directory tree."""
        try:
            paths = sorted(directory.iterdir())
            dirs = [p for p in paths if p.is_dir()]
            files = [p for p in paths if p.is_file()]

            # Print directories first
            for i, path in enumerate(dirs):
                is_last_dir = (i == len(dirs) - 1) and len(files) == 0
                connector = "└── " if is_last_dir else "├── "
                print(f"{prefix}{connector}{path.name}/")

                extension = "    " if is_last_dir else "│   "
                print_tree(path, prefix + extension, max_files)

            # Print files
            files_to_show = files[:max_files]
            remaining = len(files) - max_files

            for i, path in enumerate(files_to_show):
                is_last = i == len(files_to_show) - 1 and remaining == 0
                connector = "└── " if is_last else "├── "

                # Show file size
                size = path.stat().st_size
                size_str = f"{size:,} bytes" if size < 1024 else f"{size/1024:.1f} KB"
                print(f"{prefix}{connector}{path.name} ({size_str})")

            if remaining > 0:
                print(f"{prefix}└── ... {remaining} more file(s)")

        except PermissionError:
            print(f"{prefix}[Permission Denied]")

    print(f"\n{logger.run_dir}/")
    print_tree(logger.run_dir)

    # Show sample log content
    print("\n" + "="*70)
    print("SAMPLE LOG CONTENT")
    print("="*70)

    # Show orchestrator main log (first few events)
    orch_main_log = logger.run_dir / "orchestrator" / "main.jsonl"
    if orch_main_log.exists():
        print(f"\n{orch_main_log.relative_to(logger.run_dir)}:")
        print("-" * 60)
        with open(orch_main_log) as f:
            lines = f.readlines()[:3]
            for line in lines:
                event = json.loads(line)
                print(f"[{event['timestamp']}] {event['event']}")
                # Show truncated data
                data_str = json.dumps(event['data'], indent=2)
                if len(data_str) > 200:
                    data_str = data_str[:200] + "..."
                print(f"  {data_str}")

    # Show MCP main log
    mcp_main_log = logger.run_dir / "mcp" / "step-mcp-001" / "main.jsonl"
    if mcp_main_log.exists():
        print(f"\n{mcp_main_log.relative_to(logger.run_dir)}:")
        print("-" * 60)
        with open(mcp_main_log) as f:
            lines = f.readlines()[:2]
            for line in lines:
                event = json.loads(line)
                print(f"[{event['timestamp']}] {event['event']}")

    print("\n" + "="*70)
    print("VERIFICATION COMPLETE")
    print("="*70)
    print(f"\nFull logs available at: {logger.run_dir}")
    print("\nKey features demonstrated:")
    print("  ✓ Hierarchical directory structure")
    print("  ✓ Agent-specific logging (orchestrator, mcp, computer_use)")
    print("  ✓ Step-based separation (step_id directories)")
    print("  ✓ Sub-logger support (planner, worker, code_agent)")
    print("  ✓ Payload truncation (500 char limit)")
    print("  ✓ Metadata tracking (timestamps, task info)")
    print("  ✓ JSONL format for easy parsing")

    return logger.run_dir


if __name__ == "__main__":
    log_dir = demonstrate_logging_structure()
    print(f"\nTo explore the logs:\n  cd {log_dir}")
    print(f"  find . -name '*.jsonl' | head -5")
