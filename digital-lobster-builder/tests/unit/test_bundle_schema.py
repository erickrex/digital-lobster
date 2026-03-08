import re

import pytest
from pydantic import ValidationError

from src.models.bundle_schema import (
    ArtifactDefinition,
    ArtifactRequirement,
    BundleSchema,
    BUNDLE_SCHEMA_V1,
)

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

# The 9 new CMS artifact file paths added by this spec.
NEW_CMS_ARTIFACTS = {
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


class TestBundleSchemaV1Completeness:
    """BUNDLE_SCHEMA_V1 contains exactly 34 artifacts (25 existing + 9 new)."""

    def test_total_artifact_count(self):
        assert len(BUNDLE_SCHEMA_V1.artifacts) == 34

    def test_all_new_cms_artifacts_present(self):
        paths = {a.file_path for a in BUNDLE_SCHEMA_V1.artifacts}
        assert NEW_CMS_ARTIFACTS.issubset(paths)

    def test_new_cms_artifacts_are_required(self):
        for artifact in BUNDLE_SCHEMA_V1.artifacts:
            if artifact.file_path in NEW_CMS_ARTIFACTS:
                assert artifact.requirement == ArtifactRequirement.REQUIRED, (
                    f"{artifact.file_path} should be REQUIRED"
                )


class TestOptionalArtifacts:
    """hooks_registry and error_log are the only OPTIONAL artifacts."""

    def test_hooks_registry_optional(self):
        by_path = {a.file_path: a for a in BUNDLE_SCHEMA_V1.artifacts}
        assert by_path["hooks_registry.json"].requirement == ArtifactRequirement.OPTIONAL

    def test_error_log_optional(self):
        by_path = {a.file_path: a for a in BUNDLE_SCHEMA_V1.artifacts}
        assert by_path["error_log.json"].requirement == ArtifactRequirement.OPTIONAL


class TestArtifactDefinitionSemver:
    """ArtifactDefinition schema_version follows semver format (X.Y.Z)."""

    def test_all_artifact_schema_versions_are_semver(self):
        for artifact in BUNDLE_SCHEMA_V1.artifacts:
            assert SEMVER_RE.match(artifact.schema_version), (
                f"{artifact.file_path} schema_version '{artifact.schema_version}' is not semver"
            )

    def test_bundle_schema_version_is_semver(self):
        assert SEMVER_RE.match(BUNDLE_SCHEMA_V1.schema_version)


class TestArtifactFilePaths:
    """All artifact file_paths end with .json and are unique."""

    def test_all_file_paths_end_with_json(self):
        for artifact in BUNDLE_SCHEMA_V1.artifacts:
            assert artifact.file_path.endswith(".json"), (
                f"{artifact.file_path} does not end with .json"
            )

    def test_no_duplicate_file_paths(self):
        paths = [a.file_path for a in BUNDLE_SCHEMA_V1.artifacts]
        assert len(paths) == len(set(paths)), "Duplicate file_paths found"
