from typing import Any

import pytest

from src.agents.base import AgentResult, BaseAgent


class ConcreteAgent(BaseAgent):
    """Minimal concrete agent for testing the abstract base."""

    async def execute(self, context: dict[str, Any]) -> AgentResult:
        return AgentResult(
            agent_name="test_agent",
            artifacts={"key": context.get("input", "none")},
            warnings=[],
            duration_seconds=1.5,
        )


class TestAgentResult:
    def test_required_fields(self):
        result = AgentResult(agent_name="a0", artifacts={"inv": {}}, warnings=["w1"], duration_seconds=2.0)
        assert result.agent_name == "a0"
        assert result.artifacts == {"inv": {}}
        assert result.warnings == ["w1"]
        assert result.duration_seconds == 2.0

    def test_defaults(self):
        result = AgentResult(agent_name="a0")
        assert result.artifacts == {}
        assert result.warnings == []
        assert result.duration_seconds == 0.0

    def test_mutable_defaults_are_independent(self):
        r1 = AgentResult(agent_name="a")
        r2 = AgentResult(agent_name="b")
        r1.artifacts["x"] = 1
        r1.warnings.append("w")
        assert r2.artifacts == {}
        assert r2.warnings == []


class TestBaseAgent:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            BaseAgent(gradient_client=object())  # type: ignore[abstract]

    def test_stores_clients(self):
        gc = object()
        kb = object()
        agent = ConcreteAgent(gradient_client=gc, kb_client=kb)
        assert agent.gradient_client is gc
        assert agent.kb_client is kb

    def test_kb_client_defaults_to_none(self):
        agent = ConcreteAgent(gradient_client=object())
        assert agent.kb_client is None

    @pytest.mark.asyncio
    async def test_execute_returns_agent_result(self):
        agent = ConcreteAgent(gradient_client=object())
        result = await agent.execute({"input": "hello"})
        assert isinstance(result, AgentResult)
        assert result.agent_name == "test_agent"
        assert result.artifacts == {"key": "hello"}
