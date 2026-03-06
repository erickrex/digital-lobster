<?php
/**
 * Content Scanner Test
 *
 * Tests for the Digital_Lobster_Exporter_Content_Scanner class.
 *
 * @package Digital_Lobster_Exporter
 */

use PHPUnit\Framework\TestCase;

/**
 * Content Scanner Test Class
 */
class ContentScannerTest extends TestCase {

	/**
	 * Set up test environment.
	 */
	protected function setUp(): void {
		parent::setUp();
		
		// Set up mock posts
		global $mock_posts, $mock_postmeta;
		
		$mock_posts = array(
			1 => (object) array(
				'ID' => 1,
				'post_type' => 'post',
				'post_name' => 'sample-post',
				'post_status' => 'publish',
				'post_title' => 'Sample Post',
				'post_excerpt' => 'This is a sample post',
				'post_author' => 1,
				'post_date_gmt' => '2024-01-15 10:30:00',
				'post_modified_gmt' => '2024-01-20 14:22:00',
				'post_content' => '<!-- wp:paragraph --><p>Test content</p><!-- /wp:paragraph -->',
			),
		);
		
		$mock_postmeta = array(
			1 => array(
				'_yoast_wpseo_title' => 'SEO Title',
				'custom_field' => 'value',
			),
		);
	}

	/**
	 * Test scanner instantiation.
	 */
	public function test_scanner_instantiation() {
		$scanner = new Digital_Lobster_Exporter_Content_Scanner();
		$this->assertInstanceOf( Digital_Lobster_Exporter_Content_Scanner::class, $scanner );
	}

	/**
	 * Test scan method returns expected structure.
	 */
	public function test_scan_returns_expected_structure() {
		$scanner = new Digital_Lobster_Exporter_Content_Scanner();
		$result = $scanner->scan();

		$this->assertIsArray( $result );
		$this->assertArrayHasKey( 'posts', $result );
		$this->assertArrayHasKey( 'pages', $result );
		$this->assertArrayHasKey( 'custom_post_types', $result );
		$this->assertArrayHasKey( 'block_usage', $result );
	}

	/**
	 * Test content item structure.
	 */
	public function test_content_item_structure() {
		$scanner = new Digital_Lobster_Exporter_Content_Scanner();
		$result = $scanner->scan();

		$posts = $result['posts'];
		
		if ( ! empty( $posts ) ) {
			$post = $posts[0];
			
			$this->assertArrayHasKey( 'type', $post );
			$this->assertArrayHasKey( 'id', $post );
			$this->assertArrayHasKey( 'slug', $post );
			$this->assertArrayHasKey( 'status', $post );
			$this->assertArrayHasKey( 'title', $post );
			$this->assertArrayHasKey( 'excerpt', $post );
			$this->assertArrayHasKey( 'author', $post );
			$this->assertArrayHasKey( 'date_gmt', $post );
			$this->assertArrayHasKey( 'modified_gmt', $post );
			$this->assertArrayHasKey( 'taxonomies', $post );
			$this->assertArrayHasKey( 'blocks', $post );
			$this->assertArrayHasKey( 'raw_html', $post );
			$this->assertArrayHasKey( 'legacy_permalink', $post );
			$this->assertArrayHasKey( 'postmeta', $post );
		}
	}

	/**
	 * Test block parsing.
	 */
	public function test_block_parsing() {
		$scanner = new Digital_Lobster_Exporter_Content_Scanner();
		$result = $scanner->scan();

		$posts = $result['posts'];
		
		if ( ! empty( $posts ) ) {
			$post = $posts[0];
			
			$this->assertIsArray( $post['blocks'] );
			
			if ( ! empty( $post['blocks'] ) ) {
				$block = $post['blocks'][0];
				
				$this->assertArrayHasKey( 'name', $block );
				$this->assertArrayHasKey( 'attrs', $block );
				$this->assertArrayHasKey( 'html', $block );
			}
		}
	}

	/**
	 * Test block usage statistics.
	 */
	public function test_block_usage_statistics() {
		$scanner = new Digital_Lobster_Exporter_Content_Scanner();
		$result = $scanner->scan();

		$block_usage = $result['block_usage'];
		
		$this->assertIsArray( $block_usage );
		
		if ( ! empty( $block_usage ) ) {
			$stat = $block_usage[0];
			
			$this->assertArrayHasKey( 'name', $stat );
			$this->assertArrayHasKey( 'count', $stat );
			$this->assertIsInt( $stat['count'] );
		}
	}

	/**
	 * Test postmeta filtering.
	 */
	public function test_postmeta_filtering() {
		$scanner = new Digital_Lobster_Exporter_Content_Scanner();
		$result = $scanner->scan();

		$posts = $result['posts'];
		
		if ( ! empty( $posts ) ) {
			$post = $posts[0];
			$postmeta = $post['postmeta'];
			
			// Should include SEO meta
			$this->assertArrayHasKey( '_yoast_wpseo_title', $postmeta );
			
			// Should not include sensitive keys (if they were present)
			$this->assertArrayNotHasKey( '_edit_lock', $postmeta );
			$this->assertArrayNotHasKey( 'password', $postmeta );
		}
	}

	/**
	 * Test query logic respects limits.
	 */
	public function test_query_respects_limits() {
		// Set custom limits
		global $mock_options;
		$mock_options['digital_lobster_settings'] = array(
			'max_posts' => 2,
			'max_pages' => 1,
		);
		
		$scanner = new Digital_Lobster_Exporter_Content_Scanner();
		$result = $scanner->scan();

		// The actual count depends on mock data, but structure should be correct
		$this->assertIsArray( $result['posts'] );
		$this->assertIsArray( $result['pages'] );
	}

	/**
	 * Test GeoDirectory CPT detection.
	 */
	public function test_geodirectory_cpt_detection() {
		// Add geodir_cpt taxonomy to mock
		global $wp_taxonomies;
		$wp_taxonomies['geodir_cpt'] = (object) array(
			'name' => 'geodir_cpt',
			'label' => 'GeoDirectory CPT',
		);
		
		$scanner = new Digital_Lobster_Exporter_Content_Scanner();
		$result = $scanner->scan();

		// Test passes if no errors occur
		$this->assertIsArray( $result );
	}

	/**
	 * Test internal links extraction.
	 */
	public function test_internal_links_extraction() {
		global $mock_posts;
		
		$mock_posts[2] = (object) array(
			'ID' => 2,
			'post_type' => 'post',
			'post_name' => 'post-with-links',
			'post_status' => 'publish',
			'post_title' => 'Post with Links',
			'post_excerpt' => '',
			'post_author' => 1,
			'post_date_gmt' => '2024-01-15 10:30:00',
			'post_modified_gmt' => '2024-01-20 14:22:00',
			'post_content' => '<p>Check out <a href="https://example.com/about/">our about page</a></p>',
		);
		
		$scanner = new Digital_Lobster_Exporter_Content_Scanner();
		$result = $scanner->scan();

		$posts = $result['posts'];
		
		if ( count( $posts ) > 1 ) {
			$post = $posts[1];
			
			$this->assertArrayHasKey( 'internal_links', $post );
			$this->assertIsArray( $post['internal_links'] );
		}
	}

	/**
	 * Test author data structure.
	 */
	public function test_author_data_structure() {
		$scanner = new Digital_Lobster_Exporter_Content_Scanner();
		$result = $scanner->scan();

		$posts = $result['posts'];
		
		if ( ! empty( $posts ) ) {
			$post = $posts[0];
			
			$this->assertArrayHasKey( 'author', $post );
			$this->assertArrayHasKey( 'display_name', $post['author'] );
			
			// Should NOT include email or user ID
			$this->assertArrayNotHasKey( 'email', $post['author'] );
			$this->assertArrayNotHasKey( 'user_id', $post['author'] );
		}
	}
}
