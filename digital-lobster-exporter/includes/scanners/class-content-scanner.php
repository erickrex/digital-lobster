<?php
/**
 * Content Scanner Class
 *
 * Exports sample content from posts, pages, and custom post types.
 * Parses blocks, generates block usage statistics, and exports content
 * to structured JSON files.
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Content Scanner Class
 */
class Digital_Lobster_Exporter_Content_Scanner {

	/**
	 * Block usage statistics.
	 *
	 * @var array
	 */
	private $block_usage = array();

	/**
	 * Settings for sample limits.
	 *
	 * @var array
	 */
	private $settings = array();

	/**
	 * Export directory path.
	 *
	 * @var string
	 */
	private $export_dir = '';

	/**
	 * Constructor.
	 *
	 * @param string $export_dir Optional export directory path.
	 */
	public function __construct( $export_dir = '' ) {
		$this->load_settings();
		$this->export_dir = $export_dir;
	}

	/**
	 * Load settings from wp_options.
	 */
	private function load_settings() {
		$defaults = array(
			'max_posts' => 5,
			'max_pages' => 2,
			'max_per_custom_post_type' => 10,
		);

		$saved_settings = get_option( 'digital_lobster_settings', array() );
		$this->settings = wp_parse_args( $saved_settings, $defaults );
	}

	/**
	 * Scan and collect content.
	 *
	 * @return array Content data.
	 */
	public function scan() {
		$this->block_usage = array();

		$content_data = array(
			'posts' => $this->export_posts(),
			'pages' => $this->export_pages(),
			'custom_post_types' => $this->export_custom_post_types(),
			'block_usage' => $this->get_block_usage_stats(),
		);

		return $content_data;
	}

	/**
	 * Export sample posts.
	 *
	 * @return array Exported posts data.
	 */
	private function export_posts() {
		$limit = absint( $this->settings['max_posts'] );
		
		$args = array(
			'post_type'      => 'post',
			'post_status'    => array( 'publish', 'private' ),
			'posts_per_page' => $limit,
			'orderby'        => 'date',
			'order'          => 'DESC',
			'no_found_rows'  => true,
		);

		return $this->query_and_export_content( $args, 'post' );
	}

	/**
	 * Export sample pages.
	 *
	 * @return array Exported pages data.
	 */
	private function export_pages() {
		$limit = absint( $this->settings['max_pages'] );
		
		$args = array(
			'post_type'      => 'page',
			'post_status'    => array( 'publish', 'private' ),
			'posts_per_page' => $limit,
			'orderby'        => 'date',
			'order'          => 'DESC',
			'no_found_rows'  => true,
		);

		return $this->query_and_export_content( $args, 'page' );
	}

	/**
	 * Export samples from all custom post types.
	 *
	 * @return array Exported custom post types data.
	 */
	private function export_custom_post_types() {
		$custom_post_types = $this->get_custom_post_types();
		$exported_data = array();

		foreach ( $custom_post_types as $post_type ) {
			$limit = absint( $this->settings['max_per_custom_post_type'] );
			
			$args = array(
				'post_type'      => $post_type,
				'post_status'    => array( 'publish', 'private' ),
				'posts_per_page' => $limit,
				'orderby'        => 'date',
				'order'          => 'DESC',
				'no_found_rows'  => true,
			);

			$exported_data[ $post_type ] = $this->query_and_export_content( $args, $post_type );
		}

		return $exported_data;
	}

	/**
	 * Get all custom post types (excluding built-in types).
	 *
	 * @return array Custom post type names.
	 */
	private function get_custom_post_types() {
		$all_post_types = get_post_types( array( 'public' => true ), 'names' );
		
		// Exclude built-in types
		$exclude = array( 'post', 'page', 'attachment' );
		
		return array_diff( $all_post_types, $exclude );
	}

	/**
	 * Query and export content based on WP_Query args.
	 *
	 * @param array  $args WP_Query arguments.
	 * @param string $post_type Post type being queried.
	 * @return array Exported content items.
	 */
	private function query_and_export_content( $args, $post_type ) {
		$query = new WP_Query( $args );
		$exported_items = array();

		if ( $query->have_posts() ) {
			while ( $query->have_posts() ) {
				$query->the_post();
				$post = get_post();
				
				$exported_items[] = $this->export_single_content_item( $post );
			}
			wp_reset_postdata();
		}

		return $exported_items;
	}

	/**
	 * Export a single content item to structured format.
	 *
	 * @param WP_Post $post Post object.
	 * @return array Structured content data.
	 */
	private function export_single_content_item( $post ) {
		// Parse blocks from content
		$blocks = parse_blocks( $post->post_content );
		$parsed_blocks = $this->parse_and_track_blocks( $blocks );

		// Get author info
		$author = get_userdata( $post->post_author );
		$author_data = array(
			'display_name' => $author ? $author->display_name : 'Unknown',
		);

		// Get taxonomies
		$taxonomies = $this->get_post_taxonomies( $post );

		// Get featured media
		$featured_media = $this->get_featured_media( $post->ID );

		// Get internal links
		$internal_links = $this->extract_internal_links( $post->post_content );

		// Get legacy permalink
		$legacy_permalink = $this->get_legacy_permalink( $post );

		// Get template
		$template = get_page_template_slug( $post->ID );
		if ( empty( $template ) ) {
			$template = 'default';
		}

		// Get postmeta
		$postmeta = $this->get_post_metadata( $post->ID, $post->post_type );

		// Build content item
		$content_item = array(
			'type'             => $post->post_type,
			'id'               => $post->ID,
			'slug'             => $post->post_name,
			'status'           => $post->post_status,
			'title'            => $post->post_title,
			'excerpt'          => $post->post_excerpt,
			'author'           => $author_data,
			'date_gmt'         => $post->post_date_gmt,
			'modified_gmt'     => $post->post_modified_gmt,
			'taxonomies'       => $taxonomies,
			'blocks'           => $parsed_blocks,
			'raw_html'         => $post->post_content,
			'featured_media'   => $featured_media,
			'internal_links'   => $internal_links,
			'legacy_permalink' => $legacy_permalink,
			'template'         => $template,
			'postmeta'         => $postmeta,
		);

		// Add GeoDirectory-specific metadata if this is a GeoDirectory CPT
		if ( $this->is_geodirectory_cpt( $post->post_type ) ) {
			$geodir_data = $this->get_geodirectory_metadata( $post );
			if ( ! empty( $geodir_data ) ) {
				$content_item['geodirectory'] = $geodir_data;
			}
		}

		// Generate HTML snapshot if export directory is set
		if ( ! empty( $this->export_dir ) && $this->should_generate_html_snapshot() ) {
			$this->generate_html_snapshot( $post );
		}

		return $content_item;
	}

	/**
	 * Parse blocks and track usage statistics.
	 *
	 * @param array $blocks Parsed blocks from parse_blocks().
	 * @return array Processed blocks with sanitized HTML.
	 */
	private function parse_and_track_blocks( $blocks ) {
		$parsed = array();

		foreach ( $blocks as $block ) {
			// Skip empty blocks
			if ( empty( $block['blockName'] ) ) {
				continue;
			}

			// Track block usage
			if ( ! isset( $this->block_usage[ $block['blockName'] ] ) ) {
				$this->block_usage[ $block['blockName'] ] = 0;
			}
			$this->block_usage[ $block['blockName'] ]++;

			// Build block data
			$block_data = array(
				'name'  => $block['blockName'],
				'attrs' => $block['attrs'] ?? array(),
				'html'  => $this->sanitize_block_html( $block['innerHTML'] ?? '' ),
			);

			// Recursively parse inner blocks
			if ( ! empty( $block['innerBlocks'] ) ) {
				$block_data['innerBlocks'] = $this->parse_and_track_blocks( $block['innerBlocks'] );
			}

			$parsed[] = $block_data;
		}

		return $parsed;
	}

	/**
	 * Sanitize block HTML content.
	 *
	 * @param string $html Raw HTML content.
	 * @return string Sanitized HTML.
	 */
	private function sanitize_block_html( $html ) {
		// Remove excessive whitespace but preserve structure
		$html = trim( $html );
		
		// Allow all HTML tags for content preservation
		// In a real migration, we want to preserve the exact HTML
		return $html;
	}

	/**
	 * Get taxonomies and terms for a post.
	 *
	 * @param WP_Post $post Post object.
	 * @return array Taxonomies with term IDs.
	 */
	private function get_post_taxonomies( $post ) {
		$taxonomies = get_object_taxonomies( $post->post_type );
		$taxonomy_data = array();

		foreach ( $taxonomies as $taxonomy ) {
			$terms = wp_get_post_terms( $post->ID, $taxonomy, array( 'fields' => 'ids' ) );
			
			if ( ! is_wp_error( $terms ) && ! empty( $terms ) ) {
				$taxonomy_data[ $taxonomy ] = $terms;
			}
		}

		return $taxonomy_data;
	}

	/**
	 * Get featured media information.
	 *
	 * @param int $post_id Post ID.
	 * @return array|null Featured media data or null.
	 */
	private function get_featured_media( $post_id ) {
		$thumbnail_id = get_post_thumbnail_id( $post_id );
		
		if ( ! $thumbnail_id ) {
			return null;
		}

		$attachment = get_post( $thumbnail_id );
		$image_url = wp_get_attachment_url( $thumbnail_id );
		$alt_text = get_post_meta( $thumbnail_id, '_wp_attachment_image_alt', true );

		return array(
			'id'  => $thumbnail_id,
			'url' => $image_url,
			'alt' => $alt_text,
		);
	}

	/**
	 * Get post metadata with filtering.
	 *
	 * @param int    $post_id Post ID.
	 * @param string $post_type Post type.
	 * @return array Filtered postmeta.
	 */
	private function get_post_metadata( $post_id, $post_type ) {
		// Get all postmeta for this post
		$all_meta = get_post_meta( $post_id );
		
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

		// For attachment post type, include additional metadata
		if ( $post_type === 'attachment' ) {
			$filtered_meta = $this->add_attachment_metadata( $post_id, $filtered_meta );
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
			'_edit_lock',           // Edit lock temporary data
			'_edit_last',           // Last editor temporary data
			'_wp_old_slug',         // Old slug redirects (handled separately)
			'_wp_old_date',         // Old date temporary data
			'_wp_trash_',           // Trash-related temporary data
			'_transient_',          // Transients
			'_site_transient_',     // Site transients
			'_oembed_',             // oEmbed cache
			'_encloseme',           // Pingback temporary data
			'_pingme',              // Pingback temporary data
			'_wp_attachment_backup_sizes', // Image backup data (large)
		);

		// Check exact matches and patterns
		foreach ( $exclude_patterns as $pattern ) {
			if ( $meta_key === $pattern || strpos( $meta_key, $pattern ) === 0 ) {
				return true;
			}
		}

		// Exclude sensitive meta keys (check for patterns anywhere in the key)
		$sensitive_patterns = array(
			'password',             // Any password fields
			'api_key',              // API keys
			'apikey',               // API keys (no underscore)
			'secret',               // Secret keys
			'token',                // Auth tokens
			'private_key',          // Private keys
			'privatekey',           // Private keys (no underscore)
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

		// For string values, check for sensitive patterns
		if ( is_string( $meta_value ) ) {
			// Don't filter SEO meta or other important string fields
			// Just return as-is for now
			return $meta_value;
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
	 * Add attachment-specific metadata.
	 *
	 * @param int   $attachment_id Attachment ID.
	 * @param array $meta Existing meta array.
	 * @return array Meta with attachment data added.
	 */
	private function add_attachment_metadata( $attachment_id, $meta ) {
		// Get attachment metadata
		$attachment_meta = wp_get_attachment_metadata( $attachment_id );
		
		if ( ! empty( $attachment_meta ) ) {
			$meta['_wp_attachment_metadata'] = $attachment_meta;
		}

		// Get alt text (already in meta, but ensure it's included)
		$alt_text = get_post_meta( $attachment_id, '_wp_attachment_image_alt', true );
		if ( ! empty( $alt_text ) ) {
			$meta['_wp_attachment_image_alt'] = $alt_text;
		}

		// Get attachment URL
		$attachment_url = wp_get_attachment_url( $attachment_id );
		if ( $attachment_url ) {
			$meta['_attachment_url'] = $attachment_url;
		}

		// Get MIME type
		$mime_type = get_post_mime_type( $attachment_id );
		if ( $mime_type ) {
			$meta['_mime_type'] = $mime_type;
		}

		return $meta;
	}

	/**
	 * Extract internal links from content.
	 *
	 * @param string $content Post content.
	 * @return array Internal link paths.
	 */
	private function extract_internal_links( $content ) {
		$internal_links = array();
		$site_url = get_site_url();
		
		// Match all href attributes
		preg_match_all( '/<a[^>]+href=["\']([^"\']+)["\'][^>]*>/i', $content, $matches );
		
		if ( ! empty( $matches[1] ) ) {
			foreach ( $matches[1] as $url ) {
				// Check if it's an internal link
				if ( strpos( $url, $site_url ) === 0 ) {
					// Convert to relative path
					$path = str_replace( $site_url, '', $url );
					$internal_links[] = $path;
				} elseif ( strpos( $url, '/' ) === 0 && strpos( $url, '//' ) !== 0 ) {
					// Already a relative path
					$internal_links[] = $url;
				}
			}
		}

		return array_unique( $internal_links );
	}

	/**
	 * Get legacy permalink for a post.
	 *
	 * @param WP_Post $post Post object.
	 * @return string Legacy permalink.
	 */
	private function get_legacy_permalink( $post ) {
		$permalink = get_permalink( $post->ID );
		$site_url = get_site_url();
		
		// Convert to relative path
		return str_replace( $site_url, '', $permalink );
	}

	/**
	 * Get block usage statistics.
	 *
	 * @return array Top blocks by usage count.
	 */
	private function get_block_usage_stats() {
		// Sort by usage count descending
		arsort( $this->block_usage );

		// Convert to array format
		$stats = array();
		foreach ( $this->block_usage as $block_name => $count ) {
			$stats[] = array(
				'name'  => $block_name,
				'count' => $count,
			);
		}

		return $stats;
	}

	/**
	 * Check if a post type is a GeoDirectory custom post type.
	 *
	 * @param string $post_type Post type name.
	 * @return bool True if GeoDirectory CPT.
	 */
	private function is_geodirectory_cpt( $post_type ) {
		// Check if the geodir_cpt taxonomy exists
		if ( ! taxonomy_exists( 'geodir_cpt' ) ) {
			return false;
		}

		// Check if this post type is associated with geodir_cpt taxonomy
		$taxonomies = get_object_taxonomies( $post_type );
		return in_array( 'geodir_cpt', $taxonomies, true );
	}

	/**
	 * Get GeoDirectory-specific metadata for a post.
	 *
	 * @param WP_Post $post Post object.
	 * @return array GeoDirectory metadata.
	 */
	private function get_geodirectory_metadata( $post ) {
		global $wpdb;

		$geodir_data = array();

		// Get the detail table name for this post type
		$detail_table = $this->get_geodir_detail_table( $post->post_type );

		// Read metadata from GeoDirectory custom table if it exists
		if ( $detail_table ) {
			$detail_data = $wpdb->get_row(
				$wpdb->prepare(
					"SELECT * FROM {$detail_table} WHERE post_id = %d",
					$post->ID
				),
				ARRAY_A
			);

			if ( $detail_data ) {
				// Extract address information
				$geodir_data['address'] = array(
					'street'   => isset( $detail_data['street'] ) ? $detail_data['street'] : '',
					'street2'  => isset( $detail_data['street2'] ) ? $detail_data['street2'] : '',
					'city'     => isset( $detail_data['city'] ) ? $detail_data['city'] : '',
					'region'   => isset( $detail_data['region'] ) ? $detail_data['region'] : '',
					'country'  => isset( $detail_data['country'] ) ? $detail_data['country'] : '',
					'zip'      => isset( $detail_data['zip'] ) ? $detail_data['zip'] : '',
					'postcode' => isset( $detail_data['postcode'] ) ? $detail_data['postcode'] : '',
				);

				// Extract geo coordinates
				$geodir_data['geo'] = array(
					'latitude'  => isset( $detail_data['latitude'] ) ? $detail_data['latitude'] : '',
					'longitude' => isset( $detail_data['longitude'] ) ? $detail_data['longitude'] : '',
				);

				// Store all other custom fields from the detail table
				$geodir_data['custom_fields'] = array();
				$exclude_fields = array( 'post_id', 'street', 'street2', 'city', 'region', 'country', 'zip', 'postcode', 'latitude', 'longitude' );
				
				foreach ( $detail_data as $key => $value ) {
					if ( ! in_array( $key, $exclude_fields, true ) ) {
						$geodir_data['custom_fields'][ $key ] = $value;
					}
				}
			}
		}

		// Get standard postmeta that GeoDirectory might use
		$geodir_meta_keys = array(
			'geodir_contact',
			'geodir_email',
			'geodir_website',
			'geodir_phone',
			'geodir_twitter',
			'geodir_facebook',
			'geodir_video',
			'geodir_timing',
			'geodir_featured',
			'geodir_special_offers',
		);

		$postmeta = array();
		foreach ( $geodir_meta_keys as $meta_key ) {
			$value = get_post_meta( $post->ID, $meta_key, true );
			if ( ! empty( $value ) ) {
				$postmeta[ $meta_key ] = $value;
			}
		}

		if ( ! empty( $postmeta ) ) {
			$geodir_data['postmeta'] = $postmeta;
		}

		// Get categories (from GeoDirectory category taxonomies)
		$category_taxonomies = $this->get_geodir_category_taxonomies( $post->post_type );
		if ( ! empty( $category_taxonomies ) ) {
			$categories = array();
			foreach ( $category_taxonomies as $taxonomy ) {
				$terms = wp_get_post_terms( $post->ID, $taxonomy, array( 'fields' => 'all' ) );
				if ( ! is_wp_error( $terms ) && ! empty( $terms ) ) {
					foreach ( $terms as $term ) {
						$categories[] = array(
							'taxonomy' => $taxonomy,
							'term_id'  => $term->term_id,
							'name'     => $term->name,
							'slug'     => $term->slug,
						);
					}
				}
			}
			if ( ! empty( $categories ) ) {
				$geodir_data['categories'] = $categories;
			}
		}

		// Get tags/amenities (from GeoDirectory tags taxonomies)
		$tags_taxonomies = $this->get_geodir_tags_taxonomies( $post->post_type );
		if ( ! empty( $tags_taxonomies ) ) {
			$tags = array();
			foreach ( $tags_taxonomies as $taxonomy ) {
				$terms = wp_get_post_terms( $post->ID, $taxonomy, array( 'fields' => 'all' ) );
				if ( ! is_wp_error( $terms ) && ! empty( $terms ) ) {
					foreach ( $terms as $term ) {
						$tags[] = array(
							'taxonomy' => $taxonomy,
							'term_id'  => $term->term_id,
							'name'     => $term->name,
							'slug'     => $term->slug,
						);
					}
				}
			}
			if ( ! empty( $tags ) ) {
				$geodir_data['tags'] = $tags;
			}
		}

		return $geodir_data;
	}

	/**
	 * Get the GeoDirectory detail table name for a post type.
	 *
	 * @param string $post_type Post type name.
	 * @return string|null Table name or null if not found.
	 */
	private function get_geodir_detail_table( $post_type ) {
		global $wpdb;

		// GeoDirectory uses tables like geodir_gd_place_detail, geodir_gd_event_detail, etc.
		$table_name = $wpdb->prefix . 'geodir_' . $post_type . '_detail';

		// Check if table exists
		$table_exists = $wpdb->get_var(
			$wpdb->prepare(
				'SHOW TABLES LIKE %s',
				$table_name
			)
		);

		return $table_exists ? $table_name : null;
	}

	/**
	 * Get GeoDirectory category taxonomies for a post type.
	 *
	 * @param string $post_type Post type name.
	 * @return array Category taxonomy names.
	 */
	private function get_geodir_category_taxonomies( $post_type ) {
		$taxonomies = get_object_taxonomies( $post_type );
		$category_taxonomies = array();

		foreach ( $taxonomies as $taxonomy ) {
			// GeoDirectory category taxonomies typically end with 'category'
			if ( strpos( $taxonomy, 'category' ) !== false && strpos( $taxonomy, 'gd_' ) === 0 ) {
				$category_taxonomies[] = $taxonomy;
			}
		}

		return $category_taxonomies;
	}

	/**
	 * Get GeoDirectory tags/amenities taxonomies for a post type.
	 *
	 * @param string $post_type Post type name.
	 * @return array Tags taxonomy names.
	 */
	private function get_geodir_tags_taxonomies( $post_type ) {
		$taxonomies = get_object_taxonomies( $post_type );
		$tags_taxonomies = array();

		foreach ( $taxonomies as $taxonomy ) {
			// GeoDirectory tags taxonomies typically contain 'tags' or specific names like 'gd_amenity'
			if ( ( strpos( $taxonomy, 'tags' ) !== false || strpos( $taxonomy, 'amenity' ) !== false ) && strpos( $taxonomy, 'gd_' ) === 0 ) {
				$tags_taxonomies[] = $taxonomy;
			}
		}

		return $tags_taxonomies;
	}

	/**
	 * Check if HTML snapshots should be generated.
	 *
	 * @return bool True if snapshots should be generated.
	 */
	private function should_generate_html_snapshot() {
		// Check if setting is enabled (default to true)
		$include_snapshots = isset( $this->settings['include_html_snapshots'] ) 
			? $this->settings['include_html_snapshots'] 
			: true;

		return (bool) $include_snapshots;
	}

	/**
	 * Generate HTML snapshot for a post.
	 *
	 * @param WP_Post $post Post object.
	 * @return bool True on success, false on failure.
	 */
	private function generate_html_snapshot( $post ) {
		// Create snapshots directory if it doesn't exist
		$snapshots_dir = trailingslashit( $this->export_dir ) . 'snapshots';
		if ( ! file_exists( $snapshots_dir ) ) {
			wp_mkdir_p( $snapshots_dir );
		}

		// Generate filename
		$filename = sanitize_file_name( $post->post_name ) . '.html';
		$filepath = trailingslashit( $snapshots_dir ) . $filename;

		// Try to fetch rendered HTML via wp_remote_get
		$html = $this->fetch_rendered_html( $post );

		// If remote fetch failed, try server-side template capture
		if ( false === $html ) {
			$html = $this->capture_template_output( $post );
		}

		// If we still don't have HTML, log error and return
		if ( false === $html ) {
			error_log( sprintf(
				'Digital Lobster Exporter: Failed to generate HTML snapshot for post %d (%s)',
				$post->ID,
				$post->post_name
			) );
			return false;
		}

		// Save HTML to file
		$result = file_put_contents( $filepath, $html );

		if ( false === $result ) {
			error_log( sprintf(
				'Digital Lobster Exporter: Failed to write HTML snapshot file for post %d (%s)',
				$post->ID,
				$post->post_name
			) );
			return false;
		}

		return true;
	}

	/**
	 * Fetch rendered HTML via wp_remote_get.
	 *
	 * @param WP_Post $post Post object.
	 * @return string|false HTML content or false on failure.
	 */
	private function fetch_rendered_html( $post ) {
		// Get the permalink
		$permalink = get_permalink( $post->ID );

		if ( ! $permalink ) {
			return false;
		}

		// Skip if post is not published (private posts may not be accessible)
		if ( 'publish' !== $post->post_status ) {
			return false;
		}

		// Make remote request
		$response = wp_remote_get( $permalink, array(
			'timeout'     => 30,
			'redirection' => 5,
			'sslverify'   => false, // Allow self-signed certificates in dev environments
			'headers'     => array(
				'User-Agent' => 'Digital-Lobster-Exporter/1.0',
			),
		) );

		// Check for errors
		if ( is_wp_error( $response ) ) {
			error_log( sprintf(
				'Digital Lobster Exporter: wp_remote_get error for post %d: %s',
				$post->ID,
				$response->get_error_message()
			) );
			return false;
		}

		// Check response code
		$response_code = wp_remote_retrieve_response_code( $response );
		if ( 200 !== $response_code ) {
			error_log( sprintf(
				'Digital Lobster Exporter: HTTP %d response for post %d (%s)',
				$response_code,
				$post->ID,
				$permalink
			) );
			return false;
		}

		// Get body
		$html = wp_remote_retrieve_body( $response );

		if ( empty( $html ) ) {
			return false;
		}

		return $html;
	}

	/**
	 * Capture template output server-side as fallback.
	 *
	 * @param WP_Post $post Post object.
	 * @return string|false HTML content or false on failure.
	 */
	private function capture_template_output( $post ) {
		// This is a fallback method that captures the template output
		// by simulating the WordPress template hierarchy

		global $wp_query;

		// Save current query
		$original_query = $wp_query;

		// Create a new query for this specific post
		$wp_query = new WP_Query( array(
			'p'         => $post->ID,
			'post_type' => $post->post_type,
		) );

		// Set up post data
		if ( $wp_query->have_posts() ) {
			$wp_query->the_post();

			// Start output buffering
			ob_start();

			try {
				// Try to load the template
				// This will use the theme's template hierarchy
				if ( 'page' === $post->post_type ) {
					$template = get_page_template();
				} else {
					$template = get_single_template();
				}

				// If we found a template, include it
				if ( $template && file_exists( $template ) ) {
					include $template;
				} else {
					// No template found, return false
					ob_end_clean();
					wp_reset_postdata();
					$wp_query = $original_query;
					return false;
				}

				// Get the buffered content
				$html = ob_get_clean();

				// Reset post data
				wp_reset_postdata();

				// Restore original query
				$wp_query = $original_query;

				return $html;

			} catch ( Exception $e ) {
				// Clean buffer and restore state on error
				ob_end_clean();
				wp_reset_postdata();
				$wp_query = $original_query;

				error_log( sprintf(
					'Digital Lobster Exporter: Template capture exception for post %d: %s',
					$post->ID,
					$e->getMessage()
				) );

				return false;
			}
		}

		// Restore original query
		$wp_query = $original_query;

		return false;
	}
}
