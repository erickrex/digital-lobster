<?php
/**
 * Theme Scanner Test
 *
 * Tests for the Digital_Lobster_Exporter_Theme_Scanner class.
 *
 * @package Digital_Lobster_Exporter
 */

use PHPUnit\Framework\TestCase;

/**
 * Theme Scanner Test Class
 */
class ThemeScannerTest extends TestCase {

	/**
	 * Test scanner instantiation.
	 */
	public function test_scanner_instantiation() {
		$scanner = new Digital_Lobster_Exporter_Theme_Scanner();
		$this->assertInstanceOf( Digital_Lobster_Exporter_Theme_Scanner::class, $scanner );
	}

	/**
	 * Test scan method returns expected structure.
	 */
	public function test_scan_returns_expected_structure() {
		$scanner = new Digital_Lobster_Exporter_Theme_Scanner();
		$result = $scanner->scan();

		$this->assertIsArray( $result );
		$this->assertArrayHasKey( 'theme_info', $result );
		$this->assertArrayHasKey( 'exported_files', $result );
		$this->assertArrayHasKey( 'template_hierarchy', $result );
	}

	/**
	 * Test theme info collection.
	 */
	public function test_theme_info_collection() {
		$scanner = new Digital_Lobster_Exporter_Theme_Scanner();
		$result = $scanner->scan();

		$theme_info = $result['theme_info'];
		
		$this->assertArrayHasKey( 'name', $theme_info );
		$this->assertArrayHasKey( 'version', $theme_info );
		$this->assertArrayHasKey( 'is_child_theme', $theme_info );
		$this->assertArrayHasKey( 'block_theme', $theme_info );

		$this->assertEquals( 'Twenty Twenty-Four', $theme_info['name'] );
		$this->assertFalse( $theme_info['is_child_theme'] );
	}

	/**
	 * Test exported files structure.
	 */
	public function test_exported_files_structure() {
		$scanner = new Digital_Lobster_Exporter_Theme_Scanner();
		$result = $scanner->scan();

		$exported_files = $result['exported_files'];
		
		$this->assertArrayHasKey( 'style.css', $exported_files );
		$this->assertArrayHasKey( 'theme.json', $exported_files );
		$this->assertArrayHasKey( 'functions.php', $exported_files );
		$this->assertArrayHasKey( 'templates', $exported_files );
	}

	/**
	 * Test file copying returns success status.
	 */
	public function test_file_copying_status() {
		$scanner = new Digital_Lobster_Exporter_Theme_Scanner();
		$result = $scanner->scan();

		$style_css = $result['exported_files']['style.css'];
		
		$this->assertArrayHasKey( 'success', $style_css );
		$this->assertIsBool( $style_css['success'] );
	}

	/**
	 * Test template hierarchy generation.
	 */
	public function test_template_hierarchy_generation() {
		$scanner = new Digital_Lobster_Exporter_Theme_Scanner();
		$result = $scanner->scan();

		$hierarchy = $result['template_hierarchy'];
		
		$this->assertIsArray( $hierarchy );
		$this->assertArrayHasKey( 'front_page', $hierarchy );
		$this->assertArrayHasKey( 'single_post', $hierarchy );
		$this->assertArrayHasKey( '404', $hierarchy );

		// Check structure of hierarchy item
		$front_page = $hierarchy['front_page'];
		$this->assertArrayHasKey( 'description', $front_page );
		$this->assertArrayHasKey( 'fallback_chain', $front_page );
	}

	/**
	 * Test child theme detection.
	 */
	public function test_child_theme_detection() {
		$scanner = new Digital_Lobster_Exporter_Theme_Scanner();
		$result = $scanner->scan();

		$theme_info = $result['theme_info'];
		
		$this->assertArrayHasKey( 'parent_theme', $theme_info );
		
		// For non-child theme, parent_theme should be null
		if ( ! $theme_info['is_child_theme'] ) {
			$this->assertNull( $theme_info['parent_theme'] );
		}
	}

	/**
	 * Test block theme detection.
	 */
	public function test_block_theme_detection() {
		$scanner = new Digital_Lobster_Exporter_Theme_Scanner();
		$result = $scanner->scan();

		$theme_info = $result['theme_info'];
		
		$this->assertArrayHasKey( 'block_theme', $theme_info );
		$this->assertIsBool( $theme_info['block_theme'] );
	}
}
