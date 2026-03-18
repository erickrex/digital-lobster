from __future__ import annotations

import re
import time
from typing import Callable
from urllib.parse import urlparse

from src.agents.base import AgentResult
from src.models.inventory import Inventory
from src.models.modeling_manifest import ModelingManifest

from .scaffold_shared import (
    generate_components,
    generate_content_config,
    generate_layouts,
    generate_media_assets,
    generate_theme_assets,
)


def _generate_redirect_page(target: str) -> str:
    """Generate an Astro page that performs a client-side redirect."""
    return f"""---
return Astro.redirect("{target}");
---
"""


def _normalize_path(url_or_path: str) -> str:
    """Normalize a permalink or path to a site-relative route."""
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


def _item_value(item: object, *keys: str) -> str:
    """Read a string field from either a dict or model-like object."""
    for key in keys:
        value = item.get(key) if isinstance(item, dict) else getattr(item, key, None)
        if value:
            return str(value)
    return ""


def _extract_page_routes(
    context: dict,
    manifest: ModelingManifest,
) -> dict[str, dict[str, str]]:
    """Map WordPress page permalinks to collection entries."""
    page_collection = next(
        (collection for collection in manifest.collections if collection.source_post_type == "page"),
        None,
    )
    if page_collection is None:
        return {}

    routes: dict[str, dict[str, str]] = {}
    for item in context.get("content_items", []):
        post_type = _item_value(item, "post_type", "type")
        if post_type != "page":
            continue
        slug = _item_value(item, "slug")
        if not slug:
            continue
        permalink = _item_value(item, "legacy_permalink", "link", "permalink")
        path = _normalize_path(permalink or f"/{slug}/")
        routes[path] = {
            "collection_name": page_collection.collection_name,
            "slug": slug,
        }
    return routes


def _page_route_file(path: str) -> str:
    """Return the concrete Astro file path for a static page route."""
    normalized = path.strip("/")
    if not normalized:
        return "src/pages/index.astro"
    return f"src/pages/{normalized}/index.astro"


def _generate_page_entry_route(
    source_dir: str,
    collection_name: str,
    slug: str,
    layout_import_path_fn: Callable[[str, str], str],
) -> str:
    """Generate a static route page that renders a specific content entry."""
    page_layout_import = layout_import_path_fn(source_dir, "PageLayout.astro")
    return f"""---
import {{ getEntry }} from 'astro:content';
import PageLayout from '{page_layout_import}';

const entry = await getEntry('{collection_name}', '{slug}');
if (!entry) {{
  throw new Error("Missing content entry: {collection_name}/{slug}");
}}

const {{ Content }} = await entry.render();
---
<PageLayout
  title={{entry.data.seo_title || entry.data.title}}
  description={{entry.data.meta_description || entry.data.excerpt || ''}}
  bodyClass={{entry.data.body_class || ''}}
>
  <Content />
</PageLayout>
"""


def _generate_rewrite_index(
    source_dir: str,
    collection_name: str,
    layout_import_path_fn: Callable[[str, str], str],
) -> str:
    """Generate an index page that re-exports a collection's paginated index.

    Uses Astro's ``getStaticPaths`` with ``paginate`` so the alias route
    (e.g. ``/plugins/``) serves the same paginated archive as the canonical
    route (e.g. ``/gd_plugin/``).
    """
    page_layout_import = layout_import_path_fn(source_dir, "PageLayout.astro")
    # We import getCollection and re-paginate — this keeps the alias fully
    # functional with its own pagination URLs under the alias prefix.
    return f"""---
import {{ getCollection }} from 'astro:content';
import PageLayout from '{page_layout_import}';

export async function getStaticPaths({{ paginate }}) {{
  const allEntries = (await getCollection('{collection_name}'))
    .sort((a, b) => new Date(b.data.date).valueOf() - new Date(a.data.date).valueOf());
  return paginate(allEntries, {{ pageSize: 12 }});
}}

const {{ page }} = Astro.props;
---
<PageLayout title="{collection_name.replace('_', ' ').title()}">
  <div class="archive-header">
    <h1>{collection_name.replace('_', ' ').title()}</h1>
    <p class="archive-count">{{page.total}} items</p>
  </div>

  <div class="card-grid">
    {{page.data.map((entry) => (
      <article class="card">
        <a href={{`/{source_dir}/${{entry.slug}}`}} class="card-link">
          <div class="card-body">
            <h2 class="card-title">{{entry.data.title}}</h2>
          </div>
        </a>
      </article>
    ))}}
  </div>

  <nav class="pagination" aria-label="Pagination">
    {{page.url.prev && <a href={{page.url.prev}} class="pagination-link">&larr; Previous</a>}}
    <span class="pagination-info">Page {{page.currentPage}} of {{page.lastPage}}</span>
    {{page.url.next && <a href={{page.url.next}} class="pagination-link">Next &rarr;</a>}}
  </nav>
</PageLayout>
"""


def _generate_rewrite_slug(
    source_dir: str,
    collection_name: str,
    layout_import_path_fn: Callable[[str, str], str],
) -> str:
    """Generate a ``[slug].astro`` page that mirrors a collection under an alias route."""
    post_layout_import = layout_import_path_fn(source_dir, "PostLayout.astro")
    return f"""---
import {{ getCollection }} from 'astro:content';
import PostLayout from '{post_layout_import}';

export async function getStaticPaths() {{
  const entries = await getCollection('{collection_name}');
  return entries.map((entry) => ({{
    params: {{ slug: entry.slug }},
    props: {{ entry }},
  }}));
}}

const {{ entry }} = Astro.props;
const {{ Content }} = await entry.render();
---
<PostLayout
  title={{entry.data.seo_title || entry.data.title}}
  description={{entry.data.meta_description || entry.data.excerpt || ''}}
  bodyClass={{entry.data.body_class || ''}}
>
  <Content />
</PostLayout>
"""


def _extract_nav_links(theme_layouts: dict[str, str]) -> set[str]:
    """Extract internal link paths from the BaseLayout's navigation HTML."""
    base_layout = theme_layouts.get("BaseLayout.astro", "")
    if not base_layout:
        return set()
    # Find all href="/some-path/" links (internal, starting with /)
    paths: set[str] = set()
    for match in re.finditer(r'href=["\'](/[a-zA-Z0-9_-]+/?)["\']', base_layout):
        path = match.group(1).strip("/")
        if path:
            paths.add(path)
    return paths


def _humanize_for_route(collection_name: str) -> str:
    """Derive a likely WordPress permalink slug from a collection name.

    Strips common CPT prefixes (gd_, wp_, ct_, etc.) and returns the
    lowercase remainder — e.g. ``gd_plugin`` → ``plugin``.
    """
    cleaned = re.sub(r"^(gd|wp|ct|cpt|wc|edd|tribe|jet|acf)_", "", collection_name)
    return cleaned.lower().replace("_", "-")

def build_static_project(
    context: dict,
    inventory: Inventory,
    manifest: ModelingManifest,
    theme_layouts: dict[str, str],
    *,
    generate_astro_config: Callable[[str], str],
    generate_package_json: Callable[[str], str],
    generate_tsconfig: Callable[[], str],
    generate_home_page: Callable[[str, list], str],
    generate_route_page: Callable[..., str],
    generate_index_page: Callable[..., str],
    generate_component: Callable[[object], str],
    generate_base_layout_with_seo: Callable[[str, dict[str, str]], str],
    generate_readme: Callable[[str, str], str],
    package_as_zip: Callable[[dict[str, str | bytes]], bytes],
    default_page_layout: Callable[[str], str],
    default_post_layout: Callable[[str], str],
    layout_import_path: Callable[[str, str], str],
    route_dir: Callable[[str], str],
) -> AgentResult:
    start = time.monotonic()
    warnings: list[str] = []
    project: dict[str, str | bytes] = {}

    project["astro.config.mjs"] = generate_astro_config(inventory.site_url)
    project["package.json"] = generate_package_json(inventory.site_name)
    project["tsconfig.json"] = generate_tsconfig()

    generate_layouts(
        project,
        inventory,
        theme_layouts,
        base_layout_generator=generate_base_layout_with_seo,
        default_page_layout_generator=default_page_layout,
        default_post_layout_generator=default_post_layout,
    )
    generate_theme_assets(project, context)
    generate_media_assets(project, context, warnings)

    page_routes = _extract_page_routes(context, manifest)
    blocked_archive_dirs = {
        path.strip("/")
        for path in page_routes
        if path.strip("/")
    }

    if "/" in page_routes:
        front_page = page_routes["/"]
        project["src/pages/index.astro"] = _generate_page_entry_route(
            "",
            front_page["collection_name"],
            front_page["slug"],
            layout_import_path,
        )
    else:
        project["src/pages/index.astro"] = generate_home_page(
            inventory.site_name, manifest.collections
        )

    for path, route in page_routes.items():
        if path == "/":
            continue
        route_dir_path = path.strip("/")
        project[_page_route_file(path)] = _generate_page_entry_route(
            route_dir_path,
            route["collection_name"],
            route["slug"],
            layout_import_path,
        )

    for collection in manifest.collections:
        current_route_dir = route_dir(collection.route_pattern)
        base = f"src/pages/{current_route_dir}" if current_route_dir else "src/pages"
        page_layout_import = layout_import_path(current_route_dir, "PageLayout.astro")
        post_layout_import = layout_import_path(current_route_dir, "PostLayout.astro")
        project[f"{base}/[slug].astro"] = generate_route_page(
            collection,
            layout_import_path=(
                page_layout_import
                if collection.source_post_type == "page"
                else post_layout_import
            ),
        )
        if current_route_dir:
            if current_route_dir in blocked_archive_dirs:
                warnings.append(
                    "Skipped generating collection index for route "
                    f"'{current_route_dir}' because a WordPress page already owns that path."
                )
            else:
                project[f"{base}/[...page].astro"] = generate_index_page(
                    collection,
                    layout_import_path=page_layout_import,
                )
        else:
            warnings.append(
                "Skipped generating collection index for root route "
                f"pattern '{collection.route_pattern}' to preserve home page."
            )

    generate_components(
        project,
        manifest,
        component_generator=generate_component,
    )

    # --- Route aliases: mirror collections under WordPress permalink paths ---
    # The nav may link to /plugins/ but the collection lives at /gd_plugin/.
    # Detect these mismatches and generate alias pages so both routes work.
    nav_paths = _extract_nav_links(theme_layouts)
    collection_dirs = {route_dir(c.route_pattern) for c in manifest.collections if route_dir(c.route_pattern)}

    for collection in manifest.collections:
        coll_dir = route_dir(collection.route_pattern)
        if not coll_dir:
            continue
        # Check if any nav link matches a humanized version of this collection
        # e.g. nav has "plugins" and collection dir is "gd_plugin"
        humanized = _humanize_for_route(collection.collection_name)
        for nav_path in nav_paths:
            # Skip if nav_path already matches an existing collection dir
            if nav_path in collection_dirs:
                continue
            if nav_path in blocked_archive_dirs:
                continue
            # Match: nav path is the humanized plural of the collection name
            if nav_path == humanized or nav_path == humanized + "s":
                alias_dir = f"src/pages/{nav_path}"
                project[f"{alias_dir}/[...page].astro"] = _generate_rewrite_index(
                    nav_path, collection.collection_name, layout_import_path,
                )
                project[f"{alias_dir}/[slug].astro"] = _generate_rewrite_slug(
                    nav_path, collection.collection_name, layout_import_path,
                )
                # Track so we don't double-generate
                collection_dirs.add(nav_path)

    project["src/content/config.ts"] = generate_content_config(manifest)
    project["public/.gitkeep"] = ""
    project["README.md"] = generate_readme(inventory.site_name, inventory.site_url)
    project_zip = package_as_zip(project)

    return AgentResult(
        agent_name="scaffold",
        artifacts={
            "astro_project": project,
            "astro_project_zip": project_zip,
        },
        warnings=warnings,
        duration_seconds=time.monotonic() - start,
    )
