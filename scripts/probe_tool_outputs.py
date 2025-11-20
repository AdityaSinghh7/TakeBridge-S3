from __future__ import annotations

import json
from pathlib import Path

import yaml  # type: ignore[import]

from mcp_agent.knowledge.registry import get_tool_spec
from mcp_agent.types import ActionResponse


def main() -> None:
    config_path = Path("tool_output_samples.yaml")
    if not config_path.exists():
        raise SystemExit("tool_output_samples.yaml not found; create it before probing tool outputs.")

    cfg = yaml.safe_load(config_path.read_text()) or {}
    results: dict[str, dict[str, object]] = {}

    for key, entry in cfg.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("skip"):
            continue

        try:
            provider, tool_name = key.split(".", 1)
        except ValueError:
            print(f"Skipping {key!r}: expected 'provider.tool_name' key.")
            continue

        spec = get_tool_spec(provider, tool_name)
        if spec is None or spec.func is None:
            print(f"Skipping {key!r}: no ToolSpec or func registered.")
            continue

        tool_result: dict[str, object] = {}

        success_cfg = entry.get("success")
        if isinstance(success_cfg, dict):
            args = success_cfg.get("args") or {}
            if not isinstance(args, dict):
                print(f"Skipping success case for {key!r}: args must be a mapping.")
            else:
                resp: ActionResponse = spec.func(**args)  # type: ignore[misc]
                tool_result["success"] = {
                    "successful": bool(resp.get("successful")),
                    "data": resp.get("data"),
                    "error": resp.get("error"),
                }

        error_cfg = entry.get("error")
        if isinstance(error_cfg, dict):
            args = error_cfg.get("args") or {}
            if not isinstance(args, dict):
                print(f"Skipping error case for {key!r}: args must be a mapping.")
            else:
                resp_err: ActionResponse = spec.func(**args)  # type: ignore[misc]
                tool_result["error"] = {
                    "successful": bool(resp_err.get("successful")),
                    "data": resp_err.get("data"),
                    "error": resp_err.get("error"),
                }

        if tool_result:
            results[key] = tool_result

    Path("tool_output_samples.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

