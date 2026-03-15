from __future__ import annotations

import json
import logging
import time
import warnings
from typing import Any

from pydantic import BaseModel, Field

from src.agents.base import AgentResult, BaseAgent
from src.models.ai_review import (
    AIDecisionMetrics,
    CapabilityReviewReport,
    ReviewRecommendation,
    ReviewReport,
)
from src.models.behavior_manifest import BehaviorManifest
from src.models.bundle_manifest import BundleManifest
from src.models.capability_manifest import CapabilityManifest
from src.models.content_model_manifest import ContentModelManifest
from src.models.presentation_manifest import PresentationManifest
from src.pipeline_context import (
    extract_behavior_manifest,
    extract_bundle_manifest,
    extract_capability_manifest,
    extract_content_model_manifest,
    extract_presentation_manifest,
)

logger = logging.getLogger(__name__)

warnings.filterwarnings(
    "ignore",
    message='Field name "construct" in',
    category=UserWarning,
)

MAX_CANDIDATES_PER_AREA = 6


class _ReviewRecommendationPayload(BaseModel):
    construct: str
    summary: str
    rationale: str
    recommendation: str
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class _ReviewResponse(BaseModel):
    recommendations: list[_ReviewRecommendationPayload] = Field(default_factory=list)


class ManifestReviewAgent(BaseAgent):
    """Review deterministic manifests and emit visible AI guidance artifacts."""

    async def execute(self, context: dict[str, Any]) -> AgentResult:
        start = time.monotonic()
        warnings: list[str] = []

        capability_manifest = extract_capability_manifest(context)
        bundle_manifest = extract_bundle_manifest(context)
        content_model_manifest = extract_content_model_manifest(context)
        presentation_manifest = extract_presentation_manifest(context)
        behavior_manifest = extract_behavior_manifest(context)

        schema_candidates = self._build_schema_candidates(
            capability_manifest,
            content_model_manifest,
        )
        presentation_candidates = self._build_presentation_candidates(
            capability_manifest,
            presentation_manifest,
        )
        behavior_candidates = self._build_behavior_candidates(
            capability_manifest,
            behavior_manifest,
        )

        schema_report = await self._review_area(
            "schema",
            bundle_manifest,
            schema_candidates,
            warnings,
        )
        presentation_report = await self._review_area(
            "presentation",
            bundle_manifest,
            presentation_candidates,
            warnings,
        )
        behavior_report = await self._review_area(
            "behavior",
            bundle_manifest,
            behavior_candidates,
            warnings,
        )

        capability_review = self._coerce_capability_review_report(
            context.get("capability_review_report")
        )
        metrics = AIDecisionMetrics(
            capability_review_requested=capability_review.ai_review_requested,
            capability_review_completed=capability_review.ai_review_completed,
            capabilities_reviewed=capability_review.reviewed_count,
            capability_decisions_applied=capability_review.applied_count,
            capability_decisions_skipped=capability_review.skipped_count,
            manifest_review_requested=any(
                report.ai_review_requested
                for report in (schema_report, presentation_report, behavior_report)
            ),
            manifest_review_completed=all(
                (not report.ai_review_requested) or report.ai_review_completed
                for report in (schema_report, presentation_report, behavior_report)
            ),
            schema_recommendations=len(schema_report.recommendations),
            presentation_recommendations=len(presentation_report.recommendations),
            behavior_recommendations=len(behavior_report.recommendations),
        )

        return AgentResult(
            agent_name="manifest_review",
            artifacts={
                "schema_enrichment_report": schema_report,
                "presentation_risk_report": presentation_report,
                "behavior_decision_log": behavior_report,
                "ai_decision_metrics": metrics,
            },
            warnings=warnings,
            duration_seconds=time.monotonic() - start,
        )

    async def _review_area(
        self,
        review_area: str,
        bundle_manifest: BundleManifest,
        candidates: list[dict[str, Any]],
        warnings: list[str],
    ) -> ReviewReport:
        """Run an optional structured AI review over one manifest area."""

        report = ReviewReport(
            review_area=review_area,
            ai_review_requested=bool(candidates),
            ai_review_completed=False,
            reviewed_items=len(candidates),
            recommendations=[
                ReviewRecommendation(
                    construct=item["construct"],
                    summary=item["summary"],
                    rationale=item["summary"],
                    recommendation=item["recommendation"],
                    evidence_refs=item.get("evidence_refs", []),
                    confidence=0.55,
                )
                for item in candidates[:3]
            ],
        )
        if not candidates or self.gradient_client is None:
            return report

        messages = [
            {
                "role": "system",
                "content": (
                    "You are reviewing a deterministic WordPress migration manifest. "
                    "Return focused, implementation-ready recommendations only for "
                    "the riskiest issues. Do not restate the input."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "site_url": bundle_manifest.site_url,
                        "review_area": review_area,
                        "candidates": candidates,
                        "instructions": {
                            "max_recommendations": 4,
                            "goal": (
                                "prioritize suggestions that reduce manual migration "
                                "risk without rewriting deterministic manifests"
                            ),
                        },
                    },
                    indent=2,
                ),
            },
        ]

        try:
            payload = await self.gradient_client.complete_structured(
                messages=messages,
                schema=_ReviewResponse,
            )
            recommendations = [
                ReviewRecommendation.model_validate(item)
                for item in payload.get("recommendations", [])
            ]
            if recommendations:
                report.recommendations = recommendations
            report.ai_review_completed = True
        except Exception as exc:
            warnings.append(f"{review_area} AI review failed: {exc}")
            logger.warning("%s AI review failed: %s", review_area, exc)

        return report

    @staticmethod
    def _build_schema_candidates(
        capability_manifest: CapabilityManifest,
        content_model_manifest: ContentModelManifest,
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []

        for finding in content_model_manifest.findings:
            candidates.append({
                "construct": finding.construct,
                "summary": finding.message,
                "recommendation": finding.recommended_action,
                "evidence_refs": [finding.construct],
            })

        for cap in capability_manifest.content_model_capabilities:
            if cap.classification == "strapi_native" and cap.confidence >= 0.8:
                continue
            candidates.append({
                "construct": _capability_construct(cap),
                "summary": (
                    f"Content-model capability '{cap.capability_type}' from "
                    f"{cap.source_plugin or 'core'} remains {cap.classification} "
                    f"at confidence {cap.confidence:.2f}"
                ),
                "recommendation": "Verify target collection/component strategy before generation",
                "evidence_refs": _capability_evidence_refs(cap),
            })

        for collection in content_model_manifest.collections:
            if collection.fields:
                continue
            candidates.append({
                "construct": f"collection:{collection.api_id}",
                "summary": f"Collection '{collection.api_id}' has no mapped fields",
                "recommendation": "Validate whether this post type should remain in scope",
                "evidence_refs": [f"collection:{collection.api_id}"],
            })

        return _dedupe_candidates(candidates, MAX_CANDIDATES_PER_AREA)

    @staticmethod
    def _build_presentation_candidates(
        capability_manifest: CapabilityManifest,
        presentation_manifest: PresentationManifest,
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []

        for fallback in presentation_manifest.fallback_zones:
            candidates.append({
                "construct": f"fallback:{fallback.page_url}#{fallback.zone_name}",
                "summary": (
                    f"Fallback zone '{fallback.zone_name}' is rendering raw HTML "
                    f"for {fallback.page_url}: {fallback.reason}"
                ),
                "recommendation": "Replace fallback HTML with a typed Astro section where possible",
                "evidence_refs": [fallback.page_url, fallback.zone_name],
            })

        for finding in presentation_manifest.findings:
            candidates.append({
                "construct": finding.construct,
                "summary": finding.message,
                "recommendation": finding.recommended_action,
                "evidence_refs": [finding.construct],
            })

        for cap in capability_manifest.presentation_capabilities:
            if cap.classification == "astro_runtime" and cap.confidence >= 0.8:
                continue
            candidates.append({
                "construct": _capability_construct(cap),
                "summary": (
                    f"Presentation capability '{cap.capability_type}' is still "
                    f"classified as {cap.classification} at confidence {cap.confidence:.2f}"
                ),
                "recommendation": "Review section/component mapping before scaffold generation",
                "evidence_refs": _capability_evidence_refs(cap),
            })

        return _dedupe_candidates(candidates, MAX_CANDIDATES_PER_AREA)

    @staticmethod
    def _build_behavior_candidates(
        capability_manifest: CapabilityManifest,
        behavior_manifest: BehaviorManifest,
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []

        for finding in behavior_manifest.unsupported_constructs:
            candidates.append({
                "construct": finding.construct,
                "summary": finding.message,
                "recommendation": finding.recommended_action,
                "evidence_refs": [finding.construct],
            })

        for boundary in behavior_manifest.integration_boundaries:
            if boundary.disposition not in {"drop", "proxy"}:
                continue
            candidates.append({
                "construct": f"integration:{boundary.integration_id}",
                "summary": (
                    f"Integration '{boundary.integration_id}' is marked for "
                    f"{boundary.disposition}"
                ),
                "recommendation": "Confirm the runtime boundary and ownership before deployment",
                "evidence_refs": [boundary.integration_id, boundary.target_system],
            })

        for cap in capability_manifest.behavior_capabilities:
            if cap.classification == "astro_runtime" and cap.confidence >= 0.8:
                continue
            candidates.append({
                "construct": _capability_construct(cap),
                "summary": (
                    f"Behavior capability '{cap.capability_type}' remains "
                    f"{cap.classification} at confidence {cap.confidence:.2f}"
                ),
                "recommendation": "Validate the behavior boundary and manual follow-up path",
                "evidence_refs": _capability_evidence_refs(cap),
            })

        return _dedupe_candidates(candidates, MAX_CANDIDATES_PER_AREA)

    @staticmethod
    def _coerce_capability_review_report(raw: Any) -> CapabilityReviewReport:
        if raw is None:
            return CapabilityReviewReport()
        if isinstance(raw, CapabilityReviewReport):
            return raw
        return CapabilityReviewReport.model_validate(raw)


def _capability_construct(capability: Any) -> str:
    details = getattr(capability, "details", {}) or {}
    for key in (
        "integration_id",
        "tag",
        "form_id",
        "hook",
        "template",
        "canonical_url",
        "table_name",
        "field_name",
        "source",
    ):
        value = details.get(key)
        if value:
            return f"{capability.capability_type}:{value}"
    return f"{capability.capability_type}:{capability.source_plugin or 'core'}"


def _capability_evidence_refs(capability: Any) -> list[str]:
    refs = [_capability_construct(capability)]
    details = getattr(capability, "details", {}) or {}
    for key in ("integration_id", "form_id", "tag", "template", "canonical_url"):
        value = details.get(key)
        if value:
            refs.append(str(value))
    return refs


def _dedupe_candidates(
    candidates: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in candidates:
        construct = str(item.get("construct", "")).strip()
        if not construct or construct in seen:
            continue
        seen.add(construct)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return deduped
