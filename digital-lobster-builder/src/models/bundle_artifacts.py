from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 1. Content Relationships
# ---------------------------------------------------------------------------

class ContentRelationship(BaseModel):
    """A single relationship between two entities in the source site."""
    source_id: str
    target_id: str
    relation_type: str
    source_plugin: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class ContentRelationshipsArtifact(BaseModel):
    """Normalized relation graph across the site."""
    schema_version: str
    relationships: list[ContentRelationship]

# ---------------------------------------------------------------------------
# 2. Field Usage Report
# ---------------------------------------------------------------------------

class FieldUsageEntry(BaseModel):
    """Per-field analysis for a single content-type field."""
    post_type: str
    field_name: str
    source_plugin: str | None = None
    source_system: str
    inferred_type: str
    nullable: bool
    cardinality: str
    distinct_value_count: int
    sample_values: list[Any]
    behaves_as: str | None = None

class FieldUsageReportArtifact(BaseModel):
    """Normalized field analysis per content type and per field."""
    schema_version: str
    fields: list[FieldUsageEntry]

# ---------------------------------------------------------------------------
# 3. Plugin Instances
# ---------------------------------------------------------------------------

class PluginInstance(BaseModel):
    """A single plugin construct actually in use on the site."""
    instance_id: str
    source_plugin: str
    instance_type: str
    config: dict[str, Any] = Field(default_factory=dict)
    references: list[str] = Field(default_factory=list)

class PluginInstancesArtifact(BaseModel):
    """Inventory of actual plugin constructs in use."""
    schema_version: str
    instances: list[PluginInstance]

# ---------------------------------------------------------------------------
# 4. Page Composition
# ---------------------------------------------------------------------------

class PageCompositionEntry(BaseModel):
    """Resolved composition map for a single page."""
    canonical_url: str
    template: str
    blocks: list[dict[str, Any]]
    shortcodes: list[dict[str, Any]]
    widget_placements: list[dict[str, Any]]
    forms_embedded: list[str]
    plugin_components: list[dict[str, Any]]
    enqueued_assets: list[str]
    content_sections: list[dict[str, Any]]
    snapshot_ref: str | None = None

class PageCompositionArtifact(BaseModel):
    """Per-page resolved composition maps."""
    schema_version: str
    pages: list[PageCompositionEntry]

# ---------------------------------------------------------------------------
# 5. SEO Full
# ---------------------------------------------------------------------------

class SeoPageEntry(BaseModel):
    """Normalized SEO metadata for a single page."""
    canonical_url: str
    source_plugin: str
    robots: str | None = None
    noindex: bool = False
    nofollow: bool = False
    title_template: str | None = None
    resolved_title: str | None = None
    meta_description: str | None = None
    og_metadata: dict[str, Any] = Field(default_factory=dict)
    twitter_metadata: dict[str, Any] = Field(default_factory=dict)
    schema_type_hints: list[str] = Field(default_factory=list)
    breadcrumb_config: dict[str, Any] | None = None
    sitemap_inclusion: bool = True
    redirect_ownership: dict[str, Any] | None = None

class SeoFullArtifact(BaseModel):
    """Normalized per-page SEO data."""
    schema_version: str
    pages: list[SeoPageEntry]

# ---------------------------------------------------------------------------
# 6. Editorial Workflows
# ---------------------------------------------------------------------------

class EditorialWorkflowsArtifact(BaseModel):
    """Editorial behavior profile for the source site."""
    schema_version: str
    statuses_in_use: list[str]
    scheduled_publishing: bool
    draft_behavior: str
    preview_expectations: str
    revision_policy: str
    comments_enabled: bool
    authoring_model: str

# ---------------------------------------------------------------------------
# 7. Plugin Table Export
# ---------------------------------------------------------------------------

class PluginTableExport(BaseModel):
    """Structured export of a single plugin-owned database table."""
    table_name: str
    schema_version: str
    source_plugin: str
    row_count: int
    primary_key: str
    foreign_key_candidates: list[str]
    rows: list[dict[str, Any]]

# ---------------------------------------------------------------------------
# 8. Search Config
# ---------------------------------------------------------------------------

class SearchConfigArtifact(BaseModel):
    """Normalized search and filtering configuration."""
    schema_version: str
    searchable_types: list[str]
    ranking_hints: list[dict[str, Any]]
    facets: list[dict[str, Any]]
    archive_behavior: dict[str, Any] = Field(default_factory=dict)
    search_template_hints: dict[str, Any] = Field(default_factory=dict)

# ---------------------------------------------------------------------------
# 9. Integration Manifest
# ---------------------------------------------------------------------------

class IntegrationEntry(BaseModel):
    """A single external integration detected on the source site."""
    integration_id: str
    integration_type: str
    target: str
    config: dict[str, Any] = Field(default_factory=dict)
    business_critical: bool = False

class IntegrationManifestArtifact(BaseModel):
    """Inventory of external integrations."""
    schema_version: str
    integrations: list[IntegrationEntry]
