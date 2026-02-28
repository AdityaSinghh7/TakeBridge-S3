from __future__ import annotations

import argparse
import uuid

from server.api.controller_client import VMControllerClient
from server.api.deepagents_backend import VMControllerBackend


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test for VMControllerBackend")
    parser.add_argument("--base-url", dest="base_url", default=None)
    parser.add_argument("--vm-root", dest="vm_root", default=None)
    parser.add_argument("--windows", dest="is_windows", action="store_true")
    args = parser.parse_args()

    controller = VMControllerClient(base_url=args.base_url) if args.base_url else VMControllerClient()
    backend = VMControllerBackend(
        controller=controller,
        vm_root=args.vm_root,
        is_windows=True if args.is_windows else None,
    )

    test_id = uuid.uuid4().hex[:8]
    test_dir = "/smoke"
    test_path = f"{test_dir}/backend_smoke_{test_id}.txt"
    content = "alpha\nbeta\ngamma\n"

    print("write:", backend.write(test_path, content))
    print("read:", backend.read(test_path, offset=0, limit=10))
    print("edit:", backend.edit(test_path, "beta", "beta-edited", replace_all=False))
    print("grep:", backend.grep_raw("beta", path=test_dir))
    print("glob:", backend.glob_info("**/*.txt", path=test_dir))
    print("ls:", backend.ls_info(test_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
