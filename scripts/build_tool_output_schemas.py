from __future__ import annotations

import json
from pathlib import Path

from mcp_agent.knowledge.schema_inference import infer_schema_from_value


def main() -> None:
    samples_path = Path("tool_output_samples.json")
    if not samples_path.exists():
        raise SystemExit("tool_output_samples.json not found; run probe_tool_outputs.py first.")

    samples = json.loads(samples_path.read_text(encoding="utf-8")) or {}
    schemas: dict[str, dict[str, object]] = {}

    for key, sample in samples.items():
        if not isinstance(sample, dict):
            continue

        success_entry = sample.get("success")
        error_entry = sample.get("error")

        success_schema = None
        error_schema = None

        if isinstance(success_entry, dict) and bool(success_entry.get("successful")):
            success_schema = infer_schema_from_value(success_entry.get("data"))

        if isinstance(error_entry, dict) and not bool(error_entry.get("successful")):
            error_data = error_entry.get("data")
            if error_data:
                error_schema = infer_schema_from_value(error_data)

        schemas[key] = {
            "data_schema_success": success_schema,
            "data_schema_error": error_schema,
        }

    Path("tool_output_schemas.json").write_text(json.dumps(schemas, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

