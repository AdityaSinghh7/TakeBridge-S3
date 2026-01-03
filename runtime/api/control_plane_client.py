from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import requests

CONTROL_PLANE_BASE_URL = os.getenv("CONTROL_PLANE_BASE_URL", "https://127.0.0.1:8000").rstrip("/")
CONTROL_PLANE_VERIFY_SSL = os.getenv("CONTROL_PLANE_VERIFY_SSL", "false").lower() in {"1", "true", "yes", "on"}
CONTROL_PLANE_CA_BUNDLE = os.getenv("CONTROL_PLANE_CA_BUNDLE") or os.getenv("REQUESTS_CA_BUNDLE") or os.getenv(
    "CURL_CA_BUNDLE"
)


class ControlPlaneError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _build_verify() -> object:
    if CONTROL_PLANE_CA_BUNDLE:
        return CONTROL_PLANE_CA_BUNDLE
    return CONTROL_PLANE_VERIFY_SSL


def _should_trust_env(url: str) -> bool:
    try:
        hostname = (urlparse(url).hostname or "").lower()
        return hostname not in {"127.0.0.1", "localhost"}
    except Exception:
        return True


@dataclass
class ControlPlaneClient:
    base_url: str = CONTROL_PLANE_BASE_URL
    internal_token: str = (os.getenv("INTERNAL_API_TOKEN") or "").strip()

    def __post_init__(self) -> None:
        self._session = requests.Session()
        self._session.verify = _build_verify()
        if not _should_trust_env(self.base_url):
            self._session.trust_env = False

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self.internal_token:
            headers["X-Internal-Token"] = self.internal_token
            headers["Authorization"] = f"Bearer {self.internal_token}"
        return headers

    def _request(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None, json_body: Any = None) -> Any:
        url = f"{self.base_url}{path}"
        resp = self._session.request(method, url, headers=self._headers(), params=params, json=json_body, timeout=30)
        if resp.status_code >= 400:
            detail = resp.text
            raise ControlPlaneError(resp.status_code, detail)
        if not resp.content:
            return None
        try:
            return resp.json()
        except Exception:
            return resp.text

    def get_run_context(self, run_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/internal/runs/{run_id}/context")

    def get_resume_context(self, run_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/internal/runs/{run_id}/resume-context")

    def persist_run_event(self, run_id: str, event: str, payload: Optional[Dict[str, Any]] = None, message: str | None = None) -> None:
        body = {"event": event, "payload": payload or {}}
        if message is not None:
            body["message"] = message
        self._request("POST", f"/internal/runs/{run_id}/events", json_body=body)

    def update_run_status(self, run_id: str, status: str, summary: Optional[str] = None) -> None:
        body: Dict[str, Any] = {"status": status}
        if summary is not None:
            body["summary"] = summary
        self._request("POST", f"/internal/runs/{run_id}/status", json_body=body)

    def merge_environment(self, run_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", f"/internal/runs/{run_id}/environment", json_body={"patch": patch})

    def register_vm(
        self,
        run_id: str,
        *,
        vm_id: str,
        endpoint: Dict[str, Any],
        provider: str,
        spec: Dict[str, Any],
    ) -> None:
        body = {"vm_id": vm_id, "endpoint": endpoint, "provider": provider, "spec": spec}
        self._request("POST", f"/internal/runs/{run_id}/vm", json_body=body)

    def merge_agent_states(self, run_id: str, patch: Dict[str, Any], *, path: Optional[list[str]] = None) -> None:
        body: Dict[str, Any] = {"patch": patch}
        if path is not None:
            body["path"] = path
        self._request("POST", f"/internal/runs/{run_id}/agent-states", json_body=body)

    def get_drive_files(self, run_id: str, *, ensure_full: bool) -> Dict[str, Any]:
        params = {"ensure_full": "true"} if ensure_full else {}
        return self._request("GET", f"/internal/runs/{run_id}/drive-files", params=params)

    def update_drive_file_status(self, run_id: str, payload: Dict[str, Any]) -> None:
        self._request("POST", f"/internal/runs/{run_id}/drive-files/status", json_body=payload)

    def list_drive_changes(self, run_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/internal/runs/{run_id}/drive-changes")

    def upsert_drive_changes(
        self, run_id: str, *, changes: list[Dict[str, Any]], new_files: list[Dict[str, Any]]
    ) -> None:
        self._request(
            "POST",
            f"/internal/runs/{run_id}/drive-changes/upsert",
            json_body={"changes": changes, "new_files": new_files},
        )

    def update_drive_change_status(self, run_id: str, *, path: str, status: str, error: Optional[str] = None) -> None:
        body: Dict[str, Any] = {"path": path, "status": status}
        if error:
            body["error"] = error
        self._request("POST", f"/internal/runs/{run_id}/drive-changes/status", json_body=body)

    def fetch_mcp_capabilities(self, user_id: str, *, force_refresh: bool = False) -> Dict[str, Any]:
        params = {"force_refresh": "true"} if force_refresh else {}
        return self._request("GET", f"/internal/users/{user_id}/mcp-capabilities", params=params)
