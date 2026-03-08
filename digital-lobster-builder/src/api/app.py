from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from fastapi import FastAPI

from src.api.routes import configure_routes, router
from src.orchestrator.pipeline import PipelineOrchestrator
from src.storage.spaces import SpacesClient

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"
REQUIRED_ENV_VARS = (
    "GRADIENT_API_KEY",
    "DO_SPACES_KEY",
    "DO_SPACES_SECRET",
    "DO_SPACES_REGION",
    "DO_SPACES_INGESTION_BUCKET",
    "DO_SPACES_ARTIFACTS_BUCKET",
)

@dataclass(frozen=True, slots=True)
class BuilderRuntimeSettings:
    gradient_api_key: str
    spaces_key: str
    spaces_secret: str
    spaces_region: str
    ingestion_bucket: str
    artifacts_bucket: str

def create_app(
    spaces_client: SpacesClient | None = None,
    orchestrator: PipelineOrchestrator | None = None,
    ingestion_bucket: str = "",
    artifacts_bucket: str = "",
) -> FastAPI:
    """Build and return the FastAPI application.

    Args:
        spaces_client: DigitalOcean Spaces client instance.
        orchestrator: Pipeline orchestrator instance.
        ingestion_bucket: Name of the Spaces ingestion bucket.
        artifacts_bucket: Name of the Spaces artifacts bucket.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(title="Astro Agentic Builder", version="0.1.0")

    # Always configure route globals to avoid stale state across app instances.
    configure_routes(
        spaces_client=spaces_client,
        orchestrator=orchestrator,
        ingestion_bucket=ingestion_bucket,
        artifacts_bucket=artifacts_bucket,
    )

    app.include_router(router)

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return app

def _load_env_file(env_file: str | Path = DEFAULT_ENV_FILE) -> None:
    """Load a local .env file without overriding already-set environment values."""
    env_path = Path(env_file)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()

        key, separator, value = line.partition("=")
        if not separator:
            continue

        key = key.strip()
        if not key:
            continue

        value = value.strip()
        if value and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]

        os.environ.setdefault(key, value)

def _read_settings(env: Mapping[str, str]) -> BuilderRuntimeSettings | None:
    """Return runtime settings when all required variables are available."""
    missing = [
        name for name in REQUIRED_ENV_VARS if not str(env.get(name, "")).strip()
    ]
    if missing:
        logger.info(
            "Builder app not fully configured; missing env vars: %s",
            ", ".join(missing),
        )
        return None

    return BuilderRuntimeSettings(
        gradient_api_key=str(env["GRADIENT_API_KEY"]).strip(),
        spaces_key=str(env["DO_SPACES_KEY"]).strip(),
        spaces_secret=str(env["DO_SPACES_SECRET"]).strip(),
        spaces_region=str(env["DO_SPACES_REGION"]).strip(),
        ingestion_bucket=str(env["DO_SPACES_INGESTION_BUCKET"]).strip(),
        artifacts_bucket=str(env["DO_SPACES_ARTIFACTS_BUCKET"]).strip(),
    )

def _build_runtime_dependencies(
    settings: BuilderRuntimeSettings,
) -> tuple[SpacesClient, PipelineOrchestrator, str, str]:
    """Construct runtime dependencies for the module-level builder app."""
    from src.gradient.client import GradientClient
    from src.gradient.knowledge_base import KnowledgeBaseClient
    from src.gradient.tracing import Tracer

    spaces_client = SpacesClient(
        access_key=settings.spaces_key,
        secret_key=settings.spaces_secret,
        region=settings.spaces_region,
    )
    orchestrator = PipelineOrchestrator(
        gradient_client=GradientClient(api_key=settings.gradient_api_key),
        kb_client=KnowledgeBaseClient(api_key=settings.gradient_api_key),
        spaces_client=spaces_client,
        tracer=Tracer(run_id="app-bootstrap"),
        artifacts_bucket=settings.artifacts_bucket,
        ingestion_bucket=settings.ingestion_bucket,
    )
    return (
        spaces_client,
        orchestrator,
        settings.ingestion_bucket,
        settings.artifacts_bucket,
    )

def create_app_from_env(
    *,
    env: Mapping[str, str] | None = None,
    env_file: str | Path = DEFAULT_ENV_FILE,
    raise_on_error: bool = False,
) -> FastAPI:
    """Build an app using environment variables from the process or local .env."""
    if env is None:
        _load_env_file(env_file)
        env = os.environ

    settings = _read_settings(env)
    if settings is None:
        return create_app()

    try:
        spaces_client, orchestrator, ingestion_bucket, artifacts_bucket = (
            _build_runtime_dependencies(settings)
        )
    except Exception:
        if raise_on_error:
            raise
        logger.exception("Failed to configure builder app from environment")
        return create_app()

    return create_app(
        spaces_client=spaces_client,
        orchestrator=orchestrator,
        ingestion_bucket=ingestion_bucket,
        artifacts_bucket=artifacts_bucket,
    )

app = create_app_from_env()
