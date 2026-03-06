<?php
/**
 * Shortcode Scanner Class
 *
 * Scans all exported content for shortcode usage and creates an inventory
 * of all registered shortcodes with usage statistics and examples.
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Shortcode Scanner Class
 */
class Digital_Lobster_Exporter_Shortcode_Scanner extends Digital_Lobster_Exporter_Scanner_Base {

	/**
	 * Shortcode usage data.
	 *
	 * @var array
	 */
	private $shortcode_usage = array();

	/**
	 * Constructor.
	 *
	 * @param array $deps Optional. Associative array of dependencies.
	 */
	public function __construct( array $deps = array() ) {
		parent::__construct( $deps );
	}

	/**
	 * Run the shortcode scan.
	 *
	 * @return array Scan results.
	 */
	public function scan() {
		$results = array(
			'success' => true,
			'message' => 'Shortcode inventory scan completed',
			'data'    => array(),
		);

		try {
			// Get all registered shortcodes.
			$registered_shortcodes = $this->get_registered_shortcodes();

			// Scan content for shortcode usage.
			$this->scan_content_for_shortcodes();

			// Build the inventory.
			$inventory = $this->build_inventory( $registered_shortcodes );

			$results['data'] = array(
				'total_registered' => count( $registered_shortcodes ),
				'total_used'       => count( $this->shortcode_usage ),
			);

		} catch ( Exception $e ) {
			$results['success'] = false;
			$results['message'] = 'Shortcode scan failed: ' . $e->getMessage();
		}

		return $results;
	}

	/**
	 * Get all registered shortcodes with their callback information.
	 *
	 * @return array Registered shortcodes.
	 */
	private function get_registered_shortcodes() {
		global $shortcode_tags;

		$registered = array();

		if ( empty( $shortcode_tags ) || ! is_array( $shortcode_tags ) ) {
			return $registered;
		}

		foreach ( $shortcode_tags as $tag => $callback ) {
			$registered[ $tag ] = array(
				'tag'      => $tag,
				'callback' => $this->get_callback_info( $callback ),
				'source'   => $this->identify_shortcode_source( $tag, $callback ),
			);
		}

		return $registered;
	}

	/**
	 * Get callback information.
	 *
	 * @param mixed $callback Callback function.
	 * @return string Callback description.
	 */
	private function get_callback_info( $callback ) {
		$resolved = Digital_Lobster_Exporter_Callback_Resolver::resolve( $callback );
		return isset( $resolved['name'] ) ? $resolved['name'] : 'Unknown';
	}

	/**
	 * Identify the source plugin or theme for a shortcode.
	 *
	 * @param string $tag      Shortcode tag.
	 * @param mixed  $callback Callback function.
	 * @return array Source information.
	 */
	private function identify_shortcode_source( $tag, $callback ) {
		$source = array(
			'type' => 'unknown',
			'name' => 'Unknown',
		);

		// Check if it's a WordPress core shortcode.
		$core_shortcodes = array(
			'caption',
			'gallery',
			'playlist',
			'audio',
			'video',
			'embed',
		);

		if ( in_array( $tag, $core_shortcodes, true ) ) {
			$source['type'] = 'core';
			$source['name'] = 'WordPress Core';
			return $source;
		}

		// Use Callback_Resolver to get file info, then Source_Identifier.
		$resolved = Digital_Lobster_Exporter_Callback_Resolver::resolve( $callback );

		if ( isset( $resolved['file'] ) && ! empty( $resolved['file'] ) ) {
			$source = Digital_Lobster_Exporter_Source_Identifier::identify( $resolved['file'] );
		}

		return $source;
	}

	/**
	 * Scan all exported content for shortcode usage.
	 */
	private function scan_content_for_shortcodes() {
		$content_dir = $this->export_dir . '/content';

		if ( ! is_dir( $content_dir ) ) {
			return;
		}

		// Scan all content JSON files.
		$this->scan_directory_for_shortcodes( $content_dir );
	}

	/**
	 * Recursively scan directory for content files.
	 *
	 * @param string $dir Directory path.
	 */
	private function scan_directory_for_shortcodes( $dir ) {
		$items = scandir( $dir );

		foreach ( $items as $item ) {
			if ( $item === '.' || $item === '..' ) {
				continue;
			}

			$path = $dir . '/' . $item;

			if ( is_dir( $path ) ) {
				$this->scan_directory_for_shortcodes( $path );
			} elseif ( is_file( $path ) && pathinfo( $path, PATHINFO_EXTENSION ) === 'json' ) {
				$this->scan_content_file( $path );
			}
		}
	}

	/**
	 * Scan a content JSON file for shortcodes.
	 *
	 * @param string $file_path File path.
	 */
	private function scan_content_file( $file_path ) {
		$content = file_get_contents( $file_path );
		if ( ! $content ) {
			return;
		}

		$data = json_decode( $content, true );
		if ( ! $data ) {
			return;
		}

		// Get the raw HTML content.
		$raw_html = isset( $data['raw_html'] ) ? $data['raw_html'] : '';

		// Also check title and excerpt.
		$title   = isset( $data['title'] ) ? $data['title'] : '';
		$excerpt = isset( $data['excerpt'] ) ? $data['excerpt'] : '';

		// Combine all text to search.
		$text_to_search = $raw_html . ' ' . $title . ' ' . $excerpt;

		// Find all shortcodes.
		$this->extract_shortcodes_from_text( $text_to_search, $data );
	}

	/**
	 * Extract shortcodes from text.
	 *
	 * @param string $text Text to search.
	 * @param array  $content_data Content data for context.
	 */
	private function extract_shortcodes_from_text( $text, $content_data ) {
		// Use WordPress shortcode regex pattern.
		$pattern = get_shortcode_regex();

		if ( preg_match_all( '/' . $pattern . '/s', $text, $matches, PREG_SET_ORDER ) ) {
			foreach ( $matches as $match ) {
				$tag   = $match[2];
				$attrs = isset( $match[3] ) ? $match[3] : '';
				$full  = $match[0];

				// Initialize usage tracking for this shortcode.
				if ( ! isset( $this->shortcode_usage[ $tag ] ) ) {
					$this->shortcode_usage[ $tag ] = array(
						'count'    => 0,
						'examples' => array(),
					);
				}

				$this->shortcode_usage[ $tag ]['count']++;

				// Store example (limit to 3 examples per shortcode).
				if ( count( $this->shortcode_usage[ $tag ]['examples'] ) < 3 ) {
					$example = array(
						'shortcode'   => $full,
						'attributes'  => $this->parse_shortcode_attributes( $attrs ),
						'found_in'    => array(
							'type' => isset( $content_data['type'] ) ? $content_data['type'] : 'unknown',
							'slug' => isset( $content_data['slug'] ) ? $content_data['slug'] : 'unknown',
							'id'   => isset( $content_data['id'] ) ? $content_data['id'] : 0,
						),
					);

					$this->shortcode_usage[ $tag ]['examples'][] = $example;
				}
			}
		}
	}

	/**
	 * Parse shortcode attributes string.
	 *
	 * @param string $attrs Attributes string.
	 * @return array Parsed attributes.
	 */
	private function parse_shortcode_attributes( $attrs ) {
		$attrs = trim( $attrs );

		if ( empty( $attrs ) ) {
			return array();
		}

		// Use WordPress shortcode_parse_atts function.
		return shortcode_parse_atts( $attrs );
	}

	/**
	 * Build the complete inventory.
	 *
	 * @param array $registered_shortcodes Registered shortcodes.
	 * @return array Complete inventory.
	 */
	private function build_inventory( $registered_shortcodes ) {
		$inventory = array(
			'schema_version'        => 1,
			'total_registered'      => count( $registered_shortcodes ),
			'total_used_in_content' => count( $this->shortcode_usage ),
			'shortcodes'            => array(),
		);

		foreach ( $registered_shortcodes as $tag => $info ) {
			$usage_data = isset( $this->shortcode_usage[ $tag ] ) ? $this->shortcode_usage[ $tag ] : null;

			$shortcode_entry = array(
				'tag'              => $tag,
				'callback'         => $info['callback'],
				'source'           => $info['source'],
				'used_in_content'  => $usage_data !== null,
				'usage_count'      => $usage_data ? $usage_data['count'] : 0,
				'sample_usage'     => $usage_data ? $usage_data['examples'] : array(),
			);

			$inventory['shortcodes'][] = $shortcode_entry;
		}

		// Sort by usage count (most used first).
		usort( $inventory['shortcodes'], function( $a, $b ) {
			return $b['usage_count'] - $a['usage_count'];
		});

		return $inventory;
	}

}
