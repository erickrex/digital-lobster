from __future__ import annotations

import pytest

from src.adapters.base import MigrationRule, PluginAdapter, QAAssertion, SchemaContribution
from src.adapters.blocks import GutenbergCoreAdapter, KadenceBlocksAdapter
from src.adapters.custom_fields import (
    AcfAdapter,
    CarbonFieldsAdapter,
    MetaBoxAdapter,
    PodsAdapter,
)
from src.adapters.forms import (
    ContactForm7Adapter,
    GravityFormsAdapter,
    NinjaFormsAdapter,
    WpFormsAdapter,
)
from src.adapters.registry import build_adapter_registry, default_adapters
from src.adapters.seo import AioSeoAdapter, RankMathAdapter, YoastAdapter
from src.adapters.utilities import RedirectAdapter, WidgetSidebarAdapter
from src.models.bundle_artifacts import (
    ContentRelationshipsArtifact,
    EditorialWorkflowsArtifact,
    FieldUsageReportArtifact,
    IntegrationManifestArtifact,
    PageCompositionArtifact,
    PluginInstance,
    PluginInstancesArtifact,
    SearchConfigArtifact,
    SeoFullArtifact,
    SeoPageEntry,
)
from src.models.bundle_manifest import BundleManifest

def _empty_bundle(**overrides) -> BundleManifest:
    """Build a minimal BundleManifest with empty artifacts, applying overrides."""
    defaults: dict = dict(
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
        plugins_fingerprint={},
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
        content_relationships=ContentRelationshipsArtifact(schema_version="1.0.0", relationships=[]),
        field_usage_report=FieldUsageReportArtifact(schema_version="1.0.0", fields=[]),
        plugin_instances=PluginInstancesArtifact(schema_version="1.0.0", instances=[]),
        page_composition=PageCompositionArtifact(schema_version="1.0.0", pages=[]),
        seo_full=SeoFullArtifact(schema_version="1.0.0", pages=[]),
        editorial_workflows=EditorialWorkflowsArtifact(
            schema_version="1.0.0",
            statuses_in_use=["publish"],
            scheduled_publishing=False,
            draft_behavior="standard",
            preview_expectations="none",
            revision_policy="default",
            comments_enabled=False,
            authoring_model="single_editor",
        ),
        plugin_table_exports=[],
        search_config=SearchConfigArtifact(schema_version="1.0.0", searchable_types=[], ranking_hints=[], facets=[]),
        integration_manifest=IntegrationManifestArtifact(schema_version="1.0.0", integrations=[]),
    )
    defaults.update(overrides)
    return BundleManifest(**defaults)

# ---------------------------------------------------------------------------
# Expected plugin_family identifiers for all 15 adapters
# ---------------------------------------------------------------------------

EXPECTED_FAMILIES = {
    "acf", "pods", "meta_box", "carbon_fields",
    "yoast", "rank_math", "aio_seo",
    "cf7", "wpforms", "gravity_forms", "ninja_forms",
    "gutenberg_core", "kadence_blocks",
    "redirects", "widget_sidebar",
}

# ===================================================================
# 1. Each adapter returns correct plugin_family identifier
# ===================================================================

class TestPluginFamilyIdentifiers:
    """Each concrete adapter returns the expected plugin_family string."""
    @pytest.mark.parametrize(
        "adapter_cls, expected_family",
        [
            (AcfAdapter, "acf"),
            (PodsAdapter, "pods"),
            (MetaBoxAdapter, "meta_box"),
            (CarbonFieldsAdapter, "carbon_fields"),
            (YoastAdapter, "yoast"),
            (RankMathAdapter, "rank_math"),
            (AioSeoAdapter, "aio_seo"),
            (ContactForm7Adapter, "cf7"),
            (WpFormsAdapter, "wpforms"),
            (GravityFormsAdapter, "gravity_forms"),
            (NinjaFormsAdapter, "ninja_forms"),
            (GutenbergCoreAdapter, "gutenberg_core"),
            (KadenceBlocksAdapter, "kadence_blocks"),
            (RedirectAdapter, "redirects"),
            (WidgetSidebarAdapter, "widget_sidebar"),
        ],
    )
    def test_plugin_family(self, adapter_cls: type[PluginAdapter], expected_family: str):
        assert adapter_cls().plugin_family() == expected_family

    def test_default_adapters_cover_all_families(self):
        families = {a.plugin_family() for a in default_adapters()}
        assert families == EXPECTED_FAMILIES

    def test_build_adapter_registry_keys_match_families(self):
        registry = build_adapter_registry()
        assert set(registry.keys()) == EXPECTED_FAMILIES

# ===================================================================
# 2. ACF adapter maps repeaters to nested components
# ===================================================================

class TestAcfAdapterRepeaterMapping:
    """ACF adapter migration rules include repeater → nested component mapping."""
    def test_migration_rules_include_repeater(self):
        adapter = AcfAdapter()
        rules = adapter.migration_rules([])
        repeater_rules = [r for r in rules if r.source_construct == "acf_repeater"]
        assert len(repeater_rules) == 1
        rule = repeater_rules[0]
        assert rule.target_type == "component"
        assert rule.transform == "nested_component"

    def test_migration_rules_include_flexible_content(self):
        adapter = AcfAdapter()
        rules = adapter.migration_rules([])
        flex_rules = [r for r in rules if r.source_construct == "acf_flexible_content"]
        assert len(flex_rules) == 1
        assert flex_rules[0].transform == "dynamic_zone"

    def test_acf_classify_capabilities_from_field_groups(self):
        bundle = _empty_bundle(
            acf_field_groups={
                "field_groups": [
                    {"title": "Hero Section", "fields": [{"name": "heading"}, {"name": "image"}]},
                    {"title": "CTA Block", "fields": [{"name": "text"}]},
                ]
            }
        )
        caps = AcfAdapter().classify_capabilities(bundle)
        assert len(caps) == 2
        assert all(c.source_plugin == "acf" for c in caps)
        assert all(c.classification == "strapi_native" for c in caps)

# ===================================================================
# 3. Form adapters produce capabilities for each form instance
# ===================================================================

_FORM_ADAPTERS = [
    (ContactForm7Adapter, "cf7"),
    (WpFormsAdapter, "wpforms"),
    (GravityFormsAdapter, "gravity_forms"),
    (NinjaFormsAdapter, "ninja_forms"),
]

class TestFormAdapters:
    """Form adapters classify one capability per form instance in the bundle."""
    @pytest.mark.parametrize("adapter_cls, plugin_name", _FORM_ADAPTERS)
    def test_produces_capability_per_form_instance(self, adapter_cls, plugin_name):
        instances = [
            PluginInstance(
                instance_id=f"{plugin_name}_form_{i}",
                source_plugin=plugin_name,
                instance_type="form",
            )
            for i in range(3)
        ]
        bundle = _empty_bundle(
            plugin_instances=PluginInstancesArtifact(
                schema_version="1.0.0", instances=instances,
            ),
        )
        caps = adapter_cls().classify_capabilities(bundle)
        assert len(caps) == 3
        assert all(c.capability_type == "form" for c in caps)
        assert all(c.source_plugin == plugin_name for c in caps)

    @pytest.mark.parametrize("adapter_cls, plugin_name", _FORM_ADAPTERS)
    def test_no_capabilities_when_no_matching_instances(self, adapter_cls, plugin_name):
        bundle = _empty_bundle()
        caps = adapter_cls().classify_capabilities(bundle)
        assert caps == []

    @pytest.mark.parametrize("adapter_cls, plugin_name", _FORM_ADAPTERS)
    def test_migration_rules_use_form_strategy_transform(self, adapter_cls, plugin_name):
        rules = adapter_cls().migration_rules([])
        form_rules = [r for r in rules if r.transform == "form_strategy"]
        assert len(form_rules) >= 1

# ===================================================================
# 4. unsupported_cases returns non-empty list for each adapter
# ===================================================================

class TestUnsupportedCases:
    """Every adapter declares at least one unsupported case."""
    @pytest.mark.parametrize("adapter", default_adapters(), ids=lambda a: a.plugin_family())
    def test_unsupported_cases_non_empty(self, adapter: PluginAdapter):
        cases = adapter.unsupported_cases()
        assert len(cases) > 0
        assert all(isinstance(c, str) and len(c) > 0 for c in cases)
