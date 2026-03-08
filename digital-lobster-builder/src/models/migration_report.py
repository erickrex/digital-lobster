from typing import Any

from pydantic import BaseModel

from src.utils.scrubbing import scrub_credentials


class ContentTypeMigrationStats(BaseModel):
    """Migration statistics for a single content type."""

    content_type: str
    total: int
    succeeded: int
    failed: int
    skipped: int
    failed_entries: list[str]  # Titles of failed entries


class MediaMigrationStats(BaseModel):
    """Migration statistics for media uploads."""

    total: int
    succeeded: int
    failed: int
    failed_urls: list[str]  # Original URLs that failed


class MigrationReport(BaseModel):
    """Complete report of the content migration process."""

    content_stats: list[ContentTypeMigrationStats]
    media_stats: MediaMigrationStats
    taxonomy_terms_created: int
    menu_entries_created: int
    total_entries_succeeded: int
    total_entries_failed: int
    total_entries_skipped: int
    warnings: list[str]

    def to_safe_dict(self) -> dict[str, Any]:
        """Return a dict with any credentials scrubbed as a safety net."""
        return scrub_credentials(self.model_dump())
