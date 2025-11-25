from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np

from .types import ToolboxManifest, ProviderSpec, ToolSpec


def _build_tool_text(tool: ToolSpec) -> str:
    """Construct searchable text representation for a tool with weighted fields.

    Combines tool metadata fields into a single searchable string.
    Important fields are weighted more heavily by repetition to improve
    embedding quality and semantic matching.

    Args:
        tool: ToolSpec to build text representation for.

    Returns:
        Combined text string for embedding with weighted fields.
    """
    parts: list[str] = []

    # Tool name appears 3x (most important - exact matches are critical)
    if tool.name:
        parts.extend([tool.name] * 3)

    # Provider appears 2x (important for provider filtering)
    if tool.provider:
        parts.extend([tool.provider] * 2)

    # Description appears 1x (contextual information)
    if tool.description:
        parts.append(tool.description)
    if tool.short_description and tool.short_description != tool.description:
        parts.append(tool.short_description)

    # Secondary fields appear 1x
    if tool.docstring:
        parts.append(tool.docstring)
    if tool.mcp_tool_name:
        parts.append(tool.mcp_tool_name)

    # Parameter names appear 1x each (helpful for semantic matching)
    param_names = [param.name for param in tool.parameters]
    if param_names:
        parts.extend(param_names)

    return " ".join(parts)


@dataclass
class ToolboxIndex:
    """Lightweight index over a ToolboxManifest for fast lookup with semantic search support."""

    providers: Dict[str, ProviderSpec]
    tools_by_id: Dict[str, ToolSpec]
    tool_embeddings: Dict[str, np.ndarray] = field(default_factory=dict)
    query_embedding_cache: Dict[str, np.ndarray] = field(default_factory=dict)

    @classmethod
    def from_manifest(cls, manifest: ToolboxManifest) -> "ToolboxIndex":
        """Build index from manifest, including pre-computed tool embeddings.

        Args:
            manifest: ToolboxManifest to build index from.

        Returns:
            ToolboxIndex with embeddings pre-computed.
        """
        from .embeddings import get_embedding_service

        providers_map = manifest.provider_map()
        tools_by_id: Dict[str, ToolSpec] = {}
        tool_texts: list[str] = []
        tool_ids: list[str] = []

        # Collect all tools and their text representations
        for provider in manifest.providers:
            for tool in provider.actions:
                tools_by_id[tool.tool_id] = tool
                tool_texts.append(_build_tool_text(tool))
                tool_ids.append(tool.tool_id)

        # Generate embeddings in batch for efficiency
        embedding_service = get_embedding_service()
        tool_embeddings: Dict[str, np.ndarray] = {}

        if tool_texts:
            batch_embeddings = embedding_service.embed_batch(tool_texts)
            if batch_embeddings is not None:
                for tool_id, embedding in zip(tool_ids, batch_embeddings):
                    tool_embeddings[tool_id] = embedding
            else:
                # Fallback: generate embeddings one by one if batch fails
                for tool_id, tool_text in zip(tool_ids, tool_texts):
                    embedding = embedding_service.embed_text(tool_text)
                    if embedding is not None:
                        tool_embeddings[tool_id] = embedding

        return cls(
            providers=providers_map,
            tools_by_id=tools_by_id,
            tool_embeddings=tool_embeddings,
            query_embedding_cache={},
        )

    def get_tool(self, tool_id: str) -> ToolSpec | None:
        """Get tool by ID."""
        return self.tools_by_id.get(tool_id)

    def get_tool_embedding(self, tool_id: str) -> Optional[np.ndarray]:
        """Get pre-computed embedding for a tool.

        Args:
            tool_id: Tool identifier.

        Returns:
            Embedding vector or None if not found.
        """
        return self.tool_embeddings.get(tool_id)

    def get_query_embedding(self, query: str) -> Optional[np.ndarray]:
        """Get cached query embedding or generate and cache it.

        Args:
            query: Query string (should be normalized).

        Returns:
            Embedding vector or None if generation failed.
        """
        if query in self.query_embedding_cache:
            return self.query_embedding_cache[query]

        from .embeddings import get_embedding_service

        embedding_service = get_embedding_service()
        embedding = embedding_service.embed_text(query)
        if embedding is not None:
            self.query_embedding_cache[query] = embedding
        return embedding

