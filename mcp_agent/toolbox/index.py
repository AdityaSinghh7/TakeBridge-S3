from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from .models import ToolboxManifest, ProviderSpec, ToolSpec


@dataclass
class ToolboxIndex:
    """Lightweight index over a ToolboxManifest for fast lookup."""

    providers: Dict[str, ProviderSpec]
    tools_by_id: Dict[str, ToolSpec]

    @classmethod
    def from_manifest(cls, manifest: ToolboxManifest) -> "ToolboxIndex":
        providers_map = manifest.provider_map()
        tools_by_id: Dict[str, ToolSpec] = {}
        for provider in manifest.providers:
            for tool in provider.actions:
                tools_by_id[tool.tool_id] = tool
        return cls(providers=providers_map, tools_by_id=tools_by_id)

    def get_tool(self, tool_id: str) -> ToolSpec | None:
        return self.tools_by_id.get(tool_id)

