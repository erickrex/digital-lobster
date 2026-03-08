from __future__ import annotations

from pydantic import BaseModel

from src.models.cms_config import CMSConfig


class PresignRequest(BaseModel):
    """Request body for generating a presigned upload URL."""

    filename: str


class PresignResponse(BaseModel):
    """Response body with presigned URL and bundle key."""

    upload_url: str
    bundle_key: str


class MigrationRequest(BaseModel):
    """Request body for triggering a new migration run."""

    bundle_key: str
    cms_mode: bool = False
    cms_config: CMSConfig | None = None


class MigrationResponse(BaseModel):
    """Response body after triggering a migration run."""

    run_id: str
    status: str


class MigrationStatus(BaseModel):
    """Response body for migration run status."""

    run_id: str
    status: str
    current_agent: str | None
    warnings: list[str]
    error: dict | None
    started_at: str
    completed_at: str | None
    agent_durations: dict[str, float]


class ArtifactListResponse(BaseModel):
    """Response body listing artifacts for a run."""

    run_id: str
    artifacts: list[str]
