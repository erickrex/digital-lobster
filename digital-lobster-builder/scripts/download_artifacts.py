"""Download pipeline artifacts from DigitalOcean Spaces.

Usage:
    uv run python scripts/download_artifacts.py <run_id> [--output-dir ./output]

Connects using the same DO_SPACES_* credentials from .env.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Add project root to path so we can import src modules
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.storage.spaces import SpacesClient


def _load_env(env_file: Path) -> None:
    """Minimal .env loader (no-override)."""
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip().strip("\"'")
        os.environ.setdefault(key, value)


async def list_objects(client: SpacesClient, bucket: str, prefix: str) -> list[str]:
    """List object keys under a prefix using the S3 ListObjectsV2 XML API."""
    import datetime
    import hashlib
    import hmac
    import urllib.parse

    import httpx
    from src.storage.spaces import (
        ALGORITHM, AWS4_REQUEST, S3_SERVICE, _derive_signing_key,
    )

    host = f"{bucket}.{client._region}.digitaloceanspaces.com"
    now = datetime.datetime.now(datetime.timezone.utc)
    datestamp = now.strftime("%Y%m%d")
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    payload_hash = hashlib.sha256(b"").hexdigest()

    # S3v4 requires query params to be URI-encoded in the canonical request.
    # urllib.parse.quote with safe="" encodes '/' as '%2F' which S3 expects.
    query_params = {
        "list-type": "2",
        "prefix": prefix,
    }
    canonical_querystring = "&".join(
        f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
        for k, v in sorted(query_params.items())
    )

    canonical_headers = (
        f"host:{host}\n"
        f"x-amz-content-sha256:{payload_hash}\n"
        f"x-amz-date:{amz_date}\n"
    )
    signed_headers = "host;x-amz-content-sha256;x-amz-date"

    canonical_request = "\n".join([
        "GET", "/", canonical_querystring,
        canonical_headers, signed_headers, payload_hash,
    ])
    credential_scope = f"{datestamp}/{client._region}/{S3_SERVICE}/{AWS4_REQUEST}"
    string_to_sign = "\n".join([
        ALGORITHM, amz_date, credential_scope,
        hashlib.sha256(canonical_request.encode()).hexdigest(),
    ])
    signing_key = _derive_signing_key(
        client._secret_key, datestamp, client._region, S3_SERVICE,
    )
    signature = hmac.new(
        signing_key, string_to_sign.encode(), hashlib.sha256,
    ).hexdigest()

    authorization = (
        f"{ALGORITHM} "
        f"Credential={client._access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )
    req_headers = {
        "Authorization": authorization,
        "x-amz-date": amz_date,
        "x-amz-content-sha256": payload_hash,
    }

    # Build the URL with the exact same encoded query string we signed.
    # Use httpx.URL directly to prevent httpx from re-encoding the query.
    raw_url = f"https://{host}/?{canonical_querystring}"
    async with httpx.AsyncClient() as http:
        resp = await http.get(raw_url, headers=req_headers)
        if resp.status_code != 200:
            print(f"S3 ListObjects failed ({resp.status_code}):")
            print(resp.text[:500])
        resp.raise_for_status()

    root = ET.fromstring(resp.text)
    ns = root.tag.split("}")[0] + "}" if "}" in root.tag else ""
    return [el.text for el in root.findall(f".//{ns}Key") if el.text]


async def main(run_id: str, output_dir: Path) -> None:
    env_file = Path(__file__).resolve().parents[1] / ".env"
    _load_env(env_file)

    client = SpacesClient(
        access_key=os.environ["DO_SPACES_KEY"],
        secret_key=os.environ["DO_SPACES_SECRET"],
        region=os.environ["DO_SPACES_REGION"],
    )
    bucket = os.environ["DO_SPACES_ARTIFACTS_BUCKET"]
    prefix = f"{run_id}/"

    print(f"Listing artifacts in s3://{bucket}/{prefix} …")
    keys = await list_objects(client, bucket, prefix)

    if not keys:
        print("No artifacts found for this run ID.")
        return

    print(f"Found {len(keys)} artifact(s):")
    for k in keys:
        print(f"  {k}")

    output_dir.mkdir(parents=True, exist_ok=True)

    for key in keys:
        name = key.removeprefix(prefix)
        dest = output_dir / name
        print(f"Downloading {key} → {dest} …")
        data = await client.download(bucket, key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        print(f"  {len(data):,} bytes")

    # If there's an astro_project_zip, unzip it
    zip_path = output_dir / "astro_project_zip"
    if zip_path.exists():
        import zipfile
        astro_dir = output_dir / "astro-site"
        print(f"\nExtracting astro_project_zip → {astro_dir}/ …")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(astro_dir)
        print(f"Done! Run your Astro site with:")
        print(f"  cd {astro_dir}")
        print(f"  npm install")
        print(f"  npm run dev")
    else:
        print("\nNo astro_project_zip found in artifacts.")

    print(f"\nAll artifacts saved to {output_dir}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download pipeline artifacts from DO Spaces")
    parser.add_argument("run_id", help="Pipeline run ID")
    parser.add_argument("--output-dir", "-o", default="./output", help="Output directory (default: ./output)")
    args = parser.parse_args()
    asyncio.run(main(args.run_id, Path(args.output_dir)))
