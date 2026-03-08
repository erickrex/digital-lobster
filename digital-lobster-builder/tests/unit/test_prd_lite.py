from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.agents.prd_lite import (
    MAX_WORDS,
    REQUIRED_SECTIONS,
    PrdLiteAgent,
    _build_system_prompt,
    _build_user_prompt,
    _count_words,
    _extract_inventory,
    _validate_sections,
)
from src.models.inventory import (
    ContentTypeSummary,
    Inventory,
    MenuSummary,
    PluginFeature,
    TaxonomySummary,
    ThemeMetadata,
)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


def _make_inventory(**overrides: Any) -> Inventory:
    """Build a minimal Inventory with optional overrides."""
    defaults: dict[str, Any] = {
        "site_url": "https://example.com",
        "site_name": "Example Site",
        "wordpress_version": "6.4",
        "content_types": [
            ContentTypeSummary(
                post_type="post",
                count=50,
                custom_fields=["author_bio"],
                taxonomies=["category", "post_tag"],
                sample_slugs=["hello-world"],
            ),
            ContentTypeSummary(
                post_type="page",
                count=10,
                custom_fields=[],
                taxonomies=[],
                sample_slugs=["about"],
            ),
        ],
        "plugins": [
            PluginFeature(
                slug="yoast-seo",
                name="Yoast SEO",
                version="21.0",
                family="yoast",
                custom_post_types=[],
                custom_taxonomies=[],
                detected_features=["seo_titles", "meta_descriptions"],
            ),
        ],
        "taxonomies": [
            TaxonomySummary(
                taxonomy="category",
                term_count=5,
                associated_post_types=["post"],
            ),
        ],
        "menus": [
            MenuSummary(name="Primary", location="header", item_count=6),
        ],
        "theme": ThemeMetadata(
            name="flavor",
            has_theme_json=True,
            has_custom_css=True,
            design_tokens={"color": {"primary": "#333"}},
        ),
        "has_html_snapshots": True,
        "has_media_manifest": True,
        "has_redirect_rules": False,
        "has_seo_data": True,
    }
    defaults.update(overrides)
    return Inventory(**defaults)


def _good_prd_body() -> str:
    """Return a well-formed PRD body with all required sections."""
    return (
        "## Goals\n"
        "Migrate Example Site from WordPress to Astro JS 5.\n\n"
        "## Non-Goals\n"
        "No e-commerce migration.\n\n"
        "## Information Architecture\n"
        "- post → collection `posts`, route `/posts/[slug]`\n"
        "- page → collection `pages`, route `/[slug]`\n\n"
        "## Sitemap\n"
        "Home, Posts index, individual posts, pages.\n\n"
        "## Theming Mode\n"
        "Preserve existing theme CSS with design token extraction.\n\n"
        "## SEO Scope\n"
        "Yoast SEO titles and meta descriptions in frontmatter.\n\n"
        "## Acceptance Metrics\n"
        "Visual parity ≥90%, all pages return HTTP 200.\n\n"
        "## Impact Metrics\n"
        "Baseline: 30–60 engineer hours. Target: ~2 hours.\n"
    )


def _make_gradient_client(response: str = "") -> AsyncMock:
    """Create a mock GradientClient that returns the given response."""
    client = AsyncMock()
    client.complete = AsyncMock(return_value=response)
    return client


def _make_kb_client(
    query_results: list[dict] | None = None,
) -> AsyncMock:
    """Create a mock KnowledgeBaseClient."""
    client = AsyncMock()
    client.query = AsyncMock(return_value=query_results or [])
    return client


# ------------------------------------------------------------------
# Pure function tests
# ------------------------------------------------------------------


class TestCountWords:
    def test_empty_string(self):
        # "".split() returns [] so len is 0, but we get 1 from "".split()
        # Actually "".split() returns [] in Python
        assert _count_words("") == 0

    def test_single_word(self):
        assert _count_words("hello") == 1

    def test_multiple_words(self):
        assert _count_words("one two three four five") == 5

    def test_multiline(self):
        assert _count_words("line one\nline two\nline three") == 6


class TestValidateSections:
    def test_all_sections_present(self):
        prd = _good_prd_body()
        assert _validate_sections(prd) == []

    def test_missing_goals(self):
        prd = _good_prd_body().replace("## Goals", "## Objectives")
        missing = _validate_sections(prd)
        assert "goals" in missing

    def test_missing_multiple_sections(self):
        prd = "## Goals\nSome goals.\n## Sitemap\nSome sitemap.\n"
        missing = _validate_sections(prd)
        assert "non-goals" in missing
        assert "information architecture" in missing
        assert "theming mode" in missing
        assert "seo scope" in missing
        assert "acceptance metrics" in missing

    def test_case_insensitive(self):
        prd = _good_prd_body().replace("## Goals", "## goals")
        assert _validate_sections(prd) == []

    def test_empty_string(self):
        missing = _validate_sections("")
        assert len(missing) == len(REQUIRED_SECTIONS)


class TestBuildUserPrompt:
    def test_includes_site_info(self):
        inv = _make_inventory()
        prompt = _build_user_prompt(inv, [])
        assert "Example Site" in prompt
        assert "https://example.com" in prompt
        assert "6.4" in prompt

    def test_includes_content_types(self):
        inv = _make_inventory()
        prompt = _build_user_prompt(inv, [])
        assert "post" in prompt
        assert "50 items" in prompt
        assert "page" in prompt

    def test_includes_plugins(self):
        inv = _make_inventory()
        prompt = _build_user_prompt(inv, [])
        assert "Yoast SEO" in prompt
        assert "[yoast]" in prompt

    def test_includes_taxonomies(self):
        inv = _make_inventory()
        prompt = _build_user_prompt(inv, [])
        assert "category" in prompt

    def test_includes_menus(self):
        inv = _make_inventory()
        prompt = _build_user_prompt(inv, [])
        assert "Primary" in prompt

    def test_includes_theme(self):
        inv = _make_inventory()
        prompt = _build_user_prompt(inv, [])
        assert "flavor" in prompt

    def test_includes_flags(self):
        inv = _make_inventory()
        prompt = _build_user_prompt(inv, [])
        assert "HTML snapshots available" in prompt
        assert "SEO data available" in prompt

    def test_includes_kb_context(self):
        inv = _make_inventory()
        kb_docs = [{"content": "KB doc content here"}]
        prompt = _build_user_prompt(inv, kb_docs)
        assert "KB doc content here" in prompt

    def test_truncates_long_kb_content(self):
        inv = _make_inventory()
        long_content = "x" * 1000
        kb_docs = [{"content": long_content}]
        prompt = _build_user_prompt(inv, kb_docs)
        # Should be truncated to 800 chars + ellipsis
        assert "…" in prompt

    def test_no_plugins(self):
        inv = _make_inventory(plugins=[])
        prompt = _build_user_prompt(inv, [])
        assert "Detected plugins" not in prompt

    def test_no_menus(self):
        inv = _make_inventory(menus=[])
        prompt = _build_user_prompt(inv, [])
        assert "Menus:" not in prompt


class TestBuildSystemPrompt:
    def test_mentions_word_limit(self):
        prompt = _build_system_prompt()
        assert "1500" in prompt

    def test_mentions_required_sections(self):
        prompt = _build_system_prompt()
        assert "## Goals" in prompt
        assert "## Non-Goals" in prompt
        assert "## Information Architecture" in prompt
        assert "## Impact Metrics" in prompt

    def test_mentions_impact_metrics(self):
        prompt = _build_system_prompt()
        assert "30–60" in prompt
        assert "2 hours" in prompt


class TestExtractInventory:
    def test_from_inventory_instance(self):
        inv = _make_inventory()
        result = _extract_inventory({"inventory": inv})
        assert result is inv

    def test_from_dict(self):
        inv = _make_inventory()
        result = _extract_inventory({"inventory": inv.model_dump()})
        assert isinstance(result, Inventory)
        assert result.site_name == "Example Site"

    def test_missing_key_raises(self):
        with pytest.raises(KeyError):
            _extract_inventory({})


# ------------------------------------------------------------------
# Agent execution tests
# ------------------------------------------------------------------


class TestPrdLiteAgentExecute:
    @pytest.mark.asyncio
    async def test_successful_generation(self):
        """PRD is generated with all sections and returned as artifact."""
        body = _good_prd_body()
        gradient = _make_gradient_client(body)
        kb = _make_kb_client()

        agent = PrdLiteAgent(gradient_client=gradient, kb_client=kb)
        result = await agent.execute({
            "inventory": _make_inventory(),
            "kb_ref": "kb-123",
        })

        assert result.agent_name == "prd_lite"
        assert "prd_md" in result.artifacts
        prd = result.artifacts["prd_md"]
        assert prd.startswith("# PRD — Example Site Migration")
        assert "## Goals" in prd
        assert result.duration_seconds > 0

    @pytest.mark.asyncio
    async def test_queries_knowledge_base(self):
        """Agent queries KB with multiple queries when kb_ref is provided."""
        body = _good_prd_body()
        gradient = _make_gradient_client(body)
        kb = _make_kb_client([{"content": "site info", "metadata": {}}])

        agent = PrdLiteAgent(gradient_client=gradient, kb_client=kb)
        await agent.execute({
            "inventory": _make_inventory(),
            "kb_ref": "kb-123",
        })

        # Should have queried KB 3 times (site metadata, plugins, content types)
        assert kb.query.call_count == 3

    @pytest.mark.asyncio
    async def test_skips_kb_when_no_ref(self):
        """Agent skips KB queries when kb_ref is None."""
        body = _good_prd_body()
        gradient = _make_gradient_client(body)
        kb = _make_kb_client()

        agent = PrdLiteAgent(gradient_client=gradient, kb_client=kb)
        result = await agent.execute({
            "inventory": _make_inventory(),
            "kb_ref": None,
        })

        assert kb.query.call_count == 0
        assert "prd_md" in result.artifacts

    @pytest.mark.asyncio
    async def test_skips_kb_when_no_client(self):
        """Agent skips KB queries when kb_client is None."""
        body = _good_prd_body()
        gradient = _make_gradient_client(body)

        agent = PrdLiteAgent(gradient_client=gradient, kb_client=None)
        result = await agent.execute({
            "inventory": _make_inventory(),
            "kb_ref": "kb-123",
        })

        assert "prd_md" in result.artifacts

    @pytest.mark.asyncio
    async def test_missing_sections_triggers_regeneration(self):
        """Agent retries when initial PRD is missing required sections."""
        incomplete_body = "## Goals\nSome goals.\n"
        complete_body = _good_prd_body()

        gradient = AsyncMock()
        gradient.complete = AsyncMock(
            side_effect=[incomplete_body, complete_body]
        )

        agent = PrdLiteAgent(gradient_client=gradient, kb_client=None)
        result = await agent.execute({
            "inventory": _make_inventory(),
        })

        assert gradient.complete.call_count == 2
        prd = result.artifacts["prd_md"]
        assert "## Goals" in prd
        assert "## Non-Goals" in prd
        assert any("missing sections" in w.lower() for w in result.warnings)

    @pytest.mark.asyncio
    async def test_word_limit_triggers_condensation(self):
        """Agent condenses PRD when it exceeds the word limit."""
        # Generate a body that exceeds 1500 words
        long_body = _good_prd_body() + "\n" + " ".join(["word"] * 1600)
        condensed_body = _good_prd_body()

        gradient = AsyncMock()
        gradient.complete = AsyncMock(
            side_effect=[long_body, condensed_body]
        )

        agent = PrdLiteAgent(gradient_client=gradient, kb_client=None)
        result = await agent.execute({
            "inventory": _make_inventory(),
        })

        assert gradient.complete.call_count == 2
        assert any("exceeds word limit" in w.lower() for w in result.warnings)

    @pytest.mark.asyncio
    async def test_kb_query_failure_produces_warning(self):
        """KB query failures are caught and logged as warnings."""
        body = _good_prd_body()
        gradient = _make_gradient_client(body)
        kb = AsyncMock()
        kb.query = AsyncMock(side_effect=RuntimeError("KB unavailable"))

        agent = PrdLiteAgent(gradient_client=gradient, kb_client=kb)
        result = await agent.execute({
            "inventory": _make_inventory(),
            "kb_ref": "kb-123",
        })

        # Should still produce a PRD despite KB failures
        assert "prd_md" in result.artifacts
        assert any("KB query failed" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_inventory_from_dict(self):
        """Agent accepts inventory as a dict (not just Inventory instance)."""
        body = _good_prd_body()
        gradient = _make_gradient_client(body)

        agent = PrdLiteAgent(gradient_client=gradient, kb_client=None)
        result = await agent.execute({
            "inventory": _make_inventory().model_dump(),
        })

        assert "prd_md" in result.artifacts

    @pytest.mark.asyncio
    async def test_custom_post_types_in_prompt(self):
        """Custom post types beyond post/page appear in the LLM prompt."""
        inv = _make_inventory(
            content_types=[
                ContentTypeSummary(
                    post_type="post", count=10, custom_fields=[],
                    taxonomies=[], sample_slugs=[],
                ),
                ContentTypeSummary(
                    post_type="place", count=25,
                    custom_fields=["address", "latitude", "longitude"],
                    taxonomies=["place_category"],
                    sample_slugs=["central-park"],
                ),
                ContentTypeSummary(
                    post_type="event", count=15,
                    custom_fields=["start_date", "end_date"],
                    taxonomies=["event_type"],
                    sample_slugs=["summer-fest"],
                ),
            ],
        )
        body = _good_prd_body()
        gradient = _make_gradient_client(body)

        agent = PrdLiteAgent(gradient_client=gradient, kb_client=None)
        await agent.execute({"inventory": inv})

        # Check the prompt sent to the LLM includes custom post types
        call_args = gradient.complete.call_args
        messages = call_args[0][0]
        user_msg = messages[1]["content"]
        assert "place" in user_msg
        assert "event" in user_msg
        assert "address" in user_msg

    @pytest.mark.asyncio
    async def test_prd_title_includes_site_name(self):
        """The PRD title heading includes the site name."""
        body = _good_prd_body()
        gradient = _make_gradient_client(body)

        agent = PrdLiteAgent(gradient_client=gradient, kb_client=None)
        result = await agent.execute({
            "inventory": _make_inventory(site_name="My Cool Blog"),
        })

        prd = result.artifacts["prd_md"]
        assert "# PRD — My Cool Blog Migration" in prd

    @pytest.mark.asyncio
    async def test_still_missing_sections_after_retry(self):
        """Warning is added when sections are still missing after retry."""
        incomplete = "## Goals\nSome goals.\n"

        gradient = AsyncMock()
        gradient.complete = AsyncMock(return_value=incomplete)

        agent = PrdLiteAgent(gradient_client=gradient, kb_client=None)
        result = await agent.execute({
            "inventory": _make_inventory(),
        })

        assert any("still missing" in w.lower() for w in result.warnings)
