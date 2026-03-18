import pytest
from unittest.mock import AsyncMock
from typing import Any

from src.agents.importer import (
    ImporterAgent,
    build_media_map,
    build_frontmatter,
    convert_content_item,
    generate_navigation,
    generate_redirects,
    rewrite_media_urls,
    scan_media_urls,
    _extract_modeling_manifest,
    _find_collection_schema,
    _rewrite_url,
    _safe_filename,
    _build_astro_route,
)
from src.models.content import SerializedContent, WordPressBlock, WordPressContentItem
from src.models.modeling_manifest import (
    ComponentMapping,
    ContentCollectionSchema,
    FrontmatterField,
    ModelingManifest,
    TaxonomyDefinition,
)
from src.pipeline_context import MediaManifestEntry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_schema(**overrides: Any) -> ContentCollectionSchema:
    defaults = {
        "collection_name": "posts",
        "source_post_type": "post",
        "frontmatter_fields": [
            FrontmatterField(name="title", type="string", required=True, description="Title"),
            FrontmatterField(name="slug", type="string", required=True, description="Slug"),
            FrontmatterField(name="date", type="date", required=True, description="Date"),
            FrontmatterField(name="excerpt", type="string", required=False, description="Excerpt"),
        ],
        "route_pattern": "/blog/[slug]",
    }
    defaults.update(overrides)
    return ContentCollectionSchema(**defaults)

def _make_manifest(**overrides: Any) -> ModelingManifest:
    defaults: dict[str, Any] = {
        "collections": [_make_schema()],
        "components": [
            ComponentMapping(
                wp_block_type="core/paragraph",
                astro_component="Paragraph",
                is_island=False,
                hydration_directive=None,
                props=[],
                fallback=False,
            ),
        ],
        "taxonomies": [],
    }
    defaults.update(overrides)
    return ModelingManifest(**defaults)

def _make_content_item(**overrides: Any) -> WordPressContentItem:
    defaults: dict[str, Any] = {
        "id": 1,
        "post_type": "post",
        "title": "Hello World",
        "slug": "hello-world",
        "status": "publish",
        "date": "2024-01-15",
        "excerpt": "A short excerpt",
        "blocks": [
            WordPressBlock(
                name="core/paragraph",
                attrs={},
                html="<p>Hello there.</p>",
            ),
        ],
        "raw_html": "<p>Hello there.</p>",
        "taxonomies": {"categories": ["news"]},
        "meta": {},
        "featured_media": None,
        "legacy_permalink": "/2024/01/hello-world/",
        "seo": None,
    }
    defaults.update(overrides)
    return WordPressContentItem(**defaults)

def _make_gradient_client() -> AsyncMock:
    return AsyncMock()

def _make_context(
    manifest: ModelingManifest | None = None,
    content_items: list | None = None,
    menus: list | None = None,
    redirect_rules: list | None = None,
    inventory: dict | None = None,
    media_manifest: list[dict[str, Any]] | None = None,
    html_snapshots: dict[str, str] | None = None,
    astro_project: dict[str, str | bytes] | None = None,
) -> dict[str, Any]:
    m = manifest or _make_manifest()
    return {
        "modeling_manifest": m,
        "content_items": content_items or [],
        "menus": menus or [],
        "redirect_rules": redirect_rules or [],
        "inventory": inventory or {"site_url": "https://example.com"},
        "media_manifest": media_manifest or [],
        "html_snapshots": html_snapshots or {},
        "astro_project": astro_project or {},
    }

# ---------------------------------------------------------------------------
# Tests: _extract_modeling_manifest
# ---------------------------------------------------------------------------

class TestExtractModelingManifest:
    def test_from_instance(self):
        m = _make_manifest()
        assert _extract_modeling_manifest({"modeling_manifest": m}) == m

    def test_from_dict(self):
        m = _make_manifest()
        result = _extract_modeling_manifest({"modeling_manifest": m.model_dump()})
        assert isinstance(result, ModelingManifest)
        assert result.collections[0].collection_name == "posts"

    def test_missing_raises(self):
        with pytest.raises(ValueError, match="Missing"):
            _extract_modeling_manifest({})

# ---------------------------------------------------------------------------
# Tests: _find_collection_schema
# ---------------------------------------------------------------------------

class TestFindCollectionSchema:
    def test_found(self):
        m = _make_manifest()
        schema = _find_collection_schema(m, "post")
        assert schema is not None
        assert schema.collection_name == "posts"

    def test_not_found(self):
        m = _make_manifest()
        assert _find_collection_schema(m, "unknown_type") is None

# ---------------------------------------------------------------------------
# Tests: build_frontmatter
# ---------------------------------------------------------------------------

class TestBuildFrontmatter:
    def test_core_fields_present(self):
        item = _make_content_item()
        schema = _make_schema()
        fm = build_frontmatter(item, schema)
        assert fm["title"] == "Hello World"
        assert fm["slug"] == "hello-world"
        assert fm["date"] == "2024-01-15"

    def test_excerpt_included(self):
        item = _make_content_item(excerpt="My excerpt")
        schema = _make_schema()
        fm = build_frontmatter(item, schema)
        assert fm["excerpt"] == "My excerpt"

    def test_seo_fields_included(self):
        item = _make_content_item(
            seo={"title": "SEO Title", "description": "SEO desc"}
        )
        schema = _make_schema()
        fm = build_frontmatter(item, schema)
        assert fm["seo_title"] == "SEO Title"
        assert fm["meta_description"] == "SEO desc"

    def test_seo_metadesc_fallback(self):
        item = _make_content_item(seo={"title": "T", "metadesc": "Meta D"})
        schema = _make_schema()
        fm = build_frontmatter(item, schema)
        assert fm["meta_description"] == "Meta D"

    def test_no_seo_when_absent(self):
        item = _make_content_item(seo=None)
        schema = _make_schema()
        fm = build_frontmatter(item, schema)
        assert "seo_title" not in fm
        assert "meta_description" not in fm

    def test_legacy_url_included(self):
        item = _make_content_item(legacy_permalink="/old/path/")
        schema = _make_schema()
        fm = build_frontmatter(item, schema)
        assert fm["legacy_url"] == "/old/path/"

    def test_taxonomy_fields(self):
        item = _make_content_item(taxonomies={"categories": ["tech", "news"]})
        schema = _make_schema(
            frontmatter_fields=[
                FrontmatterField(name="title", type="string", required=True, description=""),
                FrontmatterField(name="categories", type="list", required=False, description=""),
            ]
        )
        fm = build_frontmatter(item, schema)
        assert fm["categories"] == ["tech", "news"]

    def test_featured_media(self):
        item = _make_content_item(
            featured_media={"url": "https://example.com/img.jpg"}
        )
        schema = _make_schema(
            frontmatter_fields=[
                FrontmatterField(name="title", type="string", required=True, description=""),
                FrontmatterField(name="featured_image", type="string", required=False, description=""),
            ]
        )
        fm = build_frontmatter(item, schema)
        assert fm["featured_image"] == "https://example.com/img.jpg"

    def test_slug_preserved(self):
        item = _make_content_item(slug="my-custom-slug")
        schema = _make_schema()
        fm = build_frontmatter(item, schema)
        assert fm["slug"] == "my-custom-slug"

# ---------------------------------------------------------------------------
# Tests: scan_media_urls
# ---------------------------------------------------------------------------

class TestScanMediaUrls:
    def test_finds_urls_in_blocks(self):
        item = _make_content_item(
            blocks=[
                WordPressBlock(
                    name="core/image",
                    attrs={},
                    html='<img src="https://wp.example.com/uploads/photo.jpg" />',
                )
            ],
            raw_html="",
        )
        media_map = scan_media_urls([item])
        assert "https://wp.example.com/uploads/photo.jpg" in media_map
        assert media_map["https://wp.example.com/uploads/photo.jpg"] == "/media/photo.jpg"

    def test_finds_urls_in_raw_html(self):
        item = _make_content_item(
            blocks=[],
            raw_html='<img src="https://wp.example.com/uploads/banner.png" />',
        )
        media_map = scan_media_urls([item])
        assert "https://wp.example.com/uploads/banner.png" in media_map

    def test_finds_featured_media(self):
        item = _make_content_item(
            blocks=[],
            raw_html="",
            featured_media={"url": "https://wp.example.com/uploads/thumb.webp"},
        )
        media_map = scan_media_urls([item])
        assert "https://wp.example.com/uploads/thumb.webp" in media_map

    def test_deduplicates_urls(self):
        item = _make_content_item(
            blocks=[
                WordPressBlock(name="core/image", attrs={}, html='<img src="https://wp.example.com/a.jpg" />'),
                WordPressBlock(name="core/image", attrs={}, html='<img src="https://wp.example.com/a.jpg" />'),
            ],
            raw_html='<img src="https://wp.example.com/a.jpg" />',
        )
        media_map = scan_media_urls([item])
        assert len(media_map) == 1

    def test_empty_items(self):
        assert scan_media_urls([]) == {}

# ---------------------------------------------------------------------------
# Tests: rewrite_media_urls
# ---------------------------------------------------------------------------

class TestRewriteMediaUrls:
    def test_rewrites_urls(self):
        body = "Check out ![photo](https://wp.example.com/uploads/photo.jpg)"
        media_map = {"https://wp.example.com/uploads/photo.jpg": "/media/photo.jpg"}
        result = rewrite_media_urls(body, media_map)
        assert "https://wp.example.com/uploads/photo.jpg" not in result
        assert "/media/photo.jpg" in result

    def test_no_change_when_no_match(self):
        body = "No media here"
        result = rewrite_media_urls(body, {"https://other.com/x.jpg": "/media/x.jpg"})
        assert result == body

    def test_multiple_urls(self):
        body = "A https://a.com/1.jpg and https://b.com/2.png"
        media_map = {
            "https://a.com/1.jpg": "/media/1.jpg",
            "https://b.com/2.png": "/media/2.png",
        }
        result = rewrite_media_urls(body, media_map)
        assert "/media/1.jpg" in result
        assert "/media/2.png" in result

# ---------------------------------------------------------------------------
# Tests: build_media_map
# ---------------------------------------------------------------------------

class TestBuildMediaMap:
    def test_uses_only_manifest_entries_present_in_bundle(self):
        item = _make_content_item(
            blocks=[
                WordPressBlock(
                    name="core/image",
                    attrs={},
                    html='<img src="https://wp.example.com/uploads/nested/photo.jpg" />',
                )
            ]
        )
        media_map = build_media_map(
            [item],
            [
                MediaManifestEntry(
                    source_url="https://wp.example.com/uploads/nested/photo.jpg",
                    bundle_path="media/2024/01/photo.jpg",
                    artifact_path="media/2024/01/photo.jpg",
                    filename="photo.jpg",
                ),
                MediaManifestEntry(
                    source_url="https://wp.example.com/uploads/unused.jpg",
                    bundle_path="media/unused.jpg",
                    artifact_path="media/unused.jpg",
                    filename="unused.jpg",
                ),
            ],
        )
        assert media_map == {
            "https://wp.example.com/uploads/nested/photo.jpg": "/media/2024/01/photo.jpg"
        }

    def test_returns_empty_when_no_manifest(self):
        item = _make_content_item(
            featured_media={"url": "https://wp.example.com/uploads/thumb.jpg"}
        )
        assert build_media_map([item], []) == {}

# ---------------------------------------------------------------------------
# Tests: generate_navigation
# ---------------------------------------------------------------------------

class TestGenerateNavigation:
    def test_basic_menu(self):
        menus = [
            {
                "name": "Main Menu",
                "location": "primary",
                "items": [
                    {"title": "Home", "url": "https://example.com/"},
                    {"title": "Blog", "url": "https://example.com/blog/"},
                ],
            }
        ]
        nav = generate_navigation(menus, site_url="https://example.com")
        assert len(nav["menus"]) == 1
        assert nav["menus"][0]["name"] == "Main Menu"
        items = nav["menus"][0]["items"]
        assert items[0]["label"] == "Home"
        assert items[0]["url"] == "/"
        assert items[1]["label"] == "Blog"
        assert items[1]["url"] == "/blog/"

    def test_nested_children(self):
        menus = [
            {
                "name": "Nav",
                "location": "header",
                "items": [
                    {
                        "title": "Services",
                        "url": "https://example.com/services/",
                        "children": [
                            {"title": "Web", "url": "https://example.com/services/web/"},
                        ],
                    }
                ],
            }
        ]
        nav = generate_navigation(menus, site_url="https://example.com")
        parent = nav["menus"][0]["items"][0]
        assert parent["label"] == "Services"
        assert len(parent["children"]) == 1
        assert parent["children"][0]["url"] == "/services/web/"

    def test_empty_menus(self):
        nav = generate_navigation([], site_url="https://example.com")
        assert nav["menus"] == []

    def test_external_urls_preserved(self):
        menus = [
            {
                "name": "Footer",
                "location": "footer",
                "items": [
                    {"title": "Twitter", "url": "https://twitter.com/example"},
                ],
            }
        ]
        nav = generate_navigation(menus, site_url="https://example.com")
        assert nav["menus"][0]["items"][0]["url"] == "https://twitter.com/example"

# ---------------------------------------------------------------------------
# Tests: _rewrite_url
# ---------------------------------------------------------------------------

class TestRewriteUrl:
    def test_strips_site_url(self):
        assert _rewrite_url("https://example.com/blog/", "https://example.com") == "/blog/"

    def test_root_url(self):
        assert _rewrite_url("https://example.com/", "https://example.com") == "/"

    def test_relative_url_unchanged(self):
        assert _rewrite_url("/about", "https://example.com") == "/about"

    def test_external_url_unchanged(self):
        assert _rewrite_url("https://other.com/page", "https://example.com") == "https://other.com/page"

    def test_empty_url(self):
        assert _rewrite_url("", "https://example.com") == "/"

# ---------------------------------------------------------------------------
# Tests: generate_redirects
# ---------------------------------------------------------------------------

class TestGenerateRedirects:
    def test_legacy_permalink_redirect(self):
        item = _make_content_item(
            slug="hello-world",
            legacy_permalink="/2024/01/hello-world/",
        )
        manifest = _make_manifest()
        redirects = generate_redirects([item], manifest, [])
        assert len(redirects) == 1
        assert redirects[0]["source"] == "/2024/01/hello-world"
        assert redirects[0]["destination"] == "/blog/hello-world"
        assert redirects[0]["status"] == 301

    def test_no_redirect_when_paths_match(self):
        item = _make_content_item(
            slug="hello-world",
            legacy_permalink="/blog/hello-world",
        )
        manifest = _make_manifest()
        redirects = generate_redirects([item], manifest, [])
        assert len(redirects) == 0

    def test_redirection_plugin_rules(self):
        rules = [
            {"source": "/old-page", "destination": "/new-page", "status": 302},
        ]
        redirects = generate_redirects([], _make_manifest(), rules)
        assert len(redirects) == 1
        assert redirects[0]["source"] == "/old-page"
        assert redirects[0]["destination"] == "/new-page"
        assert redirects[0]["status"] == 302

    def test_plugin_rules_alternate_keys(self):
        rules = [
            {"source_url": "/old", "target_url": "/new", "status_code": 307},
        ]
        redirects = generate_redirects([], _make_manifest(), rules)
        assert redirects[0]["source"] == "/old"
        assert redirects[0]["destination"] == "/new"
        assert redirects[0]["status"] == 307

    def test_combined_redirects(self):
        item = _make_content_item(
            slug="post-1",
            legacy_permalink="/2023/post-1/",
        )
        rules = [{"source": "/x", "destination": "/y", "status": 301}]
        redirects = generate_redirects([item], _make_manifest(), rules)
        assert len(redirects) == 2

    def test_no_schema_skips_item(self):
        item = _make_content_item(post_type="custom_type")
        redirects = generate_redirects([item], _make_manifest(), [])
        assert len(redirects) == 0

    def test_empty_legacy_permalink_skipped(self):
        item = _make_content_item(legacy_permalink="")
        redirects = generate_redirects([item], _make_manifest(), [])
        assert len(redirects) == 0

    def test_root_legacy_permalink_skipped(self):
        item = _make_content_item(legacy_permalink="/")
        redirects = generate_redirects([item], _make_manifest(), [])
        assert redirects == []

# ---------------------------------------------------------------------------
# Tests: _build_astro_route
# ---------------------------------------------------------------------------

class TestBuildAstroRoute:
    def test_replaces_slug(self):
        schema = _make_schema(route_pattern="/blog/[slug]")
        assert _build_astro_route(schema, "my-post") == "/blog/my-post"

    def test_nested_route(self):
        schema = _make_schema(route_pattern="/places/[slug]")
        assert _build_astro_route(schema, "paris") == "/places/paris"

# ---------------------------------------------------------------------------
# Tests: _safe_filename
# ---------------------------------------------------------------------------

class TestSafeFilename:
    def test_basic_url(self):
        assert _safe_filename("https://example.com/uploads/photo.jpg") == "photo.jpg"

    def test_url_with_query(self):
        assert _safe_filename("https://example.com/img.png?w=300") == "img.png"

    def test_empty_path(self):
        assert _safe_filename("https://example.com/") == "media_file"

# ---------------------------------------------------------------------------
# Tests: convert_content_item
# ---------------------------------------------------------------------------

class TestConvertContentItem:
    def test_basic_conversion(self):
        item = _make_content_item()
        manifest = _make_manifest()
        warnings: list[str] = []
        result = convert_content_item(item, manifest, {}, warnings)
        assert result is not None
        assert result.collection == "posts"
        assert result.slug == "hello-world"
        assert result.frontmatter["title"] == "Hello World"

    def test_slug_preserved(self):
        item = _make_content_item(slug="custom-slug-123")
        manifest = _make_manifest()
        result = convert_content_item(item, manifest, {}, [])
        assert result is not None
        assert result.slug == "custom-slug-123"
        assert result.frontmatter["slug"] == "custom-slug-123"

    def test_seo_in_frontmatter(self):
        item = _make_content_item(
            seo={"title": "SEO Title", "description": "SEO Desc"}
        )
        manifest = _make_manifest()
        result = convert_content_item(item, manifest, {}, [])
        assert result is not None
        assert result.frontmatter["seo_title"] == "SEO Title"
        assert result.frontmatter["meta_description"] == "SEO Desc"

    def test_legacy_url_in_frontmatter(self):
        item = _make_content_item(legacy_permalink="/old/path/")
        manifest = _make_manifest()
        result = convert_content_item(item, manifest, {}, [])
        assert result is not None
        assert result.frontmatter["legacy_url"] == "/old/path/"

    def test_no_schema_returns_none(self):
        item = _make_content_item(post_type="unknown_type")
        manifest = _make_manifest()
        warnings: list[str] = []
        result = convert_content_item(item, manifest, {}, warnings)
        assert result is None
        assert any("No collection schema" in w for w in warnings)

    def test_media_url_rewritten_in_body(self):
        item = _make_content_item(
            blocks=[
                WordPressBlock(
                    name="core/image",
                    attrs={"url": "https://wp.com/img.jpg", "alt": "photo"},
                    html='<img src="https://wp.com/img.jpg" alt="photo" />',
                )
            ]
        )
        # Use a manifest with only fallback components so markdown is used
        manifest = _make_manifest(components=[])
        media_map = {"https://wp.com/img.jpg": "/media/img.jpg"}
        result = convert_content_item(item, manifest, media_map, [])
        assert result is not None
        assert "https://wp.com/img.jpg" not in result.body
        assert "/media/img.jpg" in result.body

    def test_unsupported_block_warning(self):
        item = _make_content_item(
            blocks=[
                WordPressBlock(
                    name="plugin/custom-widget",
                    attrs={},
                    html="<div>Custom</div>",
                )
            ]
        )
        manifest = _make_manifest()
        warnings: list[str] = []
        convert_content_item(item, manifest, {}, warnings)
        assert any("Unsupported block type" in w and "plugin/custom-widget" in w for w in warnings)

    def test_uses_mdx_when_component_mappings_exist(self):
        item = _make_content_item()
        manifest = _make_manifest()
        result = convert_content_item(item, manifest, {}, [])
        assert result is not None
        assert result.file_extension == "mdx"

    def test_uses_md_when_no_component_mappings(self):
        item = _make_content_item()
        manifest = _make_manifest(
            components=[
                ComponentMapping(
                    wp_block_type="core/paragraph",
                    astro_component="FallbackHtml",
                    is_island=False,
                    hydration_directive=None,
                    props=[],
                    fallback=True,
                )
            ]
        )
        result = convert_content_item(item, manifest, {}, [])
        assert result is not None
        assert result.file_extension == "md"

    def test_featured_image_rewritten(self):
        item = _make_content_item(
            featured_media={"url": "https://wp.com/thumb.jpg"},
        )
        schema = _make_schema(
            frontmatter_fields=[
                FrontmatterField(name="title", type="string", required=True, description=""),
                FrontmatterField(name="featured_image", type="string", required=False, description=""),
            ]
        )
        manifest = _make_manifest(collections=[schema])
        media_map = {"https://wp.com/thumb.jpg": "/media/thumb.jpg"}
        result = convert_content_item(item, manifest, media_map, [])
        assert result is not None
        assert result.frontmatter["featured_image"] == "/media/thumb.jpg"

    def test_page_snapshot_body_and_body_class_preserved(self):
        item = _make_content_item(
            post_type="page",
            slug="plugins",
            title="Plugins",
            blocks=[],
            raw_html="",
            legacy_permalink="/plugins/",
        )
        schema = _make_schema(
            collection_name="pages",
            source_post_type="page",
            route_pattern="/[slug]",
        )
        manifest = _make_manifest(collections=[schema])
        snapshot_html = (
            '<html><body class="archive plugin-page">'
            '<main><div class="entry-content"><img src="https://example.com/wp-content/uploads/plugins.png" />'
            '<a href="https://example.com/contact/">Contact</a></div></main>'
            "</body></html>"
        )
        result = convert_content_item(
            item,
            manifest,
            {"https://example.com/wp-content/uploads/plugins.png": "/media/plugins.png"},
            [],
            html_snapshots={"/plugins": snapshot_html},
            site_url="https://example.com",
        )
        assert result is not None
        # Snapshot-based pages use .md (raw HTML breaks MDX's JSX parser)
        assert result.file_extension == "md"
        assert 'src="/media/plugins.png"' in result.body
        assert 'href="/contact/"' in result.body
        assert result.frontmatter["body_class"] == "archive plugin-page"

# ---------------------------------------------------------------------------
# Tests: ImporterAgent.execute
# ---------------------------------------------------------------------------

class TestImporterAgentExecute:
    @pytest.mark.asyncio
    async def test_successful_execution(self):
        agent = ImporterAgent(gradient_client=_make_gradient_client())
        item = _make_content_item()
        ctx = _make_context(content_items=[item.model_dump()])
        result = await agent.execute(ctx)
        assert result.agent_name == "importer"
        assert "content_files" in result.artifacts
        assert "media_map" in result.artifacts
        assert "navigation" in result.artifacts
        assert "redirects" in result.artifacts

    @pytest.mark.asyncio
    async def test_content_files_generated(self):
        agent = ImporterAgent(gradient_client=_make_gradient_client())
        item = _make_content_item()
        ctx = _make_context(content_items=[item.model_dump()])
        result = await agent.execute(ctx)
        files = result.artifacts["content_files"]
        assert len(files) == 1
        path = list(files.keys())[0]
        assert path.startswith("src/content/posts/")
        assert "hello-world" in path

    @pytest.mark.asyncio
    async def test_content_has_frontmatter(self):
        agent = ImporterAgent(gradient_client=_make_gradient_client())
        item = _make_content_item()
        ctx = _make_context(content_items=[item.model_dump()])
        result = await agent.execute(ctx)
        files = result.artifacts["content_files"]
        content = list(files.values())[0]
        assert content.startswith("---\n")
        assert "title: Hello World" in content

    @pytest.mark.asyncio
    async def test_seo_metadata_in_output(self):
        agent = ImporterAgent(gradient_client=_make_gradient_client())
        item = _make_content_item(
            seo={"title": "My SEO Title", "description": "My meta desc"}
        )
        ctx = _make_context(content_items=[item.model_dump()])
        result = await agent.execute(ctx)
        content = list(result.artifacts["content_files"].values())[0]
        assert "seo_title: My SEO Title" in content
        assert "meta_description: My meta desc" in content

    @pytest.mark.asyncio
    async def test_media_map_generated(self):
        agent = ImporterAgent(gradient_client=_make_gradient_client())
        item = _make_content_item(
            blocks=[
                WordPressBlock(
                    name="core/image",
                    attrs={},
                    html='<img src="https://wp.com/uploads/pic.jpg" />',
                )
            ]
        )
        ctx = _make_context(
            content_items=[item.model_dump()],
            media_manifest=[
                {
                    "source_url": "https://wp.com/uploads/pic.jpg",
                    "bundle_path": "media/2024/01/pic.jpg",
                    "artifact_path": "media/2024/01/pic.jpg",
                    "filename": "pic.jpg",
                }
            ],
        )
        result = await agent.execute(ctx)
        media_map = result.artifacts["media_map"]
        assert media_map == {
            "https://wp.com/uploads/pic.jpg": "/media/2024/01/pic.jpg"
        }

    @pytest.mark.asyncio
    async def test_media_urls_rewritten_in_content_when_manifest_present(self):
        agent = ImporterAgent(gradient_client=_make_gradient_client())
        item = _make_content_item(
            blocks=[
                WordPressBlock(
                    name="core/image",
                    attrs={"url": "https://wp.com/uploads/pic.jpg", "alt": "pic"},
                    html='<img src="https://wp.com/uploads/pic.jpg" alt="pic" />',
                )
            ],
            raw_html='<img src="https://wp.com/uploads/pic.jpg" alt="pic" />',
        )
        # Use manifest with no non-fallback components so markdown path is used
        ctx = _make_context(
            content_items=[item.model_dump()],
            manifest=_make_manifest(components=[]),
            media_manifest=[
                {
                    "source_url": "https://wp.com/uploads/pic.jpg",
                    "bundle_path": "media/uploads/pic.jpg",
                    "artifact_path": "media/uploads/pic.jpg",
                    "filename": "pic.jpg",
                }
            ],
        )
        result = await agent.execute(ctx)
        content = list(result.artifacts["content_files"].values())[0]
        assert "https://wp.com/uploads/pic.jpg" not in content
        assert "/media/uploads/pic.jpg" in content

    @pytest.mark.asyncio
    async def test_page_snapshot_used_during_agent_execution(self):
        agent = ImporterAgent(gradient_client=_make_gradient_client())
        item = _make_content_item(
            post_type="page",
            slug="plugins",
            title="Plugins",
            blocks=[],
            raw_html="",
            legacy_permalink="/plugins/",
        )
        manifest = _make_manifest(
            collections=[
                _make_schema(
                    collection_name="pages",
                    source_post_type="page",
                    route_pattern="/[slug]",
                )
            ]
        )
        result = await agent.execute(
            _make_context(
                manifest=manifest,
                content_items=[item.model_dump()],
                html_snapshots={
                    "/plugins": '<html><body class="archive geodir"><main><div class="entry-content"><p>Snapshot body</p></div></main></body></html>'
                },
            )
        )
        content = result.artifacts["content_files"]["src/content/pages/plugins.md"]
        assert "Snapshot body" in content
        assert "body_class: archive geodir" in content

    @pytest.mark.asyncio
    async def test_media_urls_left_unchanged_when_manifest_missing(self):
        agent = ImporterAgent(gradient_client=_make_gradient_client())
        item = _make_content_item(
            blocks=[
                WordPressBlock(
                    name="core/image",
                    attrs={"url": "https://wp.com/uploads/pic.jpg", "alt": "pic"},
                    html='<img src="https://wp.com/uploads/pic.jpg" alt="pic" />',
                )
            ],
            raw_html='<img src="https://wp.com/uploads/pic.jpg" alt="pic" />',
        )
        ctx = _make_context(
            content_items=[item.model_dump()],
            manifest=_make_manifest(components=[]),
        )
        result = await agent.execute(ctx)
        content = list(result.artifacts["content_files"].values())[0]
        assert "https://wp.com/uploads/pic.jpg" in content
        assert result.artifacts["media_map"] == {}

    @pytest.mark.asyncio
    async def test_navigation_generated(self):
        agent = ImporterAgent(gradient_client=_make_gradient_client())
        menus = [
            {
                "name": "Main",
                "location": "primary",
                "items": [
                    {"title": "Home", "url": "https://example.com/"},
                ],
            }
        ]
        ctx = _make_context(menus=menus)
        result = await agent.execute(ctx)
        nav = result.artifacts["navigation"]
        assert len(nav["menus"]) == 1
        assert nav["menus"][0]["items"][0]["label"] == "Home"

    @pytest.mark.asyncio
    async def test_redirects_generated(self):
        agent = ImporterAgent(gradient_client=_make_gradient_client())
        item = _make_content_item(legacy_permalink="/2024/01/hello-world/")
        ctx = _make_context(content_items=[item.model_dump()])
        result = await agent.execute(ctx)
        redirects = result.artifacts["redirects"]
        assert len(redirects) >= 1
        assert redirects[0]["source"] == "/2024/01/hello-world"

    @pytest.mark.asyncio
    async def test_redirect_plugin_rules_included(self):
        agent = ImporterAgent(gradient_client=_make_gradient_client())
        rules = [{"source": "/old", "destination": "/new", "status": 302}]
        ctx = _make_context(redirect_rules=rules)
        result = await agent.execute(ctx)
        redirects = result.artifacts["redirects"]
        assert any(r["source"] == "/old" for r in redirects)

    @pytest.mark.asyncio
    async def test_malformed_content_skipped(self):
        agent = ImporterAgent(gradient_client=_make_gradient_client())
        # One valid, one malformed (missing required fields)
        valid = _make_content_item().model_dump()
        malformed = {"id": 99, "title": "Bad"}  # missing many required fields
        ctx = _make_context(content_items=[valid, malformed])
        result = await agent.execute(ctx)
        # Should have processed the valid item
        assert len(result.artifacts["content_files"]) == 1
        # Should have a warning about the malformed item
        assert any("Malformed content item" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_unsupported_block_fallback_warning(self):
        agent = ImporterAgent(gradient_client=_make_gradient_client())
        item = _make_content_item(
            blocks=[
                WordPressBlock(
                    name="vendor/exotic-block",
                    attrs={},
                    html="<div>Exotic</div>",
                )
            ]
        )
        ctx = _make_context(content_items=[item.model_dump()])
        result = await agent.execute(ctx)
        assert any(
            "Unsupported block type" in w and "vendor/exotic-block" in w
            for w in result.warnings
        )

    @pytest.mark.asyncio
    async def test_slug_preserved_in_file_path(self):
        agent = ImporterAgent(gradient_client=_make_gradient_client())
        item = _make_content_item(slug="my-unique-slug")
        ctx = _make_context(content_items=[item.model_dump()])
        result = await agent.execute(ctx)
        paths = list(result.artifacts["content_files"].keys())
        assert any("my-unique-slug" in p for p in paths)

    @pytest.mark.asyncio
    async def test_duration_recorded(self):
        agent = ImporterAgent(gradient_client=_make_gradient_client())
        ctx = _make_context()
        result = await agent.execute(ctx)
        assert result.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_content_items_as_model_instances(self):
        agent = ImporterAgent(gradient_client=_make_gradient_client())
        item = _make_content_item()
        ctx = _make_context(content_items=[item])  # pass model instance directly
        result = await agent.execute(ctx)
        assert len(result.artifacts["content_files"]) == 1

    @pytest.mark.asyncio
    async def test_inventory_from_dict(self):
        agent = ImporterAgent(gradient_client=_make_gradient_client())
        item = _make_content_item()
        menus = [
            {
                "name": "Nav",
                "location": "primary",
                "items": [
                    {"title": "Home", "url": "https://mysite.org/"},
                ],
            }
        ]
        ctx = _make_context(
            content_items=[item.model_dump()],
            menus=menus,
            inventory={"site_url": "https://mysite.org"},
        )
        result = await agent.execute(ctx)
        nav = result.artifacts["navigation"]
        assert nav["menus"][0]["items"][0]["url"] == "/"

    @pytest.mark.asyncio
    async def test_empty_content_items(self):
        agent = ImporterAgent(gradient_client=_make_gradient_client())
        ctx = _make_context(content_items=[])
        result = await agent.execute(ctx)
        assert result.artifacts["content_files"] == {}
        assert result.artifacts["media_map"] == {}

    @pytest.mark.asyncio
    async def test_multiple_content_items(self):
        agent = ImporterAgent(gradient_client=_make_gradient_client())
        items = [
            _make_content_item(id=1, slug="post-one").model_dump(),
            _make_content_item(id=2, slug="post-two").model_dump(),
        ]
        ctx = _make_context(content_items=items)
        result = await agent.execute(ctx)
        assert len(result.artifacts["content_files"]) == 2

    @pytest.mark.asyncio
    async def test_updates_astro_project_and_zip_with_generated_content(self):
        agent = ImporterAgent(gradient_client=_make_gradient_client())
        item = _make_content_item()
        ctx = _make_context(
            content_items=[item.model_dump()],
            astro_project={"package.json": "{\"name\": \"site\"}\n"},
        )
        result = await agent.execute(ctx)

        assert "astro_project" in result.artifacts
        project = result.artifacts["astro_project"]
        assert "package.json" in project
        assert any(path.startswith("src/content/posts/") for path in project)

        import io
        import zipfile

        with zipfile.ZipFile(io.BytesIO(result.artifacts["astro_project_zip"]), "r") as zf:
            assert "package.json" in zf.namelist()
            assert any(name.startswith("src/content/posts/") for name in zf.namelist())
