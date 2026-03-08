from __future__ import annotations

import io
import json
import zipfile
from typing import Any

import pytest

from src.agents.blueprint_intake import (
    _is_version_compatible,
    validate_cms_bundle,
)
from src.models.bundle_manifest import BundleManifest
from src.models.bundle_schema import BUNDLE_SCHEMA_V1, ArtifactRequirement
from src.orchestrator.errors import BundleValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Minimal valid data for each of the 9 new typed artifacts.
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

# Minimal valid data for the 23 existing artifacts (plain dicts/lists).
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
    # Optional artifacts — included for completeness
    "hooks_registry.json": {"schema_version": "1.0.0"},
    "error_log.json": {"schema_version": "1.0.0"},
}


def _all_artifact_data() -> dict[str, Any]:
    """Return a complete set of artifact data for a valid CMS bundle."""
    return {**_EXISTING_ARTIFACT_DATA, **_NEW_ARTIFACT_DATA}


def _make_zip(files: dict[str, Any]) -> zipfile.ZipFile:
    """Build an in-memory ZIP from a mapping of path → JSON-serialisable data."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for path, data in files.items():
            zf.writestr(path, json.dumps(data))
    buf.seek(0)
    return zipfile.ZipFile(buf)


_SITE_INFO: dict[str, str] = {
    "site_url": "https://example.com",
    "site_name": "Test Site",
    "wordpress_version": "6.5",
}


# ---------------------------------------------------------------------------
# _is_version_compatible
# ---------------------------------------------------------------------------


class TestIsVersionCompatible:
    def test_same_version(self):
        assert _is_version_compatible("1.0.0", "1.0.0") is True

    def test_minor_bump_compatible(self):
        assert _is_version_compatible("1.2.0", "1.0.0") is True

    def test_patch_bump_compatible(self):
        assert _is_version_compatible("1.0.3", "1.0.0") is True

    def test_major_mismatch(self):
        assert _is_version_compatible("2.0.0", "1.0.0") is False

    def test_empty_string(self):
        assert _is_version_compatible("", "1.0.0") is False

    def test_non_semver(self):
        assert _is_version_compatible("abc", "1.0.0") is False


# ---------------------------------------------------------------------------
# validate_cms_bundle — missing artifacts
# ---------------------------------------------------------------------------


class TestMissingArtifacts:
    """Requirement 3.1, 3.2: detect and report all missing required artifacts."""

    def test_empty_bundle_reports_all_missing(self):
        """An empty ZIP should list every required artifact as missing."""
        zf = _make_zip({})
        required = [
            a.file_path
            for a in BUNDLE_SCHEMA_V1.artifacts
            if a.requirement == ArtifactRequirement.REQUIRED
        ]
        with pytest.raises(BundleValidationError) as exc_info:
            validate_cms_bundle(zf, _SITE_INFO, [])
        err = exc_info.value
        assert sorted(err.missing_artifacts) == sorted(required)

    def test_single_missing_artifact(self):
        """Removing one required artifact should list exactly that artifact."""
        files = _all_artifact_data()
        files.pop("content_relationships.json")
        zf = _make_zip(files)
        with pytest.raises(BundleValidationError) as exc_info:
            validate_cms_bundle(zf, _SITE_INFO, [])
        err = exc_info.value
        assert err.missing_artifacts == ["content_relationships.json"]

    def test_multiple_missing_artifacts_all_listed(self):
        """All missing artifacts should be listed, not just the first."""
        files = _all_artifact_data()
        files.pop("seo_full.json")
        files.pop("search_config.json")
        zf = _make_zip(files)
        with pytest.raises(BundleValidationError) as exc_info:
            validate_cms_bundle(zf, _SITE_INFO, [])
        err = exc_info.value
        assert set(err.missing_artifacts) == {"seo_full.json", "search_config.json"}

    def test_optional_artifact_not_required(self):
        """Omitting optional artifacts should not cause a failure."""
        files = _all_artifact_data()
        files.pop("hooks_registry.json", None)
        files.pop("error_log.json", None)
        zf = _make_zip(files)
        # Should succeed — optional artifacts are not required
        result = validate_cms_bundle(zf, _SITE_INFO, [])
        assert isinstance(result, BundleManifest)


# ---------------------------------------------------------------------------
# validate_cms_bundle — validation failures
# ---------------------------------------------------------------------------


class TestValidationFailures:
    """Requirement 2.3, 3.3: abort with artifact name and field-level details."""

    def test_malformed_json_artifact(self):
        files = _all_artifact_data()
        zf_files: dict[str, Any] = {}
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for path, data in files.items():
                if path == "content_relationships.json":
                    zf.writestr(path, "NOT VALID JSON{{{")
                else:
                    zf.writestr(path, json.dumps(data))
        buf.seek(0)
        zf = zipfile.ZipFile(buf)
        with pytest.raises(BundleValidationError) as exc_info:
            validate_cms_bundle(zf, _SITE_INFO, [])
        err = exc_info.value
        assert len(err.validation_failures) >= 1
        assert err.validation_failures[0]["artifact"] == "content_relationships.json"

    def test_pydantic_validation_failure(self):
        """A new artifact with wrong shape should produce field-level errors."""
        files = _all_artifact_data()
        # Missing required 'relationships' key
        files["content_relationships.json"] = {"schema_version": "1.0.0"}
        zf = _make_zip(files)
        with pytest.raises(BundleValidationError) as exc_info:
            validate_cms_bundle(zf, _SITE_INFO, [])
        err = exc_info.value
        assert len(err.validation_failures) >= 1
        failure = err.validation_failures[0]
        assert failure["artifact"] == "content_relationships.json"
        assert "relationships" in failure["error"]


# ---------------------------------------------------------------------------
# validate_cms_bundle — schema_version compatibility
# ---------------------------------------------------------------------------


class TestSchemaVersionCompatibility:
    """Requirement 3.5: validate schema_version compatibility."""

    def test_incompatible_major_version_rejected(self):
        files = _all_artifact_data()
        files["content_relationships.json"] = {
            "schema_version": "2.0.0",
            "relationships": [],
        }
        zf = _make_zip(files)
        with pytest.raises(BundleValidationError) as exc_info:
            validate_cms_bundle(zf, _SITE_INFO, [])
        err = exc_info.value
        assert len(err.validation_failures) >= 1
        assert "schema_version" in err.validation_failures[0]["error"].lower()

    def test_compatible_minor_bump_accepted(self):
        files = _all_artifact_data()
        files["content_relationships.json"] = {
            "schema_version": "1.1.0",
            "relationships": [],
        }
        zf = _make_zip(files)
        result = validate_cms_bundle(zf, _SITE_INFO, [])
        assert isinstance(result, BundleManifest)

    def test_boundary_version_same_major(self):
        files = _all_artifact_data()
        files["content_relationships.json"] = {
            "schema_version": "1.99.99",
            "relationships": [],
        }
        zf = _make_zip(files)
        result = validate_cms_bundle(zf, _SITE_INFO, [])
        assert isinstance(result, BundleManifest)


# ---------------------------------------------------------------------------
# validate_cms_bundle — success path
# ---------------------------------------------------------------------------


class TestSuccessfulValidation:
    """Requirement 3.4: produce BundleManifest on success."""

    def test_valid_bundle_produces_bundle_manifest(self):
        files = _all_artifact_data()
        zf = _make_zip(files)
        result = validate_cms_bundle(zf, _SITE_INFO, [])
        assert isinstance(result, BundleManifest)
        assert result.schema_version == BUNDLE_SCHEMA_V1.schema_version
        assert result.site_url == "https://example.com"
        assert result.site_name == "Test Site"

    def test_manifest_contains_typed_new_artifacts(self):
        files = _all_artifact_data()
        zf = _make_zip(files)
        result = validate_cms_bundle(zf, _SITE_INFO, [])
        # New artifacts should be typed Pydantic models, not raw dicts
        from src.models.bundle_artifacts import (
            ContentRelationshipsArtifact,
            FieldUsageReportArtifact,
            IntegrationManifestArtifact,
            SearchConfigArtifact,
        )
        assert isinstance(result.content_relationships, ContentRelationshipsArtifact)
        assert isinstance(result.field_usage_report, FieldUsageReportArtifact)
        assert isinstance(result.search_config, SearchConfigArtifact)
        assert isinstance(result.integration_manifest, IntegrationManifestArtifact)

    def test_manifest_contains_existing_artifacts_as_dicts(self):
        files = _all_artifact_data()
        zf = _make_zip(files)
        result = validate_cms_bundle(zf, _SITE_INFO, [])
        assert isinstance(result.site_blueprint, dict)
        assert isinstance(result.plugins_fingerprint, dict)
        assert isinstance(result.menus, list)
