"""Unit tests for block-to-MDX converter."""

from src.models.content import WordPressBlock
from src.models.modeling_manifest import ComponentMapping
from src.serialization.mdx import block_to_mdx, blocks_to_mdx


def _mapping(
    wp_block_type: str = "core/paragraph",
    astro_component: str = "Paragraph",
    is_island: bool = False,
    hydration_directive: str | None = None,
    props: list[dict] | None = None,
    fallback: bool = False,
) -> ComponentMapping:
    return ComponentMapping(
        wp_block_type=wp_block_type,
        astro_component=astro_component,
        is_island=is_island,
        hydration_directive=hydration_directive,
        props=props or [],
        fallback=fallback,
    )


class TestBlockToMdxMappedComponents:
    """Mapped components generate correct MDX component references."""

    def test_simple_mapped_component(self):
        block = WordPressBlock(name="core/paragraph", attrs={}, html="<p>Hello</p>")
        mapping = _mapping()
        result = block_to_mdx(block, mapping)
        assert result == "<Paragraph />"

    def test_mapped_component_with_props(self):
        block = WordPressBlock(
            name="kadence/tabs",
            attrs={"tabCount": 3, "layout": "vertical"},
            html="<div>tabs</div>",
        )
        mapping = _mapping(
            wp_block_type="kadence/tabs",
            astro_component="KadenceTabs",
            props=[{"name": "tabCount"}, {"name": "layout"}],
        )
        result = block_to_mdx(block, mapping)
        assert 'tabCount={3}' in result
        assert 'layout="vertical"' in result
        assert result.startswith("<KadenceTabs")
        assert result.endswith("/>")

    def test_mapped_component_with_string_prop(self):
        block = WordPressBlock(
            name="core/image",
            attrs={"url": "https://example.com/img.jpg", "alt": "Photo"},
            html="<img />",
        )
        mapping = _mapping(
            wp_block_type="core/image",
            astro_component="Image",
            props=[{"name": "url"}, {"name": "alt"}],
        )
        result = block_to_mdx(block, mapping)
        assert 'url="https://example.com/img.jpg"' in result
        assert 'alt="Photo"' in result

    def test_mapped_component_with_boolean_prop(self):
        block = WordPressBlock(
            name="custom/toggle",
            attrs={"open": True},
            html="<div>toggle</div>",
        )
        mapping = _mapping(
            wp_block_type="custom/toggle",
            astro_component="Toggle",
            props=[{"name": "open"}],
        )
        result = block_to_mdx(block, mapping)
        assert "open={true}" in result

    def test_missing_prop_value_skipped(self):
        block = WordPressBlock(name="core/paragraph", attrs={}, html="<p>Hi</p>")
        mapping = _mapping(props=[{"name": "color"}])
        result = block_to_mdx(block, mapping)
        assert result == "<Paragraph />"


class TestBlockToMdxIslandComponents:
    """Island components include hydration directives."""

    def test_island_with_client_visible(self):
        block = WordPressBlock(name="geodir/map", attrs={}, html="<div>map</div>")
        mapping = _mapping(
            wp_block_type="geodir/map",
            astro_component="GeoMap",
            is_island=True,
            hydration_directive="client:visible",
        )
        result = block_to_mdx(block, mapping)
        assert result == "<GeoMap client:visible />"

    def test_island_with_client_load(self):
        block = WordPressBlock(name="forminator/form", attrs={}, html="<form></form>")
        mapping = _mapping(
            wp_block_type="forminator/form",
            astro_component="ForminatorForm",
            is_island=True,
            hydration_directive="client:load",
        )
        result = block_to_mdx(block, mapping)
        assert result == "<ForminatorForm client:load />"

    def test_island_with_props_and_directive(self):
        block = WordPressBlock(
            name="search/block",
            attrs={"placeholder": "Search..."},
            html="<div>search</div>",
        )
        mapping = _mapping(
            wp_block_type="search/block",
            astro_component="SearchBlock",
            is_island=True,
            hydration_directive="client:idle",
            props=[{"name": "placeholder"}],
        )
        result = block_to_mdx(block, mapping)
        assert "client:idle" in result
        assert 'placeholder="Search..."' in result
        assert result.startswith("<SearchBlock")

    def test_island_without_directive_no_crash(self):
        block = WordPressBlock(name="custom/widget", attrs={}, html="<div></div>")
        mapping = _mapping(
            wp_block_type="custom/widget",
            astro_component="Widget",
            is_island=True,
            hydration_directive=None,
        )
        result = block_to_mdx(block, mapping)
        assert result == "<Widget />"
        assert "client:" not in result


class TestBlockToMdxFallbackComponents:
    """Fallback components wrap raw HTML."""

    def test_fallback_wraps_html(self):
        raw_html = '<div class="wp-block-custom">Custom content</div>'
        block = WordPressBlock(name="custom/block", attrs={}, html=raw_html)
        mapping = _mapping(
            wp_block_type="custom/block",
            astro_component="FallbackComponent",
            fallback=True,
        )
        result = block_to_mdx(block, mapping)
        assert result.startswith("<FallbackComponent")
        assert "html={`" in result
        assert raw_html in result
        assert result.endswith("/>" )

    def test_fallback_escapes_backticks(self):
        raw_html = '<div>`code`</div>'
        block = WordPressBlock(name="custom/code", attrs={}, html=raw_html)
        mapping = _mapping(
            wp_block_type="custom/code",
            astro_component="FallbackComponent",
            fallback=True,
        )
        result = block_to_mdx(block, mapping)
        assert "\\`code\\`" in result


class TestBlockToMdxUnmappedBlocks:
    """Unmapped blocks fall back to markdown."""

    def test_unmapped_paragraph_uses_markdown(self):
        block = WordPressBlock(name="core/paragraph", attrs={}, html="<p>Hello world</p>")
        result = block_to_mdx(block, None)
        assert result == "Hello world"

    def test_unmapped_heading_uses_markdown(self):
        block = WordPressBlock(name="core/heading", attrs={"level": 2}, html="<h2>Title</h2>")
        result = block_to_mdx(block, None)
        assert result == "## Title"

    def test_unmapped_unknown_block_uses_raw_html(self):
        raw = '<div class="unknown">stuff</div>'
        block = WordPressBlock(name="unknown/block", attrs={}, html=raw)
        result = block_to_mdx(block, None)
        assert result == raw


class TestBlocksToMdxImports:
    """Import statements are generated for used components."""

    def test_imports_generated_for_used_components(self):
        blocks = [
            WordPressBlock(name="kadence/tabs", attrs={}, html="<div>tabs</div>"),
            WordPressBlock(name="geodir/map", attrs={}, html="<div>map</div>"),
        ]
        mappings = [
            _mapping(wp_block_type="kadence/tabs", astro_component="KadenceTabs"),
            _mapping(wp_block_type="geodir/map", astro_component="GeoMap"),
        ]
        result = blocks_to_mdx(blocks, mappings)
        assert 'import GeoMap from "../components/GeoMap.astro";' in result
        assert 'import KadenceTabs from "../components/KadenceTabs.astro";' in result

    def test_no_imports_for_unmapped_blocks(self):
        blocks = [
            WordPressBlock(name="core/paragraph", attrs={}, html="<p>Hello</p>"),
        ]
        result = blocks_to_mdx(blocks, [])
        assert "import" not in result

    def test_imports_sorted_alphabetically(self):
        blocks = [
            WordPressBlock(name="z/block", attrs={}, html="<div>z</div>"),
            WordPressBlock(name="a/block", attrs={}, html="<div>a</div>"),
        ]
        mappings = [
            _mapping(wp_block_type="z/block", astro_component="Zebra"),
            _mapping(wp_block_type="a/block", astro_component="Alpha"),
        ]
        result = blocks_to_mdx(blocks, mappings)
        lines = result.split("\n")
        import_lines = [l for l in lines if l.startswith("import")]
        assert len(import_lines) == 2
        assert "Alpha" in import_lines[0]
        assert "Zebra" in import_lines[1]

    def test_duplicate_component_imported_once(self):
        blocks = [
            WordPressBlock(name="core/paragraph", attrs={}, html="<p>One</p>"),
            WordPressBlock(name="core/paragraph", attrs={}, html="<p>Two</p>"),
        ]
        mappings = [_mapping(wp_block_type="core/paragraph", astro_component="Paragraph")]
        result = blocks_to_mdx(blocks, mappings)
        assert result.count("import Paragraph") == 1


class TestBlocksToMdxMultipleBlocks:
    """Multiple blocks produce correct output."""

    def test_mixed_mapped_and_unmapped(self):
        blocks = [
            WordPressBlock(name="kadence/tabs", attrs={}, html="<div>tabs</div>"),
            WordPressBlock(name="core/paragraph", attrs={}, html="<p>Hello</p>"),
        ]
        mappings = [
            _mapping(wp_block_type="kadence/tabs", astro_component="KadenceTabs"),
        ]
        result = blocks_to_mdx(blocks, mappings)
        # Should have import for KadenceTabs
        assert 'import KadenceTabs' in result
        # Should have the component reference
        assert "<KadenceTabs />" in result
        # Unmapped paragraph falls back to markdown
        assert "Hello" in result

    def test_blocks_separated_by_double_newlines(self):
        blocks = [
            WordPressBlock(name="a/block", attrs={}, html="<div>a</div>"),
            WordPressBlock(name="b/block", attrs={}, html="<div>b</div>"),
        ]
        mappings = [
            _mapping(wp_block_type="a/block", astro_component="A"),
            _mapping(wp_block_type="b/block", astro_component="B"),
        ]
        result = blocks_to_mdx(blocks, mappings)
        # Imports section, then body with blocks separated by \n\n
        assert "<A />" in result
        assert "<B />" in result


class TestBlocksToMdxEdgeCases:
    """Empty blocks handled gracefully."""

    def test_empty_block_list(self):
        result = blocks_to_mdx([], [])
        assert result == ""

    def test_all_empty_blocks(self):
        blocks = [
            WordPressBlock(name="core/paragraph", attrs={}, html=""),
            WordPressBlock(name="unknown/block", attrs={}, html=""),
        ]
        result = blocks_to_mdx(blocks, [])
        assert result == ""

    def test_empty_mappings_list(self):
        blocks = [
            WordPressBlock(name="core/heading", attrs={"level": 1}, html="<h1>Title</h1>"),
        ]
        result = blocks_to_mdx(blocks, [])
        assert "# Title" in result
        assert "import" not in result
