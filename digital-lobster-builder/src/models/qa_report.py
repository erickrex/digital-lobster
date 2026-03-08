from pydantic import BaseModel

class PageCheck(BaseModel):
    url: str
    http_status: int | None
    visual_parity_score: float | None
    accessibility_issues: list[str]
    passed: bool

class CMSValidation(BaseModel):
    """CMS-specific validation results for QA."""
    strapi_content_count: int
    export_bundle_count: int
    count_match: bool
    failed_tolerance: int
    media_urls_checked: int
    media_urls_valid: int

class QAReport(BaseModel):
    build_success: bool
    build_errors: list[str]
    pages_checked: list[PageCheck]
    total_passed: int
    total_failed: int
    warnings: list[str]
    cms_validation: CMSValidation | None = None
