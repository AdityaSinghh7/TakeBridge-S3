"""AgentContext: Multi-tenant context for MCP operations.

Eliminates global state by passing context explicitly through all operations.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generator

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from mcp_agent.user_identity import normalize_user_id


@dataclass
class AgentContext:
    """
    Multi-tenant context for MCP agent operations.
    
    This replaces global lookups like TB_USER_ID and per-user registries.
    Every operation receives an AgentContext as its first parameter.
    
    Fields:
        user_id: Tenant/account identifier (normalized)
        request_id: Unique identifier for this request/operation
        db_session: Optional SQLAlchemy session (lazy-loaded via get_db())
        extra: Dictionary for additional context data
    """
    
    user_id: str
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    db_session: Session | None = field(default=None, repr=False)
    extra: dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Normalize user_id on initialization."""
        self.user_id = normalize_user_id(self.user_id)
    
    @contextmanager
    def get_db(self) -> Generator[Session, None, None]:
        """
        Get or create a database session for this context.
        
        If db_session is already set, yields it directly.
        Otherwise, creates a new scoped session.
        
        Yields:
            SQLAlchemy Session
        """
        if self.db_session is not None:
            # Reuse existing session (caller manages lifecycle)
            yield self.db_session
        else:
            # Create new scoped session
            from shared.db.engine import session_scope
            
            with session_scope() as session:
                yield session
    
    @classmethod
    def create(cls, user_id: str, **kwargs) -> AgentContext:
        """
        Factory method to create an AgentContext.
        
        Args:
            user_id: Tenant/account identifier
            **kwargs: Additional fields (request_id, extra)
        
        Returns:
            Initialized AgentContext
        """
        return cls(user_id=user_id, **kwargs)

