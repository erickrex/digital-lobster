from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.agents.behavior_compiler import BehaviorCompilerAgent
from src.models.behavior_manifest import BehaviorManifest
from src.models.bundle_artifacts import (
    ContentRelationshipsArtifact,
    EditorialWorkflowsArtifact,
    FieldUsageReportArtifact,
    IntegrationEntry,
    IntegrationManifestArtifact,
    PageCompositionArtifact,
    PluginInstance,
    PluginInstancesArtifact,
    SearchConfigArtifact,
    SeoFullArtifact,
    SeoPageEntry,
)
from src.models.bundle_manifest import BundleManifest
from src.models.capability_manifest import Capability, CapabilityManifest
from src.models.content_model_manifest import (
    ContentModelManifest,
    StrapiCollection,
    StrapiRelation,
)
from src.models.migration_mapping_manifest import MigrationMappingManifest
from src.models.presentation_manifest import (
    PresentationManifest,
    RouteTemplate,
)
from src.models.strapi_types import StrapiFieldDefinition


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean_bundle(**overrides: Any) -> BundleManifest:
    """Build a minimal BundleManifest for behavior compiler tests."""
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
    defaults: dict[str, Any] = dict(
        capabilities=[],
        findings=[],
    )
    defaults.update(overrides)
    return CapabilityManifest(**defaults)


def _clean_content_model(**overrides: Any) -> ContentModelManifest:
    defaults: dict[str, Any] = dict(
        collections=[],
        components=[],
        relations=[],
        seo_strategy=None,
        validation_hints=[],
    )
    defaults.update(overrides)
    return ContentModelManifest(**defaults)


def _clean_presentation(**overrides: Any) -> PresentationManifest:
    defaults: dict[str, Any] = dict(
        layouts=[],
        route_templates=[],
        sections=[],
        fallback_zones=[],
        style_tokens={},
    )
    defaults.update(overrides)
    return PresentationManifest(**defaults)


def _make_agent() -> BehaviorCompilerAgent:
    return BehaviorCompilerAgent(gradient_client=None)


def _run(coro):
    return asyncio.run(coro)


def _execute(
    bundle: BundleManifest,
    cap_manifest: CapabilityManifest | None = None,
    content_model: ContentModelManifest | None = None,
    presentation: PresentationManifest | None = None,
) -> dict[str, Any]:
    agent = _make_agent()
    context: dict[str, Any] = {
        "bundle_manifest": bundle,
        "capability_manifest": cap_manifest or _clean_capability_manifest(),
        "content_model_manifest": content_model or _clean_content_model(),
        "presentation_manifest": presentation or _clean_presentation(),
    }
    result = _run(agent.execute(context))
    return result.artifacts


# ---------------------------------------------------------------------------
# Redirect compilation — Requirement 16.4
# ---------------------------------------------------------------------------


class TestRedirectCompilation:
    def test_redirect_from_rewrite_rules(self):
        bundle = _clean_bundle(
            rewrite_rules={
                "redirects": [
                    {"source_url": "/old", "target_url": "/new", "status_code": 301},
                ]
            },
        )
        artifacts = _execute(bundle)
        bm: BehaviorManifest = artifacts["behavior_manifest"]
        assert len(bm.redirects) == 1
        assert bm.redirects[0].source_url == "/old"
        assert bm.redirects[0].target_url == "/new"
        assert bm.redirects[0].status_code == 301

    def test_redirect_from_seo_redirect_ownership(self):
        bundle = _clean_bundle(
            seo_full=SeoFullArtifact(
                schema_version="1.0.0",
                pages=[
                    SeoPageEntry(
                        canonical_url="/legacy-page",
                        source_plugin="yoast",
                        redirect_ownership={
                            "target_url": "/new-page",
                            "status_code": 302,
                        },
                    ),
                ],
            ),
        )
        artifacts = _execute(bundle)
        bm: BehaviorManifest = artifacts["behavior_manifest"]
        assert len(bm.redirects) == 1
        assert bm.redirects[0].source_url == "/legacy-page"
        assert bm.redirects[0].target_url == "/new-page"
        assert bm.redirects[0].status_code == 302
        assert bm.redirects[0].source_plugin == "yoast"

    def test_redirects_from_multiple_sources_deduplicated(self):
        bundle = _clean_bundle(
            rewrite_rules={
                "redirects": [
                    {"source_url": "/dup", "target_url": "/target", "status_code": 301},
                ]
            },
            seo_full=SeoFullArtifact(
                schema_version="1.0.0",
                pages=[
                    SeoPageEntry(
                        canonical_url="/dup",
                        source_plugin="yoast",
                        redirect_ownership={"target_url": "/target", "status_code": 301},
                    ),
                ],
            ),
        )
        artifacts = _execute(bundle)
        bm: BehaviorManifest = artifacts["behavior_manifest"]
        assert len(bm.redirects) == 1

    def test_redirects_sorted_deterministically(self):
        bundle = _clean_bundle(
            rewrite_rules={
                "redirects": [
                    {"source_url": "/z-page", "target_url": "/z-new", "status_code": 301},
                    {"source_url": "/a-page", "target_url": "/a-new", "status_code": 301},
                ]
            },
        )
        artifacts = _execute(bundle)
        bm: BehaviorManifest = artifacts["behavior_manifest"]
        assert bm.redirects[0].source_url == "/a-page"
        assert bm.redirects[1].source_url == "/z-page"


# ---------------------------------------------------------------------------
# Form strategy — Requirement 16.3
# ---------------------------------------------------------------------------


class TestFormStrategy:
    @pytest.mark.parametrize("provider", ["cf7", "wpforms", "gravity_forms", "ninja_forms"])
    def test_supported_form_provider_produces_strategy(self, provider: str):
        bundle = _clean_bundle(
            plugin_instances=PluginInstancesArtifact(
                schema_version="1.0.0",
                instances=[
                    PluginInstance(
                        instance_id=f"form-{provider}-1",
                        source_plugin=provider,
                        instance_type="form",
                        config={"fields": [{"name": "email", "type": "email"}]},
                    ),
                ],
            ),
        )
        artifacts = _execute(bundle)
        bm: BehaviorManifest = artifacts["behavior_manifest"]
        assert len(bm.forms_strategy) == 1
        fs = bm.forms_strategy[0]
        assert fs.form_id == f"form-{provider}-1"
        assert fs.source_plugin == provider
        assert fs.target == "astro_api_route"
        assert len(fs.fields) == 1

    def test_unsupported_form_provider_skipped(self):
        bundle = _clean_bundle(
            plugin_instances=PluginInstancesArtifact(
                schema_version="1.0.0",
                instances=[
                    PluginInstance(
                        instance_id="form-unknown-1",
                        source_plugin="unknown_forms",
                        instance_type="form",
                        config={},
                    ),
                ],
            ),
        )
        artifacts = _execute(bundle)
        bm: BehaviorManifest = artifacts["behavior_manifest"]
        assert len(bm.forms_strategy) == 0

    def test_non_form_instance_skipped(self):
        bundle = _clean_bundle(
            plugin_instances=PluginInstancesArtifact(
                schema_version="1.0.0",
                instances=[
                    PluginInstance(
                        instance_id="seo-yoast-1",
                        source_plugin="cf7",
                        instance_type="seo_object",
                        config={},
                    ),
                ],
            ),
        )
        artifacts = _execute(bundle)
        bm: BehaviorManifest = artifacts["behavior_manifest"]
        assert len(bm.forms_strategy) == 0


# ---------------------------------------------------------------------------
# Integration boundary — Requirement 16.6
# ---------------------------------------------------------------------------


class TestIntegrationBoundary:
    def test_form_destination_classified_as_rebuild(self):
        bundle = _clean_bundle(
            integration_manifest=IntegrationManifestArtifact(
                schema_version="1.0.0",
                integrations=[
                    IntegrationEntry(
                        integration_id="int-1",
                        integration_type="form_destination",
                        target="https://api.example.com/submit",
                    ),
                ],
            ),
        )
        artifacts = _execute(bundle)
        bm: BehaviorManifest = artifacts["behavior_manifest"]
        assert len(bm.integration_boundaries) == 1
        assert bm.integration_boundaries[0].disposition == "rebuild"
        assert bm.integration_boundaries[0].target_system == "strapi"
        assert bm.integration_boundaries[0].finding is None

    @pytest.mark.parametrize("itype", ["runtime_api", "webhook", "crm", "embed", "third_party_script"])
    def test_external_integration_classified_as_proxy(self, itype: str):
        bundle = _clean_bundle(
            integration_manifest=IntegrationManifestArtifact(
                schema_version="1.0.0",
                integrations=[
                    IntegrationEntry(
                        integration_id="int-proxy",
                        integration_type=itype,
                        target="https://external.example.com",
                    ),
                ],
            ),
        )
        artifacts = _execute(bundle)
        bm: BehaviorManifest = artifacts["behavior_manifest"]
        assert bm.integration_boundaries[0].disposition == "proxy"
        assert bm.integration_boundaries[0].target_system == "external"
        assert bm.integration_boundaries[0].finding is None

    def test_unknown_integration_type_classified_as_drop_with_finding(self):
        bundle = _clean_bundle(
            integration_manifest=IntegrationManifestArtifact(
                schema_version="1.0.0",
                integrations=[
                    IntegrationEntry(
                        integration_id="int-drop",
                        integration_type="custom_magic",
                        target="https://magic.example.com",
                    ),
                ],
            ),
        )
        artifacts = _execute(bundle)
        bm: BehaviorManifest = artifacts["behavior_manifest"]
        assert bm.integration_boundaries[0].disposition == "drop"
        assert bm.integration_boundaries[0].finding is not None
        assert "custom_magic" in bm.integration_boundaries[0].finding.message


# ---------------------------------------------------------------------------
# Search strategy — Requirement 16.5
# ---------------------------------------------------------------------------


class TestSearchStrategy:
    def test_search_strategy_present_when_searchable_types_non_empty(self):
        bundle = _clean_bundle(
            search_config=SearchConfigArtifact(
                schema_version="1.0.0",
                searchable_types=["post", "page"],
                ranking_hints=[],
                facets=[{"field": "category", "type": "term"}],
            ),
        )
        content_model = _clean_content_model(
            collections=[
                StrapiCollection(
                    display_name="Post",
                    singular_name="post",
                    plural_name="posts",
                    api_id="api::post.post",
                    fields=[],
                    components=[],
                    source_post_type="post",
                ),
                StrapiCollection(
                    display_name="Page",
                    singular_name="page",
                    plural_name="pages",
                    api_id="api::page.page",
                    fields=[],
                    components=[],
                    source_post_type="page",
                ),
            ],
        )
        artifacts = _execute(bundle, content_model=content_model)
        bm: BehaviorManifest = artifacts["behavior_manifest"]
        assert bm.search_strategy is not None
        assert bm.search_strategy.enabled is True
        assert bm.search_strategy.implementation == "strapi_filter"
        assert sorted(bm.search_strategy.searchable_collections) == [
            "api::page.page",
            "api::post.post",
        ]
        assert len(bm.search_strategy.facets) == 1

    def test_search_strategy_absent_when_no_searchable_types(self):
        bundle = _clean_bundle()
        artifacts = _execute(bundle)
        bm: BehaviorManifest = artifacts["behavior_manifest"]
        assert bm.search_strategy is None


# ---------------------------------------------------------------------------
# Preview rules
# ---------------------------------------------------------------------------


class TestPreviewRules:
    def test_preview_rules_extracted_from_editorial_workflows(self):
        bundle = _clean_bundle(
            editorial_workflows=EditorialWorkflowsArtifact(
                schema_version="1.0.0",
                statuses_in_use=["publish", "draft", "pending"],
                scheduled_publishing=True,
                draft_behavior="save_as_draft",
                preview_expectations="live_preview",
                revision_policy="keep_all",
                comments_enabled=True,
                authoring_model="two_editor",
            ),
        )
        artifacts = _execute(bundle)
        bm: BehaviorManifest = artifacts["behavior_manifest"]
        assert bm.preview_rules["draft_behavior"] == "save_as_draft"
        assert bm.preview_rules["preview_expectations"] == "live_preview"
        assert bm.preview_rules["revision_policy"] == "keep_all"


# ---------------------------------------------------------------------------
# Metadata strategy
# ---------------------------------------------------------------------------


class TestMetadataStrategy:
    def test_metadata_strategy_from_seo_data(self):
        bundle = _clean_bundle(
            seo_full=SeoFullArtifact(
                schema_version="1.0.0",
                pages=[
                    SeoPageEntry(
                        canonical_url="/home",
                        source_plugin="yoast",
                        title_template="%%title%% | %%sitename%%",
                        og_metadata={"og:title": "Home"},
                        twitter_metadata={"twitter:card": "summary"},
                        schema_type_hints=["WebPage"],
                    ),
                ],
            ),
        )
        artifacts = _execute(bundle)
        bm: BehaviorManifest = artifacts["behavior_manifest"]
        assert bm.metadata_strategy["seo_plugin"] == "yoast"
        assert bm.metadata_strategy["title_template"] == "%%title%% | %%sitename%%"
        assert bm.metadata_strategy["has_og"] is True
        assert bm.metadata_strategy["has_twitter"] is True
        assert bm.metadata_strategy["has_schema_markup"] is True

    def test_metadata_strategy_empty_when_no_seo_pages(self):
        bundle = _clean_bundle()
        artifacts = _execute(bundle)
        bm: BehaviorManifest = artifacts["behavior_manifest"]
        assert bm.metadata_strategy["seo_plugin"] is None
        assert bm.metadata_strategy["has_og"] is False


# ---------------------------------------------------------------------------
# Unsupported constructs
# ---------------------------------------------------------------------------


class TestUnsupportedConstructs:
    def test_unsupported_capability_produces_finding(self):
        cap = _clean_capability_manifest(
            capabilities=[
                Capability(
                    capability_type="integration",
                    source_plugin="custom_plugin",
                    classification="unsupported",
                    confidence=0.5,
                ),
            ],
        )
        artifacts = _execute(_clean_bundle(), cap_manifest=cap)
        bm: BehaviorManifest = artifacts["behavior_manifest"]
        assert len(bm.unsupported_constructs) >= 1
        assert any("custom_plugin" in f.construct for f in bm.unsupported_constructs)


# ---------------------------------------------------------------------------
# MigrationMappingManifest — Requirements 17.1, 17.2
# ---------------------------------------------------------------------------


class TestMigrationMappingManifest:
    def test_type_mappings_from_collections(self):
        content_model = _clean_content_model(
            collections=[
                StrapiCollection(
                    display_name="Post",
                    singular_name="post",
                    plural_name="posts",
                    api_id="api::post.post",
                    fields=[],
                    components=[],
                    source_post_type="post",
                ),
            ],
        )
        artifacts = _execute(_clean_bundle(), content_model=content_model)
        mm: MigrationMappingManifest = artifacts["migration_mapping_manifest"]
        assert len(mm.type_mappings) == 1
        assert mm.type_mappings[0].source_post_type == "post"
        assert mm.type_mappings[0].target_api_id == "api::post.post"

    def test_field_mappings_from_collection_fields(self):
        content_model = _clean_content_model(
            collections=[
                StrapiCollection(
                    display_name="Post",
                    singular_name="post",
                    plural_name="posts",
                    api_id="api::post.post",
                    fields=[
                        StrapiFieldDefinition(name="title", strapi_type="text"),
                        StrapiFieldDefinition(name="body", strapi_type="richtext"),
                    ],
                    components=[],
                    source_post_type="post",
                ),
            ],
        )
        artifacts = _execute(_clean_bundle(), content_model=content_model)
        mm: MigrationMappingManifest = artifacts["migration_mapping_manifest"]
        assert len(mm.field_mappings) == 2
        title_map = next(f for f in mm.field_mappings if f.source_field == "title")
        assert title_map.transform == "direct"
        body_map = next(f for f in mm.field_mappings if f.source_field == "body")
        assert body_map.transform == "rich_text"

    def test_relation_mappings_from_content_model_relations(self):
        content_model = _clean_content_model(
            relations=[
                StrapiRelation(
                    source_collection="api::post.post",
                    target_collection="api::category.category",
                    field_name="categories",
                    relation_type="manyToMany",
                    source_relationship_id="rel-1",
                ),
            ],
        )
        artifacts = _execute(_clean_bundle(), content_model=content_model)
        mm: MigrationMappingManifest = artifacts["migration_mapping_manifest"]
        assert len(mm.relation_mappings) == 1
        assert mm.relation_mappings[0].source_relationship_id == "rel-1"
        assert mm.relation_mappings[0].relation_type == "manyToMany"

    def test_template_mappings_from_presentation(self):
        presentation = _clean_presentation(
            route_templates=[
                RouteTemplate(
                    route_pattern="/blog/[slug]",
                    layout="single",
                    source_template="single.php",
                    content_collection="api::post.post",
                ),
            ],
        )
        artifacts = _execute(_clean_bundle(), presentation=presentation)
        mm: MigrationMappingManifest = artifacts["migration_mapping_manifest"]
        assert len(mm.template_mappings) == 1
        assert mm.template_mappings[0].source_template == "single.php"
        assert mm.template_mappings[0].target_route_pattern == "/blog/[slug]"

    def test_term_mappings_from_taxonomies(self):
        bundle = _clean_bundle(
            taxonomies={"taxonomies": [{"name": "category"}, {"name": "post_tag"}]},
        )
        artifacts = _execute(bundle)
        mm: MigrationMappingManifest = artifacts["migration_mapping_manifest"]
        assert len(mm.term_mappings) == 2

    def test_media_mapping_strategy_defaults(self):
        artifacts = _execute(_clean_bundle())
        mm: MigrationMappingManifest = artifacts["migration_mapping_manifest"]
        assert mm.media_mapping_strategy.relation_aware is True
        assert mm.media_mapping_strategy.preserve_alt_text is True
        assert mm.media_mapping_strategy.preserve_caption is True

    def test_agent_result_contains_both_artifacts(self):
        artifacts = _execute(_clean_bundle())
        assert "behavior_manifest" in artifacts
        assert "migration_mapping_manifest" in artifacts
        assert isinstance(artifacts["behavior_manifest"], BehaviorManifest)
        assert isinstance(artifacts["migration_mapping_manifest"], MigrationMappingManifest)
