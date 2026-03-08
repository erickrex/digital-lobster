from pydantic import BaseModel

class TypeMapping(BaseModel):
    """Maps a source WordPress post type to a target Strapi API identifier."""
    source_post_type: str
    target_api_id: str
    source_plugin: str | None = None

class FieldMapping(BaseModel):
    """Maps a source field on a post type to a target Strapi field."""
    source_post_type: str
    source_field: str
    target_api_id: str
    target_field: str
    transform: str | None = None  # "direct", "component", "dynamic_zone", "json"

class RelationMapping(BaseModel):
    """Maps a source content relationship to a target Strapi relation."""
    source_relationship_id: str
    source_collection: str
    target_collection: str
    target_field: str
    relation_type: str  # "oneToOne", "oneToMany", "manyToMany", "manyToOne"

class MediaMappingStrategy(BaseModel):
    """Defines how media URLs are rewritten and handled during migration."""
    url_rewrite_pattern: str
    relation_aware: bool = True
    preserve_alt_text: bool = True
    preserve_caption: bool = True

class TermMapping(BaseModel):
    """Maps a source WordPress taxonomy to a target Strapi collection and field."""
    source_taxonomy: str
    target_api_id: str
    target_field: str

class TemplateMapping(BaseModel):
    """Maps a source page template to a target Astro layout and route pattern."""
    source_template: str
    target_layout: str
    target_route_pattern: str

class PluginInstanceMapping(BaseModel):
    """Maps a source plugin instance to a target Strapi collection, component, or skip."""
    source_plugin: str
    source_instance_type: str
    target_api_id: str | None = None
    target_component_uid: str | None = None
    migration_strategy: str  # "collection", "singleton", "component", "skip"

class MigrationMappingManifest(BaseModel):
    """Complete source-to-target mapping manifest for content migration.

    Produced before content migration begins from the Content_Model_Manifest,
    Presentation_Manifest, and Behavior_Manifest.
    """
    type_mappings: list[TypeMapping]
    field_mappings: list[FieldMapping]
    relation_mappings: list[RelationMapping]
    media_mapping_strategy: MediaMappingStrategy
    term_mappings: list[TermMapping]
    template_mappings: list[TemplateMapping]
    plugin_instance_mappings: list[PluginInstanceMapping]
