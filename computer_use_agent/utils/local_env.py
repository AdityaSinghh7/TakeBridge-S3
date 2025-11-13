import subprocess
import sys
from typing import Dict, Optional


class LocalController:
    """Minimal controller to execute bash and python code locally."""

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
