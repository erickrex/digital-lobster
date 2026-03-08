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

class AcfAdapter(PluginAdapter):
    """Adapter for Advanced Custom Fields / ACF Pro."""
    def plugin_family(self) -> str:
        return "acf"

    def required_artifacts(self) -> list[str]:
        return ["acf_field_groups.json", "custom_fields_config.json", "field_usage_report.json"]

    def supported_constructs(self) -> list[str]:
        return [
            "field_group",
            "text",
            "textarea",
            "number",
            "email",
            "url",
            "image",
            "file",
            "wysiwyg",
            "select",
            "checkbox",
            "radio",
            "true_false",
            "relationship",
            "post_object",
            "taxonomy",
            "repeater",
            "flexible_content",
            "group",
            "gallery",
            "date_picker",
            "color_picker",
        ]

    def classify_capabilities(self, bundle_manifest: BundleManifest) -> list[Capability]:
        capabilities: list[Capability] = []
        field_groups = bundle_manifest.acf_field_groups
        groups = field_groups.get("field_groups", []) if isinstance(field_groups, dict) else []
        for group in groups:
            capabilities.append(
                Capability(
                    capability_type="content_model",
                    source_plugin="acf",
                    classification="strapi_native",
                    confidence=0.95,
                    details={"field_group": group.get("title", ""), "field_count": len(group.get("fields", []))},
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
                source_construct="acf_field_group",
                target_type="component",
                target_identifier="acf.field-group",
                transform="field_mapping",
            ),
            MigrationRule(
                source_construct="acf_repeater",
                target_type="component",
                target_identifier="acf.repeater-row",
                transform="nested_component",
            ),
            MigrationRule(
                source_construct="acf_flexible_content",
                target_type="component",
                target_identifier="acf.dynamic-zone",
                transform="dynamic_zone",
            ),
        ]

    def unsupported_cases(self) -> list[str]:
        return [
            "ACF clone fields with circular references",
            "ACF bidirectional relationship fields",
            "ACF Google Maps field (requires API key migration)",
        ]

    def qa_assertions(self, capabilities: list[Capability]) -> list[QAAssertion]:
        return [
            QAAssertion(
                assertion_id="acf_field_group_parity",
                description="All ACF field groups are represented in Strapi schema",
                category="plugin_parity",
                check_type="count",
            ),
        ]

class PodsAdapter(PluginAdapter):
    """Adapter for Pods framework."""
    def plugin_family(self) -> str:
        return "pods"

    def required_artifacts(self) -> list[str]:
        return ["custom_fields_config.json", "field_usage_report.json"]

    def supported_constructs(self) -> list[str]:
        return [
            "pod",
            "pod_field",
            "pod_relationship",
            "pod_file_upload",
            "pod_pick",
        ]

    def classify_capabilities(self, bundle_manifest: BundleManifest) -> list[Capability]:
        capabilities: list[Capability] = []
        config = bundle_manifest.custom_fields_config
        pods = config.get("pods", []) if isinstance(config, dict) else []
        for pod in pods:
            capabilities.append(
                Capability(
                    capability_type="content_model",
                    source_plugin="pods",
                    classification="strapi_native",
                    confidence=0.9,
                    details={"pod_name": pod.get("name", "")},
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
                source_construct="pod",
                target_type="collection",
                target_identifier="pods.pod",
                transform="field_mapping",
            ),
        ]

    def unsupported_cases(self) -> list[str]:
        return [
            "Pods advanced content types with custom storage tables",
            "Pods bidirectional relationships",
        ]

    def qa_assertions(self, capabilities: list[Capability]) -> list[QAAssertion]:
        return [
            QAAssertion(
                assertion_id="pods_field_parity",
                description="All Pods fields are represented in Strapi schema",
                category="plugin_parity",
                check_type="count",
            ),
        ]

class MetaBoxAdapter(PluginAdapter):
    """Adapter for Meta Box plugin."""
    def plugin_family(self) -> str:
        return "meta_box"

    def required_artifacts(self) -> list[str]:
        return ["custom_fields_config.json", "field_usage_report.json"]

    def supported_constructs(self) -> list[str]:
        return [
            "meta_box",
            "meta_box_field",
            "meta_box_group",
            "meta_box_cloneable",
        ]

    def classify_capabilities(self, bundle_manifest: BundleManifest) -> list[Capability]:
        capabilities: list[Capability] = []
        config = bundle_manifest.custom_fields_config
        boxes = config.get("meta_boxes", []) if isinstance(config, dict) else []
        for box in boxes:
            capabilities.append(
                Capability(
                    capability_type="content_model",
                    source_plugin="meta_box",
                    classification="strapi_native",
                    confidence=0.9,
                    details={"meta_box_id": box.get("id", "")},
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
                source_construct="meta_box_group",
                target_type="component",
                target_identifier="meta-box.field-group",
                transform="field_mapping",
            ),
            MigrationRule(
                source_construct="meta_box_cloneable",
                target_type="component",
                target_identifier="meta-box.cloneable-row",
                transform="nested_component",
            ),
        ]

    def unsupported_cases(self) -> list[str]:
        return [
            "Meta Box custom table storage mode",
            "Meta Box frontend submission forms",
        ]

    def qa_assertions(self, capabilities: list[Capability]) -> list[QAAssertion]:
        return [
            QAAssertion(
                assertion_id="meta_box_field_parity",
                description="All Meta Box fields are represented in Strapi schema",
                category="plugin_parity",
                check_type="count",
            ),
        ]

class CarbonFieldsAdapter(PluginAdapter):
    """Adapter for Carbon Fields plugin."""
    def plugin_family(self) -> str:
        return "carbon_fields"

    def required_artifacts(self) -> list[str]:
        return ["custom_fields_config.json", "field_usage_report.json"]

    def supported_constructs(self) -> list[str]:
        return [
            "container",
            "carbon_field",
            "complex_field",
            "association_field",
        ]

    def classify_capabilities(self, bundle_manifest: BundleManifest) -> list[Capability]:
        capabilities: list[Capability] = []
        config = bundle_manifest.custom_fields_config
        containers = config.get("carbon_fields_containers", []) if isinstance(config, dict) else []
        for container in containers:
            capabilities.append(
                Capability(
                    capability_type="content_model",
                    source_plugin="carbon_fields",
                    classification="strapi_native",
                    confidence=0.85,
                    details={"container_id": container.get("id", "")},
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
                source_construct="carbon_fields_container",
                target_type="component",
                target_identifier="carbon-fields.container",
                transform="field_mapping",
            ),
            MigrationRule(
                source_construct="carbon_fields_complex",
                target_type="component",
                target_identifier="carbon-fields.complex-row",
                transform="nested_component",
            ),
        ]

    def unsupported_cases(self) -> list[str]:
        return [
            "Carbon Fields theme options containers (no direct Strapi equivalent)",
            "Carbon Fields association field with mixed entity types",
        ]

    def qa_assertions(self, capabilities: list[Capability]) -> list[QAAssertion]:
        return [
            QAAssertion(
                assertion_id="carbon_fields_parity",
                description="All Carbon Fields containers are represented in Strapi schema",
                category="plugin_parity",
                check_type="count",
            ),
        ]
