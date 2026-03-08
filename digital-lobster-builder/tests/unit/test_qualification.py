from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.agents.qualification import QualificationAgent
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
from src.orchestrator.errors import QualificationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_bundle(**overrides: Any) -> BundleManifest:
    """Build a minimal BundleManifest that passes all qualification checks."""
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
        content_relationships=ContentRelationshipsArtifact(schema_version="1.0.0", relationships=[]),
        field_usage_report=FieldUsageReportArtifact(schema_version="1.0.0", fields=[]),
        plugin_instances=PluginInstancesArtifact(schema_version="1.0.0", instances=[]),
        page_composition=PageCompositionArtifact(schema_version="1.0.0", pages=[]),
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
        search_config=SearchConfigArtifact(schema_version="1.0.0", searchable_types=[], ranking_hints=[], facets=[]),
        integration_manifest=IntegrationManifestArtifact(schema_version="1.0.0", integrations=[]),
    )
    defaults.update(overrides)
    return BundleManifest(**defaults)

def _inject_active_plugin(
    bundle: BundleManifest, slug: str, family: str = "",
) -> BundleManifest:
    """Return a new bundle with the given slug injected as an active plugin."""
    existing = list(bundle.plugins_fingerprint.get("plugins", []))
    entry: dict[str, str] = {"slug": slug, "status": "active"}
    if family:
        entry["family"] = family
    existing.append(entry)
    return bundle.model_copy(update={"plugins_fingerprint": {"plugins": existing}})

def _make_agent() -> QualificationAgent:
    return QualificationAgent(gradient_client=None)

def _run(coro):
    return asyncio.run(coro)

# ---------------------------------------------------------------------------
# Page builder disqualification — Requirement 21.2
# ---------------------------------------------------------------------------

class TestPageBuilderDisqualification:
    def test_elementor_disqualifies(self):
        bundle = _inject_active_plugin(_clean_bundle(), "elementor")
        with pytest.raises(QualificationError) as exc_info:
            _run(_make_agent().execute({"bundle_manifest": bundle}))

        err = exc_info.value
        assert err.readiness_report.qualified is False
        critical = [f for f in err.findings if f.severity == FindingSeverity.CRITICAL]
        assert len(critical) == 1
        assert critical[0].construct == "page_builder"
        assert "elementor" in critical[0].message

    def test_divi_disqualifies(self):
        bundle = _inject_active_plugin(_clean_bundle(), "divi-builder")
        with pytest.raises(QualificationError) as exc_info:
            _run(_make_agent().execute({"bundle_manifest": bundle}))

        assert exc_info.value.readiness_report.qualified is False
        critical = [f for f in exc_info.value.findings if f.severity == FindingSeverity.CRITICAL]
        assert any("divi-builder" in f.message for f in critical)

    def test_inactive_page_builder_does_not_disqualify(self):
        bundle = _clean_bundle(
            plugins_fingerprint={"plugins": [{"slug": "elementor", "status": "inactive"}]},
        )
        result = _run(_make_agent().execute({"bundle_manifest": bundle}))
        assert result.artifacts["readiness_report"].qualified is True

# ---------------------------------------------------------------------------
# WooCommerce disqualification — Requirement 21.3
# ---------------------------------------------------------------------------

class TestWooCommerceDisqualification:
    def test_woocommerce_disqualifies(self):
        bundle = _inject_active_plugin(_clean_bundle(), "woocommerce")
        with pytest.raises(QualificationError) as exc_info:
            _run(_make_agent().execute({"bundle_manifest": bundle}))

        err = exc_info.value
        assert err.readiness_report.qualified is False
        critical = [f for f in err.findings if f.severity == FindingSeverity.CRITICAL]
        assert len(critical) == 1
        assert critical[0].construct == "woocommerce"

# ---------------------------------------------------------------------------
# Multilingual disqualification — Requirement 21.4
# ---------------------------------------------------------------------------

class TestMultilingualDisqualification:
    def test_wpml_disqualifies(self):
        bundle = _inject_active_plugin(_clean_bundle(), "wpml")
        with pytest.raises(QualificationError) as exc_info:
            _run(_make_agent().execute({"bundle_manifest": bundle}))

        err = exc_info.value
        assert err.readiness_report.qualified is False
        critical = [f for f in err.findings if f.severity == FindingSeverity.CRITICAL]
        assert len(critical) == 1
        assert critical[0].construct == "multilingual"
        assert "wpml" in critical[0].message

    def test_polylang_disqualifies(self):
        bundle = _inject_active_plugin(_clean_bundle(), "polylang")
        with pytest.raises(QualificationError) as exc_info:
            _run(_make_agent().execute({"bundle_manifest": bundle}))

        critical = [f for f in exc_info.value.findings if f.severity == FindingSeverity.CRITICAL]
        assert any("polylang" in f.message for f in critical)

# ---------------------------------------------------------------------------
# Membership disqualification — Requirement 21.5
# ---------------------------------------------------------------------------

class TestMembershipDisqualification:
    def test_buddypress_disqualifies(self):
        bundle = _inject_active_plugin(_clean_bundle(), "buddypress")
        with pytest.raises(QualificationError) as exc_info:
            _run(_make_agent().execute({"bundle_manifest": bundle}))

        err = exc_info.value
        assert err.readiness_report.qualified is False
        critical = [f for f in err.findings if f.severity == FindingSeverity.CRITICAL]
        assert len(critical) == 1
        assert critical[0].construct == "membership"
        assert "buddypress" in critical[0].message

    def test_memberpress_disqualifies(self):
        bundle = _inject_active_plugin(_clean_bundle(), "memberpress")
        with pytest.raises(QualificationError) as exc_info:
            _run(_make_agent().execute({"bundle_manifest": bundle}))

        critical = [f for f in exc_info.value.findings if f.severity == FindingSeverity.CRITICAL]
        assert any("memberpress" in f.message for f in critical)

# ---------------------------------------------------------------------------
# Enterprise editorial workflow disqualification — Requirement 21.6
# ---------------------------------------------------------------------------

class TestEnterpriseEditorialDisqualification:
    def test_custom_status_disqualifies(self):
        bundle = _clean_bundle(
            editorial_workflows=EditorialWorkflowsArtifact(
                schema_version="1.0.0",
                statuses_in_use=["publish", "draft", "in-review"],
                scheduled_publishing=False,
                draft_behavior="standard",
                preview_expectations="none",
                revision_policy="default",
                comments_enabled=False,
                authoring_model="single_editor",
            ),
        )
        with pytest.raises(QualificationError) as exc_info:
            _run(_make_agent().execute({"bundle_manifest": bundle}))

        err = exc_info.value
        assert err.readiness_report.qualified is False
        critical = [f for f in err.findings if f.severity == FindingSeverity.CRITICAL]
        assert len(critical) == 1
        assert critical[0].construct == "editorial_workflows"
        assert "in-review" in critical[0].message

    def test_standard_statuses_do_not_disqualify(self):
        bundle = _clean_bundle(
            editorial_workflows=EditorialWorkflowsArtifact(
                schema_version="1.0.0",
                statuses_in_use=["publish", "draft", "pending", "private", "trash", "future", "auto-draft", "inherit"],
                scheduled_publishing=True,
                draft_behavior="standard",
                preview_expectations="none",
                revision_policy="default",
                comments_enabled=True,
                authoring_model="two_editor",
            ),
        )
        result = _run(_make_agent().execute({"bundle_manifest": bundle}))
        assert result.artifacts["readiness_report"].qualified is True

# ---------------------------------------------------------------------------
# Combined disqualification — multiple criteria fail
# ---------------------------------------------------------------------------

class TestCombinedDisqualification:
    def test_elementor_plus_woocommerce_produces_multiple_critical_findings(self):
        bundle = _inject_active_plugin(_clean_bundle(), "elementor")
        bundle = _inject_active_plugin(bundle, "woocommerce")

        with pytest.raises(QualificationError) as exc_info:
            _run(_make_agent().execute({"bundle_manifest": bundle}))

        err = exc_info.value
        assert err.readiness_report.qualified is False
        critical = [f for f in err.findings if f.severity == FindingSeverity.CRITICAL]
        assert len(critical) == 2
        constructs = {f.construct for f in critical}
        assert constructs == {"page_builder", "woocommerce"}

    def test_three_disqualifying_categories(self):
        bundle = _inject_active_plugin(_clean_bundle(), "divi")
        bundle = _inject_active_plugin(bundle, "wpml")
        bundle = _inject_active_plugin(bundle, "buddypress")

        with pytest.raises(QualificationError) as exc_info:
            _run(_make_agent().execute({"bundle_manifest": bundle}))

        critical = [f for f in exc_info.value.findings if f.severity == FindingSeverity.CRITICAL]
        assert len(critical) == 3
        constructs = {f.construct for f in critical}
        assert constructs == {"page_builder", "multilingual", "membership"}

# ---------------------------------------------------------------------------
# Advisory findings on qualified site — Requirement 21.7, 21.9
# ---------------------------------------------------------------------------

class TestAdvisoryFindings:
    def test_unsupported_active_plugin_produces_warning(self):
        """An active plugin not in any supported family produces a WARNING, not CRITICAL."""
        bundle = _inject_active_plugin(_clean_bundle(), "some-unknown-plugin")
        result = _run(_make_agent().execute({"bundle_manifest": bundle}))

        report = result.artifacts["readiness_report"]
        assert report.qualified is True
        warnings = [f for f in report.findings if f.severity == FindingSeverity.WARNING]
        assert len(warnings) == 1
        assert warnings[0].construct == "plugin:some-unknown-plugin"

    def test_page_builder_block_namespaces_produce_warning(self):
        """Page-builder block namespaces in blocks_usage produce a WARNING when
        no page-builder plugin is active."""
        bundle = _clean_bundle(
            blocks_usage={
                "block_types": [
                    {"name": "elementor/heading"},
                    {"name": "elementor/section"},
                    {"name": "core/paragraph"},
                ],
            },
        )
        result = _run(_make_agent().execute({"bundle_manifest": bundle}))

        report = result.artifacts["readiness_report"]
        assert report.qualified is True
        warnings = [f for f in report.findings if f.severity == FindingSeverity.WARNING]
        assert len(warnings) == 1
        assert warnings[0].construct == "page_builder_blocks"
        assert "2" in warnings[0].message  # 2 page-builder block types

    def test_irrelevant_plugin_produces_no_finding(self):
        """Infrastructure plugins (akismet, wordfence, etc.) produce no findings."""
        bundle = _inject_active_plugin(_clean_bundle(), "akismet")
        bundle = _inject_active_plugin(bundle, "wordfence")
        result = _run(_make_agent().execute({"bundle_manifest": bundle}))

        report = result.artifacts["readiness_report"]
        assert report.qualified is True
        assert report.findings == []

    def test_supported_family_plugin_produces_no_finding(self):
        """A plugin in a supported family produces no findings."""
        bundle = _inject_active_plugin(_clean_bundle(), "yoast-seo", family="yoast")
        result = _run(_make_agent().execute({"bundle_manifest": bundle}))

        report = result.artifacts["readiness_report"]
        assert report.qualified is True
        assert report.findings == []

# ---------------------------------------------------------------------------
# Clean site passes — Requirement 21.9
# ---------------------------------------------------------------------------

class TestCleanSiteQualifies:
    def test_clean_bundle_qualifies(self):
        result = _run(_make_agent().execute({"bundle_manifest": _clean_bundle()}))

        report = result.artifacts["readiness_report"]
        assert report.qualified is True
        assert len(report.checked_criteria) == 6
        assert report.findings == []

    def test_readiness_report_is_in_artifacts(self):
        result = _run(_make_agent().execute({"bundle_manifest": _clean_bundle()}))
        assert "readiness_report" in result.artifacts
        assert result.agent_name == "qualification"
