from pydantic import BaseModel

class StrapiFieldDefinition(BaseModel):
    """A single field in a Strapi Content Type."""
    name: str
    strapi_type: str  # "text", "integer", "boolean", "datetime", "relation", "json"
    required: bool = False
    relation_target: str | None = None  # API ID of related content type
    relation_type: str | None = None  # "manyToMany", "oneToMany", etc.

class StrapiComponentSchema(BaseModel):
    """A reusable Strapi component (e.g., seo-metadata)."""
    name: str
    category: str  # e.g., "shared"
    fields: list[StrapiFieldDefinition]

class StrapiContentTypeDefinition(BaseModel):
    """Full definition for a Strapi Content Type."""
    display_name: str
    singularName: str
    pluralName: str
    api_id: str  # The Strapi API identifier (e.g., "api::post.post")
    fields: list[StrapiFieldDefinition]
    components: list[str] = []  # Component UIDs used by this type

class ContentTypeMap(BaseModel):
    """Maps Modeling_Manifest collection names to Strapi API identifiers."""
    mappings: dict[str, str]  # collection_name → Strapi api_id
    taxonomy_mappings: dict[str, str]  # taxonomy_name → Strapi api_id
    component_uids: list[str]  # UIDs of created components
