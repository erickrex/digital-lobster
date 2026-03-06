"""YAML frontmatter serialization and parsing.

Handles special YAML characters (colons, quotes, newlines, Unicode)
with proper escaping via pyyaml. Provides round-trip fidelity for
content serialization.
"""

import yaml


def serialize_frontmatter(data: dict) -> str:
    """Convert a dict to a YAML frontmatter string (without --- delimiters).

    Handles special YAML characters including colons, quotes, newlines,
    and Unicode by delegating to pyyaml with safe settings.

    Args:
        data: Dictionary of frontmatter fields to serialize.

    Returns:
        YAML string representation of the data (no trailing newline).
    """
    if not data:
        return ""
    return yaml.dump(
        data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    ).rstrip("\n")


def parse_frontmatter(text: str) -> dict:
    """Parse a YAML frontmatter string back to a dict.

    Args:
        text: YAML string (without --- delimiters).

    Returns:
        Parsed dictionary. Returns empty dict for empty/whitespace input.
    """
    if not text or not text.strip():
        return {}
    result = yaml.safe_load(text)
    if result is None:
        return {}
    return result


def serialize_file(frontmatter: dict, body: str) -> str:
    """Produce the full file content: ---\\nfrontmatter\\n---\\nbody.

    Args:
        frontmatter: Dictionary of frontmatter fields.
        body: Markdown or MDX body content.

    Returns:
        Complete file string with YAML frontmatter delimiters.
    """
    fm_str = serialize_frontmatter(frontmatter)
    return f"---\n{fm_str}\n---\n{body}"


def parse_file(content: str) -> tuple[dict, str]:
    """Parse a full file back into (frontmatter_dict, body_string).

    Expects the file to start with '---' followed by YAML frontmatter,
    then another '---' delimiter, then the body content.

    Args:
        content: Full file content string.

    Returns:
        Tuple of (frontmatter dict, body string).

    Raises:
        ValueError: If the content doesn't have valid frontmatter delimiters.
    """
    if not content.startswith("---\n"):
        raise ValueError("Content does not start with frontmatter delimiter '---'")

    # Find the closing delimiter
    end_idx = content.find("\n---\n", 3)
    if end_idx == -1:
        raise ValueError("Missing closing frontmatter delimiter '---'")

    fm_text = content[4:end_idx]
    body = content[end_idx + 5:]  # skip past \n---\n

    return parse_frontmatter(fm_text), body
