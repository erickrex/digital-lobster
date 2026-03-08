<?php
/**
 * Content Relationships Scanner Class
 *
 * Produces a normalized content_relationships.json artifact containing
 * the relation graph across the site: post-to-post, post-to-user,
 * post-to-term, post-to-media, plugin-owned entity references, and
 * custom-table-to-post/meta relationships.
 *
 * All entity references use stable source identifiers:
 *   Posts:   "post:{ID}"
 *   Users:   "user:{ID}"
 *   Terms:   "term:{taxonomy}:{term_id}"
 *   Media:   "media:{ID}"
 *   Plugin:  "plugin:{source_plugin}:{entity_type}:{ID}"
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Content Relationships Scanner Class
 */
class Digital_Lobster_Exporter_Content_Relationships_Scanner extends Digital_Lobster_Exporter_Scanner_Base {

	/**
	 * Exported content data (from ContentScanner).
	 *
	 * @var array
	 */
	private $exported_content = array();

	/**
	 * Post IDs that were exported.
	 *
	 * @var int[]
	 */
	private $exported_post_ids = array();

	/**
	 * Collected relationships.
	 *
	 * @var array
	 */
	private $relationships = array();

	/**
	 * Constructor.
	 *
	 * @param array $deps Optional. Associative array of dependencies.
	 */
	public function __construct( array $deps = array() ) {
		parent::__construct( $deps );
		$this->exported_content = isset( $this->context['content'] ) ? $this->context['content'] : array();
		$this->extract_exported_post_ids();
	}

	/**
	 * Extract post IDs from exported content data.
	 */
	private function extract_exported_post_ids() {
		$this->exported_post_ids = array();

		if ( isset( $this->exported_content['posts'] ) && is_array( $this->exported_content['posts'] ) ) {
			foreach ( $this->exported_content['posts'] as $post ) {
				if ( isset( $post['id'] ) ) {
					$this->exported_post_ids[] = (int) $post['id'];
				}
			}
		}

		if ( isset( $this->exported_content['pages'] ) && is_array( $this->exported_content['pages'] ) ) {
			foreach ( $this->exported_content['pages'] as $page ) {
				if ( isset( $page['id'] ) ) {
					$this->exported_post_ids[] = (int) $page['id'];
				}
			}
		}

		if ( isset( $this->exported_content['custom_post_types'] ) && is_array( $this->exported_content['custom_post_types'] ) ) {
			foreach ( $this->exported_content['custom_post_types'] as $post_type => $items ) {
				if ( is_array( $items ) ) {
					foreach ( $items as $item ) {
						if ( isset( $item['id'] ) ) {
							$this->exported_post_ids[] = (int) $item['id'];
						}
					}
				}
			}
		}

		$this->exported_post_ids = array_unique( $this->exported_post_ids );
	}

	/**
	 * Scan and collect content relationships.
	 *
	 * @return array Content relationships data matching ContentRelationshipsArtifact schema.
	 */
	public function scan() {
		$this->relationships = array();

		$this->scan_post_parent_relationships();
		$this->scan_post_to_user_relationships();
		$this->scan_post_to_term_relationships();
		$this->scan_post_to_media_relationships();
		$this->scan_internal_link_relationships();
		$this->scan_plugin_entity_relationships();
		$this->scan_custom_table_relationships();

		return array(
			'schema_version' => '1.0.0',
			'relationships'  => $this->relationships,
		);
	}

	/**
	 * Scan post parent (hierarchical) relationships.
	 *
	 * Captures parent-child relationships for pages and hierarchical CPTs.
	 */
	private function scan_post_parent_relationships() {
		foreach ( $this->exported_post_ids as $post_id ) {
			$post = get_post( $post_id );
			if ( ! $post || empty( $post->post_parent ) ) {
				continue;
			}

			$this->add_relationship(
				'post:' . $post_id,
				'post:' . $post->post_parent,
				'post_to_post',
				null,
				array( 'subtype' => 'parent' )
			);
		}
	}

	/**
	 * Scan post-to-user (author) relationships.
	 */
	private function scan_post_to_user_relationships() {
		foreach ( $this->exported_post_ids as $post_id ) {
			$post = get_post( $post_id );
			if ( ! $post || empty( $post->post_author ) ) {
				continue;
			}

			$this->add_relationship(
				'post:' . $post_id,
				'user:' . $post->post_author,
				'post_to_user'
			);
		}
	}

	/**
	 * Scan post-to-term relationships from wp_term_relationships.
	 */
	private function scan_post_to_term_relationships() {
		$exclude_taxonomies = array( 'nav_menu', 'link_category', 'post_format' );

		foreach ( $this->exported_post_ids as $post_id ) {
			$post = get_post( $post_id );
			if ( ! $post ) {
				continue;
			}

			$taxonomies = get_object_taxonomies( $post->post_type );

			foreach ( $taxonomies as $taxonomy ) {
				if ( in_array( $taxonomy, $exclude_taxonomies, true ) ) {
					continue;
				}

				$terms = wp_get_post_terms( $post_id, $taxonomy, array( 'fields' => 'all' ) );
				if ( is_wp_error( $terms ) || empty( $terms ) ) {
					continue;
				}

				foreach ( $terms as $term ) {
					$this->add_relationship(
						'post:' . $post_id,
						'term:' . $taxonomy . ':' . $term->term_id,
						'post_to_term',
						null,
						array( 'taxonomy' => $taxonomy )
					);
				}
			}
		}
	}

	/**
	 * Scan post-to-media relationships.
	 *
	 * Captures featured images, inline media references from post_content,
	 * and gallery block media.
	 */
	private function scan_post_to_media_relationships() {
		foreach ( $this->exported_post_ids as $post_id ) {
			$post = get_post( $post_id );
			if ( ! $post ) {
				continue;
			}

			// Featured image.
			$thumbnail_id = get_post_thumbnail_id( $post_id );
			if ( $thumbnail_id ) {
				$this->add_relationship(
					'post:' . $post_id,
					'media:' . $thumbnail_id,
					'post_to_media',
					null,
					array( 'subtype' => 'featured_image' )
				);
			}

			// Inline images in post_content.
			$this->scan_inline_media( $post_id, $post->post_content );

			// Gallery blocks.
			$this->scan_gallery_blocks( $post_id, $post->post_content );
		}
	}

	/**
	 * Scan inline media references (img tags) in post content.
	 *
	 * @param int    $post_id Post ID.
	 * @param string $content Post content.
	 */
	private function scan_inline_media( $post_id, $content ) {
		if ( empty( $content ) ) {
			return;
		}

		// Match wp-image-{ID} class on img tags (standard WP pattern).
		preg_match_all( '/wp-image-(\d+)/i', $content, $matches );

		if ( ! empty( $matches[1] ) ) {
			$media_ids = array_unique( $matches[1] );
			foreach ( $media_ids as $media_id ) {
				$media_id = (int) $media_id;
				if ( $media_id > 0 ) {
					$this->add_relationship(
						'post:' . $post_id,
						'media:' . $media_id,
						'post_to_media',
						null,
						array( 'subtype' => 'inline' )
					);
				}
			}
		}

		// Match attachment page URLs that resolve to media IDs.
		$site_url = get_site_url();
		preg_match_all( '/<img[^>]+src=["\']([^"\']+)["\'][^>]*>/i', $content, $img_matches );

		if ( ! empty( $img_matches[1] ) ) {
			foreach ( $img_matches[1] as $src ) {
				// Only process internal URLs.
				if ( strpos( $src, $site_url ) !== 0 && strpos( $src, '/' ) !== 0 ) {
					continue;
				}

				$attachment_id = attachment_url_to_postid( $src );
				if ( $attachment_id > 0 ) {
					$this->add_relationship(
						'post:' . $post_id,
						'media:' . $attachment_id,
						'post_to_media',
						null,
						array( 'subtype' => 'inline' )
					);
				}
			}
		}
	}

	/**
	 * Scan gallery blocks for media references.
	 *
	 * @param int    $post_id Post ID.
	 * @param string $content Post content.
	 */
	private function scan_gallery_blocks( $post_id, $content ) {
		if ( empty( $content ) || ! has_blocks( $content ) ) {
			return;
		}

		$blocks = parse_blocks( $content );
		$this->extract_gallery_media_from_blocks( $post_id, $blocks );
	}

	/**
	 * Recursively extract media IDs from gallery blocks.
	 *
	 * @param int   $post_id Post ID.
	 * @param array $blocks  Parsed blocks.
	 */
	private function extract_gallery_media_from_blocks( $post_id, $blocks ) {
		foreach ( $blocks as $block ) {
			if ( 'core/gallery' === $block['blockName'] && ! empty( $block['attrs']['ids'] ) ) {
				foreach ( $block['attrs']['ids'] as $media_id ) {
					$media_id = (int) $media_id;
					if ( $media_id > 0 ) {
						$this->add_relationship(
							'post:' . $post_id,
							'media:' . $media_id,
							'post_to_media',
							null,
							array( 'subtype' => 'gallery' )
						);
					}
				}
			}

			// Also check core/image blocks for explicit ID attrs.
			if ( 'core/image' === $block['blockName'] && ! empty( $block['attrs']['id'] ) ) {
				$media_id = (int) $block['attrs']['id'];
				if ( $media_id > 0 ) {
					$this->add_relationship(
						'post:' . $post_id,
						'media:' . $media_id,
						'post_to_media',
						null,
						array( 'subtype' => 'block_image' )
					);
				}
			}

			// Recurse into inner blocks.
			if ( ! empty( $block['innerBlocks'] ) ) {
				$this->extract_gallery_media_from_blocks( $post_id, $block['innerBlocks'] );
			}
		}
	}

	/**
	 * Scan internal link relationships (post-to-post via href analysis).
	 */
	private function scan_internal_link_relationships() {
		$site_url = get_site_url();

		foreach ( $this->exported_post_ids as $post_id ) {
			$post = get_post( $post_id );
			if ( ! $post || empty( $post->post_content ) ) {
				continue;
			}

			preg_match_all( '/<a[^>]+href=["\']([^"\']+)["\'][^>]*>/i', $post->post_content, $matches );

			if ( empty( $matches[1] ) ) {
				continue;
			}

			foreach ( $matches[1] as $url ) {
				$target_id = $this->resolve_url_to_post_id( $url, $site_url );
				if ( $target_id && $target_id !== $post_id ) {
					$this->add_relationship(
						'post:' . $post_id,
						'post:' . $target_id,
						'post_to_post',
						null,
						array( 'subtype' => 'internal_link' )
					);
				}
			}
		}
	}

	/**
	 * Resolve a URL to a WordPress post ID.
	 *
	 * @param string $url      The URL to resolve.
	 * @param string $site_url The site URL for comparison.
	 * @return int|false Post ID or false if not resolvable.
	 */
	private function resolve_url_to_post_id( $url, $site_url ) {
		// Must be an internal URL.
		if ( strpos( $url, $site_url ) === 0 ) {
			$resolved = url_to_postid( $url );
			return $resolved > 0 ? $resolved : false;
		}

		// Relative URL starting with /.
		if ( strpos( $url, '/' ) === 0 && strpos( $url, '//' ) !== 0 ) {
			$full_url = $site_url . $url;
			$resolved = url_to_postid( $full_url );
			return $resolved > 0 ? $resolved : false;
		}

		return false;
	}

	/**
	 * Scan plugin-owned entity relationships.
	 *
	 * Detects ACF relationship/post_object fields and Pods relationship fields
	 * that create entity-to-entity references.
	 */
	private function scan_plugin_entity_relationships() {
		$this->scan_acf_relationships();
		$this->scan_pods_relationships();
	}

	/**
	 * Scan ACF relationship and post_object fields.
	 */
	private function scan_acf_relationships() {
		if ( ! function_exists( 'acf_get_field_groups' ) ) {
			return;
		}

		$field_groups = acf_get_field_groups();
		if ( empty( $field_groups ) ) {
			return;
		}

		// Collect relationship field keys.
		$relationship_fields = array();
		foreach ( $field_groups as $group ) {
			$fields = acf_get_fields( $group['key'] );
			if ( empty( $fields ) ) {
				continue;
			}
			foreach ( $fields as $field ) {
				if ( in_array( $field['type'], array( 'relationship', 'post_object' ), true ) ) {
					$relationship_fields[] = $field['name'];
				}
			}
		}

		if ( empty( $relationship_fields ) ) {
			return;
		}

		// For each exported post, check these fields.
		foreach ( $this->exported_post_ids as $post_id ) {
			foreach ( $relationship_fields as $field_name ) {
				$value = get_post_meta( $post_id, $field_name, true );
				if ( empty( $value ) ) {
					continue;
				}

				$target_ids = is_array( $value ) ? $value : array( $value );
				foreach ( $target_ids as $target_id ) {
					$target_id = (int) $target_id;
					if ( $target_id > 0 ) {
						$this->add_relationship(
							'post:' . $post_id,
							'post:' . $target_id,
							'plugin_entity',
							'acf',
							array( 'field_name' => $field_name )
						);
					}
				}
			}
		}
	}

	/**
	 * Scan Pods relationship fields.
	 */
	private function scan_pods_relationships() {
		if ( ! function_exists( 'pods_api' ) ) {
			return;
		}

		try {
			$api = pods_api();
			$pods = $api->load_pods( array( 'names' => true ) );
		} catch ( \Exception $e ) {
			$this->log_warning( 'content_relationships', 'Failed to load Pods API: ' . $e->getMessage() );
			return;
		}

		if ( empty( $pods ) || ! is_array( $pods ) ) {
			return;
		}

		foreach ( $pods as $pod_name => $pod_label ) {
			try {
				$pod = pods_api()->load_pod( array( 'name' => $pod_name ) );
			} catch ( \Exception $e ) {
				continue;
			}

			if ( empty( $pod['fields'] ) ) {
				continue;
			}

			$rel_fields = array();
			foreach ( $pod['fields'] as $field ) {
				if ( isset( $field['type'] ) && $field['type'] === 'pick' ) {
					$rel_fields[] = $field['name'];
				}
			}

			if ( empty( $rel_fields ) ) {
				continue;
			}

			// Check exported posts that match this pod's post type.
			foreach ( $this->exported_post_ids as $post_id ) {
				$post = get_post( $post_id );
				if ( ! $post || $post->post_type !== $pod_name ) {
					continue;
				}

				foreach ( $rel_fields as $field_name ) {
					$value = get_post_meta( $post_id, $field_name, true );
					if ( empty( $value ) ) {
						continue;
					}

					$target_ids = is_array( $value ) ? $value : array( $value );
					foreach ( $target_ids as $target_id ) {
						$target_id = (int) $target_id;
						if ( $target_id > 0 ) {
							$this->add_relationship(
								'post:' . $post_id,
								'post:' . $target_id,
								'plugin_entity',
								'pods',
								array( 'field_name' => $field_name )
							);
						}
					}
				}
			}
		}
	}

	/**
	 * Scan custom table foreign key references to posts/meta.
	 *
	 * Uses context['database'] if available (from Database_Scanner) to find
	 * custom tables with columns that reference post IDs.
	 */
	private function scan_custom_table_relationships() {
		$database_context = isset( $this->context['database'] ) ? $this->context['database'] : array();
		if ( empty( $database_context ) ) {
			return;
		}

		$custom_tables = isset( $database_context['custom_tables'] ) ? $database_context['custom_tables'] : array();
		if ( empty( $custom_tables ) || ! is_array( $custom_tables ) ) {
			return;
		}

		global $wpdb;

		foreach ( $custom_tables as $table_info ) {
			$table_name = isset( $table_info['name'] ) ? $table_info['name'] : '';
			if ( empty( $table_name ) ) {
				continue;
			}

			$source_plugin = isset( $table_info['source_plugin'] ) ? $table_info['source_plugin'] : null;

			// Look for columns that likely reference post IDs.
			$fk_columns = $this->detect_post_reference_columns( $table_info );
			if ( empty( $fk_columns ) ) {
				continue;
			}

			foreach ( $fk_columns as $column_name ) {
				$this->scan_custom_table_column( $wpdb, $table_name, $column_name, $source_plugin );
			}
		}
	}

	/**
	 * Detect columns in a custom table that likely reference post IDs.
	 *
	 * @param array $table_info Table info from database context.
	 * @return string[] Column names that likely reference posts.
	 */
	private function detect_post_reference_columns( $table_info ) {
		$fk_columns = array();

		// Check explicit foreign_key_candidates if available.
		if ( ! empty( $table_info['foreign_key_candidates'] ) && is_array( $table_info['foreign_key_candidates'] ) ) {
			return $table_info['foreign_key_candidates'];
		}

		// Heuristic: columns named *_post_id, *_object_id, post_id, object_id.
		$columns = isset( $table_info['columns'] ) ? $table_info['columns'] : array();
		if ( empty( $columns ) || ! is_array( $columns ) ) {
			return $fk_columns;
		}

		$post_ref_patterns = array( 'post_id', 'object_id', 'item_id' );

		foreach ( $columns as $col ) {
			$col_name = is_array( $col ) ? ( isset( $col['name'] ) ? $col['name'] : '' ) : (string) $col;
			if ( empty( $col_name ) ) {
				continue;
			}

			$col_lower = strtolower( $col_name );
			foreach ( $post_ref_patterns as $pattern ) {
				if ( $col_lower === $pattern || substr( $col_lower, -strlen( '_' . $pattern ) ) === '_' . $pattern ) {
					$fk_columns[] = $col_name;
					break;
				}
			}
		}

		return $fk_columns;
	}

	/**
	 * Scan a single custom table column for post ID references.
	 *
	 * @param wpdb        $wpdb          WordPress database object.
	 * @param string      $table_name    Full table name.
	 * @param string      $column_name   Column to scan.
	 * @param string|null $source_plugin Source plugin identifier.
	 */
	private function scan_custom_table_column( $wpdb, $table_name, $column_name, $source_plugin ) {
		// Sanitize identifiers to prevent SQL injection.
		$safe_table  = esc_sql( $table_name );
		$safe_column = esc_sql( $column_name );

		// phpcs:ignore WordPress.DB.PreparedSQL.InterpolatedNotPrepared -- table/column names are escaped above.
		$results = $wpdb->get_results(
			"SELECT DISTINCT `{$safe_column}` AS ref_id FROM `{$safe_table}` WHERE `{$safe_column}` IS NOT NULL AND `{$safe_column}` > 0 LIMIT 1000",
			ARRAY_A
		);

		if ( empty( $results ) ) {
			return;
		}

		foreach ( $results as $row ) {
			$ref_id = (int) $row['ref_id'];
			if ( $ref_id <= 0 ) {
				continue;
			}

			// Verify the referenced ID is actually a post.
			$ref_post = get_post( $ref_id );
			if ( ! $ref_post ) {
				continue;
			}

			$entity_type = str_replace( $wpdb->prefix, '', $table_name );

			$this->add_relationship(
				'plugin:' . ( $source_plugin ? $source_plugin : 'unknown' ) . ':' . $entity_type . ':row',
				'post:' . $ref_id,
				'custom_table',
				$source_plugin,
				array(
					'table'  => $table_name,
					'column' => $column_name,
				)
			);
		}
	}

	/**
	 * Add a relationship to the collection, avoiding duplicates.
	 *
	 * @param string      $source_id     Stable source identifier.
	 * @param string      $target_id     Stable target identifier.
	 * @param string      $relation_type Relationship type.
	 * @param string|null $source_plugin Source plugin, if applicable.
	 * @param array       $metadata      Additional metadata.
	 */
	private function add_relationship( $source_id, $target_id, $relation_type, $source_plugin = null, $metadata = array() ) {
		$entry = array(
			'source_id'     => $source_id,
			'target_id'     => $target_id,
			'relation_type' => $relation_type,
			'source_plugin' => $source_plugin,
		);

		if ( ! empty( $metadata ) ) {
			$entry['metadata'] = $metadata;
		}

		// Deduplicate by source_id + target_id + relation_type.
		$key = $source_id . '|' . $target_id . '|' . $relation_type;
		if ( ! empty( $metadata['subtype'] ) ) {
			$key .= '|' . $metadata['subtype'];
		}
		if ( ! empty( $metadata['field_name'] ) ) {
			$key .= '|' . $metadata['field_name'];
		}

		$this->relationships[ $key ] = $entry;
	}

	/**
	 * Get collected scan data.
	 *
	 * Overrides base to return indexed array for relationships (not keyed).
	 *
	 * @return array
	 */
	public function get_data() {
		$data = $this->scan();
		// Convert keyed relationships map to indexed array.
		$data['relationships'] = array_values( $data['relationships'] );
		return $data;
	}
}
