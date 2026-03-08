from __future__ import annotations

import pytest
from unittest.mock import AsyncMock
from typing import Any

from src.agents.theming import (
    ThemingAgent,
    extract_design_tokens,
    generate_tokens_css,
    detect_missing_css_assets,
    generate_base_layout,
    generate_page_layout,
    generate_post_layout,
    extract_snapshot_sections,
    css_has_responsive_breakpoints,
    _extract_inventory,
)
from src.models.inventory import (
    Inventory,
    ThemeMetadata,
    ContentTypeSummary,
    PluginFeature,
    TaxonomySummary,
    MenuSummary,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_inventory(**overrides: Any) -> Inventory:
    defaults: dict[str, Any] = {
        "site_url": "https://example.com",
        "site_name": "Test Site",
        "wordpress_version": "6.4",
        "content_types": [
            ContentTypeSummary(
                post_type="post",
                count=10,
                custom_fields=[],
                taxonomies=["category"],
                sample_slugs=["hello-world"],
            ),
        ],
        "plugins": [],
        "taxonomies": [
            TaxonomySummary(
                taxonomy="category",
                term_count=3,
                associated_post_types=["post"],
            ),
        ],
        "menus": [
            MenuSummary(name="Primary", location="primary", item_count=5),
        ],
        "theme": ThemeMetadata(
            name="twentytwentyfour",
            has_theme_json=True,
            has_custom_css=True,
            design_tokens=None,
        ),
        "has_html_snapshots": True,
        "has_media_manifest": False,
        "has_redirect_rules": False,
        "has_seo_data": False,
    }
    defaults.update(overrides)
    return Inventory(**defaults)

def _make_gradient_client() -> AsyncMock:
    client = AsyncMock()
    client.complete = AsyncMock(return_value="{}")
    return client

def _make_theme_json(
    colors: list[dict] | None = None,
    font_sizes: list[dict] | None = None,
    font_families: list[dict] | None = None,
    spacing: list[dict] | None = None,
    custom: dict | None = None,
) -> dict:
    settings: dict[str, Any] = {}
    if colors is not None:
        settings["color"] = {"palette": colors}
    if font_sizes is not None:
        settings.setdefault("typography", {})["fontSizes"] = font_sizes
    if font_families is not None:
        settings.setdefault("typography", {})["fontFamilies"] = font_families
    if spacing is not None:
        settings["spacing"] = {"spacingSizes": spacing}
    if custom is not None:
        settings["custom"] = custom
    return {"settings": settings}

# ---------------------------------------------------------------------------
# extract_design_tokens
# ---------------------------------------------------------------------------

class TestExtractDesignTokens:
    def test_colors(self):
        tj = _make_theme_json(colors=[
            {"slug": "primary", "color": "#ff0000"},
            {"slug": "secondary", "color": "#00ff00"},
        ])
        tokens = extract_design_tokens(tj)
        assert tokens["--wp-color-primary"] == "#ff0000"
        assert tokens["--wp-color-secondary"] == "#00ff00"

    def test_font_sizes(self):
        tj = _make_theme_json(font_sizes=[
            {"slug": "small", "size": "0.875rem"},
            {"slug": "large", "size": "1.5rem"},
        ])
        tokens = extract_design_tokens(tj)
        assert tokens["--wp-font-size-small"] == "0.875rem"
        assert tokens["--wp-font-size-large"] == "1.5rem"

    def test_font_families(self):
        tj = _make_theme_json(font_families=[
            {"slug": "body", "fontFamily": "Inter, sans-serif"},
        ])
        tokens = extract_design_tokens(tj)
        assert tokens["--wp-font-family-body"] == "Inter, sans-serif"

    def test_spacing(self):
        tj = _make_theme_json(spacing=[
            {"slug": "sm", "size": "0.5rem"},
        ])
        tokens = extract_design_tokens(tj)
        assert tokens["--wp-spacing-sm"] == "0.5rem"

    def test_custom_nested(self):
        tj = _make_theme_json(custom={"line-height": {"body": "1.6", "heading": "1.2"}})
        tokens = extract_design_tokens(tj)
        assert tokens["--wp-custom-line-height-body"] == "1.6"
        assert tokens["--wp-custom-line-height-heading"] == "1.2"

    def test_empty_theme_json(self):
        tokens = extract_design_tokens({})
        assert tokens == {}

    def test_skips_entries_without_slug(self):
        tj = _make_theme_json(colors=[{"color": "#aaa"}])
        tokens = extract_design_tokens(tj)
        assert len(tokens) == 0

# ---------------------------------------------------------------------------
# generate_tokens_css
# ---------------------------------------------------------------------------

class TestGenerateTokensCss:
    def test_produces_root_block(self):
        tokens = {"--wp-color-primary": "#000"}
        css = generate_tokens_css(tokens)
        assert ":root {" in css
        assert "--wp-color-primary: #000;" in css

    def test_empty_tokens(self):
        css = generate_tokens_css({})
        assert ":root {}" in css

    def test_sorted_output(self):
        tokens = {"--b": "2", "--a": "1"}
        css = generate_tokens_css(tokens)
        a_pos = css.index("--a")
        b_pos = css.index("--b")
        assert a_pos < b_pos

# ---------------------------------------------------------------------------
# detect_missing_css_assets
# ---------------------------------------------------------------------------

class TestDetectMissingCssAssets:
    def test_detects_missing_relative_path(self):
        css = "body { background: url('../images/bg.png'); }"
        missing = detect_missing_css_assets(css, set())
        assert "../images/bg.png" in missing

    def test_ignores_absolute_urls(self):
        css = "body { background: url('https://cdn.example.com/bg.png'); }"
        missing = detect_missing_css_assets(css, set())
        assert missing == []

    def test_ignores_data_uris(self):
        css = "body { background: url('data:image/png;base64,abc'); }"
        missing = detect_missing_css_assets(css, set())
        assert missing == []

    def test_available_asset_not_reported(self):
        css = "body { background: url('images/bg.png'); }"
        missing = detect_missing_css_assets(css, {"images/bg.png"})
        assert missing == []

    def test_multiple_missing(self):
        css = (
            ".a { background: url('a.png'); }\n"
            ".b { background: url('b.png'); }"
        )
        missing = detect_missing_css_assets(css, set())
        assert "a.png" in missing
        assert "b.png" in missing

# ---------------------------------------------------------------------------
# extract_snapshot_sections
# ---------------------------------------------------------------------------

class TestExtractSnapshotSections:
    def test_extracts_header(self):
        html = '<header class="site-header"><h1>Title</h1></header>'
        sections = extract_snapshot_sections(html)
        assert "site-header" in sections["header"]

    def test_extracts_footer(self):
        html = '<footer class="site-footer">© 2024</footer>'
        sections = extract_snapshot_sections(html)
        assert "site-footer" in sections["footer"]

    def test_extracts_nav(self):
        html = '<nav class="main-nav"><a href="/">Home</a></nav>'
        sections = extract_snapshot_sections(html)
        assert "main-nav" in sections["nav"]

    def test_empty_html(self):
        sections = extract_snapshot_sections("")
        assert sections == {"header": "", "footer": "", "nav": ""}

    def test_full_page(self):
        html = (
            "<html><body>"
            '<header class="h">H</header>'
            '<nav class="n">N</nav>'
            "<main>Content</main>"
            '<footer class="f">F</footer>'
            "</body></html>"
        )
        sections = extract_snapshot_sections(html)
        assert sections["header"] != ""
        assert sections["nav"] != ""
        assert sections["footer"] != ""

# ---------------------------------------------------------------------------
# css_has_responsive_breakpoints
# ---------------------------------------------------------------------------

class TestCssHasResponsiveBreakpoints:
    def test_detects_media_query(self):
        css = "@media (max-width: 768px) { .col { width: 100%; } }"
        assert css_has_responsive_breakpoints(css) is True

    def test_no_media_query(self):
        css = "body { margin: 0; }"
        assert css_has_responsive_breakpoints(css) is False

# ---------------------------------------------------------------------------
# Layout generation
# ---------------------------------------------------------------------------

class TestGenerateBaseLayout:
    def test_contains_viewport_meta(self):
        layout = generate_base_layout([], False, "Test")
        assert '<meta name="viewport"' in layout

    def test_contains_css_links(self):
        layout = generate_base_layout(["style.css", "custom.css"], False, "Test")
        assert 'href="/styles/style.css"' in layout
        assert 'href="/styles/custom.css"' in layout

    def test_contains_tokens_link_when_present(self):
        layout = generate_base_layout([], True, "Test")
        assert 'href="/styles/tokens.css"' in layout

    def test_no_tokens_link_when_absent(self):
        layout = generate_base_layout([], False, "Test")
        assert "tokens.css" not in layout

    def test_uses_snapshot_header(self):
        header = '<header class="custom">My Header</header>'
        layout = generate_base_layout([], False, "Test", header_html=header)
        assert "custom" in layout
        assert "My Header" in layout

    def test_default_slot_when_no_snapshot(self):
        layout = generate_base_layout([], False, "Test")
        assert "<header>" in layout
        assert "<footer>" in layout

    def test_contains_main_slot(self):
        layout = generate_base_layout([], False, "Test")
        assert "<main>" in layout
        assert "<slot />" in layout

class TestGeneratePageLayout:
    def test_imports_base_layout(self):
        layout = generate_page_layout("Test")
        assert 'import BaseLayout from "./BaseLayout.astro"' in layout

    def test_contains_page_content_class(self):
        layout = generate_page_layout("Test")
        assert "page-content" in layout

class TestGeneratePostLayout:
    def test_imports_base_layout(self):
        layout = generate_post_layout("Test")
        assert 'import BaseLayout from "./BaseLayout.astro"' in layout

    def test_contains_post_header(self):
        layout = generate_post_layout("Test")
        assert "post-header" in layout

    def test_contains_post_body(self):
        layout = generate_post_layout("Test")
        assert "post-body" in layout

# ---------------------------------------------------------------------------
# _extract_inventory
# ---------------------------------------------------------------------------

class TestExtractInventory:
    def test_from_inventory_instance(self):
        inv = _make_inventory()
        result = _extract_inventory({"inventory": inv})
        assert result.site_name == "Test Site"

    def test_from_dict(self):
        inv = _make_inventory()
        result = _extract_inventory({"inventory": inv.model_dump()})
        assert result.site_name == "Test Site"

    def test_missing_key_raises(self):
        with pytest.raises(KeyError):
            _extract_inventory({})

# ---------------------------------------------------------------------------
# ThemingAgent.execute integration tests
# ---------------------------------------------------------------------------

class TestThemingAgentExecute:
    @pytest.mark.asyncio
    async def test_successful_execution(self):
        agent = ThemingAgent(gradient_client=_make_gradient_client())
        inv = _make_inventory()
        context = {
            "inventory": inv,
            "export_bundle": {
                "theme/style.css": "body { margin: 0; }",
                "theme/theme.json": '{"settings": {"color": {"palette": [{"slug": "primary", "color": "#000"}]}}}',
            },
        }
        result = await agent.execute(context)
        assert result.agent_name == "theming"
        assert "theme_css" in result.artifacts
        assert "tokens_css" in result.artifacts
        assert "layouts" in result.artifacts

    @pytest.mark.asyncio
    async def test_css_files_collected(self):
        agent = ThemingAgent(gradient_client=_make_gradient_client())
        inv = _make_inventory()
        context = {
            "inventory": inv,
            "export_bundle": {
                "theme/style.css": ".main { color: red; }",
                "theme/custom.css": ".custom { color: blue; }",
                "theme/readme.txt": "not css",
            },
        }
        result = await agent.execute(context)
        css = result.artifacts["theme_css"]
        assert "style.css" in css
        assert "custom.css" in css
        assert "readme.txt" not in css

    @pytest.mark.asyncio
    async def test_tokens_css_generated_when_theme_json_present(self):
        agent = ThemingAgent(gradient_client=_make_gradient_client())
        inv = _make_inventory(theme=ThemeMetadata(
            name="test", has_theme_json=True, has_custom_css=False, design_tokens=None,
        ))
        theme_json = {
            "settings": {
                "color": {"palette": [{"slug": "bg", "color": "#fff"}]},
            },
        }
        import json
        context = {
            "inventory": inv,
            "export_bundle": {
                "theme/theme.json": json.dumps(theme_json),
            },
        }
        result = await agent.execute(context)
        assert "--wp-color-bg" in result.artifacts["tokens_css"]

    @pytest.mark.asyncio
    async def test_no_tokens_when_no_theme_json(self):
        agent = ThemingAgent(gradient_client=_make_gradient_client())
        inv = _make_inventory(theme=ThemeMetadata(
            name="test", has_theme_json=False, has_custom_css=False, design_tokens=None,
        ))
        context = {"inventory": inv, "export_bundle": {}}
        result = await agent.execute(context)
        assert result.artifacts["tokens_css"] == ""

    @pytest.mark.asyncio
    async def test_missing_asset_warning(self):
        agent = ThemingAgent(gradient_client=_make_gradient_client())
        inv = _make_inventory()
        context = {
            "inventory": inv,
            "export_bundle": {
                "theme/style.css": "body { background: url('images/bg.png'); }",
            },
        }
        result = await agent.execute(context)
        assert any("missing asset" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_layouts_generated(self):
        agent = ThemingAgent(gradient_client=_make_gradient_client())
        inv = _make_inventory()
        context = {"inventory": inv, "export_bundle": {}}
        result = await agent.execute(context)
        layouts = result.artifacts["layouts"]
        assert "BaseLayout.astro" in layouts
        assert "PageLayout.astro" in layouts
        assert "PostLayout.astro" in layouts

    @pytest.mark.asyncio
    async def test_viewport_meta_in_base_layout(self):
        agent = ThemingAgent(gradient_client=_make_gradient_client())
        inv = _make_inventory()
        context = {"inventory": inv, "export_bundle": {}}
        result = await agent.execute(context)
        base = result.artifacts["layouts"]["BaseLayout.astro"]
        assert '<meta name="viewport"' in base

    @pytest.mark.asyncio
    async def test_html_snapshot_sections_used(self):
        agent = ThemingAgent(gradient_client=_make_gradient_client())
        inv = _make_inventory()
        context = {
            "inventory": inv,
            "export_bundle": {
                "snapshots/home.html": (
                    "<html><body>"
                    '<header class="wp-header">Logo</header>'
                    '<nav class="wp-nav"><a href="/">Home</a></nav>'
                    "<main>Content</main>"
                    '<footer class="wp-footer">© 2024</footer>'
                    "</body></html>"
                ),
            },
        }
        result = await agent.execute(context)
        base = result.artifacts["layouts"]["BaseLayout.astro"]
        assert "wp-header" in base
        assert "wp-nav" in base
        assert "wp-footer" in base

    @pytest.mark.asyncio
    async def test_duration_recorded(self):
        agent = ThemingAgent(gradient_client=_make_gradient_client())
        inv = _make_inventory()
        context = {"inventory": inv, "export_bundle": {}}
        result = await agent.execute(context)
        assert result.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_inventory_from_dict(self):
        agent = ThemingAgent(gradient_client=_make_gradient_client())
        inv = _make_inventory()
        context = {"inventory": inv.model_dump(), "export_bundle": {}}
        result = await agent.execute(context)
        assert result.agent_name == "theming"

    @pytest.mark.asyncio
    async def test_bytes_css_content(self):
        agent = ThemingAgent(gradient_client=_make_gradient_client())
        inv = _make_inventory()
        context = {
            "inventory": inv,
            "export_bundle": {
                "theme/style.css": b"body { margin: 0; }",
            },
        }
        result = await agent.execute(context)
        assert "style.css" in result.artifacts["theme_css"]
        assert result.artifacts["theme_css"]["style.css"] == "body { margin: 0; }"

    @pytest.mark.asyncio
    async def test_malformed_theme_json_produces_warning(self):
        agent = ThemingAgent(gradient_client=_make_gradient_client())
        inv = _make_inventory(theme=ThemeMetadata(
            name="test", has_theme_json=True, has_custom_css=False, design_tokens=None,
        ))
        context = {
            "inventory": inv,
            "export_bundle": {
                "theme/theme.json": "not valid json {{{",
            },
        }
        result = await agent.execute(context)
        assert any("Failed to parse" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_no_responsive_breakpoints_warning(self):
        agent = ThemingAgent(gradient_client=_make_gradient_client())
        inv = _make_inventory()
        context = {
            "inventory": inv,
            "export_bundle": {
                "theme/style.css": "body { margin: 0; }",
            },
        }
        result = await agent.execute(context)
        assert any("breakpoints" in w.lower() for w in result.warnings)

    @pytest.mark.asyncio
    async def test_css_link_in_base_layout(self):
        agent = ThemingAgent(gradient_client=_make_gradient_client())
        inv = _make_inventory()
        context = {
            "inventory": inv,
            "export_bundle": {
                "theme/style.css": "body { margin: 0; }",
            },
        }
        result = await agent.execute(context)
        base = result.artifacts["layouts"]["BaseLayout.astro"]
        assert 'href="/styles/style.css"' in base
