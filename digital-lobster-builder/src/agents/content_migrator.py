"""Content Migrator agent — populates Strapi with content, media,
taxonomies, and navigation menus from the WordPress Export Bundle.

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8,
             7.1, 7.2, 7.3, 7.4, 7.5, 7.6,
             8.1, 8.2, 8.3, 8.4
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
import time
from html.parser import HTMLParser
from typing import Any

import httpx

from src.agents.base import AgentResult, BaseAgent
from src.models.content import WordPressBlock, WordPressContentItem
from src.models.migration_report import (
    ContentTypeMigrationStats,
    MediaMigrationStats,
    MigrationReport,
)
from src.models.modeling_manifest import ModelingManifest
from src.models.strapi_types import ContentTypeMap
from src.pipeline_context import (
    MediaManifestEntry,
    extract_content_items,
    extract_content_type_map,
    extract_media_manifest,
    extract_menus,
    extract_modeling_manifest,
)
from src.utils.ssh import strapi_base_url_context

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MEDIA_CONCURRENCY = 5
DEFAULT_BATCH_SIZE = 50
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 2.0


# ---------------------------------------------------------------------------
# Block HTML → Strapi Rich Text conversion (Requirement 6.3)
# ---------------------------------------------------------------------------


class _BlockHTMLParser(HTMLParser):
    """Converts WordPress block HTML into Strapi rich text blocks.

    Strapi v4 rich text (blocks format) uses a JSON structure with typed
    nodes.  This parser handles: headings (h1-h6), paragraphs, lists
    (ul/ol with li), images, and links (a tags).
    """

    def __init__(self) -> None:
        super().__init__()
        self._blocks: list[dict[str, Any]] = []
        self._stack: list[dict[str, Any]] = []
        self._current_text: str = ""
        self._current_children: list[dict[str, Any]] = []
        self._in_list: str | None = None  # "unordered" or "ordered"
        self._list_items: list[dict[str, Any]] = []
        self._link_url: str | None = None

    def _flush_text(self) -> None:
        """Push accumulated text as a text node into current children."""
        if self._current_text:
            node: dict[str, Any] = {"type": "text", "text": self._current_text}
            if self._link_url is not None:
                node["url"] = self._link_url
                node["type"] = "link"
                node["children"] = [{"type": "text", "text": self._current_text}]
            self._current_children.append(node)
            self._current_text = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        tag_lower = tag.lower()

        if tag_lower in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush_text()
            level = int(tag_lower[1])
            self._stack.append({"type": "heading", "level": level})
            self._current_children = []

        elif tag_lower == "p":
            self._flush_text()
            self._stack.append({"type": "paragraph"})
            self._current_children = []

        elif tag_lower in ("ul", "ol"):
            self._flush_text()
            self._in_list = "unordered" if tag_lower == "ul" else "ordered"
            self._list_items = []

        elif tag_lower == "li":
            self._flush_text()
            self._current_children = []

        elif tag_lower == "a":
            self._flush_text()
            self._link_url = attr_dict.get("href", "")

        elif tag_lower == "img":
            self._flush_text()
            image_block: dict[str, Any] = {
                "type": "image",
                "image": {
                    "url": attr_dict.get("src", ""),
                    "alternativeText": attr_dict.get("alt", ""),
                },
            }
            if attr_dict.get("width"):
                image_block["image"]["width"] = attr_dict["width"]
            if attr_dict.get("height"):
                image_block["image"]["height"] = attr_dict["height"]
            self._blocks.append(image_block)

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()

        if tag_lower in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush_text()
            if self._stack and self._stack[-1]["type"] == "heading":
                node = self._stack.pop()
                node["children"] = self._current_children or [
                    {"type": "text", "text": ""}
                ]
                self._blocks.append(node)
                self._current_children = []

        elif tag_lower == "p":
            self._flush_text()
            if self._stack and self._stack[-1]["type"] == "paragraph":
                node = self._stack.pop()
                node["children"] = self._current_children or [
                    {"type": "text", "text": ""}
                ]
                self._blocks.append(node)
                self._current_children = []

        elif tag_lower == "li":
            self._flush_text()
            item: dict[str, Any] = {
                "type": "list-item",
                "children": self._current_children or [
                    {"type": "text", "text": ""}
                ],
            }
            self._list_items.append(item)
            self._current_children = []

        elif tag_lower in ("ul", "ol"):
            if self._in_list is not None:
                list_block: dict[str, Any] = {
                    "type": "list",
                    "format": self._in_list,
                    "children": self._list_items,
                }
                self._blocks.append(list_block)
                self._in_list = None
                self._list_items = []

        elif tag_lower == "a":
            self._flush_text()
            self._link_url = None

    def handle_data(self, data: str) -> None:
        self._current_text += data

    def get_blocks(self) -> list[dict[str, Any]]:
        """Return the parsed Strapi rich text blocks."""
        self._flush_text()
        # Flush any remaining inline text as a paragraph
        if self._current_children:
            self._blocks.append(
                {"type": "paragraph", "children": self._current_children}
            )
            self._current_children = []
        return self._blocks


def convert_blocks_to_rich_text(
    blocks: list[WordPressBlock],
) -> list[dict[str, Any]]:
    """Convert a list of WordPress blocks to Strapi rich text blocks format.

    Each ``WordPressBlock`` has an ``html`` field containing the rendered
    HTML for that block.  We concatenate all block HTML and parse it into
    Strapi's blocks-based rich text structure.

    Preserves: headings, paragraphs, lists, images, and links.
    """
    combined_html = "".join(block.html for block in blocks)
    parser = _BlockHTMLParser()
    parser.feed(combined_html)
    return parser.get_blocks()


# ---------------------------------------------------------------------------
# Media URL replacement helper
# ---------------------------------------------------------------------------


def replace_media_urls(
    data: Any,
    media_url_map: dict[str, str],
) -> Any:
    """Recursively replace WordPress media URLs with Strapi URLs in data.

    Works on strings, dicts, and lists.
    """
    if isinstance(data, str):
        result = data
        for wp_url, strapi_url in media_url_map.items():
            result = result.replace(wp_url, strapi_url)
        return result
    if isinstance(data, dict):
        return {k: replace_media_urls(v, media_url_map) for k, v in data.items()}
    if isinstance(data, list):
        return [replace_media_urls(item, media_url_map) for item in data]
    return data


# ---------------------------------------------------------------------------
# Menu URL rewriting helper (Requirement 8.3, 8.4)
# ---------------------------------------------------------------------------


def rewrite_menu_url(
    url: str,
    route_map: dict[str, str],
    migrated_slugs: set[str],
) -> str:
    """Rewrite an internal WordPress URL to an Astro route pattern.

    *route_map* maps WordPress post types to Astro route patterns
    (e.g. ``{"post": "/blog/[slug]", "page": "/[slug]"}``).

    *migrated_slugs* is the set of slugs that were successfully migrated.

    If the URL references a non-migrated page, returns ``"#not-migrated"``.
    External URLs are returned unchanged.
    """
    # External URLs pass through
    if url.startswith(("http://", "https://", "//", "mailto:", "tel:", "#")):
        # Check if it's an internal WP URL by looking for known slugs
        for slug in migrated_slugs:
            if slug in url:
                # Try to find a matching route pattern
                for _post_type, pattern in route_map.items():
                    return pattern.replace("[slug]", slug)
        return url

    # Relative internal URL — extract slug from path
    slug = url.strip("/").split("/")[-1] if url.strip("/") else ""

    if not slug:
        return url

    if slug not in migrated_slugs:
        return "#not-migrated"

    # Find matching route pattern
    for _post_type, pattern in route_map.items():
        return pattern.replace("[slug]", slug)

    return url


# ---------------------------------------------------------------------------
# Strapi API helpers with retry logic
# ---------------------------------------------------------------------------


async def _upload_single_media(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    media_entry: MediaManifestEntry,
    export_bundle: dict[str, Any],
    semaphore: asyncio.Semaphore,
) -> tuple[str, str | None]:
    """Upload a single media file to Strapi Media Library.

    Returns ``(original_url, strapi_url)`` on success, or
    ``(original_url, None)`` on failure.
    """
    original_url = media_entry.source_url
    filename = media_entry.filename or original_url.split("/")[-1]
    alt_text = media_entry.alt_text
    caption = media_entry.caption

    async with semaphore:
        try:
            content = export_bundle.get(media_entry.bundle_path)
            if content is None:
                logger.warning(
                    "Media bundle asset missing for %s at %s",
                    original_url,
                    media_entry.bundle_path,
                )
                return original_url, None

            if isinstance(content, str):
                content = content.encode("utf-8")

            content_type = media_entry.mime_type or "application/octet-stream"

            # Upload to Strapi
            upload_url = f"{base_url}/api/upload"
            headers = {"Authorization": f"Bearer {token}"}
            files_payload = {
                "files": (filename, content, content_type),
            }
            data_payload: dict[str, str] = {}
            if alt_text:
                data_payload["fileInfo"] = (
                    f'{{"alternativeText": "{alt_text}", "caption": "{caption}"}}'
                )

            upload_resp = await client.post(
                upload_url,
                headers=headers,
                files=files_payload,
                data=data_payload,
                timeout=120,
            )

            if upload_resp.status_code in (200, 201):
                resp_data = upload_resp.json()
                if isinstance(resp_data, list) and resp_data:
                    strapi_url = resp_data[0].get("url", "")
                    return original_url, strapi_url
                elif isinstance(resp_data, dict):
                    strapi_url = resp_data.get("url", "")
                    return original_url, strapi_url

            logger.warning(
                "Media upload failed (HTTP %d) for %s: %s",
                upload_resp.status_code,
                original_url,
                upload_resp.text[:200],
            )
            return original_url, None

        except Exception as exc:
            logger.warning("Media upload error for %s: %s", original_url, exc)
            return original_url, None


async def upload_media_files(
    base_url: str,
    token: str,
    media_manifest: list[MediaManifestEntry],
    export_bundle: dict[str, Any],
    concurrency: int = DEFAULT_MEDIA_CONCURRENCY,
) -> tuple[dict[str, str], MediaMigrationStats]:
    """Upload all media files in parallel with bounded concurrency.

    Returns ``(media_url_map, stats)``.
    """
    media_url_map: dict[str, str] = {}
    failed_urls: list[str] = []
    semaphore = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient() as client:
        tasks = [
            _upload_single_media(
                client,
                base_url,
                token,
                entry,
                export_bundle,
                semaphore,
            )
            for entry in media_manifest
        ]
        results = await asyncio.gather(*tasks)

    for original_url, strapi_url in results:
        if strapi_url is not None:
            media_url_map[original_url] = strapi_url
        else:
            failed_urls.append(original_url)

    stats = MediaMigrationStats(
        total=len(media_manifest),
        succeeded=len(media_url_map),
        failed=len(failed_urls),
        failed_urls=failed_urls,
    )
    return media_url_map, stats


# ---------------------------------------------------------------------------
# Content entry creation with batching and retry (Requirement 6.5, 6.6, 6.7)
# ---------------------------------------------------------------------------


async def _create_entry_with_retry(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    api_id: str,
    payload: dict[str, Any],
    max_retries: int = MAX_RETRIES,
    initial_backoff: float = INITIAL_BACKOFF_SECONDS,
) -> dict[str, Any] | None:
    """Create a single Strapi entry with exponential backoff on retryable errors.

    Returns the created entry data on success, or ``None`` on permanent failure.
    """
    # Derive the plural API name from api_id (e.g. "api::post.post" → "posts")
    singular = api_id.split("::")[-1].split(".")[-1] if "::" in api_id else api_id
    # Naïve pluralisation
    if singular.endswith("y") and not singular.endswith("ey"):
        plural = singular[:-1] + "ies"
    elif singular.endswith("s") or singular.endswith("sh") or singular.endswith("ch"):
        plural = singular + "es"
    else:
        plural = singular + "s"

    url = f"{base_url}/api/{plural}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    backoff = initial_backoff
    for attempt in range(max_retries + 1):
        try:
            resp = await client.post(
                url, json={"data": payload}, headers=headers, timeout=30
            )

            if resp.status_code in (200, 201):
                return resp.json()

            # Retryable: rate limit or server error
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt < max_retries:
                    logger.warning(
                        "Retryable error (HTTP %d) creating entry, "
                        "retrying in %.1fs (attempt %d/%d)",
                        resp.status_code,
                        backoff,
                        attempt + 1,
                        max_retries,
                    )
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue

            # Permanent failure
            logger.error(
                "Failed to create entry (HTTP %d): %s",
                resp.status_code,
                resp.text[:300],
            )
            return None

        except Exception as exc:
            if attempt < max_retries:
                logger.warning(
                    "Network error creating entry, retrying in %.1fs: %s",
                    backoff,
                    exc,
                )
                await asyncio.sleep(backoff)
                backoff *= 2
                continue
            logger.error("Failed to create entry after retries: %s", exc)
            return None

    return None


def _build_entry_payload(
    item: WordPressContentItem,
    content_type_map: ContentTypeMap,
    media_url_map: dict[str, str],
    taxonomy_term_ids: dict[str, dict[str, int]],
) -> dict[str, Any]:
    """Build the Strapi entry payload from a WordPress content item.

    Maps frontmatter fields, converts block HTML to rich text, replaces
    media URLs, and links taxonomy relations.
    """
    payload: dict[str, Any] = {
        "title": item.title,
        "slug": item.slug,
    }

    # Map metadata fields
    if item.date:
        payload["date"] = item.date
    if item.excerpt:
        payload["excerpt"] = item.excerpt
    if item.status:
        payload["status"] = item.status

    # Add all meta fields
    for key, value in item.meta.items():
        payload[key] = value

    # Convert block HTML to Strapi rich text
    if item.blocks:
        rich_text = convert_blocks_to_rich_text(item.blocks)
        rich_text = replace_media_urls(rich_text, media_url_map)
        payload["content"] = rich_text

    # Replace media URLs in the entire payload
    payload = replace_media_urls(payload, media_url_map)

    # Handle featured media
    if item.featured_media and item.featured_media.get("url"):
        original_url = item.featured_media["url"]
        if original_url in media_url_map:
            payload["featured_image"] = media_url_map[original_url]

    # Link taxonomy relations
    for tax_name, terms in item.taxonomies.items():
        if tax_name in taxonomy_term_ids:
            term_ids = []
            for term in terms:
                term_slug = term if isinstance(term, str) else str(term)
                if term_slug in taxonomy_term_ids[tax_name]:
                    term_ids.append(taxonomy_term_ids[tax_name][term_slug])
            if term_ids:
                payload[tax_name] = term_ids

    # Add SEO fields if present
    if item.seo:
        payload["seo"] = replace_media_urls(item.seo, media_url_map)

    return payload


async def create_taxonomy_terms(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    content_items: list[WordPressContentItem],
    content_type_map: ContentTypeMap,
) -> tuple[dict[str, dict[str, int]], int, list[str]]:
    """Create taxonomy term entries in Strapi.

    Returns ``(taxonomy_term_ids, total_created, warnings)`` where
    *taxonomy_term_ids* maps ``{taxonomy_name: {term_slug: strapi_id}}``.
    """
    taxonomy_term_ids: dict[str, dict[str, int]] = {}
    total_created = 0
    warnings: list[str] = []

    # Collect unique terms per taxonomy from all content items
    terms_by_taxonomy: dict[str, set[str]] = {}
    for item in content_items:
        for tax_name, terms in item.taxonomies.items():
            if tax_name not in terms_by_taxonomy:
                terms_by_taxonomy[tax_name] = set()
            for term in terms:
                term_str = term if isinstance(term, str) else str(term)
                terms_by_taxonomy[tax_name].add(term_str)

    for tax_name, terms in terms_by_taxonomy.items():
        if tax_name not in content_type_map.taxonomy_mappings:
            warnings.append(
                f"Taxonomy '{tax_name}' not found in content type map, skipping."
            )
            continue

        api_id = content_type_map.taxonomy_mappings[tax_name]
        taxonomy_term_ids[tax_name] = {}

        for term_slug in terms:
            result = await _create_entry_with_retry(
                client,
                base_url,
                token,
                api_id,
                {"name": term_slug, "slug": term_slug},
            )
            if result:
                # Extract the ID from the Strapi response
                entry_data = result.get("data", result)
                entry_id = entry_data.get("id", 0)
                taxonomy_term_ids[tax_name][term_slug] = entry_id
                total_created += 1
            else:
                warnings.append(
                    f"Failed to create taxonomy term '{term_slug}' "
                    f"for taxonomy '{tax_name}'."
                )

    return taxonomy_term_ids, total_created, warnings


async def migrate_content_entries(
    base_url: str,
    token: str,
    content_items: list[WordPressContentItem],
    content_type_map: ContentTypeMap,
    media_url_map: dict[str, str],
    taxonomy_term_ids: dict[str, dict[str, int]],
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> list[ContentTypeMigrationStats]:
    """Migrate content entries to Strapi in batches.

    Returns per-content-type migration statistics.
    """
    # Group items by post type
    items_by_type: dict[str, list[WordPressContentItem]] = {}
    for item in content_items:
        if item.post_type not in items_by_type:
            items_by_type[item.post_type] = []
        items_by_type[item.post_type].append(item)

    stats_list: list[ContentTypeMigrationStats] = []

    async with httpx.AsyncClient() as client:
        for post_type, items in items_by_type.items():
            # Find the Strapi API ID for this post type
            api_id: str | None = None
            for collection_name, mapped_id in content_type_map.mappings.items():
                if collection_name == post_type or post_type in collection_name:
                    api_id = mapped_id
                    break

            if api_id is None:
                stats_list.append(
                    ContentTypeMigrationStats(
                        content_type=post_type,
                        total=len(items),
                        succeeded=0,
                        failed=0,
                        skipped=len(items),
                        failed_entries=[],
                    )
                )
                continue

            succeeded = 0
            failed = 0
            skipped = 0
            failed_entries: list[str] = []

            # Process in batches
            num_batches = math.ceil(len(items) / batch_size)
            for batch_idx in range(num_batches):
                start = batch_idx * batch_size
                end = min(start + batch_size, len(items))
                batch = items[start:end]

                for item in batch:
                    payload = _build_entry_payload(
                        item, content_type_map, media_url_map, taxonomy_term_ids
                    )
                    result = await _create_entry_with_retry(
                        client, base_url, token, api_id, payload
                    )
                    if result:
                        succeeded += 1
                    else:
                        failed += 1
                        failed_entries.append(item.title)
                        logger.error(
                            "Permanent failure migrating '%s' (post_type=%s)",
                            item.title,
                            item.post_type,
                        )

            stats_list.append(
                ContentTypeMigrationStats(
                    content_type=post_type,
                    total=len(items),
                    succeeded=succeeded,
                    failed=failed,
                    skipped=skipped,
                    failed_entries=failed_entries,
                )
            )

    return stats_list


# ---------------------------------------------------------------------------
# Menu and navigation migration (Requirements 8.1–8.4)
# ---------------------------------------------------------------------------


async def _create_navigation_menu_type(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
) -> None:
    """Create the ``navigation-menu`` Content Type in Strapi if it doesn't exist.

    Fields: name, location, and a nested repeatable component for menu items.
    Menu item component fields: label, url, target, css_classes, and a
    self-referencing child relation.
    """
    headers = {"Authorization": f"Bearer {token}"}

    # First create the menu-item component
    component_payload: dict[str, Any] = {
        "component": {
            "category": "navigation",
            "displayName": "menu-item",
            "attributes": {
                "label": {"type": "string", "required": True},
                "url": {"type": "string", "required": True},
                "target": {"type": "string", "required": False},
                "css_classes": {"type": "string", "required": False},
            },
        },
    }

    resp = await client.post(
        f"{base_url}/content-type-builder/components",
        json=component_payload,
        headers=headers,
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        logger.warning(
            "Menu item component creation returned HTTP %d (may already exist): %s",
            resp.status_code,
            resp.text[:200],
        )

    # Create the navigation-menu content type
    ct_payload: dict[str, Any] = {
        "contentType": {
            "displayName": "Navigation Menu",
            "singularName": "navigation-menu",
            "pluralName": "navigation-menus",
            "attributes": {
                "name": {"type": "string", "required": True},
                "location": {"type": "string", "required": True},
                "items": {
                    "type": "component",
                    "repeatable": True,
                    "component": "navigation.menu-item",
                },
            },
        },
    }

    resp = await client.post(
        f"{base_url}/content-type-builder/content-types",
        json=ct_payload,
        headers=headers,
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        logger.warning(
            "Navigation menu content type creation returned HTTP %d "
            "(may already exist): %s",
            resp.status_code,
            resp.text[:200],
        )


def _build_menu_items(
    raw_items: list[dict[str, Any]],
    route_map: dict[str, str],
    migrated_slugs: set[str],
) -> list[dict[str, Any]]:
    """Build Strapi menu item component data from raw WP menu items.

    Recursively processes child items.
    """
    result: list[dict[str, Any]] = []
    for raw in raw_items:
        url = raw.get("url", "")
        rewritten_url = rewrite_menu_url(url, route_map, migrated_slugs)

        item: dict[str, Any] = {
            "label": raw.get("title", raw.get("label", "")),
            "url": rewritten_url,
            "target": raw.get("target", ""),
            "css_classes": " ".join(raw.get("classes", [])) if isinstance(raw.get("classes"), list) else raw.get("css_classes", ""),
        }

        # Process children recursively
        children = raw.get("children", [])
        if children:
            item["children"] = _build_menu_items(
                children, route_map, migrated_slugs
            )

        result.append(item)
    return result


async def migrate_menus(
    base_url: str,
    token: str,
    menus: list[dict[str, Any]],
    manifest: ModelingManifest,
    migrated_slugs: set[str],
) -> tuple[int, list[str]]:
    """Migrate WordPress menus to Strapi navigation-menu entries.

    Returns ``(entries_created, warnings)``.
    """
    warnings: list[str] = []
    entries_created = 0

    # Build route map from manifest: post_type → route_pattern
    route_map: dict[str, str] = {}
    for collection in manifest.collections:
        route_map[collection.source_post_type] = collection.route_pattern

    async with httpx.AsyncClient() as client:
        # Ensure the navigation-menu content type exists
        await _create_navigation_menu_type(client, base_url, token)

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        for menu in menus:
            menu_name = menu.get("name", "Unnamed Menu")
            menu_location = menu.get("location", "primary")
            raw_items = menu.get("items", [])

            items = _build_menu_items(raw_items, route_map, migrated_slugs)

            payload: dict[str, Any] = {
                "data": {
                    "name": menu_name,
                    "location": menu_location,
                    "items": items,
                },
            }

            try:
                resp = await client.post(
                    f"{base_url}/api/navigation-menus",
                    json=payload,
                    headers=headers,
                    timeout=30,
                )
                if resp.status_code in (200, 201):
                    entries_created += 1
                else:
                    warnings.append(
                        f"Failed to create menu '{menu_name}' "
                        f"(HTTP {resp.status_code}): {resp.text[:200]}"
                    )
            except Exception as exc:
                warnings.append(
                    f"Error creating menu '{menu_name}': {exc}"
                )

    return entries_created, warnings


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------


class ContentMigratorAgent(BaseAgent):
    """Populates Strapi with content, media, taxonomies, and menus.

    Reads ``content_type_map``, ``strapi_base_url``, ``strapi_api_token``,
    ``content_items``, ``modeling_manifest``, and ``export_bundle`` from
    the pipeline context.  Writes ``migration_report`` and ``media_url_map``
    back into the context.
    """

    async def execute(self, context: dict[str, Any]) -> AgentResult:
        """Execute the content migration workflow.

        1. Upload media files to Strapi Media Library (parallel, concurrency=5)
           - Build media_url_map: original WP URL → Strapi Media Library URL
        2. Create taxonomy term entries
        3. Create content entries in batches (default 50):
           a. Map frontmatter fields using content_type_map
           b. Convert block HTML to Strapi rich text
           c. Replace media URLs using media_url_map
           d. Link taxonomy relations
           e. On rate limit/server error: backoff + retry (max 3)
           f. On permanent failure: log and continue
        4. Create navigation menu entries
           - Rewrite internal WP URLs to Astro route patterns
        5. Return migration_report artifact
        """
        start = time.monotonic()
        all_warnings: list[str] = []

        content_type_map = extract_content_type_map(context)
        base_url: str = context["strapi_base_url"]
        api_token: str = context["strapi_api_token"]
        content_items = extract_content_items(context)
        manifest = extract_modeling_manifest(context)
        menus = extract_menus(context)
        media_manifest_entries = extract_media_manifest(context)
        export_bundle: dict[str, Any] = context.get("export_bundle", {})
        ssh_connection_string = context.get("ssh_connection_string")
        cms_config = context.get("cms_config")
        ssh_private_key_path = (
            getattr(cms_config, "ssh_private_key_path", None)
            if cms_config is not None
            else None
        )

        batch_size: int = context.get("batch_size", DEFAULT_BATCH_SIZE)
        media_concurrency: int = context.get(
            "media_concurrency", DEFAULT_MEDIA_CONCURRENCY
        )

        async with strapi_base_url_context(
            base_url, ssh_connection_string, ssh_private_key_path
        ) as resolved_base_url:
            # ------------------------------------------------------------------
            # Phase 1: Upload media files
            # ------------------------------------------------------------------
            media_url_map: dict[str, str] = {}
            media_stats: MediaMigrationStats

            if media_manifest_entries:
                media_url_map, media_stats = await upload_media_files(
                    resolved_base_url,
                    api_token,
                    media_manifest_entries,
                    export_bundle,
                    media_concurrency,
                )
                if media_stats.failed_urls:
                    for url in media_stats.failed_urls:
                        all_warnings.append(f"Media upload failed: {url}")
            else:
                media_stats = MediaMigrationStats(
                    total=0, succeeded=0, failed=0, failed_urls=[]
                )

            # ------------------------------------------------------------------
            # Phase 2: Create taxonomy term entries
            # ------------------------------------------------------------------
            async with httpx.AsyncClient() as client:
                taxonomy_term_ids, taxonomy_count, tax_warnings = (
                    await create_taxonomy_terms(
                        client,
                        resolved_base_url,
                        api_token,
                        content_items,
                        content_type_map,
                    )
                )
            all_warnings.extend(tax_warnings)

            # ------------------------------------------------------------------
            # Phase 3: Create content entries in batches
            # ------------------------------------------------------------------
            content_stats = await migrate_content_entries(
                resolved_base_url,
                api_token,
                content_items,
                content_type_map,
                media_url_map,
                taxonomy_term_ids,
                batch_size,
            )

            # ------------------------------------------------------------------
            # Phase 4: Create navigation menu entries
            # ------------------------------------------------------------------
            migrated_slugs: set[str] = {item.slug for item in content_items}
            menu_entries_created = 0
            if menus:
                menu_entries_created, menu_warnings = await migrate_menus(
                    resolved_base_url,
                    api_token,
                    menus,
                    manifest,
                    migrated_slugs,
                )
                all_warnings.extend(menu_warnings)

        # ------------------------------------------------------------------
        # Phase 5: Build migration report
        # ------------------------------------------------------------------
        total_succeeded = sum(s.succeeded for s in content_stats)
        total_failed = sum(s.failed for s in content_stats)
        total_skipped = sum(s.skipped for s in content_stats)

        migration_report = MigrationReport(
            content_stats=content_stats,
            media_stats=media_stats,
            taxonomy_terms_created=taxonomy_count,
            menu_entries_created=menu_entries_created,
            total_entries_succeeded=total_succeeded,
            total_entries_failed=total_failed,
            total_entries_skipped=total_skipped,
            warnings=all_warnings,
        )

        duration = time.monotonic() - start
        return AgentResult(
            agent_name="content_migrator",
            artifacts={
                "migration_report": migration_report,
                "media_url_map": media_url_map,
            },
            warnings=all_warnings,
            duration_seconds=duration,
        )
