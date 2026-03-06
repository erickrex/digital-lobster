"""Pipeline run state model.

Tracks the lifecycle of a single pipeline run including status transitions,
agent execution tracking, artifact accumulation, and error recording.
"""

import traceback
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from src.utils.scrubbing import scrub_credentials


class PipelineRunState(BaseModel):
    """Tracks the full state of a pipeline run."""

    run_id: str
    status: str = "pending"  # "pending", "running", "completed", "failed"
    bundle_key: str
    kb_id: str | None = None
    current_agent: str | None = None
    artifacts: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    error: dict | None = None  # {agent, message, traceback}
    started_at: str = ""
    completed_at: str | None = None
    agent_durations: dict[str, float] = Field(default_factory=dict)
    cms_mode: bool = False
    live_site_url: str | None = None
    strapi_admin_url: str | None = None
    deployment_report: dict | None = None

    @classmethod
    def create(cls, run_id: str, bundle_key: str) -> "PipelineRunState":
        """Factory method to initialize a new pipeline run state."""
        return cls(
            run_id=run_id,
            bundle_key=bundle_key,
            started_at=datetime.now(timezone.utc).isoformat(),
        )

    def mark_running(self) -> None:
        """Transition status to running."""
        self.status = "running"

    def mark_agent_started(self, agent_name: str) -> None:
        """Record that an agent has started execution."""
        self.current_agent = agent_name

    def mark_agent_completed(self, agent_name: str, duration: float, artifacts: dict[str, Any]) -> None:
        """Record agent completion with duration and output artifacts."""
        self.agent_durations[agent_name] = duration
        self.artifacts.update(artifacts)
        self.current_agent = None

    def mark_failed(self, agent_name: str, error: Exception) -> None:
        """Record pipeline failure from an agent error."""
        self.status = "failed"
        self.current_agent = None
        self.error = {
            "agent": agent_name,
            "message": str(error),
            "traceback": traceback.format_exception(type(error), error, error.__traceback__),
        }
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def mark_completed(self) -> None:
        """Transition status to completed."""
        self.status = "completed"
        self.current_agent = None
        self.completed_at = datetime.now(timezone.utc).isoformat()

    def to_safe_dict(self) -> dict[str, Any]:
        """Return a dict with credentials scrubbed from artifacts, deployment_report, and error."""
        data = self.model_dump()
        for key in ("artifacts", "deployment_report", "error"):
            if data.get(key) is not None:
                data[key] = scrub_credentials(data[key])
        return data
