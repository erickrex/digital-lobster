# Digital Lobster Exporter Unit Tests

This directory contains unit tests for the Digital Lobster Exporter plugin scanner classes.

## Overview

The test suite covers the following scanner classes:
- **SiteScanner**: Tests for site information collection
- **ThemeScanner**: Tests for theme file copying and metadata collection
- **PluginScanner**: Tests for plugin detection logic and fingerprinting
- **ContentScanner**: Tests for content query logic and block parsing
- **TaxonomyScanner**: Tests for taxonomy and term relationship handling
- **MediaScanner**: Tests for media file identification and mapping

## Requirements

- PHP 7.4 or higher
- PHPUnit 9.x or higher
- Composer (for installing PHPUnit)

## Installation

Install PHPUnit via Composer:

```bash
composer require --dev phpunit/phpunit ^9.0
```

## Running Tests

Run all tests:

```bash
vendor/bin/phpunit
```

Run a specific test file:

```bash
vendor/bin/phpunit tests/SiteScannerTest.php
```

Run tests with coverage report (requires Xdebug):

```bash
vendor/bin/phpunit --coverage-html coverage/
```

## Test Structure

### Bootstrap File
`tests/bootstrap.php` - Initializes the test environment and loads required files

### Mock Functions
`tests/mocks/wordpress-functions.php` - Provides mock implementations of WordPress functions

### Test Files
- `tests/SiteScannerTest.php` - Tests for site data collection
- `tests/ThemeScannerTest.php` - Tests for theme file exports
- `tests/PluginScannerTest.php` - Tests for plugin detection
- `tests/ContentScannerTest.php` - Tests for content queries
- `tests/TaxonomyScannerTest.php` - Tests for taxonomy exports
- `tests/MediaScannerTest.php` - Tests for media identification

## Writing Tests

### Test Naming Convention
- Test methods should start with `test_`
- Use descriptive names: `test_scanner_returns_expected_structure()`

### Assertions
Common assertions used:
- `assertInstanceOf()` - Check object type
- `assertIsArray()` - Check if value is array
- `assertArrayHasKey()` - Check if array has key
- `assertEquals()` - Check equality
- `assertTrue()` / `assertFalse()` - Check boolean values
- `assertGreaterThan()` - Check numeric comparisons

### Mock Data
Set up mock data in `setUp()` method:

```php
protected function setUp(): void {
    parent::setUp();
    
    global $mock_posts;
    $mock_posts = array(
        1 => (object) array(
            'ID' => 1,
            'post_title' => 'Test Post',
        ),
    );
}
```

## Integration Tests

Integration tests verify the complete scan workflow on a live WordPress installation.

### Running Integration Tests

**PHPUnit Integration Tests:**
```bash
vendor/bin/phpunit tests/IntegrationTest.php
```

**WordPress CLI Integration Test:**
```bash
wp eval-file test-integration-full-scan.php
```

### Integration Test Coverage

The integration test suite covers:
- ✅ Complete scan execution
- ✅ ZIP structure and contents validation
- ✅ JSON schema validation
- ✅ GeoDirectory plugin integration
- ✅ ACF plugin integration
- ✅ Multilingual plugin integration (WPML, Polylang, TranslatePress)
- ✅ Multiple plugins active simultaneously
- ✅ Error handling and recovery
- ✅ Progress tracking
- ✅ Content sampling limits
- ✅ ZIP compression and file size
- ✅ Performance metrics

### Test Scenarios

**Scenario 1: Basic WordPress Site**
- Fresh WordPress installation
- Default theme and plugins
- Sample content

**Scenario 2: GeoDirectory Site**
- GeoDirectory plugin active
- Multiple custom post types (places, events, custom listings)
- GeoDirectory-specific metadata

**Scenario 3: Multilingual Site**
- WPML, Polylang, or TranslatePress active
- Multiple languages configured
- Translated content

**Scenario 4: ACF Site**
- Advanced Custom Fields active
- Custom field groups defined
- Custom fields in content

**Scenario 5: Complex Site**
- Multiple plugins active
- Various custom post types
- Large content volume

## Test Coverage

The test suite covers:
- ✅ Scanner instantiation
- ✅ Data structure validation
- ✅ Data collection methods
- ✅ Filtering and sanitization
- ✅ Error handling
- ✅ Edge cases
- ✅ Full scan workflow
- ✅ ZIP creation and validation
- ✅ JSON schema compliance
- ✅ Plugin-specific integrations

## Continuous Integration

These tests can be integrated into CI/CD pipelines:

### GitHub Actions Example
```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: php-actions/composer@v6
      - uses: php-actions/phpunit@v3
```

## Troubleshooting

### Common Issues

**Issue**: `Class not found` errors
**Solution**: Ensure `tests/bootstrap.php` is loading all required files

**Issue**: Mock functions not working
**Solution**: Check that `tests/mocks/wordpress-functions.php` is loaded before scanner classes

**Issue**: Tests fail with file system errors
**Solution**: Mock file operations or use temporary directories

## Contributing

When adding new scanner classes:
1. Create a corresponding test file in `tests/`
2. Add mock functions to `tests/mocks/wordpress-functions.php` if needed
3. Follow existing test patterns
4. Ensure all public methods are tested
5. Test both success and failure scenarios

## License

Same as the main plugin (GPL v2 or later)
