# vm_manager/gcp_vm_manager.py

import time
import uuid
from typing import Optional, Tuple

import httpx
from google.cloud import compute_v1

from vm_manager.config import settings

# Simple constants
HEALTHCHECK_TIMEOUT_SECONDS = 300  # total time we'll wait for instance + controller
HEALTHCHECK_INTERVAL_SECONDS = 5  # poll interval (seconds)


def _parse_tags(s: str) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip()]


def _resolve_image_self_link() -> str:
    image = (settings.GCP_IMAGE or "").strip()
    if not image:
        raise RuntimeError("GCP_IMAGE is required")

    if image.startswith("projects/") or image.startswith("https://"):
        return image

    image_project = settings.GCP_IMAGE_PROJECT or settings.GCP_PROJECT_ID
    if not image_project:
        raise RuntimeError("GCP_IMAGE_PROJECT or GCP_PROJECT_ID is required for image name")

    return f"projects/{image_project}/global/images/{image}"


def _resolve_machine_image_self_link() -> str:
    image = (settings.GCP_MACHINE_IMAGE or "").strip()
    if not image:
        raise RuntimeError("GCP_MACHINE_IMAGE is required")

    if image.startswith("projects/") or image.startswith("https://"):
        return image

    image_project = settings.GCP_MACHINE_IMAGE_PROJECT or settings.GCP_PROJECT_ID
    if not image_project:
        raise RuntimeError(
            "GCP_MACHINE_IMAGE_PROJECT or GCP_PROJECT_ID is required for machine image name"
        )

    return f"projects/{image_project}/global/machineImages/{image}"


def _wait_for_zone_operation(project: str, zone: str, operation_name: str) -> None:
    client = compute_v1.ZoneOperationsClient()
    deadline = time.time() + HEALTHCHECK_TIMEOUT_SECONDS
    while True:
        if time.time() > deadline:
            raise RuntimeError(f"Timeout waiting for GCP operation {operation_name}")

        op = client.get(project=project, zone=zone, operation=operation_name)
        if op.status == compute_v1.Operation.Status.DONE:
            if op.error:
                raise RuntimeError(f"GCP operation {operation_name} failed: {op.error}")
            return
        time.sleep(HEALTHCHECK_INTERVAL_SECONDS)


def _wait_for_instance_running_and_get_public_ip(
    instance_client: compute_v1.InstancesClient, instance_name: str
) -> str:
    """
    Poll GCP until instance is running and has a public IP.
    """
    project = settings.GCP_PROJECT_ID
    zone = settings.GCP_ZONE
    deadline = time.time() + HEALTHCHECK_TIMEOUT_SECONDS

    while True:
        if time.time() > deadline:
            raise RuntimeError(f"Timeout waiting for GCP instance {instance_name} to start")

        inst = instance_client.get(project=project, zone=zone, instance=instance_name)
        state = inst.status
        public_ip = None

        for nic in inst.network_interfaces:
            for access_config in nic.access_configs or []:
                if access_config.nat_i_p:
                    public_ip = access_config.nat_i_p
                    break
            if public_ip:
                break

        print(
            f"[gcp_vm_manager] Instance {instance_name} state={state}, public_ip={public_ip}"
        )

        if state == "RUNNING" and public_ip:
            return public_ip

        time.sleep(HEALTHCHECK_INTERVAL_SECONDS)


def _wait_for_controller_health(base_url: str, health_path: str) -> None:
    """Poll the controller's /health endpoint until it responds 200 or timeout."""
    url = f"{base_url.rstrip('/')}{health_path}"
    print(f"[gcp_vm_manager] Waiting for controller health at {url}")

    deadline = time.time() + HEALTHCHECK_TIMEOUT_SECONDS
    while True:
        if time.time() > deadline:
            raise RuntimeError(f"Timeout waiting for controller health at {url}")

        try:
            resp = httpx.get(url, timeout=5.0)
            print(f"[gcp_vm_manager] Healthcheck status={resp.status_code}")
            if resp.status_code == 200:
                return
        except Exception as e:
            print(f"[gcp_vm_manager] Healthcheck error: {e}")

        time.sleep(HEALTHCHECK_INTERVAL_SECONDS)


def create_agent_instance_for_user(user_id: str) -> Tuple[str, str, Optional[str]]:
    """
    Launch a new Agent VM instance for this user on GCP.

    Returns:
        (instance_id, controller_base_url, vnc_url)
    """
    project = settings.GCP_PROJECT_ID
    zone = settings.GCP_ZONE
    if not project:
        raise RuntimeError("GCP_PROJECT_ID is required")
    if not settings.GCP_ASSIGN_PUBLIC_IP:
        raise RuntimeError("GCP_ASSIGN_PUBLIC_IP must be true for controller access")

    instance_name = f"{settings.GCP_INSTANCE_NAME_PREFIX}-{uuid.uuid4().hex[:8]}"
    print(
        f"[gcp_vm_manager] create_agent_instance_for_user(user={user_id}) project={project} zone={zone}"
    )

    instance = compute_v1.Instance()
    instance.name = instance_name
    if settings.GCP_MACHINE_IMAGE:
        instance.source_machine_image = _resolve_machine_image_self_link()
    else:
        instance.machine_type = f"zones/{zone}/machineTypes/{settings.GCP_MACHINE_TYPE}"

        disk = compute_v1.AttachedDisk()
        disk.boot = True
        disk.auto_delete = True
        disk.initialize_params = compute_v1.AttachedDiskInitializeParams(
            source_image=_resolve_image_self_link(),
            disk_size_gb=settings.GCP_DISK_SIZE_GB,
        )
        instance.disks = [disk]

    nic = compute_v1.NetworkInterface()
    nic.network = settings.GCP_NETWORK
    if settings.GCP_SUBNETWORK:
        nic.subnetwork = settings.GCP_SUBNETWORK
    if settings.GCP_ASSIGN_PUBLIC_IP:
        nic.access_configs = [
            compute_v1.AccessConfig(name="External NAT", type_="ONE_TO_ONE_NAT")
        ]
    instance.network_interfaces = [nic]

    tags = _parse_tags(settings.GCP_TAGS)
    if tags:
        instance.tags = compute_v1.Tags(items=tags)

    if settings.GCP_SERVICE_ACCOUNT:
        instance.service_accounts = [
            compute_v1.ServiceAccount(
                email=settings.GCP_SERVICE_ACCOUNT,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
        ]

    if settings.GCP_STARTUP_SCRIPT:
        instance.metadata = compute_v1.Metadata(
            items=[
                compute_v1.Metadata.ItemsValueListEntry(
                    key="startup-script", value=settings.GCP_STARTUP_SCRIPT
                )
            ]
        )

    instance.labels = {"project": "takebridge", "role": "agentvm", "user": user_id}

    client = compute_v1.InstancesClient()
    op = client.insert(project=project, zone=zone, instance_resource=instance)
    _wait_for_zone_operation(project, zone, op.name)

    public_ip = _wait_for_instance_running_and_get_public_ip(client, instance_name)

    controller_base_url = f"http://{public_ip}:{settings.AGENT_CONTROLLER_PORT}"
    print(f"[gcp_vm_manager] Using controller_base_url={controller_base_url}")
    if not settings.VM_SKIP_CONTROLLER_HEALTHCHECK:
        _wait_for_controller_health(
            controller_base_url, settings.AGENT_CONTROLLER_HEALTH_PATH
        )

    ws_scheme = settings.AGENT_VNC_SCHEME
    ws_port = settings.AGENT_VNC_WS_PORT
    ws_path = settings.AGENT_VNC_WS_PATH or ""
    if ws_path and not ws_path.startswith("/"):
        ws_path = "/" + ws_path
    vnc_url = f"{ws_scheme}://{public_ip}:{ws_port}{ws_path}"

    return instance_name, controller_base_url, vnc_url


def terminate_instance(instance_id: str) -> None:
    """
    Terminate a GCP instance.
    """
    print(f"[gcp_vm_manager] terminate_instance({instance_id})")
    client = compute_v1.InstancesClient()
    op = client.delete(
        project=settings.GCP_PROJECT_ID,
        zone=settings.GCP_ZONE,
        instance=instance_id,
    )
    _wait_for_zone_operation(settings.GCP_PROJECT_ID, settings.GCP_ZONE, op.name)


def stop_instance(instance_id: str, *, wait: bool = True) -> None:
    """
    Stop (power off) a GCP instance.
    """
    print(f"[gcp_vm_manager] stop_instance({instance_id}) wait={wait}")
    client = compute_v1.InstancesClient()
    op = client.stop(
        project=settings.GCP_PROJECT_ID,
        zone=settings.GCP_ZONE,
        instance=instance_id,
    )
    if wait:
        _wait_for_zone_operation(settings.GCP_PROJECT_ID, settings.GCP_ZONE, op.name)
        _wait_for_instance_state(client, instance_id, target_state="TERMINATED")


def _wait_for_instance_state(
    instance_client: compute_v1.InstancesClient, instance_name: str, *, target_state: str
) -> None:
    """
    Poll GCP until instance reaches a target state or timeout.
    """
    project = settings.GCP_PROJECT_ID
    zone = settings.GCP_ZONE
    deadline = time.time() + HEALTHCHECK_TIMEOUT_SECONDS

    while True:
        if time.time() > deadline:
            raise RuntimeError(
                f"Timeout waiting for GCP instance {instance_name} to reach state={target_state}"
            )

        inst = instance_client.get(project=project, zone=zone, instance=instance_name)
        state = inst.status
        print(f"[gcp_vm_manager] Instance {instance_name} state={state}")

        if state == target_state:
            return

        time.sleep(HEALTHCHECK_INTERVAL_SECONDS)
