"""Pipeline error types for the orchestrator.

AgentError is raised when an individual agent fails during execution.
PipelineError is raised for pipeline-level failures (e.g., missing bundle, invalid config).
"""


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
