from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class LocalUploadStore:
    """Local filesystem storage for uploaded bundle ZIPs."""

    upload_dir: Path

    def save(self, filename: str, data: bytes) -> str:
        """Save file to disk, return bundle_key (relative path).

        Creates ``upload_dir`` if it does not exist.  The bundle_key is
        ``{uuid_hex}/{original_filename}`` so every upload gets a unique
        directory while preserving the original name.
        """
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        bundle_key = f"{uuid.uuid4().hex}/{filename}"
        dest = self.upload_dir / bundle_key
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        logger.info("Saved upload %s (%d bytes)", bundle_key, len(data))
        return bundle_key

    def get_path(self, bundle_key: str) -> Path:
        """Resolve a bundle_key to an absolute path."""
        return (self.upload_dir / bundle_key).resolve()
