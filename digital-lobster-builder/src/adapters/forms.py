from __future__ import annotations

from src.adapters.base import (
    MigrationRule,
    PluginAdapter,
    QAAssertion,
    RenderingContribution,
    SchemaContribution,
)
from src.models.bundle_manifest import BundleManifest
from src.models.capability_manifest import Capability


class ContactForm7Adapter(PluginAdapter):
    """Adapter for Contact Form 7."""

    def plugin_family(self) -> str:
        return "cf7"

    def required_artifacts(self) -> list[str]:
        return ["forms_config.json", "plugin_instances.json"]

    def supported_constructs(self) -> list[str]:
        return ["form", "form_field", "mail_template", "submission"]

    def classify_capabilities(self, bundle_manifest: BundleManifest) -> list[Capability]:
        capabilities: list[Capability] = []
        for instance in bundle_manifest.plugin_instances.instances:
            if instance.source_plugin == "cf7" and instance.instance_type == "form":
                capabilities.append(
                    Capability(
                        capability_type="form",
                        source_plugin="cf7",
                        classification="astro_runtime",
                        confidence=0.9,
                        details={"form_id": instance.instance_id},
                    )
                )
        return capabilities

    def schema_strategy(self, capabilities: list[Capability]) -> SchemaContribution:
        return SchemaContribution()

    def rendering_strategy(self, capabilities: list[Capability]) -> RenderingContribution:
        return RenderingContribution()

    def migration_rules(self, capabilities: list[Capability]) -> list[MigrationRule]:
        return [
            MigrationRule(
                source_construct="cf7_form",
                target_type="collection",
                target_identifier="forms.submission",
                transform="form_strategy",
            ),
        ]

    def unsupported_cases(self) -> list[str]:
        return [
            "CF7 conditional logic via third-party add-ons",
            "CF7 file upload fields with server-side validation hooks",
        ]

    def qa_assertions(self, capabilities: list[Capability]) -> list[QAAssertion]:
        return [
            QAAssertion(
                assertion_id="cf7_form_presence",
                description="All CF7 forms are rendered on their embedding pages",
                category="plugin_parity",
                check_type="presence",
            ),
        ]


class WpFormsAdapter(PluginAdapter):
    """Adapter for WPForms."""

    def plugin_family(self) -> str:
        return "wpforms"

    def required_artifacts(self) -> list[str]:
        return ["forms_config.json", "plugin_instances.json"]

    def supported_constructs(self) -> list[str]:
        return ["form", "form_field", "notification", "confirmation", "submission"]

    def classify_capabilities(self, bundle_manifest: BundleManifest) -> list[Capability]:
        capabilities: list[Capability] = []
        for instance in bundle_manifest.plugin_instances.instances:
            if instance.source_plugin == "wpforms" and instance.instance_type == "form":
                capabilities.append(
                    Capability(
                        capability_type="form",
                        source_plugin="wpforms",
                        classification="astro_runtime",
                        confidence=0.9,
                        details={"form_id": instance.instance_id},
                    )
                )
        return capabilities

    def schema_strategy(self, capabilities: list[Capability]) -> SchemaContribution:
        return SchemaContribution()

    def rendering_strategy(self, capabilities: list[Capability]) -> RenderingContribution:
        return RenderingContribution()

    def migration_rules(self, capabilities: list[Capability]) -> list[MigrationRule]:
        return [
            MigrationRule(
                source_construct="wpforms_form",
                target_type="collection",
                target_identifier="forms.submission",
                transform="form_strategy",
            ),
        ]

    def unsupported_cases(self) -> list[str]:
        return [
            "WPForms payment integrations (Stripe, PayPal)",
            "WPForms conversational forms layout",
        ]

    def qa_assertions(self, capabilities: list[Capability]) -> list[QAAssertion]:
        return [
            QAAssertion(
                assertion_id="wpforms_form_presence",
                description="All WPForms forms are rendered on their embedding pages",
                category="plugin_parity",
                check_type="presence",
            ),
        ]


class GravityFormsAdapter(PluginAdapter):
    """Adapter for Gravity Forms."""

    def plugin_family(self) -> str:
        return "gravity_forms"

    def required_artifacts(self) -> list[str]:
        return ["forms_config.json", "plugin_instances.json", "plugin_table_exports/gravity_forms"]

    def supported_constructs(self) -> list[str]:
        return ["form", "form_field", "notification", "confirmation", "entry", "feed"]

    def classify_capabilities(self, bundle_manifest: BundleManifest) -> list[Capability]:
        capabilities: list[Capability] = []
        for instance in bundle_manifest.plugin_instances.instances:
            if instance.source_plugin == "gravity_forms" and instance.instance_type == "form":
                capabilities.append(
                    Capability(
                        capability_type="form",
                        source_plugin="gravity_forms",
                        classification="astro_runtime",
                        confidence=0.9,
                        details={"form_id": instance.instance_id},
                    )
                )
        return capabilities

    def schema_strategy(self, capabilities: list[Capability]) -> SchemaContribution:
        return SchemaContribution()

    def rendering_strategy(self, capabilities: list[Capability]) -> RenderingContribution:
        return RenderingContribution()

    def migration_rules(self, capabilities: list[Capability]) -> list[MigrationRule]:
        return [
            MigrationRule(
                source_construct="gravity_forms_form",
                target_type="collection",
                target_identifier="forms.submission",
                transform="form_strategy",
            ),
            MigrationRule(
                source_construct="gravity_forms_entry",
                target_type="collection",
                target_identifier="forms.entry",
                transform="direct",
            ),
        ]

    def unsupported_cases(self) -> list[str]:
        return [
            "Gravity Forms payment add-ons",
            "Gravity Forms multi-page form conditional logic",
            "Gravity Forms quiz/survey add-ons",
        ]

    def qa_assertions(self, capabilities: list[Capability]) -> list[QAAssertion]:
        return [
            QAAssertion(
                assertion_id="gravity_forms_presence",
                description="All Gravity Forms are rendered on their embedding pages",
                category="plugin_parity",
                check_type="presence",
            ),
        ]


class NinjaFormsAdapter(PluginAdapter):
    """Adapter for Ninja Forms."""

    def plugin_family(self) -> str:
        return "ninja_forms"

    def required_artifacts(self) -> list[str]:
        return ["forms_config.json", "plugin_instances.json"]

    def supported_constructs(self) -> list[str]:
        return ["form", "form_field", "action", "submission"]

    def classify_capabilities(self, bundle_manifest: BundleManifest) -> list[Capability]:
        capabilities: list[Capability] = []
        for instance in bundle_manifest.plugin_instances.instances:
            if instance.source_plugin == "ninja_forms" and instance.instance_type == "form":
                capabilities.append(
                    Capability(
                        capability_type="form",
                        source_plugin="ninja_forms",
                        classification="astro_runtime",
                        confidence=0.9,
                        details={"form_id": instance.instance_id},
                    )
                )
        return capabilities

    def schema_strategy(self, capabilities: list[Capability]) -> SchemaContribution:
        return SchemaContribution()

    def rendering_strategy(self, capabilities: list[Capability]) -> RenderingContribution:
        return RenderingContribution()

    def migration_rules(self, capabilities: list[Capability]) -> list[MigrationRule]:
        return [
            MigrationRule(
                source_construct="ninja_forms_form",
                target_type="collection",
                target_identifier="forms.submission",
                transform="form_strategy",
            ),
        ]

    def unsupported_cases(self) -> list[str]:
        return [
            "Ninja Forms multi-step forms",
            "Ninja Forms conditional logic with complex branching",
        ]

    def qa_assertions(self, capabilities: list[Capability]) -> list[QAAssertion]:
        return [
            QAAssertion(
                assertion_id="ninja_forms_presence",
                description="All Ninja Forms are rendered on their embedding pages",
                category="plugin_parity",
                check_type="presence",
            ),
        ]
