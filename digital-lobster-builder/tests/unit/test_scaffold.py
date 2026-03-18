from __future__ import annotations

import json
import zipfile
import io

import pytest
from unittest.mock import AsyncMock
from typing import Any

from src.agents.scaffold import (
    ScaffoldAgent,
    generate_astro_config,
    generate_cms_index_page,
    generate_cms_route_page,
    generate_package_json,
    generate_tsconfig,
    generate_route_page,
    generate_index_page,
    generate_home_page,
    generate_component,
    generate_island_usage,
    generate_base_layout_with_seo,
    generate_readme,
    package_as_zip,
    _extract_inventory,
    _extract_modeling_manifest,
    _extract_theme_layouts,
    _slugify,
    _to_kebab,
    _route_prefix,
    _route_dir,
)
from src.models.inventory import (
    Inventory,
    ThemeMetadata,
    ContentTypeSummary,
    TaxonomySummary,
    MenuSummary,
)
from src.models.modeling_manifest import (
    ModelingManifest,
    ContentCollectionSchema,
    ComponentMapping,
    FrontmatterField,
    TaxonomyDefinition,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_inventory(**overrides: Any) -> Inventory:
    defaults: dict[str, Any] = {
        "site_url": "https://example.com",
        "site_name": "Test Site",
        "wordpress_version": "6.4",
        "content_types": [
            ContentTypeSummary(
                post_type="post",
                count=10,
                custom_fields=[],
                taxonomies=["category"],
                sample_slugs=["hello-world"],
            ),
        ],
        "plugins": [],
        "taxonomies": [
            TaxonomySummary(
                taxonomy="category",
                term_count=3,
                associated_post_types=["post"],
            ),
        ],
        "menus": [
            MenuSummary(name="Primary", location="primary", item_count=5),
        ],
        "theme": ThemeMetadata(
            name="twentytwentyfour",
            has_theme_json=True,
            has_custom_css=True,
            design_tokens=None,
        ),
        "has_html_snapshots": True,
        "has_media_manifest": False,
        "has_redirect_rules": False,
        "has_seo_data": False,
    }
    defaults.update(overrides)
    return Inventory(**defaults)

def _make_manifest(**overrides: Any) -> ModelingManifest:
    defaults: dict[str, Any] = {
        "collections": [
            ContentCollectionSchema(
                collection_name="posts",
                source_post_type="post",
                frontmatter_fields=[
                    FrontmatterField(name="title", type="string", required=True, description="Post title"),
                    FrontmatterField(name="date", type="date", required=True, description="Publish date"),
                    FrontmatterField(name="description", type="string", required=False, description="Excerpt"),
                ],
                route_pattern="/blog/[slug]",
            ),
        ],
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
        "taxonomies": [
            TaxonomyDefinition(
                taxonomy="category",
                collection_ref="posts",
                data_file=None,
            ),
        ],
    }
    defaults.update(overrides)
    return ModelingManifest(**defaults)

def _make_gradient_client() -> AsyncMock:
    client = AsyncMock()
    client.complete = AsyncMock(return_value="{}")
    return client

def _make_island_component(**overrides: Any) -> ComponentMapping:
    defaults = {
        "wp_block_type": "geodirectory/map",
        "astro_component": "GeoMap",
        "is_island": True,
        "hydration_directive": "client:visible",
        "props": [{"name": "lat", "type": "number"}, {"name": "lng", "type": "number"}],
        "fallback": False,
    }
    defaults.update(overrides)
    return ComponentMapping(**defaults)

def _make_fallback_component(**overrides: Any) -> ComponentMapping:
    defaults = {
        "wp_block_type": "unknown/widget",
        "astro_component": "UnknownWidget",
        "is_island": False,
        "hydration_directive": None,
        "props": [],
        "fallback": True,
    }
    defaults.update(overrides)
    return ComponentMapping(**defaults)

# ---------------------------------------------------------------------------
# Context extraction tests
# ---------------------------------------------------------------------------

class TestExtractInventory:
    def test_from_instance(self):
        inv = _make_inventory()
        result = _extract_inventory({"inventory": inv})
        assert result.site_name == "Test Site"

    def test_from_dict(self):
        inv = _make_inventory()
        result = _extract_inventory({"inventory": inv.model_dump()})
        assert result.site_url == "https://example.com"

    def test_missing_raises(self):
        with pytest.raises(KeyError):
            _extract_inventory({})

class TestExtractModelingManifest:
    def test_from_instance(self):
        m = _make_manifest()
        result = _extract_modeling_manifest({"modeling_manifest": m})
        assert len(result.collections) == 1

    def test_from_dict(self):
        m = _make_manifest()
        result = _extract_modeling_manifest({"modeling_manifest": m.model_dump()})
        assert result.collections[0].collection_name == "posts"

    def test_missing_raises(self):
        with pytest.raises(KeyError):
            _extract_modeling_manifest({})

class TestExtractThemeLayouts:
    def test_from_layouts_key(self):
        layouts = {"BaseLayout.astro": "<html></html>"}
        result = _extract_theme_layouts({"layouts": layouts})
        assert "BaseLayout.astro" in result

    def test_from_theme_layouts_key(self):
        layouts = {"BaseLayout.astro": "<html></html>"}
        result = _extract_theme_layouts({"theme_layouts": layouts})
        assert "BaseLayout.astro" in result

    def test_empty_when_missing(self):
        result = _extract_theme_layouts({})
        assert result == {}

# ---------------------------------------------------------------------------
# astro.config.mjs generation
# ---------------------------------------------------------------------------

class TestGenerateAstroConfig:
    def test_contains_static_output(self):
        config = generate_astro_config("https://example.com")
        assert "output: 'static'" in config

    def test_contains_site_url(self):
        config = generate_astro_config("https://mysite.org")
        assert "site: 'https://mysite.org'" in config

    def test_contains_mdx_integration(self):
        config = generate_astro_config("https://example.com")
        assert "mdx" in config
        assert "@astrojs/mdx" in config


class TestGenerateCmsPages:
    def test_route_page_uses_rest_endpoint(self):
        page = generate_cms_route_page("posts", "/api/posts", "/blog/[slug]")
        assert "fetchAllPages<Posts>('/api/posts')" in page

    def test_index_page_uses_rest_endpoint(self):
        page = generate_cms_index_page("posts", "/api/posts", "/blog/[slug]")
        assert "fetchAllPages<Posts>('/api/posts')" in page

    def test_contains_define_config(self):
        config = generate_astro_config("https://example.com")
        assert "defineConfig" in config

# ---------------------------------------------------------------------------
# package.json generation
# ---------------------------------------------------------------------------

class TestGeneratePackageJson:
    def test_has_astro_5x_dependency(self):
        pkg_str = generate_package_json("Test Site")
        pkg = json.loads(pkg_str)
        assert "astro" in pkg["dependencies"]
        assert pkg["dependencies"]["astro"].startswith("^5")

    def test_has_mdx_integration(self):
        pkg_str = generate_package_json("Test Site")
        pkg = json.loads(pkg_str)
        assert "@astrojs/mdx" in pkg["dependencies"]

    def test_has_build_script(self):
        pkg_str = generate_package_json("Test Site")
        pkg = json.loads(pkg_str)
        assert "build" in pkg["scripts"]
        assert "astro build" in pkg["scripts"]["build"]

    def test_slugified_name(self):
        pkg_str = generate_package_json("My Awesome Site!")
        pkg = json.loads(pkg_str)
        assert pkg["name"] == "my-awesome-site"

    def test_valid_json(self):
        pkg_str = generate_package_json("Test")
        json.loads(pkg_str)  # Should not raise

# ---------------------------------------------------------------------------
# tsconfig.json generation
# ---------------------------------------------------------------------------

class TestGenerateTsconfig:
    def test_extends_astro_strict(self):
        ts = generate_tsconfig()
        cfg = json.loads(ts)
        assert cfg["extends"] == "astro/tsconfigs/strict"

# ---------------------------------------------------------------------------
# Route page generation
# ---------------------------------------------------------------------------

class TestGenerateRoutePage:
    def test_contains_get_static_paths(self):
        coll = _make_manifest().collections[0]
        page = generate_route_page(coll)
        assert "getStaticPaths" in page

    def test_references_collection_name(self):
        coll = _make_manifest().collections[0]
        page = generate_route_page(coll)
        assert "posts" in page

    def test_uses_post_layout(self):
        coll = _make_manifest().collections[0]
        page = generate_route_page(coll)
        assert "PostLayout" in page

class TestGenerateIndexPage:
    def test_references_collection(self):
        coll = _make_manifest().collections[0]
        page = generate_index_page(coll)
        assert "posts" in page

    def test_contains_list(self):
        coll = _make_manifest().collections[0]
        page = generate_index_page(coll)
        assert "<ul>" in page

    def test_uses_page_layout(self):
        coll = _make_manifest().collections[0]
        page = generate_index_page(coll)
        assert "PageLayout" in page

class TestGenerateHomePage:
    def test_contains_site_name(self):
        colls = _make_manifest().collections
        page = generate_home_page("My Site", colls)
        assert "My Site" in page

    def test_links_to_collections(self):
        colls = _make_manifest().collections
        page = generate_home_page("My Site", colls)
        assert "/blog" in page

# ---------------------------------------------------------------------------
# Component generation
# ---------------------------------------------------------------------------

class TestGenerateComponent:
    def test_static_component(self):
        mapping = _make_manifest().components[0]
        comp = generate_component(mapping)
        assert "paragraph" in comp.lower()
        assert "client:" not in comp

    def test_island_component_has_directive_comment(self):
        mapping = _make_island_component()
        comp = generate_component(mapping)
        assert "client:visible" in comp
        assert "data-island" in comp

    def test_island_default_directive(self):
        mapping = _make_island_component(hydration_directive=None)
        comp = generate_component(mapping)
        assert "client:load" in comp

    def test_fallback_component(self):
        mapping = _make_fallback_component()
        comp = generate_component(mapping)
        assert "wp-block-fallback" in comp
        assert "set:html" in comp
        assert mapping.wp_block_type in comp

    def test_component_with_props(self):
        mapping = _make_island_component()
        comp = generate_component(mapping)
        assert "lat" in comp
        assert "lng" in comp

class TestGenerateIslandUsage:
    def test_includes_directive(self):
        mapping = _make_island_component()
        usage = generate_island_usage(mapping)
        assert "client:visible" in usage
        assert "GeoMap" in usage

    def test_default_directive(self):
        mapping = _make_island_component(hydration_directive=None)
        usage = generate_island_usage(mapping)
        assert "client:load" in usage

# ---------------------------------------------------------------------------
# Base layout with SEO
# ---------------------------------------------------------------------------

class TestGenerateBaseLayoutWithSeo:
    def test_fresh_layout_has_og_tags(self):
        layout = generate_base_layout_with_seo("Test", {})
        assert 'og:title' in layout
        assert 'og:description' in layout
        assert 'og:url' in layout

    def test_fresh_layout_has_canonical(self):
        layout = generate_base_layout_with_seo("Test", {})
        assert 'canonical' in layout

    def test_fresh_layout_has_meta_description(self):
        layout = generate_base_layout_with_seo("Test", {})
        assert 'name="description"' in layout

    def test_fresh_layout_has_viewport(self):
        layout = generate_base_layout_with_seo("Test", {})
        assert 'name="viewport"' in layout

    def test_injects_into_existing_layout(self):
        existing = """---
const { title = "Site" } = Astro.props;
---
<!DOCTYPE html>
<html>
  <head>
    <title>{title}</title>
  </head>
  <body><slot /></body>
</html>
"""
        layout = generate_base_layout_with_seo("Test", {"BaseLayout.astro": existing})
        assert 'og:title' in layout
        assert 'canonical' in layout

    def test_site_name_in_fresh_layout(self):
        layout = generate_base_layout_with_seo("My Cool Site", {})
        assert "My Cool Site" in layout

# ---------------------------------------------------------------------------
# README generation
# ---------------------------------------------------------------------------

class TestGenerateReadme:
    def test_contains_site_name(self):
        readme = generate_readme("Test Site", "https://example.com")
        assert "Test Site" in readme

    def test_contains_build_instructions(self):
        readme = generate_readme("Test", "https://example.com")
        assert "npm run build" in readme
        assert "npm install" in readme

    def test_contains_site_url(self):
        readme = generate_readme("Test", "https://example.com")
        assert "https://example.com" in readme

    def test_contains_project_structure(self):
        readme = generate_readme("Test", "https://example.com")
        assert "src/" in readme
        assert "layouts/" in readme

    def test_contains_deployment_guidance(self):
        readme = generate_readme("Test", "https://example.com")
        assert "Deployment" in readme or "deploy" in readme.lower()

# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

class TestSlugify:
    def test_basic(self):
        assert _slugify("My Site") == "my-site"

    def test_special_chars(self):
        assert _slugify("Hello World!") == "hello-world"

    def test_empty(self):
        assert _slugify("") == "astro-site"

    def test_already_slug(self):
        assert _slugify("my-site") == "my-site"

class TestToKebab:
    def test_pascal_case(self):
        assert _to_kebab("GeoMap") == "geo-map"

    def test_single_word(self):
        assert _to_kebab("Paragraph") == "paragraph"

class TestRoutePrefix:
    def test_with_slug(self):
        assert _route_prefix("/blog/[slug]") == "/blog"

    def test_root_slug(self):
        assert _route_prefix("/[slug]") == "/"

    def test_nested(self):
        assert _route_prefix("/places/reviews/[slug]") == "/places/reviews"

class TestRouteDir:
    def test_blog(self):
        assert _route_dir("/blog/[slug]") == "blog"

    def test_root(self):
        assert _route_dir("/[slug]") == ""

    def test_nested(self):
        assert _route_dir("/places/reviews/[slug]") == "places/reviews"

# ---------------------------------------------------------------------------
# ZIP packaging
# ---------------------------------------------------------------------------

class TestPackageAsZip:
    def test_produces_valid_zip(self):
        project = {"file.txt": "hello", "src/main.ts": "console.log('hi');"}
        data = package_as_zip(project)
        buf = io.BytesIO(data)
        with zipfile.ZipFile(buf, "r") as zf:
            assert "file.txt" in zf.namelist()
            assert "src/main.ts" in zf.namelist()

    def test_content_preserved(self):
        project = {"test.txt": "content here"}
        data = package_as_zip(project)
        buf = io.BytesIO(data)
        with zipfile.ZipFile(buf, "r") as zf:
            assert zf.read("test.txt").decode() == "content here"

    def test_empty_project(self):
        data = package_as_zip({})
        buf = io.BytesIO(data)
        with zipfile.ZipFile(buf, "r") as zf:
            assert zf.namelist() == []

# ---------------------------------------------------------------------------
# ScaffoldAgent.execute integration tests
# ---------------------------------------------------------------------------

class TestScaffoldAgentExecute:
    @pytest.mark.asyncio
    async def test_successful_execution(self):
        agent = ScaffoldAgent(gradient_client=_make_gradient_client())
        context = {
            "inventory": _make_inventory(),
            "modeling_manifest": _make_manifest(),
        }
        result = await agent.execute(context)
        assert result.agent_name == "scaffold"
        assert "astro_project" in result.artifacts
        assert "astro_project_zip" in result.artifacts

    @pytest.mark.asyncio
    async def test_astro_config_has_static_output(self):
        agent = ScaffoldAgent(gradient_client=_make_gradient_client())
        context = {
            "inventory": _make_inventory(),
            "modeling_manifest": _make_manifest(),
        }
        result = await agent.execute(context)
        project = result.artifacts["astro_project"]
        assert "astro.config.mjs" in project
        assert "output: 'static'" in project["astro.config.mjs"]

    @pytest.mark.asyncio
    async def test_astro_config_has_site_url(self):
        agent = ScaffoldAgent(gradient_client=_make_gradient_client())
        context = {
            "inventory": _make_inventory(site_url="https://mysite.org"),
            "modeling_manifest": _make_manifest(),
        }
        result = await agent.execute(context)
        project = result.artifacts["astro_project"]
        assert "https://mysite.org" in project["astro.config.mjs"]

    @pytest.mark.asyncio
    async def test_package_json_has_astro_5x(self):
        agent = ScaffoldAgent(gradient_client=_make_gradient_client())
        context = {
            "inventory": _make_inventory(),
            "modeling_manifest": _make_manifest(),
        }
        result = await agent.execute(context)
        project = result.artifacts["astro_project"]
        pkg = json.loads(project["package.json"])
        assert pkg["dependencies"]["astro"].startswith("^5")

    @pytest.mark.asyncio
    async def test_route_files_generated_for_each_collection(self):
        collections = [
            ContentCollectionSchema(
                collection_name="posts",
                source_post_type="post",
                frontmatter_fields=[
                    FrontmatterField(name="title", type="string", required=True, description="Title"),
                ],
                route_pattern="/blog/[slug]",
            ),
            ContentCollectionSchema(
                collection_name="places",
                source_post_type="gd_place",
                frontmatter_fields=[
                    FrontmatterField(name="title", type="string", required=True, description="Title"),
                ],
                route_pattern="/places/[slug]",
            ),
        ]
        manifest = _make_manifest(collections=collections)
        agent = ScaffoldAgent(gradient_client=_make_gradient_client())
        context = {
            "inventory": _make_inventory(),
            "modeling_manifest": manifest,
        }
        result = await agent.execute(context)
        project = result.artifacts["astro_project"]
        assert "src/pages/blog/[slug].astro" in project
        assert "src/pages/blog/index.astro" in project
        assert "src/pages/places/[slug].astro" in project
        assert "src/pages/places/index.astro" in project

    @pytest.mark.asyncio
    async def test_root_slug_route_uses_correct_layout_import(self):
        manifest = _make_manifest(
            collections=[
                ContentCollectionSchema(
                    collection_name="pages",
                    source_post_type="page",
                    frontmatter_fields=[
                        FrontmatterField(name="title", type="string", required=True, description="Title"),
                    ],
                    route_pattern="/[slug]",
                )
            ]
        )
        agent = ScaffoldAgent(gradient_client=_make_gradient_client())
        context = {
            "inventory": _make_inventory(),
            "modeling_manifest": manifest,
        }
        result = await agent.execute(context)
        project = result.artifacts["astro_project"]
        route_file = project["src/pages/[slug].astro"]
        assert "import PostLayout from '../layouts/PostLayout.astro';" in route_file

    @pytest.mark.asyncio
    async def test_root_collection_does_not_overwrite_home_page(self):
        manifest = _make_manifest(
            collections=[
                ContentCollectionSchema(
                    collection_name="pages",
                    source_post_type="page",
                    frontmatter_fields=[
                        FrontmatterField(name="title", type="string", required=True, description="Title"),
                    ],
                    route_pattern="/[slug]",
                )
            ]
        )
        agent = ScaffoldAgent(gradient_client=_make_gradient_client())
        result = await agent.execute(
            {"inventory": _make_inventory(), "modeling_manifest": manifest}
        )
        project = result.artifacts["astro_project"]
        assert "Test Site" in project["src/pages/index.astro"]
        assert any("Skipped generating collection index for root route pattern" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_theme_assets_written_to_public_styles(self):
        agent = ScaffoldAgent(gradient_client=_make_gradient_client())
        context = {
            "inventory": _make_inventory(),
            "modeling_manifest": _make_manifest(),
            "theme_css": {"style.css": "body { color: red; }"},
            "tokens_css": ":root { --wp-color-primary: #f00; }",
        }
        result = await agent.execute(context)
        project = result.artifacts["astro_project"]
        assert project["public/styles/style.css"] == "body { color: red; }"
        assert "public/styles/tokens.css" in project

    @pytest.mark.asyncio
    async def test_media_assets_written_to_public_media_with_nested_paths(self):
        agent = ScaffoldAgent(gradient_client=_make_gradient_client())
        context = {
            "inventory": _make_inventory(has_media_manifest=True),
            "modeling_manifest": _make_manifest(),
            "export_bundle": {
                "media/2024/01/photo.jpg": b"jpeg-bytes",
            },
            "media_manifest": [
                {
                    "source_url": "https://example.com/wp-content/uploads/2024/01/photo.jpg",
                    "bundle_path": "media/2024/01/photo.jpg",
                    "artifact_path": "media/2024/01/photo.jpg",
                    "filename": "photo.jpg",
                }
            ],
        }
        result = await agent.execute(context)
        project = result.artifacts["astro_project"]
        assert project["public/media/2024/01/photo.jpg"] == b"jpeg-bytes"

    @pytest.mark.asyncio
    async def test_missing_media_asset_emits_warning(self):
        agent = ScaffoldAgent(gradient_client=_make_gradient_client())
        context = {
            "inventory": _make_inventory(has_media_manifest=True),
            "modeling_manifest": _make_manifest(),
            "export_bundle": {},
            "media_manifest": [
                {
                    "source_url": "https://example.com/wp-content/uploads/2024/01/photo.jpg",
                    "bundle_path": "media/2024/01/photo.jpg",
                    "artifact_path": "media/2024/01/photo.jpg",
                    "filename": "photo.jpg",
                }
            ],
        }
        result = await agent.execute(context)
        assert any(
            "Media asset missing from export bundle: media/2024/01/photo.jpg" in warning
            for warning in result.warnings
        )

    @pytest.mark.asyncio
    async def test_island_components_get_hydration_directives(self):
        components = [
            _make_island_component(),
            ComponentMapping(
                wp_block_type="core/paragraph",
                astro_component="Paragraph",
                is_island=False,
                hydration_directive=None,
                props=[],
                fallback=False,
            ),
        ]
        manifest = _make_manifest(components=components)
        agent = ScaffoldAgent(gradient_client=_make_gradient_client())
        context = {
            "inventory": _make_inventory(),
            "modeling_manifest": manifest,
        }
        result = await agent.execute(context)
        project = result.artifacts["astro_project"]
        geo_comp = project["src/components/GeoMap.astro"]
        assert "client:visible" in geo_comp
        para_comp = project["src/components/Paragraph.astro"]
        assert "client:" not in para_comp

    @pytest.mark.asyncio
    async def test_components_generated_from_mappings(self):
        components = [
            ComponentMapping(
                wp_block_type="core/heading",
                astro_component="Heading",
                is_island=False,
                hydration_directive=None,
                props=[{"name": "level", "type": "number"}],
                fallback=False,
            ),
        ]
        manifest = _make_manifest(components=components)
        agent = ScaffoldAgent(gradient_client=_make_gradient_client())
        context = {
            "inventory": _make_inventory(),
            "modeling_manifest": manifest,
        }
        result = await agent.execute(context)
        project = result.artifacts["astro_project"]
        assert "src/components/Heading.astro" in project
        assert "level" in project["src/components/Heading.astro"]

    @pytest.mark.asyncio
    async def test_theme_layouts_included(self):
        theme_layouts = {
            "BaseLayout.astro": """---
const { title = "Site" } = Astro.props;
---
<html><head><title>{title}</title></head><body><slot /></body></html>
""",
            "PageLayout.astro": "<div>Page</div>",
            "PostLayout.astro": "<div>Post</div>",
        }
        agent = ScaffoldAgent(gradient_client=_make_gradient_client())
        context = {
            "inventory": _make_inventory(),
            "modeling_manifest": _make_manifest(),
            "layouts": theme_layouts,
        }
        result = await agent.execute(context)
        project = result.artifacts["astro_project"]
        assert "src/layouts/BaseLayout.astro" in project
        assert "src/layouts/PageLayout.astro" in project
        assert "src/layouts/PostLayout.astro" in project

    @pytest.mark.asyncio
    async def test_readme_generated(self):
        agent = ScaffoldAgent(gradient_client=_make_gradient_client())
        context = {
            "inventory": _make_inventory(),
            "modeling_manifest": _make_manifest(),
        }
        result = await agent.execute(context)
        project = result.artifacts["astro_project"]
        assert "README.md" in project
        assert "npm run build" in project["README.md"]

    @pytest.mark.asyncio
    async def test_zip_packaging(self):
        agent = ScaffoldAgent(gradient_client=_make_gradient_client())
        context = {
            "inventory": _make_inventory(),
            "modeling_manifest": _make_manifest(),
        }
        result = await agent.execute(context)
        zip_bytes = result.artifacts["astro_project_zip"]
        assert isinstance(zip_bytes, bytes)
        buf = io.BytesIO(zip_bytes)
        with zipfile.ZipFile(buf, "r") as zf:
            names = zf.namelist()
            assert "astro.config.mjs" in names
            assert "package.json" in names
            assert "README.md" in names

    @pytest.mark.asyncio
    async def test_og_tags_in_base_layout(self):
        agent = ScaffoldAgent(gradient_client=_make_gradient_client())
        context = {
            "inventory": _make_inventory(),
            "modeling_manifest": _make_manifest(),
        }
        result = await agent.execute(context)
        project = result.artifacts["astro_project"]
        base = project["src/layouts/BaseLayout.astro"]
        assert "og:title" in base
        assert "og:description" in base
        assert "og:url" in base

    @pytest.mark.asyncio
    async def test_canonical_url_in_base_layout(self):
        agent = ScaffoldAgent(gradient_client=_make_gradient_client())
        context = {
            "inventory": _make_inventory(),
            "modeling_manifest": _make_manifest(),
        }
        result = await agent.execute(context)
        project = result.artifacts["astro_project"]
        base = project["src/layouts/BaseLayout.astro"]
        assert "canonical" in base

    @pytest.mark.asyncio
    async def test_duration_recorded(self):
        agent = ScaffoldAgent(gradient_client=_make_gradient_client())
        context = {
            "inventory": _make_inventory(),
            "modeling_manifest": _make_manifest(),
        }
        result = await agent.execute(context)
        assert result.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_inventory_from_dict(self):
        agent = ScaffoldAgent(gradient_client=_make_gradient_client())
        context = {
            "inventory": _make_inventory().model_dump(),
            "modeling_manifest": _make_manifest().model_dump(),
        }
        result = await agent.execute(context)
        assert result.agent_name == "scaffold"

    @pytest.mark.asyncio
    async def test_content_config_generated(self):
        agent = ScaffoldAgent(gradient_client=_make_gradient_client())
        context = {
            "inventory": _make_inventory(),
            "modeling_manifest": _make_manifest(),
        }
        result = await agent.execute(context)
        project = result.artifacts["astro_project"]
        assert "src/content/config.ts" in project
        config = project["src/content/config.ts"]
        assert "defineCollection" in config
        assert "posts" in config

    @pytest.mark.asyncio
    async def test_tsconfig_generated(self):
        agent = ScaffoldAgent(gradient_client=_make_gradient_client())
        context = {
            "inventory": _make_inventory(),
            "modeling_manifest": _make_manifest(),
        }
        result = await agent.execute(context)
        project = result.artifacts["astro_project"]
        assert "tsconfig.json" in project
        cfg = json.loads(project["tsconfig.json"])
        assert cfg["extends"] == "astro/tsconfigs/strict"

    @pytest.mark.asyncio
    async def test_home_page_generated(self):
        agent = ScaffoldAgent(gradient_client=_make_gradient_client())
        context = {
            "inventory": _make_inventory(),
            "modeling_manifest": _make_manifest(),
        }
        result = await agent.execute(context)
        project = result.artifacts["astro_project"]
        assert "src/pages/index.astro" in project

    @pytest.mark.asyncio
    async def test_fallback_layouts_when_no_theme(self):
        agent = ScaffoldAgent(gradient_client=_make_gradient_client())
        context = {
            "inventory": _make_inventory(),
            "modeling_manifest": _make_manifest(),
        }
        result = await agent.execute(context)
        project = result.artifacts["astro_project"]
        assert "src/layouts/PageLayout.astro" in project
        assert "src/layouts/PostLayout.astro" in project
        assert "BaseLayout" in project["src/layouts/PageLayout.astro"]
        assert "BaseLayout" in project["src/layouts/PostLayout.astro"]

    @pytest.mark.asyncio
    async def test_multiple_collections_all_have_routes(self):
        collections = [
            ContentCollectionSchema(
                collection_name="posts",
                source_post_type="post",
                frontmatter_fields=[
                    FrontmatterField(name="title", type="string", required=True, description="Title"),
                ],
                route_pattern="/blog/[slug]",
            ),
            ContentCollectionSchema(
                collection_name="pages",
                source_post_type="page",
                frontmatter_fields=[
                    FrontmatterField(name="title", type="string", required=True, description="Title"),
                ],
                route_pattern="/[slug]",
            ),
            ContentCollectionSchema(
                collection_name="places",
                source_post_type="gd_place",
                frontmatter_fields=[
                    FrontmatterField(name="title", type="string", required=True, description="Title"),
                    FrontmatterField(name="address", type="string", required=False, description="Address"),
                ],
                route_pattern="/places/[slug]",
            ),
        ]
        manifest = _make_manifest(collections=collections)
        agent = ScaffoldAgent(gradient_client=_make_gradient_client())
        context = {
            "inventory": _make_inventory(),
            "modeling_manifest": manifest,
        }
        result = await agent.execute(context)
        project = result.artifacts["astro_project"]
        # Blog routes
        assert "src/pages/blog/[slug].astro" in project
        assert "src/pages/blog/index.astro" in project
        # Root-level pages routes
        assert "src/pages/[slug].astro" in project
        # Places routes
        assert "src/pages/places/[slug].astro" in project
        assert "src/pages/places/index.astro" in project
