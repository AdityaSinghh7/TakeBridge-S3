"""
MCP (Model Context Protocol) client wrapper.

Purpose
- Connect/register with MCP servers.
- Discover capabilities: tools, resources, prompts.
- Invoke tools and actions; fetch resources and exchange messages.
- Support streaming, errors with context, timeouts/retries where needed.
- Be transport-agnostic (e.g., stdio/WebSocket) with optional auth hooks.

Intended API (sketch)
- Lifecycle: `MCPClient(...)`, `connect()`, `close()`, `session()`.
- Discovery: `list_tools()`, `list_resources()`, `list_prompts()`.
- Ops: `call_tool(name, params)`, `read_resource(uri)`.

Implementation to follow; keep this summary aligned as features land.
"""

import asyncio
import logging
from typing import Any, Dict, Optional, List
from mcp import ClientSession
from dotenv import load_dotenv
from mcp.client.streamable_http import streamablehttp_client

load_dotenv()

logger = logging.getLogger("mcp.client")

class MCPClient:
    def __init__(self, base_url: str, headers: Optional[Dict[str, str]] = None):
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}
        try:
            # Redact sensitive headers for logs
            red = {}
            for k, v in (self.headers or {}).items():
                kl = k.lower()
                if kl == "authorization" and isinstance(v, str):
                    red[k] = v.split(" ")[0] + " *****"
                elif kl in ("x-api-key", "x-api-key".lower()) and isinstance(v, str):
                    red[k] = v[:4] + "*****"
                else:
                    red[k] = v
            logger.info("MCPClient init url=%s headers=%s", self.base_url, red)
        except Exception:
            pass

    async def _acall(self, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        async with streamablehttp_client(self.base_url, headers=self.headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                # Optional: validate tool exists
                tools_resp = await session.list_tools()
                tool_names = {t.name for t in tools_resp.tools}
                if tool not in tool_names:
                    return {"status": "error", "error": f"tool {tool} not found", "tools": sorted(tool_names)}
                result = await session.call_tool(tool, arguments=args)
                # result contains structured content (texts/json); return a simple dict
                return {"status": "success", "result": result.model_dump()}
    
    def call(self, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        return asyncio.run(self._acall(tool, args))

    async def _alist_tools(self) -> List[str]:
        async with streamablehttp_client(self.base_url, headers=self.headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_resp = await session.list_tools()
                return sorted([t.name for t in tools_resp.tools])

    def list_tools(self) -> List[str]:
        return asyncio.run(self._alist_tools())
