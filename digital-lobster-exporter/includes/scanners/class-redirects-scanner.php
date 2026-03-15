<?php
/**
 * Redirects Scanner Class
 *
 * Analyzes exported content for redirect candidates, detects redirect plugins,
 * exports redirect rules, and captures rewrite rules.
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Redirects Scanner Class
 */
class Digital_Lobster_Exporter_Redirects_Scanner extends Digital_Lobster_Exporter_Scanner_Base {

	/**
	 * Scan results.
	 *
	 * @var array
	 */
	private $scan_results = array();

	/**
	 * Constructor.
	 *
	 * @param array $deps Optional. Associative array of dependencies.
	 */
	public function __construct( array $deps = array() ) {
		parent::__construct( $deps );
	}

	/**
	 * Scan and collect redirect and rewrite rule information.
	 *
	 * @return array Redirect and rewrite rule data.
	 */
	public function scan() {
		$content_data = isset( $this->context['content'] ) ? $this->context['content'] : array();

		$this->scan_results = array(
			'redirect_candidates' => $this->generate_redirect_candidates( $content_data ),
			'redirect_plugins'    => $this->detect_redirect_plugins(),
			'plugin_redirects'    => $this->export_plugin_redirects(),
			'rewrite_rules'       => $this->export_rewrite_rules(),
			'permalink_structure' => get_option( 'permalink_structure', '' ),
		);

		return $this->scan_results;
	}

	/**
	 * Generate redirect candidates from exported content.
	 *
	 * @param array $content_data Previously exported content data.
	 * @return array Redirect candidates.
	 */
	private function generate_redirect_candidates( $content_data ) {
		$candidates = array();

		if ( empty( $content_data ) ) {
			return $candidates;
		}

		// Process each content type
		foreach ( $content_data as $post_type => $items ) {
			if ( ! is_array( $items ) ) {
				continue;
			}

			foreach ( $items as $item ) {
				if ( ! isset( $item['id'] ) ) {
					continue;
				}

				$post_id = $item['id'];
				$post = get_post( $post_id );

				if ( ! $post ) {
					continue;
				}

				$permalink = get_permalink( $post_id );
				$legacy_permalink = $this->get_legacy_permalink( $post );

				$candidate = array(
					'post_id'          => $post_id,
					'post_type'        => $post->post_type,
					'slug'             => $post->post_name,
					'current_url'      => $permalink,
					'legacy_permalink' => $legacy_permalink,
					'status'           => $post->post_status,
					'notes'            => '',
				);

				// Check for custom permalink plugins
				$custom_permalink = $this->get_custom_permalink( $post_id );
				if ( $custom_permalink && $custom_permalink !== $permalink ) {
					$candidate['custom_permalink'] = $custom_permalink;
					$candidate['notes'] = 'Has custom permalink';
				}

				$candidates[] = $candidate;
			}
		}

		return $candidates;
	}

	/**
	 * Get legacy permalink for a post.
	 *
	 * @param WP_Post $post Post object.
	 * @return string Legacy permalink.
	 */
	private function get_legacy_permalink( $post ) {
		// Get the post's date
		$date = strtotime( $post->post_date );

		// Build legacy permalink based on common structures
		$year = date( 'Y', $date );
		$month = date( 'm', $date );
		$day = date( 'd', $date );

		$home_url = trailingslashit( get_home_url() );

		// Common permalink structures
		$structures = array(
			'/%year%/%monthnum%/%day%/%postname%/' => $home_url . $year . '/' . $month . '/' . $day . '/' . $post->post_name . '/',
			'/%year%/%monthnum%/%postname%/'       => $home_url . $year . '/' . $month . '/' . $post->post_name . '/',
			'/%postname%/'                         => $home_url . $post->post_name . '/',
			'/archives/%post_id%'                  => $home_url . 'archives/' . $post->ID,
		);

		$current_structure = get_option( 'permalink_structure', '' );

		if ( isset( $structures[ $current_structure ] ) ) {
			return $structures[ $current_structure ];
		}

		// Default to current permalink
		return get_permalink( $post->ID );
	}

	/**
	 * Get custom permalink if set by a plugin.
	 *
	 * @param int $post_id Post ID.
	 * @return string|null Custom permalink or null.
	 */
	private function get_custom_permalink( $post_id ) {
		// Check for Custom Permalinks plugin
		$custom_permalink = get_post_meta( $post_id, 'custom_permalink', true );
		if ( $custom_permalink ) {
			return trailingslashit( get_home_url() ) . ltrim( $custom_permalink, '/' );
		}

		// Check for Permalink Manager plugin
		$permalink_manager = get_post_meta( $post_id, 'custom_uri', true );
		if ( $permalink_manager ) {
			return trailingslashit( get_home_url() ) . ltrim( $permalink_manager, '/' );
		}

		return null;
	}

	/**
	 * Detect common redirect plugins.
	 *
	 * @return array Detected redirect plugins.
	 */
	private function detect_redirect_plugins() {
		// Ensure is_plugin_active() is available.
		if ( ! function_exists( 'is_plugin_active' ) ) {
			require_once ABSPATH . 'wp-admin/includes/plugin.php';
		}

		$plugins = array();

		// Check for Redirection plugin
		if ( is_plugin_active( 'redirection/redirection.php' ) || class_exists( 'Red_Item' ) ) {
			$plugins[] = array(
				'name'   => 'Redirection',
				'slug'   => 'redirection',
				'active' => true,
			);
		}

		// Check for Simple 301 Redirects
		if ( is_plugin_active( 'simple-301-redirects/simple-301-redirects.php' ) || function_exists( 'simple_301_redirects_add_settings_page' ) ) {
			$plugins[] = array(
				'name'   => 'Simple 301 Redirects',
				'slug'   => 'simple-301-redirects',
				'active' => true,
			);
		}

		// Check for Safe Redirect Manager
		if ( is_plugin_active( 'safe-redirect-manager/safe-redirect-manager.php' ) || class_exists( 'SRM_Redirect' ) ) {
			$plugins[] = array(
				'name'   => 'Safe Redirect Manager',
				'slug'   => 'safe-redirect-manager',
				'active' => true,
			);
		}

		// Check for Yoast SEO Premium (has redirect manager)
		if ( is_plugin_active( 'wordpress-seo-premium/wp-seo-premium.php' ) || class_exists( 'WPSEO_Redirect_Manager' ) ) {
			$plugins[] = array(
				'name'   => 'Yoast SEO Premium',
				'slug'   => 'wordpress-seo-premium',
				'active' => true,
				'feature' => 'Redirect Manager',
			);
		}

		// Check for Rank Math (has redirect manager)
		if ( is_plugin_active( 'seo-by-rank-math/rank-math.php' ) || class_exists( 'RankMath' ) ) {
			$plugins[] = array(
				'name'   => 'Rank Math',
				'slug'   => 'seo-by-rank-math',
				'active' => true,
				'feature' => 'Redirect Manager',
			);
		}

		return $plugins;
	}

	/**
	 * Export redirect rules from detected plugins.
	 *
	 * @return array Redirect rules from plugins.
	 */
	private function export_plugin_redirects() {
		$redirects = array();

		// Export from Redirection plugin
		if ( class_exists( 'Red_Item' ) ) {
			$redirects['redirection'] = $this->export_redirection_plugin();
		}

		// Export from Simple 301 Redirects
		$simple_redirects = get_option( '301_redirects', array() );
		if ( ! empty( $simple_redirects ) ) {
			$redirects['simple_301_redirects'] = $this->export_simple_301_redirects( $simple_redirects );
		}

		// Export from Safe Redirect Manager
		if ( post_type_exists( 'redirect_rule' ) ) {
			$redirects['safe_redirect_manager'] = $this->export_safe_redirect_manager();
		}

		// Export from Yoast SEO Premium
		if ( class_exists( 'WPSEO_Redirect_Option' ) ) {
			$redirects['yoast_seo_premium'] = $this->export_yoast_redirects();
		}

		// Export from Rank Math
		if ( class_exists( 'RankMath' ) && function_exists( 'rank_math' ) ) {
			$redirects['rank_math'] = $this->export_rank_math_redirects();
		}

		return $redirects;
	}

	/**
	 * Export redirects from Redirection plugin.
	 *
	 * @return array Redirect rules.
	 */
	private function export_redirection_plugin() {
		global $wpdb;

		$redirects = array();
		$table_name = $wpdb->prefix . 'redirection_items';

		// Check if table exists
		$safe_table = esc_sql( $table_name );
		if ( $wpdb->get_var( $wpdb->prepare( 'SHOW TABLES LIKE %s', $table_name ) ) !== $table_name ) {
			return $redirects;
		}

		// phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery, WordPress.DB.DirectDatabaseQuery.NoCaching, WordPress.DB.PreparedSQL.InterpolatedNotPrepared
		$results = $wpdb->get_results(
			"SELECT url, action_data, action_code, regex, status FROM `{$safe_table}` WHERE status = 'enabled' ORDER BY id",
			ARRAY_A
		);

		foreach ( $results as $row ) {
			$redirects[] = array(
				'source_url'  => $row['url'],
				'target_url'  => $row['action_data'],
				'status_code' => $row['action_code'],
				'regex'       => (bool) $row['regex'],
				'status'      => $row['status'],
			);
		}

		return $redirects;
	}

	/**
	 * Export redirects from Simple 301 Redirects.
	 *
	 * @param array $simple_redirects Redirect data from options.
	 * @return array Redirect rules.
	 */
	private function export_simple_301_redirects( $simple_redirects ) {
		$redirects = array();

		foreach ( $simple_redirects as $source => $target ) {
			$redirects[] = array(
				'source_url'  => $source,
				'target_url'  => $target,
				'status_code' => 301,
				'regex'       => false,
			);
		}

		return $redirects;
	}

	/**
	 * Export redirects from Safe Redirect Manager.
	 *
	 * @return array Redirect rules.
	 */
	private function export_safe_redirect_manager() {
		$redirects = array();

		$args = array(
			'post_type'      => 'redirect_rule',
			'posts_per_page' => -1,
			'post_status'    => 'publish',
		);

		$redirect_posts = get_posts( $args );

		foreach ( $redirect_posts as $post ) {
			$source = get_post_meta( $post->ID, '_redirect_rule_from', true );
			$target = get_post_meta( $post->ID, '_redirect_rule_to', true );
			$status_code = get_post_meta( $post->ID, '_redirect_rule_status_code', true );
			$enable_regex = get_post_meta( $post->ID, '_redirect_rule_from_regex', true );

			$redirects[] = array(
				'source_url'  => $source,
				'target_url'  => $target,
				'status_code' => $status_code ? intval( $status_code ) : 301,
				'regex'       => (bool) $enable_regex,
			);
		}

		return $redirects;
	}

	/**
	 * Export redirects from Yoast SEO Premium.
	 *
	 * @return array Redirect rules.
	 */
	private function export_yoast_redirects() {
		$redirects = array();

		if ( ! class_exists( 'WPSEO_Redirect_Option' ) ) {
			return $redirects;
		}

		$redirect_option = get_option( 'wpseo-premium-redirects', array() );

		if ( ! empty( $redirect_option ) && is_array( $redirect_option ) ) {
			foreach ( $redirect_option as $source => $redirect_data ) {
				if ( is_array( $redirect_data ) ) {
					$redirects[] = array(
						'source_url'  => $source,
						'target_url'  => isset( $redirect_data['url'] ) ? $redirect_data['url'] : '',
						'status_code' => isset( $redirect_data['type'] ) ? intval( $redirect_data['type'] ) : 301,
						'regex'       => isset( $redirect_data['regex'] ) ? (bool) $redirect_data['regex'] : false,
					);
				}
			}
		}

		return $redirects;
	}

	/**
	 * Export redirects from Rank Math.
	 *
	 * @return array Redirect rules.
	 */
	private function export_rank_math_redirects() {
		global $wpdb;

		$redirects = array();
		$table_name = $wpdb->prefix . 'rank_math_redirections';

		// Check if table exists
		$safe_table = esc_sql( $table_name );
		if ( $wpdb->get_var( $wpdb->prepare( 'SHOW TABLES LIKE %s', $table_name ) ) !== $table_name ) {
			return $redirects;
		}

		// phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery, WordPress.DB.DirectDatabaseQuery.NoCaching, WordPress.DB.PreparedSQL.InterpolatedNotPrepared
		$results = $wpdb->get_results(
			"SELECT url_from, url_to, header_code, status FROM `{$safe_table}` WHERE status = 'active' ORDER BY id",
			ARRAY_A
		);

		foreach ( $results as $row ) {
			$redirects[] = array(
				'source_url'  => $row['url_from'],
				'target_url'  => $row['url_to'],
				'status_code' => intval( $row['header_code'] ),
				'status'      => $row['status'],
			);
		}

		return $redirects;
	}

	/**
	 * Export WordPress rewrite rules.
	 *
	 * @return array Rewrite rules.
	 */
	private function export_rewrite_rules() {
		global $wp_rewrite;

		$rewrite_rules = array(
			'permalink_structure' => get_option( 'permalink_structure', '' ),
			'category_base'       => get_option( 'category_base', '' ),
			'tag_base'            => get_option( 'tag_base', '' ),
			'rules'               => array(),
			'extra_rules'         => array(),
		);

		// Get all rewrite rules
		$rules = get_option( 'rewrite_rules', array() );

		if ( ! empty( $rules ) && is_array( $rules ) ) {
			foreach ( $rules as $pattern => $replacement ) {
				$rewrite_rules['rules'][] = array(
					'pattern'     => $pattern,
					'replacement' => $replacement,
				);
			}
		}

		// Get extra permastructs
		if ( ! empty( $wp_rewrite->extra_permastructs ) ) {
			foreach ( $wp_rewrite->extra_permastructs as $name => $struct ) {
				$rewrite_rules['extra_rules'][ $name ] = array(
					'struct'       => isset( $struct['struct'] ) ? $struct['struct'] : '',
					'with_front'   => isset( $struct['with_front'] ) ? $struct['with_front'] : true,
					'ep_mask'      => isset( $struct['ep_mask'] ) ? $struct['ep_mask'] : EP_NONE,
					'paged'        => isset( $struct['paged'] ) ? $struct['paged'] : true,
					'feed'         => isset( $struct['feed'] ) ? $struct['feed'] : true,
					'forcomments'  => isset( $struct['forcomments'] ) ? $struct['forcomments'] : false,
					'walk_dirs'    => isset( $struct['walk_dirs'] ) ? $struct['walk_dirs'] : true,
					'endpoints'    => isset( $struct['endpoints'] ) ? $struct['endpoints'] : true,
				);
			}
		}

		return $rewrite_rules;
	}

	/**
	 * Export redirect candidates to CSV format.
	 *
	 * @param array $candidates Redirect candidates.
	 * @return string CSV content.
	 */
	public function generate_csv( $candidates ) {
		if ( empty( $candidates ) ) {
			return '';
		}

		$csv = "source_url,target_url,status_code,post_type,notes\n";

		foreach ( $candidates as $candidate ) {
			$source_url = isset( $candidate['legacy_permalink'] ) ? $candidate['legacy_permalink'] : '';
			$target_url = isset( $candidate['current_url'] ) ? $candidate['current_url'] : '';
			$post_type = isset( $candidate['post_type'] ) ? $candidate['post_type'] : '';
			$notes = isset( $candidate['notes'] ) ? $candidate['notes'] : '';

			// Only add if URLs are different
			if ( $source_url !== $target_url ) {
				$csv .= sprintf(
					'"%s","%s",301,"%s","%s"' . "\n",
					$this->escape_csv( $source_url ),
					$this->escape_csv( $target_url ),
					$this->escape_csv( $post_type ),
					$this->escape_csv( $notes )
				);
			}
		}

		return $csv;
	}

	/**
	 * Escape CSV field.
	 *
	 * @param string $field Field value.
	 * @return string Escaped field.
	 */
	private function escape_csv( $field ) {
		return str_replace( '"', '""', $field );
	}
}
