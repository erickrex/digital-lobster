from pydantic import BaseModel

class PluginFeature(BaseModel):
    slug: str
    name: str
    version: str
    family: str | None  # "geodirectory", "kadence", "forminator", "yoast", etc.
    custom_post_types: list[str]
    custom_taxonomies: list[str]
    detected_features: list[str]

class ContentTypeSummary(BaseModel):
    post_type: str
    count: int
    custom_fields: list[str]
    taxonomies: list[str]
    sample_slugs: list[str]

class TaxonomySummary(BaseModel):
    taxonomy: str
    term_count: int
    associated_post_types: list[str]

class MenuSummary(BaseModel):
    name: str
    location: str
    item_count: int

class ThemeMetadata(BaseModel):
    name: str
    has_theme_json: bool
    has_custom_css: bool
    design_tokens: dict | None

class Inventory(BaseModel):
    site_url: str
    site_name: str
    wordpress_version: str
    content_types: list[ContentTypeSummary]
    plugins: list[PluginFeature]
    taxonomies: list[TaxonomySummary]
    menus: list[MenuSummary]
    theme: ThemeMetadata
    has_html_snapshots: bool
    has_media_manifest: bool
    has_redirect_rules: bool
    has_seo_data: bool
