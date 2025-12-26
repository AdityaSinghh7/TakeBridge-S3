from __future__ import annotations

import os

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()
IS_PG = os.getenv("DB_URL", "").startswith("postgres")

# JSON column: JSONB on PG, JSON on SQLite
if IS_PG:
    from sqlalchemy.dialects.postgresql import JSONB as JSONType
else:
    JSONType = JSON


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(String, primary_key=True)
    name = Column(Text)
    avatar_url = Column(Text)
    credits = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Folder(Base):
    __tablename__ = "folders"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("profiles.id", ondelete="cascade"), nullable=False)
    name = Column(Text, nullable=False)
    position = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("profiles.id", ondelete="cascade"), nullable=False)
    folder_id = Column(String, ForeignKey("folders.id", ondelete="set null"))
    name = Column(Text, nullable=False)
    prompt = Column(Text)
    description = Column(Text)
    status = Column(String, nullable=False, server_default="draft")
    definition_json = Column(JSONType)
    metadata = Column(JSONType, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id = Column(String, primary_key=True)
    workflow_id = Column(String, ForeignKey("workflows.id", ondelete="cascade"), nullable=False)
    user_id = Column(String, ForeignKey("profiles.id", ondelete="cascade"), nullable=False)
    folder_id = Column(String)
    status = Column(String, nullable=False, server_default="queued")
    vm_id = Column(String)
    claimed_by = Column(String)
    summary = Column(Text)
    trigger_source = Column(String)
    metadata = Column(JSONType, nullable=False, server_default="{}")
    environment = Column(JSONType, nullable=False, server_default="{}")
    agent_states = Column(JSONType, nullable=False, server_default="{}")
    agent_states_updated_at = Column(DateTime(timezone=True))
    started_at = Column(DateTime(timezone=True))
    ended_at = Column(DateTime(timezone=True))
    last_heartbeat_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class RunEvent(Base):
    __tablename__ = "run_events"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("workflow_runs.id", ondelete="cascade"), nullable=False)
    ts = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    kind = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    payload = Column(JSONType, nullable=False, server_default="{}")
    step_id = Column(String)
    actor = Column(String)


class VMInstance(Base):
    __tablename__ = "vm_instances"

    id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("workflow_runs.id", ondelete="cascade"), nullable=False)
    status = Column(String, nullable=False)
    provider = Column(Text)
    spec = Column(JSONType)
    endpoint = Column(JSONType)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    terminated_at = Column(DateTime(timezone=True))
    stopped_at = Column(DateTime(timezone=True))


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(String, primary_key=True)
    # Canonical user ID: Supabase auth.users.id (UUID). Must be the same across all clients.
    user_id = Column(String, index=True, nullable=False)
    status = Column(String, default="running")  # "running", "stopped", "terminated", "creating"
    controller_base_url = Column(String, nullable=False)
    vnc_url = Column(String, nullable=True)
    # AWS EC2 instance details
    vm_instance_id = Column(String, nullable=True)
    cloud_region = Column(String, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
    )
    last_used_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class WorkflowFile(Base):
    __tablename__ = "workflow_files"

    id = Column(String, primary_key=True)
    workflow_id = Column(String, index=True, nullable=False)
    user_id = Column(String, index=True, nullable=False)
    source_type = Column(String, nullable=False, default="upload")
    storage_key = Column(Text, nullable=False)
    filename = Column(Text, nullable=False)
    content_type = Column(Text)
    size_bytes = Column(BigInteger)
    checksum = Column(String(128))
    status = Column(String, nullable=False, default="pending")
    metadata_json = Column(JSONType, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    run_files = relationship("WorkflowRunFile", back_populates="workflow_file")


class WorkflowRunFile(Base):
    __tablename__ = "workflow_run_files"

    id = Column(String, primary_key=True)
    run_id = Column(String, index=True, nullable=False)
    workflow_file_id = Column(String, ForeignKey("workflow_files.id", ondelete="SET NULL"))
    user_id = Column(String, index=True, nullable=False)
    source_type = Column(String, nullable=False, default="upload")
    storage_key = Column(Text, nullable=False)
    drive_path = Column(Text)
    r2_key = Column(Text)
    filename = Column(Text, nullable=False)
    content_type = Column(Text)
    size_bytes = Column(BigInteger)
    checksum = Column(String(128))
    status = Column(String, nullable=False, default="pending")
    vm_path = Column(Text)
    error = Column(Text)
    metadata_json = Column(JSONType, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    workflow_file = relationship("WorkflowFile", back_populates="run_files")


class WorkflowRunArtifact(Base):
    __tablename__ = "workflow_run_artifacts"

    id = Column(String, primary_key=True)
    run_id = Column(String, index=True, nullable=False)
    filename = Column(Text, nullable=False)
    storage_key = Column(Text, nullable=False)
    size_bytes = Column(BigInteger)
    content_type = Column(Text)
    checksum = Column(String(128))
    source_path = Column(Text)
    metadata_json = Column(JSONType, nullable=False, server_default="{}")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class WorkflowRunDriveChange(Base):
    __tablename__ = "workflow_run_drive_changes"

    id = Column(String, primary_key=True)
    run_id = Column(String, index=True, nullable=False)
    user_id = Column(String, index=True, nullable=False)
    path = Column(Text, nullable=False)
    r2_key = Column(Text, nullable=False)
    baseline_hash = Column(String(128))
    new_hash = Column(String(128))
    size_bytes = Column(BigInteger)
    content_type = Column(Text)
    status = Column(String, nullable=False, default="pending")
    committed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
