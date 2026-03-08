from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .finding import Finding

class LayoutDefinition(BaseModel):
    """An Astro layout in the presentation hierarchy."""
    name: str
    template_path: str
    shared_sections: list[str]
    style_tokens: dict[str, Any] = Field(default_factory=dict)

class RouteTemplate(BaseModel):
    """A route-to-layout mapping for Astro page generation."""
    route_pattern: str
    layout: str
    source_template: str
    content_collection: str | None = None

class SectionDefinition(BaseModel):
    """A deterministic Astro section component mapped from widgets/sidebars."""
    name: str
    source_type: str  # "widget", "sidebar", "block", "plugin_component"
    source_plugin: str | None = None
    component_path: str
    props: dict[str, Any] = Field(default_factory=dict)

class FallbackZone(BaseModel):
    """A fallback HTML rendering zone for unsupported presentational fragments."""
    page_url: str
    zone_name: str
    raw_html: str
    reason: str

class PresentationManifest(BaseModel):
    """Canonical Astro presentation model produced by the Presentation Compiler."""
    layouts: list[LayoutDefinition]
    route_templates: list[RouteTemplate]
    sections: list[SectionDefinition]
    fallback_zones: list[FallbackZone]
    style_tokens: dict[str, Any] = Field(default_factory=dict)
    findings: list[Finding] = Field(default_factory=list)
