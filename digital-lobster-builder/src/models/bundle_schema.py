from enum import Enum

from pydantic import BaseModel, Field

class ArtifactRequirement(str, Enum):
    """Whether an artifact must be present for a valid CMS migration bundle."""
    REQUIRED = "required"
    OPTIONAL = "optional"

class ArtifactDefinition(BaseModel):
    """Definition of a single artifact in the Bundle_Schema."""
    file_path: str = Field(min_length=1)
    requirement: ArtifactRequirement
    schema_version: str = Field(min_length=1)
    description: str = Field(min_length=1)

class BundleSchema(BaseModel):
    """Canonical versioned contract for the export bundle."""
    schema_version: str = Field(min_length=1)
    artifacts: list[ArtifactDefinition]

# ---------------------------------------------------------------------------
# BUNDLE_SCHEMA_V1 — the canonical v1 contract
# ---------------------------------------------------------------------------

BUNDLE_SCHEMA_V1 = BundleSchema(
    schema_version="1.0.0",
    artifacts=[
        # ---- 23 existing scanner artifacts --------------------------------
        ArtifactDefinition(
            file_path="site_blueprint.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="High-level site structure and metadata",
        ),
        ArtifactDefinition(
            file_path="site_settings.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="WordPress general, reading, writing, and discussion settings",
        ),
        ArtifactDefinition(
            file_path="site_options.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="WordPress options table entries relevant to migration",
        ),
        ArtifactDefinition(
            file_path="site_environment.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="Server environment, PHP version, and hosting details",
        ),
        ArtifactDefinition(
            file_path="taxonomies.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="Registered taxonomies with terms and term-post assignments",
        ),
        ArtifactDefinition(
            file_path="menus.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="Navigation menus with items, locations, and hierarchy",
        ),
        ArtifactDefinition(
            file_path="media_map.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="Media library inventory with URLs, sizes, and alt text",
        ),
        ArtifactDefinition(
            file_path="theme_mods.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="Active theme modifications and customizer values",
        ),
        ArtifactDefinition(
            file_path="global_styles.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="Global styles and theme.json design tokens",
        ),
        ArtifactDefinition(
            file_path="customizer_settings.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="WordPress Customizer settings and controls",
        ),
        ArtifactDefinition(
            file_path="css_sources.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="Enqueued stylesheets and inline CSS sources",
        ),
        ArtifactDefinition(
            file_path="plugins_fingerprint.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="Installed plugins with versions, status, and family classification",
        ),
        ArtifactDefinition(
            file_path="plugin_behaviors.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="Detected runtime behaviors contributed by plugins",
        ),
        ArtifactDefinition(
            file_path="blocks_usage.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="Gutenberg block types in use with frequency and attributes",
        ),
        ArtifactDefinition(
            file_path="block_patterns.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="Registered block patterns and reusable blocks",
        ),
        ArtifactDefinition(
            file_path="acf_field_groups.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="ACF field group definitions with field types and rules",
        ),
        ArtifactDefinition(
            file_path="custom_fields_config.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="Non-ACF custom field configurations (Pods, Meta Box, Carbon Fields)",
        ),
        ArtifactDefinition(
            file_path="shortcodes_inventory.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="Registered shortcodes with usage counts and sample attributes",
        ),
        ArtifactDefinition(
            file_path="forms_config.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="Form plugin configurations with fields and submission targets",
        ),
        ArtifactDefinition(
            file_path="widgets.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="Widget instances and sidebar assignments",
        ),
        ArtifactDefinition(
            file_path="page_templates.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="Registered page templates with usage counts",
        ),
        ArtifactDefinition(
            file_path="rewrite_rules.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="WordPress rewrite rules and permalink structures",
        ),
        ArtifactDefinition(
            file_path="rest_api_endpoints.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="Registered REST API endpoints and namespaces",
        ),
        ArtifactDefinition(
            file_path="hooks_registry.json",
            requirement=ArtifactRequirement.OPTIONAL,
            schema_version="1.0.0",
            description="Registered action and filter hooks with callbacks",
        ),
        ArtifactDefinition(
            file_path="error_log.json",
            requirement=ArtifactRequirement.OPTIONAL,
            schema_version="1.0.0",
            description="Recent PHP error log entries relevant to migration diagnostics",
        ),
        # ---- 9 new CMS artifacts ------------------------------------------
        ArtifactDefinition(
            file_path="content_relationships.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="Normalized relation graph across posts, terms, media, users, and plugin entities",
        ),
        ArtifactDefinition(
            file_path="field_usage_report.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="Per-field analysis with inferred types, nullability, cardinality, and sample values",
        ),
        ArtifactDefinition(
            file_path="plugin_instances.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="Inventory of actual plugin constructs in use (forms, directories, filters, CTAs)",
        ),
        ArtifactDefinition(
            file_path="page_composition.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="Per-page resolved composition map with blocks, shortcodes, widgets, and assets",
        ),
        ArtifactDefinition(
            file_path="seo_full.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="Normalized per-page SEO metadata including OG, Twitter, schema hints, and sitemaps",
        ),
        ArtifactDefinition(
            file_path="editorial_workflows.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="Editorial behavior profile with statuses, scheduling, drafts, and revision policy",
        ),
        ArtifactDefinition(
            file_path="plugin_table_exports.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="Structured exports of plugin-owned database tables for supported plugin families",
        ),
        ArtifactDefinition(
            file_path="search_config.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="Search and filtering configuration with facets, ranking hints, and archive behavior",
        ),
        ArtifactDefinition(
            file_path="integration_manifest.json",
            requirement=ArtifactRequirement.REQUIRED,
            schema_version="1.0.0",
            description="External integrations inventory including form destinations, webhooks, CRM, and embeds",
        ),
    ],
)
