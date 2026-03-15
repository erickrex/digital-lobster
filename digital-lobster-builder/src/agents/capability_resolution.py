from __future__ import annotations

import json
import logging
import warnings
from typing import Any

from pydantic import BaseModel, Field

from src.adapters.base import PluginAdapter
from src.adapters.registry import build_adapter_registry, default_adapters
from src.agents.base import AgentResult, BaseAgent
from src.models.ai_review import CapabilityReviewDecision, CapabilityReviewReport
from src.models.bundle_manifest import BundleManifest
from src.models.capability_manifest import Capability, CapabilityManifest
from src.models.finding import Finding, FindingSeverity
from src.orchestrator.errors import CompilationError
from src.pipeline_context import extract_bundle_manifest

logger = logging.getLogger(__name__)

warnings.filterwarnings(
    "ignore",
    message='Field name "construct" in',
    category=UserWarning,
)

LOW_CONFIDENCE_THRESHOLD = 0.8
LLM_BATCH_SIZE = 6
_VALID_AI_CLASSIFICATIONS = frozenset({
    "strapi_native",
    "astro_runtime",
    "unsupported",
})


class _CapabilityReviewDecisionPayload(BaseModel):
    construct: str
    suggested_classification: str
    suggested_confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    recommended_action: str
    evidence_refs: list[str] = Field(default_factory=list)


class _CapabilityReviewResponse(BaseModel):
    decisions: list[_CapabilityReviewDecisionPayload] = Field(default_factory=list)

class CapabilityResolutionAgent(BaseAgent):
    """Produces the Capability_Manifest from raw bundle data.

    Iterates plugins_fingerprint, delegates to registered PluginAdapters for
    known families, and emits Findings for unsupported plugins.  After plugin
    processing, walks remaining bundle sections (plugin instances, settings,
    options, ACF/custom fields, shortcodes, forms, widgets, hooks, templates,
    page composition, custom table manifests, SEO data, editorial workflows,
    search config, integration manifest) to ensure full coverage.
    """
    def __init__(
        self,
        gradient_client: Any,
        kb_client: Any = None,
        adapters: list[PluginAdapter] | None = None,
    ) -> None:
        super().__init__(gradient_client, kb_client)
        self._adapters = build_adapter_registry(adapters or default_adapters())

    async def execute(self, context: dict[str, Any]) -> AgentResult:
        bundle = extract_bundle_manifest(context)
        capabilities: list[Capability] = []
        findings: list[Finding] = []
        warnings: list[str] = []

        logger.info("Starting capability resolution for %s", bundle.site_url)

        # --- Phase 1: Plugin fingerprint delegation ---
        self._resolve_plugins(bundle, capabilities, findings)

        # --- Phase 2: Process remaining bundle sections ---
        self._process_plugin_instances(bundle, capabilities, findings)
        self._process_settings_and_options(bundle, capabilities)
        self._process_custom_fields(bundle, capabilities)
        self._process_shortcodes(bundle, capabilities)
        self._process_forms(bundle, capabilities)
        self._process_widgets(bundle, capabilities)
        self._process_hooks(bundle, capabilities)
        self._process_templates(bundle, capabilities)
        self._process_page_composition(bundle, capabilities)
        self._process_custom_tables(bundle, capabilities)
        self._process_seo(bundle, capabilities)
        self._process_editorial_workflows(bundle, capabilities)
        self._process_search_config(bundle, capabilities)
        self._process_integration_manifest(bundle, capabilities, findings)

        # --- Phase 3: LLM fallback for low-confidence capabilities ---
        capability_review_report = CapabilityReviewReport()
        ambiguous = [c for c in capabilities if c.confidence < LOW_CONFIDENCE_THRESHOLD]
        if ambiguous:
            logger.info(
                "AI review needed for %d low-confidence capabilities",
                len(ambiguous),
            )
            refined, capability_review_report, review_warnings = await self._llm_classify(
                ambiguous, bundle
            )
            warnings.extend(review_warnings)
            refined_iter = iter(refined)
            rebuilt: list[Capability] = []
            for capability in capabilities:
                if capability.confidence < LOW_CONFIDENCE_THRESHOLD:
                    rebuilt.append(next(refined_iter))
                else:
                    rebuilt.append(capability)
            capabilities = rebuilt

        # --- Phase 4: Categorise capabilities ---
        content_model = [c for c in capabilities if c.capability_type == "content_model"]
        presentation = [c for c in capabilities if c.capability_type in {"widget", "template", "shortcode"}]
        behavior = [c for c in capabilities if c.capability_type in {"form", "search_filter", "integration", "editorial"}]

        plugin_caps: dict[str, list[Capability]] = {}
        for cap in capabilities:
            if cap.source_plugin:
                plugin_caps.setdefault(cap.source_plugin, []).append(cap)

        manifest = CapabilityManifest(
            capabilities=capabilities,
            findings=findings,
            content_model_capabilities=content_model,
            presentation_capabilities=presentation,
            behavior_capabilities=behavior,
            plugin_capabilities=plugin_caps,
        )

        # --- Phase 5: Abort on critical findings ---
        critical = [f for f in findings if f.severity == FindingSeverity.CRITICAL]
        if critical:
            logger.warning(
                "Capability resolution produced %d critical finding(s) for %s",
                len(critical),
                bundle.site_url,
            )
            raise CompilationError("capability_resolution", findings)

        logger.info(
            "Capability resolution complete for %s: %d capabilities, %d findings",
            bundle.site_url,
            len(capabilities),
            len(findings),
        )

        return AgentResult(
            agent_name="capability_resolution",
            artifacts={
                "capability_manifest": manifest,
                "capability_review_report": capability_review_report,
            },
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Plugin fingerprint resolution
    # ------------------------------------------------------------------

    def _resolve_plugins(
        self,
        bundle: Any,
        capabilities: list[Capability],
        findings: list[Finding],
    ) -> None:
        """Iterate plugins_fingerprint and delegate to adapters or flag unsupported."""
        plugins = bundle.plugins_fingerprint.get("plugins", [])
        for plugin in plugins:
            if not isinstance(plugin, dict):
                continue
            status = plugin.get("status", "active")
            if status != "active":
                continue

            family = plugin.get("family", "")
            slug = plugin.get("slug", "")

            if family and family in self._adapters:
                adapter = self._adapters[family]
                caps = adapter.classify_capabilities(bundle)
                capabilities.extend(caps)
                logger.info("Adapter '%s' classified %d capabilities for plugin '%s'", family, len(caps), slug)
            elif slug:
                findings.append(Finding(
                    severity=FindingSeverity.WARNING,
                    stage="capability_resolution",
                    construct=f"plugin:{slug}",
                    message=f"No adapter for plugin family '{family or 'unknown'}'",
                    recommended_action="Review plugin manually",
                ))

    # ------------------------------------------------------------------
    # Bundle section processors
    # ------------------------------------------------------------------

    def _process_plugin_instances(
        self,
        bundle: Any,
        capabilities: list[Capability],
        findings: list[Finding],
    ) -> None:
        """Process plugin_instances artifact for additional capabilities."""
        for instance in bundle.plugin_instances.instances:
            family = instance.source_plugin
            if family in self._adapters:
                # Already handled by adapter in _resolve_plugins
                continue
            capabilities.append(Capability(
                capability_type=self._instance_type_to_capability(instance.instance_type),
                source_plugin=instance.source_plugin,
                classification="unsupported",
                confidence=0.5,
                details={"instance_id": instance.instance_id, "instance_type": instance.instance_type},
            ))

    def _process_settings_and_options(
        self, bundle: Any, capabilities: list[Capability]
    ) -> None:
        """Extract capabilities from site_settings and site_options."""
        if bundle.site_settings:
            capabilities.append(Capability(
                capability_type="content_model",
                source_plugin=None,
                classification="strapi_native",
                confidence=1.0,
                details={"source": "site_settings"},
            ))
        if bundle.site_options:
            capabilities.append(Capability(
                capability_type="content_model",
                source_plugin=None,
                classification="strapi_native",
                confidence=1.0,
                details={"source": "site_options"},
            ))

    def _process_custom_fields(
        self, bundle: Any, capabilities: list[Capability]
    ) -> None:
        """Extract capabilities from acf_field_groups and custom_fields_config."""
        for field_entry in bundle.field_usage_report.fields:
            capabilities.append(Capability(
                capability_type="content_model",
                source_plugin=field_entry.source_plugin,
                classification="strapi_native",
                confidence=0.9,
                details={
                    "post_type": field_entry.post_type,
                    "field_name": field_entry.field_name,
                    "inferred_type": field_entry.inferred_type,
                    "source_system": field_entry.source_system,
                },
            ))

    def _process_shortcodes(
        self, bundle: Any, capabilities: list[Capability]
    ) -> None:
        """Extract capabilities from shortcodes_inventory."""
        shortcodes = bundle.shortcodes_inventory
        for tag in shortcodes.get("shortcodes", []) if isinstance(shortcodes, dict) else []:
            if not isinstance(tag, dict):
                continue
            capabilities.append(Capability(
                capability_type="shortcode",
                source_plugin=tag.get("source_plugin"),
                classification="astro_runtime",
                confidence=0.7,
                details={"tag": tag.get("tag", "unknown")},
            ))

    def _process_forms(
        self, bundle: Any, capabilities: list[Capability]
    ) -> None:
        """Extract capabilities from forms_config."""
        forms = bundle.forms_config
        for form in forms.get("forms", []) if isinstance(forms, dict) else []:
            if not isinstance(form, dict):
                continue
            capabilities.append(Capability(
                capability_type="form",
                source_plugin=form.get("source_plugin"),
                classification="astro_runtime",
                confidence=0.9,
                details={"form_id": form.get("id", "unknown")},
            ))

    def _process_widgets(
        self, bundle: Any, capabilities: list[Capability]
    ) -> None:
        """Extract capabilities from widgets."""
        widgets = bundle.widgets
        for sidebar in widgets.get("sidebars", []) if isinstance(widgets, dict) else []:
            if not isinstance(sidebar, dict):
                continue
            capabilities.append(Capability(
                capability_type="widget",
                source_plugin=sidebar.get("source_plugin"),
                classification="astro_runtime",
                confidence=0.8,
                details={"sidebar_id": sidebar.get("id", "unknown")},
            ))

    def _process_hooks(
        self, bundle: Any, capabilities: list[Capability]
    ) -> None:
        """Extract capabilities from hooks_registry."""
        hooks = bundle.hooks_registry
        for hook in hooks.get("hooks", []) if isinstance(hooks, dict) else []:
            if not isinstance(hook, dict):
                continue
            capabilities.append(Capability(
                capability_type="integration",
                source_plugin=hook.get("source_plugin"),
                classification="unsupported",
                confidence=0.5,
                details={"hook": hook.get("name", "unknown")},
            ))

    def _process_templates(
        self, bundle: Any, capabilities: list[Capability]
    ) -> None:
        """Extract capabilities from page_templates."""
        templates = bundle.page_templates
        for tpl in templates.get("templates", []) if isinstance(templates, dict) else []:
            if not isinstance(tpl, dict):
                continue
            capabilities.append(Capability(
                capability_type="template",
                source_plugin=tpl.get("source_plugin"),
                classification="astro_runtime",
                confidence=0.9,
                details={"template": tpl.get("name", "unknown")},
            ))

    def _process_page_composition(
        self, bundle: Any, capabilities: list[Capability]
    ) -> None:
        """Extract capabilities from page_composition."""
        for page in bundle.page_composition.pages:
            capabilities.append(Capability(
                capability_type="template",
                source_plugin=None,
                classification="astro_runtime",
                confidence=0.9,
                details={"canonical_url": page.canonical_url, "template": page.template},
            ))

    def _process_custom_tables(
        self, bundle: Any, capabilities: list[Capability]
    ) -> None:
        """Extract capabilities from plugin_table_exports."""
        for table_export in bundle.plugin_table_exports:
            capabilities.append(Capability(
                capability_type="content_model",
                source_plugin=table_export.source_plugin,
                classification="strapi_native",
                confidence=0.8,
                details={"table_name": table_export.table_name, "row_count": table_export.row_count},
            ))

    def _process_seo(
        self, bundle: Any, capabilities: list[Capability]
    ) -> None:
        """Extract capabilities from seo_full."""
        if bundle.seo_full.pages:
            source_plugins = {p.source_plugin for p in bundle.seo_full.pages}
            for sp in source_plugins:
                capabilities.append(Capability(
                    capability_type="seo",
                    source_plugin=sp,
                    classification="strapi_native",
                    confidence=1.0,
                    details={"page_count": len(bundle.seo_full.pages)},
                ))

    def _process_editorial_workflows(
        self, bundle: Any, capabilities: list[Capability]
    ) -> None:
        """Extract capabilities from editorial_workflows."""
        ew = bundle.editorial_workflows
        capabilities.append(Capability(
            capability_type="editorial",
            source_plugin=None,
            classification="strapi_native",
            confidence=1.0,
            details={
                "statuses": ew.statuses_in_use,
                "authoring_model": ew.authoring_model,
                "scheduled_publishing": ew.scheduled_publishing,
            },
        ))

    def _process_search_config(
        self, bundle: Any, capabilities: list[Capability]
    ) -> None:
        """Extract capabilities from search_config."""
        sc = bundle.search_config
        if sc.searchable_types:
            capabilities.append(Capability(
                capability_type="search_filter",
                source_plugin=None,
                classification="astro_runtime",
                confidence=0.8,
                details={
                    "searchable_types": sc.searchable_types,
                    "facet_count": len(sc.facets),
                },
            ))

    def _process_integration_manifest(
        self,
        bundle: Any,
        capabilities: list[Capability],
        findings: list[Finding],
    ) -> None:
        """Extract capabilities from integration_manifest."""
        for integration in bundle.integration_manifest.integrations:
            capabilities.append(Capability(
                capability_type="integration",
                source_plugin=None,
                classification="unsupported" if integration.business_critical else "astro_runtime",
                confidence=0.7,
                details={
                    "integration_id": integration.integration_id,
                    "integration_type": integration.integration_type,
                    "target": integration.target,
                    "business_critical": integration.business_critical,
                },
            ))
            if integration.business_critical:
                findings.append(Finding(
                    severity=FindingSeverity.WARNING,
                    stage="capability_resolution",
                    construct=f"integration:{integration.integration_id}",
                    message=f"Business-critical integration '{integration.integration_id}' requires manual review",
                    recommended_action="Verify integration target and configure proxy or rebuild",
                ))

    # ------------------------------------------------------------------
    # AI review for low-confidence capabilities
    # ------------------------------------------------------------------

    async def _llm_classify(
        self,
        ambiguous: list[Capability],
        bundle: BundleManifest,
    ) -> tuple[list[Capability], CapabilityReviewReport, list[str]]:
        """Review ambiguous capabilities with structured model output."""

        warnings: list[str] = []
        report = CapabilityReviewReport(
            ai_review_requested=bool(ambiguous),
            ai_review_completed=False,
            reviewed_count=len(ambiguous),
            skipped_count=len(ambiguous),
        )
        if not ambiguous or self.gradient_client is None:
            return ambiguous, report, warnings

        decisions_by_construct: dict[str, _CapabilityReviewDecisionPayload] = {}
        batch_count = 0
        successful_batches = 0

        for start_idx in range(0, len(ambiguous), LLM_BATCH_SIZE):
            batch = ambiguous[start_idx:start_idx + LLM_BATCH_SIZE]
            batch_count += 1
            payload = [
                self._build_review_payload(capability, bundle)
                for capability in batch
            ]
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are reviewing ambiguous WordPress migration capabilities. "
                        "For each construct, choose the most plausible target "
                        "classification using ONLY these values: "
                        "strapi_native, astro_runtime, unsupported. "
                        "Increase confidence only when the evidence clearly supports it."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "site_url": bundle.site_url,
                            "capabilities": payload,
                        },
                        indent=2,
                    ),
                },
            ]

            try:
                response = await self.gradient_client.complete_structured(
                    messages=messages,
                    schema=_CapabilityReviewResponse,
                )
            except Exception as exc:
                warnings.append(f"Capability AI review failed: {exc}")
                logger.warning("Capability AI review failed: %s", exc)
                continue

            successful_batches += 1
            for item in response.get("decisions", []):
                decision = _CapabilityReviewDecisionPayload.model_validate(item)
                decisions_by_construct[decision.construct] = decision

        report.ai_review_completed = successful_batches == batch_count and batch_count > 0

        refined: list[Capability] = []
        applied_count = 0
        findings: list[Finding] = []
        decisions: list[CapabilityReviewDecision] = []

        for capability in ambiguous:
            construct = _capability_construct(capability)
            decision = decisions_by_construct.get(construct)
            final_capability = capability
            rationale = "No AI review decision returned"
            recommended_action = "Proceed with deterministic classification"
            evidence_refs = _capability_evidence_refs(capability)
            applied = False

            if decision is not None:
                rationale = decision.rationale
                recommended_action = decision.recommended_action
                evidence_refs = decision.evidence_refs or evidence_refs
                if (
                    decision.suggested_classification in _VALID_AI_CLASSIFICATIONS
                    and decision.suggested_confidence > capability.confidence
                    and (
                        decision.suggested_classification != capability.classification
                        or decision.suggested_confidence > capability.confidence
                    )
                ):
                    applied = True
                    applied_count += 1
                    final_capability = capability.model_copy(
                        update={
                            "classification": decision.suggested_classification,
                            "confidence": decision.suggested_confidence,
                        }
                    )
                    severity = (
                        FindingSeverity.WARNING
                        if decision.suggested_classification == "unsupported"
                        else FindingSeverity.INFO
                    )
                    findings.append(Finding(
                        severity=severity,
                        stage="capability_review",
                        construct=construct,
                        message=(
                            f"AI review updated '{construct}' to "
                            f"{decision.suggested_classification}"
                        ),
                        recommended_action=decision.recommended_action,
                    ))

            decisions.append(CapabilityReviewDecision(
                construct=construct,
                capability_type=capability.capability_type,
                source_plugin=capability.source_plugin,
                original_classification=capability.classification,
                final_classification=final_capability.classification,
                original_confidence=capability.confidence,
                final_confidence=final_capability.confidence,
                rationale=rationale,
                recommended_action=recommended_action,
                evidence_refs=evidence_refs,
                applied=applied,
            ))
            refined.append(final_capability)

        report.decisions = decisions
        report.applied_count = applied_count
        report.skipped_count = len(ambiguous) - applied_count
        report.findings = findings

        return refined, report, warnings

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _instance_type_to_capability(instance_type: str) -> str:
        """Map a plugin instance type to a capability_type string."""
        mapping = {
            "form": "form",
            "directory": "content_model",
            "filter": "search_filter",
            "cta": "widget",
            "seo_object": "seo",
            "map": "widget",
            "profile": "content_model",
            "member": "content_model",
            "widget": "widget",
            "singleton": "content_model",
        }
        return mapping.get(instance_type, "integration")

    def _build_review_payload(
        self,
        capability: Capability,
        bundle: BundleManifest,
    ) -> dict[str, Any]:
        """Build the structured evidence packet sent to the model."""

        details = capability.details or {}
        payload: dict[str, Any] = {
            "construct": _capability_construct(capability),
            "capability_type": capability.capability_type,
            "source_plugin": capability.source_plugin,
            "original_classification": capability.classification,
            "original_confidence": capability.confidence,
            "details": details,
            "evidence_refs": _capability_evidence_refs(capability),
        }

        plugin_matches = [
            plugin for plugin in bundle.plugins_fingerprint.get("plugins", [])
            if isinstance(plugin, dict)
            and (
                plugin.get("slug") == capability.source_plugin
                or plugin.get("family") == capability.source_plugin
            )
        ]
        if plugin_matches:
            payload["plugin_fingerprint_matches"] = plugin_matches[:3]

        instance_matches = [
            instance.model_dump()
            for instance in bundle.plugin_instances.instances
            if instance.source_plugin == capability.source_plugin
            or instance.instance_id == details.get("instance_id")
            or instance.instance_id == details.get("form_id")
        ]
        if instance_matches:
            payload["plugin_instances"] = instance_matches[:3]

        if capability.capability_type == "shortcode":
            payload["shortcodes"] = [
                tag for tag in bundle.shortcodes_inventory.get("shortcodes", [])
                if isinstance(tag, dict)
                and (
                    tag.get("tag") == details.get("tag")
                    or tag.get("source_plugin") == capability.source_plugin
                )
            ][:5]
        elif capability.capability_type == "form":
            payload["forms"] = [
                form for form in bundle.forms_config.get("forms", [])
                if isinstance(form, dict)
                and (
                    str(form.get("id")) == str(details.get("form_id"))
                    or form.get("source_plugin") == capability.source_plugin
                )
            ][:5]
        elif capability.capability_type == "widget":
            payload["widgets"] = _take_mapping_or_list_items(
                bundle.widgets.get("sidebars", [])
            )
        elif capability.capability_type == "integration":
            payload["integrations"] = [
                integration.model_dump()
                for integration in bundle.integration_manifest.integrations
                if (
                    integration.integration_id == details.get("integration_id")
                    or integration.target == details.get("target")
                )
            ][:5]
            payload["hooks"] = _take_mapping_or_list_items(
                bundle.hooks_registry.get("hooks", [])
            )
        elif capability.capability_type == "template":
            payload["templates"] = _take_mapping_or_list_items(
                bundle.page_templates.get("templates", [])
            )
            payload["page_composition"] = [
                page.model_dump()
                for page in bundle.page_composition.pages
                if (
                    page.template == details.get("template")
                    or page.canonical_url == details.get("canonical_url")
                )
            ][:3]
        elif capability.capability_type == "content_model":
            payload["field_usage"] = [
                entry.model_dump()
                for entry in bundle.field_usage_report.fields
                if (
                    entry.post_type == details.get("post_type")
                    or entry.field_name == details.get("field_name")
                    or entry.source_plugin == capability.source_plugin
                )
            ][:5]
            payload["plugin_table_exports"] = [
                table.model_dump()
                for table in bundle.plugin_table_exports
                if (
                    table.table_name == details.get("table_name")
                    or table.source_plugin == capability.source_plugin
                )
            ][:3]
        elif capability.capability_type == "search_filter":
            payload["search_config"] = bundle.search_config.model_dump()

        return payload


def _capability_construct(capability: Capability) -> str:
    details = capability.details or {}
    for key in (
        "integration_id",
        "tag",
        "form_id",
        "hook",
        "template",
        "canonical_url",
        "table_name",
        "field_name",
        "source",
    ):
        value = details.get(key)
        if value:
            return f"{capability.capability_type}:{value}"
    return f"{capability.capability_type}:{capability.source_plugin or 'core'}"


def _capability_evidence_refs(capability: Capability) -> list[str]:
    refs = [_capability_construct(capability)]
    details = capability.details or {}
    for key in ("integration_id", "form_id", "tag", "template", "canonical_url"):
        value = details.get(key)
        if value:
            refs.append(str(value))
    return refs


def _take_mapping_or_list_items(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value[:5]
    if isinstance(value, dict):
        return list(value.values())[:5]
    return []
