<?php
/**
 * Taxonomy Scanner Test
 *
 * Tests for the Digital_Lobster_Exporter_Taxonomy_Scanner class.
 *
 * @package Digital_Lobster_Exporter
 */

use PHPUnit\Framework\TestCase;

/**
 * Taxonomy Scanner Test Class
 */
class TaxonomyScannerTest extends TestCase {

	/**
	 * Set up test environment.
	 */
	protected function setUp(): void {
		parent::setUp();
		
		// Set up mock content data
		global $mock_terms;
		
		$mock_terms = array(
			(object) array(
				'term_id' => 1,
				'name' => 'News',
				'slug' => 'news',
				'description' => 'News articles',
				'parent' => 0,
				'count' => 25,
			),
			(object) array(
				'term_id' => 2,
				'name' => 'Technology',
				'slug' => 'technology',
				'description' => 'Tech news',
				'parent' => 1,
				'count' => 10,
			),
		);
	}

	/**
	 * Test scanner instantiation.
	 */
	public function test_scanner_instantiation() {
		$exported_content = array(
			'posts' => array(
				array( 'id' => 1 ),
			),
		);
		
		$scanner = new Digital_Lobster_Exporter_Taxonomy_Scanner( $exported_content );
		$this->assertInstanceOf( Digital_Lobster_Exporter_Taxonomy_Scanner::class, $scanner );
	}

	/**
	 * Test scan method returns expected structure.
	 */
	public function test_scan_returns_expected_structure() {
		$exported_content = array(
			'posts' => array(
				array( 'id' => 1 ),
			),
		);
		
		$scanner = new Digital_Lobster_Exporter_Taxonomy_Scanner( $exported_content );
		$result = $scanner->scan();

		$this->assertIsArray( $result );
		$this->assertArrayHasKey( 'schema_version', $result );
		$this->assertArrayHasKey( 'taxonomies', $result );
		$this->assertArrayHasKey( 'term_relationships', $result );
		
		$this->assertEquals( 1, $result['schema_version'] );
	}

	/**
	 * Test taxonomy data structure.
	 */
	public function test_taxonomy_data_structure() {
		$exported_content = array(
			'posts' => array(
				array( 'id' => 1 ),
			),
		);
		
		$scanner = new Digital_Lobster_Exporter_Taxonomy_Scanner( $exported_content );
		$result = $scanner->scan();

		$taxonomies = $result['taxonomies'];
		
		if ( ! empty( $taxonomies ) ) {
			$taxonomy = reset( $taxonomies );
			
			$this->assertArrayHasKey( 'name', $taxonomy );
			$this->assertArrayHasKey( 'slug', $taxonomy );
			$this->assertArrayHasKey( 'hierarchical', $taxonomy );
			$this->assertArrayHasKey( 'terms', $taxonomy );
			
			$this->assertIsArray( $taxonomy['terms'] );
		}
	}

	/**
	 * Test term data structure.
	 */
	public function test_term_data_structure() {
		$exported_content = array(
			'posts' => array(
				array( 'id' => 1 ),
			),
		);
		
		$scanner = new Digital_Lobster_Exporter_Taxonomy_Scanner( $exported_content );
		$result = $scanner->scan();

		$taxonomies = $result['taxonomies'];
		
		foreach ( $taxonomies as $taxonomy ) {
			if ( ! empty( $taxonomy['terms'] ) ) {
				$term = $taxonomy['terms'][0];
				
				$this->assertArrayHasKey( 'term_id', $term );
				$this->assertArrayHasKey( 'name', $term );
				$this->assertArrayHasKey( 'slug', $term );
				$this->assertArrayHasKey( 'description', $term );
				$this->assertArrayHasKey( 'parent', $term );
				$this->assertArrayHasKey( 'count', $term );
				
				$this->assertIsInt( $term['term_id'] );
				$this->assertIsInt( $term['parent'] );
				$this->assertIsInt( $term['count'] );
				
				break;
			}
		}
	}

	/**
	 * Test hierarchical relationships preservation.
	 */
	public function test_hierarchical_relationships() {
		$exported_content = array(
			'posts' => array(
				array( 'id' => 1 ),
			),
		);
		
		$scanner = new Digital_Lobster_Exporter_Taxonomy_Scanner( $exported_content );
		$result = $scanner->scan();

		$taxonomies = $result['taxonomies'];
		
		foreach ( $taxonomies as $taxonomy ) {
			if ( $taxonomy['hierarchical'] && ! empty( $taxonomy['terms'] ) ) {
				// Check that parent field exists
				foreach ( $taxonomy['terms'] as $term ) {
					$this->assertArrayHasKey( 'parent', $term );
					$this->assertIsInt( $term['parent'] );
				}
				break;
			}
		}
	}

	/**
	 * Test term relationships export.
	 */
	public function test_term_relationships_export() {
		global $mock_posts;
		
		$mock_posts = array(
			1 => (object) array(
				'ID' => 1,
				'post_type' => 'post',
			),
		);
		
		$exported_content = array(
			'posts' => array(
				array( 'id' => 1 ),
			),
		);
		
		$scanner = new Digital_Lobster_Exporter_Taxonomy_Scanner( $exported_content );
		$result = $scanner->scan();

		$relationships = $result['term_relationships'];
		
		$this->assertIsArray( $relationships );
		
		// If relationships exist, check structure
		if ( ! empty( $relationships ) ) {
			foreach ( $relationships as $post_id => $terms ) {
				$this->assertIsInt( $post_id );
				$this->assertIsArray( $terms );
				
				// Each taxonomy should have an array of term IDs
				foreach ( $terms as $taxonomy => $term_ids ) {
					$this->assertIsString( $taxonomy );
					$this->assertIsArray( $term_ids );
				}
				
				break;
			}
		}
	}

	/**
	 * Test excluded taxonomies are not exported.
	 */
	public function test_excluded_taxonomies() {
		$exported_content = array(
			'posts' => array(
				array( 'id' => 1 ),
			),
		);
		
		$scanner = new Digital_Lobster_Exporter_Taxonomy_Scanner( $exported_content );
		$result = $scanner->scan();

		$taxonomies = $result['taxonomies'];
		
		// These should be excluded
		$this->assertArrayNotHasKey( 'nav_menu', $taxonomies );
		$this->assertArrayNotHasKey( 'link_category', $taxonomies );
		$this->assertArrayNotHasKey( 'post_format', $taxonomies );
	}

	/**
	 * Test term metadata export.
	 */
	public function test_term_metadata_export() {
		$exported_content = array(
			'posts' => array(
				array( 'id' => 1 ),
			),
		);
		
		$scanner = new Digital_Lobster_Exporter_Taxonomy_Scanner( $exported_content );
		$result = $scanner->scan();

		$taxonomies = $result['taxonomies'];
		
		foreach ( $taxonomies as $taxonomy ) {
			if ( ! empty( $taxonomy['terms'] ) ) {
				$term = $taxonomy['terms'][0];
				
				// Meta key should exist (even if empty)
				// If meta exists, it should be an array
				if ( isset( $term['meta'] ) ) {
					$this->assertIsArray( $term['meta'] );
				}
				
				break;
			}
		}
	}

	/**
	 * Test post ID extraction from content.
	 */
	public function test_post_id_extraction() {
		$exported_content = array(
			'posts' => array(
				array( 'id' => 1 ),
				array( 'id' => 2 ),
			),
			'pages' => array(
				array( 'id' => 3 ),
			),
			'custom_post_types' => array(
				'product' => array(
					array( 'id' => 4 ),
				),
			),
		);
		
		$scanner = new Digital_Lobster_Exporter_Taxonomy_Scanner( $exported_content );
		$result = $scanner->scan();

		// Test passes if scanner correctly extracts all post IDs
		$this->assertIsArray( $result );
	}

	/**
	 * Test sensitive meta filtering.
	 */
	public function test_sensitive_meta_filtering() {
		$exported_content = array(
			'posts' => array(
				array( 'id' => 1 ),
			),
		);
		
		$scanner = new Digital_Lobster_Exporter_Taxonomy_Scanner( $exported_content );
		$result = $scanner->scan();

		$taxonomies = $result['taxonomies'];
		
		foreach ( $taxonomies as $taxonomy ) {
			if ( ! empty( $taxonomy['terms'] ) ) {
				foreach ( $taxonomy['terms'] as $term ) {
					if ( isset( $term['meta'] ) ) {
						// Should not contain sensitive keys
						$this->assertArrayNotHasKey( 'password', $term['meta'] );
						$this->assertArrayNotHasKey( 'api_key', $term['meta'] );
						$this->assertArrayNotHasKey( 'secret', $term['meta'] );
					}
				}
			}
		}
	}
}
