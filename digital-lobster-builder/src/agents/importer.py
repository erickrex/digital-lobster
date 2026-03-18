import logging
import re
import time
from posixpath import basename as url_basename
from typing import Any
from urllib.parse import urlparse

from src.agents.base import AgentResult, BaseAgent
from src.agents.scaffold import package_as_zip
from src.agents.theming import rewrite_site_urls
from src.models.content import SerializedContent, WordPressContentItem
from src.models.modeling_manifest import (
    ComponentMapping,
    ContentCollectionSchema,
    ModelingManifest,
)
from src.pipeline_context import (
    MediaManifestEntry,
    extract_media_manifest as shared_extract_media_manifest,
)
from src.serialization.frontmatter import serialize_frontmatter
from src.serialization.markdown import blocks_to_markdown
from src.serialization.mdx import blocks_to_mdx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Context extraction helpers
# ---------------------------------------------------------------------------

def _extract_modeling_manifest(context: dict[str, Any]) -> ModelingManifest:
    """Extract ModelingManifest from pipeline context."""
    raw = context.get("modeling_manifest")
    if raw is None:
        raise ValueError("Missing 'modeling_manifest' in context")
    if isinstance(raw, ModelingManifest):
        return raw
    return ModelingManifest(**raw)

def _extract_content_items(context: dict[str, Any]) -> list[dict]:
    """Extract raw content item dicts from pipeline context."""
    return context.get("content_items", [])

def _extract_menus(context: dict[str, Any]) -> list[dict]:
    """Extract menu definitions from pipeline context."""
    return context.get("menus", [])

def _extract_redirect_rules(context: dict[str, Any]) -> list[dict]:
    """Extract redirect rules from pipeline context."""
    return context.get("redirect_rules", [])

def _extract_media_manifest(context: dict[str, Any]) -> list[MediaManifestEntry]:
    """Extract normalized media manifest entries from pipeline context."""
    return shared_extract_media_manifest(context)

def _extract_html_snapshots(context: dict[str, Any]) -> dict[str, str]:
    """Extract normalized HTML snapshots keyed by URL path."""
    raw = context.get("html_snapshots", {})
    if isinstance(raw, dict):
        return {
            str(key): value
            for key, value in raw.items()
            if isinstance(value, str)
        }
    return {}

def _extract_astro_project(context: dict[str, Any]) -> dict[str, str | bytes]:
    """Extract the current Astro project scaffold from context."""
    raw = context.get("astro_project", {})
    if isinstance(raw, dict):
        return dict(raw)
    return {}

# ---------------------------------------------------------------------------
# Schema / collection helpers
# ---------------------------------------------------------------------------

def _find_collection_schema(
    manifest: ModelingManifest, post_type: str
) -> ContentCollectionSchema | None:
    """Find the ContentCollectionSchema matching a WordPress post_type."""
    for schema in manifest.collections:
        if schema.source_post_type == post_type:
            return schema
    return None

def _has_component_mappings(manifest: ModelingManifest) -> bool:
    """Return True if the manifest has any non-fallback component mappings."""
    return any(not m.fallback for m in manifest.components)

# ---------------------------------------------------------------------------
# Frontmatter building
# ---------------------------------------------------------------------------

def build_frontmatter(
    item: WordPressContentItem,
    schema: ContentCollectionSchema,
) -> dict:
    """Build a frontmatter dict from a content item and its collection schema.

    Includes all required schema fields that can be sourced from the content
    item, plus SEO fields and legacy_url.
    """
    # Map of schema field names to content item sources
    field_sources: dict[str, Any] = {
        "title": item.title,
        "slug": item.slug,
        "date": item.date,
        "status": item.status,
        "excerpt": item.excerpt or "",
        "post_type": item.post_type,
    }

    # Add taxonomy fields
    for tax_name, terms in item.taxonomies.items():
        field_sources[tax_name] = terms

    # Add meta fields
    for meta_key, meta_val in item.meta.items():
        field_sources[meta_key] = meta_val

    # Add featured media
    if item.featured_media:
        field_sources["featured_image"] = item.featured_media.get("url", "")

    fm: dict[str, Any] = {}

    # Populate from schema fields
    for field_def in schema.frontmatter_fields:
        name = field_def.name
        if name in field_sources:
            fm[name] = field_sources[name]

    # Always ensure core fields are present
    fm.setdefault("title", item.title)
    fm.setdefault("slug", item.slug)
    fm.setdefault("date", item.date)

    # SEO metadata
    if item.seo:
        seo_title = item.seo.get("title", "")
        meta_desc = item.seo.get("description", "") or item.seo.get(
            "metadesc", ""
        )
        if seo_title:
            fm["seo_title"] = seo_title
        if meta_desc:
            fm["meta_description"] = meta_desc

    # Legacy URL for redirect generation
    if item.legacy_permalink:
        fm["legacy_url"] = item.legacy_permalink

    return fm

# ---------------------------------------------------------------------------
# Media URL scanning and rewriting
# ---------------------------------------------------------------------------

_MEDIA_URL_RE = re.compile(
    r'https?://[^\s"\'<>]+\.(?:jpg|jpeg|png|gif|svg|webp|mp4|mp3|pdf|ico)',
    re.IGNORECASE,
)
_BODY_CLASS_RE = re.compile(
    r'<body\b[^>]*class=(["\'])(.*?)\1',
    re.IGNORECASE | re.DOTALL,
)
_SNAPSHOT_CONTENT_PATTERNS = (
    re.compile(
        r'<(?:section|div)\b[^>]*class=(["\']).*?\bentry-content\b.*?\1[^>]*>(.*?)</(?:section|div)>',
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(r"<main\b[^>]*>(.*?)</main>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<article\b[^>]*>(.*?)</article>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<body\b[^>]*>(.*?)</body>", re.IGNORECASE | re.DOTALL),
)

def scan_media_urls(
    content_items: list[WordPressContentItem],
    html_snapshots: dict[str, str] | None = None,
) -> dict[str, str]:
    """Scan all content items for media URLs and build a media map.

    Returns a dict mapping original WordPress media URLs to local
    ``/media/{path}`` URLs.
    """
    media_map: dict[str, str] = {}

    def _record_urls(html: str) -> None:
        for url in _MEDIA_URL_RE.findall(html):
            if url not in media_map:
                filename = _safe_filename(url)
                media_map[url] = f"/media/{filename}"

    for item in content_items:
        # Scan blocks
        for block in item.blocks:
            _record_urls(block.html)
        # Scan raw_html
        _record_urls(item.raw_html)
        # Featured media
        if item.featured_media:
            fm_url = item.featured_media.get("url", "")
            if fm_url and fm_url not in media_map:
                filename = _safe_filename(fm_url)
                media_map[fm_url] = f"/media/{filename}"
    for snapshot_html in (html_snapshots or {}).values():
        _record_urls(snapshot_html)
    return media_map

def build_media_map(
    content_items: list[WordPressContentItem],
    media_manifest: list[MediaManifestEntry],
    html_snapshots: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build a media map only for assets present in the normalized bundle manifest."""
    if not media_manifest:
        return {}

    referenced_urls = set(scan_media_urls(content_items, html_snapshots).keys())
    media_map: dict[str, str] = {}
    for entry in media_manifest:
        if entry.source_url in referenced_urls:
            media_map[entry.source_url] = entry.public_url
    return media_map

def _safe_filename(url: str) -> str:
    """Extract a safe filename from a URL."""
    parsed = urlparse(url)
    name = url_basename(parsed.path)
    if not name:
        name = "media_file"
    # Remove query params that might be in the basename
    name = name.split("?")[0]
    return name

def rewrite_media_urls(body: str, media_map: dict[str, str]) -> str:
    """Replace all WordPress media URLs in body with local paths."""
    for wp_url, local_path in media_map.items():
        body = body.replace(wp_url, local_path)
    return body


def _normalize_route_path(url_or_path: str) -> str:
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


def _extract_snapshot_body(snapshot_html: str) -> str:
    """Extract the main content region from an HTML snapshot."""
    if not snapshot_html:
        return ""
    for pattern in _SNAPSHOT_CONTENT_PATTERNS:
        match = pattern.search(snapshot_html)
        if match:
            body = match.group(match.lastindex or 1).strip()
            if body:
                return body
    return ""


def _extract_body_class(snapshot_html: str) -> str:
    """Extract the ``class`` attribute value from the snapshot body."""
    if not snapshot_html:
        return ""
    match = _BODY_CLASS_RE.search(snapshot_html)
    if not match:
        return ""
    return " ".join(match.group(2).split())


def _snapshot_for_item(
    item: WordPressContentItem,
    html_snapshots: dict[str, str],
) -> str:
    """Find the HTML snapshot that corresponds to a content item."""
    if not html_snapshots:
        return ""
    candidates = [
        _normalize_route_path(item.legacy_permalink),
        f"/{item.slug}",
        f"/{item.slug}/",
    ]
    for candidate in candidates:
        snapshot = html_snapshots.get(_normalize_route_path(candidate))
        if snapshot:
            return snapshot
    return ""

# ---------------------------------------------------------------------------
# Navigation JSON generation
# ---------------------------------------------------------------------------

def generate_navigation(
    menus: list[dict], site_url: str = ""
) -> dict[str, Any]:
    """Convert WordPress menu definitions to a navigation JSON structure.

    Each menu dict is expected to have:
    - ``name``: menu name
    - ``location``: theme location
    - ``items``: list of menu item dicts with ``title``, ``url``, and
      optional ``children``

    URLs are rewritten from WordPress paths to Astro routes by stripping
    the site_url prefix.
    """
    nav: dict[str, Any] = {"menus": []}
    for menu in menus:
        menu_entry: dict[str, Any] = {
            "name": menu.get("name", ""),
            "location": menu.get("location", ""),
            "items": _rewrite_menu_items(menu.get("items", []), site_url),
        }
        nav["menus"].append(menu_entry)
    return nav

def _rewrite_menu_items(items: list[dict], site_url: str) -> list[dict]:
    """Recursively rewrite menu item URLs and process children."""
    result: list[dict] = []
    for item in items:
        entry: dict[str, Any] = {
            "label": item.get("title", ""),
            "url": _rewrite_url(item.get("url", ""), site_url),
        }
        children = item.get("children", [])
        if children:
            entry["children"] = _rewrite_menu_items(children, site_url)
        result.append(entry)
    return result

def _rewrite_url(url: str, site_url: str) -> str:
    """Rewrite a WordPress URL to an Astro route.

    Strips the site_url prefix so ``https://example.com/blog/hello``
    becomes ``/blog/hello``.
    """
    if not url:
        return "/"
    if site_url and url.startswith(site_url):
        path = url[len(site_url):]
        if not path.startswith("/"):
            path = "/" + path
        return path
    # If it's already a relative path or external, leave it
    parsed = urlparse(url)
    if not parsed.scheme:
        return url
    # External URL — keep as-is
    if site_url:
        site_parsed = urlparse(site_url)
        if parsed.netloc and parsed.netloc != site_parsed.netloc:
            return url
    return parsed.path or "/"

# ---------------------------------------------------------------------------
# Redirect generation
# ---------------------------------------------------------------------------

def generate_redirects(
    content_items: list[WordPressContentItem],
    manifest: ModelingManifest,
    redirect_rules: list[dict],
) -> list[dict[str, Any]]:
    """Generate redirect configuration from legacy permalinks and plugin rules.

    Returns a list of redirect entries, each with ``source``, ``destination``,
    and ``status`` (HTTP status code).
    """
    redirects: list[dict[str, Any]] = []

    # 1. Legacy permalink → new Astro route for each content item
    for item in content_items:
        if not item.legacy_permalink:
            continue
        schema = _find_collection_schema(manifest, item.post_type)
        if schema is None:
            continue
        new_route = _build_astro_route(schema, item.slug)
        legacy = item.legacy_permalink
        # Only add if the paths differ
        legacy_path = _normalize_route_path(legacy)
        new_route_path = _normalize_route_path(new_route)
        if legacy_path != "/" and legacy_path != new_route_path:
            redirects.append({
                "source": legacy_path,
                "destination": new_route_path,
                "status": 301,
            })

    # 2. Redirection plugin rules
    for rule in redirect_rules:
        redirects.append({
            "source": rule.get("source", rule.get("source_url", "")),
            "destination": rule.get("destination", rule.get("target_url", "")),
            "status": rule.get("status", rule.get("status_code", 301)),
        })

    return redirects

def _build_astro_route(schema: ContentCollectionSchema, slug: str) -> str:
    """Build the Astro route path from a collection schema and slug."""
    pattern = schema.route_pattern
    return pattern.replace("[slug]", slug)

# ---------------------------------------------------------------------------
# Content conversion
# ---------------------------------------------------------------------------

def convert_content_item(
    item: WordPressContentItem,
    manifest: ModelingManifest,
    media_map: dict[str, str],
    warnings: list[str],
    *,
    html_snapshots: dict[str, str] | None = None,
    site_url: str = "",
) -> SerializedContent | None:
    """Convert a single WordPress content item to a SerializedContent object.

    Returns None if the item's post_type has no matching collection schema.
    """
    schema = _find_collection_schema(manifest, item.post_type)
    if schema is None:
        warnings.append(
            f"No collection schema for post_type '{item.post_type}', "
            f"skipping item '{item.slug}'"
        )
        return None

    # Build frontmatter
    fm = build_frontmatter(item, schema)

    # Convert blocks to body content
    use_mdx = _has_component_mappings(manifest)
    snapshot_html = _snapshot_for_item(item, html_snapshots or {})
    body_class = ""

    if item.post_type == "page" and snapshot_html:
        body = _extract_snapshot_body(snapshot_html) or item.raw_html
        body = rewrite_site_urls(body, site_url, media_map=media_map)
        body = rewrite_media_urls(body, media_map)
        body_class = _extract_body_class(snapshot_html)
        ext = "mdx"
    else:
        if use_mdx:
            body = blocks_to_mdx(item.blocks, manifest.components)
            ext = "mdx"
        else:
            body = blocks_to_markdown(item.blocks)
            ext = "md"

    # Check for unsupported blocks and log warnings
    known_block_types = {m.wp_block_type for m in manifest.components}
    for block in item.blocks:
        if block.name not in known_block_types and not block.name.startswith("core/"):
            warnings.append(
                f"Unsupported block type '{block.name}' in content "
                f"item '{item.slug}' — converted to raw HTML fallback"
            )

    # Rewrite media URLs in body
    body = rewrite_media_urls(body, media_map)

    # Rewrite media URLs in frontmatter (featured image)
    if "featured_image" in fm and fm["featured_image"] in media_map:
        fm["featured_image"] = media_map[fm["featured_image"]]
    if body_class:
        fm["body_class"] = body_class

    return SerializedContent(
        collection=schema.collection_name,
        slug=item.slug,
        frontmatter=fm,
        body=body,
        file_extension=ext,
    )

# ---------------------------------------------------------------------------
# ImporterAgent
# ---------------------------------------------------------------------------

class ImporterAgent(BaseAgent):
    """Agent 5: converts WordPress content to Astro content collection entries."""
    async def execute(self, context: dict[str, Any]) -> AgentResult:
        """Execute the Importer agent.

        Args:
            context: Must contain ``modeling_manifest`` and ``content_items``.
                May contain ``menus``, ``redirect_rules``, ``inventory``.

        Returns:
            AgentResult with artifacts:
            - ``content_files``: dict mapping file paths → content strings
            - ``media_map``: dict mapping WP media URLs → local paths
            - ``navigation``: navigation JSON structure
            - ``redirects``: list of redirect rules
        """
        start = time.monotonic()
        warnings: list[str] = []

        manifest = _extract_modeling_manifest(context)
        raw_items = _extract_content_items(context)
        menus = _extract_menus(context)
        redirect_rules = _extract_redirect_rules(context)
        media_manifest = _extract_media_manifest(context)
        html_snapshots = _extract_html_snapshots(context)

        # Parse content items, skipping malformed ones
        content_items: list[WordPressContentItem] = []
        for i, raw in enumerate(raw_items):
            try:
                if isinstance(raw, WordPressContentItem):
                    content_items.append(raw)
                else:
                    content_items.append(WordPressContentItem(**raw))
            except Exception as exc:
                warnings.append(
                    f"Malformed content item at index {i}: {exc} — skipped"
                )
                logger.error("Malformed content item at index %d: %s", i, exc)

        # Generate media map
        site_url = ""
        inv = context.get("inventory")
        if inv is not None:
            if hasattr(inv, "site_url"):
                site_url = inv.site_url
            elif isinstance(inv, dict):
                site_url = inv.get("site_url", "")

        media_map = build_media_map(content_items, media_manifest, html_snapshots)

        # Convert each content item
        content_files: dict[str, str] = {}
        for item in content_items:
            try:
                serialized = convert_content_item(
                    item,
                    manifest,
                    media_map,
                    warnings,
                    html_snapshots=html_snapshots,
                    site_url=site_url,
                )
                if serialized is not None:
                    file_path = (
                        f"src/content/{serialized.collection}/"
                        f"{serialized.slug}.{serialized.file_extension}"
                    )
                    content_files[file_path] = serialized.to_file_content()
            except Exception as exc:
                warnings.append(
                    f"Error converting content item '{item.slug}': {exc} — skipped"
                )
                logger.error(
                    "Error converting content item '%s': %s", item.slug, exc
                )

        # Generate navigation JSON
        navigation = generate_navigation(menus, site_url)

        # Generate redirects
        redirects = generate_redirects(content_items, manifest, redirect_rules)

        artifacts: dict[str, Any] = {
            "content_files": content_files,
            "media_map": media_map,
            "navigation": navigation,
            "redirects": redirects,
        }

        astro_project = _extract_astro_project(context)
        if astro_project:
            astro_project.update(content_files)
            artifacts["astro_project"] = astro_project
            artifacts["astro_project_zip"] = package_as_zip(astro_project)

        return AgentResult(
            agent_name="importer",
            artifacts=artifacts,
            warnings=warnings,
            duration_seconds=time.monotonic() - start,
        )
