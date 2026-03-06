"""DigitalOcean Spaces (S3-compatible) storage client.

Uses httpx for upload/download operations and implements AWS Signature V4
presigned URL generation for client-side uploads. DigitalOcean Spaces is
fully S3-compatible, so standard S3 signing works out of the box.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import logging
import urllib.parse
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# S3v4 signing constants
UNSIGNED_PAYLOAD = "UNSIGNED-PAYLOAD"
S3_SERVICE = "s3"
AWS4_REQUEST = "aws4_request"
ALGORITHM = "AWS4-HMAC-SHA256"
DEFAULT_PRESIGN_EXPIRES = 3600  # 1 hour


class SpacesClient:
    """DigitalOcean Spaces (S3-compatible) client."""

    def __init__(
        self,
        access_key: str,
        secret_key: str,
        region: str,
        endpoint_url: str | None = None,
        presign_expires: int = DEFAULT_PRESIGN_EXPIRES,
    ) -> None:
        self._access_key = access_key
        self._secret_key = secret_key
        self._region = region
        self._endpoint_url = endpoint_url or f"https://{region}.digitaloceanspaces.com"
        self._presign_expires = presign_expires

    def generate_presigned_upload_url(
        self,
        key: str,
        bucket: str | None = None,
        expires: int | None = None,
    ) -> str:
        """Generate a presigned URL for client-side ZIP upload via PUT.

        Args:
            key: The object key (path) in the bucket.
            bucket: Bucket name. If provided, used as subdomain.
            expires: URL validity in seconds. Defaults to ``presign_expires``.

        Returns:
            A presigned URL string that accepts a PUT request.
        """
        expires = expires or self._presign_expires
        now = datetime.datetime.now(datetime.timezone.utc)
        datestamp = now.strftime("%Y%m%d")
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")

        if bucket:
            host = f"{bucket}.{self._region}.digitaloceanspaces.com"
            url_base = f"https://{host}"
        else:
            host = urllib.parse.urlparse(self._endpoint_url).hostname or ""
            url_base = self._endpoint_url

        canonical_uri = f"/{urllib.parse.quote(key, safe='/')}"
        credential_scope = f"{datestamp}/{self._region}/{S3_SERVICE}/{AWS4_REQUEST}"
        credential = f"{self._access_key}/{credential_scope}"

        query_params = {
            "X-Amz-Algorithm": ALGORITHM,
            "X-Amz-Credential": credential,
            "X-Amz-Date": amz_date,
            "X-Amz-Expires": str(expires),
            "X-Amz-SignedHeaders": "host",
        }
        canonical_querystring = urllib.parse.urlencode(
            sorted(query_params.items())
        )

        canonical_headers = f"host:{host}\n"
        signed_headers = "host"

        canonical_request = "\n".join([
            "PUT",
            canonical_uri,
            canonical_querystring,
            canonical_headers,
            signed_headers,
            UNSIGNED_PAYLOAD,
        ])

        string_to_sign = "\n".join([
            ALGORITHM,
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ])

        signing_key = _derive_signing_key(
            self._secret_key, datestamp, self._region, S3_SERVICE
        )
        signature = hmac.new(
            signing_key,
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return (
            f"{url_base}{canonical_uri}"
            f"?{canonical_querystring}"
            f"&X-Amz-Signature={signature}"
        )

    async def download(self, bucket: str, key: str) -> bytes:
        """Download an object from Spaces.

        Args:
            bucket: The Spaces bucket name.
            key: The object key (path) within the bucket.

        Returns:
            The raw bytes of the downloaded object.

        Raises:
            httpx.HTTPStatusError: If the download request fails.
        """
        url = self._object_url(bucket, key)
        headers = self._sign_request("GET", bucket, key)

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.content

    async def upload(self, bucket: str, key: str, data: bytes) -> None:
        """Upload an object to Spaces.

        Args:
            bucket: The Spaces bucket name.
            key: The object key (path) within the bucket.
            data: The raw bytes to upload.

        Raises:
            httpx.HTTPStatusError: If the upload request fails.
        """
        url = self._object_url(bucket, key)
        content_sha256 = hashlib.sha256(data).hexdigest()
        headers = self._sign_request(
            "PUT", bucket, key, payload_hash=content_sha256
        )
        headers["Content-Type"] = "application/octet-stream"

        async with httpx.AsyncClient() as client:
            response = await client.put(url, content=data, headers=headers)
            response.raise_for_status()

        logger.info("Uploaded %d bytes to s3://%s/%s", len(data), bucket, key)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _object_url(self, bucket: str, key: str) -> str:
        """Build the full URL for an object in a bucket."""
        host = f"{bucket}.{self._region}.digitaloceanspaces.com"
        encoded_key = urllib.parse.quote(key, safe="/")
        return f"https://{host}/{encoded_key}"

    def _sign_request(
        self,
        method: str,
        bucket: str,
        key: str,
        payload_hash: str | None = None,
    ) -> dict[str, str]:
        """Generate AWS Signature V4 authorization headers.

        Args:
            method: HTTP method (GET, PUT, etc.).
            bucket: Bucket name.
            key: Object key.
            payload_hash: SHA-256 hex digest of the payload body.
                Defaults to the empty-body hash for GET requests.

        Returns:
            A dict of headers including Authorization, x-amz-date,
            and x-amz-content-sha256.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        datestamp = now.strftime("%Y%m%d")
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")

        host = f"{bucket}.{self._region}.digitaloceanspaces.com"
        canonical_uri = f"/{urllib.parse.quote(key, safe='/')}"

        if payload_hash is None:
            payload_hash = hashlib.sha256(b"").hexdigest()

        canonical_headers = (
            f"host:{host}\n"
            f"x-amz-content-sha256:{payload_hash}\n"
            f"x-amz-date:{amz_date}\n"
        )
        signed_headers = "host;x-amz-content-sha256;x-amz-date"

        canonical_request = "\n".join([
            method,
            canonical_uri,
            "",  # empty query string
            canonical_headers,
            signed_headers,
            payload_hash,
        ])

        credential_scope = f"{datestamp}/{self._region}/{S3_SERVICE}/{AWS4_REQUEST}"

        string_to_sign = "\n".join([
            ALGORITHM,
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ])

        signing_key = _derive_signing_key(
            self._secret_key, datestamp, self._region, S3_SERVICE
        )
        signature = hmac.new(
            signing_key,
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        authorization = (
            f"{ALGORITHM} "
            f"Credential={self._access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )

        return {
            "Authorization": authorization,
            "x-amz-date": amz_date,
            "x-amz-content-sha256": payload_hash,
        }


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _derive_signing_key(
    secret_key: str, datestamp: str, region: str, service: str
) -> bytes:
    """Derive the AWS Signature V4 signing key."""
    k_date = _hmac_sha256(
        f"AWS4{secret_key}".encode("utf-8"), datestamp
    )
    k_region = _hmac_sha256(k_date, region)
    k_service = _hmac_sha256(k_region, service)
    return _hmac_sha256(k_service, AWS4_REQUEST)


def _hmac_sha256(key: bytes, msg: str) -> bytes:
    """Compute HMAC-SHA256."""
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()
