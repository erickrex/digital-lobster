from __future__ import annotations

import asyncio
import importlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.app import create_app, create_app_from_env
from src.api.routes import _run_states
from src.orchestrator.state import PipelineRunState
from src.utils.scrubbing import REDACTED


@pytest.fixture(autouse=True)
def _clear_run_states():
    """Ensure run states are clean before each test."""
    _run_states.clear()
    yield
    _run_states.clear()


@pytest.fixture()
def mock_spaces():
    client = MagicMock()
    client.generate_presigned_upload_url = MagicMock(
        return_value="https://spaces.example.com/presigned-url"
    )
    client.download = AsyncMock(return_value=b"artifact-bytes")
    return client


@pytest.fixture()
def mock_orchestrator():
    return AsyncMock()


@pytest.fixture()
def app(mock_spaces, mock_orchestrator):
    application = create_app(
        spaces_client=mock_spaces,
        orchestrator=mock_orchestrator,
        ingestion_bucket="test-ingestion",
        artifacts_bucket="test-artifacts",
    )
    return application


@pytest.fixture()
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestHealthCheck:
    async def test_health_returns_200(self, client: AsyncClient) -> None:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestUiAssets:
    async def test_vendored_htmx_asset_is_a_working_local_shim(
        self, client: AsyncClient
    ) -> None:
        resp = await client.get("/static/htmx.min.js")
        assert resp.status_code == 200
        body = resp.text
        assert "window.htmx" in body
        assert "placeholder loaded" not in body


class TestPresignEndpoint:
    async def test_presign_returns_url_and_key(
        self, client: AsyncClient, mock_spaces: MagicMock
    ) -> None:
        resp = await client.post(
            "/uploads/presign", json={"filename": "export.zip"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "upload_url" in body
        assert "bundle_key" in body
        assert body["upload_url"] == "https://spaces.example.com/presigned-url"
        assert "export.zip" in body["bundle_key"]
        mock_spaces.generate_presigned_upload_url.assert_called_once()


class TestMigrationTrigger:
    async def test_trigger_returns_run_id_and_status(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post(
            "/migrations", json={"bundle_key": "uploads/abc/export.zip"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "run_id" in body
        assert body["status"] == "pending"
        assert len(body["run_id"]) > 0

    async def test_trigger_passes_production_mode_to_orchestrator(
        self,
        client: AsyncClient,
        mock_orchestrator: AsyncMock,
    ) -> None:
        mock_orchestrator.run.return_value = PipelineRunState.create(
            run_id="ignored", bundle_key="uploads/abc/export.zip"
        )

        resp = await client.post(
            "/migrations",
            json={
                "bundle_key": "uploads/abc/export.zip",
                "cms_mode": True,
                "production_mode": True,
                "cms_config": {
                    "domain_name": "example.com",
                    "ssh_public_key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest",
                    "ssh_private_key_path": "/tmp/test-key",
                    "strapi_admin_email": "admin@example.com",
                    "do_token": "do-token",
                    "strapi_admin_password": "admin-password",
                },
            },
        )

        assert resp.status_code == 200
        assert mock_orchestrator.run.await_count == 1
        await_args = mock_orchestrator.run.await_args
        assert await_args.args[:2] == (
            "uploads/abc/export.zip",
            resp.json()["run_id"],
        )
        assert await_args.kwargs["cms_mode"] is True
        assert await_args.kwargs["production_mode"] is True


class TestMigrationStatus:
    async def test_status_returns_correct_state(
        self, client: AsyncClient
    ) -> None:
        # Seed a run state
        state = PipelineRunState.create(
            run_id="run-123", bundle_key="uploads/abc/export.zip"
        )
        state.mark_running()
        state.current_agent = "modeling"
        state.warnings = ["warn1"]
        state.agent_durations = {"blueprint_intake": 1.5}
        _run_states["run-123"] = state

        resp = await client.get("/migrations/run-123")
        assert resp.status_code == 200
        body = resp.json()
        assert body["run_id"] == "run-123"
        assert body["status"] == "running"
        assert body["current_agent"] == "modeling"
        assert body["warnings"] == ["warn1"]
        assert body["agent_durations"] == {"blueprint_intake": 1.5}

    async def test_unknown_run_returns_404(
        self, client: AsyncClient
    ) -> None:
        resp = await client.get("/migrations/nonexistent")
        assert resp.status_code == 404

    async def test_status_scrubs_secret_error_fields(
        self, client: AsyncClient
    ) -> None:
        state = PipelineRunState.create(
            run_id="run-secret", bundle_key="uploads/abc/export.zip"
        )
        state.error = {
            "agent": "content_type_generator",
            "message": "failed",
            "strapi_api_token": "tok-secret",
        }
        _run_states["run-secret"] = state

        resp = await client.get("/migrations/run-secret")
        assert resp.status_code == 200
        assert resp.json()["error"]["strapi_api_token"] == REDACTED


class TestArtifactList:
    async def test_list_artifacts_returns_names(
        self, client: AsyncClient
    ) -> None:
        state = PipelineRunState.create(
            run_id="run-456", bundle_key="uploads/abc/export.zip"
        )
        state.artifacts = {"prd_md": "# PRD", "inventory": {"data": 1}}
        _run_states["run-456"] = state

        resp = await client.get("/migrations/run-456/artifacts")
        assert resp.status_code == 200
        body = resp.json()
        assert body["run_id"] == "run-456"
        assert sorted(body["artifacts"]) == ["inventory", "prd_md"]

    async def test_unknown_run_returns_404(
        self, client: AsyncClient
    ) -> None:
        resp = await client.get("/migrations/nonexistent/artifacts")
        assert resp.status_code == 404

    async def test_sensitive_artifacts_are_not_listed(
        self, client: AsyncClient
    ) -> None:
        state = PipelineRunState.create(
            run_id="run-456", bundle_key="uploads/abc/export.zip"
        )
        state.artifacts = {"prd_md": "# PRD"}
        _run_states["run-456"] = state

        resp = await client.get("/migrations/run-456/artifacts")
        assert resp.status_code == 200
        assert resp.json()["artifacts"] == ["prd_md"]


class TestArtifactDownload:
    async def test_download_artifact(
        self, client: AsyncClient, mock_spaces: MagicMock
    ) -> None:
        state = PipelineRunState.create(
            run_id="run-789", bundle_key="uploads/abc/export.zip"
        )
        state.artifacts = {"prd_md": "# PRD"}
        _run_states["run-789"] = state

        resp = await client.get("/migrations/run-789/artifacts/prd_md")
        assert resp.status_code == 200
        assert resp.content == b"artifact-bytes"
        mock_spaces.download.assert_called_once_with(
            "test-artifacts", "run-789/prd_md"
        )

    async def test_unknown_run_returns_404(
        self, client: AsyncClient
    ) -> None:
        resp = await client.get("/migrations/nonexistent/artifacts/prd_md")
        assert resp.status_code == 404

    async def test_unknown_artifact_returns_404(
        self, client: AsyncClient
    ) -> None:
        state = PipelineRunState.create(
            run_id="run-aaa", bundle_key="uploads/abc/export.zip"
        )
        state.artifacts = {"prd_md": "# PRD"}
        _run_states["run-aaa"] = state

        resp = await client.get("/migrations/run-aaa/artifacts/missing")
        assert resp.status_code == 404

    async def test_sensitive_artifact_download_returns_404(
        self, client: AsyncClient
    ) -> None:
        state = PipelineRunState.create(
            run_id="run-safe", bundle_key="uploads/abc/export.zip"
        )
        state.artifacts = {"prd_md": "# PRD"}
        _run_states["run-safe"] = state

        resp = await client.get(
            "/migrations/run-safe/artifacts/strapi_api_token"
        )
        assert resp.status_code == 404


class TestUnconfiguredDependencies:
    async def test_presign_returns_503_when_spaces_missing(self) -> None:
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/uploads/presign", json={"filename": "x.zip"})
        assert resp.status_code == 503
        assert "not configured" in resp.json()["detail"]

    async def test_background_pipeline_marks_run_failed_when_unconfigured(self) -> None:
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            trigger = await client.post(
                "/migrations", json={"bundle_key": "uploads/x/export.zip"}
            )
            assert trigger.status_code == 200
            run_id = trigger.json()["run_id"]

            body = {}
            for _ in range(10):
                status_resp = await client.get(f"/migrations/{run_id}")
                assert status_resp.status_code == 200
                body = status_resp.json()
                if body["status"] == "failed":
                    break
                await asyncio.sleep(0)

            assert body["status"] == "failed"
            assert body["error"] is not None


class TestEnvConfiguredFactory:
    async def test_create_app_from_env_wires_dependencies(
        self,
    ) -> None:
        env = {
            "GRADIENT_MODEL_ACCESS_KEY": "model-key",
            "DIGITALOCEAN_ACCESS_TOKEN": "do-token",
            "DO_SPACES_KEY": "spaces-key",
            "DO_SPACES_SECRET": "spaces-secret",
            "DO_SPACES_REGION": "nyc3",
            "DO_SPACES_INGESTION_BUCKET": "ingestion-bucket",
            "DO_SPACES_ARTIFACTS_BUCKET": "artifacts-bucket",
        }
        mock_spaces = MagicMock()
        mock_spaces.generate_presigned_upload_url = MagicMock(
            return_value="https://spaces.example.com/presigned-url"
        )
        mock_orchestrator = AsyncMock()
        captured = {}

        def fake_build_runtime_dependencies(settings, **kwargs):
            captured["settings"] = settings
            return (
                mock_spaces,
                mock_orchestrator,
                settings.ingestion_bucket,
                settings.artifacts_bucket,
            )

        with patch(
            "src.api.app._build_runtime_dependencies",
            side_effect=fake_build_runtime_dependencies,
        ):
            app = create_app_from_env(env=env)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/uploads/presign", json={"filename": "export.zip"}
            )

        assert resp.status_code == 200
        assert resp.json()["upload_url"] == "https://spaces.example.com/presigned-url"
        assert captured["settings"].gradient_model_access_key == "model-key"
        assert captured["settings"].do_access_token == "do-token"
        assert captured["settings"].artifacts_bucket == "artifacts-bucket"

    async def test_create_app_from_env_loads_env_file(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(
            "\n".join([
                "GRADIENT_MODEL_ACCESS_KEY=file-model-key",
                "DIGITALOCEAN_ACCESS_TOKEN=file-do-token",
                "GRADIENT_MODEL_ID=anthropic-claude-4.6-sonnet",
                "DO_SPACES_KEY=file-spaces-key",
                "DO_SPACES_SECRET=file-spaces-secret",
                "DO_SPACES_REGION=ams3",
                "DO_SPACES_INGESTION_BUCKET=file-ingestion",
                "DO_SPACES_ARTIFACTS_BUCKET=file-artifacts",
            ]),
            encoding="utf-8",
        )
        for key in (
            "GRADIENT_MODEL_ACCESS_KEY",
            "DIGITALOCEAN_ACCESS_TOKEN",
            "GRADIENT_MODEL_ID",
            "DO_SPACES_KEY",
            "DO_SPACES_SECRET",
            "DO_SPACES_REGION",
            "DO_SPACES_INGESTION_BUCKET",
            "DO_SPACES_ARTIFACTS_BUCKET",
        ):
            monkeypatch.delenv(key, raising=False)

        mock_spaces = MagicMock()
        mock_spaces.generate_presigned_upload_url = MagicMock(
            return_value="https://spaces.example.com/file-presigned-url"
        )
        mock_orchestrator = AsyncMock()

        def fake_build_runtime_dependencies(settings, **kwargs):
            assert settings.spaces_region == "ams3"
            assert settings.gradient_model_id == "anthropic-claude-4.6-sonnet"
            return (
                mock_spaces,
                mock_orchestrator,
                settings.ingestion_bucket,
                settings.artifacts_bucket,
            )

        with patch(
            "src.api.app._build_runtime_dependencies",
            side_effect=fake_build_runtime_dependencies,
        ):
            app = create_app_from_env(env_file=env_file)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/uploads/presign", json={"filename": "export.zip"}
            )

        assert resp.status_code == 200
        assert resp.json()["upload_url"] == "https://spaces.example.com/file-presigned-url"

    def test_module_exports_app(self) -> None:
        module = importlib.import_module("src.api.app")
        assert module.app is not None
