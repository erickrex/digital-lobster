from __future__ import annotations

import asyncio
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

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
from src.models.capability_manifest import Capability, CapabilityManifest
from src.models.presentation_manifest import PresentationManifest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEMPLATES = st.sampled_from([
    "default", "single.php", "page.php", "archive.php",
    "templates/full-width.php", "templates/sidebar-left.php",
])

_WIDGET_TYPES = st.sampled_from([
    "recent-posts", "categories", "search", "calendar",
    "tag-cloud", "custom-html", "nav-menu",
])

_SHORTCODE_TAGS = st.sampled_from([
    "gallery", "contact-form", "map-embed", "pricing-table",
    "testimonial-slider", "video-player",
])

_BLOCK_NAMES = st.sampled_from([
    "custom/hero-banner", "custom/testimonial", "custom/pricing",
    "third-party/map", "third-party/chart",
])

_CANONICAL_URLS = st.sampled_from([
    "https://example.com/",
    "https://example.com/about/",
    "https://example.com/blog/hello-world/",
    "https://example.com/services/web-design/",
    "https://example.com/contact/",
])

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

def _make_agent() -> PresentationCompilerAgent:
    return PresentationCompilerAgent(gradient_client=None)

def _run(coro):
    return asyncio.run(coro)

def _execute(
    bundle: BundleManifest,
    cap_manifest: CapabilityManifest,
) -> PresentationManifest:
    agent = _make_agent()
    context: dict[str, Any] = {
        "bundle_manifest": bundle,
        "capability_manifest": cap_manifest,
    }
    result = _run(agent.execute(context))
    return result.artifacts["presentation_manifest"]

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

@st.composite
def page_composition_entries(draw) -> PageCompositionEntry:
    """Generate a PageCompositionEntry with a template, widgets, shortcodes, and blocks."""
    return PageCompositionEntry(
        canonical_url=draw(_CANONICAL_URLS),
        template=draw(_TEMPLATES),
        blocks=[
            {"blockName": draw(_BLOCK_NAMES), "innerHTML": "<div>block</div>"}
            for _ in range(draw(st.integers(min_value=0, max_value=2)))
        ],
        shortcodes=[
            {"tag": draw(_SHORTCODE_TAGS), "content": "[shortcode]"}
            for _ in range(draw(st.integers(min_value=0, max_value=2)))
        ],
        widget_placements=[
            {
                "widget_type": draw(_WIDGET_TYPES),
                "widget_id": f"widget-{i}",
                "sidebar_id": draw(st.sampled_from(["sidebar-1", "footer-1"])),
            }
            for i in range(draw(st.integers(min_value=0, max_value=2)))
        ],
        forms_embedded=[],
        plugin_components=[],
        enqueued_assets=[],
        content_sections=[],
    )

# ===========================================================================
# Property 14: Presentation compiler completeness
# ===========================================================================

class TestPresentationCompilerCompleteness:
    """For any bundle with page_composition pages, widgets, and unsupported
    shortcodes/blocks:
    - Every page template produces a layout
    - Every page produces a route template
    - Widget placements produce section definitions
    - Unsupported shortcodes/blocks produce fallback zones (not silently dropped)
    """
    @given(
        pages=st.lists(page_composition_entries(), min_size=1, max_size=5),
    )
    @settings(max_examples=100)
    def test_every_page_template_produces_a_layout(
        self, pages: list[PageCompositionEntry]
    ):
        """        Every unique page template referenced in page_composition must
        produce a corresponding LayoutDefinition in the manifest.
        """
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=pages
            ),
        )
        manifest = _execute(bundle, _clean_capability_manifest())

        expected_templates = {p.template for p in pages if p.template}
        layout_names = {l.name for l in manifest.layouts}

        from src.agents.presentation_compiler import _template_to_layout_name

        for template in expected_templates:
            expected_name = _template_to_layout_name(template)
            assert expected_name in layout_names, (
                f"Template '{template}' (layout name '{expected_name}') "
                f"has no layout in manifest. Got: {layout_names}"
            )

    @given(
        pages=st.lists(page_composition_entries(), min_size=1, max_size=5),
    )
    @settings(max_examples=100)
    def test_every_page_produces_a_route_template(
        self, pages: list[PageCompositionEntry]
    ):
        """        Every page in page_composition must produce a route template.
        Deduplication by route_pattern is expected, so we check that every
        unique canonical_url maps to a route_pattern present in the manifest.
        """
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=pages
            ),
        )
        manifest = _execute(bundle, _clean_capability_manifest())

        from src.agents.presentation_compiler import PresentationCompilerAgent

        expected_patterns = {
            PresentationCompilerAgent._url_to_route_pattern(p.canonical_url)
            for p in pages
        }
        actual_patterns = {r.route_pattern for r in manifest.route_templates}

        assert expected_patterns == actual_patterns, (
            f"Missing route patterns: {expected_patterns - actual_patterns}"
        )

    @given(
        pages=st.lists(page_composition_entries(), min_size=1, max_size=5),
    )
    @settings(max_examples=100)
    def test_widget_placements_produce_section_definitions(
        self, pages: list[PageCompositionEntry]
    ):
        """        Every widget placement across all pages must produce a
        SectionDefinition in the manifest (deduplicated by name).
        """
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=pages
            ),
        )
        manifest = _execute(bundle, _clean_capability_manifest())

        from src.agents.presentation_compiler import _slugify

        expected_widget_names: set[str] = set()
        for page in pages:
            for placement in page.widget_placements:
                wtype = placement.get("widget_type") or placement.get("type", "")
                wid = placement.get("widget_id") or placement.get("id", "")
                if wtype or wid:
                    expected_widget_names.add(_slugify(wtype or wid))

        section_names = {s.name for s in manifest.sections if s.source_type == "widget"}

        for name in expected_widget_names:
            assert name in section_names, (
                f"Widget '{name}' has no section in manifest. "
                f"Got widget sections: {section_names}"
            )

    @given(
        pages=st.lists(page_composition_entries(), min_size=1, max_size=5),
    )
    @settings(max_examples=100)
    def test_unsupported_shortcodes_produce_fallback_zones(
        self, pages: list[PageCompositionEntry]
    ):
        """        Shortcodes without adapter support must produce FallbackZone entries
        rather than being silently dropped.
        """
        # Filter to pages that actually have shortcodes
        pages_with_shortcodes = [p for p in pages if p.shortcodes]
        if not pages_with_shortcodes:
            return

        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=pages
            ),
        )
        manifest = _execute(bundle, _clean_capability_manifest())

        fallback_zone_names = {fz.zone_name for fz in manifest.fallback_zones}

        for page in pages_with_shortcodes:
            for shortcode in page.shortcodes:
                tag = shortcode.get("tag") or shortcode.get("name", "unknown")
                expected_zone = f"shortcode-{tag}"
                assert expected_zone in fallback_zone_names, (
                    f"Shortcode '{tag}' on page '{page.canonical_url}' "
                    f"was silently dropped — no fallback zone found. "
                    f"Got: {fallback_zone_names}"
                )

    @given(
        pages=st.lists(page_composition_entries(), min_size=1, max_size=5),
    )
    @settings(max_examples=100)
    def test_unsupported_blocks_produce_fallback_zones(
        self, pages: list[PageCompositionEntry]
    ):
        """        Non-core blocks without adapter support must produce FallbackZone
        entries rather than being silently dropped.
        """
        pages_with_blocks = [
            p for p in pages
            if any(
                b.get("blockName", "")
                and not b.get("blockName", "").startswith("core/")
                for b in p.blocks
            )
        ]
        if not pages_with_blocks:
            return

        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=pages
            ),
        )
        manifest = _execute(bundle, _clean_capability_manifest())

        fallback_zone_names = {fz.zone_name for fz in manifest.fallback_zones}

        for page in pages_with_blocks:
            for block in page.blocks:
                block_name = block.get("blockName", "")
                if not block_name or block_name.startswith("core/"):
                    continue
                expected_zone = f"block-{block_name}"
                assert expected_zone in fallback_zone_names, (
                    f"Block '{block_name}' on page '{page.canonical_url}' "
                    f"was silently dropped — no fallback zone found. "
                    f"Got: {fallback_zone_names}"
                )

# ===========================================================================
# Property 15: Presentation compiler determinism
# ===========================================================================

class TestPresentationCompilerDeterminism:
    """Running the compiler twice with identical inputs produces identical
    PresentationManifest outputs."""
    @given(
        pages=st.lists(page_composition_entries(), min_size=1, max_size=5),
    )
    @settings(max_examples=100)
    def test_identical_inputs_produce_identical_outputs(
        self, pages: list[PageCompositionEntry]
    ):
        """        For any valid inputs, running the Presentation_Compiler twice must
        produce identical PresentationManifest outputs.
        """
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=pages
            ),
        )
        cap = _clean_capability_manifest()

        manifest_1 = _execute(bundle, cap)
        manifest_2 = _execute(bundle, cap)

        assert manifest_1 == manifest_2, (
            "Presentation compiler produced different outputs for identical inputs"
        )
