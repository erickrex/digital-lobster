from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

from src.adapters.base import PluginAdapter, SchemaContribution
from src.adapters.registry import default_adapters
from src.agents.schema_compiler import SchemaCompilerAgent, _WP_TO_STRAPI_TYPE
from src.models.bundle_artifacts import (
    ContentRelationship,
    ContentRelationshipsArtifact,
    EditorialWorkflowsArtifact,
    FieldUsageEntry,
    FieldUsageReportArtifact,
    IntegrationManifestArtifact,
    PageCompositionArtifact,
    PluginInstancesArtifact,
    SearchConfigArtifact,
    SeoFullArtifact,
)
from src.models.bundle_manifest import BundleManifest
from src.models.capability_manifest import Capability, CapabilityManifest
from src.models.content_model_manifest import (
    ContentModelManifest,
    StrapiCollection,
    StrapiComponent,
)
from src.models.strapi_types import StrapiFieldDefinition


# ---------------------------------------------------------------------------
# Helpers — reuse patterns from unit tests
# ---------------------------------------------------------------------------

# Inferred types that the schema compiler maps to Strapi types
_SIMPLE_INFERRED_TYPES = list(_WP_TO_STRAPI_TYPE.keys())

# Valid Strapi field types the compiler can produce (including special ones)
_VALID_STRAPI_TYPES = set(_WP_TO_STRAPI_TYPE.values()) | {
    "string",       # fallback for unknown inferred types
    "component",    # repeater fields
    "dynamiczone",  # flexible content fields
    "relation",     # reference fields
}

_RELATION_TYPES = st.sampled_from([
    "post_to_post", "post_to_term", "post_to_media", "post_to_user",
])

_POST_TYPES = st.sampled_from([
    "post", "page", "event", "testimonial", "team_member", "service",
])

_FIELD_NAMES = st.sampled_from([
    "subtitle", "hero_image", "body", "count", "email_address",
    "featured_image", "gallery", "is_featured", "publish_date",
    "color", "category_ref", "author_ref",
])

_INFERRED_TYPES = st.sampled_from(_SIMPLE_INFERRED_TYPES)

_BEHAVES_AS_OPTIONS = st.sampled_from([
    None, "enum", "reference", "repeater", "object", "flexible",
])


def _clean_bundle(**overrides: Any) -> BundleManifest:
    """Build a minimal BundleManifest for schema compiler tests."""
    defaults: dict[str, Any] = dict(
        schema_version="1.0.0",
        site_url="https://example.com",
        site_name="Test",
        wordpress_version="6.4.2",
        site_blueprint={},
        site_settings={},
        site_options={},
        site_environment={},
        taxonomies={},
        menus=[],
        media_map=[],
        theme_mods={},
        global_styles={},
        customizer_settings={},
        css_sources={},
        plugins_fingerprint={"plugins": []},
        plugin_behaviors={},
        blocks_usage={},
        block_patterns={},
        acf_field_groups={},
        custom_fields_config={},
        shortcodes_inventory={},
        forms_config={},
        widgets={},
        page_templates={},
        rewrite_rules={},
        rest_api_endpoints={},
        hooks_registry={},
        error_log={},
        content_relationships=ContentRelationshipsArtifact(
            schema_version="1.0.0", relationships=[]
        ),
        field_usage_report=FieldUsageReportArtifact(
            schema_version="1.0.0", fields=[]
        ),
        plugin_instances=PluginInstancesArtifact(
            schema_version="1.0.0", instances=[]
        ),
        page_composition=PageCompositionArtifact(
            schema_version="1.0.0", pages=[]
        ),
        seo_full=SeoFullArtifact(schema_version="1.0.0", pages=[]),
        editorial_workflows=EditorialWorkflowsArtifact(
            schema_version="1.0.0",
            statuses_in_use=["publish", "draft"],
            scheduled_publishing=False,
            draft_behavior="standard",
            preview_expectations="none",
            revision_policy="default",
            comments_enabled=False,
            authoring_model="single_editor",
        ),
        plugin_table_exports=[],
        search_config=SearchConfigArtifact(
            schema_version="1.0.0",
            searchable_types=[],
            ranking_hints=[],
            facets=[],
        ),
        integration_manifest=IntegrationManifestArtifact(
            schema_version="1.0.0", integrations=[]
        ),
    )
    defaults.update(overrides)
    return BundleManifest(**defaults)


def _clean_capability_manifest(**overrides: Any) -> CapabilityManifest:
    defaults: dict[str, Any] = dict(
        capabilities=[],
        findings=[],
        content_model_capabilities=[],
        presentation_capabilities=[],
        behavior_capabilities=[],
        plugin_capabilities={},
    )
    defaults.update(overrides)
    return CapabilityManifest(**defaults)


def _make_field_entry(**overrides: Any) -> FieldUsageEntry:
    defaults: dict[str, Any] = dict(
        post_type="post",
        field_name="title",
        source_system="core",
        inferred_type="text",
        nullable=False,
        cardinality="single",
        distinct_value_count=10,
        sample_values=["Hello", "World"],
    )
    defaults.update(overrides)
    return FieldUsageEntry(**defaults)


def _make_agent(
    adapters: list[PluginAdapter] | None = None,
) -> SchemaCompilerAgent:
    return SchemaCompilerAgent(gradient_client=None, adapters=adapters)


def _run(coro):
    return asyncio.run(coro)


def _execute(
    bundle: BundleManifest,
    cap_manifest: CapabilityManifest,
    adapters: list[PluginAdapter] | None = None,
) -> ContentModelManifest:
    agent = _make_agent(adapters=adapters)
    context: dict[str, Any] = {
        "bundle_manifest": bundle,
        "capability_manifest": cap_manifest,
    }
    result = _run(agent.execute(context))
    return result.artifacts["content_model_manifest"]


# ---------------------------------------------------------------------------
# Hypothesis strategies for field usage entries
# ---------------------------------------------------------------------------

@st.composite
def field_usage_entries(draw) -> FieldUsageEntry:
    """Generate a random FieldUsageEntry with valid inferred types."""
    inferred_type = draw(_INFERRED_TYPES)
    behaves_as = draw(_BEHAVES_AS_OPTIONS)

    # Ensure repeater/flexible behaves_as aligns with inferred_type for clarity
    if behaves_as == "repeater":
        inferred_type = "repeater"
    elif behaves_as == "flexible":
        inferred_type = "flexible_content"

    sample_values: list[Any] = []
    if behaves_as == "repeater" or inferred_type == "repeater":
        sample_values = [{"sub_field": "value", "count": 1}]
    elif behaves_as == "enum":
        sample_values = draw(
            st.lists(st.text(min_size=1, max_size=10), min_size=1, max_size=5)
        )
    else:
        sample_values = draw(
            st.lists(st.text(min_size=1, max_size=20), max_size=3)
        )

    return FieldUsageEntry(
        post_type=draw(_POST_TYPES),
        field_name=draw(_FIELD_NAMES),
        source_system=draw(st.sampled_from(["core", "acf", "pods", "meta_box", "carbon_fields"])),
        inferred_type=inferred_type,
        nullable=draw(st.booleans()),
        cardinality=draw(st.sampled_from(["single", "multiple"])),
        distinct_value_count=draw(st.integers(min_value=0, max_value=500)),
        sample_values=sample_values,
        behaves_as=behaves_as,
    )


@st.composite
def content_relationships(draw) -> ContentRelationship:
    """Generate a random ContentRelationship."""
    source_pt = draw(_POST_TYPES)
    target_pt = draw(_POST_TYPES)
    return ContentRelationship(
        source_id=f"{source_pt}:{draw(st.integers(min_value=1, max_value=999))}",
        target_id=f"{target_pt}:{draw(st.integers(min_value=1, max_value=999))}",
        relation_type=draw(_RELATION_TYPES),
    )


# ===========================================================================
# Property 12: Schema compiler produces valid Content_Model_Manifest
# Validates: Requirements 14.1, 14.2, 14.3, 14.5, 14.6, 14.7
# ===========================================================================


class TestSchemaCompilerProducesValidManifest:
    """For any set of field usage entries with various inferred types, the
    schema compiler must produce a ContentModelManifest where:
    - Every post type in field_usage_report has a corresponding collection
    - Every field maps to a valid Strapi type
    - Repeater fields produce component references and corresponding components
    - Validation hints are generated for every field
    - When SEO capabilities exist, SEO strategy is applied to all collections
    """

    @given(
        field_entries=st.lists(field_usage_entries(), min_size=1, max_size=8),
    )
    @settings(max_examples=100)
    def test_every_post_type_has_collection(
        self, field_entries: list[FieldUsageEntry]
    ):
        """**Validates: Requirements 14.1**

        Every post type present in the field_usage_report must have a
        corresponding StrapiCollection in the manifest.
        """
        bundle = _clean_bundle(
            field_usage_report=FieldUsageReportArtifact(
                schema_version="1.0.0", fields=field_entries
            ),
        )
        manifest = _execute(bundle, _clean_capability_manifest())

        expected_post_types = {e.post_type for e in field_entries}
        collection_source_types = {
            c.source_post_type for c in manifest.collections
        }
        assert expected_post_types == collection_source_types, (
            f"Missing collections for post types: "
            f"{expected_post_types - collection_source_types}"
        )

    @given(
        field_entries=st.lists(field_usage_entries(), min_size=1, max_size=8),
    )
    @settings(max_examples=100)
    def test_every_field_maps_to_valid_strapi_type(
        self, field_entries: list[FieldUsageEntry]
    ):
        """**Validates: Requirements 14.2**

        Every field in every collection must have a valid Strapi type.
        """
        bundle = _clean_bundle(
            field_usage_report=FieldUsageReportArtifact(
                schema_version="1.0.0", fields=field_entries
            ),
        )
        manifest = _execute(bundle, _clean_capability_manifest())

        for coll in manifest.collections:
            for field in coll.fields:
                assert field.strapi_type in _VALID_STRAPI_TYPES, (
                    f"Field '{field.name}' in collection '{coll.api_id}' "
                    f"has invalid Strapi type '{field.strapi_type}'"
                )

    @given(
        post_type=_POST_TYPES,
        repeater_name=st.sampled_from(["team_members", "slides", "features", "faq_items"]),
    )
    @settings(max_examples=100)
    def test_repeater_produces_component_reference_and_entry(
        self, post_type: str, repeater_name: str
    ):
        """**Validates: Requirements 14.3**

        Repeater fields must produce a component-type field reference in the
        collection AND a corresponding StrapiComponent entry.
        """
        entry = _make_field_entry(
            post_type=post_type,
            field_name=repeater_name,
            inferred_type="repeater",
            behaves_as="repeater",
            sample_values=[{"sub_field": "value"}],
        )
        bundle = _clean_bundle(
            field_usage_report=FieldUsageReportArtifact(
                schema_version="1.0.0", fields=[entry]
            ),
        )
        manifest = _execute(bundle, _clean_capability_manifest())

        # The collection field must be of type "component"
        coll = manifest.collections[0]
        repeater_field = next(
            (f for f in coll.fields if f.name == repeater_name), None
        )
        assert repeater_field is not None, (
            f"Repeater field '{repeater_name}' not found in collection"
        )
        assert repeater_field.strapi_type == "component"

        # A corresponding StrapiComponent must exist
        expected_uid_fragment = repeater_name.replace("_", "-")
        matching_components = [
            c for c in manifest.components if expected_uid_fragment in c.uid
        ]
        assert len(matching_components) >= 1, (
            f"No component found for repeater '{repeater_name}'"
        )

        # The component UID must be in the collection's components list
        assert any(
            expected_uid_fragment in uid for uid in coll.components
        ), (
            f"Component UID for '{repeater_name}' not in collection components"
        )

    @given(
        relationships=st.lists(
            content_relationships(), min_size=1, max_size=5
        ),
    )
    @settings(max_examples=100)
    def test_content_relationships_produce_strapi_relations(
        self, relationships: list[ContentRelationship]
    ):
        """**Validates: Requirements 14.5**

        Every content relationship must produce a corresponding StrapiRelation.
        """
        bundle = _clean_bundle(
            content_relationships=ContentRelationshipsArtifact(
                schema_version="1.0.0", relationships=relationships
            ),
        )
        manifest = _execute(bundle, _clean_capability_manifest())

        assert len(manifest.relations) == len(relationships), (
            f"Expected {len(relationships)} relations, "
            f"got {len(manifest.relations)}"
        )
        for rel in manifest.relations:
            assert rel.relation_type in {
                "oneToOne", "oneToMany", "manyToMany", "manyToOne"
            }, f"Invalid relation type: {rel.relation_type}"
            assert rel.source_collection, "source_collection must be non-empty"
            assert rel.target_collection, "target_collection must be non-empty"
            assert rel.field_name, "field_name must be non-empty"
            assert rel.source_relationship_id, "source_relationship_id must be non-empty"

    @given(
        field_entries=st.lists(field_usage_entries(), min_size=1, max_size=6),
    )
    @settings(max_examples=100)
    def test_seo_strategy_applied_to_all_collections_when_seo_exists(
        self, field_entries: list[FieldUsageEntry]
    ):
        """**Validates: Requirements 14.6**

        When SEO capabilities exist, the SEO component strategy must be
        applied to every collection.
        """
        cap = _clean_capability_manifest(
            capabilities=[
                Capability(
                    capability_type="seo",
                    source_plugin="yoast",
                    classification="strapi_native",
                    confidence=0.95,
                ),
            ],
        )
        bundle = _clean_bundle(
            field_usage_report=FieldUsageReportArtifact(
                schema_version="1.0.0", fields=field_entries
            ),
        )
        manifest = _execute(bundle, cap)

        assert manifest.seo_strategy is not None
        for coll in manifest.collections:
            assert manifest.seo_strategy.component_uid in coll.components, (
                f"SEO component not applied to collection '{coll.api_id}'"
            )

    @given(
        field_entries=st.lists(field_usage_entries(), min_size=1, max_size=8),
    )
    @settings(max_examples=100)
    def test_validation_hints_for_every_field(
        self, field_entries: list[FieldUsageEntry]
    ):
        """**Validates: Requirements 14.7**

        Every field in the field_usage_report must have a corresponding
        validation hint in the manifest.
        """
        bundle = _clean_bundle(
            field_usage_report=FieldUsageReportArtifact(
                schema_version="1.0.0", fields=field_entries
            ),
        )
        manifest = _execute(bundle, _clean_capability_manifest())

        assert len(manifest.validation_hints) == len(field_entries), (
            f"Expected {len(field_entries)} validation hints, "
            f"got {len(manifest.validation_hints)}"
        )
        for hint in manifest.validation_hints:
            assert hint.collection_api_id, "collection_api_id must be non-empty"
            assert hint.field_name, "field_name must be non-empty"
            assert hint.cardinality in {"single", "multiple"}, (
                f"Invalid cardinality: {hint.cardinality}"
            )


# ===========================================================================
# Property 13: Plugin instance schema mapping
# Validates: Requirements 14.4
# ===========================================================================


class TestPluginInstanceSchemaMapping:
    """For any plugin instance with a supported adapter family, the adapter's
    schema_strategy is invoked and its contributions are merged into the
    manifest."""

    @given(adapter_idx=st.sampled_from(range(len(default_adapters()))))
    @settings(max_examples=100)
    def test_adapter_schema_strategy_invoked_for_plugin_capabilities(
        self, adapter_idx: int
    ):
        """**Validates: Requirements 14.4**

        When a plugin family has capabilities in the CapabilityManifest's
        plugin_capabilities, the schema compiler must invoke that adapter's
        schema_strategy().
        """
        real_adapter = default_adapters()[adapter_idx]
        family = real_adapter.plugin_family()

        spy_adapter = MagicMock(wraps=real_adapter)
        spy_adapter.plugin_family = real_adapter.plugin_family

        plugin_cap = Capability(
            capability_type="content_model",
            source_plugin=family,
            classification="strapi_native",
            confidence=0.95,
            details={"source": "test"},
        )
        cap = _clean_capability_manifest(
            plugin_capabilities={family: [plugin_cap]},
        )
        bundle = _clean_bundle()
        _execute(bundle, cap, adapters=[spy_adapter])

        spy_adapter.schema_strategy.assert_called_once()

    @given(
        collection_name=st.sampled_from(["form_submissions", "directory_listings", "cta_entries"]),
        component_uid=st.sampled_from(["plugin.form-field", "plugin.listing-card", "plugin.cta-block"]),
    )
    @settings(max_examples=100)
    def test_adapter_schema_contributions_merged_into_manifest(
        self, collection_name: str, component_uid: str
    ):
        """**Validates: Requirements 14.4**

        When an adapter's schema_strategy returns collections or components,
        they must appear in the final ContentModelManifest.
        """
        # Create a mock adapter that returns non-empty schema contributions
        mock_adapter = MagicMock(spec=PluginAdapter)
        mock_adapter.plugin_family.return_value = "test_plugin"
        mock_adapter.schema_strategy.return_value = SchemaContribution(
            collections=[
                StrapiCollection(
                    display_name=collection_name.replace("_", " ").title(),
                    singular_name=collection_name.replace("_", "-"),
                    plural_name=collection_name.replace("_", "-") + "s",
                    api_id=collection_name.replace("_", "-"),
                    fields=[StrapiFieldDefinition(name="value", strapi_type="string")],
                    components=[],
                ),
            ],
            components=[
                StrapiComponent(
                    uid=component_uid,
                    display_name=component_uid.split(".")[-1].replace("-", " ").title(),
                    category="plugin",
                    fields=[StrapiFieldDefinition(name="label", strapi_type="string")],
                ),
            ],
        )

        plugin_cap = Capability(
            capability_type="content_model",
            source_plugin="test_plugin",
            classification="strapi_native",
            confidence=0.95,
        )
        cap = _clean_capability_manifest(
            plugin_capabilities={"test_plugin": [plugin_cap]},
        )
        bundle = _clean_bundle()
        manifest = _execute(bundle, cap, adapters=[mock_adapter])

        # Verify the adapter's collection appears in the manifest
        api_ids = [c.api_id for c in manifest.collections]
        assert collection_name.replace("_", "-") in api_ids, (
            f"Adapter collection '{collection_name}' not in manifest collections"
        )

        # Verify the adapter's component appears in the manifest
        comp_uids = [c.uid for c in manifest.components]
        assert component_uid in comp_uids, (
            f"Adapter component '{component_uid}' not in manifest components"
        )
