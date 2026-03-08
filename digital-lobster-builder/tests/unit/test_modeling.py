from __future__ import annotations

import pytest
from unittest.mock import AsyncMock
from typing import Any

from src.agents.modeling import (
    ModelingAgent,
    build_collection_schemas,
    build_component_mappings,
    build_taxonomy_definitions,
    _post_type_to_collection,
    _infer_field_type,
    _extract_inventory,
    _extract_block_types_from_inventory,
    _extract_block_types_from_kb,
    KNOWN_BLOCK_MAPPINGS,
)
from src.models.inventory import (
    ContentTypeSummary,
    Inventory,
    MenuSummary,
    PluginFeature,
    TaxonomySummary,
    ThemeMetadata,
)
from src.models.modeling_manifest import (
    ComponentMapping,
    ContentCollectionSchema,
    FrontmatterField,
    ModelingManifest,
    TaxonomyDefinition,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_inventory(**overrides: Any) -> Inventory:
    """Create a minimal Inventory for testing."""
    defaults: dict[str, Any] = {
        "site_url": "https://example.com",
        "site_name": "Test Site",
        "wordpress_version": "6.4",
        "content_types": [
            ContentTypeSummary(
                post_type="post",
                count=50,
                custom_fields=["subtitle"],
                taxonomies=["category", "post_tag"],
                sample_slugs=["hello-world"],
            ),
            ContentTypeSummary(
                post_type="page",
                count=10,
                custom_fields=[],
                taxonomies=[],
                sample_slugs=["about"],
            ),
        ],
        "plugins": [
            PluginFeature(
                slug="kadence-blocks",
                name="Kadence Blocks",
                version="3.0",
                family="kadence",
                custom_post_types=[],
                custom_taxonomies=[],
                detected_features=["kadence/tabs", "kadence/accordion"],
            ),
        ],
        "taxonomies": [
            TaxonomySummary(
                taxonomy="category",
                term_count=5,
                associated_post_types=["post"],
            ),
            TaxonomySummary(
                taxonomy="post_tag",
                term_count=20,
                associated_post_types=["post"],
            ),
        ],
        "menus": [
            MenuSummary(name="Primary", location="header", item_count=6),
        ],
        "theme": ThemeMetadata(
            name="flavor",
            has_theme_json=True,
            has_custom_css=True,
            design_tokens=None,
        ),
        "has_html_snapshots": False,
        "has_media_manifest": False,
        "has_redirect_rules": False,
        "has_seo_data": False,
    }
    defaults.update(overrides)
    return Inventory(**defaults)

def _make_gradient_client(response: str = "{}") -> AsyncMock:
    client = AsyncMock()
    client.complete = AsyncMock(return_value=response)
    client.complete_structured = AsyncMock(return_value={
        "collections": [],
        "components": [],
        "taxonomies": [],
    })
    return client

def _make_kb_client(
    results: list[dict] | None = None,
) -> AsyncMock:
    client = AsyncMock()
    client.query = AsyncMock(return_value=results or [])
    return client

# ---------------------------------------------------------------------------
# Tests: _post_type_to_collection
# ---------------------------------------------------------------------------

class TestPostTypeToCollection:
    def test_standard_post(self):
        name, route = _post_type_to_collection("post")
        assert name == "posts"
        assert route == "/posts/[slug]"

    def test_standard_page(self):
        name, route = _post_type_to_collection("page")
        assert name == "pages"
        assert route == "/[slug]"

    def test_standard_attachment(self):
        name, route = _post_type_to_collection("attachment")
        assert name == "media"
        assert route == "/media/[slug]"

    def test_custom_post_type(self):
        name, route = _post_type_to_collection("gd_place")
        assert name == "gd_place"
        assert route == "/gd_place/[slug]"

    def test_custom_post_type_with_hyphens(self):
        name, route = _post_type_to_collection("my-custom-type")
        assert name == "my_custom_type"
        assert route == "/my_custom_type/[slug]"

# ---------------------------------------------------------------------------
# Tests: _infer_field_type
# ---------------------------------------------------------------------------

class TestInferFieldType:
    def test_date_field(self):
        assert _infer_field_type("published_date") == "date"
        assert _infer_field_type("created_at") == "date"

    def test_number_field(self):
        assert _infer_field_type("price") == "number"
        assert _infer_field_type("item_count") == "number"
        assert _infer_field_type("rating") == "number"

    def test_boolean_field(self):
        assert _infer_field_type("is_featured") == "boolean"
        assert _infer_field_type("has_sidebar") == "boolean"

    def test_list_field(self):
        assert _infer_field_type("gallery") == "list"
        assert _infer_field_type("images") == "list"

    def test_reference_field(self):
        assert _infer_field_type("author") == "reference"
        assert _infer_field_type("parent_ref") == "reference"

    def test_default_string(self):
        assert _infer_field_type("subtitle") == "string"
        assert _infer_field_type("description") == "string"

# ---------------------------------------------------------------------------
# Tests: build_collection_schemas
# ---------------------------------------------------------------------------

class TestBuildCollectionSchemas:
    def test_one_per_post_type(self):
        content_types = [
            ContentTypeSummary(
                post_type="post", count=10, custom_fields=[],
                taxonomies=[], sample_slugs=[],
            ),
            ContentTypeSummary(
                post_type="page", count=5, custom_fields=[],
                taxonomies=[], sample_slugs=[],
            ),
        ]
        schemas = build_collection_schemas(content_types)
        assert len(schemas) == 2
        assert schemas[0].collection_name == "posts"
        assert schemas[1].collection_name == "pages"

    def test_base_fields_present(self):
        content_types = [
            ContentTypeSummary(
                post_type="post", count=1, custom_fields=[],
                taxonomies=[], sample_slugs=[],
            ),
        ]
        schemas = build_collection_schemas(content_types)
        field_names = [f.name for f in schemas[0].frontmatter_fields]
        assert "title" in field_names
        assert "slug" in field_names
        assert "date" in field_names
        assert "status" in field_names
        assert "excerpt" in field_names

    def test_custom_fields_added(self):
        content_types = [
            ContentTypeSummary(
                post_type="post", count=1,
                custom_fields=["subtitle", "rating"],
                taxonomies=[], sample_slugs=[],
            ),
        ]
        schemas = build_collection_schemas(content_types)
        field_names = [f.name for f in schemas[0].frontmatter_fields]
        assert "subtitle" in field_names
        assert "rating" in field_names

    def test_taxonomy_fields_added(self):
        content_types = [
            ContentTypeSummary(
                post_type="post", count=1, custom_fields=[],
                taxonomies=["category", "post_tag"], sample_slugs=[],
            ),
        ]
        schemas = build_collection_schemas(content_types)
        field_names = [f.name for f in schemas[0].frontmatter_fields]
        assert "category" in field_names
        assert "post_tag" in field_names

    def test_no_duplicate_fields(self):
        """Custom field named same as a base field should not duplicate."""
        content_types = [
            ContentTypeSummary(
                post_type="post", count=1,
                custom_fields=["title", "subtitle"],
                taxonomies=[], sample_slugs=[],
            ),
        ]
        schemas = build_collection_schemas(content_types)
        field_names = [f.name for f in schemas[0].frontmatter_fields]
        assert field_names.count("title") == 1

    def test_custom_post_type_route(self):
        content_types = [
            ContentTypeSummary(
                post_type="gd_place", count=100, custom_fields=[],
                taxonomies=[], sample_slugs=[],
            ),
        ]
        schemas = build_collection_schemas(content_types)
        assert schemas[0].source_post_type == "gd_place"
        assert schemas[0].route_pattern == "/gd_place/[slug]"

    def test_empty_content_types(self):
        schemas = build_collection_schemas([])
        assert schemas == []

# ---------------------------------------------------------------------------
# Tests: build_component_mappings
# ---------------------------------------------------------------------------

class TestBuildComponentMappings:
    def test_known_block_mapped(self):
        mappings = build_component_mappings(["core/paragraph"])
        assert len(mappings) == 1
        assert mappings[0].astro_component == "Paragraph"
        assert mappings[0].fallback is False

    def test_unknown_block_fallback(self):
        mappings = build_component_mappings(["myplugin/custom-widget"])
        assert len(mappings) == 1
        assert mappings[0].astro_component == "RawHtmlBlock"
        assert mappings[0].fallback is True

    def test_island_block(self):
        mappings = build_component_mappings(["core/embed"])
        assert mappings[0].is_island is True
        assert mappings[0].hydration_directive == "client:visible"

    def test_non_island_block(self):
        mappings = build_component_mappings(["core/paragraph"])
        assert mappings[0].is_island is False
        assert mappings[0].hydration_directive is None

    def test_kadence_block(self):
        mappings = build_component_mappings(["kadence/tabs"])
        assert mappings[0].astro_component == "KadenceTabs"
        assert mappings[0].is_island is True

    def test_geodirectory_block(self):
        mappings = build_component_mappings(["geodirectory/geodir-widget-map"])
        assert mappings[0].astro_component == "GeoMap"
        assert mappings[0].hydration_directive == "client:load"

    def test_forminator_block(self):
        mappings = build_component_mappings(["forminator/forminator-form"])
        assert mappings[0].astro_component == "ForminatorForm"
        assert mappings[0].is_island is True

    def test_multiple_blocks_mixed(self):
        blocks = ["core/paragraph", "unknown/block", "core/heading"]
        mappings = build_component_mappings(blocks)
        assert len(mappings) == 3
        fallbacks = [m for m in mappings if m.fallback]
        non_fallbacks = [m for m in mappings if not m.fallback]
        assert len(fallbacks) == 1
        assert len(non_fallbacks) == 2

    def test_empty_block_list(self):
        mappings = build_component_mappings([])
        assert mappings == []

# ---------------------------------------------------------------------------
# Tests: build_taxonomy_definitions
# ---------------------------------------------------------------------------

class TestBuildTaxonomyDefinitions:
    def test_standard_category(self):
        taxonomies = [
            TaxonomySummary(taxonomy="category", term_count=5, associated_post_types=["post"]),
        ]
        defs = build_taxonomy_definitions(taxonomies)
        assert len(defs) == 1
        assert defs[0].data_file == "src/data/category.json"
        assert defs[0].collection_ref is None

    def test_standard_post_tag(self):
        taxonomies = [
            TaxonomySummary(taxonomy="post_tag", term_count=10, associated_post_types=["post"]),
        ]
        defs = build_taxonomy_definitions(taxonomies)
        assert defs[0].data_file == "src/data/post_tag.json"
        assert defs[0].collection_ref is None

    def test_custom_taxonomy(self):
        taxonomies = [
            TaxonomySummary(taxonomy="gd_placecategory", term_count=8, associated_post_types=["gd_place"]),
        ]
        defs = build_taxonomy_definitions(taxonomies)
        assert defs[0].collection_ref == "gd_placecategory"
        assert defs[0].data_file is None

    def test_mixed_taxonomies(self):
        taxonomies = [
            TaxonomySummary(taxonomy="category", term_count=5, associated_post_types=["post"]),
            TaxonomySummary(taxonomy="custom_tax", term_count=3, associated_post_types=["page"]),
        ]
        defs = build_taxonomy_definitions(taxonomies)
        assert len(defs) == 2
        assert defs[0].data_file is not None  # standard
        assert defs[1].collection_ref is not None  # custom

    def test_empty_taxonomies(self):
        defs = build_taxonomy_definitions([])
        assert defs == []

# ---------------------------------------------------------------------------
# Tests: _extract_inventory
# ---------------------------------------------------------------------------

class TestExtractInventory:
    def test_from_inventory_instance(self):
        inv = _make_inventory()
        result = _extract_inventory({"inventory": inv})
        assert result.site_name == "Test Site"

    def test_from_dict(self):
        inv = _make_inventory()
        result = _extract_inventory({"inventory": inv.model_dump()})
        assert result.site_name == "Test Site"

    def test_missing_key_raises(self):
        with pytest.raises(KeyError):
            _extract_inventory({})

# ---------------------------------------------------------------------------
# Tests: _extract_block_types_from_inventory
# ---------------------------------------------------------------------------

class TestExtractBlockTypesFromInventory:
    def test_extracts_block_features(self):
        inv = _make_inventory(
            plugins=[
                PluginFeature(
                    slug="kadence-blocks",
                    name="Kadence Blocks",
                    version="3.0",
                    family="kadence",
                    custom_post_types=[],
                    custom_taxonomies=[],
                    detected_features=["kadence/tabs", "kadence/accordion", "some-non-block-feature"],
                ),
            ]
        )
        blocks = _extract_block_types_from_inventory(inv)
        assert "kadence/tabs" in blocks
        assert "kadence/accordion" in blocks
        assert "some-non-block-feature" not in blocks

    def test_empty_plugins(self):
        inv = _make_inventory(plugins=[])
        blocks = _extract_block_types_from_inventory(inv)
        assert blocks == []

# ---------------------------------------------------------------------------
# Tests: _extract_block_types_from_kb
# ---------------------------------------------------------------------------

class TestExtractBlockTypesFromKb:
    def test_json_dict_keys(self):
        kb_results = [
            {"content": '{"core/paragraph": 50, "core/heading": 30}'},
        ]
        blocks = _extract_block_types_from_kb(kb_results)
        assert "core/paragraph" in blocks
        assert "core/heading" in blocks

    def test_json_list_with_name(self):
        kb_results = [
            {"content": '[{"name": "core/image"}, {"name": "core/list"}]'},
        ]
        blocks = _extract_block_types_from_kb(kb_results)
        assert "core/image" in blocks
        assert "core/list" in blocks

    def test_plain_text_regex(self):
        kb_results = [
            {"content": "The site uses core/paragraph and kadence/tabs blocks."},
        ]
        blocks = _extract_block_types_from_kb(kb_results)
        assert "core/paragraph" in blocks
        assert "kadence/tabs" in blocks

    def test_empty_results(self):
        blocks = _extract_block_types_from_kb([])
        assert blocks == []

# ---------------------------------------------------------------------------
# Tests: ModelingAgent.execute
# ---------------------------------------------------------------------------

class TestModelingAgentExecute:
    @pytest.mark.asyncio
    async def test_successful_execution(self):
        """Agent produces a manifest with collections, components, and taxonomies."""
        inv = _make_inventory()
        client = _make_gradient_client()
        agent = ModelingAgent(gradient_client=client, kb_client=None)

        result = await agent.execute({"inventory": inv})

        assert result.agent_name == "modeling"
        manifest = result.artifacts["modeling_manifest"]
        assert "collections" in manifest
        assert "components" in manifest
        assert "taxonomies" in manifest

    @pytest.mark.asyncio
    async def test_collection_per_post_type(self):
        """One collection schema per content type in inventory."""
        inv = _make_inventory()
        client = _make_gradient_client()
        agent = ModelingAgent(gradient_client=client, kb_client=None)

        result = await agent.execute({"inventory": inv})

        manifest = result.artifacts["modeling_manifest"]
        assert len(manifest["collections"]) == len(inv.content_types)

    @pytest.mark.asyncio
    async def test_taxonomy_per_inventory_taxonomy(self):
        """One taxonomy definition per taxonomy in inventory."""
        inv = _make_inventory()
        client = _make_gradient_client()
        agent = ModelingAgent(gradient_client=client, kb_client=None)

        result = await agent.execute({"inventory": inv})

        manifest = result.artifacts["modeling_manifest"]
        assert len(manifest["taxonomies"]) == len(inv.taxonomies)

    @pytest.mark.asyncio
    async def test_components_from_inventory_plugins(self):
        """Block types from plugin features are mapped to components."""
        inv = _make_inventory()
        client = _make_gradient_client()
        agent = ModelingAgent(gradient_client=client, kb_client=None)

        result = await agent.execute({"inventory": inv})

        manifest = result.artifacts["modeling_manifest"]
        component_blocks = [c["wp_block_type"] for c in manifest["components"]]
        assert "kadence/tabs" in component_blocks
        assert "kadence/accordion" in component_blocks

    @pytest.mark.asyncio
    async def test_queries_knowledge_base(self):
        """Agent queries KB when kb_ref is provided."""
        inv = _make_inventory()
        client = _make_gradient_client()
        # Return enriched manifest from complete_structured
        enriched = ModelingManifest(
            collections=build_collection_schemas(inv.content_types),
            components=[],
            taxonomies=[],
        ).model_dump()
        client.complete_structured = AsyncMock(return_value=enriched)

        kb_client = _make_kb_client(results=[
            {"content": '{"core/paragraph": 100}'},
        ])
        agent = ModelingAgent(gradient_client=client, kb_client=kb_client)

        result = await agent.execute({"inventory": inv, "kb_ref": "kb-123"})

        assert kb_client.query.call_count == 3  # 3 queries
        assert result.agent_name == "modeling"

    @pytest.mark.asyncio
    async def test_skips_kb_when_no_ref(self):
        """Agent works without KB reference."""
        inv = _make_inventory()
        client = _make_gradient_client()
        kb_client = _make_kb_client()
        agent = ModelingAgent(gradient_client=client, kb_client=kb_client)

        result = await agent.execute({"inventory": inv})

        kb_client.query.assert_not_called()
        assert result.agent_name == "modeling"

    @pytest.mark.asyncio
    async def test_skips_kb_when_no_client(self):
        """Agent works without KB client."""
        inv = _make_inventory()
        client = _make_gradient_client()
        agent = ModelingAgent(gradient_client=client, kb_client=None)

        result = await agent.execute({"inventory": inv, "kb_ref": "kb-123"})

        assert result.agent_name == "modeling"

    @pytest.mark.asyncio
    async def test_unmapped_blocks_produce_warnings(self):
        """Unknown block types generate warnings about fallback."""
        inv = _make_inventory(
            plugins=[
                PluginFeature(
                    slug="custom-plugin",
                    name="Custom Plugin",
                    version="1.0",
                    family=None,
                    custom_post_types=[],
                    custom_taxonomies=[],
                    detected_features=["custom/unknown-widget"],
                ),
            ]
        )
        client = _make_gradient_client()
        agent = ModelingAgent(gradient_client=client, kb_client=None)

        result = await agent.execute({"inventory": inv})

        assert any("custom/unknown-widget" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_kb_query_failure_produces_warning(self):
        """KB query failure is logged as a warning, not an error."""
        inv = _make_inventory()
        client = _make_gradient_client()
        kb_client = AsyncMock()
        kb_client.query = AsyncMock(side_effect=RuntimeError("KB down"))
        agent = ModelingAgent(gradient_client=client, kb_client=kb_client)

        result = await agent.execute({"inventory": inv, "kb_ref": "kb-123"})

        assert any("KB query failed" in w for w in result.warnings)
        assert result.agent_name == "modeling"

    @pytest.mark.asyncio
    async def test_llm_enrichment_failure_falls_back(self):
        """If LLM enrichment fails, the base manifest is returned."""
        inv = _make_inventory()
        client = _make_gradient_client()
        client.complete_structured = AsyncMock(
            side_effect=RuntimeError("LLM error")
        )
        kb_client = _make_kb_client(results=[
            {"content": '{"core/paragraph": 100}'},
        ])
        agent = ModelingAgent(gradient_client=client, kb_client=kb_client)

        result = await agent.execute({"inventory": inv, "kb_ref": "kb-123"})

        assert any("LLM enrichment failed" in w for w in result.warnings)
        # Manifest should still be present
        assert "modeling_manifest" in result.artifacts

    @pytest.mark.asyncio
    async def test_inventory_from_dict(self):
        """Agent accepts inventory as a dict (not just Inventory instance)."""
        inv = _make_inventory()
        client = _make_gradient_client()
        agent = ModelingAgent(gradient_client=client, kb_client=None)

        result = await agent.execute({"inventory": inv.model_dump()})

        assert result.agent_name == "modeling"
        assert "modeling_manifest" in result.artifacts

    @pytest.mark.asyncio
    async def test_custom_post_type_collection(self):
        """Custom post types get their own collection with correct route."""
        inv = _make_inventory(
            content_types=[
                ContentTypeSummary(
                    post_type="gd_place",
                    count=200,
                    custom_fields=["address", "latitude", "longitude", "rating"],
                    taxonomies=["gd_placecategory"],
                    sample_slugs=["best-pizza"],
                ),
            ]
        )
        client = _make_gradient_client()
        agent = ModelingAgent(gradient_client=client, kb_client=None)

        result = await agent.execute({"inventory": inv})

        manifest = result.artifacts["modeling_manifest"]
        coll = manifest["collections"][0]
        assert coll["collection_name"] == "gd_place"
        assert coll["source_post_type"] == "gd_place"
        assert coll["route_pattern"] == "/gd_place/[slug]"
        field_names = [f["name"] for f in coll["frontmatter_fields"]]
        assert "address" in field_names
        assert "latitude" in field_names
        assert "rating" in field_names

    @pytest.mark.asyncio
    async def test_duration_recorded(self):
        """Agent records execution duration."""
        inv = _make_inventory()
        client = _make_gradient_client()
        agent = ModelingAgent(gradient_client=client, kb_client=None)

        result = await agent.execute({"inventory": inv})

        assert result.duration_seconds >= 0
