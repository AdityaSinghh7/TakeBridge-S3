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
