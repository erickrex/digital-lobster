class AgentError(Exception):
    """Raised when an individual agent fails during pipeline execution."""
    def __init__(self, agent_name: str, message: str, original_error: Exception | None = None) -> None:
        self.agent_name = agent_name
        self.message = message
        self.original_error = original_error
        super().__init__(f"Agent '{agent_name}' failed: {message}")

class PipelineError(Exception):
    """Raised for pipeline-level failures (e.g., missing bundle, invalid config)."""
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)

class BundleValidationError(AgentError):
    """Raised when the export bundle fails CMS schema validation.

    Carries structured details about missing artifacts or validation failures
    so the caller can present actionable diagnostics.
    """
    def __init__(
        self,
        message: str,
        missing_artifacts: list[str] | None = None,
        validation_failures: list[dict[str, str]] | None = None,
    ) -> None:
        self.missing_artifacts = missing_artifacts or []
        self.validation_failures = validation_failures or []
        super().__init__(agent_name="blueprint_intake", message=message)

class QualificationError(AgentError):
    """Raised when a site fails qualification checks.

    Carries the ReadinessReport (qualified=False) and the list of findings
    that caused disqualification so the caller can present actionable diagnostics.
    """
    def __init__(
        self,
        findings: list,
        readiness_report: object | None = None,
    ) -> None:
        from src.models.finding import Finding

        self.findings: list[Finding] = findings
        self.readiness_report = readiness_report
        summary = ", ".join(f.construct for f in findings[:5])
        super().__init__(
            agent_name="qualification",
            message=f"Site failed qualification: {summary}",
        )

class CompilationError(AgentError):
    """Raised when a compilation stage produces critical findings.

    Carries the stage name and the list of findings that caused the abort
    so the caller can present actionable diagnostics.
    """
    def __init__(
        self,
        stage_name: str,
        findings: list,
    ) -> None:
        from src.models.finding import Finding

        self.stage_name = stage_name
        self.findings: list[Finding] = findings
        summary = ", ".join(f.construct for f in findings[:5])
        super().__init__(
            agent_name=stage_name,
            message=f"Compilation failed at '{stage_name}': {summary}",
        )

class ParityGateError(AgentError):
    """Raised when the overall parity score falls below the configured threshold.

    Carries the full ParityReport so the caller can inspect category-level
    scores and individual findings.
    """
    def __init__(self, parity_report: object) -> None:
        from src.models.parity_report import ParityReport

        self.parity_report: ParityReport = parity_report  # type: ignore[assignment]
        super().__init__(
            agent_name="parity_qa",
            message=(
                f"Parity score {getattr(parity_report, 'overall_score', '?'):.2f} "
                "below threshold — deployment blocked"
            ),
        )

