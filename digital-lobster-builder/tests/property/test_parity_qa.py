from __future__ import annotations

import asyncio
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.adapters.base import PluginAdapter, QAAssertion
from src.adapters.registry import default_adapters
from src.agents.parity_qa import ParityQAAgent
from src.models.behavior_manifest import BehaviorManifest
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
from src.models.finding import Finding, FindingSeverity
from src.models.parity_report import PARITY_CATEGORIES, ParityReport, SnapshotComparison
from src.models.presentation_manifest import (
    PresentationManifest,
    RouteTemplate,
)
from src.orchestrator.errors import ParityGateError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean_bundle(**overrides: Any) -> BundleManifest:
    """Build a minimal BundleManifest for parity QA tests."""
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
    defaults: dict[str, Any] = dict(capabilities=[], findings=[])
    defaults.update(overrides)
    return CapabilityManifest(**defaults)


def _clean_presentation(**overrides: Any) -> PresentationManifest:
    defaults: dict[str, Any] = dict(
        layouts=[], route_templates=[], sections=[], fallback_zones=[], style_tokens={}
    )
    defaults.update(overrides)
    return PresentationManifest(**defaults)


def _clean_behavior(**overrides: Any) -> BehaviorManifest:
    defaults: dict[str, Any] = dict(
        redirects=[],
        metadata_strategy={},
        forms_strategy=[],
        preview_rules={},
        integration_boundaries=[],
        unsupported_constructs=[],
    )
    defaults.update(overrides)
    return BehaviorManifest(**defaults)


def _make_agent(threshold: float = 0.8) -> ParityQAAgent:
    return ParityQAAgent(gradient_client=None, threshold=threshold)


def _run(coro):
    return asyncio.run(coro)


def _build_context(
    bundle: BundleManifest,
    cap_manifest: CapabilityManifest | None = None,
    presentation: PresentationManifest | None = None,
    behavior: BehaviorManifest | None = None,
    **extra: Any,
) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "bundle_manifest": bundle,
        "capability_manifest": cap_manifest or _clean_capability_manifest(),
        "presentation_manifest": presentation or _clean_presentation(),
        "behavior_manifest": behavior or _clean_behavior(),
    }
    ctx.update(extra)
    return ctx


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_TEMPLATES = st.sampled_from(
    ["default", "full-width", "sidebar-left", "landing", "archive", "single"]
)


@st.composite
def page_composition_entries(draw, with_snapshot: bool = False) -> PageCompositionEntry:
    """Generate a PageCompositionEntry, optionally with a snapshot_ref."""
    idx = draw(st.integers(min_value=1, max_value=500))
    template = draw(_TEMPLATES)
    snapshot = f"snapshots/page-{idx}.html" if with_snapshot else None
    return PageCompositionEntry(
        canonical_url=f"https://example.com/page-{idx}/",
        template=template,
        blocks=[],
        shortcodes=[],
        widget_placements=[],
        forms_embedded=[],
        plugin_components=[],
        enqueued_assets=[],
        content_sections=[],
        snapshot_ref=snapshot,
    )


# Adapter families that produce QA assertions
_ADAPTER_FAMILIES = sorted(a.plugin_family() for a in default_adapters())


# ===========================================================================
# Property 23: Parity report category coverage
# Validates: Requirements 20.1, 20.3
# ===========================================================================


class TestParityReportCategoryCoverage:
    """For any valid inputs, the ParityReport must contain exactly the 7
    parity categories, each score between 0.0 and 1.0, and overall_score
    must equal the mean of all category scores."""

    @given(
        page_count=st.integers(min_value=0, max_value=5),
        template=_TEMPLATES,
    )
    @settings(max_examples=100)
    def test_report_contains_all_seven_categories(
        self, page_count: int, template: str
    ):
        """**Validates: Requirements 20.1, 20.3**

        The ParityReport must contain numeric scores for all 7 parity
        categories regardless of input data.
        """
        pages = [
            PageCompositionEntry(
                canonical_url=f"https://example.com/p{i}/",
                template=template,
                blocks=[],
                shortcodes=[],
                widget_placements=[],
                forms_embedded=[],
                plugin_components=[],
                enqueued_assets=[],
                content_sections=[],
            )
            for i in range(page_count)
        ]
        # Create matching route templates so route parity can score
        route_templates = [
            RouteTemplate(
                route_pattern=f"/p{i}/[slug]",
                layout="default",
                source_template=template,
                content_collection="pages",
            )
            for i in range(page_count)
        ]
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=pages
            ),
        )
        presentation = _clean_presentation(route_templates=route_templates)

        # Use threshold=0.0 so the gate never fires
        agent = _make_agent(threshold=0.0)
        context = _build_context(bundle, presentation=presentation)
        result = _run(agent.execute(context))
        report: ParityReport = result.artifacts["parity_report"]

        # Must have exactly the 7 categories
        assert set(report.category_scores.keys()) == PARITY_CATEGORIES

        # Each score must be between 0.0 and 1.0
        for cat, score in report.category_scores.items():
            assert 0.0 <= score <= 1.0, (
                f"Category '{cat}' score {score} out of range [0.0, 1.0]"
            )

    @given(
        page_count=st.integers(min_value=0, max_value=4),
    )
    @settings(max_examples=100)
    def test_overall_score_equals_mean_of_categories(self, page_count: int):
        """**Validates: Requirements 20.1, 20.3**

        The overall_score must equal the arithmetic mean of all 7 category
        scores within floating-point tolerance.
        """
        pages = [
            PageCompositionEntry(
                canonical_url=f"https://example.com/p{i}/",
                template="default",
                blocks=[],
                shortcodes=[],
                widget_placements=[],
                forms_embedded=[],
                plugin_components=[],
                enqueued_assets=[],
                content_sections=[],
            )
            for i in range(page_count)
        ]
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=pages
            ),
        )
        agent = _make_agent(threshold=0.0)
        context = _build_context(bundle)
        result = _run(agent.execute(context))
        report: ParityReport = result.artifacts["parity_report"]

        expected_mean = sum(report.category_scores.values()) / len(
            report.category_scores
        )
        assert abs(report.overall_score - expected_mean) < 1e-9, (
            f"overall_score {report.overall_score} != mean {expected_mean}"
        )

    @given(
        page_count=st.integers(min_value=0, max_value=3),
    )
    @settings(max_examples=100)
    def test_category_scores_are_floats(self, page_count: int):
        """**Validates: Requirements 20.3**

        Each category score must be a float value.
        """
        pages = [
            PageCompositionEntry(
                canonical_url=f"https://example.com/p{i}/",
                template="default",
                blocks=[],
                shortcodes=[],
                widget_placements=[],
                forms_embedded=[],
                plugin_components=[],
                enqueued_assets=[],
                content_sections=[],
            )
            for i in range(page_count)
        ]
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=pages
            ),
        )
        agent = _make_agent(threshold=0.0)
        context = _build_context(bundle)
        result = _run(agent.execute(context))
        report: ParityReport = result.artifacts["parity_report"]

        for cat, score in report.category_scores.items():
            assert isinstance(score, float), (
                f"Category '{cat}' score is {type(score).__name__}, expected float"
            )


# ===========================================================================
# Property 24: Parity gate enforcement
# Validates: Requirements 20.4
# ===========================================================================


class TestParityGateEnforcement:
    """When overall_score < threshold, ParityGateError must be raised.
    When overall_score >= threshold, no error is raised and ParityReport
    is returned. The ParityGateError must carry the ParityReport."""

    @given(
        page_count=st.integers(min_value=0, max_value=3),
    )
    @settings(max_examples=100)
    def test_high_threshold_triggers_gate_error(self, page_count: int):
        """**Validates: Requirements 20.4**

        A threshold of 1.1 (impossible to reach) must always trigger
        ParityGateError.
        """
        pages = [
            PageCompositionEntry(
                canonical_url=f"https://example.com/p{i}/",
                template="default",
                blocks=[],
                shortcodes=[],
                widget_placements=[],
                forms_embedded=[],
                plugin_components=[],
                enqueued_assets=[],
                content_sections=[],
            )
            for i in range(page_count)
        ]
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=pages
            ),
        )
        agent = _make_agent(threshold=1.1)
        context = _build_context(bundle)

        with pytest.raises(ParityGateError) as exc_info:
            _run(agent.execute(context))

        err = exc_info.value
        assert err.parity_report is not None
        assert isinstance(err.parity_report, ParityReport)
        assert set(err.parity_report.category_scores.keys()) == PARITY_CATEGORIES

    @given(
        page_count=st.integers(min_value=0, max_value=3),
    )
    @settings(max_examples=100)
    def test_zero_threshold_never_triggers_gate(self, page_count: int):
        """**Validates: Requirements 20.4**

        A threshold of 0.0 must never trigger ParityGateError since all
        scores are >= 0.0.
        """
        pages = [
            PageCompositionEntry(
                canonical_url=f"https://example.com/p{i}/",
                template="default",
                blocks=[],
                shortcodes=[],
                widget_placements=[],
                forms_embedded=[],
                plugin_components=[],
                enqueued_assets=[],
                content_sections=[],
            )
            for i in range(page_count)
        ]
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=pages
            ),
        )
        agent = _make_agent(threshold=0.0)
        context = _build_context(bundle)
        result = _run(agent.execute(context))

        report: ParityReport = result.artifacts["parity_report"]
        assert isinstance(report, ParityReport)
        assert report.overall_score >= 0.0

    @given(
        page_count=st.integers(min_value=0, max_value=3),
    )
    @settings(max_examples=100)
    def test_gate_error_carries_parity_report_with_scores(self, page_count: int):
        """**Validates: Requirements 20.4**

        The ParityGateError must carry a ParityReport with valid category
        scores and an overall_score matching the mean.
        """
        pages = [
            PageCompositionEntry(
                canonical_url=f"https://example.com/p{i}/",
                template="default",
                blocks=[],
                shortcodes=[],
                widget_placements=[],
                forms_embedded=[],
                plugin_components=[],
                enqueued_assets=[],
                content_sections=[],
            )
            for i in range(page_count)
        ]
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=pages
            ),
        )
        agent = _make_agent(threshold=1.1)
        context = _build_context(bundle)

        with pytest.raises(ParityGateError) as exc_info:
            _run(agent.execute(context))

        report = exc_info.value.parity_report
        expected_mean = sum(report.category_scores.values()) / len(
            report.category_scores
        )
        assert abs(report.overall_score - expected_mean) < 1e-9


# ===========================================================================
# Property 25: Snapshot comparison coverage
# Validates: Requirements 20.2
# ===========================================================================


class TestSnapshotComparisonCoverage:
    """For any BundleManifest with pages that have snapshot_ref, the report
    must contain SnapshotComparison entries for those pages. Each
    SnapshotComparison must have a valid page_url and visual_parity_score
    between 0.0 and 1.0."""

    @given(
        snapshot_pages=st.lists(
            page_composition_entries(with_snapshot=True),
            min_size=1,
            max_size=5,
        ),
        non_snapshot_pages=st.lists(
            page_composition_entries(with_snapshot=False),
            min_size=0,
            max_size=3,
        ),
    )
    @settings(max_examples=100)
    def test_snapshot_pages_produce_comparisons(
        self,
        snapshot_pages: list[PageCompositionEntry],
        non_snapshot_pages: list[PageCompositionEntry],
    ):
        """**Validates: Requirements 20.2**

        Every page with a snapshot_ref must produce a SnapshotComparison
        entry in the report.
        """
        # Deduplicate by canonical_url
        seen_urls: set[str] = set()
        unique_pages: list[PageCompositionEntry] = []
        for page in snapshot_pages + non_snapshot_pages:
            if page.canonical_url not in seen_urls:
                seen_urls.add(page.canonical_url)
                unique_pages.append(page)

        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=unique_pages
            ),
        )
        agent = _make_agent(threshold=0.0)
        context = _build_context(bundle)
        result = _run(agent.execute(context))
        report: ParityReport = result.artifacts["parity_report"]

        snapshot_urls = {
            p.canonical_url for p in unique_pages if p.snapshot_ref is not None
        }
        comparison_urls = {sc.page_url for sc in report.snapshot_comparisons}

        assert snapshot_urls == comparison_urls, (
            f"Missing comparisons for: {snapshot_urls - comparison_urls}"
        )

    @given(
        snapshot_pages=st.lists(
            page_composition_entries(with_snapshot=True),
            min_size=1,
            max_size=5,
        ),
    )
    @settings(max_examples=100)
    def test_snapshot_comparisons_have_valid_scores(
        self, snapshot_pages: list[PageCompositionEntry]
    ):
        """**Validates: Requirements 20.2**

        Each SnapshotComparison must have a visual_parity_score between
        0.0 and 1.0 and a non-empty page_url.
        """
        # Deduplicate
        seen: set[str] = set()
        unique: list[PageCompositionEntry] = []
        for p in snapshot_pages:
            if p.canonical_url not in seen:
                seen.add(p.canonical_url)
                unique.append(p)

        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=unique
            ),
        )
        agent = _make_agent(threshold=0.0)
        context = _build_context(bundle)
        result = _run(agent.execute(context))
        report: ParityReport = result.artifacts["parity_report"]

        for sc in report.snapshot_comparisons:
            assert sc.page_url, "SnapshotComparison page_url must be non-empty"
            assert 0.0 <= sc.visual_parity_score <= 1.0, (
                f"visual_parity_score {sc.visual_parity_score} out of range"
            )

    @given(
        non_snapshot_pages=st.lists(
            page_composition_entries(with_snapshot=False),
            min_size=1,
            max_size=5,
        ),
    )
    @settings(max_examples=100)
    def test_pages_without_snapshot_ref_produce_no_comparisons(
        self, non_snapshot_pages: list[PageCompositionEntry]
    ):
        """**Validates: Requirements 20.2**

        Pages without snapshot_ref must not produce SnapshotComparison
        entries.
        """
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0", pages=non_snapshot_pages
            ),
        )
        agent = _make_agent(threshold=0.0)
        context = _build_context(bundle)
        result = _run(agent.execute(context))
        report: ParityReport = result.artifacts["parity_report"]

        assert report.snapshot_comparisons == [], (
            "Pages without snapshot_ref should produce no comparisons"
        )


# ===========================================================================
# Property 26: Plugin parity assertions
# Validates: Requirements 20.6
# ===========================================================================


class TestPluginParityAssertions:
    """For any CapabilityManifest with plugin_capabilities that have matching
    adapters, plugin_assertions must contain entries for those plugin families.
    Each assertion entry must have assertion_id, description, category,
    check_type."""

    @given(
        families=st.lists(
            st.sampled_from(_ADAPTER_FAMILIES),
            min_size=1,
            max_size=5,
            unique=True,
        ),
    )
    @settings(max_examples=100)
    def test_adapter_families_produce_plugin_assertions(
        self, families: list[str]
    ):
        """**Validates: Requirements 20.6**

        For each plugin family with a registered adapter, the ParityReport
        must include QA assertions from that adapter.
        """
        # Build plugin_capabilities with at least one capability per family
        plugin_caps: dict[str, list[Capability]] = {}
        for family in families:
            plugin_caps[family] = [
                Capability(
                    capability_type="content_model",
                    source_plugin=family,
                    classification="strapi_native",
                    confidence=0.95,
                )
            ]

        cap_manifest = _clean_capability_manifest(plugin_capabilities=plugin_caps)
        bundle = _clean_bundle()
        agent = _make_agent(threshold=0.0)
        context = _build_context(bundle, cap_manifest=cap_manifest)
        result = _run(agent.execute(context))
        report: ParityReport = result.artifacts["parity_report"]

        # Every family with an adapter that produces assertions must appear
        registry = {a.plugin_family(): a for a in default_adapters()}
        for family in families:
            adapter = registry.get(family)
            if adapter is None:
                continue
            assertions = adapter.qa_assertions(plugin_caps[family])
            if assertions:
                assert family in report.plugin_assertions, (
                    f"Missing plugin_assertions for family '{family}'"
                )

    @given(
        family=st.sampled_from(_ADAPTER_FAMILIES),
    )
    @settings(max_examples=100)
    def test_plugin_assertion_entries_have_required_fields(
        self, family: str
    ):
        """**Validates: Requirements 20.6**

        Each assertion entry in plugin_assertions must have assertion_id,
        description, category, and check_type fields.
        """
        caps = [
            Capability(
                capability_type="content_model",
                source_plugin=family,
                classification="strapi_native",
                confidence=0.95,
            )
        ]
        cap_manifest = _clean_capability_manifest(
            plugin_capabilities={family: caps}
        )
        bundle = _clean_bundle()
        agent = _make_agent(threshold=0.0)
        context = _build_context(bundle, cap_manifest=cap_manifest)
        result = _run(agent.execute(context))
        report: ParityReport = result.artifacts["parity_report"]

        if family not in report.plugin_assertions:
            # Adapter may produce no assertions — that's valid
            return

        for entry in report.plugin_assertions[family]:
            assert "assertion_id" in entry, (
                f"Missing 'assertion_id' in assertion for {family}"
            )
            assert "description" in entry, (
                f"Missing 'description' in assertion for {family}"
            )
            assert "category" in entry, (
                f"Missing 'category' in assertion for {family}"
            )
            assert "check_type" in entry, (
                f"Missing 'check_type' in assertion for {family}"
            )
