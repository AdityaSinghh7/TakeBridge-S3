# DeepAgents VM Backend

This adapter wraps `VMControllerClient` to implement the DeepAgents `BackendProtocol`.
Agent paths are POSIX-style and mapped onto a VM root directory.

## Requirements

- Install the `deepagents` package in the environment that runs the agent.
- Ensure the VM controller is reachable (see `server/api/controller_client.py` for env vars).

## Configuration

- `DEEPAGENTS_VM_ROOT`: VM path used as the agent `/` root. Defaults to
  `C:\Users\Docker\deepagent` on Windows or `/home/user/deepagent` on POSIX.
- `DEEPAGENTS_VM_RUN_TIMEOUT_SECONDS`: `run_python` timeout (default: `30`).
- `DEEPAGENTS_VM_REQUEST_TIMEOUT_SECONDS`: HTTP request timeout for controller calls.

## Usage

```python
from server.api.controller_client import VMControllerClient
from server.api.deepagents_backend import VMControllerBackend, create_vm_deep_agent

controller = VMControllerClient(base_url="http://127.0.0.1:5000")
backend = VMControllerBackend(
    controller=controller,
    vm_root="C:\\Users\\Docker\\deepagent",
)

agent = create_vm_deep_agent(
    controller=controller,
    vm_root="C:\\Users\\Docker\\deepagent",
    system_prompt="You have access to the VM filesystem under /",
)
```

## Smoke test

```bash
python scripts/smoke_deepagents_backend.py --base-url http://127.0.0.1:5000 --windows
```
