"""Download all artifacts for a pipeline run from DO Spaces to output/<run_id>/."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    # python-dotenv not installed; load .env manually
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

# Reuse the project's SpacesClient
from src.storage.spaces import SpacesClient

RUN_ID = "5e4fa9e957064e898fa66b6118042406"

ARTIFACT_NAMES = [
    "inventory",
    "prd_md",
    "modeling_manifest",
    "theme_css",
    "tokens_css",
    "layouts",
    "astro_project",
    "astro_project_zip",
    "content_files",
    "media_map",
    "navigation",
    "redirects",
    "qa_report",
]


async def main() -> None:
    client = SpacesClient(
        access_key=os.environ["DO_SPACES_KEY"],
        secret_key=os.environ["DO_SPACES_SECRET"],
        region=os.environ["DO_SPACES_REGION"],
    )
    bucket = os.environ["DO_SPACES_ARTIFACTS_BUCKET"]
    run_id = sys.argv[1] if len(sys.argv) > 1 else RUN_ID

    out_dir = Path(__file__).parent / "output" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    for name in ARTIFACT_NAMES:
        key = f"{run_id}/{name}"
        print(f"Downloading {key} …", end=" ", flush=True)
        try:
            data = await client.download(bucket, key)
            (out_dir / name).write_bytes(data)
            print(f"{len(data):,} bytes")
        except Exception as exc:
            print(f"FAILED ({exc})")

    print(f"\nDone → {out_dir}")


if __name__ == "__main__":
    asyncio.run(main())
