<?php
/**
 * Integration Tests for Full Scan Process
 *
 * Tests the complete scan workflow including:
 * - Full scan execution
 * - ZIP structure and contents
 * - JSON schema validation
 * - Plugin-specific scenarios (GeoDirectory, ACF, multilingual)
 *
 * @package Digital_Lobster_Exporter
 */

use PHPUnit\Framework\TestCase;

/**
 * Integration Test Class
 */
class IntegrationTest extends TestCase {

	/**
	 * Scanner instance.
	 *
	 * @var Digital_Lobster_Exporter_Scanner
	 */
	private $scanner;

	/**
	 * Temporary export directory.
	 *
	 * @var string
	 */
	private $temp_export_dir;

	/**
	 * Set up test environment.
	 */
	protected function setUp(): void {
		parent::setUp();

		// Create temporary export directory
		$this->temp_export_dir = sys_get_temp_dir() . '/digital_lobster_integration_test_' . time();
		if ( ! file_exists( $this->temp_export_dir ) ) {
			mkdir( $this->temp_export_dir, 0755, true );
		}

		// Mock WordPress constants
		if ( ! defined( 'DIGITAL_LOBSTER_EXPORTER_PATH' ) ) {
			define( 'DIGITAL_LOBSTER_EXPORTER_PATH', dirname( __DIR__ ) . '/' );
		}

		// Set up mock WordPress environment
		$this->setup_mock_wordpress_environment();

		// Load required classes
		require_once DIGITAL_LOBSTER_EXPORTER_PATH . 'includes/class-scanner.php';
		require_once DIGITAL_LOBSTER_EXPORTER_PATH . 'includes/class-exporter.php';
		require_once DIGITAL_LOBSTER_EXPORTER_PATH . 'includes/class-packager.php';
		require_once DIGITAL_LOBSTER_EXPORTER_PATH . 'includes/class-security-filters.php';

		// Create scanner instance
		$this->scanner = new Digital_Lobster_Exporter_Scanner();
	}

	/**
	 * Tear down test environment.
	 */
	protected function tearDown(): void {
		// Clean up temporary directory
		if ( file_exists( $this->temp_export_dir ) ) {
			$this->recursiveRemoveDirectory( $this->temp_export_dir );
		}

		parent::tearDown();
	}

	/**
	 * Test complete scan on test WordPress site.
	 *
	 * @group integration
	 */
	public function test_complete_scan_execution() {
		// Execute full scan
		$result = $this->scanner->run_scan();

		// Assert scan completed successfully
		$this->assertTrue( $result['success'], 'Scan should complete successfully' );
		$this->assertIsArray( $result['results'], 'Results should be an array' );
		$this->assertArrayHasKey( 'site', $result['results'], 'Results should include site data' );
		$this->assertArrayHasKey( 'theme', $result['results'], 'Results should include theme data' );
		$this->assertArrayHasKey( 'plugins', $result['results'], 'Results should include plugins data' );

		// Verify no critical errors
		if ( isset( $result['errors'] ) && ! empty( $result['errors'] ) ) {
			$critical_errors = array_filter( $result['errors'], function( $error ) {
				return $error['severity'] === 'critical';
			});
			$this->assertEmpty( $critical_errors, 'Should not have critical errors' );
		}
	}

	/**
	 * Test ZIP structure and contents.
	 *
	 * @group integration
	 */
	public function test_zip_structure_and_contents() {
		// Run scan to generate ZIP
		$result = $this->scanner->run_scan();
		$this->assertTrue( $result['success'], 'Scan must succeed to test ZIP' );

		// Get ZIP file path
		$this->assertArrayHasKey( 'zip_filename', $result['results'], 'Results should include ZIP filename' );
		$zip_filename = $result['results']['zip_filename'];

		// Verify ZIP file exists
		$upload_dir = wp_upload_dir();
		$zip_path = trailingslashit( $upload_dir['basedir'] ) . 'ai_migration_artifacts/' . $zip_filename;
		$this->assertFileExists( $zip_path, 'ZIP file should exist' );

		// Open and verify ZIP structure
		$zip = new ZipArchive();
		$opened = $zip->open( $zip_path );
		$this->assertTrue( $opened, 'ZIP file should be openable' );

		// Verify required files exist in ZIP
		$required_files = array(
			'site_blueprint.json',
			'site_settings.json',
			'site_environment.json',
			'schema_mysql.sql',
		);

		foreach ( $required_files as $file ) {
			$this->assertNotFalse(
				$zip->locateName( $file ),
				"ZIP should contain {$file}"
			);
		}

		// Verify directory structure
		$required_dirs = array(
			'content/',
			'snapshots/',
			'media/',
			'theme/',
			'plugins/',
		);

		foreach ( $required_dirs as $dir ) {
			$found = false;
			for ( $i = 0; $i < $zip->numFiles; $i++ ) {
				$stat = $zip->statIndex( $i );
				if ( strpos( $stat['name'], $dir ) === 0 ) {
					$found = true;
					break;
				}
			}
			$this->assertTrue( $found, "ZIP should contain {$dir} directory" );
		}

		$zip->close();
	}

	/**
	 * Test JSON file validation against schemas.
	 *
	 * @group integration
	 */
	public function test_json_files_validation() {
		// Run scan
		$result = $this->scanner->run_scan();
		$this->assertTrue( $result['success'], 'Scan must succeed' );

		// Get export directory
		$upload_dir = wp_upload_dir();
		$export_dir = trailingslashit( $upload_dir['basedir'] ) . 'ai_migration_artifacts';

		// Test site_blueprint.json
		$blueprint_file = $export_dir . '/site_blueprint.json';
		if ( file_exists( $blueprint_file ) ) {
			$blueprint = json_decode( file_get_contents( $blueprint_file ), true );
			$this->assertNotNull( $blueprint, 'site_blueprint.json should be valid JSON' );
			$this->assertArrayHasKey( 'schema_version', $blueprint, 'Blueprint should have schema_version' );
			$this->assertEquals( 1, $blueprint['schema_version'], 'Schema version should be 1' );
			$this->assertArrayHasKey( 'site', $blueprint, 'Blueprint should have site data' );
			$this->assertArrayHasKey( 'theme', $blueprint, 'Blueprint should have theme data' );
			$this->assertArrayHasKey( 'plugins', $blueprint, 'Blueprint should have plugins array' );
		}

		// Test site_settings.json
		$settings_file = $export_dir . '/site_settings.json';
		if ( file_exists( $settings_file ) ) {
			$settings = json_decode( file_get_contents( $settings_file ), true );
			$this->assertNotNull( $settings, 'site_settings.json should be valid JSON' );
			$this->assertArrayHasKey( 'site_title', $settings, 'Settings should have site_title' );
		}

		// Test taxonomies.json
		$taxonomies_file = $export_dir . '/taxonomies.json';
		if ( file_exists( $taxonomies_file ) ) {
			$taxonomies = json_decode( file_get_contents( $taxonomies_file ), true );
			$this->assertNotNull( $taxonomies, 'taxonomies.json should be valid JSON' );
			$this->assertArrayHasKey( 'schema_version', $taxonomies, 'Taxonomies should have schema_version' );
			$this->assertArrayHasKey( 'taxonomies', $taxonomies, 'Should have taxonomies array' );
		}

		// Test media_map.json
		$media_map_file = $export_dir . '/media/media_map.json';
		if ( file_exists( $media_map_file ) ) {
			$media_map = json_decode( file_get_contents( $media_map_file ), true );
			$this->assertNotNull( $media_map, 'media_map.json should be valid JSON' );
			$this->assertIsArray( $media_map, 'Media map should be an array' );
		}
	}

	/**
	 * Test scan with GeoDirectory plugin active.
	 *
	 * @group integration
	 * @group geodirectory
	 */
	public function test_scan_with_geodirectory_plugin() {
		// Mock GeoDirectory plugin as active
		global $mock_active_plugins;
		$mock_active_plugins = array(
			'geodirectory/geodirectory.php',
		);

		// Mock GeoDirectory custom post types
		global $mock_post_types;
		$mock_post_types = array(
			'post' => (object) array( 'name' => 'post', 'label' => 'Posts' ),
			'page' => (object) array( 'name' => 'page', 'label' => 'Pages' ),
			'gd_place' => (object) array( 'name' => 'gd_place', 'label' => 'Places' ),
			'gd_event' => (object) array( 'name' => 'gd_event', 'label' => 'Events' ),
			'gd_custom_listing' => (object) array( 'name' => 'gd_custom_listing', 'label' => 'Custom Listings' ),
		);

		// Mock GeoDirectory posts
		global $mock_posts;
		$mock_posts = array(
			100 => (object) array(
				'ID' => 100,
				'post_type' => 'gd_place',
				'post_title' => 'Sample Cafe',
				'post_name' => 'sample-cafe',
				'post_status' => 'publish',
				'post_content' => '<!-- wp:paragraph --><p>A cozy cafe</p><!-- /wp:paragraph -->',
			),
			101 => (object) array(
				'ID' => 101,
				'post_type' => 'gd_event',
				'post_title' => 'Music Festival',
				'post_name' => 'music-festival',
				'post_status' => 'publish',
				'post_content' => '<!-- wp:paragraph --><p>Annual music event</p><!-- /wp:paragraph -->',
			),
		);

		// Run scan
		$result = $this->scanner->run_scan();
		$this->assertTrue( $result['success'], 'Scan with GeoDirectory should succeed' );

		// Verify GeoDirectory plugin detected
		$plugins_data = $result['results']['plugins'];
		$geodir_found = false;
		foreach ( $plugins_data as $plugin ) {
			if ( strpos( $plugin['file'], 'geodirectory' ) !== false ) {
				$geodir_found = true;
				$this->assertTrue( $plugin['active'], 'GeoDirectory should be marked as active' );
				break;
			}
		}
		$this->assertTrue( $geodir_found, 'GeoDirectory plugin should be detected' );

		// Verify GeoDirectory CPTs in content
		if ( isset( $result['results']['content'] ) ) {
			$content_data = $result['results']['content'];
			$this->assertArrayHasKey( 'gd_place', $content_data, 'Should have gd_place content' );
			$this->assertArrayHasKey( 'gd_event', $content_data, 'Should have gd_event content' );
		}

		// Verify GeoDirectory-specific metadata
		$upload_dir = wp_upload_dir();
		$export_dir = trailingslashit( $upload_dir['basedir'] ) . 'ai_migration_artifacts';
		$place_file = $export_dir . '/content/gd_place/sample-cafe.json';
		
		if ( file_exists( $place_file ) ) {
			$place_data = json_decode( file_get_contents( $place_file ), true );
			$this->assertNotNull( $place_data, 'Place JSON should be valid' );
			$this->assertEquals( 'gd_place', $place_data['type'], 'Type should be gd_place' );
			$this->assertArrayHasKey( 'postmeta', $place_data, 'Should have postmeta' );
		}
	}

	/**
	 * Test scan with multilingual plugin active.
	 *
	 * @group integration
	 * @group multilingual
	 */
	public function test_scan_with_multilingual_plugin() {
		// Mock WPML plugin as active
		global $mock_active_plugins;
		$mock_active_plugins = array(
			'sitepress-multilingual-cms/sitepress.php',
		);

		// Mock WPML options
		global $mock_options;
		$mock_options['icl_sitepress_settings'] = array(
			'default_language' => 'en',
			'active_languages' => array( 'en', 'es', 'fr' ),
		);

		// Run scan
		$result = $this->scanner->run_scan();
		$this->assertTrue( $result['success'], 'Scan with multilingual plugin should succeed' );

		// Verify translations data
		if ( isset( $result['results']['translations'] ) ) {
			$translations = $result['results']['translations'];
			$this->assertArrayHasKey( 'plugin_detected', $translations, 'Should detect multilingual plugin' );
			$this->assertNotEmpty( $translations['plugin_detected'], 'Should identify the plugin' );
			$this->assertArrayHasKey( 'languages', $translations, 'Should have languages data' );
		}

		// Verify translations.json file
		$upload_dir = wp_upload_dir();
		$export_dir = trailingslashit( $upload_dir['basedir'] ) . 'ai_migration_artifacts';
		$translations_file = $export_dir . '/translations.json';
		
		if ( file_exists( $translations_file ) ) {
			$translations_data = json_decode( file_get_contents( $translations_file ), true );
			$this->assertNotNull( $translations_data, 'translations.json should be valid JSON' );
			$this->assertArrayHasKey( 'plugin_detected', $translations_data, 'Should have plugin info' );
		}
	}

	/**
	 * Test scan with ACF plugin active.
	 *
	 * @group integration
	 * @group acf
	 */
	public function test_scan_with_acf_plugin() {
		// Mock ACF plugin as active
		global $mock_active_plugins;
		$mock_active_plugins = array(
			'advanced-custom-fields/acf.php',
		);

		// Mock ACF field groups
		global $mock_posts;
		$mock_posts[200] = (object) array(
			'ID' => 200,
			'post_type' => 'acf-field-group',
			'post_title' => 'Product Fields',
			'post_name' => 'product-fields',
			'post_status' => 'publish',
			'post_content' => '',
		);

		// Run scan
		$result = $this->scanner->run_scan();
		$this->assertTrue( $result['success'], 'Scan with ACF should succeed' );

		// Verify ACF plugin detected
		$plugins_data = $result['results']['plugins'];
		$acf_found = false;
		foreach ( $plugins_data as $plugin ) {
			if ( strpos( $plugin['file'], 'advanced-custom-fields' ) !== false ) {
				$acf_found = true;
				$this->assertTrue( $plugin['active'], 'ACF should be marked as active' );
				break;
			}
		}
		$this->assertTrue( $acf_found, 'ACF plugin should be detected' );

		// Verify ACF data exported
		if ( isset( $result['results']['acf'] ) ) {
			$acf_data = $result['results']['acf'];
			$this->assertArrayHasKey( 'field_groups', $acf_data, 'Should have field_groups' );
		}

		// Verify acf_field_groups.json file
		$upload_dir = wp_upload_dir();
		$export_dir = trailingslashit( $upload_dir['basedir'] ) . 'ai_migration_artifacts';
		$acf_file = $export_dir . '/acf_field_groups.json';
		
		if ( file_exists( $acf_file ) ) {
			$acf_json = json_decode( file_get_contents( $acf_file ), true );
			$this->assertNotNull( $acf_json, 'acf_field_groups.json should be valid JSON' );
			$this->assertIsArray( $acf_json, 'ACF data should be an array' );
		}
	}

	/**
	 * Test scan with multiple plugins active simultaneously.
	 *
	 * @group integration
	 */
	public function test_scan_with_multiple_plugins() {
		// Mock multiple plugins active
		global $mock_active_plugins;
		$mock_active_plugins = array(
			'geodirectory/geodirectory.php',
			'advanced-custom-fields/acf.php',
			'sitepress-multilingual-cms/sitepress.php',
			'kadence-blocks/kadence-blocks.php',
		);

		// Mock various post types
		global $mock_post_types;
		$mock_post_types = array(
			'post' => (object) array( 'name' => 'post', 'label' => 'Posts' ),
			'page' => (object) array( 'name' => 'page', 'label' => 'Pages' ),
			'gd_place' => (object) array( 'name' => 'gd_place', 'label' => 'Places' ),
			'acf-field-group' => (object) array( 'name' => 'acf-field-group', 'label' => 'Field Groups' ),
		);

		// Run scan
		$result = $this->scanner->run_scan();
		$this->assertTrue( $result['success'], 'Scan with multiple plugins should succeed' );

		// Verify all plugins detected
		$plugins_data = $result['results']['plugins'];
		$this->assertGreaterThanOrEqual( 4, count( $plugins_data ), 'Should detect all plugins' );

		// Verify comprehensive data collection
		$this->assertArrayHasKey( 'site', $result['results'], 'Should have site data' );
		$this->assertArrayHasKey( 'theme', $result['results'], 'Should have theme data' );
		$this->assertArrayHasKey( 'plugins', $result['results'], 'Should have plugins data' );
		$this->assertArrayHasKey( 'content', $result['results'], 'Should have content data' );
	}

	/**
	 * Test error handling during scan.
	 *
	 * @group integration
	 */
	public function test_error_handling_during_scan() {
		// Mock a scenario that might cause warnings
		global $mock_theme_root;
		$mock_theme_root = '/nonexistent/path';

		// Run scan
		$result = $this->scanner->run_scan();

		// Scan should still complete even with some errors
		$this->assertTrue( $result['success'], 'Scan should complete despite non-critical errors' );

		// Check if warnings were logged
		if ( isset( $result['warnings'] ) && ! empty( $result['warnings'] ) ) {
			$this->assertIsArray( $result['warnings'], 'Warnings should be an array' );
			foreach ( $result['warnings'] as $warning ) {
				$this->assertArrayHasKey( 'scanner', $warning, 'Warning should have scanner field' );
				$this->assertArrayHasKey( 'message', $warning, 'Warning should have message field' );
				$this->assertArrayHasKey( 'severity', $warning, 'Warning should have severity field' );
			}
		}
	}

	/**
	 * Test progress tracking during scan.
	 *
	 * @group integration
	 */
	public function test_progress_tracking() {
		// Start scan in background (simulate)
		$progress_updates = array();

		// Hook into progress updates
		add_action( 'digital_lobster_before_scanner', function( $name ) use ( &$progress_updates ) {
			$progress = $this->scanner->get_progress();
			if ( $progress ) {
				$progress_updates[] = $progress;
			}
		});

		// Run scan
		$result = $this->scanner->run_scan();
		$this->assertTrue( $result['success'], 'Scan should succeed' );

		// Verify progress was tracked
		$final_progress = $this->scanner->get_progress();
		$this->assertNotFalse( $final_progress, 'Progress should be available' );
		$this->assertArrayHasKey( 'stage', $final_progress, 'Progress should have stage' );
		$this->assertArrayHasKey( 'percent', $final_progress, 'Progress should have percent' );
		$this->assertEquals( 100, $final_progress['percent'], 'Final progress should be 100%' );
		$this->assertTrue( $final_progress['completed'], 'Scan should be marked as completed' );
	}

	/**
	 * Test content sampling limits.
	 *
	 * @group integration
	 */
	public function test_content_sampling_limits() {
		// Mock many posts
		global $mock_posts;
		for ( $i = 1; $i <= 100; $i++ ) {
			$mock_posts[ $i ] = (object) array(
				'ID' => $i,
				'post_type' => 'post',
				'post_title' => "Post {$i}",
				'post_name' => "post-{$i}",
				'post_status' => 'publish',
				'post_content' => '<!-- wp:paragraph --><p>Content</p><!-- /wp:paragraph -->',
			);
		}

		// Set sampling limits
		global $mock_options;
		$mock_options['digital_lobster_settings'] = array(
			'max_posts' => 5,
			'max_pages' => 2,
		);

		// Run scan
		$result = $this->scanner->run_scan();
		$this->assertTrue( $result['success'], 'Scan should succeed' );

		// Verify content was limited
		if ( isset( $result['results']['content']['post'] ) ) {
			$exported_posts = $result['results']['content']['post'];
			$this->assertLessThanOrEqual( 5, count( $exported_posts ), 'Should respect max_posts limit' );
		}
	}

	/**
	 * Test ZIP file size and compression.
	 *
	 * @group integration
	 */
	public function test_zip_file_size_and_compression() {
		// Run scan
		$result = $this->scanner->run_scan();
		$this->assertTrue( $result['success'], 'Scan must succeed' );

		// Get ZIP file info
		$this->assertArrayHasKey( 'zip_size', $result['results'], 'Should have ZIP size' );
		$zip_size = $result['results']['zip_size'];

		// Verify ZIP size is reasonable (not empty, not too large)
		$this->assertGreaterThan( 0, $zip_size, 'ZIP should not be empty' );
		$this->assertLessThan( 100 * 1024 * 1024, $zip_size, 'ZIP should be under 100MB for test data' );

		// Verify compression ratio
		$upload_dir = wp_upload_dir();
		$export_dir = trailingslashit( $upload_dir['basedir'] ) . 'ai_migration_artifacts';
		$uncompressed_size = $this->getDirectorySize( $export_dir );

		if ( $uncompressed_size > 0 ) {
			$compression_ratio = $zip_size / $uncompressed_size;
			$this->assertLessThan( 1, $compression_ratio, 'ZIP should be compressed' );
		}
	}

	/**
	 * Set up mock WordPress environment.
	 */
	private function setup_mock_wordpress_environment() {
		// Mock global variables
		global $mock_posts, $mock_options, $mock_active_plugins, $mock_post_types;
		global $mock_taxonomies, $mock_terms, $mock_theme_root;

		$mock_posts = array();
		$mock_options = array(
			'blogname' => 'Test Site',
			'blogdescription' => 'Just another WordPress site',
			'siteurl' => 'https://example.com',
			'home' => 'https://example.com',
		);
		$mock_active_plugins = array();
		$mock_post_types = array(
			'post' => (object) array( 'name' => 'post', 'label' => 'Posts' ),
			'page' => (object) array( 'name' => 'page', 'label' => 'Pages' ),
		);
		$mock_taxonomies = array(
			'category' => (object) array( 'name' => 'category', 'label' => 'Categories' ),
			'post_tag' => (object) array( 'name' => 'post_tag', 'label' => 'Tags' ),
		);
		$mock_terms = array();
		$mock_theme_root = dirname( __DIR__ ) . '/tests/fixtures/themes';
	}

	/**
	 * Recursively remove directory.
	 *
	 * @param string $dir Directory path.
	 */
	private function recursiveRemoveDirectory( $dir ) {
		if ( ! is_dir( $dir ) ) {
			return;
		}

		$files = array_diff( scandir( $dir ), array( '.', '..' ) );
		foreach ( $files as $file ) {
			$path = $dir . '/' . $file;
			is_dir( $path ) ? $this->recursiveRemoveDirectory( $path ) : unlink( $path );
		}
		rmdir( $dir );
	}

	/**
	 * Get directory size recursively.
	 *
	 * @param string $dir Directory path.
	 * @return int Total size in bytes.
	 */
	private function getDirectorySize( $dir ) {
		$size = 0;
		if ( ! is_dir( $dir ) ) {
			return $size;
		}

		foreach ( new RecursiveIteratorIterator( new RecursiveDirectoryIterator( $dir ) ) as $file ) {
			if ( $file->isFile() ) {
				$size += $file->getSize();
			}
		}

		return $size;
	}
}
