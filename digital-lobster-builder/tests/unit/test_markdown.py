from src.models.content import WordPressBlock
from src.serialization.markdown import block_to_markdown, blocks_to_markdown


class TestParagraph:
    def test_simple_paragraph(self):
        block = WordPressBlock(
            name="core/paragraph",
            attrs={},
            html="<p>Hello world</p>",
        )
        assert block_to_markdown(block) == "Hello world"

    def test_paragraph_with_bold(self):
        block = WordPressBlock(
            name="core/paragraph",
            attrs={},
            html="<p>This is <strong>bold</strong> text</p>",
        )
        assert block_to_markdown(block) == "This is **bold** text"

    def test_paragraph_with_italic(self):
        block = WordPressBlock(
            name="core/paragraph",
            attrs={},
            html="<p>This is <em>italic</em> text</p>",
        )
        assert block_to_markdown(block) == "This is *italic* text"

    def test_paragraph_with_link(self):
        block = WordPressBlock(
            name="core/paragraph",
            attrs={},
            html='<p>Visit <a href="https://example.com">our site</a></p>',
        )
        assert block_to_markdown(block) == "Visit [our site](https://example.com)"

    def test_paragraph_with_inline_code(self):
        block = WordPressBlock(
            name="core/paragraph",
            attrs={},
            html="<p>Use <code>print()</code> to output</p>",
        )
        assert block_to_markdown(block) == "Use `print()` to output"


class TestHeading:
    def test_h1(self):
        block = WordPressBlock(
            name="core/heading",
            attrs={"level": 1},
            html="<h1>Title</h1>",
        )
        assert block_to_markdown(block) == "# Title"

    def test_h2(self):
        block = WordPressBlock(
            name="core/heading",
            attrs={"level": 2},
            html="<h2>Subtitle</h2>",
        )
        assert block_to_markdown(block) == "## Subtitle"

    def test_h3(self):
        block = WordPressBlock(
            name="core/heading",
            attrs={"level": 3},
            html="<h3>Section</h3>",
        )
        assert block_to_markdown(block) == "### Section"

    def test_h4(self):
        block = WordPressBlock(
            name="core/heading",
            attrs={"level": 4},
            html="<h4>Subsection</h4>",
        )
        assert block_to_markdown(block) == "#### Subsection"

    def test_heading_with_inline_formatting(self):
        block = WordPressBlock(
            name="core/heading",
            attrs={"level": 2},
            html="<h2>Hello <strong>World</strong></h2>",
        )
        assert block_to_markdown(block) == "## Hello **World**"

    def test_heading_level_from_html_tag(self):
        """Level should be detected from the HTML tag, not just attrs."""
        block = WordPressBlock(
            name="core/heading",
            attrs={},
            html="<h3>Detected</h3>",
        )
        assert block_to_markdown(block) == "### Detected"


class TestList:
    def test_unordered_list(self):
        block = WordPressBlock(
            name="core/list",
            attrs={"ordered": False},
            html="<ul><li>Apple</li><li>Banana</li><li>Cherry</li></ul>",
        )
        result = block_to_markdown(block)
        assert result == "- Apple\n- Banana\n- Cherry"

    def test_ordered_list(self):
        block = WordPressBlock(
            name="core/list",
            attrs={"ordered": True},
            html="<ol><li>First</li><li>Second</li><li>Third</li></ol>",
        )
        result = block_to_markdown(block)
        assert result == "1. First\n2. Second\n3. Third"

    def test_ordered_list_detected_from_html(self):
        """Ordered list detected from <ol> tag even without attrs."""
        block = WordPressBlock(
            name="core/list",
            attrs={},
            html="<ol><li>One</li><li>Two</li></ol>",
        )
        result = block_to_markdown(block)
        assert result == "1. One\n2. Two"

    def test_list_with_inline_formatting(self):
        block = WordPressBlock(
            name="core/list",
            attrs={"ordered": False},
            html="<ul><li><strong>Bold</strong> item</li><li><em>Italic</em> item</li></ul>",
        )
        result = block_to_markdown(block)
        assert result == "- **Bold** item\n- *Italic* item"


class TestCode:
    def test_simple_code_block(self):
        block = WordPressBlock(
            name="core/code",
            attrs={},
            html="<pre><code>print('hello')</code></pre>",
        )
        result = block_to_markdown(block)
        assert result == "```\nprint('hello')\n```"

    def test_code_block_with_language(self):
        block = WordPressBlock(
            name="core/code",
            attrs={"language": "python"},
            html="<pre><code>def foo():\n    pass</code></pre>",
        )
        result = block_to_markdown(block)
        assert result == "```python\ndef foo():\n    pass\n```"

    def test_code_block_with_html_entities(self):
        block = WordPressBlock(
            name="core/code",
            attrs={},
            html="<pre><code>&lt;div&gt;hello&lt;/div&gt;</code></pre>",
        )
        result = block_to_markdown(block)
        assert result == "```\n<div>hello</div>\n```"


class TestImage:
    def test_image_from_attrs(self):
        block = WordPressBlock(
            name="core/image",
            attrs={"url": "https://example.com/img.jpg", "alt": "A photo"},
            html='<figure><img src="https://example.com/img.jpg" alt="A photo"/></figure>',
        )
        assert block_to_markdown(block) == "![A photo](https://example.com/img.jpg)"

    def test_image_from_html(self):
        block = WordPressBlock(
            name="core/image",
            attrs={},
            html='<figure><img src="https://example.com/pic.png" alt="Pic"/></figure>',
        )
        assert block_to_markdown(block) == "![Pic](https://example.com/pic.png)"

    def test_image_no_alt(self):
        block = WordPressBlock(
            name="core/image",
            attrs={"url": "https://example.com/img.jpg"},
            html='<figure><img src="https://example.com/img.jpg"/></figure>',
        )
        assert block_to_markdown(block) == "![](https://example.com/img.jpg)"


class TestQuote:
    def test_simple_quote(self):
        block = WordPressBlock(
            name="core/quote",
            attrs={},
            html="<blockquote><p>To be or not to be</p></blockquote>",
        )
        assert block_to_markdown(block) == "> To be or not to be"

    def test_multiline_quote(self):
        block = WordPressBlock(
            name="core/quote",
            attrs={},
            html="<blockquote><p>Line one</p><p>Line two</p></blockquote>",
        )
        result = block_to_markdown(block)
        # After stripping, the two paragraphs become text separated by space
        assert result.startswith(">")


class TestSeparator:
    def test_separator(self):
        block = WordPressBlock(
            name="core/separator",
            attrs={},
            html="<hr/>",
        )
        assert block_to_markdown(block) == "---"

    def test_separator_empty_html(self):
        block = WordPressBlock(
            name="core/separator",
            attrs={},
            html="",
        )
        assert block_to_markdown(block) == "---"


class TestPreformatted:
    def test_preformatted(self):
        block = WordPressBlock(
            name="core/preformatted",
            attrs={},
            html="<pre>Some preformatted text</pre>",
        )
        assert block_to_markdown(block) == "```\nSome preformatted text\n```"


class TestHtml:
    def test_raw_html_passthrough(self):
        raw = '<div class="custom">Custom content</div>'
        block = WordPressBlock(
            name="core/html",
            attrs={},
            html=raw,
        )
        assert block_to_markdown(block) == raw


class TestTable:
    def test_simple_table(self):
        block = WordPressBlock(
            name="core/table",
            attrs={},
            html=(
                "<table><thead><tr><th>Name</th><th>Age</th></tr></thead>"
                "<tbody><tr><td>Alice</td><td>30</td></tr>"
                "<tr><td>Bob</td><td>25</td></tr></tbody></table>"
            ),
        )
        result = block_to_markdown(block)
        lines = result.split("\n")
        assert lines[0] == "| Name | Age |"
        assert lines[1] == "| --- | --- |"
        assert lines[2] == "| Alice | 30 |"
        assert lines[3] == "| Bob | 25 |"


class TestEmbed:
    def test_embed_with_url(self):
        block = WordPressBlock(
            name="core/embed",
            attrs={"url": "https://youtube.com/watch?v=abc", "providerNameSlug": "youtube"},
            html='<figure><div class="wp-block-embed__wrapper">https://youtube.com/watch?v=abc</div></figure>',
        )
        assert block_to_markdown(block) == "[youtube](https://youtube.com/watch?v=abc)"

    def test_embed_no_url_falls_back_to_html(self):
        raw = '<figure><div>embedded content</div></figure>'
        block = WordPressBlock(
            name="core/embed",
            attrs={},
            html=raw,
        )
        assert block_to_markdown(block) == raw


class TestUnknownBlock:
    def test_unknown_block_returns_raw_html(self):
        raw = '<div class="wp-block-custom">Custom block</div>'
        block = WordPressBlock(
            name="my-plugin/custom-block",
            attrs={},
            html=raw,
        )
        assert block_to_markdown(block) == raw


class TestEmptyBlocks:
    def test_empty_paragraph(self):
        block = WordPressBlock(name="core/paragraph", attrs={}, html="")
        assert block_to_markdown(block) == ""

    def test_empty_heading(self):
        block = WordPressBlock(name="core/heading", attrs={}, html="")
        assert block_to_markdown(block) == ""

    def test_empty_unknown(self):
        block = WordPressBlock(name="unknown/block", attrs={}, html="")
        assert block_to_markdown(block) == ""


class TestBlocksToMarkdown:
    def test_multiple_blocks(self):
        blocks = [
            WordPressBlock(name="core/heading", attrs={"level": 1}, html="<h1>Title</h1>"),
            WordPressBlock(name="core/paragraph", attrs={}, html="<p>Hello world</p>"),
            WordPressBlock(name="core/separator", attrs={}, html="<hr/>"),
            WordPressBlock(name="core/paragraph", attrs={}, html="<p>Goodbye</p>"),
        ]
        result = blocks_to_markdown(blocks)
        assert "# Title" in result
        assert "Hello world" in result
        assert "---" in result
        assert "Goodbye" in result
        # Blocks separated by double newlines
        parts = result.split("\n\n")
        assert len(parts) == 4

    def test_empty_blocks_skipped(self):
        blocks = [
            WordPressBlock(name="core/paragraph", attrs={}, html="<p>Keep</p>"),
            WordPressBlock(name="core/paragraph", attrs={}, html=""),
            WordPressBlock(name="core/paragraph", attrs={}, html="<p>Also keep</p>"),
        ]
        result = blocks_to_markdown(blocks)
        parts = result.split("\n\n")
        assert len(parts) == 2
        assert parts[0] == "Keep"
        assert parts[1] == "Also keep"

    def test_empty_list(self):
        assert blocks_to_markdown([]) == ""

    def test_proper_spacing(self):
        blocks = [
            WordPressBlock(name="core/heading", attrs={"level": 2}, html="<h2>Section</h2>"),
            WordPressBlock(name="core/paragraph", attrs={}, html="<p>Content here.</p>"),
        ]
        result = blocks_to_markdown(blocks)
        assert result == "## Section\n\nContent here."
