from __future__ import annotations

import warnings

from pydantic import BaseModel, Field

from .finding import Finding

warnings.filterwarnings(
    "ignore",
    message='Field name "construct" in',
    category=UserWarning,
)


class CapabilityReviewDecision(BaseModel):
    """A single AI-assisted classification review decision."""

    construct: str
    capability_type: str
    source_plugin: str | None = None
    original_classification: str
    final_classification: str
    original_confidence: float = Field(ge=0.0, le=1.0)
    final_confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    recommended_action: str
    evidence_refs: list[str] = Field(default_factory=list)
    applied: bool = False


class CapabilityReviewReport(BaseModel):
    """Review artifact emitted by capability resolution for ambiguous constructs."""

    ai_review_requested: bool = False
    ai_review_completed: bool = False
    reviewed_count: int = 0
    applied_count: int = 0
    skipped_count: int = 0
    decisions: list[CapabilityReviewDecision] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)


class ReviewRecommendation(BaseModel):
    """A single recommendation produced by the manifest review stage."""

    construct: str
    summary: str
    rationale: str
    recommendation: str
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class ReviewReport(BaseModel):
    """Review-only report for one deterministic manifest area."""

    review_area: str
    ai_review_requested: bool = False
    ai_review_completed: bool = False
    reviewed_items: int = 0
    recommendations: list[ReviewRecommendation] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)


class AIDecisionMetrics(BaseModel):
    """Visible metrics summarising AI-assisted review activity."""

    capability_review_requested: bool = False
    capability_review_completed: bool = False
    capabilities_reviewed: int = 0
    capability_decisions_applied: int = 0
    capability_decisions_skipped: int = 0
    manifest_review_requested: bool = False
    manifest_review_completed: bool = False
    schema_recommendations: int = 0
    presentation_recommendations: int = 0
    behavior_recommendations: int = 0
