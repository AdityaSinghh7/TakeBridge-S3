from __future__ import annotations
from sqlalchemy import (
    Column, String, Text, Integer, BigInteger, ForeignKey,
    DateTime, func, UniqueConstraint, JSON
)
from sqlalchemy.orm import declarative_base, relationship
import os

Base = declarative_base()
IS_PG = os.getenv("DB_URL","").startswith("postgres")

# JSON column: JSONB on PG, JSON on SQLite
if IS_PG:
    from sqlalchemy.dialects.postgresql import JSONB as JSONType
else:
    JSONType = JSON

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)  # Historically "singleton" in dev; now per-user ids.
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    accounts = relationship("ConnectedAccount", back_populates="user", cascade="all,delete-orphan")

class AuthConfig(Base):
    __tablename__ = "auth_configs"
    id = Column(String, primary_key=True)          # ac_...
    provider = Column(String, nullable=False)      # "gmail"|"slack"
    name = Column(Text)

    accounts = relationship("ConnectedAccount", back_populates="auth_config")

class ConnectedAccount(Base):
    __tablename__ = "connected_accounts"
    id = Column(String, primary_key=True)          # ca_...
    user_id = Column(String, ForeignKey("users.id", ondelete="cascade"), nullable=False)
    auth_config_id = Column(String, ForeignKey("auth_configs.id"), nullable=False)
    provider = Column(String, nullable=False)
    status = Column(String, nullable=False)        # ACTIVE|INITIATED|...
    provider_uid = Column(String)                  # email or slack team id
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", back_populates="accounts")
    auth_config = relationship("AuthConfig", back_populates="accounts")
    mcp_connections = relationship("MCPConnection", back_populates="connected_account", cascade="all,delete-orphan")

    __table_args__ = (
        UniqueConstraint("user_id", "auth_config_id", name="uq_user_authconfig"),
    )

class MCPConnection(Base):
    __tablename__ = "mcp_connections"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    connected_account_id = Column(String, ForeignKey("connected_accounts.id", ondelete="cascade"), nullable=False)
    mcp_url = Column(Text)
    headers_json = Column(JSONType, server_default="{}", nullable=False)
    last_synced_at = Column(DateTime(timezone=True))
    last_error = Column(Text)

    connected_account = relationship("ConnectedAccount", back_populates="mcp_connections")
