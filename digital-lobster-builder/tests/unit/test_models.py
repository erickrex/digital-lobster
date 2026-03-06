"""Unit tests for Pydantic data models."""

import yaml

from src.models.manifest import ExportManifest
from src.models.inventory import (
    PluginFeature,
    ContentTypeSummary,
    TaxonomySummary,
    MenuSummary,
    ThemeMetadata,
    Inventory,
)
from src.models.modeling_manifest import (
    FrontmatterField,
    ContentCollectionSchema,
    ComponentMapping,
    TaxonomyDefinition,
    ModelingManifest,
)
from src.models.content import (
    WordPressBlock,
    WordPressContentItem,
    SerializedContent,
)
from src.models.qa_report import PageCheck, QAReport


class TestExportManifest:
    def test_create_manifest(self):
        m = ExportManifest(
            export_version="1.0",
            site_url="https://example.com",
            export_date="2024-01-01",
            wordpress_version="6.4",
            total_files=42,
            total_size_bytes=1024000,
            files={"content": 30, "theme": 12},
        )
        assert m.export_version == "1.0"
        assert m.total_files == 42
        assert m.files["content"] == 30

    def test_manifest_roundtrip_json(self):
        m = ExportManifest(
            export_version="2.0",
            site_url="https://test.org",
            export_date="2024-06-15",
            wordpress_version="6.5",
            total_files=10,
            total_size_bytes=500,
            files={"media": 5, "pages": 5},
        )
        data = m.model_dump()
        m2 = ExportManifest(**data)
        assert m == m2


class TestInventoryModels:
    def test_plugin_feature(self):
        p = PluginFeature(
            slug="yoast-seo",
            name="Yoast SEO",
            version="21.0",
            family="yoast",
            custom_post_types=[],
            custom_taxonomies=[],
            detected_features=["xml-sitemap", "meta-tags"],
        )
        assert p.family == "yoast"
        assert len(p.detected_features) == 2

    def test_plugin_feature_no_family(self):
        p = PluginFeature(
            slug="custom-plugin",
            name="Custom Plugin",
            version="1.0",
            family=None,
            custom_post_types=["portfolio"],
            custom_taxonomies=["skill"],
            detected_features=[],
        )
        assert p.family is None

    def test_inventory_full(self):
        inv = Inventory(
            site_url="https://example.com",
            site_name="Example Site",
            wordpress_version="6.4",
            content_types=[
                ContentTypeSummary(
                    post_type="post",
                    count=50,
                    custom_fields=[],
                    taxonomies=["category", "post_tag"],
                    sample_slugs=["hello-world"],
                )
            ],
            plugins=[],
            taxonomies=[
                TaxonomySummary(
                    taxonomy="category",
                    term_count=5,
                    associated_post_types=["post"],
                )
            ],
            menus=[
                MenuSummary(name="Primary", location="header", item_count=6)
            ],
            theme=ThemeMetadata(
                name="Twenty Twenty-Four",
                has_theme_json=True,
                has_custom_css=False,
                design_tokens={"colors": {"primary": "#000"}},
            ),
            has_html_snapshots=True,
            has_media_manifest=True,
            has_redirect_rules=False,
            has_seo_data=True,
        )
        assert inv.site_name == "Example Site"
        assert len(inv.content_types) == 1
        assert inv.theme.has_theme_json is True


class TestModelingManifestModels:
    def test_content_collection_schema(self):
        schema = ContentCollectionSchema(
            collection_name="places",
            source_post_type="gd_place",
            frontmatter_fields=[
                FrontmatterField(
                    name="title", type="string", required=True, description="Place title"
                ),
                FrontmatterField(
                    name="rating", type="number", required=False, description="Average rating"
                ),
            ],
            route_pattern="/places/[slug]",
        )
        assert schema.collection_name == "places"
        assert len(schema.frontmatter_fields) == 2

    def test_component_mapping_island(self):
        cm = ComponentMapping(
            wp_block_type="kadence/tabs",
            astro_component="KadenceTabs",
            is_island=True,
            hydration_directive="client:visible",
            props=[{"name": "tabs", "type": "array"}],
            fallback=False,
        )
        assert cm.is_island is True
        assert cm.hydration_directive == "client:visible"

    def test_component_mapping_fallback(self):
        cm = ComponentMapping(
            wp_block_type="unknown/block",
            astro_component="FallbackHTML",
            is_island=False,
            hydration_directive=None,
            props=[],
            fallback=True,
        )
        assert cm.fallback is True

    def test_modeling_manifest(self):
        mm = ModelingManifest(
            collections=[],
            components=[],
            taxonomies=[
                TaxonomyDefinition(
                    taxonomy="category",
                    collection_ref="categories",
                    data_file=None,
                )
            ],
        )
        assert len(mm.taxonomies) == 1


class TestContentModels:
    def test_wordpress_block(self):
        b = WordPressBlock(
            name="core/paragraph",
            attrs={"align": "center"},
            html="<p>Hello world</p>",
        )
        assert b.name == "core/paragraph"

    def test_wordpress_content_item(self):
        item = WordPressContentItem(
            id=1,
            post_type="post",
            title="Hello World",
            slug="hello-world",
            status="publish",
            date="2024-01-01T00:00:00",
            excerpt="A test post",
            blocks=[],
            raw_html="<p>Hello</p>",
            taxonomies={"category": ["uncategorized"]},
            meta={"_edit_last": "1"},
            featured_media=None,
            legacy_permalink="/2024/01/hello-world/",
            seo={"title": "Hello World | Site", "description": "A test"},
        )
        assert item.slug == "hello-world"
        assert item.seo is not None

    def test_serialized_content_to_file_content(self):
        sc = SerializedContent(
            collection="posts",
            slug="hello-world",
            frontmatter={"title": "Hello World", "date": "2024-01-01"},
            body="This is the body content.\n",
            file_extension="md",
        )
        output = sc.to_file_content()
        assert output.startswith("---\n")
        assert output.endswith("This is the body content.\n")
        # Parse the frontmatter back
        parts = output.split("---\n")
        # parts: ['', frontmatter, body]
        parsed_fm = yaml.safe_load(parts[1])
        assert parsed_fm["title"] == "Hello World"

    def test_serialized_content_special_chars(self):
        sc = SerializedContent(
            collection="pages",
            slug="about",
            frontmatter={
                "title": 'About: "Our Company"',
                "description": "Line one\nLine two",
                "emoji": "Hello 🌍",
            },
            body="Body with special chars: é à ü\n",
            file_extension="mdx",
        )
        output = sc.to_file_content()
        parsed_parts = output.split("---\n")
        parsed_fm = yaml.safe_load(parsed_parts[1])
        assert parsed_fm["title"] == 'About: "Our Company"'
        assert parsed_fm["emoji"] == "Hello 🌍"


class TestQAReportModels:
    def test_page_check_passed(self):
        pc = PageCheck(
            url="/",
            http_status=200,
            visual_parity_score=95.5,
            accessibility_issues=[],
            passed=True,
        )
        assert pc.passed is True

    def test_page_check_failed(self):
        pc = PageCheck(
            url="/about",
            http_status=404,
            visual_parity_score=None,
            accessibility_issues=["Missing h1"],
            passed=False,
        )
        assert pc.passed is False
        assert len(pc.accessibility_issues) == 1

    def test_qa_report(self):
        report = QAReport(
            build_success=True,
            build_errors=[],
            pages_checked=[
                PageCheck(
                    url="/",
                    http_status=200,
                    visual_parity_score=92.0,
                    accessibility_issues=[],
                    passed=True,
                ),
                PageCheck(
                    url="/missing",
                    http_status=404,
                    visual_parity_score=None,
                    accessibility_issues=["No skip-nav link"],
                    passed=False,
                ),
            ],
            total_passed=1,
            total_failed=1,
            warnings=["Low visual parity on /blog"],
        )
        assert report.total_passed == 1
        assert report.total_failed == 1
        assert len(report.pages_checked) == 2
