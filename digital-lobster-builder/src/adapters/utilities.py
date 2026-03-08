from __future__ import annotations

from src.adapters.base import (
    MigrationRule,
    PluginAdapter,
    QAAssertion,
    RenderingContribution,
    SchemaContribution,
)
from src.models.bundle_manifest import BundleManifest
from src.models.capability_manifest import Capability

class RedirectAdapter(PluginAdapter):
    """Adapter for common redirect plugins (Redirection, Safe Redirect Manager, etc.)."""
    def plugin_family(self) -> str:
        return "redirects"

    def required_artifacts(self) -> list[str]:
        return ["rewrite_rules.json", "seo_full.json"]

    def supported_constructs(self) -> list[str]:
        return ["redirect_301", "redirect_302", "regex_redirect"]

    def classify_capabilities(self, bundle_manifest: BundleManifest) -> list[Capability]:
        capabilities: list[Capability] = []
        rules = bundle_manifest.rewrite_rules
        redirect_list = rules.get("redirects", []) if isinstance(rules, dict) else []
        if redirect_list:
            capabilities.append(
                Capability(
                    capability_type="content_model",
                    source_plugin="redirects",
                    classification="astro_runtime",
                    confidence=0.95,
                    details={"redirect_count": len(redirect_list)},
                )
            )
        return capabilities

    def schema_strategy(self, capabilities: list[Capability]) -> SchemaContribution:
        return SchemaContribution()

    def rendering_strategy(self, capabilities: list[Capability]) -> RenderingContribution:
        return RenderingContribution()

    def migration_rules(self, capabilities: list[Capability]) -> list[MigrationRule]:
        return [
            MigrationRule(
                source_construct="redirect_rule",
                target_type="collection",
                target_identifier="redirects.rule",
                transform="direct",
            ),
        ]

    def unsupported_cases(self) -> list[str]:
        return [
            "Regex-based redirects with capture groups (require manual review)",
            "Server-level redirects defined in .htaccess outside plugin scope",
        ]

    def qa_assertions(self, capabilities: list[Capability]) -> list[QAAssertion]:
        return [
            QAAssertion(
                assertion_id="redirect_parity",
                description="All redirect rules produce correct HTTP status codes",
                category="redirect_parity",
                check_type="route_match",
            ),
        ]

class WidgetSidebarAdapter(PluginAdapter):
    """Adapter for common widget and sidebar patterns."""
    def plugin_family(self) -> str:
        return "widget_sidebar"

    def required_artifacts(self) -> list[str]:
        return ["widgets.json", "page_composition.json"]

    def supported_constructs(self) -> list[str]:
        return [
            "widget_text",
            "widget_custom_html",
            "widget_navigation_menu",
            "widget_search",
            "widget_recent_posts",
            "widget_categories",
            "widget_archives",
            "widget_media_image",
            "sidebar",
        ]

    def classify_capabilities(self, bundle_manifest: BundleManifest) -> list[Capability]:
        capabilities: list[Capability] = []
        widgets = bundle_manifest.widgets
        widget_list = widgets.get("widgets", []) if isinstance(widgets, dict) else []
        if widget_list:
            capabilities.append(
                Capability(
                    capability_type="widget",
                    source_plugin="widget_sidebar",
                    classification="astro_runtime",
                    confidence=0.85,
                    details={"widget_count": len(widget_list)},
                )
            )
        return capabilities

    def schema_strategy(self, capabilities: list[Capability]) -> SchemaContribution:
        return SchemaContribution()

    def rendering_strategy(self, capabilities: list[Capability]) -> RenderingContribution:
        return RenderingContribution()

    def migration_rules(self, capabilities: list[Capability]) -> list[MigrationRule]:
        return [
            MigrationRule(
                source_construct="widget",
                target_type="component",
                target_identifier="widgets.section",
                transform="widget_to_section",
            ),
            MigrationRule(
                source_construct="sidebar",
                target_type="component",
                target_identifier="layout.sidebar",
                transform="sidebar_to_section",
            ),
        ]

    def unsupported_cases(self) -> list[str]:
        return [
            "Widgets with embedded PHP execution",
            "Third-party widget plugins not in the supported plugin family list",
        ]

    def qa_assertions(self, capabilities: list[Capability]) -> list[QAAssertion]:
        return [
            QAAssertion(
                assertion_id="widget_sidebar_presence",
                description="All widget areas are represented as Astro sections",
                category="template_parity",
                check_type="presence",
            ),
        ]
