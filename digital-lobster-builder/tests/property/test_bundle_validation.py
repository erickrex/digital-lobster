from __future__ import annotations

import io
import json
import zipfile
from typing import Any

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from src.agents.blueprint_intake import validate_cms_bundle, _is_version_compatible
from src.models.bundle_manifest import BundleManifest
from src.models.bundle_schema import BUNDLE_SCHEMA_V1, ArtifactRequirement
from src.orchestrator.errors import BundleValidationError

# ---------------------------------------------------------------------------
# Helpers — reuse the same patterns from unit tests
# ---------------------------------------------------------------------------

_NEW_ARTIFACT_DATA: dict[str, Any] = {
    "content_relationships.json": {"schema_version": "1.0.0", "relationships": []},
    "field_usage_report.json": {"schema_version": "1.0.0", "fields": []},
    "plugin_instances.json": {"schema_version": "1.0.0", "instances": []},
    "page_composition.json": {"schema_version": "1.0.0", "pages": []},
    "seo_full.json": {"schema_version": "1.0.0", "pages": []},
    "editorial_workflows.json": {
        "schema_version": "1.0.0",
        "statuses_in_use": ["publish"],
        "scheduled_publishing": False,
        "draft_behavior": "standard",
        "preview_expectations": "none",
        "revision_policy": "keep_all",
        "comments_enabled": False,
        "authoring_model": "single_editor",
    },
    "plugin_table_exports.json": [],
    "search_config.json": {
        "schema_version": "1.0.0",
        "searchable_types": [],
        "ranking_hints": [],
        "facets": [],
    },
    "integration_manifest.json": {"schema_version": "1.0.0", "integrations": []},
}

_EXISTING_ARTIFACT_DATA: dict[str, Any] = {
    "site_blueprint.json": {"schema_version": "1.0.0"},
    "site_settings.json": {"schema_version": "1.0.0"},
    "site_options.json": {"schema_version": "1.0.0"},
    "site_environment.json": {"schema_version": "1.0.0"},
    "taxonomies.json": {"schema_version": "1.0.0"},
    "menus.json": [],
    "media_map.json": [],
    "theme_mods.json": {"schema_version": "1.0.0"},
    "global_styles.json": {"schema_version": "1.0.0"},
    "customizer_settings.json": {"schema_version": "1.0.0"},
    "css_sources.json": {"schema_version": "1.0.0"},
    "plugins_fingerprint.json": {"schema_version": "1.0.0"},
    "plugin_behaviors.json": {"schema_version": "1.0.0"},
    "blocks_usage.json": {"schema_version": "1.0.0"},
    "block_patterns.json": {"schema_version": "1.0.0"},
    "acf_field_groups.json": {"schema_version": "1.0.0"},
    "custom_fields_config.json": {"schema_version": "1.0.0"},
    "shortcodes_inventory.json": {"schema_version": "1.0.0"},
    "forms_config.json": {"schema_version": "1.0.0"},
    "widgets.json": {"schema_version": "1.0.0"},
    "page_templates.json": {"schema_version": "1.0.0"},
    "rewrite_rules.json": {"schema_version": "1.0.0"},
    "rest_api_endpoints.json": {"schema_version": "1.0.0"},
    "hooks_registry.json": {"schema_version": "1.0.0"},
    "error_log.json": {"schema_version": "1.0.0"},
}

_SITE_INFO: dict[str, str] = {
    "site_url": "https://example.com",
    "site_name": "Test Site",
    "wordpress_version": "6.5",
}

# All required artifact file paths from the schema
_REQUIRED_ARTIFACTS = [
    a.file_path
    for a in BUNDLE_SCHEMA_V1.artifacts
    if a.requirement == ArtifactRequirement.REQUIRED
]

def _all_artifact_data() -> dict[str, Any]:
    """Return a complete set of artifact data for a valid CMS bundle."""
    return {**_EXISTING_ARTIFACT_DATA, **_NEW_ARTIFACT_DATA}

def _make_zip(files: dict[str, Any], raw_overrides: dict[str, bytes] | None = None) -> zipfile.ZipFile:
    """Build an in-memory ZIP from a mapping of path → JSON-serialisable data.

    ``raw_overrides`` lets callers inject raw bytes for specific paths
    (e.g. malformed JSON).
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for path, data in files.items():
            if raw_overrides and path in raw_overrides:
                zf.writestr(path, raw_overrides[path])
            else:
                zf.writestr(path, json.dumps(data))
    buf.seek(0)
    return zipfile.ZipFile(buf)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy: draw a non-empty subset of required artifacts to remove
_required_artifact_subsets = st.lists(
    st.sampled_from(_REQUIRED_ARTIFACTS),
    min_size=1,
    max_size=len(_REQUIRED_ARTIFACTS),
    unique=True,
)

# The 9 new typed artifacts that go through Pydantic validation
_NEW_TYPED_ARTIFACT_PATHS = [
    "content_relationships.json",
    "field_usage_report.json",
    "plugin_instances.json",
    "page_composition.json",
    "seo_full.json",
    "editorial_workflows.json",
    "plugin_table_exports.json",
    "search_config.json",
    "integration_manifest.json",
]

# Strategy: pick a new typed artifact to corrupt
_new_artifact_to_corrupt = st.sampled_from(_NEW_TYPED_ARTIFACT_PATHS)

# Strategy: generate incompatible major versions (2-9, never 1)
_incompatible_major = st.integers(min_value=2, max_value=9)

# Strategy: generate compatible minor/patch bumps (same major=1)
_compatible_minor = st.integers(min_value=0, max_value=99)
_compatible_patch = st.integers(min_value=0, max_value=99)

# ===========================================================================
# Property 4: Missing artifact detection
# ===========================================================================

class TestMissingArtifactDetection:
    """For any subset of required artifacts removed from a valid bundle,
    validate_cms_bundle raises BundleValidationError listing exactly
    those missing artifacts."""
    @given(to_remove=_required_artifact_subsets)
    @settings(max_examples=80)
    def test_removed_required_artifacts_are_all_reported(self, to_remove: list[str]):
        """        Removing any non-empty subset of required artifacts from a complete
        bundle must raise BundleValidationError whose missing_artifacts
        field lists exactly the removed artifacts.
        """
        files = _all_artifact_data()
        for path in to_remove:
            files.pop(path, None)

        zf = _make_zip(files)
        with pytest.raises(BundleValidationError) as exc_info:
            validate_cms_bundle(zf, _SITE_INFO, [])

        err = exc_info.value
        assert set(err.missing_artifacts) == set(to_remove)

# ===========================================================================
# Property 5: Malformed artifact rejection
# ===========================================================================

class TestMalformedArtifactRejection:
    """For any artifact replaced with malformed JSON or invalid Pydantic data,
    validate_cms_bundle raises BundleValidationError with that artifact name
    in validation_failures."""
    @given(artifact_path=_new_artifact_to_corrupt)
    @settings(max_examples=50)
    def test_malformed_json_detected(self, artifact_path: str):
        """        Replacing any new typed artifact with invalid JSON must raise
        BundleValidationError with that artifact in validation_failures.
        """
        files = _all_artifact_data()
        raw_overrides = {artifact_path: b"NOT VALID JSON{{{"}
        zf = _make_zip(files, raw_overrides=raw_overrides)

        with pytest.raises(BundleValidationError) as exc_info:
            validate_cms_bundle(zf, _SITE_INFO, [])

        err = exc_info.value
        failed_artifacts = [f["artifact"] for f in err.validation_failures]
        assert artifact_path in failed_artifacts

    @given(artifact_path=st.sampled_from([
        p for p in _NEW_TYPED_ARTIFACT_PATHS if p != "plugin_table_exports.json"
    ]))
    @settings(max_examples=50)
    def test_invalid_pydantic_data_detected_dict_artifacts(self, artifact_path: str):
        """        Replacing any new dict-shaped typed artifact with structurally wrong
        JSON (valid JSON but missing required Pydantic fields) must raise
        BundleValidationError with that artifact in validation_failures.
        """
        files = _all_artifact_data()
        # Replace with a dict that has schema_version but is missing
        # the required content fields for every model
        files[artifact_path] = {"schema_version": "1.0.0", "bogus_field": True}
        zf = _make_zip(files)

        with pytest.raises(BundleValidationError) as exc_info:
            validate_cms_bundle(zf, _SITE_INFO, [])

        err = exc_info.value
        failed_artifacts = [f["artifact"] for f in err.validation_failures]
        assert artifact_path in failed_artifacts

    def test_invalid_pydantic_data_detected_list_artifact(self):
        """        Replacing plugin_table_exports.json with a list of entries that
        have invalid Pydantic data must raise BundleValidationError.
        """
        files = _all_artifact_data()
        # A list entry missing required fields for PluginTableExport
        files["plugin_table_exports.json"] = [{"schema_version": "1.0.0", "bogus": True}]
        zf = _make_zip(files)

        with pytest.raises(BundleValidationError) as exc_info:
            validate_cms_bundle(zf, _SITE_INFO, [])

        err = exc_info.value
        failed_artifacts = [f["artifact"] for f in err.validation_failures]
        assert "plugin_table_exports.json" in failed_artifacts

# ===========================================================================
# Property 6: Schema version compatibility validation
# ===========================================================================

class TestSchemaVersionCompatibility:
    """For any artifact with incompatible major version, validate_cms_bundle
    rejects; for compatible versions (same major), it accepts."""
    @given(
        artifact_path=st.sampled_from(_NEW_TYPED_ARTIFACT_PATHS),
        bad_major=_incompatible_major,
        minor=_compatible_minor,
        patch=_compatible_patch,
    )
    @settings(max_examples=80)
    def test_incompatible_major_version_rejected(
        self, artifact_path: str, bad_major: int, minor: int, patch: int
    ):
        """        Any artifact whose major version differs from the expected major
        version must cause a BundleValidationError.
        """
        files = _all_artifact_data()
        bad_version = f"{bad_major}.{minor}.{patch}"

        # Inject the bad version into the artifact data
        if isinstance(files[artifact_path], dict):
            files[artifact_path] = {**files[artifact_path], "schema_version": bad_version}
        elif isinstance(files[artifact_path], list):
            # plugin_table_exports is a list — inject a single entry with bad version
            files[artifact_path] = [{
                "table_name": "wp_test",
                "schema_version": bad_version,
                "source_plugin": "test-plugin",
                "row_count": 0,
                "primary_key": "id",
                "foreign_key_candidates": [],
                "rows": [],
            }]

        zf = _make_zip(files)
        with pytest.raises(BundleValidationError) as exc_info:
            validate_cms_bundle(zf, _SITE_INFO, [])

        err = exc_info.value
        failed_artifacts = [f["artifact"] for f in err.validation_failures]
        assert artifact_path in failed_artifacts
        # The error message should mention schema_version
        matching = [f for f in err.validation_failures if f["artifact"] == artifact_path]
        assert any("schema_version" in f["error"].lower() for f in matching)

    @given(
        minor=_compatible_minor,
        patch=_compatible_patch,
    )
    @settings(max_examples=50)
    def test_compatible_version_accepted(self, minor: int, patch: int):
        """        Artifacts with the same major version (1.x.y) as expected must
        be accepted and produce a valid BundleManifest.
        """
        files = _all_artifact_data()
        compatible_version = f"1.{minor}.{patch}"

        # Apply compatible version to content_relationships as representative
        files["content_relationships.json"] = {
            "schema_version": compatible_version,
            "relationships": [],
        }

        zf = _make_zip(files)
        result = validate_cms_bundle(zf, _SITE_INFO, [])
        assert isinstance(result, BundleManifest)

# ===========================================================================
# Property 7: Valid Bundle_Manifest production
# ===========================================================================

class TestValidBundleManifestProduction:
    """For a complete valid bundle, validate_cms_bundle returns a
    BundleManifest with all artifacts populated."""
    @given(data=st.data())
    @settings(max_examples=30)
    def test_valid_bundle_produces_manifest_with_all_fields(self, data):
        """        A complete valid bundle must produce a BundleManifest where every
        expected field is populated (not None).
        """
        files = _all_artifact_data()
        zf = _make_zip(files)
        result = validate_cms_bundle(zf, _SITE_INFO, [])

        assert isinstance(result, BundleManifest)
        assert result.schema_version == BUNDLE_SCHEMA_V1.schema_version
        assert result.site_url == _SITE_INFO["site_url"]
        assert result.site_name == _SITE_INFO["site_name"]
        assert result.wordpress_version == _SITE_INFO["wordpress_version"]

        # All 9 new typed artifacts must be present and not None
        assert result.content_relationships is not None
        assert result.field_usage_report is not None
        assert result.plugin_instances is not None
        assert result.page_composition is not None
        assert result.seo_full is not None
        assert result.editorial_workflows is not None
        assert result.plugin_table_exports is not None
        assert result.search_config is not None
        assert result.integration_manifest is not None

    @given(artifact_def=st.sampled_from(BUNDLE_SCHEMA_V1.artifacts))
    @settings(max_examples=50)
    def test_every_schema_artifact_represented_in_manifest(self, artifact_def):
        """        For every artifact defined in BUNDLE_SCHEMA_V1, the resulting
        BundleManifest must have a corresponding non-None field.
        """
        files = _all_artifact_data()
        zf = _make_zip(files)
        result = validate_cms_bundle(zf, _SITE_INFO, [])

        # Map file_path to BundleManifest field name
        field_map = {
            "site_blueprint.json": "site_blueprint",
            "site_settings.json": "site_settings",
            "site_options.json": "site_options",
            "site_environment.json": "site_environment",
            "taxonomies.json": "taxonomies",
            "menus.json": "menus",
            "media_map.json": "media_map",
            "theme_mods.json": "theme_mods",
            "global_styles.json": "global_styles",
            "customizer_settings.json": "customizer_settings",
            "css_sources.json": "css_sources",
            "plugins_fingerprint.json": "plugins_fingerprint",
            "plugin_behaviors.json": "plugin_behaviors",
            "blocks_usage.json": "blocks_usage",
            "block_patterns.json": "block_patterns",
            "acf_field_groups.json": "acf_field_groups",
            "custom_fields_config.json": "custom_fields_config",
            "shortcodes_inventory.json": "shortcodes_inventory",
            "forms_config.json": "forms_config",
            "widgets.json": "widgets",
            "page_templates.json": "page_templates",
            "rewrite_rules.json": "rewrite_rules",
            "rest_api_endpoints.json": "rest_api_endpoints",
            "hooks_registry.json": "hooks_registry",
            "error_log.json": "error_log",
            "content_relationships.json": "content_relationships",
            "field_usage_report.json": "field_usage_report",
            "plugin_instances.json": "plugin_instances",
            "page_composition.json": "page_composition",
            "seo_full.json": "seo_full",
            "editorial_workflows.json": "editorial_workflows",
            "plugin_table_exports.json": "plugin_table_exports",
            "search_config.json": "search_config",
            "integration_manifest.json": "integration_manifest",
        }

        field_name = field_map.get(artifact_def.file_path)
        assert field_name is not None, f"No field mapping for {artifact_def.file_path}"
        value = getattr(result, field_name)
        assert value is not None
