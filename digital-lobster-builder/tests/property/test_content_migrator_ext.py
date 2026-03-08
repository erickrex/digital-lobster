from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from src.agents.content_migrator import (
    _build_production_entry_payload,
    _make_entry_finding,
    _map_content_status,
)
from src.models.content import WordPressBlock, WordPressContentItem
from src.models.finding import Finding, FindingSeverity
from src.models.migration_mapping_manifest import (
    FieldMapping,
    MediaMappingStrategy,
    MigrationMappingManifest,
    RelationMapping,
    TemplateMapping,
    TermMapping,
    TypeMapping,
)

# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

_VALID_STRAPI_STATUSES = {"published", "draft", "scheduled"}

_WP_STATUSES = st.sampled_from(["publish", "draft", "future", "pending", "private"])

_slug = st.from_regex(r"[a-z][a-z0-9\-]{1,30}", fullmatch=True)
_name = st.text(
    min_size=1,
    max_size=60,
    alphabet=st.characters(categories=("L", "N", "Z")),
)
_post_type = st.sampled_from(["post", "page", "event", "testimonial", "service"])
_date = st.from_regex(
    r"2024\-(?:0[1-9]|1[0-2])\-(?:0[1-9]|[12][0-9]|3[01])",
    fullmatch=True,
)

@st.composite
def wordpress_content_items(draw) -> WordPressContentItem:
    """Generate random WordPressContentItem instances."""
    slug = draw(_slug)
    return WordPressContentItem(
        id=draw(st.integers(min_value=1, max_value=999999)),
        post_type=draw(_post_type),
        title=draw(_name),
        slug=slug,
        status=draw(_WP_STATUSES),
        date=draw(_date),
        excerpt=draw(st.one_of(st.none(), st.text(max_size=100))),
        blocks=[],
        raw_html="",
        taxonomies=draw(
            st.fixed_dictionaries(
                {},
                optional={
                    "category": st.lists(_name, max_size=3),
                    "post_tag": st.lists(_name, max_size=3),
                },
            )
        ),
        meta=draw(st.dictionaries(keys=_slug, values=st.text(max_size=50), max_size=3)),
        featured_media=draw(
            st.one_of(
                st.none(),
                st.fixed_dictionaries({"url": st.just("https://wp.example.com/img.jpg"), "alt": _name}),
            )
        ),
        legacy_permalink=draw(st.builds(lambda s: f"/{s}/", _slug)),
        seo=draw(st.one_of(st.none(), st.fixed_dictionaries({"title": _name}))),
    )

def _minimal_mapping_manifest() -> MigrationMappingManifest:
    """Return a minimal MigrationMappingManifest with no mappings."""
    return MigrationMappingManifest(
        type_mappings=[],
        field_mappings=[],
        relation_mappings=[],
        media_mapping_strategy=MediaMappingStrategy(
            url_rewrite_pattern="/uploads/{filename}",
            relation_aware=True,
            preserve_alt_text=True,
            preserve_caption=True,
        ),
        term_mappings=[],
        template_mappings=[],
        plugin_instance_mappings=[],
    )

def _type_mapping_for(post_type: str) -> TypeMapping:
    return TypeMapping(source_post_type=post_type, target_api_id=f"api.{post_type}")

# ---------------------------------------------------------------------------
# Property 19: Content migrator preserves identity fields
# ---------------------------------------------------------------------------

class TestContentMigratorPreservesIdentityFields:
    """    For any WordPressContentItem, the production entry payload must preserve
    slug, canonical_url, status, and title.
    """
    @given(item=wordpress_content_items())
    @settings(max_examples=100)
    def test_slug_always_present_and_matches(self, item: WordPressContentItem):
        """Property 19: slug is always preserved in the payload."""
        payload = _build_production_entry_payload(
            item=item,
            type_mapping=_type_mapping_for(item.post_type),
            field_mappings=[],
            relation_mappings=[],
            template_mapping=None,
            media_url_map={},
            taxonomy_term_ids={},
            mapping_manifest=_minimal_mapping_manifest(),
            entry_id_map={},
        )
        assert "slug" in payload
        assert payload["slug"] == item.slug

    @given(item=wordpress_content_items())
    @settings(max_examples=100)
    def test_canonical_url_always_present_and_matches(self, item: WordPressContentItem):
        """Property 19: canonical_url is always preserved in the payload."""
        payload = _build_production_entry_payload(
            item=item,
            type_mapping=_type_mapping_for(item.post_type),
            field_mappings=[],
            relation_mappings=[],
            template_mapping=None,
            media_url_map={},
            taxonomy_term_ids={},
            mapping_manifest=_minimal_mapping_manifest(),
            entry_id_map={},
        )
        assert "canonical_url" in payload
        assert payload["canonical_url"] == item.legacy_permalink

    @given(item=wordpress_content_items())
    @settings(max_examples=100)
    def test_status_always_present_and_valid(self, item: WordPressContentItem):
        """Property 19: status is always a valid Strapi status."""
        payload = _build_production_entry_payload(
            item=item,
            type_mapping=_type_mapping_for(item.post_type),
            field_mappings=[],
            relation_mappings=[],
            template_mapping=None,
            media_url_map={},
            taxonomy_term_ids={},
            mapping_manifest=_minimal_mapping_manifest(),
            entry_id_map={},
        )
        assert "status" in payload
        assert payload["status"] in _VALID_STRAPI_STATUSES

    @given(item=wordpress_content_items())
    @settings(max_examples=100)
    def test_status_matches_mapped_value(self, item: WordPressContentItem):
        """Property 19: status matches the _map_content_status output."""
        payload = _build_production_entry_payload(
            item=item,
            type_mapping=_type_mapping_for(item.post_type),
            field_mappings=[],
            relation_mappings=[],
            template_mapping=None,
            media_url_map={},
            taxonomy_term_ids={},
            mapping_manifest=_minimal_mapping_manifest(),
            entry_id_map={},
        )
        assert payload["status"] == _map_content_status(item.status)

    @given(item=wordpress_content_items())
    @settings(max_examples=100)
    def test_title_always_present_and_matches(self, item: WordPressContentItem):
        """Property 19: title is always preserved in the payload."""
        payload = _build_production_entry_payload(
            item=item,
            type_mapping=_type_mapping_for(item.post_type),
            field_mappings=[],
            relation_mappings=[],
            template_mapping=None,
            media_url_map={},
            taxonomy_term_ids={},
            mapping_manifest=_minimal_mapping_manifest(),
            entry_id_map={},
        )
        assert "title" in payload
        assert payload["title"] == item.title

# ---------------------------------------------------------------------------
# Property 20: Content migrator error resilience
# ---------------------------------------------------------------------------

class TestContentMigratorErrorResilience:
    """    _make_entry_finding() must always produce a valid Finding with
    non-empty severity, stage, construct, message, and recommended_action.
    """
    @given(
        item=wordpress_content_items(),
        error=st.text(min_size=1, max_size=200),
    )
    @settings(max_examples=100)
    def test_finding_has_valid_severity(self, item: WordPressContentItem, error: str):
        """Property 20: Finding severity is a valid FindingSeverity enum."""
        finding = _make_entry_finding(item, error)
        assert isinstance(finding.severity, FindingSeverity)

    @given(
        item=wordpress_content_items(),
        error=st.text(min_size=1, max_size=200),
    )
    @settings(max_examples=100)
    def test_finding_stage_is_content_migrator(self, item: WordPressContentItem, error: str):
        """Property 20: Finding stage is always 'content_migrator'."""
        finding = _make_entry_finding(item, error)
        assert finding.stage == "content_migrator"
        assert len(finding.stage) > 0

    @given(
        item=wordpress_content_items(),
        error=st.text(min_size=1, max_size=200),
    )
    @settings(max_examples=100)
    def test_finding_construct_contains_post_type_and_slug(
        self, item: WordPressContentItem, error: str
    ):
        """Property 20: Finding construct contains post_type and slug."""
        finding = _make_entry_finding(item, error)
        assert len(finding.construct) > 0
        assert item.post_type in finding.construct
        assert item.slug in finding.construct

    @given(
        item=wordpress_content_items(),
        error=st.text(min_size=1, max_size=200),
    )
    @settings(max_examples=100)
    def test_finding_message_contains_title(self, item: WordPressContentItem, error: str):
        """Property 20: Finding message contains the item title."""
        finding = _make_entry_finding(item, error)
        assert len(finding.message) > 0
        assert item.title in finding.message

    @given(
        item=wordpress_content_items(),
        error=st.text(min_size=1, max_size=200),
    )
    @settings(max_examples=100)
    def test_finding_recommended_action_non_empty(
        self, item: WordPressContentItem, error: str
    ):
        """Property 20: Finding recommended_action is non-empty."""
        finding = _make_entry_finding(item, error)
        assert len(finding.recommended_action) > 0

    @given(
        item=wordpress_content_items(),
        error=st.text(min_size=1, max_size=200),
    )
    @settings(max_examples=100)
    def test_finding_is_valid_pydantic_model(self, item: WordPressContentItem, error: str):
        """Property 20: Finding round-trips through Pydantic validation."""
        finding = _make_entry_finding(item, error)
        restored = Finding.model_validate(finding.model_dump())
        assert restored == finding
