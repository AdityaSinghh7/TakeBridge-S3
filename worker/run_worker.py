"""
Worker loop scaffold for claiming and executing workflow runs.

This is a synchronous placeholder showing how to:
- Claim a queued run
- Provision a VM per run (placeholder)
- Emit run_events into Supabase
- Mark run completion or errors
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
import uuid
from typing import Any, Dict, Optional, Union
from urllib.parse import urlparse

from sqlalchemy import text

from computer_use_agent.orchestrator.data_types import (
    OrchestrateRequest,
    WorkerConfig,
    GroundingConfig,
    ControllerConfig,
)
from server.api.orchestrator_adapter import orchestrate_to_orchestrator
from orchestrator_agent.runtime import OrchestratorRuntime
from shared.db.engine import SessionLocal
from shared.supabase_client import get_service_supabase_client
from shared.streaming import StreamEmitter, set_current_emitter, reset_current_emitter
from vm_manager.aws_vm_manager import create_agent_instance_for_user, terminate_instance
from vm_manager.config import settings

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 30  # seconds
ATTENTION_TIMEOUT = 180  # seconds


def claim_next_run(claimed_by: str) -> Optional[Dict[str, Any]]:
    """
    Atomically claim the oldest queued run.
    """
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                """
                WITH next_run AS (
                    SELECT id, workflow_id, user_id
                    FROM workflow_runs
                    WHERE status = 'queued'
                    ORDER BY created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE workflow_runs wr
                SET status = 'running',
                    started_at = NOW(),
                    last_heartbeat_at = NOW(),
                    claimed_by = :claimed_by,
                    updated_at = NOW()
                FROM next_run
                WHERE wr.id = next_run.id
                RETURNING wr.id, wr.workflow_id, wr.user_id
                """
            ),
            {"claimed_by": claimed_by},
        ).mappings().first()
        db.commit()
        return dict(row) if row else None
    except Exception as exc:  # pragma: no cover - scaffolding
        db.rollback()
        logger.exception("Failed to claim run: %s", exc)
        return None
    finally:
        db.close()


def insert_vm_instance(run_id: str, status: str, provider: str, spec: Dict[str, Any], endpoint: Dict[str, Any]) -> str:
    db = SessionLocal()
    try:
        res = db.execute(
            text(
                """
                INSERT INTO vm_instances (id, run_id, status, provider, spec, endpoint, created_at)
                VALUES (:id, :run_id, :status, :provider, :spec, :endpoint, NOW())
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "run_id": run_id,
                "status": status,
                "provider": provider,
                "spec": json.dumps(spec),
                "endpoint": json.dumps(endpoint),
            },
        )
        db.commit()
        return res.lastrowid if hasattr(res, "lastrowid") else ""
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def update_vm_status(vm_id: str, status: str, terminated: bool = False):
    db = SessionLocal()
    try:
        db.execute(
            text(
                """
                UPDATE vm_instances
                SET status = :status,
                    terminated_at = CASE WHEN :terminated THEN NOW() ELSE terminated_at END
                WHERE id = :vm_id
                """
            ),
            {"status": status, "vm_id": vm_id, "terminated": terminated},
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _json_safe(val: Any) -> Any:
    """
    Ensure payloads are JSON serializable by coercing UUIDs and other objects to str.
    """
    try:
        json.dumps(val)
        return val
    except TypeError:
        if isinstance(val, dict):
            return {k: _json_safe(v) for k, v in val.items()}
        if isinstance(val, (list, tuple)):
            return [_json_safe(v) for v in val]
        return str(val)


def record_event(run_id: str, kind: str, message: str, payload: Optional[Dict[str, Any]] = None) -> None:
    """
    Insert a run_event row in Supabase using the service client.
    """
    client = get_service_supabase_client()
    try:
        client.table("run_events").insert(
            {
                "run_id": str(run_id),
                "kind": kind,
                "message": message,
                "payload": _json_safe(payload) if payload else {},
            }
        ).execute()
    except Exception as exc:  # pragma: no cover - scaffolding
        logger.warning("Failed to record event for run %s: %s", run_id, exc)


def _build_run_emitter(run_id: str) -> StreamEmitter:
    """
    Create a StreamEmitter that mirrors orchestrator stream events into run_events.
    """
    noisy_suffixes = (
        ".output.delta",
        ".reasoning.delta",
        ".stream.completed",
        ".stream.error",
    )

    def _publish(event: str, data: Optional[Any] = None) -> None:
        # Drop high-volume token streams; keep higher-level lifecycle events.
        for suffix in noisy_suffixes:
            if event.endswith(suffix):
                return

        payload_dict: Dict[str, Any] = {}
        message = event
        if data is not None:
            try:
                if isinstance(data, dict):
                    payload_dict = data
                    message = str(
                        data.get("message")
                        or data.get("text")
                        or data.get("status")
                        or event
                    )
                else:
                    payload_dict = {"value": _json_safe(data)}
                    message = str(data)
            except Exception:
                payload_dict = {"value": str(data)}
        record_event(run_id, event, message, payload_dict)

    return StreamEmitter(_publish)


def update_run_status(run_id: str, status: str, summary: Optional[str] = None, vm_id: Optional[str] = None):
    db = SessionLocal()
    try:
        db.execute(
            text(
                """
                UPDATE workflow_runs
                SET status = :status,
                    summary = COALESCE(:summary, summary),
                    vm_id = COALESCE(:vm_id, vm_id),
                    ended_at = CASE WHEN :terminal THEN NOW() ELSE ended_at END,
                    updated_at = NOW()
                WHERE id = :run_id
                """
            ),
            {
                "status": status,
                "summary": summary,
                "vm_id": vm_id,
                "run_id": run_id,
                "terminal": status in {"success", "error", "attention", "cancelled"},
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def heartbeat(run_id: str):
    db = SessionLocal()
    try:
        db.execute(
            text(
                "UPDATE workflow_runs SET last_heartbeat_at = NOW(), updated_at = NOW() WHERE id = :run_id"
            ),
            {"run_id": run_id},
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def fetch_workflow(workflow_id: str) -> Dict[str, Any]:
    client = get_service_supabase_client()
    res = client.table("workflows").select("id,name,prompt,definition_json,user_id").eq("id", workflow_id).single().execute()
    if not res.data:
        raise RuntimeError("workflow_not_found")
    return res.data


def _build_controller(controller_base_url: str) -> Dict[str, Any]:
    parsed = urlparse(controller_base_url)
    host = parsed.hostname
    port = parsed.port or settings.AGENT_CONTROLLER_PORT
    return {"base_url": controller_base_url, "host": host, "port": port}


async def run_once(claimed_by: str = "worker") -> bool:
    claim = claim_next_run(claimed_by)
    if not claim:
        return False

    run_id = claim["id"]
    workflow_id = claim["workflow_id"]
    user_id = claim["user_id"]

    record_event(run_id, "system", "Run claimed", {"claimed_by": claimed_by})

    # Fetch workflow definition
    wf = fetch_workflow(workflow_id)
    composed_plan = wf.get("definition_json") or {}
    task_prompt = wf.get("prompt") or wf.get("name") or "task"

    # Provision VM per run
    try:
        record_event(run_id, "system", "Provisioning VM")
        instance_id, controller_base_url, vnc_url = create_agent_instance_for_user(str(user_id))
        controller = _build_controller(controller_base_url)
        endpoint = {"controller_base_url": controller_base_url, "vnc_url": vnc_url, **controller}
        spec = {"instance_type": settings.AGENT_INSTANCE_TYPE, "region": settings.AWS_REGION}
        vm_id = str(uuid.uuid4())

        db = SessionLocal()
        try:
            db.execute(
                text(
                    """
                    INSERT INTO vm_instances (id, run_id, status, provider, spec, endpoint, created_at)
                    VALUES (:id, :run_id, :status, :provider, :spec, :endpoint, NOW())
                    """
                ),
                {
                    "id": vm_id,
                    "run_id": run_id,
                    "status": "ready",
                    "provider": "aws",
                    "spec": json.dumps(spec),
                    "endpoint": json.dumps(endpoint),
                },
            )
            db.execute(
                text(
                    """
                    UPDATE workflow_runs
                    SET vm_id = :vm_id, environment = :env, updated_at = NOW()
                    WHERE id = :run_id
                    """
                ),
                {"vm_id": vm_id, "env": json.dumps({"endpoint": endpoint}), "run_id": run_id},
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    except Exception as exc:
        record_event(run_id, "error", "VM provisioning failed", {"error": str(exc)})
        update_run_status(run_id, "error", summary="vm provisioning failed")
        return True

    # Build orchestrate request
    orch_request = OrchestrateRequest(
        task=task_prompt,
        worker=WorkerConfig.from_dict({}),
        grounding=GroundingConfig.from_dict({}),
        controller=ControllerConfig.from_dict(controller),
    )
    setattr(orch_request, "composed_plan", composed_plan)

    # Heartbeat loop
    async def _heartbeat_loop():
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            heartbeat(run_id)

    import asyncio

    hb_task = asyncio.create_task(_heartbeat_loop())
    emitter_token = None
    emitter = _build_run_emitter(run_id)

    try:
        record_event(run_id, "execution", "Run started")
        # Attach emitter so orchestrator stream events land in run_events
        emitter_token = set_current_emitter(emitter)
        orch_req = orchestrate_to_orchestrator(
            orch_request,
            user_id=user_id,
            workspace={"controller_base_url": controller_base_url, "vnc_url": vnc_url, "id": vm_id},
        )
        runtime = OrchestratorRuntime()
        result = await runtime.run_task(orch_req)
        summary = "; ".join([r.final_summary or "" for r in result.results if hasattr(r, "final_summary")])
        status = "success" if all(r.success for r in result.results) else "error"
        update_run_status(run_id, status, summary=summary, vm_id=vm_id)
        record_event(run_id, "execution", "Run completed", {"status": status})
    except Exception as exc:  # pragma: no cover
        logger.exception("Run failed: %s", exc)
        update_run_status(run_id, "error", summary=str(exc), vm_id=vm_id)
        record_event(run_id, "error", "Run failed", {"error": str(exc)})
    finally:
        if emitter_token:
            with contextlib.suppress(Exception):
                reset_current_emitter(emitter_token)
        hb_task.cancel()
        with contextlib.suppress(Exception, asyncio.CancelledError):
            await hb_task

        # Leave VM running for inspection per requirement
        try:
            update_vm_status(vm_id, "ready")
        except Exception:
            pass

    return True


async def worker_loop():
    """
    Simple loop to process queued runs.
    """
    import asyncio

    while True:
        processed = await run_once()
        if not processed:
            await asyncio.sleep(2)


if __name__ == "__main__":  # pragma: no cover
    import asyncio

    logging.basicConfig(level=logging.INFO)
    asyncio.run(worker_loop())
