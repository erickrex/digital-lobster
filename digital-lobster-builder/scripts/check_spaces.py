"""Quick connectivity check for DigitalOcean Spaces credentials and buckets.

Uses the project's own SpacesClient (httpx + AWS v4 signing).
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys


def _load_dotenv() -> None:
    """Minimal .env loader — no external dependency needed."""
    env_path = pathlib.Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

KEY = os.getenv("DO_SPACES_KEY", "")
SECRET = os.getenv("DO_SPACES_SECRET", "")
REGION = os.getenv("DO_SPACES_REGION", "fra1")
INGESTION = os.getenv("DO_SPACES_INGESTION_BUCKET", "dl-ingestion")
ARTIFACTS = os.getenv("DO_SPACES_ARTIFACTS_BUCKET", "dl-artifacts")


async def check() -> bool:
    from src.storage.spaces import SpacesClient

    print(f"Region   : {REGION}")
    print(f"Endpoint : https://{REGION}.digitaloceanspaces.com")
    print(f"Key      : {KEY[:8]}...{KEY[-4:]}" if len(KEY) > 12 else f"Key: {KEY}")
    print()

    client = SpacesClient(
        access_key=KEY,
        secret_key=SECRET,
        region=REGION,
    )

    ok = True
    test_key = "_connectivity_test.txt"
    test_data = b"digital-lobster-spaces-check"

    for label, bucket in [("Ingestion", INGESTION), ("Artifacts", ARTIFACTS)]:
        print(f"--- {label} bucket: {bucket} ---")

        # 1. Write
        try:
            await client.upload(bucket, test_key, test_data)
            print(f"  WRITE  OK")
        except Exception as e:
            print(f"  WRITE  FAIL — {type(e).__name__}: {e}")
            ok = False
            print()
            continue

        # 2. Read back
        try:
            data = await client.download(bucket, test_key)
            if data == test_data:
                print(f"  READ   OK — content matches")
            else:
                print(f"  READ   MISMATCH — got {len(data)} bytes")
                ok = False
        except Exception as e:
            print(f"  READ   FAIL — {type(e).__name__}: {e}")
            ok = False

        # 3. Presigned URL generation (smoke test)
        try:
            url = client.generate_presigned_upload_url(key="test.zip", bucket=bucket)
            if url.startswith("https://"):
                print(f"  PRESIGN OK — URL generated")
            else:
                print(f"  PRESIGN FAIL — unexpected URL: {url[:80]}")
                ok = False
        except Exception as e:
            print(f"  PRESIGN FAIL — {type(e).__name__}: {e}")
            ok = False

        # 4. Clean up
        try:
            # No delete method on SpacesClient, so use httpx directly
            import hashlib
            import httpx
            obj_url = client._object_url(bucket, test_key)
            headers = client._sign_request(
                "DELETE", bucket, test_key,
                payload_hash=hashlib.sha256(b"").hexdigest(),
            )
            async with httpx.AsyncClient() as http:
                resp = await http.delete(obj_url, headers=headers)
                if resp.status_code < 300:
                    print(f"  CLEAN  OK — deleted test object")
                else:
                    print(f"  CLEAN  WARN — {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            print(f"  CLEAN  WARN — {type(e).__name__}: {e}")

        print()

    if ok:
        print("All checks passed. Both buckets are reachable and writable.")
    else:
        print("Some checks FAILED — see above.")
    return ok


if __name__ == "__main__":
    result = asyncio.run(check())
    sys.exit(0 if result else 1)
