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


class YoastAdapter(PluginAdapter):
    """Adapter for Yoast SEO."""

    def plugin_family(self) -> str:
        return "yoast"

    def required_artifacts(self) -> list[str]:
        return ["seo_full.json", "plugin_instances.json"]

    def supported_constructs(self) -> list[str]:
        return [
            "seo_title",
            "seo_description",
            "og_metadata",
            "twitter_metadata",
            "schema_markup",
            "breadcrumbs",
            "sitemap",
            "redirects",
            "robots",
        ]

    def classify_capabilities(self, bundle_manifest: BundleManifest) -> list[Capability]:
        capabilities: list[Capability] = []
        for page in bundle_manifest.seo_full.pages:
            if page.source_plugin == "yoast":
                capabilities.append(
                    Capability(
                        capability_type="seo",
                        source_plugin="yoast",
                        classification="strapi_native",
                        confidence=0.95,
                        details={"canonical_url": page.canonical_url},
                    )
                )
                break  # one capability entry for the whole plugin
        return capabilities

    def schema_strategy(self, capabilities: list[Capability]) -> SchemaContribution:
        return SchemaContribution()

    def rendering_strategy(self, capabilities: list[Capability]) -> RenderingContribution:
        return RenderingContribution()

    def migration_rules(self, capabilities: list[Capability]) -> list[MigrationRule]:
        return [
            MigrationRule(
                source_construct="yoast_seo_meta",
                target_type="component",
                target_identifier="seo.metadata",
                transform="direct",
            ),
        ]

    def unsupported_cases(self) -> list[str]:
        return [
            "Yoast SEO premium redirect manager (partial — redirects migrated, manager UI not replicated)",
            "Yoast SEO internal linking suggestions",
            "Yoast SEO readability analysis",
        ]

    def qa_assertions(self, capabilities: list[Capability]) -> list[QAAssertion]:
        return [
            QAAssertion(
                assertion_id="yoast_meta_parity",
                description="SEO title and meta description match source for all pages",
                category="metadata_parity",
                check_type="content_match",
            ),
            QAAssertion(
                assertion_id="yoast_og_parity",
                description="Open Graph metadata preserved for all pages",
                category="metadata_parity",
                check_type="content_match",
            ),
        ]


class RankMathAdapter(PluginAdapter):
    """Adapter for Rank Math SEO."""

    def plugin_family(self) -> str:
        return "rank_math"

    def required_artifacts(self) -> list[str]:
        return ["seo_full.json", "plugin_instances.json"]

    def supported_constructs(self) -> list[str]:
        return [
            "seo_title",
            "seo_description",
            "og_metadata",
            "twitter_metadata",
            "schema_markup",
            "breadcrumbs",
            "sitemap",
            "redirects",
            "robots",
        ]

    def classify_capabilities(self, bundle_manifest: BundleManifest) -> list[Capability]:
        capabilities: list[Capability] = []
        for page in bundle_manifest.seo_full.pages:
            if page.source_plugin == "rank_math":
                capabilities.append(
                    Capability(
                        capability_type="seo",
                        source_plugin="rank_math",
                        classification="strapi_native",
                        confidence=0.95,
                        details={"canonical_url": page.canonical_url},
                    )
                )
                break
        return capabilities

    def schema_strategy(self, capabilities: list[Capability]) -> SchemaContribution:
        return SchemaContribution()

    def rendering_strategy(self, capabilities: list[Capability]) -> RenderingContribution:
        return RenderingContribution()

    def migration_rules(self, capabilities: list[Capability]) -> list[MigrationRule]:
        return [
            MigrationRule(
                source_construct="rank_math_seo_meta",
                target_type="component",
                target_identifier="seo.metadata",
                transform="direct",
            ),
        ]

    def unsupported_cases(self) -> list[str]:
        return [
            "Rank Math SEO analytics dashboard",
            "Rank Math content AI suggestions",
            "Rank Math 404 monitor",
        ]

    def qa_assertions(self, capabilities: list[Capability]) -> list[QAAssertion]:
        return [
            QAAssertion(
                assertion_id="rank_math_meta_parity",
                description="SEO title and meta description match source for all pages",
                category="metadata_parity",
                check_type="content_match",
            ),
        ]


class AioSeoAdapter(PluginAdapter):
    """Adapter for All in One SEO."""

    def plugin_family(self) -> str:
        return "aio_seo"

    def required_artifacts(self) -> list[str]:
        return ["seo_full.json", "plugin_instances.json"]

    def supported_constructs(self) -> list[str]:
        return [
            "seo_title",
            "seo_description",
            "og_metadata",
            "twitter_metadata",
            "schema_markup",
            "sitemap",
            "robots",
        ]

    def classify_capabilities(self, bundle_manifest: BundleManifest) -> list[Capability]:
        capabilities: list[Capability] = []
        for page in bundle_manifest.seo_full.pages:
            if page.source_plugin == "aio_seo":
                capabilities.append(
                    Capability(
                        capability_type="seo",
                        source_plugin="aio_seo",
                        classification="strapi_native",
                        confidence=0.9,
                        details={"canonical_url": page.canonical_url},
                    )
                )
                break
        return capabilities

    def schema_strategy(self, capabilities: list[Capability]) -> SchemaContribution:
        return SchemaContribution()

    def rendering_strategy(self, capabilities: list[Capability]) -> RenderingContribution:
        return RenderingContribution()

    def migration_rules(self, capabilities: list[Capability]) -> list[MigrationRule]:
        return [
            MigrationRule(
                source_construct="aio_seo_meta",
                target_type="component",
                target_identifier="seo.metadata",
                transform="direct",
            ),
        ]

    def unsupported_cases(self) -> list[str]:
        return [
            "AIOSEO link assistant",
            "AIOSEO local SEO module",
            "AIOSEO image SEO auto-alt-text",
        ]

    def qa_assertions(self, capabilities: list[Capability]) -> list[QAAssertion]:
        return [
            QAAssertion(
                assertion_id="aio_seo_meta_parity",
                description="SEO title and meta description match source for all pages",
                category="metadata_parity",
                check_type="content_match",
            ),
        ]
