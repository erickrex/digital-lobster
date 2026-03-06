"""Pipeline API endpoints.

Provides routes for presigned upload URLs, migration triggering,
status polling, and artifact retrieval.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Response

from src.api.schemas import (
    ArtifactListResponse,
    MigrationRequest,
    MigrationResponse,
    MigrationStatus,
    PresignRequest,
    PresignResponse,
)
from src.models.cms_config import CMSConfig
from src.orchestrator.pipeline import PipelineOrchestrator
from src.orchestrator.state import PipelineRunState
from src.storage.spaces import SpacesClient

router = APIRouter()

# In-memory run state store (keyed by run_id)
_run_states: dict[str, PipelineRunState] = {}

# These are set by the app factory via ``configure_routes``
_spaces_client: SpacesClient | None = None
_orchestrator: PipelineOrchestrator | None = None
_ingestion_bucket: str = ""
_artifacts_bucket: str = ""


def configure_routes(
    spaces_client: SpacesClient | None,
    orchestrator: PipelineOrchestrator | None,
    ingestion_bucket: str,
    artifacts_bucket: str,
) -> None:
    """Inject dependencies into the router module."""
    global _spaces_client, _orchestrator, _ingestion_bucket, _artifacts_bucket
    _spaces_client = spaces_client
    _orchestrator = orchestrator
    _ingestion_bucket = ingestion_bucket
    _artifacts_bucket = artifacts_bucket


def get_run_states() -> dict[str, PipelineRunState]:
    """Expose run states dict for testing."""
    return _run_states


def _require_spaces_client() -> SpacesClient:
    if _spaces_client is None:
        raise HTTPException(
            status_code=503,
            detail="Spaces storage client is not configured",
        )
    return _spaces_client


def _require_orchestrator() -> PipelineOrchestrator:
    if _orchestrator is None:
        raise HTTPException(
            status_code=503,
            detail="Pipeline orchestrator is not configured",
        )
    return _orchestrator


async def _run_pipeline(
    run_id: str,
    bundle_key: str,
    cms_mode: bool = False,
    cms_config: Any | None = None,
) -> None:
    """Background task that executes the pipeline and updates state."""
    state = _run_states.get(run_id)
    if state is None:
        state = PipelineRunState.create(run_id=run_id, bundle_key=bundle_key)

    try:
        orchestrator = _require_orchestrator()
        final_state = await orchestrator.run(
            bundle_key, run_id, cms_mode=cms_mode, cms_config=cms_config
        )
        _run_states[run_id] = final_state
    except Exception as exc:
        state.mark_failed("pipeline", exc)
        _run_states[run_id] = state


@router.post("/uploads/presign", response_model=PresignResponse)
async def presign_upload(request: PresignRequest) -> PresignResponse:
    """Generate a presigned URL for bundle upload to Spaces."""
    spaces_client = _require_spaces_client()
    bundle_key = f"uploads/{uuid.uuid4().hex}/{request.filename}"
    upload_url = spaces_client.generate_presigned_upload_url(
        key=bundle_key, bucket=_ingestion_bucket
    )
    return PresignResponse(upload_url=upload_url, bundle_key=bundle_key)


def _validate_cms_config(config: CMSConfig) -> list[str]:
    """Return names of required CMS credential fields that are missing or empty."""
    missing: list[str] = []
    # Plain string fields that must be non-empty
    for field_name in (
        "domain_name",
        "ssh_public_key",
        "ssh_private_key_path",
        "strapi_admin_email",
    ):
        value = getattr(config, field_name, None)
        if not value or not str(value).strip():
            missing.append(field_name)
    # SecretStr fields that must have non-empty secret values
    for field_name in ("do_token", "strapi_admin_password"):
        secret = getattr(config, field_name, None)
        if secret is None or not secret.get_secret_value().strip():
            missing.append(field_name)
    return missing


@router.post("/migrations", response_model=MigrationResponse)
async def trigger_migration(
    request: MigrationRequest, background_tasks: BackgroundTasks
) -> MigrationResponse:
    """Trigger a new migration run as a background task."""
    # --- CMS mode validation ---
    if request.cms_mode:
        if request.cms_config is None:
            raise HTTPException(
                status_code=422,
                detail="cms_config is required when cms_mode is enabled",
            )
        missing_fields = _validate_cms_config(request.cms_config)
        if missing_fields:
            raise HTTPException(
                status_code=422,
                detail=f"Missing required CMS credential fields: {', '.join(missing_fields)}",
            )

    run_id = uuid.uuid4().hex
    # Create initial pending state
    state = PipelineRunState.create(run_id=run_id, bundle_key=request.bundle_key)
    _run_states[run_id] = state
    background_tasks.add_task(
        _run_pipeline,
        run_id,
        request.bundle_key,
        cms_mode=request.cms_mode,
        cms_config=request.cms_config,
    )
    return MigrationResponse(run_id=run_id, status=state.status)


@router.get("/migrations/{run_id}", response_model=MigrationStatus)
async def get_migration_status(run_id: str) -> MigrationStatus:
    """Get run status and progress."""
    state = _run_states.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return MigrationStatus(
        run_id=state.run_id,
        status=state.status,
        current_agent=state.current_agent,
        warnings=state.warnings,
        error=state.error,
        started_at=state.started_at,
        completed_at=state.completed_at,
        agent_durations=state.agent_durations,
    )


@router.get("/migrations/{run_id}/artifacts", response_model=ArtifactListResponse)
async def list_artifacts(run_id: str) -> ArtifactListResponse:
    """List output artifact names from run state."""
    state = _run_states.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return ArtifactListResponse(
        run_id=state.run_id,
        artifacts=list(state.artifacts.keys()),
    )


@router.get("/migrations/{run_id}/artifacts/{name}")
async def download_artifact(run_id: str, name: str) -> Response:
    """Download a specific artifact from Spaces."""
    spaces_client = _require_spaces_client()
    state = _run_states.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if name not in state.artifacts:
        raise HTTPException(status_code=404, detail="Artifact not found")
    key = f"{run_id}/{name}"
    data = await spaces_client.download(_artifacts_bucket, key)
    return Response(content=data, media_type="application/octet-stream")
