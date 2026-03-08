<?php
/**
 * Search Config Scanner Class
 *
 * Produces a normalized search_config.json artifact containing
 * search and filtering configuration: searchable entity types,
 * ranking hints, facets/filters, archive/query behavior, and
 * search result template hints.
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Search Config Scanner Class
 */
class Digital_Lobster_Exporter_Search_Config_Scanner extends Digital_Lobster_Exporter_Scanner_Base {

	/**
	 * Scan search and filtering configuration.
	 *
	 * @return array Search config data matching SearchConfigArtifact schema.
	 */
	public function scan() {
		return array(
			'schema_version'       => '1.0.0',
			'searchable_types'     => $this->detect_searchable_types(),
			'ranking_hints'        => $this->detect_ranking_hints(),
			'facets'               => $this->detect_facets(),
			'archive_behavior'     => $this->detect_archive_behavior(),
			'search_template_hints' => $this->detect_search_template_hints(),
		);
	}

	/**
	 * Detect which post types are searchable.
	 *
	 * @return array List of searchable post type slugs.
	 */
	private function detect_searchable_types() {
		$searchable = array();

		$post_types = get_post_types( array( 'public' => true ), 'objects' );

		foreach ( $post_types as $post_type ) {
			if ( $post_type->exclude_from_search ) {
				continue;
			}
			$searchable[] = $post_type->name;
		}

		return $searchable;
	}

	/**
	 * Detect ranking hints from search plugins or WordPress defaults.
	 *
	 * @return array Ranking hint descriptors.
	 */
	private function detect_ranking_hints() {
		$hints = array();

		// Check for SearchWP.
		if ( class_exists( 'SearchWP' ) ) {
			$hints[] = array(
				'source'  => 'searchwp',
				'type'    => 'weighted_search',
				'details' => 'SearchWP provides custom search engine with weighted fields',
			);
		}

		// Check for Relevanssi.
		if ( function_exists( 'relevanssi_search' ) ) {
			$hints[] = array(
				'source'  => 'relevanssi',
				'type'    => 'fuzzy_search',
				'details' => 'Relevanssi provides fuzzy matching and custom ranking',
			);
		}

		// Check for ElasticPress.
		if ( class_exists( 'ElasticPress\\Elasticsearch' ) ) {
			$hints[] = array(
				'source'  => 'elasticpress',
				'type'    => 'elasticsearch',
				'details' => 'ElasticPress provides Elasticsearch-powered search',
			);
		}

		// Default WordPress search.
		if ( empty( $hints ) ) {
			$hints[] = array(
				'source'  => 'wordpress',
				'type'    => 'default',
				'details' => 'Standard WordPress LIKE-based search',
			);
		}

		return $hints;
	}

	/**
	 * Detect facets and filters from plugins or taxonomies.
	 *
	 * @return array Facet descriptors.
	 */
	private function detect_facets() {
		$facets = array();

		// Check for FacetWP.
		if ( class_exists( 'FacetWP' ) ) {
			$facetwp_settings = get_option( 'facetwp_settings', '' );
			if ( ! empty( $facetwp_settings ) ) {
				$settings = json_decode( $facetwp_settings, true );
				if ( isset( $settings['facets'] ) && is_array( $settings['facets'] ) ) {
					foreach ( $settings['facets'] as $facet ) {
						$facets[] = array(
							'source_plugin' => 'facetwp',
							'facet_name'    => isset( $facet['name'] ) ? $facet['name'] : '',
							'facet_type'    => isset( $facet['type'] ) ? $facet['type'] : 'unknown',
							'data_source'   => isset( $facet['source'] ) ? $facet['source'] : '',
						);
					}
				}
			}
		}

		// Detect taxonomy-based filtering (common pattern).
		$taxonomies = get_taxonomies( array( 'public' => true ), 'objects' );
		foreach ( $taxonomies as $taxonomy ) {
			if ( in_array( $taxonomy->name, array( 'post_tag', 'category', 'post_format', 'nav_menu' ), true ) ) {
				continue;
			}

			$term_count = wp_count_terms( array( 'taxonomy' => $taxonomy->name ) );
			if ( is_wp_error( $term_count ) || (int) $term_count < 2 ) {
				continue;
			}

			$facets[] = array(
				'source_plugin' => 'core',
				'facet_name'    => $taxonomy->name,
				'facet_type'    => 'taxonomy',
				'data_source'   => 'taxonomy:' . $taxonomy->name,
			);
		}

		return $facets;
	}

	/**
	 * Detect archive and query behavior.
	 *
	 * @return array Archive behavior configuration.
	 */
	private function detect_archive_behavior() {
		$behavior = array(
			'posts_per_page'    => (int) get_option( 'posts_per_page', 10 ),
			'has_date_archives' => true,
			'has_author_archives' => true,
		);

		// Check for custom archive pages.
		$post_types = get_post_types( array( 'public' => true, 'has_archive' => true ), 'objects' );
		$archives   = array();

		foreach ( $post_types as $pt ) {
			$archives[] = array(
				'post_type'   => $pt->name,
				'archive_slug' => is_string( $pt->has_archive ) ? $pt->has_archive : $pt->rewrite['slug'],
			);
		}

		$behavior['custom_archives'] = $archives;

		// Check for category/tag archives.
		$behavior['category_base'] = get_option( 'category_base', '' );
		$behavior['tag_base']      = get_option( 'tag_base', '' );

		return $behavior;
	}

	/**
	 * Detect search result template hints.
	 *
	 * @return array Template hint configuration.
	 */
	private function detect_search_template_hints() {
		$hints = array();

		// Check if a custom search.php template exists.
		$search_template = locate_template( 'search.php' );
		if ( ! empty( $search_template ) ) {
			$hints['has_custom_search_template'] = true;
			$hints['template_file']              = basename( $search_template );
		} else {
			$hints['has_custom_search_template'] = false;
		}

		// Check for search form template.
		$searchform = locate_template( 'searchform.php' );
		$hints['has_custom_search_form'] = ! empty( $searchform );

		return $hints;
	}
}
