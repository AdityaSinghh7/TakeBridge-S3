import subprocess
import sys
import platform
from typing import Any, Dict, Optional


class LocalController:
    """Minimal controller to execute bash and python code locally."""

    def get_apps(self, *, exclude_system: bool = True, timeout: Optional[float] = None) -> Dict[str, Any]:
        """
        Get list of available apps on local system.

        Args:
            exclude_system: Whether to exclude system apps (not implemented for local)
            timeout: Timeout in seconds (not used)

        Returns:
            Dict with status and apps list
        """
        try:
            system = platform.system().lower()

            if system == "darwin":  # macOS
                # Get running apps on macOS
                result = subprocess.run(
                    ["osascript", "-e", 'tell application "System Events" to get name of every application process'],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    apps = [app.strip() for app in result.stdout.split(",") if app.strip()]
                    return {"status": "success", "apps": apps}
                else:
                    return {"status": "error", "apps": [], "error": result.stderr}
            else:
                # For other platforms, return empty list
                return {"status": "success", "apps": []}

        except Exception as exc:
            return {"status": "error", "apps": [], "error": str(exc)}

    def get_active_windows(self, *, exclude_system: bool = True, timeout: Optional[float] = None) -> Dict[str, Any]:
        """
        Get list of active windows on local system.

        Args:
            exclude_system: Whether to exclude system windows (not implemented for local)
            timeout: Timeout in seconds (not used)

        Returns:
            Dict with status and windows list
        """
        try:
            system = platform.system().lower()

            if system == "darwin":  # macOS
                # Get window info on macOS
                result = subprocess.run(
                    ["osascript", "-e", '''
                        tell application "System Events"
                            set windowList to {}
                            repeat with proc in (every application process whose visible is true)
                                set procName to name of proc
                                try
                                    repeat with win in (every window of proc)
                                        set end of windowList to procName & ": " & (name of win)
                                    end repeat
                                end try
                            end repeat
                            return windowList
                        end tell
                    '''],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    windows = []
                    for item in result.stdout.split(","):
                        item = item.strip()
                        if ":" in item:
                            app_name, title = item.split(":", 1)
                            windows.append({
                                "app_name": app_name.strip(),
                                "title": title.strip()
                            })
                    return {"status": "success", "windows": windows}
                else:
                    return {"status": "error", "windows": [], "error": result.stderr}
            else:
                # For other platforms, return empty list
                return {"status": "success", "windows": []}

        except Exception as exc:
            return {"status": "error", "windows": [], "error": str(exc)}

    def run_bash_script(
        self,
        code: str,
        timeout: int = 30,
        *,
        timeout_seconds: Optional[int] = None,
    ) -> Dict:
        if timeout_seconds is not None:
            timeout = timeout_seconds
        try:
            proc = subprocess.run(
                ["/bin/bash", "-lc", code],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = (proc.stdout or "") + (proc.stderr or "")

            print("BASH OUTPUT =======================================")
            print(output)
            print("BASH OUTPUT =======================================")

            return {
                "status": "ok" if proc.returncode == 0 else "error",
                "returncode": proc.returncode,
                "output": output,
                "error": "",
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "status": "error",
                "returncode": -1,
                "output": exc.stdout or "",
                "error": f"TimeoutExpired: {str(exc)}",
            }
        except Exception as exc:
            return {
                "status": "error",
                "returncode": -1,
                "output": "",
                "error": str(exc),
            }

    def run_python_script(
        self,
        code: str,
        *,
        timeout_seconds: Optional[int] = None,
    ) -> Dict:
        try:
            proc = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=timeout_seconds if timeout_seconds is not None else None,
            )
            print("PYTHON OUTPUT =======================================")
            print(proc.stdout or "")
            print("PYTHON OUTPUT =======================================")
            return {
                "status": "ok" if proc.returncode == 0 else "error",
                "return_code": proc.returncode,
                "output": proc.stdout or "",
                "error": proc.stderr or "",
            }
        except Exception as exc:
            return {
                "status": "error",
                "return_code": -1,
                "output": "",
                "error": str(exc),
            }


class LocalEnv:
    """Simple environment that provides a controller compatible with CodeAgent."""

    def __init__(self):
        self.controller = LocalController()
