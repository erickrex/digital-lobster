from src.models.content import WordPressBlock
from src.models.modeling_manifest import ComponentMapping
from src.serialization.markdown import block_to_markdown


def _build_mapping_lookup(
    component_mappings: list[ComponentMapping],
) -> dict[str, ComponentMapping]:
    """Build a lookup dict from wp_block_type → ComponentMapping."""
    return {m.wp_block_type: m for m in component_mappings}


def _format_props(mapping: ComponentMapping, block: WordPressBlock) -> str:
    """Format component props from the mapping and block attrs.

    Each prop definition in the mapping has a 'name' key. The value is pulled
    from the block's attrs dict if present.
    """
    parts: list[str] = []
    for prop_def in mapping.props:
        name = prop_def.get("name", "")
        if not name:
            continue
        value = block.attrs.get(name)
        if value is None:
            continue
        if isinstance(value, str):
            parts.append(f'{name}="{value}"')
        elif isinstance(value, bool):
            parts.append(f"{name}={{{str(value).lower()}}}")
        else:
            parts.append(f"{name}={{{value}}}")
    return " ".join(parts)


def block_to_mdx(block: WordPressBlock, mapping: ComponentMapping | None) -> str:
    """Convert a single WordPress block to MDX.

    Args:
        block: A WordPressBlock object.
        mapping: The ComponentMapping for this block type, or None if unmapped.

    Returns:
        MDX string for the block.
    """
    if mapping is None:
        # No mapping — fall back to the markdown converter
        return block_to_markdown(block)

    component = mapping.astro_component

    if mapping.fallback:
        # Fallback component: wrap raw HTML
        escaped_html = block.html.replace("`", "\\`")
        return f"<{component} html={{`{escaped_html}`}} />"

    # Build props string
    props_str = _format_props(mapping, block)

    # Build hydration directive for island components
    directive = ""
    if mapping.is_island and mapping.hydration_directive:
        directive = f" {mapping.hydration_directive}"

    # Assemble the component tag
    parts = [f"<{component}"]
    if directive:
        parts.append(directive)
    if props_str:
        parts.append(f" {props_str}")
    parts.append(" />")

    return "".join(parts)


def blocks_to_mdx(
    blocks: list[WordPressBlock],
    component_mappings: list[ComponentMapping],
) -> str:
    """Convert a list of WordPress blocks to MDX using component mappings.

    Generates import statements at the top for all used components, then
    converts each block to its MDX representation.

    Args:
        blocks: List of WordPressBlock objects.
        component_mappings: List of ComponentMapping objects from the modeling manifest.

    Returns:
        MDX string with imports and converted blocks.
    """
    lookup = _build_mapping_lookup(component_mappings)

    # First pass: convert blocks and track which components are used
    used_components: set[str] = set()
    converted_parts: list[str] = []

    for block in blocks:
        mapping = lookup.get(block.name)
        mdx = block_to_mdx(block, mapping)
        if mdx:
            converted_parts.append(mdx)
            if mapping is not None:
                used_components.add(mapping.astro_component)

    # Generate import statements for used components
    imports: list[str] = []
    for comp in sorted(used_components):
        imports.append(f'import {comp} from "../components/{comp}.astro";')

    # Combine imports and body
    sections: list[str] = []
    if imports:
        sections.append("\n".join(imports))
    if converted_parts:
        sections.append("\n\n".join(converted_parts))

    return "\n\n".join(sections)
