<?php
/**
 * Site Options Scanner
 *
 * Exports critical wp_options entries for site configuration and plugin settings.
 *
 * @package Digital_Lobster_Exporter
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Class Digital_Lobster_Exporter_Site_Options_Scanner
 *
 * Collects critical WordPress options including:
 * - Plugin-specific options
 * - Theme settings
 * - Cron schedules and jobs
 * - Permalink and rewrite settings
 * - Core configuration options
 *
 * Delegates sensitive-data and temporary-key filtering to Security_Filters.
 */
class Digital_Lobster_Exporter_Site_Options_Scanner extends Digital_Lobster_Exporter_Scanner_Base {

	/**
	 * Active plugins list
	 *
	 * @var array
	 */
	private $active_plugins = array();

	/**
	 * Active theme slug
	 *
	 * @var string
	 */
	private $active_theme = '';

	/**
	 * Constructor.
	 *
	 * @param array $deps Optional. Associative array of dependencies.
	 */
	public function __construct( array $deps = array() ) {
		parent::__construct( $deps );
		$this->active_plugins = get_option( 'active_plugins', array() );
		$this->active_theme = get_stylesheet();
	}

	/**
	 * Scan and collect site options
	 *
	 * @return array Options data
	 */
	public function scan() {
		$options = array(
			'schema_version' => 1,
			'core'           => $this->get_core_options(),
			'permalink'      => $this->get_permalink_options(),
			'rewrite'        => $this->get_rewrite_rules(),
			'cron'           => $this->get_cron_jobs(),
			'plugins'        => $this->get_plugin_options(),
			'theme'          => $this->get_theme_options(),
		);

		return $options;
	}

	/**
	 * Get core WordPress options
	 *
	 * @return array Core options
	 */
	private function get_core_options() {
		$core_option_keys = array(
			'siteurl',
			'home',
			'blogname',
			'blogdescription',
			'users_can_register',
			'default_role',
			'timezone_string',
			'date_format',
			'time_format',
			'start_of_week',
			'WPLANG',
			'permalink_structure',
			'category_base',
			'tag_base',
			'show_on_front',
			'page_on_front',
			'page_for_posts',
			'posts_per_page',
			'posts_per_rss',
			'rss_use_excerpt',
			'blog_public',
			'default_comment_status',
			'default_ping_status',
			'comment_registration',
			'close_comments_for_old_posts',
			'close_comments_days_old',
			'thread_comments',
			'thread_comments_depth',
			'page_comments',
			'comments_per_page',
			'comment_order',
			'comment_moderation',
			'require_name_email',
			'comment_previously_approved',
			'show_avatars',
			'avatar_rating',
			'avatar_default',
			'thumbnail_size_w',
			'thumbnail_size_h',
			'thumbnail_crop',
			'medium_size_w',
			'medium_size_h',
			'large_size_w',
			'large_size_h',
			'uploads_use_yearmonth_folders',
			'upload_path',
			'upload_url_path',
		);

		$core_options = array();

		foreach ( $core_option_keys as $key ) {
			$value = get_option( $key );
			if ( false !== $value ) {
				$core_options[ $key ] = $this->sanitize_option_value( $key, $value );
			}
		}

		return $core_options;
	}

	/**
	 * Get permalink and rewrite options
	 *
	 * @return array Permalink options
	 */
	private function get_permalink_options() {
		return array(
			'permalink_structure' => get_option( 'permalink_structure' ),
			'category_base'       => get_option( 'category_base' ),
			'tag_base'            => get_option( 'tag_base' ),
			'use_verbose_page_rules' => (bool) get_option( 'use_verbose_page_rules' ),
		);
	}

	/**
	 * Get rewrite rules
	 *
	 * @return array Rewrite rules
	 */
	private function get_rewrite_rules() {
		global $wp_rewrite;

		if ( ! $wp_rewrite ) {
			return array();
		}

		$rules = get_option( 'rewrite_rules' );

		if ( ! is_array( $rules ) ) {
			return array();
		}

		// Limit to first 100 rules to avoid huge exports
		$rules = array_slice( $rules, 0, 100, true );

		return array(
			'rules' => $rules,
			'extra_rules_top' => $wp_rewrite->extra_rules_top ?? array(),
		);
	}

	/**
	 * Get cron jobs and schedules
	 *
	 * @return array Cron data
	 */
	private function get_cron_jobs() {
		$cron_array = _get_cron_array();

		if ( ! is_array( $cron_array ) ) {
			return array(
				'schedules' => array(),
				'jobs'      => array(),
			);
		}

		$schedules = wp_get_schedules();
		$jobs = array();

		foreach ( $cron_array as $timestamp => $cron ) {
			foreach ( $cron as $hook => $events ) {
				foreach ( $events as $key => $event ) {
					$jobs[] = array(
						'hook'      => $hook,
						'timestamp' => $timestamp,
						'schedule'  => $event['schedule'] ?? 'single',
						'interval'  => $event['interval'] ?? null,
						'args'      => $this->sanitize_cron_args( $event['args'] ?? array() ),
					);
				}
			}
		}

		return array(
			'schedules' => $schedules,
			'jobs'      => $jobs,
		);
	}

	/**
	 * Get plugin-specific options
	 *
	 * @return array Plugin options grouped by plugin
	 */
	private function get_plugin_options() {
		global $wpdb;

		$plugin_options = array();

		// Get all options from database
		$all_options = $wpdb->get_results(
			"SELECT option_name, option_value FROM {$wpdb->options} 
			WHERE autoload = 'yes' 
			ORDER BY option_name",
			ARRAY_A
		);

		if ( ! $all_options ) {
			return $plugin_options;
		}

		// Extract plugin slugs from active plugins
		$plugin_slugs = array();
		foreach ( $this->active_plugins as $plugin_file ) {
			$slug = dirname( $plugin_file );
			if ( '.' !== $slug ) {
				$plugin_slugs[] = $slug;
			} else {
				// Single file plugin
				$slug = basename( $plugin_file, '.php' );
				$plugin_slugs[] = $slug;
			}
		}

		// Group options by plugin
		foreach ( $all_options as $option ) {
			$option_name = $option['option_name'];

			// Skip if sensitive or temporary — delegate to Security_Filters
			if ( Digital_Lobster_Exporter_Security_Filters::is_sensitive_option( $option_name ) ||
			     Digital_Lobster_Exporter_Security_Filters::is_temporary_key( $option_name ) ) {
				continue;
			}

			// Try to match option to a plugin
			$matched_plugin = null;
			foreach ( $plugin_slugs as $slug ) {
				$slug_pattern = str_replace( '-', '[-_]?', preg_quote( $slug, '/' ) );
				if ( preg_match( "/^{$slug_pattern}/i", $option_name ) ) {
					$matched_plugin = $slug;
					break;
				}
			}

			if ( $matched_plugin ) {
				if ( ! isset( $plugin_options[ $matched_plugin ] ) ) {
					$plugin_options[ $matched_plugin ] = array();
				}

				$value = maybe_unserialize( $option['option_value'] );
				$plugin_options[ $matched_plugin ][ $option_name ] = $this->sanitize_option_value( $option_name, $value );
			}
		}

		return $plugin_options;
	}

	/**
	 * Get theme-specific options
	 *
	 * @return array Theme options
	 */
	private function get_theme_options() {
		$theme_options = array();

		// Get theme mods
		$theme_mods = get_theme_mods();
		if ( is_array( $theme_mods ) ) {
			$theme_options['theme_mods'] = $this->sanitize_option_value( 'theme_mods', $theme_mods );
		}

		// Get theme-specific options
		$theme_option_key = 'theme_mods_' . $this->active_theme;
		$theme_specific = get_option( $theme_option_key );
		if ( false !== $theme_specific ) {
			$theme_options[ $theme_option_key ] = $this->sanitize_option_value( $theme_option_key, $theme_specific );
		}

		// Get stylesheet and template options
		$theme_options['stylesheet'] = get_option( 'stylesheet' );
		$theme_options['template'] = get_option( 'template' );
		$theme_options['current_theme'] = get_option( 'current_theme' );

		return $theme_options;
	}

	/**
	 * Sanitize option value
	 *
	 * @param string $option_name Option name
	 * @param mixed  $value Option value
	 * @return mixed Sanitized value
	 */
	private function sanitize_option_value( $option_name, $value ) {
		// If value is an array or object, recursively sanitize
		if ( is_array( $value ) ) {
			return $this->sanitize_array( $value );
		}

		if ( is_object( $value ) ) {
			return $this->sanitize_array( (array) $value );
		}

		// Sanitize strings that might contain sensitive data
		if ( is_string( $value ) ) {
			// Check for email addresses
			if ( is_email( $value ) ) {
				$parts = explode( '@', $value );
				return '[email]@' . ( $parts[1] ?? 'example.com' );
			}

			// Check for URLs with credentials
			if ( preg_match( '/^https?:\/\/[^:]+:[^@]+@/', $value ) ) {
				return preg_replace( '/^(https?:\/\/)[^:]+:[^@]+@/', '$1[user]:[password]@', $value );
			}
		}

		return $value;
	}

	/**
	 * Sanitize array recursively
	 *
	 * @param array $array Array to sanitize
	 * @return array Sanitized array
	 */
	private function sanitize_array( $array ) {
		$sanitized = array();

		foreach ( $array as $key => $value ) {
			// Delegate sensitive-key check to Security_Filters
			if ( Digital_Lobster_Exporter_Security_Filters::is_sensitive_option( $key ) ) {
				$sanitized[ $key ] = '[REDACTED]';
				continue;
			}

			if ( is_array( $value ) ) {
				$sanitized[ $key ] = $this->sanitize_array( $value );
			} elseif ( is_object( $value ) ) {
				$sanitized[ $key ] = $this->sanitize_array( (array) $value );
			} else {
				$sanitized[ $key ] = $this->sanitize_option_value( $key, $value );
			}
		}

		return $sanitized;
	}

	/**
	 * Sanitize cron job arguments
	 *
	 * @param array $args Cron arguments
	 * @return array Sanitized arguments
	 */
	private function sanitize_cron_args( $args ) {
		if ( ! is_array( $args ) ) {
			return array();
		}

		return $this->sanitize_array( $args );
	}
}
