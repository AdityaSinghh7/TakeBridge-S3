# vm_manager/vm_provider.py

from typing import Optional, Tuple

from vm_manager.config import settings


def _provider() -> str:
    return (settings.VM_PROVIDER or "aws").strip().lower()


def create_agent_instance_for_user(user_id: str) -> Tuple[str, str, Optional[str]]:
    provider = _provider()
    if provider == "aws":
        from vm_manager.aws_vm_manager import create_agent_instance_for_user as _create

        return _create(user_id)
    if provider == "gcp":
        from vm_manager.gcp_vm_manager import create_agent_instance_for_user as _create

        return _create(user_id)
    raise RuntimeError(f"Unsupported VM_PROVIDER '{provider}'")


def terminate_instance(instance_id: str) -> None:
    provider = _provider()
    if provider == "aws":
        from vm_manager.aws_vm_manager import terminate_instance as _terminate

        return _terminate(instance_id)
    if provider == "gcp":
        from vm_manager.gcp_vm_manager import terminate_instance as _terminate

        return _terminate(instance_id)
    raise RuntimeError(f"Unsupported VM_PROVIDER '{provider}'")


def stop_instance(instance_id: str, *, wait: bool = True) -> None:
    provider = _provider()
    if provider == "aws":
        from vm_manager.aws_vm_manager import stop_instance as _stop

        return _stop(instance_id, wait=wait)
    if provider == "gcp":
        from vm_manager.gcp_vm_manager import stop_instance as _stop

        return _stop(instance_id, wait=wait)
    raise RuntimeError(f"Unsupported VM_PROVIDER '{provider}'")
