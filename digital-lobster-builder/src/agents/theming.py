from __future__ import annotations

import json
import logging
import re
import time
from pathlib import PurePosixPath
from typing import Any

from src.agents.base import AgentResult, BaseAgent
from src.models.inventory import Inventory, ThemeMetadata

logger = logging.getLogger(__name__)

# CSS url() pattern for detecting asset references
_CSS_URL_RE = re.compile(r"""url\(\s*['"]?([^'")]+)['"]?\s*\)""")

# ---------------------------------------------------------------------------
# Pure helpers (no I/O, easily testable)
# ---------------------------------------------------------------------------


def _extract_inventory(context: dict[str, Any]) -> Inventory:
    """Pull the Inventory out of the pipeline context."""
    raw = context.get("inventory")
    if raw is None:
        raise KeyError("'inventory' missing from pipeline context")
    if isinstance(raw, Inventory):
        return raw
    return Inventory.model_validate(raw)


def extract_design_tokens(theme_json: dict) -> dict[str, str]:
    """Flatten a WordPress theme.json ``settings`` block into CSS custom properties.

    Returns a mapping of CSS variable name → value, e.g.
    ``{"--wp-color-primary": "#1a1a1a", ...}``.
    """
    tokens: dict[str, str] = {}
    settings = theme_json.get("settings", {})

    # Colors
    palette = settings.get("color", {}).get("palette", [])
    for entry in palette:
        slug = entry.get("slug", "")
        color = entry.get("color", "")
        if slug and color:
            tokens[f"--wp-color-{slug}"] = color

    # Typography — font sizes
    font_sizes = settings.get("typography", {}).get("fontSizes", [])
    for entry in font_sizes:
        slug = entry.get("slug", "")
        size = entry.get("size", "")
        if slug and size:
            tokens[f"--wp-font-size-{slug}"] = size

    # Typography — font families
    font_families = settings.get("typography", {}).get("fontFamilies", [])
    for entry in font_families:
        slug = entry.get("slug", "")
        family = entry.get("fontFamily", "")
        if slug and family:
            tokens[f"--wp-font-family-{slug}"] = family

    # Spacing
    spacing_sizes = settings.get("spacing", {}).get("spacingSizes", [])
    for entry in spacing_sizes:
        slug = entry.get("slug", "")
        size = entry.get("size", "")
        if slug and size:
            tokens[f"--wp-spacing-{slug}"] = size

    # Custom values (flat key-value)
    custom = settings.get("custom", {})
    _flatten_custom(custom, "--wp-custom", tokens)

    return tokens


def _flatten_custom(
    obj: Any, prefix: str, out: dict[str, str]
) -> None:
    """Recursively flatten nested custom token objects."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            _flatten_custom(val, f"{prefix}-{key}", out)
    elif isinstance(obj, (str, int, float)):
        out[prefix] = str(obj)


def generate_tokens_css(tokens: dict[str, str]) -> str:
    """Render a ``tokens.css`` file from a flat token mapping."""
    if not tokens:
        return "/* No design tokens found */\n:root {}\n"
    lines = [":root {"]
    for name, value in sorted(tokens.items()):
        lines.append(f"  {name}: {value};")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def detect_missing_css_assets(
    css_content: str,
    available_assets: set[str],
) -> list[str]:
    """Return a list of asset paths referenced in CSS but not in *available_assets*.

    Only relative paths are checked — absolute URLs (http/https/data) are
    skipped because they don't depend on local bundle files.
    """
    missing: list[str] = []
    for match in _CSS_URL_RE.finditer(css_content):
        ref = match.group(1).strip()
        # Skip absolute URLs and data URIs
        if ref.startswith(("http://", "https://", "data:", "//")):
            continue
        # Normalise the path for comparison
        normalised = str(PurePosixPath(ref))
        if normalised not in available_assets:
            missing.append(normalised)
    return missing


# ---------------------------------------------------------------------------
# Layout generation helpers
# ---------------------------------------------------------------------------

_VIEWPORT_META = '<meta name="viewport" content="width=device-width, initial-scale=1.0" />'


def _build_css_links(css_filenames: list[str]) -> str:
    """Build ``<link>`` tags for each CSS file in ``public/styles/``."""
    links: list[str] = []
    for name in sorted(css_filenames):
        links.append(f'    <link rel="stylesheet" href="/styles/{name}" />')
    return "\n".join(links)


def generate_base_layout(
    css_filenames: list[str],
    has_tokens_css: bool,
    site_name: str,
    header_html: str = "",
    footer_html: str = "",
    nav_html: str = "",
) -> str:
    """Generate ``BaseLayout.astro`` preserving DOM structure and CSS classes.

    The layout includes:
    - Responsive viewport meta tag
    - Links to all theme CSS files and tokens.css
    - Header / nav / main / footer structure derived from HTML snapshots
    """
    css_links = _build_css_links(css_filenames)
    tokens_link = ""
    if has_tokens_css:
        tokens_link = '    <link rel="stylesheet" href="/styles/tokens.css" />'

    header_block = header_html or "    <header>\n      <slot name=\"header\" />\n    </header>"
    nav_block = nav_html or "      <nav>\n        <slot name=\"nav\" />\n      </nav>"
    footer_block = footer_html or "    <footer>\n      <slot name=\"footer\" />\n    </footer>"

    return f"""---
export interface Props {{
  title?: string;
  description?: string;
}}

const {{ title = "{site_name}", description = "" }} = Astro.props;
---
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    {_VIEWPORT_META}
    <title>{{title}}</title>
    <meta name="description" content="{{description}}" />
{tokens_link}
{css_links}
  </head>
  <body>
{header_block}
{nav_block}
    <main>
      <slot />
    </main>
{footer_block}
  </body>
</html>
"""


def generate_page_layout(site_name: str) -> str:
    """Generate ``PageLayout.astro`` wrapping BaseLayout for static pages."""
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


def generate_post_layout(site_name: str) -> str:
    """Generate ``PostLayout.astro`` wrapping BaseLayout for blog posts."""
    return f"""---
import BaseLayout from "./BaseLayout.astro";

export interface Props {{
  title?: string;
  description?: string;
  date?: string;
  author?: string;
}}

const {{ title = "{site_name}", description = "", date = "", author = "" }} = Astro.props;
---
<BaseLayout title={{title}} description={{description}}>
  <article class="post-content">
    <header class="post-header">
      <h1>{{title}}</h1>
      {{date && <time datetime={{date}}>{{date}}</time>}}
      {{author && <span class="post-author">{{author}}</span>}}
    </header>
    <div class="post-body">
      <slot />
    </div>
  </article>
</BaseLayout>
"""


# ---------------------------------------------------------------------------
# HTML snapshot helpers
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(
    r"<(header|footer|nav)\b[^>]*>(.*?)</\1>",
    re.DOTALL | re.IGNORECASE,
)


def extract_snapshot_sections(html: str) -> dict[str, str]:
    """Extract ``<header>``, ``<footer>``, and ``<nav>`` blocks from an HTML snapshot.

    Returns a dict with keys ``"header"``, ``"footer"``, ``"nav"`` whose
    values are the *outer* HTML of the first matching element (or empty
    string if not found).
    """
    sections: dict[str, str] = {"header": "", "footer": "", "nav": ""}
    for match in _TAG_RE.finditer(html):
        tag = match.group(1).lower()
        if tag in sections and not sections[tag]:
            sections[tag] = match.group(0)
    return sections


# ---------------------------------------------------------------------------
# CSS breakpoint detection
# ---------------------------------------------------------------------------

_MEDIA_QUERY_RE = re.compile(r"@media\s*[^{]*\{", re.IGNORECASE)


def css_has_responsive_breakpoints(css_content: str) -> bool:
    """Return True if the CSS contains at least one ``@media`` query."""
    return bool(_MEDIA_QUERY_RE.search(css_content))


# ---------------------------------------------------------------------------
# ThemingAgent
# ---------------------------------------------------------------------------


class ThemingAgent(BaseAgent):
    """Preserves WordPress theme CSS and layout structure for Astro."""

    async def execute(self, context: dict[str, Any]) -> AgentResult:
        """Execute the Theming agent.

        Args:
            context: Must contain ``inventory`` (Inventory or dict).
                May contain ``modeling_manifest`` (dict) and
                ``export_bundle`` (dict mapping relative paths to file
                content bytes/strings inside the extracted bundle).

        Returns:
            AgentResult with artifacts:
            - ``theme_css``: dict mapping filename → CSS content
            - ``tokens_css``: CSS custom properties string (or empty)
            - ``layouts``: dict mapping layout filename → Astro content
        """
        start = time.monotonic()
        warnings: list[str] = []

        inventory = _extract_inventory(context)
        export_bundle: dict[str, Any] = context.get("export_bundle", {})

        # 1. Collect theme CSS files from the export bundle
        theme_css = self._collect_theme_css(export_bundle, warnings)

        # 2. Extract design tokens from theme.json → generate tokens.css
        tokens_css = ""
        if inventory.theme.has_theme_json:
            theme_json_raw = export_bundle.get("theme/theme.json", "{}")
            theme_json = self._parse_json_safe(theme_json_raw, "theme.json", warnings)
            tokens = extract_design_tokens(theme_json)
            tokens_css = generate_tokens_css(tokens)

        # 3. Check CSS for missing asset references
        available_assets = set(export_bundle.keys())
        for css_name, css_content in theme_css.items():
            missing = detect_missing_css_assets(css_content, available_assets)
            for asset_path in missing:
                msg = (
                    f"CSS file '{css_name}' references missing asset: "
                    f"{asset_path}"
                )
                logger.warning(msg)
                warnings.append(msg)

        # 4. Check for responsive breakpoints — warn if none found
        all_css = "\n".join(theme_css.values())
        if all_css and not css_has_responsive_breakpoints(all_css):
            warnings.append(
                "No responsive CSS breakpoints (@media queries) detected "
                "in theme CSS files."
            )

        # 5. Extract header/footer/nav from HTML snapshots
        snapshot_sections = self._extract_from_snapshots(export_bundle)

        # 6. Generate layout files
        css_filenames = list(theme_css.keys())
        has_tokens = bool(tokens_css and tokens_css.strip() != "/* No design tokens found */\n:root {}")

        layouts = {
            "BaseLayout.astro": generate_base_layout(
                css_filenames=css_filenames,
                has_tokens_css=has_tokens,
                site_name=inventory.site_name,
                header_html=snapshot_sections.get("header", ""),
                footer_html=snapshot_sections.get("footer", ""),
                nav_html=snapshot_sections.get("nav", ""),
            ),
            "PageLayout.astro": generate_page_layout(inventory.site_name),
            "PostLayout.astro": generate_post_layout(inventory.site_name),
        }

        return AgentResult(
            agent_name="theming",
            artifacts={
                "theme_css": theme_css,
                "tokens_css": tokens_css,
                "layouts": layouts,
            },
            warnings=warnings,
            duration_seconds=time.monotonic() - start,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_theme_css(
        export_bundle: dict[str, Any],
        warnings: list[str],
    ) -> dict[str, str]:
        """Gather CSS files from the ``theme/`` directory in the bundle.

        Returns a dict mapping target filename (for ``public/styles/``)
        to CSS content string.
        """
        css_files: dict[str, str] = {}
        for path, content in export_bundle.items():
            if not path.startswith("theme/") or not path.endswith(".css"):
                continue
            # Use the basename as the target filename
            filename = PurePosixPath(path).name
            if isinstance(content, bytes):
                content = content.decode("utf-8", errors="replace")
            css_files[filename] = content
        return css_files

    @staticmethod
    def _parse_json_safe(
        raw: Any, label: str, warnings: list[str]
    ) -> dict:
        """Parse JSON from a string or bytes, returning {} on failure."""
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, ValueError) as exc:
                warnings.append(f"Failed to parse {label}: {exc}")
        return {}

    @staticmethod
    def _extract_from_snapshots(
        export_bundle: dict[str, Any],
    ) -> dict[str, str]:
        """Find the first HTML snapshot and extract header/footer/nav."""
        for path, content in export_bundle.items():
            if not path.endswith(".html"):
                continue
            if isinstance(content, bytes):
                content = content.decode("utf-8", errors="replace")
            sections = extract_snapshot_sections(content)
            # Use the first snapshot that has at least one section
            if any(sections.values()):
                return sections
        return {"header": "", "footer": "", "nav": ""}
