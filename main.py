import ctypes
import sys
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
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import queue
import tempfile
from urllib.parse import urlparse

import pyautogui
from PIL import Image, ImageGrab

from flask import Flask, Response, jsonify, request, send_file
from flask_cors import CORS


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
    import logging
    import sys

    app.logger.setLevel(logging.INFO)
    if not any(isinstance(h, logging.StreamHandler) for h in app.logger.handlers):
        _handler = logging.StreamHandler(sys.stdout)
        _handler.setLevel(logging.INFO)
        _handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        app.logger.addHandler(_handler)
    logging.getLogger('werkzeug').setLevel(logging.INFO)
except Exception:
    pass

pyautogui.PAUSE = 0
pyautogui.DARWIN_CATCH_UP_TIME = 0
pyautogui.FAILSAFE = False

USE_GLOBAL_DESKTOP_VNC = True

logger = app.logger

_sse_subscribers_lock = threading.Lock()
_sse_subscribers: List["queue.Queue[str]"] = []
_open_windows_lock = threading.Lock()
_open_windows: Dict[str, Dict[str, Any]] = {}
_window_watcher_started = False
_recent_launches: Dict[str, float] = {}
_last_focused_app_id: Optional[str] = None

LOCK_DIR = Path("/home/user/server")
try:
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

STREAM_SH = "/home/user/server/stream_window.sh"
CLOSE_SH = "/home/user/server/close_app.sh"


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

def _normalize_app_id(name: str) -> str:
    """
    Turn a human-readable app name or class into a stable, URL-safe id.
    Example: 'Windows PowerShell' -> 'windows-powershell'
    """
    name = name.strip().lower()
    name = re.sub(r'[^a-z0-9]+', '-', name)
    return name.strip('-') or 'unknown'


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
                            # Strip field codes like %U, %u, %f, etc.
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
            is_system = d.startswith("/usr/share")  # rough heuristic

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

    Returns a list of:
      {
        "id": <normalized id>,
        "name": <display name>,
        "app_id": <raw AppID from Windows>,
        "kind": "startapps",
        "is_system": bool,
        "platform": "Windows",
      }
    """
    apps: List[Dict[str, Any]] = []

    # Prefer PowerShell Get-StartApps
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

            # Get-StartApps returns either an object or an array
            items = data if isinstance(data, list) else [data]

            for item in items:
                name = (item.get("Name") or "").strip()
                appid = (item.get("AppID") or "").strip()
                if not name:
                    continue

                norm_id = _normalize_app_id(name)

                lower_name = name.lower()
                is_system = (
                    lower_name.startswith("windows ") or
                    "update" in lower_name or
                    "uninstall" in lower_name
                )

                apps.append({
                    "id": norm_id,
                    "name": name,
                    "app_id": appid,
                    "kind": "startapps",
                    "is_system": is_system,
                    "platform": "Windows",
                })

            # If we got anything, we're done
            if apps:
                return apps

    except Exception as exc:
        logger.warning("Get-StartApps scan failed: %s", exc)

    # Fallback: old .lnk-based scan if Get-StartApps fails
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

                    app_id = _normalize_app_id(name)
                    if app_id in seen_ids:
                        continue
                    seen_ids.add(app_id)

                    lower_name = name.lower()
                    is_system = (
                        lower_name.startswith("windows ") or
                        "update" in lower_name or
                        "uninstall" in lower_name
                    )

                    apps.append({
                        "id": app_id,
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
            name = entry[:-4]  # strip .app
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
_HOST_APPS_TTL = 30.0  # seconds


def _scan_host_apps(force: bool = False) -> List[Dict[str, Any]]:
    """
    Cross-platform scan of installed GUI-ish apps.
    We keep a short-lived cache to avoid walking the filesystem on every request.
    """
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
            res = subprocess.run([
                "xdotool",
                "search",
                "--onlyvisible",
                "--class",
                str(cls),
            ], capture_output=True, text=True, timeout=1)
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
            res = subprocess.run([
                "xdotool",
                "search",
                "--onlyvisible",
                "--class",
                str(cls),
            ], capture_output=True, text=True, timeout=1)
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
    return subprocess.check_output(["hostname", "-I"]).decode().split()[0].strip()


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
    # Launch Outlook PWA via Chrome/Chromium app-id with the Default profile.
    # App ID from your WM_CLASS: crx_faolnafnngnfdaknnbpnkhgohbobgegn
    try:
        for bin_name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
            if shutil.which(bin_name):
                return f"{bin_name} --profile-directory=Default --app-id=faolnafnngnfdaknnbpnkhgohbobgegn"
    except Exception:
        pass
    # Fallback to google-chrome; shell will error if not present
    return "google-chrome --profile-directory=Default --app-id=faolnafnngnfdaknnbpnkhgohbobgegn"


APPS: Dict[str, Dict[str, Any]] = {
    "chrome": {
        "bin": "/usr/bin/google-chrome",
        "class": "google-chrome",
        "ws": 6093,
        "launch": "/usr/bin/google-chrome --new-window --start-maximized --no-first-run --disable-restore-session-state --no-default-browser-check --disable-dev-shm-usage",
    },
    "code": {
        "bin": "/usr/bin/code",
        "class": "code",
        "ws": 6091,
        "launch": "code",
    },
    "calc": {
        "bin": "/usr/bin/libreoffice",
        "class": "libreoffice-calc",
        "ws": 6094,
        "launch": "libreoffice --calc",
    },
    "writer": {
        "bin": "/usr/bin/libreoffice",
        "class": "libreoffice-writer",
        "ws": 6095,
        "launch": "libreoffice --writer",
    },
    "libreoffice": {
        "bin": "/usr/bin/libreoffice",
        "class": "libreoffice",
        "ws": 6090,
        "launch": "libreoffice --writer",
    },
    "terminal": {
        "bin": "/usr/bin/gnome-terminal",
        "class": "gnome-terminal-server",
        "ws": 6100,
        "launch": "bash -lc 'command -v gnome-terminal >/dev/null 2>&1 && gnome-terminal || command -v x-terminal-emulator >/dev/null 2>&1 && x-terminal-emulator || command -v xterm >/dev/null 2>&1 && xterm || command -v konsole >/dev/null 2>&1 && konsole || command -v tilix >/dev/null 2>&1 && tilix || command -v mate-terminal >/dev/null 2>&1 && mate-terminal || command -v alacritty >/dev/null 2>&1 && alacritty || command -v kitty >/dev/null 2>&1 && kitty'",
    },
    "files": {
        "bin": "/usr/bin/nautilus",
        "class": "nautilus",
        "ws": 6101,
        "launch": "nautilus",
    },
    "impress": {
        "bin": "/usr/bin/libreoffice",
        "class": "libreoffice-impress",
        "ws": 6102,
        "launch": "libreoffice --impress",
    },
    "gimp": {
        "bin": "/usr/bin/gimp",
        "class": "gimp",
        "ws": 6103,
        "launch": "gimp",
    },
    "vlc": {
        "bin": "/usr/bin/vlc",
        "class": "vlc",
        "ws": 6104,
        "launch": "vlc",
    },
    "outlook": {
        "bin": "/usr/bin/google-chrome",
        "class": "google-chrome",
        "ws": 6092,
        "launch": _default_outlook_launch(),
    },
    "gedit": {
        "bin": "/usr/bin/gedit",
        "class": "gedit",
        "ws": 6105,
        "launch": "gedit",
    },
    "evince": {
        "bin": "/usr/bin/evince",
        "class": "evince",
        "ws": 6106,
        "launch": "evince",
    },
    "slack": {
        "bin": "/usr/bin/slack",
        "class": "slack",
        "ws": 6107,
        "launch": "slack",
    },
    "mailspring": {
        "bin": "/snap/bin/mailspring",
        "class": "Mailspring",
        "ws": 6109,
        "launch": "/snap/bin/mailspring",
    },
    "firefox": {
        "bin": "/usr/bin/firefox",
        "class": "firefox",
        "ws": 6108,
        "launch": "firefox",
    },
}

def _lc(s: str) -> str:
    return s.lower()


DEFAULT_APPS_BY_PLATFORM: Dict[str, List[Dict[str, Any]]] = {
    # ---- Windows defaults (logical TakeBridge app IDs) ----
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
            "match": ["libreoffice "],  # generic launcher
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


try:
    if isinstance(APPS.get("terminal"), dict):
        APPS["terminal"]["launch"] = "gnome-terminal"
except Exception:
    pass



def _get_default_app_specs_for_platform() -> List[Dict[str, Any]]:
    return DEFAULT_APPS_BY_PLATFORM.get(platform_name, [])



def _map_window_to_default_app(window: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Given a raw window descriptor (title, wmClass/cls, etc.), try to map it
    to one of the TakeBridge default app specs for this platform.

    Returns the matching spec or None.
    """
    specs = _get_default_app_specs_for_platform()
    if not specs:
        return None

    # Build a searchable text blob out of common window fields
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



def _discover_available_apps() -> Dict[str, Dict[str, Any]]:
    """
    Return a subset of APPS that are actually available on this host,
    based on their configured 'bin' or the executable in 'launch'.
    Platform-agnostic: works for Linux, Windows, and macOS.
    """
    available: Dict[str, Dict[str, Any]] = {}

    for app_id, meta in APPS.items():
        bin_path = meta.get("bin")
        launch_cmd = meta.get("launch")
        is_available = False

        # 1) If an absolute binary path is provided, check that it exists
        if isinstance(bin_path, str) and bin_path.strip():
            if os.path.isabs(bin_path) and os.path.exists(bin_path):
                is_available = True
            elif shutil.which(bin_path):
                is_available = True

        # 2) Otherwise, look at the first token of the launch command and see if it's on PATH
        if not is_available and isinstance(launch_cmd, str) and launch_cmd.strip():
            try:
                first_token = shlex.split(launch_cmd)[0]
                if shutil.which(first_token):
                    is_available = True
            except Exception:
                pass

        if is_available:
            available[app_id] = meta

    return available


def _list_active_windows_from_host() -> List[Dict[str, Any]]:
    """
    Inspect the host desktop to discover visible windows/apps.

    For each window, we try to map it to one of the TakeBridge default apps
    for this platform. Only windows that match a default app are returned, and
    their id/appId are normalized to logical IDs like 'chrome', 'edge', etc.
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

                # Map to a default app (chrome, libreoffice, etc.)
                spec = _map_window_to_default_app(window)
                if not spec:
                    # Skip non-default apps/windows
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
                    # Skip windows that aren't in our TakeBridge default app set
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

    # ---------- Fallback ----------
    with _open_windows_lock:
        return list(_open_windows.values())



@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "platform": platform_name,
    }), 200


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
                # Launch via Start menu ID
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
                return jsonify({"status": "error", "message": "no launchable path for app"}), 500

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

    # maintain your existing VNC/open-window behaviour
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

    available_apps = _discover_available_apps()
    if key not in available_apps:
        if key in APPS:
            return jsonify({"status": "error", "message": f"app '{key}' not available on this host"}), 400
        return jsonify({"status": "error", "message": "unknown app"}), 400

    meta = available_apps[key]
    if not os.path.isfile(CLOSE_SH):
        return jsonify({"status": "error", "message": f"{CLOSE_SH} not found"}), 500
    cmd = [CLOSE_SH, key, meta["bin"], str(meta["ws"]), meta["class"]]
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
    file_path = os.path.join(os.path.dirname(__file__), "screenshots", "screenshot.png")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    user_platform = platform.system()
    if user_platform == "Windows":
        def get_cursor():
            hcursor = win32gui.GetCursorInfo()[1]
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
            hotspot = win32gui.GetIconInfo(hcursor)[1:3]
            return cursor, hotspot
        ratio = ctypes.windll.shcore.GetScaleFactorForDevice(0) / 100
        try:
            img = ImageGrab.grab(bbox=None, include_layered_windows=True)
        except OSError:
            # Fallback that we already know works from REPL
            img = ImageGrab.grab()
        try:
            cursor, (hotspotx, hotspoty) = get_cursor()
            pos_win = win32gui.GetCursorPos()
            pos = (round(pos_win[0] * ratio - hotspotx), round(pos_win[1] * ratio - hotspoty))
            img.paste(cursor, pos, cursor)
        except Exception as exc:
            logger.warning("Failed to capture cursor on Windows: %s", exc)
        img.save(file_path)
    elif user_platform == "Linux":
        cursor_obj = Xcursor()
        imgarray = cursor_obj.getCursorImageArrayFast()
        cursor_img = Image.fromarray(imgarray)
        screenshot = pyautogui.screenshot()
        cursor_x, cursor_y = pyautogui.position()
        screenshot.paste(cursor_img, (cursor_x, cursor_y), cursor_img)
        screenshot.save(file_path)
    elif user_platform == "Darwin":
        subprocess.run(["screencapture", "-C", file_path])
    else:
        logger.warning("Platform %s not supported for screenshot", user_platform)
        return jsonify({"error": f"Platform {user_platform} not supported"}), 400
    return send_file(file_path, mimetype='image/png')


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


@app.get("/platform")
def get_platform():
    return platform.system()


@app.post("/execute")
def execute_command():
    _log_request_details("execute_command")
    data = request.get_json(force=True, silent=True) or {}
    shell = data.get('shell', False)
    command = data.get('command', '' if shell else [])
    if isinstance(command, str) and not shell:
        command = shlex.split(command)
    for i, arg in enumerate(command):
        if isinstance(arg, str) and arg.startswith("~/"):
            command[i] = os.path.expanduser(arg)

    if platform_name == "Windows" and not shell and isinstance(command, list) and command:
        if command[0] in ("python3", "python"):
            command[0] = sys.executable
    try:
        flags = subprocess.CREATE_NO_WINDOW if platform_name == "Windows" else 0
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=shell,
            text=True,
            timeout=120,
            creationflags=flags,
        )
        return jsonify({
            'status': 'success',
            'output': result.stdout,
            'error': result.stderr,
            'returncode': result.returncode
        })
    except Exception as exc:
        return jsonify({'status': 'error', 'message': str(exc)}), 500


@app.post("/run_python")
def run_python():
    data = request.get_json(force=True, silent=True) or {}
    code = data.get('code')
    if not code:
        return jsonify({'status': 'error', 'message': 'Code not supplied!'}), 400
    temp_filename = f"/tmp/python_exec_{uuid.uuid4().hex}.py"
    try:
        with open(temp_filename, 'w') as handle:
            handle.write(code)
        result = subprocess.run(
            ['/usr/bin/python3', temp_filename],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
        output = result.stdout
        error_output = result.stderr
        combined = output
        if error_output:
            combined = (combined + '\n' + error_output) if combined else error_output
        status = 'success' if result.returncode == 0 else 'error'
        if result.returncode != 0 and not error_output:
            error_output = f"Process exited with code {result.returncode}"
            combined = (combined + '\n' + error_output) if combined else error_output
        return jsonify({
            'status': status,
            'message': combined,
            'need_more': False,
            'output': output,
            'error': error_output,
            'return_code': result.returncode,
        })
    except subprocess.TimeoutExpired:
        return jsonify({
            'status': 'error',
            'message': 'Execution timeout: Code took too long to execute',
            'error': 'TimeoutExpired',
            'need_more': False,
            'output': None,
        }), 500
    except Exception as exc:
        return jsonify({
            'status': 'error',
            'message': f'Execution error: {exc}',
            'error': traceback.format_exc(),
            'need_more': False,
            'output': None,
        }), 500
    finally:
        try:
            os.remove(temp_filename)
        except Exception:
            pass


@app.post("/run_bash_script")
def run_bash_script():
    data = request.get_json(force=True, silent=True) or {}
    script = data.get('script')
    timeout = data.get('timeout', 100)
    working_dir = data.get('working_dir')
    if not script:
        return jsonify({
            'status': 'error',
            'output': 'Script not supplied!',
            'error': '',
            'returncode': -1,
        }), 400
    if working_dir:
        working_dir = os.path.expanduser(working_dir)
        if not os.path.exists(working_dir):
            return jsonify({
                'status': 'error',
                'output': f'Working directory does not exist: {working_dir}',
                'error': '',
                'returncode': -1,
            }), 400
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as tmp_file:
        if "#!/bin/bash" not in script:
            script = "#!/bin/bash\n\n" + script
        tmp_file.write(script)
        tmp_file_path = tmp_file.name
    try:
        os.chmod(tmp_file_path, 0o755)
        if platform_name == "Windows":
            flags = subprocess.CREATE_NO_WINDOW
            result = subprocess.run(
                ['bash', tmp_file_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout,
                cwd=working_dir,
                creationflags=flags,
                shell=False,
            )
        else:
            flags = 0
            result = subprocess.run(
                ['/bin/bash', tmp_file_path],
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
        })
    except subprocess.TimeoutExpired:
        return jsonify({
            'status': 'error',
            'output': f'Script execution timed out after {timeout} seconds',
            'error': '',
            'returncode': -1,
        }), 500
    except FileNotFoundError:
        try:
            result = subprocess.run(
                ['sh', tmp_file_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout,
                cwd=working_dir,
                shell=False,
            )
            return jsonify({
                'status': 'success' if result.returncode == 0 else 'error',
                'output': result.stdout,
                'error': '',
                'returncode': result.returncode,
            })
        except Exception as exc:
            return jsonify({
                'status': 'error',
                'output': f'Failed to execute script: {exc}',
                'error': '',
                'returncode': -1,
            }), 500
    except Exception as exc:
        return jsonify({
            'status': 'error',
            'output': f'Failed to execute script: {exc}',
            'error': '',
            'returncode': -1,
        }), 500
    finally:
        try:
            os.unlink(tmp_file_path)
        except Exception:
            pass


@app.get("/apps")
def get_available_apps():
    """
    Return only the TakeBridge default apps that are actually present on this host.

    - Logical IDs are stable across machines (e.g. "chrome", "edge", "libreoffice-writer").
    - Under the hood we match them to whatever the OS reports via Get-StartApps / .desktop / .app.
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
        # We expose the host metadata under "host" so you can debug if needed.
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
