"""Sequential pipeline executor.

Orchestrates the migration pipeline in a configurable order,
accumulating artifacts and warnings across agents, recording per-agent
durations via Gradient tracing, and storing final artifacts to Spaces.

When ``cms_mode=True`` the orchestrator inserts four CMS agents
(Strapi Provisioner, Content Type Generator, Content Migrator,
Deployment Pipeline) into the sequence.  When ``cms_mode=False``
the original 7-agent pipeline runs unchanged.
"""

from __future__ import annotations

import json
import logging
from inspect import isawaitable
from typing import Any

from src.agents.base import AgentResult, BaseAgent
from src.agents.blueprint_intake import BlueprintIntakeAgent
from src.agents.content_migrator import ContentMigratorAgent
from src.agents.content_type_generator import ContentTypeGeneratorAgent
from src.agents.deployment_pipeline import DeploymentPipelineAgent
from src.agents.importer import ImporterAgent
from src.agents.modeling import ModelingAgent
from src.agents.prd_lite import PrdLiteAgent
from src.agents.qa import QAAgent
from src.agents.scaffold import ScaffoldAgent
from src.agents.strapi_provisioner import StrapiProvisionerAgent
from src.agents.theming import ThemingAgent
from src.gradient.tracing import Tracer, TracingBackend
from src.orchestrator.errors import AgentError
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

# Artifacts that are only used as transient in-memory pipeline context
# and should not be persisted to Spaces as downloadable outputs.
NON_PERSISTED_ARTIFACTS: set[str] = {
    "export_bundle",
    "content_items",
    "menus",
    "redirect_rules",
    "html_snapshots",
}


class PipelineOrchestrator:
    """Executes the migration pipeline in sequential agent order.

    Supports both the standard 7-agent sequence and the extended
    11-agent CMS sequence when ``cms_mode=True``.
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
    ) -> PipelineRunState:
        """Execute the pipeline sequentially.

        When *cms_mode* is ``True`` the orchestrator uses the extended
        11-agent CMS sequence; otherwise the original 7-agent sequence
        runs unchanged.

        Args:
            bundle_key: Object key of the uploaded ZIP in the Spaces
                ingestion bucket.
            run_id: Unique identifier for this pipeline run.
            cms_mode: When ``True``, enable Strapi CMS integration.
            cms_config: A ``CMSConfig`` instance required when
                *cms_mode* is ``True``.

        Returns:
            The final ``PipelineRunState`` with accumulated artifacts,
            warnings, durations, and status.
        """
        state = PipelineRunState.create(run_id=run_id, bundle_key=bundle_key)
        state.cms_mode = cms_mode
        state.mark_running()

        agents = self._build_agents(cms_mode=cms_mode)
        context: dict[str, Any] = {
            "bundle_key": bundle_key,
            "run_id": run_id,
            "cms_mode": cms_mode,
        }
        if cms_mode and cms_config is not None:
            context["cms_config"] = cms_config
        tracer = self._make_tracer(run_id)

        try:
            for agent_name, agent in agents:
                try:
                    result = await self._execute_agent(
                        agent_name, agent, context, state, tracer
                    )
                except AgentError:
                    # State already marked as failed inside _execute_agent
                    return state

                # Accumulate artifacts and warnings from this agent
                context.update(result.artifacts)
                state.warnings.extend(result.warnings)

                if "kb_ref" in result.artifacts and result.artifacts["kb_ref"]:
                    state.kb_id = str(result.artifacts["kb_ref"])

            # Pipeline completed successfully — store artifacts to Spaces
            await self._store_artifacts(run_id, state.artifacts)

            # Populate CMS result fields when running in CMS mode
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

            state.mark_completed()
        except Exception as exc:
            # Any pipeline-level error not tied to a specific agent step
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
        and raises ``AgentError``.
        """
        state.mark_agent_started(agent_name)

        async with tracer.agent_span(agent_name) as span:
            try:
                result = await agent.execute(context)
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
            if name not in NON_PERSISTED_ARTIFACTS
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
        self, *, cms_mode: bool = False
    ) -> list[tuple[str, BaseAgent]]:
        """Instantiate agents in pipeline order.

        When *cms_mode* is ``False`` the original 7-agent sequence is
        returned.  When ``True`` the four CMS agents are inserted into
        the sequence producing an 11-agent pipeline.
        """
        # Shared agent instances used in both modes
        agent_map: dict[str, BaseAgent] = {
            "blueprint_intake": BlueprintIntakeAgent(
                self._gradient_client,
                self._kb_client,
                spaces_client=self._spaces_client,
                ingestion_bucket=self._ingestion_bucket,
            ),
            "prd_lite": PrdLiteAgent(self._gradient_client, self._kb_client),
            "modeling": ModelingAgent(self._gradient_client, self._kb_client),
            "theming": ThemingAgent(self._gradient_client, self._kb_client),
            "scaffold": ScaffoldAgent(self._gradient_client, self._kb_client),
            "importer": ImporterAgent(self._gradient_client, self._kb_client),
            "qa": QAAgent(self._gradient_client, self._kb_client),
        }

        if cms_mode:
            agent_map["strapi_provisioner"] = StrapiProvisionerAgent(
                self._gradient_client, self._kb_client
            )
            agent_map["content_type_generator"] = ContentTypeGeneratorAgent(
                self._gradient_client, self._kb_client
            )
            agent_map["content_migrator"] = ContentMigratorAgent(
                self._gradient_client, self._kb_client
            )
            agent_map["deployment_pipeline"] = DeploymentPipelineAgent(
                self._gradient_client, self._kb_client
            )
            order = CMS_AGENT_ORDER
        else:
            order = AGENT_ORDER

        return [(name, agent_map[name]) for name in order]
