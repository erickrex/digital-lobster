"""CMS-backed Astro project assembly for the scaffold agent."""

from __future__ import annotations

import time
from typing import Callable

from src.agents.base import AgentResult
from src.models.inventory import Inventory
from src.models.modeling_manifest import ModelingManifest
from src.models.strapi_types import ContentTypeMap

from .scaffold_shared import (
    generate_components,
    generate_layouts,
    generate_media_assets,
    generate_theme_assets,
)


def build_cms_project(
    context: dict,
    inventory: Inventory,
    manifest: ModelingManifest,
    theme_layouts: dict[str, str],
    content_type_map: ContentTypeMap,
    *,
    generate_cms_astro_config: Callable[[str], str],
    generate_cms_package_json: Callable[[str], str],
    generate_tsconfig: Callable[[], str],
    generate_env_example: Callable[[], str],
    generate_strapi_client: Callable[[], str],
    generate_strapi_types: Callable[[ContentTypeMap], str],
    generate_rich_text_renderer: Callable[[], str],
    generate_cms_home_page: Callable[[str, list], str],
    generate_cms_route_page: Callable[[str, str, str], str],
    generate_cms_index_page: Callable[[str, str, str], str],
    generate_component: Callable[[object], str],
    generate_base_layout_with_seo: Callable[[str, dict[str, str]], str],
    generate_readme: Callable[[str, str], str],
    package_as_zip: Callable[[dict[str, str | bytes]], bytes],
    default_page_layout: Callable[[str], str],
    default_post_layout: Callable[[str], str],
    route_dir: Callable[[str], str],
) -> AgentResult:
    start = time.monotonic()
    warnings: list[str] = []
    project: dict[str, str | bytes] = {}

    project["astro.config.mjs"] = generate_cms_astro_config(inventory.site_url)
    project["package.json"] = generate_cms_package_json(inventory.site_name)
    project["tsconfig.json"] = generate_tsconfig()
    project[".env.example"] = generate_env_example()
    project["src/lib/strapi.ts"] = generate_strapi_client()
    project["src/types/strapi.ts"] = generate_strapi_types(content_type_map)

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
    project["src/components/RichTextRenderer.astro"] = generate_rich_text_renderer()
    project["src/pages/index.astro"] = generate_cms_home_page(
        inventory.site_name, manifest.collections
    )

    for collection in manifest.collections:
        api_id = content_type_map.mappings.get(collection.collection_name)
        if not api_id:
            warnings.append(
                f"No Strapi API ID found for collection '{collection.collection_name}'; "
                "skipping CMS route generation."
            )
            continue

        current_route_dir = route_dir(collection.route_pattern)
        base = f"src/pages/{current_route_dir}" if current_route_dir else "src/pages"
        project[f"{base}/[slug].astro"] = generate_cms_route_page(
            collection.collection_name,
            api_id,
            collection.route_pattern,
        )
        if current_route_dir:
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

    generate_components(project, manifest, component_generator=generate_component)
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
