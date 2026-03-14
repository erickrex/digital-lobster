from __future__ import annotations

import os
import textwrap

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from typing import Any

from src.agents.qa import (
    QAAgent,
    check_accessibility,
    count_strapi_entries,
    compute_visual_parity,
    derive_key_pages,
)
from src.models.strapi_types import ContentTypeMap
from src.models.qa_report import PageCheck, QAReport
from src.models.modeling_manifest import (
    ModelingManifest,
    ContentCollectionSchema,
    FrontmatterField,
    ComponentMapping,
    TaxonomyDefinition,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gradient_client() -> AsyncMock:
    return AsyncMock()

def _make_manifest(**overrides: Any) -> ModelingManifest:
    defaults: dict[str, Any] = {
        "collections": [
            ContentCollectionSchema(
                collection_name="blog",
                source_post_type="post",
                frontmatter_fields=[
                    FrontmatterField(
                        name="title", type="string", required=True, description="Title"
                    )
                ],
                route_pattern="/blog/[slug]",
            ),
        ],
        "components": [
            ComponentMapping(
                wp_block_type="core/paragraph",
                astro_component="Paragraph",
                is_island=False,
                hydration_directive=None,
                props=[],
                fallback=False,
            ),
        ],
        "taxonomies": [
            TaxonomyDefinition(
                taxonomy="category",
                collection_ref="categories",
                data_file=None,
            ),
        ],
    }
    defaults.update(overrides)
    return ModelingManifest(**defaults)

def _good_html() -> str:
    """HTML that passes all accessibility checks."""
    return textwrap.dedent("""\
        <html>
        <body>
        <a href="#main-content">Skip to content</a>
        <header><nav><ul><li>Home</li></ul></nav></header>
        <main id="main-content">
        <h1>Welcome</h1>
        <h2>Subtitle</h2>
        <img src="photo.jpg" alt="A photo">
        </main>
        <footer>Footer</footer>
        </body>
        </html>
    """)

def _bad_html() -> str:
    """HTML that fails multiple accessibility checks."""
    return textwrap.dedent("""\
        <html>
        <body>
        <div>
        <h2>No h1 first</h2>
        <img src="photo.jpg">
        </div>
        </body>
        </html>
    """)

# ---------------------------------------------------------------------------
# check_accessibility
# ---------------------------------------------------------------------------

class TestCheckAccessibility:
    def test_good_html_no_issues(self):
        issues = check_accessibility(_good_html())
        assert issues == []

    def test_missing_landmarks(self):
        html = "<html><body><div>Hello</div></body></html>"
        issues = check_accessibility(html)
        assert any("Missing landmark: <main>" in i for i in issues)
        assert any("Missing landmark: <nav>" in i for i in issues)
        assert any("Missing landmark: <header>" in i for i in issues)
        assert any("Missing landmark: <footer>" in i for i in issues)

    def test_heading_hierarchy_h2_before_h1(self):
        html = "<html><body><header></header><nav></nav><main><h2>Sub</h2><h1>Title</h1></main><footer></footer></body></html>"
        issues = check_accessibility(html)
        assert any("h2" in i and "before" in i.lower() for i in issues)

    def test_heading_hierarchy_h2_without_h1(self):
        html = "<html><body><header></header><nav></nav><main><h2>Sub</h2></main><footer></footer></body></html>"
        issues = check_accessibility(html)
        assert any("h2" in i and "without" in i.lower() for i in issues)

    def test_image_missing_alt(self):
        html = '<html><body><header></header><nav></nav><main><h1>T</h1><img src="x.jpg"></main><footer></footer></body></html>'
        issues = check_accessibility(html)
        assert any("alt attribute" in i.lower() for i in issues)

    def test_image_with_alt_ok(self):
        html = '<html><body><a href="#m">skip</a><header></header><nav></nav><main id="m"><h1>T</h1><img src="x.jpg" alt="desc"></main><footer></footer></body></html>'
        issues = check_accessibility(html)
        assert not any("alt attribute" in i.lower() for i in issues)

    def test_missing_skip_nav(self):
        html = "<html><body><header></header><nav></nav><main><h1>T</h1></main><footer></footer></body></html>"
        issues = check_accessibility(html)
        assert any("skip-navigation" in i.lower() for i in issues)

    def test_skip_nav_present(self):
        html = '<html><body><a href="#c">Skip</a><header></header><nav></nav><main id="c"><h1>T</h1></main><footer></footer></body></html>'
        issues = check_accessibility(html)
        assert not any("skip-navigation" in i.lower() for i in issues)

# ---------------------------------------------------------------------------
# compute_visual_parity
# ---------------------------------------------------------------------------

class TestComputeVisualParity:
    def test_identical_html_returns_1(self):
        html = "<html><body><p>Hello world</p></body></html>"
        assert compute_visual_parity(html, html) == 1.0

    def test_completely_different_returns_low(self):
        a = "<html><body><p>Alpha bravo charlie</p></body></html>"
        b = "<html><body><p>Xray yankee zulu</p></body></html>"
        score = compute_visual_parity(a, b)
        assert 0.0 <= score < 0.8

    def test_similar_html_returns_high(self):
        a = "<html><body><h1>Title</h1><p>Content here</p></body></html>"
        b = "<html><body><h1>Title</h1><p>Content here!</p></body></html>"
        score = compute_visual_parity(a, b)
        assert score > 0.9

    def test_empty_strings_return_1(self):
        assert compute_visual_parity("", "") == 1.0

    def test_score_between_0_and_1(self):
        a = "<p>Some text</p>"
        b = "<p>Other text</p>"
        score = compute_visual_parity(a, b)
        assert 0.0 <= score <= 1.0

# ---------------------------------------------------------------------------
# derive_key_pages
# ---------------------------------------------------------------------------

class TestDeriveKeyPages:
    def test_always_includes_home_and_404(self):
        pages = derive_key_pages({})
        assert "/" in pages
        assert "/404" in pages

    def test_includes_collection_index(self):
        manifest = _make_manifest()
        pages = derive_key_pages({"modeling_manifest": manifest})
        assert "/blog" in pages

    def test_includes_sample_content_page(self):
        manifest = _make_manifest()
        context = {
            "modeling_manifest": manifest,
            "content_files": {"src/content/blog/hello-world.md": "---\ntitle: Hello\n---\n"},
        }
        pages = derive_key_pages(context)
        assert "/blog/hello-world" in pages

    def test_works_with_dict_manifest(self):
        manifest_dict = {
            "collections": [
                {
                    "collection_name": "posts",
                    "source_post_type": "post",
                    "frontmatter_fields": [],
                    "route_pattern": "/posts/[slug]",
                }
            ],
            "components": [],
            "taxonomies": [],
        }
        pages = derive_key_pages({"modeling_manifest": manifest_dict})
        assert "/posts" in pages

    def test_no_manifest_returns_only_defaults(self):
        pages = derive_key_pages({"some_key": "value"})
        assert pages == ["/", "/404"]


class TestCountStrapiEntries:
    @pytest.mark.asyncio
    async def test_prefers_explicit_rest_endpoints(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        requested_urls: list[str] = []

        class FakeResponse:
            status_code = 200

            def json(self) -> dict[str, Any]:
                return {"meta": {"pagination": {"total": 7}}}

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, url: str, headers=None):
                requested_urls.append(url)
                return FakeResponse()

        monkeypatch.setattr(
            "src.agents.qa.httpx.AsyncClient",
            lambda timeout=30.0: FakeClient(),
        )

        total = await count_strapi_entries(
            "https://cms.example.com",
            "tok-secret",
            ContentTypeMap(
                mappings={"news": "api::news.news"},
                taxonomy_mappings={},
                component_uids=[],
                rest_endpoints={"news": "/api/editorial-news"},
            ),
        )

        assert total == 7
        assert requested_urls == [
            "https://cms.example.com/api/editorial-news?pagination[pageSize]=1"
        ]

# ---------------------------------------------------------------------------
# QAAgent — build failure
# ---------------------------------------------------------------------------

class TestQAAgentBuildFailure:
    @pytest.mark.asyncio
    async def test_build_failure_produces_report(self):
        agent = QAAgent(gradient_client=_make_gradient_client())
        context = {"astro_project": {"package.json": "{}"}}

        with patch.object(
            agent, "_run_build", return_value=(False, ["npm run build failed (exit 1): Error"])
        ), patch.object(agent, "_write_project", return_value="/tmp/fake"), patch.object(
            agent, "_cleanup"
        ):
            result = await agent.execute(context)

        report = result.artifacts["qa_report"]
        assert report["build_success"] is False
        assert len(report["build_errors"]) > 0
        assert report["pages_checked"] == []
        assert report["total_passed"] == 0
        assert report["total_failed"] == 0

    @pytest.mark.asyncio
    async def test_build_failure_records_error_details(self):
        agent = QAAgent(gradient_client=_make_gradient_client())
        context = {"astro_project": {"package.json": "{}"}}

        with patch.object(
            agent, "_run_build", return_value=(False, ["npm install failed (exit 127): not found"])
        ), patch.object(agent, "_write_project", return_value="/tmp/fake"), patch.object(
            agent, "_cleanup"
        ):
            result = await agent.execute(context)

        report = result.artifacts["qa_report"]
        assert "npm install failed" in report["build_errors"][0]

# ---------------------------------------------------------------------------
# QAAgent — build success with page checks
# ---------------------------------------------------------------------------

class TestQAAgentBuildSuccess:
    def _make_context(self) -> dict[str, Any]:
        return {
            "astro_project": {"package.json": "{}"},
            "content_files": {"src/content/blog/hello.md": "---\ntitle: Hello\n---\n"},
            "modeling_manifest": _make_manifest(),
        }

    @pytest.mark.asyncio
    async def test_successful_build_checks_pages(self):
        agent = QAAgent(gradient_client=_make_gradient_client())
        context = self._make_context()

        page_checks = [
            PageCheck(url="/", http_status=200, visual_parity_score=None, accessibility_issues=[], passed=False),
            PageCheck(url="/404", http_status=200, visual_parity_score=None, accessibility_issues=[], passed=False),
            PageCheck(url="/blog", http_status=200, visual_parity_score=None, accessibility_issues=[], passed=False),
        ]

        with patch.object(agent, "_run_build", return_value=(True, [])), \
             patch.object(agent, "_write_project", return_value="/tmp/fake"), \
             patch.object(agent, "_check_pages", return_value=page_checks), \
             patch.object(agent, "_read_generated_page", return_value=_good_html()), \
             patch.object(agent, "_cleanup"):
            result = await agent.execute(context)

        report = result.artifacts["qa_report"]
        assert report["build_success"] is True
        assert len(report["pages_checked"]) == 3

    @pytest.mark.asyncio
    async def test_total_passed_and_failed_counts(self):
        agent = QAAgent(gradient_client=_make_gradient_client())
        context = self._make_context()

        page_checks = [
            PageCheck(url="/", http_status=200, visual_parity_score=None, accessibility_issues=[], passed=False),
            PageCheck(url="/404", http_status=404, visual_parity_score=None, accessibility_issues=[], passed=False),
        ]

        with patch.object(agent, "_run_build", return_value=(True, [])), \
             patch.object(agent, "_write_project", return_value="/tmp/fake"), \
             patch.object(agent, "_check_pages", return_value=page_checks), \
             patch.object(agent, "_read_generated_page", return_value=_good_html()), \
             patch.object(agent, "_cleanup"):
            result = await agent.execute(context)

        report = result.artifacts["qa_report"]
        # / has status 200 + good html → passed
        # /404 has status 404 → failed
        assert report["total_passed"] == 1
        assert report["total_failed"] == 1

    @pytest.mark.asyncio
    async def test_accessibility_issues_recorded(self):
        agent = QAAgent(gradient_client=_make_gradient_client())
        context = self._make_context()

        page_checks = [
            PageCheck(url="/", http_status=200, visual_parity_score=None, accessibility_issues=[], passed=False),
        ]

        with patch.object(agent, "_run_build", return_value=(True, [])), \
             patch.object(agent, "_write_project", return_value="/tmp/fake"), \
             patch.object(agent, "_check_pages", return_value=page_checks), \
             patch.object(agent, "_read_generated_page", return_value=_bad_html()), \
             patch.object(agent, "_cleanup"):
            result = await agent.execute(context)

        report = result.artifacts["qa_report"]
        page = report["pages_checked"][0]
        assert len(page["accessibility_issues"]) > 0
        assert page["passed"] is False

    @pytest.mark.asyncio
    async def test_visual_parity_computed_when_snapshots_present(self):
        agent = QAAgent(gradient_client=_make_gradient_client())
        context = self._make_context()
        context["html_snapshots"] = {"/": "<html><body><h1>Welcome</h1></body></html>"}

        page_checks = [
            PageCheck(url="/", http_status=200, visual_parity_score=None, accessibility_issues=[], passed=False),
        ]

        with patch.object(agent, "_run_build", return_value=(True, [])), \
             patch.object(agent, "_write_project", return_value="/tmp/fake"), \
             patch.object(agent, "_check_pages", return_value=page_checks), \
             patch.object(agent, "_read_generated_page", return_value=_good_html()), \
             patch.object(agent, "_cleanup"):
            result = await agent.execute(context)

        report = result.artifacts["qa_report"]
        page = report["pages_checked"][0]
        assert page["visual_parity_score"] is not None
        assert 0.0 <= page["visual_parity_score"] <= 1.0

    @pytest.mark.asyncio
    async def test_visual_parity_not_computed_without_snapshots(self):
        agent = QAAgent(gradient_client=_make_gradient_client())
        context = self._make_context()
        # No html_snapshots key

        page_checks = [
            PageCheck(url="/", http_status=200, visual_parity_score=None, accessibility_issues=[], passed=False),
        ]

        with patch.object(agent, "_run_build", return_value=(True, [])), \
             patch.object(agent, "_write_project", return_value="/tmp/fake"), \
             patch.object(agent, "_check_pages", return_value=page_checks), \
             patch.object(agent, "_read_generated_page", return_value=_good_html()), \
             patch.object(agent, "_cleanup"):
            result = await agent.execute(context)

        report = result.artifacts["qa_report"]
        page = report["pages_checked"][0]
        assert page["visual_parity_score"] is None

    @pytest.mark.asyncio
    async def test_duration_recorded(self):
        agent = QAAgent(gradient_client=_make_gradient_client())
        context = self._make_context()

        with patch.object(agent, "_run_build", return_value=(True, [])), \
             patch.object(agent, "_write_project", return_value="/tmp/fake"), \
             patch.object(agent, "_check_pages", return_value=[]), \
             patch.object(agent, "_cleanup"):
            result = await agent.execute(context)

        assert result.duration_seconds >= 0.0

    @pytest.mark.asyncio
    async def test_agent_name_is_qa(self):
        agent = QAAgent(gradient_client=_make_gradient_client())
        context = self._make_context()

        with patch.object(agent, "_run_build", return_value=(True, [])), \
             patch.object(agent, "_write_project", return_value="/tmp/fake"), \
             patch.object(agent, "_check_pages", return_value=[]), \
             patch.object(agent, "_cleanup"):
            result = await agent.execute(context)

        assert result.agent_name == "qa"

    @pytest.mark.asyncio
    async def test_low_visual_parity_adds_warning(self):
        agent = QAAgent(gradient_client=_make_gradient_client())
        context = self._make_context()
        # Snapshot is very different from generated page
        context["html_snapshots"] = {"/": "<html><body><p>Completely different content xyz abc</p></body></html>"}

        page_checks = [
            PageCheck(url="/", http_status=200, visual_parity_score=None, accessibility_issues=[], passed=False),
        ]

        generated = "<html><body><a href='#m'>skip</a><header></header><nav></nav><main id='m'><h1>Title</h1></main><footer></footer></body></html>"

        with patch.object(agent, "_run_build", return_value=(True, [])), \
             patch.object(agent, "_write_project", return_value="/tmp/fake"), \
             patch.object(agent, "_check_pages", return_value=page_checks), \
             patch.object(agent, "_read_generated_page", return_value=generated), \
             patch.object(agent, "_cleanup"):
            result = await agent.execute(context)

        assert any("Visual parity below 90%" in w for w in result.warnings)

# ---------------------------------------------------------------------------
# QAAgent — collect_project_files
# ---------------------------------------------------------------------------

class TestCollectProjectFiles:
    def test_merges_scaffold_and_content(self):
        context = {
            "astro_project": {"package.json": "{}", "astro.config.mjs": "export default {}"},
            "content_files": {"src/content/blog/post.md": "---\ntitle: P\n---\n"},
        }
        files = QAAgent._collect_project_files(context)
        assert "package.json" in files
        assert "src/content/blog/post.md" in files

    def test_empty_context(self):
        files = QAAgent._collect_project_files({})
        assert files == {}

    def test_only_scaffold(self):
        context = {"astro_project": {"a.txt": "hello"}}
        files = QAAgent._collect_project_files(context)
        assert files == {"a.txt": "hello"}

# ---------------------------------------------------------------------------
# QAAgent — _write_project and _check_pages integration
# ---------------------------------------------------------------------------

class TestWriteProjectAndCheckPages:
    @pytest.mark.asyncio
    async def test_check_pages_finds_existing_files(self):
        agent = QAAgent(gradient_client=_make_gradient_client())
        files = {
            "dist/index.html": "<html><body>Home</body></html>",
            "dist/blog/index.html": "<html><body>Blog</body></html>",
            "dist/404.html": "<html><body>Not Found</body></html>",
        }
        project_dir = agent._write_project(files)
        try:
            dist_dir = os.path.join(project_dir, "dist")
            checks = await agent._check_pages(dist_dir, ["/", "/blog", "/404"])
            statuses = {c.url: c.http_status for c in checks}
            assert statuses["/"] == 200
            assert statuses["/blog"] == 200
            assert statuses["/404"] == 200
        finally:
            agent._cleanup(project_dir)

    @pytest.mark.asyncio
    async def test_check_pages_missing_file_returns_404(self):
        agent = QAAgent(gradient_client=_make_gradient_client())
        files = {"dist/index.html": "<html>Home</html>"}
        project_dir = agent._write_project(files)
        try:
            dist_dir = os.path.join(project_dir, "dist")
            checks = await agent._check_pages(dist_dir, ["/", "/missing"])
            statuses = {c.url: c.http_status for c in checks}
            assert statuses["/"] == 200
            assert statuses["/missing"] == 404
        finally:
            agent._cleanup(project_dir)

# ---------------------------------------------------------------------------
# QAAgent — _read_generated_page
# ---------------------------------------------------------------------------

class TestReadGeneratedPage:
    def test_reads_index_html(self):
        agent = QAAgent(gradient_client=_make_gradient_client())
        files = {"dist/index.html": "<html>Home</html>"}
        project_dir = agent._write_project(files)
        try:
            dist_dir = os.path.join(project_dir, "dist")
            content = agent._read_generated_page(dist_dir, "/")
            assert content == "<html>Home</html>"
        finally:
            agent._cleanup(project_dir)

    def test_reads_nested_page(self):
        agent = QAAgent(gradient_client=_make_gradient_client())
        files = {"dist/blog/index.html": "<html>Blog</html>"}
        project_dir = agent._write_project(files)
        try:
            dist_dir = os.path.join(project_dir, "dist")
            content = agent._read_generated_page(dist_dir, "/blog")
            assert content == "<html>Blog</html>"
        finally:
            agent._cleanup(project_dir)

    def test_returns_none_for_missing(self):
        agent = QAAgent(gradient_client=_make_gradient_client())
        files = {"dist/index.html": "<html>Home</html>"}
        project_dir = agent._write_project(files)
        try:
            dist_dir = os.path.join(project_dir, "dist")
            content = agent._read_generated_page(dist_dir, "/nope")
            assert content is None
        finally:
            agent._cleanup(project_dir)

# ---------------------------------------------------------------------------
# QA report structure validation
# ---------------------------------------------------------------------------

class TestQAReportStructure:
    @pytest.mark.asyncio
    async def test_report_conforms_to_model(self):
        agent = QAAgent(gradient_client=_make_gradient_client())
        context = {"astro_project": {"package.json": "{}"}}

        with patch.object(agent, "_run_build", return_value=(False, ["error"])), \
             patch.object(agent, "_write_project", return_value="/tmp/fake"), \
             patch.object(agent, "_cleanup"):
            result = await agent.execute(context)

        report_dict = result.artifacts["qa_report"]
        # Should be parseable back into QAReport
        report = QAReport(**report_dict)
        assert isinstance(report.build_success, bool)
        assert isinstance(report.build_errors, list)
        assert isinstance(report.pages_checked, list)
        assert isinstance(report.total_passed, int)
        assert isinstance(report.total_failed, int)
        assert isinstance(report.warnings, list)

    @pytest.mark.asyncio
    async def test_failed_check_includes_details(self):
        """A page that returns 404 should appear in the report with its URL and status."""
        agent = QAAgent(gradient_client=_make_gradient_client())
        context = {
            "astro_project": {"package.json": "{}"},
            "modeling_manifest": _make_manifest(),
        }

        page_checks = [
            PageCheck(url="/blog", http_status=404, visual_parity_score=None, accessibility_issues=[], passed=False),
        ]

        with patch.object(agent, "_run_build", return_value=(True, [])), \
             patch.object(agent, "_write_project", return_value="/tmp/fake"), \
             patch.object(agent, "_check_pages", return_value=page_checks), \
             patch.object(agent, "_cleanup"):
            result = await agent.execute(context)

        report = result.artifacts["qa_report"]
        failed_page = report["pages_checked"][0]
        assert failed_page["url"] == "/blog"
        assert failed_page["http_status"] == 404
        assert failed_page["passed"] is False
