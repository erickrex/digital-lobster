from __future__ import annotations

import time
from typing import Callable

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

    project["src/pages/index.astro"] = generate_home_page(
        inventory.site_name, manifest.collections
    )
    for collection in manifest.collections:
        current_route_dir = route_dir(collection.route_pattern)
        base = f"src/pages/{current_route_dir}" if current_route_dir else "src/pages"
        page_layout_import = layout_import_path(current_route_dir, "PageLayout.astro")
        post_layout_import = layout_import_path(current_route_dir, "PostLayout.astro")
        project[f"{base}/[slug].astro"] = generate_route_page(
            collection,
            layout_import_path=post_layout_import,
        )
        if current_route_dir:
            project[f"{base}/index.astro"] = generate_index_page(
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
