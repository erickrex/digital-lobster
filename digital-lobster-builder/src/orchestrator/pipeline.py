from __future__ import annotations

import json
import logging
from inspect import isawaitable
from typing import Any

from src.agents.base import AgentResult, BaseAgent
from src.agents.behavior_compiler import BehaviorCompilerAgent
from src.agents.blueprint_intake import BlueprintIntakeAgent
from src.agents.capability_resolution import CapabilityResolutionAgent
from src.agents.content_migrator import ContentMigratorAgent
from src.agents.content_type_generator import ContentTypeGeneratorAgent
from src.agents.deployment_pipeline import DeploymentPipelineAgent
from src.agents.importer import ImporterAgent
from src.agents.modeling import ModelingAgent
from src.agents.parity_qa import ParityQAAgent
from src.agents.prd_lite import PrdLiteAgent
from src.agents.presentation_compiler import PresentationCompilerAgent
from src.agents.qa import QAAgent
from src.agents.qualification import QualificationAgent
from src.agents.scaffold import ScaffoldAgent
from src.agents.schema_compiler import SchemaCompilerAgent
from src.agents.strapi_provisioner import StrapiProvisionerAgent
from src.agents.theming import ThemingAgent
from src.gradient.tracing import Tracer, TracingBackend
from src.models.finding import Finding, FindingSeverity
from src.orchestrator.errors import (
    AgentError,
    CompilationError,
    ParityGateError,
    QualificationError,
)
from src.orchestrator.state import PipelineRunState
from src.storage.spaces import SpacesClient

logger = logging.getLogger(__name__)

# Fixed agent execution order
AGENT_ORDER: list[str] = [
    "blueprint_intake",
    "prd_lite",
    "modeling",
    "theming",
    "scaffold",
    "importer",
    "qa",
]

# CMS mode agent execution order — inserts 4 new agents into the sequence
CMS_AGENT_ORDER: list[str] = [
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

# Production CMS mode — 13-agent deterministic compilation pipeline.
# Replaces CMS_AGENT_ORDER when cms_mode=True AND production_mode=True.
PRODUCTION_CMS_AGENT_ORDER: list[str] = [
    "blueprint_intake",
    "qualification",
    "capability_resolution",
    "schema_compiler",
    "presentation_compiler",
    "behavior_compiler",
    "content_type_generator",
    "theming",
    "scaffold",
    "importer",
    "content_migrator",
    "parity_qa",
    "deployment_pipeline",
]

# Compilation stages that abort the pipeline on critical Findings.
_COMPILATION_STAGES: frozenset[str] = frozenset({
    "capability_resolution",
    "schema_compiler",
    "presentation_compiler",
    "behavior_compiler",
})

# Artifacts that may be safely persisted and downloaded by API consumers.
PERSISTED_ARTIFACTS: set[str] = {
    "inventory",
    "prd_md",
    "modeling_manifest",
    "theme_css",
    "tokens_css",
    "layouts",
    "content_files",
    "media_map",
    "navigation",
    "redirects",
    "astro_project",
    "astro_project_zip",
    "qa_report",
    "migration_report",
    "deployment_report",
}


class PipelineOrchestrator:
    """Executes the migration pipeline in sequential agent order.

    Supports three sequences:

    * ``cms_mode=False`` — standard 7-agent ``AGENT_ORDER``.
    * ``cms_mode=True, production_mode=False`` — 11-agent ``CMS_AGENT_ORDER``.
    * ``cms_mode=True, production_mode=True`` — 13-agent
      ``PRODUCTION_CMS_AGENT_ORDER`` with deterministic compilation,
      finding accumulation, and critical-finding abort.
    """

    def __init__(
        self,
        gradient_client: Any,
        kb_client: Any,
        spaces_client: SpacesClient,
        tracer: Tracer,
        artifacts_bucket: str,
        ingestion_bucket: str = "",
    ) -> None:
        self._gradient_client = gradient_client
        self._kb_client = kb_client
        self._spaces_client = spaces_client
        self._tracing_backend: TracingBackend | None = getattr(
            tracer, "_backend", None
        )
        self._artifacts_bucket = artifacts_bucket
        self._ingestion_bucket = ingestion_bucket

    async def run(
        self,
        bundle_key: str,
        run_id: str,
        cms_mode: bool = False,
        cms_config: Any | None = None,
        production_mode: bool = False,
    ) -> PipelineRunState:
        """Execute the pipeline sequentially.

        When *cms_mode* is ``True`` and *production_mode* is ``True``
        the orchestrator uses the 13-agent
        ``PRODUCTION_CMS_AGENT_ORDER`` with finding accumulation and
        critical-finding abort.  When *cms_mode* is ``True`` but
        *production_mode* is ``False`` the 11-agent ``CMS_AGENT_ORDER``
        runs.  When *cms_mode* is ``False`` the original 7-agent
        sequence runs unchanged.

        Args:
            bundle_key: Object key of the uploaded ZIP in the Spaces
                ingestion bucket.
            run_id: Unique identifier for this pipeline run.
            cms_mode: When ``True``, enable Strapi CMS integration.
            cms_config: A ``CMSConfig`` instance required when
                *cms_mode* is ``True``.
            production_mode: When ``True`` (and *cms_mode* is ``True``),
                use the production compilation pipeline.

        Returns:
            The final ``PipelineRunState`` with accumulated artifacts,
            warnings, durations, and status.
        """
        state = PipelineRunState.create(run_id=run_id, bundle_key=bundle_key)
        state.cms_mode = cms_mode
        state.mark_running()

        use_production = cms_mode and production_mode
        agents = self._build_agents(
            cms_mode=cms_mode, production_mode=use_production,
        )
        context: dict[str, Any] = {
            "bundle_key": bundle_key,
            "run_id": run_id,
            "cms_mode": cms_mode,
            "production_mode": use_production,
        }
        if cms_mode and cms_config is not None:
            context["cms_config"] = cms_config

        # Accumulated findings across all agents (production mode only).
        accumulated_findings: list[Finding] = []
        context["accumulated_findings"] = accumulated_findings

        tracer = self._make_tracer(run_id)

        try:
            for agent_name, agent in agents:
                try:
                    result = await self._execute_agent(
                        agent_name, agent, context, state, tracer
                    )
                except (QualificationError, CompilationError, ParityGateError) as exc:
                    # Domain errors carry structured findings — accumulate
                    # them so the caller gets full diagnostics.
                    exc_findings = getattr(exc, "findings", [])
                    if not exc_findings:
                        report = getattr(exc, "parity_report", None)
                        if report is not None:
                            exc_findings = getattr(report, "findings", [])
                    accumulated_findings.extend(exc_findings)
                    context["accumulated_findings"] = accumulated_findings
                    state.artifacts["accumulated_findings"] = [
                        f.model_dump() for f in accumulated_findings
                    ]
                    state.artifacts["findings_summary"] = (
                        _build_findings_summary(accumulated_findings)
                    )
                    return state
                except AgentError:
                    # Generic agent failure — state already marked failed.
                    state.artifacts["accumulated_findings"] = [
                        f.model_dump() for f in accumulated_findings
                    ]
                    state.artifacts["findings_summary"] = (
                        _build_findings_summary(accumulated_findings)
                    )
                    return state

                # Accumulate artifacts and warnings from this agent.
                context.update(result.artifacts)
                state.warnings.extend(result.warnings)

                if "kb_ref" in result.artifacts and result.artifacts["kb_ref"]:
                    state.kb_id = str(result.artifacts["kb_ref"])

                # --- Finding accumulation (production mode) ---
                if use_production:
                    self._accumulate_findings(
                        agent_name, result, accumulated_findings, context,
                    )

                    # Abort on critical findings from compilation stages.
                    if agent_name in _COMPILATION_STAGES:
                        critical = [
                            f for f in accumulated_findings
                            if f.severity == FindingSeverity.CRITICAL
                        ]
                        if critical:
                            logger.warning(
                                "Aborting pipeline run %s: %d critical finding(s) after %s",
                                run_id,
                                len(critical),
                                agent_name,
                            )
                            state.mark_failed(
                                agent_name,
                                CompilationError(agent_name, critical),
                            )
                            state.artifacts["accumulated_findings"] = [
                                f.model_dump() for f in accumulated_findings
                            ]
                            state.artifacts["findings_summary"] = (
                                _build_findings_summary(accumulated_findings)
                            )
                            return state

            # Pipeline completed successfully — store artifacts to Spaces.
            await self._store_artifacts(run_id, state.artifacts)

            # Populate CMS result fields when running in CMS mode.
            if cms_mode:
                state.live_site_url = context.get("live_site_url") or (
                    context.get("deployment_report", {}) or {}
                ).get("live_site_url")
                state.strapi_admin_url = context.get("strapi_admin_url") or (
                    context.get("deployment_report", {}) or {}
                ).get("strapi_admin_url")
                deployment_report = context.get("deployment_report")
                if deployment_report is not None:
                    state.deployment_report = (
                        deployment_report
                        if isinstance(deployment_report, dict)
                        else deployment_report.model_dump()
                        if hasattr(deployment_report, "model_dump")
                        else vars(deployment_report)
                        if hasattr(deployment_report, "__dict__")
                        else deployment_report
                    )

            # Include findings summary in final result (production mode).
            if use_production:
                state.artifacts["accumulated_findings"] = [
                    f.model_dump() for f in accumulated_findings
                ]
                state.artifacts["findings_summary"] = (
                    _build_findings_summary(accumulated_findings)
                )

            state.mark_completed()
        except Exception as exc:
            # Any pipeline-level error not tied to a specific agent step.
            state.mark_failed("pipeline", exc)
        finally:
            await self._cleanup_kb(context, state)

        return state

    async def _execute_agent(
        self,
        agent_name: str,
        agent: BaseAgent,
        context: dict[str, Any],
        state: PipelineRunState,
        tracer: Tracer,
    ) -> AgentResult:
        """Execute a single agent wrapped in a Gradient trace span.

        Updates the pipeline state with agent start/completion markers
        and per-agent duration. On failure, marks the state as failed
        and raises the error.  Domain errors (``QualificationError``,
        ``CompilationError``, ``ParityGateError``) are re-raised as-is
        so the run loop can handle them with structured findings.
        """
        state.mark_agent_started(agent_name)

        async with tracer.agent_span(agent_name) as span:
            try:
                result = await agent.execute(context)
            except (QualificationError, CompilationError, ParityGateError) as exc:
                span.set_error(exc)
                state.mark_failed(agent_name, exc)
                raise
            except Exception as exc:
                span.set_error(exc)
                state.mark_failed(agent_name, exc)
                raise AgentError(
                    agent_name=agent_name,
                    message=str(exc),
                    original_error=exc,
                ) from exc

            span.set_ok(artifacts=list(result.artifacts.keys()))

        duration = result.duration_seconds
        state.mark_agent_completed(
            agent_name,
            duration,
            self._filter_persisted_artifacts(result.artifacts),
        )

        return result

    async def _store_artifacts(
        self, run_id: str, artifacts: dict[str, Any]
    ) -> None:
        """Upload all accumulated artifacts to Spaces with run_id prefix."""
        for name, value in artifacts.items():
            key = f"{run_id}/{name}"
            if isinstance(value, bytes):
                data = value
            elif isinstance(value, str):
                data = value.encode("utf-8")
            else:
                data = json.dumps(value, default=str).encode("utf-8")

            await self._spaces_client.upload(
                self._artifacts_bucket, key, data
            )
            logger.info("Stored artifact %s to %s", name, key)

    @staticmethod
    def _filter_persisted_artifacts(
        artifacts: dict[str, Any]
    ) -> dict[str, Any]:
        """Remove transient context artifacts before persisting in run state."""
        return {
            name: value
            for name, value in artifacts.items()
            if name in PERSISTED_ARTIFACTS
        }

    def _make_tracer(self, run_id: str) -> Tracer:
        """Create a per-run tracer so trace run IDs match pipeline run IDs."""
        return Tracer(run_id=run_id, backend=self._tracing_backend)

    async def _cleanup_kb(
        self, context: dict[str, Any], state: PipelineRunState
    ) -> None:
        """Best-effort KB cleanup after run completion/failure."""
        kb_id = context.get("kb_ref")
        if not kb_id or not self._kb_client:
            return
        try:
            delete_result = self._kb_client.delete(kb_id)
            if isawaitable(delete_result):
                await delete_result
        except Exception as exc:
            msg = f"Knowledge Base cleanup failed for {kb_id}: {exc}"
            logger.warning(msg)
            state.warnings.append(msg)

    def _build_agents(
        self, *, cms_mode: bool = False, production_mode: bool = False,
    ) -> list[tuple[str, BaseAgent]]:
        """Instantiate agents in pipeline order.

        When *cms_mode* is ``False`` the original 7-agent sequence is
        returned.  When ``True`` and *production_mode* is ``False`` the
        11-agent CMS sequence is returned.  When both are ``True`` the
        13-agent production compilation pipeline is returned.
        """
        gc = self._gradient_client
        kb = self._kb_client

        # Shared agent instances used in all modes.
        agent_map: dict[str, BaseAgent] = {
            "blueprint_intake": BlueprintIntakeAgent(
                gc,
                kb,
                spaces_client=self._spaces_client,
                ingestion_bucket=self._ingestion_bucket,
            ),
            "prd_lite": PrdLiteAgent(gc, kb),
            "modeling": ModelingAgent(gc, kb),
            "theming": ThemingAgent(gc, kb),
            "scaffold": ScaffoldAgent(gc, kb),
            "importer": ImporterAgent(gc, kb),
            "qa": QAAgent(gc, kb),
        }

        if cms_mode and production_mode:
            # Production CMS pipeline — 13 agents.
            agent_map["qualification"] = QualificationAgent(gc, kb)
            agent_map["capability_resolution"] = CapabilityResolutionAgent(gc, kb)
            agent_map["schema_compiler"] = SchemaCompilerAgent(gc, kb)
            agent_map["presentation_compiler"] = PresentationCompilerAgent(gc, kb)
            agent_map["behavior_compiler"] = BehaviorCompilerAgent(gc, kb)
            agent_map["content_type_generator"] = ContentTypeGeneratorAgent(gc, kb)
            agent_map["content_migrator"] = ContentMigratorAgent(gc, kb)
            agent_map["parity_qa"] = ParityQAAgent(gc, kb)
            agent_map["deployment_pipeline"] = DeploymentPipelineAgent(gc, kb)
            order = PRODUCTION_CMS_AGENT_ORDER
        elif cms_mode:
            # Legacy CMS pipeline — 11 agents.
            agent_map["strapi_provisioner"] = StrapiProvisionerAgent(gc, kb)
            agent_map["content_type_generator"] = ContentTypeGeneratorAgent(gc, kb)
            agent_map["content_migrator"] = ContentMigratorAgent(gc, kb)
            agent_map["deployment_pipeline"] = DeploymentPipelineAgent(gc, kb)
            order = CMS_AGENT_ORDER
        else:
            order = AGENT_ORDER

        return [(name, agent_map[name]) for name in order]

    # ------------------------------------------------------------------
    # Finding accumulation
    # ------------------------------------------------------------------

    @staticmethod
    def _accumulate_findings(
        agent_name: str,
        result: AgentResult,
        accumulated: list[Finding],
        context: dict[str, Any],
    ) -> None:
        """Collect Finding objects from an agent's result artifacts.

        Agents may emit findings inside their artifacts under various
        keys (e.g. ``readiness_report.findings``, ``capability_manifest.findings``,
        ``parity_report.findings``).  This method also checks for bare
        ``Finding`` lists stored directly in artifacts.
        """
        for _key, value in result.artifacts.items():
            # Direct list of Finding objects
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, Finding):
                        accumulated.append(item)
                continue

            # Objects with a .findings attribute (manifests, reports)
            findings_attr = getattr(value, "findings", None)
            if isinstance(findings_attr, list):
                for item in findings_attr:
                    if isinstance(item, Finding):
                        accumulated.append(item)

        context["accumulated_findings"] = accumulated


def _build_findings_summary(findings: list[Finding]) -> dict[str, int]:
    """Return a count of findings per severity level."""
    summary: dict[str, int] = {}
    for f in findings:
        key = f.severity.value
        summary[key] = summary.get(key, 0) + 1
    return summary
