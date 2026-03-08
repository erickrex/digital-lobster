from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from gradient import APITimeoutError, APIError

from src.gradient.knowledge_base import (
    KnowledgeBaseClient,
    MAX_UPLOAD_RETRIES,
    UPLOAD_BACKOFF_SECONDS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_api_error(message: str = "server error") -> APIError:
    """Build an APIError matching the gradient SDK constructor."""
    request = httpx.Request("POST", "https://api.gradient.ai")
    return APIError(message, request=request, body=None)


def _make_timeout_error() -> APITimeoutError:
    request = httpx.Request("POST", "https://api.gradient.ai")
    return APITimeoutError(request=request)


def _make_create_response(kb_uuid: str = "kb-123") -> MagicMock:
    """Build a mock KnowledgeBaseCreateResponse."""
    kb = MagicMock()
    kb.uuid = kb_uuid
    resp = MagicMock()
    resp.knowledge_base = kb
    return resp


def _make_presigned_response(num_uploads: int = 1) -> MagicMock:
    """Build a mock DataSourceCreatePresignedURLsResponse."""
    uploads = []
    for i in range(num_uploads):
        upload = MagicMock()
        upload.presigned_url = f"https://presigned.example.com/upload-{i}"
        upload.object_key = f"obj-key-{i}"
        upload.original_file_name = f"doc_{i}.json"
        uploads.append(upload)
    resp = MagicMock()
    resp.uploads = uploads
    return resp


def _make_query_result(
    text_content: str, metadata: dict | None = None
) -> MagicMock:
    result = MagicMock()
    result.text_content = text_content
    result.metadata = metadata or {}
    return result


def _make_query_response(results: list[MagicMock]) -> MagicMock:
    resp = MagicMock()
    resp.results = results
    resp.total_results = len(results)
    return resp


# ---------------------------------------------------------------------------
# Tests — create()
# ---------------------------------------------------------------------------


class TestCreate:
    """Tests for KnowledgeBaseClient.create()."""

    async def test_returns_kb_uuid(self):
        client = KnowledgeBaseClient(api_key="test-key")
        client._sdk.knowledge_bases.create = AsyncMock(
            return_value=_make_create_response("kb-abc")
        )

        kb_id = await client.create("run-001")
        assert kb_id == "kb-abc"

    async def test_passes_run_id_in_name(self):
        client = KnowledgeBaseClient(api_key="test-key")
        client._sdk.knowledge_bases.create = AsyncMock(
            return_value=_make_create_response()
        )

        await client.create("run-xyz")
        call_kwargs = client._sdk.knowledge_bases.create.call_args.kwargs
        assert "run-xyz" in call_kwargs["name"]

    async def test_propagates_api_error(self):
        client = KnowledgeBaseClient(api_key="test-key")
        client._sdk.knowledge_bases.create = AsyncMock(
            side_effect=_make_api_error("creation failed")
        )

        with pytest.raises(APIError):
            await client.create("run-001")


# ---------------------------------------------------------------------------
# Tests — upload_documents()
# ---------------------------------------------------------------------------


class TestUploadDocuments:
    """Tests for KnowledgeBaseClient.upload_documents()."""

    async def test_uploads_successfully(self):
        client = KnowledgeBaseClient(api_key="test-key")
        client._sdk.knowledge_bases.data_sources.create_presigned_urls = AsyncMock(
            return_value=_make_presigned_response(1)
        )

        docs = [{"content": "hello", "metadata": {"file": "a.json"}}]

        mock_put_resp = MagicMock()
        mock_put_resp.raise_for_status = MagicMock()

        with patch(
            "src.gradient.knowledge_base.httpx.AsyncClient"
        ) as MockClient:
            mock_http = AsyncMock()
            mock_http.put = AsyncMock(return_value=mock_put_resp)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_http

            await client.upload_documents("kb-123", docs)

        # Presigned URL was requested
        client._sdk.knowledge_bases.data_sources.create_presigned_urls.assert_called_once()
        call_kwargs = (
            client._sdk.knowledge_bases.data_sources.create_presigned_urls.call_args.kwargs
        )
        assert call_kwargs["knowledge_base_id"] == "kb-123"
        # File was PUT to the presigned URL
        mock_http.put.assert_called_once()

    async def test_retries_on_api_error(self):
        client = KnowledgeBaseClient(
            api_key="test-key", max_upload_retries=2, upload_backoff=0.0
        )
        # First call fails, second succeeds
        presigned_resp = _make_presigned_response(1)
        client._sdk.knowledge_bases.data_sources.create_presigned_urls = AsyncMock(
            side_effect=[_make_api_error(), presigned_resp]
        )

        mock_put_resp = MagicMock()
        mock_put_resp.raise_for_status = MagicMock()

        docs = [{"content": "data", "metadata": {}}]

        with patch(
            "src.gradient.knowledge_base.httpx.AsyncClient"
        ) as MockClient:
            mock_http = AsyncMock()
            mock_http.put = AsyncMock(return_value=mock_put_resp)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_http

            await client.upload_documents("kb-123", docs)

        assert (
            client._sdk.knowledge_bases.data_sources.create_presigned_urls.call_count
            == 2
        )

    async def test_retries_on_timeout(self):
        client = KnowledgeBaseClient(
            api_key="test-key", max_upload_retries=2, upload_backoff=0.0
        )
        presigned_resp = _make_presigned_response(1)
        client._sdk.knowledge_bases.data_sources.create_presigned_urls = AsyncMock(
            side_effect=[_make_timeout_error(), presigned_resp]
        )

        mock_put_resp = MagicMock()
        mock_put_resp.raise_for_status = MagicMock()

        docs = [{"content": "data", "metadata": {}}]

        with patch(
            "src.gradient.knowledge_base.httpx.AsyncClient"
        ) as MockClient:
            mock_http = AsyncMock()
            mock_http.put = AsyncMock(return_value=mock_put_resp)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_http

            await client.upload_documents("kb-123", docs)

        assert (
            client._sdk.knowledge_bases.data_sources.create_presigned_urls.call_count
            == 2
        )

    async def test_raises_after_exhausting_retries(self):
        client = KnowledgeBaseClient(
            api_key="test-key", max_upload_retries=2, upload_backoff=0.0
        )
        client._sdk.knowledge_bases.data_sources.create_presigned_urls = AsyncMock(
            side_effect=_make_api_error()
        )

        docs = [{"content": "data", "metadata": {}}]
        with pytest.raises(APIError):
            await client.upload_documents("kb-123", docs)

        assert (
            client._sdk.knowledge_bases.data_sources.create_presigned_urls.call_count
            == 2
        )

    async def test_raises_timeout_after_exhausting_retries(self):
        client = KnowledgeBaseClient(
            api_key="test-key", max_upload_retries=2, upload_backoff=0.0
        )
        client._sdk.knowledge_bases.data_sources.create_presigned_urls = AsyncMock(
            side_effect=_make_timeout_error()
        )

        docs = [{"content": "data", "metadata": {}}]
        with pytest.raises(APITimeoutError):
            await client.upload_documents("kb-123", docs)

        assert (
            client._sdk.knowledge_bases.data_sources.create_presigned_urls.call_count
            == 2
        )

    async def test_exponential_backoff_on_retry(self):
        client = KnowledgeBaseClient(
            api_key="test-key", max_upload_retries=2, upload_backoff=1.0
        )
        client._sdk.knowledge_bases.data_sources.create_presigned_urls = AsyncMock(
            side_effect=_make_api_error()
        )

        with patch(
            "src.gradient.knowledge_base.asyncio.sleep",
            new_callable=AsyncMock,
        ) as mock_sleep:
            with pytest.raises(APIError):
                await client.upload_documents(
                    "kb-123", [{"content": "x", "metadata": {}}]
                )

        # 1 sleep: after attempt 1 fails, before attempt 2 (which also fails)
        mock_sleep.assert_called_once_with(1.0)

    async def test_no_retry_on_first_success(self):
        client = KnowledgeBaseClient(
            api_key="test-key", max_upload_retries=2, upload_backoff=0.0
        )
        client._sdk.knowledge_bases.data_sources.create_presigned_urls = AsyncMock(
            return_value=_make_presigned_response(1)
        )

        mock_put_resp = MagicMock()
        mock_put_resp.raise_for_status = MagicMock()

        with patch(
            "src.gradient.knowledge_base.httpx.AsyncClient"
        ) as MockClient:
            mock_http = AsyncMock()
            mock_http.put = AsyncMock(return_value=mock_put_resp)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_http

            await client.upload_documents(
                "kb-123", [{"content": "ok", "metadata": {}}]
            )

        assert (
            client._sdk.knowledge_bases.data_sources.create_presigned_urls.call_count
            == 1
        )

    async def test_retries_on_http_put_failure(self):
        """Retry when the presigned URL PUT itself fails."""
        client = KnowledgeBaseClient(
            api_key="test-key", max_upload_retries=2, upload_backoff=0.0
        )
        presigned_resp = _make_presigned_response(1)
        client._sdk.knowledge_bases.data_sources.create_presigned_urls = AsyncMock(
            return_value=presigned_resp
        )

        # First PUT raises HTTPStatusError, second attempt succeeds
        fail_response = httpx.Response(
            status_code=500,
            request=httpx.Request("PUT", "https://presigned.example.com/upload-0"),
        )
        ok_resp = MagicMock()
        ok_resp.raise_for_status = MagicMock()

        call_count = 0

        async def mock_put_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.HTTPStatusError(
                    "Server Error", request=fail_response.request, response=fail_response
                )
            return ok_resp

        with patch(
            "src.gradient.knowledge_base.httpx.AsyncClient"
        ) as MockClient:
            mock_http = AsyncMock()
            mock_http.put = AsyncMock(side_effect=mock_put_side_effect)
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_http

            await client.upload_documents(
                "kb-123", [{"content": "data", "metadata": {}}]
            )

        # Both attempts called create_presigned_urls (full retry loop)
        assert (
            client._sdk.knowledge_bases.data_sources.create_presigned_urls.call_count
            == 2
        )


# ---------------------------------------------------------------------------
# Tests — query()
# ---------------------------------------------------------------------------


class TestQuery:
    """Tests for KnowledgeBaseClient.query()."""

    async def test_returns_results(self):
        client = KnowledgeBaseClient(api_key="test-key")
        mock_results = [
            _make_query_result("doc1 content", {"file": "a.json"}),
            _make_query_result("doc2 content"),
        ]
        client._sdk.retrieve.documents = AsyncMock(
            return_value=_make_query_response(mock_results)
        )

        results = await client.query("kb-123", "what is the site name?")

        assert len(results) == 2
        assert results[0]["content"] == "doc1 content"
        assert results[0]["metadata"] == {"file": "a.json"}
        assert results[1]["content"] == "doc2 content"

    async def test_passes_top_k_as_num_results(self):
        client = KnowledgeBaseClient(api_key="test-key")
        client._sdk.retrieve.documents = AsyncMock(
            return_value=_make_query_response([])
        )

        await client.query("kb-123", "search", top_k=10)

        call_kwargs = client._sdk.retrieve.documents.call_args.kwargs
        assert call_kwargs["num_results"] == 10

    async def test_default_top_k_is_five(self):
        client = KnowledgeBaseClient(api_key="test-key")
        client._sdk.retrieve.documents = AsyncMock(
            return_value=_make_query_response([])
        )

        await client.query("kb-123", "search")

        call_kwargs = client._sdk.retrieve.documents.call_args.kwargs
        assert call_kwargs["num_results"] == 5

    async def test_returns_empty_list_for_no_results(self):
        client = KnowledgeBaseClient(api_key="test-key")
        client._sdk.retrieve.documents = AsyncMock(
            return_value=_make_query_response([])
        )

        results = await client.query("kb-123", "nothing here")
        assert results == []

    async def test_propagates_api_error(self):
        client = KnowledgeBaseClient(api_key="test-key")
        client._sdk.retrieve.documents = AsyncMock(
            side_effect=_make_api_error("query failed")
        )

        with pytest.raises(APIError):
            await client.query("kb-123", "search")


# ---------------------------------------------------------------------------
# Tests — delete()
# ---------------------------------------------------------------------------


class TestDelete:
    """Tests for KnowledgeBaseClient.delete()."""

    async def test_deletes_knowledge_base(self):
        client = KnowledgeBaseClient(api_key="test-key")
        client._sdk.knowledge_bases.delete = AsyncMock(return_value=None)

        await client.delete("kb-123")

        client._sdk.knowledge_bases.delete.assert_called_once_with(
            uuid="kb-123",
        )

    async def test_propagates_api_error(self):
        client = KnowledgeBaseClient(api_key="test-key")
        client._sdk.knowledge_bases.delete = AsyncMock(
            side_effect=_make_api_error("delete failed")
        )

        with pytest.raises(APIError):
            await client.delete("kb-123")
