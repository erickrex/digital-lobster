from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from .finding import Finding

class SnapshotComparison(BaseModel):
    """Comparison of a generated page against its original snapshot."""
    page_url: str
    visual_parity_score: float = Field(ge=0.0, le=1.0)
    content_match: bool
    differences: list[str] = Field(default_factory=list)

PARITY_CATEGORIES: set[str] = {
    "route",
    "redirect",
    "metadata",
    "media",
    "menu",
    "template",
    "plugin_behavior",
}

class ParityReport(BaseModel):
    """Machine-readable post-build report scoring migration parity."""
    category_scores: dict[str, float]  # 7 categories, each 0.0-1.0
    overall_score: float = Field(ge=0.0, le=1.0)
    findings: list[Finding] = Field(default_factory=list)
    snapshot_comparisons: list[SnapshotComparison] = Field(default_factory=list)
    plugin_assertions: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)

    @field_validator("category_scores")
    @classmethod
    def _validate_category_scores(cls, v: dict[str, float]) -> dict[str, float]:
        for key, score in v.items():
            if not 0.0 <= score <= 1.0:
                raise ValueError(
                    f"Category score for '{key}' must be between 0.0 and 1.0, got {score}"
                )
        return v
