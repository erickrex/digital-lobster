<?php
/**
 * Site Scanner Class
 *
 * Collects basic site information including URL, WordPress version,
 * multisite status, permalink structure, and registered post types/taxonomies.
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Site Scanner Class
 */
class Digital_Lobster_Exporter_Site_Scanner {

	/**
	 * Scan and collect site information.
	 *
	 * @return array Site information data.
	 */
	public function scan() {
		return array(
			'site'         => $this->collect_site_info(),
			'post_types'   => $this->collect_post_types(),
			'taxonomies'   => $this->collect_taxonomies(),
			'content_counts' => $this->collect_content_counts(),
		);
	}

	/**
	 * Collect basic site information.
	 *
	 * @return array Site information.
	 */
	private function collect_site_info() {
		global $wp_version;

		return array(
			'url'                => get_site_url(),
			'home_url'           => get_home_url(),
			'wp_version'         => $wp_version,
			'is_multisite'       => is_multisite(),
			'permalink_structure' => get_option( 'permalink_structure', '' ),
			'site_title'         => get_bloginfo( 'name' ),
			'site_description'   => get_bloginfo( 'description' ),
			'language'           => get_bloginfo( 'language' ),
			'charset'            => get_bloginfo( 'charset' ),
		);
	}

	/**
	 * Collect all registered post types.
	 *
	 * @return array Post types information.
	 */
	private function collect_post_types() {
		$post_types = get_post_types( array(), 'objects' );
		$result = array();

		foreach ( $post_types as $post_type ) {
			// Skip built-in types that are not content-related
			if ( in_array( $post_type->name, array( 'revision', 'nav_menu_item', 'custom_css', 'customize_changeset', 'oembed_cache', 'user_request', 'wp_block' ), true ) ) {
				continue;
			}

			$result[ $post_type->name ] = array(
				'label'        => $post_type->label,
				'labels'       => (array) $post_type->labels,
				'description'  => $post_type->description,
				'public'       => $post_type->public,
				'hierarchical' => $post_type->hierarchical,
				'has_archive'  => $post_type->has_archive,
				'rewrite'      => $post_type->rewrite,
				'menu_icon'    => $post_type->menu_icon,
				'supports'     => get_all_post_type_supports( $post_type->name ),
				'taxonomies'   => get_object_taxonomies( $post_type->name ),
				'rest_enabled' => $post_type->show_in_rest,
				'rest_base'    => $post_type->rest_base,
			);
		}

		return $result;
	}

	/**
	 * Collect all registered taxonomies.
	 *
	 * @return array Taxonomies information.
	 */
	private function collect_taxonomies() {
		$taxonomies = get_taxonomies( array(), 'objects' );
		$result = array();

		foreach ( $taxonomies as $taxonomy ) {
			// Skip built-in types that are not content-related
			if ( in_array( $taxonomy->name, array( 'nav_menu', 'link_category', 'post_format' ), true ) ) {
				continue;
			}

			$result[ $taxonomy->name ] = array(
				'label'        => $taxonomy->label,
				'labels'       => (array) $taxonomy->labels,
				'description'  => $taxonomy->description,
				'public'       => $taxonomy->public,
				'hierarchical' => $taxonomy->hierarchical,
				'rewrite'      => $taxonomy->rewrite,
				'object_types' => $taxonomy->object_type,
				'rest_enabled' => $taxonomy->show_in_rest,
				'rest_base'    => $taxonomy->rest_base,
			);
		}

		return $result;
	}

	/**
	 * Collect content counts for each post type.
	 *
	 * @return array Content counts by post type.
	 */
	private function collect_content_counts() {
		$post_types = get_post_types( array( 'public' => true ), 'names' );
		$counts = array();

		foreach ( $post_types as $post_type ) {
			// Skip built-in types that are not content-related
			if ( in_array( $post_type, array( 'attachment' ), true ) ) {
				continue;
			}

			$count_obj = wp_count_posts( $post_type );
			
			// Sum up published and private posts
			$total = 0;
			if ( isset( $count_obj->publish ) ) {
				$total += $count_obj->publish;
			}
			if ( isset( $count_obj->private ) ) {
				$total += $count_obj->private;
			}

			$counts[ $post_type ] = $total;
		}

		return $counts;
	}
}
