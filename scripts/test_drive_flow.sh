#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
AUTH_TOKEN="${AUTH_TOKEN:-}"
RUN_ID="${RUN_ID:-}"
WORKFLOW_ID="${WORKFLOW_ID:-}"
DRIVE_PATHS="${DRIVE_PATHS:-}"
WAIT_SECONDS="${WAIT_SECONDS:-0}"
VALIDATE_URLS="${VALIDATE_URLS:-0}"

if [[ -z "${AUTH_TOKEN}" ]]; then
  echo "AUTH_TOKEN is required (Bearer token)." >&2
  exit 1
fi

auth_header="Authorization: Bearer ${AUTH_TOKEN}"

if [[ -z "${RUN_ID}" && -n "${WORKFLOW_ID}" ]]; then
  payload='{}'
  if [[ -n "${DRIVE_PATHS}" ]]; then
    payload="$(python - <<'PY'
import json
import os

paths = [p.strip() for p in os.environ.get("DRIVE_PATHS", "").split(",") if p.strip()]
print(json.dumps({"drive_paths": paths}))
PY
)"
  fi

  run_resp="$(curl -sS -X POST \
    -H "${auth_header}" \
    -H "Content-Type: application/json" \
    -d "${payload}" \
    "${API_BASE_URL}/api/workflows/${WORKFLOW_ID}/run")"

  RUN_ID="$(RUN_RESP="${run_resp}" python - <<'PY'
import json
import os
data = json.loads(os.environ["RUN_RESP"])
print(data.get("run_id") or data.get("id") or "")
PY
)"
  if [[ -z "${RUN_ID}" ]]; then
    echo "Failed to extract run_id from response:" >&2
    echo "${run_resp}" >&2
    exit 1
  fi
  echo "Started run_id=${RUN_ID}"
fi

if [[ -z "${RUN_ID}" ]]; then
  echo "RUN_ID is required (or set WORKFLOW_ID to create a run)." >&2
  exit 1
fi

if [[ "${WAIT_SECONDS}" != "0" ]]; then
  echo "Waiting ${WAIT_SECONDS}s for run completion..."
  sleep "${WAIT_SECONDS}"
fi

summary_json="$(curl -sS \
  -H "${auth_header}" \
  "${API_BASE_URL}/api/runs/${RUN_ID}/drive-summary")"

SUMMARY_JSON="${summary_json}" python - <<'PY'
import json
import os

data = json.loads(os.environ["SUMMARY_JSON"])
changes = data.get("changes", [])
new_files = data.get("new_files", [])
unchanged = data.get("unchanged", [])

print(f"changes={len(changes)} new_files={len(new_files)} unchanged={len(unchanged)}")

def show(label, items, extra_keys=()):
    if not items:
        return
    print(f"\n{label}:")
    for item in items:
        path = item.get("path")
        ctype = item.get("content_type")
        change_type = item.get("change_type")
        extras = " ".join(
            f"{k}={item.get(k)}" for k in extra_keys if item.get(k)
        )
        bits = [path or "<missing>", ctype or "unknown"]
        if change_type:
            bits.append(change_type)
        if extras:
            bits.append(extras)
        print(" - " + " | ".join(bits))

show("New files", new_files)
show("Changed files", changes, extra_keys=("backup_get_url",))
show("Unchanged files", unchanged)
PY

if [[ "${VALIDATE_URLS}" != "0" ]]; then
  SUMMARY_JSON="${summary_json}" python - <<'PY'
import json
import os
from subprocess import check_output, CalledProcessError

data = json.loads(os.environ["SUMMARY_JSON"])
urls = []
for item in data.get("changes", []):
    url = item.get("current_get_url")
    if url:
        urls.append(("current", item.get("path"), url))
    backup = item.get("backup_get_url")
    if backup:
        urls.append(("backup", item.get("path"), backup))
for item in data.get("unchanged", []):
    url = item.get("current_get_url")
    if url:
        urls.append(("unchanged", item.get("path"), url))
for item in data.get("new_files", []):
    url = item.get("current_get_url")
    if url:
        urls.append(("new", item.get("path"), url))

for label, path, url in urls:
    try:
        code = check_output(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", url],
            text=True,
        ).strip()
    except CalledProcessError as exc:
        code = f"error:{exc}"
    print(f"{label} {path} -> {code}")
PY
fi
