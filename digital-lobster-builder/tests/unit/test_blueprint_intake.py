from __future__ import annotations

import io
import json
import zipfile
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.blueprint_intake import (
    BlueprintIntakeAgent,
    build_inventory,
    collect_kb_documents,
    detect_plugin_family,
    validate_bundle_structure,
)
from src.models.manifest import ExportManifest


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_zip(files: dict[str, str | bytes]) -> zipfile.ZipFile:
    """Create an in-memory ZipFile from a dict of {path: content}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for path, content in files.items():
            if isinstance(content, str):
                content = content.encode("utf-8")
            zf.writestr(path, content)
    buf.seek(0)
    return zipfile.ZipFile(buf, "r")


def _minimal_bundle_files() -> dict[str, str]:
    """Return the minimal set of files for a valid export bundle."""
    manifest = json.dumps({
        "export_version": "1.0",
        "site_url": "https://example.com",
        "export_date": "2024-01-01",
        "wordpress_version": "6.4",
        "total_files": 5,
        "total_size_bytes": 1024,
        "files": {"content": 1},
    })
    site_info = json.dumps({
        "site_url": "https://example.com",
        "site_name": "Test Site",
        "wordpress_version": "6.4",
    })
    return {
        "MANIFEST.json": manifest,
        "site/site_info.json": site_info,
        "theme/style.css": "/* theme */",
        "content/posts.json": json.dumps([]),
        "menus/primary.json": json.dumps({"name": "Primary", "location": "header", "items": []}),
    }


def _exporter_bundle_files() -> dict[str, str]:
    """Return a compatible bundle using the exporter-style root artifacts."""
    return {
        "site_blueprint.json": json.dumps({
            "export_metadata": {
                "version": "2.0",
                "site_url": "https://example.com",
                "site_name": "Exporter Site",
                "export_date": "2024-01-02",
                "wordpress_version": "6.5",
                "total_files": 7,
                "total_size_bytes": 4096,
                "files": {"content": 1, "media": 1},
            },
            "site_info": {
                "site_url": "https://example.com",
                "site_name": "Exporter Site",
                "wordpress_version": "6.5",
            },
            "active_plugins": [
                {"slug": "wordpress-seo", "name": "Yoast SEO", "version": "22.0"}
            ],
        }),
        "theme/style.css": "/* theme */",
        "content/posts.json": json.dumps([
            {
                "id": 1,
                "post_type": "post",
                "title": "Hello Exporter",
                "slug": "hello-exporter",
                "status": "publish",
                "date": "2024-01-02",
                "content": {"rendered": "<p>Hello</p>"},
                "taxonomies": {"category": ["news"]},
                "meta": {},
                "link": "https://example.com/hello-exporter/",
            }
        ]),
        "menus.json": json.dumps({
            "menus": [
                {
                    "name": "Primary",
                    "location": "header",
                    "items": [{"title": "Home", "url": "https://example.com/"}],
                }
            ]
        }),
        "taxonomies.json": json.dumps({"category": ["news"]}),
        "media/media_map.json": json.dumps([
            {
                "source_url": "https://example.com/wp-content/uploads/2024/01/photo.jpg",
                "filename": "photo.jpg",
                "bundle_path": "media/2024/01/photo.jpg",
                "metadata": {"alt": "Photo", "caption": "Caption"},
            }
        ]),
        "media/2024/01/photo.jpg": "binary-jpg-placeholder",
        "redirects.json": json.dumps([
            {"source": "/old", "destination": "/new", "status": 301}
        ]),
    }


def _manifest() -> ExportManifest:
    return ExportManifest(
        export_version="1.0",
        site_url="https://example.com",
        export_date="2024-01-01",
        wordpress_version="6.4",
        total_files=5,
        total_size_bytes=1024,
        files={"content": 1},
    )


# ==================================================================
# validate_bundle_structure
# ==================================================================


class TestValidateBundleStructure:
    def test_valid_bundle_returns_no_errors(self):
        zf = _make_zip(_minimal_bundle_files())
        errors = validate_bundle_structure(zf)
        assert errors == []

    def test_missing_manifest(self):
        files = _minimal_bundle_files()
        del files["MANIFEST.json"]
        zf = _make_zip(files)
        errors = validate_bundle_structure(zf)
        paths = [e["path"] for e in errors]
        assert "MANIFEST.json" in paths

    def test_missing_site_info(self):
        files = _minimal_bundle_files()
        del files["site/site_info.json"]
        zf = _make_zip(files)
        errors = validate_bundle_structure(zf)
        paths = [e["path"] for e in errors]
        assert "site/site_info.json" in paths

    def test_missing_theme_dir(self):
        files = _minimal_bundle_files()
        del files["theme/style.css"]
        zf = _make_zip(files)
        errors = validate_bundle_structure(zf)
        paths = [e["path"] for e in errors]
        assert "theme/" in paths

    def test_missing_content_dir(self):
        files = _minimal_bundle_files()
        del files["content/posts.json"]
        zf = _make_zip(files)
        errors = validate_bundle_structure(zf)
        paths = [e["path"] for e in errors]
        assert "content/" in paths

    def test_missing_menus_dir(self):
        files = _minimal_bundle_files()
        del files["menus/primary.json"]
        zf = _make_zip(files)
        errors = validate_bundle_structure(zf)
        paths = [e["path"] for e in errors]
        assert "menus/" in paths

    def test_malformed_manifest_json(self):
        files = _minimal_bundle_files()
        files["MANIFEST.json"] = "not valid json {"
        zf = _make_zip(files)
        errors = validate_bundle_structure(zf)
        malformed = [e for e in errors if "malformed" in e["error"]]
        assert len(malformed) == 1
        assert malformed[0]["path"] == "MANIFEST.json"

    def test_malformed_site_info_json(self):
        files = _minimal_bundle_files()
        files["site/site_info.json"] = "{broken"
        zf = _make_zip(files)
        errors = validate_bundle_structure(zf)
        malformed = [e for e in errors if "malformed" in e["error"]]
        assert len(malformed) == 1
        assert malformed[0]["path"] == "site/site_info.json"

    def test_multiple_missing_files(self):
        """All required entries missing → one error per missing item."""
        zf = _make_zip({"readme.txt": "hello"})
        errors = validate_bundle_structure(zf)
        # 2 required files + 3 required dirs = 5 errors
        assert len(errors) == 5

    def test_empty_zip(self):
        zf = _make_zip({})
        errors = validate_bundle_structure(zf)
        assert len(errors) == 5

    def test_exporter_bundle_shape_is_accepted(self):
        zf = _make_zip(_exporter_bundle_files())
        errors = validate_bundle_structure(zf)
        assert errors == []


# ==================================================================
# detect_plugin_family
# ==================================================================


class TestDetectPluginFamily:
    @pytest.mark.parametrize(
        "slug,expected",
        [
            ("geodirectory", "geodirectory"),
            ("geodir-custom-posts", "geodirectory"),
            ("kadence-blocks", "kadence"),
            ("kadence-starter-templates", "kadence"),
            ("forminator", "forminator"),
            ("forminator-pro", "forminator"),
            ("wordpress-seo", "yoast"),
            ("yoast-seo-premium", "yoast"),
            ("akismet", None),
            ("jetpack", None),
            ("contact-form-7", None),
        ],
    )
    def test_family_detection(self, slug: str, expected: str | None):
        assert detect_plugin_family(slug) == expected


# ==================================================================
# build_inventory
# ==================================================================


class TestBuildInventory:
    def test_minimal_valid_bundle(self):
        zf = _make_zip(_minimal_bundle_files())
        manifest = _manifest()
        site_info = {"site_url": "https://example.com", "site_name": "Test Site", "wordpress_version": "6.4"}
        warnings: list[str] = []
        inv = build_inventory(zf, manifest, site_info, warnings)

        assert inv.site_url == "https://example.com"
        assert inv.site_name == "Test Site"
        assert inv.wordpress_version == "6.4"
        assert isinstance(inv.theme, object)
        assert inv.has_html_snapshots is False
        assert inv.has_media_manifest is False

    def test_content_types_extracted(self):
        files = _minimal_bundle_files()
        files["content/posts.json"] = json.dumps([
            {"post_type": "post", "slug": "hello-world", "meta": {"author": "admin"}, "taxonomies": {"category": ["news"]}},
            {"post_type": "post", "slug": "second-post", "meta": {}, "taxonomies": {}},
            {"post_type": "page", "slug": "about", "meta": {}, "taxonomies": {}},
        ])
        zf = _make_zip(files)
        warnings: list[str] = []
        inv = build_inventory(zf, _manifest(), {"site_url": "", "site_name": "", "wordpress_version": ""}, warnings)

        types_by_name = {ct.post_type: ct for ct in inv.content_types}
        assert "post" in types_by_name
        assert "page" in types_by_name
        assert types_by_name["post"].count == 2
        assert types_by_name["page"].count == 1
        assert "author" in types_by_name["post"].custom_fields

    def test_plugins_extracted_with_families(self):
        files = _minimal_bundle_files()
        files["plugins/yoast-seo.json"] = json.dumps({
            "slug": "wordpress-seo",
            "name": "Yoast SEO",
            "version": "21.0",
            "custom_post_types": [],
            "custom_taxonomies": [],
            "detected_features": ["sitemaps", "meta-tags"],
        })
        files["plugins/kadence-blocks.json"] = json.dumps({
            "slug": "kadence-blocks",
            "name": "Kadence Blocks",
            "version": "3.0",
            "custom_post_types": [],
            "custom_taxonomies": [],
            "detected_features": ["tabs", "accordion"],
        })
        zf = _make_zip(files)
        warnings: list[str] = []
        inv = build_inventory(zf, _manifest(), {"site_url": "", "site_name": "", "wordpress_version": ""}, warnings)

        plugins_by_slug = {p.slug: p for p in inv.plugins}
        assert plugins_by_slug["wordpress-seo"].family == "yoast"
        assert plugins_by_slug["kadence-blocks"].family == "kadence"
        assert inv.has_seo_data is True

    def test_menus_extracted(self):
        files = _minimal_bundle_files()
        files["menus/primary.json"] = json.dumps({
            "name": "Main Menu",
            "location": "header",
            "items": [{"label": "Home", "url": "/"}, {"label": "About", "url": "/about"}],
        })
        zf = _make_zip(files)
        warnings: list[str] = []
        inv = build_inventory(zf, _manifest(), {"site_url": "", "site_name": "", "wordpress_version": ""}, warnings)

        assert len(inv.menus) == 1
        assert inv.menus[0].name == "Main Menu"
        assert inv.menus[0].item_count == 2

    def test_theme_metadata_with_theme_json(self):
        files = _minimal_bundle_files()
        files["theme/theme.json"] = json.dumps({
            "name": "Twenty Twenty-Four",
            "settings": {
                "color": {"palette": [{"slug": "primary", "color": "#0073aa"}]},
                "typography": {"fontSizes": [{"slug": "small", "size": "13px"}]},
            },
        })
        zf = _make_zip(files)
        warnings: list[str] = []
        inv = build_inventory(zf, _manifest(), {"site_url": "", "site_name": "", "wordpress_version": ""}, warnings)

        assert inv.theme.name == "Twenty Twenty-Four"
        assert inv.theme.has_theme_json is True
        assert inv.theme.has_custom_css is True
        assert inv.theme.design_tokens is not None
        assert "color" in inv.theme.design_tokens

    def test_html_snapshots_detected(self):
        files = _minimal_bundle_files()
        files["snapshots/home.html"] = "<html></html>"
        zf = _make_zip(files)
        warnings: list[str] = []
        inv = build_inventory(zf, _manifest(), {"site_url": "", "site_name": "", "wordpress_version": ""}, warnings)
        assert inv.has_html_snapshots is True

    def test_media_manifest_detected(self):
        files = _minimal_bundle_files()
        files["media/media_manifest.json"] = json.dumps([])
        zf = _make_zip(files)
        warnings: list[str] = []
        inv = build_inventory(zf, _manifest(), {"site_url": "", "site_name": "", "wordpress_version": ""}, warnings)
        assert inv.has_media_manifest is True

    def test_exporter_media_map_detected(self):
        zf = _make_zip(_exporter_bundle_files())
        warnings: list[str] = []
        inv = build_inventory(
            zf,
            _manifest(),
            {"site_url": "", "site_name": "", "wordpress_version": ""},
            warnings,
        )
        assert inv.has_media_manifest is True

    def test_malformed_content_file_produces_warning(self):
        files = _minimal_bundle_files()
        files["content/broken.json"] = "not json"
        zf = _make_zip(files)
        warnings: list[str] = []
        build_inventory(zf, _manifest(), {"site_url": "", "site_name": "", "wordpress_version": ""}, warnings)
        assert any("broken.json" in w for w in warnings)


# ==================================================================
# collect_kb_documents
# ==================================================================


class TestCollectKbDocuments:
    def test_includes_site_info(self):
        files = _minimal_bundle_files()
        zf = _make_zip(files)
        docs = collect_kb_documents(zf)
        file_names = [d["metadata"]["file"] for d in docs]
        assert "site/site_info.json" in file_names

    def test_includes_plugin_fingerprints(self):
        files = _minimal_bundle_files()
        files["plugins/yoast.json"] = json.dumps({"slug": "yoast"})
        files["plugins/akismet.json"] = json.dumps({"slug": "akismet"})
        zf = _make_zip(files)
        docs = collect_kb_documents(zf)
        file_names = [d["metadata"]["file"] for d in docs]
        assert "plugins/yoast.json" in file_names
        assert "plugins/akismet.json" in file_names

    def test_includes_blocks_usage(self):
        files = _minimal_bundle_files()
        files["blocks_usage.json"] = json.dumps({"core/paragraph": 42})
        zf = _make_zip(files)
        docs = collect_kb_documents(zf)
        file_names = [d["metadata"]["file"] for d in docs]
        assert "blocks_usage.json" in file_names

    def test_includes_content_json_files(self):
        files = _minimal_bundle_files()
        files["content/posts.json"] = json.dumps([])
        files["content/pages.json"] = json.dumps([])
        zf = _make_zip(files)
        docs = collect_kb_documents(zf)
        file_names = [d["metadata"]["file"] for d in docs]
        assert "content/posts.json" in file_names
        assert "content/pages.json" in file_names

    def test_excludes_non_json_files(self):
        files = _minimal_bundle_files()
        files["content/readme.txt"] = "not json"
        zf = _make_zip(files)
        docs = collect_kb_documents(zf)
        file_names = [d["metadata"]["file"] for d in docs]
        assert "content/readme.txt" not in file_names

    def test_prefers_site_info_over_site_blueprint(self):
        files = _minimal_bundle_files()
        files["site/site_blueprint.json"] = json.dumps({"alt": True})
        zf = _make_zip(files)
        docs = collect_kb_documents(zf)
        file_names = [d["metadata"]["file"] for d in docs]
        assert "site/site_info.json" in file_names
        # Should not include both
        assert file_names.count("site/site_info.json") + file_names.count("site/site_blueprint.json") == 1

    def test_includes_root_site_blueprint_when_site_info_missing(self):
        zf = _make_zip(_exporter_bundle_files())
        docs = collect_kb_documents(zf)
        file_names = [d["metadata"]["file"] for d in docs]
        assert "site_blueprint.json" in file_names


# ==================================================================
# BlueprintIntakeAgent.execute (integration-style with mocks)
# ==================================================================


class TestBlueprintIntakeAgentExecute:
    @pytest.mark.asyncio
    async def test_successful_execution(self):
        """Full happy-path: download → validate → build inventory → create KB."""
        bundle_files = _minimal_bundle_files()
        bundle_files["plugins/yoast.json"] = json.dumps({
            "slug": "wordpress-seo", "name": "Yoast SEO", "version": "21.0",
            "custom_post_types": [], "custom_taxonomies": [], "detected_features": [],
        })
        bundle_files["content/posts.json"] = json.dumps([
            {
                "id": 10,
                "post_type": "post",
                "title": "Hello World",
                "slug": "hello-world",
                "status": "publish",
                "date": "2024-01-01",
                "content": {"rendered": "<p>Hello</p>"},
                "taxonomies": {"category": ["news"]},
                "meta": {"author": "admin"},
                "link": "/2024/hello-world/",
            }
        ])
        bundle_files["menus/primary.json"] = json.dumps({
            "name": "Primary",
            "location": "header",
            "items": [{"label": "Home", "url": "https://example.com/"}],
        })
        bundle_files["media/media_manifest.json"] = json.dumps([
            {
                "source_url": "https://example.com/wp-content/uploads/2024/01/photo.jpg",
                "filename": "photo.jpg",
                "bundle_path": "media/2024/01/photo.jpg",
            }
        ])
        bundle_files["media/2024/01/photo.jpg"] = "binary-jpg-placeholder"
        bundle_files["redirects/redirects.json"] = json.dumps([
            {"source": "/old", "destination": "/new", "status": 301}
        ])
        bundle_files["snapshots/home.html"] = "<html><body><main>Home</main></body></html>"

        # Build ZIP bytes
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for path, content in bundle_files.items():
                zf.writestr(path, content if isinstance(content, bytes) else content.encode())
        zip_bytes = buf.getvalue()

        spaces_client = AsyncMock()
        spaces_client.download.return_value = zip_bytes

        kb_client = AsyncMock()
        kb_client.create.return_value = "kb-123"

        agent = BlueprintIntakeAgent(
            gradient_client=MagicMock(),
            kb_client=kb_client,
            spaces_client=spaces_client,
            ingestion_bucket="test-bucket",
        )

        result = await agent.execute({"bundle_key": "export.zip", "run_id": "run-1"})

        assert result.agent_name == "blueprint_intake"
        assert "inventory" in result.artifacts
        assert result.artifacts["kb_ref"] == "kb-123"
        assert "export_bundle" in result.artifacts
        assert "content_items" in result.artifacts
        assert "menus" in result.artifacts
        assert "redirect_rules" in result.artifacts
        assert "html_snapshots" in result.artifacts
        assert "media_manifest" in result.artifacts
        assert result.artifacts.get("errors") is None

        inv = result.artifacts["inventory"]
        assert inv.site_name == "Test Site"
        assert inv.has_seo_data is True
        assert len(result.artifacts["content_items"]) == 1
        assert result.artifacts["content_items"][0]["slug"] == "hello-world"
        assert result.artifacts["menus"][0]["name"] == "Primary"
        assert result.artifacts["redirect_rules"][0]["source"] == "/old"
        assert "/" in result.artifacts["html_snapshots"]
        assert result.artifacts["media_manifest"][0]["artifact_path"] == "media/2024/01/photo.jpg"

        spaces_client.download.assert_awaited_once_with("test-bucket", "export.zip")
        kb_client.create.assert_awaited_once_with("run-1")
        kb_client.upload_documents.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_exporter_bundle_shape_executes_successfully(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for path, content in _exporter_bundle_files().items():
                zf.writestr(path, content if isinstance(content, bytes) else content.encode())
        zip_bytes = buf.getvalue()

        spaces_client = AsyncMock()
        spaces_client.download.return_value = zip_bytes

        agent = BlueprintIntakeAgent(
            gradient_client=MagicMock(),
            kb_client=None,
            spaces_client=spaces_client,
            ingestion_bucket="bucket",
        )

        result = await agent.execute({"bundle_key": "exporter.zip"})

        assert "errors" not in result.artifacts
        assert result.artifacts["inventory"].site_name == "Exporter Site"
        assert result.artifacts["menus"][0]["location"] == "header"
        assert result.artifacts["media_manifest"][0]["bundle_path"] == "media/2024/01/photo.jpg"
        assert result.artifacts["redirect_rules"][0]["destination"] == "/new"

    @pytest.mark.asyncio
    async def test_missing_files_returns_errors(self):
        """Bundle missing required files → returns errors artifact."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("readme.txt", "hello")
        zip_bytes = buf.getvalue()

        spaces_client = AsyncMock()
        spaces_client.download.return_value = zip_bytes

        agent = BlueprintIntakeAgent(
            gradient_client=MagicMock(),
            spaces_client=spaces_client,
            ingestion_bucket="bucket",
        )

        result = await agent.execute({"bundle_key": "bad.zip"})

        assert "errors" in result.artifacts
        assert len(result.artifacts["errors"]) == 5
        assert "inventory" not in result.artifacts

    @pytest.mark.asyncio
    async def test_bad_zip_returns_error(self):
        """Corrupt ZIP data → returns error artifact."""
        spaces_client = AsyncMock()
        spaces_client.download.return_value = b"not a zip file"

        agent = BlueprintIntakeAgent(
            gradient_client=MagicMock(),
            spaces_client=spaces_client,
            ingestion_bucket="bucket",
        )

        result = await agent.execute({"bundle_key": "corrupt.zip"})

        assert "errors" in result.artifacts
        assert len(result.artifacts["errors"]) == 1

    @pytest.mark.asyncio
    async def test_no_kb_client_skips_kb_creation(self):
        """When kb_client is None, KB creation is skipped."""
        bundle_files = _minimal_bundle_files()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for path, content in bundle_files.items():
                zf.writestr(path, content if isinstance(content, bytes) else content.encode())
        zip_bytes = buf.getvalue()

        spaces_client = AsyncMock()
        spaces_client.download.return_value = zip_bytes

        agent = BlueprintIntakeAgent(
            gradient_client=MagicMock(),
            kb_client=None,
            spaces_client=spaces_client,
            ingestion_bucket="bucket",
        )

        result = await agent.execute({"bundle_key": "export.zip"})

        assert result.artifacts["kb_ref"] is None
        assert "inventory" in result.artifacts
