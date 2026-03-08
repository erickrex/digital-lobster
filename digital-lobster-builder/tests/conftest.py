import io
import json
import zipfile

from hypothesis import strategies as st
from pydantic import SecretStr

from src.models.cms_config import CMSConfig
from src.models.content import WordPressBlock, WordPressContentItem
from src.models.deployment_report import DeploymentReport
from src.models.inventory import (
    ContentTypeSummary,
    Inventory,
    MenuSummary,
    PluginFeature,
    TaxonomySummary,
    ThemeMetadata,
)
from src.models.modeling_manifest import (
    ComponentMapping,
    ContentCollectionSchema,
    FrontmatterField,
    ModelingManifest,
    TaxonomyDefinition,
)
from src.models.migration_report import (
    ContentTypeMigrationStats,
    MediaMigrationStats,
    MigrationReport,
)
from src.models.qa_report import PageCheck, QAReport
from src.models.strapi_types import (
    ContentTypeMap,
    StrapiComponentSchema,
    StrapiContentTypeDefinition,
    StrapiFieldDefinition,
)


# Primitive helpers
_slug = st.from_regex(r"[a-z][a-z0-9\-]{1,30}", fullmatch=True)
_name = st.text(
    min_size=1, max_size=60,
    alphabet=st.characters(categories=("L", "N", "Z")),
)
_version = st.from_regex(
    r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}", fullmatch=True
)
_url = st.builds(lambda s: f"https://{s}.example.com", _slug)
_date = st.from_regex(
    r"2024\-(?:0[1-9]|1[0-2])\-(?:0[1-9]|[12][0-9]|3[01])",
    fullmatch=True,
)
_post_type = st.sampled_from([
    "post", "page", "gd_place", "product", "event", "testimonial",
])
_taxonomy = st.sampled_from([
    "category", "post_tag", "gd_placecategory", "product_cat", "genre",
])
_block_name = st.sampled_from([
    "core/paragraph", "core/heading", "core/image", "core/list",
    "core/code", "core/quote", "core/gallery", "core/columns",
    "kadence/rowlayout", "forminator/form", "geodir/listing",
])
_field_type = st.sampled_from([
    "string", "number", "boolean", "date", "reference", "list",
])
_hydration = st.sampled_from([
    "client:load", "client:idle", "client:visible", None,
])
_plugin_family = st.sampled_from([
    "geodirectory", "kadence", "forminator", "yoast", None,
])


# ---------------------------------------------------------------------------
# Strategy: plugin_fingerprints
# ---------------------------------------------------------------------------

@st.composite
def plugin_fingerprints(draw):
    """Generate random PluginFeature instances."""
    return PluginFeature(
        slug=draw(_slug),
        name=draw(_name),
        version=draw(_version),
        family=draw(_plugin_family),
        custom_post_types=draw(st.lists(_post_type, max_size=3)),
        custom_taxonomies=draw(st.lists(_taxonomy, max_size=3)),
        detected_features=draw(st.lists(_slug, max_size=5)),
    )


# ---------------------------------------------------------------------------
# Strategy: inventories
# ---------------------------------------------------------------------------

@st.composite
def inventories(draw):
    """Generate random Inventory instances."""
    plugins = draw(st.lists(plugin_fingerprints(), min_size=0, max_size=5))
    content_types = draw(st.lists(
        st.builds(
            ContentTypeSummary,
            post_type=_post_type,
            count=st.integers(min_value=0, max_value=5000),
            custom_fields=st.lists(_slug, max_size=5),
            taxonomies=st.lists(_taxonomy, max_size=3),
            sample_slugs=st.lists(_slug, max_size=3),
        ),
        min_size=1,
        max_size=6,
    ))
    taxonomies = draw(st.lists(
        st.builds(
            TaxonomySummary,
            taxonomy=_taxonomy,
            term_count=st.integers(min_value=0, max_value=500),
            associated_post_types=st.lists(_post_type, max_size=3),
        ),
        max_size=5,
    ))
    menus = draw(st.lists(
        st.builds(
            MenuSummary,
            name=_name,
            location=st.sampled_from([
                "primary", "footer", "sidebar", "mobile",
            ]),
            item_count=st.integers(min_value=1, max_value=50),
        ),
        max_size=4,
    ))
    theme = draw(st.builds(
        ThemeMetadata,
        name=_name,
        has_theme_json=st.booleans(),
        has_custom_css=st.booleans(),
        design_tokens=st.none(),
    ))
    return Inventory(
        site_url=draw(_url),
        site_name=draw(_name),
        wordpress_version=draw(_version),
        content_types=content_types,
        plugins=plugins,
        taxonomies=taxonomies,
        menus=menus,
        theme=theme,
        has_html_snapshots=draw(st.booleans()),
        has_media_manifest=draw(st.booleans()),
        has_redirect_rules=draw(st.booleans()),
        has_seo_data=draw(st.booleans()),
    )


# ---------------------------------------------------------------------------
# Strategy: wordpress_content_items
# ---------------------------------------------------------------------------

@st.composite
def wordpress_content_items(draw):
    """Generate random WordPressContentItem instances with blocks, special chars, media refs, SEO."""
    blocks = draw(st.lists(
        st.builds(
            WordPressBlock,
            name=_block_name,
            attrs=st.fixed_dictionaries({}, optional={
                "level": st.integers(min_value=1, max_value=6),
                "align": st.sampled_from(["left", "center", "right"]),
            }),
            html=st.text(min_size=1, max_size=200, alphabet=st.characters(
                categories=("L", "N", "P", "Z"),
            )),
        ),
        min_size=1,
        max_size=10,
    ))
    seo = draw(st.one_of(
        st.none(),
        st.fixed_dictionaries({
            "title": _name,
            "description": st.text(min_size=0, max_size=160),
        }),
    ))
    featured = draw(st.one_of(
        st.none(),
        st.fixed_dictionaries({
            "url": _url,
            "alt": _name,
        }),
    ))
    return WordPressContentItem(
        id=draw(st.integers(min_value=1, max_value=999999)),
        post_type=draw(_post_type),
        title=draw(_name),
        slug=draw(_slug),
        status=draw(st.sampled_from(["publish", "draft", "private"])),
        date=draw(_date),
        excerpt=draw(st.one_of(st.none(), st.text(max_size=300))),
        blocks=blocks,
        raw_html=draw(st.text(min_size=1, max_size=500)),
        taxonomies=draw(st.fixed_dictionaries({}, optional={
            "category": st.lists(_name, max_size=3),
            "post_tag": st.lists(_name, max_size=5),
        })),
        meta=draw(st.dictionaries(
            keys=_slug, values=st.text(max_size=100), max_size=5,
        )),
        featured_media=featured,
        legacy_permalink=draw(st.builds(
            lambda s: f"/{s}/", _slug,
        )),
        seo=seo,
    )


# ---------------------------------------------------------------------------
# Strategy: modeling_manifests
# ---------------------------------------------------------------------------

@st.composite
def modeling_manifests(draw):
    """Generate random ModelingManifest instances."""
    collections = draw(st.lists(
        st.builds(
            ContentCollectionSchema,
            collection_name=_slug,
            source_post_type=_post_type,
            frontmatter_fields=st.lists(
                st.builds(
                    FrontmatterField,
                    name=_slug,
                    type=_field_type,
                    required=st.booleans(),
                    description=st.text(max_size=100),
                ),
                min_size=1,
                max_size=8,
            ),
            route_pattern=st.builds(lambda s: f"/{s}/[slug]", _slug),
        ),
        min_size=1,
        max_size=5,
    ))
    components = draw(st.lists(
        st.builds(
            ComponentMapping,
            wp_block_type=_block_name,
            astro_component=st.builds(lambda s: f"{s.title().replace('-', '')}Block", _slug),
            is_island=st.booleans(),
            hydration_directive=_hydration,
            props=st.just([]),
            fallback=st.booleans(),
        ),
        min_size=1,
        max_size=10,
    ))
    taxonomies = draw(st.lists(
        st.builds(
            TaxonomyDefinition,
            taxonomy=_taxonomy,
            collection_ref=st.one_of(st.none(), _slug),
            data_file=st.one_of(st.none(), st.builds(lambda s: f"src/data/{s}.json", _slug)),
        ),
        max_size=5,
    ))
    return ModelingManifest(
        collections=collections,
        components=components,
        taxonomies=taxonomies,
    )


# ---------------------------------------------------------------------------
# Strategy: theme_json_tokens
# ---------------------------------------------------------------------------

@st.composite
def theme_json_tokens(draw):
    """Generate random design token sets resembling theme.json settings."""
    colors = draw(st.lists(
        st.fixed_dictionaries({
            "slug": _slug,
            "color": st.from_regex(r"#[0-9a-f]{6}", fullmatch=True),
            "name": _name,
        }),
        min_size=1,
        max_size=10,
    ))
    font_sizes = draw(st.lists(
        st.fixed_dictionaries({
            "slug": _slug,
            "size": st.builds(lambda n: f"{n}px", st.integers(min_value=10, max_value=72)),
            "name": _name,
        }),
        max_size=6,
    ))
    spacing = draw(st.lists(
        st.fixed_dictionaries({
            "slug": _slug,
            "size": st.builds(lambda n: f"{n}rem", st.floats(min_value=0.25, max_value=8.0, allow_nan=False, allow_infinity=False)),
            "name": _name,
        }),
        max_size=8,
    ))
    return {
        "settings": {
            "color": {"palette": colors},
            "typography": {"fontSizes": font_sizes},
            "spacing": {"spacingSizes": spacing},
        }
    }


# ---------------------------------------------------------------------------
# Strategy: menu_definitions
# ---------------------------------------------------------------------------

@st.composite
def menu_definitions(draw):
    """Generate random menu structures with nesting."""
    def _menu_item(depth=0):
        children_st = st.just([]) if depth >= 2 else st.lists(
            st.builds(
                lambda: draw(_menu_item_flat()),
            ),
            max_size=3,
        )
        return st.fixed_dictionaries({
            "title": _name,
            "url": st.builds(lambda s: f"/{s}/", _slug),
            "target": st.sampled_from(["_self", "_blank"]),
            "children": st.just([]),
        })

    @st.composite
    def _menu_item_flat(draw_inner):
        return {
            "title": draw_inner(_name),
            "url": draw_inner(st.builds(lambda s: f"/{s}/", _slug)),
            "target": draw_inner(st.sampled_from(["_self", "_blank"])),
            "children": draw_inner(st.lists(
                st.fixed_dictionaries({
                    "title": _name,
                    "url": st.builds(lambda s: f"/{s}/", _slug),
                    "target": st.sampled_from(["_self", "_blank"]),
                    "children": st.just([]),
                }),
                max_size=3,
            )),
        }

    items = draw(st.lists(_menu_item_flat(), min_size=1, max_size=8))
    return {
        "name": draw(_name),
        "location": draw(st.sampled_from(["primary", "footer", "sidebar", "mobile"])),
        "items": items,
    }


# ---------------------------------------------------------------------------
# Strategy: redirect_rules
# ---------------------------------------------------------------------------

@st.composite
def redirect_rules(draw):
    """Generate random redirect rule sets."""
    rules = draw(st.lists(
        st.fixed_dictionaries({
            "source": st.builds(lambda s: f"/{s}/", _slug),
            "target": st.builds(lambda s: f"/{s}/", _slug),
            "status_code": st.sampled_from([301, 302, 307, 308]),
            "regex": st.booleans(),
        }),
        min_size=1,
        max_size=20,
    ))
    return rules


# ---------------------------------------------------------------------------
# Strategy: qa_check_results
# ---------------------------------------------------------------------------

@st.composite
def qa_check_results(draw):
    """Generate random QA check results (QAReport instances)."""
    pages = draw(st.lists(
        st.builds(
            PageCheck,
            url=st.builds(lambda s: f"/{s}/", _slug),
            http_status=st.one_of(st.none(), st.sampled_from([200, 404, 500])),
            visual_parity_score=st.one_of(
                st.none(),
                st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            ),
            accessibility_issues=st.lists(st.text(min_size=1, max_size=100), max_size=5),
            passed=st.booleans(),
        ),
        min_size=1,
        max_size=10,
    ))
    total_passed = sum(1 for p in pages if p.passed)
    total_failed = len(pages) - total_passed
    return QAReport(
        build_success=draw(st.booleans()),
        build_errors=draw(st.lists(st.text(min_size=1, max_size=200), max_size=5)),
        pages_checked=pages,
        total_passed=total_passed,
        total_failed=total_failed,
        warnings=draw(st.lists(st.text(min_size=1, max_size=200), max_size=10)),
    )


# ---------------------------------------------------------------------------
# Strategy: export_bundles
# ---------------------------------------------------------------------------

_REQUIRED_FILES = [
    "MANIFEST.json",
    "site/site_info.json",
]
_OPTIONAL_FILES = [
    "theme/theme.json",
    "theme/style.css",
    "content/posts.json",
    "content/pages.json",
    "content/gd_places.json",
    "menus/primary.json",
    "menus/footer.json",
    "media/media_manifest.json",
    "redirects/redirects.json",
    "seo/yoast_meta.json",
    "snapshots/home.html",
    "snapshots/sample-post.html",
]


@st.composite
def export_bundles(draw):
    """Generate random ZIP archives with varying required/optional files.

    Returns a tuple of (bytes, included_files) where bytes is the ZIP content
    and included_files is the list of file paths in the archive.
    """
    include_required = draw(st.booleans())
    files_to_include = []

    if include_required:
        files_to_include.extend(_REQUIRED_FILES)

    optional = draw(st.lists(
        st.sampled_from(_OPTIONAL_FILES),
        min_size=0,
        max_size=len(_OPTIONAL_FILES),
        unique=True,
    ))
    files_to_include.extend(optional)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fpath in files_to_include:
            if fpath == "MANIFEST.json":
                content = json.dumps({
                    "export_version": "1.0.0",
                    "site_url": "https://example.com",
                    "export_date": "2024-01-15",
                    "wordpress_version": "6.4.2",
                    "total_files": len(files_to_include),
                    "total_size_bytes": 1024,
                    "files": {"content": 2, "theme": 1},
                })
            elif fpath == "site/site_info.json":
                content = json.dumps({
                    "name": draw(_name),
                    "url": "https://example.com",
                    "version": "6.4.2",
                })
            else:
                content = json.dumps({"placeholder": True})
            zf.writestr(fpath, content)

    return buf.getvalue(), files_to_include


# ---------------------------------------------------------------------------
# Primitive helpers for CMS strategies
# ---------------------------------------------------------------------------

_ip_address = st.builds(
    lambda a, b, c, d: f"{a}.{b}.{c}.{d}",
    st.integers(min_value=1, max_value=254),
    st.integers(min_value=0, max_value=255),
    st.integers(min_value=0, max_value=255),
    st.integers(min_value=1, max_value=254),
)
_email = st.builds(lambda s: f"{s}@example.com", _slug)
_do_region = st.sampled_from(["nyc1", "nyc3", "sfo3", "ams3", "lon1", "sgp1"])
_droplet_size = st.sampled_from([
    "s-2vcpu-4gb", "s-4vcpu-8gb", "s-2vcpu-2gb",
])
_strapi_field_type = st.sampled_from([
    "text", "integer", "boolean", "datetime", "relation", "json",
])
_relation_type = st.sampled_from([
    "manyToMany", "oneToMany", "manyToOne", "oneToOne",
])
_mime_type = st.sampled_from([
    "image/jpeg", "image/png", "image/webp", "image/gif",
    "application/pdf", "video/mp4",
])


# ---------------------------------------------------------------------------
# Strategy: cms_configs
# ---------------------------------------------------------------------------

@st.composite
def cms_configs(draw):
    """Generate random CMSConfig instances."""
    return CMSConfig(
        domain_name=draw(st.builds(lambda s: f"{s}.example.com", _slug)),
        droplet_region=draw(_do_region),
        droplet_size=draw(_droplet_size),
        ssh_public_key=draw(st.builds(lambda s: f"ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA{s}", _slug)),
        ssh_private_key_path=draw(st.builds(lambda s: f"/home/user/.ssh/{s}", _slug)),
        do_token=SecretStr(draw(st.text(min_size=20, max_size=40, alphabet="abcdef0123456789"))),
        strapi_admin_email=draw(_email),
        strapi_admin_password=SecretStr(draw(st.text(min_size=8, max_size=30, alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#"))),
        terraform_state_path=draw(st.builds(lambda s: f"./{s}.tfstate", _slug)),
    )


# ---------------------------------------------------------------------------
# Strategy: strapi_field_definitions
# ---------------------------------------------------------------------------

@st.composite
def strapi_field_definitions(draw):
    """Generate random StrapiFieldDefinition instances."""
    strapi_type = draw(_strapi_field_type)
    relation_target = None
    relation_type_val = None
    if strapi_type == "relation":
        relation_target = draw(st.builds(lambda s: f"api::{s}.{s}", _slug))
        relation_type_val = draw(_relation_type)
    return StrapiFieldDefinition(
        name=draw(_slug),
        strapi_type=strapi_type,
        required=draw(st.booleans()),
        relation_target=relation_target,
        relation_type=relation_type_val,
    )


# ---------------------------------------------------------------------------
# Strategy: content_type_maps
# ---------------------------------------------------------------------------

@st.composite
def content_type_maps(draw):
    """Generate random ContentTypeMap instances."""
    num_mappings = draw(st.integers(min_value=1, max_value=5))
    mapping_keys = draw(st.lists(_slug, min_size=num_mappings, max_size=num_mappings, unique=True))
    mappings = {k: draw(st.builds(lambda s: f"api::{s}.{s}", _slug)) for k in mapping_keys}

    num_tax = draw(st.integers(min_value=0, max_value=3))
    tax_keys = draw(st.lists(_taxonomy, min_size=num_tax, max_size=num_tax, unique=True))
    taxonomy_mappings = {k: draw(st.builds(lambda s: f"api::{s}.{s}", _slug)) for k in tax_keys}

    component_uids = draw(st.lists(
        st.builds(lambda s: f"shared.{s}", _slug),
        max_size=3,
    ))
    return ContentTypeMap(
        mappings=mappings,
        taxonomy_mappings=taxonomy_mappings,
        component_uids=component_uids,
    )


# ---------------------------------------------------------------------------
# Strategy: migration_reports
# ---------------------------------------------------------------------------

@st.composite
def migration_reports(draw):
    """Generate random MigrationReport instances with consistent count invariants.

    Invariants enforced:
    - For each ContentTypeMigrationStats: total == succeeded + failed + skipped
    - total_entries_succeeded == sum(s.succeeded for s in content_stats)
    - total_entries_failed == sum(s.failed for s in content_stats)
    - total_entries_skipped == sum(s.skipped for s in content_stats)
    """
    num_types = draw(st.integers(min_value=1, max_value=5))
    content_stats = []
    for _ in range(num_types):
        succeeded = draw(st.integers(min_value=0, max_value=100))
        failed = draw(st.integers(min_value=0, max_value=20))
        skipped = draw(st.integers(min_value=0, max_value=10))
        total = succeeded + failed + skipped
        failed_entries = draw(st.lists(
            _name, min_size=failed, max_size=failed,
        )) if failed > 0 else []
        content_stats.append(ContentTypeMigrationStats(
            content_type=draw(_slug),
            total=total,
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
            failed_entries=failed_entries,
        ))

    media_succeeded = draw(st.integers(min_value=0, max_value=200))
    media_failed = draw(st.integers(min_value=0, max_value=20))
    media_failed_urls = draw(st.lists(
        _url, min_size=media_failed, max_size=media_failed,
    )) if media_failed > 0 else []
    media_stats = MediaMigrationStats(
        total=media_succeeded + media_failed,
        succeeded=media_succeeded,
        failed=media_failed,
        failed_urls=media_failed_urls,
    )

    return MigrationReport(
        content_stats=content_stats,
        media_stats=media_stats,
        taxonomy_terms_created=draw(st.integers(min_value=0, max_value=100)),
        menu_entries_created=draw(st.integers(min_value=0, max_value=20)),
        total_entries_succeeded=sum(s.succeeded for s in content_stats),
        total_entries_failed=sum(s.failed for s in content_stats),
        total_entries_skipped=sum(s.skipped for s in content_stats),
        warnings=draw(st.lists(st.text(min_size=1, max_size=200), max_size=5)),
    )


# ---------------------------------------------------------------------------
# Strategy: deployment_reports
# ---------------------------------------------------------------------------

@st.composite
def deployment_reports(draw):
    """Generate random DeploymentReport instances."""
    domain = draw(st.builds(lambda s: f"{s}.example.com", _slug))
    return DeploymentReport(
        live_site_url=f"https://{domain}",
        strapi_admin_url=f"https://{domain}/admin",
        droplet_ip=draw(_ip_address),
        deployment_timestamp=draw(_date) + "T12:00:00Z",
        build_duration_seconds=draw(st.floats(min_value=1.0, max_value=600.0, allow_nan=False, allow_infinity=False)),
        files_deployed=draw(st.integers(min_value=1, max_value=5000)),
        homepage_status=draw(st.sampled_from([200, 301, 404, 500])),
        sample_page_status=draw(st.sampled_from([200, 301, 404, 500])),
        webhook_registered=draw(st.booleans()),
    )


# ---------------------------------------------------------------------------
# Strategy: wordpress_blocks (standalone for CMS property tests)
# ---------------------------------------------------------------------------

@st.composite
def wordpress_blocks(draw):
    """Generate random WordPressBlock instances."""
    return WordPressBlock(
        name=draw(_block_name),
        attrs=draw(st.fixed_dictionaries({}, optional={
            "level": st.integers(min_value=1, max_value=6),
            "align": st.sampled_from(["left", "center", "right"]),
            "className": st.builds(lambda s: f"wp-block-{s}", _slug),
        })),
        html=draw(st.text(min_size=1, max_size=200, alphabet=st.characters(
            categories=("L", "N", "P", "Z"),
        ))),
    )


# ---------------------------------------------------------------------------
# Strategy: media_manifests
# ---------------------------------------------------------------------------

@st.composite
def media_manifests(draw):
    """Generate random media manifest lists (list of dicts with media metadata)."""
    return draw(st.lists(
        st.fixed_dictionaries({
            "url": _url,
            "filename": st.builds(lambda s, ext: f"{s}.{ext}", _slug, st.sampled_from(["jpg", "png", "webp", "gif", "pdf"])),
            "alt_text": _name,
            "caption": st.text(min_size=0, max_size=200),
            "mime_type": _mime_type,
        }),
        min_size=1,
        max_size=20,
    ))


# ---------------------------------------------------------------------------
# Production pipeline model imports
# ---------------------------------------------------------------------------

from src.models.finding import Finding, FindingSeverity
from src.models.capability_manifest import Capability, CapabilityManifest
from src.models.bundle_manifest import BundleManifest
from src.models.bundle_artifacts import (
    ContentRelationship,
    ContentRelationshipsArtifact,
    EditorialWorkflowsArtifact,
    FieldUsageEntry,
    FieldUsageReportArtifact,
    IntegrationEntry,
    IntegrationManifestArtifact,
    PageCompositionEntry,
    PageCompositionArtifact,
    PluginInstance,
    PluginInstancesArtifact,
    PluginTableExport,
    SearchConfigArtifact,
    SeoPageEntry,
    SeoFullArtifact,
)
from src.models.content_model_manifest import (
    ContentModelManifest,
    SeoComponentStrategy,
    StrapiCollection,
    StrapiComponent,
    StrapiRelation,
    ValidationHint,
)
from src.models.presentation_manifest import (
    FallbackZone,
    LayoutDefinition,
    PresentationManifest,
    RouteTemplate,
    SectionDefinition,
)
from src.models.behavior_manifest import (
    BehaviorManifest,
    FormStrategy,
    IntegrationBoundary,
    RedirectRule,
    SearchStrategy,
)
from src.models.migration_mapping_manifest import (
    FieldMapping,
    MediaMappingStrategy,
    MigrationMappingManifest,
    PluginInstanceMapping,
    RelationMapping,
    TemplateMapping,
    TermMapping,
    TypeMapping,
)
from src.models.parity_report import ParityReport, SnapshotComparison, PARITY_CATEGORIES
from src.models.readiness_report import ReadinessReport


# ---------------------------------------------------------------------------
# Primitive helpers for production pipeline strategies
# ---------------------------------------------------------------------------

_finding_stage = st.sampled_from([
    "blueprint_intake", "qualification", "capability_resolution",
    "schema_compiler", "presentation_compiler", "behavior_compiler",
    "content_migrator", "parity_qa",
])
_capability_type = st.sampled_from([
    "content_model", "seo", "widget", "form", "shortcode",
    "search_filter", "integration", "editorial", "template",
])
_classification = st.sampled_from([
    "strapi_native", "astro_runtime", "unsupported",
])
_source_system = st.sampled_from([
    "acf", "pods", "meta_box", "carbon_fields", "core",
])
_inferred_type = st.sampled_from([
    "text", "number", "boolean", "date", "reference",
    "repeater", "flexible", "object", "enum",
])
_cardinality = st.sampled_from(["single", "multiple"])
_behaves_as = st.sampled_from([
    None, "enum", "reference", "repeater", "object", "flexible",
])
_instance_type = st.sampled_from([
    "form", "directory", "filter", "cta", "seo_object",
    "widget", "singleton",
])
_relation_type_str = st.sampled_from([
    "post_to_post", "post_to_term", "post_to_media",
    "post_to_user", "plugin_entity",
])
_seo_plugin = st.sampled_from(["yoast", "rank_math", "aioseo"])
_authoring_model = st.sampled_from(["single_editor", "two_editor"])
_integration_type = st.sampled_from([
    "form_destination", "webhook", "crm", "embed",
    "runtime_api", "third_party_script",
])
_disposition = st.sampled_from(["rebuild", "proxy", "drop"])
_target_system = st.sampled_from(["strapi", "astro", "external"])
_form_target = st.sampled_from([
    "strapi_collection", "astro_api_route", "external_proxy",
])
_search_impl = st.sampled_from([
    "strapi_filter", "astro_search", "external",
])
_strapi_relation = st.sampled_from([
    "oneToOne", "oneToMany", "manyToMany", "manyToOne",
])
_section_source_type = st.sampled_from([
    "widget", "sidebar", "block", "plugin_component",
])
_transform = st.sampled_from([
    None, "direct", "component", "dynamic_zone", "json",
])
_migration_strategy = st.sampled_from([
    "collection", "singleton", "component", "skip",
])
_parity_score = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)


# ---------------------------------------------------------------------------
# Strategy: findings
# ---------------------------------------------------------------------------

@st.composite
def findings(draw):
    """Generate random Finding instances."""
    return Finding(
        severity=draw(st.sampled_from(list(FindingSeverity))),
        stage=draw(_finding_stage),
        construct=draw(_slug),
        message=draw(_name),
        recommended_action=draw(_name),
    )


# ---------------------------------------------------------------------------
# Strategy: capabilities
# ---------------------------------------------------------------------------

@st.composite
def capabilities(draw):
    """Generate random Capability instances."""
    return Capability(
        capability_type=draw(_capability_type),
        source_plugin=draw(st.one_of(st.none(), _slug)),
        classification=draw(_classification),
        confidence=draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)),
        details=draw(st.fixed_dictionaries({}, optional={"note": _name})),
        findings=draw(st.lists(findings(), max_size=2)),
    )


# ---------------------------------------------------------------------------
# Strategy: capability_manifests
# ---------------------------------------------------------------------------

@st.composite
def capability_manifests(draw):
    """Generate random CapabilityManifest instances."""
    caps = draw(st.lists(capabilities(), max_size=5))
    return CapabilityManifest(
        capabilities=caps,
        findings=draw(st.lists(findings(), max_size=3)),
        content_model_capabilities=draw(st.lists(capabilities(), max_size=2)),
        presentation_capabilities=draw(st.lists(capabilities(), max_size=2)),
        behavior_capabilities=draw(st.lists(capabilities(), max_size=2)),
        plugin_capabilities=draw(st.dictionaries(
            keys=_slug, values=st.lists(capabilities(), max_size=2), max_size=2,
        )),
    )


# ---------------------------------------------------------------------------
# Strategy: bundle_manifests
# ---------------------------------------------------------------------------

@st.composite
def bundle_manifests(draw):
    """Generate random BundleManifest instances with all 23 existing + 9 new artifacts."""
    empty_dict = st.just({})
    empty_list_of_dicts = st.just([])

    # New CMS artifact sub-models
    content_rels = ContentRelationshipsArtifact(
        schema_version=draw(_version),
        relationships=draw(st.lists(
            st.builds(
                ContentRelationship,
                source_id=_slug,
                target_id=_slug,
                relation_type=_relation_type_str,
                source_plugin=st.one_of(st.none(), _slug),
            ),
            max_size=5,
        )),
    )
    field_usage = FieldUsageReportArtifact(
        schema_version=draw(_version),
        fields=draw(st.lists(
            st.builds(
                FieldUsageEntry,
                post_type=_post_type,
                field_name=_slug,
                source_plugin=st.one_of(st.none(), _slug),
                source_system=_source_system,
                inferred_type=_inferred_type,
                nullable=st.booleans(),
                cardinality=_cardinality,
                distinct_value_count=st.integers(min_value=0, max_value=100),
                sample_values=st.just([]),
                behaves_as=_behaves_as,
            ),
            max_size=5,
        )),
    )
    plugin_insts = PluginInstancesArtifact(
        schema_version=draw(_version),
        instances=draw(st.lists(
            st.builds(
                PluginInstance,
                instance_id=_slug,
                source_plugin=_slug,
                instance_type=_instance_type,
            ),
            max_size=3,
        )),
    )
    page_comp = PageCompositionArtifact(
        schema_version=draw(_version),
        pages=draw(st.lists(
            st.builds(
                PageCompositionEntry,
                canonical_url=_url,
                template=_slug,
                blocks=st.just([]),
                shortcodes=st.just([]),
                widget_placements=st.just([]),
                forms_embedded=st.just([]),
                plugin_components=st.just([]),
                enqueued_assets=st.just([]),
                content_sections=st.just([]),
                snapshot_ref=st.one_of(st.none(), _slug),
            ),
            max_size=3,
        )),
    )
    seo = SeoFullArtifact(
        schema_version=draw(_version),
        pages=draw(st.lists(
            st.builds(
                SeoPageEntry,
                canonical_url=_url,
                source_plugin=_seo_plugin,
            ),
            max_size=3,
        )),
    )
    editorial = draw(st.builds(
        EditorialWorkflowsArtifact,
        schema_version=_version,
        statuses_in_use=st.just(["publish", "draft"]),
        scheduled_publishing=st.booleans(),
        draft_behavior=st.sampled_from(["standard", "auto_save"]),
        preview_expectations=st.sampled_from(["live_preview", "manual_refresh"]),
        revision_policy=st.sampled_from(["keep_all", "limit_10", "none"]),
        comments_enabled=st.booleans(),
        authoring_model=_authoring_model,
    ))
    table_exports = draw(st.lists(
        st.builds(
            PluginTableExport,
            table_name=_slug,
            schema_version=_version,
            source_plugin=_slug,
            row_count=st.integers(min_value=0, max_value=100),
            primary_key=st.just("id"),
            foreign_key_candidates=st.just([]),
            rows=st.just([]),
        ),
        max_size=2,
    ))
    search_cfg = draw(st.builds(
        SearchConfigArtifact,
        schema_version=_version,
        searchable_types=st.just(["post", "page"]),
        ranking_hints=st.just([]),
        facets=st.just([]),
    ))
    integration = IntegrationManifestArtifact(
        schema_version=draw(_version),
        integrations=draw(st.lists(
            st.builds(
                IntegrationEntry,
                integration_id=_slug,
                integration_type=_integration_type,
                target=_url,
                business_critical=st.booleans(),
            ),
            max_size=3,
        )),
    )

    return BundleManifest(
        schema_version=draw(_version),
        site_url=draw(_url),
        site_name=draw(_name),
        wordpress_version=draw(_version),
        # 23 existing artifacts as dicts/lists
        site_blueprint=draw(empty_dict),
        site_settings=draw(empty_dict),
        site_options=draw(empty_dict),
        site_environment=draw(empty_dict),
        taxonomies=draw(empty_dict),
        menus=draw(empty_list_of_dicts),
        media_map=draw(empty_list_of_dicts),
        theme_mods=draw(empty_dict),
        global_styles=draw(empty_dict),
        customizer_settings=draw(empty_dict),
        css_sources=draw(empty_dict),
        plugins_fingerprint=draw(empty_dict),
        plugin_behaviors=draw(empty_dict),
        blocks_usage=draw(empty_dict),
        block_patterns=draw(empty_dict),
        acf_field_groups=draw(empty_dict),
        custom_fields_config=draw(empty_dict),
        shortcodes_inventory=draw(empty_dict),
        forms_config=draw(empty_dict),
        widgets=draw(empty_dict),
        page_templates=draw(empty_dict),
        rewrite_rules=draw(empty_dict),
        rest_api_endpoints=draw(empty_dict),
        hooks_registry=draw(empty_dict),
        error_log=draw(empty_dict),
        # 9 new CMS artifacts
        content_relationships=content_rels,
        field_usage_report=field_usage,
        plugin_instances=plugin_insts,
        page_composition=page_comp,
        seo_full=seo,
        editorial_workflows=editorial,
        plugin_table_exports=table_exports,
        search_config=search_cfg,
        integration_manifest=integration,
    )


# ---------------------------------------------------------------------------
# Strategy: content_model_manifests
# ---------------------------------------------------------------------------

@st.composite
def content_model_manifests(draw):
    """Generate random ContentModelManifest instances."""
    fields_st = st.lists(strapi_field_definitions(), min_size=1, max_size=4)

    collections = draw(st.lists(
        st.builds(
            StrapiCollection,
            display_name=_name,
            singular_name=_slug,
            plural_name=_slug,
            api_id=st.builds(lambda s: f"api::{s}.{s}", _slug),
            fields=fields_st,
            components=st.lists(st.builds(lambda s: f"shared.{s}", _slug), max_size=2),
            source_post_type=st.one_of(st.none(), _post_type),
            source_plugin=st.one_of(st.none(), _slug),
        ),
        min_size=1,
        max_size=4,
    ))
    components = draw(st.lists(
        st.builds(
            StrapiComponent,
            uid=st.builds(lambda s: f"shared.{s}", _slug),
            display_name=_name,
            category=st.sampled_from(["shared", "seo", "layout"]),
            fields=fields_st,
        ),
        max_size=3,
    ))
    relations = draw(st.lists(
        st.builds(
            StrapiRelation,
            source_collection=st.builds(lambda s: f"api::{s}.{s}", _slug),
            target_collection=st.builds(lambda s: f"api::{s}.{s}", _slug),
            field_name=_slug,
            relation_type=_strapi_relation,
            source_relationship_id=_slug,
        ),
        max_size=3,
    ))
    seo_strategy = draw(st.one_of(
        st.none(),
        st.builds(
            SeoComponentStrategy,
            component_uid=st.builds(lambda s: f"shared.{s}", _slug),
            fields=fields_st,
            applied_to=st.lists(st.builds(lambda s: f"api::{s}.{s}", _slug), min_size=1, max_size=3),
        ),
    ))
    validation_hints = draw(st.lists(
        st.builds(
            ValidationHint,
            collection_api_id=st.builds(lambda s: f"api::{s}.{s}", _slug),
            field_name=_slug,
            nullable=st.booleans(),
            cardinality=_cardinality,
            enum_values=st.one_of(st.none(), st.lists(_slug, min_size=1, max_size=4)),
        ),
        max_size=4,
    ))
    return ContentModelManifest(
        collections=collections,
        components=components,
        relations=relations,
        seo_strategy=seo_strategy,
        validation_hints=validation_hints,
    )


# ---------------------------------------------------------------------------
# Strategy: presentation_manifests
# ---------------------------------------------------------------------------

@st.composite
def presentation_manifests(draw):
    """Generate random PresentationManifest instances."""
    layouts = draw(st.lists(
        st.builds(
            LayoutDefinition,
            name=_slug,
            template_path=st.builds(lambda s: f"src/layouts/{s}.astro", _slug),
            shared_sections=st.lists(_slug, max_size=3),
        ),
        min_size=1,
        max_size=3,
    ))
    route_templates = draw(st.lists(
        st.builds(
            RouteTemplate,
            route_pattern=st.builds(lambda s: f"/{s}/[slug]", _slug),
            layout=_slug,
            source_template=_slug,
            content_collection=st.one_of(st.none(), _slug),
        ),
        max_size=4,
    ))
    sections = draw(st.lists(
        st.builds(
            SectionDefinition,
            name=_slug,
            source_type=_section_source_type,
            source_plugin=st.one_of(st.none(), _slug),
            component_path=st.builds(lambda s: f"src/components/{s}.astro", _slug),
        ),
        max_size=4,
    ))
    fallback_zones = draw(st.lists(
        st.builds(
            FallbackZone,
            page_url=_url,
            zone_name=_slug,
            raw_html=st.text(min_size=1, max_size=100, alphabet=st.characters(categories=("L", "N", "P", "Z"))),
            reason=_name,
        ),
        max_size=3,
    ))
    return PresentationManifest(
        layouts=layouts,
        route_templates=route_templates,
        sections=sections,
        fallback_zones=fallback_zones,
        style_tokens=draw(st.fixed_dictionaries({}, optional={"primary_color": _slug})),
    )


# ---------------------------------------------------------------------------
# Strategy: behavior_manifests
# ---------------------------------------------------------------------------

@st.composite
def behavior_manifests(draw):
    """Generate random BehaviorManifest instances."""
    redirects = draw(st.lists(
        st.builds(
            RedirectRule,
            source_url=st.builds(lambda s: f"/{s}/", _slug),
            target_url=st.builds(lambda s: f"/{s}/", _slug),
            status_code=st.sampled_from([301, 302, 307, 308]),
            source_plugin=st.one_of(st.none(), _slug),
        ),
        max_size=5,
    ))
    forms = draw(st.lists(
        st.builds(
            FormStrategy,
            form_id=_slug,
            source_plugin=st.sampled_from(["contact_form_7", "wpforms", "gravity_forms", "ninja_forms"]),
            target=_form_target,
            fields=st.just([{"name": "email", "type": "email"}]),
            submission_destination=_url,
        ),
        max_size=3,
    ))
    search = draw(st.one_of(
        st.none(),
        st.builds(
            SearchStrategy,
            enabled=st.booleans(),
            searchable_collections=st.lists(_slug, min_size=1, max_size=3),
            facets=st.just([]),
            implementation=_search_impl,
        ),
    ))
    boundaries = draw(st.lists(
        st.builds(
            IntegrationBoundary,
            integration_id=_slug,
            disposition=_disposition,
            target_system=_target_system,
        ),
        max_size=3,
    ))
    return BehaviorManifest(
        redirects=redirects,
        metadata_strategy=draw(st.fixed_dictionaries({}, optional={"strategy": _slug})),
        forms_strategy=forms,
        preview_rules=draw(st.fixed_dictionaries({}, optional={"enabled": st.booleans()})),
        search_strategy=search,
        integration_boundaries=boundaries,
        unsupported_constructs=draw(st.lists(findings(), max_size=2)),
    )


# ---------------------------------------------------------------------------
# Strategy: migration_mapping_manifests
# ---------------------------------------------------------------------------

@st.composite
def migration_mapping_manifests(draw):
    """Generate random MigrationMappingManifest instances."""
    return MigrationMappingManifest(
        type_mappings=draw(st.lists(
            st.builds(
                TypeMapping,
                source_post_type=_post_type,
                target_api_id=st.builds(lambda s: f"api::{s}.{s}", _slug),
                source_plugin=st.one_of(st.none(), _slug),
            ),
            min_size=1,
            max_size=4,
        )),
        field_mappings=draw(st.lists(
            st.builds(
                FieldMapping,
                source_post_type=_post_type,
                source_field=_slug,
                target_api_id=st.builds(lambda s: f"api::{s}.{s}", _slug),
                target_field=_slug,
                transform=_transform,
            ),
            max_size=5,
        )),
        relation_mappings=draw(st.lists(
            st.builds(
                RelationMapping,
                source_relationship_id=_slug,
                source_collection=st.builds(lambda s: f"api::{s}.{s}", _slug),
                target_collection=st.builds(lambda s: f"api::{s}.{s}", _slug),
                target_field=_slug,
                relation_type=_strapi_relation,
            ),
            max_size=3,
        )),
        media_mapping_strategy=draw(st.builds(
            MediaMappingStrategy,
            url_rewrite_pattern=st.just("/uploads/{filename}"),
            relation_aware=st.booleans(),
            preserve_alt_text=st.booleans(),
            preserve_caption=st.booleans(),
        )),
        term_mappings=draw(st.lists(
            st.builds(
                TermMapping,
                source_taxonomy=_taxonomy,
                target_api_id=st.builds(lambda s: f"api::{s}.{s}", _slug),
                target_field=_slug,
            ),
            max_size=3,
        )),
        template_mappings=draw(st.lists(
            st.builds(
                TemplateMapping,
                source_template=_slug,
                target_layout=_slug,
                target_route_pattern=st.builds(lambda s: f"/{s}/[slug]", _slug),
            ),
            max_size=3,
        )),
        plugin_instance_mappings=draw(st.lists(
            st.builds(
                PluginInstanceMapping,
                source_plugin=_slug,
                source_instance_type=_instance_type,
                target_api_id=st.one_of(st.none(), st.builds(lambda s: f"api::{s}.{s}", _slug)),
                target_component_uid=st.one_of(st.none(), st.builds(lambda s: f"shared.{s}", _slug)),
                migration_strategy=_migration_strategy,
            ),
            max_size=3,
        )),
    )


# ---------------------------------------------------------------------------
# Strategy: parity_reports
# ---------------------------------------------------------------------------

@st.composite
def parity_reports(draw):
    """Generate random ParityReport instances with consistent score invariants.

    Invariant: overall_score == mean of category_scores.
    """
    scores = {cat: draw(_parity_score) for cat in PARITY_CATEGORIES}
    overall = sum(scores.values()) / len(scores)

    return ParityReport(
        category_scores=scores,
        overall_score=overall,
        findings=draw(st.lists(findings(), max_size=3)),
        snapshot_comparisons=draw(st.lists(snapshot_comparisons(), max_size=3)),
        plugin_assertions=draw(st.dictionaries(
            keys=_slug,
            values=st.just([{"assertion": "ok"}]),
            max_size=2,
        )),
    )


# ---------------------------------------------------------------------------
# Strategy: snapshot_comparisons
# ---------------------------------------------------------------------------

@st.composite
def snapshot_comparisons(draw):
    """Generate random SnapshotComparison instances."""
    return SnapshotComparison(
        page_url=draw(_url),
        visual_parity_score=draw(_parity_score),
        content_match=draw(st.booleans()),
        differences=draw(st.lists(_name, max_size=3)),
    )


# ---------------------------------------------------------------------------
# Strategy: readiness_reports
# ---------------------------------------------------------------------------

@st.composite
def readiness_reports(draw):
    """Generate random ReadinessReport instances."""
    return ReadinessReport(
        qualified=draw(st.booleans()),
        findings=draw(st.lists(findings(), max_size=4)),
        checked_criteria=draw(st.lists(
            st.sampled_from([
                "gutenberg_first", "no_woocommerce", "no_multilingual",
                "no_membership", "no_enterprise_editorial", "supported_plugins",
            ]),
            min_size=1,
            max_size=6,
            unique=True,
        )),
    )
