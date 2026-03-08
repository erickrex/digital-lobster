from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .finding import Finding


class Capability(BaseModel):
    """A single detected site capability."""

    capability_type: str  # "content_model", "seo", "widget", "form", "shortcode",
    #                       "search_filter", "integration", "editorial", "template"
    source_plugin: str | None = None
    classification: str  # "strapi_native", "astro_runtime", "unsupported"
    confidence: float = Field(ge=0.0, le=1.0)  # below 0.8 triggers LLM fallback
    details: dict[str, Any] = Field(default_factory=dict)
    findings: list[Finding] = Field(default_factory=list)


class CapabilityManifest(BaseModel):
    """Complete site capability model — sole input for all compilers."""

    capabilities: list[Capability]
    findings: list[Finding]
    content_model_capabilities: list[Capability] = Field(default_factory=list)
    presentation_capabilities: list[Capability] = Field(default_factory=list)
    behavior_capabilities: list[Capability] = Field(default_factory=list)
    plugin_capabilities: dict[str, list[Capability]] = Field(default_factory=dict)
