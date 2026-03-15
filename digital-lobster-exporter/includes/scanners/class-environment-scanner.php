<?php
/**
 * Environment Scanner Class
 *
 * Collects technical environment information including PHP version, extensions,
 * database version, server type, WordPress constants, and configuration settings.
 * This data helps understand the hosting environment and technical requirements.
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Environment Scanner Class
 */
class Digital_Lobster_Exporter_Environment_Scanner extends Digital_Lobster_Exporter_Scanner_Base {

	/**
	 * WordPress database object.
	 *
	 * @var wpdb
	 */
	private $wpdb;

	/**
	 * Constructor.
	 *
	 * @param array $deps Optional. Associative array of dependencies.
	 */
	public function __construct( array $deps = array() ) {
		parent::__construct( $deps );
		global $wpdb;
		$this->wpdb = $wpdb;
	}

	/**
	 * Run the environment scan.
	 *
	 * @return array Environment data.
	 */
	public function scan() {
		$environment = array(
			'schema_version' => 1,
			'php'            => $this->collect_php_info(),
			'database'       => $this->collect_database_info(),
			'server'         => $this->collect_server_info(),
			'wordpress'      => $this->collect_wordpress_info(),
			'filesystem'     => $this->collect_filesystem_info(),
			'security'       => $this->collect_security_info(),
			'features'       => $this->collect_features_info(),
			'site_health'    => $this->collect_site_health_info(),
		);

		return $environment;
	}

	/**
	 * Collect PHP information.
	 *
	 * @return array PHP information.
	 */
	private function collect_php_info() {
		$php_info = array(
			'version'    => phpversion(),
			'sapi'       => php_sapi_name(),
			'extensions' => get_loaded_extensions(),
			'limits'     => array(
				'memory_limit'       => ini_get( 'memory_limit' ),
				'max_execution_time' => ini_get( 'max_execution_time' ),
				'max_input_time'     => ini_get( 'max_input_time' ),
				'upload_max_filesize' => ini_get( 'upload_max_filesize' ),
				'post_max_size'      => ini_get( 'post_max_size' ),
				'max_input_vars'     => ini_get( 'max_input_vars' ),
			),
			'settings'   => array(
				'display_errors'     => ini_get( 'display_errors' ),
				'error_reporting'    => error_reporting(),
				'default_timezone'   => date_default_timezone_get(),
				'allow_url_fopen'    => ini_get( 'allow_url_fopen' ),
				'disable_functions'  => ini_get( 'disable_functions' ),
			),
		);

		// Add key extension versions if available.
		if ( extension_loaded( 'gd' ) ) {
			$gd_info = gd_info();
			$php_info['extension_versions']['gd'] = isset( $gd_info['GD Version'] ) ? $gd_info['GD Version'] : 'unknown';
		}

		if ( extension_loaded( 'curl' ) ) {
			$curl_version = curl_version();
			$php_info['extension_versions']['curl'] = $curl_version['version'];
		}

		if ( extension_loaded( 'imagick' ) ) {
			$imagick = new Imagick();
			$php_info['extension_versions']['imagick'] = $imagick->getVersion()['versionString'];
		}

		return $php_info;
	}

	/**
	 * Collect database information.
	 *
	 * @return array Database information.
	 */
	private function collect_database_info() {
		$db_info = array(
			'type'    => 'mysql', // WordPress only supports MySQL/MariaDB.
			'version' => $this->wpdb->db_version(),
		);

		// Get database character set and collation.
		$charset_collate = $this->wpdb->get_row( "SHOW VARIABLES LIKE 'character_set_database'" );
		if ( $charset_collate ) {
			$db_info['charset'] = $charset_collate->Value;
		}

		$collation = $this->wpdb->get_row( "SHOW VARIABLES LIKE 'collation_database'" );
		if ( $collation ) {
			$db_info['collation'] = $collation->Value;
		}

		// Check if it's MariaDB.
		if ( stripos( $db_info['version'], 'mariadb' ) !== false ) {
			$db_info['type'] = 'mariadb';
		}

		// Get max allowed packet size.
		$max_packet = $this->wpdb->get_row( "SHOW VARIABLES LIKE 'max_allowed_packet'" );
		if ( $max_packet ) {
			$db_info['max_allowed_packet'] = $max_packet->Value;
		}

		// Get table count.
		$tables = $this->wpdb->get_results( "SHOW TABLES", ARRAY_N );
		$db_info['table_count'] = count( $tables );

		return $db_info;
	}

	/**
	 * Collect server information.
	 *
	 * @return array Server information.
	 */
	private function collect_server_info() {
		$server_info = array(
			'software' => isset( $_SERVER['SERVER_SOFTWARE'] ) ? $_SERVER['SERVER_SOFTWARE'] : 'unknown',
			'os'       => PHP_OS,
			'hostname' => gethostname(),
		);

		// Parse server software to identify type and version.
		if ( isset( $_SERVER['SERVER_SOFTWARE'] ) ) {
			$software = $_SERVER['SERVER_SOFTWARE'];
			
			if ( stripos( $software, 'apache' ) !== false ) {
				$server_info['type'] = 'Apache';
				if ( preg_match( '/Apache\/([0-9.]+)/', $software, $matches ) ) {
					$server_info['version'] = $matches[1];
				}
			} elseif ( stripos( $software, 'nginx' ) !== false ) {
				$server_info['type'] = 'Nginx';
				if ( preg_match( '/nginx\/([0-9.]+)/', $software, $matches ) ) {
					$server_info['version'] = $matches[1];
				}
			} elseif ( stripos( $software, 'litespeed' ) !== false ) {
				$server_info['type'] = 'LiteSpeed';
				if ( preg_match( '/LiteSpeed\/([0-9.]+)/', $software, $matches ) ) {
					$server_info['version'] = $matches[1];
				}
			} else {
				$server_info['type'] = 'Other';
			}
		}

		return $server_info;
	}

	/**
	 * Collect WordPress information.
	 *
	 * @return array WordPress information.
	 */
	private function collect_wordpress_info() {
		global $wp_version;

		$wp_info = array(
			'version'   => $wp_version,
			'constants' => array(
				'WP_DEBUG'            => defined( 'WP_DEBUG' ) ? WP_DEBUG : false,
				'WP_DEBUG_LOG'        => defined( 'WP_DEBUG_LOG' ) ? WP_DEBUG_LOG : false,
				'WP_DEBUG_DISPLAY'    => defined( 'WP_DEBUG_DISPLAY' ) ? WP_DEBUG_DISPLAY : false,
				'SCRIPT_DEBUG'        => defined( 'SCRIPT_DEBUG' ) ? SCRIPT_DEBUG : false,
				'WP_CACHE'            => defined( 'WP_CACHE' ) ? WP_CACHE : false,
				'CONCATENATE_SCRIPTS' => defined( 'CONCATENATE_SCRIPTS' ) ? CONCATENATE_SCRIPTS : false,
				'COMPRESS_SCRIPTS'    => defined( 'COMPRESS_SCRIPTS' ) ? COMPRESS_SCRIPTS : false,
				'COMPRESS_CSS'        => defined( 'COMPRESS_CSS' ) ? COMPRESS_CSS : false,
				'WP_MEMORY_LIMIT'     => defined( 'WP_MEMORY_LIMIT' ) ? WP_MEMORY_LIMIT : 'default',
				'WP_MAX_MEMORY_LIMIT' => defined( 'WP_MAX_MEMORY_LIMIT' ) ? WP_MAX_MEMORY_LIMIT : 'default',
				'MULTISITE'           => defined( 'MULTISITE' ) ? MULTISITE : false,
				'SUBDOMAIN_INSTALL'   => defined( 'SUBDOMAIN_INSTALL' ) ? SUBDOMAIN_INSTALL : false,
				'DISABLE_WP_CRON'     => defined( 'DISABLE_WP_CRON' ) ? DISABLE_WP_CRON : false,
				'ALTERNATE_WP_CRON'   => defined( 'ALTERNATE_WP_CRON' ) ? ALTERNATE_WP_CRON : false,
				'WP_CRON_LOCK_TIMEOUT' => defined( 'WP_CRON_LOCK_TIMEOUT' ) ? WP_CRON_LOCK_TIMEOUT : 60,
				'EMPTY_TRASH_DAYS'    => defined( 'EMPTY_TRASH_DAYS' ) ? EMPTY_TRASH_DAYS : 30,
				'WP_POST_REVISIONS'   => defined( 'WP_POST_REVISIONS' ) ? WP_POST_REVISIONS : true,
				'AUTOSAVE_INTERVAL'   => defined( 'AUTOSAVE_INTERVAL' ) ? AUTOSAVE_INTERVAL : 60,
				'WP_ALLOW_REPAIR'     => defined( 'WP_ALLOW_REPAIR' ) ? WP_ALLOW_REPAIR : false,
			),
			'locale'    => get_locale(),
			'timezone'  => get_option( 'timezone_string' ),
			'gmt_offset' => get_option( 'gmt_offset' ),
		);

		return $wp_info;
	}

	/**
	 * Collect filesystem information.
	 *
	 * @return array Filesystem information.
	 */
	private function collect_filesystem_info() {
		$fs_info = array(
			'method' => get_filesystem_method(),
		);

		// Check permissions for key directories (without exposing full paths).
		$directories = array(
			'wp-content'        => WP_CONTENT_DIR,
			'uploads'           => wp_upload_dir()['basedir'],
			'plugins'           => WP_PLUGIN_DIR,
			'themes'            => get_theme_root(),
		);

		$fs_info['permissions'] = array();
		foreach ( $directories as $name => $path ) {
			if ( file_exists( $path ) ) {
				$fs_info['permissions'][ $name ] = array(
					'readable'   => is_readable( $path ),
					'writable'   => is_writable( $path ),
					'executable' => is_executable( $path ),
				);
			}
		}

		return $fs_info;
	}

	/**
	 * Collect security information.
	 *
	 * @return array Security information.
	 */
	private function collect_security_info() {
		$security_info = array(
			'https'     => is_ssl(),
			'site_url'  => get_site_url(),
			'home_url'  => get_home_url(),
		);

		// Check if URLs use HTTPS.
		$security_info['site_uses_https'] = ( strpos( get_site_url(), 'https://' ) === 0 );
		$security_info['home_uses_https'] = ( strpos( get_home_url(), 'https://' ) === 0 );

		// Check for security headers (if accessible).
		if ( function_exists( 'apache_response_headers' ) ) {
			$headers = apache_response_headers();
			$security_info['security_headers'] = array(
				'x_frame_options'         => isset( $headers['X-Frame-Options'] ) ? $headers['X-Frame-Options'] : 'not set',
				'x_content_type_options'  => isset( $headers['X-Content-Type-Options'] ) ? $headers['X-Content-Type-Options'] : 'not set',
				'strict_transport_security' => isset( $headers['Strict-Transport-Security'] ) ? $headers['Strict-Transport-Security'] : 'not set',
			);
		}

		return $security_info;
	}

	/**
	 * Collect WordPress features information.
	 *
	 * @return array Features information.
	 */
	private function collect_features_info() {
		// Ensure is_plugin_active() is available.
		if ( ! function_exists( 'is_plugin_active' ) ) {
			require_once ABSPATH . 'wp-admin/includes/plugin.php';
		}

		$features = array(
			'rest_api_enabled' => true, // REST API is always enabled in modern WordPress.
			'xmlrpc_enabled'   => apply_filters( 'xmlrpc_enabled', true ),
			'cron_enabled'     => ! ( defined( 'DISABLE_WP_CRON' ) && DISABLE_WP_CRON ),
			'block_editor'     => function_exists( 'use_block_editor_for_post' ),
			'gutenberg_active' => function_exists( 'gutenberg_init' ),
		);

		// Check for common caching plugins.
		$caching_plugins = array(
			'W3 Total Cache'    => 'w3-total-cache/w3-total-cache.php',
			'WP Super Cache'    => 'wp-super-cache/wp-super-cache.php',
			'WP Rocket'         => 'wp-rocket/wp-rocket.php',
			'LiteSpeed Cache'   => 'litespeed-cache/litespeed-cache.php',
			'Autoptimize'       => 'autoptimize/autoptimize.php',
		);

		$features['caching_plugins'] = array();
		foreach ( $caching_plugins as $name => $plugin_file ) {
			if ( is_plugin_active( $plugin_file ) ) {
				$features['caching_plugins'][] = $name;
			}
		}

		// Check for CDN configuration.
		$features['cdn_detected'] = $this->detect_cdn();

		return $features;
	}

	/**
	 * Detect CDN configuration.
	 *
	 * @return array CDN detection results.
	 */
	private function detect_cdn() {
		// Ensure is_plugin_active() is available.
		if ( ! function_exists( 'is_plugin_active' ) ) {
			require_once ABSPATH . 'wp-admin/includes/plugin.php';
		}

		$cdn_info = array(
			'detected' => false,
			'type'     => null,
		);

		// Check for common CDN constants.
		if ( defined( 'CLOUDFLARE_PLUGIN_DIR' ) || is_plugin_active( 'cloudflare/cloudflare.php' ) ) {
			$cdn_info['detected'] = true;
			$cdn_info['type']     = 'Cloudflare';
		}

		// Check for CDN Enabler plugin.
		if ( is_plugin_active( 'cdn-enabler/cdn-enabler.php' ) ) {
			$cdn_info['detected'] = true;
			$cdn_info['type']     = 'CDN Enabler';
		}

		// Check for WP Offload Media.
		if ( is_plugin_active( 'amazon-s3-and-cloudfront/wordpress-s3.php' ) ) {
			$cdn_info['detected'] = true;
			$cdn_info['type']     = 'WP Offload Media (S3)';
		}

		// Check upload URL for CDN.
		$upload_dir = wp_upload_dir();
		$site_url   = get_site_url();
		if ( strpos( $upload_dir['baseurl'], $site_url ) === false ) {
			$cdn_info['detected']   = true;
			$cdn_info['type']       = 'Custom CDN';
			$cdn_info['upload_url'] = $upload_dir['baseurl'];
		}

		return $cdn_info;
	}

	/**
	 * Collect site health information.
	 *
	 * @return array Site health information.
	 */
	private function collect_site_health_info() {
		$health_info = array(
			'available' => false,
		);

		// Skip Site Health during AJAX to avoid admin dependencies
		// WP_Site_Health requires admin context and may call get_current_screen()
		if ( wp_doing_ajax() ) {
			$health_info['note'] = 'Site Health skipped during AJAX request to avoid admin dependencies';
			return $health_info;
		}

		// Check if Site Health is available (WordPress 5.2+).
		if ( ! class_exists( 'WP_Site_Health' ) ) {
			if ( file_exists( ABSPATH . 'wp-admin/includes/class-wp-site-health.php' ) ) {
				require_once ABSPATH . 'wp-admin/includes/class-wp-site-health.php';
			}
		}

		if ( class_exists( 'WP_Site_Health' ) ) {
			try {
				$health_info['available'] = true;

				// Get site health status.
				$site_health = WP_Site_Health::get_instance();
				
				// Get test results (without running all tests to avoid performance issues).
				$health_info['status'] = array(
					'description' => 'Site health data available',
				);

				// Get critical info (if method exists).
				if ( method_exists( $site_health, 'get_tests' ) ) {
					$info = $site_health->get_tests();
					if ( ! empty( $info ) ) {
						$health_info['tests_available'] = count( $info['direct'] ) + count( $info['async'] );
					}
				}

				// Get debug info (sanitized) - only if method exists (WordPress 5.2+).
				if ( method_exists( $site_health, 'debug_data' ) ) {
					$debug_info = $site_health->debug_data();
					if ( ! empty( $debug_info ) ) {
						$health_info['debug_sections'] = array_keys( $debug_info );
					}
				} else {
					// Fallback for older WordPress versions
					$health_info['note'] = 'debug_data() method not available in this WordPress version';
				}
			} catch ( Exception $e ) {
				// If anything fails, just mark as unavailable
				$health_info['available'] = false;
				$health_info['error'] = $e->getMessage();
			}
		}

		return $health_info;
	}

}
