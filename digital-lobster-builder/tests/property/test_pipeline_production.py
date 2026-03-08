from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.agents.base import AgentResult, BaseAgent
from src.gradient.tracing import Tracer
from src.models.finding import Finding, FindingSeverity
from src.orchestrator.errors import CompilationError
from src.orchestrator.pipeline import (
    PRODUCTION_CMS_AGENT_ORDER,
    PipelineOrchestrator,
    _COMPILATION_STAGES,
    _build_findings_summary,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    """Run an async coroutine synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

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
    """Create a mock agent returning a predetermined AgentResult."""
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
    """Build a PipelineOrchestrator with injected mock agents."""
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
# Hypothesis strategies
# ---------------------------------------------------------------------------

SEVERITY_VALUES = list(FindingSeverity)

COMPILATION_STAGE_LIST = sorted(_COMPILATION_STAGES)

# Stages that come before any compilation stage in the production order.
_PRE_COMPILATION = ["blueprint_intake", "qualification"]

# Stages that come after all compilation stages in the production order.
_POST_COMPILATION = [
    s for s in PRODUCTION_CMS_AGENT_ORDER
    if s not in _COMPILATION_STAGES and s not in _PRE_COMPILATION
]

@st.composite
def finding_lists(draw: st.DrawFn, *, min_size: int = 1, max_size: int = 5) -> list[Finding]:
    """Generate a list of Finding objects with random severities."""
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    return [
        Finding(
            severity=draw(st.sampled_from(SEVERITY_VALUES)),
            stage=draw(st.sampled_from(COMPILATION_STAGE_LIST + ["qualification", "parity_qa"])),
            construct=f"construct_{i}",
            message=f"message_{i}",
            recommended_action=f"action_{i}",
        )
        for i in range(n)
    ]

@st.composite
def critical_finding_lists(draw: st.DrawFn) -> list[Finding]:
    """Generate a list of findings guaranteed to contain at least one CRITICAL."""
    # At least one critical finding
    critical = Finding(
        severity=FindingSeverity.CRITICAL,
        stage=draw(st.sampled_from(COMPILATION_STAGE_LIST)),
        construct="critical_construct",
        message="critical issue found",
        recommended_action="fix it",
    )
    # Optionally more findings of any severity
    extras = draw(finding_lists(min_size=0, max_size=4))
    result = [critical] + extras
    draw(st.randoms()).shuffle(result)
    return result

# ---------------------------------------------------------------------------
# Property 29: Critical Finding aborts compilation
# ---------------------------------------------------------------------------

class TestCriticalFindingAbortsCompilation:
    """Property 29: Critical Finding aborts compilation.

    For any compilation stage that produces a Finding with severity CRITICAL,
    the pipeline SHALL abort and return all accumulated Findings without
    executing subsequent stages.
    """
    @given(
        compilation_stage=st.sampled_from(COMPILATION_STAGE_LIST),
        critical_findings=critical_finding_lists(),
    )
    @settings(max_examples=100)
    def test_critical_finding_aborts_before_subsequent_stages(
        self,
        compilation_stage: str,
        critical_findings: list[Finding],
    ) -> None:
        """Feature: production-migration-pipeline, Property 29: Critical Finding aborts compilation"""
        executed_agents: list[str] = []

        # Build the full production agent list. The compilation stage that
        # produces critical findings returns them as an object with a
        # .findings attribute (mimicking a manifest).
        agents: list[tuple[str, BaseAgent]] = []
        for name in PRODUCTION_CMS_AGENT_ORDER:
            if name == compilation_stage:
                # This agent returns findings inside a manifest-like object
                manifest_with_findings = MagicMock()
                manifest_with_findings.findings = critical_findings
                agent = _make_mock_agent(
                    name,
                    artifacts={f"{name}_manifest": manifest_with_findings},
                )
            else:
                agent = _make_mock_agent(name, artifacts={})

            # Track which agents actually execute
            original_execute = agent.execute

            async def _tracking_exec(ctx, _name=name, _orig=original_execute):
                executed_agents.append(_name)
                return await _orig(ctx)

            agent.execute = AsyncMock(side_effect=_tracking_exec)
            agents.append((name, agent))

        orch = _make_orchestrator(agents)
        state = _run(orch.run(
            "bundle.zip", "run-001",
            cms_mode=True, production_mode=True,
        ))

        # The pipeline must have aborted (failed state).
        assert state.status == "failed", (
            f"Pipeline should have failed after critical finding in {compilation_stage}"
        )

        # Stages after the critical-finding stage must NOT have executed.
        stage_idx = PRODUCTION_CMS_AGENT_ORDER.index(compilation_stage)
        subsequent_stages = PRODUCTION_CMS_AGENT_ORDER[stage_idx + 1:]
        for subsequent in subsequent_stages:
            assert subsequent not in executed_agents, (
                f"Stage '{subsequent}' should not have executed after "
                f"critical finding in '{compilation_stage}'"
            )

        # Accumulated findings must be present in state artifacts.
        assert "accumulated_findings" in state.artifacts
        assert "findings_summary" in state.artifacts

        # The critical findings must appear in the accumulated list.
        accumulated = state.artifacts["accumulated_findings"]
        critical_count = sum(
            1 for f in accumulated if f.get("severity") == "critical"
        )
        assert critical_count >= 1, "At least one critical finding must be accumulated"

# ---------------------------------------------------------------------------
# Property 28: Finding accumulation and summary
# ---------------------------------------------------------------------------

class TestFindingAccumulationAndSummary:
    """Property 28: Finding accumulation and summary.

    For any pipeline run, the final result SHALL contain all Findings from
    all stages. The summary count per severity level SHALL equal the actual
    count of Findings with that severity in the accumulated list.
    """
    @given(
        per_agent_findings=st.lists(
            finding_lists(min_size=0, max_size=4),
            min_size=2,
            max_size=5,
        ),
    )
    @settings(max_examples=100)
    def test_findings_accumulated_across_agents_with_correct_summary(
        self,
        per_agent_findings: list[list[Finding]],
    ) -> None:
        """Feature: production-migration-pipeline, Property 28: Finding accumulation and summary"""
        # Filter out any CRITICAL findings — we want the pipeline to
        # complete successfully so we can verify full accumulation.
        sanitized: list[list[Finding]] = []
        for agent_findings in per_agent_findings:
            safe = [
                Finding(
                    severity=(
                        FindingSeverity.WARNING
                        if f.severity == FindingSeverity.CRITICAL
                        else f.severity
                    ),
                    stage=f.stage,
                    construct=f.construct,
                    message=f.message,
                    recommended_action=f.recommended_action,
                )
                for f in agent_findings
            ]
            sanitized.append(safe)

        all_expected_findings = [f for group in sanitized for f in group]

        # Use a subset of production stages (enough to cover the agents
        # we're injecting findings into). We use the first N compilation
        # stages plus pre-compilation stages.
        stage_names = list(PRODUCTION_CMS_AGENT_ORDER)

        agents: list[tuple[str, BaseAgent]] = []
        finding_idx = 0
        for name in stage_names:
            if finding_idx < len(sanitized):
                agent_findings = sanitized[finding_idx]
                finding_idx += 1
                # Wrap findings in a manifest-like object with .findings attr
                manifest = MagicMock()
                manifest.findings = agent_findings
                agent = _make_mock_agent(
                    name,
                    artifacts={f"{name}_result": manifest},
                )
            else:
                agent = _make_mock_agent(name, artifacts={})
            agents.append((name, agent))

        orch = _make_orchestrator(agents)
        state = _run(orch.run(
            "bundle.zip", "run-002",
            cms_mode=True, production_mode=True,
        ))

        assert state.status == "completed", (
            f"Pipeline should complete when no critical findings exist, got {state.status}"
        )

        # Verify accumulated_findings contains all findings from all agents.
        accumulated_dicts = state.artifacts.get("accumulated_findings", [])
        assert len(accumulated_dicts) == len(all_expected_findings), (
            f"Expected {len(all_expected_findings)} accumulated findings, "
            f"got {len(accumulated_dicts)}"
        )

        # Verify findings_summary counts match actual severity counts.
        summary = state.artifacts.get("findings_summary", {})
        actual_counts: dict[str, int] = {}
        for f_dict in accumulated_dicts:
            sev = f_dict.get("severity", "")
            actual_counts[sev] = actual_counts.get(sev, 0) + 1

        for severity_val in actual_counts:
            assert summary.get(severity_val, 0) == actual_counts[severity_val], (
                f"Summary count for '{severity_val}' should be "
                f"{actual_counts[severity_val]}, got {summary.get(severity_val, 0)}"
            )

        # Also verify the reverse: summary doesn't contain phantom counts.
        for sev_key, count in summary.items():
            assert actual_counts.get(sev_key, 0) == count, (
                f"Summary has {count} for '{sev_key}' but actual count is "
                f"{actual_counts.get(sev_key, 0)}"
            )

    @given(
        findings_data=st.lists(
            st.sampled_from(SEVERITY_VALUES),
            min_size=1,
            max_size=20,
        ),
    )
    @settings(max_examples=100)
    def test_build_findings_summary_matches_actual_counts(
        self,
        findings_data: list[FindingSeverity],
    ) -> None:
        """Feature: production-migration-pipeline, Property 28: Finding accumulation and summary

        Directly test _build_findings_summary: the summary count per severity
        level SHALL equal the actual count of Findings with that severity.
        """
        findings = [
            Finding(
                severity=sev,
                stage="test",
                construct=f"c_{i}",
                message=f"m_{i}",
                recommended_action=f"a_{i}",
            )
            for i, sev in enumerate(findings_data)
        ]

        summary = _build_findings_summary(findings)

        # Count expected per severity
        expected: dict[str, int] = {}
        for sev in findings_data:
            expected[sev.value] = expected.get(sev.value, 0) + 1

        assert summary == expected, (
            f"Summary {summary} does not match expected {expected}"
        )
