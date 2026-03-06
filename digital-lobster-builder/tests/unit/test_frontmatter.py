"""Unit tests for YAML frontmatter serialization and parsing."""

import yaml

from src.serialization.frontmatter import (
    serialize_frontmatter,
    parse_frontmatter,
    serialize_file,
    parse_file,
)


class TestSerializeFrontmatter:
    def test_simple_values(self):
        data = {"title": "Hello World", "draft": False, "count": 42}
        result = serialize_frontmatter(data)
        parsed = yaml.safe_load(result)
        assert parsed["title"] == "Hello World"
        assert parsed["draft"] is False
        assert parsed["count"] == 42

    def test_colon_in_value(self):
        data = {"title": "Title: A Subtitle"}
        result = serialize_frontmatter(data)
        parsed = yaml.safe_load(result)
        assert parsed["title"] == "Title: A Subtitle"

    def test_double_quotes_in_value(self):
        data = {"title": 'About "Our Company"'}
        result = serialize_frontmatter(data)
        parsed = yaml.safe_load(result)
        assert parsed["title"] == 'About "Our Company"'

    def test_single_quotes_in_value(self):
        data = {"title": "It's a test"}
        result = serialize_frontmatter(data)
        parsed = yaml.safe_load(result)
        assert parsed["title"] == "It's a test"

    def test_newlines_in_value(self):
        data = {"description": "Line one\nLine two\nLine three"}
        result = serialize_frontmatter(data)
        parsed = yaml.safe_load(result)
        assert parsed["description"] == "Line one\nLine two\nLine three"

    def test_unicode_characters(self):
        data = {"title": "Hello 🌍", "author": "José García", "tag": "日本語"}
        result = serialize_frontmatter(data)
        parsed = yaml.safe_load(result)
        assert parsed["title"] == "Hello 🌍"
        assert parsed["author"] == "José García"
        assert parsed["tag"] == "日本語"

    def test_empty_dict(self):
        assert serialize_frontmatter({}) == ""

    def test_none_value(self):
        data = {"title": "Test", "subtitle": None}
        result = serialize_frontmatter(data)
        parsed = yaml.safe_load(result)
        assert parsed["title"] == "Test"
        assert parsed["subtitle"] is None

    def test_empty_string_value(self):
        data = {"title": "", "body": "content"}
        result = serialize_frontmatter(data)
        parsed = yaml.safe_load(result)
        assert parsed["title"] == ""
        assert parsed["body"] == "content"

    def test_list_values(self):
        data = {"tags": ["python", "astro", "web"]}
        result = serialize_frontmatter(data)
        parsed = yaml.safe_load(result)
        assert parsed["tags"] == ["python", "astro", "web"]

    def test_nested_dict(self):
        data = {"seo": {"title": "SEO Title", "description": "SEO Desc"}}
        result = serialize_frontmatter(data)
        parsed = yaml.safe_load(result)
        assert parsed["seo"]["title"] == "SEO Title"
        assert parsed["seo"]["description"] == "SEO Desc"

    def test_preserves_key_order(self):
        data = {"zebra": 1, "alpha": 2, "middle": 3}
        result = serialize_frontmatter(data)
        lines = result.strip().split("\n")
        keys = [line.split(":")[0] for line in lines]
        assert keys == ["zebra", "alpha", "middle"]

    def test_mixed_special_characters(self):
        data = {"title": 'Colons: and "quotes" and newlines\nhere'}
        result = serialize_frontmatter(data)
        parsed = yaml.safe_load(result)
        assert parsed["title"] == 'Colons: and "quotes" and newlines\nhere'


class TestParseFrontmatter:
    def test_simple_yaml(self):
        text = "title: Hello World\ndraft: false\n"
        result = parse_frontmatter(text)
        assert result["title"] == "Hello World"
        assert result["draft"] is False

    def test_empty_string(self):
        assert parse_frontmatter("") == {}

    def test_whitespace_only(self):
        assert parse_frontmatter("   \n  ") == {}

    def test_none_input(self):
        assert parse_frontmatter(None) == {}

    def test_yaml_null_value(self):
        text = "title: Test\nsubtitle: null\n"
        result = parse_frontmatter(text)
        assert result["subtitle"] is None


class TestRoundTrip:
    def test_simple_roundtrip(self):
        data = {"title": "Hello", "count": 5, "draft": True}
        result = parse_frontmatter(serialize_frontmatter(data))
        assert result == data

    def test_special_chars_roundtrip(self):
        data = {
            "title": 'Title: "A Subtitle"',
            "description": "Line one\nLine two",
            "emoji": "Hello 🌍",
            "quote": "It's working",
        }
        result = parse_frontmatter(serialize_frontmatter(data))
        assert result == data

    def test_complex_roundtrip(self):
        data = {
            "title": "Complex Post",
            "tags": ["python", "yaml", "testing"],
            "seo": {"title": "SEO: Title", "desc": "A description"},
            "empty": "",
            "nothing": None,
        }
        result = parse_frontmatter(serialize_frontmatter(data))
        assert result == data


class TestSerializeFile:
    def test_basic_file(self):
        fm = {"title": "Hello World"}
        body = "This is the body.\n"
        result = serialize_file(fm, body)
        assert result.startswith("---\n")
        assert "\n---\n" in result
        assert result.endswith("This is the body.\n")

    def test_empty_frontmatter(self):
        result = serialize_file({}, "Body content\n")
        assert result == "---\n\n---\nBody content\n"

    def test_empty_body(self):
        result = serialize_file({"title": "Test"}, "")
        assert result.startswith("---\n")
        assert result.endswith("\n---\n")


class TestParseFile:
    def test_basic_parse(self):
        content = "---\ntitle: Hello World\n---\nBody content\n"
        fm, body = parse_file(content)
        assert fm["title"] == "Hello World"
        assert body == "Body content\n"

    def test_multiline_body(self):
        content = "---\ntitle: Test\n---\nLine 1\nLine 2\nLine 3\n"
        fm, body = parse_file(content)
        assert fm["title"] == "Test"
        assert body == "Line 1\nLine 2\nLine 3\n"

    def test_empty_body(self):
        content = "---\ntitle: Test\n---\n"
        fm, body = parse_file(content)
        assert fm["title"] == "Test"
        assert body == ""

    def test_missing_opening_delimiter(self):
        try:
            parse_file("title: Test\n---\nBody\n")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "does not start with" in str(e)

    def test_missing_closing_delimiter(self):
        try:
            parse_file("---\ntitle: Test\nBody\n")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "closing" in str(e).lower()


class TestFileRoundTrip:
    def test_simple_file_roundtrip(self):
        fm = {"title": "Hello", "date": "2024-01-01"}
        body = "This is the body content.\n"
        content = serialize_file(fm, body)
        parsed_fm, parsed_body = parse_file(content)
        assert parsed_fm == fm
        assert parsed_body == body

    def test_special_chars_file_roundtrip(self):
        fm = {
            "title": 'About: "Our Company"',
            "description": "Line one\nLine two",
            "emoji": "Hello 🌍",
        }
        body = "Body with special chars: é à ü\n"
        content = serialize_file(fm, body)
        parsed_fm, parsed_body = parse_file(content)
        assert parsed_fm == fm
        assert parsed_body == body

    def test_complex_file_roundtrip(self):
        fm = {
            "title": "Complex",
            "tags": ["a", "b", "c"],
            "meta": {"key": "value"},
            "empty_field": None,
        }
        body = "# Heading\n\nParagraph with **bold** text.\n"
        content = serialize_file(fm, body)
        parsed_fm, parsed_body = parse_file(content)
        assert parsed_fm == fm
        assert parsed_body == body
