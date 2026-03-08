from __future__ import annotations

import asyncio
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from src.agents.behavior_compiler import (
    BehaviorCompilerAgent,
    _PROXY_INTEGRATION_TYPES,
    _REBUILD_INTEGRATION_TYPES,
    _SUPPORTED_FORM_PROVIDERS,
)
from src.models.behavior_manifest import BehaviorManifest
from src.models.bundle_artifacts import (
    ContentRelationshipsArtifact,
    EditorialWorkflowsArtifact,
    FieldUsageReportArtifact,
    IntegrationEntry,
    IntegrationManifestArtifact,
    PageCompositionArtifact,
    PluginInstance,
    PluginInstancesArtifact,
    SearchConfigArtifact,
    SeoFullArtifact,
    SeoPageEntry,
)
from src.models.bundle_manifest import BundleManifest
from src.models.capability_manifest import Capability, CapabilityManifest
from src.models.content_model_manifest import (
    ContentModelManifest,
    StrapiCollection,
    StrapiRelation,
)
from src.models.finding import Finding, FindingSeverity
from src.models.migration_mapping_manifest import MigrationMappingManifest
from src.models.presentation_manifest import (
    PresentationManifest,
    RouteTemplate,
)
from src.models.strapi_types import StrapiFieldDefinition


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FORM_PROVIDERS = st.sampled_from(sorted(_SUPPORTED_FORM_PROVIDERS))

_INTEGRATION_TYPES_REBUILD = st.sampled_from(sorted(_REBUILD_INTEGRATION_TYPES))
_INTEGRATION_TYPES_PROXY = st.sampled_from(sorted(_PROXY_INTEGRATION_TYPES))
_INTEGRATION_TYPES_ALL = st.sampled_from(
    sorted(_REBUILD_INTEGRATION_TYPES | _PROXY_INTEGRATION_TYPES | {"custom_unknown", "legacy_sync"})
)

_POST_TYPES = st.sampled_from(["post", "page", "event", "testimonial", "service"])

_SEARCHABLE_TYPES = st.sampled_from(["post", "page", "event", "service"])


def _clean_bundle(**overrides: Any) -> BundleManifest:
    """Build a minimal BundleManifest for behavior compiler tests."""
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
    )
    defaults.update(overrides)
    return CapabilityManifest(**defaults)


def _clean_content_model(**overrides: Any) -> ContentModelManifest:
    defaults: dict[str, Any] = dict(
        collections=[],
        components=[],
        relations=[],
        seo_strategy=None,
        validation_hints=[],
    )
    defaults.update(overrides)
    return ContentModelManifest(**defaults)


def _clean_presentation(**overrides: Any) -> PresentationManifest:
    defaults: dict[str, Any] = dict(
        layouts=[],
        route_templates=[],
        sections=[],
        fallback_zones=[],
        style_tokens={},
    )
    defaults.update(overrides)
    return PresentationManifest(**defaults)


def _make_agent() -> BehaviorCompilerAgent:
    return BehaviorCompilerAgent(gradient_client=None)


def _run(coro):
    return asyncio.run(coro)


def _execute(
    bundle: BundleManifest,
    cap_manifest: CapabilityManifest | None = None,
    content_model: ContentModelManifest | None = None,
    presentation: PresentationManifest | None = None,
) -> tuple[BehaviorManifest, MigrationMappingManifest]:
    agent = _make_agent()
    context: dict[str, Any] = {
        "bundle_manifest": bundle,
        "capability_manifest": cap_manifest or _clean_capability_manifest(),
        "content_model_manifest": content_model or _clean_content_model(),
        "presentation_manifest": presentation or _clean_presentation(),
    }
    result = _run(agent.execute(context))
    return (
        result.artifacts["behavior_manifest"],
        result.artifacts["migration_mapping_manifest"],
    )


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------


@st.composite
def form_instances(draw) -> PluginInstance:
    """Generate a form PluginInstance from a supported provider."""
    provider = draw(_FORM_PROVIDERS)
    idx = draw(st.integers(min_value=1, max_value=999))
    return PluginInstance(
        instance_id=f"form-{provider}-{idx}",
        source_plugin=provider,
        instance_type="form",
        config={
            "fields": [{"name": "email", "type": "email"}],
            "submission_destination": "astro_api_route",
        },
    )


@st.composite
def redirect_rules_data(draw) -> dict[str, Any]:
    """Generate a redirect entry for rewrite_rules."""
    idx = draw(st.integers(min_value=1, max_value=500))
    return {
        "source_url": f"/old-page-{idx}/",
        "target_url": f"/new-page-{idx}/",
        "status_code": draw(st.sampled_from([301, 302])),
        "source_plugin": draw(st.sampled_from([None, "redirection", "yoast"])),
    }


@st.composite
def integration_entries(draw) -> IntegrationEntry:
    """Generate an IntegrationEntry with a random type."""
    itype = draw(_INTEGRATION_TYPES_ALL)
    idx = draw(st.integers(min_value=1, max_value=500))
    return IntegrationEntry(
        integration_id=f"int-{itype}-{idx}",
        integration_type=itype,
        target=f"https://api.example.com/{itype}",
        business_critical=draw(st.booleans()),
    )


# ===========================================================================
# Property 16: Behavior compiler completeness
# Validates: Requirements 16.1, 16.3, 16.4, 16.5, 16.6
# ===========================================================================


class TestBehaviorCompilerCompleteness:
    """For any valid BundleManifest:
    - Every form instance from a supported provider has a FormStrategy
    - Every redirect rule maps to a RedirectRule
    - Every integration has an IntegrationBoundary
    - Search strategy is present when search_config is non-empty
    - All output lists are sorted (determinism)
    """

    @given(
        instances=st.lists(form_instances(), min_size=1, max_size=6),
    )
    @settings(max_examples=100)
    def test_every_supported_form_instance_has_strategy(
        self, instances: list[PluginInstance]
    ):
        """**Validates: Requirements 16.1, 16.3**

        Every form instance from a supported provider (cf7, wpforms,
        gravity_forms, ninja_forms) must produce a FormStrategy entry.
        """
        # Deduplicate by instance_id to match what the compiler sees
        seen_ids: set[str] = set()
        unique: list[PluginInstance] = []
        for inst in instances:
            if inst.instance_id not in seen_ids:
                seen_ids.add(inst.instance_id)
                unique.append(inst)

        bundle = _clean_bundle(
            plugin_instances=PluginInstancesArtifact(
                schema_version="1.0.0", instances=unique
            ),
        )
        behavior, _ = _execute(bundle)

        strategy_form_ids = {fs.form_id for fs in behavior.forms_strategy}
        expected_ids = {inst.instance_id for inst in unique}

        assert expected_ids == strategy_form_ids, (
            f"Missing FormStrategy for form IDs: {expected_ids - strategy_form_ids}"
        )

        # Each strategy must reference the correct source_plugin
        for fs in behavior.forms_strategy:
            matching = next(i for i in unique if i.instance_id == fs.form_id)
            assert fs.source_plugin == matching.source_plugin

    @given(
        redirects=st.lists(redirect_rules_data(), min_size=1, max_size=6),
    )
    @settings(max_examples=100)
    def test_every_redirect_rule_produces_redirect_entry(
        self, redirects: list[dict[str, Any]]
    ):
        """**Validates: Requirements 16.1, 16.4**

        Every redirect in rewrite_rules must produce a RedirectRule in the
        behavior manifest.
        """
        # Deduplicate by (source_url, target_url) to match compiler logic
        seen: set[tuple[str, str]] = set()
        unique: list[dict[str, Any]] = []
        for r in redirects:
            key = (r["source_url"], r["target_url"])
            if key not in seen:
                seen.add(key)
                unique.append(r)

        bundle = _clean_bundle(
            rewrite_rules={"redirects": unique},
        )
        behavior, _ = _execute(bundle)

        result_pairs = {(r.source_url, r.target_url) for r in behavior.redirects}
        expected_pairs = {(r["source_url"], r["target_url"]) for r in unique}

        assert expected_pairs == result_pairs, (
            f"Missing redirects: {expected_pairs - result_pairs}"
        )

    @given(
        integrations=st.lists(integration_entries(), min_size=1, max_size=6),
    )
    @settings(max_examples=100)
    def test_every_integration_has_boundary(
        self, integrations: list[IntegrationEntry]
    ):
        """**Validates: Requirements 16.1, 16.6**

        Every integration in the integration_manifest must produce an
        IntegrationBoundary with a valid disposition.
        """
        bundle = _clean_bundle(
            integration_manifest=IntegrationManifestArtifact(
                schema_version="1.0.0", integrations=integrations
            ),
        )
        behavior, _ = _execute(bundle)

        boundary_ids = {b.integration_id for b in behavior.integration_boundaries}
        expected_ids = {i.integration_id for i in integrations}

        assert expected_ids == boundary_ids, (
            f"Missing boundaries: {expected_ids - boundary_ids}"
        )

        for boundary in behavior.integration_boundaries:
            assert boundary.disposition in {"rebuild", "proxy", "drop"}, (
                f"Invalid disposition '{boundary.disposition}' for {boundary.integration_id}"
            )

    @given(
        searchable=st.lists(
            _SEARCHABLE_TYPES, min_size=1, max_size=3, unique=True
        ),
    )
    @settings(max_examples=100)
    def test_search_strategy_present_when_searchable_types_non_empty(
        self, searchable: list[str]
    ):
        """**Validates: Requirements 16.1, 16.5**

        When search_config has non-empty searchable_types and matching
        content model collections, search_strategy must be non-None.
        """
        collections = [
            StrapiCollection(
                display_name=pt.title(),
                singular_name=pt,
                plural_name=f"{pt}s",
                api_id=pt,
                fields=[StrapiFieldDefinition(name="title", strapi_type="string")],
                components=[],
                source_post_type=pt,
            )
            for pt in searchable
        ]
        content_model = _clean_content_model(collections=collections)

        bundle = _clean_bundle(
            search_config=SearchConfigArtifact(
                schema_version="1.0.0",
                searchable_types=searchable,
                ranking_hints=[],
                facets=[],
            ),
        )
        behavior, _ = _execute(bundle, content_model=content_model)

        assert behavior.search_strategy is not None, (
            "search_strategy must be non-None when searchable_types is non-empty"
        )
        assert behavior.search_strategy.enabled is True

    @given(
        instances=st.lists(form_instances(), min_size=2, max_size=5),
    )
    @settings(max_examples=100)
    def test_output_lists_are_sorted(
        self, instances: list[PluginInstance]
    ):
        """**Validates: Requirements 16.1**

        All output lists in the behavior manifest must be sorted for
        determinism.
        """
        bundle = _clean_bundle(
            plugin_instances=PluginInstancesArtifact(
                schema_version="1.0.0", instances=instances
            ),
        )
        behavior, _ = _execute(bundle)

        form_ids = [fs.form_id for fs in behavior.forms_strategy]
        assert form_ids == sorted(form_ids), "forms_strategy must be sorted by form_id"


# ===========================================================================
# Property 17: Behavior classification
# Validates: Requirements 16.2
# ===========================================================================


class TestBehaviorClassification:
    """For any CapabilityManifest with capabilities classified as
    'unsupported', the behavior manifest must contain Finding entries in
    unsupported_constructs. Each Finding must have non-empty severity,
    stage, construct, message, recommended_action.
    """

    @given(
        unsupported_count=st.integers(min_value=1, max_value=5),
        cap_type=st.sampled_from([
            "content_model", "seo", "widget", "form", "shortcode",
            "search_filter", "integration", "editorial", "template",
        ]),
        plugin_name=st.sampled_from([
            "elementor", "divi", "woocommerce", "bbpress", "buddypress",
        ]),
    )
    @settings(max_examples=100)
    def test_unsupported_capabilities_produce_findings(
        self, unsupported_count: int, cap_type: str, plugin_name: str
    ):
        """**Validates: Requirements 16.2**

        Every capability classified as 'unsupported' must produce a Finding
        in unsupported_constructs.
        """
        unsupported_caps = [
            Capability(
                capability_type=cap_type,
                source_plugin=f"{plugin_name}_{i}",
                classification="unsupported",
                confidence=0.9,
            )
            for i in range(unsupported_count)
        ]
        # Mix in some supported capabilities to ensure they don't produce findings
        supported_cap = Capability(
            capability_type="content_model",
            source_plugin="acf",
            classification="strapi_native",
            confidence=0.95,
        )
        cap_manifest = _clean_capability_manifest(
            capabilities=unsupported_caps + [supported_cap],
        )
        bundle = _clean_bundle()
        behavior, _ = _execute(bundle, cap_manifest=cap_manifest)

        # Must have at least one Finding per unsupported capability
        assert len(behavior.unsupported_constructs) >= unsupported_count, (
            f"Expected at least {unsupported_count} findings, "
            f"got {len(behavior.unsupported_constructs)}"
        )

    @given(
        plugin_name=st.sampled_from([
            "elementor", "divi", "woocommerce", "bbpress", "buddypress",
        ]),
    )
    @settings(max_examples=100)
    def test_unsupported_finding_fields_are_valid(
        self, plugin_name: str
    ):
        """**Validates: Requirements 16.2**

        Each Finding for an unsupported capability must have non-empty
        severity, stage, construct, message, and recommended_action.
        """
        cap = Capability(
            capability_type="widget",
            source_plugin=plugin_name,
            classification="unsupported",
            confidence=0.9,
        )
        cap_manifest = _clean_capability_manifest(capabilities=[cap])
        bundle = _clean_bundle()
        behavior, _ = _execute(bundle, cap_manifest=cap_manifest)

        assert len(behavior.unsupported_constructs) >= 1

        for finding in behavior.unsupported_constructs:
            assert isinstance(finding.severity, FindingSeverity), (
                f"Finding severity must be a FindingSeverity enum, got {finding.severity}"
            )
            assert finding.stage, "Finding stage must be non-empty"
            assert finding.construct, "Finding construct must be non-empty"
            assert finding.message, "Finding message must be non-empty"
            assert finding.recommended_action, "Finding recommended_action must be non-empty"


# ===========================================================================
# Property 18: Migration_Mapping_Manifest completeness
# Validates: Requirements 17.1, 17.2
# ===========================================================================


class TestMigrationMappingManifestCompleteness:
    """For any valid ContentModelManifest, PresentationManifest, and
    BehaviorManifest:
    - Every collection with source_post_type has a TypeMapping
    - Every relation has a RelationMapping
    - Every route template has a TemplateMapping
    - media_mapping_strategy is always present with relation_aware=True
    """

    @given(
        post_types=st.lists(_POST_TYPES, min_size=1, max_size=4, unique=True),
    )
    @settings(max_examples=100)
    def test_type_mappings_per_collection(
        self, post_types: list[str]
    ):
        """**Validates: Requirements 17.1, 17.2**

        Every ContentModelManifest collection with a source_post_type must
        produce a TypeMapping in the MigrationMappingManifest.
        """
        collections = [
            StrapiCollection(
                display_name=pt.title(),
                singular_name=pt,
                plural_name=f"{pt}s",
                api_id=pt,
                fields=[StrapiFieldDefinition(name="title", strapi_type="string")],
                components=[],
                source_post_type=pt,
            )
            for pt in post_types
        ]
        content_model = _clean_content_model(collections=collections)
        bundle = _clean_bundle()
        _, mapping = _execute(bundle, content_model=content_model)

        mapped_types = {tm.source_post_type for tm in mapping.type_mappings}
        expected_types = set(post_types)

        assert expected_types == mapped_types, (
            f"Missing type mappings: {expected_types - mapped_types}"
        )

        # Each mapping must point to the correct api_id
        for tm in mapping.type_mappings:
            assert tm.target_api_id == tm.source_post_type, (
                f"TypeMapping for '{tm.source_post_type}' points to "
                f"'{tm.target_api_id}' instead of '{tm.source_post_type}'"
            )

    @given(
        relation_count=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=100)
    def test_relation_mappings_per_relation(
        self, relation_count: int
    ):
        """**Validates: Requirements 17.1, 17.2**

        Every relation in the ContentModelManifest must produce a
        RelationMapping in the MigrationMappingManifest.
        """
        relations = [
            StrapiRelation(
                source_collection=f"source-{i}",
                target_collection=f"target-{i}",
                field_name=f"rel_field_{i}",
                relation_type="oneToMany",
                source_relationship_id=f"rel-{i}",
            )
            for i in range(relation_count)
        ]
        content_model = _clean_content_model(relations=relations)
        bundle = _clean_bundle()
        _, mapping = _execute(bundle, content_model=content_model)

        mapped_rel_ids = {rm.source_relationship_id for rm in mapping.relation_mappings}
        expected_ids = {f"rel-{i}" for i in range(relation_count)}

        assert expected_ids == mapped_rel_ids, (
            f"Missing relation mappings: {expected_ids - mapped_rel_ids}"
        )

    @given(
        template_count=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=100)
    def test_template_mappings_per_route_template(
        self, template_count: int
    ):
        """**Validates: Requirements 17.1, 17.2**

        Every route template in the PresentationManifest must produce a
        TemplateMapping in the MigrationMappingManifest.
        """
        route_templates = [
            RouteTemplate(
                route_pattern=f"/section-{i}/[slug]",
                layout=f"layout-{i}",
                source_template=f"template-{i}.php",
                content_collection=f"collection-{i}",
            )
            for i in range(template_count)
        ]
        presentation = _clean_presentation(route_templates=route_templates)
        bundle = _clean_bundle()
        _, mapping = _execute(bundle, presentation=presentation)

        mapped_templates = {tm.source_template for tm in mapping.template_mappings}
        expected_templates = {f"template-{i}.php" for i in range(template_count)}

        assert expected_templates == mapped_templates, (
            f"Missing template mappings: {expected_templates - mapped_templates}"
        )

        # Each mapping must preserve the route pattern and layout
        for tm in mapping.template_mappings:
            matching_rt = next(
                rt for rt in route_templates if rt.source_template == tm.source_template
            )
            assert tm.target_route_pattern == matching_rt.route_pattern
            assert tm.target_layout == matching_rt.layout

    @given(
        post_types=st.lists(_POST_TYPES, min_size=1, max_size=3, unique=True),
    )
    @settings(max_examples=100)
    def test_media_mapping_strategy_always_present_and_relation_aware(
        self, post_types: list[str]
    ):
        """**Validates: Requirements 17.1, 17.2**

        The media_mapping_strategy must always be present with
        relation_aware=True.
        """
        collections = [
            StrapiCollection(
                display_name=pt.title(),
                singular_name=pt,
                plural_name=f"{pt}s",
                api_id=pt,
                fields=[StrapiFieldDefinition(name="title", strapi_type="string")],
                components=[],
                source_post_type=pt,
            )
            for pt in post_types
        ]
        content_model = _clean_content_model(collections=collections)
        bundle = _clean_bundle()
        _, mapping = _execute(bundle, content_model=content_model)

        assert mapping.media_mapping_strategy is not None, (
            "media_mapping_strategy must always be present"
        )
        assert mapping.media_mapping_strategy.relation_aware is True, (
            "media_mapping_strategy.relation_aware must be True"
        )
