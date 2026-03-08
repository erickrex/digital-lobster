from __future__ import annotations

import logging
import re
from typing import Any

from src.adapters.base import PluginAdapter, RenderingContribution
from src.adapters.registry import build_adapter_registry, default_adapters
from src.agents.base import AgentResult, BaseAgent
from src.models.bundle_artifacts import PageCompositionEntry
from src.models.bundle_manifest import BundleManifest
from src.models.capability_manifest import CapabilityManifest
from src.models.finding import Finding, FindingSeverity
from src.models.presentation_manifest import (
    FallbackZone,
    LayoutDefinition,
    PresentationManifest,
    RouteTemplate,
    SectionDefinition,
)
from src.pipeline_context import extract_bundle_manifest, extract_capability_manifest

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    """Convert a display name to a URL-safe slug (lowercase, hyphens)."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "unnamed"

def _template_to_layout_name(template: str) -> str:
    """Derive a layout name from a WordPress template identifier."""
    # Strip file extensions and path prefixes
    name = template.rsplit("/", 1)[-1]
    name = name.rsplit(".", 1)[0]
    return _slugify(name)

# ---------------------------------------------------------------------------
# Supported source types for sections
# ---------------------------------------------------------------------------

_SUPPORTED_SECTION_SOURCE_TYPES = {"widget", "sidebar", "block", "plugin_component"}

# Block types that have known Astro component mappings via adapters
_ADAPTER_SUPPORTED_BLOCK_TYPES: set[str] = set()

class PresentationCompilerAgent(BaseAgent):
    """Produces the Presentation_Manifest from capability and bundle data.

    Deterministically compiles:
    - Layouts from page templates and theme data
    - Route templates from page composition pages
    - Sections from widgets, sidebars, blocks, and plugin components
    - Fallback zones for unsupported presentational fragments
    - Style tokens from theme_mods, global_styles, css_sources
    - Plugin rendering contributions via adapter rendering_strategy
    """
    def __init__(
        self,
        gradient_client: Any,
        kb_client: Any = None,
        adapters: list[PluginAdapter] | None = None,
    ) -> None:
        super().__init__(gradient_client, kb_client)
        self._adapters = build_adapter_registry(adapters or default_adapters())

    async def execute(self, context: dict[str, Any]) -> AgentResult:
        capability_manifest = extract_capability_manifest(context)
        bundle_manifest = extract_bundle_manifest(context)

        logger.info("Starting presentation compilation for %s", bundle_manifest.site_url)

        findings: list[Finding] = []

        layouts = self._compile_layouts(capability_manifest, bundle_manifest)
        route_templates = self._compile_route_templates(bundle_manifest)
        sections = self._compile_sections(capability_manifest, bundle_manifest)
        fallback_zones = self._compile_fallback_zones(capability_manifest, bundle_manifest, findings)
        style_tokens = self._compile_style_tokens(bundle_manifest)

        # Merge plugin adapter rendering contributions
        plugin_contributions = self._compile_plugin_contributions(capability_manifest)
        for contrib in plugin_contributions:
            sections.extend(contrib.sections)
            fallback_zones.extend(contrib.fallback_zones)

        # Sort all outputs for determinism (Requirement 15.4)
        layouts.sort(key=lambda l: l.name)
        route_templates.sort(key=lambda r: r.route_pattern)
        sections.sort(key=lambda s: (s.source_type, s.name))
        fallback_zones.sort(key=lambda f: (f.page_url, f.zone_name))

        manifest = PresentationManifest(
            layouts=layouts,
            route_templates=route_templates,
            sections=sections,
            fallback_zones=fallback_zones,
            style_tokens=style_tokens,
            findings=findings,
        )

        logger.info(
            "Presentation compilation complete for %s: %d layouts, %d routes, %d sections, %d fallbacks, %d findings",
            bundle_manifest.site_url,
            len(layouts),
            len(route_templates),
            len(sections),
            len(fallback_zones),
            len(findings),
        )

        return AgentResult(
            agent_name="presentation_compiler",
            artifacts={"presentation_manifest": manifest},
        )

    # ------------------------------------------------------------------
    # Layout compilation
    # ------------------------------------------------------------------

    def _compile_layouts(
        self,
        capability_manifest: CapabilityManifest,
        bundle_manifest: BundleManifest,
    ) -> list[LayoutDefinition]:
        """Build LayoutDefinitions from page templates and theme data.

        Each unique WordPress page template becomes an Astro layout.
        """
        templates: set[str] = set()

        # Collect templates from page_templates artifact
        for tpl_name in bundle_manifest.page_templates.get("templates", {}):
            templates.add(tpl_name)

        # Also collect templates referenced in page_composition
        for page in bundle_manifest.page_composition.pages:
            if page.template:
                templates.add(page.template)

        # Collect from presentation capabilities
        for cap in capability_manifest.presentation_capabilities:
            tpl = cap.details.get("template")
            if tpl:
                templates.add(tpl)

        # Extract shared section names from widget areas
        widget_areas = self._extract_widget_area_names(bundle_manifest)

        layouts: list[LayoutDefinition] = []
        for template in templates:
            layout_name = _template_to_layout_name(template)
            template_path = f"src/layouts/{layout_name}.astro"

            # Determine which shared sections this layout uses
            shared_sections = self._resolve_shared_sections(
                template, bundle_manifest, widget_areas
            )

            # Extract style tokens relevant to this layout from theme data
            layout_tokens = self._extract_layout_tokens(template, bundle_manifest)

            layouts.append(
                LayoutDefinition(
                    name=layout_name,
                    template_path=template_path,
                    shared_sections=sorted(shared_sections),
                    style_tokens=layout_tokens,
                )
            )

        # Ensure a default layout exists
        if not any(l.name == "default" for l in layouts):
            layouts.append(
                LayoutDefinition(
                    name="default",
                    template_path="src/layouts/default.astro",
                    shared_sections=sorted(widget_areas),
                    style_tokens={},
                )
            )

        return layouts

    @staticmethod
    def _extract_widget_area_names(bundle_manifest: BundleManifest) -> list[str]:
        """Extract widget area/sidebar names from the widgets artifact."""
        areas: set[str] = set()
        sidebars = bundle_manifest.widgets.get("sidebars", [])
        if isinstance(sidebars, list):
            for sidebar in sidebars:
                if isinstance(sidebar, dict) and "id" in sidebar:
                    areas.add(sidebar["id"])
        elif isinstance(sidebars, dict):
            areas.update(sidebars.keys())
        return sorted(areas)

    @staticmethod
    def _resolve_shared_sections(
        template: str,
        bundle_manifest: BundleManifest,
        widget_areas: list[str],
    ) -> list[str]:
        """Determine which shared sections (widget areas) a template uses.

        Pages using this template are inspected for widget_placements to
        determine which widget areas are active.
        """
        sections: set[str] = set()
        for page in bundle_manifest.page_composition.pages:
            if page.template != template:
                continue
            for placement in page.widget_placements:
                area = placement.get("sidebar_id") or placement.get("area")
                if area:
                    sections.add(area)

        # If no specific placements found, include all widget areas as shared
        if not sections:
            sections.update(widget_areas)

        return sorted(sections)

    @staticmethod
    def _extract_layout_tokens(
        template: str,
        bundle_manifest: BundleManifest,
    ) -> dict[str, str]:
        """Extract style tokens relevant to a specific layout template."""
        tokens: dict[str, str] = {}
        # Pull template-specific tokens from global_styles if available
        template_styles = bundle_manifest.global_styles.get("templates", {})
        if isinstance(template_styles, dict):
            tpl_tokens = template_styles.get(template, {})
            if isinstance(tpl_tokens, dict):
                for key, value in sorted(tpl_tokens.items()):
                    tokens[str(key)] = str(value)
        return tokens

    # ------------------------------------------------------------------
    # Route template compilation
    # ------------------------------------------------------------------

    def _compile_route_templates(
        self,
        bundle_manifest: BundleManifest,
    ) -> list[RouteTemplate]:
        """Build RouteTemplates from page_composition pages.

        Each page in the composition map produces a route template with
        route_pattern, layout, source_template, and content_collection.
        """
        seen_patterns: set[str] = set()
        route_templates: list[RouteTemplate] = []

        for page in bundle_manifest.page_composition.pages:
            route_pattern = self._url_to_route_pattern(page.canonical_url)

            # Deduplicate: same route pattern should not appear twice
            if route_pattern in seen_patterns:
                continue
            seen_patterns.add(route_pattern)

            layout_name = _template_to_layout_name(page.template) if page.template else "default"

            # Infer content collection from the page's content sections
            content_collection = self._infer_content_collection(page)

            route_templates.append(
                RouteTemplate(
                    route_pattern=route_pattern,
                    layout=layout_name,
                    source_template=page.template or "default",
                    content_collection=content_collection,
                )
            )

        return route_templates

    @staticmethod
    def _url_to_route_pattern(canonical_url: str) -> str:
        """Convert a canonical URL to an Astro route pattern.

        Examples:
            https://example.com/about/ → /about
            https://example.com/blog/my-post/ → /blog/[slug]
            https://example.com/ → /
        """
        from urllib.parse import urlparse

        parsed = urlparse(canonical_url)
        path = parsed.path.rstrip("/") or "/"

        # If the path has multiple segments, parameterize the last segment
        parts = [p for p in path.split("/") if p]
        if len(parts) > 1:
            return "/" + "/".join(parts[:-1]) + "/[slug]"
        elif len(parts) == 1:
            return "/" + parts[0]
        return "/"

    @staticmethod
    def _infer_content_collection(page: PageCompositionEntry) -> str | None:
        """Infer the Strapi content collection for a page from its composition."""
        # Look for content_type hints in content_sections
        for section in page.content_sections:
            ct = section.get("content_type") or section.get("post_type")
            if ct:
                return ct

        # Fall back to template-based inference
        template = page.template or ""
        if "single" in template.lower():
            return "posts"
        if "page" in template.lower():
            return "pages"

        return None

    # ------------------------------------------------------------------
    # Section compilation
    # ------------------------------------------------------------------

    def _compile_sections(
        self,
        capability_manifest: CapabilityManifest,
        bundle_manifest: BundleManifest,
    ) -> list[SectionDefinition]:
        """Build SectionDefinitions from widgets, sidebars, blocks, and plugin components.

        Maps widget placements and sidebar content to Astro section components.
        """
        sections: list[SectionDefinition] = []
        seen_names: set[str] = set()

        # 1. Widget placements → sections
        for page in bundle_manifest.page_composition.pages:
            for placement in page.widget_placements:
                section = self._widget_placement_to_section(placement)
                if section and section.name not in seen_names:
                    seen_names.add(section.name)
                    sections.append(section)

        # 2. Sidebar definitions → sections
        sidebars = bundle_manifest.widgets.get("sidebars", [])
        if isinstance(sidebars, list):
            for sidebar in sidebars:
                if isinstance(sidebar, dict):
                    name = sidebar.get("id", sidebar.get("name", ""))
                    if name and name not in seen_names:
                        seen_names.add(name)
                        sections.append(
                            SectionDefinition(
                                name=_slugify(name),
                                source_type="sidebar",
                                component_path=f"src/components/sections/{_slugify(name)}.astro",
                                props={"sidebar_id": name},
                            )
                        )

        # 3. Block types from page composition → sections
        for page in bundle_manifest.page_composition.pages:
            for block in page.blocks:
                block_name = block.get("blockName") or block.get("name", "")
                if not block_name:
                    continue
                section_name = _slugify(block_name)
                if section_name not in seen_names:
                    seen_names.add(section_name)
                    sections.append(
                        SectionDefinition(
                            name=section_name,
                            source_type="block",
                            source_plugin=block.get("source_plugin"),
                            component_path=f"src/components/blocks/{section_name}.astro",
                            props={k: v for k, v in sorted(block.items()) if k not in ("blockName", "name", "source_plugin", "innerHTML", "innerContent")},
                        )
                    )

        # 4. Plugin components from page composition → sections
        for page in bundle_manifest.page_composition.pages:
            for comp in page.plugin_components:
                comp_name = comp.get("name") or comp.get("type", "")
                if not comp_name:
                    continue
                section_name = _slugify(comp_name)
                if section_name not in seen_names:
                    seen_names.add(section_name)
                    sections.append(
                        SectionDefinition(
                            name=section_name,
                            source_type="plugin_component",
                            source_plugin=comp.get("source_plugin"),
                            component_path=f"src/components/plugins/{section_name}.astro",
                            props={k: v for k, v in sorted(comp.items()) if k not in ("name", "type", "source_plugin")},
                        )
                    )

        return sections

    @staticmethod
    def _widget_placement_to_section(
        placement: dict[str, Any],
    ) -> SectionDefinition | None:
        """Convert a single widget placement dict to a SectionDefinition."""
        widget_type = placement.get("widget_type") or placement.get("type", "")
        widget_id = placement.get("widget_id") or placement.get("id", "")
        if not widget_type and not widget_id:
            return None

        name = _slugify(widget_type or widget_id)
        return SectionDefinition(
            name=name,
            source_type="widget",
            source_plugin=placement.get("source_plugin"),
            component_path=f"src/components/widgets/{name}.astro",
            props={
                k: v
                for k, v in sorted(placement.items())
                if k not in ("widget_type", "type", "widget_id", "id", "source_plugin")
            },
        )

    # ------------------------------------------------------------------
    # Fallback zone compilation
    # ------------------------------------------------------------------

    def _compile_fallback_zones(
        self,
        capability_manifest: CapabilityManifest,
        bundle_manifest: BundleManifest,
        findings: list[Finding],
    ) -> list[FallbackZone]:
        """Generate FallbackZones for unsupported presentational fragments.

        Blocks, shortcodes, and plugin components without adapter support
        get a fallback zone with raw_html placeholder and reason, rather
        than being silently dropped (Requirement 15.5).  Each fallback
        also produces a Finding (Requirement 24.1, 24.3).
        """
        fallback_zones: list[FallbackZone] = []
        seen: set[tuple[str, str]] = set()

        # Collect supported plugin families from adapters
        supported_families = set(self._adapters.keys())

        for page in bundle_manifest.page_composition.pages:
            # Unsupported shortcodes → fallback zones
            for shortcode in page.shortcodes:
                tag = shortcode.get("tag") or shortcode.get("name", "unknown")
                source_plugin = shortcode.get("source_plugin")

                if source_plugin and source_plugin in supported_families:
                    continue

                zone_key = (page.canonical_url, f"shortcode-{tag}")
                if zone_key in seen:
                    continue
                seen.add(zone_key)

                raw_html = shortcode.get("raw_html", shortcode.get("content", f"[{tag}]"))
                reason = (
                    f"Shortcode '{tag}' has no adapter support"
                    + (f" (plugin: {source_plugin})" if source_plugin else "")
                )
                fallback_zones.append(
                    FallbackZone(
                        page_url=page.canonical_url,
                        zone_name=f"shortcode-{tag}",
                        raw_html=str(raw_html),
                        reason=reason,
                    )
                )
                findings.append(Finding(
                    severity=FindingSeverity.WARNING,
                    stage="presentation_compiler",
                    construct=f"shortcode:{tag}",
                    message=reason,
                    recommended_action="Implement custom Astro component or remove shortcode",
                ))

            # Unsupported blocks → fallback zones
            for block in page.blocks:
                block_name = block.get("blockName") or block.get("name", "")
                source_plugin = block.get("source_plugin")

                if not block_name:
                    continue

                # Core blocks and adapter-supported blocks are not fallbacks
                if block_name.startswith("core/"):
                    continue
                if source_plugin and source_plugin in supported_families:
                    continue

                zone_key = (page.canonical_url, f"block-{block_name}")
                if zone_key in seen:
                    continue
                seen.add(zone_key)

                raw_html = block.get("innerHTML", block.get("innerContent", ""))
                if isinstance(raw_html, list):
                    raw_html = "".join(str(part) for part in raw_html if part)
                reason = (
                    f"Block '{block_name}' has no adapter support"
                    + (f" (plugin: {source_plugin})" if source_plugin else "")
                )
                fallback_zones.append(
                    FallbackZone(
                        page_url=page.canonical_url,
                        zone_name=f"block-{block_name}",
                        raw_html=str(raw_html),
                        reason=reason,
                    )
                )
                findings.append(Finding(
                    severity=FindingSeverity.WARNING,
                    stage="presentation_compiler",
                    construct=f"block:{block_name}",
                    message=reason,
                    recommended_action="Implement custom Astro component or replace block",
                ))

            # Unsupported plugin components → fallback zones
            for comp in page.plugin_components:
                comp_name = comp.get("name") or comp.get("type", "")
                source_plugin = comp.get("source_plugin")

                if not comp_name:
                    continue
                if source_plugin and source_plugin in supported_families:
                    continue

                zone_key = (page.canonical_url, f"plugin-{comp_name}")
                if zone_key in seen:
                    continue
                seen.add(zone_key)

                raw_html = comp.get("raw_html", comp.get("content", ""))
                reason = (
                    f"Plugin component '{comp_name}' has no adapter support"
                    + (f" (plugin: {source_plugin})" if source_plugin else "")
                )
                fallback_zones.append(
                    FallbackZone(
                        page_url=page.canonical_url,
                        zone_name=f"plugin-{comp_name}",
                        raw_html=str(raw_html),
                        reason=reason,
                    )
                )
                findings.append(Finding(
                    severity=FindingSeverity.WARNING,
                    stage="presentation_compiler",
                    construct=f"plugin_component:{comp_name}",
                    message=reason,
                    recommended_action="Implement custom Astro component or remove plugin component",
                ))

        return fallback_zones

    # ------------------------------------------------------------------
    # Style token compilation
    # ------------------------------------------------------------------

    def _compile_style_tokens(
        self,
        bundle_manifest: BundleManifest,
    ) -> dict[str, str]:
        """Compile style tokens from theme_mods, global_styles, and css_sources.

        Produces a flat dict of token_name → token_value for use in
        Astro CSS custom properties.
        """
        tokens: dict[str, str] = {}

        # 1. Theme mods → tokens
        self._extract_theme_mod_tokens(bundle_manifest.theme_mods, tokens)

        # 2. Global styles → tokens
        self._extract_global_style_tokens(bundle_manifest.global_styles, tokens)

        # 3. CSS sources → tokens (custom properties from stylesheets)
        self._extract_css_source_tokens(bundle_manifest.css_sources, tokens)

        # Sort for determinism
        return dict(sorted(tokens.items()))

    @staticmethod
    def _extract_theme_mod_tokens(
        theme_mods: dict[str, Any],
        tokens: dict[str, str],
    ) -> None:
        """Extract style tokens from theme_mods data."""
        color_keys = [
            "background_color", "header_textcolor", "accent_color",
            "link_color", "text_color",
        ]
        for key in color_keys:
            value = theme_mods.get(key)
            if value and isinstance(value, str):
                tokens[f"--theme-{key.replace('_', '-')}"] = value

        # Custom CSS if present
        custom_css = theme_mods.get("custom_css")
        if custom_css and isinstance(custom_css, str):
            tokens["--theme-has-custom-css"] = "true"

    @staticmethod
    def _extract_global_style_tokens(
        global_styles: dict[str, Any],
        tokens: dict[str, str],
    ) -> None:
        """Extract style tokens from global_styles (block theme styles)."""
        settings = global_styles.get("settings", {})
        if not isinstance(settings, dict):
            return

        # Color palette
        palette = settings.get("color", {})
        if isinstance(palette, dict):
            for entry in palette.get("palette", []):
                if isinstance(entry, dict) and "slug" in entry and "color" in entry:
                    tokens[f"--wp-preset-color-{entry['slug']}"] = str(entry["color"])

        # Typography
        typography = settings.get("typography", {})
        if isinstance(typography, dict):
            for font in typography.get("fontFamilies", []):
                if isinstance(font, dict) and "slug" in font and "fontFamily" in font:
                    tokens[f"--wp-preset-font-family-{font['slug']}"] = str(font["fontFamily"])

            for size in typography.get("fontSizes", []):
                if isinstance(size, dict) and "slug" in size and "size" in size:
                    tokens[f"--wp-preset-font-size-{size['slug']}"] = str(size["size"])

        # Spacing
        spacing = settings.get("spacing", {})
        if isinstance(spacing, dict):
            for sp in spacing.get("spacingSizes", []):
                if isinstance(sp, dict) and "slug" in sp and "size" in sp:
                    tokens[f"--wp-preset-spacing-{sp['slug']}"] = str(sp["size"])

    @staticmethod
    def _extract_css_source_tokens(
        css_sources: dict[str, Any],
        tokens: dict[str, str],
    ) -> None:
        """Extract CSS custom property tokens from css_sources artifact."""
        custom_properties = css_sources.get("custom_properties", {})
        if isinstance(custom_properties, dict):
            for prop_name, prop_value in sorted(custom_properties.items()):
                # Normalize property names to use -- prefix
                key = prop_name if prop_name.startswith("--") else f"--{prop_name}"
                tokens[key] = str(prop_value)

    # ------------------------------------------------------------------
    # Plugin adapter rendering contributions
    # ------------------------------------------------------------------

    def _compile_plugin_contributions(
        self,
        capability_manifest: CapabilityManifest,
    ) -> list[RenderingContribution]:
        """Delegate to plugin adapters for rendering contributions."""
        contributions: list[RenderingContribution] = []

        for family, caps in capability_manifest.plugin_capabilities.items():
            adapter = self._adapters.get(family)
            if adapter is None:
                continue
            contrib = adapter.rendering_strategy(caps)
            if contrib.sections or contrib.fallback_zones:
                contributions.append(contrib)
                logger.info(
                    "Plugin adapter '%s' contributed %d sections, %d fallback zones",
                    family,
                    len(contrib.sections),
                    len(contrib.fallback_zones),
                )

        return contributions
