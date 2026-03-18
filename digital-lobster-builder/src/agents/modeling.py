from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib.parse import urlparse

from src.agents.base import AgentResult, BaseAgent
from src.models.inventory import ContentTypeSummary, Inventory, TaxonomySummary
from src.models.modeling_manifest import (
    ComponentMapping,
    ContentCollectionSchema,
    FrontmatterField,
    ModelingManifest,
    TaxonomyDefinition,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# WordPress field type → Zod/frontmatter type mapping
# ---------------------------------------------------------------------------

WP_FIELD_TYPE_MAP: dict[str, str] = {
    "text": "string",
    "textarea": "string",
    "wysiwyg": "string",
    "number": "number",
    "range": "number",
    "email": "string",
    "url": "string",
    "password": "string",
    "image": "string",
    "file": "string",
    "gallery": "list",
    "select": "string",
    "checkbox": "boolean",
    "radio": "string",
    "true_false": "boolean",
    "date_picker": "date",
    "date_time_picker": "date",
    "time_picker": "string",
    "color_picker": "string",
    "relationship": "reference",
    "post_object": "reference",
    "taxonomy": "reference",
    "user": "reference",
    "repeater": "list",
    "flexible_content": "list",
    "group": "string",
}

# ---------------------------------------------------------------------------
# Known WordPress block → Astro component mappings
# ---------------------------------------------------------------------------

KNOWN_BLOCK_MAPPINGS: dict[str, dict[str, Any]] = {
    "core/paragraph": {
        "astro_component": "Paragraph",
        "is_island": False,
        "props": [{"name": "content", "type": "string"}],
    },
    "core/heading": {
        "astro_component": "Heading",
        "is_island": False,
        "props": [
            {"name": "level", "type": "number"},
            {"name": "content", "type": "string"},
        ],
    },
    "core/image": {
        "astro_component": "Image",
        "is_island": False,
        "props": [
            {"name": "src", "type": "string"},
            {"name": "alt", "type": "string"},
            {"name": "caption", "type": "string"},
        ],
    },
    "core/list": {
        "astro_component": "List",
        "is_island": False,
        "props": [
            {"name": "ordered", "type": "boolean"},
            {"name": "items", "type": "array"},
        ],
    },
    "core/quote": {
        "astro_component": "Blockquote",
        "is_island": False,
        "props": [
            {"name": "content", "type": "string"},
            {"name": "citation", "type": "string"},
        ],
    },
    "core/code": {
        "astro_component": "CodeBlock",
        "is_island": False,
        "props": [
            {"name": "content", "type": "string"},
            {"name": "language", "type": "string"},
        ],
    },
    "core/table": {
        "astro_component": "Table",
        "is_island": False,
        "props": [{"name": "content", "type": "string"}],
    },
    "core/embed": {
        "astro_component": "Embed",
        "is_island": True,
        "hydration_directive": "client:visible",
        "props": [
            {"name": "url", "type": "string"},
            {"name": "provider", "type": "string"},
        ],
    },
    "core/gallery": {
        "astro_component": "Gallery",
        "is_island": False,
        "props": [{"name": "images", "type": "array"}],
    },
    "core/video": {
        "astro_component": "Video",
        "is_island": True,
        "hydration_directive": "client:visible",
        "props": [
            {"name": "src", "type": "string"},
            {"name": "poster", "type": "string"},
        ],
    },
    "core/audio": {
        "astro_component": "Audio",
        "is_island": True,
        "hydration_directive": "client:visible",
        "props": [{"name": "src", "type": "string"}],
    },
    "core/buttons": {
        "astro_component": "Buttons",
        "is_island": False,
        "props": [{"name": "buttons", "type": "array"}],
    },
    "core/button": {
        "astro_component": "Button",
        "is_island": False,
        "props": [
            {"name": "text", "type": "string"},
            {"name": "url", "type": "string"},
        ],
    },
    "core/columns": {
        "astro_component": "Columns",
        "is_island": False,
        "props": [{"name": "columns", "type": "number"}],
    },
    "core/group": {
        "astro_component": "Group",
        "is_island": False,
        "props": [],
    },
    "core/separator": {
        "astro_component": "Separator",
        "is_island": False,
        "props": [],
    },
    "core/spacer": {
        "astro_component": "Spacer",
        "is_island": False,
        "props": [{"name": "height", "type": "string"}],
    },
    "core/html": {
        "astro_component": "RawHtml",
        "is_island": False,
        "props": [{"name": "content", "type": "string"}],
    },
    "core/shortcode": {
        "astro_component": "RawHtml",
        "is_island": False,
        "props": [{"name": "content", "type": "string"}],
    },
    # Kadence Blocks
    "kadence/tabs": {
        "astro_component": "KadenceTabs",
        "is_island": True,
        "hydration_directive": "client:visible",
        "props": [{"name": "tabs", "type": "array"}],
    },
    "kadence/accordion": {
        "astro_component": "KadenceAccordion",
        "is_island": True,
        "hydration_directive": "client:visible",
        "props": [{"name": "panes", "type": "array"}],
    },
    "kadence/advancedbtn": {
        "astro_component": "KadenceButton",
        "is_island": False,
        "props": [
            {"name": "text", "type": "string"},
            {"name": "url", "type": "string"},
        ],
    },
    "kadence/rowlayout": {
        "astro_component": "KadenceRow",
        "is_island": False,
        "props": [{"name": "columns", "type": "number"}],
    },
    # GeoDirectory blocks
    "geodirectory/geodir-widget-map": {
        "astro_component": "GeoMap",
        "is_island": True,
        "hydration_directive": "client:load",
        "props": [
            {"name": "latitude", "type": "number"},
            {"name": "longitude", "type": "number"},
            {"name": "zoom", "type": "number"},
        ],
    },
    "geodirectory/geodir-widget-search": {
        "astro_component": "GeoSearch",
        "is_island": True,
        "hydration_directive": "client:load",
        "props": [{"name": "placeholder", "type": "string"}],
    },
    # Forminator
    "forminator/forminator-form": {
        "astro_component": "ForminatorForm",
        "is_island": True,
        "hydration_directive": "client:load",
        "props": [{"name": "formId", "type": "number"}],
    },
}

# ---------------------------------------------------------------------------
# Post type → collection name / route pattern helpers
# ---------------------------------------------------------------------------

# Standard WP post types and their conventional Astro mappings
_STANDARD_POST_TYPE_ROUTES: dict[str, tuple[str, str]] = {
    "post": ("posts", "/posts/[slug]"),
    "page": ("pages", "/[slug]"),
    "attachment": ("media", "/media/[slug]"),
}

def _post_type_to_collection(post_type: str) -> tuple[str, str]:
    """Derive an Astro collection name and route pattern from a WP post type.

    Returns:
        (collection_name, route_pattern)
    """
    if post_type in _STANDARD_POST_TYPE_ROUTES:
        return _STANDARD_POST_TYPE_ROUTES[post_type]

    # Custom post types: slugify and build a route
    collection = post_type.replace("-", "_").replace(" ", "_").lower()
    route = f"/{collection}/[slug]"
    return collection, route


def _normalize_legacy_path(url_or_path: str) -> str:
    """Normalize a permalink or URL to a site-relative path."""
    if not url_or_path:
        return "/"
    parsed = urlparse(url_or_path)
    path = parsed.path if parsed.scheme or parsed.netloc else url_or_path
    if not path:
        return "/"
    if not path.startswith("/"):
        path = "/" + path
    normalized = path.rstrip("/")
    return normalized or "/"


def _common_path_segments(paths: list[str]) -> list[str]:
    """Return the shared leading path segments across all paths."""
    if not paths:
        return []
    split_paths = [
        [segment for segment in path.strip("/").split("/") if segment]
        for path in paths
    ]
    common = split_paths[0]
    for parts in split_paths[1:]:
        shared: list[str] = []
        for index, segment in enumerate(common):
            if index >= len(parts) or parts[index] != segment:
                break
            shared.append(segment)
        common = shared
        if not common:
            break
    return common


def infer_route_pattern(
    post_type: str,
    content_items: list[dict[str, Any]] | None = None,
) -> str:
    """Infer a stable route pattern from exported permalinks when possible."""
    _, default_route = _post_type_to_collection(post_type)
    if post_type in _STANDARD_POST_TYPE_ROUTES or not content_items:
        return default_route

    candidate_prefixes: list[str] = []
    for item in content_items:
        if not isinstance(item, dict):
            continue
        raw_post_type = str(item.get("post_type") or item.get("type") or "")
        if raw_post_type != post_type:
            continue
        permalink = str(
            item.get("legacy_permalink")
            or item.get("link")
            or item.get("permalink")
            or ""
        )
        path = _normalize_legacy_path(permalink)
        if path == "/":
            continue
        segments = [segment for segment in path.strip("/").split("/") if segment]
        if len(segments) < 2:
            continue
        candidate_prefixes.append("/" + "/".join(segments[:-1]))

    shared_segments = _common_path_segments(candidate_prefixes)
    if not shared_segments:
        return default_route

    return "/" + "/".join(shared_segments) + "/[slug]"

def _infer_field_type(field_name: str) -> str:
    """Infer a Zod-compatible type from a WordPress custom field name.

    Uses heuristics based on common naming conventions.
    """
    name_lower = field_name.lower()

    if any(kw in name_lower for kw in ("date", "time", "_at", "published")):
        return "date"
    if any(kw in name_lower for kw in ("count", "number", "price", "amount", "qty", "quantity", "rating", "order")):
        return "number"
    if any(kw in name_lower for kw in ("is_", "has_", "enable", "active", "visible", "featured")):
        return "boolean"
    # Check list/plural keywords BEFORE singular image keywords
    if any(kw in name_lower for kw in ("gallery", "images", "photos", "items", "list", "tags")):
        return "list"
    if any(kw in name_lower for kw in ("image", "photo", "thumbnail", "avatar", "logo", "icon", "banner")):
        return "string"
    if any(kw in name_lower for kw in ("author", "parent", "related", "ref")):
        return "reference"

    return "string"

# ---------------------------------------------------------------------------
# Default frontmatter fields every content collection gets
# ---------------------------------------------------------------------------

_BASE_FRONTMATTER: list[dict[str, Any]] = [
    {"name": "title", "type": "string", "required": True, "description": "Content title"},
    {"name": "slug", "type": "string", "required": True, "description": "URL slug"},
    {"name": "date", "type": "date", "required": True, "description": "Publication date"},
    {"name": "status", "type": "string", "required": True, "description": "Publication status (publish, draft, etc.)"},
    {"name": "excerpt", "type": "string", "required": False, "description": "Short excerpt or summary"},
]

# ---------------------------------------------------------------------------
# Pure mapping functions (no LLM needed)
# ---------------------------------------------------------------------------

def build_collection_schemas(
    content_types: list[ContentTypeSummary],
    content_items: list[dict[str, Any]] | None = None,
) -> list[ContentCollectionSchema]:
    """Map WordPress post types to Astro content collection schemas.

    Each post type becomes one ContentCollectionSchema with frontmatter
    fields derived from the WP custom fields plus standard base fields.
    """
    schemas: list[ContentCollectionSchema] = []

    for ct in content_types:
        collection_name, _ = _post_type_to_collection(ct.post_type)
        route_pattern = infer_route_pattern(ct.post_type, content_items)

        # Start with base fields
        fields = [FrontmatterField(**f) for f in _BASE_FRONTMATTER]

        # Add taxonomy reference fields
        for tax in ct.taxonomies:
            fields.append(
                FrontmatterField(
                    name=tax,
                    type="list",
                    required=False,
                    description=f"Associated {tax} terms",
                )
            )

        # Add custom fields
        seen_names = {f.name for f in fields}
        for cf in ct.custom_fields:
            if cf in seen_names:
                continue
            seen_names.add(cf)
            fields.append(
                FrontmatterField(
                    name=cf,
                    type=_infer_field_type(cf),
                    required=False,
                    description=f"Custom field: {cf}",
                )
            )

        schemas.append(
            ContentCollectionSchema(
                collection_name=collection_name,
                source_post_type=ct.post_type,
                frontmatter_fields=fields,
                route_pattern=route_pattern,
            )
        )

    return schemas

def build_component_mappings(
    block_types: list[str],
) -> list[ComponentMapping]:
    """Map WordPress block types to Astro component specs.

    Known blocks get a specific component mapping; unknown blocks get a
    fallback rich-text HTML component.
    """
    mappings: list[ComponentMapping] = []

    for block_type in block_types:
        known = KNOWN_BLOCK_MAPPINGS.get(block_type)
        if known:
            mappings.append(
                ComponentMapping(
                    wp_block_type=block_type,
                    astro_component=known["astro_component"],
                    is_island=known["is_island"],
                    hydration_directive=known.get("hydration_directive"),
                    props=known["props"],
                    fallback=False,
                )
            )
        else:
            # Fallback: rich-text HTML component
            mappings.append(
                ComponentMapping(
                    wp_block_type=block_type,
                    astro_component="RawHtmlBlock",
                    is_island=False,
                    hydration_directive=None,
                    props=[{"name": "content", "type": "string"}],
                    fallback=True,
                )
            )

    return mappings

def build_taxonomy_definitions(
    taxonomies: list[TaxonomySummary],
) -> list[TaxonomyDefinition]:
    """Map WordPress taxonomies to Astro content collection references or data files.

    Standard taxonomies (category, post_tag) become data files.
    Custom taxonomies become content collection references.
    """
    definitions: list[TaxonomyDefinition] = []

    # Standard WP taxonomies that map to simple data files
    data_file_taxonomies = {"category", "post_tag"}

    for tax in taxonomies:
        if tax.taxonomy in data_file_taxonomies:
            definitions.append(
                TaxonomyDefinition(
                    taxonomy=tax.taxonomy,
                    collection_ref=None,
                    data_file=f"src/data/{tax.taxonomy}.json",
                )
            )
        else:
            # Custom taxonomy → content collection reference
            collection_name = tax.taxonomy.replace("-", "_").lower()
            definitions.append(
                TaxonomyDefinition(
                    taxonomy=tax.taxonomy,
                    collection_ref=collection_name,
                    data_file=None,
                )
            )

    return definitions

def _extract_inventory(context: dict[str, Any]) -> Inventory:
    """Extract an Inventory from the pipeline context."""
    raw = context["inventory"]
    if isinstance(raw, Inventory):
        return raw
    return Inventory.model_validate(raw)

def _extract_block_types_from_inventory(inventory: Inventory) -> list[str]:
    """Collect all unique block type names from the inventory's plugin features."""
    block_types: set[str] = set()
    for plugin in inventory.plugins:
        for feature in plugin.detected_features:
            # Features that look like block type identifiers (contain '/')
            if "/" in feature:
                block_types.add(feature)
    return sorted(block_types)

def _extract_block_types_from_kb(kb_results: list[dict]) -> list[str]:
    """Extract block type names from Knowledge Base query results."""
    block_types: set[str] = set()
    for result in kb_results:
        content = result.get("content", "")
        # Try to parse as JSON (blocks_usage.json format)
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                # blocks_usage.json typically has block names as keys
                for key in data:
                    if "/" in key:
                        block_types.add(key)
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "name" in item:
                        block_types.add(item["name"])
                    elif isinstance(item, str) and "/" in item:
                        block_types.add(item)
        except (json.JSONDecodeError, TypeError):
            # Not JSON — scan for block-type patterns (namespace/block-name)
            import re

            pattern = re.compile(r"\b([a-z][a-z0-9-]*/[a-z][a-z0-9-]*)\b")
            block_types.update(pattern.findall(content))
    return sorted(block_types)

# ---------------------------------------------------------------------------
# LLM-assisted enrichment prompt
# ---------------------------------------------------------------------------

def _build_enrichment_system_prompt() -> str:
    """System prompt for LLM-assisted manifest enrichment."""
    return (
        "You are a WordPress-to-Astro migration expert. You will receive a "
        "modeling manifest (JSON) and additional context from a Knowledge Base. "
        "Your job is to review and enrich the manifest:\n\n"
        "1. Verify that component mappings are sensible.\n"
        "2. Suggest any missing frontmatter fields based on the KB context.\n"
        "3. Confirm taxonomy definitions are appropriate.\n\n"
        "Return ONLY a valid JSON object conforming to the ModelingManifest schema. "
        "Do not add explanatory text outside the JSON."
    )

def _build_enrichment_user_prompt(
    manifest_dict: dict[str, Any],
    kb_context: list[dict],
) -> str:
    """Build the user prompt for LLM enrichment."""
    lines: list[str] = [
        "Here is the current modeling manifest:\n",
        json.dumps(manifest_dict, indent=2),
        "\n\n--- Additional context from Knowledge Base ---\n",
    ]
    for doc in kb_context:
        content = doc.get("content", "")
        if len(content) > 800:
            content = content[:800] + "…"
        lines.append(content)

    lines.append(
        "\n\nPlease review and return the enriched manifest as JSON. "
        "Keep all existing entries. Only add or adjust fields if the KB "
        "context clearly supports it."
    )
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# ModelingAgent
# ---------------------------------------------------------------------------

class ModelingAgent(BaseAgent):
    """Maps WordPress content types, blocks, and taxonomies to Astro equivalents."""
    async def execute(self, context: dict[str, Any]) -> AgentResult:
        """Execute the Modeling agent.

        Args:
            context: Must contain ``inventory`` (Inventory or dict) and
                optionally ``kb_ref`` (Knowledge Base ID string) and
                ``prd_md`` (PRD markdown string).

        Returns:
            AgentResult with a ``modeling_manifest`` artifact containing
            the ModelingManifest dict.
        """
        start = time.monotonic()
        warnings: list[str] = []

        inventory = _extract_inventory(context)
        kb_ref: str | None = context.get("kb_ref")

        # 1. Query KB for block usage data, CPT definitions, taxonomy structures
        kb_context = await self._query_kb(kb_ref, warnings)

        # 2. Collect all block types from inventory + KB
        block_types_inv = _extract_block_types_from_inventory(inventory)
        block_types_kb = _extract_block_types_from_kb(kb_context)
        all_block_types = sorted(set(block_types_inv) | set(block_types_kb))

        # 3. Build content collection schemas from post types
        collections = build_collection_schemas(
            inventory.content_types,
            context.get("content_items", []),
        )

        # 4. Build component mappings from block types
        components = build_component_mappings(all_block_types)

        # Log fallback blocks
        for comp in components:
            if comp.fallback:
                warnings.append(
                    f"Unmapped block type '{comp.wp_block_type}' → "
                    "fallback RawHtmlBlock component"
                )

        # 5. Build taxonomy definitions
        taxonomies = build_taxonomy_definitions(inventory.taxonomies)

        # 6. Assemble manifest
        manifest = ModelingManifest(
            collections=collections,
            components=components,
            taxonomies=taxonomies,
        )

        # 7. Optionally enrich via LLM if KB context is available
        if kb_context and self.gradient_client:
            manifest = await self._enrich_with_llm(
                manifest, kb_context, warnings
            )

        return AgentResult(
            agent_name="modeling",
            artifacts={"modeling_manifest": manifest.model_dump()},
            warnings=warnings,
            duration_seconds=time.monotonic() - start,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _query_kb(
        self,
        kb_ref: str | None,
        warnings: list[str],
    ) -> list[dict]:
        """Query the Knowledge Base for block usage, CPT, and taxonomy data."""
        if not kb_ref or not self.kb_client:
            return []

        queries = [
            "WordPress block usage data and block types",
            "custom post type definitions and custom fields",
            "taxonomy structures categories tags",
        ]

        results: list[dict] = []
        for q in queries:
            try:
                docs = await self.kb_client.query(kb_ref, q, top_k=5)
                results.extend(docs)
            except Exception as exc:
                logger.warning("KB query failed for '%s': %s", q, exc)
                warnings.append(f"KB query failed: {q} — {exc}")

        return results

    async def _enrich_with_llm(
        self,
        manifest: ModelingManifest,
        kb_context: list[dict],
        warnings: list[str],
    ) -> ModelingManifest:
        """Use LLM to review and enrich the manifest with KB context."""
        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            try:
                enriched_dict = await self.gradient_client.complete_structured(
                    messages=[
                        {
                            "role": "system",
                            "content": _build_enrichment_system_prompt(),
                        },
                        {
                            "role": "user",
                            "content": _build_enrichment_user_prompt(
                                manifest.model_dump(), kb_context
                            ),
                        },
                    ],
                    schema=ModelingManifest,
                )
                return ModelingManifest.model_validate(enriched_dict)
            except json.JSONDecodeError:
                if attempt < max_attempts:
                    logger.warning(
                        "LLM returned empty/invalid JSON (attempt %d/%d), retrying",
                        attempt, max_attempts,
                    )
                    continue
                logger.warning("LLM enrichment returned invalid JSON after %d attempts, using base manifest", max_attempts)
                warnings.append("LLM enrichment failed: empty response after retries")
                return manifest
            except Exception as exc:
                logger.warning(
                    "LLM enrichment failed, using base manifest: %s", exc
                )
                warnings.append(f"LLM enrichment failed: {exc}")
                return manifest
        return manifest
