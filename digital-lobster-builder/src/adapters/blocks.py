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

class GutenbergCoreAdapter(PluginAdapter):
    """Adapter for Gutenberg core blocks."""
    def plugin_family(self) -> str:
        return "gutenberg_core"

    def required_artifacts(self) -> list[str]:
        return ["blocks_usage.json", "block_patterns.json", "page_composition.json"]

    def supported_constructs(self) -> list[str]:
        return [
            "core/paragraph",
            "core/heading",
            "core/image",
            "core/gallery",
            "core/list",
            "core/quote",
            "core/code",
            "core/table",
            "core/columns",
            "core/group",
            "core/cover",
            "core/media-text",
            "core/buttons",
            "core/separator",
            "core/spacer",
            "core/embed",
            "core/html",
            "core/shortcode",
        ]

    def classify_capabilities(self, bundle_manifest: BundleManifest) -> list[Capability]:
        capabilities: list[Capability] = []
        blocks = bundle_manifest.blocks_usage
        block_list = blocks.get("blocks", []) if isinstance(blocks, dict) else []
        seen_types: set[str] = set()
        for block in block_list:
            block_type = block.get("blockName", "")
            if block_type.startswith("core/") and block_type not in seen_types:
                seen_types.add(block_type)
                capabilities.append(
                    Capability(
                        capability_type="template",
                        source_plugin="gutenberg_core",
                        classification="astro_runtime",
                        confidence=0.95,
                        details={"block_type": block_type},
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
                source_construct="core_block",
                target_type="component",
                target_identifier="blocks.core-block",
                transform="block_to_astro",
            ),
        ]

    def unsupported_cases(self) -> list[str]:
        return [
            "Gutenberg reusable blocks with dynamic server-side rendering",
            "Gutenberg block bindings API (WordPress 6.5+)",
        ]

    def qa_assertions(self, capabilities: list[Capability]) -> list[QAAssertion]:
        return [
            QAAssertion(
                assertion_id="gutenberg_block_rendering",
                description="All core Gutenberg blocks render correctly in Astro",
                category="template_parity",
                check_type="content_match",
            ),
        ]

class KadenceBlocksAdapter(PluginAdapter):
    """Adapter for Kadence Blocks."""
    def plugin_family(self) -> str:
        return "kadence_blocks"

    def required_artifacts(self) -> list[str]:
        return ["blocks_usage.json", "block_patterns.json", "page_composition.json"]

    def supported_constructs(self) -> list[str]:
        return [
            "kadence/rowlayout",
            "kadence/column",
            "kadence/advancedheading",
            "kadence/advancedbtn",
            "kadence/tabs",
            "kadence/accordion",
            "kadence/iconlist",
            "kadence/spacer",
            "kadence/icon",
            "kadence/infobox",
            "kadence/image",
        ]

    def classify_capabilities(self, bundle_manifest: BundleManifest) -> list[Capability]:
        capabilities: list[Capability] = []
        blocks = bundle_manifest.blocks_usage
        block_list = blocks.get("blocks", []) if isinstance(blocks, dict) else []
        seen_types: set[str] = set()
        for block in block_list:
            block_type = block.get("blockName", "")
            if block_type.startswith("kadence/") and block_type not in seen_types:
                seen_types.add(block_type)
                capabilities.append(
                    Capability(
                        capability_type="template",
                        source_plugin="kadence_blocks",
                        classification="astro_runtime",
                        confidence=0.9,
                        details={"block_type": block_type},
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
                source_construct="kadence_block",
                target_type="component",
                target_identifier="blocks.kadence-block",
                transform="block_to_astro",
            ),
        ]

    def unsupported_cases(self) -> list[str]:
        return [
            "Kadence Blocks Pro dynamic content features",
            "Kadence Blocks Pro header/footer builder",
            "Kadence Blocks custom CSS per block (partially supported via style tokens)",
        ]

    def qa_assertions(self, capabilities: list[Capability]) -> list[QAAssertion]:
        return [
            QAAssertion(
                assertion_id="kadence_block_rendering",
                description="All Kadence blocks render correctly in Astro",
                category="template_parity",
                check_type="content_match",
            ),
        ]
