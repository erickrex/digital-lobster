from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from src.agents.strapi_provisioner import (
    create_admin_user,
    generate_api_token,
    poll_health,
)

class _Response:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict:
        return self._payload

class TestStrapiProvisionerTunnelUsage:
    @pytest.mark.asyncio
    async def test_poll_health_uses_tunneled_base_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: dict[str, object] = {}

        @asynccontextmanager
        async def fake_base_url_context(
            base_url: str,
            ssh_connection_string: str | None,
            ssh_private_key_path: str | None,
        ):
            seen["requested_base_url"] = base_url
            seen["ssh_connection_string"] = ssh_connection_string
            seen["ssh_private_key_path"] = ssh_private_key_path
            yield "http://127.0.0.1:49999"

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, url: str):
                seen["health_url"] = url
                return _Response(200)

        monkeypatch.setattr(
            "src.agents.strapi_provisioner.strapi_base_url_context",
            fake_base_url_context,
        )
        monkeypatch.setattr(
            "src.agents.strapi_provisioner.httpx.AsyncClient",
            lambda timeout=10: FakeClient(),
        )

        await poll_health(
            "203.0.113.10",
            ssh_connection_string="root@203.0.113.10",
            ssh_private_key_path="/tmp/test-key",
            timeout=1,
            poll_interval=0,
        )

        assert seen == {
            "requested_base_url": "http://203.0.113.10",
            "ssh_connection_string": "root@203.0.113.10",
            "ssh_private_key_path": "/tmp/test-key",
            "health_url": "http://127.0.0.1:49999/_health",
        }

    @pytest.mark.asyncio
    async def test_admin_bootstrap_and_token_generation_use_tunnel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        posts: list[str] = []

        @asynccontextmanager
        async def fake_base_url_context(
            base_url: str,
            ssh_connection_string: str | None,
            ssh_private_key_path: str | None,
        ):
            assert base_url == "http://203.0.113.10"
            assert ssh_connection_string == "root@203.0.113.10"
            assert ssh_private_key_path == "/tmp/test-key"
            yield "http://127.0.0.1:49999"

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, url: str, json=None, headers=None):
                posts.append(url)
                if url.endswith("/admin/register-admin"):
                    return _Response(201, {"data": {"token": "admin-jwt"}})
                if url.endswith("/admin/api-tokens"):
                    assert headers == {"Authorization": "Bearer admin-jwt"}
                    return _Response(201, {"data": {"accessKey": "api-token"}})
                raise AssertionError(f"Unexpected URL: {url}")

        monkeypatch.setattr(
            "src.agents.strapi_provisioner.strapi_base_url_context",
            fake_base_url_context,
        )
        monkeypatch.setattr(
            "src.agents.strapi_provisioner.httpx.AsyncClient",
            lambda timeout=30: FakeClient(),
        )

        admin_jwt = await create_admin_user(
            "203.0.113.10",
            "admin@example.com",
            "password123",
            ssh_connection_string="root@203.0.113.10",
            ssh_private_key_path="/tmp/test-key",
        )
        api_token = await generate_api_token(
            "203.0.113.10",
            admin_jwt,
            ssh_connection_string="root@203.0.113.10",
            ssh_private_key_path="/tmp/test-key",
        )

        assert admin_jwt == "admin-jwt"
        assert api_token == "api-token"
        assert posts == [
            "http://127.0.0.1:49999/admin/register-admin",
            "http://127.0.0.1:49999/admin/api-tokens",
        ]
