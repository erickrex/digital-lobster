from pydantic import BaseModel

from .finding import Finding


class ReadinessReport(BaseModel):
    """Structured report explaining why a site passed or failed qualification."""

    qualified: bool
    findings: list[Finding]
    checked_criteria: list[str]
