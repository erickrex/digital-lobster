from __future__ import annotations

import logging
from typing import Any

from src.adapters.base import PluginAdapter
from src.adapters.registry import build_adapter_registry, default_adapters
from src.agents.base import AgentResult, BaseAgent
from src.models.capability_manifest import Capability, CapabilityManifest
from src.models.finding import Finding, FindingSeverity
from src.orchestrator.errors import CompilationError
from src.pipeline_context import extract_bundle_manifest

logger = logging.getLogger(__name__)

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
        ambiguous = [c for c in capabilities if c.confidence < 0.8]
        if ambiguous:
            logger.info(
                "LLM fallback needed for %d low-confidence capabilities",
                len(ambiguous),
            )
            refined = await self._llm_classify(ambiguous, bundle)
            high_confidence = [c for c in capabilities if c.confidence >= 0.8]
            capabilities = high_confidence + refined

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
            artifacts={"capability_manifest": manifest},
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
    # LLM fallback (stub)
    # ------------------------------------------------------------------

    async def _llm_classify(
        self,
        ambiguous: list[Capability],
        bundle: Any,
    ) -> list[Capability]:
        """Stub LLM fallback for capabilities with confidence < 0.8.

        Actual LLM call is out of scope for this task.  Logs the attempt
        and returns the capabilities unchanged.
        """
        logger.info("LLM fallback stub: %d ambiguous capabilities unchanged", len(ambiguous))
        return ambiguous

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
