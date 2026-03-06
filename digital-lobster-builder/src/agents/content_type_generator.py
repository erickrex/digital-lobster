"""Content Type Generator agent — translates ModelingManifest schemas into
Strapi Content Types via the Content-Type Builder API.

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2, 5.3, 5.4
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import httpx

from src.agents.base import AgentResult, BaseAgent
from src.models.modeling_manifest import (
    ContentCollectionSchema,
    FrontmatterField,
    ModelingManifest,
    TaxonomyDefinition,
)
from src.models.strapi_types import (
    ContentTypeMap,
    StrapiComponentSchema,
    StrapiContentTypeDefinition,
    StrapiFieldDefinition,
)
from src.pipeline_context import extract_modeling_manifest
from src.utils.ssh import strapi_base_url_context

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FIELD_TYPE_MAP: dict[str, str] = {
    "string": "text",
    "number": "integer",
    "boolean": "boolean",
    "date": "datetime",
    "reference": "relation",
    "list": "json",
}

SEO_FIELD_PATTERNS: set[str] = {
    "meta_title",
    "meta_description",
    "og_image",
    "canonical_url",
}

# Strapi reserved attribute names that cannot be used directly.
_STRAPI_RESERVED_WORDS: set[str] = {
    "id",
    "created_at",
    "updated_at",
    "published_at",
    "created_by",
    "updated_by",
    "locale",
    "localizations",
}


# ---------------------------------------------------------------------------
# Pure helper functions (testable in isolation)
# ---------------------------------------------------------------------------


def map_frontmatter_to_strapi(field: FrontmatterField) -> StrapiFieldDefinition:
    """Map a single ``FrontmatterField`` to a ``StrapiFieldDefinition``.

    Unknown field types default to ``"text"``.
    """
    return StrapiFieldDefinition(
        name=field.name,
        strapi_type=FIELD_TYPE_MAP.get(field.type, "text"),
        required=field.required,
    )


def _sanitize_field_name(name: str) -> str:
    """Prefix reserved words with ``x_`` so Strapi accepts them."""
    if name.lower() in _STRAPI_RESERVED_WORDS:
        return f"x_{name}"
    return name


def _to_singular(name: str) -> str:
    """Naïve singularisation: strip trailing 's' when present."""
    if name.endswith("ies"):
        return name[:-3] + "y"
    if name.endswith("ses"):
        return name[:-2]
    if name.endswith("s") and not name.endswith("ss"):
        return name[:-1]
    return name


def _to_plural(name: str) -> str:
    """Naïve pluralisation."""
    if name.endswith("y") and not name.endswith("ey"):
        return name[:-1] + "ies"
    if name.endswith("s") or name.endswith("sh") or name.endswith("ch"):
        return name + "es"
    return name + "s"


def _slugify(name: str) -> str:
    """Convert a collection name to a URL-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug


def detect_seo_fields(
    fields: list[FrontmatterField],
) -> tuple[list[FrontmatterField], list[FrontmatterField]]:
    """Split *fields* into (seo_fields, remaining_fields)."""
    seo: list[FrontmatterField] = []
    rest: list[FrontmatterField] = []
    for f in fields:
        if f.name in SEO_FIELD_PATTERNS:
            seo.append(f)
        else:
            rest.append(f)
    return seo, rest


def build_seo_component(
    seo_fields: list[FrontmatterField],
) -> StrapiComponentSchema:
    """Build the reusable ``seo-metadata`` component schema."""
    return StrapiComponentSchema(
        name="seo-metadata",
        category="shared",
        fields=[map_frontmatter_to_strapi(f) for f in seo_fields],
    )


def build_content_type_definition(
    schema: ContentCollectionSchema,
    seo_component_uid: str | None = None,
) -> StrapiContentTypeDefinition:
    """Build a ``StrapiContentTypeDefinition`` from a collection schema.

    SEO fields are excluded from the inline field list when a
    *seo_component_uid* is provided (they live in the component instead).
    """
    seo_fields, remaining = detect_seo_fields(schema.frontmatter_fields)

    strapi_fields: list[StrapiFieldDefinition] = []
    for f in remaining:
        sf = map_frontmatter_to_strapi(f)
        sf.name = _sanitize_field_name(sf.name)
        strapi_fields.append(sf)

    singular = _to_singular(schema.collection_name)
    plural = _to_plural(singular) if singular == schema.collection_name else schema.collection_name
    api_id = f"api::{singular}.{singular}"

    components: list[str] = []
    if seo_fields and seo_component_uid:
        components.append(seo_component_uid)

    return StrapiContentTypeDefinition(
        display_name=schema.collection_name.replace("-", " ").replace("_", " ").title(),
        singularName=singular,
        pluralName=plural,
        api_id=api_id,
        fields=strapi_fields,
        components=components,
    )


def build_taxonomy_content_type(
    taxonomy: TaxonomyDefinition,
    content_type_map: dict[str, str],
) -> tuple[StrapiContentTypeDefinition, list[str]]:
    """Build a Content Type for a taxonomy with standard fields and relations.

    Returns ``(definition, warnings)`` where *warnings* contains messages
    about skipped relations.
    """
    warnings: list[str] = []
    singular = _to_singular(taxonomy.taxonomy)
    plural = _to_plural(singular) if singular == taxonomy.taxonomy else taxonomy.taxonomy
    api_id = f"api::{singular}.{singular}"

    fields: list[StrapiFieldDefinition] = [
        StrapiFieldDefinition(name="name", strapi_type="text", required=True),
        StrapiFieldDefinition(name="slug", strapi_type="text", required=True),
        StrapiFieldDefinition(name="description", strapi_type="text", required=False),
        # Self-referencing parent relation for hierarchy
        StrapiFieldDefinition(
            name="parent",
            strapi_type="relation",
            required=False,
            relation_target=api_id,
            relation_type="manyToOne",
        ),
    ]

    # Many-to-many relation to referenced collection
    if taxonomy.collection_ref:
        if taxonomy.collection_ref in content_type_map:
            target_api_id = content_type_map[taxonomy.collection_ref]
            fields.append(
                StrapiFieldDefinition(
                    name=_slugify(taxonomy.collection_ref),
                    strapi_type="relation",
                    required=False,
                    relation_target=target_api_id,
                    relation_type="manyToMany",
                )
            )
        else:
            msg = (
                f"Taxonomy '{taxonomy.taxonomy}' references collection "
                f"'{taxonomy.collection_ref}' which is not in the content type map — "
                f"skipping relation."
            )
            logger.warning(msg)
            warnings.append(msg)

    return (
        StrapiContentTypeDefinition(
            display_name=taxonomy.taxonomy.replace("-", " ").replace("_", " ").title(),
            singularName=singular,
            pluralName=plural,
            api_id=api_id,
            fields=fields,
            components=[],
        ),
        warnings,
    )


# ---------------------------------------------------------------------------
# Strapi API interaction helpers
# ---------------------------------------------------------------------------


async def _post_component(
    base_url: str,
    token: str,
    component: StrapiComponentSchema,
) -> str:
    """POST a component schema to the Content-Type Builder API.

    Returns the component UID (e.g. ``shared.seo-metadata``).
    """
    url = f"{base_url}/content-type-builder/components"
    headers = {"Authorization": f"Bearer {token}"}

    attributes: dict[str, Any] = {}
    for f in component.fields:
        attributes[f.name] = {"type": f.strapi_type, "required": f.required}

    payload: dict[str, Any] = {
        "component": {
            "category": component.category,
            "displayName": component.name,
            "attributes": attributes,
        },
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=payload, headers=headers)

    if resp.status_code in (401, 403):
        raise RuntimeError(
            f"Auth error creating component '{component.name}' "
            f"(HTTP {resp.status_code}): {resp.text}"
        )

    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"Failed to create component '{component.name}' "
            f"(HTTP {resp.status_code}): {resp.text}"
        )

    uid = f"{component.category}.{component.name}"
    logger.info("Created component %s", uid)
    return uid


async def _post_content_type(
    base_url: str,
    token: str,
    ct: StrapiContentTypeDefinition,
) -> str:
    """POST a content type to the Content-Type Builder API.

    On a 400 validation error the function adjusts field names (prefixing
    reserved words with ``x_``) and retries once.

    Returns the Strapi API identifier.
    """
    url = f"{base_url}/content-type-builder/content-types"
    headers = {"Authorization": f"Bearer {token}"}

    def _build_payload(definition: StrapiContentTypeDefinition) -> dict[str, Any]:
        attributes: dict[str, Any] = {}
        for f in definition.fields:
            attr: dict[str, Any] = {"type": f.strapi_type, "required": f.required}
            if f.relation_target:
                attr["target"] = f.relation_target
                attr["relation"] = f.relation_type or "oneToMany"
            attributes[f.name] = attr
        return {
            "contentType": {
                "displayName": definition.display_name,
                "singularName": definition.singularName,
                "pluralName": definition.pluralName,
                "attributes": attributes,
            },
        }

    payload = _build_payload(ct)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=payload, headers=headers)

        # Auth errors → abort immediately
        if resp.status_code in (401, 403):
            raise RuntimeError(
                f"Auth error creating content type '{ct.display_name}' "
                f"(HTTP {resp.status_code}): {resp.text}"
            )

        # Validation error → adjust field names and retry once
        if resp.status_code == 400:
            logger.warning(
                "Validation error for '%s', adjusting field names and retrying: %s",
                ct.display_name,
                resp.text,
            )
            adjusted_fields = []
            for f in ct.fields:
                adjusted = f.model_copy()
                adjusted.name = _sanitize_field_name(f.name)
                adjusted_fields.append(adjusted)
            adjusted_ct = ct.model_copy(update={"fields": adjusted_fields})
            payload = _build_payload(adjusted_ct)
            resp = await client.post(url, json=payload, headers=headers)

        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"Failed to create content type '{ct.display_name}' "
                f"(HTTP {resp.status_code}): {resp.text}"
            )

    logger.info("Created content type %s", ct.api_id)
    return ct.api_id


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------


class ContentTypeGeneratorAgent(BaseAgent):
    """Translates a ``ModelingManifest`` into Strapi Content Types.

    Reads ``modeling_manifest``, ``strapi_base_url``, and
    ``strapi_api_token`` from the pipeline context.  Writes
    ``content_type_map`` back into the context.
    """

    async def execute(self, context: dict[str, Any]) -> AgentResult:
        """Execute the content type generation workflow.

        1. Read ModelingManifest from context
        2. For each ContentCollectionSchema:
           a. Map FrontmatterFields to Strapi field types
           b. Detect SEO field patterns → create seo-metadata component
           c. POST to Content-Type Builder API
           d. On validation error: adjust field names/types, retry once
        3. For each TaxonomyDefinition:
           a. Create taxonomy Content Type (name, slug, description, parent)
           b. Create many-to-many relation to referenced collection
        4. Return content_type_map artifact
        """
        start = time.monotonic()
        warnings: list[str] = []

        manifest = extract_modeling_manifest(context)
        base_url: str = context["strapi_base_url"]
        api_token: str = context["strapi_api_token"]
        ssh_connection_string = context.get("ssh_connection_string")
        cms_config = context.get("cms_config")
        ssh_private_key_path = (
            getattr(cms_config, "ssh_private_key_path", None)
            if cms_config is not None
            else None
        )

        mappings: dict[str, str] = {}
        taxonomy_mappings: dict[str, str] = {}
        component_uids: list[str] = []

        # ------------------------------------------------------------------
        # Phase 1: Detect if any collection has SEO fields → create component
        # ------------------------------------------------------------------
        seo_component_uid: str | None = None
        needs_seo = False
        for schema in manifest.collections:
            seo_fields, _ = detect_seo_fields(schema.frontmatter_fields)
            if seo_fields:
                needs_seo = True
                break

        async with strapi_base_url_context(
            base_url, ssh_connection_string, ssh_private_key_path
        ) as resolved_base_url:
            if needs_seo:
                # Gather all unique SEO fields across collections
                all_seo: dict[str, FrontmatterField] = {}
                for schema in manifest.collections:
                    seo_fields, _ = detect_seo_fields(schema.frontmatter_fields)
                    for f in seo_fields:
                        all_seo[f.name] = f

                seo_component = build_seo_component(list(all_seo.values()))
                seo_component_uid = await _post_component(
                    resolved_base_url, api_token, seo_component
                )
                component_uids.append(seo_component_uid)

            # ------------------------------------------------------------------
            # Phase 2: Create Content Types for each collection
            # ------------------------------------------------------------------
            for schema in manifest.collections:
                ct_def = build_content_type_definition(schema, seo_component_uid)
                api_id = await _post_content_type(
                    resolved_base_url, api_token, ct_def
                )
                mappings[schema.collection_name] = api_id

            # ------------------------------------------------------------------
            # Phase 3: Create taxonomy Content Types with relations
            # ------------------------------------------------------------------
            for tax in manifest.taxonomies:
                tax_def, tax_warnings = build_taxonomy_content_type(tax, mappings)
                warnings.extend(tax_warnings)
                api_id = await _post_content_type(
                    resolved_base_url, api_token, tax_def
                )
                taxonomy_mappings[tax.taxonomy] = api_id

        # ------------------------------------------------------------------
        # Build result
        # ------------------------------------------------------------------
        content_type_map = ContentTypeMap(
            mappings=mappings,
            taxonomy_mappings=taxonomy_mappings,
            component_uids=component_uids,
        )

        duration = time.monotonic() - start
        return AgentResult(
            agent_name="content_type_generator",
            artifacts={"content_type_map": content_type_map},
            warnings=warnings,
            duration_seconds=duration,
        )
