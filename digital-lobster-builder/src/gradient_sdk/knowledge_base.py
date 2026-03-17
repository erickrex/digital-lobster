from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx
from gradient import AsyncGradient, APITimeoutError, APIError

DO_PROJECTS_URL = "https://api.digitalocean.com/v2/projects"

logger = logging.getLogger(__name__)

MAX_UPLOAD_RETRIES = 2
UPLOAD_BACKOFF_SECONDS = 1.0
UPLOAD_BACKOFF_MULTIPLIER = 2.0
DEFAULT_EMBEDDING_MODEL_UUID = "22653204-79ed-11ef-bf8f-4e013e2ddde4"  # GTE Large EN v1.5
DEFAULT_DB_READY_TIMEOUT = 600.0  # seconds; matches Gradient SDK default
DEFAULT_DB_POLL_INTERVAL = 5.0
DEFAULT_INDEX_READY_TIMEOUT = 60.0
QUERY_INDEX_RETRIES = 6
QUERY_INDEX_BACKOFF = 10.0  # seconds between retries on index-not-found 404s

class KnowledgeBaseClient:
    """Manages per-run Gradient Knowledge Bases."""
    def __init__(
        self,
        access_token: str | None = None,
        *,
        api_key: str | None = None,
        embedding_model_uuid: str = DEFAULT_EMBEDDING_MODEL_UUID,
        project_id: str | None = None,
        region: str | None = None,
        max_upload_retries: int = MAX_UPLOAD_RETRIES,
        upload_backoff: float = UPLOAD_BACKOFF_SECONDS,
        db_ready_timeout: float = DEFAULT_DB_READY_TIMEOUT,
        db_poll_interval: float = DEFAULT_DB_POLL_INTERVAL,
        index_ready_timeout: float = DEFAULT_INDEX_READY_TIMEOUT,
    ) -> None:
        resolved_access_token = (access_token or api_key or "").strip()
        if not resolved_access_token:
            raise ValueError("A DigitalOcean access token is required")

        self._access_token = resolved_access_token
        self._sdk = AsyncGradient(
            access_token=resolved_access_token,
            max_retries=0,  # We handle retries ourselves
        )
        self._embedding_model_uuid = embedding_model_uuid
        self._project_id = project_id
        self._region = region
        self._max_upload_retries = max_upload_retries
        self._upload_backoff = upload_backoff
        self._db_ready_timeout = db_ready_timeout
        self._db_poll_interval = db_poll_interval
        self._index_ready_timeout = index_ready_timeout

    async def create(self, run_id: str, documents: list[dict] | None = None) -> str:
        """Create a new Knowledge Base for a pipeline run.

        The DigitalOcean GenAI API requires at least one datasource at
        creation time.  When *documents* are provided they are uploaded
        via presigned URLs first, then referenced as
        ``file_upload_data_source`` entries in the create call.

        Args:
            run_id: Unique identifier for the pipeline run.
            documents: Optional list of document dicts (each with
                ``content`` and ``metadata`` keys) to seed the KB.

        Returns:
            The Knowledge Base UUID (kb_id).

        Raises:
            APIError: If the Knowledge Base creation fails.
        """
        logger.info("Creating Knowledge Base for run %s", run_id)
        project_id = await self._resolve_project_id()

        datasources: list[dict[str, Any]] = []
        if documents:
            datasources = await self._upload_and_build_datasources(documents)

        create_kwargs: dict[str, Any] = {
            "name": f"migration-run-{run_id}",
            "embedding_model_uuid": self._embedding_model_uuid,
            "project_id": project_id,
            "datasources": datasources,
        }
        if self._region:
            create_kwargs["region"] = self._region

        response = await self._sdk.knowledge_bases.create(**create_kwargs)
        kb_id: str = response.knowledge_base.uuid
        logger.info("Created Knowledge Base %s for run %s", kb_id, run_id)

        # Wait for the vector database to become queryable.
        if datasources:
            logger.info("Waiting for Knowledge Base %s database to come online…", kb_id)
            await self._wait_for_database_safe(kb_id)
            logger.info("Knowledge Base %s database is online", kb_id)

            # The database being ONLINE only means OpenSearch is up.
            # Documents still need to be indexed before queries work.
            await self._wait_for_indexing(kb_id)

        return kb_id

    async def _wait_for_database_safe(self, kb_id: str) -> None:
        """Wrap the SDK's wait_for_database with resilience to transient errors.

        The SDK's polling loop crashes on any HTTP error (e.g. Cloudflare
        challenge pages returning HTML instead of JSON).  We retry the
        entire wait call so a single bad response doesn't abort provisioning.
        """
        attempts = 3
        for attempt in range(1, attempts + 1):
            try:
                await self._sdk.knowledge_bases.wait_for_database(
                    kb_id,
                    timeout=self._db_ready_timeout,
                    poll_interval=self._db_poll_interval,
                )
                return
            except Exception as exc:
                # Truncate the error message — SDK embeds full response
                # bodies (including Cloudflare HTML) in exception messages.
                short_msg = str(exc)[:200]
                if attempt == attempts:
                    logger.error(
                        "KB %s wait_for_database failed after %d attempts: %s",
                        kb_id, attempts, short_msg,
                    )
                    raise
                logger.warning(
                    "KB %s wait_for_database error (attempt %d/%d): %s — retrying",
                    kb_id, attempt, attempts, short_msg,
                )
                await asyncio.sleep(self._db_poll_interval)

    async def _wait_for_indexing(self, kb_id: str) -> None:
        """Poll indexing jobs until all documents are indexed.

        After the database reports ONLINE, the uploaded documents go
        through an asynchronous indexing pipeline.  Queries return 404
        "index not found" until indexing completes.
        """
        if self._index_ready_timeout <= 0:
            logger.info("Skipping KB %s indexing wait (timeout disabled)", kb_id)
            return

        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._index_ready_timeout
        interval = self._db_poll_interval

        while loop.time() < deadline:
            try:
                jobs_resp = await self._sdk.knowledge_bases.list_indexing_jobs(kb_id)
            except APIError as exc:
                logger.warning("Failed to list indexing jobs for KB %s: %s", kb_id, exc)
                await asyncio.sleep(interval)
                continue
            except Exception as exc:
                logger.warning(
                    "Unexpected indexing wait error for KB %s: %s; proceeding without waiting",
                    kb_id,
                    str(exc)[:200],
                )
                return

            jobs = getattr(jobs_resp, "jobs", None) or []
            if not jobs:
                # No jobs yet — indexing hasn't started, keep waiting.
                logger.info("KB %s: no indexing jobs yet, waiting…", kb_id)
                await asyncio.sleep(interval)
                continue

            latest = jobs[0]
            status = getattr(latest, "status", None) or "unknown"
            if "COMPLETED" in status or "NO_CHANGES" in status:
                logger.info("KB %s indexing completed (status=%s)", kb_id, status)
                return
            if "FAILED" in status or "ERROR" in status or "CANCELLED" in status:
                logger.error("KB %s indexing failed (status=%s)", kb_id, status)
                return  # Let query-time retries handle it

            logger.info("KB %s indexing status: %s, waiting…", kb_id, status)
            await asyncio.sleep(interval)

        logger.warning(
            "KB %s indexing did not complete within timeout, proceeding anyway",
            kb_id,
        )

    async def _upload_and_build_datasources(
        self, documents: list[dict],
    ) -> list[dict[str, Any]]:
        """Upload documents via presigned URLs and return datasource dicts.

        Each uploaded file becomes a ``file_upload_data_source`` entry
        suitable for the ``datasources`` parameter of
        ``knowledge_bases.create``.
        """
        backoff = self._upload_backoff

        for attempt in range(1, self._max_upload_retries + 1):
            try:
                # Build file descriptors for presigned URL request
                files = []
                encoded: list[bytes] = []
                for i, doc in enumerate(documents):
                    file_name = doc.get("metadata", {}).get("file", f"doc_{i}.json")
                    content_bytes = json.dumps(doc).encode("utf-8")
                    encoded.append(content_bytes)
                    files.append({
                        "file_name": file_name,
                        "file_size": str(len(content_bytes)),
                    })

                presigned_resp = await (
                    self._sdk.knowledge_bases.data_sources.create_presigned_urls(
                        files=files,
                    )
                )

                # Upload each document to its presigned URL
                datasources: list[dict[str, Any]] = []
                async with httpx.AsyncClient() as http:
                    for i, upload in enumerate(presigned_resp.uploads):
                        put_resp = await http.put(
                            upload.presigned_url,
                            content=encoded[i],
                            headers={"Content-Type": "application/json"},
                        )
                        put_resp.raise_for_status()
                        datasources.append({
                            "file_upload_data_source": {
                                "original_file_name": upload.original_file_name,
                                "stored_object_key": upload.object_key,
                                "size_in_bytes": str(len(encoded[i])),
                            },
                        })

                logger.info(
                    "Uploaded %d document(s) via presigned URLs",
                    len(documents),
                )
                return datasources

            except (APITimeoutError, APIError, httpx.HTTPStatusError) as exc:
                if attempt == self._max_upload_retries:
                    logger.error(
                        "Presigned upload failed after %d attempts: %s",
                        attempt,
                        exc,
                    )
                    raise
                logger.warning(
                    "Presigned upload failed (attempt %d/%d), retrying in %.1fs…",
                    attempt,
                    self._max_upload_retries,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff *= UPLOAD_BACKOFF_MULTIPLIER

        raise RuntimeError("Exhausted upload retries without raising")  # pragma: no cover

    async def query(
        self, kb_id: str, query: str, top_k: int = 5
    ) -> list[dict]:
        """RAG query against the Knowledge Base.

        Retries transparently on 404 "index not found" errors, which can
        occur briefly after the database reports ONLINE but before the
        search index is fully warmed up.

        Args:
            kb_id: The Knowledge Base UUID.
            query: The search query string.
            top_k: Maximum number of results to return.

        Returns:
            A list of result dicts, each containing ``content`` and
            ``metadata`` keys.

        Raises:
            APIError: If the query fails after retries.
        """
        backoff = QUERY_INDEX_BACKOFF
        for attempt in range(1, QUERY_INDEX_RETRIES + 1):
            try:
                response = await self._sdk.retrieve.documents(
                    knowledge_base_id=kb_id,
                    query=query,
                    num_results=top_k,
                )
                results: list[dict[str, Any]] = []
                for result in response.results:
                    results.append({
                        "content": result.text_content,
                        "metadata": result.metadata,
                    })
                return results
            except APIError as exc:
                is_index_not_found = (
                    getattr(exc, "status_code", None) == 404
                    and "index not found" in str(exc).lower()
                )
                if not is_index_not_found or attempt == QUERY_INDEX_RETRIES:
                    raise
                logger.warning(
                    "KB %s index not ready (attempt %d/%d), retrying in %.0fs…",
                    kb_id, attempt, QUERY_INDEX_RETRIES, backoff,
                )
                await asyncio.sleep(backoff)

    async def delete(self, kb_id: str) -> None:
        """Clean up a Knowledge Base after pipeline completion.

        Args:
            kb_id: The Knowledge Base UUID to delete.

        Raises:
            APIError: If the deletion fails.
        """
        logger.info("Deleting Knowledge Base %s", kb_id)
        await self._sdk.knowledge_bases.delete(uuid=kb_id)
        logger.info("Deleted Knowledge Base %s", kb_id)

    async def _resolve_project_id(self) -> str:
        """Return the project ID, fetching the default project if needed."""
        if self._project_id:
            return self._project_id

        async with httpx.AsyncClient() as http:
            resp = await http.get(
                DO_PROJECTS_URL,
                headers={"Authorization": f"Bearer {self._access_token}"},
            )
            resp.raise_for_status()
            projects = resp.json().get("projects", [])

        for proj in projects:
            if proj.get("is_default"):
                self._project_id = proj["id"]
                logger.info("Resolved default DO project: %s", self._project_id)
                return self._project_id

        if projects:
            self._project_id = projects[0]["id"]
            logger.warning(
                "No default project found, using first project: %s",
                self._project_id,
            )
            return self._project_id

        raise RuntimeError("No DigitalOcean projects found for this account")

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._sdk.close()
