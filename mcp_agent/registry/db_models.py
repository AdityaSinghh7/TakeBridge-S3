"""Database models for MCP registry (migrated from shared/db/models.py).

These models are the source of truth for provider/tool metadata and OAuth state.
"""

from __future__ import annotations

import os

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# Use JSONB on PostgreSQL for better performance
IS_PG = os.getenv("DB_URL", "").startswith("postgres")

if IS_PG:
    from sqlalchemy.dialects.postgresql import JSONB as JSONType
    from sqlalchemy.dialects.postgresql import UUID as UUIDType
else:
    JSONType = JSON
    UUIDType = String


class User(Base):
    """
    User/tenant entity.
    
    In the multi-tenant model, user_id acts as the tenant identifier.
    """
    __tablename__ = "users"
    
    id = Column(UUIDType(as_uuid=True) if IS_PG else UUIDType, primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    metadata_json = Column("metadata", JSONType, nullable=False, server_default="{}")
    
    # Relationships
    accounts = relationship("ConnectedAccount", back_populates="user", cascade="all,delete-orphan")


class AuthConfig(Base):
    """
    OAuth configuration for a provider.
    
    Maps to Composio auth config IDs (ac_...).
    """
    __tablename__ = "auth_configs"
    
    id = Column(String, primary_key=True)  # ac_...
    provider = Column(String, nullable=False)  # "gmail" | "slack"
    name = Column(Text)
    
    # Relationships
    accounts = relationship("ConnectedAccount", back_populates="auth_config")


class ConnectedAccount(Base):
    """
    OAuth connection between a user and a provider via an auth config.
    
    Maps to Composio connected account IDs (ca_...).
    Enforces unique (user_id, auth_config_id) constraint.
    """
    __tablename__ = "connected_accounts"
    
    id = Column(String, primary_key=True)  # ca_...
    user_id = Column(UUIDType(as_uuid=True) if IS_PG else UUIDType, ForeignKey("users.id", ondelete="cascade"), nullable=False)
    auth_config_id = Column(String, ForeignKey("auth_configs.id"), nullable=False)
    provider = Column(String, nullable=False)  # "gmail" | "slack"
    status = Column(String, nullable=False)  # "ACTIVE" | "INITIATED" | "DISCONNECTED"
    provider_uid = Column(String)  # email or Slack team ID
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="accounts")
    auth_config = relationship("AuthConfig", back_populates="accounts")
    mcp_connections = relationship("MCPConnection", back_populates="connected_account", cascade="all,delete-orphan")
    
    __table_args__ = (
        UniqueConstraint("user_id", "auth_config_id", name="uq_user_authconfig"),
    )


class MCPConnection(Base):
    """
    MCP server connection details for a connected account.
    
    Stores the MCP HTTP URL and headers (including auth tokens).
    """
    __tablename__ = "mcp_connections"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    connected_account_id = Column(String, ForeignKey("connected_accounts.id", ondelete="cascade"), nullable=False)
    mcp_url = Column(Text)
    headers_json = Column(JSONType, server_default="{}", nullable=False)
    last_synced_at = Column(DateTime(timezone=True))
    last_error = Column(Text)
    
    # Relationships
    connected_account = relationship("ConnectedAccount", back_populates="mcp_connections")
