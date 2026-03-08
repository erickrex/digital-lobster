from __future__ import annotations

import logging
from typing import Any

from src.adapters.base import PluginAdapter
from src.adapters.registry import build_adapter_registry, default_adapters
from src.agents.base import AgentResult, BaseAgent
from src.models.behavior_manifest import (
    BehaviorManifest,
    FormStrategy,
    IntegrationBoundary,
    RedirectRule,
    SearchStrategy,
)
from src.models.bundle_manifest import BundleManifest
from src.models.capability_manifest import CapabilityManifest
from src.models.content_model_manifest import ContentModelManifest
from src.models.finding import Finding, FindingSeverity
from src.models.migration_mapping_manifest import (
    FieldMapping,
    MediaMappingStrategy,
    MigrationMappingManifest,
    PluginInstanceMapping,
    RelationMapping,
    TemplateMapping,
    TermMapping,
    TypeMapping,
)
from src.models.presentation_manifest import PresentationManifest
from src.pipeline_context import (
    extract_bundle_manifest,
    extract_capability_manifest,
    extract_content_model_manifest,
    extract_presentation_manifest,
)

logger = logging.getLogger(__name__)

# Supported form providers that get an astro_api_route target
_SUPPORTED_FORM_PROVIDERS = frozenset({"cf7", "wpforms", "gravity_forms", "ninja_forms"})

# Integration types that map to proxy disposition
_PROXY_INTEGRATION_TYPES = frozenset({
    "runtime_api",
    "webhook",
    "crm",
    "embed",
    "third_party_script",
})

# Integration types compatible with rebuild
_REBUILD_INTEGRATION_TYPES = frozenset({"form_destination"})

# Behavior classification buckets
_BEHAVIOR_CLASSIFICATIONS = frozenset({"strapi", "astro", "api_glue", "unsupported"})


class BehaviorCompilerAgent(BaseAgent):
    """Produces BehaviorManifest and MigrationMappingManifest from pipeline data.

    Deterministically compiles:
    - Redirects from rewrite_rules and SEO redirect ownership
    - Metadata generation strategy from SEO data
    - Forms migration strategy per supported form provider
    - Preview rules from editorial workflows
    - Search/filtering strategy when search_config is non-empty
    - Integration boundaries (rebuild / proxy / drop)
    - Unsupported construct findings
    - Complete MigrationMappingManifest for content migration
    """

    def __init__(
        self,
        gradient_client: Any,
        kb_client: Any = None,
        adapters: list[PluginAdapter] | None = None,
    ) -> None:
        super().__init__(gradient_client, kb_client)
        self._adapters = build_adapter_registry(adapters or default_adapters())

    async def execute(self, context: dict[str, Any]) -> AgentResult:
        capability_manifest = extract_capability_manifest(context)
        bundle_manifest = extract_bundle_manifest(context)
        content_model = extract_content_model_manifest(context)
        presentation = extract_presentation_manifest(context)

        logger.info("Starting behavior compilation for %s", bundle_manifest.site_url)

        redirects = self._compile_redirects(bundle_manifest)
        metadata_strategy = self._compile_metadata_strategy(bundle_manifest)
        forms_strategy = self._compile_forms_strategy(bundle_manifest)
        preview_rules = self._compile_preview_rules(bundle_manifest)
        search_strategy = self._compile_search_strategy(bundle_manifest, content_model)
        integration_boundaries = self._compile_integration_boundaries(bundle_manifest)
        unsupported_constructs = self._collect_unsupported(capability_manifest)

        # Sort all lists for determinism
        redirects.sort(key=lambda r: (r.source_url, r.target_url))
        forms_strategy.sort(key=lambda f: f.form_id)
        integration_boundaries.sort(key=lambda b: b.integration_id)
        unsupported_constructs.sort(key=lambda f: (f.stage, f.construct))

        behavior = BehaviorManifest(
            redirects=redirects,
            metadata_strategy=metadata_strategy,
            forms_strategy=forms_strategy,
            preview_rules=preview_rules,
            search_strategy=search_strategy,
            integration_boundaries=integration_boundaries,
            unsupported_constructs=unsupported_constructs,
        )

        mapping = self._build_migration_mapping(
            bundle_manifest, content_model, presentation,
        )

        logger.info(
            "Behavior compilation complete for %s: %d redirects, %d forms, %d integrations",
            bundle_manifest.site_url,
            len(redirects),
            len(forms_strategy),
            len(integration_boundaries),
        )

        return AgentResult(
            agent_name="behavior_compiler",
            artifacts={
                "behavior_manifest": behavior,
                "migration_mapping_manifest": mapping,
            },
        )

    # ------------------------------------------------------------------
    # Redirect compilation
    # ------------------------------------------------------------------

    def _compile_redirects(
        self,
        bundle_manifest: BundleManifest,
    ) -> list[RedirectRule]:
        """Build redirect rules from rewrite_rules and SEO redirect ownership."""
        redirects: list[RedirectRule] = []
        seen: set[tuple[str, str]] = set()

        # 1. From rewrite_rules artifact
        rules = bundle_manifest.rewrite_rules
        redirect_list = rules.get("redirects", []) if isinstance(rules, dict) else []
        for rule in redirect_list:
            if not isinstance(rule, dict):
                continue
            source = rule.get("source_url", "")
            target = rule.get("target_url", "")
            if not source or not target:
                continue
            key = (source, target)
            if key in seen:
                continue
            seen.add(key)
            redirects.append(RedirectRule(
                source_url=source,
                target_url=target,
                status_code=int(rule.get("status_code", 301)),
                source_plugin=rule.get("source_plugin"),
            ))

        # 2. From SEO pages with redirect_ownership
        for page in bundle_manifest.seo_full.pages:
            if not page.redirect_ownership:
                continue
            ownership = page.redirect_ownership
            target = ownership.get("target_url", "")
            if not target:
                continue
            key = (page.canonical_url, target)
            if key in seen:
                continue
            seen.add(key)
            redirects.append(RedirectRule(
                source_url=page.canonical_url,
                target_url=target,
                status_code=int(ownership.get("status_code", 301)),
                source_plugin=page.source_plugin,
            ))

        return redirects

    # ------------------------------------------------------------------
    # Metadata strategy compilation
    # ------------------------------------------------------------------

    def _compile_metadata_strategy(
        self,
        bundle_manifest: BundleManifest,
    ) -> dict[str, Any]:
        """Build metadata generation strategy from SEO data."""
        pages = bundle_manifest.seo_full.pages
        if not pages:
            return {
                "seo_plugin": None,
                "title_template": None,
                "has_og": False,
                "has_twitter": False,
                "has_schema_markup": False,
            }

        # Determine active SEO plugin from the most common source_plugin
        plugin_counts: dict[str, int] = {}
        for page in pages:
            plugin_counts[page.source_plugin] = plugin_counts.get(page.source_plugin, 0) + 1
        seo_plugin = max(plugin_counts, key=plugin_counts.get)  # type: ignore[arg-type]

        # Determine title template pattern from first page that has one
        title_template: str | None = None
        for page in pages:
            if page.title_template:
                title_template = page.title_template
                break

        has_og = any(bool(p.og_metadata) for p in pages)
        has_twitter = any(bool(p.twitter_metadata) for p in pages)
        has_schema_markup = any(bool(p.schema_type_hints) for p in pages)

        return {
            "seo_plugin": seo_plugin,
            "title_template": title_template,
            "has_og": has_og,
            "has_twitter": has_twitter,
            "has_schema_markup": has_schema_markup,
        }

    # ------------------------------------------------------------------
    # Forms strategy compilation
    # ------------------------------------------------------------------

    def _compile_forms_strategy(
        self,
        bundle_manifest: BundleManifest,
    ) -> list[FormStrategy]:
        """Build form migration strategy for each supported form instance."""
        strategies: list[FormStrategy] = []

        for instance in bundle_manifest.plugin_instances.instances:
            if instance.instance_type != "form":
                continue
            if instance.source_plugin not in _SUPPORTED_FORM_PROVIDERS:
                continue

            fields = instance.config.get("fields", [])
            if not isinstance(fields, list):
                fields = []

            submission_dest = instance.config.get(
                "submission_destination", "astro_api_route",
            )

            strategies.append(FormStrategy(
                form_id=instance.instance_id,
                source_plugin=instance.source_plugin,
                target="astro_api_route",
                fields=fields,
                submission_destination=str(submission_dest),
            ))

        return strategies

    # ------------------------------------------------------------------
    # Preview rules compilation
    # ------------------------------------------------------------------

    def _compile_preview_rules(
        self,
        bundle_manifest: BundleManifest,
    ) -> dict[str, Any]:
        """Extract preview rules from editorial workflows."""
        ew = bundle_manifest.editorial_workflows
        return {
            "draft_behavior": ew.draft_behavior,
            "preview_expectations": ew.preview_expectations,
            "revision_policy": ew.revision_policy,
        }

    # ------------------------------------------------------------------
    # Search strategy compilation
    # ------------------------------------------------------------------

    def _compile_search_strategy(
        self,
        bundle_manifest: BundleManifest,
        content_model: ContentModelManifest,
    ) -> SearchStrategy | None:
        """Build search strategy when search_config has searchable types."""
        sc = bundle_manifest.search_config
        if not sc.searchable_types:
            return None

        # Map searchable WordPress types to Strapi collection api_ids
        type_to_api: dict[str, str] = {}
        for coll in content_model.collections:
            if coll.source_post_type:
                type_to_api[coll.source_post_type] = coll.api_id

        searchable_collections = sorted(
            type_to_api[t] for t in sc.searchable_types if t in type_to_api
        )

        return SearchStrategy(
            enabled=True,
            searchable_collections=searchable_collections,
            facets=sc.facets,
            implementation="strapi_filter",
        )

    # ------------------------------------------------------------------
    # Integration boundaries compilation
    # ------------------------------------------------------------------

    def _compile_integration_boundaries(
        self,
        bundle_manifest: BundleManifest,
    ) -> list[IntegrationBoundary]:
        """Classify each integration as rebuild, proxy, or drop."""
        boundaries: list[IntegrationBoundary] = []

        for integration in bundle_manifest.integration_manifest.integrations:
            disposition, target_system, finding = self._classify_integration(integration)
            boundaries.append(IntegrationBoundary(
                integration_id=integration.integration_id,
                disposition=disposition,
                target_system=target_system,
                details={
                    "integration_type": integration.integration_type,
                    "target": integration.target,
                    "business_critical": integration.business_critical,
                },
                finding=finding,
            ))

        return boundaries

    def _classify_integration(
        self,
        integration: Any,
    ) -> tuple[str, str, Finding | None]:
        """Return (disposition, target_system, optional_finding) for an integration."""
        itype = integration.integration_type

        # Form destinations can be rebuilt in Strapi/Astro
        if itype in _REBUILD_INTEGRATION_TYPES:
            return "rebuild", "strapi", None

        # External APIs, webhooks, CRMs, embeds, scripts → proxy
        if itype in _PROXY_INTEGRATION_TYPES:
            return "proxy", "external", None

        # Anything else is unsupported → drop with Finding
        finding = Finding(
            severity=FindingSeverity.WARNING,
            stage="behavior_compiler",
            construct=f"integration:{integration.integration_id}",
            message=f"Unsupported integration type '{itype}' for '{integration.target}'",
            recommended_action="Review integration manually and decide whether to rebuild or drop",
        )
        logger.warning(
            "Dropping unsupported integration %s (type=%s)",
            integration.integration_id,
            itype,
        )
        return "drop", "external", finding

    # ------------------------------------------------------------------
    # Unsupported construct collection
    # ------------------------------------------------------------------

    def _collect_unsupported(
        self,
        capability_manifest: CapabilityManifest,
    ) -> list[Finding]:
        """Collect findings for capabilities classified as unsupported."""
        findings: list[Finding] = []

        for cap in capability_manifest.capabilities:
            if cap.classification != "unsupported":
                continue
            findings.append(Finding(
                severity=FindingSeverity.WARNING,
                stage="behavior_compiler",
                construct=f"{cap.capability_type}:{cap.source_plugin or 'unknown'}",
                message=f"Unsupported capability '{cap.capability_type}' from plugin '{cap.source_plugin or 'unknown'}'",
                recommended_action="Review manually and implement custom handling if needed",
            ))
            # Also include any findings attached to the capability itself
            findings.extend(cap.findings)

        return findings

    # ------------------------------------------------------------------
    # Migration Mapping Manifest
    # ------------------------------------------------------------------

    def _build_migration_mapping(
        self,
        bundle_manifest: BundleManifest,
        content_model: ContentModelManifest,
        presentation: PresentationManifest,
    ) -> MigrationMappingManifest:
        """Build the complete MigrationMappingManifest."""
        type_mappings = self._build_type_mappings(content_model)
        field_mappings = self._build_field_mappings(content_model)
        relation_mappings = self._build_relation_mappings(content_model)
        media_strategy = self._build_media_strategy()
        term_mappings = self._build_term_mappings(bundle_manifest)
        template_mappings = self._build_template_mappings(presentation)
        plugin_mappings = self._build_plugin_instance_mappings(bundle_manifest)

        return MigrationMappingManifest(
            type_mappings=sorted(type_mappings, key=lambda m: m.source_post_type),
            field_mappings=sorted(
                field_mappings, key=lambda m: (m.source_post_type, m.source_field),
            ),
            relation_mappings=sorted(
                relation_mappings, key=lambda m: m.source_relationship_id,
            ),
            media_mapping_strategy=media_strategy,
            term_mappings=sorted(term_mappings, key=lambda m: m.source_taxonomy),
            template_mappings=sorted(
                template_mappings, key=lambda m: m.source_template,
            ),
            plugin_instance_mappings=sorted(
                plugin_mappings, key=lambda m: (m.source_plugin, m.source_instance_type),
            ),
        )

    def _build_type_mappings(
        self,
        content_model: ContentModelManifest,
    ) -> list[TypeMapping]:
        """Map source post types to Strapi collection api_ids."""
        mappings: list[TypeMapping] = []
        for coll in content_model.collections:
            if coll.source_post_type:
                mappings.append(TypeMapping(
                    source_post_type=coll.source_post_type,
                    target_api_id=coll.api_id,
                    source_plugin=coll.source_plugin,
                ))
        return mappings

    def _build_field_mappings(
        self,
        content_model: ContentModelManifest,
    ) -> list[FieldMapping]:
        """Map source fields to target Strapi fields per collection."""
        mappings: list[FieldMapping] = []
        for coll in content_model.collections:
            if not coll.source_post_type:
                continue
            for field_def in coll.fields:
                transform = self._infer_field_transform(field_def.strapi_type)
                mappings.append(FieldMapping(
                    source_post_type=coll.source_post_type,
                    source_field=field_def.name,
                    target_api_id=coll.api_id,
                    target_field=field_def.name,
                    transform=transform,
                ))
        return mappings

    @staticmethod
    def _infer_field_transform(field_type: str) -> str:
        """Infer the migration transform from a Strapi field type."""
        transform_map: dict[str, str] = {
            "richtext": "rich_text",
            "component": "component",
            "dynamiczone": "dynamic_zone",
            "relation": "relation",
            "media": "relation",
        }
        return transform_map.get(field_type, "direct")

    def _build_relation_mappings(
        self,
        content_model: ContentModelManifest,
    ) -> list[RelationMapping]:
        """Map content relationships to Strapi relations."""
        mappings: list[RelationMapping] = []
        for rel in content_model.relations:
            mappings.append(RelationMapping(
                source_relationship_id=rel.source_relationship_id,
                source_collection=rel.source_collection,
                target_collection=rel.target_collection,
                target_field=rel.field_name,
                relation_type=rel.relation_type,
            ))
        return mappings

    @staticmethod
    def _build_media_strategy() -> MediaMappingStrategy:
        """Build sensible default media mapping strategy."""
        return MediaMappingStrategy(
            url_rewrite_pattern="/uploads/{filename}",
            relation_aware=True,
            preserve_alt_text=True,
            preserve_caption=True,
        )

    def _build_term_mappings(
        self,
        bundle_manifest: BundleManifest,
    ) -> list[TermMapping]:
        """Map WordPress taxonomies to Strapi collections."""
        mappings: list[TermMapping] = []
        taxonomies = bundle_manifest.taxonomies
        tax_list = taxonomies.get("taxonomies", []) if isinstance(taxonomies, dict) else []

        for tax in tax_list:
            if not isinstance(tax, dict):
                continue
            name = tax.get("name", "")
            if not name:
                continue
            # Convention: taxonomy name → api_id, field is plural name
            api_id = name.lower().replace(" ", "-").replace("_", "-")
            mappings.append(TermMapping(
                source_taxonomy=name,
                target_api_id=api_id,
                target_field=name.lower().replace(" ", "_"),
            ))

        return mappings

    def _build_template_mappings(
        self,
        presentation: PresentationManifest,
    ) -> list[TemplateMapping]:
        """Map source templates to Astro route patterns and layouts."""
        mappings: list[TemplateMapping] = []
        for rt in presentation.route_templates:
            mappings.append(TemplateMapping(
                source_template=rt.source_template,
                target_route_pattern=rt.route_pattern,
                target_layout=rt.layout,
            ))
        return mappings

    def _build_plugin_instance_mappings(
        self,
        bundle_manifest: BundleManifest,
    ) -> list[PluginInstanceMapping]:
        """Map plugin instances to migration strategies using adapter rules."""
        mappings: list[PluginInstanceMapping] = []
        seen: set[tuple[str, str]] = set()

        for instance in bundle_manifest.plugin_instances.instances:
            key = (instance.source_plugin, instance.instance_type)
            if key in seen:
                continue
            seen.add(key)

            target_api: str | None = None
            target_comp: str | None = None
            adapter = self._adapters.get(instance.source_plugin)
            if adapter:
                rules = adapter.migration_rules([])
                strategy = "collection"
                if rules:
                    first_rule = rules[0]
                    strategy = first_rule.target_type
                    if first_rule.target_type == "component":
                        target_comp = first_rule.target_identifier
                    else:
                        target_api = first_rule.target_identifier
            else:
                strategy = "skip"

            mappings.append(PluginInstanceMapping(
                source_plugin=instance.source_plugin,
                source_instance_type=instance.instance_type,
                target_api_id=target_api,
                target_component_uid=target_comp,
                migration_strategy=strategy,
            ))

        return mappings
