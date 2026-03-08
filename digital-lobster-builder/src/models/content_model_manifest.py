from pydantic import BaseModel, Field

from src.models.finding import Finding
from src.models.strapi_types import StrapiFieldDefinition


class StrapiCollection(BaseModel):
    """A Strapi collection type in the target content model."""

    display_name: str
    singular_name: str
    plural_name: str
    api_id: str
    fields: list[StrapiFieldDefinition]
    components: list[str]  # component UIDs
    source_post_type: str | None = None
    source_plugin: str | None = None


class StrapiComponent(BaseModel):
    """A reusable Strapi component in the target content model."""

    uid: str
    display_name: str
    category: str
    fields: list[StrapiFieldDefinition]


class StrapiRelation(BaseModel):
    """An explicit relation between two Strapi collections."""

    source_collection: str  # api_id
    target_collection: str  # api_id
    field_name: str
    relation_type: str  # "oneToOne", "oneToMany", "manyToMany", "manyToOne"
    source_relationship_id: str  # from content_relationships


class SeoComponentStrategy(BaseModel):
    """Reusable SEO component strategy applied across content types."""

    component_uid: str
    fields: list[StrapiFieldDefinition]
    applied_to: list[str]  # collection api_ids


class ValidationHint(BaseModel):
    """Field validation hint derived from the field usage report."""

    collection_api_id: str
    field_name: str
    nullable: bool
    cardinality: str  # "single", "multiple"
    enum_values: list[str] | None = None


class ContentModelManifest(BaseModel):
    """Canonical Strapi target model produced by the Schema Compiler."""

    collections: list[StrapiCollection]
    components: list[StrapiComponent]
    relations: list[StrapiRelation]
    seo_strategy: SeoComponentStrategy | None = None
    validation_hints: list[ValidationHint]
    findings: list[Finding] = Field(default_factory=list)
