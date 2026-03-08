from __future__ import annotations

import logging
from typing import Any

from src.adapters.base import PluginAdapter, QAAssertion
from src.adapters.registry import build_adapter_registry, default_adapters
from src.agents.base import AgentResult, BaseAgent
from src.models.behavior_manifest import BehaviorManifest
from src.models.bundle_manifest import BundleManifest
from src.models.capability_manifest import CapabilityManifest
from src.models.finding import Finding, FindingSeverity
from src.models.parity_report import (
    PARITY_CATEGORIES,
    ParityReport,
    SnapshotComparison,
)
from src.models.presentation_manifest import PresentationManifest
from src.orchestrator.errors import ParityGateError
from src.pipeline_context import (
    extract_behavior_manifest,
    extract_bundle_manifest,
    extract_capability_manifest,
    extract_presentation_manifest,
)

logger = logging.getLogger(__name__)

# Default parity threshold — deployment is blocked below this score.
_DEFAULT_PARITY_THRESHOLD = 0.8


class ParityQAAgent(BaseAgent):
    """Scores migration parity across 7 categories and gates deployment.

    Each category produces a float score between 0.0 and 1.0.  The overall
    score is the arithmetic mean of all category scores.  When the overall
    score falls below the configurable threshold (default 0.8) a
    ``ParityGateError`` is raised to block deployment.
    """

    def __init__(
        self,
        gradient_client: Any,
        kb_client: Any = None,
        adapters: list[PluginAdapter] | None = None,
        threshold: float = _DEFAULT_PARITY_THRESHOLD,
    ) -> None:
        super().__init__(gradient_client, kb_client)
        self._registry = build_adapter_registry(adapters or default_adapters())
        self._threshold = threshold

    async def execute(self, context: dict[str, Any]) -> AgentResult:
        bundle_manifest = extract_bundle_manifest(context)
        capability_manifest = extract_capability_manifest(context)
        presentation_manifest = extract_presentation_manifest(context)
        behavior_manifest = extract_behavior_manifest(context)

        # Allow per-run threshold override via context
        threshold = context.get("parity_threshold", self._threshold)

        logger.info("Starting parity QA for %s", bundle_manifest.site_url)

        # Score each of the 7 parity categories
        category_scores: dict[str, float] = {
            "route": self._score_route_parity(bundle_manifest, presentation_manifest),
            "redirect": self._score_redirect_parity(bundle_manifest, behavior_manifest),
            "metadata": self._score_metadata_parity(bundle_manifest),
            "media": self._score_media_parity(bundle_manifest),
            "menu": self._score_menu_parity(bundle_manifest, presentation_manifest),
            "template": self._score_template_parity(bundle_manifest, presentation_manifest),
            "plugin_behavior": self._score_plugin_behavior_parity(
                capability_manifest,
            ),
        }

        overall_score = sum(category_scores.values()) / len(category_scores)

        # Snapshot comparisons for pages with snapshot_ref
        snapshot_comparisons = self._compare_snapshots(bundle_manifest, context)

        # Plugin-specific QA assertions from adapters
        plugin_assertions = self._collect_plugin_assertions(capability_manifest)

        # Collect findings for any category below 1.0
        findings = self._build_findings(category_scores)

        report = ParityReport(
            category_scores=category_scores,
            overall_score=overall_score,
            findings=findings,
            snapshot_comparisons=snapshot_comparisons,
            plugin_assertions=plugin_assertions,
        )

        if overall_score < threshold:
            findings.append(
                Finding(
                    severity=FindingSeverity.CRITICAL,
                    stage="parity_qa",
                    construct="overall_parity",
                    message=(
                        f"Overall parity score {overall_score:.2f} "
                        f"below threshold {threshold}"
                    ),
                    recommended_action="Review parity failures before deployment",
                )
            )
            # Rebuild report with the gate finding included
            report = ParityReport(
                category_scores=category_scores,
                overall_score=overall_score,
                findings=findings,
                snapshot_comparisons=snapshot_comparisons,
                plugin_assertions=plugin_assertions,
            )
            logger.warning(
                "Parity gate failed for %s: overall=%.2f threshold=%.2f",
                bundle_manifest.site_url,
                overall_score,
                threshold,
            )
            raise ParityGateError(report)

        logger.info(
            "Parity QA passed for %s: overall=%.2f",
            bundle_manifest.site_url,
            overall_score,
        )

        return AgentResult(
            agent_name="parity_qa",
            artifacts={"parity_report": report},
        )

    # ------------------------------------------------------------------
    # Category scoring — each returns a float between 0.0 and 1.0
    # ------------------------------------------------------------------

    @staticmethod
    def _score_route_parity(
        bundle: BundleManifest,
        presentation: PresentationManifest,
    ) -> float:
        """Check that all page_composition pages have a corresponding route template."""
        pages = bundle.page_composition.pages
        if not pages:
            return 1.0

        route_sources = {rt.source_template for rt in presentation.route_templates}
        matched = sum(1 for p in pages if p.template in route_sources)
        return matched / len(pages)

    @staticmethod
    def _score_redirect_parity(
        bundle: BundleManifest,
        behavior: BehaviorManifest,
    ) -> float:
        """Check that all rewrite_rules redirects appear in behavior manifest redirects."""
        source_rules = bundle.rewrite_rules.get("rules", [])
        if not source_rules:
            return 1.0

        compiled_sources = {r.source_url for r in behavior.redirects}
        matched = sum(
            1
            for rule in source_rules
            if rule.get("source") in compiled_sources
            or rule.get("source_url") in compiled_sources
        )
        return matched / len(source_rules)

    @staticmethod
    def _score_metadata_parity(bundle: BundleManifest) -> float:
        """Check that SEO metadata strategy covers all pages with SEO data."""
        seo_pages = bundle.seo_full.pages
        composition_pages = bundle.page_composition.pages
        if not composition_pages:
            return 1.0

        seo_urls = {p.canonical_url for p in seo_pages}
        pages_needing_seo = [
            p for p in composition_pages if p.canonical_url in seo_urls
        ]
        if not pages_needing_seo:
            # No pages have SEO data — nothing to check
            return 1.0

        covered = sum(1 for p in pages_needing_seo if p.canonical_url in seo_urls)
        return covered / len(pages_needing_seo)

    @staticmethod
    def _score_media_parity(bundle: BundleManifest) -> float:
        """Check that media_map entries are accounted for in the migration."""
        media_entries = bundle.media_map
        if not media_entries:
            return 1.0

        # Score based on media entries having required fields for migration
        valid = sum(
            1
            for entry in media_entries
            if entry.get("source_url") or entry.get("url")
        )
        return valid / len(media_entries)

    @staticmethod
    def _score_menu_parity(
        bundle: BundleManifest,
        presentation: PresentationManifest,
    ) -> float:
        """Check that menus from the bundle are represented in the presentation."""
        menus = bundle.menus
        if not menus:
            return 1.0

        # Check that sections or layouts reference menu-like components
        section_names = {s.name.lower() for s in presentation.sections}
        layout_sections = set()
        for layout in presentation.layouts:
            for sec in layout.shared_sections:
                layout_sections.add(sec.lower())

        all_presentation_names = section_names | layout_sections
        matched = sum(
            1
            for menu in menus
            if any(
                menu_name in name
                for name in all_presentation_names
                for menu_name in [
                    menu.get("name", "").lower(),
                    menu.get("slug", "").lower(),
                    "menu",
                    "nav",
                ]
                if menu_name
            )
        )
        return min(matched / len(menus), 1.0)

    @staticmethod
    def _score_template_parity(
        bundle: BundleManifest,
        presentation: PresentationManifest,
    ) -> float:
        """Check that all page templates have corresponding layouts."""
        templates = bundle.page_templates.get("templates", [])
        if not templates:
            return 1.0

        layout_names = {layout.name for layout in presentation.layouts}
        route_sources = {rt.source_template for rt in presentation.route_templates}
        known_templates = layout_names | route_sources

        matched = sum(
            1
            for t in templates
            if (t if isinstance(t, str) else t.get("name", "")) in known_templates
        )
        return matched / len(templates)

    def _score_plugin_behavior_parity(
        self,
        capability_manifest: CapabilityManifest,
    ) -> float:
        """Check that plugin capabilities have adapter coverage."""
        plugin_caps = capability_manifest.plugin_capabilities
        if not plugin_caps:
            return 1.0

        covered = sum(
            1 for family in plugin_caps if family in self._registry
        )
        return covered / len(plugin_caps)

    # ------------------------------------------------------------------
    # Snapshot comparison
    # ------------------------------------------------------------------

    @staticmethod
    def _compare_snapshots(
        bundle: BundleManifest,
        context: dict[str, Any],
    ) -> list[SnapshotComparison]:
        """Compare generated pages against snapshots for pages with snapshot_ref.

        Since we cannot do visual comparison at build time, scoring is based on
        whether the snapshot_ref exists and the html_snapshots context contains
        content for that reference.
        """
        html_snapshots: dict[str, str] = context.get("html_snapshots", {})
        comparisons: list[SnapshotComparison] = []

        for page in bundle.page_composition.pages:
            if not page.snapshot_ref:
                continue

            has_content = bool(html_snapshots.get(page.snapshot_ref))
            score = 1.0 if has_content else 0.5
            differences: list[str] = []
            if not has_content:
                differences.append(
                    f"Snapshot content not found for ref '{page.snapshot_ref}'"
                )

            comparisons.append(
                SnapshotComparison(
                    page_url=page.canonical_url,
                    visual_parity_score=score,
                    content_match=has_content,
                    differences=differences,
                )
            )

        # Sort for determinism
        comparisons.sort(key=lambda c: c.page_url)
        return comparisons

    # ------------------------------------------------------------------
    # Plugin QA assertions
    # ------------------------------------------------------------------

    def _collect_plugin_assertions(
        self,
        capability_manifest: CapabilityManifest,
    ) -> dict[str, list[dict[str, Any]]]:
        """Collect QA assertions from each adapter's qa_assertions() method."""
        result: dict[str, list[dict[str, Any]]] = {}

        for family, caps in sorted(capability_manifest.plugin_capabilities.items()):
            adapter = self._registry.get(family)
            if adapter is None:
                continue

            assertions: list[QAAssertion] = adapter.qa_assertions(caps)
            if assertions:
                result[family] = [a.model_dump() for a in assertions]

        return result

    # ------------------------------------------------------------------
    # Finding generation
    # ------------------------------------------------------------------

    @staticmethod
    def _build_findings(category_scores: dict[str, float]) -> list[Finding]:
        """Produce a Finding for every category that scored below 1.0."""
        findings: list[Finding] = []

        for category in sorted(category_scores):
            score = category_scores[category]
            if score >= 1.0:
                continue

            severity = (
                FindingSeverity.CRITICAL if score < 0.5 else FindingSeverity.WARNING
            )
            findings.append(
                Finding(
                    severity=severity,
                    stage="parity_qa",
                    construct=f"{category}_parity",
                    message=f"{category} parity score {score:.2f} — below perfect",
                    recommended_action=f"Review {category} parity failures",
                )
            )

        return findings
