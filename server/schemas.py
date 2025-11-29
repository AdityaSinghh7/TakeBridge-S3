# server/schemas.py

from pydantic import BaseModel
from typing import Any, List, Optional
from datetime import datetime


class RunTaskRequest(BaseModel):
    task: str
    # user_id removed - now extracted from JWT token via get_current_user


class RunnerResult(BaseModel):
    task: str
    status: str
    completion_reason: str
    steps: List[Any]
    grounding_prompts: Optional[Any] = None


class WorkspaceOut(BaseModel):
    """Workspace output schema for API responses."""
    id: str
    user_id: str
    status: str
    controller_base_url: str
    vnc_url: Optional[str] = None
    vm_instance_id: Optional[str] = None
    cloud_region: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None

    class Config:
        from_attributes = True

