<?php
/**
 * Site Scanner Test
 *
 * Tests for the Digital_Lobster_Exporter_Site_Scanner class.
 *
 * @package Digital_Lobster_Exporter
 */

use PHPUnit\Framework\TestCase;

/**
 * Site Scanner Test Class
 */
class SiteScannerTest extends TestCase {

	/**
	 * Test scanner instantiation.
	 */
	public function test_scanner_instantiation() {
		$scanner = new Digital_Lobster_Exporter_Site_Scanner();
		$this->assertInstanceOf( Digital_Lobster_Exporter_Site_Scanner::class, $scanner );
	}

	/**
	 * Test scan method returns expected structure.
	 */
	public function test_scan_returns_expected_structure() {
		$scanner = new Digital_Lobster_Exporter_Site_Scanner();
		$result = $scanner->scan();

		$this->assertIsArray( $result );
		$this->assertArrayHasKey( 'site', $result );
		$this->assertArrayHasKey( 'post_types', $result );
		$this->assertArrayHasKey( 'taxonomies', $result );
		$this->assertArrayHasKey( 'content_counts', $result );
	}

	/**
	 * Test site info collection.
	 */
	public function test_site_info_collection() {
		$scanner = new Digital_Lobster_Exporter_Site_Scanner();
		$result = $scanner->scan();

		$this->assertArrayHasKey( 'url', $result['site'] );
		$this->assertArrayHasKey( 'wp_version', $result['site'] );
		$this->assertArrayHasKey( 'is_multisite', $result['site'] );
		$this->assertArrayHasKey( 'permalink_structure', $result['site'] );

		$this->assertEquals( 'https://example.com', $result['site']['url'] );
		$this->assertFalse( $result['site']['is_multisite'] );
	}

	/**
	 * Test post types collection.
	 */
	public function test_post_types_collection() {
		$scanner = new Digital_Lobster_Exporter_Site_Scanner();
		$result = $scanner->scan();

		$this->assertIsArray( $result['post_types'] );
		$this->assertArrayHasKey( 'post', $result['post_types'] );
		$this->assertArrayHasKey( 'page', $result['post_types'] );

		// Check post type structure
		$post_type = $result['post_types']['post'];
		$this->assertArrayHasKey( 'label', $post_type );
		$this->assertArrayHasKey( 'public', $post_type );
		$this->assertArrayHasKey( 'hierarchical', $post_type );
		$this->assertArrayHasKey( 'taxonomies', $post_type );
	}

	/**
	 * Test taxonomies collection.
	 */
	public function test_taxonomies_collection() {
		$scanner = new Digital_Lobster_Exporter_Site_Scanner();
		$result = $scanner->scan();

		$this->assertIsArray( $result['taxonomies'] );
		$this->assertArrayHasKey( 'category', $result['taxonomies'] );
		$this->assertArrayHasKey( 'post_tag', $result['taxonomies'] );

		// Check taxonomy structure
		$taxonomy = $result['taxonomies']['category'];
		$this->assertArrayHasKey( 'label', $taxonomy );
		$this->assertArrayHasKey( 'hierarchical', $taxonomy );
		$this->assertTrue( $taxonomy['hierarchical'] );
	}

	/**
	 * Test content counts collection.
	 */
	public function test_content_counts_collection() {
		$scanner = new Digital_Lobster_Exporter_Site_Scanner();
		$result = $scanner->scan();

		$this->assertIsArray( $result['content_counts'] );
		$this->assertArrayHasKey( 'post', $result['content_counts'] );
		$this->assertIsInt( $result['content_counts']['post'] );
		$this->assertEquals( 12, $result['content_counts']['post'] ); // 10 published + 2 private
	}

	/**
	 * Test built-in post types are excluded.
	 */
	public function test_builtin_post_types_excluded() {
		$scanner = new Digital_Lobster_Exporter_Site_Scanner();
		$result = $scanner->scan();

		$excluded_types = array( 'revision', 'nav_menu_item', 'custom_css', 'wp_block' );
		
		foreach ( $excluded_types as $type ) {
			$this->assertArrayNotHasKey( $type, $result['post_types'] );
		}
	}

	/**
	 * Test built-in taxonomies are excluded.
	 */
	public function test_builtin_taxonomies_excluded() {
		$scanner = new Digital_Lobster_Exporter_Site_Scanner();
		$result = $scanner->scan();

		$excluded_taxonomies = array( 'nav_menu', 'link_category', 'post_format' );
		
		foreach ( $excluded_taxonomies as $taxonomy ) {
			$this->assertArrayNotHasKey( $taxonomy, $result['taxonomies'] );
		}
	}
}
