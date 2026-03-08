from __future__ import annotations

from fastapi import FastAPI

from src.api.routes import configure_routes, router
from src.orchestrator.pipeline import PipelineOrchestrator
from src.storage.spaces import SpacesClient


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
