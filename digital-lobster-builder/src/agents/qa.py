"""Agent 6: QA — builds the Astro project, smoke-tests pages, checks
visual parity against HTML snapshots, and runs basic accessibility audits.

All subprocess / HTTP operations are isolated in helper methods so that
tests can mock them without touching the filesystem or network.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile
import time
from difflib import SequenceMatcher
from typing import Any

import httpx

from src.agents.base import AgentResult, BaseAgent
from src.models.qa_report import CMSValidation, PageCheck, QAReport

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Accessibility helpers (pure functions — easy to test directly)
# ---------------------------------------------------------------------------

_LANDMARK_TAGS = {"main", "nav", "header", "footer"}


def check_accessibility(html: str) -> list[str]:
    """Return a list of accessibility issues found in *html*.

    Checks performed:
    - Landmark regions (<main>, <nav>, <header>, <footer>)
    - Heading hierarchy (an <h1> should appear before any <h2>)
    - Image alt attributes
    - Skip-navigation link (an <a> whose href starts with ``#`` appearing
      before the first <main> tag)
    """
    issues: list[str] = []
    html_lower = html.lower()

    # 1. Landmark regions
    for tag in _LANDMARK_TAGS:
        if f"<{tag}" not in html_lower:
            issues.append(f"Missing landmark: <{tag}>")

    # 2. Heading hierarchy — h1 must appear before h2
    h1_pos = html_lower.find("<h1")
    h2_pos = html_lower.find("<h2")
    if h1_pos == -1 and h2_pos != -1:
        issues.append("Heading hierarchy: <h2> found without preceding <h1>")
    elif h1_pos != -1 and h2_pos != -1 and h2_pos < h1_pos:
        issues.append("Heading hierarchy: <h2> appears before <h1>")

    # 3. Image alt attributes
    img_pattern = re.compile(r"<img\b[^>]*?>", re.IGNORECASE | re.DOTALL)
    for img_tag in img_pattern.findall(html):
        if "alt=" not in img_tag.lower():
            issues.append(f"Image missing alt attribute: {img_tag[:80]}")

    # 4. Skip-navigation link
    main_pos = html_lower.find("<main")
    skip_pattern = re.compile(
        r'<a\b[^>]*href\s*=\s*["\']#[^"\']*["\'][^>]*>', re.IGNORECASE
    )
    skip_links = list(skip_pattern.finditer(html))
    has_skip = any(m.start() < main_pos for m in skip_links) if main_pos != -1 and skip_links else False
    if not has_skip:
        issues.append("Missing skip-navigation link before <main>")

    return issues


# ---------------------------------------------------------------------------
# Visual parity helper (pure function)
# ---------------------------------------------------------------------------


def compute_visual_parity(generated_html: str, snapshot_html: str) -> float:
    """Return a similarity score between 0.0 and 1.0.

    Uses :class:`difflib.SequenceMatcher` on the *text content* of both
    HTML strings (tags stripped) to approximate structural/text similarity.
    """
    generated_text = _strip_tags(generated_html)
    snapshot_text = _strip_tags(snapshot_html)
    if not generated_text and not snapshot_text:
        return 1.0
    return SequenceMatcher(None, generated_text, snapshot_text).ratio()


def _strip_tags(html: str) -> str:
    """Naively strip HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# Key-page URL derivation
# ---------------------------------------------------------------------------


def derive_key_pages(context: dict[str, Any]) -> list[str]:
    """Derive the list of key page URLs to check from the pipeline context.

    Always includes ``/`` (home) and ``/404`` (error page).
    Adds collection index pages and a sample content page per collection
    when a ``modeling_manifest`` is available.
    """
    urls: list[str] = ["/", "/404"]

    manifest = context.get("modeling_manifest")
    if manifest is None:
        return urls

    # Accept both dict and ModelingManifest instances
    collections: list[Any] = []
    if hasattr(manifest, "collections"):
        collections = manifest.collections
    elif isinstance(manifest, dict):
        collections = manifest.get("collections", [])

    content_files: dict[str, str] = context.get("content_files", {})

    for col in collections:
        col_name = col.collection_name if hasattr(col, "collection_name") else col.get("collection_name", "")
        route_pattern = col.route_pattern if hasattr(col, "route_pattern") else col.get("route_pattern", "")

        # Collection index — e.g. /blog
        prefix = route_pattern.split("[")[0].rstrip("/")
        if prefix:
            urls.append(prefix)

        # Sample content page — pick the first matching content file
        for path in content_files:
            if f"src/content/{col_name}/" in path:
                slug = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
                sample_url = route_pattern.replace("[slug]", slug).replace("[...slug]", slug)
                urls.append(sample_url)
                break  # one sample per collection

    return urls


# ---------------------------------------------------------------------------
# CMS validation helpers (module-level pure/async functions)
# ---------------------------------------------------------------------------


async def count_strapi_entries(
    base_url: str, token: str, content_type_map: Any
) -> int:
    """Count total content entries across all Strapi content types.

    Queries each content type's REST API endpoint with ``pagination[pageSize]=1``
    to read the total from the pagination metadata without fetching full payloads.
    """
    total = 0
    mappings: dict[str, str] = {}
    if hasattr(content_type_map, "mappings"):
        mappings = content_type_map.mappings
    elif isinstance(content_type_map, dict):
        mappings = content_type_map.get("mappings", {})

    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        for _col_name, api_id in mappings.items():
            # api_id is like "api::post.post" → plural name is the last segment
            plural = api_id.split(".")[-1] + "s" if "." in api_id else api_id
            url = f"{base_url.rstrip('/')}/api/{plural}?pagination[pageSize]=1"
            try:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    meta = data.get("meta", {})
                    pagination = meta.get("pagination", {})
                    total += pagination.get("total", 0)
                else:
                    logger.warning(
                        "Strapi API returned %d for %s", resp.status_code, url
                    )
            except httpx.HTTPError as exc:
                logger.warning("Failed to query Strapi for %s: %s", api_id, exc)

    return total


async def check_media_urls(
    media_url_map: dict[str, str], timeout: float = 10.0
) -> tuple[int, int]:
    """Verify that Strapi media URLs resolve via HEAD requests.

    Returns ``(checked, valid)`` counts.
    """
    if not media_url_map:
        return 0, 0

    checked = 0
    valid = 0

    async with httpx.AsyncClient(timeout=timeout) as client:
        for _original_url, strapi_url in media_url_map.items():
            checked += 1
            try:
                resp = await client.head(strapi_url)
                if resp.status_code == 200:
                    valid += 1
                else:
                    logger.warning(
                        "Media URL returned %d: %s", resp.status_code, strapi_url
                    )
            except httpx.HTTPError as exc:
                logger.warning("Media URL check failed for %s: %s", strapi_url, exc)

    return checked, valid


def validate_content_counts(
    strapi_count: int, export_count: int, failed_count: int
) -> bool:
    """Return ``True`` if the content count discrepancy is within tolerance.

    The check passes when ``export_count - strapi_count <= failed_count``,
    meaning the only missing entries are those that failed during migration.
    """
    return export_count - strapi_count <= failed_count


# ---------------------------------------------------------------------------
# QAAgent
# ---------------------------------------------------------------------------


class QAAgent(BaseAgent):
    """Agent 6 — Quality Assurance.

    Builds the Astro project, smoke-tests key pages, compares against
    HTML snapshots, runs accessibility checks, and produces a
    :class:`QAReport`.
    """

    async def execute(self, context: dict[str, Any]) -> AgentResult:
        start = time.monotonic()
        warnings: list[str] = []

        # Collect the project files from context
        project_files = self._collect_project_files(context)

        # Write project to a temp directory
        project_dir = self._write_project(project_files)

        try:
            # 1. Build
            build_ok, build_errors = await self._run_build(project_dir)

            if not build_ok:
                # --- CMS mode: enrich build failure with Strapi API status ---
                cms_validation = None
                if context.get("cms_mode", False):
                    strapi_status = await self._check_strapi_api_status(context)
                    build_errors.append(
                        f"Strapi API status: {strapi_status}"
                    )

                report = QAReport(
                    build_success=False,
                    build_errors=build_errors,
                    pages_checked=[],
                    total_passed=0,
                    total_failed=0,
                    warnings=warnings,
                    cms_validation=cms_validation,
                )
                return AgentResult(
                    agent_name="qa",
                    artifacts={"qa_report": report.model_dump()},
                    warnings=warnings,
                    duration_seconds=time.monotonic() - start,
                )

            # 2. Determine key pages
            key_pages = derive_key_pages(context)

            # 3. Check pages
            dist_dir = os.path.join(project_dir, "dist")
            page_checks = await self._check_pages(dist_dir, key_pages)

            # 4. Visual parity against snapshots
            snapshots: dict[str, str] = context.get("html_snapshots", {})
            for check in page_checks:
                snapshot = snapshots.get(check.url)
                if snapshot is not None and check.http_status == 200:
                    generated = self._read_generated_page(dist_dir, check.url)
                    if generated is not None:
                        check.visual_parity_score = compute_visual_parity(
                            generated, snapshot
                        )
                        if check.visual_parity_score < 0.9:
                            warnings.append(
                                f"Visual parity below 90% for {check.url}: "
                                f"{check.visual_parity_score:.1%}"
                            )

            # 5. Accessibility checks
            for check in page_checks:
                if check.http_status == 200:
                    generated = self._read_generated_page(dist_dir, check.url)
                    if generated:
                        check.accessibility_issues = check_accessibility(generated)

            # 6. Determine pass/fail per page
            for check in page_checks:
                check.passed = (
                    check.http_status == 200
                    and len(check.accessibility_issues) == 0
                )

            total_passed = sum(1 for c in page_checks if c.passed)
            total_failed = len(page_checks) - total_passed

            # 7. CMS validation (only when cms_mode is enabled)
            cms_validation = None
            if context.get("cms_mode", False):
                cms_validation = await self._run_cms_validation(
                    context, warnings
                )

            report = QAReport(
                build_success=True,
                build_errors=[],
                pages_checked=page_checks,
                total_passed=total_passed,
                total_failed=total_failed,
                warnings=warnings,
                cms_validation=cms_validation,
            )
        finally:
            # Clean up temp directory (best-effort)
            self._cleanup(project_dir)

        return AgentResult(
            agent_name="qa",
            artifacts={"qa_report": report.model_dump()},
            warnings=warnings,
            duration_seconds=time.monotonic() - start,
        )

    # ------------------------------------------------------------------
    # Helpers — all designed to be easily mocked in tests
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_project_files(
        context: dict[str, Any]
    ) -> dict[str, str | bytes]:
        """Merge scaffold + importer content files into a single dict."""
        files: dict[str, str | bytes] = {}
        scaffold = context.get("astro_project", {})
        if isinstance(scaffold, dict):
            files.update(scaffold)
        content = context.get("content_files", {})
        if isinstance(content, dict):
            files.update(content)
        return files

    @staticmethod
    def _write_project(files: dict[str, str | bytes]) -> str:
        """Write *files* to a temporary directory and return its path."""
        tmp = tempfile.mkdtemp(prefix="qa_astro_")
        for rel_path, content in files.items():
            full = os.path.join(tmp, rel_path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            if isinstance(content, bytes):
                with open(full, "wb") as fh:
                    fh.write(content)
            else:
                with open(full, "w", encoding="utf-8") as fh:
                    fh.write(content)
        return tmp

    async def _run_build(self, project_dir: str) -> tuple[bool, list[str]]:
        """Run ``npm install`` then ``npm run build`` in *project_dir*.

        Returns ``(success, error_lines)``.
        """
        errors: list[str] = []
        for cmd in ["npm install", "npm run build"]:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                cwd=project_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                err_text = stderr.decode(errors="replace").strip()
                errors.append(f"{cmd} failed (exit {proc.returncode}): {err_text}")
                return False, errors
        return True, []

    async def _check_pages(
        self, dist_dir: str, urls: list[str]
    ) -> list[PageCheck]:
        """Check each URL by looking for the corresponding file in *dist_dir*.

        Astro static builds produce files like ``dist/index.html``,
        ``dist/blog/index.html``, etc.
        """
        results: list[PageCheck] = []
        for url in urls:
            file_path = self._url_to_dist_path(dist_dir, url)
            if os.path.isfile(file_path):
                status = 200
            else:
                status = 404
            results.append(
                PageCheck(
                    url=url,
                    http_status=status,
                    visual_parity_score=None,
                    accessibility_issues=[],
                    passed=False,  # determined later
                )
            )
        return results

    @staticmethod
    def _url_to_dist_path(dist_dir: str, url: str) -> str:
        """Map a URL path to the expected file in the dist directory."""
        clean = url.strip("/")
        if not clean:
            return os.path.join(dist_dir, "index.html")
        candidate = os.path.join(dist_dir, clean, "index.html")
        if os.path.isfile(candidate):
            return candidate
        # Try direct .html file (e.g. /404 → dist/404.html)
        return os.path.join(dist_dir, f"{clean}.html")

    @staticmethod
    def _read_generated_page(dist_dir: str, url: str) -> str | None:
        """Read the generated HTML for *url* from *dist_dir*."""
        clean = url.strip("/")
        candidates = []
        if not clean:
            candidates.append(os.path.join(dist_dir, "index.html"))
        else:
            candidates.append(os.path.join(dist_dir, clean, "index.html"))
            candidates.append(os.path.join(dist_dir, f"{clean}.html"))
        for path in candidates:
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as fh:
                    return fh.read()
        return None

    @staticmethod
    def _cleanup(project_dir: str) -> None:
        """Best-effort removal of the temporary project directory."""
        import shutil

        try:
            shutil.rmtree(project_dir, ignore_errors=True)
        except Exception:  # pragma: no cover
            logger.debug("Failed to clean up %s", project_dir, exc_info=True)

    # ------------------------------------------------------------------
    # CMS validation helpers (instance methods)
    # ------------------------------------------------------------------

    async def _run_cms_validation(
        self, context: dict[str, Any], warnings: list[str]
    ) -> CMSValidation:
        """Run all CMS-specific validation checks and return a CMSValidation."""
        base_url = context.get("strapi_base_url", "")
        token = context.get("strapi_api_token", "")
        content_type_map = context.get("content_type_map")
        migration_report = context.get("migration_report")
        content_items = context.get("content_items", [])
        media_url_map: dict[str, str] = context.get("media_url_map", {})

        # Count entries in Strapi
        strapi_count = await count_strapi_entries(base_url, token, content_type_map)

        # Count entries in Export_Bundle
        export_count = len(content_items)

        # Determine failed tolerance from migration report
        failed_count = 0
        if migration_report is not None:
            if hasattr(migration_report, "total_entries_failed"):
                failed_count = migration_report.total_entries_failed
            elif isinstance(migration_report, dict):
                failed_count = migration_report.get("total_entries_failed", 0)

        count_match = validate_content_counts(strapi_count, export_count, failed_count)
        if not count_match:
            warnings.append(
                f"CMS content count mismatch: Strapi={strapi_count}, "
                f"Export={export_count}, Failed tolerance={failed_count}"
            )

        # Check media URLs
        media_checked, media_valid = await check_media_urls(media_url_map)
        if media_checked > 0 and media_valid < media_checked:
            warnings.append(
                f"CMS media URL check: {media_valid}/{media_checked} valid"
            )

        return CMSValidation(
            strapi_content_count=strapi_count,
            export_bundle_count=export_count,
            count_match=count_match,
            failed_tolerance=failed_count,
            media_urls_checked=media_checked,
            media_urls_valid=media_valid,
        )

    async def _check_strapi_api_status(self, context: dict[str, Any]) -> str:
        """Check Strapi API health and return a status string for error reports."""
        base_url = context.get("strapi_base_url", "")
        if not base_url:
            return "no strapi_base_url configured"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{base_url.rstrip('/')}/_health")
                return f"{resp.status_code}"
        except httpx.HTTPError as exc:
            return f"unreachable ({exc})"

