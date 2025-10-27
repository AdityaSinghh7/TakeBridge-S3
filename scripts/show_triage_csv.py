#!/usr/bin/env python3
"""
Fetch /home/user/takebridge_demo/triage/triage_results.csv via the VM controller.
"""

import logging
logging.basicConfig(level=logging.DEBUG)

import json
import os

from framework.api.controller_client import VMControllerClient

logger = logging.getLogger(__name__)

def main() -> None:
    base_url = os.getenv("VM_SERVER_BASE_URL")
    logger.debug("os.getenv('VM_SERVER_BASE_URL')=%s", base_url)
    client = VMControllerClient(base_url=base_url)
    logger.debug("client.base_url=%s", client.base_url)
    result = client.run_bash_script(
        script="cat /home/user/takebridge_demo/triage/triage_results.csv",
        timeout_seconds=30,
        working_dir=None,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
