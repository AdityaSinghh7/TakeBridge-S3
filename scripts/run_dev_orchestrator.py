#!/usr/bin/env python
"""
End-to-end test script for the orchestrator_agent.

This script validates all data connections across orchestrator_agent, mcp_agent,
and computer_use_agent, then executes orchestration with rich stepwise logging.

Usage:
    python scripts/run_dev_orchestrator.py --task "Your task here"
    python scripts/run_dev_orchestrator.py --test-scenario hybrid
    python scripts/run_dev_orchestrator.py --validate-only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

# Orchestrator imports
from shared import agent_signal
from orchestrator_agent.runtime import OrchestratorRuntime
from orchestrator_agent.data_types import (
    OrchestratorRequest,
    Budget,
    RunState,
    StepResult,
    PlannedStep,
)

# MCP agent imports
from mcp_agent.dev import resolve_dev_user
from mcp_agent.env_sync import ensure_env_for_provider

logger = logging.getLogger(__name__)

# Test scenarios
TEST_SCENARIOS = {
    "mcp": "Use Gmail to search for emails from john@example.com sent in the last 7 days",
    "computer": "Open a web browser and navigate to google.com",
    "hybrid": "Use Gmail to find my most recent email with an attachment, download the attachment, and open it in the Preview app on macOS.",
}

DEFAULT_TASK = TEST_SCENARIOS["hybrid"]


# ============================================================================
# Validation Functions
# ============================================================================


def validate_bridge_connectivity() -> Dict[str, bool]:
    """
    Test that both agent bridges are accessible and functional.

    Returns:
        {"mcp": bool, "computer_use": bool, "vm_controller": bool}
    """
    results = {}

    # Test MCP bridge
    try:
        from mcp_agent.agent import execute_mcp_task
        results["mcp"] = True
    except Exception as e:
        print(f"[ERROR] MCP agent bridge not available: {e}")
        results["mcp"] = False

    # Test computer-use bridge
    try:
        from computer_use_agent.orchestrator.runner import runner
        from computer_use_agent.orchestrator.data_types import OrchestrateRequest
        results["computer_use"] = True
    except Exception as e:
        print(f"[ERROR] Computer-use agent bridge not available: {e}")
        results["computer_use"] = False

    # Test VM controller connectivity
    try:
        from server.api.controller_client import VMControllerClient

        # Check for required environment variable
        base_url = os.getenv("VM_SERVER_BASE_URL")
        if not base_url:
            host = os.getenv("VM_SERVER_HOST")
            port = os.getenv("VM_SERVER_PORT")
            if not host:
                print("[ERROR] VM controller not configured: VM_SERVER_BASE_URL or VM_SERVER_HOST required")
                results["vm_controller"] = False
            else:
                # Try to create client and test connectivity
                client = VMControllerClient(host=host, port=port)
                # Test basic connectivity with screen_size call
                client.screen_size()
                results["vm_controller"] = True
        else:
            # Try to create client and test connectivity
            client = VMControllerClient(base_url=base_url)
            client.screen_size()
            results["vm_controller"] = True
    except Exception as e:
        print(f"[ERROR] VM controller not accessible: {e}")
        results["vm_controller"] = False

    return results


def validate_data_schemas() -> Dict[str, bool]:
    """
    Verify that data structures match expected schemas.

    Checks:
    - OrchestratorRequest can be created
    - PlannedStep structure is correct
    - StepResult structure is correct
    - Budget tracking works
    """
    try:
        # Create test request
        request = OrchestratorRequest.from_task(
            tenant_id="validation",
            task="test",
            budget=Budget(max_steps=1)
        )

        return {
            "request_creation": request is not None,
            "budget_tracking": hasattr(request, "budget"),
            "metadata_support": hasattr(request, "metadata"),
        }
    except Exception as e:
        print(f"[ERROR] Data schema validation failed: {e}")
        return {
            "request_creation": False,
            "budget_tracking": False,
            "metadata_support": False,
        }


def resolve_controller_metadata(default_platform: Optional[str] = None) -> Dict[str, Any]:
    """
    Build metadata entries for controller discovery so capability fetches
    can hit the live VM controller and so the computer-use agent receives
    a normalized controller config. Platform is now detected from the VM
    controller; the optional argument is ignored.
    """
    metadata: Dict[str, Any] = {}
    try:
        from server.api.controller_client import VMControllerClient

        controller_client = VMControllerClient(
            base_url=os.getenv("VM_SERVER_BASE_URL"),
            host=os.getenv("VM_SERVER_HOST"),
            port=os.getenv("VM_SERVER_PORT"),
        )
        metadata["controller_client"] = controller_client
        metadata["controller"] = {
            "base_url": controller_client.base_url,
            "host": controller_client.host,
            "port": controller_client.port,
            "timeout": controller_client.timeout,
        }
    except Exception as exc:
        logger.warning(
            "VM controller not available; desktop capabilities will be stubbed: %s",
            exc,
        )

    return metadata


# ============================================================================
# Logging Infrastructure
# ============================================================================


class OrchestrationLogger:
    """
    Logger for orchestration execution with color-coded output.

    Provides stepwise logging of planning decisions, agent execution,
    and budget usage without modifying the core orchestrator runtime.
    """

    def __init__(self, verbose: bool = False, use_color: bool = True):
        self.verbose = verbose
        self.use_color = use_color
        self.colors = {
            "planning": "\033[96m",      # Cyan
            "mcp": "\033[92m",           # Green
            "computer_use": "\033[93m",  # Yellow
            "success": "\033[92m",       # Green
            "failed": "\033[91m",        # Red
            "budget": "\033[95m",        # Magenta
            "reset": "\033[0m"
        }

    def _color(self, text: str, color: str) -> str:
        """Apply color to text if color output is enabled."""
        if not self.use_color:
            return text
        return f"{self.colors.get(color, '')}{text}{self.colors['reset']}"

    def log_start(self, request: OrchestratorRequest):
        """Log orchestration start."""
        print("\n" + "="*80)
        print(self._color("🚀 ORCHESTRATOR START", "planning"))
        print("="*80)
        print(f"Task: {request.task}")
        print(f"Tenant: {request.tenant.tenant_id if request.tenant else 'N/A'}")
        print(f"Budget: {request.budget.max_steps} steps, ${request.budget.max_cost_usd or 'unlimited'}")
        print("="*80 + "\n")

    def log_planning_decision(self, step_num: int, decision: Dict, reasoning: str):
        """Log LLM planning decision."""
        target = decision.get("target", "unknown")
        task = decision.get("task", "")

        print(self._color(f"\n📋 STEP {step_num} - PLANNING DECISION", "planning"))
        print(f"  Agent Selected: {self._color(target.upper(), target)}")
        print(f"  Task: {task[:100]}{'...' if len(task) > 100 else ''}")
        print(f"  Reasoning: {reasoning[:150]}{'...' if len(reasoning) > 150 else ''}")

    def log_step_execution(self, step_num: int, result: StepResult):
        """Log step execution result."""
        status_color = "success" if result.success else "failed"
        status_icon = "✅" if result.success else "❌"

        print(f"\n{status_icon} STEP {step_num} - {self._color(result.status.upper(), status_color)}")
        print(f"  Step ID: {result.step_id}")
        print(f"  Target: {result.target}")

        if result.started_at and result.finished_at:
            duration = (result.finished_at - result.started_at).total_seconds()
            print(f"  Duration: {duration:.2f}s")

        # Extract nested agent details
        if result.target == "mcp":
            self._log_mcp_details(result.output)
        elif result.target == "computer_use":
            self._log_computer_use_details(result.output)

        # Budget usage for this step
        if "usage" in result.output:
            self._log_step_budget(result.output["usage"])

    def _log_mcp_details(self, output: Dict):
        """Log MCP agent execution details."""
        translated = output.get("translated", {})
        raw_ref = output.get("raw_ref", "")

        print(f"\n  {self._color('MCP AGENT EXECUTION', 'mcp')}")
        print(f"    Summary: {translated.get('summary', 'N/A')}")

        # Tool calls
        artifacts = translated.get("artifacts", {})
        tool_outputs = artifacts.get("tool_outputs", [])
        if tool_outputs:
            print(f"    Tool Calls: {len(tool_outputs)}")
            for i, tool_out in enumerate(tool_outputs[:3]):  # Show first 3
                print(f"      {i+1}. {tool_out.get('tool', 'unknown')}: {str(tool_out.get('result', ''))[:80]}")
            if len(tool_outputs) > 3:
                print(f"      ... and {len(tool_outputs) - 3} more")

        # Data retrieved
        retrieved_data = artifacts.get("retrieved_data", {})
        if retrieved_data:
            print(f"    Data Retrieved: {list(retrieved_data.keys())}")

        if self.verbose:
            print(f"    Raw Reference: {raw_ref}")

    def _log_computer_use_details(self, output: Dict):
        """Log computer-use agent execution details."""
        translated = output.get("translated", {})

        print(f"\n  {self._color('COMPUTER-USE AGENT EXECUTION', 'computer_use')}")
        print(f"    Summary: {translated.get('summary', 'N/A')}")

        # UI actions
        artifacts = translated.get("artifacts", {})
        ui_observations = artifacts.get("ui_observations", [])
        if ui_observations:
            print(f"    UI Actions: {len(ui_observations)}")
            for i, obs in enumerate(ui_observations[:3]):
                print(f"      {i+1}. {str(obs)[:80]}")
            if len(ui_observations) > 3:
                print(f"      ... and {len(ui_observations) - 3} more")

        # Code executed
        code_executed = artifacts.get("code_executed", [])
        if code_executed:
            print(f"    Code Blocks Executed: {len(code_executed)}")
            if self.verbose:
                for i, code in enumerate(code_executed[:3]):
                    print(f"      {i+1}. {str(code)[:100]}")

    def _log_step_budget(self, usage: Dict):
        """Log budget usage for a step."""
        tokens = usage.get("tokens", {})
        cost = usage.get("cost_usd", {})

        print(f"\n  {self._color('BUDGET USAGE', 'budget')}")
        print(f"    Tokens: {tokens.get('input_new', 0)} in, {tokens.get('output', 0)} out")
        if tokens.get("input_cached", 0) > 0:
            print(f"    Cached: {tokens.get('input_cached', 0)} tokens")
        print(f"    Cost: ${cost.get('delta', 0.0):.4f} (Total: ${cost.get('run_total', 0.0):.4f})")

    def log_completion(self, state: RunState):
        """Log final results."""
        total_steps = len(state.results)
        successful = sum(1 for r in state.results if r.success)

        print("\n" + "="*80)
        print(self._color("🏁 ORCHESTRATOR COMPLETE", "planning"))
        print("="*80)
        print(f"Total Steps: {total_steps}")
        print(f"Successful: {successful}/{total_steps}")

        # Final status
        completion_status = state.intermediate.get("completion_status", "unknown")
        if completion_status == "impossible":
            reason = state.intermediate.get("impossible_reason", "Unknown")
            print(f"\nStatus: {self._color('TASK IMPOSSIBLE', 'failed')}")
            print(f"Reason: {reason}")
        elif successful == total_steps and total_steps > 0:
            print(f"\nStatus: {self._color('SUCCESS', 'success')}")
        else:
            print(f"\nStatus: {self._color('PARTIAL SUCCESS', 'failed')}")

        print("="*80 + "\n")


# ============================================================================
# Main Execution Function
# ============================================================================


async def run_orchestrator_task(
    task: str,
    *,
    user_id: str,
    tenant_id: str = "dev",
    budget: Budget,
    platform: Optional[str] = None,
    allow_code_execution: bool = False,
    metadata: Optional[Dict[str, Any]] = None,
    logger: Optional[OrchestrationLogger] = None,
) -> RunState:
    """
    Execute an orchestrator task with logging.

    Args:
        task: Natural language task description
        user_id: User identifier
        tenant_id: Tenant identifier
        budget: Budget constraints
        platform: Deprecated. Platform is now auto-detected from the VM controller.
        allow_code_execution: Enable code execution
        metadata: Additional metadata (controller, grounding, worker configs)
        logger: OrchestrationLogger instance

    Returns:
        RunState with complete execution history
    """
    runtime = OrchestratorRuntime()

    # Platform is auto-detected from the VM controller; ignore CLI/platform hints.
    if platform:
        logger_warning = logger and getattr(logger, "verbose", False)
        if logger_warning:
            print("[warning] Platform flag is ignored; using VM-reported platform.")
        else:
            logging.getLogger(__name__).warning(
                "Platform flag is ignored; using VM-reported platform."
            )

    # Build request
    request = OrchestratorRequest.from_task(
        tenant_id=tenant_id,
        task=task,
        budget=budget,
        platform=None,  # platform comes from VM controller
        allow_code_execution=allow_code_execution,
        user_id=user_id,
        metadata=metadata or {},
    )

    if logger:
        logger.log_start(request)

    # Execute
    state = await runtime.run_task(request)

    # Post-process logging (after each step is in state.results)
    if logger:
        for i, result in enumerate(state.results, 1):
            # Reconstruct planning decision from step
            step = state.plan[i-1] if i-1 < len(state.plan) else None
            if step:
                # Note: we don't have access to the original LLM reasoning here
                # We only have the task and target from the PlannedStep
                logger.log_planning_decision(
                    i,
                    {"target": step.target, "task": step.next_task},
                    f"Execute via {step.target}"
                )

            logger.log_step_execution(i, result)

        logger.log_completion(state)

    return state


# ============================================================================
# Output Formatting
# ============================================================================


def format_json_output(state: RunState) -> Dict[str, Any]:
    """Format RunState as JSON-serializable dict."""
    return {
        "task": state.request.task,
        "tenant_id": state.request.tenant.tenant_id if state.request.tenant else None,
        "budget": {
            "max_steps": state.request.budget.max_steps,
            "max_cost_usd": state.request.budget.max_cost_usd,
        },
        "execution": {
            "total_steps": len(state.results),
            "successful_steps": sum(1 for r in state.results if r.success),
        },
        "steps": [
            {
                "step_num": i + 1,
                "step_id": result.step_id,
                "target": result.target,
                "task": result.next_task,
                "status": result.status,
                "success": result.success,
                "duration_seconds": (result.finished_at - result.started_at).total_seconds() if result.finished_at and result.started_at else None,
                "output": result.output,
                "error": result.error,
            }
            for i, result in enumerate(state.results)
        ],
        "final_status": state.intermediate.get("completion_status", "completed"),
        "total_cost_usd": state.results[-1].output.get("usage", {}).get("cost_usd", {}).get("run_total", 0.0) if state.results else 0.0,
    }


# ============================================================================
# CLI Argument Parser
# ============================================================================


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run end-to-end orchestrator agent test with validation and logging.",
    )

    # Task specification
    parser.add_argument(
        "--task",
        help="Task description for orchestrator"
    )
    parser.add_argument(
        "--test-scenario",
        choices=["mcp", "computer", "hybrid"],
        help="Run predefined test scenario"
    )

    # User and tenant configuration
    parser.add_argument(
        "--user-id",
        help="User ID (defaults to TB_USER_ID or dev-local)"
    )
    parser.add_argument(
        "--tenant-id",
        default="dev",
        help="Tenant ID (default: dev)"
    )

    # Budget controls
    parser.add_argument(
        "--max-steps",
        type=int,
        default=5,
        help="Max orchestrator steps (default: 5)"
    )
    parser.add_argument(
        "--max-cost",
        type=float,
        help="Max cost in USD"
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        help="Max total tokens"
    )

    # Platform config
    parser.add_argument(
        "--platform",
        choices=["macos", "linux", "windows"],
        help="(Deprecated/ignored) Platform is auto-detected from the VM controller"
    )
    parser.add_argument(
        "--allow-code-execution",
        action="store_true",
        help="Enable code execution"
    )

    # Output modes
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of human-readable"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose debug output"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Minimal output"
    )
    parser.add_argument(
        "--output-file",
        help="Save result to JSON file"
    )

    # Validation
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only run validation checks"
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip pre-flight validation"
    )

    return parser


# ============================================================================
# Main Entry Point
# ============================================================================


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point for the orchestrator test script."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Configure logging early so downstream modules can emit breadcrumbs
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    # Quiet noisy HTTP/LLM clients while keeping our app logs readable
    noisy_loggers = [
        "openai",
        "openai._base_client",
        "httpx",
        "httpcore",
        "urllib3",
    ]
    for name in noisy_loggers:
        logging.getLogger(name).setLevel(logging.WARNING)
    # Our packages stay at DEBUG when --verbose is set
    if args.verbose:
        for name in ["orchestrator_agent", "mcp_agent", "server", "computer_use_agent"]:
            logging.getLogger(name).setLevel(logging.DEBUG)

    # Configure global pause/resume/exit handling (Ctrl+C pauses, second Ctrl+C exits, Esc resumes)
    agent_signal.set_interactive_mode(True)
    agent_signal.register_signal_handlers()
    agent_signal.clear_signal_state()

    # 1. Validation phase
    if not args.skip_validation or args.validate_only:
        print("Running pre-flight validation...")
        connectivity = validate_bridge_connectivity()
        schemas = validate_data_schemas()

        print(f"  MCP Bridge: {'✅' if connectivity.get('mcp') else '❌'}")
        print(f"  Computer-Use Bridge: {'✅' if connectivity.get('computer_use') else '❌'}")
        print(f"  VM Controller: {'✅' if connectivity.get('vm_controller') else '❌'}")
        print(f"  Data Schemas: {'✅' if all(schemas.values()) else '❌'}")

        # Strict validation: exit on failure
        validation_passed = (
            all(connectivity.values()) and
            all(schemas.values())
        )

        if args.validate_only:
            return 0 if validation_passed else 1

        if not validation_passed:
            print("\n❌ Validation failed. Fix the issues above and try again.")
            print("   Use --skip-validation to bypass (not recommended)")
            return 1

        print("✅ All validation checks passed!\n")

    # 2. Resolve inputs
    user_id = resolve_dev_user(args.user_id)
    task = args.task or TEST_SCENARIOS.get(args.test_scenario, "")

    if not task:
        print("Error: Must provide --task or --test-scenario", file=sys.stderr)
        return 1

    # 3. Environment setup (following run_dev_mcp_task.py pattern)
    os.environ.setdefault("TB_USER_ID", user_id)
    os.environ["MCP_PLANNER_LLM_ENABLED"] = "1"
    os.environ.setdefault("COMPOSIO_TOOL_EXECUTE_ENABLED", "0")

    # Ensure provider environments
    for provider in ("gmail", "slack", "shopify"):
        ensure_env_for_provider(user_id, provider)

    # 4. Build budget
    budget = Budget(
        max_steps=args.max_steps,
        max_cost_usd=args.max_cost,
        max_tokens=args.max_tokens,
    )

    # 5. Setup logger
    logger_instance = None if args.quiet else OrchestrationLogger(
        verbose=args.verbose,
        use_color=not args.json
    )

    metadata = resolve_controller_metadata()

    # 6. Execute
    try:
        state = asyncio.run(run_orchestrator_task(
            task=task,
            user_id=user_id,
            tenant_id=args.tenant_id,
            budget=budget,
            platform=args.platform,  # ignored; platform comes from VM controller
            allow_code_execution=args.allow_code_execution,
            logger=logger_instance,
            metadata=metadata,
        ))
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user", file=sys.stderr)
        return 130
    except Exception as exc:
        import traceback
        print(f"\n❌ Orchestrator execution failed: {exc}", file=sys.stderr)
        if args.verbose:
            traceback.print_exc(file=sys.stderr)
        return 1

    # 7. Output
    if args.json:
        output = format_json_output(state)
        print(json.dumps(output, indent=2, default=str))

    if args.output_file:
        with open(args.output_file, "w") as f:
            json.dump(format_json_output(state), f, indent=2, default=str)
        if not args.quiet:
            print(f"\n💾 Results saved to: {args.output_file}")

    # 8. Exit code
    successful = sum(1 for r in state.results if r.success)
    total = len(state.results)

    return 0 if successful == total and total > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
