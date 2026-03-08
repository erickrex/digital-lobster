from __future__ import annotations

import logging
from typing import Any

from src.adapters.registry import default_adapters
from src.agents.base import AgentResult, BaseAgent
from src.models.finding import Finding, FindingSeverity
from src.models.readiness_report import ReadinessReport
from src.orchestrator.errors import QualificationError
from src.pipeline_context import extract_bundle_manifest

logger = logging.getLogger(__name__)

# Page-builder plugin slugs that disqualify a site as Gutenberg-first.
_PAGE_BUILDER_SLUGS = frozenset({
    "elementor",
    "divi",
    "divi-builder",
    "beaver-builder",
    "beaver-builder-lite-version",
    "wpbakery",
    "js_composer",
    "fusion-builder",
    "avada",
    "oxygen",
    "brizy",
    "thrive-architect",
    "visual-composer",
})

# WooCommerce slugs.
_WOOCOMMERCE_SLUGS = frozenset({
    "woocommerce",
    "woo-commerce",
})

# Multilingual plugin slugs.
_MULTILINGUAL_SLUGS = frozenset({
    "wpml",
    "sitepress-multilingual-cms",
    "polylang",
    "translatepress",
    "translatepress-multilingual",
    "weglot",
    "weglot-translate",
})

# Membership / community plugin slugs.
_MEMBERSHIP_SLUGS = frozenset({
    "memberpress",
    "mepr-corporate-accounts",
    "restrict-content-pro",
    "restrict-content",
    "buddypress",
    "bbpress",
    "ultimate-member",
    "paid-memberships-pro",
    "woocommerce-memberships",
    "s2member",
    "wishlist-member",
    "peepso",
})

class QualificationAgent(BaseAgent):
    """Evaluates site scope before migration.

    Consumes the BundleManifest from pipeline context and runs all
    qualification checks. On any critical finding, raises
    QualificationError with a ReadinessReport (qualified=False).
    On pass, returns AgentResult with ReadinessReport (qualified=True).
    """
    def __init__(
        self,
        gradient_client: Any,
        kb_client: Any = None,
        supported_families: set[str] | None = None,
    ) -> None:
        super().__init__(gradient_client, kb_client)
        # Build the set of supported plugin families from the adapter registry.
        if supported_families is not None:
            self._supported_families = supported_families
        else:
            self._supported_families = {
                a.plugin_family() for a in default_adapters()
            }

    async def execute(self, context: dict[str, Any]) -> AgentResult:
        bundle_manifest = extract_bundle_manifest(context)
        findings: list[Finding] = []

        checked_criteria = [
            "gutenberg_first",
            "no_woocommerce",
            "no_multilingual",
            "no_membership",
            "no_enterprise_editorial",
            "supported_plugins",
        ]

        logger.info("Starting qualification checks for %s", bundle_manifest.site_url)

        self._check_gutenberg_first(bundle_manifest, findings)
        self._check_no_woocommerce(bundle_manifest, findings)
        self._check_no_multilingual(bundle_manifest, findings)
        self._check_no_membership(bundle_manifest, findings)
        self._check_no_enterprise_editorial(bundle_manifest, findings)
        self._check_supported_plugins(bundle_manifest, findings)

        critical = [f for f in findings if f.severity == FindingSeverity.CRITICAL]

        if critical:
            report = ReadinessReport(
                qualified=False,
                findings=findings,
                checked_criteria=checked_criteria,
            )
            logger.warning(
                "Site %s failed qualification with %d critical finding(s)",
                bundle_manifest.site_url,
                len(critical),
            )
            raise QualificationError(findings=findings, readiness_report=report)

        report = ReadinessReport(
            qualified=True,
            findings=findings,
            checked_criteria=checked_criteria,
        )
        logger.info("Site %s passed qualification", bundle_manifest.site_url)

        return AgentResult(
            agent_name="qualification",
            artifacts={"readiness_report": report},
        )

    # ------------------------------------------------------------------
    # Qualification checks
    # ------------------------------------------------------------------

    def _get_active_plugin_slugs(self, bundle_manifest: Any) -> set[str]:
        """Extract active plugin slugs from plugins_fingerprint."""
        plugins = bundle_manifest.plugins_fingerprint.get("plugins", [])
        slugs: set[str] = set()
        for plugin in plugins:
            if not isinstance(plugin, dict):
                continue
            status = plugin.get("status", "active")
            if status != "active":
                continue
            slug = plugin.get("slug", "")
            if slug:
                slugs.add(slug.lower())
        return slugs

    def _check_gutenberg_first(
        self, bundle_manifest: Any, findings: list[Finding]
    ) -> None:
        """Check that the site is Gutenberg-first, not page-builder-first."""
        active_slugs = self._get_active_plugin_slugs(bundle_manifest)
        detected = active_slugs & _PAGE_BUILDER_SLUGS
        if detected:
            findings.append(Finding(
                severity=FindingSeverity.CRITICAL,
                stage="qualification",
                construct="page_builder",
                message=f"Site uses page builder plugin(s): {', '.join(sorted(detected))}",
                recommended_action="Migrate using a page-builder-aware pipeline or remove the page builder first",
            ))
        else:
            # Advisory: check blocks_usage for any page-builder block namespaces
            blocks = bundle_manifest.blocks_usage
            block_types = blocks.get("block_types", []) if isinstance(blocks, dict) else []
            pb_namespaces = {"elementor", "divi", "fl-builder", "vc_", "oxygen"}
            pb_blocks = [
                b for b in block_types
                if isinstance(b, dict) and any(
                    ns in (b.get("name", "") or "").lower() for ns in pb_namespaces
                )
            ]
            if pb_blocks:
                findings.append(Finding(
                    severity=FindingSeverity.WARNING,
                    stage="qualification",
                    construct="page_builder_blocks",
                    message=f"Found {len(pb_blocks)} page-builder block type(s) in blocks_usage",
                    recommended_action="Review whether these blocks are actively used or leftover",
                ))

    def _check_no_woocommerce(
        self, bundle_manifest: Any, findings: list[Finding]
    ) -> None:
        """Check that the site does not use WooCommerce."""
        active_slugs = self._get_active_plugin_slugs(bundle_manifest)
        detected = active_slugs & _WOOCOMMERCE_SLUGS
        if detected:
            findings.append(Finding(
                severity=FindingSeverity.CRITICAL,
                stage="qualification",
                construct="woocommerce",
                message="Site uses WooCommerce",
                recommended_action="Use a WooCommerce-aware migration pipeline",
            ))

    def _check_no_multilingual(
        self, bundle_manifest: Any, findings: list[Finding]
    ) -> None:
        """Check that the site does not require multilingual support."""
        active_slugs = self._get_active_plugin_slugs(bundle_manifest)
        detected = active_slugs & _MULTILINGUAL_SLUGS
        if detected:
            findings.append(Finding(
                severity=FindingSeverity.CRITICAL,
                stage="qualification",
                construct="multilingual",
                message=f"Site uses multilingual plugin(s): {', '.join(sorted(detected))}",
                recommended_action="Use a multilingual-aware migration pipeline or remove multilingual plugins first",
            ))

    def _check_no_membership(
        self, bundle_manifest: Any, findings: list[Finding]
    ) -> None:
        """Check that the site does not exhibit membership/community behavior."""
        active_slugs = self._get_active_plugin_slugs(bundle_manifest)
        detected = active_slugs & _MEMBERSHIP_SLUGS
        if detected:
            findings.append(Finding(
                severity=FindingSeverity.CRITICAL,
                stage="qualification",
                construct="membership",
                message=f"Site uses membership/community plugin(s): {', '.join(sorted(detected))}",
                recommended_action="Remove membership plugins or use a membership-aware migration pipeline",
            ))

    def _check_no_enterprise_editorial(
        self, bundle_manifest: Any, findings: list[Finding]
    ) -> None:
        """Check that the site does not require enterprise editorial workflows."""
        workflows = bundle_manifest.editorial_workflows
        statuses = workflows.statuses_in_use
        # Standard WordPress statuses that don't indicate enterprise workflows
        standard_statuses = {"publish", "draft", "pending", "private", "trash", "future", "auto-draft", "inherit"}
        custom_statuses = set(s.lower() for s in statuses) - standard_statuses
        if custom_statuses:
            findings.append(Finding(
                severity=FindingSeverity.CRITICAL,
                stage="qualification",
                construct="editorial_workflows",
                message=f"Site uses custom editorial statuses: {', '.join(sorted(custom_statuses))}",
                recommended_action="Simplify editorial workflow to standard WordPress statuses before migration",
            ))

    def _check_supported_plugins(
        self, bundle_manifest: Any, findings: list[Finding]
    ) -> None:
        """Check that all active plugins are supported or irrelevant."""
        plugins = bundle_manifest.plugins_fingerprint.get("plugins", [])
        for plugin in plugins:
            if not isinstance(plugin, dict):
                continue
            status = plugin.get("status", "active")
            if status != "active":
                continue
            slug = plugin.get("slug", "")
            family = plugin.get("family", "")
            if not slug:
                continue
            # Skip if the plugin belongs to a supported family
            if family and family in self._supported_families:
                continue
            # Skip known-irrelevant plugins (utility/infrastructure plugins)
            if self._is_irrelevant_plugin(slug):
                continue
            # Unsupported active plugin
            findings.append(Finding(
                severity=FindingSeverity.WARNING,
                stage="qualification",
                construct=f"plugin:{slug}",
                message=f"Active plugin '{slug}' is not in a supported plugin family",
                recommended_action=f"Review plugin '{slug}' manually to determine migration impact",
            ))

    @staticmethod
    def _is_irrelevant_plugin(slug: str) -> bool:
        """Return True for plugins that are infrastructure/utility and irrelevant to migration."""
        irrelevant_prefixes = (
            "akismet",
            "wordfence",
            "sucuri",
            "ithemes-security",
            "better-wp-security",
            "updraftplus",
            "backwpup",
            "duplicator",
            "wp-super-cache",
            "w3-total-cache",
            "wp-fastest-cache",
            "litespeed-cache",
            "autoptimize",
            "jetpack",
            "google-analytics",
            "google-site-kit",
            "site-kit-by-google",
            "wp-mail-smtp",
            "classic-editor",
            "disable-gutenberg",
            "health-check",
            "query-monitor",
            "debug-bar",
        )
        slug_lower = slug.lower()
        return any(slug_lower.startswith(prefix) for prefix in irrelevant_prefixes)
