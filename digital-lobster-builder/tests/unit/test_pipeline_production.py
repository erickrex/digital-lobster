from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.base import AgentResult, BaseAgent
from src.gradient_sdk.tracing import Tracer
from src.models.finding import Finding, FindingSeverity
from src.orchestrator.pipeline import (
    AGENT_ORDER,
    CMS_AGENT_ORDER,
    PRODUCTION_CMS_AGENT_ORDER,
    PipelineOrchestrator,
    _COMPILATION_STAGES,
    _build_findings_summary,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_finding(
    severity: FindingSeverity = FindingSeverity.WARNING,
    stage: str = "test_stage",
    construct: str = "test_construct",
) -> Finding:
    return Finding(
        severity=severity,
        stage=stage,
        construct=construct,
        message="test message",
        recommended_action="test action",
    )

def _make_mock_agent(
    name: str,
    artifacts: dict[str, Any] | None = None,
    side_effect: Exception | None = None,
) -> BaseAgent:
    agent = AsyncMock(spec=BaseAgent)
    if side_effect:
        agent.execute = AsyncMock(side_effect=side_effect)
    else:
        result = AgentResult(
            agent_name=name,
            artifacts=artifacts or {},
        )
        agent.execute = AsyncMock(return_value=result)
    return agent

def _make_orchestrator(
    agents: list[tuple[str, BaseAgent]],
) -> PipelineOrchestrator:
    gradient_client = MagicMock()
    kb_client = MagicMock()
    sc = AsyncMock()
    sc.upload = AsyncMock()
    tr = Tracer(run_id="test-run")

    orch = PipelineOrchestrator(
        gradient_client=gradient_client,
        kb_client=kb_client,
        spaces_client=sc,
        tracer=tr,
        artifacts_bucket="test-artifacts",
    )
    orch._build_agents = lambda **_kw: agents  # type: ignore[assignment]
    return orch

# ---------------------------------------------------------------------------
# Agent order constants
# ---------------------------------------------------------------------------

class TestProductionCmsAgentOrder:
    """PRODUCTION_CMS_AGENT_ORDER has the correct 14-agent sequence.

    Validates: Requirement 22.1
    """
    def test_has_exactly_14_agents(self) -> None:
        assert len(PRODUCTION_CMS_AGENT_ORDER) == 14

    def test_exact_sequence(self) -> None:
        expected = [
            "blueprint_intake",
            "qualification",
            "capability_resolution",
            "schema_compiler",
            "presentation_compiler",
            "behavior_compiler",
            "manifest_review",
            "content_type_generator",
            "theming",
            "scaffold",
            "importer",
            "content_migrator",
            "parity_qa",
            "deployment_pipeline",
        ]
        assert PRODUCTION_CMS_AGENT_ORDER == expected

    def test_compilation_stages_are_subset_of_production_order(self) -> None:
        assert _COMPILATION_STAGES <= set(PRODUCTION_CMS_AGENT_ORDER)

class TestOriginalAgentOrderUnchanged:
    """cms_mode=False uses original AGENT_ORDER unchanged.

    Validates: Requirement 22.2
    """
    def test_agent_order_has_7_agents(self) -> None:
        assert len(AGENT_ORDER) == 7

    def test_agent_order_exact_sequence(self) -> None:
        expected = [
            "blueprint_intake",
            "prd_lite",
            "modeling",
            "theming",
            "scaffold",
            "importer",
            "qa",
        ]
        assert AGENT_ORDER == expected

    def test_cms_agent_order_has_11_agents(self) -> None:
        assert len(CMS_AGENT_ORDER) == 11

    def test_cms_agent_order_exact_sequence(self) -> None:
        expected = [
            "blueprint_intake",
            "strapi_provisioner",
            "prd_lite",
            "modeling",
            "content_type_generator",
            "theming",
            "scaffold",
            "importer",
            "content_migrator",
            "qa",
            "deployment_pipeline",
        ]
        assert CMS_AGENT_ORDER == expected

class TestBuildAgentsMode:
    """_build_agents returns the correct agent list for each mode."""
    def test_non_cms_mode_returns_agent_order(self) -> None:
        gradient = MagicMock()
        kb = MagicMock()
        spaces = AsyncMock()
        tr = Tracer(run_id="seed")

        orch = PipelineOrchestrator(
            gradient_client=gradient,
            kb_client=kb,
            spaces_client=spaces,
            tracer=tr,
            artifacts_bucket="b",
        )
        agents = orch._build_agents(cms_mode=False)
        names = [name for name, _ in agents]
        assert names == AGENT_ORDER

    def test_cms_mode_non_production_returns_cms_agent_order(self) -> None:
        gradient = MagicMock()
        kb = MagicMock()
        spaces = AsyncMock()
        tr = Tracer(run_id="seed")

        orch = PipelineOrchestrator(
            gradient_client=gradient,
            kb_client=kb,
            spaces_client=spaces,
            tracer=tr,
            artifacts_bucket="b",
        )
        agents = orch._build_agents(cms_mode=True, production_mode=False)
        names = [name for name, _ in agents]
        assert names == CMS_AGENT_ORDER

    def test_production_mode_returns_production_cms_agent_order(self) -> None:
        gradient = MagicMock()
        kb = MagicMock()
        spaces = AsyncMock()
        tr = Tracer(run_id="seed")

        orch = PipelineOrchestrator(
            gradient_client=gradient,
            kb_client=kb,
            spaces_client=spaces,
            tracer=tr,
            artifacts_bucket="b",
        )
        agents = orch._build_agents(cms_mode=True, production_mode=True)
        names = [name for name, _ in agents]
        assert names == PRODUCTION_CMS_AGENT_ORDER

# ---------------------------------------------------------------------------
# Finding accumulation
# ---------------------------------------------------------------------------

class TestFindingAccumulation:
    """Findings from multiple agents are accumulated in state artifacts.

    Validates: Requirement 22.4
    """
    async def test_findings_accumulated_across_agents(self) -> None:
        """Findings from manifests with .findings attr are collected."""
        warning_finding = _make_finding(FindingSeverity.WARNING, stage="qualification")
        info_finding = _make_finding(FindingSeverity.INFO, stage="capability_resolution")

        # Manifest-like objects with .findings attribute
        qual_manifest = MagicMock()
        qual_manifest.findings = [warning_finding]

        cap_manifest = MagicMock()
        cap_manifest.findings = [info_finding]

        agents: list[tuple[str, BaseAgent]] = []
        for name in PRODUCTION_CMS_AGENT_ORDER:
            if name == "qualification":
                agent = _make_mock_agent(name, artifacts={"readiness_report": qual_manifest})
            elif name == "capability_resolution":
                agent = _make_mock_agent(name, artifacts={"capability_manifest": cap_manifest})
            else:
                agent = _make_mock_agent(name)
            agents.append((name, agent))

        orch = _make_orchestrator(agents)
        state = await orch.run(
            "bundle.zip", "run-accum",
            cms_mode=True, production_mode=True,
        )

        assert state.status == "completed"
        accumulated = state.artifacts["accumulated_findings"]
        assert len(accumulated) == 2
        severities = {f["severity"] for f in accumulated}
        assert severities == {"warning", "info"}

    async def test_findings_summary_counts_per_severity(self) -> None:
        """findings_summary has correct counts per severity level."""
        findings = [
            _make_finding(FindingSeverity.WARNING, stage="s1"),
            _make_finding(FindingSeverity.WARNING, stage="s2"),
            _make_finding(FindingSeverity.INFO, stage="s3"),
        ]

        manifest = MagicMock()
        manifest.findings = findings

        agents: list[tuple[str, BaseAgent]] = []
        for name in PRODUCTION_CMS_AGENT_ORDER:
            if name == "qualification":
                agent = _make_mock_agent(name, artifacts={"report": manifest})
            else:
                agent = _make_mock_agent(name)
            agents.append((name, agent))

        orch = _make_orchestrator(agents)
        state = await orch.run(
            "bundle.zip", "run-summary",
            cms_mode=True, production_mode=True,
        )

        assert state.status == "completed"
        summary = state.artifacts["findings_summary"]
        assert summary == {"warning": 2, "info": 1}

# ---------------------------------------------------------------------------
# Critical finding abort
# ---------------------------------------------------------------------------

class TestCriticalFindingAbort:
    """Critical Finding from a compilation stage aborts the pipeline.

    Validates: Requirement 22.4
    """
    async def test_critical_finding_aborts_pipeline(self) -> None:
        """Pipeline aborts when a compilation stage emits a critical finding."""
        critical = _make_finding(FindingSeverity.CRITICAL, stage="schema_compiler")
        manifest = MagicMock()
        manifest.findings = [critical]

        executed: list[str] = []
        agents: list[tuple[str, BaseAgent]] = []
        for name in PRODUCTION_CMS_AGENT_ORDER:
            if name == "schema_compiler":
                agent = _make_mock_agent(name, artifacts={"content_model_manifest": manifest})
            else:
                agent = _make_mock_agent(name)

            original = agent.execute

            async def _track(ctx, _n=name, _orig=original):
                executed.append(_n)
                return await _orig(ctx)

            agent.execute = AsyncMock(side_effect=_track)
            agents.append((name, agent))

        orch = _make_orchestrator(agents)
        state = await orch.run(
            "bundle.zip", "run-abort",
            cms_mode=True, production_mode=True,
        )

        assert state.status == "failed"
        # Stages after schema_compiler must not have executed
        idx = PRODUCTION_CMS_AGENT_ORDER.index("schema_compiler")
        for subsequent in PRODUCTION_CMS_AGENT_ORDER[idx + 1:]:
            assert subsequent not in executed

        # Accumulated findings and summary present
        assert "accumulated_findings" in state.artifacts
        assert "findings_summary" in state.artifacts
        assert state.artifacts["findings_summary"].get("critical", 0) >= 1

    async def test_non_critical_findings_do_not_abort(self) -> None:
        """Pipeline continues when compilation stages emit only warnings."""
        warning = _make_finding(FindingSeverity.WARNING, stage="capability_resolution")
        manifest = MagicMock()
        manifest.findings = [warning]

        agents: list[tuple[str, BaseAgent]] = []
        for name in PRODUCTION_CMS_AGENT_ORDER:
            if name == "capability_resolution":
                agent = _make_mock_agent(name, artifacts={"capability_manifest": manifest})
            else:
                agent = _make_mock_agent(name)
            agents.append((name, agent))

        orch = _make_orchestrator(agents)
        state = await orch.run(
            "bundle.zip", "run-no-abort",
            cms_mode=True, production_mode=True,
        )

        assert state.status == "completed"
        assert len(state.artifacts["accumulated_findings"]) == 1
        assert state.artifacts["accumulated_findings"][0]["severity"] == "warning"

    async def test_critical_finding_from_non_compilation_stage_aborts_at_next_compilation_check(self) -> None:
        """Critical findings accumulated before a compilation stage trigger abort at that stage.

        Findings accumulate globally. Even though qualification is not a
        compilation stage, its critical finding is checked after the next
        compilation stage (capability_resolution) and causes an abort.
        """
        critical = _make_finding(FindingSeverity.CRITICAL, stage="qualification")
        manifest = MagicMock()
        manifest.findings = [critical]

        executed: list[str] = []
        agents: list[tuple[str, BaseAgent]] = []
        for name in PRODUCTION_CMS_AGENT_ORDER:
            if name == "qualification":
                agent = _make_mock_agent(name, artifacts={"readiness_report": manifest})
            else:
                agent = _make_mock_agent(name)

            original = agent.execute

            async def _track(ctx, _n=name, _orig=original):
                executed.append(_n)
                return await _orig(ctx)

            agent.execute = AsyncMock(side_effect=_track)
            agents.append((name, agent))

        orch = _make_orchestrator(agents)
        state = await orch.run(
            "bundle.zip", "run-qual-critical",
            cms_mode=True, production_mode=True,
        )

        assert state.status == "failed"
        # capability_resolution executes (it's the first compilation stage)
        assert "capability_resolution" in executed
        # schema_compiler should NOT have executed (abort after capability_resolution)
        assert "schema_compiler" not in executed

# ---------------------------------------------------------------------------
# _build_findings_summary
# ---------------------------------------------------------------------------

class TestBuildFindingsSummary:
    """_build_findings_summary returns correct severity counts."""
    def test_empty_list(self) -> None:
        assert _build_findings_summary([]) == {}

    def test_single_severity(self) -> None:
        findings = [_make_finding(FindingSeverity.WARNING) for _ in range(3)]
        assert _build_findings_summary(findings) == {"warning": 3}

    def test_mixed_severities(self) -> None:
        findings = [
            _make_finding(FindingSeverity.CRITICAL),
            _make_finding(FindingSeverity.WARNING),
            _make_finding(FindingSeverity.WARNING),
            _make_finding(FindingSeverity.INFO),
        ]
        assert _build_findings_summary(findings) == {
            "critical": 1,
            "warning": 2,
            "info": 1,
        }
