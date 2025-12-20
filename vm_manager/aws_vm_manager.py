# vm_manager/aws_vm_manager.py

import time
from typing import Tuple, Optional

import boto3
import httpx
from botocore.exceptions import ClientError

from vm_manager.config import settings

# Simple constants
HEALTHCHECK_TIMEOUT_SECONDS = 300  # total time we'll wait for instance + controller
HEALTHCHECK_INTERVAL_SECONDS = 5  # poll interval (seconds)


def _parse_security_groups(s: str) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip()]


def create_agent_instance_for_user(user_id: str) -> Tuple[str, str, Optional[str]]:
    """
    Launch a new Agent VM instance for this user.

    Returns:
        (instance_id, controller_base_url, vnc_url)

    For now:
      - uses EC2 public IPv4 address
      - assumes controller is at http://<public-ip>:AGENT_CONTROLLER_PORT
      - vnc_url is left None (we'll wire VNC separately later)
    """
    region = settings.AWS_REGION
    print(
        f"[aws_vm_manager] create_agent_instance_for_user(user={user_id}) in region={region}"
    )

    ec2 = boto3.client("ec2", region_name=region)
    sg_ids = _parse_security_groups(settings.AGENT_SECURITY_GROUP_IDS)

    run_args = {
        "ImageId": settings.AGENT_AMI_ID,
        "InstanceType": settings.AGENT_INSTANCE_TYPE,
        "MinCount": 1,
        "MaxCount": 1,
        "TagSpecifications": [
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Project", "Value": "TakeBridge"},
                    {"Key": "Role", "Value": "AgentVM"},
                    {"Key": "UserId", "Value": user_id},
                ],
            }
        ],
    }

    if sg_ids:
        run_args["SecurityGroupIds"] = sg_ids
    if settings.AGENT_SUBNET_ID:
        run_args["SubnetId"] = settings.AGENT_SUBNET_ID
    if settings.AGENT_SSH_KEY_NAME:
        run_args["KeyName"] = settings.AGENT_SSH_KEY_NAME

    print(f"[aws_vm_manager] run_instances args: {run_args}")
    resp = ec2.run_instances(**run_args)

    inst = resp["Instances"][0]
    instance_id = inst["InstanceId"]
    print(f"[aws_vm_manager] Launched instance_id={instance_id}")

    # Wait until instance is in 'running' state and has a public IP
    public_ip = _wait_for_instance_running_and_get_public_ip(ec2, instance_id)

    # Build controller URL
    controller_base_url = f"http://{public_ip}:{settings.AGENT_CONTROLLER_PORT}"
    print(f"[aws_vm_manager] Using controller_base_url={controller_base_url}")

    # Healthcheck the controller
    if not settings.VM_SKIP_CONTROLLER_HEALTHCHECK:
        _wait_for_controller_health(
            controller_base_url, settings.AGENT_CONTROLLER_HEALTH_PATH
        )

    # Build streaming URL (Guacamole)
    guac_path = settings.AGENT_GUACAMOLE_PATH or ""
    if guac_path and not guac_path.startswith("/"):
        guac_path = "/" + guac_path
    vnc_url = f"http://{public_ip}:{settings.AGENT_GUACAMOLE_PORT}{guac_path}"

    return instance_id, controller_base_url, vnc_url


def _wait_for_instance_running_and_get_public_ip(ec2, instance_id: str) -> str:
    """
    Poll EC2 until instance is running and has a public IP.
    Handles InvalidInstanceID.NotFound by retrying for a while
    (EC2 eventual-consistency right after run_instances).
    """
    deadline = time.time() + HEALTHCHECK_TIMEOUT_SECONDS

    while True:
        if time.time() > deadline:
            raise RuntimeError(f"Timeout waiting for EC2 instance {instance_id} to start")

        try:
            desc = ec2.describe_instances(InstanceIds=[instance_id])
        except ClientError as e:
            code = e.response["Error"]["Code"]
            msg = e.response["Error"]["Message"]
            print(
                f"[aws_vm_manager] describe_instances error for {instance_id}: {code} - {msg}"
            )
            if code == "InvalidInstanceID.NotFound":
                # Very common right after run_instances: just retry
                time.sleep(HEALTHCHECK_INTERVAL_SECONDS)
                continue
            # Any other error: bubble up
            raise

        reservations = desc.get("Reservations", [])
        if not reservations or not reservations[0].get("Instances"):
            print(f"[aws_vm_manager] No instances found yet for {instance_id}, retrying...")
            time.sleep(HEALTHCHECK_INTERVAL_SECONDS)
            continue

        inst = reservations[0]["Instances"][0]
        state = inst["State"]["Name"]
        public_ip = inst.get("PublicIpAddress")

        print(f"[aws_vm_manager] Instance {instance_id} state={state}, public_ip={public_ip}")

        if state == "running" and public_ip:
            return public_ip

        time.sleep(HEALTHCHECK_INTERVAL_SECONDS)


def _wait_for_controller_health(base_url: str, health_path: str):
    """Poll the controller's /health endpoint until it responds 200 or timeout."""
    url = f"{base_url.rstrip('/')}{health_path}"
    print(f"[aws_vm_manager] Waiting for controller health at {url}")

    deadline = time.time() + HEALTHCHECK_TIMEOUT_SECONDS
    while True:
        if time.time() > deadline:
            raise RuntimeError(f"Timeout waiting for controller health at {url}")

        try:
            # We assume HTTP (no TLS) inside VM
            resp = httpx.get(url, timeout=5.0)
            print(f"[aws_vm_manager] Healthcheck status={resp.status_code}")
            if resp.status_code == 200:
                return
        except Exception as e:
            print(f"[aws_vm_manager] Healthcheck error: {e}")

        time.sleep(HEALTHCHECK_INTERVAL_SECONDS)


def terminate_instance(instance_id: str):
    """
    Terminate an EC2 instance.

    Args:
        instance_id: The EC2 instance ID to terminate
    """
    print(f"[aws_vm_manager] terminate_instance({instance_id})")
    ec2 = boto3.client("ec2", region_name=settings.AWS_REGION)
    ec2.terminate_instances(InstanceIds=[instance_id])


def stop_instance(instance_id: str, *, wait: bool = True) -> None:
    """
    Stop (power off) an EC2 instance.

    This is a reversible alternative to termination for EBS-backed instances.

    Args:
        instance_id: The EC2 instance ID to stop.
        wait: When True, block until the instance reaches 'stopped' (or timeout).
    """
    print(f"[aws_vm_manager] stop_instance({instance_id}) wait={wait}")
    ec2 = boto3.client("ec2", region_name=settings.AWS_REGION)
    try:
        ec2.stop_instances(InstanceIds=[instance_id])
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        msg = e.response.get("Error", {}).get("Message")
        # If the instance is already stopped/stopping, treat as success.
        if code == "IncorrectInstanceState":
            print(f"[aws_vm_manager] stop_instances: {code} - {msg}; continuing")
        else:
            raise

    if wait:
        _wait_for_instance_state(ec2, instance_id, target_state="stopped")


def _wait_for_instance_state(ec2, instance_id: str, *, target_state: str) -> None:
    """
    Poll EC2 until instance reaches a target state or timeout.
    """
    deadline = time.time() + HEALTHCHECK_TIMEOUT_SECONDS
    while True:
        if time.time() > deadline:
            raise RuntimeError(
                f"Timeout waiting for EC2 instance {instance_id} to reach state={target_state}"
            )

        try:
            desc = ec2.describe_instances(InstanceIds=[instance_id])
        except ClientError as e:
            code = e.response["Error"]["Code"]
            msg = e.response["Error"]["Message"]
            print(
                f"[aws_vm_manager] describe_instances error for {instance_id}: {code} - {msg}"
            )
            if code == "InvalidInstanceID.NotFound":
                time.sleep(HEALTHCHECK_INTERVAL_SECONDS)
                continue
            raise

        reservations = desc.get("Reservations", [])
        if not reservations or not reservations[0].get("Instances"):
            print(f"[aws_vm_manager] No instances found yet for {instance_id}, retrying...")
            time.sleep(HEALTHCHECK_INTERVAL_SECONDS)
            continue

        inst = reservations[0]["Instances"][0]
        state = inst["State"]["Name"]
        print(f"[aws_vm_manager] Instance {instance_id} state={state}")

        if state == target_state:
            return

        # If the instance transitions to a terminal state that cannot reach the target, fail fast.
        if target_state in {"stopped", "running"} and state in {"shutting-down", "terminated"}:
            raise RuntimeError(
                f"Instance {instance_id} entered terminal state={state} while waiting for state={target_state}"
            )

        time.sleep(HEALTHCHECK_INTERVAL_SECONDS)
