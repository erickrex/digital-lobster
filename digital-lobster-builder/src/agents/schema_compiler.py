from __future__ import annotations

import logging
import re
from typing import Any

from src.adapters.base import PluginAdapter
from src.adapters.registry import build_adapter_registry, default_adapters
from src.agents.base import AgentResult, BaseAgent
from src.models.bundle_artifacts import FieldUsageEntry
from src.models.bundle_manifest import BundleManifest
from src.models.capability_manifest import Capability, CapabilityManifest
from src.models.content_model_manifest import (
    ContentModelManifest,
    SeoComponentStrategy,
    StrapiCollection,
    StrapiComponent,
    StrapiRelation,
    ValidationHint,
)
from src.models.finding import Finding, FindingSeverity
from src.models.strapi_types import StrapiFieldDefinition
from src.pipeline_context import extract_bundle_manifest, extract_capability_manifest

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# WordPress → Strapi field type mapping
# ---------------------------------------------------------------------------

_WP_TO_STRAPI_TYPE: dict[str, str] = {
    "text": "string",
    "textarea": "richtext",
    "wysiwyg": "richtext",
    "number": "integer",
    "email": "email",
    "url": "string",
    "image": "media",
    "file": "media",
    "gallery": "media",
    "boolean": "boolean",
    "true_false": "boolean",
    "date": "date",
    "date_picker": "date",
    "datetime": "datetime",
    "color_picker": "string",
    "select": "enumeration",
    "checkbox": "json",
    "radio": "enumeration",
    "reference": "relation",
    "relationship": "relation",
    "post_object": "relation",
    "taxonomy": "relation",
    "object": "json",
    "json": "json",
    "enum": "enumeration",
}


def _slugify(name: str) -> str:
    """Convert a display name to a Strapi-safe slug (lowercase, hyphens)."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "unnamed"


def _api_id(name: str) -> str:
    """Convert a display name to a Strapi api_id (lowercase, hyphens)."""
    return _slugify(name)


def _map_field_type(inferred_type: str) -> str:
    """Map a WordPress/field-usage inferred type to a Strapi field type."""
    return _WP_TO_STRAPI_TYPE.get(inferred_type, "string")


# ---------------------------------------------------------------------------
# Standard SEO component fields
# ---------------------------------------------------------------------------

_SEO_FIELDS: list[StrapiFieldDefinition] = [
    StrapiFieldDefinition(name="meta_title", strapi_type="string"),
    StrapiFieldDefinition(name="meta_description", strapi_type="text"),
    StrapiFieldDefinition(name="canonical_url", strapi_type="string"),
    StrapiFieldDefinition(name="no_index", strapi_type="boolean"),
    StrapiFieldDefinition(name="no_follow", strapi_type="boolean"),
    StrapiFieldDefinition(name="og_title", strapi_type="string"),
    StrapiFieldDefinition(name="og_description", strapi_type="text"),
    StrapiFieldDefinition(name="og_image", strapi_type="media"),
    StrapiFieldDefinition(name="twitter_title", strapi_type="string"),
    StrapiFieldDefinition(name="twitter_description", strapi_type="text"),
    StrapiFieldDefinition(name="twitter_image", strapi_type="media"),
    StrapiFieldDefinition(name="structured_data", strapi_type="json"),
]

_SEO_COMPONENT_UID = "shared.seo-metadata"


class SchemaCompilerAgent(BaseAgent):
    """Produces the Content_Model_Manifest from capability and bundle data.

    Deterministically compiles:
    - Collections from content-model capabilities and field_usage_report
    - Components from repeaters and flexible content structures
    - Relations from content_relationships
    - SEO component strategy from SEO capabilities
    - Validation hints from field_usage_report
    - Plugin-specific schema contributions via adapter schema_strategy
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

        logger.info("Starting schema compilation for %s", bundle_manifest.site_url)

        findings: list[Finding] = []

        collections = self._compile_collections(capability_manifest, bundle_manifest, findings)
        components = self._compile_components(bundle_manifest)
        relations = self._compile_relations(capability_manifest, bundle_manifest)
        seo_strategy = self._compile_seo_strategy(capability_manifest, collections)
        plugin_contributions = self._compile_plugin_contributions(capability_manifest)
        validation_hints = self._compile_validation_hints(bundle_manifest)

        # Merge plugin adapter schema contributions
        for contrib in plugin_contributions:
            collections.extend(contrib.collections)
            components.extend(contrib.components)
            relations.extend(contrib.relations)

        # Attach SEO component UID to all collections
        if seo_strategy:
            for coll in collections:
                if seo_strategy.component_uid not in coll.components:
                    coll.components.append(seo_strategy.component_uid)

        manifest = ContentModelManifest(
            collections=collections,
            components=components,
            relations=relations,
            seo_strategy=seo_strategy,
            validation_hints=validation_hints,
            findings=findings,
        )

        logger.info(
            "Schema compilation complete for %s: %d collections, %d components, %d relations, %d findings",
            bundle_manifest.site_url,
            len(collections),
            len(components),
            len(relations),
            len(findings),
        )

        return AgentResult(
            agent_name="schema_compiler",
            artifacts={"content_model_manifest": manifest},
        )


    # ------------------------------------------------------------------
    # Collection compilation
    # ------------------------------------------------------------------

    def _compile_collections(
        self,
        capability_manifest: CapabilityManifest,
        bundle_manifest: BundleManifest,
        findings: list[Finding],
    ) -> list[StrapiCollection]:
        """Build StrapiCollections from content-model capabilities and field_usage_report."""
        # Group field usage entries by post_type
        fields_by_post_type: dict[str, list[FieldUsageEntry]] = {}
        for entry in bundle_manifest.field_usage_report.fields:
            fields_by_post_type.setdefault(entry.post_type, []).append(entry)

        # Determine which post types have content-model capabilities
        content_post_types: set[str] = set()
        for cap in capability_manifest.content_model_capabilities:
            pt = cap.details.get("post_type")
            if pt:
                content_post_types.add(pt)

        # Also include any post type present in field_usage_report
        content_post_types.update(fields_by_post_type.keys())

        collections: list[StrapiCollection] = []
        for post_type in sorted(content_post_types):
            fields = self._map_fields(
                fields_by_post_type.get(post_type, []), findings,
            )
            component_uids = self._extract_component_uids(
                fields_by_post_type.get(post_type, [])
            )
            api_id = _api_id(post_type)
            singular = post_type.replace("_", " ").replace("-", " ").title()

            collections.append(
                StrapiCollection(
                    display_name=singular,
                    singular_name=_slugify(post_type),
                    plural_name=_slugify(post_type) + "s",
                    api_id=api_id,
                    fields=fields,
                    components=component_uids,
                    source_post_type=post_type,
                )
            )

        return collections

    def _map_fields(
        self, field_entries: list[FieldUsageEntry], findings: list[Finding],
    ) -> list[StrapiFieldDefinition]:
        """Map FieldUsageEntry list to StrapiFieldDefinition list.

        Repeaters and flexible content are handled as component/dynamiczone
        references rather than inline fields.  Field types not in the
        mapping table produce a Finding and fall back to ``string``.
        """
        fields: list[StrapiFieldDefinition] = []
        for entry in field_entries:
            behaves_as = entry.behaves_as or ""
            inferred = entry.inferred_type

            if behaves_as == "repeater" or inferred == "repeater":
                # Repeater → component reference (actual component built in _compile_components)
                fields.append(
                    StrapiFieldDefinition(
                        name=entry.field_name,
                        strapi_type="component",
                        required=not entry.nullable,
                    )
                )
            elif behaves_as == "flexible" or inferred == "flexible_content":
                # Flexible content → dynamic zone
                fields.append(
                    StrapiFieldDefinition(
                        name=entry.field_name,
                        strapi_type="dynamiczone",
                        required=not entry.nullable,
                    )
                )
            elif behaves_as == "reference" or inferred in ("reference", "relationship", "post_object", "taxonomy"):
                fields.append(
                    StrapiFieldDefinition(
                        name=entry.field_name,
                        strapi_type="relation",
                        required=not entry.nullable,
                        relation_type="manyToOne" if entry.cardinality == "single" else "manyToMany",
                    )
                )
            else:
                strapi_type = _map_field_type(inferred)
                # Report unmapped field types that fell back to "string"
                if inferred not in _WP_TO_STRAPI_TYPE and inferred != "text":
                    findings.append(Finding(
                        severity=FindingSeverity.INFO,
                        stage="schema_compiler",
                        construct=f"field:{entry.post_type}.{entry.field_name}",
                        message=(
                            f"Unknown field type '{inferred}' for "
                            f"'{entry.field_name}' on '{entry.post_type}', "
                            f"mapped to Strapi '{strapi_type}'"
                        ),
                        recommended_action="Review field type mapping and adjust if needed",
                    ))
                fields.append(
                    StrapiFieldDefinition(
                        name=entry.field_name,
                        strapi_type=strapi_type,
                        required=not entry.nullable,
                    )
                )
        return fields

    @staticmethod
    def _extract_component_uids(field_entries: list[FieldUsageEntry]) -> list[str]:
        """Return component UIDs for repeater/flexible fields in a post type."""
        uids: list[str] = []
        for entry in field_entries:
            behaves_as = entry.behaves_as or ""
            inferred = entry.inferred_type
            if behaves_as == "repeater" or inferred == "repeater":
                uids.append(f"content.{_slugify(entry.field_name)}")
            elif behaves_as == "flexible" or inferred == "flexible_content":
                uids.append(f"content.{_slugify(entry.field_name)}")
        return uids


    # ------------------------------------------------------------------
    # Component compilation
    # ------------------------------------------------------------------

    def _compile_components(
        self, bundle_manifest: BundleManifest
    ) -> list[StrapiComponent]:
        """Build StrapiComponents from repeater and flexible content fields."""
        components: list[StrapiComponent] = []
        seen_uids: set[str] = set()

        for entry in bundle_manifest.field_usage_report.fields:
            behaves_as = entry.behaves_as or ""
            inferred = entry.inferred_type

            if behaves_as in ("repeater", "flexible") or inferred in (
                "repeater",
                "flexible_content",
            ):
                uid = f"content.{_slugify(entry.field_name)}"
                if uid in seen_uids:
                    continue
                seen_uids.add(uid)

                # Build sub-fields from sample_values if they contain dicts
                sub_fields = self._infer_component_fields(entry)

                components.append(
                    StrapiComponent(
                        uid=uid,
                        display_name=entry.field_name.replace("_", " ").title(),
                        category="content",
                        fields=sub_fields,
                    )
                )

        return components

    @staticmethod
    def _infer_component_fields(
        entry: FieldUsageEntry,
    ) -> list[StrapiFieldDefinition]:
        """Infer component sub-fields from a repeater/flexible field's sample values."""
        fields: list[StrapiFieldDefinition] = []
        for sample in entry.sample_values:
            if isinstance(sample, dict):
                for key, value in sample.items():
                    if any(f.name == key for f in fields):
                        continue
                    if isinstance(value, bool):
                        strapi_type = "boolean"
                    elif isinstance(value, int):
                        strapi_type = "integer"
                    elif isinstance(value, float):
                        strapi_type = "float"
                    else:
                        strapi_type = "string"
                    fields.append(
                        StrapiFieldDefinition(name=key, strapi_type=strapi_type)
                    )
                break  # one sample dict is enough to infer shape
        # Fallback: if no dict samples, add a generic value field
        if not fields:
            fields.append(StrapiFieldDefinition(name="value", strapi_type="string"))
        return fields

    # ------------------------------------------------------------------
    # Relation compilation
    # ------------------------------------------------------------------

    def _compile_relations(
        self,
        capability_manifest: CapabilityManifest,
        bundle_manifest: BundleManifest,
    ) -> list[StrapiRelation]:
        """Generate StrapiRelations from content_relationships data."""
        relations: list[StrapiRelation] = []
        # Build a lookup of known collection api_ids from field_usage post types
        known_types: set[str] = {
            _api_id(e.post_type) for e in bundle_manifest.field_usage_report.fields
        }

        for rel in bundle_manifest.content_relationships.relationships:
            relation_type = self._infer_relation_type(rel.relation_type)
            source_api = _api_id(rel.source_id.split(":")[0]) if ":" in rel.source_id else _api_id(rel.source_id)
            target_api = _api_id(rel.target_id.split(":")[0]) if ":" in rel.target_id else _api_id(rel.target_id)

            field_name = f"{target_api}_relation"

            relations.append(
                StrapiRelation(
                    source_collection=source_api,
                    target_collection=target_api,
                    field_name=field_name,
                    relation_type=relation_type,
                    source_relationship_id=f"{rel.source_id}->{rel.target_id}",
                )
            )

        return relations

    @staticmethod
    def _infer_relation_type(wp_relation_type: str) -> str:
        """Map a WordPress relation type string to a Strapi relation type."""
        mapping = {
            "post_to_post": "manyToMany",
            "post_to_term": "manyToMany",
            "post_to_media": "manyToOne",
            "post_to_user": "manyToOne",
            "term_to_term": "manyToMany",
        }
        return mapping.get(wp_relation_type, "manyToOne")


    # ------------------------------------------------------------------
    # SEO component strategy
    # ------------------------------------------------------------------

    def _compile_seo_strategy(
        self,
        capability_manifest: CapabilityManifest,
        collections: list[StrapiCollection],
    ) -> SeoComponentStrategy | None:
        """Create a reusable SEO component strategy if SEO capabilities exist."""
        seo_caps = [
            c for c in capability_manifest.capabilities if c.capability_type == "seo"
        ]
        if not seo_caps:
            return None

        applied_to = [c.api_id for c in collections]

        return SeoComponentStrategy(
            component_uid=_SEO_COMPONENT_UID,
            fields=list(_SEO_FIELDS),
            applied_to=applied_to,
        )

    # ------------------------------------------------------------------
    # Plugin adapter schema contributions
    # ------------------------------------------------------------------

    def _compile_plugin_contributions(
        self,
        capability_manifest: CapabilityManifest,
    ) -> list[SchemaContribution]:
        """Delegate to plugin adapters for schema contributions.

        For each plugin family with capabilities, call the adapter's
        schema_strategy() to get collections, components, and relations
        that the plugin contributes to the Strapi model.
        """
        from src.adapters.base import SchemaContribution

        contributions: list[SchemaContribution] = []

        for family, caps in capability_manifest.plugin_capabilities.items():
            adapter = self._adapters.get(family)
            if adapter is None:
                continue
            contrib = adapter.schema_strategy(caps)
            if contrib.collections or contrib.components or contrib.relations:
                contributions.append(contrib)
                logger.info(
                    "Plugin adapter '%s' contributed %d collections, %d components, %d relations",
                    family,
                    len(contrib.collections),
                    len(contrib.components),
                    len(contrib.relations),
                )

        # Also handle plugin instances that define a schema strategy
        for family, adapter in self._adapters.items():
            if family in capability_manifest.plugin_capabilities:
                continue  # already handled above
            # Check if there are plugin instances for this family
            instance_caps = [
                c
                for c in capability_manifest.capabilities
                if c.source_plugin == family and c.capability_type == "content_model"
            ]
            if instance_caps:
                contrib = adapter.schema_strategy(instance_caps)
                if contrib.collections or contrib.components or contrib.relations:
                    contributions.append(contrib)

        return contributions

    # ------------------------------------------------------------------
    # Validation hints
    # ------------------------------------------------------------------

    def _compile_validation_hints(
        self, bundle_manifest: BundleManifest
    ) -> list[ValidationHint]:
        """Attach validation hints from field_usage_report."""
        hints: list[ValidationHint] = []
        for entry in bundle_manifest.field_usage_report.fields:
            enum_values: list[str] | None = None
            if entry.behaves_as == "enum" or entry.inferred_type in ("select", "radio", "enum"):
                # Extract enum values from sample_values
                enum_values = [
                    str(v) for v in entry.sample_values if v is not None
                ] or None

            hints.append(
                ValidationHint(
                    collection_api_id=_api_id(entry.post_type),
                    field_name=entry.field_name,
                    nullable=entry.nullable,
                    cardinality=entry.cardinality,
                    enum_values=enum_values,
                )
            )
        return hints
