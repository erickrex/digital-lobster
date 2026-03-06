from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from src.agents.content_type_generator import ContentTypeGeneratorAgent
from src.models.modeling_manifest import ModelingManifest
from src.models.strapi_types import StrapiComponentSchema, StrapiContentTypeDefinition


def _manifest_dict() -> dict:
    return {
        "collections": [
            {
                "collection_name": "posts",
                "source_post_type": "post",
                "frontmatter_fields": [
                    {
                        "name": "title",
                        "type": "string",
                        "required": True,
                        "description": "Title",
                    },
                    {
                        "name": "meta_description",
                        "type": "string",
                        "required": False,
                        "description": "SEO description",
                    },
                ],
                "route_pattern": "/blog/[slug]",
            }
        ],
        "components": [],
        "taxonomies": [
            {
                "taxonomy": "category",
                "collection_ref": "posts",
                "data_file": None,
            }
        ],
    }


class TestContentTypeGeneratorAgent:
    @pytest.mark.asyncio
    async def test_execute_accepts_dict_manifest_and_uses_tunneled_base_url(
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
            yield "http://127.0.0.1:47777"

        async def fake_post_component(
            base_url: str,
            token: str,
            component: StrapiComponentSchema,
        ) -> str:
            assert base_url == "http://127.0.0.1:47777"
            assert token == "tok-secret"
            assert component.name == "seo-metadata"
            return "shared.seo-metadata"

        created_types: list[StrapiContentTypeDefinition] = []

        async def fake_post_content_type(
            base_url: str,
            token: str,
            ct: StrapiContentTypeDefinition,
        ) -> str:
            assert base_url == "http://127.0.0.1:47777"
            assert token == "tok-secret"
            created_types.append(ct)
            return ct.api_id

        monkeypatch.setattr(
            "src.agents.content_type_generator.strapi_base_url_context",
            fake_base_url_context,
        )
        monkeypatch.setattr(
            "src.agents.content_type_generator._post_component",
            fake_post_component,
        )
        monkeypatch.setattr(
            "src.agents.content_type_generator._post_content_type",
            fake_post_content_type,
        )

        agent = ContentTypeGeneratorAgent(gradient_client=None)
        result = await agent.execute(
            {
                "modeling_manifest": _manifest_dict(),
                "strapi_base_url": "http://203.0.113.10:1337",
                "strapi_api_token": "tok-secret",
                "ssh_connection_string": "root@203.0.113.10",
                "cms_config": SimpleNamespace(ssh_private_key_path="/tmp/test-key"),
            }
        )

        assert seen == {
            "requested_base_url": "http://203.0.113.10:1337",
            "ssh_connection_string": "root@203.0.113.10",
            "ssh_private_key_path": "/tmp/test-key",
        }
        assert isinstance(result.artifacts["content_type_map"].mappings, dict)
        assert result.artifacts["content_type_map"].mappings["posts"] == "api::post.post"
        assert result.artifacts["content_type_map"].taxonomy_mappings["category"] == "api::category.category"
        assert result.artifacts["content_type_map"].component_uids == ["shared.seo-metadata"]
        assert [ct.singularName for ct in created_types] == ["post", "category"]
        assert ModelingManifest.model_validate(_manifest_dict()).collections[0].collection_name == "posts"
