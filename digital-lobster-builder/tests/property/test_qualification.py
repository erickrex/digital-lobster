from __future__ import annotations

import asyncio

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.agents.qualification import (
    QualificationAgent,
    _MEMBERSHIP_SLUGS,
    _MULTILINGUAL_SLUGS,
    _PAGE_BUILDER_SLUGS,
    _WOOCOMMERCE_SLUGS,
)
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

# Standard editorial statuses that do NOT trigger enterprise-editorial disqualification.
_STANDARD_STATUSES = ["publish", "draft", "pending", "private", "trash", "future"]


def _clean_bundle(**overrides) -> BundleManifest:
    """Build a minimal BundleManifest that passes all qualification checks."""
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


def _inject_active_plugin(bundle: BundleManifest, slug: str) -> BundleManifest:
    """Return a new bundle with the given slug injected as an active plugin."""
    existing = list(bundle.plugins_fingerprint.get("plugins", []))
    existing.append({"slug": slug, "status": "active"})
    return bundle.model_copy(update={"plugins_fingerprint": {"plugins": existing}})


def _make_agent() -> QualificationAgent:
    return QualificationAgent(gradient_client=None)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Slug sets combined for Property 21
# ---------------------------------------------------------------------------

_ALL_DISQUALIFYING_SLUGS = sorted(
    _PAGE_BUILDER_SLUGS | _WOOCOMMERCE_SLUGS | _MULTILINGUAL_SLUGS | _MEMBERSHIP_SLUGS
)


# ===========================================================================
# Property 21: Qualification system disqualification
# Validates: Requirements 21.2, 21.3, 21.4, 21.5, 21.6, 21.7, 21.8
# ===========================================================================


class TestQualificationDisqualification:
    """Injecting any disqualifying plugin slug into a clean bundle causes
    QualificationError with qualified=False and at least one critical finding."""

    @given(slug=st.sampled_from(_ALL_DISQUALIFYING_SLUGS))
    @settings(max_examples=len(_ALL_DISQUALIFYING_SLUGS))
    def test_disqualifying_plugin_raises_qualification_error(self, slug: str):
        """**Validates: Requirements 21.2, 21.3, 21.4, 21.5, 21.8**

        For any slug drawn from the known disqualifying sets (page builders,
        WooCommerce, multilingual, membership), injecting it as an active
        plugin into a clean bundle must raise QualificationError.
        """
        bundle = _inject_active_plugin(_clean_bundle(), slug)
        agent = _make_agent()

        with pytest.raises(QualificationError) as exc_info:
            _run(agent.execute({"bundle_manifest": bundle}))

        err = exc_info.value
        assert err.readiness_report is not None
        assert err.readiness_report.qualified is False
        critical = [f for f in err.findings if f.severity == FindingSeverity.CRITICAL]
        assert len(critical) >= 1

    @given(slug=st.sampled_from(_ALL_DISQUALIFYING_SLUGS))
    @settings(max_examples=len(_ALL_DISQUALIFYING_SLUGS))
    def test_disqualifying_plugin_finding_references_correct_stage(self, slug: str):
        """**Validates: Requirements 21.8**

        Every critical finding from a disqualifying plugin must reference
        the 'qualification' stage.
        """
        bundle = _inject_active_plugin(_clean_bundle(), slug)
        agent = _make_agent()

        with pytest.raises(QualificationError) as exc_info:
            _run(agent.execute({"bundle_manifest": bundle}))

        for finding in exc_info.value.findings:
            if finding.severity == FindingSeverity.CRITICAL:
                assert finding.stage == "qualification"

    @given(
        custom_status=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_"),
            min_size=3,
            max_size=30,
        ).filter(
            lambda s: s.lower() not in {
                "publish", "draft", "pending", "private", "trash",
                "future", "auto-draft", "inherit",
            }
        )
    )
    @settings(max_examples=30)
    def test_custom_editorial_status_disqualifies(self, custom_status: str):
        """**Validates: Requirements 21.6, 21.8**

        A site with custom editorial statuses (beyond standard WordPress
        statuses) must fail qualification with a critical finding.
        """
        bundle = _clean_bundle(
            editorial_workflows=EditorialWorkflowsArtifact(
                schema_version="1.0.0",
                statuses_in_use=["publish", "draft", custom_status],
                scheduled_publishing=False,
                draft_behavior="standard",
                preview_expectations="none",
                revision_policy="default",
                comments_enabled=False,
                authoring_model="single_editor",
            ),
        )
        agent = _make_agent()

        with pytest.raises(QualificationError) as exc_info:
            _run(agent.execute({"bundle_manifest": bundle}))

        err = exc_info.value
        assert err.readiness_report is not None
        assert err.readiness_report.qualified is False
        critical = [f for f in err.findings if f.severity == FindingSeverity.CRITICAL]
        assert len(critical) >= 1
        assert any(f.construct == "editorial_workflows" for f in critical)

    @given(slug=st.sampled_from(_ALL_DISQUALIFYING_SLUGS))
    @settings(max_examples=len(_ALL_DISQUALIFYING_SLUGS))
    def test_readiness_report_lists_checked_criteria(self, slug: str):
        """**Validates: Requirements 21.7, 21.8**

        The ReadinessReport attached to QualificationError must list all
        checked criteria even when the site is disqualified.
        """
        bundle = _inject_active_plugin(_clean_bundle(), slug)
        agent = _make_agent()

        with pytest.raises(QualificationError) as exc_info:
            _run(agent.execute({"bundle_manifest": bundle}))

        report = exc_info.value.readiness_report
        assert len(report.checked_criteria) >= 6


# ===========================================================================
# Property 22: Qualification success report
# Validates: Requirements 21.9
# ===========================================================================


class TestQualificationSuccessReport:
    """A clean bundle with no disqualifying plugins and standard editorial
    statuses qualifies successfully with qualified=True."""

    @given(
        statuses=st.lists(
            st.sampled_from(_STANDARD_STATUSES),
            min_size=1,
            max_size=4,
            unique=True,
        )
    )
    @settings(max_examples=30)
    def test_clean_bundle_qualifies(self, statuses: list[str]):
        """**Validates: Requirements 21.9**

        A bundle with only standard editorial statuses and no disqualifying
        plugins must pass qualification with qualified=True.
        """
        bundle = _clean_bundle(
            editorial_workflows=EditorialWorkflowsArtifact(
                schema_version="1.0.0",
                statuses_in_use=statuses,
                scheduled_publishing=False,
                draft_behavior="standard",
                preview_expectations="none",
                revision_policy="default",
                comments_enabled=False,
                authoring_model="single_editor",
            ),
        )
        agent = _make_agent()
        result = _run(agent.execute({"bundle_manifest": bundle}))

        report = result.artifacts["readiness_report"]
        assert report.qualified is True
        assert len(report.checked_criteria) >= 6

    @given(
        statuses=st.lists(
            st.sampled_from(_STANDARD_STATUSES),
            min_size=1,
            max_size=4,
            unique=True,
        )
    )
    @settings(max_examples=30)
    def test_success_report_has_no_critical_findings(self, statuses: list[str]):
        """**Validates: Requirements 21.9**

        When qualification succeeds, the ReadinessReport must contain zero
        critical findings.
        """
        bundle = _clean_bundle(
            editorial_workflows=EditorialWorkflowsArtifact(
                schema_version="1.0.0",
                statuses_in_use=statuses,
                scheduled_publishing=False,
                draft_behavior="standard",
                preview_expectations="none",
                revision_policy="default",
                comments_enabled=False,
                authoring_model="single_editor",
            ),
        )
        agent = _make_agent()
        result = _run(agent.execute({"bundle_manifest": bundle}))

        report = result.artifacts["readiness_report"]
        critical = [f for f in report.findings if f.severity == FindingSeverity.CRITICAL]
        assert critical == []
