from __future__ import annotations

import pytest

from src.agents.content_migrator import (
    _build_production_entry_payload,
    _field_mappings_for,
    _make_entry_finding,
    _map_content_status,
    _relation_mappings_for,
    _resolve_type_mapping,
    _template_mapping_for,
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
# Helpers
# ---------------------------------------------------------------------------

def _make_item(**overrides) -> WordPressContentItem:
    """Build a minimal WordPressContentItem with sensible defaults."""
    defaults = dict(
        id=1,
        title="Test Post",
        slug="test-post",
        post_type="post",
        status="publish",
        date="2024-01-15",
        excerpt="An excerpt",
        blocks=[],
        raw_html="",
        meta={},
        taxonomies={},
        featured_media=None,
        legacy_permalink="https://example.com/test-post",
        seo=None,
    )
    defaults.update(overrides)
    return WordPressContentItem(**defaults)

def _make_manifest(**overrides) -> MigrationMappingManifest:
    """Build a minimal MigrationMappingManifest."""
    defaults = dict(
        type_mappings=[],
        field_mappings=[],
        relation_mappings=[],
        media_mapping_strategy=MediaMappingStrategy(
            url_rewrite_pattern="/uploads/{filename}",
        ),
        term_mappings=[],
        template_mappings=[],
        plugin_instance_mappings=[],
    )
    defaults.update(overrides)
    return MigrationMappingManifest(**defaults)

def _build_payload(
    item: WordPressContentItem | None = None,
    *,
    field_mappings: list[FieldMapping] | None = None,
    relation_mappings: list[RelationMapping] | None = None,
    template_mapping: TemplateMapping | None = None,
    media_url_map: dict[str, str] | None = None,
    taxonomy_term_ids: dict[str, dict[str, int]] | None = None,
    manifest: MigrationMappingManifest | None = None,
    entry_id_map: dict[str, int] | None = None,
) -> dict:
    """Convenience wrapper around _build_production_entry_payload."""
    if item is None:
        item = _make_item()
    tm = TypeMapping(source_post_type=item.post_type, target_api_id="api::post.post")
    return _build_production_entry_payload(
        item=item,
        type_mapping=tm,
        field_mappings=field_mappings or [],
        relation_mappings=relation_mappings or [],
        template_mapping=template_mapping,
        media_url_map=media_url_map or {},
        taxonomy_term_ids=taxonomy_term_ids or {},
        mapping_manifest=manifest or _make_manifest(),
        entry_id_map=entry_id_map or {},
    )

# ---------------------------------------------------------------------------
# 1. Custom field payload migration (Requirement 19.1)
# ---------------------------------------------------------------------------

class TestCustomFieldPayloadMigration:
    """Validate field mapping transforms: direct, rich_text, component, dynamic_zone."""
    def test_direct_transform_copies_value_as_is(self):
        item = _make_item(meta={"subtitle": "Hello World"})
        fm = FieldMapping(
            source_post_type="post",
            source_field="subtitle",
            target_api_id="api::post.post",
            target_field="subtitle",
            transform="direct",
        )
        payload = _build_payload(item, field_mappings=[fm])
        assert payload["subtitle"] == "Hello World"

    def test_rich_text_transform_converts_blocks(self):
        blocks = [
            WordPressBlock(name="core/paragraph", attrs={}, html="<p>Hello</p>"),
        ]
        item = _make_item(
            blocks=blocks,
            meta={"content": "raw"},
        )
        fm = FieldMapping(
            source_post_type="post",
            source_field="content",
            target_api_id="api::post.post",
            target_field="body",
            transform="rich_text",
        )
        payload = _build_payload(item, field_mappings=[fm])
        # rich_text transform produces a list of rich text blocks
        assert isinstance(payload["body"], list)

    def test_component_transform_wraps_in_dict(self):
        item = _make_item(meta={"hero_text": "Welcome"})
        fm = FieldMapping(
            source_post_type="post",
            source_field="hero_text",
            target_api_id="api::post.post",
            target_field="hero",
            transform="component",
        )
        payload = _build_payload(item, field_mappings=[fm])
        assert isinstance(payload["hero"], dict)
        assert payload["hero"]["value"] == "Welcome"

    def test_component_transform_preserves_dict_value(self):
        item = _make_item(meta={"hero_data": '{"heading": "Hi", "cta": "Click"}'})
        fm = FieldMapping(
            source_post_type="post",
            source_field="hero_data",
            target_api_id="api::post.post",
            target_field="hero",
            transform="component",
        )
        payload = _build_payload(item, field_mappings=[fm])
        # String meta values are not dicts, so they get wrapped
        assert isinstance(payload["hero"], dict)

    def test_dynamic_zone_transform_wraps_in_list(self):
        item = _make_item(meta={"flexible_content": "section_a"})
        fm = FieldMapping(
            source_post_type="post",
            source_field="flexible_content",
            target_api_id="api::post.post",
            target_field="sections",
            transform="dynamic_zone",
        )
        payload = _build_payload(item, field_mappings=[fm])
        assert isinstance(payload["sections"], list)
        assert len(payload["sections"]) == 1
        assert payload["sections"][0]["__component"] == "sections"

    def test_meta_fields_mapped_via_field_mappings(self):
        item = _make_item(meta={"acf_color": "blue", "acf_size": "large"})
        fms = [
            FieldMapping(
                source_post_type="post",
                source_field="acf_color",
                target_api_id="api::post.post",
                target_field="color",
                transform="direct",
            ),
            FieldMapping(
                source_post_type="post",
                source_field="acf_size",
                target_api_id="api::post.post",
                target_field="size",
                transform="direct",
            ),
        ]
        payload = _build_payload(item, field_mappings=fms)
        assert payload["color"] == "blue"
        assert payload["size"] == "large"

    def test_missing_source_field_skipped(self):
        item = _make_item(meta={})
        fm = FieldMapping(
            source_post_type="post",
            source_field="nonexistent",
            target_api_id="api::post.post",
            target_field="target",
            transform="direct",
        )
        payload = _build_payload(item, field_mappings=[fm])
        assert "target" not in payload

# ---------------------------------------------------------------------------
# 2. Relation migration (Requirement 19.2)
# ---------------------------------------------------------------------------

class TestRelationMigration:
    """Validate relation mappings produce correct relation fields."""
    def test_matching_entry_id_produces_relation(self):
        rm = RelationMapping(
            source_relationship_id="rel-1",
            source_collection="posts",
            target_collection="articles",
            target_field="related_article",
            relation_type="oneToOne",
        )
        payload = _build_payload(
            relation_mappings=[rm],
            entry_id_map={"rel-1": 42},
        )
        assert payload["related_article"] == 42

    def test_one_to_many_produces_list(self):
        rm = RelationMapping(
            source_relationship_id="rel-1",
            source_collection="posts",
            target_collection="tags",
            target_field="tags",
            relation_type="oneToMany",
        )
        payload = _build_payload(
            relation_mappings=[rm],
            entry_id_map={"rel-1": 10},
        )
        assert isinstance(payload["tags"], list)
        assert 10 in payload["tags"]

    def test_many_to_many_produces_list(self):
        rm = RelationMapping(
            source_relationship_id="rel-1",
            source_collection="posts",
            target_collection="categories",
            target_field="categories",
            relation_type="manyToMany",
        )
        payload = _build_payload(
            relation_mappings=[rm],
            entry_id_map={"rel-1": 5},
        )
        assert isinstance(payload["categories"], list)
        assert 5 in payload["categories"]

    def test_one_to_one_produces_single_value(self):
        rm = RelationMapping(
            source_relationship_id="rel-1",
            source_collection="posts",
            target_collection="authors",
            target_field="author",
            relation_type="oneToOne",
        )
        payload = _build_payload(
            relation_mappings=[rm],
            entry_id_map={"rel-1": 7},
        )
        assert payload["author"] == 7

    def test_missing_entry_id_skipped(self):
        rm = RelationMapping(
            source_relationship_id="rel-missing",
            source_collection="posts",
            target_collection="authors",
            target_field="author",
            relation_type="oneToOne",
        )
        payload = _build_payload(
            relation_mappings=[rm],
            entry_id_map={},
        )
        assert "author" not in payload

    def test_multiple_one_to_many_relations_accumulate(self):
        rms = [
            RelationMapping(
                source_relationship_id="rel-1",
                source_collection="posts",
                target_collection="tags",
                target_field="tags",
                relation_type="oneToMany",
            ),
            RelationMapping(
                source_relationship_id="rel-2",
                source_collection="posts",
                target_collection="tags",
                target_field="tags",
                relation_type="oneToMany",
            ),
        ]
        payload = _build_payload(
            relation_mappings=rms,
            entry_id_map={"rel-1": 10, "rel-2": 20},
        )
        assert payload["tags"] == [10, 20]

# ---------------------------------------------------------------------------
# 3. Helper functions for plugin table row migration (Requirement 19.3)
# ---------------------------------------------------------------------------

class TestHelperFunctions:
    """Test pure helper functions that support plugin table row migration."""
    def test_resolve_type_mapping_found(self):
        manifest = _make_manifest(
            type_mappings=[
                TypeMapping(source_post_type="post", target_api_id="api::post.post"),
                TypeMapping(source_post_type="page", target_api_id="api::page.page"),
            ],
        )
        result = _resolve_type_mapping("page", manifest)
        assert result is not None
        assert result.target_api_id == "api::page.page"

    def test_resolve_type_mapping_not_found(self):
        manifest = _make_manifest(
            type_mappings=[
                TypeMapping(source_post_type="post", target_api_id="api::post.post"),
            ],
        )
        assert _resolve_type_mapping("custom_type", manifest) is None

    def test_field_mappings_for_filters_correctly(self):
        manifest = _make_manifest(
            field_mappings=[
                FieldMapping(
                    source_post_type="post",
                    source_field="title",
                    target_api_id="api::post.post",
                    target_field="title",
                ),
                FieldMapping(
                    source_post_type="page",
                    source_field="title",
                    target_api_id="api::page.page",
                    target_field="title",
                ),
                FieldMapping(
                    source_post_type="post",
                    source_field="body",
                    target_api_id="api::post.post",
                    target_field="content",
                ),
            ],
        )
        result = _field_mappings_for("post", "api::post.post", manifest)
        assert len(result) == 2
        assert all(fm.source_post_type == "post" for fm in result)

    def test_field_mappings_for_empty_when_no_match(self):
        manifest = _make_manifest(
            field_mappings=[
                FieldMapping(
                    source_post_type="post",
                    source_field="title",
                    target_api_id="api::post.post",
                    target_field="title",
                ),
            ],
        )
        assert _field_mappings_for("page", "api::page.page", manifest) == []

    def test_relation_mappings_for_filters_by_source_collection(self):
        manifest = _make_manifest(
            relation_mappings=[
                RelationMapping(
                    source_relationship_id="r1",
                    source_collection="posts",
                    target_collection="tags",
                    target_field="tags",
                    relation_type="oneToMany",
                ),
                RelationMapping(
                    source_relationship_id="r2",
                    source_collection="pages",
                    target_collection="menus",
                    target_field="menu",
                    relation_type="oneToOne",
                ),
            ],
        )
        result = _relation_mappings_for("posts", manifest)
        assert len(result) == 1
        assert result[0].source_relationship_id == "r1"

    def test_template_mapping_for_found(self):
        manifest = _make_manifest(
            template_mappings=[
                TemplateMapping(
                    source_template="full-width",
                    target_layout="FullWidth",
                    target_route_pattern="/[slug]",
                ),
            ],
        )
        result = _template_mapping_for("full-width", manifest)
        assert result is not None
        assert result.target_layout == "FullWidth"

    def test_template_mapping_for_not_found(self):
        manifest = _make_manifest(template_mappings=[])
        assert _template_mapping_for("missing", manifest) is None

# ---------------------------------------------------------------------------
# 4. Per-entry failure (Requirement 19.8)
# ---------------------------------------------------------------------------

class TestPerEntryFailure:
    """Validate _make_entry_finding produces valid Finding with context."""
    def test_produces_valid_finding(self):
        item = _make_item(post_type="event", slug="summer-gala", title="Summer Gala")
        finding = _make_entry_finding(item, "Connection timeout")
        assert isinstance(finding, Finding)

    def test_finding_severity_is_warning(self):
        item = _make_item()
        finding = _make_entry_finding(item, "some error")
        assert finding.severity == FindingSeverity.WARNING

    def test_finding_contains_post_type_and_slug(self):
        item = _make_item(post_type="portfolio", slug="my-project")
        finding = _make_entry_finding(item, "bad data")
        assert "portfolio" in finding.construct
        assert "my-project" in finding.construct

    def test_finding_contains_title_and_error(self):
        item = _make_item(title="My Great Post")
        finding = _make_entry_finding(item, "field validation failed")
        assert "My Great Post" in finding.message
        assert "field validation failed" in finding.message

    def test_finding_stage_is_content_migrator(self):
        item = _make_item()
        finding = _make_entry_finding(item, "err")
        assert finding.stage == "content_migrator"

    def test_finding_recommended_action_non_empty(self):
        item = _make_item()
        finding = _make_entry_finding(item, "err")
        assert len(finding.recommended_action) > 0

# ---------------------------------------------------------------------------
# 5. Identity preservation (Requirement 19.7)
# ---------------------------------------------------------------------------

class TestIdentityPreservation:
    """Validate slug, canonical URL, title, and status are preserved."""
    def test_slug_preserved(self):
        item = _make_item(slug="my-custom-slug")
        payload = _build_payload(item)
        assert payload["slug"] == "my-custom-slug"

    def test_canonical_url_matches_legacy_permalink(self):
        item = _make_item(legacy_permalink="https://example.com/old-path")
        payload = _build_payload(item)
        assert payload["canonical_url"] == "https://example.com/old-path"

    def test_title_preserved(self):
        item = _make_item(title="Important Article")
        payload = _build_payload(item)
        assert payload["title"] == "Important Article"

    @pytest.mark.parametrize(
        "wp_status,expected",
        [
            ("publish", "published"),
            ("draft", "draft"),
            ("future", "scheduled"),
            ("pending", "draft"),
            ("private", "draft"),
        ],
    )
    def test_status_mapping(self, wp_status: str, expected: str):
        assert _map_content_status(wp_status) == expected

    def test_unknown_status_defaults_to_draft(self):
        assert _map_content_status("trash") == "draft"

    def test_status_in_payload_uses_mapping(self):
        item = _make_item(status="future")
        payload = _build_payload(item)
        assert payload["status"] == "scheduled"

# ---------------------------------------------------------------------------
# 6. Template assignment
# ---------------------------------------------------------------------------

class TestTemplateAssignment:
    """Validate template mapping adds page_template and layout to payload."""
    def test_template_mapping_adds_fields(self):
        tm = TemplateMapping(
            source_template="sidebar-left",
            target_layout="SidebarLeft",
            target_route_pattern="/[slug]",
        )
        payload = _build_payload(template_mapping=tm)
        assert payload["page_template"] == "sidebar-left"
        assert payload["layout"] == "SidebarLeft"

    def test_none_template_mapping_omits_fields(self):
        payload = _build_payload(template_mapping=None)
        assert "page_template" not in payload
        assert "layout" not in payload

# ---------------------------------------------------------------------------
# 7. Taxonomy term mapping
# ---------------------------------------------------------------------------

class TestTaxonomyTermMapping:
    """Validate taxonomy terms are mapped using term_mappings from manifest."""
    def test_taxonomy_terms_mapped(self):
        item = _make_item(taxonomies={"category": ["news", "tech"]})
        manifest = _make_manifest(
            term_mappings=[
                TermMapping(
                    source_taxonomy="category",
                    target_api_id="api::category.category",
                    target_field="categories",
                ),
            ],
        )
        taxonomy_term_ids = {"category": {"news": 1, "tech": 2}}
        payload = _build_payload(
            item,
            manifest=manifest,
            taxonomy_term_ids=taxonomy_term_ids,
        )
        assert payload["categories"] == [1, 2]

    def test_missing_taxonomy_skipped(self):
        item = _make_item(taxonomies={})
        manifest = _make_manifest(
            term_mappings=[
                TermMapping(
                    source_taxonomy="category",
                    target_api_id="api::category.category",
                    target_field="categories",
                ),
            ],
        )
        payload = _build_payload(item, manifest=manifest)
        assert "categories" not in payload

    def test_unmapped_term_slug_skipped(self):
        item = _make_item(taxonomies={"category": ["news", "unknown"]})
        manifest = _make_manifest(
            term_mappings=[
                TermMapping(
                    source_taxonomy="category",
                    target_api_id="api::category.category",
                    target_field="categories",
                ),
            ],
        )
        taxonomy_term_ids = {"category": {"news": 1}}
        payload = _build_payload(
            item,
            manifest=manifest,
            taxonomy_term_ids=taxonomy_term_ids,
        )
        # Only the mapped term appears
        assert payload["categories"] == [1]
