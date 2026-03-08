from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .bundle_artifacts import (
    ContentRelationshipsArtifact,
    EditorialWorkflowsArtifact,
    FieldUsageReportArtifact,
    IntegrationManifestArtifact,
    PageCompositionArtifact,
    PluginInstancesArtifact,
    PluginTableExport,
    SearchConfigArtifact,
    SeoFullArtifact,
)


class BundleManifest(BaseModel):
    """Normalized bundle manifest — single source of truth for all exporter data."""

    # Top-level metadata
    schema_version: str
    site_url: str
    site_name: str
    wordpress_version: str

    # Existing artifacts (23 scanner outputs, typed loosely until individually modeled)
    site_blueprint: dict[str, Any]
    site_settings: dict[str, Any]
    site_options: dict[str, Any]
    site_environment: dict[str, Any]
    taxonomies: dict[str, Any]
    menus: list[dict[str, Any]]
    media_map: list[dict[str, Any]]
    theme_mods: dict[str, Any]
    global_styles: dict[str, Any]
    customizer_settings: dict[str, Any]
    css_sources: dict[str, Any]
    plugins_fingerprint: dict[str, Any]
    plugin_behaviors: dict[str, Any]
    blocks_usage: dict[str, Any]
    block_patterns: dict[str, Any]
    acf_field_groups: dict[str, Any]
    custom_fields_config: dict[str, Any]
    shortcodes_inventory: dict[str, Any]
    forms_config: dict[str, Any]
    widgets: dict[str, Any]
    page_templates: dict[str, Any]
    rewrite_rules: dict[str, Any]
    rest_api_endpoints: dict[str, Any]
    hooks_registry: dict[str, Any]
    error_log: dict[str, Any]

    # New CMS artifacts (9 typed Pydantic models)
    content_relationships: ContentRelationshipsArtifact
    field_usage_report: FieldUsageReportArtifact
    plugin_instances: PluginInstancesArtifact
    page_composition: PageCompositionArtifact
    seo_full: SeoFullArtifact
    editorial_workflows: EditorialWorkflowsArtifact
    plugin_table_exports: list[PluginTableExport]
    search_config: SearchConfigArtifact
    integration_manifest: IntegrationManifestArtifact
