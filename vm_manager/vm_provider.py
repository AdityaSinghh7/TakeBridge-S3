# vm_manager/vm_provider.py

from typing import Optional, Tuple

from vm_manager.config import settings


def _provider() -> str:
    return (settings.VM_PROVIDER or "aws").strip().lower()


def current_provider() -> str:
    return _provider()


def provider_location() -> str:
    provider = _provider()
    if provider == "gcp":
        return settings.GCP_ZONE
    return settings.AWS_REGION


def provider_spec() -> dict:
    provider = _provider()
    if provider == "gcp":
        spec: dict[str, str | int] = {"zone": settings.GCP_ZONE}
        if settings.GCP_MACHINE_IMAGE:
            spec["machine_image"] = settings.GCP_MACHINE_IMAGE
            spec["machine_image_project"] = (
                settings.GCP_MACHINE_IMAGE_PROJECT or settings.GCP_PROJECT_ID
            )
        else:
            spec["image"] = settings.GCP_IMAGE
            spec["image_project"] = settings.GCP_IMAGE_PROJECT or settings.GCP_PROJECT_ID
            spec["machine_type"] = settings.GCP_MACHINE_TYPE
            spec["disk_size_gb"] = settings.GCP_DISK_SIZE_GB
        if (settings.GCP_BASE_DISK_NAME or "").strip():
            spec["base_disk_name"] = settings.GCP_BASE_DISK_NAME
            spec["base_disk_device_name"] = settings.GCP_BASE_DISK_DEVICE_NAME
            spec["base_disk_mode"] = settings.GCP_BASE_DISK_MODE
            spec["base_disk_attach_strategy"] = settings.GCP_BASE_DISK_ATTACH_STRATEGY
        return spec
    return {
        "instance_type": settings.AGENT_INSTANCE_TYPE,
        "region": settings.AWS_REGION,
        "ami_id": settings.AGENT_AMI_ID,
    }


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
