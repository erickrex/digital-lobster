"""Base agent interface for the multi-agent pipeline.

Every agent implements BaseAgent and returns an AgentResult from execute().
The Orchestrator calls execute() on each agent in sequence, passing
accumulated pipeline context.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentResult:
    """Result returned by every agent after execution."""

    agent_name: str
    artifacts: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


class BaseAgent(ABC):
    """Abstract base class for all pipeline agents."""

    def __init__(self, gradient_client: Any, kb_client: Any = None) -> None:
        self.gradient_client = gradient_client
        self.kb_client = kb_client

    @abstractmethod
    async def execute(self, context: dict[str, Any]) -> AgentResult:
        """Execute the agent with accumulated pipeline context."""
        ...
