<?php
/**
 * SEO Full Scanner Class
 *
 * Produces a normalized seo_full.json artifact containing per-page
 * SEO data from Yoast, Rank Math, or AIOSEO: canonical URL, robots,
 * noindex, nofollow, title template/resolved, meta description,
 * OG metadata, Twitter metadata, schema type hints, breadcrumb config,
 * sitemap rules, and redirect ownership.
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * SEO Full Scanner Class
 */
class Digital_Lobster_Exporter_Seo_Full_Scanner extends Digital_Lobster_Exporter_Scanner_Base {

	/**
	 * Collected SEO page entries.
	 *
	 * @var array
	 */
	private $pages = array();

	/**
	 * Detected SEO plugin.
	 *
	 * @var string|null
	 */
	private $seo_plugin = null;

	/**
	 * Scan per-page SEO data.
	 *
	 * @return array SEO data matching SeoFullArtifact schema.
	 */
	public function scan() {
		$this->pages = array();
		$this->seo_plugin = $this->detect_seo_plugin();

		if ( null === $this->seo_plugin ) {
			return array(
				'schema_version' => '1.0.0',
				'pages'          => array(),
			);
		}

		$post_types = get_post_types( array( 'public' => true ), 'names' );

		foreach ( $post_types as $post_type ) {
			if ( 'attachment' === $post_type ) {
				continue;
			}

			$posts = get_posts( array(
				'post_type'      => $post_type,
				'posts_per_page' => -1,
				'post_status'    => array( 'publish', 'draft' ),
			) );

			foreach ( $posts as $post ) {
				$this->scan_post_seo( $post );
			}
		}

		return array(
			'schema_version' => '1.0.0',
			'pages'          => $this->pages,
		);
	}

	/**
	 * Detect which SEO plugin is active.
	 *
	 * @return string|null Plugin identifier or null.
	 */
	private function detect_seo_plugin() {
		if ( defined( 'WPSEO_VERSION' ) ) {
			return 'yoast';
		}
		if ( class_exists( 'RankMath' ) ) {
			return 'rank_math';
		}
		if ( defined( 'AIOSEO_VERSION' ) ) {
			return 'aioseo';
		}
		return null;
	}

	/**
	 * Scan SEO data for a single post.
	 *
	 * @param WP_Post $post The post object.
	 */
	private function scan_post_seo( $post ) {
		$canonical_url = wp_make_link_relative( get_permalink( $post->ID ) );
		if ( empty( $canonical_url ) ) {
			$canonical_url = '/' . $post->post_name;
		}

		switch ( $this->seo_plugin ) {
			case 'yoast':
				$entry = $this->scan_yoast( $post, $canonical_url );
				break;
			case 'rank_math':
				$entry = $this->scan_rank_math( $post, $canonical_url );
				break;
			case 'aioseo':
				$entry = $this->scan_aioseo( $post, $canonical_url );
				break;
			default:
				return;
		}

		if ( ! empty( $entry ) ) {
			$this->pages[] = $entry;
		}
	}

	/**
	 * Scan Yoast SEO data for a post.
	 *
	 * @param WP_Post $post          The post object.
	 * @param string  $canonical_url Canonical URL.
	 * @return array SEO page entry.
	 */
	private function scan_yoast( $post, $canonical_url ) {
		$meta_robots_noindex  = get_post_meta( $post->ID, '_yoast_wpseo_meta-robots-noindex', true );
		$meta_robots_nofollow = get_post_meta( $post->ID, '_yoast_wpseo_meta-robots-nofollow', true );
		$title                = get_post_meta( $post->ID, '_yoast_wpseo_title', true );
		$metadesc             = get_post_meta( $post->ID, '_yoast_wpseo_metadesc', true );
		$opengraph_title      = get_post_meta( $post->ID, '_yoast_wpseo_opengraph-title', true );
		$opengraph_desc       = get_post_meta( $post->ID, '_yoast_wpseo_opengraph-description', true );
		$opengraph_image      = get_post_meta( $post->ID, '_yoast_wpseo_opengraph-image', true );
		$twitter_title        = get_post_meta( $post->ID, '_yoast_wpseo_twitter-title', true );
		$twitter_desc         = get_post_meta( $post->ID, '_yoast_wpseo_twitter-description', true );
		$twitter_image        = get_post_meta( $post->ID, '_yoast_wpseo_twitter-image', true );
		$schema_type          = get_post_meta( $post->ID, '_yoast_wpseo_schema_page_type', true );
		$schema_article_type  = get_post_meta( $post->ID, '_yoast_wpseo_schema_article_type', true );
		$canonical            = get_post_meta( $post->ID, '_yoast_wpseo_canonical', true );

		$og_metadata = array();
		if ( $opengraph_title ) {
			$og_metadata['title'] = $opengraph_title;
		}
		if ( $opengraph_desc ) {
			$og_metadata['description'] = $opengraph_desc;
		}
		if ( $opengraph_image ) {
			$og_metadata['image'] = $opengraph_image;
		}

		$twitter_metadata = array();
		if ( $twitter_title ) {
			$twitter_metadata['title'] = $twitter_title;
		}
		if ( $twitter_desc ) {
			$twitter_metadata['description'] = $twitter_desc;
		}
		if ( $twitter_image ) {
			$twitter_metadata['image'] = $twitter_image;
		}

		$schema_type_hints = array();
		if ( $schema_type ) {
			$schema_type_hints[] = $schema_type;
		}
		if ( $schema_article_type ) {
			$schema_type_hints[] = $schema_article_type;
		}

		// Breadcrumb config from global Yoast settings.
		$titles_options  = get_option( 'wpseo_titles', array() );
		$breadcrumb_config = null;
		if ( ! empty( $titles_options['breadcrumbs-enable'] ) ) {
			$breadcrumb_config = array(
				'enabled'   => true,
				'separator' => isset( $titles_options['breadcrumbs-sep'] ) ? $titles_options['breadcrumbs-sep'] : '»',
			);
		}

		// Sitemap inclusion.
		$sitemap_inclusion = ( '1' !== $meta_robots_noindex );

		// Redirect ownership.
		$redirect_ownership = null;
		if ( class_exists( 'WPSEO_Redirect_Manager' ) ) {
			$redirect_ownership = array( 'managed_by' => 'yoast_premium' );
		}

		// Robots string.
		$robots_parts = array();
		if ( '1' === $meta_robots_noindex ) {
			$robots_parts[] = 'noindex';
		}
		if ( '1' === $meta_robots_nofollow ) {
			$robots_parts[] = 'nofollow';
		}
		$robots = ! empty( $robots_parts ) ? implode( ', ', $robots_parts ) : null;

		return array(
			'canonical_url'      => $canonical_url,
			'source_plugin'      => 'yoast',
			'robots'             => $robots,
			'noindex'            => ( '1' === $meta_robots_noindex ),
			'nofollow'           => ( '1' === $meta_robots_nofollow ),
			'title_template'     => $title ? $title : null,
			'resolved_title'     => $title ? $title : get_the_title( $post->ID ),
			'meta_description'   => $metadesc ? $metadesc : null,
			'og_metadata'        => $og_metadata,
			'twitter_metadata'   => $twitter_metadata,
			'schema_type_hints'  => $schema_type_hints,
			'breadcrumb_config'  => $breadcrumb_config,
			'sitemap_inclusion'  => $sitemap_inclusion,
			'redirect_ownership' => $redirect_ownership,
		);
	}

	/**
	 * Scan Rank Math SEO data for a post.
	 *
	 * @param WP_Post $post          The post object.
	 * @param string  $canonical_url Canonical URL.
	 * @return array SEO page entry.
	 */
	private function scan_rank_math( $post, $canonical_url ) {
		$robots       = get_post_meta( $post->ID, 'rank_math_robots', true );
		$title        = get_post_meta( $post->ID, 'rank_math_title', true );
		$description  = get_post_meta( $post->ID, 'rank_math_description', true );
		$canonical    = get_post_meta( $post->ID, 'rank_math_canonical_url', true );
		$og_title     = get_post_meta( $post->ID, 'rank_math_facebook_title', true );
		$og_desc      = get_post_meta( $post->ID, 'rank_math_facebook_description', true );
		$og_image     = get_post_meta( $post->ID, 'rank_math_facebook_image', true );
		$tw_title     = get_post_meta( $post->ID, 'rank_math_twitter_title', true );
		$tw_desc      = get_post_meta( $post->ID, 'rank_math_twitter_description', true );
		$schema_type  = get_post_meta( $post->ID, 'rank_math_rich_snippet', true );

		$robots_array = is_array( $robots ) ? $robots : array();
		$noindex      = in_array( 'noindex', $robots_array, true );
		$nofollow     = in_array( 'nofollow', $robots_array, true );

		$og_metadata = array();
		if ( $og_title ) {
			$og_metadata['title'] = $og_title;
		}
		if ( $og_desc ) {
			$og_metadata['description'] = $og_desc;
		}
		if ( $og_image ) {
			$og_metadata['image'] = $og_image;
		}

		$twitter_metadata = array();
		if ( $tw_title ) {
			$twitter_metadata['title'] = $tw_title;
		}
		if ( $tw_desc ) {
			$twitter_metadata['description'] = $tw_desc;
		}

		$schema_type_hints = array();
		if ( $schema_type ) {
			$schema_type_hints[] = $schema_type;
		}

		// Breadcrumb config.
		$general = get_option( 'rank-math-options-general', array() );
		$breadcrumb_config = null;
		if ( ! empty( $general['breadcrumbs'] ) ) {
			$breadcrumb_config = array(
				'enabled'   => true,
				'separator' => isset( $general['breadcrumbs_separator'] ) ? $general['breadcrumbs_separator'] : '-',
			);
		}

		return array(
			'canonical_url'      => $canonical_url,
			'source_plugin'      => 'rank_math',
			'robots'             => ! empty( $robots_array ) ? implode( ', ', $robots_array ) : null,
			'noindex'            => $noindex,
			'nofollow'           => $nofollow,
			'title_template'     => $title ? $title : null,
			'resolved_title'     => $title ? $title : get_the_title( $post->ID ),
			'meta_description'   => $description ? $description : null,
			'og_metadata'        => $og_metadata,
			'twitter_metadata'   => $twitter_metadata,
			'schema_type_hints'  => $schema_type_hints,
			'breadcrumb_config'  => $breadcrumb_config,
			'sitemap_inclusion'  => ! $noindex,
			'redirect_ownership' => null,
		);
	}

	/**
	 * Scan All in One SEO data for a post.
	 *
	 * @param WP_Post $post          The post object.
	 * @param string  $canonical_url Canonical URL.
	 * @return array SEO page entry.
	 */
	private function scan_aioseo( $post, $canonical_url ) {
		global $wpdb;

		$entry = array(
			'canonical_url'      => $canonical_url,
			'source_plugin'      => 'aioseo',
			'robots'             => null,
			'noindex'            => false,
			'nofollow'           => false,
			'title_template'     => null,
			'resolved_title'     => get_the_title( $post->ID ),
			'meta_description'   => null,
			'og_metadata'        => array(),
			'twitter_metadata'   => array(),
			'schema_type_hints'  => array(),
			'breadcrumb_config'  => null,
			'sitemap_inclusion'  => true,
			'redirect_ownership' => null,
		);

		// AIOSEO stores data in its own table.
		$table_name = $wpdb->prefix . 'aioseo_posts';

		// phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery, WordPress.DB.DirectDatabaseQuery.NoCaching
		$aioseo_data = $wpdb->get_row(
			$wpdb->prepare(
				"SELECT * FROM `{$table_name}` WHERE post_id = %d LIMIT 1",
				$post->ID
			),
			ARRAY_A
		);

		if ( empty( $aioseo_data ) ) {
			return $entry;
		}

		$entry['title_template']   = isset( $aioseo_data['title'] ) ? $aioseo_data['title'] : null;
		$entry['resolved_title']   = isset( $aioseo_data['title'] ) && $aioseo_data['title'] ? $aioseo_data['title'] : get_the_title( $post->ID );
		$entry['meta_description'] = isset( $aioseo_data['description'] ) ? $aioseo_data['description'] : null;

		// Robots.
		$robots_parts = array();
		if ( ! empty( $aioseo_data['robots_noindex'] ) ) {
			$entry['noindex'] = true;
			$robots_parts[]   = 'noindex';
		}
		if ( ! empty( $aioseo_data['robots_nofollow'] ) ) {
			$entry['nofollow'] = true;
			$robots_parts[]    = 'nofollow';
		}
		$entry['robots'] = ! empty( $robots_parts ) ? implode( ', ', $robots_parts ) : null;

		// OG metadata.
		$og = array();
		if ( ! empty( $aioseo_data['og_title'] ) ) {
			$og['title'] = $aioseo_data['og_title'];
		}
		if ( ! empty( $aioseo_data['og_description'] ) ) {
			$og['description'] = $aioseo_data['og_description'];
		}
		$entry['og_metadata'] = $og;

		// Twitter metadata.
		$tw = array();
		if ( ! empty( $aioseo_data['twitter_title'] ) ) {
			$tw['title'] = $aioseo_data['twitter_title'];
		}
		if ( ! empty( $aioseo_data['twitter_description'] ) ) {
			$tw['description'] = $aioseo_data['twitter_description'];
		}
		$entry['twitter_metadata'] = $tw;

		// Schema type.
		if ( ! empty( $aioseo_data['schema_type'] ) ) {
			$entry['schema_type_hints'][] = $aioseo_data['schema_type'];
		}

		$entry['sitemap_inclusion'] = ! $entry['noindex'];

		return $entry;
	}
}
