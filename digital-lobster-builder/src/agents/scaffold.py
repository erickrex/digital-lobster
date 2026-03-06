"""Agent 4: Scaffold — generates a complete Astro JS 5 project.

Receives the modeling manifest, theme layouts, and inventory from prior agents
and produces a full Astro project directory structure as an in-memory dict,
then packages it as a ZIP archive.
"""

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
    return f"""---
import {{ getCollection }} from 'astro:content';
import PostLayout from '{layout_import_path}';

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
<PostLayout title={{entry.data.title}} description={{entry.data.description || ''}}>
  <Content />
</PostLayout>
"""


def generate_index_page(
    collection: ContentCollectionSchema,
    layout_import_path: str = "../../layouts/PageLayout.astro",
) -> str:
    """Generate an index page listing all entries in a content collection."""
    return f"""---
import {{ getCollection }} from 'astro:content';
import PageLayout from '{layout_import_path}';

const entries = await getCollection('{collection.collection_name}');
---
<PageLayout title="{collection.collection_name.replace('_', ' ').title()}">
  <h1>{collection.collection_name.replace('_', ' ').title()}</h1>
  <ul>
    {{entries.map((entry) => (
      <li>
        <a href={{`{_route_prefix(collection.route_pattern)}/${{entry.slug}}`}}>
          {{entry.data.title}}
        </a>
      </li>
    ))}}
  </ul>
</PageLayout>
"""


def generate_home_page(site_name: str, collections: list[ContentCollectionSchema]) -> str:
    """Generate the home ``index.astro`` page."""
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
}}

const {{ title = "{site_name}", description = "", canonicalUrl = "", ogImage = "" }} = Astro.props;
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
  <body>
    <main>
      <slot />
    </main>
  </body>
</html>
"""


def _inject_seo_into_layout(layout: str) -> str:
    """Inject SEO meta tags into an existing BaseLayout.astro ``<head>`` section."""
    seo_tags = """    <link rel="canonical" href={canonicalUrl || Astro.url.href} />
    <meta property="og:title" content={title} />
    <meta property="og:description" content={description} />
    <meta property="og:url" content={canonicalUrl || Astro.url.href} />"""

    # Add canonicalUrl and ogImage to the Props interface if not present
    frontmatter_addition = ""
    if "canonicalUrl" not in layout:
        frontmatter_addition = (
            '\nconst canonicalUrl = Astro.props.canonicalUrl || "";\n'
            'const ogImage = Astro.props.ogImage || "";'
        )

    # Insert SEO tags before </head>
    if "</head>" in layout:
        layout = layout.replace("</head>", f"{seo_tags}\n  </head>")

    # Insert frontmatter additions before the closing ---
    if frontmatter_addition:
        # Find the second --- (closing frontmatter fence)
        parts = layout.split("---", 2)
        if len(parts) >= 3:
            layout = parts[0] + "---" + parts[1] + frontmatter_addition + "\n---" + parts[2]

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
- **DigitalOcean App Platform**: Deploy as a static site with build command `npm run build` and output directory `dist`

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


def package_as_zip(project: dict[str, str]) -> bytes:
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
    api_id: str,
    route_pattern: str,
) -> str:
    """Generate a detail page using ``getStaticPaths`` that fetches from Strapi API.

    Fetches a single entry by slug with ``populate`` depth of 2.
    """
    interface_name = collection_name.replace("_", " ").title().replace(" ", "")
    return f"""---
import {{ fetchAllPages, fetchBySlug }} from '../../lib/strapi';
import type {{ {interface_name} }} from '../../types/strapi';
import RichTextRenderer from '../../components/RichTextRenderer.astro';
import PostLayout from '../../layouts/PostLayout.astro';

export async function getStaticPaths() {{
  const entries = await fetchAllPages<{interface_name}>('{api_id}');
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
    api_id: str,
    route_pattern: str,
) -> str:
    """Generate an index page that fetches paginated entries from Strapi API."""
    interface_name = collection_name.replace("_", " ").title().replace(" ", "")
    title = collection_name.replace("_", " ").title()
    prefix = _route_prefix(route_pattern)
    return f"""---
import {{ fetchAllPages }} from '../../lib/strapi';
import type {{ {interface_name} }} from '../../types/strapi';
import PageLayout from '../../layouts/PageLayout.astro';

const entries = await fetchAllPages<{interface_name}>('{api_id}');
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
            return await self._generate_cms_project(context)
        return await self._generate_static_project(context)

    async def _generate_static_project(self, context: dict[str, Any]) -> AgentResult:
        """Generate a static Astro project (original code path)."""
        start = time.monotonic()
        warnings: list[str] = []

        inventory = _extract_inventory(context)
        manifest = _extract_modeling_manifest(context)
        theme_layouts = _extract_theme_layouts(context)

        project: dict[str, str] = {}

        # 1. Configuration files
        project["astro.config.mjs"] = generate_astro_config(inventory.site_url)
        project["package.json"] = generate_package_json(inventory.site_name)
        project["tsconfig.json"] = generate_tsconfig()

        # 2. Layouts — wire in theme layouts with SEO head injection
        self._generate_layouts(project, inventory, theme_layouts)
        self._generate_theme_assets(project, context)

        # 3. Pages — route files matching WordPress permalink structure
        self._generate_pages(project, inventory, manifest, warnings)

        # 4. Components — from modeling manifest component specs
        self._generate_components(project, manifest, warnings)

        # 5. Content collection config placeholder
        project["src/content/config.ts"] = self._generate_content_config(manifest)

        # 6. Public directory placeholder
        project["public/.gitkeep"] = ""

        # 7. README
        project["README.md"] = generate_readme(inventory.site_name, inventory.site_url)

        # 8. Package as ZIP
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

    async def _generate_cms_project(self, context: dict[str, Any]) -> AgentResult:
        """Generate a Strapi-backed Astro project (CMS mode code path)."""
        start = time.monotonic()
        warnings: list[str] = []

        inventory = _extract_inventory(context)
        manifest = _extract_modeling_manifest(context)
        theme_layouts = _extract_theme_layouts(context)
        content_type_map = _extract_content_type_map(context)

        project: dict[str, str] = {}

        # 1. Configuration files (CMS-specific)
        project["astro.config.mjs"] = generate_cms_astro_config(inventory.site_url)
        project["package.json"] = generate_cms_package_json(inventory.site_name)
        project["tsconfig.json"] = generate_tsconfig()
        project[".env.example"] = generate_env_example()

        # 2. Strapi API client and types
        project["src/lib/strapi.ts"] = generate_strapi_client()
        project["src/types/strapi.ts"] = generate_strapi_types(content_type_map)

        # 3. Layouts — reuse theme layouts with SEO head injection
        self._generate_layouts(project, inventory, theme_layouts)
        self._generate_theme_assets(project, context)

        # 4. RichTextRenderer component
        project["src/components/RichTextRenderer.astro"] = generate_rich_text_renderer()

        # 5. CMS route pages — fetch from Strapi API
        self._generate_cms_pages(project, inventory, manifest, content_type_map, warnings)

        # 6. Components — from modeling manifest component specs
        self._generate_components(project, manifest, warnings)

        # 7. Public directory placeholder
        project["public/.gitkeep"] = ""

        # 8. README
        project["README.md"] = generate_readme(inventory.site_name, inventory.site_url)

        # 9. Package as ZIP
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

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_layouts(
        project: dict[str, str],
        inventory: Inventory,
        theme_layouts: dict[str, str],
    ) -> None:
        """Wire theme layouts into ``src/layouts/``, injecting SEO tags."""
        # Base layout gets SEO head tags
        project["src/layouts/BaseLayout.astro"] = generate_base_layout_with_seo(
            inventory.site_name, theme_layouts
        )

        # Copy other theme layouts as-is
        for name, content in theme_layouts.items():
            if name == "BaseLayout.astro":
                continue  # Already handled with SEO injection
            project[f"src/layouts/{name}"] = content

        # Ensure PageLayout and PostLayout exist
        if "src/layouts/PageLayout.astro" not in project:
            project["src/layouts/PageLayout.astro"] = _default_page_layout(inventory.site_name)
        if "src/layouts/PostLayout.astro" not in project:
            project["src/layouts/PostLayout.astro"] = _default_post_layout(inventory.site_name)

    @staticmethod
    def _generate_pages(
        project: dict[str, str],
        inventory: Inventory,
        manifest: ModelingManifest,
        warnings: list[str],
    ) -> None:
        """Generate route pages in ``src/pages/`` for each collection."""
        # Home page
        project["src/pages/index.astro"] = generate_home_page(
            inventory.site_name, manifest.collections
        )

        # Per-collection routes
        for collection in manifest.collections:
            route_dir = _route_dir(collection.route_pattern)
            if route_dir:
                base = f"src/pages/{route_dir}"
            else:
                base = "src/pages"

            page_layout_import = _layout_import_path(
                route_dir, "PageLayout.astro"
            )
            post_layout_import = _layout_import_path(
                route_dir, "PostLayout.astro"
            )

            # Dynamic route page: [slug].astro
            project[f"{base}/[slug].astro"] = generate_route_page(
                collection,
                layout_import_path=post_layout_import,
            )

            # Index page for the collection
            if route_dir:
                project[f"{base}/index.astro"] = generate_index_page(
                    collection,
                    layout_import_path=page_layout_import,
                )
            else:
                warnings.append(
                    "Skipped generating collection index for root route "
                    f"pattern '{collection.route_pattern}' to preserve home page."
                )

    @staticmethod
    def _generate_cms_pages(
        project: dict[str, str],
        inventory: Inventory,
        manifest: ModelingManifest,
        content_type_map: "ContentTypeMap",
        warnings: list[str],
    ) -> None:
        """Generate CMS route pages in ``src/pages/`` that fetch from Strapi API."""
        # Home page
        project["src/pages/index.astro"] = generate_cms_home_page(
            inventory.site_name, manifest.collections
        )

        # Per-collection routes
        for collection in manifest.collections:
            api_id = content_type_map.mappings.get(collection.collection_name)
            if not api_id:
                warnings.append(
                    f"No Strapi API ID found for collection '{collection.collection_name}'; "
                    "skipping CMS route generation."
                )
                continue

            route_dir = _route_dir(collection.route_pattern)
            if route_dir:
                base = f"src/pages/{route_dir}"
            else:
                base = "src/pages"

            # Dynamic route page: [slug].astro — fetches single entry by slug
            project[f"{base}/[slug].astro"] = generate_cms_route_page(
                collection.collection_name,
                api_id,
                collection.route_pattern,
            )

            # Index page for the collection — fetches paginated entries
            if route_dir:
                project[f"{base}/index.astro"] = generate_cms_index_page(
                    collection.collection_name,
                    api_id,
                    collection.route_pattern,
                )
            else:
                warnings.append(
                    "Skipped generating CMS collection index for root route "
                    f"pattern '{collection.route_pattern}' to preserve home page."
                )


    @staticmethod
    def _generate_components(
        project: dict[str, str],
        manifest: ModelingManifest,
        warnings: list[str],
    ) -> None:
        """Generate component files in ``src/components/``."""
        for mapping in manifest.components:
            filename = f"src/components/{mapping.astro_component}.astro"
            project[filename] = generate_component(mapping)
            if mapping.is_island:
                logger.info(
                    "Island component %s uses %s",
                    mapping.astro_component,
                    mapping.hydration_directive or "client:load",
                )

    @staticmethod
    def _generate_theme_assets(
        project: dict[str, str],
        context: dict[str, Any],
    ) -> None:
        """Write theme CSS and tokens.css into ``public/styles`` when present."""
        theme_css = context.get("theme_css", {})
        if isinstance(theme_css, dict):
            for name, content in theme_css.items():
                safe_name = PurePosixPath(str(name)).name
                if not safe_name:
                    continue
                if isinstance(content, bytes):
                    content = content.decode("utf-8", errors="replace")
                elif not isinstance(content, str):
                    content = str(content)
                project[f"public/styles/{safe_name}"] = content

        tokens_css = context.get("tokens_css", "")
        if isinstance(tokens_css, bytes):
            tokens_css = tokens_css.decode("utf-8", errors="replace")
        if isinstance(tokens_css, str) and tokens_css.strip():
            project["public/styles/tokens.css"] = tokens_css

    @staticmethod
    def _generate_content_config(manifest: ModelingManifest) -> str:
        """Generate ``src/content/config.ts`` with Zod schemas for collections."""
        lines = [
            "import { defineCollection, z } from 'astro:content';",
            "",
        ]
        collection_defs: list[str] = []
        for coll in manifest.collections:
            schema_fields = _build_zod_fields(coll)
            lines.append(f"const {coll.collection_name} = defineCollection({{")
            lines.append("  schema: z.object({")
            for field_line in schema_fields:
                lines.append(f"    {field_line}")
            lines.append("  }),")
            lines.append("});")
            lines.append("")
            collection_defs.append(f"  {coll.collection_name},")

        lines.append("export const collections = {")
        lines.extend(collection_defs)
        lines.append("};")
        lines.append("")
        return "\n".join(lines)


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
}}

const {{ title = "{site_name}", description = "" }} = Astro.props;
---
<BaseLayout title={{title}} description={{description}}>
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
}}

const {{ title = "{site_name}", description = "", date = "" }} = Astro.props;
---
<BaseLayout title={{title}} description={{description}}>
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
