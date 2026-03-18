"""Apply post-pipeline fixes to the output Astro site.

Fixes:
1. Rewrites absolute WordPress URLs to relative paths in BaseLayout.astro
2. Consolidates inline CSS files into a single file
3. Regenerates the homepage with proper content
"""
from __future__ import annotations

import os
import re
from pathlib import Path

SITE_URL = "https://horuswp.com"
ASTRO_DIR = Path("output/astro-site")
STYLES_DIR = ASTRO_DIR / "public" / "styles"
LAYOUTS_DIR = ASTRO_DIR / "src" / "layouts"
PAGES_DIR = ASTRO_DIR / "src" / "pages"


def rewrite_urls(html: str) -> str:
    """Replace absolute horuswp.com URLs in href attributes only."""
    import re as _re
    base = SITE_URL.rstrip("/")
    variants = [base, base.replace("https://", "http://")]

    def _rewrite_href(match):
        quote = match.group(1)
        url = match.group(2)
        for variant in variants:
            if url.startswith(variant + "/"):
                url = url[len(variant):]
                break
            elif url == variant:
                url = "/"
                break
        return f"href={quote}{url}{quote}"

    return _re.sub(r"""href=(['"])(.*?)\1""", _rewrite_href, html)


def consolidate_inline_css() -> None:
    """Merge rendered_inline_*.css into one file and remove originals."""
    if not STYLES_DIR.exists():
        return
    inline_files = sorted(
        f for f in STYLES_DIR.iterdir()
        if re.match(r"rendered_inline_\d+\.css$", f.name)
    )
    if not inline_files:
        return
    parts = []
    for f in inline_files:
        parts.append(f.read_text(encoding="utf-8", errors="replace"))
        f.unlink()
    combined = STYLES_DIR / "rendered_inline_all.css"
    combined.write_text("\n".join(parts), encoding="utf-8")
    print(f"Consolidated {len(inline_files)} inline CSS files → rendered_inline_all.css")


def fix_base_layout() -> None:
    """Rewrite URLs and fix CSS links in BaseLayout.astro.

    Restores the original layout from the pipeline artifact first so that
    image src/srcset attributes are preserved with their original absolute
    URLs (they still load from the WordPress host).
    """
    layout_path = LAYOUTS_DIR / "BaseLayout.astro"

    # Restore from pipeline artifact if available (has untouched absolute URLs)
    artifact = Path("output/3cc8b34678354139940e338421e2f336/layouts")
    if artifact.exists():
        import json as _json
        layouts = _json.loads(artifact.read_text(encoding="utf-8"))
        if "BaseLayout.astro" in layouts:
            layout_path.write_text(layouts["BaseLayout.astro"], encoding="utf-8")

    if not layout_path.exists():
        return
    content = layout_path.read_text(encoding="utf-8")

    # Rewrite only href attributes (navigation links) — leave src/srcset alone
    content = rewrite_urls(content)

    # Replace 100+ inline CSS link tags with single consolidated one
    lines = content.split("\n")
    new_lines = []
    skipped_inline = False
    for line in lines:
        if re.search(r'href="/styles/rendered_inline_\d+\.css"', line):
            if not skipped_inline:
                new_lines.append('    <link rel="stylesheet" href="/styles/rendered_inline_all.css" />')
                skipped_inline = True
            continue
        new_lines.append(line)
    content = "\n".join(new_lines)

    layout_path.write_text(content, encoding="utf-8")
    print("Fixed BaseLayout.astro: rewrote URLs, consolidated CSS links")


def fix_homepage() -> None:
    """Replace generic homepage with proper content."""
    index_path = PAGES_DIR / "index.astro"
    index_path.write_text("""---
import BaseLayout from '../layouts/BaseLayout.astro';
import { getCollection } from 'astro:content';
const allPosts = (await getCollection('posts')).slice(0, 6);
---
<BaseLayout title="HorusWP">
  <section class="hero">
    <h1>HorusWP</h1>
    <p>Find your twin websites using the same technology</p>
    <p class="hero-sub">Copy what works for you and avoid what doesn't</p>
  </section>

  <section class="latest-posts">
    <h2>Latest Posts</h2>
    <ul class="post-list">
      {allPosts.map((post) => (
        <li>
          <a href={`/posts/${post.slug}`}>
            <h3>{post.data.title}</h3>
            {post.data.excerpt && <p>{post.data.excerpt}</p>}
          </a>
        </li>
      ))}
    </ul>
  </section>

  <section class="explore-section">
    <h2>Explore Themes</h2>
    <a href="/gd_theme" class="explore-link">Browse all Themes &rarr;</a>
  </section>

  <section class="explore-section">
    <h2>Explore Plugins</h2>
    <a href="/gd_plugin" class="explore-link">Browse all Plugins &rarr;</a>
  </section>

  <section class="explore-section">
    <h2>Explore Sites</h2>
    <a href="/gd_site" class="explore-link">Browse all Sites &rarr;</a>
  </section>

  <section class="explore-section">
    <h2>Explore Hosting</h2>
    <a href="/gd_hosting" class="explore-link">Browse all Hosting &rarr;</a>
  </section>
</BaseLayout>
""", encoding="utf-8")
    print("Fixed index.astro: replaced generic homepage with proper content")


if __name__ == "__main__":
    consolidate_inline_css()
    fix_base_layout()
    fix_homepage()
    print("Done! Run 'npm run build' to verify.")
