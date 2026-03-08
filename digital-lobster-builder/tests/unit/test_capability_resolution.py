from __future__ import annotations

import asyncio
import logging
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.adapters.custom_fields import AcfAdapter
from src.adapters.registry import default_adapters
from src.agents.capability_resolution import CapabilityResolutionAgent
from src.models.bundle_artifacts import (
    ContentRelationshipsArtifact,
    EditorialWorkflowsArtifact,
    FieldUsageReportArtifact,
    IntegrationEntry,
    IntegrationManifestArtifact,
    PageCompositionArtifact,
    PluginInstancesArtifact,
    SearchConfigArtifact,
    SeoFullArtifact,
)
from src.models.bundle_manifest import BundleManifest
from src.models.capability_manifest import Capability
from src.models.finding import Finding, FindingSeverity
from src.orchestrator.errors import CompilationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean_bundle(**overrides: Any) -> BundleManifest:
    """Build a minimal BundleManifest that passes capability resolution."""
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


def _make_agent(adapters=None) -> CapabilityResolutionAgent:
    return CapabilityResolutionAgent(gradient_client=None, adapters=adapters)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# ACF adapter delegation — Requirements 13.5, 18.4
# ---------------------------------------------------------------------------


class TestAdapterDelegation:
    def test_acf_plugin_delegates_to_adapter(self):
        """Inject plugin with family='acf' and ACF field groups; verify
        capabilities come from the adapter."""
        bundle = _inject_active_plugin(_clean_bundle(), slug="acf-pro", family="acf")
        bundle = bundle.model_copy(
            update={
                "acf_field_groups": {
                    "field_groups": [
                        {"title": "Hero Section", "fields": [{"name": "heading"}, {"name": "image"}]},
                        {"title": "Footer CTA", "fields": [{"name": "text"}]},
                    ]
                }
            }
        )

        agent = _make_agent()
        result = _run(agent.execute({"bundle_manifest": bundle}))
        manifest = result.artifacts["capability_manifest"]

        # ACF adapter should produce one capability per field group
        acf_caps = [c for c in manifest.capabilities if c.source_plugin == "acf"]
        assert len(acf_caps) == 2
        assert all(c.capability_type == "content_model" for c in acf_caps)
        assert all(c.classification == "strapi_native" for c in acf_caps)
        assert all(c.confidence >= 0.8 for c in acf_caps)

    def test_adapter_spy_called_exactly_once(self):
        """Verify the adapter's classify_capabilities is called once per plugin."""
        real_adapter = AcfAdapter()
        spy = MagicMock(wraps=real_adapter)
        spy.plugin_family = real_adapter.plugin_family

        bundle = _inject_active_plugin(_clean_bundle(), slug="acf", family="acf")
        agent = _make_agent(adapters=[spy])
        _run(agent.execute({"bundle_manifest": bundle}))

        spy.classify_capabilities.assert_called_once()

    def test_supported_plugin_produces_no_unsupported_finding(self):
        """A plugin with a registered adapter should not produce an unsupported finding."""
        bundle = _inject_active_plugin(_clean_bundle(), slug="acf-pro", family="acf")
        agent = _make_agent()
        result = _run(agent.execute({"bundle_manifest": bundle}))
        manifest = result.artifacts["capability_manifest"]

        unsupported = [
            f for f in manifest.findings
            if f.stage == "capability_resolution" and "acf" in f.construct
        ]
        assert unsupported == []


# ---------------------------------------------------------------------------
# Unsupported plugin produces Finding — Requirements 13.3, 18.5
# ---------------------------------------------------------------------------


class TestUnsupportedPluginFinding:
    def test_unknown_plugin_produces_warning_finding(self):
        """An active plugin without an adapter produces a WARNING finding
        with stage='capability_resolution'."""
        bundle = _inject_active_plugin(_clean_bundle(), slug="tablepress")
        agent = _make_agent()
        result = _run(agent.execute({"bundle_manifest": bundle}))
        manifest = result.artifacts["capability_manifest"]

        findings = [
            f for f in manifest.findings
            if f.stage == "capability_resolution" and "tablepress" in f.construct
        ]
        assert len(findings) == 1
        assert findings[0].severity == FindingSeverity.WARNING
        assert findings[0].recommended_action

    def test_multiple_unsupported_plugins_produce_separate_findings(self):
        """Each unsupported plugin gets its own finding."""
        bundle = _inject_active_plugin(_clean_bundle(), slug="tablepress")
        bundle = _inject_active_plugin(bundle, slug="fancy-slider")
        agent = _make_agent()
        result = _run(agent.execute({"bundle_manifest": bundle}))
        manifest = result.artifacts["capability_manifest"]

        plugin_findings = [
            f for f in manifest.findings
            if f.stage == "capability_resolution"
        ]
        constructs = {f.construct for f in plugin_findings}
        assert "plugin:tablepress" in constructs
        assert "plugin:fancy-slider" in constructs


# ---------------------------------------------------------------------------
# LLM fallback for low-confidence capabilities — Requirement 13.5
# ---------------------------------------------------------------------------


class TestLlmFallback:
    def test_low_confidence_shortcode_triggers_llm_stub(self, caplog):
        """Shortcodes produce confidence=0.7 capabilities, which should
        trigger the LLM fallback stub and log accordingly."""
        bundle = _clean_bundle(
            shortcodes_inventory={
                "shortcodes": [
                    {"tag": "gallery", "source_plugin": "core"},
                ]
            }
        )
        agent = _make_agent()
        with caplog.at_level(logging.INFO):
            result = _run(agent.execute({"bundle_manifest": bundle}))

        assert "LLM fallback" in caplog.text

        # The stub returns capabilities unchanged, so the shortcode cap
        # should still be present in the manifest
        manifest = result.artifacts["capability_manifest"]
        shortcode_caps = [
            c for c in manifest.capabilities if c.capability_type == "shortcode"
        ]
        assert len(shortcode_caps) == 1
        assert shortcode_caps[0].confidence == 0.7

    def test_high_confidence_caps_skip_llm_fallback(self, caplog):
        """When all capabilities have confidence >= 0.8, no LLM fallback
        should be triggered."""
        bundle = _inject_active_plugin(_clean_bundle(), slug="acf", family="acf")
        agent = _make_agent()
        with caplog.at_level(logging.INFO):
            _run(agent.execute({"bundle_manifest": bundle}))

        assert "LLM fallback" not in caplog.text


# ---------------------------------------------------------------------------
# Critical finding aborts stage — Requirement 18.5
# ---------------------------------------------------------------------------


class TestCriticalFindingAbort:
    def test_critical_finding_raises_compilation_error(self):
        """When a critical Finding is present, the stage must raise
        CompilationError with stage_name='capability_resolution'."""
        # The agent itself only produces WARNING findings for unsupported
        # plugins and business-critical integrations. To trigger a CRITICAL
        # abort, we subclass and inject a critical finding during resolution.
        agent = _make_agent()

        # Monkey-patch _resolve_plugins to inject a critical finding
        original_resolve = agent._resolve_plugins

        def _patched_resolve(bundle, capabilities, findings):
            original_resolve(bundle, capabilities, findings)
            findings.append(Finding(
                severity=FindingSeverity.CRITICAL,
                stage="capability_resolution",
                construct="integration:payment-gateway",
                message="Business-critical payment integration cannot be migrated",
                recommended_action="Manual migration required",
            ))

        agent._resolve_plugins = _patched_resolve

        bundle = _clean_bundle()
        with pytest.raises(CompilationError) as exc_info:
            _run(agent.execute({"bundle_manifest": bundle}))

        err = exc_info.value
        assert err.stage_name == "capability_resolution"
        assert len(err.findings) >= 1
        critical = [f for f in err.findings if f.severity == FindingSeverity.CRITICAL]
        assert len(critical) >= 1

    def test_non_critical_findings_do_not_abort(self):
        """WARNING findings should not cause CompilationError."""
        bundle = _inject_active_plugin(_clean_bundle(), slug="tablepress")
        agent = _make_agent()
        # Should not raise
        result = _run(agent.execute({"bundle_manifest": bundle}))
        manifest = result.artifacts["capability_manifest"]
        warnings = [f for f in manifest.findings if f.severity == FindingSeverity.WARNING]
        assert len(warnings) >= 1


# ---------------------------------------------------------------------------
# Empty bundle produces baseline capabilities — Requirements 13.1, 13.2
# ---------------------------------------------------------------------------


class TestEmptyBundleBaseline:
    def test_empty_bundle_produces_settings_and_editorial_capabilities(self):
        """A bundle with non-empty settings/options should produce baseline
        capabilities from site_settings, site_options, and editorial_workflows."""
        bundle = _clean_bundle(
            site_settings={"blogname": "Test Site"},
            site_options={"permalink_structure": "/%postname%/"},
        )
        agent = _make_agent()
        result = _run(agent.execute({"bundle_manifest": bundle}))
        manifest = result.artifacts["capability_manifest"]

        # site_settings and site_options each produce a content_model capability
        settings_caps = [
            c for c in manifest.capabilities
            if c.details.get("source") in ("site_settings", "site_options")
        ]
        assert len(settings_caps) == 2

        # editorial_workflows produces an editorial capability
        editorial_caps = [
            c for c in manifest.capabilities if c.capability_type == "editorial"
        ]
        assert len(editorial_caps) == 1
        assert editorial_caps[0].details["authoring_model"] == "single_editor"

    def test_empty_bundle_has_no_findings(self):
        """A clean empty bundle should produce zero findings."""
        bundle = _clean_bundle()
        agent = _make_agent()
        result = _run(agent.execute({"bundle_manifest": bundle}))
        manifest = result.artifacts["capability_manifest"]
        assert manifest.findings == []


# ---------------------------------------------------------------------------
# CapabilityManifest categorisation — Requirement 13.2
# ---------------------------------------------------------------------------


class TestManifestCategorisation:
    def test_content_model_capabilities_categorised(self):
        """Capabilities with type 'content_model' appear in
        content_model_capabilities."""
        bundle = _clean_bundle()
        agent = _make_agent()
        result = _run(agent.execute({"bundle_manifest": bundle}))
        manifest = result.artifacts["capability_manifest"]

        for cap in manifest.content_model_capabilities:
            assert cap.capability_type == "content_model"

    def test_presentation_capabilities_categorised(self):
        """Widget, template, and shortcode capabilities appear in
        presentation_capabilities."""
        bundle = _clean_bundle(
            widgets={"sidebars": [{"id": "sidebar-1", "source_plugin": None}]},
            page_templates={"templates": [{"name": "full-width", "source_plugin": None}]},
            shortcodes_inventory={"shortcodes": [{"tag": "gallery", "source_plugin": "core"}]},
        )
        agent = _make_agent()
        result = _run(agent.execute({"bundle_manifest": bundle}))
        manifest = result.artifacts["capability_manifest"]

        pres_types = {c.capability_type for c in manifest.presentation_capabilities}
        assert "widget" in pres_types
        assert "template" in pres_types
        assert "shortcode" in pres_types

    def test_behavior_capabilities_categorised(self):
        """Form, search_filter, integration, and editorial capabilities
        appear in behavior_capabilities."""
        bundle = _clean_bundle(
            forms_config={"forms": [{"id": "contact-1", "source_plugin": "cf7"}]},
            search_config=SearchConfigArtifact(
                schema_version="1.0.0",
                searchable_types=["post"],
                ranking_hints=[],
                facets=[],
            ),
            integration_manifest=IntegrationManifestArtifact(
                schema_version="1.0.0",
                integrations=[
                    IntegrationEntry(
                        integration_id="mailchimp",
                        integration_type="crm",
                        target="https://api.mailchimp.com",
                        business_critical=False,
                    )
                ],
            ),
        )
        agent = _make_agent()
        result = _run(agent.execute({"bundle_manifest": bundle}))
        manifest = result.artifacts["capability_manifest"]

        behavior_types = {c.capability_type for c in manifest.behavior_capabilities}
        assert "form" in behavior_types
        assert "search_filter" in behavior_types
        assert "integration" in behavior_types
        assert "editorial" in behavior_types

    def test_plugin_capabilities_grouped_by_source(self):
        """Capabilities with source_plugin are grouped in plugin_capabilities."""
        bundle = _inject_active_plugin(_clean_bundle(), slug="acf-pro", family="acf")
        bundle = bundle.model_copy(
            update={
                "acf_field_groups": {
                    "field_groups": [{"title": "Hero", "fields": [{"name": "h"}]}]
                }
            }
        )
        agent = _make_agent()
        result = _run(agent.execute({"bundle_manifest": bundle}))
        manifest = result.artifacts["capability_manifest"]

        assert "acf" in manifest.plugin_capabilities
        assert len(manifest.plugin_capabilities["acf"]) >= 1
