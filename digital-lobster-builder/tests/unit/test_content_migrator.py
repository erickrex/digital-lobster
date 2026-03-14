from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from src.agents.content_migrator import ContentMigratorAgent
from src.models.migration_report import ContentTypeMigrationStats, MediaMigrationStats
from src.pipeline_context import MediaManifestEntry

def _content_item_dict() -> dict:
    return {
        "id": 1,
        "post_type": "post",
        "title": "Hello CMS",
        "slug": "hello-cms",
        "status": "publish",
        "date": "2024-01-01",
        "excerpt": "Excerpt",
        "blocks": [],
        "raw_html": "<p>Hello</p>",
        "taxonomies": {"category": ["news"]},
        "meta": {},
        "featured_media": {
            "url": "https://example.com/wp-content/uploads/2024/01/photo.jpg"
        },
        "legacy_permalink": "/hello-cms/",
        "seo": None,
    }

def _modeling_manifest_dict() -> dict:
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
                    }
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

class TestContentMigratorAgent:
    @pytest.mark.asyncio
    async def test_execute_accepts_dict_context_and_uses_normalized_artifacts(
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
            yield "http://127.0.0.1:48888"

        async def fake_upload_media_files(
            base_url: str,
            token: str,
            media_manifest: list[MediaManifestEntry],
            export_bundle: dict[str, object],
            concurrency: int,
        ):
            assert base_url == "http://127.0.0.1:48888"
            assert token == "tok-secret"
            assert concurrency == 3
            assert media_manifest[0].bundle_path == "media/2024/01/photo.jpg"
            assert export_bundle["media/2024/01/photo.jpg"] == b"jpeg-bytes"
            return (
                {
                    "https://example.com/wp-content/uploads/2024/01/photo.jpg": "/uploads/photo.jpg"
                },
                MediaMigrationStats(
                    total=1, succeeded=1, failed=0, failed_urls=[]
                ),
            )

        async def fake_create_taxonomy_terms(*args, **kwargs):
            return ({"category": {"news": 7}}, 1, [])

        async def fake_migrate_content_entries(
            base_url: str,
            token: str,
            content_items,
            content_type_map,
            media_url_map,
            taxonomy_term_ids,
            batch_size: int,
        ):
            assert base_url == "http://127.0.0.1:48888"
            assert media_url_map["https://example.com/wp-content/uploads/2024/01/photo.jpg"] == "/uploads/photo.jpg"
            assert taxonomy_term_ids["category"]["news"] == 7
            assert batch_size == 25
            assert content_items[0].slug == "hello-cms"
            assert content_type_map.mappings["posts"] == "api::post.post"
            return [
                ContentTypeMigrationStats(
                    content_type="post",
                    total=1,
                    succeeded=1,
                    failed=0,
                    skipped=0,
                    failed_entries=[],
                )
            ]

        async def fake_migrate_menus(
            base_url: str,
            token: str,
            menus,
            manifest,
            migrated_slugs: set[str],
        ):
            assert base_url == "http://127.0.0.1:48888"
            assert menus[0]["name"] == "Primary"
            assert manifest.collections[0].route_pattern == "/blog/[slug]"
            assert migrated_slugs == {"hello-cms"}
            return 1, []

        monkeypatch.setattr(
            "src.agents.content_migrator.strapi_base_url_context",
            fake_base_url_context,
        )
        monkeypatch.setattr(
            "src.agents.content_migrator.upload_media_files",
            fake_upload_media_files,
        )
        monkeypatch.setattr(
            "src.agents.content_migrator.create_taxonomy_terms",
            fake_create_taxonomy_terms,
        )
        monkeypatch.setattr(
            "src.agents.content_migrator.migrate_content_entries",
            fake_migrate_content_entries,
        )
        monkeypatch.setattr(
            "src.agents.content_migrator.migrate_menus",
            fake_migrate_menus,
        )

        agent = ContentMigratorAgent(gradient_client=None)
        result = await agent.execute(
            {
                "content_type_map": {
                    "mappings": {"posts": "api::post.post"},
                    "taxonomy_mappings": {"category": "api::category.category"},
                    "component_uids": [],
                },
                "strapi_base_url": "http://203.0.113.10",
                "strapi_api_token": "tok-secret",
                "content_items": [_content_item_dict()],
                "modeling_manifest": _modeling_manifest_dict(),
                "menus": [
                    {
                        "name": "Primary",
                        "location": "header",
                        "items": [{"title": "Home", "url": "https://example.com/"}],
                    }
                ],
                "media_manifest": [
                    {
                        "source_url": "https://example.com/wp-content/uploads/2024/01/photo.jpg",
                        "bundle_path": "media/2024/01/photo.jpg",
                        "artifact_path": "media/2024/01/photo.jpg",
                        "filename": "photo.jpg",
                        "mime_type": "image/jpeg",
                    }
                ],
                "export_bundle": {"media/2024/01/photo.jpg": b"jpeg-bytes"},
                "ssh_connection_string": "root@203.0.113.10",
                "cms_config": SimpleNamespace(ssh_private_key_path="/tmp/test-key"),
                "batch_size": 25,
                "media_concurrency": 3,
            }
        )

        assert seen == {
            "requested_base_url": "http://203.0.113.10",
            "ssh_connection_string": "root@203.0.113.10",
            "ssh_private_key_path": "/tmp/test-key",
        }
        report = result.artifacts["migration_report"]
        assert report.total_entries_succeeded == 1
        assert report.taxonomy_terms_created == 1
        assert report.menu_entries_created == 1
        assert result.artifacts["media_url_map"] == {
            "https://example.com/wp-content/uploads/2024/01/photo.jpg": "/uploads/photo.jpg"
        }
