from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from src.agents.manifest_review import (
    ManifestReviewAgent,
    _build_manifest_review_system_prompt,
    _build_manifest_review_user_prompt,
)
from src.models.behavior_manifest import BehaviorManifest, IntegrationBoundary
from src.models.bundle_artifacts import (
    ContentRelationshipsArtifact,
    EditorialWorkflowsArtifact,
    FieldUsageReportArtifact,
    IntegrationManifestArtifact,
    PageCompositionArtifact,
    PluginInstancesArtifact,
    SearchConfigArtifact,
    SeoFullArtifact,
)
from src.models.bundle_manifest import BundleManifest
from src.models.capability_manifest import Capability, CapabilityManifest
from src.models.content_model_manifest import ContentModelManifest, StrapiCollection
from src.models.presentation_manifest import (
    FallbackZone,
    PresentationManifest,
)


def _run(coro):
    return asyncio.run(coro)


def _clean_bundle() -> BundleManifest:
    return BundleManifest(
        schema_version="1.0.0",
        site_url="https://example.com",
        site_name="Example",
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
            statuses_in_use=["publish"],
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


def _build_context() -> dict:
    capability_manifest = CapabilityManifest(
        capabilities=[
            Capability(
                capability_type="content_model",
                source_plugin="legacy-cpt",
                classification="unsupported",
                confidence=0.65,
                details={"post_type": "resource"},
            ),
            Capability(
                capability_type="template",
                source_plugin="builder",
                classification="unsupported",
                confidence=0.7,
                details={"template": "landing"},
            ),
            Capability(
                capability_type="integration",
                source_plugin=None,
                classification="unsupported",
                confidence=0.6,
                details={"integration_id": "crm-sync"},
            ),
        ],
        findings=[],
        content_model_capabilities=[
            Capability(
                capability_type="content_model",
                source_plugin="legacy-cpt",
                classification="unsupported",
                confidence=0.65,
                details={"post_type": "resource"},
            )
        ],
        presentation_capabilities=[
            Capability(
                capability_type="template",
                source_plugin="builder",
                classification="unsupported",
                confidence=0.7,
                details={"template": "landing"},
            )
        ],
        behavior_capabilities=[
            Capability(
                capability_type="integration",
                source_plugin=None,
                classification="unsupported",
                confidence=0.6,
                details={"integration_id": "crm-sync"},
            )
        ],
    )

    content_model_manifest = ContentModelManifest(
        collections=[
            StrapiCollection(
                display_name="Resource",
                singular_name="resource",
                plural_name="resources",
                api_id="resource",
                fields=[],
                components=[],
                source_post_type="resource",
            )
        ],
        components=[],
        relations=[],
        validation_hints=[],
        findings=[],
    )

    presentation_manifest = PresentationManifest(
        layouts=[],
        route_templates=[],
        sections=[],
        fallback_zones=[
            FallbackZone(
                page_url="/landing",
                zone_name="hero",
                raw_html="<div>legacy hero</div>",
                reason="page builder fragment",
            )
        ],
        findings=[],
    )

    behavior_manifest = BehaviorManifest(
        redirects=[],
        metadata_strategy={},
        forms_strategy=[],
        preview_rules={},
        search_strategy=None,
        integration_boundaries=[
            IntegrationBoundary(
                integration_id="crm-sync",
                disposition="drop",
                target_system="external",
            )
        ],
        unsupported_constructs=[],
    )

    return {
        "bundle_manifest": _clean_bundle(),
        "capability_manifest": capability_manifest,
        "content_model_manifest": content_model_manifest,
        "presentation_manifest": presentation_manifest,
        "behavior_manifest": behavior_manifest,
    }


class TestManifestReviewAgent:
    def test_manifest_review_prompt_has_additive_guardrails(self) -> None:
        system_prompt = _build_manifest_review_system_prompt()
        user_prompt = _build_manifest_review_user_prompt(
            "https://example.com",
            "schema",
            [{"construct": "collection:resource", "evidence_refs": ["collection:resource"]}],
        )
        assert "non-destructive" in system_prompt
        assert "Cite evidence_refs only from the supplied candidates" in system_prompt
        assert '"prefer_additive_changes": true' in user_prompt

    def test_returns_visible_reports_without_model(self) -> None:
        agent = ManifestReviewAgent(gradient_client=None)
        result = _run(agent.execute(_build_context()))

        assert "schema_enrichment_report" in result.artifacts
        assert "presentation_risk_report" in result.artifacts
        assert "behavior_decision_log" in result.artifacts
        assert "ai_decision_metrics" in result.artifacts

        schema_report = result.artifacts["schema_enrichment_report"]
        presentation_report = result.artifacts["presentation_risk_report"]
        behavior_report = result.artifacts["behavior_decision_log"]
        metrics = result.artifacts["ai_decision_metrics"]

        assert schema_report.ai_review_requested is True
        assert schema_report.ai_review_completed is False
        assert presentation_report.reviewed_items >= 1
        assert behavior_report.reviewed_items >= 1
        assert metrics.manifest_review_requested is True
        assert metrics.manifest_review_completed is False

    def test_uses_structured_model_review_when_available(self) -> None:
        gradient_client = MagicMock()
        gradient_client.complete_structured = AsyncMock(
            side_effect=[
                {
                    "recommendations": [
                        {
                            "construct": "collection:resource",
                            "summary": "Add explicit fields for the resource collection",
                            "rationale": "The collection is currently empty",
                            "recommendation": "Map at least title and slug before generation",
                            "evidence_refs": ["collection:resource"],
                            "confidence": 0.9,
                        }
                    ]
                },
                {
                    "recommendations": [
                        {
                            "construct": "fallback:/landing#hero",
                            "summary": "Replace the hero fallback zone",
                            "rationale": "The page builder fragment is not componentized",
                            "recommendation": "Create a dedicated Hero.astro section",
                            "evidence_refs": ["/landing", "hero"],
                            "confidence": 0.88,
                        }
                    ]
                },
                {
                    "recommendations": [
                        {
                            "construct": "integration:crm-sync",
                            "summary": "Revisit the dropped CRM sync",
                            "rationale": "Dropping it will regress lead routing",
                            "recommendation": "Model it as a queued webhook handoff",
                            "evidence_refs": ["crm-sync"],
                            "confidence": 0.91,
                        }
                    ]
                },
            ]
        )
        agent = ManifestReviewAgent(gradient_client=gradient_client)
        result = _run(agent.execute(_build_context()))

        assert gradient_client.complete_structured.await_count == 3
        first_call = gradient_client.complete_structured.await_args_list[0]
        messages = first_call.kwargs["messages"]
        assert "non-destructive" in messages[0]["content"]
        assert '"require_candidate_backed_evidence_refs": true' in messages[1]["content"]
        assert result.artifacts["schema_enrichment_report"].ai_review_completed is True
        assert result.artifacts["presentation_risk_report"].ai_review_completed is True
        assert result.artifacts["behavior_decision_log"].ai_review_completed is True
        assert (
            result.artifacts["behavior_decision_log"].recommendations[0].construct
            == "integration:crm-sync"
        )
