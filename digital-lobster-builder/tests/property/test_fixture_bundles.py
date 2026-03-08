from __future__ import annotations

import json
import re
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from src.models.bundle_artifacts import (
    ContentRelationshipsArtifact,
    EditorialWorkflowsArtifact,
    FieldUsageReportArtifact,
    IntegrationManifestArtifact,
    PageCompositionArtifact,
    PluginInstancesArtifact,
    PluginTableExport,
    SearchConfigArtifact,
    SeoFullArtifact,
)
from src.models.bundle_manifest import BundleManifest
from src.models.bundle_schema import BUNDLE_SCHEMA_V1, ArtifactRequirement

# ---------------------------------------------------------------------------
# Fixture bundle discovery
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
FIXTURE_BUNDLES = sorted(p for p in FIXTURE_DIR.iterdir() if p.is_dir() and not p.name.startswith("."))

# Mapping from artifact file_path to the Pydantic model that validates it.
# plugin_table_exports.json is a list of PluginTableExport, handled separately.
_ARTIFACT_MODEL_MAP: dict[str, type] = {
    "content_relationships.json": ContentRelationshipsArtifact,
    "field_usage_report.json": FieldUsageReportArtifact,
    "plugin_instances.json": PluginInstancesArtifact,
    "page_composition.json": PageCompositionArtifact,
    "seo_full.json": SeoFullArtifact,
    "editorial_workflows.json": EditorialWorkflowsArtifact,
    "search_config.json": SearchConfigArtifact,
    "integration_manifest.json": IntegrationManifestArtifact,
}

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

# ===========================================================================
# Property 30: Fixture bundle schema conformance
# ===========================================================================

class TestFixtureBundleSchemaConformance:
    """Every fixture bundle conforms to the Bundle_Schema contract."""
    @given(bundle_path=st.sampled_from(FIXTURE_BUNDLES))
    @settings(max_examples=100)
    def test_all_required_artifacts_present(self, bundle_path: Path):
        """        Every artifact marked as required in BUNDLE_SCHEMA_V1 must exist as
        a file in the fixture bundle directory or be embedded in bundle_manifest.json.
        """
        manifest_path = bundle_path / "bundle_manifest.json"
        assert manifest_path.exists(), f"bundle_manifest.json missing from {bundle_path.name}"
        manifest_data = json.loads(manifest_path.read_text())

        for artifact_def in BUNDLE_SCHEMA_V1.artifacts:
            if artifact_def.requirement != ArtifactRequirement.REQUIRED:
                continue

            artifact_file = bundle_path / artifact_def.file_path
            # Artifact is either a standalone file or embedded in bundle_manifest
            artifact_key = artifact_def.file_path.replace(".json", "")
            has_standalone = artifact_file.exists()
            has_embedded = artifact_key in manifest_data

            assert has_standalone or has_embedded, (
                f"Required artifact '{artifact_def.file_path}' missing from "
                f"fixture bundle '{bundle_path.name}' (not found as file or in manifest)"
            )

    @given(bundle_path=st.sampled_from(FIXTURE_BUNDLES))
    @settings(max_examples=100)
    def test_bundle_manifest_parses_into_pydantic_model(self, bundle_path: Path):
        """        bundle_manifest.json must parse into a valid BundleManifest model.
        """
        manifest_path = bundle_path / "bundle_manifest.json"
        data = json.loads(manifest_path.read_text())
        manifest = BundleManifest.model_validate(data)
        assert manifest.schema_version
        assert manifest.site_url
        assert manifest.site_name

    @given(bundle_path=st.sampled_from(FIXTURE_BUNDLES))
    @settings(max_examples=100)
    def test_new_cms_artifacts_parse_into_pydantic_models(self, bundle_path: Path):
        """        Each of the 9 new CMS artifacts (standalone or embedded) must parse
        into its corresponding Pydantic model.
        """
        manifest_data = json.loads((bundle_path / "bundle_manifest.json").read_text())

        for file_path, model_cls in _ARTIFACT_MODEL_MAP.items():
            artifact_key = file_path.replace(".json", "")
            standalone = bundle_path / file_path
            if standalone.exists():
                data = json.loads(standalone.read_text())
            else:
                data = manifest_data[artifact_key]
            model_cls.model_validate(data)

    @given(bundle_path=st.sampled_from(FIXTURE_BUNDLES))
    @settings(max_examples=100)
    def test_plugin_table_exports_parse(self, bundle_path: Path):
        """        plugin_table_exports.json must parse as a list of PluginTableExport.
        """
        manifest_data = json.loads((bundle_path / "bundle_manifest.json").read_text())
        standalone = bundle_path / "plugin_table_exports.json"
        if standalone.exists():
            data = json.loads(standalone.read_text())
        else:
            data = manifest_data["plugin_table_exports"]

        assert isinstance(data, list)
        for entry in data:
            PluginTableExport.model_validate(entry)

    @given(bundle_path=st.sampled_from(FIXTURE_BUNDLES))
    @settings(max_examples=100)
    def test_all_schema_versions_are_semver(self, bundle_path: Path):
        """        Every schema_version field across all artifacts must match semver.
        """
        manifest_data = json.loads((bundle_path / "bundle_manifest.json").read_text())

        # Top-level manifest schema_version
        assert _SEMVER_RE.match(manifest_data["schema_version"]), (
            f"bundle_manifest schema_version '{manifest_data['schema_version']}' is not semver"
        )

        # Each new CMS artifact's schema_version
        for file_path in list(_ARTIFACT_MODEL_MAP) + ["plugin_table_exports.json"]:
            artifact_key = file_path.replace(".json", "")
            standalone = bundle_path / file_path
            if standalone.exists():
                data = json.loads(standalone.read_text())
            else:
                data = manifest_data[artifact_key]

            if isinstance(data, list):
                for entry in data:
                    sv = entry.get("schema_version", "")
                    assert _SEMVER_RE.match(sv), (
                        f"{file_path} entry schema_version '{sv}' is not semver "
                        f"in bundle '{bundle_path.name}'"
                    )
            else:
                sv = data.get("schema_version", "")
                assert _SEMVER_RE.match(sv), (
                    f"{file_path} schema_version '{sv}' is not semver "
                    f"in bundle '{bundle_path.name}'"
                )

    @given(bundle_path=st.sampled_from(FIXTURE_BUNDLES))
    @settings(max_examples=100)
    def test_page_composition_pages_have_canonical_url(self, bundle_path: Path):
        """        Every page in page_composition must have a non-empty canonical_url.
        """
        manifest_data = json.loads((bundle_path / "bundle_manifest.json").read_text())
        standalone = bundle_path / "page_composition.json"
        if standalone.exists():
            data = json.loads(standalone.read_text())
        else:
            data = manifest_data["page_composition"]

        artifact = PageCompositionArtifact.model_validate(data)
        for page in artifact.pages:
            assert page.canonical_url, (
                f"Page in {bundle_path.name} page_composition missing canonical_url"
            )

    @given(bundle_path=st.sampled_from(FIXTURE_BUNDLES))
    @settings(max_examples=100)
    def test_seo_full_pages_have_canonical_url_and_source_plugin(self, bundle_path: Path):
        """        Every page in seo_full must have canonical_url and source_plugin.
        """
        manifest_data = json.loads((bundle_path / "bundle_manifest.json").read_text())
        standalone = bundle_path / "seo_full.json"
        if standalone.exists():
            data = json.loads(standalone.read_text())
        else:
            data = manifest_data["seo_full"]

        artifact = SeoFullArtifact.model_validate(data)
        for page in artifact.pages:
            assert page.canonical_url, (
                f"SEO page in {bundle_path.name} missing canonical_url"
            )
            assert page.source_plugin, (
                f"SEO page '{page.canonical_url}' in {bundle_path.name} missing source_plugin"
            )

    @given(bundle_path=st.sampled_from(FIXTURE_BUNDLES))
    @settings(max_examples=100)
    def test_plugin_instances_have_source_plugin(self, bundle_path: Path):
        """        Every plugin instance must have a non-empty source_plugin.
        """
        manifest_data = json.loads((bundle_path / "bundle_manifest.json").read_text())
        standalone = bundle_path / "plugin_instances.json"
        if standalone.exists():
            data = json.loads(standalone.read_text())
        else:
            data = manifest_data["plugin_instances"]

        artifact = PluginInstancesArtifact.model_validate(data)
        for inst in artifact.instances:
            assert inst.source_plugin, (
                f"Plugin instance '{inst.instance_id}' in {bundle_path.name} missing source_plugin"
            )
