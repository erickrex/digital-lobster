from __future__ import annotations

import logging
import time
from typing import Any

from src.agents.base import AgentResult, BaseAgent
from src.models.inventory import Inventory

logger = logging.getLogger(__name__)

# Hard ceiling for the PRD document.
MAX_WORDS = 1500

# Required sections that must appear in every generated PRD.
REQUIRED_SECTIONS = (
    "goals",
    "non-goals",
    "information architecture",
    "sitemap",
    "theming mode",
    "seo scope",
    "acceptance metrics",
)


def _build_system_prompt() -> str:
    """Return the system prompt that instructs the LLM on PRD format."""
    return (
        "You are a senior technical writer producing a concise PRD (Product "
        "Requirements Document) for a WordPress-to-Astro JS 5 migration.\n\n"
        "The PRD MUST contain exactly these sections as markdown headings:\n"
        "## Goals\n"
        "## Non-Goals\n"
        "## Information Architecture\n"
        "## Sitemap\n"
        "## Theming Mode\n"
        "## SEO Scope\n"
        "## Acceptance Metrics\n"
        "## Impact Metrics\n\n"
        "Rules:\n"
        "- The entire document MUST be 1500 words or fewer.\n"
        "- In the Information Architecture section, list EVERY custom post "
        "type with its proposed Astro content collection name and route "
        "pattern (e.g., `places` → collection `places`, route `/places/[slug]`).\n"
        "- The Impact Metrics section MUST state: baseline 30–60 engineer "
        "hours, target approximately 2 hours.\n"
        "- Use markdown formatting. Be specific and actionable.\n"
        "- Do NOT include a title heading — the caller adds that.\n"
    )


def _build_user_prompt(
    inventory: Inventory,
    kb_context: list[dict],
) -> str:
    """Build the user prompt from inventory data and KB retrieval results."""
    lines: list[str] = []

    lines.append("Generate a PRD.md for migrating the following WordPress site to Astro JS 5.\n")

    # Site basics
    lines.append(f"Site: {inventory.site_name} ({inventory.site_url})")
    lines.append(f"WordPress version: {inventory.wordpress_version}\n")

    # Content types
    lines.append("Content types:")
    for ct in inventory.content_types:
        fields_str = ", ".join(ct.custom_fields[:10]) if ct.custom_fields else "none"
        lines.append(
            f"  - {ct.post_type} ({ct.count} items, fields: {fields_str}, "
            f"taxonomies: {', '.join(ct.taxonomies) or 'none'})"
        )

    # Plugins
    if inventory.plugins:
        lines.append("\nDetected plugins:")
        for p in inventory.plugins:
            family_tag = f" [{p.family}]" if p.family else ""
            lines.append(f"  - {p.name} v{p.version}{family_tag}")

    # Taxonomies
    if inventory.taxonomies:
        lines.append("\nTaxonomies:")
        for t in inventory.taxonomies:
            lines.append(
                f"  - {t.taxonomy} ({t.term_count} terms, "
                f"post types: {', '.join(t.associated_post_types)})"
            )

    # Menus
    if inventory.menus:
        lines.append("\nMenus:")
        for m in inventory.menus:
            lines.append(f"  - {m.name} ({m.item_count} items, location: {m.location})")

    # Theme
    lines.append(f"\nTheme: {inventory.theme.name}")
    lines.append(f"  has_theme_json: {inventory.theme.has_theme_json}")
    lines.append(f"  has_custom_css: {inventory.theme.has_custom_css}")

    # Flags
    flags = []
    if inventory.has_html_snapshots:
        flags.append("HTML snapshots available")
    if inventory.has_media_manifest:
        flags.append("media manifest available")
    if inventory.has_redirect_rules:
        flags.append("redirect rules available")
    if inventory.has_seo_data:
        flags.append("SEO data available")
    if flags:
        lines.append(f"\nAdditional data: {', '.join(flags)}")

    # KB context
    if kb_context:
        lines.append("\n--- Additional context from Knowledge Base ---")
        for doc in kb_context:
            content = doc.get("content", "")
            # Truncate long KB results to keep prompt manageable
            if len(content) > 800:
                content = content[:800] + "…"
            lines.append(content)

    return "\n".join(lines)


def _count_words(text: str) -> int:
    """Count words in a text string."""
    return len(text.split())


def _validate_sections(prd_md: str) -> list[str]:
    """Check that all required sections are present in the PRD.

    Returns a list of missing section names (empty if all present).
    """
    lower = prd_md.lower()
    missing: list[str] = []
    for section in REQUIRED_SECTIONS:
        # Look for the section as a markdown heading
        if f"## {section}" not in lower:
            missing.append(section)
    return missing


def _extract_inventory(context: dict[str, Any]) -> Inventory:
    """Extract an Inventory from the pipeline context.

    Accepts either an ``Inventory`` instance or a dict (which gets
    validated into one).
    """
    raw = context["inventory"]
    if isinstance(raw, Inventory):
        return raw
    return Inventory.model_validate(raw)


class PrdLiteAgent(BaseAgent):
    """Generates a concise PRD.md from the Inventory and Knowledge Base."""

    async def execute(self, context: dict[str, Any]) -> AgentResult:
        """Execute the PRD-Lite agent.

        Args:
            context: Must contain ``inventory`` (Inventory or dict) and
                optionally ``kb_ref`` (Knowledge Base ID string).

        Returns:
            AgentResult with a ``prd_md`` artifact containing the PRD
            markdown string.
        """
        start = time.monotonic()
        warnings: list[str] = []

        inventory = _extract_inventory(context)
        kb_ref: str | None = context.get("kb_ref")

        # 1. Query Knowledge Base for additional context
        kb_context = await self._query_kb(kb_ref, inventory, warnings)

        # 2. Build prompts
        system_prompt = _build_system_prompt()
        user_prompt = _build_user_prompt(inventory, kb_context)

        # 3. Call LLM to generate the PRD
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        prd_body = await self.gradient_client.complete(messages)

        # 4. Prepend title
        prd_md = f"# PRD — {inventory.site_name} Migration\n\n{prd_body}"

        # 5. Validate required sections
        missing = _validate_sections(prd_md)
        if missing:
            warnings.append(
                f"PRD missing sections: {', '.join(missing)}. "
                "Attempting regeneration."
            )
            prd_md, prd_body = await self._regenerate_with_fixes(
                messages, prd_body, missing, inventory, warnings
            )

        # 6. Enforce word limit
        word_count = _count_words(prd_md)
        if word_count > MAX_WORDS:
            warnings.append(
                f"PRD exceeds word limit ({word_count} > {MAX_WORDS}). "
                "Requesting condensed version."
            )
            prd_md = await self._condense(prd_md, inventory, warnings)

        return AgentResult(
            agent_name="prd_lite",
            artifacts={"prd_md": prd_md},
            warnings=warnings,
            duration_seconds=time.monotonic() - start,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _query_kb(
        self,
        kb_ref: str | None,
        inventory: Inventory,
        warnings: list[str],
    ) -> list[dict]:
        """Query the Knowledge Base for site metadata and plugin features."""
        if not kb_ref or not self.kb_client:
            return []

        queries = [
            "site metadata and configuration",
            "plugin features and capabilities",
            "content type summaries and custom post types",
        ]

        results: list[dict] = []
        for q in queries:
            try:
                docs = await self.kb_client.query(kb_ref, q, top_k=3)
                results.extend(docs)
            except Exception as exc:
                logger.warning("KB query failed for '%s': %s", q, exc)
                warnings.append(f"KB query failed: {q} — {exc}")

        return results

    async def _regenerate_with_fixes(
        self,
        original_messages: list[dict],
        prd_body: str,
        missing: list[str],
        inventory: Inventory,
        warnings: list[str],
    ) -> tuple[str, str]:
        """Ask the LLM to fix missing sections in the PRD."""
        fix_prompt = (
            f"The PRD you generated is missing these required sections: "
            f"{', '.join(missing)}.\n\n"
            "Please regenerate the COMPLETE PRD with ALL required sections "
            "included. Keep it under 1500 words.\n\n"
            f"Here is your previous output for reference:\n{prd_body}"
        )
        messages = [
            *original_messages,
            {"role": "assistant", "content": prd_body},
            {"role": "user", "content": fix_prompt},
        ]
        new_body = await self.gradient_client.complete(messages)
        new_prd = f"# PRD — {inventory.site_name} Migration\n\n{new_body}"

        still_missing = _validate_sections(new_prd)
        if still_missing:
            warnings.append(
                f"PRD still missing sections after retry: "
                f"{', '.join(still_missing)}"
            )

        return new_prd, new_body

    async def _condense(
        self,
        prd_md: str,
        inventory: Inventory,
        warnings: list[str],
    ) -> str:
        """Ask the LLM to shorten the PRD to fit the word limit."""
        condense_prompt = (
            "The following PRD exceeds the 1500-word limit. "
            "Please condense it to 1500 words or fewer while keeping "
            "ALL required sections and all custom post type entries.\n\n"
            f"{prd_md}"
        )
        messages = [
            {"role": "system", "content": _build_system_prompt()},
            {"role": "user", "content": condense_prompt},
        ]
        condensed_body = await self.gradient_client.complete(messages)
        condensed = f"# PRD — {inventory.site_name} Migration\n\n{condensed_body}"

        word_count = _count_words(condensed)
        if word_count > MAX_WORDS:
            warnings.append(
                f"PRD still over limit after condensing ({word_count} words)."
            )

        return condensed
