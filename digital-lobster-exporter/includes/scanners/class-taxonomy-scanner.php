<?php
/**
 * Taxonomy Scanner Class
 *
 * Exports taxonomy and term data for all taxonomies used by exported content.
 * Includes term metadata, hierarchical relationships, and term-to-post mappings.
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Taxonomy Scanner Class
 */
class Digital_Lobster_Exporter_Taxonomy_Scanner {

	/**
	 * Exported content data (from ContentScanner).
	 *
	 * @var array
	 */
	private $exported_content = array();

	/**
	 * Post IDs that were exported.
	 *
	 * @var array
	 */
	private $exported_post_ids = array();

	/**
	 * Constructor.
	 *
	 * @param array $exported_content Optional. Content data from ContentScanner.
	 */
	public function __construct( $exported_content = array() ) {
		$this->exported_content = $exported_content;
		$this->extract_exported_post_ids();
	}

	/**
	 * Extract post IDs from exported content.
	 */
	private function extract_exported_post_ids() {
		$this->exported_post_ids = array();

		// Extract from posts
		if ( isset( $this->exported_content['posts'] ) && is_array( $this->exported_content['posts'] ) ) {
			foreach ( $this->exported_content['posts'] as $post ) {
				if ( isset( $post['id'] ) ) {
					$this->exported_post_ids[] = $post['id'];
				}
			}
		}

		// Extract from pages
		if ( isset( $this->exported_content['pages'] ) && is_array( $this->exported_content['pages'] ) ) {
			foreach ( $this->exported_content['pages'] as $page ) {
				if ( isset( $page['id'] ) ) {
					$this->exported_post_ids[] = $page['id'];
				}
			}
		}

		// Extract from custom post types
		if ( isset( $this->exported_content['custom_post_types'] ) && is_array( $this->exported_content['custom_post_types'] ) ) {
			foreach ( $this->exported_content['custom_post_types'] as $post_type => $items ) {
				if ( is_array( $items ) ) {
					foreach ( $items as $item ) {
						if ( isset( $item['id'] ) ) {
							$this->exported_post_ids[] = $item['id'];
						}
					}
				}
			}
		}

		$this->exported_post_ids = array_unique( $this->exported_post_ids );
	}

	/**
	 * Scan and collect taxonomy data.
	 *
	 * @return array Taxonomy data.
	 */
	public function scan() {
		// Identify all taxonomies used by exported content
		$used_taxonomies = $this->identify_used_taxonomies();

		// Build taxonomy data structure
		$taxonomy_data = array(
			'schema_version' => 1,
			'taxonomies'     => array(),
			'term_relationships' => array(),
		);

		// Export each taxonomy
		foreach ( $used_taxonomies as $taxonomy_name ) {
			$taxonomy_data['taxonomies'][ $taxonomy_name ] = $this->export_taxonomy( $taxonomy_name );
		}

		// Export term-to-post relationships for exported content
		$taxonomy_data['term_relationships'] = $this->export_term_relationships();

		return $taxonomy_data;
	}

	/**
	 * Identify all taxonomies used by exported content.
	 *
	 * @return array Taxonomy names.
	 */
	private function identify_used_taxonomies() {
		$taxonomies = array();

		// Get taxonomies from exported content
		foreach ( $this->exported_post_ids as $post_id ) {
			$post = get_post( $post_id );
			if ( ! $post ) {
				continue;
			}

			$post_taxonomies = get_object_taxonomies( $post->post_type );
			$taxonomies = array_merge( $taxonomies, $post_taxonomies );
		}

		// Remove duplicates and exclude certain built-in taxonomies
		$taxonomies = array_unique( $taxonomies );
		$exclude = array( 'nav_menu', 'link_category', 'post_format' );
		$taxonomies = array_diff( $taxonomies, $exclude );

		return array_values( $taxonomies );
	}

	/**
	 * Export a single taxonomy with all its terms.
	 *
	 * @param string $taxonomy_name Taxonomy name.
	 * @return array Taxonomy data.
	 */
	private function export_taxonomy( $taxonomy_name ) {
		$taxonomy_obj = get_taxonomy( $taxonomy_name );

		if ( ! $taxonomy_obj ) {
			return array();
		}

		// Get all terms for this taxonomy
		$terms = get_terms( array(
			'taxonomy'   => $taxonomy_name,
			'hide_empty' => false,
			'orderby'    => 'term_id',
			'order'      => 'ASC',
		) );

		if ( is_wp_error( $terms ) ) {
			return array();
		}

		// Build taxonomy data
		$taxonomy_data = array(
			'name'         => $taxonomy_obj->label,
			'slug'         => $taxonomy_name,
			'description'  => $taxonomy_obj->description,
			'hierarchical' => $taxonomy_obj->hierarchical,
			'public'       => $taxonomy_obj->public,
			'object_types' => $taxonomy_obj->object_type,
			'terms'        => array(),
		);

		// Export each term
		foreach ( $terms as $term ) {
			$taxonomy_data['terms'][] = $this->export_term( $term, $taxonomy_name );
		}

		return $taxonomy_data;
	}

	/**
	 * Export a single term with metadata.
	 *
	 * @param WP_Term $term Term object.
	 * @param string  $taxonomy_name Taxonomy name.
	 * @return array Term data.
	 */
	private function export_term( $term, $taxonomy_name ) {
		$term_data = array(
			'term_id'     => $term->term_id,
			'name'        => $term->name,
			'slug'        => $term->slug,
			'description' => $term->description,
			'parent'      => $term->parent,
			'count'       => $term->count,
		);

		// Get term metadata
		$term_meta = $this->get_term_metadata( $term->term_id, $taxonomy_name );
		if ( ! empty( $term_meta ) ) {
			$term_data['meta'] = $term_meta;
		}

		return $term_data;
	}

	/**
	 * Get term metadata with filtering.
	 *
	 * @param int    $term_id Term ID.
	 * @param string $taxonomy_name Taxonomy name.
	 * @return array Filtered term metadata.
	 */
	private function get_term_metadata( $term_id, $taxonomy_name ) {
		// Get all term meta
		$all_meta = get_term_meta( $term_id );

		if ( empty( $all_meta ) ) {
			return array();
		}

		$filtered_meta = array();

		foreach ( $all_meta as $meta_key => $meta_values ) {
			// Skip if this meta key should be excluded
			if ( $this->should_exclude_meta_key( $meta_key ) ) {
				continue;
			}

			// Get the single value (WordPress stores meta as arrays)
			$meta_value = isset( $meta_values[0] ) ? $meta_values[0] : '';

			// Maybe unserialize
			$meta_value = maybe_unserialize( $meta_value );

			// Filter sensitive data from the value
			$meta_value = $this->filter_sensitive_meta_value( $meta_key, $meta_value );

			// Only include if not empty after filtering
			if ( ! empty( $meta_value ) || $meta_value === '0' || $meta_value === 0 ) {
				$filtered_meta[ $meta_key ] = $meta_value;
			}
		}

		return $filtered_meta;
	}

	/**
	 * Check if a meta key should be excluded from export.
	 *
	 * @param string $meta_key Meta key to check.
	 * @return bool True if should be excluded.
	 */
	private function should_exclude_meta_key( $meta_key ) {
		// Temporary and cache-related meta keys to exclude
		$exclude_patterns = array(
			'_transient_',
			'_site_transient_',
		);

		// Check exact matches and patterns
		foreach ( $exclude_patterns as $pattern ) {
			if ( $meta_key === $pattern || strpos( $meta_key, $pattern ) === 0 ) {
				return true;
			}
		}

		// Exclude sensitive meta keys
		$sensitive_patterns = array(
			'password',
			'api_key',
			'apikey',
			'secret',
			'token',
			'private_key',
			'privatekey',
		);

		$meta_key_lower = strtolower( $meta_key );
		foreach ( $sensitive_patterns as $pattern ) {
			if ( strpos( $meta_key_lower, $pattern ) !== false ) {
				return true;
			}
		}

		return false;
	}

	/**
	 * Filter sensitive data from meta values.
	 *
	 * @param string $meta_key Meta key.
	 * @param mixed  $meta_value Meta value.
	 * @return mixed Filtered meta value.
	 */
	private function filter_sensitive_meta_value( $meta_key, $meta_value ) {
		// If it's an array or object, recursively filter
		if ( is_array( $meta_value ) ) {
			return $this->filter_sensitive_array( $meta_value );
		}

		return $meta_value;
	}

	/**
	 * Recursively filter sensitive data from arrays.
	 *
	 * @param array $array Array to filter.
	 * @return array Filtered array.
	 */
	private function filter_sensitive_array( $array ) {
		$filtered = array();

		foreach ( $array as $key => $value ) {
			// Skip sensitive keys in arrays
			$sensitive_keys = array( 'password', 'api_key', 'secret', 'token', 'private_key' );
			$key_lower = strtolower( (string) $key );
			
			$is_sensitive = false;
			foreach ( $sensitive_keys as $sensitive ) {
				if ( strpos( $key_lower, $sensitive ) !== false ) {
					$is_sensitive = true;
					break;
				}
			}

			if ( $is_sensitive ) {
				continue;
			}

			// Recursively filter nested arrays
			if ( is_array( $value ) ) {
				$filtered[ $key ] = $this->filter_sensitive_array( $value );
			} else {
				$filtered[ $key ] = $value;
			}
		}

		return $filtered;
	}

	/**
	 * Export term-to-post relationships for exported content.
	 *
	 * @return array Term relationships keyed by post ID.
	 */
	private function export_term_relationships() {
		$relationships = array();

		foreach ( $this->exported_post_ids as $post_id ) {
			$post = get_post( $post_id );
			if ( ! $post ) {
				continue;
			}

			// Get all taxonomies for this post type
			$taxonomies = get_object_taxonomies( $post->post_type );

			$post_terms = array();

			foreach ( $taxonomies as $taxonomy ) {
				// Skip excluded taxonomies
				$exclude = array( 'nav_menu', 'link_category', 'post_format' );
				if ( in_array( $taxonomy, $exclude, true ) ) {
					continue;
				}

				// Get terms for this post and taxonomy
				$terms = wp_get_post_terms( $post_id, $taxonomy, array( 'fields' => 'ids' ) );

				if ( ! is_wp_error( $terms ) && ! empty( $terms ) ) {
					$post_terms[ $taxonomy ] = $terms;
				}
			}

			if ( ! empty( $post_terms ) ) {
				$relationships[ $post_id ] = $post_terms;
			}
		}

		return $relationships;
	}
}
