from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime

class MCPConnectionOut(BaseModel):
    id: int
    connected_account_id: str
    mcp_url: Optional[str]
    headers_json: Dict[str, Any] = {}
    last_synced_at: Optional[datetime]
    last_error: Optional[str]

    class Config:
        from_attributes = True

class WorkspaceOut(BaseModel):
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
