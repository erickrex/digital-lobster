"""HTMX UI routes for the migration frontend.

All endpoints live under ``/ui/`` and return HTML fragments rendered via
Jinja2 templates.  Dependencies are injected at startup through
:func:`configure_ui_routes`, following the same pattern as
:func:`routes.configure_routes`.
"""

from __future__ import annotations

import io
import json
import logging
import uuid
import zipfile

from fastapi import APIRouter, BackgroundTasks, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates

from src.api.routes import _run_pipeline, _run_states
from src.orchestrator.state import PipelineRunState
from src.storage.local_upload import LocalUploadStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------


def _require_templates() -> Jinja2Templates:
    """Return the configured Jinja2Templates or raise if not set."""
    if _templates is None:
        raise RuntimeError("UI templates have not been configured")
    return _templates


def _require_upload_store() -> LocalUploadStore:
    """Return the configured LocalUploadStore or raise if not set."""
    if _upload_store is None:
        raise RuntimeError("Upload store has not been configured")
    return _upload_store

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

ui_router = APIRouter(prefix="/ui", default_response_class=HTMLResponse)

# ---------------------------------------------------------------------------
# Module-level dependencies (set by configure_ui_routes)
# ---------------------------------------------------------------------------

_templates: Jinja2Templates | None = None
_upload_store: LocalUploadStore | None = None


def configure_ui_routes(
    templates: Jinja2Templates,
    upload_store: LocalUploadStore,
) -> None:
    """Inject dependencies into the UI router module."""
    global _templates, _upload_store
    _templates = templates
    _upload_store = upload_store
    logger.info("UI routes configured")


# ---------------------------------------------------------------------------
# Exception handlers – render errors as HTML fragments
# ---------------------------------------------------------------------------


def _is_ui_request(request: Request) -> bool:
    """Return True if the request targets a UI route."""
    return request.url.path.startswith("/ui/") or request.url.path == "/"


async def _htmx_http_exception_handler(
    request: Request, exc: HTTPException
) -> HTMLResponse:
    """Render HTTP errors as HTML fragments for HTMX consumption."""
    if not _is_ui_request(request):
        from fastapi.exception_handlers import http_exception_handler

        return await http_exception_handler(request, exc)

    if _templates is None:
        return HTMLResponse(
            content=f"<p>{exc.detail}</p>",
            status_code=exc.status_code,
        )
    return _templates.TemplateResponse(
        "fragments/error.html",
        {"request": request, "message": exc.detail},
        status_code=exc.status_code,
    )


async def _htmx_general_exception_handler(
    request: Request, exc: Exception
) -> HTMLResponse | JSONResponse:
    """Render unexpected errors as HTML fragments for HTMX consumption."""
    if not _is_ui_request(request):
        return JSONResponse(
            content={"detail": "Internal server error"},
            status_code=500,
        )

    logger.exception("Unhandled error in UI route: %s", exc)
    message = "An unexpected error occurred"
    if _templates is None:
        return HTMLResponse(content=f"<p>{message}</p>", status_code=500)
    return _templates.TemplateResponse(
        "fragments/error.html",
        {"request": request, "message": message},
        status_code=500,
    )


def register_ui_exception_handlers(app: FastAPI) -> None:
    """Register HTMX-aware exception handlers on the application.

    Must be called after the app is created.  The handlers check the
    request path and only render HTML for ``/ui/`` and ``/`` routes;
    all other paths get the default JSON error responses.
    """
    app.add_exception_handler(HTTPException, _htmx_http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _htmx_general_exception_handler)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


async def root_page(request: Request) -> HTMLResponse:
    """Render the full landing page at ``GET /``.

    This function is registered directly on the app (not on ``ui_router``)
    so that the root URL serves the migration UI.
    """
    templates = _require_templates()
    return templates.TemplateResponse("base.html", {"request": request})


@ui_router.get("/reset")
async def reset(request: Request) -> HTMLResponse:
    """Return the initial upload form fragment, clearing all panels."""
    templates = _require_templates()
    return templates.TemplateResponse(
        "fragments/upload_form.html", {"request": request}
    )

@ui_router.post("/upload")
async def upload(request: Request, file: UploadFile) -> HTMLResponse:
    """Accept a ZIP file upload, store it locally, and return a success fragment."""
    templates = _require_templates()
    store = _require_upload_store()

    if not file.filename:
        raise HTTPException(422, "No file selected")

    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(422, "Only .zip files are accepted")

    data = await file.read()

    try:
        bundle_key = store.save(file.filename, data)
    except OSError as exc:
        raise HTTPException(500, str(exc))

    return templates.TemplateResponse(
        "fragments/upload_success.html",
        {"request": request, "filename": file.filename, "bundle_key": bundle_key},
    )



@ui_router.post("/migrate")
async def migrate(
    request: Request,
    background_tasks: BackgroundTasks,
    bundle_key: str = Form(...),
) -> HTMLResponse:
    """Trigger a migration pipeline run and return the initial progress fragment."""
    templates = _require_templates()

    if not bundle_key.strip():
        raise HTTPException(422, "Missing bundle_key")

    from src.api.routes import _orchestrator

    if _orchestrator is None:
        raise HTTPException(503, "Pipeline orchestrator is not configured")

    run_id = uuid.uuid4().hex
    state = PipelineRunState.create(run_id=run_id, bundle_key=bundle_key)
    _run_states[run_id] = state
    background_tasks.add_task(_run_pipeline, run_id, bundle_key)

    return templates.TemplateResponse(
        "fragments/progress.html",
        {
            "request": request,
            "run_id": run_id,
            "status": state.status,
            "current_agent": state.current_agent,
            "agent_durations": state.agent_durations,
            "warnings": state.warnings,
            "error": state.error,
        },
    )

@ui_router.get("/status/{run_id}")
async def status(request: Request, run_id: str) -> HTMLResponse:
    """Return the progress fragment for a given run.

    Reads the in-memory ``_run_states`` dict and renders
    ``fragments/progress.html`` with the current run context.
    The template itself handles conditional ``hx-trigger`` logic
    (polling while running, artifact fetch on completion).
    """
    templates = _require_templates()

    state = _run_states.get(run_id)
    if state is None:
        raise HTTPException(404, "Run not found")

    safe = state.to_safe_dict()

    return templates.TemplateResponse(
        "fragments/progress.html",
        {
            "request": request,
            "run_id": safe["run_id"],
            "status": safe["status"],
            "current_agent": safe["current_agent"],
            "agent_durations": safe["agent_durations"],
            "warnings": safe["warnings"],
            "error": safe["error"],
        },
    )



@ui_router.get("/artifacts/{run_id}")
async def artifacts(request: Request, run_id: str) -> HTMLResponse:
    """Return the artifact list fragment for a completed run."""
    templates = _require_templates()

    state = _run_states.get(run_id)
    if state is None:
        raise HTTPException(404, "Run not found")

    if state.status != "completed":
        raise HTTPException(409, "Migration still in progress")

    artifact_names = list(state.artifacts.keys())

    return templates.TemplateResponse(
        "fragments/artifacts.html",
        {
            "request": request,
            "run_id": run_id,
            "artifacts": artifact_names,
            "count": len(artifact_names),
        },
    )


@ui_router.get("/artifacts/{run_id}/download-all")
async def download_all(run_id: str) -> Response:
    """Bundle all artifacts from a completed run into a ZIP and return it."""
    state = _run_states.get(run_id)
    if state is None:
        raise HTTPException(404, "Run not found")

    if state.status != "completed":
        raise HTTPException(409, "Migration still in progress")

    if not state.artifacts:
        raise HTTPException(404, "No artifacts available")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in state.artifacts.items():
            if isinstance(content, str):
                data = content.encode()
            elif isinstance(content, bytes):
                data = content
            else:
                serialized = (
                    content.model_dump()
                    if hasattr(content, "model_dump")
                    else content
                )
                data = json.dumps(serialized, default=str).encode()
            zf.writestr(name, data)

    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={run_id}-artifacts.zip"},
    )
