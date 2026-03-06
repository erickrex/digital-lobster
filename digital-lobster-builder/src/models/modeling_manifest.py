from pydantic import BaseModel


class FrontmatterField(BaseModel):
    name: str
    type: str  # "string", "number", "boolean", "date", "reference", "list"
    required: bool
    description: str


class ContentCollectionSchema(BaseModel):
    collection_name: str
    source_post_type: str
    frontmatter_fields: list[FrontmatterField]
    route_pattern: str  # e.g., "/places/[slug]"


class ComponentMapping(BaseModel):
    wp_block_type: str
    astro_component: str
    is_island: bool
    hydration_directive: str | None
    props: list[dict]
    fallback: bool


class TaxonomyDefinition(BaseModel):
    taxonomy: str
    collection_ref: str | None
    data_file: str | None


class ModelingManifest(BaseModel):
    collections: list[ContentCollectionSchema]
    components: list[ComponentMapping]
    taxonomies: list[TaxonomyDefinition]
