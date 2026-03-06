<?php
/**
 * Settings Scanner
 *
 * Exports core site settings and configurations.
 *
 * @package Digital_Lobster_Exporter
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Class Digital_Lobster_Exporter_Settings_Scanner
 *
 * Collects WordPress site settings including:
 * - Core site settings (title, tagline, email, timezone)
 * - Language settings and locale
 * - Reading settings (posts per page, RSS)
 * - Discussion settings
 * - Media settings (image sizes, upload paths)
 */
class Digital_Lobster_Exporter_Settings_Scanner extends Digital_Lobster_Exporter_Scanner_Base {

	/**
	 * Constructor.
	 *
	 * @param array $deps Optional. Associative array of dependencies.
	 */
	public function __construct( array $deps = array() ) {
		parent::__construct( $deps );
	}

	/**
	 * Scan and collect site settings
	 *
	 * @return array Settings data
	 */
	public function scan() {
		$settings = array(
			'schema_version' => 1,
			'core'           => $this->get_core_settings(),
			'language'       => $this->get_language_settings(),
			'reading'        => $this->get_reading_settings(),
			'discussion'     => $this->get_discussion_settings(),
			'media'          => $this->get_media_settings(),
		);

		return $settings;
	}

	/**
	 * Get core site settings
	 *
	 * @return array Core settings
	 */
	private function get_core_settings() {
		return array(
			'site_title'       => get_bloginfo( 'name' ),
			'tagline'          => get_bloginfo( 'description' ),
			'admin_email'      => $this->sanitize_email( get_option( 'admin_email' ) ),
			'timezone_string'  => get_option( 'timezone_string' ),
			'gmt_offset'       => get_option( 'gmt_offset' ),
			'date_format'      => get_option( 'date_format' ),
			'time_format'      => get_option( 'time_format' ),
			'start_of_week'    => get_option( 'start_of_week' ),
			'site_url'         => get_site_url(),
			'home_url'         => get_home_url(),
		);
	}

	/**
	 * Get language settings
	 *
	 * @return array Language settings
	 */
	private function get_language_settings() {
		return array(
			'locale'           => get_locale(),
			'language'         => get_bloginfo( 'language' ),
			'text_direction'   => is_rtl() ? 'rtl' : 'ltr',
			'wplang'           => get_option( 'WPLANG' ),
		);
	}

	/**
	 * Get reading settings
	 *
	 * @return array Reading settings
	 */
	private function get_reading_settings() {
		$show_on_front = get_option( 'show_on_front' );
		$page_on_front = get_option( 'page_on_front' );
		$page_for_posts = get_option( 'page_for_posts' );

		$settings = array(
			'show_on_front'        => $show_on_front,
			'posts_per_page'       => (int) get_option( 'posts_per_page' ),
			'posts_per_rss'        => (int) get_option( 'posts_per_rss' ),
			'rss_use_excerpt'      => (bool) get_option( 'rss_use_excerpt' ),
			'blog_public'          => (int) get_option( 'blog_public' ),
		);

		// Add page details if using static front page
		if ( 'page' === $show_on_front ) {
			$settings['page_on_front'] = array(
				'id'    => (int) $page_on_front,
				'title' => $page_on_front ? get_the_title( $page_on_front ) : null,
				'slug'  => $page_on_front ? get_post_field( 'post_name', $page_on_front ) : null,
			);
			$settings['page_for_posts'] = array(
				'id'    => (int) $page_for_posts,
				'title' => $page_for_posts ? get_the_title( $page_for_posts ) : null,
				'slug'  => $page_for_posts ? get_post_field( 'post_name', $page_for_posts ) : null,
			);
		}

		return $settings;
	}

	/**
	 * Get discussion settings
	 *
	 * @return array Discussion settings
	 */
	private function get_discussion_settings() {
		return array(
			'default_comment_status'     => get_option( 'default_comment_status' ),
			'default_ping_status'        => get_option( 'default_ping_status' ),
			'require_name_email'         => (bool) get_option( 'require_name_email' ),
			'comment_registration'       => (bool) get_option( 'comment_registration' ),
			'close_comments_for_old_posts' => (bool) get_option( 'close_comments_for_old_posts' ),
			'close_comments_days_old'    => (int) get_option( 'close_comments_days_old' ),
			'thread_comments'            => (bool) get_option( 'thread_comments' ),
			'thread_comments_depth'      => (int) get_option( 'thread_comments_depth' ),
			'page_comments'              => (bool) get_option( 'page_comments' ),
			'comments_per_page'          => (int) get_option( 'comments_per_page' ),
			'default_comments_page'      => get_option( 'default_comments_page' ),
			'comment_order'              => get_option( 'comment_order' ),
			'comments_notify'            => (bool) get_option( 'comments_notify' ),
			'moderation_notify'          => (bool) get_option( 'moderation_notify' ),
			'comment_moderation'         => (bool) get_option( 'comment_moderation' ),
			'comment_previously_approved' => (bool) get_option( 'comment_previously_approved' ),
			'comment_max_links'          => (int) get_option( 'comment_max_links' ),
			'show_avatars'               => (bool) get_option( 'show_avatars' ),
			'avatar_rating'              => get_option( 'avatar_rating' ),
			'avatar_default'             => get_option( 'avatar_default' ),
		);
	}

	/**
	 * Get media settings
	 *
	 * @return array Media settings
	 */
	private function get_media_settings() {
		$upload_dir = wp_upload_dir();

		return array(
			'thumbnail_size_w'        => (int) get_option( 'thumbnail_size_w' ),
			'thumbnail_size_h'        => (int) get_option( 'thumbnail_size_h' ),
			'thumbnail_crop'          => (bool) get_option( 'thumbnail_crop' ),
			'medium_size_w'           => (int) get_option( 'medium_size_w' ),
			'medium_size_h'           => (int) get_option( 'medium_size_h' ),
			'medium_large_size_w'     => (int) get_option( 'medium_large_size_w' ),
			'medium_large_size_h'     => (int) get_option( 'medium_large_size_h' ),
			'large_size_w'            => (int) get_option( 'large_size_w' ),
			'large_size_h'            => (int) get_option( 'large_size_h' ),
			'uploads_use_yearmonth_folders' => (bool) get_option( 'uploads_use_yearmonth_folders' ),
			'upload_path'             => $this->sanitize_path( get_option( 'upload_path' ) ),
			'upload_url_path'         => get_option( 'upload_url_path' ),
			'upload_dir_info'         => array(
				'basedir'  => $this->sanitize_path( $upload_dir['basedir'] ),
				'baseurl'  => $upload_dir['baseurl'],
				'subdir'   => $upload_dir['subdir'],
			),
			'image_default_align'     => get_option( 'image_default_align' ),
			'image_default_link_type' => get_option( 'image_default_link_type' ),
			'image_default_size'      => get_option( 'image_default_size' ),
		);
	}

	/**
	 * Sanitize email address for privacy
	 *
	 * @param string $email Email address
	 * @return string Sanitized email
	 */
	private function sanitize_email( $email ) {
		if ( empty( $email ) ) {
			return '';
		}

		// Replace email with placeholder for privacy
		$parts = explode( '@', $email );
		if ( count( $parts ) === 2 ) {
			return '[admin-email]@' . $parts[1];
		}

		return '[admin-email]';
	}

	/**
	 * Sanitize file system paths
	 *
	 * Removes absolute server paths for security
	 *
	 * @param string $path File system path
	 * @return string Sanitized path
	 */
	private function sanitize_path( $path ) {
		if ( empty( $path ) ) {
			return '';
		}

		// Remove ABSPATH to avoid exposing server paths
		$path = str_replace( ABSPATH, '', $path );

		// Remove common server path patterns
		$path = preg_replace( '#^/home/[^/]+/#', '', $path );
		$path = preg_replace( '#^/var/www/#', '', $path );
		$path = preg_replace( '#^/usr/share/#', '', $path );

		return $path;
	}
}
