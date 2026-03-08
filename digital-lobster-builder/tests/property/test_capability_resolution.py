from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

from src.adapters.base import PluginAdapter
from src.adapters.registry import default_adapters
from src.agents.capability_resolution import CapabilityResolutionAgent
from src.models.bundle_artifacts import (
    ContentRelationshipsArtifact,
    EditorialWorkflowsArtifact,
    FieldUsageReportArtifact,
    IntegrationManifestArtifact,
    PageCompositionArtifact,
    PluginInstancesArtifact,
    SearchConfigArtifact,
    SeoFullArtifact,
)
from src.models.bundle_manifest import BundleManifest
from src.models.finding import FindingSeverity

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_CLASSIFICATIONS = {"strapi_native", "astro_runtime", "unsupported"}

_ALL_ADAPTERS = default_adapters()
_ADAPTER_FAMILIES = [a.plugin_family() for a in _ALL_ADAPTERS]

# Slugs that have no adapter and are not in any disqualifying set.
_UNSUPPORTED_SLUGS = [
    "tablepress",
    "wp-super-cache",
    "custom-gallery-pro",
    "fancy-slider",
    "my-unknown-plugin",
]

def _clean_bundle(**overrides) -> BundleManifest:
    """Build a minimal BundleManifest that passes capability resolution."""
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

def _inject_active_plugin(
    bundle: BundleManifest, slug: str, family: str = ""
) -> BundleManifest:
    """Return a new bundle with the given slug injected as an active plugin."""
    existing = list(bundle.plugins_fingerprint.get("plugins", []))
    entry: dict[str, str] = {"slug": slug, "status": "active"}
    if family:
        entry["family"] = family
    existing.append(entry)
    return bundle.model_copy(update={"plugins_fingerprint": {"plugins": existing}})

def _make_agent(
    adapters: list[PluginAdapter] | None = None,
) -> CapabilityResolutionAgent:
    return CapabilityResolutionAgent(
        gradient_client=None, adapters=adapters
    )

def _run(coro):
    return asyncio.run(coro)

# ===========================================================================
# Property 8: Capability classification completeness
# ===========================================================================

class TestCapabilityClassificationCompleteness:
    """For any bundle with active plugins, the CapabilityManifest must
    contain capabilities with valid classification and confidence values."""
    @given(family=st.sampled_from(_ADAPTER_FAMILIES))
    @settings(max_examples=100)
    def test_supported_plugin_produces_valid_capabilities(self, family: str):
        """        For any supported plugin family, the CapabilityManifest must contain
        at least one capability with a valid classification value and a
        confidence score between 0.0 and 1.0.
        """
        bundle = _inject_active_plugin(
            _clean_bundle(), slug=f"{family}-plugin", family=family
        )
        agent = _make_agent()
        result = _run(agent.execute({"bundle_manifest": bundle}))

        manifest = result.artifacts["capability_manifest"]
        assert len(manifest.capabilities) >= 1

        for cap in manifest.capabilities:
            assert cap.classification in _VALID_CLASSIFICATIONS, (
                f"Invalid classification '{cap.classification}' for {cap}"
            )
            assert 0.0 <= cap.confidence <= 1.0, (
                f"Confidence {cap.confidence} out of range for {cap}"
            )

    @given(slug=st.sampled_from(_UNSUPPORTED_SLUGS))
    @settings(max_examples=100)
    def test_unsupported_plugin_capabilities_have_valid_classification(
        self, slug: str
    ):
        """        Even for unsupported plugins, any capabilities produced must have
        valid classification values and confidence scores.
        """
        bundle = _inject_active_plugin(_clean_bundle(), slug=slug)
        agent = _make_agent()
        result = _run(agent.execute({"bundle_manifest": bundle}))

        manifest = result.artifacts["capability_manifest"]
        for cap in manifest.capabilities:
            assert cap.classification in _VALID_CLASSIFICATIONS
            assert 0.0 <= cap.confidence <= 1.0

# ===========================================================================
# Property 9: Unsupported capability Finding production
# ===========================================================================

class TestUnsupportedCapabilityFindingProduction:
    """For any active plugin without an adapter, a Finding with
    stage='capability_resolution' must be produced."""
    @given(slug=st.sampled_from(_UNSUPPORTED_SLUGS))
    @settings(max_examples=100)
    def test_unsupported_plugin_produces_finding(self, slug: str):
        """        For any active plugin without a registered adapter, the
        CapabilityManifest must contain a Finding with
        stage='capability_resolution' referencing the plugin.
        """
        bundle = _inject_active_plugin(_clean_bundle(), slug=slug)
        agent = _make_agent()
        result = _run(agent.execute({"bundle_manifest": bundle}))

        manifest = result.artifacts["capability_manifest"]
        cap_res_findings = [
            f
            for f in manifest.findings
            if f.stage == "capability_resolution"
        ]
        assert len(cap_res_findings) >= 1, (
            f"Expected at least one finding for unsupported plugin '{slug}'"
        )

        # At least one finding must reference this plugin
        plugin_findings = [
            f for f in cap_res_findings if slug in f.construct
        ]
        assert len(plugin_findings) >= 1, (
            f"No finding references plugin '{slug}'"
        )

    @given(slug=st.sampled_from(_UNSUPPORTED_SLUGS))
    @settings(max_examples=100)
    def test_unsupported_finding_has_required_fields(self, slug: str):
        """        Each Finding for an unsupported plugin must have non-empty construct,
        message, recommended_action, and severity of CRITICAL or WARNING.
        """
        bundle = _inject_active_plugin(_clean_bundle(), slug=slug)
        agent = _make_agent()
        result = _run(agent.execute({"bundle_manifest": bundle}))

        manifest = result.artifacts["capability_manifest"]
        plugin_findings = [
            f
            for f in manifest.findings
            if f.stage == "capability_resolution" and slug in f.construct
        ]

        for finding in plugin_findings:
            assert finding.construct, "Finding construct must be non-empty"
            assert finding.message, "Finding message must be non-empty"
            assert finding.recommended_action, (
                "Finding recommended_action must be non-empty"
            )
            assert finding.severity in {
                FindingSeverity.CRITICAL,
                FindingSeverity.WARNING,
            }, f"Unsupported finding severity must be CRITICAL or WARNING, got {finding.severity}"

# ===========================================================================
# Property 10: Adapter-first classification
# ===========================================================================

class TestAdapterFirstClassification:
    """When an adapter exists for a plugin family, the adapter's
    classify_capabilities() must be called (adapter-first, not LLM-first)."""
    @given(adapter=st.sampled_from(_ALL_ADAPTERS))
    @settings(max_examples=100)
    def test_adapter_classify_called_for_supported_family(
        self, adapter: PluginAdapter
    ):
        """        When a plugin with a registered adapter family is present in the
        bundle, the adapter's classify_capabilities() must be invoked and
        the resulting capabilities must have confidence >= 0.8.
        """
        family = adapter.plugin_family()
        bundle = _inject_active_plugin(
            _clean_bundle(), slug=f"{family}-plugin", family=family
        )

        # Wrap the real adapter with a spy to verify it was called
        spy_adapter = MagicMock(wraps=adapter)
        spy_adapter.plugin_family = adapter.plugin_family

        agent = _make_agent(adapters=[spy_adapter])
        result = _run(agent.execute({"bundle_manifest": bundle}))

        spy_adapter.classify_capabilities.assert_called_once()

        # Capabilities from the adapter should have confidence >= 0.8
        manifest = result.artifacts["capability_manifest"]
        adapter_caps = [
            c
            for c in manifest.capabilities
            if c.source_plugin == family
        ]
        for cap in adapter_caps:
            assert cap.confidence >= 0.8, (
                f"Adapter-classified capability for '{family}' has "
                f"confidence {cap.confidence} < 0.8"
            )

    @given(adapter=st.sampled_from(_ALL_ADAPTERS))
    @settings(max_examples=100)
    def test_adapter_family_produces_no_unsupported_finding(
        self, adapter: PluginAdapter
    ):
        """        When a plugin has a registered adapter, the capability resolution
        stage must NOT produce an 'unsupported' Finding for that plugin.
        """
        family = adapter.plugin_family()
        slug = f"{family}-plugin"
        bundle = _inject_active_plugin(
            _clean_bundle(), slug=slug, family=family
        )

        agent = _make_agent()
        result = _run(agent.execute({"bundle_manifest": bundle}))

        manifest = result.artifacts["capability_manifest"]
        unsupported_findings = [
            f
            for f in manifest.findings
            if f.stage == "capability_resolution"
            and slug in f.construct
        ]
        assert unsupported_findings == [], (
            f"Adapter-supported family '{family}' should not produce "
            f"unsupported findings, got: {unsupported_findings}"
        )
