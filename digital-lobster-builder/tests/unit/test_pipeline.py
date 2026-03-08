from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.base import AgentResult, BaseAgent
from src.gradient.tracing import Tracer
from src.orchestrator.pipeline import PipelineOrchestrator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_agent(
    name: str,
    artifacts: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    duration: float = 0.1,
    side_effect: Exception | None = None,
) -> BaseAgent:
    """Create a mock agent that returns a predetermined AgentResult."""
    agent = AsyncMock(spec=BaseAgent)

    if side_effect:
        agent.execute = AsyncMock(side_effect=side_effect)
    else:
        result = AgentResult(
            agent_name=name,
            artifacts=artifacts or {},
            warnings=warnings or [],
            duration_seconds=duration,
        )
        agent.execute = AsyncMock(return_value=result)

    return agent

def _make_orchestrator(
    agents: list[tuple[str, BaseAgent]],
    spaces_client: AsyncMock | None = None,
    tracer: Tracer | None = None,
    artifacts_bucket: str = "test-artifacts",
) -> PipelineOrchestrator:
    """Build a PipelineOrchestrator with injected mock agents."""
    gradient_client = MagicMock()
    kb_client = MagicMock()
    sc = spaces_client or AsyncMock()
    if not hasattr(sc, "upload") or not callable(getattr(sc, "upload", None)):
        sc.upload = AsyncMock()
    tr = tracer or Tracer(run_id="test-run")

    orch = PipelineOrchestrator(
        gradient_client=gradient_client,
        kb_client=kb_client,
        spaces_client=sc,
        tracer=tr,
        artifacts_bucket=artifacts_bucket,
    )
    # Patch _build_agents to return our mock agents
    orch._build_agents = lambda **_kw: agents  # type: ignore[assignment]
    return orch

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSequentialExecution:
    """Agents are called in the correct fixed order."""
    async def test_agents_called_in_order(self) -> None:
        call_order: list[str] = []
        names = [
            "blueprint_intake", "prd_lite", "modeling",
            "theming", "scaffold", "importer", "qa",
        ]

        agents: list[tuple[str, BaseAgent]] = []
        for n in names:

            async def _exec(ctx, _n=n):
                call_order.append(_n)
                return AgentResult(
                    agent_name=_n,
                    artifacts={f"{_n}_out": f"data_{_n}"},
                )

            a = _make_mock_agent(n)
            a.execute = AsyncMock(side_effect=_exec)
            agents.append((n, a))

        orch = _make_orchestrator(agents)
        state = await orch.run("bundle.zip", "run-001")

        assert call_order == names
        assert state.status == "completed"

class TestAgentConstruction:
    """Real agent construction receives required dependencies."""
    def test_blueprint_agent_receives_spaces_and_ingestion_bucket(self) -> None:
        gradient = MagicMock()
        kb = MagicMock()
        spaces = AsyncMock()
        tracer = Tracer(run_id="seed")

        orch = PipelineOrchestrator(
            gradient_client=gradient,
            kb_client=kb,
            spaces_client=spaces,
            tracer=tracer,
            artifacts_bucket="artifacts",
            ingestion_bucket="ingestion",
        )

        agents = orch._build_agents()
        blueprint = agents[0][1]

        assert agents[0][0] == "blueprint_intake"
        assert getattr(blueprint, "spaces_client") is spaces
        assert getattr(blueprint, "ingestion_bucket") == "ingestion"

class TestKbCleanup:
    """Knowledge Bases are cleaned up after pipeline runs."""
    async def test_kb_deleted_when_kb_ref_exists(self) -> None:
        a0 = _make_mock_agent("a0", artifacts={"kb_ref": "kb-123"})
        orch = _make_orchestrator([("a0", a0)])
        orch._kb_client.delete = AsyncMock()

        state = await orch.run("bundle.zip", "run-kb")

        assert state.status == "completed"
        orch._kb_client.delete.assert_awaited_once_with("kb-123")

class _RecordingBackend:
    def __init__(self) -> None:
        self.sent = []

    async def send_span(self, span) -> None:
        self.sent.append(span)

class TestTracingRunIdentity:
    """Spans should use the pipeline run_id, not constructor seed IDs."""
    async def test_span_run_id_matches_current_pipeline_run(self) -> None:
        backend = _RecordingBackend()
        seed_tracer = Tracer(run_id="seed-run", backend=backend)

        a0 = _make_mock_agent("a0")
        orch = _make_orchestrator([("a0", a0)], tracer=seed_tracer)
        await orch.run("bundle.zip", "run-actual")

        assert len(backend.sent) == 1
        assert backend.sent[0].run_id == "run-actual"

class TestArtifactPersistenceFiltering:
    """Transient context artifacts should not be persisted or uploaded."""
    async def test_non_persisted_artifacts_are_filtered(self) -> None:
        spaces = AsyncMock()
        spaces.upload = AsyncMock()
        a0 = _make_mock_agent(
            "a0",
            artifacts={
                "export_bundle": {"theme/style.css": "x"},
                "content_items": [{"id": 1}],
                "prd_md": "# PRD",
            },
        )
        orch = _make_orchestrator([("a0", a0)], spaces_client=spaces)
        state = await orch.run("bundle.zip", "run-filter")

        assert state.status == "completed"
        assert "prd_md" in state.artifacts
        assert "export_bundle" not in state.artifacts
        assert "content_items" not in state.artifacts

        keys = [call.args[1] for call in spaces.upload.call_args_list]
        assert "run-filter/prd_md" in keys
        assert "run-filter/export_bundle" not in keys

    async def test_sensitive_and_internal_artifacts_are_not_persisted(self) -> None:
        spaces = AsyncMock()
        spaces.upload = AsyncMock()
        a0 = _make_mock_agent(
            "a0",
            artifacts={
                "inventory": {"site_name": "Site"},
                "strapi_api_token": "tok-secret",
                "admin_credentials": {"email": "admin@example.com"},
                "ssh_connection_string": "root@1.2.3.4",
                "kb_ref": "kb-123",
                "content_type_map": {"posts": "api::post.post"},
            },
        )
        orch = _make_orchestrator([("a0", a0)], spaces_client=spaces)

        state = await orch.run("bundle.zip", "run-sensitive")

        assert state.status == "completed"
        assert state.artifacts == {"inventory": {"site_name": "Site"}}

        keys = [call.args[1] for call in spaces.upload.call_args_list]
        assert keys == ["run-sensitive/inventory"]

class TestArtifactAccumulation:
    """Each agent receives accumulated artifacts from all prior agents."""
    async def test_context_accumulates_across_agents(self) -> None:
        received_contexts: list[dict] = []

        specs = [
            ("a0", "inv", "inventory_data"),
            ("a1", "prd", "prd_data"),
            ("a2", "model", "model_data"),
        ]

        agents: list[tuple[str, BaseAgent]] = []
        for name, key, val in specs:

            async def _exec(ctx, _n=name, _k=key, _v=val):
                received_contexts.append(dict(ctx))
                return AgentResult(agent_name=_n, artifacts={_k: _v})

            a = _make_mock_agent(name)
            a.execute = AsyncMock(side_effect=_exec)
            agents.append((name, a))

        orch = _make_orchestrator(agents)
        await orch.run("bundle.zip", "run-002")

        # First agent sees only seed context keys
        assert received_contexts[0]["bundle_key"] == "bundle.zip"
        assert received_contexts[0]["run_id"] == "run-002"
        assert received_contexts[0]["cms_mode"] is False
        assert "inv" not in received_contexts[0]

        # Second agent sees bundle_key + first agent's artifact
        assert received_contexts[1]["inv"] == "inventory_data"
        assert "prd" not in received_contexts[1]

        # Third agent sees all prior artifacts
        assert received_contexts[2]["inv"] == "inventory_data"
        assert received_contexts[2]["prd"] == "prd_data"

class TestPipelineHaltOnFailure:
    """Pipeline halts immediately when an agent fails."""
    async def test_halts_on_agent_failure(self) -> None:
        call_order: list[str] = []

        a0 = _make_mock_agent("a0")

        async def _ok_a0(ctx):
            call_order.append("a0")
            return AgentResult(agent_name="a0", artifacts={})

        a0.execute = AsyncMock(side_effect=_ok_a0)

        a1 = _make_mock_agent("a1", side_effect=RuntimeError("LLM timeout"))

        a2 = _make_mock_agent("a2")

        async def _ok_a2(ctx):
            call_order.append("a2")
            return AgentResult(agent_name="a2", artifacts={})

        a2.execute = AsyncMock(side_effect=_ok_a2)

        agents = [("a0", a0), ("a1", a1), ("a2", a2)]
        orch = _make_orchestrator(agents)
        state = await orch.run("bundle.zip", "run-003")

        assert state.status == "failed"
        # a2 should never have been called
        assert "a2" not in call_order

    async def test_error_recorded_in_state(self) -> None:
        a0 = _make_mock_agent("a0", artifacts={"x": 1})
        a1 = _make_mock_agent("a1", side_effect=ValueError("bad data"))

        agents = [("a0", a0), ("a1", a1)]
        orch = _make_orchestrator(agents)
        state = await orch.run("bundle.zip", "run-004")

        assert state.status == "failed"
        assert state.error is not None
        assert state.error["agent"] == "a1"
        assert "bad data" in state.error["message"]
        assert state.error["traceback"] is not None

class TestWarningsAccumulation:
    """Warnings from all agents are accumulated in the final state."""
    async def test_warnings_accumulated(self) -> None:
        a0 = _make_mock_agent("a0", warnings=["warn1", "warn2"])
        a1 = _make_mock_agent("a1", warnings=["warn3"])
        a2 = _make_mock_agent("a2", warnings=[])

        agents = [("a0", a0), ("a1", a1), ("a2", a2)]
        orch = _make_orchestrator(agents)
        state = await orch.run("bundle.zip", "run-005")

        assert state.warnings == ["warn1", "warn2", "warn3"]
        assert state.status == "completed"

class TestPerAgentDurations:
    """Per-agent durations are recorded in the state."""
    async def test_durations_recorded(self) -> None:
        a0 = _make_mock_agent("a0", duration=1.5)
        a1 = _make_mock_agent("a1", duration=2.3)

        agents = [("a0", a0), ("a1", a1)]
        orch = _make_orchestrator(agents)
        state = await orch.run("bundle.zip", "run-006")

        assert "a0" in state.agent_durations
        assert "a1" in state.agent_durations
        assert state.agent_durations["a0"] == 1.5
        assert state.agent_durations["a1"] == 2.3

class TestArtifactStorage:
    """Artifacts are stored to Spaces on completion with run_id prefix."""
    async def test_artifacts_stored_with_run_id_prefix(self) -> None:
        spaces = AsyncMock()
        spaces.upload = AsyncMock()

        a0 = _make_mock_agent("a0", artifacts={"inventory": "inv_data"})
        a1 = _make_mock_agent("a1", artifacts={"prd_md": "# PRD"})

        agents = [("a0", a0), ("a1", a1)]
        orch = _make_orchestrator(
            agents, spaces_client=spaces, artifacts_bucket="my-bucket"
        )
        state = await orch.run("bundle.zip", "run-007")

        assert state.status == "completed"
        upload_calls = spaces.upload.call_args_list
        keys = [call.args[1] for call in upload_calls]
        assert "run-007/inventory" in keys
        assert "run-007/prd_md" in keys
        # All uploads go to the correct bucket
        for call in upload_calls:
            assert call.args[0] == "my-bucket"

    async def test_no_storage_on_failure(self) -> None:
        spaces = AsyncMock()
        spaces.upload = AsyncMock()

        a0 = _make_mock_agent("a0", artifacts={"inventory": "data"})
        a1 = _make_mock_agent("a1", side_effect=RuntimeError("boom"))

        agents = [("a0", a0), ("a1", a1)]
        orch = _make_orchestrator(agents, spaces_client=spaces)
        state = await orch.run("bundle.zip", "run-008")

        assert state.status == "failed"
        spaces.upload.assert_not_called()

class TestStateTransitions:
    """Run state transitions correctly through the pipeline lifecycle."""
    async def test_successful_run_transitions(self) -> None:
        a0 = _make_mock_agent("a0")
        agents = [("a0", a0)]
        orch = _make_orchestrator(agents)
        state = await orch.run("bundle.zip", "run-009")

        assert state.status == "completed"
        assert state.completed_at is not None
        assert state.started_at != ""
        assert state.current_agent is None

    async def test_failed_run_transitions(self) -> None:
        a0 = _make_mock_agent("a0", side_effect=RuntimeError("fail"))
        agents = [("a0", a0)]
        orch = _make_orchestrator(agents)
        state = await orch.run("bundle.zip", "run-010")

        assert state.status == "failed"
        assert state.completed_at is not None
        assert state.current_agent is None
        assert state.error is not None
