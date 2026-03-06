"""Shared fixtures and Hypothesis strategies for the test suite."""

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
