"""Shared pipeline context models and extraction helpers."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.models.content import WordPressContentItem
from src.models.inventory import Inventory
from src.models.modeling_manifest import ModelingManifest
from src.models.strapi_types import ContentTypeMap


class MediaManifestEntry(BaseModel):
    """Normalized media entry extracted from an export bundle."""

    source_url: str
    bundle_path: str
    artifact_path: str
    filename: str = ""
    alt_text: str = ""
    caption: str = ""
    mime_type: str = ""
    metadata: dict[str, Any] | None = None

    @property
    def public_url(self) -> str:
        """Return the public URL inside the generated Astro project."""
        return "/" + self.artifact_path.lstrip("/")


class BundleArtifacts(BaseModel):
    """Canonical normalized bundle artifacts passed between agents."""

    export_bundle: dict[str, Any] = Field(default_factory=dict)
    content_items: list[WordPressContentItem] = Field(default_factory=list)
    menus: list[dict[str, Any]] = Field(default_factory=list)
    redirect_rules: list[dict[str, Any]] = Field(default_factory=list)
    html_snapshots: dict[str, str] = Field(default_factory=dict)
    media_manifest: list[MediaManifestEntry] = Field(default_factory=list)


def extract_inventory(context: dict[str, Any]) -> Inventory:
    """Extract an :class:`Inventory` from pipeline context."""
    raw = context.get("inventory")
    if raw is None:
        raise KeyError("'inventory' missing from pipeline context")
    if isinstance(raw, Inventory):
        return raw
    return Inventory.model_validate(raw)


def extract_modeling_manifest(context: dict[str, Any]) -> ModelingManifest:
    """Extract a :class:`ModelingManifest` from pipeline context."""
    raw = context.get("modeling_manifest")
    if raw is None:
        raise KeyError("'modeling_manifest' missing from pipeline context")
    if isinstance(raw, ModelingManifest):
        return raw
    return ModelingManifest.model_validate(raw)


def extract_content_type_map(context: dict[str, Any]) -> ContentTypeMap:
    """Extract a :class:`ContentTypeMap` from pipeline context."""
    raw = context.get("content_type_map")
    if raw is None:
        raise KeyError("'content_type_map' missing from pipeline context")
    if isinstance(raw, ContentTypeMap):
        return raw
    return ContentTypeMap.model_validate(raw)


def extract_content_items(context: dict[str, Any]) -> list[WordPressContentItem]:
    """Extract normalized WordPress content items from pipeline context."""
    raw_items = context.get("content_items", [])
    items: list[WordPressContentItem] = []
    for raw in raw_items:
        if isinstance(raw, WordPressContentItem):
            items.append(raw)
        else:
            items.append(WordPressContentItem.model_validate(raw))
    return items


def extract_menus(context: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract normalized menu definitions from pipeline context."""
    raw = context.get("menus", [])
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def extract_redirect_rules(context: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract normalized redirect rules from pipeline context."""
    raw = context.get("redirect_rules", [])
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def extract_media_manifest(
    context: dict[str, Any],
) -> list[MediaManifestEntry]:
    """Extract normalized media manifest entries from pipeline context."""
    raw_entries = context.get("media_manifest", [])
    entries: list[MediaManifestEntry] = []
    for raw in raw_entries:
        if isinstance(raw, MediaManifestEntry):
            entries.append(raw)
        else:
            entries.append(MediaManifestEntry.model_validate(raw))
    return entries


def extract_bundle_artifacts(context: dict[str, Any]) -> BundleArtifacts:
    """Build a canonical :class:`BundleArtifacts` view over the pipeline context."""
    return BundleArtifacts(
        export_bundle=context.get("export_bundle", {}),
        content_items=extract_content_items(context),
        menus=extract_menus(context),
        redirect_rules=extract_redirect_rules(context),
        html_snapshots=context.get("html_snapshots", {}),
        media_manifest=extract_media_manifest(context),
    )
