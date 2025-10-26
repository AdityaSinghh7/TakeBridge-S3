"""
Client-side helper for interacting with the VM controller service.

The VM service exposes a Flask API (see server implementation in vm source).
This module provides a lightweight wrapper that:
  * Discovers the controller host/port from `.env` at the repo root.
  * Reuses a `requests.Session` for efficiency.
  * Exposes higher-level methods for the common VM endpoints.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence, Union
from urllib.parse import urlparse, urlunparse

import requests

try:
    # Optional dependency used to load `.env` files if present.
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover
    load_dotenv = None

JsonDict = Dict[str, Any]
Command = Union[str, Sequence[str]]

_DEFAULT_ENV_FILENAME = ".env"
_HOST_ENV_VAR = "VM_SERVER_HOST"
_PORT_ENV_VAR = "VM_SERVER_PORT"
_BASE_URL_ENV_VAR = "VM_SERVER_BASE_URL"


class VMControllerError(RuntimeError):
    """Raised when the controller returns an unexpected response."""

    def __init__(self, message: str, *, status_code: Optional[int] = None, payload: Optional[Any] = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


def _load_repo_dotenv(explicit_path: Optional[Union[str, Path]] = None) -> Optional[Path]:
    """
    Attempt to load environment variables from the repo's `.env`.

    Returns the path that was loaded (if any). No error is raised if dotenv is unavailable.
    """
    if load_dotenv is None:
        return None

    if explicit_path:
        dot_path = Path(explicit_path).expanduser().resolve()
        if dot_path.is_file():
            load_dotenv(dot_path, override=False)
            return dot_path
        return None

    repo_root = Path(__file__).resolve().parents[2]
    dot_path = repo_root / _DEFAULT_ENV_FILENAME
    if dot_path.is_file():
        load_dotenv(str(dot_path), override=False)
        return dot_path
    return None


def _normalize_base_url(host: Optional[str], port: Optional[Union[str, int]], *, scheme: str = "http") -> str:
    """
    Build a normalized base URL from separate host/port values.
    """
    clean_host = host or "127.0.0.1"
    clean_port = str(port or "5000")
    parsed = urlparse(clean_host if "://" in clean_host else f"{scheme}://{clean_host}")
    netloc = parsed.netloc or parsed.path  # Handle raw host
    if ":" not in netloc and clean_port:
        netloc = f"{netloc}:{clean_port}"
    return urlunparse((parsed.scheme or scheme, netloc, "", "", "", ""))


@dataclass
class VMControllerClient:
    """
    High-level client wrapper for the VM controller Flask service.

    Parameters:
        base_url: Optional manual override (e.g., "http://10.0.0.5:5001").
        host: Overrides env-derived host when provided.
        port: Overrides env-derived port when provided.
        timeout: Default request timeout (seconds) applied to each call.
        dotenv_path: Optional path to the `.env` file that provides host/port.
        session: Optional existing `requests.Session` to reuse.
    """

    base_url: Optional[str] = None
    host: Optional[str] = None
    port: Optional[Union[str, int]] = None
    timeout: float = 30.0
    dotenv_path: Optional[Union[str, Path]] = None
    session: Optional[requests.Session] = None

    def __post_init__(self) -> None:
        _load_repo_dotenv(self.dotenv_path)

        if self.base_url:
            parsed = urlparse(self.base_url)
            if not parsed.scheme:
                self.base_url = f"http://{self.base_url}"
        else:
            env_base = os.getenv(_BASE_URL_ENV_VAR)
            env_host = os.getenv(_HOST_ENV_VAR)
            env_port = os.getenv(_PORT_ENV_VAR)
            resolved_host = self.host or env_host
            resolved_port = self.port or env_port

            if env_base and not (resolved_host or resolved_port):
                base_url = env_base.strip()
                if not urlparse(base_url).scheme:
                    base_url = f"http://{base_url}"
                self.base_url = base_url
            else:
                self.base_url = _normalize_base_url(resolved_host, resolved_port)

        self._session = self.session or requests.Session()

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[JsonDict] = None,
        json: Optional[JsonDict] = None,
        data: Optional[Any] = None,
        files: Optional[Any] = None,
        expected_status: Iterable[int] = (200, 201),
        stream: bool = False,
        timeout: Optional[float] = None,
    ) -> requests.Response:
        url = f"{self.base_url}{path}"
        response = self._session.request(
            method,
            url,
            params=params,
            json=json,
            data=data,
            files=files,
            timeout=timeout or self.timeout,
            stream=stream,
        )
        if response.status_code not in expected_status:
            raise VMControllerError(
                f"Controller request to {path} failed with HTTP {response.status_code}",
                status_code=response.status_code,
                payload=_safe_json(response),
            )
        return response

    # ------------------------------------------------------------------ #
    # Public api methods
    # ------------------------------------------------------------------ #

    def execute(self, command: Command, *, shell: bool = False, setup: bool = False, timeout: Optional[float] = None) -> JsonDict:
        """
        Execute a command on the VM (`/execute` or `/setup/execute`).
        """
        path = "/setup/execute" if setup else "/execute"
        return self._request(
            "POST",
            path,
            json={"command": command, "shell": shell},
            timeout=timeout,
        ).json()

    def execute_with_verification(
        self,
        command: Command,
        *,
        shell: bool = False,
        verification: Optional[JsonDict] = None,
        max_wait_time: Optional[int] = None,
        check_interval: Optional[int] = None,
        setup: bool = False,
        timeout: Optional[float] = None,
    ) -> JsonDict:
        """
        Execute a command and wait for verificaton criteria (`/execute_with_verification`).
        """
        payload: JsonDict = {"command": command, "shell": shell}
        if verification is not None:
            payload["verification"] = verification
        if max_wait_time is not None:
            payload["max_wait_time"] = max_wait_time
        if check_interval is not None:
            payload["check_interval"] = check_interval

        path = "/setup/execute_with_verification" if setup else "/execute_with_verification"
        return self._request("POST", path, json=payload, timeout=timeout).json()

    def launch(self, command: Command, *, shell: bool = False, setup: bool = False, timeout: Optional[float] = None) -> str:
        """
        Launch an application/process (`/launch`).
        """
        path = "/setup/launch" if setup else "/setup/launch"  # Server only exposes setup route.
        response = self._request("POST", path, json={"command": command, "shell": shell}, timeout=timeout)
        return response.text

    def capture_screenshot(self, *, save_to: Optional[Union[str, Path]] = None, timeout: Optional[float] = None) -> bytes:
        """
        Retrieve a screenshot with cursor overlay (`/screenshot`).
        Optionally saves the bytes to `save_to` path.
        """
        response = self._request("GET", "/screenshot", stream=True, timeout=timeout)
        data = response.content
        if save_to:
            Path(save_to).expanduser().resolve().write_bytes(data)
        return data

    def terminal_output(self, timeout: Optional[float] = None) -> JsonDict:
        """
        Fetch terminal output (`/terminal`).
        """
        return self._request("GET", "/terminal", timeout=timeout).json()

    def start_recording(self, timeout: Optional[float] = None) -> JsonDict:
        """
        Start screen recording (`/start_recording`).
        """
        return self._request("POST", "/start_recording", timeout=timeout).json()

    def end_recording(self, *, save_to: Optional[Union[str, Path]] = None, timeout: Optional[float] = None) -> bytes:
        """
        Stop recording and download resulting mp4 (`/end_recording`).
        """
        response = self._request("POST", "/end_recording", stream=True, timeout=timeout)
        content = response.content
        if save_to:
            Path(save_to).expanduser().resolve().write_bytes(content)
        return content

    def get_platform(self, timeout: Optional[float] = None) -> str:
        """
        Retrieve the VM platform string (`/platform`).
        """
        return self._request("GET", "/platform", timeout=timeout).text

    def cursor_position(self, timeout: Optional[float] = None) -> Any:
        """
        Retrieve cursor position tuple (`/cursor_position`).
        """
        return self._request("GET", "/cursor_position", timeout=timeout).json()

    def clipboard(self, timeout: Optional[float] = None) -> JsonDict:
        """
        Retrieve clipboard text (`/clipboard`).
        """
        return self._request("GET", "/clipboard", timeout=timeout).json()
    
    def screen_size(self, timeout: Optional[float] = None) -> JsonDict:
        """
        Retrieve the screen dimensions in pixels (`/screen_size`).
        """
        return self._request("POST", "/screen_size", json={}, timeout=timeout).json()

    def desktop_path(self, timeout: Optional[float] = None) -> JsonDict:
        """
        Retrieve the desktop path on the VM (`/desktop_path`).
        """
        return self._request("POST", "/desktop_path", json={}, timeout=timeout).json()

    def accessibility_tree(self, timeout: Optional[float] = None) -> JsonDict:
        """
        Retrieve the platform accessibility tree (`/accessibility`).
        """
        return self._request("GET", "/accessibility", timeout=timeout).json()

    def window_size(self, app_class_name: str, *, timeout: Optional[float] = None) -> Optional[JsonDict]:
        """
        Retrieve the window size for the specified application class (`/window_size`).
        Returns None when the window is absent.
        """
        response = self._request(
            "POST",
            "/window_size",
            data={"app_class_name": app_class_name},
            expected_status=(200, 404),
            timeout=timeout,
        )
        if response.status_code == 404:
            return None
        return response.json()

    def change_wallpaper(self, path: Union[str, Path], *, timeout: Optional[float] = None) -> str:
        """
        Change the VM wallpaper to the provided path (`/setup/change_wallpaper`).
        """
        response = self._request(
            "POST",
            "/setup/change_wallpaper",
            json={"path": str(path)},
            timeout=timeout,
        )
        return response.text

    def download_file(self, url: str, dest_path: Union[str, Path], *, timeout: Optional[float] = None) -> str:
        """
        Download a remote file on the VM (`/setup/download_file`).
        """
        response = self._request(
            "POST",
            "/setup/download_file",
            json={"url": url, "path": str(dest_path)},
            timeout=timeout,
        )
        return response.text

    def open_file(self, path: Union[str, Path], *, timeout: Optional[float] = None) -> str:
        """
        Open a file or application (`/setup/open_file`).
        """
        response = self._request(
            "POST",
            "/setup/open_file",
            json={"path": str(path)},
            timeout=timeout,
        )
        return response.text

    def activate_window(
        self,
        window_name: str,
        *,
        strict: bool = False,
        by_class: bool = False,
        timeout: Optional[float] = None,
    ) -> str:
        """
        Activate a window by title (`/setup/activate_window`).
        """
        response = self._request(
            "POST",
            "/setup/activate_window",
            json={"window_name": window_name, "strict": strict, "by_class": by_class},
            timeout=timeout,
        )
        return response.text

    def close_window(
        self,
        window_name: str,
        *,
        strict: bool = False,
        by_class: bool = False,
        timeout: Optional[float] = None,
    ) -> str:
        """
        Close a window by title (`/setup/close_window`).
        """
        response = self._request(
            "POST",
            "/setup/close_window",
            json={"window_name": window_name, "strict": strict, "by_class": by_class},
            timeout=timeout,
        )
        return response.text

    def list_directory(self, path: Union[str, Path], *, timeout: Optional[float] = None) -> JsonDict:
        """
        Recursively list a directory (`/list_directory`).
        """
        return self._request(
            "POST",
            "/list_directory",
            json={"path": str(path)},
            timeout=timeout,
        ).json()

    def fetch_file(self, path: Union[str, Path], *, timeout: Optional[float] = None) -> bytes:
        """
        Download a file from the VM (`/file`).
        """
        response = self._request(
            "POST",
            "/file",
            data={"file_path": str(path)},
            timeout=timeout,
        )
        return response.content

    def upload_file(self, path: Union[str, Path], data: bytes, *, timeout: Optional[float] = None) -> str:
        """
        Upload a file to the VM (`/setup/upload`).
        """
        response = self._request(
            "POST",
            "/setup/upload",
            data={"file_path": str(path)},
            files={"file_data": ("payload", data)},
            timeout=timeout,
        )
        return response.text

    def run_python(self, code: str, *, timeout: Optional[float] = None) -> JsonDict:
        """
        Execute arbitrary Python code (`/run_python`).
        """
        return self._request(
            "POST",
            "/run_python",
            json={"code": code},
            timeout=timeout,
        ).json()

    def run_bash_script(
        self,
        script: str,
        *,
        timeout_seconds: Optional[int] = None,
        working_dir: Optional[Union[str, Path]] = None,
        timeout: Optional[float] = None,
    ) -> JsonDict:
        """
        Execute a bash script (`/run_bash_script`).
        """
        payload: JsonDict = {"script": script}
        if timeout_seconds is not None:
            payload["timeout"] = timeout_seconds
        if working_dir is not None:
            payload["working_dir"] = str(working_dir)
        return self._request("POST", "/run_bash_script", json=payload, timeout=timeout).json()

    # ------------------------------------------------------------------ #
    # Context management / utility
    # ------------------------------------------------------------------ #

    def close(self) -> None:
        """Close the underlying session."""
        self._session.close()

    def __enter__(self) -> "VMControllerClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def _safe_json(response: requests.Response) -> Optional[Any]:
    try:
        return response.json()
    except ValueError:
        return response.text
