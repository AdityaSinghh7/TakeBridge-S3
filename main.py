import ctypes
import sys
import base64
import json
import os
import platform
import shlex
import socket
import subprocess
import threading
import time
import traceback
import uuid
import urllib.request
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import queue
import tempfile
from urllib.parse import urlparse

import pyautogui
from PIL import Image, ImageGrab

from flask import Flask, Response, jsonify, request, send_file
from flask_cors import CORS

import logging
import re
import shutil

log_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.log")

# Setup standard logging to write to file
logging.basicConfig(
    filename=log_file_path,
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    force=True,
    encoding='utf-8'
)

# Redirect stdout and stderr to the file
# This captures print() statements and unhandled crashes (tracebacks)
if sys.stdout is None or sys.stderr is None or not sys.stdout.isatty():
    sys.stdout = open(log_file_path, 'a', buffering=1)
    sys.stderr = sys.stdout

platform_name: str = platform.system()

if platform_name == "Windows":
    import win32gui  # type: ignore
    import win32ui  # type: ignore
elif platform_name == "Linux":
    from Xlib import display
    from pyxcursor import Xcursor

app = Flask(__name__)
CORS(app)

try:
    app.logger.setLevel(logging.INFO)
    # Use FileHandler instead of StreamHandler to ensure logs go to disk
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))

    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)

    # Also capture Werkzeug (Flask server) logs
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.addHandler(file_handler)
    werkzeug_logger.setLevel(logging.INFO)
except Exception:
    pass

pyautogui.PAUSE = 0
pyautogui.DARWIN_CATCH_UP_TIME = 0
pyautogui.FAILSAFE = False

USE_GLOBAL_DESKTOP_VNC = True

logger = app.logger

_SERVER_START_TIME = time.time()
_health_cache_lock = threading.Lock()
_health_cache: Dict[str, Any] = {"ts": 0.0, "payload": None, "status_code": None}

_sse_subscribers_lock = threading.Lock()
_sse_subscribers: List["queue.Queue[str]"] = []
_open_windows_lock = threading.Lock()
_open_windows: Dict[str, Dict[str, Any]] = {}
_window_watcher_started = False
_recent_launches: Dict[str, float] = {}
_last_focused_app_id: Optional[str] = None
_exec_lock = threading.Lock()

# Legacy APPS dict is kept for compatibility with some Linux watcher code,
# but /apps and /apps/open no longer depend on it.
APPS: Dict[str, Dict[str, Any]] = {}

def _default_lock_dir() -> Path:
    explicit = (os.environ.get("TAKEBRIDGE_LOCK_DIR") or "").strip()
    if explicit:
        return Path(explicit).expanduser()

    if platform_name == "Windows":
        base = os.environ.get("ProgramData") or tempfile.gettempdir()
        return Path(base) / "TakeBridge" / "server"

    if platform_name == "Darwin":
        return Path(tempfile.gettempdir()) / "takebridge-server"

    # Linux default (matches existing VM images).
    return Path("/home/user/server")


LOCK_DIR = _default_lock_dir()
try:
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

STREAM_SH = os.environ.get("TAKEBRIDGE_STREAM_SH") or str(LOCK_DIR / "stream_window.sh")
CLOSE_SH = os.environ.get("TAKEBRIDGE_CLOSE_SH") or str(LOCK_DIR / "close_app.sh")


def _stream_lock_path(app_id: str) -> Path:
    return LOCK_DIR / f"stream_window_{app_id}.lock"


def _public_host_port() -> Tuple[str, int]:
    host = os.environ.get("VM_PUBLIC_HOST")
    port_env = os.environ.get("VM_PUBLIC_WS_PORT")
    try:
        port = int(port_env) if port_env else 6080
    except Exception:
        port = 6080
    if not host:
        try:
            host_part = request.host.split(":")[0]
            host = host_part or "localhost"
        except Exception:
            host = "localhost"
    return host, port


def _sse_format(data: Dict[str, Any]) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _broadcast(event: Dict[str, Any]) -> None:
    payload = _sse_format(event)
    with _sse_subscribers_lock:
        dead: List[queue.Queue[str]] = []
        for q in _sse_subscribers:
            try:
                q.put_nowait(payload)
            except Exception:
                dead.append(q)
        for q in dead:
            try:
                _sse_subscribers.remove(q)
            except ValueError:
                pass


def _hydrate_event() -> Dict[str, Any]:
    with _open_windows_lock:
        snapshot = list(_open_windows.values())
    try:
        client_host, _ = _public_host_port()
    except Exception:
        client_host = None
    if not client_host:
        return {"event": "hydrate", "windows": snapshot}
    adj: List[Dict[str, Any]] = []
    for window in snapshot:
        vnc = dict(window.get("vnc", {}))
        if vnc:
            vnc["host"] = os.environ.get("VM_PUBLIC_HOST") or client_host
        new_window = dict(window)
        new_window["vnc"] = vnc
        adj.append(new_window)
    return {"event": "hydrate", "windows": adj}


def _window_open_event(window: Dict[str, Any]) -> Dict[str, Any]:
    return {"event": "window_open", "window": window, "timestamp": int(time.time() * 1000)}


def _window_close_event(app_id: str) -> Dict[str, Any]:
    window = {"id": app_id, "appId": app_id}
    return {"event": "window_close", "window": window, "timestamp": int(time.time() * 1000)}


def _window_focus_event(app_id: str) -> Dict[str, Any]:
    window = {"id": app_id, "appId": app_id}
    return {"event": "window_focus", "window": window, "timestamp": int(time.time() * 1000)}


def _ensure_window(app_id: str) -> Tuple[Dict[str, Any], bool]:
    host, ws_port = _public_host_port()
    with _open_windows_lock:
        if app_id in _open_windows:
            return _open_windows[app_id], False
        window = {
            "id": app_id,
            "appId": app_id,
            "title": app_id,
            "vnc": {
                "host": host,
                "rfbPort": 5900,
                "wsPort": ws_port,
                "geometry": {"x": 0, "y": 0, "width": 0, "height": 0},
            },
        }
        _open_windows[app_id] = window
        return window, True


def _remove_window(app_id: str) -> bool:
    with _open_windows_lock:
        return _open_windows.pop(app_id, None) is not None


def _prune_stale_windows() -> None:
    # Legacy Linux behaviour that depended on APPS; with APPS empty this does nothing.
    if platform_name != "Linux":
        return
    to_remove: List[str] = []
    with _open_windows_lock:
        keys = list(_open_windows.keys())
    for app_id in keys:
        try:
            cls = APPS.get(app_id, {}).get("class")
            if not cls:
                continue
            res = subprocess.run(
                [
                    "xdotool",
                    "search",
                    "--onlyvisible",
                    "--class",
                    str(cls),
                ],
                capture_output=True,
                text=True,
                timeout=1,
            )
            if res.returncode != 0 or not res.stdout.strip():
                to_remove.append(app_id)
        except Exception:
            continue
    for app_id in to_remove:
        if _remove_window(app_id):
            try:
                _broadcast(_window_close_event(app_id))
            except Exception:
                pass


def _detect_new_user_opened_windows() -> None:
    # Legacy Linux watcher using APPS. With APPS empty, this is effectively a no-op.
    if platform_name != "Linux":
        return
    cooldown = float(os.environ.get("STREAM_WATCHER_COOLDOWN", "30"))
    for app_id, meta in APPS.items():
        try:
            now = time.time()
            with _open_windows_lock:
                if app_id in _open_windows:
                    continue
            if now - _recent_launches.get(app_id, 0) < cooldown:
                continue
            cls = meta.get("class")
            if not cls:
                continue
            lock_path = _stream_lock_path(app_id)
            if lock_path.exists():
                logger.debug("Skipping %s launch due to active lock %s", app_id, lock_path)
                continue
            res = subprocess.run(
                [
                    "xdotool",
                    "search",
                    "--onlyvisible",
                    "--class",
                    str(cls),
                ],
                capture_output=True,
                text=True,
                timeout=1,
            )
            if res.returncode != 0 or not res.stdout.strip():
                continue
            if USE_GLOBAL_DESKTOP_VNC:
                host, ws_port = _public_host_port()
                _recent_launches[app_id] = now
                window = {
                    "id": app_id,
                    "appId": app_id,
                    "title": app_id,
                    "vnc": {
                        "host": host,
                        "rfbPort": 0,
                        "wsPort": ws_port,
                        "geometry": {"x": 0, "y": 0, "width": 0, "height": 0},
                    },
                }
            else:
                try:
                    host, ws_port, _ = _launch_app_stream(app_id, meta)
                    _recent_launches[app_id] = now
                except RuntimeError as exc:
                    if "Another stream launch already in progress" in str(exc):
                        continue
                    logger.warning("watcher failed to launch stream for %s: %s", app_id, exc)
                    continue
                window = {
                    "id": app_id,
                    "appId": app_id,
                    "title": app_id,
                    "vnc": {
                        "host": host,
                        "rfbPort": 0,
                        "wsPort": ws_port,
                        "geometry": {"x": 0, "y": 0, "width": 0, "height": 0},
                    },
                }
            with _open_windows_lock:
                _open_windows[app_id] = window
            try:
                _broadcast(_window_open_event(window))
            except Exception:
                pass
        except Exception:
            continue


def _log_request_details(endpoint_name: str) -> None:
    try:
        method = request.method
        url = request.url
        remote_addr = getattr(request, "remote_addr", "unknown")
        headers = dict(request.headers)
        try:
            body = request.get_json(silent=True, force=True)
            if body is None:
                body = request.data.decode("utf-8") if request.data else None
        except Exception:
            body = request.data.decode("utf-8", errors="replace") if request.data else None
        logger.info("[API_REQUEST] %s | Method: %s | URL: %s | Remote: %s", endpoint_name, method, url, remote_addr)
        logger.info("[API_REQUEST] %s | Headers: %s", endpoint_name, json.dumps(headers, indent=2))
        if body:
            if isinstance(body, dict):
                logger.info("[API_REQUEST] %s | Body: %s", endpoint_name, json.dumps(body, indent=2))
            else:
                logger.info("[API_REQUEST] %s | Body: %s", endpoint_name, str(body)[:1000])
    except Exception as exc:
        logger.warning("[API_REQUEST] %s | Failed to log request details: %s", endpoint_name, exc)


def _active_window_tokens() -> Tuple[Optional[str], List[str]]:
    # Legacy Linux helper; no longer used for mapping, but kept for focus watcher.
    if platform_name != "Linux":
        return None, []
    wid = None
    tokens: List[str] = []
    try:
        rid = subprocess.run(["xdotool", "getactivewindow"], capture_output=True, text=True, timeout=1)
        if rid.returncode != 0:
            return None, []
        wid = rid.stdout.strip()
        if not wid:
            return None, []
        try:
            rc = subprocess.run(["xdotool", "getwindowclassname", wid], capture_output=True, text=True, timeout=1)
            if rc.returncode == 0 and rc.stdout:
                tokens.append(rc.stdout.strip())
        except Exception:
            pass
        try:
            rp = subprocess.run(["xprop", "-id", wid, "WM_CLASS"], capture_output=True, text=True, timeout=1)
            if rp.returncode == 0 and rp.stdout:
                raw = rp.stdout.split("=", 1)[-1]
                for part in raw.split(","):
                    t = part.strip().strip('"').strip()
                    if t:
                        tokens.append(t)
        except Exception:
            pass
        norm = []
        for t in tokens:
            try:
                norm.append(t.strip().lower())
            except Exception:
                continue
        logger.debug("focus_watcher: active window tokens=%s (wid=%s)", norm or tokens, wid)
        return wid, norm or tokens
    except Exception:
        return wid, [t.strip().lower() for t in tokens if t]


def _map_class_to_app_id_from_tokens(tokens: List[str]) -> Optional[str]:
    # Legacy APPS-based mapping; with APPS empty this returns None.
    if not tokens:
        return None
    toks = [t.strip().lower() for t in tokens if t]
    for app_id, meta in APPS.items():
        try:
            mc = str(meta.get("class", "")).strip().lower()
            if not mc:
                continue
            if mc in toks or any((mc in t or t in mc) for t in toks):
                return app_id
        except Exception:
            continue
    return None


def _detect_focus_change() -> None:
    global _last_focused_app_id
    if platform_name != "Linux":
        return
    _, tokens = _active_window_tokens()
    app_id = _map_class_to_app_id_from_tokens(tokens)
    if not app_id:
        if tokens:
            logger.debug("focus_watcher: unmapped tokens %s", tokens)
        return
    with _open_windows_lock:
        is_known = app_id in _open_windows
    if not is_known:
        logger.debug("focus_watcher: focus on %s but not in tracked _open_windows; broadcasting anyway", app_id)
    prev = _last_focused_app_id
    if prev == app_id:
        return
    _last_focused_app_id = app_id
    logger.debug("focus_watcher: focus changed -> %s (from %s)", app_id, prev)
    try:
        _broadcast(_window_focus_event(app_id))
    except Exception:
        pass


def _window_watcher_loop(interval_s: float = 1.0) -> None:
    if platform_name != "Linux":
        return
    while True:
        try:
            _detect_new_user_opened_windows()
            _prune_stale_windows()
            _detect_focus_change()
        except Exception:
            pass
        time.sleep(interval_s)


def _start_window_watcher_once() -> None:
    global _window_watcher_started
    if _window_watcher_started:
        return
    try:
        t = threading.Thread(
            target=_window_watcher_loop,
            kwargs={"interval_s": float(os.environ.get("WINDOW_WATCH_INTERVAL_S", "1.0"))},
            daemon=True,
        )
        t.start()
        _window_watcher_started = True
    except Exception:
        pass


def _wait_tcp_ready(host: str, port: int, timeout_s: int = 20, interval_s: float = 0.25) -> bool:
    deadline = time.time() + timeout_s
    last_err: Optional[Exception] = None
    while time.time() < deadline:
        try:
            with socket.create_connection((host, int(port)), timeout=1):
                return True
        except Exception as exc:
            last_err = exc
            time.sleep(interval_s)
    logger.warning("wait_tcp_ready: timed out waiting for %s:%s (last_err=%s)", host, port, last_err)
    return False


def _vnc_backend_host_port() -> Tuple[str, int]:
    host = os.environ.get("VNC_BACKEND_HOST") or "127.0.0.1"
    try:
        port = int(os.environ.get("VNC_BACKEND_PORT") or 5900)
    except Exception:
        port = 5900
    return host, port


def vm_ip() -> str:
    # Best-effort local IP discovery across platforms without relying on platform-specific commands.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            # Doesn't send packets; used to select an outbound interface.
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip:
                return ip
    except Exception:
        pass

    try:
        _, _, addrs = socket.gethostbyname_ex(socket.gethostname())
        for addr in addrs:
            if addr and not addr.startswith("127."):
                return addr
    except Exception:
        pass

    return "127.0.0.1"


def _launch_app_stream(app_id: str, meta: Dict[str, Any], timeout_s: Optional[int] = None):
    timeout_s = timeout_s or int(os.environ.get("STREAM_READY_TIMEOUT", "45"))
    launch_cmd = meta.get("launch", "")
    ws_value = meta.get("ws", 6080)
    cls_value = meta.get("class")
    cmd = [STREAM_SH, app_id, launch_cmd, str(ws_value), cls_value or ""]
    logger.info("launch_app_stream cmd=%s", " ".join(cmd))
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    ready_url = None
    lines: List[str] = []
    deadline = time.time() + timeout_s
    skip_message = "Another stream launch already in progress"
    while True:
        if time.time() > deadline:
            logger.error("launch_app_stream timeout waiting for READY for %s", app_id)
            break
        line = proc.stdout.readline()
        if line == "" and proc.poll() is not None:
            break
        if not line:
            time.sleep(0.1)
            continue
        stripped = line.strip()
        lines.append(stripped)
        logger.info("stream[%s]: %s", app_id, stripped)
        if stripped.startswith("READY "):
            ready_url = stripped.split(" ", 1)[1].strip()
            break
        if skip_message in stripped:
            ready_url = None
            logger.info("stream[%s] reported skip due to active lock", app_id)
            break
    if ready_url is None:
        try:
            remaining, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            remaining, _ = proc.communicate()
        if remaining:
            for line in remaining.splitlines():
                line = line.strip()
                if line:
                    lines.append(line)
                    logger.info("stream[%s]: %s", app_id, line)
        if lines and skip_message in lines[-1]:
            raise RuntimeError(skip_message)
        raise RuntimeError(lines[-1] if lines else "stream launch failed")
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    parsed = urlparse(ready_url)
    host = parsed.hostname or os.environ.get("VM_PUBLIC_HOST") or vm_ip()
    try:
        ws_port = parsed.port or int(meta.get("ws") or os.environ.get("VM_PUBLIC_WS_PORT") or 6080)
    except Exception:
        ws_port = int(meta.get("ws") or 6080)
    return host, ws_port, lines


def _get_machine_architecture() -> str:
    architecture = platform.machine().lower()
    if architecture in {'amd32', 'amd64', 'x86', 'x86_64', 'x86-64', 'x64', 'i386', 'i686'}:
        return 'amd'
    if architecture in {'arm64', 'aarch64', 'aarch32'}:
        return 'arm'
    return 'unknown'


def _default_outlook_launch() -> str:
    # Kept for compatibility; currently not used by default app mapping.
    try:
        for bin_name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
            if shutil.which(bin_name):
                return f"{bin_name} --profile-directory=Default --app-id=faolnafnngnfdaknnbpnkhgohbobgegn"
    except Exception:
        pass
    return "google-chrome --profile-directory=Default --app-id=faolnafnngnfdaknnbpnkhgohbobgegn"


# ---------- App discovery + default app mapping ----------

def _normalize_app_id(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    return name.strip("-") or "unknown"


def _lc(s: str) -> str:
    return s.lower()


DEFAULT_APPS_BY_PLATFORM: Dict[str, List[Dict[str, Any]]] = {
    # ---- Windows defaults ----
    "Windows": [
        {
            "id": "chrome",
            "label": "Google Chrome",
            "match": ["google chrome", "chrome"],
        },
        {
            "id": "edge",
            "label": "Microsoft Edge",
            "match": ["microsoft edge", "msedge"],
        },
        {
            "id": "libreoffice",
            "label": "LibreOffice",
            "match": ["libreoffice "],
        },
        {
            "id": "libreoffice-writer",
            "label": "LibreOffice Writer",
            "match": ["libreoffice writer"],
        },
        {
            "id": "libreoffice-calc",
            "label": "LibreOffice Calc",
            "match": ["libreoffice calc"],
        },
        {
            "id": "notepad",
            "label": "Notepad",
            "match": ["notepad"],
        },
        {
            "id": "powershell",
            "label": "Windows PowerShell",
            "match": ["windows powershell"],
        },
        {
            "id": "cmd",
            "label": "Command Prompt",
            "match": ["command prompt", "cmd.exe"],
        },
        {
            "id": "tightvnc-viewer",
            "label": "TightVNC Viewer",
            "match": ["tightvnc viewer"],
        },
    ],
    # ---- Linux defaults ----
    "Linux": [
        {
            "id": "chrome",
            "label": "Google Chrome",
            "match": ["google chrome", "chromium", "chrome"],
        },
        {
            "id": "firefox",
            "label": "Firefox",
            "match": ["firefox"],
        },
        {
            "id": "libreoffice-writer",
            "label": "LibreOffice Writer",
            "match": ["libreoffice writer"],
        },
        {
            "id": "libreoffice-calc",
            "label": "LibreOffice Calc",
            "match": ["libreoffice calc"],
        },
        {
            "id": "terminal",
            "label": "Terminal",
            "match": ["terminal", "gnome-terminal", "konsole", "xterm"],
        },
        {
            "id": "files",
            "label": "Files",
            "match": ["files", "nautilus", "dolphin", "thunar"],
        },
        {
            "id": "code",
            "label": "VS Code",
            "match": ["visual studio code", "code"],
        },
    ],
    # ---- macOS defaults ----
    "Darwin": [
        {
            "id": "chrome",
            "label": "Google Chrome",
            "match": ["google chrome"],
        },
        {
            "id": "safari",
            "label": "Safari",
            "match": ["safari"],
        },
        {
            "id": "terminal",
            "label": "Terminal",
            "match": ["terminal"],
        },
        {
            "id": "finder",
            "label": "Finder",
            "match": ["finder"],
        },
        {
            "id": "textedit",
            "label": "TextEdit",
            "match": ["textedit"],
        },
    ],
}


def _get_default_app_specs_for_platform() -> List[Dict[str, Any]]:
    return DEFAULT_APPS_BY_PLATFORM.get(platform_name, [])


def _scan_linux_apps() -> List[Dict[str, Any]]:
    desktop_dirs = [
        "/usr/share/applications",
        "/usr/local/share/applications",
        os.path.expanduser("~/.local/share/applications"),
    ]
    apps: List[Dict[str, Any]] = []

    for d in desktop_dirs:
        if not os.path.isdir(d):
            continue
        for entry in os.listdir(d):
            if not entry.endswith(".desktop"):
                continue
            path = os.path.join(d, entry)
            name = None
            exec_cmd = None
            hidden = False
            nodisplay = False

            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                    for line in fh:
                        line = line.strip()
                        if line.startswith("Name=") and name is None:
                            name = line.split("=", 1)[1].strip()
                        elif line.startswith("Exec=") and exec_cmd is None:
                            raw = line.split("=", 1)[1].strip()
                            exec_cmd = " ".join(
                                t for t in shlex.split(raw) if not t.startswith("%")
                            )
                        elif line.startswith("NoDisplay="):
                            nodisplay = line.split("=", 1)[1].strip().lower() == "true"
                        elif line.startswith("Hidden="):
                            hidden = line.split("=", 1)[1].strip().lower() == "true"
            except Exception:
                continue

            if not name or not exec_cmd:
                continue
            if hidden or nodisplay:
                continue

            app_id = _normalize_app_id(name)
            is_system = d.startswith("/usr/share")

            apps.append({
                "id": app_id,
                "name": name,
                "exec": exec_cmd,
                "path": path,
                "kind": "desktop",
                "is_system": is_system,
                "platform": "Linux",
            })

    return apps


def _scan_windows_apps() -> List[Dict[str, Any]]:
    """
    Discover installed apps on Windows using PowerShell Get-StartApps.

    We aggressively classify most entries as system utilities and only keep
    a small set of obviously user-facing apps as non-system.
    """
    apps: List[Dict[str, Any]] = []

    USER_APP_KEYWORDS = [
        "chrome",
        "edge",
        "firefox",
        "libreoffice",
        "word",
        "excel",
        "powerpoint",
        "notepad",
        "vim",
        "gvim",
        "tightvnc viewer",
        "viewer",
        "python",
    ]

    SYSTEM_NAME_KEYWORDS = [
        "administrative tools",
        "component services",
        "computer management",
        "control panel",
        "defragment",
        "disk cleanup",
        "event viewer",
        "local security policy",
        "magnifier",
        "math input panel",
        "narrator",
        "odbc data sources",
        "on-screen keyboard",
        "performance monitor",
        "recovery drive",
        "register tightvnc service",
        "unregister tightvnc service",
        "run tightvnc service",
        "start tightvnc service",
        "stop tightvnc service",
        "services",
        "settings",
        "snipping tool",
        "steps recorder",
        "system configuration",
        "system information",
        "task manager",
        "task scheduler",
        "this pc",
        "windows defender firewall",
        "windows memory diagnostic",
        "windows security",
        "windows server backup",
        "speech recognition",
        "xps viewer",
    ]

    SYSTEM_APPID_KEYWORDS = [
        "\\system32\\",
        ".msc",
        "controlpanel",
        "windows.explorer",
        "windows.shell.rundialog",
        "sechealthui",
    ]

    try:
        ps_cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Depth 2"
        ]
        res = subprocess.run(
            ps_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
        if res.returncode == 0 and res.stdout.strip():
            raw = res.stdout.strip()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = []

            items = data if isinstance(data, list) else [data]

            for item in items:
                name = (item.get("Name") or "").strip()
                appid = (item.get("AppID") or "").strip()
                if not name:
                    continue

                lower_name = name.lower()
                lower_appid = appid.lower()
                norm_id = _normalize_app_id(name)

                is_user_app = any(k in lower_name for k in USER_APP_KEYWORDS)

                if is_user_app:
                    is_system = False
                else:
                    looks_guid = appid.startswith("{") and "}" in appid
                    has_system_keyword = (
                        lower_name.startswith("windows ") or
                        any(k in lower_name for k in SYSTEM_NAME_KEYWORDS) or
                        any(k in lower_appid for k in SYSTEM_APPID_KEYWORDS)
                    )
                    is_system = looks_guid or has_system_keyword or True

                apps.append({
                    "id": norm_id,
                    "name": name,
                    "app_id": appid,
                    "kind": "startapps",
                    "is_system": is_system,
                    "platform": "Windows",
                })

            return apps

    except Exception as exc:
        logger.warning("Get-StartApps scan failed: %s", exc)

    # Fallback to .lnk scan if Get-StartApps fails
    try:
        start_menu_dirs: List[str] = []
        programdata = os.environ.get("ProgramData")
        appdata = os.environ.get("APPDATA")

        if programdata:
            start_menu_dirs.append(
                os.path.join(programdata, r"Microsoft\Windows\Start Menu\Programs")
            )
        if appdata:
            start_menu_dirs.append(
                os.path.join(appdata, r"Microsoft\Windows\Start Menu\Programs")
            )

        seen_ids = set()

        for base in start_menu_dirs:
            if not base or not os.path.isdir(base):
                continue
            for root, _, files in os.walk(base):
                for fname in files:
                    if not fname.lower().endswith(".lnk"):
                        continue
                    full = os.path.join(root, fname)
                    name = os.path.splitext(fname)[0].strip()
                    if not name:
                        continue

                    lower_name = name.lower()
                    norm_id = _normalize_app_id(name)
                    if norm_id in seen_ids:
                        continue
                    seen_ids.add(norm_id)

                    is_user_app = any(k in lower_name for k in USER_APP_KEYWORDS)
                    is_system = not is_user_app

                    apps.append({
                        "id": norm_id,
                        "name": name,
                        "path": full,
                        "kind": "shortcut",
                        "is_system": is_system,
                        "platform": "Windows",
                    })
    except Exception as exc:
        logger.warning("Fallback .lnk scan failed: %s", exc)

    return apps


def _scan_macos_apps() -> List[Dict[str, Any]]:
    apps: List[Dict[str, Any]] = []
    app_dirs = [
        "/Applications",
        "/System/Applications",
        os.path.expanduser("~/Applications"),
    ]

    seen_ids = set()

    for base in app_dirs:
        if not os.path.isdir(base):
            continue
        for entry in os.listdir(base):
            if not entry.endswith(".app"):
                continue
            full = os.path.join(base, entry)
            name = entry[:-4]
            app_id = _normalize_app_id(name)
            if app_id in seen_ids:
                continue
            seen_ids.add(app_id)

            is_system = full.startswith("/System/Applications")

            apps.append({
                "id": app_id,
                "name": name,
                "path": full,
                "kind": "bundle",
                "is_system": is_system,
                "platform": "Darwin",
            })

    return apps


_host_apps_cache: Optional[List[Dict[str, Any]]] = None
_host_apps_cache_ts: float = 0.0
_HOST_APPS_TTL = 30.0


def _scan_host_apps(force: bool = False) -> List[Dict[str, Any]]:
    global _host_apps_cache, _host_apps_cache_ts
    now = time.time()
    if not force and _host_apps_cache is not None and (now - _host_apps_cache_ts) < _HOST_APPS_TTL:
        return list(_host_apps_cache)

    if platform_name == "Linux":
        apps = _scan_linux_apps()
    elif platform_name == "Windows":
        apps = _scan_windows_apps()
    elif platform_name == "Darwin":
        apps = _scan_macos_apps()
    else:
        apps = []

    _host_apps_cache = apps
    _host_apps_cache_ts = now
    return list(apps)


def _match_default_apps_to_host() -> List[Dict[str, Any]]:
    """
    Intersect the TakeBridge default app list with the apps actually present
    on this host by matching substrings against discovered app metadata.
    """
    host_apps = _scan_host_apps()
    specs = _get_default_app_specs_for_platform()
    resolved: List[Dict[str, Any]] = []

    def host_text(app: Dict[str, Any]) -> str:
        parts = [
            str(app.get("name", "")),
            str(app.get("id", "")),
            str(app.get("app_id", "")),
            str(app.get("exec", "")),
            str(app.get("path", "")),
        ]
        return " ".join(parts).lower()

    host_with_text = [(app, host_text(app)) for app in host_apps]

    for spec in specs:
        wanted_id = spec["id"]
        label = spec.get("label", wanted_id)
        patterns = [p.lower() for p in spec.get("match", []) if p]

        matched_app: Optional[Dict[str, Any]] = None
        for app, text in host_with_text:
            if any(p in text for p in patterns):
                matched_app = app
                break

        if matched_app:
            resolved.append({
                "id": wanted_id,
                "label": label,
                "host": matched_app,
            })

    return resolved


def _map_window_to_default_app(window: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Given a raw window descriptor, map it to one of the TakeBridge default apps.
    """
    specs = _get_default_app_specs_for_platform()
    if not specs:
        return None

    parts = [
        str(window.get("title", "")),
        str(window.get("wmClass", "")),
        str(window.get("className", "")),
        str(window.get("bundleName", "")),
        str(window.get("id", "")),
        str(window.get("appId", "")),
    ]
    text = " ".join(parts).lower()

    for spec in specs:
        patterns = [p.lower() for p in spec.get("match", []) if p]
        if any(p in text for p in patterns):
            return spec

    return None


def _list_active_windows_from_host() -> List[Dict[str, Any]]:
    """
    Inspect the host desktop to discover visible windows/apps.
    Only windows that map to TakeBridge default apps are returned,
    and their id/appId are normalized to logical IDs.
    """

    # ---------- Linux ----------
    if platform_name == "Linux":
        try:
            res = subprocess.run(
                ["xdotool", "search", "--onlyvisible", "."],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if res.returncode != 0 or not res.stdout.strip():
                with _open_windows_lock:
                    return list(_open_windows.values())

            window_ids = [w.strip() for w in res.stdout.splitlines() if w.strip()]
            host, ws_port = _public_host_port()
            discovered: List[Dict[str, Any]] = []

            for wid in window_ids:
                title = None
                wm_class = None

                try:
                    t_res = subprocess.run(
                        ["xdotool", "getwindowname", wid],
                        capture_output=True,
                        text=True,
                        timeout=1,
                    )
                    if t_res.returncode == 0 and t_res.stdout.strip():
                        title = t_res.stdout.strip()
                except Exception:
                    pass

                try:
                    c_res = subprocess.run(
                        ["xprop", "-id", wid, "WM_CLASS"],
                        capture_output=True,
                        text=True,
                        timeout=1,
                    )
                    if c_res.returncode == 0 and c_res.stdout:
                        raw = c_res.stdout.split("=", 1)[-1]
                        parts = [p.strip().strip('"') for p in raw.split(",") if p.strip()]
                        if parts:
                            wm_class = parts[-1]
                except Exception:
                    pass

                base = title or wm_class or wid

                window: Dict[str, Any] = {
                    "id": base,
                    "appId": base,
                    "title": title or base,
                    "wmClass": wm_class,
                    "wid": wid,
                }

                spec = _map_window_to_default_app(window)
                if not spec:
                    continue

                logical_id = spec["id"]
                label = spec.get("label", logical_id)

                window["id"] = logical_id
                window["appId"] = logical_id
                window["label"] = label

                if USE_GLOBAL_DESKTOP_VNC:
                    window["vnc"] = {
                        "host": host,
                        "rfbPort": 0,
                        "wsPort": ws_port,
                        "geometry": {"x": 0, "y": 0, "width": 0, "height": 0},
                    }

                discovered.append(window)

            with _open_windows_lock:
                _open_windows.clear()
                for w in discovered:
                    _open_windows[w["appId"]] = w

            return discovered

        except Exception:
            with _open_windows_lock:
                return list(_open_windows.values())

    # ---------- Windows ----------
    if platform_name == "Windows":
        try:
            import win32gui  # type: ignore
        except ImportError:
            with _open_windows_lock:
                return list(_open_windows.values())

        host, ws_port = _public_host_port()
        discovered: List[Dict[str, Any]] = []

        def enum_handler(hwnd, _):
            try:
                if not win32gui.IsWindowVisible(hwnd):
                    return
                title = win32gui.GetWindowText(hwnd)
                if not title:
                    return

                cls = win32gui.GetClassName(hwnd)
                base = title or cls or str(hwnd)

                window: Dict[str, Any] = {
                    "id": base,
                    "appId": base,
                    "title": title,
                    "wmClass": cls,
                    "hwnd": int(hwnd),
                }

                spec = _map_window_to_default_app(window)
                if not spec:
                    return

                logical_id = spec["id"]
                label = spec.get("label", logical_id)

                window["id"] = logical_id
                window["appId"] = logical_id
                window["label"] = label

                if USE_GLOBAL_DESKTOP_VNC:
                    window["vnc"] = {
                        "host": host,
                        "rfbPort": 0,
                        "wsPort": ws_port,
                        "geometry": {"x": 0, "y": 0, "width": 0, "height": 0},
                    }

                discovered.append(window)
            except Exception:
                return

        try:
            win32gui.EnumWindows(enum_handler, None)
        except Exception:
            with _open_windows_lock:
                return list(_open_windows.values())

        with _open_windows_lock:
            _open_windows.clear()
            for w in discovered:
                _open_windows[w["appId"]] = w

        return discovered

    # ---------- macOS ----------
    if platform_name == "Darwin":
        try:
            script = (
                'tell application "System Events" to get name of application processes '
                'whose background only is false'
            )
            res = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if res.returncode != 0 or not res.stdout.strip():
                with _open_windows_lock:
                    return list(_open_windows.values())

            names = [n.strip() for n in res.stdout.split(",") if n.strip()]
            host, ws_port = _public_host_port()
            discovered: List[Dict[str, Any]] = []

            for name in names:
                window: Dict[str, Any] = {
                    "id": name,
                    "appId": name,
                    "title": name,
                    "bundleName": name,
                }

                spec = _map_window_to_default_app(window)
                if not spec:
                    continue

                logical_id = spec["id"]
                label = spec.get("label", logical_id)

                window["id"] = logical_id
                window["appId"] = logical_id
                window["label"] = label

                if USE_GLOBAL_DESKTOP_VNC:
                    window["vnc"] = {
                        "host": host,
                        "rfbPort": 0,
                        "wsPort": ws_port,
                        "geometry": {"x": 0, "y": 0, "width": 0, "height": 0},
                    }
                discovered.append(window)

            with _open_windows_lock:
                _open_windows.clear()
                for w in discovered:
                    _open_windows[w["appId"]] = w

            return discovered

        except Exception:
            with _open_windows_lock:
                return list(_open_windows.values())

    with _open_windows_lock:
        return list(_open_windows.values())


try:
    if isinstance(APPS.get("terminal"), dict):
        APPS["terminal"]["launch"] = "gnome-terminal"
except Exception:
    pass


@app.get("/health")
def health():
    # Cache for very short TTL to avoid repeated expensive checks during startup polling.
    try:
        ttl_s = float(os.environ.get("HEALTH_CACHE_TTL_S", "2.0"))
    except Exception:
        ttl_s = 2.0
    now = time.time()

    with _health_cache_lock:
        cached_payload = _health_cache.get("payload")
        cached_code = _health_cache.get("status_code")
        cached_ts = float(_health_cache.get("ts") or 0.0)
        if cached_payload is not None and cached_code is not None and (now - cached_ts) < ttl_s:
            return jsonify(cached_payload), int(cached_code)

    def _record_check(name: str, ok: bool, **extra: Any) -> Dict[str, Any]:
        entry: Dict[str, Any] = {"ok": bool(ok)}
        entry.update(extra)
        checks[name] = entry
        return entry

    checks: Dict[str, Any] = {}
    warnings: List[str] = []
    ready = True

    # Ensure the executor isn't deadlocked/busy and gate deeper checks on it.
    acquired = _exec_lock.acquire(timeout=1)
    if not acquired:
        ready = False
        _record_check("executor_lock", False, error="executor busy")
    else:
        _record_check("executor_lock", True)
        try:
            # Temp dir writeability (used by /run_python and script execution helpers).
            try:
                with tempfile.NamedTemporaryFile(mode="w", delete=True, encoding="utf-8") as fh:
                    fh.write("ok")
                _record_check("tempfile", True, temp_dir=tempfile.gettempdir())
            except Exception as exc:
                ready = False
                _record_check("tempfile", False, error=str(exc), temp_dir=tempfile.gettempdir())

            def _run_py(code: str, *, timeout_s: int = 10) -> Dict[str, Any]:
                try:
                    flags = subprocess.CREATE_NO_WINDOW if platform_name == "Windows" else 0
                    proc = subprocess.run(
                        [sys.executable, "-c", code],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=timeout_s,
                        creationflags=flags,
                    )
                    return {
                        "returncode": proc.returncode,
                        "stdout": (proc.stdout or ""),
                        "stderr": (proc.stderr or ""),
                    }
                except Exception as exc:
                    return {"error": str(exc), "returncode": -1, "stdout": "", "stderr": ""}

            # Basic python execution smoke test (mirrors /execute usage for python -c).
            smoke = _run_py("print('ok')", timeout_s=5)
            smoke_ok = smoke.get("returncode") == 0 and "ok" in (smoke.get("stdout") or "")
            if not smoke_ok:
                ready = False
            _record_check("python_subprocess", smoke_ok, **smoke)

            # Simulate orchestrator's base64 payload execution via /execute.
            pyautogui_script = (
                "import json, time; "
                "import pyautogui; "
                "pyautogui.FAILSAFE = False; pyautogui.PAUSE = 0; "
                "size = pyautogui.size(); pos = pyautogui.position(); "
                "print(json.dumps({'size':[size.width, size.height], 'pos':[pos.x, pos.y]}))"
            )
            payload = base64.b64encode(pyautogui_script.encode("utf-8")).decode("ascii")
            base64_code = f"import base64; exec(base64.b64decode('{payload}').decode('utf-8'))"
            base64_res = _run_py(base64_code, timeout_s=10)
            base64_ok = base64_res.get("returncode") == 0
            if not base64_ok:
                ready = False
            _record_check("execute_pyautogui", base64_ok, **base64_res)

            # Screenshot readiness (runner depends on /screenshot before/after each step).
            if platform_name == "Windows":
                screenshot_code = (
                    "import json; from PIL import ImageGrab; "
                    "img=None\n"
                    "try:\n"
                    "  img = ImageGrab.grab(bbox=None, include_layered_windows=True)\n"
                    "except Exception:\n"
                    "  img = ImageGrab.grab()\n"
                    "print(json.dumps({'size': list(img.size)}))"
                )
            else:
                screenshot_code = (
                    "import json; import pyautogui; "
                    "img = pyautogui.screenshot(); "
                    "print(json.dumps({'size': list(img.size)}))"
                )
            screenshot_res = _run_py(screenshot_code, timeout_s=15)
            screenshot_ok = screenshot_res.get("returncode") == 0
            if not screenshot_ok:
                ready = False
            _record_check("screenshot", screenshot_ok, **screenshot_res)

            # Optional: record bash availability for troubleshooting, but don't gate readiness.
            if platform_name == "Windows":
                bash_exe = _find_windows_bash_executable()
                if not bash_exe:
                    warnings.append("bash not found (Git Bash/WSL); /run_bash_script will fall back to PowerShell")
                _record_check("bash_available", bool(bash_exe), bash=bash_exe)
            else:
                bash_exe = _resolve_bash_executable()
                _record_check("bash_available", bool(bash_exe), bash=bash_exe)
        finally:
            _exec_lock.release()

    payload: Dict[str, Any] = {
        "status": "ok" if ready else "not_ready",
        "ready": bool(ready),
        "platform": platform_name,
        "pid": os.getpid(),
        "uptime_s": round(time.time() - _SERVER_START_TIME, 3),
        "checks": checks,
        "warnings": warnings,
    }
    status_code = 200 if ready else 503

    with _health_cache_lock:
        _health_cache["ts"] = time.time()
        _health_cache["payload"] = payload
        _health_cache["status_code"] = status_code

    return jsonify(payload), status_code


@app.post("/apps/open")
def apps_open():
    _start_window_watcher_once()
    data = request.get_json(force=True, silent=True) or {}
    raw_id = data.get("app")
    if not raw_id:
        return jsonify({"status": "error", "message": "missing 'app'"}), 400

    logical_id = str(raw_id).strip().lower()
    resolved = _match_default_apps_to_host()
    target = next((r for r in resolved if r["id"] == logical_id), None)
    if not target:
        return jsonify({"status": "error", "message": f"app '{logical_id}' not available on this host"}), 404

    host_app = target["host"]
    name = host_app.get("name", logical_id)
    logger.info("apps_open: %s -> host app %s", logical_id, host_app)

    try:
        if platform_name == "Windows":
            app_id = host_app.get("app_id")
            if host_app.get("kind") == "startapps" and app_id:
                ps_cmd = [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"Start-Process 'shell:AppsFolder\\{app_id}'"
                ]
                subprocess.Popen(ps_cmd)
            else:
                return jsonify({"status": "error", "message": "unsupported Windows host app kind"}), 500

        elif platform_name == "Darwin":
            path = host_app.get("path")
            if path and path.endswith(".app"):
                subprocess.Popen(["open", path])
            else:
                cmd = host_app.get("exec") or path
                if not cmd:
                    return jsonify({"status": "error", "message": "no launchable path for app"}), 500
                subprocess.Popen(["open", cmd])

        elif platform_name == "Linux":
            exec_cmd = host_app.get("exec")
            if not exec_cmd:
                return jsonify({"status": "error", "message": "no Exec command for app"}), 500
            subprocess.Popen(exec_cmd, shell=True)

        else:
            return jsonify({"status": "error", "message": f"unsupported platform {platform_name}"}), 500

    except Exception as exc:
        logger.error("apps_open failed to launch %s: %s", logical_id, exc)
        return jsonify({"status": "error", "message": f"failed to launch app: {exc}"}), 500

    host, ws_port = _public_host_port()
    window, created = _ensure_window(logical_id)
    window["title"] = name
    window["vnc"]["host"] = host
    window["vnc"]["wsPort"] = ws_port
    window["vnc"]["rfbPort"] = 0
    if created:
        _broadcast(_window_open_event(window))

    return jsonify({
        "status": "success",
        "mode": "global_vnc" if USE_GLOBAL_DESKTOP_VNC else "unknown",
        "launched": logical_id,
        "ws_url": f"ws://{host}:{ws_port}",
    })


@app.post("/apps/close")
def apps_close():
    _start_window_watcher_once()
    data = request.get_json(force=True, silent=True) or {}
    key = data.get("app")
    if not key:
        return jsonify({"status": "error", "message": "missing 'app'"}), 400

    if platform_name == "Windows":
        app_id = str(key).strip().lower()
        try:
            windows = _list_active_windows_from_host()
            targets = [
                w
                for w in windows
                if str(w.get("appId", "")).strip().lower() == app_id
                or str(w.get("id", "")).strip().lower() == app_id
            ]

            closed = 0
            close_errors: List[str] = []
            if targets:
                try:
                    import win32con  # type: ignore
                    import win32gui  # type: ignore
                except Exception as exc:
                    return jsonify({"status": "error", "message": f"win32 api not available: {exc}"}), 501

                for w in targets:
                    hwnd = w.get("hwnd")
                    if hwnd is None:
                        continue
                    try:
                        win32gui.PostMessage(int(hwnd), win32con.WM_CLOSE, 0, 0)
                        closed += 1
                    except Exception as exc:
                        close_errors.append(str(exc))

            if close_errors:
                logger.error("apps_close failed for %s: %s", app_id, close_errors[0])
                return jsonify({"status": "error", "message": close_errors[0], "errors": close_errors}), 500

            status = "ok"
            message = f"close requested for {app_id}" if closed else f"{app_id} already closed"
            try:
                removed = _remove_window(app_id)
                if removed:
                    _broadcast(_window_close_event(app_id))
            except Exception as exc:
                logger.warning("Failed to broadcast window_close for %s: %s", app_id, exc)

            return jsonify({"status": status, "message": message, "closed_windows": closed})

        except Exception as exc:
            logger.error("apps_close failed on Windows for %s: %s", app_id, exc)
            return jsonify({"status": "error", "message": f"failed to close app: {exc}"}), 500

    # For close, we don't need default mapping; we just try CLOSE_SH if present.
    if not os.path.isfile(CLOSE_SH):
        return jsonify({"status": "error", "message": f"{CLOSE_SH} not found"}), 500
    # This script may be legacy and expect certain args; we pass placeholders.
    cmd = [CLOSE_SH, key, "", "0", ""]
    logger.info("close_app invoking %s", " ".join(cmd))
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    output = (proc.stdout or "").strip()
    logger.info("close_app result (rc=%s) output=%s", proc.returncode, output)
    status = "ok"
    message = output or f"closed {key}"
    if proc.returncode != 0:
        if proc.returncode >= 128:
            sig = proc.returncode - 128
            message = f"{message} (terminated by signal {sig})"
            logger.warning("close_app script terminated by signal %s for %s", sig, key)
        else:
            lowered = message.lower()
            already_closed = any(token in lowered for token in [
                "no matching processes",
                "not found",
                "no process found",
                "already closed",
            ])
            if not already_closed:
                logger.error("close_app failed for %s (rc=%s): %s", key, proc.returncode, message)
                return jsonify({"status": "error", "message": message, "returncode": proc.returncode}), 500
            message = message or f"{key} already closed"
    try:
        removed = _remove_window(key)
        if removed:
            _broadcast(_window_close_event(key))
    except Exception as exc:
        logger.warning("Failed to broadcast window_close for %s: %s", key, exc)
    return jsonify({"status": status, "message": message})


@app.get("/events")
def events_stream():
    _start_window_watcher_once()
    _prune_stale_windows()
    q: "queue.Queue[str]" = queue.Queue(maxsize=1024)
    with _sse_subscribers_lock:
        _sse_subscribers.append(q)

    def gen():
        try:
            logger.info("SSE: client connected from %s; sending hydrate", request.remote_addr)
        except Exception:
            pass
        try:
            yield _sse_format(_hydrate_event())
        except GeneratorExit:
            pass
        last_heartbeat = time.time()
        try:
            while True:
                try:
                    item = q.get(timeout=5)
                    yield item
                except queue.Empty:
                    if time.time() - last_heartbeat > 15:
                        try:
                            _prune_stale_windows()
                        except Exception:
                            pass
                        yield ": ping\n\n"
                        last_heartbeat = time.time()
        except GeneratorExit:
            pass
        finally:
            with _sse_subscribers_lock:
                try:
                    _sse_subscribers.remove(q)
                except ValueError:
                    pass
            logger.info("SSE: client disconnected %s", request.remote_addr)

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
        "Access-Control-Allow-Origin": "*",
    }
    return Response(gen(), headers=headers)


@app.post("/screen_size")
def get_screen_size():
    if platform_name == "Linux":
        d = display.Display()
        screen_width = d.screen().width_in_pixels
        screen_height = d.screen().height_in_pixels
    elif platform_name == "Windows":
        user32 = ctypes.windll.user32
        screen_width = user32.GetSystemMetrics(0)
        screen_height = user32.GetSystemMetrics(1)
    else:
        screen = pyautogui.size()
        screen_width, screen_height = screen.width, screen.height
    return jsonify({"width": screen_width, "height": screen_height})


@app.get("/screenshot")
def capture_screen_with_cursor():
    user_platform = platform.system()
    if user_platform == "Windows":
        def get_cursor():
            hcursor = win32gui.GetCursorInfo()[1]
            hotspot = win32gui.GetIconInfo(hcursor)[1:3]
            hdc = win32ui.CreateDCFromHandle(win32gui.GetDC(0))
            hbmp = win32ui.CreateBitmap()
            hbmp.CreateCompatibleBitmap(hdc, 36, 36)
            hdc = hdc.CreateCompatibleDC()
            hdc.SelectObject(hbmp)
            hdc.DrawIcon((0, 0), hcursor)
            bmpinfo = hbmp.GetInfo()
            bmpstr = hbmp.GetBitmapBits(True)
            cursor = Image.frombuffer('RGB', (bmpinfo['bmWidth'], bmpinfo['bmHeight']), bmpstr, 'raw', 'BGRX', 0, 1).convert("RGBA")
            win32gui.DestroyIcon(hcursor)
            win32gui.DeleteObject(hbmp.GetHandle())
            hdc.DeleteDC()
            pixdata = cursor.load()
            width, height = cursor.size
            for y in range(height):
                for x in range(width):
                    if pixdata[x, y] == (0, 0, 0, 255):
                        pixdata[x, y] = (0, 0, 0, 0)
            return cursor, hotspot
        ratio = ctypes.windll.shcore.GetScaleFactorForDevice(0) / 100
        try:
            img = ImageGrab.grab(bbox=None, include_layered_windows=True)
        except OSError:
            img = ImageGrab.grab()
        try:
            cursor, (hotspotx, hotspoty) = get_cursor()
            pos_win = win32gui.GetCursorPos()
            pos = (round(pos_win[0] * ratio - hotspotx), round(pos_win[1] * ratio - hotspoty))
            img.paste(cursor, pos, cursor)
        except Exception as exc:
            logger.warning("Failed to capture cursor on Windows: %s", exc)
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png")
    elif user_platform == "Linux":
        cursor_obj = Xcursor()
        imgarray = cursor_obj.getCursorImageArrayFast()
        cursor_img = Image.fromarray(imgarray)
        screenshot = pyautogui.screenshot()
        cursor_x, cursor_y = pyautogui.position()
        screenshot.paste(cursor_img, (cursor_x, cursor_y), cursor_img)
        buf = BytesIO()
        screenshot.save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png")
    elif user_platform == "Darwin":
        tmp_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
                tmp_path = tmp_file.name
            subprocess.run(["screencapture", "-C", tmp_path], check=True)
            data = Path(tmp_path).read_bytes()
            return send_file(BytesIO(data), mimetype="image/png")
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
    else:
        logger.warning("Platform %s not supported for screenshot", user_platform)
        return jsonify({"error": f"Platform {user_platform} not supported"}), 400




@app.post("/file")
def fetch_file():
    data = request.form or request.get_json(force=True, silent=True) or {}
    file_path = os.path.expandvars(os.path.expanduser(data.get("file_path", "")))
    if not file_path or not os.path.isfile(file_path):
        return jsonify({"error": "file_not_found"}), 404
    try:
        return send_file(file_path, as_attachment=True)
    except Exception as exc:
        logger.error("Failed to send file %s: %s", file_path, exc)
        return jsonify({"error": str(exc)}), 500


@app.post("/list_directory")
def list_directory_route():
    data = request.get_json(force=True, silent=True) or {}
    path = data.get("path") or "."
    include_hidden = bool(data.get("include_hidden", False))
    
    # Safe conversion for max_entries
    try:
        max_entries = int(data.get("max_entries") or 1000)
    except (ValueError, TypeError):
        max_entries = 1000

    resolved = os.path.expandvars(os.path.expanduser(path))
    
    if not os.path.isdir(resolved):
        return jsonify({"error": "directory_not_found"}), 404

    entries = []
    count = 0
    
    try:
        # os.scandir is faster and fetches attributes in one go
        with os.scandir(resolved) as it:
            # Sort manually because scandir yields in arbitrary order
            sorted_entries = sorted(it, key=lambda e: e.name.lower())
            
            for entry in sorted_entries:
                if count >= max_entries:
                    break
                
                if not include_hidden and entry.name.startswith("."):
                    continue

                try:
                    # Get stats. follow_symlinks=False ensures we don't crash on broken links
                    stat = entry.stat(follow_symlinks=False)
                    
                    # Determine type
                    is_dir = entry.is_dir(follow_symlinks=False)
                    
                    # Get metadata safely
                    size = stat.st_size if not is_dir else 0
                    modified = stat.st_mtime
                    
                    entries.append({
                        "name": entry.name,
                        "path": entry.path,
                        "is_dir": is_dir,
                        "size": size,
                        "modified": modified,
                    })
                    count += 1
                    
                except OSError:
                    # If we can't read a specific file (permission/locked), 
                    # we skip it instead of crashing the whole request.
                    continue
                    
    except PermissionError:
        return jsonify({"error": "permission_denied_for_directory"}), 403
    except Exception as exc:
        logger.error("Failed to list directory %s: %s", resolved, exc)
        return jsonify({"error": str(exc)}), 500

    return jsonify({"path": resolved, "entries": entries})



@app.post("/setup/upload")
def upload_file():
    if 'file_path' not in request.form or 'file_data' not in request.files:
        return jsonify({"error": "file_path and file_data are required"}), 400
    file_path = os.path.expandvars(os.path.expanduser(request.form['file_path']))
    file = request.files['file_data']
    try:
        target_dir = os.path.dirname(file_path)
        if target_dir:
            os.makedirs(target_dir, exist_ok=True)
        file.save(file_path)
        uploaded_size = os.path.getsize(file_path)
        logger.info("File uploaded successfully: %s (%s bytes)", file_path, uploaded_size)
        return f"File Uploaded: {uploaded_size} bytes"
    except Exception as exc:
        logger.error("Error uploading file to %s: %s", file_path, exc)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        return jsonify({"error": f"Failed to upload file: {exc}"}), 500


@app.post("/setup/download_file")
def download_file_to_path():
    data = request.get_json(force=True, silent=True) or {}
    url = data.get("url")
    dest_path = data.get("path") or data.get("file_path")
    if not url or not dest_path:
        return jsonify({"error": "url and path are required"}), 400

    timeout_val = data.get("timeout", data.get("timeout_seconds", 300))
    try:
        timeout_s = int(timeout_val) if timeout_val is not None else 300
    except Exception:
        timeout_s = 300
    if timeout_s <= 0:
        timeout_s = 300

    dest_path = os.path.expandvars(os.path.expanduser(str(dest_path)))
    try:
        target_dir = os.path.dirname(dest_path)
        if target_dir:
            os.makedirs(target_dir, exist_ok=True)
        with urllib.request.urlopen(url, timeout=timeout_s) as resp, open(dest_path, "wb") as out:
            shutil.copyfileobj(resp, out, length=1024 * 1024)
        downloaded_size = os.path.getsize(dest_path)
        logger.info("File downloaded successfully: %s (%s bytes)", dest_path, downloaded_size)
        return f"File Downloaded: {downloaded_size} bytes"
    except Exception as exc:
        logger.error("Error downloading file to %s: %s", dest_path, exc)
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except Exception:
                pass
        return jsonify({"error": f"Failed to download file: {exc}"}), 500


@app.get("/platform")
def get_platform():
    return platform.system()


@app.post("/execute")
def execute_command():
    _log_request_details("execute_command")
    data = request.get_json(force=True, silent=True) or {}
    shell = data.get('shell', False)

    timeout_val = data.get("timeout", 120)
    try:
        timeout_s = int(timeout_val) if timeout_val is not None else 120
    except Exception:
        timeout_s = 120
    if timeout_s <= 0:
        timeout_s = 120

    cwd = data.get("cwd") or data.get("working_dir")
    if cwd:
        cwd = os.path.expandvars(os.path.expanduser(str(cwd)))
        if not os.path.isdir(cwd):
            return jsonify({"status": "error", "message": f"working directory does not exist: {cwd}"}), 400
    
    # --- Check 1: Empty Command ---
    command = data.get('command', '' if shell else [])
    if not command:
        return jsonify({'status': 'error', 'message': 'Command is empty'}), 400

    if isinstance(command, str) and not shell:
        try:
            command = shlex.split(command, posix=(platform_name != "Windows"))
        except Exception:
            command = shlex.split(command)
    
    # Expand User Paths (~/)
    for i, arg in enumerate(command):
        if isinstance(arg, str) and (arg.startswith("~/") or arg.startswith("~\\")):
            command[i] = os.path.expanduser(arg)

    # Ensure we use the correct python executable on Windows
    if platform_name == "Windows" and not shell and isinstance(command, list) and command:
        if command[0] in ("python3", "python"):
            command[0] = sys.executable

    # If this is a python -c payload (common for orchestrator pyautogui),
    # harden defaults inside the subprocess to avoid FAILSAFE/PAUSE surprises.
    if (
        not shell
        and isinstance(command, list)
        and len(command) >= 3
        and command[0] in (sys.executable, "python", "python3")
        and command[1] == "-c"
        and isinstance(command[2], str)
    ):
        code_str = command[2]
        needs_tuning = ("pyautogui" in code_str) or ("base64.b64decode" in code_str)
        already_tuned = "pyautogui.FAILSAFE" in code_str or "FAILSAFE" in code_str
        if needs_tuning and not already_tuned:
            patched = (
                "import pyautogui; "
                "pyautogui.FAILSAFE=False; "
                "pyautogui.PAUSE=0; "
                "pyautogui.DARWIN_CATCH_UP_TIME=0; "
                + code_str
            )
            command = list(command)
            command[2] = patched

    def _try_run(cmd_to_run):
        flags = 0
        if platform_name == "Windows" and not shell:
            try:
                if (
                    isinstance(cmd_to_run, list)
                    and len(cmd_to_run) >= 2
                    and str(cmd_to_run[1]).strip().lower() == "-c"
                    and str(cmd_to_run[0]).strip().lower() in {str(sys.executable).lower(), "python", "python3"}
                ):
                    # Avoid flashing a console window for short python -c automation payloads.
                    flags = subprocess.CREATE_NO_WINDOW
            except Exception:
                pass
        return subprocess.run(
            cmd_to_run,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, # This captures the SyntaxError
            shell=shell,
            text=True,
            timeout=timeout_s,
            cwd=cwd,
            creationflags=flags,
        )

    started = time.time()
    acquired = _exec_lock.acquire(timeout=5)
    if not acquired:
        return jsonify({'status': 'error', 'message': 'executor busy'}), 503
        
    try:
        result = _try_run(command)

        # --- Check 2: Retry Logic for Windows Base64 Escaping Issues ---
        if (
            platform_name == "Windows"
            and not shell
            and isinstance(command, list)
            and len(command) >= 3
            and command[0] in (sys.executable, "python", "python3")
            and command[1] == "-c"
            and result.returncode != 0
        ):
            code_str = command[2]
            if "base64.b64decode(" in code_str:
                fixed_code = re.sub(
                    r"base64\\.b64decode\\(([^\"'\\)]+)\\)",
                    r'base64.b64decode("\\1")',
                    code_str,
                )
                if fixed_code != code_str:
                    patched_cmd = list(command)
                    patched_cmd[2] = fixed_code
                    logger.info("Retrying execute_command with patched base64 payload")
                    result = _try_run(patched_cmd)

        duration = time.time() - started
        
        # --- NEW LOGGING LOGIC ---
        # If the command failed (returncode != 0), log the error explicitly
        if result.returncode != 0:
            logger.error(
                "Command FAILED (rc=%s). STDERR:\n%s", 
                result.returncode, 
                result.stderr.strip()
            )
            api_status = "error" # Change status to error
        else:
            logger.info(
                "Command SUCCESS (rc=0). Duration=%.2fs", 
                duration
            )
            api_status = "success"

        return jsonify({
            'status': api_status, # Now accurately reflects command success
            'output': result.stdout,
            'error': result.stderr,
            'returncode': result.returncode
        })
        
    except Exception as exc:
        logger.error("execute_command CRITICAL failure: %s", exc)
        return jsonify({'status': 'error', 'message': str(exc)}), 500
    finally:
        _exec_lock.release()


@app.post("/run_python")
def run_python():
    data = request.get_json(force=True, silent=True) or {}
    code = data.get('code')
    if not code:
        return jsonify({'status': 'error', 'message': 'Code not supplied!'}), 400

    timeout_val = data.get("timeout", data.get("timeout_seconds", 30))
    try:
        timeout_s = int(timeout_val) if timeout_val is not None else 30
    except Exception:
        timeout_s = 30
    if timeout_s <= 0:
        timeout_s = 30

    temp_filename: Optional[str] = None
    started = time.time()
    acquired = _exec_lock.acquire(timeout=5)
    if not acquired:
        return jsonify({'status': 'error', 'message': 'executor busy'}), 503
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as handle:
            handle.write(code)
            temp_filename = handle.name
        flags = subprocess.CREATE_NO_WINDOW if platform_name == "Windows" else 0
        result = subprocess.run(
            [sys.executable, temp_filename],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_s,
            creationflags=flags,
        )
        output = result.stdout
        error_output = result.stderr
        combined = output
        if error_output:
            combined = (combined + '\\n' + error_output) if combined else error_output
        status = 'success' if result.returncode == 0 else 'error'
        if result.returncode != 0 and not error_output:
            error_output = f"Process exited with code {result.returncode}"
            combined = (combined + '\\n' + error_output) if combined else error_output
        duration = time.time() - started
        logger.info("run_python finished returncode=%s duration=%.2fs", result.returncode, duration)
        return jsonify({'status': status, 'message': combined, 'need_more': False, 'output': output, 'error': error_output, 'return_code': result.returncode})
    except subprocess.TimeoutExpired:
        return jsonify({'status': 'error', 'message': f'Execution timeout: Code exceeded {timeout_s}s', 'error': 'TimeoutExpired', 'need_more': False, 'output': None}), 504
    except Exception as exc:
        logger.error("run_python failed: %s", exc)
        return jsonify({'status': 'error', 'message': str(exc)}), 500
    finally:
        if temp_filename and os.path.exists(temp_filename):
            try:
                os.remove(temp_filename)
            except Exception:
                pass
        _exec_lock.release()


def _find_windows_bash_executable() -> Optional[str]:
    # Allow explicit override (useful for Git Bash not on PATH).
    for env_key in ("BASH_PATH", "GIT_BASH_PATH"):
        candidate = (os.environ.get(env_key) or "").strip().strip('"')
        if candidate and os.path.isfile(candidate):
            return candidate

    for exe in ("bash.exe", "bash"):
        found = shutil.which(exe)
        if found:
            return found

    # Common Git for Windows locations.
    candidates: List[str] = []
    for base in (
        os.environ.get("ProgramW6432"),
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
    ):
        if not base:
            continue
        candidates.extend(
            [
                os.path.join(base, "Git", "bin", "bash.exe"),
                os.path.join(base, "Git", "usr", "bin", "bash.exe"),
                os.path.join(base, "Git", "mingw64", "bin", "bash.exe"),
                os.path.join(base, "Git", "mingw32", "bin", "bash.exe"),
            ]
        )

    # MSYS2/Cygwin (best-effort).
    candidates.extend(
        [
            r"C:\msys64\usr\bin\bash.exe",
            r"C:\msys32\usr\bin\bash.exe",
            r"C:\cygwin64\bin\bash.exe",
            r"C:\cygwin\bin\bash.exe",
        ]
    )

    for cand in candidates:
        try:
            if cand and os.path.isfile(cand):
                return cand
        except Exception:
            continue
    return None


def _resolve_bash_executable() -> Optional[str]:
    if platform_name == "Windows":
        return _find_windows_bash_executable()

    for candidate in (shutil.which("bash"), "/bin/bash", "/usr/bin/bash"):
        if not candidate:
            continue
        try:
            if os.path.isfile(candidate):
                return candidate
        except Exception:
            continue
    return None


def _resolve_powershell_executable() -> Optional[str]:
    # Prefer Windows PowerShell for widest compatibility; fall back to pwsh if present.
    for exe in ("powershell.exe", "powershell", "pwsh.exe", "pwsh"):
        found = shutil.which(exe)
        if found:
            return found
    return None


def _is_windows() -> bool:
    return platform_name == "Windows"


@app.post("/run_bash_script")
def run_bash_script():
    data = request.get_json(force=True, silent=True) or {}
    script = data.get('script')
    timeout = data.get('timeout', 100)
    working_dir = data.get('working_dir')
    requested_shell = str(data.get("shell") or "").strip().lower()
    if not script:
        return jsonify({
            'status': 'error',
            'output': 'Script not supplied!',
            'error': '',
            'returncode': -1,
        }), 400

    try:
        timeout = int(timeout) if timeout is not None else 100
    except Exception:
        timeout = 100
    if timeout <= 0:
        timeout = 100

    if working_dir:
        working_dir = os.path.expanduser(working_dir)
        working_dir = os.path.expandvars(working_dir)
        if not os.path.exists(working_dir):
            return jsonify({
                'status': 'error',
                'output': f'Working directory does not exist: {working_dir}',
                'error': '',
                'returncode': -1,
            }), 400

    shell_used: str
    if requested_shell in {"powershell", "pwsh", "ps"}:
        shell_used = "powershell"
        suffix = ".ps1"
    elif requested_shell in {"cmd", "cmd.exe"}:
        shell_used = "cmd"
        suffix = ".cmd"
    else:
        shell_used = "bash"
        suffix = ".sh"

    tmp_file_path: Optional[str] = None
    with tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8") as tmp_file:
        if shell_used == "bash" and "#!/bin/bash" not in script:
            script = "#!/bin/bash\n\n" + script
        tmp_file.write(script)
        tmp_file_path = tmp_file.name
    try:
        if tmp_file_path:
            try:
                os.chmod(tmp_file_path, 0o755)
            except Exception:
                pass

        flags = subprocess.CREATE_NO_WINDOW if _is_windows() else 0

        if shell_used == "bash":
            bash_exe = _resolve_bash_executable()
            if not bash_exe and _is_windows():
                # Windows fallback: if bash isn't installed, fall back to PowerShell instead of 500.
                shell_used = "powershell"
            elif not bash_exe:
                return jsonify({
                    'status': 'error',
                    'output': 'bash not found on this host',
                    'error': '',
                    'returncode': -1,
                    'shell_used': shell_used,
                }), 501

        if shell_used == "powershell":
            ps_exe = _resolve_powershell_executable()
            if not ps_exe:
                return jsonify({
                    'status': 'error',
                    'output': 'PowerShell not found on this host',
                    'error': '',
                    'returncode': -1,
                    'shell_used': shell_used,
                }), 501
            cmd = [ps_exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", tmp_file_path]
        elif shell_used == "cmd":
            cmd_exe = os.environ.get("ComSpec") or shutil.which("cmd.exe") or shutil.which("cmd")
            if not cmd_exe:
                return jsonify({
                    'status': 'error',
                    'output': 'cmd.exe not found on this host',
                    'error': '',
                    'returncode': -1,
                    'shell_used': shell_used,
                }), 501
            cmd = [cmd_exe, "/c", tmp_file_path]
        else:
            # bash
            cmd = [bash_exe, tmp_file_path]  # type: ignore[list-item]

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            cwd=working_dir,
            creationflags=flags,
            shell=False,
        )
        return jsonify({
            'status': 'success' if result.returncode == 0 else 'error',
            'output': result.stdout,
            'error': '',
            'returncode': result.returncode,
            'shell_used': shell_used,
        })
    except subprocess.TimeoutExpired:
        return jsonify({
            'status': 'error',
            'output': f'Script execution timed out after {timeout} seconds',
            'error': '',
            'returncode': -1,
            'shell_used': shell_used,
        }), 500
    except Exception as exc:
        return jsonify({
            'status': 'error',
            'output': f'Failed to execute script: {exc}',
            'error': '',
            'returncode': -1,
            'shell_used': shell_used,
        }), 500
    finally:
        try:
            if tmp_file_path:
                os.unlink(tmp_file_path)
        except Exception:
            pass


@app.get("/apps")
def get_available_apps():
    """
    Return only the TakeBridge default apps that are actually present on this host.
    """
    include_details = request.args.get("details", "false").strip().lower() in {"1", "true", "yes"}

    resolved = _match_default_apps_to_host()
    app_ids = [r["id"] for r in resolved]

    resp: Dict[str, Any] = {
        "status": "success",
        "platform": platform_name,
        "total_apps": len(app_ids),
        "apps": app_ids,
    }

    if include_details:
        resp["details"] = resolved

    return jsonify(resp)


@app.get("/active_windows")
def active_windows():
    _start_window_watcher_once()
    windows = _list_active_windows_from_host()
    return jsonify({
        'status': 'success',
        'platform': platform_name,
        'total_windows': len(windows),
        'windows': windows,
    })


if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5000)
