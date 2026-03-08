import html
import re

from src.models.content import WordPressBlock

def blocks_to_markdown(blocks: list[WordPressBlock]) -> str:
    """Convert a list of WordPress blocks to Markdown.

    Each block is converted individually and joined with double newlines
    for proper Markdown paragraph separation.

    Args:
        blocks: List of WordPressBlock objects.

    Returns:
        Markdown string with all blocks converted.
    """
    parts = []
    for block in blocks:
        md = block_to_markdown(block)
        if md:
            parts.append(md)
    return "\n\n".join(parts)

def block_to_markdown(block: WordPressBlock) -> str:
    """Convert a single WordPress block to Markdown.

    Dispatches to a type-specific handler based on the block name.
    Unknown block types fall back to raw HTML passthrough.

    Args:
        block: A WordPressBlock object.

    Returns:
        Markdown string for the block. Empty string for empty blocks.
    """
    if not block.html and not block.attrs and block.name != "core/separator":
        return ""

    converters = {
        "core/paragraph": _convert_paragraph,
        "core/heading": _convert_heading,
        "core/list": _convert_list,
        "core/code": _convert_code,
        "core/image": _convert_image,
        "core/quote": _convert_quote,
        "core/separator": _convert_separator,
        "core/preformatted": _convert_preformatted,
        "core/html": _convert_html,
        "core/table": _convert_table,
        "core/embed": _convert_embed,
    }

    converter = converters.get(block.name)
    if converter:
        return converter(block)
    # Unknown block type: raw HTML passthrough
    return block.html

# ---------------------------------------------------------------------------
# Inline HTML helpers
# ---------------------------------------------------------------------------

def _strip_html(text: str) -> str:
    """Strip HTML tags from text, converting inline formatting to Markdown.

    Converts <strong>/<b> to **bold**, <em>/<i> to *italic*,
    <code> to `code`, and strips all other tags.
    """
    if not text:
        return ""
    # Convert inline formatting before stripping tags
    s = re.sub(r"<(strong|b)>(.*?)</\1>", r"**\2**", text, flags=re.DOTALL)
    s = re.sub(r"<(em|i)>(.*?)</\1>", r"*\2*", s, flags=re.DOTALL)
    s = re.sub(r"<code>(.*?)</code>", r"`\1`", s, flags=re.DOTALL)
    # Convert <a href="...">text</a> to [text](href)
    s = re.sub(r'<a\s+[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r"[\2](\1)", s, flags=re.DOTALL)
    # Convert <br> / <br/> to newline
    s = re.sub(r"<br\s*/?>", "\n", s)
    # Strip remaining tags
    s = re.sub(r"<[^>]+>", "", s)
    # Decode HTML entities
    s = html.unescape(s)
    return s.strip()

def _extract_inner_html(tag: str, text: str) -> str:
    """Extract inner HTML from the first occurrence of a given tag."""
    pattern = rf"<{tag}[^>]*>(.*?)</{tag}>"
    m = re.search(pattern, text, re.DOTALL)
    return m.group(1) if m else text

# ---------------------------------------------------------------------------
# Block converters
# ---------------------------------------------------------------------------

def _convert_paragraph(block: WordPressBlock) -> str:
    inner = _extract_inner_html("p", block.html)
    return _strip_html(inner)

def _convert_heading(block: WordPressBlock) -> str:
    level = block.attrs.get("level", 2)
    # Try to extract from the actual heading tag first
    for lvl in range(1, 7):
        m = re.search(rf"<h{lvl}[^>]*>(.*?)</h{lvl}>", block.html, re.DOTALL)
        if m:
            level = lvl
            inner = m.group(1)
            return "#" * level + " " + _strip_html(inner)
    # Fallback: use attrs level and strip all tags
    inner = re.sub(r"<[^>]+>", "", block.html)
    return "#" * int(level) + " " + html.unescape(inner).strip()

def _convert_list(block: WordPressBlock) -> str:
    ordered = block.attrs.get("ordered", False)
    # Also detect from HTML tag
    if "<ol" in block.html:
        ordered = True
    items = re.findall(r"<li[^>]*>(.*?)</li>", block.html, re.DOTALL)
    lines = []
    for i, item_html in enumerate(items, 1):
        text = _strip_html(item_html)
        if ordered:
            lines.append(f"{i}. {text}")
        else:
            lines.append(f"- {text}")
    return "\n".join(lines)

def _convert_code(block: WordPressBlock) -> str:
    # Extract content from <code> inside <pre>, or just <code>
    m = re.search(r"<code[^>]*>(.*?)</code>", block.html, re.DOTALL)
    if m:
        code = m.group(1)
    else:
        m = re.search(r"<pre[^>]*>(.*?)</pre>", block.html, re.DOTALL)
        code = m.group(1) if m else block.html
    code = html.unescape(re.sub(r"<[^>]+>", "", code))
    lang = block.attrs.get("language", "")
    return f"```{lang}\n{code}\n```"

def _convert_image(block: WordPressBlock) -> str:
    # Try attrs first
    src = block.attrs.get("url", "")
    alt = block.attrs.get("alt", "")
    # Fall back to parsing the <img> tag
    if not src:
        m = re.search(r'<img[^>]+src="([^"]*)"', block.html)
        src = m.group(1) if m else ""
    if not alt:
        m = re.search(r'<img[^>]+alt="([^"]*)"', block.html)
        alt = m.group(1) if m else ""
    return f"![{alt}]({src})"

def _convert_quote(block: WordPressBlock) -> str:
    # Extract content inside <blockquote>
    inner = _extract_inner_html("blockquote", block.html)
    text = _strip_html(inner)
    lines = text.split("\n")
    return "\n".join(f"> {line}" for line in lines)

def _convert_separator(_block: WordPressBlock) -> str:
    return "---"

def _convert_preformatted(block: WordPressBlock) -> str:
    m = re.search(r"<pre[^>]*>(.*?)</pre>", block.html, re.DOTALL)
    content = m.group(1) if m else block.html
    content = html.unescape(re.sub(r"<[^>]+>", "", content))
    return f"```\n{content}\n```"

def _convert_html(block: WordPressBlock) -> str:
    return block.html

def _convert_table(block: WordPressBlock) -> str:
    """Convert an HTML table to a Markdown table."""
    rows: list[list[str]] = []
    is_header: list[bool] = []

    # Extract rows from thead and tbody
    for row_match in re.finditer(r"<tr[^>]*>(.*?)</tr>", block.html, re.DOTALL):
        row_html = row_match.group(1)
        cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row_html, re.DOTALL)
        cells = [_strip_html(c) for c in cells]
        rows.append(cells)
        is_header.append("<th" in row_html)

    if not rows:
        return block.html

    # Build markdown table
    lines = []
    # First row
    lines.append("| " + " | ".join(rows[0]) + " |")
    # Separator
    lines.append("| " + " | ".join("---" for _ in rows[0]) + " |")
    # Remaining rows
    for row in rows[1:]:
        # Pad row to match header column count
        while len(row) < len(rows[0]):
            row.append("")
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)

def _convert_embed(block: WordPressBlock) -> str:
    url = block.attrs.get("url", "")
    if url:
        provider = block.attrs.get("providerNameSlug", "")
        caption = ""
        m = re.search(r"<figcaption[^>]*>(.*?)</figcaption>", block.html, re.DOTALL)
        if m:
            caption = _strip_html(m.group(1))
        label = caption or provider or url
        return f"[{label}]({url})"
    # No URL available, pass through raw HTML
    return block.html
