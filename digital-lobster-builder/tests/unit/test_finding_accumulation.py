from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.agents.base import AgentResult
from src.agents.behavior_compiler import BehaviorCompilerAgent
from src.agents.capability_resolution import CapabilityResolutionAgent
from src.agents.parity_qa import ParityQAAgent
from src.agents.presentation_compiler import PresentationCompilerAgent
from src.agents.schema_compiler import SchemaCompilerAgent
from src.models.behavior_manifest import BehaviorManifest, IntegrationBoundary
from src.models.bundle_artifacts import (
    ContentRelationshipsArtifact,
    EditorialWorkflowsArtifact,
    FieldUsageReportArtifact,
    IntegrationEntry,
    IntegrationManifestArtifact,
    PageCompositionArtifact,
    PageCompositionEntry,
    PluginInstance,
    PluginInstancesArtifact,
    SearchConfigArtifact,
    SeoFullArtifact,
)
from src.models.bundle_manifest import BundleManifest
from src.models.capability_manifest import Capability, CapabilityManifest
from src.models.content_model_manifest import ContentModelManifest
from src.models.finding import Finding, FindingSeverity
from src.models.parity_report import ParityReport
from src.models.presentation_manifest import PresentationManifest
from src.orchestrator.pipeline import PipelineOrchestrator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_bundle(**overrides: Any) -> BundleManifest:
    """Build a minimal BundleManifest."""
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

def _clean_cap_manifest(**overrides: Any) -> CapabilityManifest:
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

def _run(coro):
    return asyncio.run(coro)

def _assert_valid_finding(finding: Finding) -> None:
    """Assert a Finding has all required non-empty fields."""
    assert isinstance(finding.severity, FindingSeverity)
    assert finding.stage and len(finding.stage) > 0
    assert finding.construct and len(finding.construct) > 0
    assert finding.message and len(finding.message) > 0
    assert finding.recommended_action and len(finding.recommended_action) > 0

# ---------------------------------------------------------------------------
# 1. CapabilityResolutionAgent — Finding production
# ---------------------------------------------------------------------------

class TestCapabilityResolutionFindings:
    """Verify capability_resolution produces Findings for unsupported plugins."""
    def test_unsupported_plugin_produces_finding(self):
        bundle = _clean_bundle(
            plugins_fingerprint={
                "plugins": [
                    {"slug": "unknown-gallery", "family": "unknown_gallery", "status": "active"},
                ]
            },
        )
        agent = CapabilityResolutionAgent(gradient_client=None)
        result = _run(agent.execute({"bundle_manifest": bundle}))
        manifest = result.artifacts["capability_manifest"]

        assert len(manifest.findings) >= 1
        finding = manifest.findings[0]
        _assert_valid_finding(finding)
        assert finding.stage == "capability_resolution"
        assert "unknown-gallery" in finding.construct

    def test_business_critical_integration_produces_finding(self):
        bundle = _clean_bundle(
            integration_manifest=IntegrationManifestArtifact(
                schema_version="1.0.0",
                integrations=[
                    IntegrationEntry(
                        integration_id="crm-sync",
                        integration_type="crm",
                        target="https://crm.example.com",
                        business_critical=True,
                    ),
                ],
            ),
        )
        agent = CapabilityResolutionAgent(gradient_client=None)
        result = _run(agent.execute({"bundle_manifest": bundle}))
        manifest = result.artifacts["capability_manifest"]

        critical_findings = [
            f for f in manifest.findings if "crm-sync" in f.construct
        ]
        assert len(critical_findings) >= 1
        _assert_valid_finding(critical_findings[0])
        assert critical_findings[0].stage == "capability_resolution"

# ---------------------------------------------------------------------------
# 2. SchemaCompilerAgent — Finding production
# ---------------------------------------------------------------------------

class TestSchemaCompilerFindings:
    """Verify schema_compiler produces Findings for unmapped field types."""
    def test_unknown_field_type_produces_finding(self):
        from src.models.bundle_artifacts import FieldUsageEntry

        bundle = _clean_bundle(
            field_usage_report=FieldUsageReportArtifact(
                schema_version="1.0.0",
                fields=[
                    FieldUsageEntry(
                        post_type="post",
                        field_name="custom_widget",
                        source_system="core",
                        inferred_type="exotic_widget_type",
                        nullable=False,
                        cardinality="single",
                        distinct_value_count=5,
                        sample_values=["a", "b"],
                    ),
                ],
            ),
        )
        cap = _clean_cap_manifest()
        agent = SchemaCompilerAgent(gradient_client=None)
        result = _run(agent.execute({
            "bundle_manifest": bundle,
            "capability_manifest": cap,
        }))
        manifest = result.artifacts["content_model_manifest"]

        assert len(manifest.findings) >= 1
        finding = manifest.findings[0]
        _assert_valid_finding(finding)
        assert finding.stage == "schema_compiler"
        assert "exotic_widget_type" in finding.message

    def test_known_field_type_produces_no_finding(self):
        from src.models.bundle_artifacts import FieldUsageEntry

        bundle = _clean_bundle(
            field_usage_report=FieldUsageReportArtifact(
                schema_version="1.0.0",
                fields=[
                    FieldUsageEntry(
                        post_type="post",
                        field_name="title",
                        source_system="core",
                        inferred_type="text",
                        nullable=False,
                        cardinality="single",
                        distinct_value_count=10,
                        sample_values=["Hello"],
                    ),
                ],
            ),
        )
        cap = _clean_cap_manifest()
        agent = SchemaCompilerAgent(gradient_client=None)
        result = _run(agent.execute({
            "bundle_manifest": bundle,
            "capability_manifest": cap,
        }))
        manifest = result.artifacts["content_model_manifest"]
        assert len(manifest.findings) == 0

    def test_findings_accessible_via_findings_attribute(self):
        """ContentModelManifest.findings is used by _accumulate_findings."""
        from src.models.bundle_artifacts import FieldUsageEntry

        bundle = _clean_bundle(
            field_usage_report=FieldUsageReportArtifact(
                schema_version="1.0.0",
                fields=[
                    FieldUsageEntry(
                        post_type="page",
                        field_name="weird_field",
                        source_system="core",
                        inferred_type="unknown_type_xyz",
                        nullable=True,
                        cardinality="single",
                        distinct_value_count=1,
                        sample_values=[],
                    ),
                ],
            ),
        )
        cap = _clean_cap_manifest()
        agent = SchemaCompilerAgent(gradient_client=None)
        result = _run(agent.execute({
            "bundle_manifest": bundle,
            "capability_manifest": cap,
        }))
        manifest = result.artifacts["content_model_manifest"]
        assert hasattr(manifest, "findings")
        assert isinstance(manifest.findings, list)
        assert all(isinstance(f, Finding) for f in manifest.findings)

# ---------------------------------------------------------------------------
# 3. PresentationCompilerAgent — Finding production
# ---------------------------------------------------------------------------

class TestPresentationCompilerFindings:
    """Verify presentation_compiler produces Findings for unsupported constructs."""
    def test_unsupported_shortcode_produces_finding(self):
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0",
                pages=[
                    PageCompositionEntry(
                        canonical_url="https://example.com/about/",
                        template="page.php",
                        blocks=[],
                        shortcodes=[{"tag": "fancy_gallery", "source_plugin": "unsupported_plugin"}],
                        widget_placements=[],
                        forms_embedded=[],
                        plugin_components=[],
                        enqueued_assets=[],
                        content_sections=[],
                    ),
                ],
            ),
        )
        cap = _clean_cap_manifest()
        agent = PresentationCompilerAgent(gradient_client=None)
        result = _run(agent.execute({
            "bundle_manifest": bundle,
            "capability_manifest": cap,
        }))
        manifest = result.artifacts["presentation_manifest"]

        assert len(manifest.findings) >= 1
        finding = manifest.findings[0]
        _assert_valid_finding(finding)
        assert finding.stage == "presentation_compiler"
        assert "fancy_gallery" in finding.construct

    def test_unsupported_block_produces_finding(self):
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0",
                pages=[
                    PageCompositionEntry(
                        canonical_url="https://example.com/home/",
                        template="front-page.php",
                        blocks=[{"blockName": "custom-plugin/hero", "source_plugin": "unsupported_plugin"}],
                        shortcodes=[],
                        widget_placements=[],
                        forms_embedded=[],
                        plugin_components=[],
                        enqueued_assets=[],
                        content_sections=[],
                    ),
                ],
            ),
        )
        cap = _clean_cap_manifest()
        agent = PresentationCompilerAgent(gradient_client=None)
        result = _run(agent.execute({
            "bundle_manifest": bundle,
            "capability_manifest": cap,
        }))
        manifest = result.artifacts["presentation_manifest"]

        block_findings = [f for f in manifest.findings if "custom-plugin/hero" in f.construct]
        assert len(block_findings) >= 1
        _assert_valid_finding(block_findings[0])

    def test_unsupported_plugin_component_produces_finding(self):
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0",
                pages=[
                    PageCompositionEntry(
                        canonical_url="https://example.com/contact/",
                        template="page.php",
                        blocks=[],
                        shortcodes=[],
                        widget_placements=[],
                        forms_embedded=[],
                        plugin_components=[{"name": "mega-slider", "source_plugin": "unsupported_plugin"}],
                        enqueued_assets=[],
                        content_sections=[],
                    ),
                ],
            ),
        )
        cap = _clean_cap_manifest()
        agent = PresentationCompilerAgent(gradient_client=None)
        result = _run(agent.execute({
            "bundle_manifest": bundle,
            "capability_manifest": cap,
        }))
        manifest = result.artifacts["presentation_manifest"]

        comp_findings = [f for f in manifest.findings if "mega-slider" in f.construct]
        assert len(comp_findings) >= 1
        _assert_valid_finding(comp_findings[0])

    def test_core_block_produces_no_finding(self):
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0",
                pages=[
                    PageCompositionEntry(
                        canonical_url="https://example.com/",
                        template="page.php",
                        blocks=[{"blockName": "core/paragraph"}],
                        shortcodes=[],
                        widget_placements=[],
                        forms_embedded=[],
                        plugin_components=[],
                        enqueued_assets=[],
                        content_sections=[],
                    ),
                ],
            ),
        )
        cap = _clean_cap_manifest()
        agent = PresentationCompilerAgent(gradient_client=None)
        result = _run(agent.execute({
            "bundle_manifest": bundle,
            "capability_manifest": cap,
        }))
        manifest = result.artifacts["presentation_manifest"]
        assert len(manifest.findings) == 0

    def test_findings_accessible_via_findings_attribute(self):
        """PresentationManifest.findings is used by _accumulate_findings."""
        bundle = _clean_bundle(
            page_composition=PageCompositionArtifact(
                schema_version="1.0.0",
                pages=[
                    PageCompositionEntry(
                        canonical_url="https://example.com/test/",
                        template="page.php",
                        blocks=[],
                        shortcodes=[{"tag": "unsupported_sc"}],
                        widget_placements=[],
                        forms_embedded=[],
                        plugin_components=[],
                        enqueued_assets=[],
                        content_sections=[],
                    ),
                ],
            ),
        )
        cap = _clean_cap_manifest()
        agent = PresentationCompilerAgent(gradient_client=None)
        result = _run(agent.execute({
            "bundle_manifest": bundle,
            "capability_manifest": cap,
        }))
        manifest = result.artifacts["presentation_manifest"]
        assert hasattr(manifest, "findings")
        assert isinstance(manifest.findings, list)
        assert all(isinstance(f, Finding) for f in manifest.findings)

# ---------------------------------------------------------------------------
# 4. BehaviorCompilerAgent — Finding production
# ---------------------------------------------------------------------------

class TestBehaviorCompilerFindings:
    """Verify behavior_compiler produces Findings for unsupported constructs."""
    def _make_context(self, **bundle_overrides: Any) -> dict[str, Any]:
        from src.models.content_model_manifest import ContentModelManifest

        bundle = _clean_bundle(**bundle_overrides)
        cap = _clean_cap_manifest(
            capabilities=[
                Capability(
                    capability_type="integration",
                    classification="unsupported",
                    confidence=0.5,
                    source_plugin="mystery_plugin",
                ),
            ],
        )
        content_model = ContentModelManifest(
            collections=[], components=[], relations=[],
            seo_strategy=None, validation_hints=[],
        )
        pres = PresentationManifest(
            layouts=[], route_templates=[], sections=[],
            fallback_zones=[], style_tokens={},
        )
        return {
            "bundle_manifest": bundle,
            "capability_manifest": cap,
            "content_model_manifest": content_model,
            "presentation_manifest": pres,
        }

    def test_unsupported_capability_produces_finding(self):
        ctx = self._make_context()
        agent = BehaviorCompilerAgent(gradient_client=None)
        result = _run(agent.execute(ctx))
        manifest = result.artifacts["behavior_manifest"]

        assert len(manifest.unsupported_constructs) >= 1
        finding = manifest.unsupported_constructs[0]
        _assert_valid_finding(finding)
        assert finding.stage == "behavior_compiler"

    def test_dropped_integration_produces_finding(self):
        ctx = self._make_context(
            integration_manifest=IntegrationManifestArtifact(
                schema_version="1.0.0",
                integrations=[
                    IntegrationEntry(
                        integration_id="custom-api",
                        integration_type="unknown_type",
                        target="https://api.example.com",
                        business_critical=False,
                    ),
                ],
            ),
        )
        agent = BehaviorCompilerAgent(gradient_client=None)
        result = _run(agent.execute(ctx))
        manifest = result.artifacts["behavior_manifest"]

        drop_boundaries = [
            b for b in manifest.integration_boundaries if b.disposition == "drop"
        ]
        assert len(drop_boundaries) >= 1
        assert drop_boundaries[0].finding is not None
        _assert_valid_finding(drop_boundaries[0].finding)

    def test_behavior_manifest_findings_property_aggregates(self):
        """BehaviorManifest.findings property collects all sub-findings."""
        finding1 = Finding(
            severity=FindingSeverity.WARNING,
            stage="behavior_compiler",
            construct="cap:test",
            message="Unsupported",
            recommended_action="Review",
        )
        finding2 = Finding(
            severity=FindingSeverity.WARNING,
            stage="behavior_compiler",
            construct="integration:x",
            message="Dropped",
            recommended_action="Review",
        )
        manifest = BehaviorManifest(
            redirects=[],
            metadata_strategy={},
            forms_strategy=[],
            preview_rules={},
            integration_boundaries=[
                IntegrationBoundary(
                    integration_id="x",
                    disposition="drop",
                    target_system="external",
                    finding=finding2,
                ),
            ],
            unsupported_constructs=[finding1],
        )
        all_findings = manifest.findings
        assert finding1 in all_findings
        assert finding2 in all_findings
        assert len(all_findings) == 2

# ---------------------------------------------------------------------------
# 5. ParityQAAgent — Finding production
# ---------------------------------------------------------------------------

class TestParityQAFindings:
    """Verify parity_qa produces Findings for parity failures."""
    def test_low_parity_score_produces_findings(self):
        from src.models.behavior_manifest import BehaviorManifest

        bundle = _clean_bundle()
        cap = _clean_cap_manifest()
        pres = PresentationManifest(
            layouts=[], route_templates=[], sections=[],
            fallback_zones=[], style_tokens={},
        )
        behavior = BehaviorManifest(
            redirects=[], metadata_strategy={}, forms_strategy=[],
            preview_rules={}, integration_boundaries=[],
            unsupported_constructs=[],
        )
        ctx: dict[str, Any] = {
            "bundle_manifest": bundle,
            "capability_manifest": cap,
            "presentation_manifest": pres,
            "behavior_manifest": behavior,
            "parity_threshold": 0.0,  # ensure it passes the gate
        }
        agent = ParityQAAgent(gradient_client=None, threshold=0.0)
        result = _run(agent.execute(ctx))
        report = result.artifacts["parity_report"]

        # With empty data, some categories may score below 1.0
        for finding in report.findings:
            _assert_valid_finding(finding)
            assert finding.stage == "parity_qa"

# ---------------------------------------------------------------------------
# 6. ContentMigratorAgent — Finding production (via _make_entry_finding)
# ---------------------------------------------------------------------------

class TestContentMigratorFindings:
    """Verify content_migrator produces valid Findings for per-entry failures."""
    def test_make_entry_finding_has_all_fields(self):
        from src.agents.content_migrator import _make_entry_finding
        from src.models.content import WordPressContentItem

        item = WordPressContentItem(
            id=1,
            title="Test Post",
            slug="test-post",
            post_type="post",
            status="publish",
            excerpt="",
            date="2024-01-01",
            blocks=[],
            raw_html="<p>Hello</p>",
            featured_media={},
            taxonomies={},
            meta={},
            seo={},
            legacy_permalink="/test-post/",
        )
        finding = _make_entry_finding(item, "Strapi API rejected entry")
        _assert_valid_finding(finding)
        assert finding.stage == "content_migrator"
        assert "test-post" in finding.construct
        assert "Test Post" in finding.message

# ---------------------------------------------------------------------------
# 7. Orchestrator _accumulate_findings — collects from all emission patterns
# ---------------------------------------------------------------------------

class TestAccumulateFindings:
    """Verify _accumulate_findings collects findings from all agent patterns."""
    def test_collects_from_findings_attribute(self):
        """Manifests with .findings attribute (CapabilityManifest, ContentModelManifest, etc.)."""
        finding = Finding(
            severity=FindingSeverity.WARNING,
            stage="test_stage",
            construct="test:construct",
            message="Test message",
            recommended_action="Test action",
        )
        cap_manifest = _clean_cap_manifest(findings=[finding])
        result = AgentResult(
            agent_name="capability_resolution",
            artifacts={"capability_manifest": cap_manifest},
        )
        accumulated: list[Finding] = []
        context: dict[str, Any] = {}
        PipelineOrchestrator._accumulate_findings(
            "capability_resolution", result, accumulated, context,
        )
        assert finding in accumulated

    def test_collects_from_direct_finding_list(self):
        """Content migrator emits findings as a direct list in artifacts."""
        finding = Finding(
            severity=FindingSeverity.WARNING,
            stage="content_migrator",
            construct="post:test",
            message="Failed",
            recommended_action="Retry",
        )
        result = AgentResult(
            agent_name="content_migrator",
            artifacts={"findings": [finding]},
        )
        accumulated: list[Finding] = []
        context: dict[str, Any] = {}
        PipelineOrchestrator._accumulate_findings(
            "content_migrator", result, accumulated, context,
        )
        assert finding in accumulated

    def test_collects_from_behavior_manifest_findings_property(self):
        """BehaviorManifest exposes .findings property aggregating all sub-findings."""
        finding = Finding(
            severity=FindingSeverity.WARNING,
            stage="behavior_compiler",
            construct="cap:unsupported",
            message="Unsupported capability",
            recommended_action="Review",
        )
        manifest = BehaviorManifest(
            redirects=[],
            metadata_strategy={},
            forms_strategy=[],
            preview_rules={},
            integration_boundaries=[],
            unsupported_constructs=[finding],
        )
        result = AgentResult(
            agent_name="behavior_compiler",
            artifacts={"behavior_manifest": manifest},
        )
        accumulated: list[Finding] = []
        context: dict[str, Any] = {}
        PipelineOrchestrator._accumulate_findings(
            "behavior_compiler", result, accumulated, context,
        )
        assert finding in accumulated

    def test_collects_from_presentation_manifest_findings(self):
        """PresentationManifest.findings is picked up by _accumulate_findings."""
        finding = Finding(
            severity=FindingSeverity.WARNING,
            stage="presentation_compiler",
            construct="shortcode:test",
            message="Unsupported shortcode",
            recommended_action="Implement component",
        )
        manifest = PresentationManifest(
            layouts=[], route_templates=[], sections=[],
            fallback_zones=[], style_tokens={}, findings=[finding],
        )
        result = AgentResult(
            agent_name="presentation_compiler",
            artifacts={"presentation_manifest": manifest},
        )
        accumulated: list[Finding] = []
        context: dict[str, Any] = {}
        PipelineOrchestrator._accumulate_findings(
            "presentation_compiler", result, accumulated, context,
        )
        assert finding in accumulated

    def test_collects_from_content_model_manifest_findings(self):
        """ContentModelManifest.findings is picked up by _accumulate_findings."""
        finding = Finding(
            severity=FindingSeverity.INFO,
            stage="schema_compiler",
            construct="field:post.weird",
            message="Unknown field type",
            recommended_action="Review mapping",
        )
        manifest = ContentModelManifest(
            collections=[], components=[], relations=[],
            seo_strategy=None, validation_hints=[], findings=[finding],
        )
        result = AgentResult(
            agent_name="schema_compiler",
            artifacts={"content_model_manifest": manifest},
        )
        accumulated: list[Finding] = []
        context: dict[str, Any] = {}
        PipelineOrchestrator._accumulate_findings(
            "schema_compiler", result, accumulated, context,
        )
        assert finding in accumulated

    def test_collects_from_parity_report_findings(self):
        """ParityReport.findings is picked up by _accumulate_findings."""
        finding = Finding(
            severity=FindingSeverity.WARNING,
            stage="parity_qa",
            construct="route_parity",
            message="Route parity 0.80",
            recommended_action="Review routes",
        )
        report = ParityReport(
            category_scores={
                "route": 0.8, "redirect": 1.0, "metadata": 1.0,
                "media": 1.0, "menu": 1.0, "template": 1.0,
                "plugin_behavior": 1.0,
            },
            overall_score=0.97,
            findings=[finding],
            snapshot_comparisons=[],
        )
        result = AgentResult(
            agent_name="parity_qa",
            artifacts={"parity_report": report},
        )
        accumulated: list[Finding] = []
        context: dict[str, Any] = {}
        PipelineOrchestrator._accumulate_findings(
            "parity_qa", result, accumulated, context,
        )
        assert finding in accumulated
