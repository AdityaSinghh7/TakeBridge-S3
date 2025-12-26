from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from shared.db.sql import execute_text


def insert_vm_instance(
    db: Session,
    *,
    vm_id: str,
    run_id: str,
    status: str,
    provider: str | None,
    spec: Any | None,
    endpoint: Any | None,
) -> None:
    spec_json = json.dumps(spec) if isinstance(spec, (dict, list)) else spec
    endpoint_json = json.dumps(endpoint) if isinstance(endpoint, (dict, list)) else endpoint
    execute_text(
        db,
        """
        INSERT INTO vm_instances (id, run_id, status, provider, spec, endpoint, created_at)
        VALUES (:id, :run_id, :status, :provider, :spec, :endpoint, NOW())
        """,
        {
            "id": vm_id,
            "run_id": run_id,
            "status": status,
            "provider": provider,
            "spec": spec_json,
            "endpoint": endpoint_json,
        },
    )


__all__ = ["insert_vm_instance"]
