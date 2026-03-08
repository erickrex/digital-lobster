from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.agents.schema_compiler import SchemaCompilerAgent
from src.models.bundle_artifacts import (
    ContentRelationship,
    ContentRelationshipsArtifact,
    EditorialWorkflowsArtifact,
    FieldUsageEntry,
    FieldUsageReportArtifact,
    IntegrationManifestArtifact,
    PageCompositionArtifact,
    PluginInstancesArtifact,
    SearchConfigArtifact,
    SeoFullArtifact,
    SeoPageEntry,
)
from src.models.bundle_manifest import BundleManifest
from src.models.capability_manifest import Capability, CapabilityManifest
from src.models.content_model_manifest import ContentModelManifest
from src.models.finding import Finding

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_bundle(**overrides: Any) -> BundleManifest:
    """Build a minimal BundleManifest for schema compiler tests."""
    defaults: dict[str, Any] = dict(
        schema_version="1.0.0",
        site_url="https://example.com",
        site_name="Test",
        wordpress_version="6.4.2",
        site_blueprint={},
        site_settings={},
        site_options={},
        site_environment={},
        taxonomies={},
        menus=[],
        media_map=[],
        theme_mods={},
        global_styles={},
        customizer_settings={},
        css_sources={},
        plugins_fingerprint={"plugins": []},
        plugin_behaviors={},
        blocks_usage={},
        block_patterns={},
        acf_field_groups={},
        custom_fields_config={},
        shortcodes_inventory={},
        forms_config={},
        widgets={},
        page_templates={},
        rewrite_rules={},
        rest_api_endpoints={},
        hooks_registry={},
        error_log={},
        content_relationships=ContentRelationshipsArtifact(
            schema_version="1.0.0", relationships=[]
        ),
        field_usage_report=FieldUsageReportArtifact(
            schema_version="1.0.0", fields=[]
        ),
        plugin_instances=PluginInstancesArtifact(
            schema_version="1.0.0", instances=[]
        ),
        page_composition=PageCompositionArtifact(
            schema_version="1.0.0", pages=[]
        ),
        seo_full=SeoFullArtifact(schema_version="1.0.0", pages=[]),
        editorial_workflows=EditorialWorkflowsArtifact(
            schema_version="1.0.0",
            statuses_in_use=["publish", "draft"],
            scheduled_publishing=False,
            draft_behavior="standard",
            preview_expectations="none",
            revision_policy="default",
            comments_enabled=False,
            authoring_model="single_editor",
        ),
        plugin_table_exports=[],
        search_config=SearchConfigArtifact(
            schema_version="1.0.0",
            searchable_types=[],
            ranking_hints=[],
            facets=[],
        ),
        integration_manifest=IntegrationManifestArtifact(
            schema_version="1.0.0", integrations=[]
        ),
    )
    defaults.update(overrides)
    return BundleManifest(**defaults)

def _clean_capability_manifest(**overrides: Any) -> CapabilityManifest:
    """Build a minimal CapabilityManifest for schema compiler tests."""
    defaults: dict[str, Any] = dict(
        capabilities=[],
        findings=[],
        content_model_capabilities=[],
        presentation_capabilities=[],
        behavior_capabilities=[],
        plugin_capabilities={},
    )
    defaults.update(overrides)
    return CapabilityManifest(**defaults)

def _make_field_entry(**overrides: Any) -> FieldUsageEntry:
    """Build a FieldUsageEntry with sensible defaults."""
    defaults: dict[str, Any] = dict(
        post_type="post",
        field_name="title",
        source_system="core",
        inferred_type="text",
        nullable=False,
        cardinality="single",
        distinct_value_count=10,
        sample_values=["Hello", "World"],
    )
    defaults.update(overrides)
    return FieldUsageEntry(**defaults)

def _make_agent() -> SchemaCompilerAgent:
    return SchemaCompilerAgent(gradient_client=None)

def _run(coro):
    return asyncio.run(coro)

def _execute(bundle: BundleManifest, cap_manifest: CapabilityManifest) -> ContentModelManifest:
    """Run the schema compiler and return the ContentModelManifest."""
    agent = _make_agent()
    context: dict[str, Any] = {
        "bundle_manifest": bundle,
        "capability_manifest": cap_manifest,
    }
    result = _run(agent.execute(context))
    return result.artifacts["content_model_manifest"]

# ---------------------------------------------------------------------------
# Collection compilation — Requirement 14.1, 14.2
# ---------------------------------------------------------------------------

class TestCollectionCompilation:
    def test_collections_created_from_field_usage_post_types(self):
        bundle = _clean_bundle(
            field_usage_report=FieldUsageReportArtifact(
                schema_version="1.0.0",
                fields=[
                    _make_field_entry(post_type="post", field_name="subtitle", inferred_type="text"),
                    _make_field_entry(post_type="page", field_name="hero_image", inferred_type="image"),
                ],
            ),
        )
        cap = _clean_capability_manifest()
        manifest = _execute(bundle, cap)

        api_ids = [c.api_id for c in manifest.collections]
        assert "post" in api_ids
        assert "page" in api_ids

    def test_text_field_maps_to_string(self):
        bundle = _clean_bundle(
            field_usage_report=FieldUsageReportArtifact(
                schema_version="1.0.0",
                fields=[_make_field_entry(inferred_type="text", field_name="subtitle")],
            ),
        )
        manifest = _execute(bundle, _clean_capability_manifest())
        field = manifest.collections[0].fields[0]
        assert field.strapi_type == "string"

    def test_image_field_maps_to_media(self):
        bundle = _clean_bundle(
            field_usage_report=FieldUsageReportArtifact(
                schema_version="1.0.0",
                fields=[_make_field_entry(inferred_type="image", field_name="hero")],
            ),
        )
        manifest = _execute(bundle, _clean_capability_manifest())
        field = manifest.collections[0].fields[0]
        assert field.strapi_type == "media"

    def test_number_field_maps_to_integer(self):
        bundle = _clean_bundle(
            field_usage_report=FieldUsageReportArtifact(
                schema_version="1.0.0",
                fields=[_make_field_entry(inferred_type="number", field_name="count")],
            ),
        )
        manifest = _execute(bundle, _clean_capability_manifest())
        field = manifest.collections[0].fields[0]
        assert field.strapi_type == "integer"

    def test_textarea_maps_to_richtext(self):
        bundle = _clean_bundle(
            field_usage_report=FieldUsageReportArtifact(
                schema_version="1.0.0",
                fields=[_make_field_entry(inferred_type="textarea", field_name="body")],
            ),
        )
        manifest = _execute(bundle, _clean_capability_manifest())
        field = manifest.collections[0].fields[0]
        assert field.strapi_type == "richtext"

    def test_non_nullable_field_is_required(self):
        bundle = _clean_bundle(
            field_usage_report=FieldUsageReportArtifact(
                schema_version="1.0.0",
                fields=[_make_field_entry(nullable=False, field_name="required_field")],
            ),
        )
        manifest = _execute(bundle, _clean_capability_manifest())
        field = manifest.collections[0].fields[0]
        assert field.required is True

    def test_nullable_field_is_not_required(self):
        bundle = _clean_bundle(
            field_usage_report=FieldUsageReportArtifact(
                schema_version="1.0.0",
                fields=[_make_field_entry(nullable=True, field_name="optional_field")],
            ),
        )
        manifest = _execute(bundle, _clean_capability_manifest())
        field = manifest.collections[0].fields[0]
        assert field.required is False

    def test_empty_field_usage_produces_no_collections(self):
        bundle = _clean_bundle()
        manifest = _execute(bundle, _clean_capability_manifest())
        assert manifest.collections == []

# ---------------------------------------------------------------------------
# Repeater → nested component — Requirement 14.3
# ---------------------------------------------------------------------------

class TestRepeaterMapping:
    def test_repeater_field_maps_to_component_type(self):
        bundle = _clean_bundle(
            field_usage_report=FieldUsageReportArtifact(
                schema_version="1.0.0",
                fields=[
                    _make_field_entry(
                        field_name="team_members",
                        inferred_type="repeater",
                        behaves_as="repeater",
                        sample_values=[{"name": "Alice", "role": "Dev"}],
                    ),
                ],
            ),
        )
        manifest = _execute(bundle, _clean_capability_manifest())

        field = manifest.collections[0].fields[0]
        assert field.strapi_type == "component"
        assert field.name == "team_members"

    def test_repeater_generates_component(self):
        bundle = _clean_bundle(
            field_usage_report=FieldUsageReportArtifact(
                schema_version="1.0.0",
                fields=[
                    _make_field_entry(
                        field_name="team_members",
                        inferred_type="repeater",
                        behaves_as="repeater",
                        sample_values=[{"name": "Alice", "role": "Dev"}],
                    ),
                ],
            ),
        )
        manifest = _execute(bundle, _clean_capability_manifest())

        assert len(manifest.components) >= 1
        comp = next(c for c in manifest.components if "team-members" in c.uid)
        assert comp.category == "content"
        sub_field_names = [f.name for f in comp.fields]
        assert "name" in sub_field_names
        assert "role" in sub_field_names

    def test_repeater_component_uid_in_collection(self):
        bundle = _clean_bundle(
            field_usage_report=FieldUsageReportArtifact(
                schema_version="1.0.0",
                fields=[
                    _make_field_entry(
                        field_name="slides",
                        inferred_type="repeater",
                        behaves_as="repeater",
                        sample_values=[],
                    ),
                ],
            ),
        )
        manifest = _execute(bundle, _clean_capability_manifest())

        coll = manifest.collections[0]
        assert "content.slides" in coll.components

# ---------------------------------------------------------------------------
# Flexible content → dynamic zone — Requirement 14.3
# ---------------------------------------------------------------------------

class TestFlexibleContentMapping:
    def test_flexible_content_maps_to_dynamiczone(self):
        bundle = _clean_bundle(
            field_usage_report=FieldUsageReportArtifact(
                schema_version="1.0.0",
                fields=[
                    _make_field_entry(
                        field_name="page_builder",
                        inferred_type="flexible_content",
                        behaves_as="flexible",
                        sample_values=[],
                    ),
                ],
            ),
        )
        manifest = _execute(bundle, _clean_capability_manifest())

        field = manifest.collections[0].fields[0]
        assert field.strapi_type == "dynamiczone"
        assert field.name == "page_builder"

    def test_flexible_content_generates_component(self):
        bundle = _clean_bundle(
            field_usage_report=FieldUsageReportArtifact(
                schema_version="1.0.0",
                fields=[
                    _make_field_entry(
                        field_name="page_builder",
                        inferred_type="flexible_content",
                        behaves_as="flexible",
                        sample_values=[{"layout": "hero", "title": "Welcome"}],
                    ),
                ],
            ),
        )
        manifest = _execute(bundle, _clean_capability_manifest())

        comp = next(c for c in manifest.components if "page-builder" in c.uid)
        assert comp.category == "content"

# ---------------------------------------------------------------------------
# SEO component strategy — Requirement 14.6
# ---------------------------------------------------------------------------

class TestSeoStrategy:
    def test_seo_strategy_created_when_seo_capabilities_exist(self):
        cap = _clean_capability_manifest(
            capabilities=[
                Capability(
                    capability_type="seo",
                    source_plugin="yoast",
                    classification="strapi_native",
                    confidence=0.95,
                ),
            ],
        )
        bundle = _clean_bundle(
            field_usage_report=FieldUsageReportArtifact(
                schema_version="1.0.0",
                fields=[_make_field_entry(post_type="post")],
            ),
        )
        manifest = _execute(bundle, cap)

        assert manifest.seo_strategy is not None
        assert manifest.seo_strategy.component_uid == "shared.seo-metadata"

    def test_seo_strategy_applied_to_all_collections(self):
        cap = _clean_capability_manifest(
            capabilities=[
                Capability(
                    capability_type="seo",
                    source_plugin="yoast",
                    classification="strapi_native",
                    confidence=0.95,
                ),
            ],
        )
        bundle = _clean_bundle(
            field_usage_report=FieldUsageReportArtifact(
                schema_version="1.0.0",
                fields=[
                    _make_field_entry(post_type="post"),
                    _make_field_entry(post_type="page", field_name="content"),
                ],
            ),
        )
        manifest = _execute(bundle, cap)

        assert manifest.seo_strategy is not None
        for coll in manifest.collections:
            assert manifest.seo_strategy.component_uid in coll.components

    def test_seo_strategy_has_standard_fields(self):
        cap = _clean_capability_manifest(
            capabilities=[
                Capability(
                    capability_type="seo",
                    source_plugin="yoast",
                    classification="strapi_native",
                    confidence=0.95,
                ),
            ],
        )
        bundle = _clean_bundle(
            field_usage_report=FieldUsageReportArtifact(
                schema_version="1.0.0",
                fields=[_make_field_entry(post_type="post")],
            ),
        )
        manifest = _execute(bundle, cap)

        seo_field_names = {f.name for f in manifest.seo_strategy.fields}
        assert "meta_title" in seo_field_names
        assert "meta_description" in seo_field_names
        assert "og_title" in seo_field_names
        assert "no_index" in seo_field_names

    def test_no_seo_strategy_when_no_seo_capabilities(self):
        bundle = _clean_bundle(
            field_usage_report=FieldUsageReportArtifact(
                schema_version="1.0.0",
                fields=[_make_field_entry(post_type="post")],
            ),
        )
        manifest = _execute(bundle, _clean_capability_manifest())
        assert manifest.seo_strategy is None

# ---------------------------------------------------------------------------
# Validation hints — Requirement 14.7
# ---------------------------------------------------------------------------

class TestValidationHints:
    def test_validation_hints_from_field_usage(self):
        bundle = _clean_bundle(
            field_usage_report=FieldUsageReportArtifact(
                schema_version="1.0.0",
                fields=[
                    _make_field_entry(
                        post_type="post",
                        field_name="status",
                        nullable=True,
                        cardinality="single",
                    ),
                ],
            ),
        )
        manifest = _execute(bundle, _clean_capability_manifest())

        assert len(manifest.validation_hints) == 1
        hint = manifest.validation_hints[0]
        assert hint.collection_api_id == "post"
        assert hint.field_name == "status"
        assert hint.nullable is True
        assert hint.cardinality == "single"

    def test_enum_values_extracted_from_sample_values(self):
        bundle = _clean_bundle(
            field_usage_report=FieldUsageReportArtifact(
                schema_version="1.0.0",
                fields=[
                    _make_field_entry(
                        field_name="color",
                        inferred_type="select",
                        behaves_as="enum",
                        sample_values=["red", "green", "blue"],
                    ),
                ],
            ),
        )
        manifest = _execute(bundle, _clean_capability_manifest())

        hint = manifest.validation_hints[0]
        assert hint.enum_values == ["red", "green", "blue"]

    def test_non_enum_field_has_no_enum_values(self):
        bundle = _clean_bundle(
            field_usage_report=FieldUsageReportArtifact(
                schema_version="1.0.0",
                fields=[_make_field_entry(inferred_type="text", behaves_as=None)],
            ),
        )
        manifest = _execute(bundle, _clean_capability_manifest())

        hint = manifest.validation_hints[0]
        assert hint.enum_values is None

# ---------------------------------------------------------------------------
# Relation compilation — Requirement 14.5
# ---------------------------------------------------------------------------

class TestRelationCompilation:
    def test_relations_generated_from_content_relationships(self):
        bundle = _clean_bundle(
            content_relationships=ContentRelationshipsArtifact(
                schema_version="1.0.0",
                relationships=[
                    ContentRelationship(
                        source_id="post:1",
                        target_id="media:5",
                        relation_type="post_to_media",
                    ),
                ],
            ),
            field_usage_report=FieldUsageReportArtifact(
                schema_version="1.0.0",
                fields=[_make_field_entry(post_type="post")],
            ),
        )
        manifest = _execute(bundle, _clean_capability_manifest())

        assert len(manifest.relations) == 1
        rel = manifest.relations[0]
        assert rel.source_collection == "post"
        assert rel.target_collection == "media"
        assert rel.relation_type == "manyToOne"

    def test_post_to_term_maps_to_many_to_many(self):
        bundle = _clean_bundle(
            content_relationships=ContentRelationshipsArtifact(
                schema_version="1.0.0",
                relationships=[
                    ContentRelationship(
                        source_id="post:1",
                        target_id="category:3",
                        relation_type="post_to_term",
                    ),
                ],
            ),
        )
        manifest = _execute(bundle, _clean_capability_manifest())

        rel = manifest.relations[0]
        assert rel.relation_type == "manyToMany"

    def test_no_relations_when_no_content_relationships(self):
        bundle = _clean_bundle()
        manifest = _execute(bundle, _clean_capability_manifest())
        assert manifest.relations == []

# ---------------------------------------------------------------------------
# Agent result structure
# ---------------------------------------------------------------------------

class TestAgentResult:
    def test_agent_result_contains_content_model_manifest(self):
        agent = _make_agent()
        bundle = _clean_bundle(
            field_usage_report=FieldUsageReportArtifact(
                schema_version="1.0.0",
                fields=[_make_field_entry()],
            ),
        )
        context: dict[str, Any] = {
            "bundle_manifest": bundle,
            "capability_manifest": _clean_capability_manifest(),
        }
        result = _run(agent.execute(context))

        assert result.agent_name == "schema_compiler"
        assert "content_model_manifest" in result.artifacts
        assert isinstance(result.artifacts["content_model_manifest"], ContentModelManifest)
