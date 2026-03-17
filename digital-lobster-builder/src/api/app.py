from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

# Configure logging before anything else so all module-level loggers
# (src.gradient_sdk, src.agents, etc.) emit to stderr.
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("gradient._base_client").setLevel(logging.WARNING)

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.api.routes import configure_routes, router
from src.api.ui_routes import configure_ui_routes, register_ui_exception_handlers, root_page, ui_router
from src.orchestrator.pipeline import PipelineOrchestrator
from src.storage.local_upload import LocalUploadStore
from src.storage.spaces import SpacesClient

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
API_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = API_DIR / "templates"
STATIC_DIR = API_DIR / "static"
DEFAULT_UPLOAD_DIR = PROJECT_ROOT / "uploads"
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"
DEFAULT_GRADIENT_MODEL = "anthropic-claude-4.6-sonnet"
MODEL_ACCESS_KEY_ENV = "GRADIENT_MODEL_ACCESS_KEY"
LEGACY_MODEL_ACCESS_KEY_ENV = "GRADIENT_API_KEY"
DO_ACCESS_TOKEN_ENV = "DIGITALOCEAN_ACCESS_TOKEN"
REQUIRED_ENV_VARS = (
    "DO_SPACES_KEY",
    "DO_SPACES_SECRET",
    "DO_SPACES_REGION",
    "DO_SPACES_INGESTION_BUCKET",
    "DO_SPACES_ARTIFACTS_BUCKET",
)

@dataclass(frozen=True, slots=True)
class BuilderRuntimeSettings:
    gradient_model_access_key: str
    gradient_model_id: str
    do_access_token: str
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

    # UI routes (HTMX frontend)
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    upload_store = LocalUploadStore(upload_dir=DEFAULT_UPLOAD_DIR)
    configure_ui_routes(templates=templates, upload_store=upload_store)
    app.include_router(ui_router)
    app.add_api_route("/", root_page, methods=["GET"])
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    register_ui_exception_handlers(app)

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
    gradient_model_access_key = _first_non_empty(
        env,
        MODEL_ACCESS_KEY_ENV,
        LEGACY_MODEL_ACCESS_KEY_ENV,
    )
    do_access_token = _first_non_empty(env, DO_ACCESS_TOKEN_ENV)
    missing = [
        name for name in REQUIRED_ENV_VARS if not str(env.get(name, "")).strip()
    ]
    if not gradient_model_access_key:
        missing.append(
            f"{MODEL_ACCESS_KEY_ENV} (or legacy {LEGACY_MODEL_ACCESS_KEY_ENV})"
        )
    if not do_access_token:
        missing.append(DO_ACCESS_TOKEN_ENV)
    if missing:
        logger.info(
            "Builder app not fully configured; missing env vars: %s",
            ", ".join(missing),
        )
        return None

    return BuilderRuntimeSettings(
        gradient_model_access_key=gradient_model_access_key,
        gradient_model_id=(
            _first_non_empty(env, "GRADIENT_MODEL_ID") or DEFAULT_GRADIENT_MODEL
        ),
        do_access_token=do_access_token,
        spaces_key=str(env["DO_SPACES_KEY"]).strip(),
        spaces_secret=str(env["DO_SPACES_SECRET"]).strip(),
        spaces_region=str(env["DO_SPACES_REGION"]).strip(),
        ingestion_bucket=str(env["DO_SPACES_INGESTION_BUCKET"]).strip(),
        artifacts_bucket=str(env["DO_SPACES_ARTIFACTS_BUCKET"]).strip(),
    )

def _build_runtime_dependencies(
    settings: BuilderRuntimeSettings,
    upload_store: LocalUploadStore | None = None,
) -> tuple[SpacesClient, PipelineOrchestrator, str, str]:
    """Construct runtime dependencies for the module-level builder app."""
    from src.gradient_sdk.client import GradientClient
    from src.gradient_sdk.knowledge_base import KnowledgeBaseClient
    from src.gradient_sdk.tracing import Tracer

    spaces_client = SpacesClient(
        access_key=settings.spaces_key,
        secret_key=settings.spaces_secret,
        region=settings.spaces_region,
    )
    orchestrator = PipelineOrchestrator(
        gradient_client=GradientClient(
            model_access_key=settings.gradient_model_access_key,
            model=settings.gradient_model_id,
        ),
        kb_client=KnowledgeBaseClient(
            access_token=settings.do_access_token,
            region=os.environ.get("DO_KB_REGION", "").strip() or None,
            db_ready_timeout=float(os.environ.get("DO_KB_READY_TIMEOUT", "600")),
        ),
        spaces_client=spaces_client,
        tracer=Tracer(run_id="app-bootstrap"),
        artifacts_bucket=settings.artifacts_bucket,
        ingestion_bucket=settings.ingestion_bucket,
        upload_store=upload_store,
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
        upload_store = LocalUploadStore(upload_dir=DEFAULT_UPLOAD_DIR)
        spaces_client, orchestrator, ingestion_bucket, artifacts_bucket = (
            _build_runtime_dependencies(settings, upload_store=upload_store)
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

def _first_non_empty(env: Mapping[str, str], *keys: str) -> str:
    """Return the first non-blank value for the given environment keys."""
    for key in keys:
        value = str(env.get(key, "")).strip()
        if value:
            return value
    return ""


app = create_app_from_env()
