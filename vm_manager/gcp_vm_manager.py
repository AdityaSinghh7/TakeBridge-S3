# vm_manager/gcp_vm_manager.py

import logging
import time
import uuid
from typing import Optional, Tuple

from google.api_core import exceptions as gcp_exceptions
from google.cloud import compute_v1

from vm_manager.config import settings

# Simple constants
HEALTHCHECK_TIMEOUT_SECONDS = 300  # total time we'll wait for instance operations
HEALTHCHECK_INTERVAL_SECONDS = 5  # poll interval (seconds)

logger = logging.getLogger("takebridge.gcp_vm_manager")
_cloud_logging_inited = False


def _init_cloud_logging_if_enabled() -> None:
    global _cloud_logging_inited
    if _cloud_logging_inited:
        return
    _cloud_logging_inited = True

    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if not settings.GCP_ENABLE_CLOUD_LOGGING:
        logger.info("Cloud Logging disabled (GCP_ENABLE_CLOUD_LOGGING=false)")
        return

    try:
        import google.cloud.logging as cloud_logging  # type: ignore

        client = cloud_logging.Client(project=settings.GCP_PROJECT_ID)
        client.setup_logging(log_level=logging.INFO)
        logger.info("Cloud Logging enabled")
    except Exception as exc:
        logger.warning("Failed to enable Cloud Logging: %s", exc)


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


def _disk_self_link(project: str, zone: str, disk_name: str) -> str:
    if disk_name.startswith("projects/") or disk_name.startswith("https://"):
        return disk_name
    return f"projects/{project}/zones/{zone}/disks/{disk_name}"


def _instance_has_disk(inst: compute_v1.Instance, device_name: str) -> bool:
    for disk in inst.disks or []:
        if (disk.device_name or "") == device_name:
            return True
    return False


def _build_base_attached_disk(project: str, zone: str) -> compute_v1.AttachedDisk:
    disk_name = (settings.GCP_BASE_DISK_NAME or "").strip()
    if not disk_name:
        raise RuntimeError("GCP_BASE_DISK_NAME is required to attach base disk")

    mode = (settings.GCP_BASE_DISK_MODE or "READ_ONLY").strip().upper()
    if mode not in {"READ_ONLY", "READ_WRITE"}:
        raise RuntimeError(
            f"Invalid GCP_BASE_DISK_MODE '{mode}'. Expected READ_ONLY or READ_WRITE."
        )

    disk = compute_v1.AttachedDisk()
    disk.type_ = "PERSISTENT"
    disk.source = _disk_self_link(project, zone, disk_name)
    disk.device_name = (settings.GCP_BASE_DISK_DEVICE_NAME or disk_name).strip()
    disk.mode = mode
    disk.auto_delete = False
    disk.boot = False
    return disk


def _attach_base_disk_post_create(
    instance_client: compute_v1.InstancesClient, instance_name: str
) -> None:
    project = settings.GCP_PROJECT_ID
    zone = settings.GCP_ZONE
    device_name = (settings.GCP_BASE_DISK_DEVICE_NAME or settings.GCP_BASE_DISK_NAME).strip()
    deadline = time.time() + settings.GCP_BASE_DISK_ATTACH_TIMEOUT_SECONDS

    while True:
        if time.time() > deadline:
            raise RuntimeError(
                "Timeout attaching base disk after "
                f"{settings.GCP_BASE_DISK_ATTACH_TIMEOUT_SECONDS}s "
                f"(device={device_name}, disk={settings.GCP_BASE_DISK_NAME})"
            )

        inst = instance_client.get(project=project, zone=zone, instance=instance_name)
        if _instance_has_disk(inst, device_name):
            logger.info("Base disk already attached device=%s", device_name)
            return

        logger.info(
            "Attaching base disk post-create disk=%s device=%s",
            settings.GCP_BASE_DISK_NAME,
            device_name,
        )
        attached_disk = _build_base_attached_disk(project, zone)
        req = compute_v1.AttachDiskInstanceRequest(
            project=project,
            zone=zone,
            instance=instance_name,
            attached_disk_resource=attached_disk,
        )
        try:
            op = instance_client.attach_disk(request=req)
            _wait_for_zone_operation(project, zone, op.name)
        except Exception as exc:
            logger.warning("Attach base disk failed: %s", exc)

        time.sleep(settings.GCP_BASE_DISK_ATTACH_INTERVAL_SECONDS)


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

        logger.info(
            "Instance %s state=%s public_ip=%s", instance_name, state, public_ip
        )

        if state == "RUNNING" and public_ip:
            return public_ip

        time.sleep(HEALTHCHECK_INTERVAL_SECONDS)


def _build_local_ssd_disks(*, count: int, zone: str, interface: str) -> list[compute_v1.AttachedDisk]:
    if count <= 0:
        return []

    disks: list[compute_v1.AttachedDisk] = []
    disk_type = f"zones/{zone}/diskTypes/local-ssd"
    for _ in range(count):
        disk = compute_v1.AttachedDisk()
        disk.type_ = "SCRATCH"
        disk.interface = interface
        disk.initialize_params = compute_v1.AttachedDiskInitializeParams(
            disk_type=disk_type,
        )
        disks.append(disk)
    return disks


def create_agent_instance_for_user(user_id: str) -> Tuple[str, str, Optional[str]]:
    """
    Launch a new Agent VM instance for this user on GCP.

    Returns:
        (instance_id, controller_base_url, vnc_url)
    """
    _init_cloud_logging_if_enabled()
    project = settings.GCP_PROJECT_ID
    zone = settings.GCP_ZONE
    if not project:
        raise RuntimeError("GCP_PROJECT_ID is required")
    if not settings.GCP_ASSIGN_PUBLIC_IP:
        raise RuntimeError("GCP_ASSIGN_PUBLIC_IP must be true for controller access")

    instance_name = f"{settings.GCP_INSTANCE_NAME_PREFIX}-{uuid.uuid4().hex[:8]}"
    logger.info(
        "create_agent_instance_for_user user=%s project=%s zone=%s",
        user_id,
        project,
        zone,
    )

    instance = compute_v1.Instance()
    instance.name = instance_name
    instance.advanced_machine_features = compute_v1.AdvancedMachineFeatures(
        enable_nested_virtualization=True
    )
    instance.scheduling = compute_v1.Scheduling(
        on_host_maintenance="TERMINATE",
        automatic_restart=False,
    )
    if settings.GCP_MACHINE_IMAGE:
        logger.info(
            "forcing pd-ssd override for machine image %s", settings.GCP_MACHINE_IMAGE
        )
        instance.source_machine_image = _resolve_machine_image_self_link()
        override_disk = compute_v1.AttachedDisk()
        override_disk.boot = True
        override_disk.auto_delete = True
        override_disk.initialize_params = compute_v1.AttachedDiskInitializeParams(
            disk_type=f"zones/{zone}/diskTypes/pd-ssd",
            disk_size_gb=settings.GCP_DISK_SIZE_GB,
        )
        instance.disks = [override_disk]
    else:
        instance.machine_type = f"zones/{zone}/machineTypes/{settings.GCP_MACHINE_TYPE}"

        disk = compute_v1.AttachedDisk()
        disk.boot = True
        disk.auto_delete = True
        disk.initialize_params = compute_v1.AttachedDiskInitializeParams(
            source_image=_resolve_image_self_link(),
            disk_size_gb=settings.GCP_DISK_SIZE_GB,
            disk_type=f"zones/{zone}/diskTypes/pd-ssd",
        )
        instance.disks = [disk]

    local_ssd_disks = _build_local_ssd_disks(
        count=settings.GCP_LOCAL_SSD_COUNT,
        zone=zone,
        interface=settings.GCP_LOCAL_SSD_INTERFACE,
    )
    if local_ssd_disks:
        instance.disks = list(instance.disks or []) + local_ssd_disks

    attach_strategy = (settings.GCP_BASE_DISK_ATTACH_STRATEGY or "auto").strip().lower()
    valid_strategies = {"auto", "create", "post", "none"}
    if attach_strategy not in valid_strategies:
        raise RuntimeError(
            f"Invalid GCP_BASE_DISK_ATTACH_STRATEGY '{attach_strategy}'. "
            f"Expected one of: {', '.join(sorted(valid_strategies))}."
        )
    want_base_disk = bool((settings.GCP_BASE_DISK_NAME or "").strip()) and attach_strategy != "none"
    if want_base_disk and attach_strategy in {"create", "auto"}:
        try:
            base_disk = _build_base_attached_disk(project, zone)
            instance.disks = list(instance.disks or []) + [base_disk]
            logger.info(
                "Base disk attach at create disk=%s device=%s mode=%s",
                settings.GCP_BASE_DISK_NAME,
                settings.GCP_BASE_DISK_DEVICE_NAME,
                settings.GCP_BASE_DISK_MODE,
            )
        except Exception as exc:
            if attach_strategy == "create":
                raise
            logger.warning(
                "Base disk attach at create failed; will attach post-create: %s",
                exc,
            )

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

    instance.labels = {"project": "takebridge", "role": "agentvm", "user": user_id}

    client = compute_v1.InstancesClient()
    op = client.insert(project=project, zone=zone, instance_resource=instance)
    _wait_for_zone_operation(project, zone, op.name)

    public_ip = _wait_for_instance_running_and_get_public_ip(client, instance_name)

    controller_base_url = f"http://{public_ip}:{settings.AGENT_CONTROLLER_PORT}"
    logger.info("Using controller_base_url=%s", controller_base_url)

    if want_base_disk and attach_strategy in {"post", "auto"}:
        _attach_base_disk_post_create(client, instance_name)

    guac_path = settings.AGENT_GUACAMOLE_PATH or ""
    if guac_path and not guac_path.startswith("/"):
        guac_path = "/" + guac_path
    vnc_url = f"http://{public_ip}:{settings.AGENT_GUACAMOLE_PORT}{guac_path}"

    return instance_name, controller_base_url, vnc_url


def terminate_instance(instance_id: str) -> None:
    """
    Terminate a GCP instance.
    """
    _init_cloud_logging_if_enabled()
    logger.info("terminate_instance %s", instance_id)
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
    _init_cloud_logging_if_enabled()
    logger.info("stop_instance %s wait=%s", instance_id, wait)
    client = compute_v1.InstancesClient()
    try:
        request = compute_v1.StopInstanceRequest(
            project=settings.GCP_PROJECT_ID,
            zone=settings.GCP_ZONE,
            instance=instance_id,
        )
        # Support older google-cloud-compute versions that don't expose this field.
        if hasattr(request, "discard_local_ssd"):
            request.discard_local_ssd = True
        op = client.stop(request=request)
    except gcp_exceptions.GoogleAPICallError as exc:
        if _is_gcp_stop_already_done(exc):
            logger.info("Instance %s already stopped or terminated; continuing", instance_id)
            return
        raise
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
        logger.info("Instance %s state=%s", instance_name, state)

        if state == target_state:
            return

        time.sleep(HEALTHCHECK_INTERVAL_SECONDS)


def _is_gcp_stop_already_done(exc: gcp_exceptions.GoogleAPICallError) -> bool:
    if isinstance(exc, gcp_exceptions.NotFound):
        return True
    if isinstance(exc, (gcp_exceptions.BadRequest, gcp_exceptions.Conflict)):
        message = str(exc).lower()
        if "already" in message and ("stopped" in message or "terminat" in message):
            return True
    return False
