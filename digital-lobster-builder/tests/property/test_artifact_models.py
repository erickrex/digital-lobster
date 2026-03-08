from __future__ import annotations

import re
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from src.models.bundle_artifacts import (
    ContentRelationship,
    ContentRelationshipsArtifact,
    EditorialWorkflowsArtifact,
    FieldUsageEntry,
    FieldUsageReportArtifact,
    IntegrationEntry,
    IntegrationManifestArtifact,
    PageCompositionArtifact,
    PageCompositionEntry,
    PluginInstance,
    PluginInstancesArtifact,
    PluginTableExport,
    SearchConfigArtifact,
    SeoFullArtifact,
    SeoPageEntry,
)
from src.models.bundle_schema import BUNDLE_SCHEMA_V1, ArtifactRequirement

# ---------------------------------------------------------------------------
# Primitive helpers
# ---------------------------------------------------------------------------

_slug = st.from_regex(r"[a-z][a-z0-9\-]{1,20}", fullmatch=True)
_nonempty = st.text(min_size=1, max_size=60, alphabet=st.characters(categories=("L", "N")))
_version = st.from_regex(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}", fullmatch=True)
_url = st.builds(lambda s: f"https://{s}.example.com/{s}", _slug)
_plugin_name = st.sampled_from(["yoast", "rank-math", "acf", "cf7", "wpforms", "kadence", "pods"])
_relation_type = st.sampled_from([
    "post_to_post", "post_to_term", "post_to_media", "post_to_user", "plugin_entity",
])
_source_system = st.sampled_from(["acf", "pods", "meta_box", "carbon_fields", "core"])
_inferred_type = st.sampled_from([
    "text", "number", "boolean", "date", "reference", "repeater", "flexible", "object", "enum",
])
_cardinality = st.sampled_from(["single", "multiple"])
_behaves_as = st.sampled_from(["enum", "reference", "repeater", "object", "flexible", None])
_instance_type = st.sampled_from(["form", "directory", "filter", "cta", "seo_object", "widget"])
_integration_type = st.sampled_from([
    "form_destination", "webhook", "crm", "embed", "runtime_api", "third_party_script",
])
_authoring_model = st.sampled_from(["single_editor", "two_editor"])
_small_dict = st.dictionaries(keys=_slug, values=_nonempty, max_size=3)
_small_dict_list = st.lists(_small_dict, max_size=3)


# ---------------------------------------------------------------------------
# Composite strategies for each artifact model
# ---------------------------------------------------------------------------

@st.composite
def content_relationships(draw: st.DrawFn) -> ContentRelationship:
    return ContentRelationship(
        source_id=draw(_slug),
        target_id=draw(_slug),
        relation_type=draw(_relation_type),
        source_plugin=draw(st.one_of(st.none(), _plugin_name)),
        metadata=draw(_small_dict),
    )


@st.composite
def content_relationships_artifacts(draw: st.DrawFn) -> ContentRelationshipsArtifact:
    return ContentRelationshipsArtifact(
        schema_version=draw(_version),
        relationships=draw(st.lists(content_relationships(), max_size=5)),
    )


@st.composite
def field_usage_entries(draw: st.DrawFn) -> FieldUsageEntry:
    return FieldUsageEntry(
        post_type=draw(_slug),
        field_name=draw(_slug),
        source_plugin=draw(st.one_of(st.none(), _plugin_name)),
        source_system=draw(_source_system),
        inferred_type=draw(_inferred_type),
        nullable=draw(st.booleans()),
        cardinality=draw(_cardinality),
        distinct_value_count=draw(st.integers(min_value=0, max_value=1000)),
        sample_values=draw(st.lists(_nonempty, max_size=3)),
        behaves_as=draw(_behaves_as),
    )


@st.composite
def field_usage_report_artifacts(draw: st.DrawFn) -> FieldUsageReportArtifact:
    return FieldUsageReportArtifact(
        schema_version=draw(_version),
        fields=draw(st.lists(field_usage_entries(), max_size=5)),
    )


@st.composite
def plugin_instances(draw: st.DrawFn) -> PluginInstance:
    return PluginInstance(
        instance_id=draw(_slug),
        source_plugin=draw(_plugin_name),
        instance_type=draw(_instance_type),
        config=draw(_small_dict),
        references=draw(st.lists(_slug, max_size=3)),
    )


@st.composite
def plugin_instances_artifacts(draw: st.DrawFn) -> PluginInstancesArtifact:
    return PluginInstancesArtifact(
        schema_version=draw(_version),
        instances=draw(st.lists(plugin_instances(), max_size=5)),
    )


@st.composite
def page_composition_entries(draw: st.DrawFn) -> PageCompositionEntry:
    return PageCompositionEntry(
        canonical_url=draw(_url),
        template=draw(_slug),
        blocks=draw(_small_dict_list),
        shortcodes=draw(_small_dict_list),
        widget_placements=draw(_small_dict_list),
        forms_embedded=draw(st.lists(_slug, max_size=3)),
        plugin_components=draw(_small_dict_list),
        enqueued_assets=draw(st.lists(_slug, max_size=3)),
        content_sections=draw(_small_dict_list),
        snapshot_ref=draw(st.one_of(st.none(), _slug)),
    )


@st.composite
def page_composition_artifacts(draw: st.DrawFn) -> PageCompositionArtifact:
    return PageCompositionArtifact(
        schema_version=draw(_version),
        pages=draw(st.lists(page_composition_entries(), max_size=3)),
    )


@st.composite
def seo_page_entries(draw: st.DrawFn) -> SeoPageEntry:
    return SeoPageEntry(
        canonical_url=draw(_url),
        source_plugin=draw(_plugin_name),
        robots=draw(st.one_of(st.none(), _nonempty)),
        noindex=draw(st.booleans()),
        nofollow=draw(st.booleans()),
        title_template=draw(st.one_of(st.none(), _nonempty)),
        resolved_title=draw(st.one_of(st.none(), _nonempty)),
        meta_description=draw(st.one_of(st.none(), _nonempty)),
        og_metadata=draw(_small_dict),
        twitter_metadata=draw(_small_dict),
        schema_type_hints=draw(st.lists(_nonempty, max_size=3)),
        breadcrumb_config=draw(st.one_of(st.none(), _small_dict)),
        sitemap_inclusion=draw(st.booleans()),
        redirect_ownership=draw(st.one_of(st.none(), _small_dict)),
    )


@st.composite
def seo_full_artifacts(draw: st.DrawFn) -> SeoFullArtifact:
    return SeoFullArtifact(
        schema_version=draw(_version),
        pages=draw(st.lists(seo_page_entries(), max_size=3)),
    )


@st.composite
def editorial_workflows_artifacts(draw: st.DrawFn) -> EditorialWorkflowsArtifact:
    return EditorialWorkflowsArtifact(
        schema_version=draw(_version),
        statuses_in_use=draw(st.lists(_nonempty, min_size=1, max_size=5)),
        scheduled_publishing=draw(st.booleans()),
        draft_behavior=draw(_nonempty),
        preview_expectations=draw(_nonempty),
        revision_policy=draw(_nonempty),
        comments_enabled=draw(st.booleans()),
        authoring_model=draw(_authoring_model),
    )


@st.composite
def plugin_table_exports(draw: st.DrawFn) -> PluginTableExport:
    rows: list[dict[str, Any]] = draw(st.lists(_small_dict, max_size=5))
    return PluginTableExport(
        table_name=draw(_slug),
        schema_version=draw(_version),
        source_plugin=draw(_plugin_name),
        row_count=len(rows),
        primary_key=draw(_slug),
        foreign_key_candidates=draw(st.lists(_slug, max_size=3)),
        rows=rows,
    )


@st.composite
def search_config_artifacts(draw: st.DrawFn) -> SearchConfigArtifact:
    return SearchConfigArtifact(
        schema_version=draw(_version),
        searchable_types=draw(st.lists(_slug, min_size=1, max_size=5)),
        ranking_hints=draw(_small_dict_list),
        facets=draw(_small_dict_list),
        archive_behavior=draw(_small_dict),
        search_template_hints=draw(_small_dict),
    )


@st.composite
def integration_entries(draw: st.DrawFn) -> IntegrationEntry:
    return IntegrationEntry(
        integration_id=draw(_slug),
        integration_type=draw(_integration_type),
        target=draw(_url),
        config=draw(_small_dict),
        business_critical=draw(st.booleans()),
    )


@st.composite
def integration_manifest_artifacts(draw: st.DrawFn) -> IntegrationManifestArtifact:
    return IntegrationManifestArtifact(
        schema_version=draw(_version),
        integrations=draw(st.lists(integration_entries(), max_size=5)),
    )



# ---------------------------------------------------------------------------
# A combined strategy that produces one of the 9 top-level artifact models
# ---------------------------------------------------------------------------

_all_top_level_artifacts = st.one_of(
    content_relationships_artifacts(),
    field_usage_report_artifacts(),
    plugin_instances_artifacts(),
    page_composition_artifacts(),
    seo_full_artifacts(),
    editorial_workflows_artifacts(),
    search_config_artifacts(),
    integration_manifest_artifacts(),
)

# PluginTableExport is also top-level but has schema_version + source_plugin
# at the entry level rather than wrapping a list, so we test it separately too.

_all_artifacts_including_table = st.one_of(
    _all_top_level_artifacts,
    plugin_table_exports(),
)


# ===========================================================================
# Property 1: Artifact model contract enforcement
# Validates: Requirements 1.2, 1.3, 1.4, 25.1, 25.2, 25.3, 25.4
# ===========================================================================


class TestArtifactModelContractEnforcement:
    """Every artifact model enforces the bundle contract rules."""

    @given(artifact=_all_artifacts_including_table)
    @settings(max_examples=200)
    def test_schema_version_present_on_all_top_level_artifacts(self, artifact):
        """**Validates: Requirements 1.2, 1.3, 1.4, 25.1, 25.2, 25.3, 25.4**

        All top-level artifacts must carry a schema_version field.
        """
        assert hasattr(artifact, "schema_version")
        assert isinstance(artifact.schema_version, str)
        assert len(artifact.schema_version) > 0

    @given(artifact=st.one_of(
        plugin_instances_artifacts(),
        seo_full_artifacts(),
    ))
    @settings(max_examples=100)
    def test_source_plugin_present_on_plugin_derived_structures(self, artifact):
        """**Validates: Requirements 1.3, 25.3**

        Plugin-derived structures (PluginInstance, SeoPageEntry, PluginTableExport)
        must include a source_plugin field.
        """
        if isinstance(artifact, PluginInstancesArtifact):
            for inst in artifact.instances:
                assert isinstance(inst.source_plugin, str)
                assert len(inst.source_plugin) > 0
        elif isinstance(artifact, SeoFullArtifact):
            for page in artifact.pages:
                assert isinstance(page.source_plugin, str)
                assert len(page.source_plugin) > 0

    @given(export=plugin_table_exports())
    @settings(max_examples=100)
    def test_source_plugin_present_on_plugin_table_export(self, export):
        """**Validates: Requirements 1.3, 25.3**

        PluginTableExport must include a source_plugin field.
        """
        assert isinstance(export.source_plugin, str)
        assert len(export.source_plugin) > 0

    @given(artifact=st.one_of(
        page_composition_artifacts(),
        seo_full_artifacts(),
    ))
    @settings(max_examples=100)
    def test_canonical_url_present_on_page_level_entities(self, artifact):
        """**Validates: Requirements 1.4, 25.4**

        Page-level entities (PageCompositionEntry, SeoPageEntry) must include
        a canonical_url field.
        """
        if isinstance(artifact, PageCompositionArtifact):
            for page in artifact.pages:
                assert isinstance(page.canonical_url, str)
                assert len(page.canonical_url) > 0
        elif isinstance(artifact, SeoFullArtifact):
            for page in artifact.pages:
                assert isinstance(page.canonical_url, str)
                assert len(page.canonical_url) > 0

    @given(rel=content_relationships())
    @settings(max_examples=100)
    def test_stable_source_identifiers_on_content_relationships(self, rel):
        """**Validates: Requirements 1.2, 25.2**

        ContentRelationship must have stable source_id and target_id.
        """
        assert isinstance(rel.source_id, str) and len(rel.source_id) > 0
        assert isinstance(rel.target_id, str) and len(rel.target_id) > 0

    @given(inst=plugin_instances())
    @settings(max_examples=100)
    def test_stable_source_identifier_on_plugin_instance(self, inst):
        """**Validates: Requirements 1.2, 25.2**

        PluginInstance must have a stable instance_id.
        """
        assert isinstance(inst.instance_id, str) and len(inst.instance_id) > 0

    @given(entry=integration_entries())
    @settings(max_examples=100)
    def test_stable_source_identifier_on_integration_entry(self, entry):
        """**Validates: Requirements 1.2, 25.2**

        IntegrationEntry must have a stable integration_id.
        """
        assert isinstance(entry.integration_id, str) and len(entry.integration_id) > 0


# ===========================================================================
# Property 2: Artifact model serialization round-trip
# Validates: Requirements 1.6, 2.4
# ===========================================================================


class TestArtifactModelSerializationRoundTrip:
    """Serialize to dict via model_dump(), reconstruct via model_validate(),
    and assert equality."""

    @given(artifact=_all_artifacts_including_table)
    @settings(max_examples=200)
    def test_round_trip_all_artifacts(self, artifact):
        """**Validates: Requirements 1.6, 2.4**

        For every artifact model, model_dump() → model_validate() must produce
        an equal instance.
        """
        dumped = artifact.model_dump()
        reconstructed = type(artifact).model_validate(dumped)
        assert reconstructed == artifact


# ===========================================================================
# Property 3: Bundle_Schema completeness
# Validates: Requirements 2.1, 2.2
# ===========================================================================

# The 23 existing artifact file paths
_EXISTING_ARTIFACT_PATHS = {
    "site_blueprint.json",
    "site_settings.json",
    "site_options.json",
    "site_environment.json",
    "taxonomies.json",
    "menus.json",
    "media_map.json",
    "theme_mods.json",
    "global_styles.json",
    "customizer_settings.json",
    "css_sources.json",
    "plugins_fingerprint.json",
    "plugin_behaviors.json",
    "blocks_usage.json",
    "block_patterns.json",
    "acf_field_groups.json",
    "custom_fields_config.json",
    "shortcodes_inventory.json",
    "forms_config.json",
    "widgets.json",
    "page_templates.json",
    "rewrite_rules.json",
    "rest_api_endpoints.json",
    "hooks_registry.json",
    "error_log.json",
}

# The 9 new CMS artifact file paths
_NEW_ARTIFACT_PATHS = {
    "content_relationships.json",
    "field_usage_report.json",
    "plugin_instances.json",
    "page_composition.json",
    "seo_full.json",
    "editorial_workflows.json",
    "plugin_table_exports.json",
    "search_config.json",
    "integration_manifest.json",
}

_ALL_ARTIFACT_PATHS = _EXISTING_ARTIFACT_PATHS | _NEW_ARTIFACT_PATHS

# Semver pattern
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


class TestBundleSchemaCompleteness:
    """BUNDLE_SCHEMA_V1 must contain all 32 artifacts with correct metadata."""

    def test_schema_contains_all_32_artifacts(self):
        """**Validates: Requirements 2.1, 2.2**

        BUNDLE_SCHEMA_V1 must define exactly 32 artifacts (23 existing + 9 new).
        """
        schema_paths = {a.file_path for a in BUNDLE_SCHEMA_V1.artifacts}
        assert len(BUNDLE_SCHEMA_V1.artifacts) == len(_ALL_ARTIFACT_PATHS)
        assert schema_paths == _ALL_ARTIFACT_PATHS

    @given(artifact=st.sampled_from(BUNDLE_SCHEMA_V1.artifacts))
    @settings(max_examples=50)
    def test_all_required_artifacts_marked_correctly(self, artifact):
        """**Validates: Requirements 2.1, 2.2**

        Every artifact in the schema has a valid requirement level.
        """
        assert artifact.requirement in (ArtifactRequirement.REQUIRED, ArtifactRequirement.OPTIONAL)

    @given(artifact=st.sampled_from(BUNDLE_SCHEMA_V1.artifacts))
    @settings(max_examples=50)
    def test_schema_version_follows_semver(self, artifact):
        """**Validates: Requirements 2.1, 2.2**

        Every artifact definition's schema_version must follow semver format.
        """
        assert _SEMVER_RE.match(artifact.schema_version), (
            f"Artifact {artifact.file_path} has non-semver schema_version: {artifact.schema_version}"
        )

    def test_bundle_schema_own_version_is_semver(self):
        """**Validates: Requirements 2.1, 2.2**

        The BUNDLE_SCHEMA_V1 top-level schema_version must follow semver.
        """
        assert _SEMVER_RE.match(BUNDLE_SCHEMA_V1.schema_version)
