"""Gradient Knowledge Base management for per-run RAG retrieval.

Each pipeline run creates a dedicated Knowledge Base, uploads relevant
export artifacts, and agents query it for context. This isolates runs
and keeps LLM context windows manageable for large sites.

Upload failures are retried up to 2 times before failing the agent.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx
from gradient import AsyncGradient, APITimeoutError, APIError

logger = logging.getLogger(__name__)

MAX_UPLOAD_RETRIES = 2
UPLOAD_BACKOFF_SECONDS = 1.0
UPLOAD_BACKOFF_MULTIPLIER = 2.0


class KnowledgeBaseClient:
    """Manages per-run Gradient Knowledge Bases."""

    def __init__(
        self,
        api_key: str,
        max_upload_retries: int = MAX_UPLOAD_RETRIES,
        upload_backoff: float = UPLOAD_BACKOFF_SECONDS,
    ) -> None:
        self._sdk = AsyncGradient(
            model_access_key=api_key,
            max_retries=0,  # We handle retries ourselves
        )
        self._max_upload_retries = max_upload_retries
        self._upload_backoff = upload_backoff

    async def create(self, run_id: str) -> str:
        """Create a new Knowledge Base for a pipeline run.

        Args:
            run_id: Unique identifier for the pipeline run.

        Returns:
            The Knowledge Base UUID (kb_id).

        Raises:
            APIError: If the Knowledge Base creation fails.
        """
        logger.info("Creating Knowledge Base for run %s", run_id)
        response = await self._sdk.knowledge_bases.create(
            name=f"migration-run-{run_id}",
        )
        kb_id: str = response.knowledge_base.uuid
        logger.info("Created Knowledge Base %s for run %s", kb_id, run_id)
        return kb_id

    async def upload_documents(
        self, kb_id: str, documents: list[dict]
    ) -> None:
        """Upload export artifacts as documents to the Knowledge Base.

        Uses presigned URLs to upload document content as JSON files.
        The ``knowledge_base_id`` is passed to presigned URL creation so
        uploaded documents are scoped to the target Knowledge Base.

        Retries up to ``max_upload_retries`` times on failure, then raises.

        Args:
            kb_id: The Knowledge Base UUID.
            documents: List of document dicts, each with at least
                ``content`` (str) and ``metadata`` (dict) keys.

        Raises:
            APIError: After exhausting all retries on upload failure.
            APITimeoutError: After exhausting all retries on timeout.
        """
        backoff = self._upload_backoff

        for attempt in range(1, self._max_upload_retries + 1):
            try:
                # Build file descriptors for presigned URL request
                files = []
                for i, doc in enumerate(documents):
                    file_name = doc.get("metadata", {}).get("file", f"doc_{i}.json")
                    content_bytes = json.dumps(doc).encode("utf-8")
                    files.append({
                        "file_name": file_name,
                        "file_size": str(len(content_bytes)),
                    })

                # Get presigned upload URLs
                create_presigned_urls = (
                    self._sdk.knowledge_bases.data_sources.create_presigned_urls
                )
                try:
                    presigned_resp = await create_presigned_urls(
                        files=files,
                        knowledge_base_id=kb_id,
                    )
                except TypeError:
                    # Backward compatibility with SDK versions that don't accept
                    # knowledge_base_id on this endpoint.
                    presigned_resp = await create_presigned_urls(files=files)

                # Upload each document to its presigned URL
                async with httpx.AsyncClient() as http:
                    for i, upload in enumerate(presigned_resp.uploads):
                        content_bytes = json.dumps(documents[i]).encode("utf-8")
                        put_resp = await http.put(
                            upload.presigned_url,
                            content=content_bytes,
                            headers={"Content-Type": "application/json"},
                        )
                        put_resp.raise_for_status()

                logger.info(
                    "Uploaded %d document(s) to Knowledge Base %s",
                    len(documents),
                    kb_id,
                )
                return

            except (APITimeoutError, APIError, httpx.HTTPStatusError) as exc:
                if attempt == self._max_upload_retries:
                    logger.error(
                        "Knowledge Base upload failed after %d attempts for kb %s: %s",
                        attempt,
                        kb_id,
                        exc,
                    )
                    raise
                logger.warning(
                    "Knowledge Base upload failed (attempt %d/%d), "
                    "retrying in %.1fs…",
                    attempt,
                    self._max_upload_retries,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff *= UPLOAD_BACKOFF_MULTIPLIER

    async def query(
        self, kb_id: str, query: str, top_k: int = 5
    ) -> list[dict]:
        """RAG query against the Knowledge Base.

        Args:
            kb_id: The Knowledge Base UUID.
            query: The search query string.
            top_k: Maximum number of results to return.

        Returns:
            A list of result dicts, each containing ``content`` and
            ``metadata`` keys.

        Raises:
            APIError: If the query fails.
        """
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

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._sdk.close()
