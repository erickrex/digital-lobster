# Digital Lobster Exporter

**AI-Powered WordPress Site Exporter**

Digital Lobster Exporter is a WordPress plugin that exports comprehensive website data and metadata for AI-powered migration to modern architectures like Astro and Strapi. With a single click, collect all the artifacts needed to recreate your WordPress site in a new platform.

## Features

- **Zero Configuration**: Works immediately after activation
- **Privacy First**: Automatically excludes PII, credentials, and sensitive data
- **Sample-Based Export**: Exports representative content samples, not entire databases
- **Comprehensive Data Collection**: Captures site structure, content, themes, plugins, settings, and more
- **Guided Export UI**: Runs as a single export request with clear on-page status messaging
- **Structured Output**: JSON files with consistent schemas for AI parsing
- **One-Click Download**: Get all artifacts in a single ZIP file

## System Requirements

### Minimum Requirements

- **WordPress Version**: 5.9 or higher
- **PHP Version**: 7.4 or higher
- **PHP Extensions**:
  - ZipArchive (for creating ZIP archives)
  - cURL (for HTML snapshot generation)
  - JSON (typically enabled by default)
- **Memory Limit**: 256MB recommended
- **Max Execution Time**: 300 seconds recommended
- **Disk Space**: Varies based on site size (typically 50-500MB for export)

### Recommended Requirements

- **WordPress Version**: 6.0 or higher
- **PHP Version**: 8.0 or higher
- **Memory Limit**: 512MB or higher for large sites
- **Max Execution Time**: 600 seconds for sites with 5000+ posts

### Server Compatibility

- Apache, Nginx, or any WordPress-compatible web server
- MySQL 5.6+ or MariaDB 10.0+
- SSL/HTTPS recommended for secure downloads

## Installation

### Method 1: WordPress Admin Upload

1. Download the plugin ZIP file
2. Log in to your WordPress admin dashboard
3. Navigate to **Plugins > Add New**
4. Click **Upload Plugin**
5. Choose the downloaded ZIP file
6. Click **Install Now**
7. Click **Activate Plugin**

### Method 2: Manual Installation

1. Download and extract the plugin ZIP file
2. Upload the `digital-lobster-exporter` folder to `/wp-content/plugins/`
3. Log in to your WordPress admin dashboard
4. Navigate to **Plugins**
5. Find "Digital Lobster Exporter" and click **Activate**

### Method 3: WP-CLI

```bash
wp plugin install digital-lobster-exporter.zip --activate
```

## Usage

### Basic Usage

1. After activation, navigate to **🧠 Migrate with AI Agents** in the WordPress admin sidebar
2. Review the information on the page about what will be exported
3. Click the **Migrate** button
4. Keep the page open while the export request runs (typically 1-5 minutes)
5. Click **Download Artifacts (.zip)** when the scan completes
6. Save the ZIP file to your local machine

### Configuring Sample Limits

To customize how much sample content is exported:

1. Navigate to **🧠 Migrate with AI Agents** in the WordPress admin sidebar
2. Click the **Settings** toggle to expand the inline settings panel
3. Adjust the following options:
   - **Max Posts**: Number of sample posts to export (default: 100)
   - **Max Pages**: Number of sample pages to export (default: 50)
   - **Max Per Custom Post Type**: Sample limit for each CPT (default: 50)
   - **Include HTML Snapshots**: Enable/disable rendered HTML exports
   - **Cleanup After Hours**: Auto-delete old exports after X hours (default: 24)
   - **Batch Size**: Items processed per batch (default: 50)
4. Click **Save Settings**

## Exported File Structure

The downloaded ZIP file contains the following structure:

```
migration-artifacts-{timestamp}.zip
├── site_blueprint.json              # Core site information and structure
├── site_settings.json               # WordPress core settings
├── site_environment.json            # Server and PHP environment info
├── schema_mysql.sql                 # Complete database schema
│
├── content/                         # Sample content exports
│   ├── posts/                       # Blog posts
│   │   ├── sample-post-1.json
│   │   └── sample-post-2.json
│   ├── pages/                       # Pages
│   │   └── about.json
│   └── {custom_post_type}/          # Custom post types (dynamic)
│       └── sample-item.json
│
├── snapshots/                       # Rendered HTML snapshots
│   ├── sample-post-1.html
│   ├── about.html
│   └── sample-place.html
│
├── taxonomies.json                  # All taxonomies and terms
│
├── media/                           # Referenced media files
│   ├── 2024/09/image.jpg
│   └── media_map.json               # URL mapping for media files
│
├── theme/                           # Active theme files
│   ├── style.css
│   ├── theme.json                   # Block theme configuration
│   ├── functions.php
│   └── templates/                   # Template files
│       ├── header.php
│       ├── footer.php
│       └── ...
│
├── theme_mods.json                  # Theme customizations
├── global_styles.json               # Block theme global styles
├── customizer_settings.json         # Customizer configurations
├── css_sources.json                 # Custom CSS documentation
├── customizer_custom.css            # Custom CSS from Customizer
│
├── plugins/                         # Plugin information
│   ├── readmes/                     # Plugin README files
│   ├── feature_maps/                # Plugin feature documentation
│   └── templates/                   # Plugin template files
│
├── plugin_behaviors.json            # Plugin behavioral fingerprints
├── plugins_fingerprint.json         # Detailed plugin features
├── plugins_templates_manifest.json  # Plugin templates index
│
├── blocks_usage.json                # Block usage statistics
├── block_patterns.json              # Registered block patterns
│
├── menus.json                       # Navigation menus
├── widgets.json                     # Sidebar widgets
│
├── user_roles.json                  # User roles and capabilities
├── site_options.json                # Critical wp_options entries
│
├── acf_field_groups.json            # ACF field configurations
├── custom_fields_config.json        # Other custom field plugins
│
├── shortcodes_inventory.json        # Shortcode usage inventory
├── forms_config.json                # Form plugin configurations
│
├── hooks_registry.json              # Registered hooks and filters
├── enqueued_assets.json             # Scripts and styles
│
├── page_templates.json              # Page template assignments
├── rest_api_endpoints.json          # REST API routes
│
├── redirects_candidates.csv         # Redirect mapping
├── rewrite_rules.json               # Custom rewrite rules
│
├── custom_tables_data.json          # Custom table sample data
├── custom_tables_manifest.json      # Custom table documentation
│
├── translations.json                # Multilingual configurations
│
├── assets/                          # Theme/plugin assets
│   ├── js/
│   └── css/
│
└── error_log.json                   # Export errors and warnings
```

### Key Files Explained

#### site_blueprint.json
Contains high-level site information including WordPress version, active theme, installed plugins, content structure, and block usage statistics.

#### content/{post_type}/{slug}.json
Individual content items with full metadata, parsed blocks, taxonomies, custom fields, and internal links.

#### snapshots/{slug}.html
Rendered HTML output of each content item for visual comparison and testing.

#### taxonomies.json
Complete taxonomy structure with terms, hierarchies, term metadata, and term-to-post relationships.

#### media_map.json
Maps original WordPress media URLs to exported file paths for URL rewriting in the new system.

#### schema_mysql.sql
Complete database schema including all tables (core and custom) for reference.

## FAQ

### General Questions

**Q: Does this plugin modify my WordPress site?**  
A: No. The plugin only reads data and creates export files. It does not modify your database, content, or settings.

**Q: How long does the export process take?**  
A: Typically 1-5 minutes for most sites. Larger sites (5000+ posts) may take 10-15 minutes.

**Q: How much disk space do I need?**  
A: Export size varies based on your site. Typical exports range from 50MB to 500MB. Ensure you have at least 1GB of free space.

**Q: Can I run multiple exports?**  
A: Yes, but only one export can run at a time. Old exports are automatically cleaned up after 24 hours (configurable).

**Q: Is my data secure?**  
A: Yes. The plugin automatically excludes passwords, API keys, and PII. Exports are stored in a secure directory and require administrator access to download.

### Content Export Questions

**Q: Why are only sample content items exported?**  
A: The plugin exports representative samples to keep file sizes manageable and focus on structure rather than bulk data. This is sufficient for AI-powered migration planning.

**Q: Can I export all my content?**  
A: You can increase sample limits in the settings panel on the export page, but exporting thousands of posts may cause timeouts and very large files.

**Q: Are custom post types supported?**  
A: Yes! The plugin automatically detects and exports samples from all registered custom post types.

**Q: What about GeoDirectory listings?**  
A: Fully supported. The plugin dynamically detects all GeoDirectory custom post types and exports their custom fields and metadata.

**Q: Are WooCommerce products exported?**  
A: No. WooCommerce export is explicitly out of scope for this plugin.

### Plugin Compatibility Questions

**Q: Which plugins are specifically supported?**  
A: Enhanced detection for:
- GeoDirectory (all custom post types)
- Advanced Custom Fields (ACF)
- Kadence Blocks
- WPML / Polylang / TranslatePress (multilingual)
- Contact Form 7, Gravity Forms, WPForms, Ninja Forms
- Yoast SEO, Rank Math, All in One SEO
- Common redirect plugins

**Q: What if I use a plugin not on the list?**  
A: The plugin still exports generic information about all installed plugins, including custom post types, taxonomies, and database tables they create.

**Q: Are page builders supported?**  
A: Block-based content is fully parsed. Classic page builders (Elementor, Divi, etc.) are exported as raw HTML for reference.

### Technical Questions

**Q: What if the export times out?**  
A: The plugin uses AJAX for asynchronous processing to avoid timeouts. If issues persist, try:
- Reducing sample limits in settings
- Increasing PHP max_execution_time
- Increasing PHP memory_limit
- Disabling HTML snapshots temporarily

**Q: Can I resume a failed export?**  
A: Not currently. If an export fails, start a new one. Check error_log.json in the export for details about what failed.

**Q: Where are temporary files stored?**  
A: In `/wp-content/uploads/ai_migration_artifacts/`. Files are automatically cleaned up after download or after the configured time period.

**Q: Can I automate exports?**  
A: Not in the current version. Scheduled exports may be added in a future release.

## Troubleshooting Guide

### Export Won't Start

**Symptom**: Clicking "Migrate" button does nothing or shows an error.

**Solutions**:
1. Check browser console for JavaScript errors
2. Verify you're logged in as an administrator
3. Try disabling other plugins temporarily
4. Clear browser cache and reload the page
5. Check that AJAX is not blocked by security plugins

### Export Fails or Stops Mid-Process

**Symptom**: Progress bar stops or shows an error message.

**Solutions**:
1. Check PHP error logs for memory or timeout errors
2. Increase PHP memory_limit to 512MB or higher
3. Increase max_execution_time to 600 seconds
4. Reduce sample limits in plugin settings
5. Disable HTML snapshots temporarily
6. Check disk space availability

### Download Button Doesn't Appear

**Symptom**: Export completes but no download button shows.

**Solutions**:
1. Refresh the page
2. Check browser console for errors
3. Verify the ZIP file exists in `/wp-content/uploads/ai_migration_artifacts/`
4. Check file permissions on the uploads directory
5. Try manually downloading from the artifacts directory

### ZIP File is Corrupted or Won't Open

**Symptom**: Downloaded ZIP file can't be extracted.

**Solutions**:
1. Verify PHP ZipArchive extension is installed
2. Check available disk space during export
3. Try downloading again (file may have been interrupted)
4. Check PHP error logs for ZipArchive errors
5. Verify file wasn't truncated during download

### Missing Content or Files

**Symptom**: Expected content or files are not in the export.

**Solutions**:
1. Check error_log.json in the export for warnings
2. Verify content is published (not draft or private)
3. Check file permissions on theme/plugin directories
4. Increase sample limits if expecting more content
5. Verify plugins are active (inactive plugins may not export fully)

### Memory Errors

**Symptom**: "Allowed memory size exhausted" errors.

**Solutions**:
1. Increase PHP memory_limit in php.ini or wp-config.php:
   ```php
   define('WP_MEMORY_LIMIT', '512M');
   define('WP_MAX_MEMORY_LIMIT', '512M');
   ```
2. Reduce batch size in plugin settings
3. Reduce sample limits
4. Disable HTML snapshots
5. Contact your hosting provider to increase limits

### Timeout Errors

**Symptom**: "Maximum execution time exceeded" errors.

**Solutions**:
1. Increase max_execution_time in php.ini:
   ```ini
   max_execution_time = 600
   ```
2. Or add to wp-config.php:
   ```php
   set_time_limit(600);
   ```
3. Reduce sample limits
4. Process fewer items per batch
5. Contact your hosting provider if you can't modify PHP settings

### Permission Errors

**Symptom**: "Permission denied" or "Failed to create directory" errors.

**Solutions**:
1. Verify wp-content/uploads directory is writable (755 or 775)
2. Check ownership of uploads directory
3. Create ai_migration_artifacts directory manually with proper permissions
4. Contact your hosting provider for assistance

### Plugin Conflicts

**Symptom**: Export fails only when certain plugins are active.

**Solutions**:
1. Identify conflicting plugin by disabling plugins one at a time
2. Check for security plugins blocking AJAX requests
3. Check for caching plugins interfering with progress tracking
4. Report compatibility issues to plugin support

### Large Site Issues

**Symptom**: Sites with 5000+ posts fail to export.

**Solutions**:
1. Reduce sample limits significantly (e.g., 2 posts, 1 page)
2. Disable HTML snapshots
3. Increase PHP memory and execution time limits
4. Consider exporting in multiple passes (different post types)
5. Use a staging environment with higher resource limits

## Extensibility Hooks

The plugin provides several hooks for developers to extend functionality.

### Filters

#### Modify Export Data

```php
// Modify content before export
add_filter('digital_lobster_export_content', function($content, $post_type) {
    // Add custom fields or modify structure
    $content['custom_field'] = 'custom_value';
    return $content;
}, 10, 2);

// Modify site settings export
add_filter('digital_lobster_export_settings', function($settings) {
    // Add or modify settings
    $settings['custom_setting'] = get_option('my_custom_option');
    return $settings;
}, 10, 1);

// Modify plugin fingerprint data
add_filter('digital_lobster_plugin_fingerprint', function($fingerprint, $plugin_file) {
    // Add custom plugin detection
    if ($plugin_file === 'my-plugin/my-plugin.php') {
        $fingerprint['custom_features'] = ['feature1', 'feature2'];
    }
    return $fingerprint;
}, 10, 2);
```

#### Register Custom Scanners

```php
// Add a custom scanner class
add_filter('digital_lobster_scanner_classes', function($scanners) {
    $scanners[] = 'My_Custom_Scanner';
    return $scanners;
}, 10, 1);
```

#### Modify Sample Limits

```php
// Override sample limits programmatically
add_filter('digital_lobster_sample_limits', function($limits) {
    $limits['post'] = 10;
    $limits['my_custom_post_type'] = 20;
    return $limits;
}, 10, 1);
```

#### Filter Sensitive Data

```php
// Add custom sensitive data filters
add_filter('digital_lobster_sensitive_meta_keys', function($keys) {
    $keys[] = 'my_secret_field';
    $keys[] = 'api_token';
    return $keys;
}, 10, 1);
```

### Actions

#### Hook into Scan Process

```php
// Before scan starts
add_action('digital_lobster_before_scan', function() {
    // Perform setup tasks
    error_log('Digital Lobster scan starting');
});

// After scan completes
add_action('digital_lobster_after_scan', function($results) {
    // Perform cleanup or notifications
    error_log('Digital Lobster scan completed');
}, 10, 1);

// Before each scanner runs
add_action('digital_lobster_before_scanner', function($scanner_name) {
    error_log("Running scanner: {$scanner_name}");
}, 10, 1);

// After each scanner completes
add_action('digital_lobster_after_scanner', function($scanner_name, $data) {
    error_log("Completed scanner: {$scanner_name}");
}, 10, 2);
```

#### Hook into Export Process

```php
// Before export files are generated
add_action('digital_lobster_before_export', function($scan_data) {
    // Modify or log scan data
}, 10, 1);

// After export files are generated
add_action('digital_lobster_after_export', function($export_path) {
    // Perform additional processing
    error_log("Export created at: {$export_path}");
}, 10, 1);
```

#### Hook into Packaging Process

```php
// Before ZIP creation
add_action('digital_lobster_before_package', function($artifacts_dir) {
    // Add custom files to export
    file_put_contents($artifacts_dir . '/custom_file.txt', 'Custom data');
}, 10, 1);

// After ZIP creation
add_action('digital_lobster_after_package', function($zip_path) {
    // Upload to cloud storage, send notifications, etc.
    error_log("ZIP created at: {$zip_path}");
}, 10, 1);
```

### Creating Custom Scanners

To create a custom scanner:

```php
class My_Custom_Scanner {
    
    public function scan() {
        $data = [];
        
        // Collect your custom data
        $data['custom_info'] = $this->get_custom_info();
        
        return $data;
    }
    
    private function get_custom_info() {
        // Your custom logic here
        return [
            'key' => 'value'
        ];
    }
}

// Register your scanner
add_filter('digital_lobster_scanner_classes', function($scanners) {
    $scanners[] = 'My_Custom_Scanner';
    return $scanners;
});
```

## Support

### Getting Help

- **Documentation**: Review this README and the exported error_log.json file
- **WordPress Forums**: Search for similar issues
- **GitHub Issues**: Report bugs or request features (if applicable)

### Reporting Bugs

When reporting issues, please include:

1. WordPress version
2. PHP version
3. Plugin version
4. Active theme and plugins
5. Error messages from browser console
6. Error messages from PHP error log
7. Contents of error_log.json from export (if available)
8. Steps to reproduce the issue

### Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Areas for improvement:
- Additional plugin detection and fingerprinting
- Performance optimizations for large sites
- Additional export formats
- Improved error handling and recovery
- Additional test scenarios
- Translations

**Development Setup:**

```bash
# Clone repository
git clone https://github.com/yourusername/digital-lobster-exporter.git
cd digital-lobster-exporter

# Install dependencies
composer install

# Run tests
composer test

# Run integration tests
vendor/bin/phpunit tests/IntegrationTest.php
```

## Privacy and Data Handling

### What is Exported

- Site structure and configuration
- Sample content (configurable limits)
- Theme files and customizations
- Plugin information and configurations
- Database schema (structure only)
- Referenced media files
- Settings and options

### What is NOT Exported

- User passwords or password hashes
- API keys and authentication tokens
- Personally Identifiable Information (PII)
- User email addresses (except admin email in settings)
- Form submissions or user-generated data
- Complete user accounts
- Payment information
- Session data or transients

### Data Storage

- Exports are stored temporarily in `/wp-content/uploads/ai_migration_artifacts/`
- Files are automatically deleted after 24 hours (configurable)
- Downloads require administrator privileges
- No data is sent to external servers

## Distribution & Compatibility

### Tested Versions

- **WordPress**: 5.9, 6.0, 6.1, 6.2, 6.3, 6.4
- **PHP**: 7.4, 8.0, 8.1, 8.2, 8.3
- **MySQL**: 5.7, 8.0
- **MariaDB**: 10.3, 10.6

### Browser Compatibility

The admin interface works with all modern browsers:
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

### Plugin Compatibility

Digital Lobster Exporter is designed to work alongside any WordPress plugins. Enhanced detection and export for:

- **Content Builders**: Elementor, Beaver Builder, Divi
- **SEO**: Yoast SEO, Rank Math, All in One SEO
- **Forms**: Contact Form 7, Gravity Forms, WPForms, Ninja Forms
- **Custom Fields**: Advanced Custom Fields (ACF), Pods, Metabox
- **Multilingual**: WPML, Polylang, TranslatePress, Weglot
- **Directory**: GeoDirectory (with dynamic CPT detection)
- **Blocks**: Kadence Blocks, Stackable, GenerateBlocks

### Known Limitations

- WooCommerce products not exported (out of scope for v1.0)
- Full database export not included (sample content only)
- No incremental exports (full export each time)
- Requires administrator privileges

## License

This plugin is licensed under the GPL v2 or later.

```
Copyright (C) 2024 [Your Name]

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301 USA
```

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for detailed version history.

### Version 1.0.0 (2024-01-15)
- Initial stable release
- Core scanning functionality for 30+ data types
- Comprehensive export structure with JSON schemas
- Admin settings page with configurable limits
- Extensibility hooks and filters
- Security and privacy filters
- Automatic cleanup functionality
- Full documentation suite
- Comprehensive unit and integration test suite
- Support for GeoDirectory, ACF, and multilingual plugins

## Support

### Getting Help

- **Documentation**: See individual scanner usage guides in repository
- **Issues**: Report bugs on [GitHub Issues](https://github.com/yourusername/digital-lobster-exporter/issues)
- **Security**: Report vulnerabilities privately to security@example.com

### Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Testing

The plugin includes comprehensive unit and integration tests:

- **Unit Tests**: Test individual scanner classes in isolation
- **Integration Tests**: Test complete scan workflow on live WordPress installations

**Running Tests:**

```bash
# Install dependencies
composer install

# Run unit tests
vendor/bin/phpunit

# Run integration tests
vendor/bin/phpunit tests/IntegrationTest.php

# Run WordPress CLI integration test (requires WordPress installation)
wp eval-file test-integration-full-scan.php
```

**Test Coverage:**
- ✅ All 23 scanner classes
- ✅ Complete scan workflow
- ✅ ZIP structure validation
- ✅ JSON schema compliance
- ✅ Plugin integrations (GeoDirectory, ACF, multilingual)
- ✅ Error handling and recovery
- ✅ Performance benchmarks

See [TESTING.md](TESTING.md) for detailed testing guide and [tests/INTEGRATION-TESTS.md](tests/INTEGRATION-TESTS.md) for integration testing documentation.

## Credits

Developed for AI-powered WordPress to Astro/Strapi migrations.

### Development Team

- Lead Developer: [Your Name]
- Contributors: [List contributors]

### Acknowledgments

- WordPress community for excellent documentation
- Plugin reviewers for valuable feedback
- Beta testers for thorough testing

---

**Note**: This plugin is designed to work with AI migration systems. The exported data is optimized for machine parsing and may require additional processing for human consumption.
