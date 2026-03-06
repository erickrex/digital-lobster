# Scanner Classes

This directory contains individual scanner classes that collect specific types of data from the WordPress site.

## SiteScanner

**File:** `class-site-scanner.php`  
**Class:** `Digital_Lobster_Exporter_Site_Scanner`  
**Priority:** 10 (runs first)

### Purpose
Collects basic site information including URL, WordPress version, multisite status, permalink structure, and registered post types/taxonomies.

### Data Collected

#### Site Information
- Site URL and home URL
- WordPress version
- Multisite status
- Permalink structure
- Site title and description
- Language and charset

#### Post Types
For each registered post type (excluding internal types like revisions):
- Label and all labels
- Description
- Public/hierarchical status
- Archive settings
- Rewrite rules
- Menu icon
- Supported features
- Associated taxonomies
- REST API settings

#### Taxonomies
For each registered taxonomy (excluding internal types):
- Label and all labels
- Description
- Public/hierarchical status
- Rewrite rules
- Associated post types
- REST API settings

#### Content Counts
- Number of published and private posts for each public post type

### Output Structure

```json
{
  "site": {
    "url": "https://example.com",
    "home_url": "https://example.com",
    "wp_version": "6.4.2",
    "is_multisite": false,
    "permalink_structure": "/%postname%/",
    "site_title": "My Site",
    "site_description": "Just another WordPress site",
    "language": "en-US",
    "charset": "UTF-8"
  },
  "post_types": {
    "post": {
      "label": "Posts",
      "labels": {...},
      "description": "",
      "public": true,
      "hierarchical": false,
      "has_archive": false,
      "rewrite": {...},
      "menu_icon": "dashicons-admin-post",
      "supports": {...},
      "taxonomies": ["category", "post_tag"],
      "rest_enabled": true,
      "rest_base": "posts"
    }
  },
  "taxonomies": {
    "category": {
      "label": "Categories",
      "labels": {...},
      "description": "",
      "public": true,
      "hierarchical": true,
      "rewrite": {...},
      "object_types": ["post"],
      "rest_enabled": true,
      "rest_base": "categories"
    }
  },
  "content_counts": {
    "post": 150,
    "page": 12,
    "gd_place": 45
  }
}
```

### Requirements Satisfied
- 3.1: Collect site URL, WordPress version, multisite status
- 3.5: Collect custom post types and taxonomies
- 11.1: Include schema_version field in site_blueprint.json
- 11.2: Include site object with url and wp_version fields

### Testing
Run the test script from the plugin directory:
```bash
wp eval-file test-site-scanner.php
```

Or access via browser (must be logged in as admin):
```
https://yoursite.com/wp-content/plugins/digital-lobster-exporter/test-site-scanner.php
```
