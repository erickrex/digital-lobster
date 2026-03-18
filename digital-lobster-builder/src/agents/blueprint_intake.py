from __future__ import annotations

import io
import json
import logging
import time
import zipfile
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urljoin

from pydantic import ValidationError as PydanticValidationError

from src.agents.base import AgentResult, BaseAgent
from src.models.bundle_artifacts import (
    ContentRelationshipsArtifact,
    EditorialWorkflowsArtifact,
    FieldUsageReportArtifact,
    IntegrationManifestArtifact,
    PageCompositionArtifact,
    PluginInstancesArtifact,
    PluginTableExport,
    SearchConfigArtifact,
    SeoFullArtifact,
)
from src.models.bundle_manifest import BundleManifest
from src.models.bundle_schema import (
    ArtifactRequirement,
    BUNDLE_SCHEMA_V1,
)
from src.models.content import WordPressBlock, WordPressContentItem
from src.models.inventory import (
    ContentTypeSummary,
    Inventory,
    MenuSummary,
    PluginFeature,
    TaxonomySummary,
    ThemeMetadata,
)
from src.models.manifest import ExportManifest
from src.orchestrator.errors import BundleValidationError
from src.pipeline_context import MediaManifestEntry

logger = logging.getLogger(__name__)

# Preferred required entries in the export bundle ZIP.
REQUIRED_FILES = ("MANIFEST.json", "site/site_info.json")
REQUIRED_DIRS = ("theme/", "content/", "menus/")

# Known plugin family indicators — slug substrings → family label.
PLUGIN_FAMILY_INDICATORS: dict[str, str] = {
    "geodirectory": "geodirectory",
    "geodir": "geodirectory",
    "kadence": "kadence",
    "forminator": "forminator",
    "yoast": "yoast",
    "wordpress-seo": "yoast",
}

class BlueprintIntakeAgent(BaseAgent):
    """Validates an Export_Bundle ZIP, builds an Inventory, and populates
    a Gradient Knowledge Base for downstream agents."""
    def __init__(
        self,
        gradient_client: Any,
        kb_client: Any = None,
        spaces_client: Any = None,
        ingestion_bucket: str = "",
        upload_store: Any = None,
    ) -> None:
        super().__init__(gradient_client, kb_client)
        self.spaces_client = spaces_client
        self.ingestion_bucket = ingestion_bucket
        self.upload_store = upload_store

    async def execute(self, context: dict[str, Any]) -> AgentResult:
        """Execute the Blueprint Intake agent.

        Args:
            context: Must contain ``bundle_key`` — the object key of the
                uploaded ZIP in the DigitalOcean Spaces ingestion bucket.

        Returns:
            AgentResult with normalized bundle artifacts for downstream agents.

        Raises:
            BundleValidationError: If the ZIP is malformed, incomplete, or
                does not contain usable content for migration.
        """
        start = time.monotonic()
        warnings: list[str] = []
        bundle_key: str = context["bundle_key"]

        # 1. Download ZIP from Spaces ingestion bucket
        zip_bytes = await self._download_bundle(bundle_key)

        # 2. Open ZIP and validate structure
        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        except zipfile.BadZipFile as exc:
            raise BundleValidationError(
                message=f"Invalid ZIP bundle '{bundle_key}': {exc}",
                validation_failures=[{"artifact": bundle_key, "error": str(exc)}],
            ) from exc

        try:
            errors = validate_bundle_structure(zf)
            if errors:
                _raise_bundle_validation_errors(errors)

            # 3. Parse manifest + site metadata with compatibility fallbacks
            manifest = _parse_manifest(zf)

            # 4. Parse site_info/site_blueprint
            site_info = _load_site_info(zf)

            # 5. Build Inventory
            inventory = build_inventory(zf, manifest, site_info, warnings)
            export_bundle = extract_export_bundle(zf, warnings)
            content_items = extract_content_items(zf, warnings)
            menus = extract_menu_definitions(zf, warnings)
            redirect_rules = extract_redirect_rules(zf, warnings)
            html_snapshots = extract_html_snapshots(zf, warnings)
            media_manifest = extract_media_manifest(zf, warnings)
            validation_errors = validate_extracted_bundle(site_info, content_items)
            if validation_errors:
                _raise_bundle_validation_errors(validation_errors)

            # 6. CMS mode: validate bundle against Bundle_Schema and produce BundleManifest
            cms_mode = context.get("cms_mode", False)
            if cms_mode:
                bundle_manifest = validate_cms_bundle(zf, site_info, warnings)
                return AgentResult(
                    agent_name="blueprint_intake",
                    artifacts={
                        "inventory": inventory,
                        "bundle_manifest": bundle_manifest,
                        "export_bundle": export_bundle,
                        "content_items": content_items,
                        "menus": menus,
                        "redirect_rules": redirect_rules,
                        "html_snapshots": html_snapshots,
                        "media_manifest": [entry.model_dump() for entry in media_manifest],
                    },
                    warnings=warnings,
                    duration_seconds=time.monotonic() - start,
                )

            # 7. Create Knowledge Base and upload documents
            kb_ref: str | None = None
            if self.kb_client is not None:
                run_id = context.get("run_id", bundle_key)
                kb_ref = await self._create_and_populate_kb(run_id, zf, warnings)

            return AgentResult(
                agent_name="blueprint_intake",
                artifacts={
                    "inventory": inventory,
                    "kb_ref": kb_ref,
                    "export_bundle": export_bundle,
                    "content_items": content_items,
                    "menus": menus,
                    "redirect_rules": redirect_rules,
                    "html_snapshots": html_snapshots,
                    "media_manifest": [entry.model_dump() for entry in media_manifest],
                },
                warnings=warnings,
                duration_seconds=time.monotonic() - start,
            )
        finally:
            zf.close()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _download_bundle(self, bundle_key: str) -> bytes:
        """Download the export bundle ZIP from local storage or Spaces."""
        # Prefer local upload store (used by the HTMX UI upload flow).
        if self.upload_store is not None:
            local_path = self.upload_store.get_path(bundle_key)
            if local_path.exists():
                logger.info("Reading bundle from local storage: %s", bundle_key)
                return local_path.read_bytes()

        if self.spaces_client is None:
            raise RuntimeError(
                "SpacesClient is required for bundle download and "
                f"bundle not found in local storage: {bundle_key}"
            )
        return await self.spaces_client.download(
            self.ingestion_bucket, bundle_key
        )

    async def _create_and_populate_kb(
        self,
        run_id: str,
        zf: zipfile.ZipFile,
        warnings: list[str],
    ) -> str:
        """Create a Gradient Knowledge Base seeded with relevant documents."""
        documents = collect_kb_documents(zf)
        kb_id = await self.kb_client.create(run_id, documents=documents or None)
        return kb_id

# ======================================================================
# Pure functions — no I/O, fully testable in isolation
# ======================================================================

def validate_bundle_structure(zf: zipfile.ZipFile) -> list[dict[str, str]]:
    """Check that all required files and directories exist in the ZIP.

    Returns an empty list when the bundle is valid, or a list of
    ``{"path": ..., "error": ...}`` dicts describing each issue.
    """
    names = set(zf.namelist())
    errors: list[dict[str, str]] = []

    has_manifest = "MANIFEST.json" in names or "site_blueprint.json" in names
    has_site_info = (
        "site/site_info.json" in names or "site_blueprint.json" in names
    )
    has_menus = any(n.startswith("menus/") for n in names) or "menus.json" in names
    has_content_files = any(
        n.startswith("content/") and n.endswith(".json") for n in names
    )

    if not has_manifest:
        errors.append({"path": "MANIFEST.json", "error": "missing required file"})
    if not has_site_info:
        errors.append(
            {"path": "site/site_info.json", "error": "missing required file"}
        )

    for req_dir in ("theme/", "content/"):
        if not any(n.startswith(req_dir) for n in names):
            errors.append({"path": req_dir, "error": "missing required directory"})
    if any(n.startswith("content/") for n in names) and not has_content_files:
        errors.append({
            "path": "content/",
            "error": "no exported content JSON files found",
        })
    if not has_menus:
        errors.append({"path": "menus/", "error": "missing required directory"})

    # Validate that required JSON files are well-formed
    for req_file in ("MANIFEST.json", "site/site_info.json", "site_blueprint.json"):
        if req_file in names:
            try:
                json.loads(zf.read(req_file))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                errors.append({"path": req_file, "error": f"malformed JSON: {exc}"})

    return errors

def validate_extracted_bundle(
    site_info: dict[str, Any],
    content_items: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Validate normalized intake artifacts required for any migration run."""
    errors: list[dict[str, str]] = []

    if not site_info.get("site_url"):
        errors.append({
            "path": "site/site_info.json",
            "error": "missing required site_url in bundle metadata",
        })
    if not site_info.get("site_name"):
        errors.append({
            "path": "site/site_info.json",
            "error": "missing required site_name in bundle metadata",
        })
    if not content_items:
        errors.append({
            "path": "content/",
            "error": "no exported content items found in bundle content JSON files",
        })

    return errors

def _raise_bundle_validation_errors(errors: list[dict[str, str]]) -> None:
    """Raise BundleValidationError from normalized intake validation errors."""
    missing_artifacts = [
        error["path"]
        for error in errors
        if error["error"].startswith("missing required")
    ]
    validation_failures = [
        {"artifact": error["path"], "error": error["error"]}
        for error in errors
        if not error["error"].startswith("missing required")
    ]
    message = "; ".join(f"{error['path']}: {error['error']}" for error in errors)
    raise BundleValidationError(
        message=message,
        missing_artifacts=missing_artifacts,
        validation_failures=validation_failures,
    )

# ---------------------------------------------------------------------------
# CMS bundle validation — used when cms_mode=True
# ---------------------------------------------------------------------------

# Mapping from artifact file_path in the schema to the Pydantic model class
# used for parsing.  Existing artifacts (the 23 scanner outputs) are stored
# as plain dicts, so they don't appear here.
_NEW_ARTIFACT_MODELS: dict[str, type] = {
    "content_relationships.json": ContentRelationshipsArtifact,
    "field_usage_report.json": FieldUsageReportArtifact,
    "plugin_instances.json": PluginInstancesArtifact,
    "page_composition.json": PageCompositionArtifact,
    "seo_full.json": SeoFullArtifact,
    "editorial_workflows.json": EditorialWorkflowsArtifact,
    "plugin_table_exports.json": list,  # sentinel — handled specially
    "search_config.json": SearchConfigArtifact,
    "integration_manifest.json": IntegrationManifestArtifact,
}

# BundleManifest field name for each artifact file_path.
_ARTIFACT_FIELD_MAP: dict[str, str] = {
    "site_blueprint.json": "site_blueprint",
    "site_settings.json": "site_settings",
    "site_options.json": "site_options",
    "site_environment.json": "site_environment",
    "taxonomies.json": "taxonomies",
    "menus.json": "menus",
    "media_map.json": "media_map",
    "theme_mods.json": "theme_mods",
    "global_styles.json": "global_styles",
    "customizer_settings.json": "customizer_settings",
    "css_sources.json": "css_sources",
    "plugins_fingerprint.json": "plugins_fingerprint",
    "plugin_behaviors.json": "plugin_behaviors",
    "blocks_usage.json": "blocks_usage",
    "block_patterns.json": "block_patterns",
    "acf_field_groups.json": "acf_field_groups",
    "custom_fields_config.json": "custom_fields_config",
    "shortcodes_inventory.json": "shortcodes_inventory",
    "forms_config.json": "forms_config",
    "widgets.json": "widgets",
    "page_templates.json": "page_templates",
    "rewrite_rules.json": "rewrite_rules",
    "rest_api_endpoints.json": "rest_api_endpoints",
    "hooks_registry.json": "hooks_registry",
    "error_log.json": "error_log",
    "content_relationships.json": "content_relationships",
    "field_usage_report.json": "field_usage_report",
    "plugin_instances.json": "plugin_instances",
    "page_composition.json": "page_composition",
    "seo_full.json": "seo_full",
    "editorial_workflows.json": "editorial_workflows",
    "plugin_table_exports.json": "plugin_table_exports",
    "search_config.json": "search_config",
    "integration_manifest.json": "integration_manifest",
}

def _is_version_compatible(actual: str, expected: str) -> bool:
    """Check semver major-version compatibility.

    Two versions are compatible when they share the same major version and
    the actual version is not newer than the expected version's next major.
    For example, ``"1.2.0"`` is compatible with expected ``"1.0.0"`` but
    ``"2.0.0"`` is not.
    """
    try:
        actual_parts = [int(p) for p in actual.split(".")]
        expected_parts = [int(p) for p in expected.split(".")]
    except (ValueError, AttributeError):
        return False
    if len(actual_parts) < 1 or len(expected_parts) < 1:
        return False
    return actual_parts[0] == expected_parts[0]

def _resolve_artifact_path(
    names: set[str],
    canonical_path: str,
    alternate_paths: list[str],
) -> str | None:
    """Return the first matching artifact path from canonical and alias paths."""
    for path in (canonical_path, *alternate_paths):
        if path in names:
            return path
    return None

def validate_cms_bundle(
    zf: zipfile.ZipFile,
    site_info: dict[str, Any],
    warnings: list[str],
) -> BundleManifest:
    """Validate the export bundle against BUNDLE_SCHEMA_V1 and produce a BundleManifest.

    Raises :class:`BundleValidationError` when required artifacts are missing
    or when any artifact fails schema/version validation.
    """
    names = set(zf.namelist())
    schema = BUNDLE_SCHEMA_V1

    # --- Phase 1: check presence of all required artifacts -----------------
    missing: list[str] = []
    for artifact_def in schema.artifacts:
        if artifact_def.requirement == ArtifactRequirement.REQUIRED:
            actual_path = _resolve_artifact_path(
                names,
                artifact_def.file_path,
                artifact_def.alternate_paths,
            )
            if actual_path is None:
                missing.append(artifact_def.file_path)

    if missing:
        raise BundleValidationError(
            message=f"Missing {len(missing)} required artifact(s): {', '.join(sorted(missing))}",
            missing_artifacts=sorted(missing),
        )

    # --- Phase 2: load, parse, and validate each artifact ------------------
    parsed: dict[str, Any] = {}
    validation_failures: list[dict[str, str]] = []

    for artifact_def in schema.artifacts:
        file_path = artifact_def.file_path
        actual_path = _resolve_artifact_path(
            names,
            file_path,
            artifact_def.alternate_paths,
        )
        if actual_path is None:
            # Optional artifact not present — skip
            continue

        # Load raw JSON
        try:
            raw = json.loads(zf.read(actual_path))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            validation_failures.append({
                "artifact": file_path,
                "error": f"Malformed JSON: {exc}",
            })
            continue

        # Validate schema_version compatibility
        if isinstance(raw, dict):
            artifact_version = raw.get("schema_version", "")
            if artifact_version and not _is_version_compatible(
                artifact_version, artifact_def.schema_version
            ):
                validation_failures.append({
                    "artifact": file_path,
                    "error": (
                        f"Incompatible schema_version: artifact has '{artifact_version}', "
                        f"expected major version compatible with '{artifact_def.schema_version}'"
                    ),
                })
                continue
        elif isinstance(raw, list):
            # List-shaped artifacts (e.g. plugin_table_exports) — check
            # version on each element if present
            for idx, item in enumerate(raw):
                if isinstance(item, dict):
                    item_version = item.get("schema_version", "")
                    if item_version and not _is_version_compatible(
                        item_version, artifact_def.schema_version
                    ):
                        validation_failures.append({
                            "artifact": file_path,
                            "error": (
                                f"Incompatible schema_version at index {idx}: "
                                f"has '{item_version}', expected compatible with "
                                f"'{artifact_def.schema_version}'"
                            ),
                        })
                        break

        # Parse into typed Pydantic model (new artifacts) or keep as dict/list
        model_cls = _NEW_ARTIFACT_MODELS.get(file_path)
        if model_cls is not None and model_cls is not list:
            try:
                parsed[file_path] = model_cls.model_validate(raw)
            except PydanticValidationError as exc:
                field_errors = "; ".join(
                    f"{'.'.join(str(l) for l in e['loc'])}: {e['msg']}"
                    for e in exc.errors()[:5]
                )
                validation_failures.append({
                    "artifact": file_path,
                    "error": f"Validation failed — {field_errors}",
                })
                continue
        elif file_path == "plugin_table_exports.json":
            # List of PluginTableExport entries
            try:
                entries = [PluginTableExport.model_validate(item) for item in raw] if isinstance(raw, list) else []
                parsed[file_path] = entries
            except PydanticValidationError as exc:
                field_errors = "; ".join(
                    f"{'.'.join(str(l) for l in e['loc'])}: {e['msg']}"
                    for e in exc.errors()[:5]
                )
                validation_failures.append({
                    "artifact": file_path,
                    "error": f"Validation failed — {field_errors}",
                })
                continue
        else:
            # Existing artifact — store as raw dict/list
            parsed[file_path] = raw

    if validation_failures:
        raise BundleValidationError(
            message=(
                f"Validation failed for {len(validation_failures)} artifact(s): "
                + ", ".join(f["artifact"] for f in validation_failures)
            ),
            validation_failures=validation_failures,
        )

    # --- Phase 3: assemble BundleManifest ----------------------------------
    logger.info("CMS bundle validation passed, assembling BundleManifest")

    def _get(fp: str, default: Any = None) -> Any:
        return parsed.get(fp, default)

    def _get_dict(fp: str) -> dict[str, Any]:
        val = parsed.get(fp)
        if isinstance(val, dict):
            return val
        return {}

    def _get_list(fp: str) -> list[dict[str, Any]]:
        val = parsed.get(fp)
        if isinstance(val, list):
            return val
        return []

    manifest = BundleManifest(
        schema_version=schema.schema_version,
        site_url=site_info.get("site_url", ""),
        site_name=site_info.get("site_name", ""),
        wordpress_version=site_info.get("wordpress_version", ""),
        # Existing artifacts
        site_blueprint=_get_dict("site_blueprint.json"),
        site_settings=_get_dict("site_settings.json"),
        site_options=_get_dict("site_options.json"),
        site_environment=_get_dict("site_environment.json"),
        taxonomies=_get_dict("taxonomies.json"),
        menus=_get_list("menus.json"),
        media_map=_get_list("media_map.json"),
        theme_mods=_get_dict("theme_mods.json"),
        global_styles=_get_dict("global_styles.json"),
        customizer_settings=_get_dict("customizer_settings.json"),
        css_sources=_get_dict("css_sources.json"),
        plugins_fingerprint=_get_dict("plugins_fingerprint.json"),
        plugin_behaviors=_get_dict("plugin_behaviors.json"),
        blocks_usage=_get_dict("blocks_usage.json"),
        block_patterns=_get_dict("block_patterns.json"),
        acf_field_groups=_get_dict("acf_field_groups.json"),
        custom_fields_config=_get_dict("custom_fields_config.json"),
        shortcodes_inventory=_get_dict("shortcodes_inventory.json"),
        forms_config=_get_dict("forms_config.json"),
        widgets=_get_dict("widgets.json"),
        page_templates=_get_dict("page_templates.json"),
        rewrite_rules=_get_dict("rewrite_rules.json"),
        rest_api_endpoints=_get_dict("rest_api_endpoints.json"),
        hooks_registry=_get_dict("hooks_registry.json"),
        error_log=_get_dict("error_log.json"),
        # New CMS artifacts (typed)
        content_relationships=_get("content_relationships.json"),
        field_usage_report=_get("field_usage_report.json"),
        plugin_instances=_get("plugin_instances.json"),
        page_composition=_get("page_composition.json"),
        seo_full=_get("seo_full.json"),
        editorial_workflows=_get("editorial_workflows.json"),
        plugin_table_exports=_get("plugin_table_exports.json", []),
        search_config=_get("search_config.json"),
        integration_manifest=_get("integration_manifest.json"),
    )

    return manifest

def build_inventory(
    zf: zipfile.ZipFile,
    manifest: ExportManifest,
    site_info: dict,
    warnings: list[str],
) -> Inventory:
    """Parse all artifacts from the ZIP and build a normalized Inventory."""
    content_types = _extract_content_types(zf, warnings)
    plugins = _extract_plugins(zf, warnings)
    taxonomies = _extract_taxonomies(zf, warnings)
    menus = _extract_menus(zf, warnings)
    theme = _extract_theme_metadata(zf, warnings)

    return Inventory(
        site_url=site_info.get("site_url", manifest.site_url),
        site_name=site_info.get("site_name", ""),
        wordpress_version=site_info.get(
            "wordpress_version", manifest.wordpress_version
        ),
        content_types=content_types,
        plugins=plugins,
        taxonomies=taxonomies,
        menus=menus,
        theme=theme,
        has_html_snapshots=any(
            n.startswith("snapshots/") for n in zf.namelist()
        ),
        has_media_manifest=(
            "media/media_manifest.json" in zf.namelist()
            or "media/media_map.json" in zf.namelist()
        ),
        has_redirect_rules=(
            "redirects/redirects.json" in zf.namelist()
            or "redirects.json" in zf.namelist()
        ),
        has_seo_data=any(
            p.family == "yoast" for p in plugins
        ),
    )

def detect_plugin_family(slug: str) -> str | None:
    """Return the plugin family label for a known slug, or None."""
    slug_lower = slug.lower()
    for indicator, family in PLUGIN_FAMILY_INDICATORS.items():
        if indicator in slug_lower:
            return family
    return None

def collect_kb_documents(zf: zipfile.ZipFile) -> list[dict]:
    """Select documents from the ZIP to upload to the Knowledge Base.

    Includes: site_info.json (or site_blueprint.json), plugin fingerprints,
    blocks_usage.json, and all content JSON files.
    """
    documents: list[dict] = []
    names = zf.namelist()

    # site_info.json / site_blueprint.json
    for candidate in ("site/site_info.json", "site/site_blueprint.json"):
        if candidate in names:
            documents.append(_make_kb_doc(zf, candidate))
            break
    if "site_blueprint.json" in names and not any(
        doc["metadata"]["file"] == "site/site_info.json" for doc in documents
    ):
        documents.append(_make_kb_doc(zf, "site_blueprint.json"))

    # Plugin fingerprints
    for name in names:
        if name.startswith("plugins/") and name.endswith(".json"):
            documents.append(_make_kb_doc(zf, name))
    if "plugins_fingerprint.json" in names:
        documents.append(_make_kb_doc(zf, "plugins_fingerprint.json"))

    # blocks_usage.json
    if "blocks_usage.json" in names:
        documents.append(_make_kb_doc(zf, "blocks_usage.json"))

    # Content JSON files
    for name in names:
        if name.startswith("content/") and name.endswith(".json"):
            documents.append(_make_kb_doc(zf, name))

    return documents

def extract_export_bundle(
    zf: zipfile.ZipFile, warnings: list[str]
) -> dict[str, str | bytes]:
    """Extract all non-directory ZIP entries into an in-memory bundle mapping."""
    bundle: dict[str, str | bytes] = {}
    for name in zf.namelist():
        if name.endswith("/"):
            continue
        try:
            raw = zf.read(name)
        except Exception as exc:
            warnings.append(f"Failed to read bundle file {name}: {exc}")
            continue
        if _is_text_like_path(name):
            bundle[name] = raw.decode("utf-8", errors="replace")
        else:
            bundle[name] = raw
    return bundle

def extract_content_items(
    zf: zipfile.ZipFile, warnings: list[str]
) -> list[dict[str, Any]]:
    """Extract and normalize WordPress content items from ``content/*.json`` files."""
    content_items: list[dict[str, Any]] = []

    for name in zf.namelist():
        if not (name.startswith("content/") and name.endswith(".json")):
            continue
        try:
            data = json.loads(zf.read(name))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            warnings.append(f"Skipping malformed content file {name}: {exc}")
            continue

        items = data if isinstance(data, list) else [data]
        if not isinstance(items, list):
            continue

        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            normalized = _normalize_content_item(item, index=index, source_file=name)
            try:
                validated = WordPressContentItem.model_validate(normalized)
            except Exception as exc:
                warnings.append(
                    f"Skipping invalid content item in {name} at index {index}: {exc}"
                )
                continue
            content_items.append(validated.model_dump())

    return content_items

def extract_menu_definitions(
    zf: zipfile.ZipFile, warnings: list[str]
) -> list[dict[str, Any]]:
    """Extract full menu definitions used by the importer."""
    menu_defs: list[dict[str, Any]] = []

    for name in zf.namelist():
        if not (
            (name.startswith("menus/") and name.endswith(".json"))
            or name == "menus.json"
        ):
            continue
        try:
            raw = json.loads(zf.read(name))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            warnings.append(f"Skipping malformed menu file {name}: {exc}")
            continue

        location_assignments = _extract_menu_location_assignments(raw)
        if isinstance(raw, dict) and "menus" in raw and isinstance(raw["menus"], list):
            menus = raw["menus"]
        else:
            menus = raw if isinstance(raw, list) else [raw]
        for menu in menus:
            if not isinstance(menu, dict):
                continue
            menu_defs.append({
                "name": menu.get("name", PurePosixPath(name).stem),
                "location": _resolve_menu_location(menu, location_assignments),
                "items": _normalize_menu_items(menu.get("items", [])),
            })

    return menu_defs

def extract_redirect_rules(
    zf: zipfile.ZipFile, warnings: list[str]
) -> list[dict[str, Any]]:
    """Extract redirect rules from ``redirects/redirects.json`` when present."""
    candidates = ("redirects/redirects.json", "redirects.json")
    path = next((candidate for candidate in candidates if candidate in zf.namelist()), "")
    if not path:
        return []

    try:
        data = json.loads(zf.read(path))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        warnings.append(f"Skipping malformed redirect rules file {path}: {exc}")
        return []

    if isinstance(data, list):
        return [rule for rule in data if isinstance(rule, dict)]
    if isinstance(data, dict):
        rules = data.get("redirects", data.get("rules", []))
        if isinstance(rules, list):
            return [rule for rule in rules if isinstance(rule, dict)]
    return [] 

def extract_media_manifest(
    zf: zipfile.ZipFile, warnings: list[str]
) -> list[MediaManifestEntry]:
    """Extract and normalize media manifest entries from known bundle formats."""
    raw_entries: list[Any] = []
    if "media/media_manifest.json" in zf.namelist():
        try:
            data = json.loads(zf.read("media/media_manifest.json"))
            raw_entries = data if isinstance(data, list) else []
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            warnings.append(
                f"Skipping malformed media manifest file media/media_manifest.json: {exc}"
            )
    elif "media/media_map.json" in zf.namelist():
        try:
            data = json.loads(zf.read("media/media_map.json"))
            raw_entries = data if isinstance(data, list) else []
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            warnings.append(
                f"Skipping malformed media manifest file media/media_map.json: {exc}"
            )

    entries: list[MediaManifestEntry] = []
    names = set(zf.namelist())
    seen: set[tuple[str, str]] = set()
    for raw in raw_entries:
        if not isinstance(raw, dict):
            continue
        for candidate in _expand_media_entries(raw, names):
            source_url = _coerce_text(
                candidate.get("url")
                or candidate.get("wp_src")
                or candidate.get("source_url")
            )
            bundle_path = _resolve_media_bundle_path(candidate, names)
            if not source_url or not bundle_path:
                continue
            dedupe_key = (source_url, bundle_path)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            artifact_path = bundle_path.lstrip("/")
            if artifact_path.startswith("public/"):
                artifact_path = artifact_path[len("public/"):]
            entries.append(
                MediaManifestEntry(
                    source_url=source_url,
                    bundle_path=bundle_path,
                    artifact_path=artifact_path,
                    filename=PurePosixPath(bundle_path).name,
                    alt_text=_coerce_text(
                        candidate.get("alt_text")
                        or candidate.get("alt")
                        or (candidate.get("metadata") or {}).get("alt")
                    ),
                    caption=_coerce_text(
                        candidate.get("caption")
                        or (candidate.get("metadata") or {}).get("caption")
                    ),
                    mime_type=_coerce_text(
                        candidate.get("mime_type")
                        or (candidate.get("metadata") or {}).get("mime_type")
                    ),
                    metadata=candidate.get("metadata")
                    if isinstance(candidate.get("metadata"), dict)
                    else None,
                )
            )
    return entries

def extract_html_snapshots(
    zf: zipfile.ZipFile, warnings: list[str]
) -> dict[str, str]:
    """Extract HTML snapshots keyed by URL path for QA visual parity checks."""
    snapshots: dict[str, str] = {}
    for name in zf.namelist():
        if not (name.startswith("snapshots/") and name.endswith(".html")):
            continue
        try:
            html = zf.read(name).decode("utf-8", errors="replace")
        except Exception as exc:
            warnings.append(f"Failed to read snapshot {name}: {exc}")
            continue
        snapshots[_snapshot_path_to_url(name)] = html
    return snapshots

def _normalize_content_item(
    raw: dict[str, Any], index: int, source_file: str
) -> dict[str, Any]:
    """Normalize varying WP export content shapes to ``WordPressContentItem``."""
    post_type = str(raw.get("post_type") or raw.get("type") or "post")
    item_id = raw.get("id")
    try:
        normalized_id = int(item_id)
    except (TypeError, ValueError):
        normalized_id = index + 1

    title = _coerce_text(raw.get("title"))
    slug = _coerce_text(raw.get("slug")) or f"{post_type}-{normalized_id}"
    status = _coerce_text(raw.get("status")) or "publish"
    date = _coerce_text(raw.get("date") or raw.get("date_gmt"))
    excerpt = _coerce_text(raw.get("excerpt")) or None
    raw_html = _extract_raw_html(raw)

    blocks = _normalize_blocks(raw.get("blocks"), raw_html)
    taxonomies = _normalize_taxonomies(raw.get("taxonomies"))
    meta = _metadata_dict(raw)

    featured_media_raw = raw.get("featured_media")
    featured_media: dict[str, Any] | None
    if isinstance(featured_media_raw, dict):
        featured_media = featured_media_raw
    elif isinstance(featured_media_raw, str) and featured_media_raw:
        featured_media = {"url": featured_media_raw}
    else:
        featured_media = None

    legacy_permalink = (
        _coerce_text(raw.get("legacy_permalink"))
        or _coerce_text(raw.get("link"))
        or _coerce_text(raw.get("permalink"))
        or f"/{slug}/"
    )

    seo = raw.get("seo")
    if not isinstance(seo, dict):
        yoast = raw.get("yoast_head_json")
        if isinstance(yoast, dict):
            seo = {
                "title": yoast.get("title", ""),
                "description": yoast.get("description", ""),
            }
        else:
            seo = None

    return {
        "id": normalized_id,
        "post_type": post_type,
        "title": title or slug,
        "slug": slug,
        "status": status,
        "date": date,
        "excerpt": excerpt,
        "blocks": blocks,
        "raw_html": raw_html,
        "taxonomies": taxonomies,
        "meta": {str(k): str(v) for k, v in meta.items()},
        "featured_media": featured_media,
        "legacy_permalink": legacy_permalink,
        "seo": seo,
    }

def _normalize_blocks(raw_blocks: Any, raw_html: str) -> list[dict[str, Any]]:
    """Normalize block array to ``WordPressBlock``-compatible dicts."""
    blocks: list[dict[str, Any]] = []
    if isinstance(raw_blocks, list):
        for block in raw_blocks:
            if isinstance(block, dict):
                name = _coerce_text(block.get("name") or block.get("blockName"))
                attrs = block.get("attrs") if isinstance(block.get("attrs"), dict) else {}
                html = _coerce_text(
                    block.get("html")
                    or block.get("innerHTML")
                    or block.get("content")
                )
                blocks.append(
                    WordPressBlock(
                        name=name or "core/html",
                        attrs=attrs,
                        html=html,
                    ).model_dump()
                )
            elif isinstance(block, str):
                blocks.append(
                    WordPressBlock(
                        name="core/html",
                        attrs={},
                        html=block,
                    ).model_dump()
                )

    if not blocks and raw_html:
        blocks.append(
            WordPressBlock(
                name="core/html",
                attrs={},
                html=raw_html,
            ).model_dump()
        )

    return blocks

def _extract_raw_html(raw: dict[str, Any]) -> str:
    """Extract rendered/raw HTML body from common WordPress export shapes."""
    value = raw.get("raw_html")
    if isinstance(value, str):
        return value
    content = raw.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return _coerce_text(content.get("rendered"))
    return ""

def _normalize_taxonomies(raw_taxonomies: Any) -> dict[str, list]:
    """Normalize taxonomy values to dict[str, list]."""
    if not isinstance(raw_taxonomies, dict):
        return {}
    normalized: dict[str, list] = {}
    for key, value in raw_taxonomies.items():
        if isinstance(value, list):
            normalized[str(key)] = value
        elif value is None:
            normalized[str(key)] = []
        else:
            normalized[str(key)] = [value]
    return normalized

def _normalize_menu_items(items: Any) -> list[dict[str, Any]]:
    """Normalize menu items recursively to importer-compatible structure."""
    if not isinstance(items, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = _coerce_text(item.get("title") or item.get("label"))
        entry: dict[str, Any] = {
            "title": title,
            "url": _coerce_text(item.get("url")),
        }
        children = _normalize_menu_items(item.get("children", []))
        if children:
            entry["children"] = children
        normalized.append(entry)
    return normalized

def _snapshot_path_to_url(path: str) -> str:
    """Map snapshot file path (under snapshots/) to a URL path."""
    rel = PurePosixPath(path).relative_to("snapshots")
    stem = rel.with_suffix("")
    parts = list(stem.parts)
    if parts and parts[-1] == "index":
        parts = parts[:-1]
    if not parts or parts == ["home"]:
        return "/"
    return "/" + "/".join(parts)

def _coerce_text(value: Any) -> str:
    """Convert mixed WP values to text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        rendered = value.get("rendered")
        if isinstance(rendered, str):
            return rendered
    return str(value)

def _is_text_like_path(path: str) -> bool:
    """Heuristic for file extensions that should be decoded as UTF-8 text."""
    text_exts = (
        ".json",
        ".html",
        ".htm",
        ".css",
        ".js",
        ".txt",
        ".md",
        ".xml",
        ".csv",
        ".yml",
        ".yaml",
        ".svg",
    )
    return path.lower().endswith(text_exts)

# ======================================================================
# Internal extraction helpers
# ======================================================================

def _load_json(zf: zipfile.ZipFile, path: str) -> Any:
    """Read and parse a JSON file from the ZIP, returning {} on failure."""
    try:
        return json.loads(zf.read(path))
    except (KeyError, json.JSONDecodeError, UnicodeDecodeError):
        return {}

def _load_first_json(zf: zipfile.ZipFile, paths: tuple[str, ...]) -> Any:
    """Return the first existing JSON artifact from the candidate paths."""
    names = set(zf.namelist())
    for path in paths:
        if path in names:
            return _load_json(zf, path)
    return {}

def _parse_manifest(zf: zipfile.ZipFile) -> ExportManifest:
    """Parse MANIFEST.json into an ExportManifest model."""
    data = _load_json(zf, "MANIFEST.json")
    if not data and "site_blueprint.json" in zf.namelist():
        blueprint = _load_json(zf, "site_blueprint.json")
        export_metadata = (
            blueprint.get("export_metadata", {})
            if isinstance(blueprint, dict)
            else {}
        )
        site_data = blueprint.get("site", {}) if isinstance(blueprint, dict) else {}
        content_summary = (
            blueprint.get("content", {}) if isinstance(blueprint, dict) else {}
        )
        data = {
            "export_version": str(
                export_metadata.get("version", blueprint.get("schema_version", ""))
            ),
            "site_url": (
                site_data.get("site_url")
                or site_data.get("url", export_metadata.get("site_url", ""))
            ),
            "export_date": export_metadata.get(
                "export_date",
                blueprint.get("exported_at", ""),
            ),
            "wordpress_version": (
                site_data.get("wordpress_version")
                or site_data.get("wp_version")
                or export_metadata.get("wordpress_version", "")
            ),
            "total_files": export_metadata.get(
                "total_files",
                content_summary.get("total_exported", 0),
            ),
            "total_size_bytes": export_metadata.get("total_size_bytes", 0),
            "files": export_metadata.get("files", {}),
        }
    return ExportManifest(
        export_version=data.get("export_version", ""),
        site_url=data.get("site_url", ""),
        export_date=data.get("export_date", ""),
        wordpress_version=data.get("wordpress_version", ""),
        total_files=data.get("total_files", 0),
        total_size_bytes=data.get("total_size_bytes", 0),
        files=data.get("files", {}),
    )

def _load_site_info(zf: zipfile.ZipFile) -> dict[str, Any]:
    """Load site metadata from either builder or exporter bundle formats."""
    site_info = _load_json(zf, "site/site_info.json")
    if site_info:
        return {
            "site_url": site_info.get("site_url", site_info.get("url", "")),
            "site_name": site_info.get("site_name", site_info.get("name", "")),
            "wordpress_version": site_info.get(
                "wordpress_version", site_info.get("version", "")
            ),
        }

    blueprint = _load_json(zf, "site_blueprint.json")
    if not blueprint:
        return {}

    export_metadata = (
        blueprint.get("export_metadata", {})
        if isinstance(blueprint, dict)
        else {}
    )
    raw_site_info = {}
    if isinstance(blueprint, dict):
        raw_site_info = blueprint.get("site_info") or blueprint.get("site") or {}
    return {
        "site_url": raw_site_info.get(
            "site_url",
            raw_site_info.get("url", export_metadata.get("site_url", "")),
        ),
        "site_name": raw_site_info.get(
            "site_name",
            raw_site_info.get(
                "name",
                raw_site_info.get(
                    "site_title",
                    export_metadata.get("site_name", ""),
                ),
            ),
        ),
        "wordpress_version": raw_site_info.get(
            "wordpress_version",
            raw_site_info.get(
                "version",
                raw_site_info.get(
                    "wp_version",
                    export_metadata.get("wordpress_version", ""),
                ),
            ),
        ),
    }

def _metadata_dict(item: dict[str, Any]) -> dict[str, Any]:
    """Return normalized post meta from legacy and current exporter keys."""
    meta = item.get("meta")
    if isinstance(meta, dict):
        return meta
    postmeta = item.get("postmeta")
    if isinstance(postmeta, dict):
        return postmeta
    return {}

def _extract_content_types(
    zf: zipfile.ZipFile, warnings: list[str]
) -> list[ContentTypeSummary]:
    """Build ContentTypeSummary entries from content/ JSON files."""
    summaries: dict[str, ContentTypeSummary] = {}

    for name in zf.namelist():
        if not (name.startswith("content/") and name.endswith(".json")):
            continue
        try:
            items = json.loads(zf.read(name))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            warnings.append(f"Skipping malformed content file {name}: {exc}")
            continue

        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            continue

        for item in items:
            if not isinstance(item, dict):
                continue
            post_type = item.get("post_type") or item.get("type") or "post"
            if post_type not in summaries:
                summaries[post_type] = ContentTypeSummary(
                    post_type=post_type,
                    count=0,
                    custom_fields=[],
                    taxonomies=[],
                    sample_slugs=[],
                )
            s = summaries[post_type]
            s.count += 1

            # Collect custom fields from meta
            for field_name in _metadata_dict(item):
                if field_name not in s.custom_fields:
                    s.custom_fields.append(field_name)

            # Collect taxonomies
            for tax_name in item.get("taxonomies", {}):
                if tax_name not in s.taxonomies:
                    s.taxonomies.append(tax_name)

            # Sample slugs (keep up to 5)
            slug = item.get("slug", "")
            if slug and len(s.sample_slugs) < 5:
                s.sample_slugs.append(slug)

    if summaries:
        return list(summaries.values())

    blueprint = _load_json(zf, "site_blueprint.json")
    content_summary = blueprint.get("content", {}) if isinstance(blueprint, dict) else {}
    post_types = (
        content_summary.get("post_types", {})
        if isinstance(content_summary, dict)
        else {}
    )
    if isinstance(post_types, dict):
        for post_type, count in post_types.items():
            try:
                normalized_count = int(count)
            except (TypeError, ValueError):
                continue
            summaries[str(post_type)] = ContentTypeSummary(
                post_type=str(post_type),
                count=max(normalized_count, 0),
                custom_fields=[],
                taxonomies=[],
                sample_slugs=[],
            )

    return list(summaries.values())

def _dedupe_strings(values: list[str]) -> list[str]:
    """Return values with order preserved and empty strings removed."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result

def _normalize_detected_features(raw_features: Any) -> list[str]:
    """Normalize plugin feature flags into a flat string list."""
    if isinstance(raw_features, list):
        return _dedupe_strings([str(item) for item in raw_features])
    if isinstance(raw_features, dict):
        features: list[str] = []
        for key, value in raw_features.items():
            if isinstance(value, bool) and value:
                features.append(str(key))
            elif isinstance(value, (list, dict)) and value:
                features.append(str(key))
            elif isinstance(value, str) and value:
                features.append(str(key))
            elif isinstance(value, (int, float)) and value:
                features.append(str(key))
        return _dedupe_strings(features)
    if isinstance(raw_features, str) and raw_features.strip():
        return [raw_features.strip()]
    return []

def _plugin_slug_from_file(file_ref: str) -> str:
    """Derive a plugin slug from a WordPress plugin file reference."""
    if not file_ref:
        return ""
    path = PurePosixPath(file_ref)
    if len(path.parts) > 1:
        return path.parts[0]
    return path.stem

def _looks_like_plugin_descriptor(data: Any) -> bool:
    """Return True when a JSON object represents a single plugin descriptor."""
    if not isinstance(data, dict):
        return False
    if isinstance(data.get("plugin_info"), dict):
        return True
    return any(
        key in data
        for key in ("slug", "plugin_slug", "file", "name", "plugin_name", "version")
    )

def _iter_plugin_fingerprint_items(data: Any) -> list[dict[str, Any]]:
    """Extract plugin fingerprint entries from legacy and current shapes."""
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    fingerprints = data.get("fingerprints")
    if isinstance(fingerprints, list):
        return [item for item in fingerprints if isinstance(item, dict)]
    if any(key in data for key in ("plugin_slug", "slug", "plugin_name", "name")):
        return [data]
    return []

def _iter_feature_maps(zf: zipfile.ZipFile) -> list[dict[str, Any]]:
    """Collect plugin feature maps from known exporter artifacts."""
    feature_maps: list[dict[str, Any]] = []

    root_fingerprint = _load_json(zf, "plugins_fingerprint.json")
    if isinstance(root_fingerprint, dict):
        enhanced = root_fingerprint.get("enhanced_detection", {})
        if isinstance(enhanced, dict):
            raw_maps = enhanced.get("feature_maps", {})
            if isinstance(raw_maps, dict):
                for value in raw_maps.values():
                    if isinstance(value, dict):
                        feature_maps.append(value)

    blueprint = _load_json(zf, "site_blueprint.json")
    if isinstance(blueprint, dict):
        plugin_features = blueprint.get("plugin_features", {})
        if isinstance(plugin_features, dict):
            enhanced = plugin_features.get("enhanced_detection", {})
            if isinstance(enhanced, dict):
                raw_maps = enhanced.get("feature_maps", {})
                if isinstance(raw_maps, dict):
                    for value in raw_maps.values():
                        if isinstance(value, dict):
                            feature_maps.append(value)

    for name in zf.namelist():
        if not (name.startswith("plugins/feature_maps/") and name.endswith(".json")):
            continue
        data = _load_json(zf, name)
        if isinstance(data, dict):
            feature_maps.append(data)

    return feature_maps

def _upsert_plugin_record(
    plugins: dict[str, dict[str, Any]],
    *,
    slug: str,
    name: str = "",
    version: str = "",
    custom_post_types: list[str] | None = None,
    custom_taxonomies: list[str] | None = None,
    detected_features: list[str] | None = None,
) -> None:
    """Merge plugin metadata from multiple exporter artifacts."""
    normalized_slug = slug.strip()
    if not normalized_slug:
        return

    record = plugins.setdefault(
        normalized_slug,
        {
            "slug": normalized_slug,
            "name": normalized_slug,
            "version": "",
            "family": detect_plugin_family(normalized_slug),
            "custom_post_types": [],
            "custom_taxonomies": [],
            "detected_features": [],
        },
    )

    if name and record["name"] == normalized_slug:
        record["name"] = name
    if version and not record["version"]:
        record["version"] = version

    record["custom_post_types"] = _dedupe_strings(
        [*record["custom_post_types"], *(custom_post_types or [])]
    )
    record["custom_taxonomies"] = _dedupe_strings(
        [*record["custom_taxonomies"], *(custom_taxonomies or [])]
    )
    record["detected_features"] = _dedupe_strings(
        [*record["detected_features"], *(detected_features or [])]
    )

def _extract_plugins(
    zf: zipfile.ZipFile, warnings: list[str]
) -> list[PluginFeature]:
    """Build PluginFeature entries from normalized plugin export artifacts."""
    plugin_records: dict[str, dict[str, Any]] = {}

    for name in zf.namelist():
        if not (name.startswith("plugins/") and name.endswith(".json")):
            continue
        try:
            data = json.loads(zf.read(name))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            warnings.append(f"Skipping malformed plugin file {name}: {exc}")
            continue

        if not _looks_like_plugin_descriptor(data):
            continue

        plugin_info = data.get("plugin_info", {}) if isinstance(data, dict) else {}
        slug = (
            data.get("slug")
            or data.get("plugin_slug")
            or _plugin_slug_from_file(data.get("file", ""))
            or plugin_info.get("slug")
            or _plugin_slug_from_file(plugin_info.get("file", ""))
            or PurePosixPath(name).stem
        )
        custom_taxonomies = [
            str(item.get("name", ""))
            for item in data.get("taxonomies", [])
            if isinstance(item, dict) and item.get("name")
        ]
        _upsert_plugin_record(
            plugin_records,
            slug=str(slug),
            name=_coerce_text(
                data.get("name")
                or data.get("plugin_name")
                or plugin_info.get("name", "")
            ),
            version=_coerce_text(
                data.get("version") or plugin_info.get("version", "")
            ),
            custom_post_types=_dedupe_strings([
                str(item)
                for item in data.get("custom_post_types", [])
            ]),
            custom_taxonomies=custom_taxonomies,
            detected_features=_normalize_detected_features(
                data.get("detected_features") or data.get("features")
            ),
        )

    for path in ("plugins/plugins_fingerprint.json", "plugins_fingerprint.json"):
        if path not in zf.namelist():
            continue
        data = _load_json(zf, path)
        for item in _iter_plugin_fingerprint_items(data):
            slug = (
                item.get("slug")
                or item.get("plugin_slug")
                or _plugin_slug_from_file(item.get("file", ""))
            )
            _upsert_plugin_record(
                plugin_records,
                slug=_coerce_text(slug),
                name=_coerce_text(item.get("name") or item.get("plugin_name")),
                version=_coerce_text(item.get("version")),
                custom_post_types=_dedupe_strings([
                    str(value) for value in item.get("custom_post_types", [])
                ]),
                custom_taxonomies=_dedupe_strings([
                    str(value) for value in item.get("custom_taxonomies", [])
                ]),
                detected_features=_normalize_detected_features(
                    item.get("detected_features") or item.get("features")
                ),
            )

    blueprint = _load_json(zf, "site_blueprint.json")
    if isinstance(blueprint, dict):
        plugin_lists: list[list[dict[str, Any]]] = []
        plugins_value = blueprint.get("plugins")
        if isinstance(plugins_value, list):
            plugin_lists.append(
                [item for item in plugins_value if isinstance(item, dict)]
            )
        active_plugins = blueprint.get("active_plugins")
        if isinstance(active_plugins, list):
            plugin_lists.append(
                [item for item in active_plugins if isinstance(item, dict)]
            )

        for plugin_list in plugin_lists:
            for item in plugin_list:
                slug = (
                    item.get("slug")
                    or _plugin_slug_from_file(item.get("file", ""))
                )
                _upsert_plugin_record(
                    plugin_records,
                    slug=_coerce_text(slug),
                    name=_coerce_text(item.get("name")),
                    version=_coerce_text(item.get("version")),
                    detected_features=_normalize_detected_features(
                        item.get("detected_features")
                        or item.get("blocks")
                        or item.get("shortcodes")
                        or item.get("rest_endpoints")
                    ),
                )

    for feature_map in _iter_feature_maps(zf):
        plugin_info = feature_map.get("plugin_info", {})
        if not isinstance(plugin_info, dict):
            continue
        custom_taxonomies = [
            str(item.get("name", ""))
            for item in feature_map.get("taxonomies", [])
            if isinstance(item, dict) and item.get("name")
        ]
        _upsert_plugin_record(
            plugin_records,
            slug=_coerce_text(
                plugin_info.get("slug")
                or _plugin_slug_from_file(plugin_info.get("file", ""))
            ),
            name=_coerce_text(plugin_info.get("name")),
            version=_coerce_text(plugin_info.get("version")),
            custom_post_types=_dedupe_strings([
                str(value) for value in feature_map.get("custom_post_types", [])
            ]),
            custom_taxonomies=custom_taxonomies,
            detected_features=_normalize_detected_features(
                feature_map.get("features")
            ),
        )

    return [
        PluginFeature.model_validate(record)
        for record in plugin_records.values()
    ]

def _extract_taxonomies(
    zf: zipfile.ZipFile, warnings: list[str]
) -> list[TaxonomySummary]:
    """Build TaxonomySummary entries from taxonomies/ or content metadata."""
    taxonomies: dict[str, TaxonomySummary] = {}

    # Try dedicated taxonomies file first
    tax_data = _load_first_json(
        zf,
        ("taxonomies/taxonomies.json", "taxonomies.json", "plugins/taxonomies.json"),
    )
    if isinstance(tax_data, list):
        for item in tax_data:
            if not isinstance(item, dict):
                continue
            tax_name = _coerce_text(item.get("taxonomy") or item.get("name"))
            if not tax_name:
                continue
            taxonomies[tax_name] = TaxonomySummary(
                taxonomy=tax_name,
                term_count=int(item.get("term_count", 0) or 0),
                associated_post_types=_dedupe_strings([
                    str(value)
                    for value in item.get("associated_post_types", [])
                ]),
            )
    elif isinstance(tax_data, dict):
        taxonomies_by_plugin = tax_data.get("taxonomies_by_plugin")
        if isinstance(taxonomies_by_plugin, dict):
            for plugin_taxonomies in taxonomies_by_plugin.values():
                if not isinstance(plugin_taxonomies, list):
                    continue
                for item in plugin_taxonomies:
                    if not isinstance(item, dict):
                        continue
                    tax_name = _coerce_text(item.get("name"))
                    if not tax_name:
                        continue
                    summary = taxonomies.setdefault(
                        tax_name,
                        TaxonomySummary(
                            taxonomy=tax_name,
                            term_count=0,
                            associated_post_types=[],
                        ),
                    )
                    for post_type in item.get("object_types", []):
                        normalized = str(post_type).strip()
                        if (
                            normalized
                            and normalized not in summary.associated_post_types
                        ):
                            summary.associated_post_types.append(normalized)
        else:
            for tax_name, item in tax_data.items():
                if tax_name == "schema_version" or not isinstance(item, dict):
                    continue
                summary_name = _coerce_text(
                    item.get("taxonomy") or item.get("name") or tax_name
                )
                taxonomies[summary_name] = TaxonomySummary(
                    taxonomy=summary_name,
                    term_count=int(item.get("term_count", 0) or 0),
                    associated_post_types=_dedupe_strings([
                        str(value)
                        for value in item.get("associated_post_types", [])
                    ]),
                )

    blueprint = _load_json(zf, "site_blueprint.json")
    blueprint_taxonomies = (
        blueprint.get("taxonomies", {}) if isinstance(blueprint, dict) else {}
    )
    if isinstance(blueprint_taxonomies, dict):
        for tax_name, details in blueprint_taxonomies.items():
            if not isinstance(details, dict):
                continue
            summary = taxonomies.setdefault(
                str(tax_name),
                TaxonomySummary(
                    taxonomy=str(tax_name),
                    term_count=0,
                    associated_post_types=[],
                ),
            )
            for post_type in details.get("object_types", []):
                normalized = str(post_type).strip()
                if normalized and normalized not in summary.associated_post_types:
                    summary.associated_post_types.append(normalized)

    # Also scan content files for taxonomy references
    for name in zf.namelist():
        if not (name.startswith("content/") and name.endswith(".json")):
            continue
        try:
            items = json.loads(zf.read(name))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            post_type = item.get("post_type") or item.get("type") or "post"
            raw_taxonomies = item.get("taxonomies", {})
            if not isinstance(raw_taxonomies, dict):
                continue
            for tax_name, terms in raw_taxonomies.items():
                if tax_name not in taxonomies:
                    taxonomies[tax_name] = TaxonomySummary(
                        taxonomy=tax_name,
                        term_count=0,
                        associated_post_types=[],
                    )
                t = taxonomies[tax_name]
                if isinstance(terms, list):
                    t.term_count = max(t.term_count, len(terms))
                if post_type not in t.associated_post_types:
                    t.associated_post_types.append(post_type)

    return list(taxonomies.values())

def _extract_menu_location_assignments(data: Any) -> dict[str, str]:
    """Return a map of menu term IDs to assigned menu locations."""
    if not isinstance(data, dict):
        return {}
    menu_locations = data.get("menu_locations", {})
    if not isinstance(menu_locations, dict):
        return {}

    assignments: dict[str, str] = {}
    for location, details in menu_locations.items():
        if not isinstance(details, dict):
            continue
        assigned_menu = details.get("assigned_menu")
        if assigned_menu in (None, "", 0, "0"):
            continue
        assignments[str(assigned_menu)] = str(location)
    return assignments

def _resolve_menu_location(
    menu: dict[str, Any],
    location_assignments: dict[str, str],
) -> str:
    """Resolve a menu location from direct fields or top-level assignments."""
    location = _coerce_text(menu.get("location"))
    if location:
        return location

    locations = menu.get("locations")
    if isinstance(locations, list) and locations:
        return _coerce_text(locations[0])

    for key in ("term_id", "id", "menu_id"):
        menu_id = menu.get(key)
        if menu_id is None:
            continue
        assigned = location_assignments.get(str(menu_id))
        if assigned:
            return assigned

    return ""

def _extract_menus(
    zf: zipfile.ZipFile, warnings: list[str]
) -> list[MenuSummary]:
    """Build MenuSummary entries from menus/ JSON files."""
    menus: list[MenuSummary] = []

    for name in zf.namelist():
        if not (
            (name.startswith("menus/") and name.endswith(".json"))
            or name == "menus.json"
        ):
            continue
        try:
            data = json.loads(zf.read(name))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            warnings.append(f"Skipping malformed menu file {name}: {exc}")
            continue

        location_assignments = _extract_menu_location_assignments(data)
        if isinstance(data, dict) and "menus" in data and isinstance(data["menus"], list):
            data = data["menus"]
        if isinstance(data, list):
            # File contains a list of menus
            for menu in data:
                if isinstance(menu, dict):
                    menus.append(_menu_from_dict(menu, name, location_assignments))
        elif isinstance(data, dict):
            menus.append(_menu_from_dict(data, name, location_assignments))

    return menus

def _menu_from_dict(
    data: dict,
    source_file: str,
    location_assignments: dict[str, str] | None = None,
) -> MenuSummary:
    """Build a MenuSummary from a menu dict."""
    items = data.get("items", [])
    return MenuSummary(
        name=data.get("name", PurePosixPath(source_file).stem),
        location=_resolve_menu_location(data, location_assignments or {}),
        item_count=len(items) if isinstance(items, list) else 0,
    )

def _extract_theme_metadata(
    zf: zipfile.ZipFile, warnings: list[str]
) -> ThemeMetadata:
    """Build ThemeMetadata from theme/ directory contents."""
    names = zf.namelist()
    has_theme_json = "theme/theme.json" in names
    has_custom_css = any(
        n.startswith("theme/") and n.endswith(".css") for n in names
    )

    design_tokens: dict | None = None
    if has_theme_json:
        theme_data = _load_json(zf, "theme/theme.json")
        settings = theme_data.get("settings", {})
        if settings:
            design_tokens = {}
            if "color" in settings:
                design_tokens["color"] = settings["color"]
            if "typography" in settings:
                design_tokens["typography"] = settings["typography"]
            if "spacing" in settings:
                design_tokens["spacing"] = settings["spacing"]

    # Try to get theme name from style.css header or theme.json
    theme_name = ""
    if has_theme_json:
        theme_data = _load_json(zf, "theme/theme.json")
        theme_name = theme_data.get("name", theme_data.get("title", ""))
    if not theme_name:
        # Fallback: look for a style.css with a Theme Name header
        if "theme/style.css" in names:
            try:
                css_text = zf.read("theme/style.css").decode("utf-8", errors="replace")
                for line in css_text.splitlines()[:30]:
                    if line.strip().lower().startswith("theme name:"):
                        theme_name = line.split(":", 1)[1].strip()
                        break
            except Exception:
                pass
    if not theme_name:
        theme_name = "unknown"

    return ThemeMetadata(
        name=theme_name,
        has_theme_json=has_theme_json,
        has_custom_css=has_custom_css,
        design_tokens=design_tokens,
    )

def _make_kb_doc(zf: zipfile.ZipFile, path: str) -> dict:
    """Create a Knowledge Base document dict from a ZIP entry."""
    try:
        content = zf.read(path).decode("utf-8", errors="replace")
    except KeyError:
        content = ""
    return {
        "content": content,
        "metadata": {"file": path},
    }

def _resolve_media_bundle_path(raw: dict[str, Any], names: set[str]) -> str:
    """Resolve a media entry to a concrete bundle path."""
    artifact = _coerce_text(
        raw.get("artifact") or raw.get("bundle_path") or raw.get("path")
    )
    if artifact:
        return artifact.lstrip("/")

    filename = _coerce_text(raw.get("filename"))
    if filename:
        direct = f"media/{filename}"
        if direct in names:
            return direct
        for candidate in names:
            if candidate.startswith("media/") and PurePosixPath(candidate).name == filename:
                return candidate
    return ""


def _expand_media_entries(
    raw: dict[str, Any],
    names: set[str],
) -> list[dict[str, Any]]:
    """Expand a media manifest row with any bundled responsive derivatives."""
    entries = [raw]
    metadata = raw.get("metadata")
    if not isinstance(metadata, dict):
        return entries

    sizes = metadata.get("sizes")
    if not isinstance(sizes, dict):
        return entries

    original_source = _coerce_text(
        raw.get("url") or raw.get("wp_src") or raw.get("source_url")
    )
    original_bundle_path = _resolve_media_bundle_path(raw, names)
    if not original_source or not original_bundle_path:
        return entries

    bundle_dir = str(PurePosixPath(original_bundle_path).parent)
    metadata_file = _coerce_text(metadata.get("file"))
    metadata_dir = (
        str(PurePosixPath(metadata_file).parent)
        if metadata_file
        else ""
    )

    for size_data in sizes.values():
        if not isinstance(size_data, dict):
            continue
        variant_name = _coerce_text(size_data.get("file"))
        if not variant_name:
            continue

        variant_candidates = [
            str(PurePosixPath(bundle_dir) / variant_name),
        ]
        if metadata_dir and metadata_dir != ".":
            variant_candidates.append(
                str(PurePosixPath("media") / metadata_dir / variant_name)
            )
        variant_bundle_path = next(
            (candidate for candidate in variant_candidates if candidate in names),
            "",
        )
        if not variant_bundle_path:
            continue

        entries.append({
            "source_url": urljoin(original_source, variant_name),
            "bundle_path": variant_bundle_path,
            "filename": variant_name,
            "metadata": size_data,
            "alt_text": raw.get("alt_text") or raw.get("alt"),
            "caption": raw.get("caption"),
            "mime_type": raw.get("mime_type"),
        })

    return entries
