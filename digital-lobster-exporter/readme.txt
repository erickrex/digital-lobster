=== Digital Lobster Exporter ===
Contributors: erickrhein
Tags: migration, export, astrojs
Requires at least: 5.9
Tested up to: 6.4
Requires PHP: 7.4
Stable tag: 1.0.0
License: GPLv2 or later
License URI: https://www.gnu.org/licenses/gpl-2.0.html

Export comprehensive WordPress site data for AI-powered migration to Django Wagtail. One-click solution to collect all migration artifacts.

== Description ==

Digital Lobster Exporter is a WordPress plugin that exports comprehensive website data and metadata for AI-powered migration to modern Python architectures like Django and Wagtail. With a single click, collect all the artifacts needed to recreate your WordPress site in a new platform.

= Key Features =

* **Zero Configuration** - Works immediately after activation
* **Privacy First** - Automatically excludes PII, credentials, and sensitive data
* **Sample-Based Export** - Exports representative content samples, not entire databases
* **Comprehensive Data Collection** - Captures site structure, content, themes, plugins, settings, and more
* **Asynchronous Processing** - AJAX-driven to handle large sites without timeouts
* **Structured Output** - JSON files with consistent schemas for AI parsing
* **One-Click Download** - Get all artifacts in a single ZIP file

= What Gets Exported =

**Site Information**
* Site URL, WordPress version, multisite status
* Permalink structure and rewrite rules
* Registered post types and taxonomies
* Block usage statistics

**Theme Data**
* Active theme files (style.css, theme.json, templates)
* Theme customization settings
* Global styles for block themes
* Custom CSS from all sources

**Plugin Data**
* Complete plugin inventory with versions
* Plugin README files and configurations
* Enhanced detection for popular plugins (ACF, GeoDirectory, WPML, etc.)
* Custom post types and taxonomies registered by plugins

**Content**
* Sample posts, pages, and custom post types
* Block parsing with detailed structure
* HTML snapshots for visual comparison
* Post metadata including SEO data
* Featured images and media references

**Taxonomies**
* All taxonomies with full hierarchy
* Terms with metadata
* Term-to-post relationships

**Media**
* Referenced media files only (not entire library)
* Media mapping file for URL rewriting
* Attachment metadata (alt text, captions)

**Settings**
* Core site settings
* Navigation menus with full hierarchy
* Widget configurations
* User roles and capabilities
* Critical wp_options entries

**Advanced Features**
* ACF field groups and configurations
* Custom field configurations
* Shortcodes inventory
* Form configurations (CF7, Gravity Forms, WPForms, etc.)
* Hooks and filters registry
* REST API endpoints documentation
* Database schema export

**Multilingual Support**
* WPML, Polylang, TranslatePress, Weglot detection
* Translation mappings and configurations

**Environment Information**
* PHP version and extensions
* Database version and configuration
* Server information
* WordPress constants

= Privacy & Security =

* No personally identifiable information (PII) exported
* No user passwords or authentication tokens
* No API keys or sensitive credentials
* All data filtered for privacy compliance
* Requires administrator privileges
* Secure file operations with automatic cleanup

= Use Cases =

* Migrating WordPress sites to Django/Wagtail
* Creating development/staging environments
* Documenting site architecture
* Analyzing site structure and dependencies
* Planning platform migrations

== Installation ==

= Automatic Installation =

1. Log in to your WordPress admin dashboard
2. Navigate to Plugins > Add New
3. Search for "Digital Lobster Exporter"
4. Click "Install Now" and then "Activate"

= Manual Installation =

1. Download the plugin ZIP file
2. Log in to your WordPress admin dashboard
3. Navigate to Plugins > Add New > Upload Plugin
4. Choose the ZIP file and click "Install Now"
5. Click "Activate Plugin"

= After Activation =

1. Navigate to "🧠 Migrate with AI Agents" in the admin menu
2. Click the "Migrate" button to start the export
3. Wait for the scan to complete (progress bar shows status)
4. Click "Download Artifacts (.zip)" to get your export

== Frequently Asked Questions ==

= What data is exported? =

The plugin exports comprehensive site data including content samples, theme files, plugin configurations, settings, taxonomies, media references, and database schema. See the Description section for a complete list.

= Is my data secure? =

Yes! The plugin automatically filters out all personally identifiable information (PII), user passwords, API keys, and sensitive credentials. Only structural and configuration data is exported.

= How long does the export take? =

Export time varies based on site size:
* Small sites (< 100 posts): 30-60 seconds
* Medium sites (100-1000 posts): 1-3 minutes
* Large sites (1000-5000 posts): 3-10 minutes

= Will this export my entire database? =

No. The plugin exports sample content (configurable limits) and database schema only. This keeps export sizes manageable while providing representative data for migration.

= Does this work with multisite? =

Yes! The plugin works on multisite installations. Each site exports independently.

= What plugins are supported? =

The plugin works with any WordPress plugins. Enhanced detection and export for popular plugins like ACF, GeoDirectory, WPML, Yoast SEO, Contact Form 7, and many more.

= Can I configure what gets exported? =

Yes! Navigate to Settings > Digital Lobster Exporter to configure sample content limits, enable/disable HTML snapshots, and adjust other export options.

= Where are the exported files stored? =

Files are temporarily stored in wp-content/uploads/ai_migration_artifacts/ and automatically cleaned up after 24 hours (configurable).

= Does this plugin send data to external servers? =

No! All processing happens on your server. No data is sent to external servers.

= What happens to the export after I download it? =

The export files are automatically deleted after a configurable time period (default: 24 hours) to save disk space and maintain security.

= Can I use this for WooCommerce sites? =

Basic WooCommerce detection is included, but product export is not supported in v1.0. This is planned for a future release.

= What if my site is very large? =

The plugin uses batch processing and AJAX to handle large sites. For sites with 10,000+ posts, you may need to increase PHP memory limit (512MB recommended) and max execution time (600 seconds).

== Screenshots ==

1. Admin page with simple one-click "Migrate" button
2. Progress bar showing scan stages in real-time
3. Success message with download button
4. Settings page for configuring export options
5. Sample of exported JSON structure

== Changelog ==

= 1.0.0 - 2024-01-15 =
* Initial stable release
* Core scanning functionality for 30+ data types
* Comprehensive export structure with JSON schemas
* Admin settings page with configurable limits
* Extensibility hooks and filters
* Security and privacy filters
* Automatic cleanup functionality
* Full documentation suite

== Upgrade Notice ==

= 1.0.0 =
Initial stable release. Install and start migrating!

== System Requirements ==

* WordPress 5.9 or higher
* PHP 7.4 or higher
* PHP ZipArchive extension
* PHP cURL extension
* 256MB PHP memory limit (recommended)
* 300 seconds max execution time (recommended)

== Support ==

For support, please visit:
* Documentation: https://github.com/yourusername/digital-lobster-exporter
* Issues: https://github.com/yourusername/digital-lobster-exporter/issues
* Security: security@example.com (private disclosure)

== Contributing ==

Contributions are welcome! Visit our GitHub repository to contribute.

== Privacy Policy ==

This plugin does not:
* Collect or store personal data
* Send data to external servers
* Use cookies or tracking
* Export personally identifiable information

This plugin does:
* Export site structure and configuration data
* Store temporary files locally (automatically deleted)
* Require administrator privileges for all operations

== Credits ==

Developed for AI-powered WordPress to Django/Wagtail migrations.

== License ==

This plugin is licensed under GPL v2 or later.

Copyright (C) 2024 [Your Name]

This program is free software; you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation; either version 2 of the License, or (at your option) any later version.
