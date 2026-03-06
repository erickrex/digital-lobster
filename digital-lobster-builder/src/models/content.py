import yaml
from pydantic import BaseModel


class WordPressBlock(BaseModel):
    name: str
    attrs: dict
    html: str


class WordPressContentItem(BaseModel):
    id: int
    post_type: str
    title: str
    slug: str
    status: str
    date: str
    excerpt: str | None
    blocks: list[WordPressBlock]
    raw_html: str
    taxonomies: dict[str, list]
    meta: dict[str, str]
    featured_media: dict | None
    legacy_permalink: str
    seo: dict | None


class SerializedContent(BaseModel):
    collection: str
    slug: str
    frontmatter: dict
    body: str
    file_extension: str  # "md" or "mdx"

    def to_file_content(self) -> str:
        """Serialize to the full file string: ---\nfrontmatter\n---\nbody"""
        fm = yaml.dump(
            self.frontmatter,
            default_flow_style=False,
            allow_unicode=True,
        ).strip()
        return f"---\n{fm}\n---\n{self.body}"
