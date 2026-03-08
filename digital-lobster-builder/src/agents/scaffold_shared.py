from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Callable

from src.models.inventory import Inventory
from src.models.modeling_manifest import ModelingManifest
from src.pipeline_context import extract_media_manifest


def generate_layouts(
    project: dict[str, str | bytes],
    inventory: Inventory,
    theme_layouts: dict[str, str],
    *,
    base_layout_generator: Callable[[str, dict[str, str]], str],
    default_page_layout_generator: Callable[[str], str],
    default_post_layout_generator: Callable[[str], str],
) -> None:
    """Wire theme layouts into ``src/layouts/``."""
    project["src/layouts/BaseLayout.astro"] = base_layout_generator(
        inventory.site_name, theme_layouts
    )

    for name, content in theme_layouts.items():
        if name == "BaseLayout.astro":
            continue
        project[f"src/layouts/{name}"] = content

    if "src/layouts/PageLayout.astro" not in project:
        project["src/layouts/PageLayout.astro"] = default_page_layout_generator(
            inventory.site_name
        )
    if "src/layouts/PostLayout.astro" not in project:
        project["src/layouts/PostLayout.astro"] = default_post_layout_generator(
            inventory.site_name
        )


def generate_components(
    project: dict[str, str | bytes],
    manifest: ModelingManifest,
    *,
    component_generator: Callable[[Any], str],
) -> None:
    """Generate component files in ``src/components/``."""
    for mapping in manifest.components:
        filename = f"src/components/{mapping.astro_component}.astro"
        project[filename] = component_generator(mapping)


def generate_theme_assets(
    project: dict[str, str | bytes],
    context: dict[str, Any],
) -> None:
    """Write theme CSS and tokens into ``public/styles`` when present."""
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


def generate_media_assets(
    project: dict[str, str | bytes],
    context: dict[str, Any],
    warnings: list[str],
) -> None:
    """Write bundled media binaries into ``public/media`` when available."""
    export_bundle = context.get("export_bundle", {})
    if not isinstance(export_bundle, dict):
        return

    for entry in extract_media_manifest(context):
        raw = export_bundle.get(entry.bundle_path)
        if raw is None:
            warnings.append(
                f"Media asset missing from export bundle: {entry.bundle_path}"
            )
            continue
        project[f"public/{entry.artifact_path.lstrip('/')}"] = raw


def generate_content_config(manifest: ModelingManifest) -> str:
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


def _build_zod_fields(coll) -> list[str]:
    field_lines: list[str] = []
    for field in coll.frontmatter_fields:
        if field.type == "string":
            zod_type = "z.string()"
        elif field.type == "number":
            zod_type = "z.number()"
        elif field.type == "boolean":
            zod_type = "z.boolean()"
        elif field.type == "date":
            zod_type = "z.string()"
        elif field.type == "list":
            zod_type = "z.array(z.string())"
        else:
            zod_type = "z.any()"

        if not field.required:
            zod_type += ".optional()"
        field_lines.append(f"{field.name}: {zod_type},")
    return field_lines
