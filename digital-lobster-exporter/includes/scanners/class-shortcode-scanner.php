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
class Digital_Lobster_Exporter_Shortcode_Scanner {

	/**
	 * Export directory path.
	 *
	 * @var string
	 */
	private $export_dir = '';

	/**
	 * Shortcode usage data.
	 *
	 * @var array
	 */
	private $shortcode_usage = array();

	/**
	 * Constructor.
	 *
	 * @param string $export_dir Export directory path.
	 */
	public function __construct( $export_dir = '' ) {
		$this->export_dir = $export_dir;
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

			// Export to JSON.
			$this->export_inventory( $inventory );

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
		if ( is_string( $callback ) ) {
			return $callback;
		} elseif ( is_array( $callback ) && count( $callback ) === 2 ) {
			$class  = is_object( $callback[0] ) ? get_class( $callback[0] ) : $callback[0];
			$method = $callback[1];
			return $class . '::' . $method;
		} elseif ( is_object( $callback ) && ( $callback instanceof Closure ) ) {
			return 'Closure';
		} elseif ( is_object( $callback ) ) {
			return get_class( $callback ) . '::__invoke';
		}

		return 'Unknown';
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

		// Try to identify from callback.
		$callback_info = $this->get_callback_info( $callback );

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

		// Try to identify from reflection.
		try {
			if ( is_array( $callback ) && count( $callback ) === 2 ) {
				$reflection = is_object( $callback[0] )
					? new ReflectionClass( $callback[0] )
					: new ReflectionClass( $callback[0] );

				$filename = $reflection->getFileName();

				if ( $filename ) {
					$source = $this->identify_source_from_file( $filename );
				}
			} elseif ( is_string( $callback ) && function_exists( $callback ) ) {
				$reflection = new ReflectionFunction( $callback );
				$filename   = $reflection->getFileName();

				if ( $filename ) {
					$source = $this->identify_source_from_file( $filename );
				}
			}
		} catch ( Exception $e ) {
			// Reflection failed, keep unknown.
		}

		return $source;
	}

	/**
	 * Identify source from file path.
	 *
	 * @param string $filename File path.
	 * @return array Source information.
	 */
	private function identify_source_from_file( $filename ) {
		$source = array(
			'type' => 'unknown',
			'name' => 'Unknown',
		);

		// Check if it's from a plugin.
		if ( strpos( $filename, WP_PLUGIN_DIR ) !== false ) {
			$relative = str_replace( WP_PLUGIN_DIR . '/', '', $filename );
			$parts    = explode( '/', $relative );

			if ( ! empty( $parts[0] ) ) {
				$plugin_slug = $parts[0];
				$plugin_data = $this->get_plugin_data( $plugin_slug );

				$source['type'] = 'plugin';
				$source['name'] = $plugin_data['name'];
				$source['slug'] = $plugin_slug;
			}
		} elseif ( strpos( $filename, get_template_directory() ) !== false ) {
			// From active theme.
			$theme          = wp_get_theme();
			$source['type'] = 'theme';
			$source['name'] = $theme->get( 'Name' );
			$source['slug'] = $theme->get_stylesheet();
		} elseif ( strpos( $filename, get_stylesheet_directory() ) !== false ) {
			// From child theme.
			$theme          = wp_get_theme();
			$source['type'] = 'theme';
			$source['name'] = $theme->get( 'Name' );
			$source['slug'] = $theme->get_stylesheet();
		}

		return $source;
	}

	/**
	 * Get plugin data from slug.
	 *
	 * @param string $plugin_slug Plugin slug.
	 * @return array Plugin data.
	 */
	private function get_plugin_data( $plugin_slug ) {
		if ( ! function_exists( 'get_plugins' ) ) {
			require_once ABSPATH . 'wp-admin/includes/plugin.php';
		}

		$all_plugins = get_plugins();

		foreach ( $all_plugins as $plugin_file => $plugin_data ) {
			if ( strpos( $plugin_file, $plugin_slug . '/' ) === 0 ) {
				return array(
					'name' => $plugin_data['Name'],
					'file' => $plugin_file,
				);
			}
		}

		return array(
			'name' => ucwords( str_replace( array( '-', '_' ), ' ', $plugin_slug ) ),
			'file' => '',
		);
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

	/**
	 * Export inventory to JSON file.
	 *
	 * @param array $inventory Inventory data.
	 */
	private function export_inventory( $inventory ) {
		$file_path = $this->export_dir . '/shortcodes_inventory.json';

		$json = wp_json_encode( $inventory, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES );

		if ( $json === false ) {
			throw new Exception( 'Failed to encode shortcodes inventory to JSON' );
		}

		$result = file_put_contents( $file_path, $json );

		if ( $result === false ) {
			throw new Exception( 'Failed to write shortcodes_inventory.json' );
		}
	}
}
