from __future__ import annotations

import io
import json
import logging
import re
import time
import zipfile
from pathlib import PurePosixPath
from typing import Any

from src.agents.base import AgentResult, BaseAgent
from src.agents.scaffold_cms import build_cms_project
from src.agents.scaffold_shared import generate_content_config
from src.agents.scaffold_static import build_static_project
from src.models.inventory import Inventory
from src.models.modeling_manifest import (
    ComponentMapping,
    ContentCollectionSchema,
    ModelingManifest,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Context extraction helpers
# ---------------------------------------------------------------------------

def _extract_inventory(context: dict[str, Any]) -> Inventory:
    raw = context.get("inventory")
    if raw is None:
        raise KeyError("'inventory' missing from pipeline context")
    if isinstance(raw, Inventory):
        return raw
    return Inventory.model_validate(raw)

def _extract_modeling_manifest(context: dict[str, Any]) -> ModelingManifest:
    raw = context.get("modeling_manifest")
    if raw is None:
        raise KeyError("'modeling_manifest' missing from pipeline context")
    if isinstance(raw, ModelingManifest):
        return raw
    return ModelingManifest.model_validate(raw)

def _extract_theme_layouts(context: dict[str, Any]) -> dict[str, str]:
    """Extract theme layouts from the pipeline context."""
    layouts = context.get("layouts", {})
    if not layouts:
        # Also check under theme_layouts key
        layouts = context.get("theme_layouts", {})
    return layouts

# ---------------------------------------------------------------------------
# File generation helpers
# ---------------------------------------------------------------------------

def generate_astro_config(site_url: str) -> str:
    """Generate ``astro.config.mjs`` with static output and MDX integration.

    Used for static (non-CMS) mode.
    """
    return f"""import {{ defineConfig }} from 'astro/config';
import mdx from '@astrojs/mdx';

export default defineConfig({{
  output: 'static',
  site: '{site_url}',
  integrations: [mdx()],
}});
"""
def generate_package_json(site_name: str) -> str:
    """Generate ``package.json`` with Astro 5.x and required integrations."""
    pkg = {
        "name": _slugify(site_name),
        "type": "module",
        "version": "0.0.1",
        "scripts": {
            "dev": "astro dev",
            "start": "astro dev",
            "build": "astro build",
            "preview": "astro preview",
            "astro": "astro",
        },
        "dependencies": {
            "astro": "^5.0.0",
            "@astrojs/mdx": "^4.0.0",
        },
        "devDependencies": {
            "typescript": "^5.0.0",
        },
    }
    return json.dumps(pkg, indent=2) + "\n"

def generate_tsconfig() -> str:
    """Generate ``tsconfig.json`` extending Astro's strict config."""
    cfg = {"extends": "astro/tsconfigs/strict"}
    return json.dumps(cfg, indent=2) + "\n"

def generate_route_page(
    collection: ContentCollectionSchema,
    layout_import_path: str = "../../layouts/PostLayout.astro",
) -> str:
    """Generate a dynamic route page ``[slug].astro`` for a content collection."""
    is_page_collection = collection.source_post_type == "page"
    has_featured = any(f.name == "featured_image" for f in collection.frontmatter_fields)
    has_date = any(f.name == "date" for f in collection.frontmatter_fields)
    layout_name = "PageLayout" if is_page_collection else "PostLayout"
    description_expr = "entry.data.meta_description || entry.data.excerpt || ''"

    image_block = ""
    if has_featured and not is_page_collection:
        image_block = """
  {entry.data.featured_image && (
    <div class="entry-featured-image">
      <img src={entry.data.featured_image} alt={entry.data.title} />
    </div>
  )}"""

    date_block = ""
    if has_date and not is_page_collection:
        date_block = """
      {entry.data.date && (
        <time class="entry-date" datetime={entry.data.date}>
          {new Date(entry.data.date).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}
        </time>
      )}"""

    page_body = """  <Content />"""
    if not is_page_collection:
        page_body = f"""  <article class="single-entry">{image_block}
    <header class="entry-header">
      <h1>{{entry.data.title}}</h1>{date_block}
    </header>
    <div class="entry-body">
      <Content />
    </div>
  </article>"""

    page_styles = ""
    if not is_page_collection:
        page_styles = """

<style>
  .single-entry {
    max-width: 800px;
    margin: 0 auto;
  }
  .entry-featured-image {
    margin-bottom: 1.5rem;
    border-radius: .5rem;
    overflow: hidden;
  }
  .entry-featured-image img {
    width: 100%;
    height: auto;
    display: block;
  }
  .entry-header {
    margin-bottom: 1.5rem;
  }
  .entry-header h1 {
    margin: 0 0 .5rem;
  }
  .entry-date {
    display: block;
    font-size: .9rem;
    color: var(--global-palette5, #888);
  }
</style>
"""

    return f"""---
import {{ getCollection }} from 'astro:content';
import {layout_name} from '{layout_import_path}';

export async function getStaticPaths() {{
  const entries = await getCollection('{collection.collection_name}');
  return entries.map((entry) => ({{
    params: {{ slug: entry.slug }},
    props: {{ entry }},
  }}));
}}

const {{ entry }} = Astro.props;
const {{ Content }} = await entry.render();
---
<{layout_name}
  title={{entry.data.seo_title || entry.data.title}}
  description={{{description_expr}}}
  bodyClass={{entry.data.body_class || ''}}
>
{page_body}
</{layout_name}>{page_styles}
"""
def generate_index_page(
    collection: ContentCollectionSchema,
    layout_import_path: str = "../../layouts/PageLayout.astro",
) -> str:
    """Generate a paginated index page with card layout for a content collection."""
    label = _humanize_collection_name(collection.collection_name)
    route_prefix = _friendly_route_prefix(collection)
    has_excerpt = any(f.name == "excerpt" for f in collection.frontmatter_fields)
    has_featured = any(f.name == "featured_image" for f in collection.frontmatter_fields)
    has_date = any(f.name == "date" for f in collection.frontmatter_fields)

    # Build optional card parts
    image_block = ""
    if has_featured:
        image_block = """
              {entry.data.featured_image && (
                <div class="card-image">
                  <img src={entry.data.featured_image} alt={entry.data.title} loading="lazy" />
                </div>
              )}"""

    date_block = ""
    if has_date:
        date_block = """
                {entry.data.date && (
                  <time class="card-date" datetime={entry.data.date}>
                    {new Date(entry.data.date).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}
                  </time>
                )}"""

    excerpt_block = ""
    if has_excerpt:
        excerpt_block = """
                {entry.data.excerpt && <p class="card-excerpt">{entry.data.excerpt}</p>}"""

    return f"""---
import {{ getCollection }} from 'astro:content';
import PageLayout from '{layout_import_path}';

export async function getStaticPaths({{ paginate }}) {{
  const allEntries = (await getCollection('{collection.collection_name}'))
    .sort((a, b) => new Date(b.data.date).valueOf() - new Date(a.data.date).valueOf());
  return paginate(allEntries, {{ pageSize: 12 }});
}}

const {{ page }} = Astro.props;
---
<PageLayout title="{label}">
  <div class="archive-header">
    <h1>{label}</h1>
    <p class="archive-count">{{page.total}} items</p>
  </div>

  <div class="card-grid">
    {{page.data.map((entry) => (
      <article class="card">
        <a href={{`{route_prefix}/${{entry.slug}}`}} class="card-link">{image_block}
          <div class="card-body">
            <h2 class="card-title">{{entry.data.title}}</h2>{date_block}{excerpt_block}
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

<style>
  .archive-header {{
    margin-bottom: 2rem;
  }}
  .archive-header h1 {{
    margin: 0 0 .25rem;
  }}
  .archive-count {{
    color: var(--global-palette5, #666);
    margin: 0;
  }}
  .card-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 1.5rem;
    margin-bottom: 2rem;
  }}
  .card {{
    border: 1px solid var(--global-gray-400, #e0e0e0);
    border-radius: .5rem;
    overflow: hidden;
    transition: box-shadow .2s, transform .2s;
    background: var(--global-palette9, #fff);
  }}
  .card:hover {{
    box-shadow: 0 4px 16px rgba(0,0,0,.1);
    transform: translateY(-2px);
  }}
  .card-link {{
    display: block;
    text-decoration: none;
    color: inherit;
  }}
  .card-image {{
    aspect-ratio: 16/9;
    overflow: hidden;
    background: var(--global-gray-200, #f0f0f0);
  }}
  .card-image img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
  }}
  .card-body {{
    padding: 1rem;
  }}
  .card-title {{
    font-size: 1.1rem;
    margin: 0 0 .5rem;
    line-height: 1.3;
  }}
  .card-date {{
    display: block;
    font-size: .8rem;
    color: var(--global-palette5, #888);
    margin-bottom: .5rem;
  }}
  .card-excerpt {{
    font-size: .9rem;
    color: var(--global-palette5, #666);
    margin: 0;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }}
  .pagination {{
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 1rem;
    padding: 2rem 0;
  }}
  .pagination-link {{
    padding: .5rem 1rem;
    border: 1px solid var(--global-palette-btn-bg, var(--global-palette1, #0073aa));
    border-radius: .25rem;
    text-decoration: none;
    color: var(--global-palette-btn-bg, var(--global-palette1, #0073aa));
    transition: background .2s, color .2s;
  }}
  .pagination-link:hover {{
    background: var(--global-palette-btn-bg, var(--global-palette1, #0073aa));
    color: #fff;
  }}
  .pagination-info {{
    color: var(--global-palette5, #666);
    font-size: .9rem;
  }}
</style>
"""
def generate_home_page(site_name: str, collections: list[ContentCollectionSchema]) -> str:
    """Generate the home ``index.astro`` page.

    Adapts to whatever collections exist in the manifest:
    - If a blog-like collection exists (posts, articles, news, blog), show
      recent entries in a featured section with cards.
    - All other non-page collections get an explore/browse section with
      preview cards showing the first few items.
    - Sites with only a ``pages`` collection get a simple welcome page.
    """
    _BLOG_NAMES = {"posts", "post", "articles", "article", "news", "blog"}

    blog_coll = None
    browse_colls: list[ContentCollectionSchema] = []
    for c in collections:
        if c.collection_name.lower() in _BLOG_NAMES and blog_coll is None:
            blog_coll = c
        elif c.collection_name.lower() not in ("pages", "page"):
            browse_colls.append(c)

    # --- Blog / recent-posts section (only when a blog collection exists) ---
    posts_section = ""
    posts_import = ""
    if blog_coll:
        coll_name = blog_coll.collection_name
        blog_route = _friendly_route_prefix(blog_coll)
        label = coll_name.replace("_", " ").title()
        has_featured = any(f.name == "featured_image" for f in blog_coll.frontmatter_fields)

        image_block = ""
        if has_featured:
            image_block = """
              {entry.data.featured_image && (
                <div class="post-card-image">
                  <img src={entry.data.featured_image} alt={entry.data.title} loading="lazy" />
                </div>
              )}"""

        posts_import = f"""
import {{ getCollection }} from 'astro:content';
const recentEntries = (await getCollection('{coll_name}'))
  .sort((a, b) => new Date(b.data.date).valueOf() - new Date(a.data.date).valueOf())
  .slice(0, 6);"""
        posts_section = f"""
  <section class="latest-posts">
    <h2>Latest {label}</h2>
    <div class="post-grid">
      {{recentEntries.map((entry) => (
        <article class="post-card">
          <a href={{`{blog_route}/${{entry.slug}}`}} class="post-card-link">{image_block}
            <div class="post-card-body">
              <h3>{{entry.data.title}}</h3>
              {{entry.data.date && (
                <time class="post-card-date" datetime={{entry.data.date}}>
                  {{new Date(entry.data.date).toLocaleDateString('en-US', {{ year: 'numeric', month: 'short', day: 'numeric' }})}}
                </time>
              )}}
              {{entry.data.excerpt && <p class="post-card-excerpt">{{entry.data.excerpt}}</p>}}
              <span class="read-more">Read More &rarr;</span>
            </div>
          </a>
        </article>
      ))}}
    </div>
  </section>"""

    # --- Browse sections for every non-page, non-blog collection ---
    explore_sections = ""
    explore_imports = ""
    for i, c in enumerate(browse_colls):
        label = _humanize_collection_name(c.collection_name)
        route = _friendly_route_prefix(c)
        var_name = f"browse_{i}"
        has_featured = any(f.name == "featured_image" for f in c.frontmatter_fields)

        explore_imports += f"""
const {var_name} = (await getCollection('{c.collection_name}')).slice(0, 6);"""

        image_block = ""
        if has_featured:
            image_block = f"""
                {{item.data.featured_image && (
                  <div class="browse-card-image">
                    <img src={{item.data.featured_image}} alt={{item.data.title}} loading="lazy" />
                  </div>
                )}}"""

        explore_sections += f"""
  <section class="explore-section">
    <div class="explore-header">
      <h2>Explore {label}</h2>
      <a href="{route}" class="explore-link">Browse all {label} &rarr;</a>
    </div>
    <div class="browse-grid">
      {{{var_name}.map((item) => (
        <article class="browse-card">
          <a href={{`{route}/${{item.slug}}`}} class="browse-card-link">{image_block}
            <div class="browse-card-body">
              <h3>{{item.data.title}}</h3>
            </div>
          </a>
        </article>
      ))}}
    </div>
  </section>"""

    # If browse collections exist, we need getCollection even without a blog
    if browse_colls and not blog_coll:
        explore_imports = f"""
import {{ getCollection }} from 'astro:content';{explore_imports}"""
    elif browse_colls and blog_coll:
        # getCollection already imported via posts_import
        explore_imports = explore_imports  # just the const lines

    return f"""---
import BaseLayout from '../layouts/BaseLayout.astro';{posts_import}{explore_imports}
---
<BaseLayout title="{site_name}">
  <section class="hero">
    <h1>{site_name}</h1>
  </section>
{posts_section}
{explore_sections}
</BaseLayout>

<style>
  .hero {{
    text-align: center;
    padding: var(--global-lg-spacing, 3rem) 0;
  }}
  .hero h1 {{
    font-size: var(--global-font-size-xxlarge, 2.5rem);
    margin: 0;
  }}
  .latest-posts {{
    padding: 2rem 0;
  }}
  .latest-posts h2 {{
    margin: 0 0 1rem;
  }}
  .post-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 1.5rem;
  }}
  .post-card {{
    border: 1px solid var(--global-gray-400, #e0e0e0);
    border-radius: .5rem;
    overflow: hidden;
    transition: box-shadow .2s, transform .2s;
    background: var(--global-palette9, #fff);
  }}
  .post-card:hover {{
    box-shadow: 0 4px 16px rgba(0,0,0,.1);
    transform: translateY(-2px);
  }}
  .post-card-link {{
    display: block;
    text-decoration: none;
    color: inherit;
  }}
  .post-card-image {{
    aspect-ratio: 16/9;
    overflow: hidden;
    background: var(--global-gray-200, #f0f0f0);
  }}
  .post-card-image img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
  }}
  .post-card-body {{
    padding: 1rem;
  }}
  .post-card-body h3 {{
    margin: 0 0 .5rem;
    font-size: 1.1rem;
    line-height: 1.3;
  }}
  .post-card-date {{
    display: block;
    font-size: .8rem;
    color: var(--global-palette5, #888);
    margin-bottom: .5rem;
  }}
  .post-card-excerpt {{
    font-size: .9rem;
    color: var(--global-palette5, #666);
    margin: 0 0 .75rem;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }}
  .read-more {{
    font-size: .85rem;
    font-weight: 600;
    color: var(--global-palette-btn-bg, var(--global-palette1, #0073aa));
  }}
  .explore-section {{
    padding: 2rem 0;
    border-top: 1px solid var(--global-gray-400, #e0e0e0);
  }}
  .explore-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
  }}
  .explore-header h2 {{
    margin: 0;
  }}
  .explore-link {{
    font-weight: 600;
    text-decoration: none;
    color: var(--global-palette-btn-bg, var(--global-palette1, #0073aa));
    white-space: nowrap;
  }}
  .explore-link:hover {{
    text-decoration: underline;
  }}
  .browse-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 1rem;
  }}
  .browse-card {{
    border: 1px solid var(--global-gray-400, #e0e0e0);
    border-radius: .5rem;
    overflow: hidden;
    transition: box-shadow .2s;
    background: var(--global-palette9, #fff);
  }}
  .browse-card:hover {{
    box-shadow: 0 4px 12px rgba(0,0,0,.1);
  }}
  .browse-card-link {{
    display: block;
    text-decoration: none;
    color: inherit;
  }}
  .browse-card-image {{
    aspect-ratio: 16/9;
    overflow: hidden;
    background: var(--global-gray-200, #f0f0f0);
  }}
  .browse-card-image img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
  }}
  .browse-card-body {{
    padding: .75rem;
  }}
  .browse-card-body h3 {{
    margin: 0;
    font-size: .95rem;
    line-height: 1.3;
  }}
</style>
"""


def _humanize_collection_name(name: str) -> str:
    """Turn a collection slug like ``gd_plugin`` into ``Plugin``.

    Strips common WordPress plugin CPT prefixes so the label reads naturally.
    Unknown prefixes pass through and get title-cased with the underscore
    replaced by a space.
    """
    cleaned = re.sub(r"^(gd|wp|ct|cpt|wc|edd|tribe|jet|acf)_", "", name)
    return cleaned.replace("_", " ").title()


_CPT_PREFIX_RE = re.compile(r"^(gd|wp|ct|cpt|wc|edd|tribe|jet|acf)_")


def _friendly_route_prefix(collection: ContentCollectionSchema) -> str:
    """Return a URL prefix that prefers the humanized plural when a CPT prefix is detected.

    For ``gd_plugin`` with route ``/gd_plugin/[slug]``, returns ``/plugins``
    so that links match the WordPress permalink structure.  For collections
    without a CPT prefix (e.g. ``posts`` → ``/blog``), falls back to the
    normal ``_route_prefix``.
    """
    canonical = _route_prefix(collection.route_pattern)
    if _CPT_PREFIX_RE.match(collection.collection_name):
        stem = _CPT_PREFIX_RE.sub("", collection.collection_name)
        stem = stem.lower().replace("_", "-")
        # Pluralize naively — add 's' if not already plural
        if not stem.endswith("s"):
            stem += "s"
        return f"/{stem}"
    return canonical
def generate_component(mapping: ComponentMapping) -> str:
    """Generate an Astro component file from a ComponentMapping."""
    if mapping.fallback:
        return _generate_fallback_component(mapping)
    if mapping.is_island:
        return _generate_island_component(mapping)
    return _generate_static_component(mapping)

def _generate_static_component(mapping: ComponentMapping) -> str:
    """Generate a static (non-island) Astro component."""
    props_interface = _build_props_interface(mapping)
    props_destructure = _build_props_destructure(mapping)
    return f"""---
{props_interface}
{props_destructure}
---
<div class="{_to_kebab(mapping.astro_component)}">
  <slot />
</div>
"""
def _generate_island_component(mapping: ComponentMapping) -> str:
    """Generate an island component with a hydration directive comment."""
    directive = mapping.hydration_directive or "client:load"
    props_interface = _build_props_interface(mapping)
    props_destructure = _build_props_destructure(mapping)
    return f"""---
// Island component — use with {directive}
{props_interface}
{props_destructure}
---
<div class="{_to_kebab(mapping.astro_component)}" data-island>
  <slot />
</div>
"""
def _generate_fallback_component(mapping: ComponentMapping) -> str:
    """Generate a fallback rich-text HTML component."""
    return f"""---
// Fallback component for WordPress block: {mapping.wp_block_type}
export interface Props {{
  html?: string;
}}
const {{ html = '' }} = Astro.props;
---
<div class="wp-block-fallback {_to_kebab(mapping.astro_component)}">
  <Fragment set:html={{html}} />
</div>
"""
def generate_island_usage(mapping: ComponentMapping) -> str:
    """Return the usage string for an island component with its directive.

    E.g. ``<SearchWidget client:load />``
    """
    directive = mapping.hydration_directive or "client:load"
    return f"<{mapping.astro_component} {directive} />"

def generate_base_layout_with_seo(
    site_name: str,
    theme_layouts: dict[str, str],
) -> str:
    """Generate or augment the base layout with OG tags, canonical URL, and meta description.

    If a BaseLayout.astro already exists from the theming agent, inject SEO
    head tags into it. Otherwise generate a new one.
    """
    existing = theme_layouts.get("BaseLayout.astro", "")
    if existing and "<head>" in existing:
        return _inject_seo_into_layout(existing)
    # Generate a fresh base layout with SEO tags
    return f"""---
export interface Props {{
  title?: string;
  description?: string;
  canonicalUrl?: string;
  ogImage?: string;
  bodyClass?: string;
}}

const {{ title = "{site_name}", description = "", canonicalUrl = "", ogImage = "", bodyClass = "" }} = Astro.props;
const resolvedCanonical = canonicalUrl || Astro.url.href;
---
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{{title}}</title>
    <meta name="description" content="{{description}}" />
    <link rel="canonical" href="{{resolvedCanonical}}" />
    <meta property="og:title" content="{{title}}" />
    <meta property="og:description" content="{{description}}" />
    <meta property="og:url" content="{{resolvedCanonical}}" />
    {{ogImage && <meta property="og:image" content={{ogImage}} />}}
  </head>
  <body class={{bodyClass}}>
    <main>
      <slot />
    </main>
  </body>
</html>
"""
def _inject_seo_into_layout(layout: str) -> str:
    """Inject SEO meta tags into an existing BaseLayout.astro ``<head>`` section."""
    has_canonical = 'rel="canonical"' in layout or "rel='canonical'" in layout
    has_og_title = 'property="og:title"' in layout or "property='og:title'" in layout
    has_og_description = 'property="og:description"' in layout or "property='og:description'" in layout
    has_og_url = 'property="og:url"' in layout or "property='og:url'" in layout

    seo_lines: list[str] = []
    if not has_canonical:
        seo_lines.append('    <link rel="canonical" href={canonicalUrl || Astro.url.href} />')
    if not has_og_title:
        seo_lines.append('    <meta property="og:title" content={title} />')
    if not has_og_description:
        seo_lines.append('    <meta property="og:description" content={description} />')
    if not has_og_url:
        seo_lines.append('    <meta property="og:url" content={canonicalUrl || Astro.url.href} />')

    if seo_lines and "</head>" in layout:
        layout = layout.replace("</head>", "\n".join(seo_lines) + "\n  </head>")

    frontmatter_additions: list[str] = []
    if "canonicalUrl" not in layout:
        frontmatter_additions.append('const canonicalUrl = Astro.props.canonicalUrl || "";')
    if "ogImage" not in layout:
        frontmatter_additions.append('const ogImage = Astro.props.ogImage || "";')
    if "bodyClass" not in layout:
        frontmatter_additions.append('const bodyClass = Astro.props.bodyClass || "";')

    if frontmatter_additions:
        parts = layout.split("---", 2)
        if len(parts) >= 3:
            injection = "\n" + "\n".join(frontmatter_additions)
            layout = parts[0] + "---" + parts[1] + injection + "\n---" + parts[2]

    if "<body>" in layout and "class={bodyClass}" not in layout:
        layout = layout.replace("<body>", '<body class={bodyClass}>', 1)

    return layout

def generate_readme(site_name: str, site_url: str) -> str:
    """Generate ``README.md`` with build and deploy instructions."""
    return f"""# {site_name}

Astro JS 5 site migrated from WordPress.

## Getting Started

```bash
npm install
npm run dev
```

## Build

```bash
npm run build
```

The built site will be in the `dist/` directory.

## Preview

```bash
npm run preview
```

## Project Structure

```
├── astro.config.mjs    # Astro configuration
├── package.json        # Dependencies and scripts
├── tsconfig.json       # TypeScript configuration
├── src/
│   ├── layouts/        # Page layouts (Base, Page, Post)
│   ├── pages/          # Route pages
│   ├── components/     # UI components
│   └── content/        # Content collections (Markdown/MDX)
└── public/             # Static assets
```

## Deployment

Build the site and deploy the `dist/` directory to any static hosting provider:

- **Netlify**: Connect your repo or drag-and-drop the `dist/` folder
- **Vercel**: Import the project and set the build command to `npm run build`
- **DigitalOcean App Platform**: Manual static-site deployment target with build command `npm run build` and output directory `dist`

Site URL: {site_url}
"""
# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    """Convert a site name to a package-json-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "astro-site"

def _to_kebab(name: str) -> str:
    """Convert PascalCase component name to kebab-case CSS class."""
    s = re.sub(r"([A-Z])", r"-\1", name).lower().lstrip("-")
    return s

def _route_prefix(route_pattern: str) -> str:
    """Extract the static prefix from a route pattern like ``/places/[slug]``."""
    # Remove dynamic segments
    prefix = re.sub(r"/\[.*?\]", "", route_pattern)
    return prefix.rstrip("/") or "/"

def _route_dir(route_pattern: str) -> str:
    """Derive the ``src/pages/`` subdirectory from a route pattern.

    ``/places/[slug]`` → ``places``
    ``/blog/[slug]``   → ``blog``
    ``/[slug]``        → ``""`` (root)
    """
    prefix = _route_prefix(route_pattern)
    return prefix.strip("/")

def _layout_import_path(route_dir: str, layout_filename: str) -> str:
    """Build a relative import path from ``src/pages/{route_dir}`` to layouts."""
    depth = 1 + (len(route_dir.split("/")) if route_dir else 0)
    prefix = "../" * depth
    return f"{prefix}layouts/{layout_filename}"

def _build_props_interface(mapping: ComponentMapping) -> str:
    """Build a TypeScript Props interface from component mapping props."""
    if not mapping.props:
        return "export interface Props {}"
    lines = ["export interface Props {"]
    for prop in mapping.props:
        name = prop.get("name", "value")
        ptype = prop.get("type", "string")
        ts_type = _wp_type_to_ts(ptype)
        lines.append(f"  {name}?: {ts_type};")
    lines.append("}")
    return "\n".join(lines)

def _build_props_destructure(mapping: ComponentMapping) -> str:
    """Build the Astro props destructuring statement."""
    if not mapping.props:
        return "const props = Astro.props;"
    names = [p.get("name", "value") for p in mapping.props]
    defaults = ", ".join(f'{n} = ""' for n in names)
    return f"const {{ {defaults} }} = Astro.props;"

def _wp_type_to_ts(wp_type: str) -> str:
    """Map a WordPress/modeling field type to a TypeScript type."""
    mapping = {
        "string": "string",
        "number": "number",
        "boolean": "boolean",
        "date": "string",
        "reference": "string",
        "list": "string[]",
    }
    return mapping.get(wp_type, "any")

# ---------------------------------------------------------------------------
# ZIP packaging
# ---------------------------------------------------------------------------

def package_as_zip(project: dict[str, str | bytes]) -> bytes:
    """Package a project file dict into a ZIP archive (in-memory bytes)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in sorted(project.items()):
            zf.writestr(path, content)
    return buf.getvalue()

# ---------------------------------------------------------------------------
# CMS mode generation helpers
# ---------------------------------------------------------------------------

def _extract_content_type_map(context: dict[str, Any]) -> "ContentTypeMap":
    """Extract ContentTypeMap from the pipeline context."""
    from src.models.strapi_types import ContentTypeMap

    raw = context.get("content_type_map")
    if raw is None:
        raise KeyError("'content_type_map' missing from pipeline context")
    if isinstance(raw, ContentTypeMap):
        return raw
    return ContentTypeMap.model_validate(raw)

def generate_cms_astro_config(site_url: str) -> str:
    """Generate ``astro.config.mjs`` for CMS mode with static output and Strapi env vars."""
    return f"""import {{ defineConfig }} from 'astro/config';

export default defineConfig({{
  output: 'static',
  site: '{site_url}',
  vite: {{
    define: {{
      'import.meta.env.STRAPI_URL': JSON.stringify(process.env.STRAPI_URL || 'http://localhost:1337'),
      'import.meta.env.STRAPI_API_TOKEN': JSON.stringify(process.env.STRAPI_API_TOKEN || ''),
    }},
  }},
}});
"""
def generate_strapi_client() -> str:
    """Generate ``src/lib/strapi.ts`` — a fetch wrapper for the Strapi REST API.

    Includes base URL from env var, API token auth header, pagination support,
    and error handling.
    """
    return """const STRAPI_URL = import.meta.env.STRAPI_URL || 'http://localhost:1337';
const STRAPI_API_TOKEN = import.meta.env.STRAPI_API_TOKEN || '';

interface StrapiResponse<T> {
  data: T;
  meta: {
    pagination?: {
      page: number;
      pageSize: number;
      pageCount: number;
      total: number;
    };
  };
}

interface StrapiError {
  status: number;
  name: string;
  message: string;
}

function buildHeaders(): HeadersInit {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };
  if (STRAPI_API_TOKEN) {
    headers['Authorization'] = `Bearer ${STRAPI_API_TOKEN}`;
  }
  return headers;
}

export async function fetchAPI<T>(
  endpoint: string,
  params: Record<string, string> = {},
): Promise<StrapiResponse<T>> {
  const url = new URL(endpoint, STRAPI_URL);
  Object.entries(params).forEach(([key, value]) => {
    url.searchParams.set(key, value);
  });

  const response = await fetch(url.toString(), {
    headers: buildHeaders(),
  });

  if (!response.ok) {
    const error: StrapiError = await response.json().catch(() => ({
      status: response.status,
      name: 'FetchError',
      message: response.statusText,
    }));
    throw new Error(`Strapi API error ${error.status}: ${error.message}`);
  }

  return response.json();
}

export async function fetchCollection<T>(
  apiId: string,
  page: number = 1,
  pageSize: number = 25,
  populate: string = '*',
  populateDepth: number = 2,
): Promise<StrapiResponse<T[]>> {
  const params: Record<string, string> = {
    'pagination[page]': String(page),
    'pagination[pageSize]': String(pageSize),
    'populate[0]': populate,
  };
  if (populateDepth > 1) {
    params['populate'] = 'deep,' + String(populateDepth);
  }
  return fetchAPI<T[]>(`/api/${apiId}`, params);
}

export async function fetchAllPages<T>(
  apiId: string,
  pageSize: number = 25,
  populate: string = '*',
  populateDepth: number = 2,
): Promise<T[]> {
  const allItems: T[] = [];
  let page = 1;
  let pageCount = 1;

  do {
    const response = await fetchCollection<T>(apiId, page, pageSize, populate, populateDepth);
    allItems.push(...response.data);
    pageCount = response.meta.pagination?.pageCount ?? 1;
    page++;
  } while (page <= pageCount);

  return allItems;
}

export async function fetchBySlug<T>(
  apiId: string,
  slug: string,
  populate: string = '*',
  populateDepth: number = 2,
): Promise<T | null> {
  const params: Record<string, string> = {
    'filters[slug][$eq]': slug,
    'populate[0]': populate,
  };
  if (populateDepth > 1) {
    params['populate'] = 'deep,' + String(populateDepth);
  }
  const response = await fetchAPI<T[]>(`/api/${apiId}`, params);
  return response.data.length > 0 ? response.data[0] : null;
}
"""
def generate_strapi_types(content_type_map: "ContentTypeMap") -> str:
    """Generate TypeScript type definitions for each Strapi Content Type.

    Produces an interface per collection with ``id``, ``attributes`` containing
    typed fields, and a wrapper ``StrapiEntity`` generic.
    """
    from src.models.strapi_types import ContentTypeMap  # noqa: F811

    lines: list[str] = [
        "// Auto-generated Strapi type definitions",
        "",
        "export interface StrapiEntity<T> {",
        "  id: number;",
        "  attributes: T;",
        "}",
        "",
        "export interface StrapiMedia {",
        "  id: number;",
        "  attributes: {",
        "    url: string;",
        "    alternativeText: string | null;",
        "    width: number;",
        "    height: number;",
        "    formats: Record<string, { url: string; width: number; height: number }>;",
        "  };",
        "}",
        "",
        "export interface StrapiRichTextBlock {",
        "  type: string;",
        "  children?: StrapiRichTextBlock[];",
        "  text?: string;",
        "  url?: string;",
        "  image?: StrapiMedia;",
        "  level?: number;",
        "  format?: string;",
        "}",
        "",
    ]

    for collection_name, api_id in content_type_map.mappings.items():
        interface_name = collection_name.replace("_", " ").title().replace(" ", "")
        lines.append(f"export interface {interface_name}Attributes {{")
        lines.append("  title: string;")
        lines.append("  slug: string;")
        lines.append("  content: StrapiRichTextBlock[];")
        lines.append("  createdAt: string;")
        lines.append("  updatedAt: string;")
        lines.append("  publishedAt: string;")
        lines.append("}")
        lines.append("")
        lines.append(
            f"export type {interface_name} = StrapiEntity<{interface_name}Attributes>;"
        )
        lines.append("")

    for taxonomy_name, api_id in content_type_map.taxonomy_mappings.items():
        interface_name = taxonomy_name.replace("_", " ").title().replace(" ", "")
        lines.append(f"export interface {interface_name}Attributes {{")
        lines.append("  name: string;")
        lines.append("  slug: string;")
        lines.append("  description: string | null;")
        lines.append("}")
        lines.append("")
        lines.append(
            f"export type {interface_name} = StrapiEntity<{interface_name}Attributes>;"
        )
        lines.append("")

    return "\n".join(lines)

def generate_env_example() -> str:
    """Generate ``.env.example`` with Strapi env var placeholders (not hardcoded)."""
    return """# Strapi CMS connection
STRAPI_URL=http://localhost:1337
STRAPI_API_TOKEN=your-strapi-api-token-here
"""
def generate_cms_route_page(
    collection_name: str,
    collection_endpoint: str,
    route_pattern: str,
) -> str:
    """Generate a detail page using ``getStaticPaths`` and a Strapi REST endpoint.

    Fetches a single entry by slug with ``populate`` depth of 2.
    """
    interface_name = collection_name.replace("_", " ").title().replace(" ", "")
    return f"""---
import {{ fetchAllPages, fetchBySlug }} from '../../lib/strapi';
import type {{ {interface_name} }} from '../../types/strapi';
import RichTextRenderer from '../../components/RichTextRenderer.astro';
import PostLayout from '../../layouts/PostLayout.astro';

export async function getStaticPaths() {{
  const entries = await fetchAllPages<{interface_name}>('{collection_endpoint}');
  return entries.map((entry) => ({{
    params: {{ slug: entry.attributes.slug }},
    props: {{ entry }},
  }}));
}}

interface Props {{
  entry: {interface_name};
}}

const {{ entry }} = Astro.props;
const {{ attributes }} = entry;
---
<PostLayout title={{attributes.title}}>
  <article>
    <h1>{{attributes.title}}</h1>
    <RichTextRenderer blocks={{attributes.content}} />
  </article>
</PostLayout>
"""
def generate_cms_index_page(
    collection_name: str,
    collection_endpoint: str,
    route_pattern: str,
) -> str:
    """Generate an index page that fetches paginated entries from Strapi."""
    interface_name = collection_name.replace("_", " ").title().replace(" ", "")
    title = collection_name.replace("_", " ").title()
    prefix = _route_prefix(route_pattern)
    return f"""---
import {{ fetchAllPages }} from '../../lib/strapi';
import type {{ {interface_name} }} from '../../types/strapi';
import PageLayout from '../../layouts/PageLayout.astro';

const entries = await fetchAllPages<{interface_name}>('{collection_endpoint}');
---
<PageLayout title="{title}">
  <h1>{title}</h1>
  <ul>
    {{entries.map((entry) => (
      <li>
        <a href={{`{prefix}/${{entry.attributes.slug}}`}}>
          {{entry.attributes.title}}
        </a>
      </li>
    ))}}
  </ul>
</PageLayout>
"""
def generate_rich_text_renderer() -> str:
    """Generate ``RichTextRenderer.astro`` component.

    Converts Strapi rich text blocks to HTML elements.
    Handles image blocks, internal link rewriting, and unknown block types.
    """
    return """---
import type { StrapiRichTextBlock } from '../types/strapi';

export interface Props {
  blocks: StrapiRichTextBlock[];
}

const { blocks = [] } = Astro.props;

function renderChildren(children: StrapiRichTextBlock[] | undefined): string {
  if (!children) return '';
  return children.map((child) => renderBlock(child)).join('');
}

function renderBlock(block: StrapiRichTextBlock): string {
  switch (block.type) {
    case 'heading': {
      const level = block.level || 2;
      const tag = `h${level}`;
      return `<${tag}>${renderChildren(block.children)}</${tag}>`;
    }
    case 'paragraph':
      return `<p>${renderChildren(block.children)}</p>`;
    case 'text':
      return block.text || '';
    case 'list': {
      const tag = block.format === 'ordered' ? 'ol' : 'ul';
      return `<${tag}>${renderChildren(block.children)}</${tag}>`;
    }
    case 'list-item':
      return `<li>${renderChildren(block.children)}</li>`;
    case 'link': {
      let href = block.url || '#';
      // Rewrite internal Strapi URLs to Astro routes
      if (href.startsWith('/api/')) {
        href = href.replace(/^\\/api\\/[^/]+/, '');
      }
      return `<a href="${href}">${renderChildren(block.children)}</a>`;
    }
    case 'image': {
      const media = block.image;
      if (!media) return '';
      const url = media.attributes.url;
      const alt = media.attributes.alternativeText || '';
      const width = media.attributes.width;
      const height = media.attributes.height;
      return `<img src="${url}" alt="${alt}" width="${width}" height="${height}" loading="lazy" />`;
    }
    case 'quote':
      return `<blockquote>${renderChildren(block.children)}</blockquote>`;
    case 'code':
      return `<pre><code>${renderChildren(block.children)}</code></pre>`;
    default:
      return `<p data-unknown-block="${block.type}">${renderChildren(block.children)}</p>`;
  }
}

const html = blocks.map((block) => renderBlock(block)).join('\\n');
---
<div class="rich-text">
  <Fragment set:html={html} />
</div>
"""
def generate_cms_home_page(
    site_name: str,
    collections: list[ContentCollectionSchema],
) -> str:
    """Generate the CMS mode home page with links to collection index pages."""
    links = "\n    ".join(
        f'<li><a href="{_route_prefix(c.route_pattern)}">{c.collection_name.replace("_", " ").title()}</a></li>'
        for c in collections
    )
    return f"""---
import PageLayout from '../layouts/PageLayout.astro';
---
<PageLayout title="{site_name}">
  <h1>Welcome to {site_name}</h1>
  <nav>
    <ul>
    {links}
    </ul>
  </nav>
</PageLayout>
"""
def generate_cms_package_json(site_name: str) -> str:
    """Generate ``package.json`` for CMS mode (no MDX needed, Strapi provides content)."""
    pkg = {
        "name": _slugify(site_name),
        "type": "module",
        "version": "0.0.1",
        "scripts": {
            "dev": "astro dev",
            "start": "astro dev",
            "build": "astro build",
            "preview": "astro preview",
            "astro": "astro",
        },
        "dependencies": {
            "astro": "^5.0.0",
        },
        "devDependencies": {
            "typescript": "^5.0.0",
        },
    }
    return json.dumps(pkg, indent=2) + "\n"

# ---------------------------------------------------------------------------
# ScaffoldAgent
# ---------------------------------------------------------------------------

class ScaffoldAgent(BaseAgent):
    """Generates a complete Astro JS 5 project from migration artifacts."""
    async def execute(self, context: dict[str, Any]) -> AgentResult:
        """Execute the Scaffold agent.

        Args:
            context: Must contain ``inventory``, ``modeling_manifest``.
                May contain ``layouts`` or ``theme_layouts`` (from theming agent).
                When ``cms_mode=True``, also requires ``content_type_map``.

        Returns:
            AgentResult with artifacts:
            - ``astro_project``: dict mapping file paths → content strings
            - ``astro_project_zip``: bytes of the ZIP archive
        """
        if context.get("cms_mode", False):
            return build_cms_project(
                context,
                _extract_inventory(context),
                _extract_modeling_manifest(context),
                _extract_theme_layouts(context),
                _extract_content_type_map(context),
                generate_cms_astro_config=generate_cms_astro_config,
                generate_cms_package_json=generate_cms_package_json,
                generate_tsconfig=generate_tsconfig,
                generate_env_example=generate_env_example,
                generate_strapi_client=generate_strapi_client,
                generate_strapi_types=generate_strapi_types,
                generate_rich_text_renderer=generate_rich_text_renderer,
                generate_cms_home_page=generate_cms_home_page,
                generate_cms_route_page=generate_cms_route_page,
                generate_cms_index_page=generate_cms_index_page,
                generate_component=generate_component,
                generate_base_layout_with_seo=generate_base_layout_with_seo,
                generate_readme=generate_readme,
                package_as_zip=package_as_zip,
                default_page_layout=_default_page_layout,
                default_post_layout=_default_post_layout,
                route_dir=_route_dir,
            )
        return build_static_project(
            context,
            _extract_inventory(context),
            _extract_modeling_manifest(context),
            _extract_theme_layouts(context),
            generate_astro_config=generate_astro_config,
            generate_package_json=generate_package_json,
            generate_tsconfig=generate_tsconfig,
            generate_home_page=generate_home_page,
            generate_route_page=generate_route_page,
            generate_index_page=generate_index_page,
            generate_component=generate_component,
            generate_base_layout_with_seo=generate_base_layout_with_seo,
            generate_readme=generate_readme,
            package_as_zip=package_as_zip,
            default_page_layout=_default_page_layout,
            default_post_layout=_default_post_layout,
            layout_import_path=_layout_import_path,
            route_dir=_route_dir,
        )

# ---------------------------------------------------------------------------
# Additional helpers used by ScaffoldAgent
# ---------------------------------------------------------------------------

def _default_page_layout(site_name: str) -> str:
    """Fallback PageLayout when theming agent didn't provide one."""
    return f"""---
import BaseLayout from "./BaseLayout.astro";

export interface Props {{
  title?: string;
  description?: string;
  bodyClass?: string;
}}

const {{ title = "{site_name}", description = "", bodyClass = "" }} = Astro.props;
---
<BaseLayout title={{title}} description={{description}} bodyClass={{bodyClass}}>
  <article class="page-content">
    <slot />
  </article>
</BaseLayout>
"""
def _default_post_layout(site_name: str) -> str:
    """Fallback PostLayout when theming agent didn't provide one."""
    return f"""---
import BaseLayout from "./BaseLayout.astro";

export interface Props {{
  title?: string;
  description?: string;
  date?: string;
  bodyClass?: string;
}}

const {{ title = "{site_name}", description = "", date = "", bodyClass = "" }} = Astro.props;
---
<BaseLayout title={{title}} description={{description}} bodyClass={{bodyClass}}>
  <article class="post-content">
    <header class="post-header">
      <h1>{{title}}</h1>
      {{date && <time datetime={{date}}>{{date}}</time>}}
    </header>
    <div class="post-body">
      <slot />
    </div>
  </article>
</BaseLayout>
"""
def _build_zod_fields(collection: ContentCollectionSchema) -> list[str]:
    """Build Zod schema field lines for a content collection."""
    type_map = {
        "string": "z.string()",
        "number": "z.number()",
        "boolean": "z.boolean()",
        "date": "z.date()",
        "reference": "z.string()",
        "list": "z.array(z.string())",
    }
    lines: list[str] = []
    for field in collection.frontmatter_fields:
        zod_type = type_map.get(field.type, "z.any()")
        if not field.required:
            zod_type += ".optional()"
        lines.append(f"{field.name}: {zod_type},")
    return lines
