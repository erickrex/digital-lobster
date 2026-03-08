from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .finding import Finding


class RedirectRule(BaseModel):
    """A single redirect mapping from source to target URL."""

    source_url: str
    target_url: str
    status_code: int  # 301, 302, etc.
    source_plugin: str | None = None


class FormStrategy(BaseModel):
    """Migration strategy for a single form instance."""

    form_id: str  # stable source identifier
    source_plugin: str
    target: str  # "strapi_collection", "astro_api_route", "external_proxy"
    fields: list[dict[str, Any]]
    submission_destination: str
    findings: list[Finding] = Field(default_factory=list)


class SearchStrategy(BaseModel):
    """Search and filtering configuration for the migrated site."""

    enabled: bool
    searchable_collections: list[str]  # Strapi api_ids
    facets: list[dict[str, Any]]
    implementation: str  # "strapi_filter", "astro_search", "external"


class IntegrationBoundary(BaseModel):
    """Disposition of an external integration: rebuild, proxy, or drop."""

    integration_id: str
    disposition: str  # "rebuild", "proxy", "drop"
    target_system: str  # "strapi", "astro", "external"
    details: dict[str, Any] = Field(default_factory=dict)
    finding: Finding | None = None  # produced when disposition is "drop"


class BehaviorManifest(BaseModel):
    """Canonical behavior model produced by the Behavior Compiler."""

    redirects: list[RedirectRule]
    metadata_strategy: dict[str, Any]
    forms_strategy: list[FormStrategy]
    preview_rules: dict[str, Any]
    search_strategy: SearchStrategy | None = None
    integration_boundaries: list[IntegrationBoundary]
    unsupported_constructs: list[Finding]

    @property
    def findings(self) -> list[Finding]:
        """Aggregate all findings for orchestrator accumulation.

        Collects unsupported construct findings, integration boundary
        findings, and per-form findings into a single list.
        """
        result: list[Finding] = list(self.unsupported_constructs)
        for boundary in self.integration_boundaries:
            if boundary.finding is not None:
                result.append(boundary.finding)
        for form in self.forms_strategy:
            result.extend(form.findings)
        return result
