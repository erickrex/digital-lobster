<?php
/**
 * Block Patterns Scanner
 *
 * Exports block patterns and reusable blocks.
 *
 * @package Digital_Lobster_Exporter
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Class Digital_Lobster_Exporter_Block_Patterns_Scanner
 *
 * Collects WordPress block patterns including:
 * - All registered block patterns
 * - Pattern metadata (name, title, description, categories)
 * - Reusable blocks (wp_block post type)
 * - Usage tracking for reusable blocks
 */
class Digital_Lobster_Exporter_Block_Patterns_Scanner extends Digital_Lobster_Exporter_Scanner_Base {

	/**
	 * Constructor.
	 *
	 * @param array $deps Optional. Associative array of dependencies.
	 */
	public function __construct( array $deps = array() ) {
		parent::__construct( $deps );
	}

	/**
	 * Scan and collect block pattern data
	 *
	 * @return array Block pattern data
	 */
	public function scan() {
		$data = array(
			'schema_version'   => 1,
			'block_patterns'   => $this->get_block_patterns(),
			'reusable_blocks'  => $this->get_reusable_blocks(),
		);

		return $data;
	}

	/**
	 * Get all registered block patterns
	 *
	 * @return array Block patterns
	 */
	private function get_block_patterns() {
		$patterns = array();

		// Check if WP_Block_Patterns_Registry exists (WP 5.5+)
		if ( ! class_exists( 'WP_Block_Patterns_Registry' ) ) {
			return $patterns;
		}

		$registry = WP_Block_Patterns_Registry::get_instance();
		$all_patterns = $registry->get_all_registered();

		foreach ( $all_patterns as $pattern ) {
			$pattern_data = array(
				'name'        => $pattern['name'] ?? '',
				'title'       => $pattern['title'] ?? '',
				'description' => $pattern['description'] ?? '',
				'content'     => $pattern['content'] ?? '',
				'categories'  => $pattern['categories'] ?? array(),
				'keywords'    => $pattern['keywords'] ?? array(),
				'viewportWidth' => $pattern['viewportWidth'] ?? null,
				'blockTypes'  => $pattern['blockTypes'] ?? array(),
				'source'      => $this->determine_pattern_source( $pattern['name'] ),
			);

			// Add inserter flag if available
			if ( isset( $pattern['inserter'] ) ) {
				$pattern_data['inserter'] = $pattern['inserter'];
			}

			$patterns[] = $pattern_data;
		}

		return $patterns;
	}

	/**
	 * Determine the source of a block pattern
	 *
	 * @param string $pattern_name Pattern name
	 * @return string Source (core, theme, plugin)
	 */
	private function determine_pattern_source( $pattern_name ) {
		// Core patterns typically start with 'core/'
		if ( strpos( $pattern_name, 'core/' ) === 0 ) {
			return 'core';
		}

		// Theme patterns often contain the theme slug
		$theme = wp_get_theme();
		$theme_slug = $theme->get_stylesheet();
		
		if ( strpos( $pattern_name, $theme_slug ) !== false ) {
			return 'theme';
		}

		// Otherwise assume it's from a plugin
		return 'plugin';
	}

	/**
	 * Get all reusable blocks
	 *
	 * @return array Reusable blocks
	 */
	private function get_reusable_blocks() {
		$reusable_blocks = array();

		// Query wp_block post type
		$blocks = get_posts(
			array(
				'post_type'      => 'wp_block',
				'posts_per_page' => -1,
				'post_status'    => array( 'publish', 'draft' ),
				'orderby'        => 'title',
				'order'          => 'ASC',
			)
		);

		foreach ( $blocks as $block ) {
			$block_data = array(
				'id'           => $block->ID,
				'title'        => $block->post_title,
				'slug'         => $block->post_name,
				'content'      => $block->post_content,
				'status'       => $block->post_status,
				'date_created' => $block->post_date_gmt,
				'date_modified' => $block->post_modified_gmt,
				'usage'        => $this->get_reusable_block_usage( $block->ID ),
			);

			// Parse blocks to get structure
			if ( function_exists( 'parse_blocks' ) ) {
				$parsed_blocks = parse_blocks( $block->post_content );
				$block_data['parsed_blocks'] = $this->sanitize_parsed_blocks( $parsed_blocks );
			}

			$reusable_blocks[] = $block_data;
		}

		return $reusable_blocks;
	}

	/**
	 * Get usage information for a reusable block
	 *
	 * @param int $block_id Reusable block ID
	 * @return array Usage information
	 */
	private function get_reusable_block_usage( $block_id ) {
		global $wpdb;

		$usage = array(
			'count' => 0,
			'posts' => array(),
		);

		// Search for references to this reusable block in post content
		// Reusable blocks are referenced as: <!-- wp:block {"ref":123} /-->
		$search_pattern = '%wp:block {"ref":' . $block_id . '}%';

		$results = $wpdb->get_results(
			$wpdb->prepare(
				"SELECT ID, post_title, post_type, post_name 
				FROM {$wpdb->posts} 
				WHERE post_content LIKE %s 
				AND post_status = 'publish' 
				AND post_type NOT IN ('revision', 'nav_menu_item', 'wp_block')
				LIMIT 100",
				$search_pattern
			)
		);

		if ( $results ) {
			$usage['count'] = count( $results );
			
			foreach ( $results as $post ) {
				$usage['posts'][] = array(
					'id'    => $post->ID,
					'title' => $post->post_title,
					'type'  => $post->post_type,
					'slug'  => $post->post_name,
				);
			}
		}

		return $usage;
	}

	/**
	 * Sanitize parsed blocks for export
	 *
	 * @param array $blocks Parsed blocks
	 * @return array Sanitized blocks
	 */
	private function sanitize_parsed_blocks( $blocks ) {
		$sanitized = array();

		foreach ( $blocks as $block ) {
			// Skip empty blocks
			if ( empty( $block['blockName'] ) ) {
				continue;
			}

			$sanitized_block = array(
				'name'  => $block['blockName'],
				'attrs' => $block['attrs'] ?? array(),
			);

			// Recursively process inner blocks
			if ( ! empty( $block['innerBlocks'] ) ) {
				$sanitized_block['innerBlocks'] = $this->sanitize_parsed_blocks( $block['innerBlocks'] );
			}

			$sanitized[] = $sanitized_block;
		}

		return $sanitized;
	}
}
