from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from src.models.bundle_manifest import BundleManifest
from src.models.capability_manifest import Capability
from src.models.content_model_manifest import StrapiCollection, StrapiComponent, StrapiRelation
from src.models.presentation_manifest import FallbackZone, SectionDefinition


class SchemaContribution(BaseModel):
    """Schema contributions from a plugin adapter."""

    collections: list[StrapiCollection] = Field(default_factory=list)
    components: list[StrapiComponent] = Field(default_factory=list)
    relations: list[StrapiRelation] = Field(default_factory=list)


class RenderingContribution(BaseModel):
    """Rendering contributions from a plugin adapter."""

    sections: list[SectionDefinition] = Field(default_factory=list)
    fallback_zones: list[FallbackZone] = Field(default_factory=list)


class MigrationRule(BaseModel):
    """A single migration rule for plugin data."""

    source_construct: str
    target_type: str  # "collection", "component", "relation", "skip"
    target_identifier: str
    transform: str | None = None


class QAAssertion(BaseModel):
    """A parity QA assertion for plugin-specific behavior."""

    assertion_id: str
    description: str
    category: str  # one of the 7 parity categories
    check_type: str  # "presence", "count", "content_match", "route_match"


class PluginAdapter(ABC):
    """Interface for deterministic plugin family migration adapters."""

    @abstractmethod
    def plugin_family(self) -> str:
        """Return the plugin family identifier (e.g., 'acf', 'yoast')."""
        ...

    @abstractmethod
    def required_artifacts(self) -> list[str]:
        """Return artifact file paths this adapter needs from the bundle."""
        ...

    @abstractmethod
    def supported_constructs(self) -> list[str]:
        """Return construct types this adapter can handle."""
        ...

    @abstractmethod
    def classify_capabilities(self, bundle_manifest: BundleManifest) -> list[Capability]:
        """Classify plugin capabilities from bundle data."""
        ...

    @abstractmethod
    def schema_strategy(self, capabilities: list[Capability]) -> SchemaContribution:
        """Return Strapi schema contributions (collections, components, relations)."""
        ...

    @abstractmethod
    def rendering_strategy(self, capabilities: list[Capability]) -> RenderingContribution:
        """Return Astro rendering contributions (layouts, components, sections)."""
        ...

    @abstractmethod
    def migration_rules(self, capabilities: list[Capability]) -> list[MigrationRule]:
        """Return content migration rules for this plugin's data."""
        ...

    @abstractmethod
    def unsupported_cases(self) -> list[str]:
        """Return known unsupported constructs for this plugin family."""
        ...

    @abstractmethod
    def qa_assertions(self, capabilities: list[Capability]) -> list[QAAssertion]:
        """Return parity QA assertions specific to this plugin."""
        ...
