from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Dict, List, Optional, Sequence, Tuple

from server.api.controller_client import VMControllerClient, VMControllerError

logger = logging.getLogger(__name__)

_DEFAULT_WINDOWS_ROOT = r"C:\Users\Docker\deepagent"
_DEFAULT_POSIX_ROOT = "/home/user/deepagent"
_ROOT_ENV_VAR = "DEEPAGENTS_VM_ROOT"
_RUN_TIMEOUT_ENV_VAR = "DEEPAGENTS_VM_RUN_TIMEOUT_SECONDS"
_REQUEST_TIMEOUT_ENV_VAR = "DEEPAGENTS_VM_REQUEST_TIMEOUT_SECONDS"

def _fallback_number_lines(text: str, *, start: int = 1) -> str:
    if not text:
        return ""
    lines = text.splitlines()
    return "\n".join(f"{start + idx}: {line}" for idx, line in enumerate(lines))


try:
    from deepagents import create_deep_agent as _create_deep_agent
    from deepagents.backends.protocol import BackendProtocol, EditResult, WriteResult
    from deepagents.backends.utils import FileInfo, GrepMatch, number_lines as _number_lines

    _HAS_DEEPAGENTS = True
except Exception:  # pragma: no cover - optional dependency
    _HAS_DEEPAGENTS = False
    _create_deep_agent = None

    class BackendProtocol:  # type: ignore[override]
        pass

    @dataclass
    class FileInfo:  # type: ignore[override]
        path: str
        is_dir: Optional[bool] = None
        size: Optional[int] = None
        modified_at: Optional[float] = None

    @dataclass
    class GrepMatch:  # type: ignore[override]
        path: str
        line: int
        text: str

    @dataclass
    class WriteResult:  # type: ignore[override]
        error: Optional[str] = None
        path: Optional[str] = None
        files_update: Optional[Dict[str, Any]] = None

    @dataclass
    class EditResult:  # type: ignore[override]
        error: Optional[str] = None
        path: Optional[str] = None
        files_update: Optional[Dict[str, Any]] = None
        occurrences: Optional[int] = None

    _number_lines = _fallback_number_lines


def _format_number_lines(text: str, start: int) -> str:
    try:
        return _number_lines(text, start=start)
    except TypeError:
        try:
            return _number_lines(text, start)
        except Exception:
            return _fallback_number_lines(text, start=start)


def _looks_like_windows(path: str) -> bool:
    return ":" in path or "\\" in path


def _coerce_int(raw: Optional[str], default: int) -> int:
    if raw is None:
        return default
    try:
        return int(raw)
    except Exception:
        return default


def _coerce_float(raw: Optional[str], default: Optional[float]) -> Optional[float]:
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except Exception:
        return default


@dataclass
class VMControllerBackend(BackendProtocol):
    """
    DeepAgents backend backed by a VMControllerClient.

    Paths are POSIX-style for the agent and mapped onto a VM root directory.
    """

    controller: VMControllerClient
    vm_root: Optional[str] = None
    is_windows: Optional[bool] = None
    run_timeout_seconds: Optional[int] = None
    request_timeout: Optional[float] = None

    def __post_init__(self) -> None:
        resolved_windows = self.is_windows
        if resolved_windows is None:
            resolved_windows = self._detect_windows()
        self.is_windows = bool(resolved_windows)

        env_root = (os.getenv(_ROOT_ENV_VAR) or "").strip()
        if not self.vm_root:
            if env_root:
                self.vm_root = env_root
            else:
                self.vm_root = _DEFAULT_WINDOWS_ROOT if self.is_windows else _DEFAULT_POSIX_ROOT

        self.vm_root = self.vm_root.strip()
        if not self.vm_root:
            self.vm_root = _DEFAULT_WINDOWS_ROOT if self.is_windows else _DEFAULT_POSIX_ROOT
        self._vm_root_path = (
            PureWindowsPath(self.vm_root) if self.is_windows else PurePosixPath(self.vm_root)
        )

        if self.run_timeout_seconds is None:
            self.run_timeout_seconds = _coerce_int(os.getenv(_RUN_TIMEOUT_ENV_VAR), 30)
        if self.request_timeout is None:
            self.request_timeout = _coerce_float(os.getenv(_REQUEST_TIMEOUT_ENV_VAR), None)

    def _detect_windows(self) -> bool:
        try:
            platform_val = self.controller.get_platform()
            if isinstance(platform_val, str):
                platform_str = platform_val.strip().lower()
                if platform_str.startswith("win"):
                    return True
                if platform_str.startswith("windows"):
                    return True
        except Exception:
            pass
        if self.vm_root:
            return _looks_like_windows(self.vm_root)
        return False

    def _normalize_agent_path(self, path: Optional[str]) -> str:
        if path is None:
            return "/"
        raw = str(path).strip()
        if not raw or raw == "/":
            return "/"
        raw = raw.replace("\\", "/")
        if not raw.startswith("/"):
            raw = f"/{raw}"
        parts = [part for part in raw.split("/") if part not in ("", ".")]
        if any(part == ".." for part in parts):
            raise ValueError("path_traversal_not_allowed")
        return "/" + "/".join(parts)

    def _to_vm_path(self, agent_path: str) -> str:
        rel_parts = [part for part in PurePosixPath(agent_path).parts if part not in ("/", "")]
        if self.is_windows:
            return str(PureWindowsPath(self._vm_root_path, *rel_parts))
        return str(PurePosixPath(self._vm_root_path, *rel_parts))

    def _from_vm_path(self, vm_path: str) -> Optional[str]:
        vm_parts = PureWindowsPath(vm_path) if self.is_windows else PurePosixPath(vm_path)
        try:
            relative = vm_parts.relative_to(self._vm_root_path)
        except Exception:
            return None
        if not relative.parts:
            return "/"
        return "/" + "/".join(relative.parts)

    def _build_script(self, payload: Dict[str, Any], body: str, *, imports: Sequence[str]) -> str:
        imports_block = "\n".join(f"import {name}" for name in imports)
        payload_json = json.dumps(payload)
        return f"{imports_block}\npayload = json.loads({payload_json!r})\n{body}"

    def _run_python_json(self, script: str) -> Tuple[bool, Any, Optional[str]]:
        try:
            resp = self.controller.run_python(
                script,
                timeout_seconds=self.run_timeout_seconds,
                timeout=self.request_timeout,
            )
        except Exception as exc:
            return False, None, f"run_python failed: {exc}"
        if not isinstance(resp, dict):
            return False, None, "run_python returned non-dict response"
        status = resp.get("status")
        if status != "success":
            return False, None, str(resp.get("message") or resp.get("error") or "run_python failed")
        raw = resp.get("output") or resp.get("message") or ""
        if not isinstance(raw, str) or not raw.strip():
            return False, None, "run_python produced no output"
        try:
            return True, json.loads(raw), None
        except Exception as exc:
            return False, None, f"Failed to parse run_python JSON: {exc}"

    def _path_exists(self, agent_path: str) -> Optional[Dict[str, bool]]:
        vm_path = self._to_vm_path(agent_path)
        payload = {"path": vm_path}
        body = """
path = payload.get("path") or ""
exists = os.path.exists(path)
is_file = os.path.isfile(path)
is_dir = os.path.isdir(path)
print(json.dumps({"exists": exists, "is_file": is_file, "is_dir": is_dir}))
"""
        script = self._build_script(payload, body, imports=["json", "os"])
        ok, data, err = self._run_python_json(script)
        if not ok or not isinstance(data, dict):
            logger.warning("VM backend path_exists failed for %s: %s", agent_path, err)
            return None
        return {
            "exists": bool(data.get("exists")),
            "is_file": bool(data.get("is_file")),
            "is_dir": bool(data.get("is_dir")),
        }

    def ls_info(self, path: str) -> List[FileInfo]:
        try:
            agent_path = self._normalize_agent_path(path)
        except ValueError:
            return []
        vm_path = self._to_vm_path(agent_path)
        try:
            response = self.controller.list_directory(vm_path, timeout=self.request_timeout)
        except VMControllerError as exc:
            logger.warning("VM backend ls_info failed for %s: %s", agent_path, exc)
            return []
        except Exception as exc:
            logger.warning("VM backend ls_info failed for %s: %s", agent_path, exc)
            return []
        entries = response.get("entries") if isinstance(response, dict) else None
        if not isinstance(entries, list):
            return []
        results: List[FileInfo] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            vm_entry_path = entry.get("path")
            if not vm_entry_path:
                continue
            agent_entry_path = self._from_vm_path(str(vm_entry_path))
            if not agent_entry_path:
                continue
            results.append(
                FileInfo(
                    path=agent_entry_path,
                    is_dir=bool(entry.get("is_dir")) if "is_dir" in entry else None,
                    size=entry.get("size"),
                    modified_at=entry.get("modified"),
                )
            )
        results.sort(key=lambda info: info.path)
        return results

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        try:
            agent_path = self._normalize_agent_path(file_path)
        except ValueError:
            return f"Error: File '{file_path}' not found"
        if agent_path == "/":
            return f"Error: File '{agent_path}' not found"
        offset_val = max(int(offset or 0), 0)
        limit_val = max(int(limit or 0), 0)
        payload = {
            "path": self._to_vm_path(agent_path),
            "agent_path": agent_path,
            "offset": offset_val,
            "limit": limit_val,
        }
        body = """
path = payload.get("path") or ""
agent_path = payload.get("agent_path") or path
offset = int(payload.get("offset") or 0)
limit = int(payload.get("limit") or 0)
if offset < 0:
    offset = 0
if limit < 0:
    limit = 0
if not os.path.isfile(path):
    print(json.dumps({"ok": False, "error": "Error: File '" + agent_path + "' not found"}))
else:
    lines = []
    if limit != 0:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for idx, line in enumerate(handle):
                if idx < offset:
                    continue
                if len(lines) >= limit:
                    break
                lines.append(line.rstrip("\\n"))
    print(json.dumps({"ok": True, "lines": lines, "start": offset + 1}))
"""
        script = self._build_script(payload, body, imports=["json", "os"])
        ok, data, err = self._run_python_json(script)
        if not ok or not isinstance(data, dict):
            logger.warning("VM backend read failed for %s: %s", agent_path, err)
            return f"Error: File '{agent_path}' not found"
        if not data.get("ok"):
            return str(data.get("error") or f"Error: File '{agent_path}' not found")
        lines = data.get("lines")
        if not isinstance(lines, list):
            return ""
        text = "\n".join(str(line) for line in lines)
        start = data.get("start")
        try:
            start_line = int(start)
        except Exception:
            start_line = offset_val + 1
        return _format_number_lines(text, start=start_line)

    def grep_raw(
        self,
        pattern: str,
        path: Optional[str] = None,
        glob: Optional[str] = None,
    ) -> List[GrepMatch] | str:
        try:
            agent_path = self._normalize_agent_path(path)
        except ValueError:
            agent_path = "/"
        payload = {
            "pattern": pattern or "",
            "path": agent_path,
            "glob": glob,
            "vm_root": self.vm_root,
        }
        body = """
vm_root = payload.get("vm_root") or ""
pattern = payload.get("pattern") or ""
path = payload.get("path") or "/"
glob_pattern = payload.get("glob")

def agent_to_vm(agent_path):
    rel = agent_path.lstrip("/")
    if not rel:
        return vm_root
    parts = [part for part in rel.split("/") if part]
    return os.path.join(vm_root, *parts)

def vm_to_agent(vm_path):
    try:
        rel = os.path.relpath(vm_path, vm_root)
    except ValueError:
        return None
    if rel.startswith(".."):
        return None
    parts = [part for part in rel.split(os.sep) if part and part != "."]
    return "/" + "/".join(parts) if parts else "/"

try:
    regex = re.compile(pattern)
except re.error as exc:
    print(json.dumps({"regex_error": "Invalid regex pattern: " + str(exc)}))
    raise SystemExit

files = []
if glob_pattern:
    if glob_pattern.startswith("/"):
        agent_glob = glob_pattern
    else:
        agent_glob = (path.rstrip("/") + "/" + glob_pattern) if path != "/" else "/" + glob_pattern
    vm_glob = agent_to_vm(agent_glob)
    for candidate in glob.glob(vm_glob, recursive=True):
        if os.path.isfile(candidate):
            files.append(candidate)
else:
    base_vm = agent_to_vm(path)
    if os.path.isfile(base_vm):
        files = [base_vm]
    elif os.path.isdir(base_vm):
        for root, _, filenames in os.walk(base_vm):
            for name in filenames:
                files.append(os.path.join(root, name))

matches = []
for file_path in files:
    agent_file = vm_to_agent(file_path)
    if not agent_file:
        continue
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as handle:
            for idx, line in enumerate(handle, start=1):
                if regex.search(line):
                    matches.append({"path": agent_file, "line": idx, "text": line.rstrip("\\n")})
    except OSError:
        continue

print(json.dumps({"matches": matches}))
"""
        script = self._build_script(payload, body, imports=["json", "os", "re", "glob"])
        ok, data, err = self._run_python_json(script)
        if not ok or not isinstance(data, dict):
            return f"Error: grep failed ({err})"
        if data.get("regex_error"):
            return str(data.get("regex_error"))
        raw_matches = data.get("matches")
        if not isinstance(raw_matches, list):
            return []
        results: List[GrepMatch] = []
        for match in raw_matches:
            if not isinstance(match, dict):
                continue
            try:
                results.append(
                    GrepMatch(
                        path=str(match.get("path") or ""),
                        line=int(match.get("line") or 0),
                        text=str(match.get("text") or ""),
                    )
                )
            except Exception:
                continue
        return results

    def glob_info(self, pattern: str, path: str = "/") -> List[FileInfo]:
        try:
            agent_path = self._normalize_agent_path(path)
        except ValueError:
            return []
        payload = {
            "pattern": pattern or "",
            "path": agent_path,
            "vm_root": self.vm_root,
        }
        body = """
vm_root = payload.get("vm_root") or ""
pattern = payload.get("pattern") or ""
path = payload.get("path") or "/"

def agent_to_vm(agent_path):
    rel = agent_path.lstrip("/")
    if not rel:
        return vm_root
    parts = [part for part in rel.split("/") if part]
    return os.path.join(vm_root, *parts)

if pattern.startswith("/"):
    agent_pattern = pattern
else:
    agent_pattern = (path.rstrip("/") + "/" + pattern) if path != "/" else "/" + pattern

vm_pattern = agent_to_vm(agent_pattern)
matches = []
for vm_path in glob.glob(vm_pattern, recursive=True):
    try:
        stat = os.stat(vm_path)
    except OSError:
        continue
    is_dir = os.path.isdir(vm_path)
    try:
        rel = os.path.relpath(vm_path, vm_root)
    except ValueError:
        continue
    if rel.startswith(".."):
        continue
    parts = [part for part in rel.split(os.sep) if part and part != "."]
    agent_path = "/" + "/".join(parts) if parts else "/"
    matches.append(
        {
            "path": agent_path,
            "is_dir": is_dir,
            "size": stat.st_size if not is_dir else 0,
            "modified_at": stat.st_mtime,
        }
    )

print(json.dumps({"matches": matches}))
"""
        script = self._build_script(payload, body, imports=["json", "os", "glob"])
        ok, data, err = self._run_python_json(script)
        if not ok or not isinstance(data, dict):
            logger.warning("VM backend glob_info failed for %s: %s", agent_path, err)
            return []
        raw_matches = data.get("matches")
        if not isinstance(raw_matches, list):
            return []
        results: List[FileInfo] = []
        for match in raw_matches:
            if not isinstance(match, dict):
                continue
            match_path = match.get("path")
            if not match_path:
                continue
            results.append(
                FileInfo(
                    path=str(match_path),
                    is_dir=bool(match.get("is_dir")) if "is_dir" in match else None,
                    size=match.get("size"),
                    modified_at=match.get("modified_at"),
                )
            )
        results.sort(key=lambda info: info.path)
        return results

    def write(self, file_path: str, content: str) -> WriteResult:
        try:
            agent_path = self._normalize_agent_path(file_path)
        except ValueError:
            return WriteResult(error=f"Error: File '{file_path}' not found")
        if agent_path == "/":
            return WriteResult(error="Error: File path must not be root")
        exists_info = self._path_exists(agent_path)
        if exists_info is None:
            return WriteResult(error=f"Error: Failed to verify '{agent_path}'")
        if exists_info.get("exists"):
            return WriteResult(error=f"Error: File '{agent_path}' already exists")
        vm_path = self._to_vm_path(agent_path)
        try:
            self.controller.upload_file(vm_path, content.encode("utf-8"), timeout=self.request_timeout)
        except Exception as exc:
            logger.warning("VM backend write failed for %s: %s", agent_path, exc)
            return WriteResult(error=f"Error: Failed to write '{agent_path}': {exc}")
        return WriteResult(error=None, path=agent_path, files_update=None)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        try:
            agent_path = self._normalize_agent_path(file_path)
        except ValueError:
            return EditResult(error=f"Error: File '{file_path}' not found")
        if agent_path == "/":
            return EditResult(error="Error: File path must not be root")
        payload = {
            "path": self._to_vm_path(agent_path),
            "agent_path": agent_path,
            "old_string": old_string,
            "new_string": new_string,
            "replace_all": bool(replace_all),
        }
        body = """
path = payload.get("path") or ""
agent_path = payload.get("agent_path") or path
old_string = payload.get("old_string")
new_string = payload.get("new_string")
replace_all = bool(payload.get("replace_all"))

if old_string is None:
    old_string = ""
if new_string is None:
    new_string = ""

if not os.path.isfile(path):
    print(json.dumps({"ok": False, "error": "Error: File '" + agent_path + "' not found"}))
elif old_string == "":
    print(json.dumps({"ok": False, "error": "Error: old_string must not be empty"}))
else:
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        data = handle.read()
    occurrences = data.count(old_string)
    if occurrences == 0:
        print(json.dumps({"ok": False, "error": "Error: old_string not found"}))
    elif (not replace_all) and occurrences > 1:
        print(json.dumps({"ok": False, "error": "Error: old_string occurs multiple times"}))
    else:
        if replace_all:
            new_data = data.replace(old_string, new_string)
        else:
            new_data = data.replace(old_string, new_string, 1)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(new_data)
        print(json.dumps({"ok": True, "occurrences": occurrences}))
"""
        script = self._build_script(payload, body, imports=["json", "os"])
        ok, data, err = self._run_python_json(script)
        if not ok or not isinstance(data, dict):
            logger.warning("VM backend edit failed for %s: %s", agent_path, err)
            return EditResult(error=f"Error: Failed to edit '{agent_path}': {err}")
        if not data.get("ok"):
            return EditResult(error=str(data.get("error") or "Error: edit failed"))
        occurrences = data.get("occurrences")
        try:
            count = int(occurrences)
        except Exception:
            count = None
        return EditResult(
            error=None,
            path=agent_path,
            files_update=None,
            occurrences=count,
        )


def create_vm_deep_agent(
    *,
    controller: VMControllerClient,
    vm_root: Optional[str] = None,
    is_windows: Optional[bool] = None,
    run_timeout_seconds: Optional[int] = None,
    request_timeout: Optional[float] = None,
    **kwargs: Any,
) -> Any:
    """
    Convenience factory for DeepAgents with the VM controller backend.
    """
    if _create_deep_agent is None or not _HAS_DEEPAGENTS:
        raise RuntimeError(
            "DeepAgents is required to build the agent. "
            "Install the 'deepagents' package to use create_vm_deep_agent."
        )
    backend = VMControllerBackend(
        controller=controller,
        vm_root=vm_root,
        is_windows=is_windows,
        run_timeout_seconds=run_timeout_seconds,
        request_timeout=request_timeout,
    )
    return _create_deep_agent(backend=backend, **kwargs)
