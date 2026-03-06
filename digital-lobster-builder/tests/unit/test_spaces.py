"""Unit tests for the DigitalOcean Spaces storage client."""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.storage.spaces import (
    SpacesClient,
    _derive_signing_key,
    _hmac_sha256,
    ALGORITHM,
    DEFAULT_PRESIGN_EXPIRES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_ACCESS_KEY = "DO_TEST_ACCESS_KEY"
TEST_SECRET_KEY = "DO_TEST_SECRET_KEY"
TEST_REGION = "nyc3"


def _make_client(**overrides) -> SpacesClient:
    defaults = {
        "access_key": TEST_ACCESS_KEY,
        "secret_key": TEST_SECRET_KEY,
        "region": TEST_REGION,
    }
    defaults.update(overrides)
    return SpacesClient(**defaults)


def _mock_http_response(
    status_code: int = 200, content: bytes = b""
) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.content = content
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error",
            request=httpx.Request("GET", "https://example.com"),
            response=resp,
        )
    return resp


# ---------------------------------------------------------------------------
# Tests — generate_presigned_upload_url()
# ---------------------------------------------------------------------------


class TestGeneratePresignedUploadUrl:
    """Tests for SpacesClient.generate_presigned_upload_url()."""

    def test_returns_url_string(self):
        client = _make_client()
        url = client.generate_presigned_upload_url("bundles/test.zip")
        assert isinstance(url, str)
        assert url.startswith("https://")

    def test_url_contains_object_key(self):
        client = _make_client()
        url = client.generate_presigned_upload_url("bundles/test.zip")
        assert "bundles/test.zip" in url

    def test_url_contains_algorithm(self):
        client = _make_client()
        url = client.generate_presigned_upload_url("test.zip")
        assert f"X-Amz-Algorithm={ALGORITHM}" in url

    def test_url_contains_credential(self):
        client = _make_client()
        url = client.generate_presigned_upload_url("test.zip")
        assert f"X-Amz-Credential={TEST_ACCESS_KEY}" in url

    def test_url_contains_signature(self):
        client = _make_client()
        url = client.generate_presigned_upload_url("test.zip")
        assert "X-Amz-Signature=" in url

    def test_url_contains_expiry(self):
        client = _make_client()
        url = client.generate_presigned_upload_url("test.zip")
        assert f"X-Amz-Expires={DEFAULT_PRESIGN_EXPIRES}" in url

    def test_custom_expiry(self):
        client = _make_client()
        url = client.generate_presigned_upload_url("test.zip", expires=600)
        assert "X-Amz-Expires=600" in url

    def test_bucket_subdomain_url(self):
        client = _make_client()
        url = client.generate_presigned_upload_url(
            "test.zip", bucket="my-bucket"
        )
        assert "my-bucket.nyc3.digitaloceanspaces.com" in url

    def test_no_bucket_uses_endpoint(self):
        client = _make_client()
        url = client.generate_presigned_upload_url("test.zip")
        assert "nyc3.digitaloceanspaces.com" in url

    def test_key_with_special_characters(self):
        client = _make_client()
        url = client.generate_presigned_upload_url("path/to/my file.zip")
        assert "path/to/my%20file.zip" in url

    def test_different_regions_produce_different_urls(self):
        client_nyc = _make_client(region="nyc3")
        client_ams = _make_client(region="ams3")
        url_nyc = client_nyc.generate_presigned_upload_url("test.zip")
        url_ams = client_ams.generate_presigned_upload_url("test.zip")
        assert "nyc3" in url_nyc
        assert "ams3" in url_ams
        assert url_nyc != url_ams


# ---------------------------------------------------------------------------
# Tests — download()
# ---------------------------------------------------------------------------


class TestDownload:
    """Tests for SpacesClient.download()."""

    async def test_returns_bytes(self):
        client = _make_client()
        expected = b"zip-file-content"

        with patch("src.storage.spaces.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(
                return_value=_mock_http_response(200, expected)
            )
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_http

            result = await client.download("my-bucket", "bundles/test.zip")

        assert result == expected

    async def test_calls_correct_url(self):
        client = _make_client()

        with patch("src.storage.spaces.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(
                return_value=_mock_http_response(200, b"data")
            )
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_http

            await client.download("my-bucket", "path/to/file.zip")

        call_args = mock_http.get.call_args
        url = call_args[0][0]
        assert "my-bucket.nyc3.digitaloceanspaces.com" in url
        assert "path/to/file.zip" in url

    async def test_includes_auth_headers(self):
        client = _make_client()

        with patch("src.storage.spaces.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(
                return_value=_mock_http_response(200, b"data")
            )
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_http

            await client.download("my-bucket", "test.zip")

        call_kwargs = mock_http.get.call_args[1]
        headers = call_kwargs["headers"]
        assert "Authorization" in headers
        assert ALGORITHM in headers["Authorization"]
        assert "x-amz-date" in headers
        assert "x-amz-content-sha256" in headers

    async def test_raises_on_http_error(self):
        client = _make_client()

        with patch("src.storage.spaces.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_http.get = AsyncMock(
                return_value=_mock_http_response(404)
            )
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_http

            with pytest.raises(httpx.HTTPStatusError):
                await client.download("my-bucket", "missing.zip")


# ---------------------------------------------------------------------------
# Tests — upload()
# ---------------------------------------------------------------------------


class TestUpload:
    """Tests for SpacesClient.upload()."""

    async def test_uploads_data(self):
        client = _make_client()
        data = b"some-binary-data"

        with patch("src.storage.spaces.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_http.put = AsyncMock(
                return_value=_mock_http_response(200)
            )
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_http

            await client.upload("my-bucket", "output/result.zip", data)

        mock_http.put.assert_called_once()

    async def test_calls_correct_url(self):
        client = _make_client()

        with patch("src.storage.spaces.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_http.put = AsyncMock(
                return_value=_mock_http_response(200)
            )
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_http

            await client.upload("artifacts", "run-1/output.zip", b"data")

        call_args = mock_http.put.call_args
        url = call_args[0][0]
        assert "artifacts.nyc3.digitaloceanspaces.com" in url
        assert "run-1/output.zip" in url

    async def test_includes_auth_and_content_headers(self):
        client = _make_client()
        data = b"test-payload"

        with patch("src.storage.spaces.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_http.put = AsyncMock(
                return_value=_mock_http_response(200)
            )
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_http

            await client.upload("my-bucket", "test.zip", data)

        call_kwargs = mock_http.put.call_args[1]
        headers = call_kwargs["headers"]
        assert "Authorization" in headers
        assert ALGORITHM in headers["Authorization"]
        assert headers["Content-Type"] == "application/octet-stream"
        assert headers["x-amz-content-sha256"] == hashlib.sha256(data).hexdigest()

    async def test_sends_correct_body(self):
        client = _make_client()
        data = b"my-upload-payload"

        with patch("src.storage.spaces.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_http.put = AsyncMock(
                return_value=_mock_http_response(200)
            )
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_http

            await client.upload("my-bucket", "test.zip", data)

        call_kwargs = mock_http.put.call_args[1]
        assert call_kwargs["content"] == data

    async def test_raises_on_http_error(self):
        client = _make_client()

        with patch("src.storage.spaces.httpx.AsyncClient") as MockClient:
            mock_http = AsyncMock()
            mock_http.put = AsyncMock(
                return_value=_mock_http_response(500)
            )
            mock_http.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_http

            with pytest.raises(httpx.HTTPStatusError):
                await client.upload("my-bucket", "test.zip", b"data")


# ---------------------------------------------------------------------------
# Tests — signing helpers
# ---------------------------------------------------------------------------


class TestSigningHelpers:
    """Tests for S3v4 signing utility functions."""

    def test_derive_signing_key_returns_bytes(self):
        key = _derive_signing_key("secret", "20240101", "nyc3", "s3")
        assert isinstance(key, bytes)
        assert len(key) == 32  # SHA-256 produces 32 bytes

    def test_derive_signing_key_deterministic(self):
        key1 = _derive_signing_key("secret", "20240101", "nyc3", "s3")
        key2 = _derive_signing_key("secret", "20240101", "nyc3", "s3")
        assert key1 == key2

    def test_derive_signing_key_varies_with_date(self):
        key1 = _derive_signing_key("secret", "20240101", "nyc3", "s3")
        key2 = _derive_signing_key("secret", "20240102", "nyc3", "s3")
        assert key1 != key2

    def test_derive_signing_key_varies_with_region(self):
        key1 = _derive_signing_key("secret", "20240101", "nyc3", "s3")
        key2 = _derive_signing_key("secret", "20240101", "ams3", "s3")
        assert key1 != key2

    def test_hmac_sha256_returns_32_bytes(self):
        result = _hmac_sha256(b"key", "message")
        assert isinstance(result, bytes)
        assert len(result) == 32


# ---------------------------------------------------------------------------
# Tests — _object_url()
# ---------------------------------------------------------------------------


class TestObjectUrl:
    """Tests for SpacesClient._object_url()."""

    def test_builds_correct_url(self):
        client = _make_client()
        url = client._object_url("my-bucket", "path/to/file.zip")
        assert url == "https://my-bucket.nyc3.digitaloceanspaces.com/path/to/file.zip"

    def test_encodes_spaces_in_key(self):
        client = _make_client()
        url = client._object_url("my-bucket", "path/my file.zip")
        assert "my%20file.zip" in url

    def test_preserves_slashes(self):
        client = _make_client()
        url = client._object_url("my-bucket", "a/b/c/d.zip")
        assert "a/b/c/d.zip" in url
