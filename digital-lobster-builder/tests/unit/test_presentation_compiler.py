from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.agents.presentation_compiler import PresentationCompilerAgent
from src.models.bundle_artifacts import (
    ContentRelationshipsArtifact,
    EditorialWorkflowsArtifact,
    FieldUsageReportArtifact,
    IntegrationManifestArtifact,
    PageCompositionArtifact,
    PageCompositionEntry,
    PluginInstancesArtifact,
    SearchConfigArtifact,
    SeoFullArtifact,
)
from src.models.bundle_manifest import BundleManifest
from src.models.capability_manifest import CapabilityManifest
from src.models.presentation_manifest import PresentationManifest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean_bundle(**overrides: Any) -> BundleManifest:
    """Build a minimal BundleManifest for presentation compiler tests."""
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
        content_model_capabilities=[],
        presentation_capabilities=[],
        behavior_capabilities=[],
        plugin_capabilities={},
    )
    defaults.update(overrides)
    return CapabilityManifest(**defaults)


def _make_page(**overrides: Any) -> PageCompositionEntry:
    """Build a PageCompositionEntry with sensible defaults."""
    defaults: dict[str, Any] = dict(
        canonical_url="https://example.com/about/",
        template="page.php",
        blocks=[],
        shortcodes=[],
        widget_placements=[],
        forms_embedded=[],
        plugin_components=[],
        enqueued_assets=[],
        content_sections=[],
    )
    defaults.update(overrides)
    return PageCompositionEntry(**defaults)


def _make_agent() -> PresentationCompilerAgent:
    return PresentationCompilerAgent(gradient_client=None)


def _run(coro):
    return asyncio.run(coro)


def _execute(
    bundle: BundleManifest,
    cap_manifest: CapabilityManifest | None = None,
) -> PresentationManifest:
    agent = _make_agent()
    context: dict[str, Any] = {
        "bundle_manifest": bundle,
        "capability_manifest": cap_manifest or _clean_capability_manifest(),
    }
    result = _run(agent.execute(context))
    return result.artifacts["presentation_manifest"]


# ---------------------------------------------------------------------------
# Page template → route template mapping — Requirement 15.1
# ---------------------------------------------------------------------------


class TestRouteTemplateMapping:
    """Page composition pages are converted into RouteTemplate objects."""

    def test_single_page_produces_route_template(self):
        page = _make_page(
            canonical_url="https://example.com/about/",
            template="page.php",
        )
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=[page]
            ),
        )
        manifest = _execute(bundle)

        assert len(manifest.route_templates) == 1
        rt = manifest.route_templates[0]
        assert rt.route_pattern == "/about"
        assert rt.layout == "page"
        assert rt.source_template == "page.php"

    def test_multiple_pages_produce_multiple_route_templates(self):
        pages = [
            _make_page(canonical_url="https://example.com/about/", template="page.php"),
            _make_page(canonical_url="https://example.com/blog/hello/", template="single.php"),
            _make_page(canonical_url="https://example.com/contact/", template="page.php"),
        ]
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=pages
            ),
        )
        manifest = _execute(bundle)

        patterns = {rt.route_pattern for rt in manifest.route_templates}
        assert "/about" in patterns
        assert "/blog/[slug]" in patterns
        assert "/contact" in patterns

    def test_route_template_layout_derived_from_template_name(self):
        page = _make_page(
            canonical_url="https://example.com/services/web-design/",
            template="templates/full-width.php",
        )
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=[page]
            ),
        )
        manifest = _execute(bundle)

        rt = manifest.route_templates[0]
        assert rt.layout == "full-width"

    def test_page_without_template_uses_default_layout(self):
        page = _make_page(
            canonical_url="https://example.com/orphan/",
            template="",
        )
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=[page]
            ),
        )
        manifest = _execute(bundle)

        rt = manifest.route_templates[0]
        assert rt.layout == "default"
        assert rt.source_template == "default"

    def test_content_collection_inferred_from_content_sections(self):
        page = _make_page(
            canonical_url="https://example.com/blog/my-post/",
            template="single.php",
            content_sections=[{"content_type": "posts"}],
        )
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=[page]
            ),
        )
        manifest = _execute(bundle)

        rt = manifest.route_templates[0]
        assert rt.content_collection == "posts"

    def test_content_collection_inferred_from_single_template(self):
        page = _make_page(
            canonical_url="https://example.com/blog/my-post/",
            template="single-post.php",
            content_sections=[],
        )
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=[page]
            ),
        )
        manifest = _execute(bundle)

        rt = manifest.route_templates[0]
        assert rt.content_collection == "posts"

    def test_duplicate_route_patterns_are_deduplicated(self):
        pages = [
            _make_page(canonical_url="https://example.com/about/", template="page.php"),
            _make_page(canonical_url="https://example.com/about/", template="page.php"),
        ]
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=pages
            ),
        )
        manifest = _execute(bundle)

        patterns = [rt.route_pattern for rt in manifest.route_templates]
        assert patterns.count("/about") == 1

    def test_root_url_produces_root_route(self):
        page = _make_page(
            canonical_url="https://example.com/",
            template="front-page.php",
        )
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=[page]
            ),
        )
        manifest = _execute(bundle)

        rt = manifest.route_templates[0]
        assert rt.route_pattern == "/"

    def test_route_templates_sorted_by_pattern(self):
        pages = [
            _make_page(canonical_url="https://example.com/zebra/", template="page.php"),
            _make_page(canonical_url="https://example.com/alpha/", template="page.php"),
        ]
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=pages
            ),
        )
        manifest = _execute(bundle)

        patterns = [rt.route_pattern for rt in manifest.route_templates]
        assert patterns == sorted(patterns)


# ---------------------------------------------------------------------------
# Widget placement → section component mapping — Requirement 15.6
# ---------------------------------------------------------------------------


class TestWidgetSectionMapping:
    """Widget placements in page_composition become SectionDefinition objects."""

    def test_widget_placement_produces_section(self):
        page = _make_page(
            widget_placements=[
                {"widget_type": "recent-posts", "widget_id": "rp-1", "sidebar_id": "sidebar-1"},
            ],
        )
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=[page]
            ),
        )
        manifest = _execute(bundle)

        widget_sections = [s for s in manifest.sections if s.source_type == "widget"]
        assert len(widget_sections) >= 1
        section = widget_sections[0]
        assert section.name == "recent-posts"
        assert section.source_type == "widget"
        assert "widgets" in section.component_path

    def test_multiple_widget_types_produce_distinct_sections(self):
        page = _make_page(
            widget_placements=[
                {"widget_type": "recent-posts", "widget_id": "rp-1", "sidebar_id": "sidebar-1"},
                {"widget_type": "categories", "widget_id": "cat-1", "sidebar_id": "sidebar-1"},
                {"widget_type": "search", "widget_id": "search-1", "sidebar_id": "footer-1"},
            ],
        )
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=[page]
            ),
        )
        manifest = _execute(bundle)

        widget_names = {s.name for s in manifest.sections if s.source_type == "widget"}
        assert "recent-posts" in widget_names
        assert "categories" in widget_names
        assert "search" in widget_names

    def test_duplicate_widget_types_across_pages_deduplicated(self):
        pages = [
            _make_page(
                canonical_url="https://example.com/page-a/",
                widget_placements=[{"widget_type": "search", "widget_id": "s-1"}],
            ),
            _make_page(
                canonical_url="https://example.com/page-b/",
                widget_placements=[{"widget_type": "search", "widget_id": "s-2"}],
            ),
        ]
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=pages
            ),
        )
        manifest = _execute(bundle)

        search_sections = [s for s in manifest.sections if s.name == "search"]
        assert len(search_sections) == 1

    def test_widget_source_plugin_preserved(self):
        page = _make_page(
            widget_placements=[
                {"widget_type": "custom-html", "widget_id": "ch-1", "source_plugin": "my-plugin"},
            ],
        )
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=[page]
            ),
        )
        manifest = _execute(bundle)

        section = next(s for s in manifest.sections if s.name == "custom-html")
        assert section.source_plugin == "my-plugin"

    def test_widget_placement_without_type_or_id_skipped(self):
        page = _make_page(
            widget_placements=[
                {},  # no widget_type or widget_id
                {"widget_type": "calendar", "widget_id": "cal-1"},
            ],
        )
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=[page]
            ),
        )
        manifest = _execute(bundle)

        widget_sections = [s for s in manifest.sections if s.source_type == "widget"]
        assert len(widget_sections) == 1
        assert widget_sections[0].name == "calendar"


# ---------------------------------------------------------------------------
# Unsupported fragment → FallbackZone — Requirement 15.5
# ---------------------------------------------------------------------------


class TestFallbackZones:
    """Shortcodes, blocks, and plugin components without adapter support
    produce FallbackZone entries rather than being silently dropped."""

    def test_unsupported_shortcode_produces_fallback(self):
        page = _make_page(
            canonical_url="https://example.com/contact/",
            shortcodes=[
                {"tag": "pricing-table", "content": "[pricing-table]", "source_plugin": "unknown-plugin"},
            ],
        )
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=[page]
            ),
        )
        manifest = _execute(bundle)

        fz = next(
            (z for z in manifest.fallback_zones if z.zone_name == "shortcode-pricing-table"),
            None,
        )
        assert fz is not None, "Unsupported shortcode was silently dropped"
        assert fz.page_url == "https://example.com/contact/"
        assert "pricing-table" in fz.reason
        assert "no adapter support" in fz.reason.lower()

    def test_unsupported_block_produces_fallback(self):
        page = _make_page(
            canonical_url="https://example.com/about/",
            blocks=[
                {"blockName": "third-party/map", "innerHTML": "<div>map</div>"},
            ],
        )
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=[page]
            ),
        )
        manifest = _execute(bundle)

        fz = next(
            (z for z in manifest.fallback_zones if z.zone_name == "block-third-party/map"),
            None,
        )
        assert fz is not None, "Unsupported block was silently dropped"
        assert fz.page_url == "https://example.com/about/"
        assert fz.raw_html == "<div>map</div>"

    def test_unsupported_plugin_component_produces_fallback(self):
        page = _make_page(
            canonical_url="https://example.com/services/",
            plugin_components=[
                {"name": "fancy-slider", "source_plugin": "unknown-slider", "raw_html": "<div>slider</div>"},
            ],
        )
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=[page]
            ),
        )
        manifest = _execute(bundle)

        fz = next(
            (z for z in manifest.fallback_zones if z.zone_name == "plugin-fancy-slider"),
            None,
        )
        assert fz is not None, "Unsupported plugin component was silently dropped"
        assert fz.raw_html == "<div>slider</div>"
        assert "fancy-slider" in fz.reason

    def test_core_blocks_do_not_produce_fallback(self):
        page = _make_page(
            blocks=[
                {"blockName": "core/paragraph", "innerHTML": "<p>Hello</p>"},
                {"blockName": "core/heading", "innerHTML": "<h2>Title</h2>"},
            ],
        )
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=[page]
            ),
        )
        manifest = _execute(bundle)

        block_fallbacks = [fz for fz in manifest.fallback_zones if fz.zone_name.startswith("block-")]
        assert len(block_fallbacks) == 0

    def test_supported_adapter_plugin_does_not_produce_fallback(self):
        """Shortcodes from a supported plugin family should NOT produce fallback zones."""
        page = _make_page(
            canonical_url="https://example.com/page/",
            shortcodes=[
                {"tag": "contact-form-7", "content": "[contact-form-7]", "source_plugin": "cf7"},
            ],
        )
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=[page]
            ),
        )
        manifest = _execute(bundle)

        shortcode_fallbacks = [
            fz for fz in manifest.fallback_zones if fz.zone_name == "shortcode-contact-form-7"
        ]
        assert len(shortcode_fallbacks) == 0

    def test_multiple_unsupported_fragments_all_captured(self):
        page = _make_page(
            canonical_url="https://example.com/complex/",
            shortcodes=[
                {"tag": "gallery-pro", "content": "[gallery-pro]"},
            ],
            blocks=[
                {"blockName": "vendor/chart", "innerHTML": "<canvas/>"},
            ],
            plugin_components=[
                {"name": "popup-maker", "raw_html": "<div>popup</div>"},
            ],
        )
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=[page]
            ),
        )
        manifest = _execute(bundle)

        zone_names = {fz.zone_name for fz in manifest.fallback_zones}
        assert "shortcode-gallery-pro" in zone_names
        assert "block-vendor/chart" in zone_names
        assert "plugin-popup-maker" in zone_names

    def test_fallback_zones_sorted_by_page_url_and_zone_name(self):
        pages = [
            _make_page(
                canonical_url="https://example.com/z-page/",
                shortcodes=[{"tag": "beta-sc"}],
            ),
            _make_page(
                canonical_url="https://example.com/a-page/",
                shortcodes=[{"tag": "alpha-sc"}],
            ),
        ]
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=pages
            ),
        )
        manifest = _execute(bundle)

        keys = [(fz.page_url, fz.zone_name) for fz in manifest.fallback_zones]
        assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# Layout compilation — Requirement 15.1
# ---------------------------------------------------------------------------


class TestLayoutCompilation:
    """Page templates become LayoutDefinition objects."""

    def test_page_template_produces_layout(self):
        bundle = _clean_bundle(
            page_templates={"templates": {"page.php": {}}},
        )
        manifest = _execute(bundle)

        layout_names = {l.name for l in manifest.layouts}
        assert "page" in layout_names

    def test_default_layout_always_present(self):
        bundle = _clean_bundle()
        manifest = _execute(bundle)

        layout_names = {l.name for l in manifest.layouts}
        assert "default" in layout_names

    def test_default_layout_not_duplicated_when_template_named_default(self):
        bundle = _clean_bundle(
            page_templates={"templates": {"default": {}}},
        )
        manifest = _execute(bundle)

        default_count = sum(1 for l in manifest.layouts if l.name == "default")
        assert default_count == 1

    def test_layout_template_path_follows_convention(self):
        page = _make_page(template="templates/sidebar-left.php")
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=[page]
            ),
        )
        manifest = _execute(bundle)

        layout = next(l for l in manifest.layouts if l.name == "sidebar-left")
        assert layout.template_path == "src/layouts/sidebar-left.astro"

    def test_layouts_sorted_by_name(self):
        bundle = _clean_bundle(
            page_templates={"templates": {"zebra.php": {}, "alpha.php": {}, "middle.php": {}}},
        )
        manifest = _execute(bundle)

        names = [l.name for l in manifest.layouts]
        assert names == sorted(names)


# ---------------------------------------------------------------------------
# Style token compilation
# ---------------------------------------------------------------------------


class TestStyleTokenCompilation:
    """theme_mods, global_styles, css_sources produce style tokens."""

    def test_theme_mod_colors_become_tokens(self):
        bundle = _clean_bundle(
            theme_mods={"background_color": "#ffffff", "accent_color": "#ff0000"},
        )
        manifest = _execute(bundle)

        assert manifest.style_tokens["--theme-background-color"] == "#ffffff"
        assert manifest.style_tokens["--theme-accent-color"] == "#ff0000"

    def test_global_style_palette_becomes_tokens(self):
        bundle = _clean_bundle(
            global_styles={
                "settings": {
                    "color": {
                        "palette": [
                            {"slug": "primary", "color": "#0073aa"},
                        ]
                    }
                }
            },
        )
        manifest = _execute(bundle)

        assert manifest.style_tokens["--wp-preset-color-primary"] == "#0073aa"

    def test_css_custom_properties_become_tokens(self):
        bundle = _clean_bundle(
            css_sources={"custom_properties": {"--brand-color": "#123456"}},
        )
        manifest = _execute(bundle)

        assert manifest.style_tokens["--brand-color"] == "#123456"

    def test_style_tokens_sorted_deterministically(self):
        bundle = _clean_bundle(
            theme_mods={"background_color": "#fff", "accent_color": "#000"},
            css_sources={"custom_properties": {"--z-var": "1", "--a-var": "2"}},
        )
        manifest = _execute(bundle)

        keys = list(manifest.style_tokens.keys())
        assert keys == sorted(keys)

    def test_empty_sources_produce_empty_tokens(self):
        bundle = _clean_bundle()
        manifest = _execute(bundle)

        assert manifest.style_tokens == {}


# ---------------------------------------------------------------------------
# Agent result structure
# ---------------------------------------------------------------------------


class TestAgentResult:
    def test_agent_result_contains_presentation_manifest(self):
        agent = _make_agent()
        bundle = _clean_bundle()
        context: dict[str, Any] = {
            "bundle_manifest": bundle,
            "capability_manifest": _clean_capability_manifest(),
        }
        result = _run(agent.execute(context))

        assert result.agent_name == "presentation_compiler"
        assert "presentation_manifest" in result.artifacts
        assert isinstance(result.artifacts["presentation_manifest"], PresentationManifest)
