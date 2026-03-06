<?php
/**
 * Exporter Class
 *
 * Handles JSON generation and file export for all collected scan data.
 * Generates structured JSON files with proper formatting and validation.
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Exporter Class
 */
class Digital_Lobster_Exporter_Exporter {

	/**
	 * Export directory path.
	 *
	 * @var string
	 */
	private $export_dir = '';

	/**
	 * Scan results data.
	 *
	 * @var array
	 */
	private $results = array();

	/**
	 * Error log.
	 *
	 * @var array
	 */
	private $errors = array();

	/**
	 * Warning log.
	 *
	 * @var array
	 */
	private $warnings = array();

	/**
	 * Schema version for JSON exports.
	 *
	 * @var int
	 */
	const SCHEMA_VERSION = 1;

	/**
	 * Maximum JSON file size before chunking (in bytes).
	 *
	 * @var int
	 */
	const MAX_JSON_SIZE = 10485760; // 10MB

	/**
	 * Constructor.
	 *
	 * @param string $export_dir Export directory path.
	 * @param array  $results Scan results data.
	 */
	public function __construct( $export_dir, $results = array() ) {
		$this->export_dir = trailingslashit( $export_dir );
		$this->results = $results;
	}

	/**
	 * Export all data to JSON files.
	 *
	 * @return array Export results with success status and any errors.
	 */
	public function export_all() {
		try {
			// Ensure export directory exists
			if ( ! file_exists( $this->export_dir ) ) {
				wp_mkdir_p( $this->export_dir );
			}

			/**
			 * Fires before any export files are written.
			 *
			 * Allows developers to perform actions before the export process begins.
			 *
			 * @since 1.0.0
			 *
			 * @param string $export_dir The export directory path.
			 * @param array  $results The scan results to be exported.
			 * @param Digital_Lobster_Exporter_Exporter $exporter The exporter instance.
			 */
			do_action( 'digital_lobster_before_export', $this->export_dir, $this->results, $this );

			// Export site blueprint (main manifest file)
			$this->export_site_blueprint();

			// Export content files (already handled by ContentScanner, but validate)
			$this->validate_content_exports();

			// Export settings files
			$this->export_settings_files();

			// Export taxonomies (already handled by TaxonomyScanner, but validate)
			$this->validate_taxonomy_export();

			// Export media map (already handled by MediaScanner, but validate)
			$this->validate_media_export();

			// Export error log if there are any errors or warnings
			$this->export_error_log();

			/**
			 * Fires after all export files have been written.
			 *
			 * Allows developers to perform actions after the export process completes.
			 *
			 * @since 1.0.0
			 *
			 * @param string $export_dir The export directory path.
			 * @param array  $errors Error log entries.
			 * @param array  $warnings Warning log entries.
			 * @param Digital_Lobster_Exporter_Exporter $exporter The exporter instance.
			 */
			do_action( 'digital_lobster_after_export', $this->export_dir, $this->errors, $this->warnings, $this );

			return array(
				'success'  => true,
				'errors'   => $this->errors,
				'warnings' => $this->warnings,
			);

		} catch ( Exception $e ) {
			$this->log_error( 'exporter', $e->getMessage(), 'critical' );
			
			return array(
				'success' => false,
				'error'   => $e->getMessage(),
				'errors'  => $this->errors,
			);
		}
	}

	/**
	 * Export site blueprint JSON file.
	 *
	 * This is the main manifest file that provides an overview of the entire site.
	 */
	private function export_site_blueprint() {
		$blueprint = array(
			'schema_version' => self::SCHEMA_VERSION,
			'exported_at'    => current_time( 'mysql', true ),
			'site'           => $this->get_site_info(),
			'theme'          => $this->get_theme_info(),
			'plugins'        => $this->get_plugins_list(),
			'plugin_features' => $this->get_plugin_features(),
			'content'        => $this->get_content_summary(),
			'taxonomies'     => $this->get_taxonomies_summary(),
			'media'          => $this->get_media_summary(),
			'environment'    => $this->get_environment_summary(),
		);

		/**
		 * Filters the site blueprint data before it is exported.
		 *
		 * Allows developers to modify or enhance the site blueprint data
		 * before it is written to the JSON file.
		 *
		 * @since 1.0.0
		 *
		 * @param array $blueprint The site blueprint data.
		 * @param Digital_Lobster_Exporter_Exporter $exporter The exporter instance.
		 */
		$blueprint = apply_filters( 'digital_lobster_export_site_blueprint', $blueprint, $this );

		$this->write_json_file( 'site_blueprint.json', $blueprint );
	}

	/**
	 * Get site information for blueprint.
	 *
	 * @return array Site information.
	 */
	private function get_site_info() {
		if ( ! isset( $this->results['site'] ) || ! isset( $this->results['site']['site'] ) ) {
			return array();
		}

		return $this->results['site']['site'];
	}

	/**
	 * Get theme information for blueprint.
	 *
	 * @return array Theme information.
	 */
	private function get_theme_info() {
		if ( ! isset( $this->results['theme'] ) || ! isset( $this->results['theme']['theme'] ) ) {
			return array();
		}

		$theme_data = $this->results['theme']['theme'];
		
		return array(
			'name'         => isset( $theme_data['name'] ) ? $theme_data['name'] : '',
			'version'      => isset( $theme_data['version'] ) ? $theme_data['version'] : '',
			'block_theme'  => isset( $theme_data['is_block_theme'] ) ? $theme_data['is_block_theme'] : false,
			'parent_theme' => isset( $theme_data['parent_theme'] ) ? $theme_data['parent_theme'] : null,
		);
	}

	/**
	 * Get plugins list for blueprint.
	 *
	 * @return array Plugins list.
	 */
	private function get_plugins_list() {
		if ( ! isset( $this->results['plugins'] ) || ! isset( $this->results['plugins']['plugins'] ) ) {
			return array();
		}

		$plugins = $this->results['plugins']['plugins'];
		$plugins_list = array();

		foreach ( $plugins as $plugin_file => $plugin_data ) {
			$plugins_list[] = array(
				'file'    => $plugin_file,
				'name'    => isset( $plugin_data['Name'] ) ? $plugin_data['Name'] : '',
				'version' => isset( $plugin_data['Version'] ) ? $plugin_data['Version'] : '',
				'active'  => isset( $plugin_data['active'] ) ? $plugin_data['active'] : false,
			);
		}

		return $plugins_list;
	}

	/**
	 * Get plugin features for blueprint.
	 *
	 * @return array Plugin features.
	 */
	private function get_plugin_features() {
		if ( ! isset( $this->results['plugins'] ) || ! isset( $this->results['plugins']['plugin_features'] ) ) {
			return array();
		}

		return $this->results['plugins']['plugin_features'];
	}

	/**
	 * Get content summary for blueprint.
	 *
	 * @return array Content summary.
	 */
	private function get_content_summary() {
		$summary = array(
			'post_types'       => array(),
			'block_usage_top'  => array(),
			'total_exported'   => 0,
		);

		// Get post type counts
		if ( isset( $this->results['site'] ) && isset( $this->results['site']['content_counts'] ) ) {
			$summary['post_types'] = $this->results['site']['content_counts'];
		}

		// Get block usage statistics
		if ( isset( $this->results['content'] ) && isset( $this->results['content']['block_usage'] ) ) {
			$block_usage = $this->results['content']['block_usage'];
			
			// Sort by count and get top blocks
			arsort( $block_usage );
			$summary['block_usage_top'] = array_slice( $block_usage, 0, 20, true );
		}

		// Get total exported content count
		if ( isset( $this->results['content'] ) && isset( $this->results['content']['exported_items'] ) ) {
			$summary['total_exported'] = count( $this->results['content']['exported_items'] );
		}

		return $summary;
	}

	/**
	 * Get taxonomies summary for blueprint.
	 *
	 * @return array Taxonomies summary.
	 */
	private function get_taxonomies_summary() {
		if ( ! isset( $this->results['site'] ) || ! isset( $this->results['site']['taxonomies'] ) ) {
			return array();
		}

		$taxonomies = $this->results['site']['taxonomies'];
		$summary = array();

		foreach ( $taxonomies as $taxonomy_name => $taxonomy_data ) {
			$summary[ $taxonomy_name ] = array(
				'label'        => isset( $taxonomy_data['label'] ) ? $taxonomy_data['label'] : '',
				'hierarchical' => isset( $taxonomy_data['hierarchical'] ) ? $taxonomy_data['hierarchical'] : false,
			);
		}

		return $summary;
	}

	/**
	 * Get media summary for blueprint.
	 *
	 * @return array Media summary.
	 */
	private function get_media_summary() {
		$summary = array(
			'total_files' => 0,
			'total_size'  => 0,
		);

		if ( isset( $this->results['media'] ) && isset( $this->results['media']['media_files'] ) ) {
			$summary['total_files'] = count( $this->results['media']['media_files'] );
			
			// Calculate total size if available
			foreach ( $this->results['media']['media_files'] as $file ) {
				if ( isset( $file['size'] ) ) {
					$summary['total_size'] += $file['size'];
				}
			}
		}

		return $summary;
	}

	/**
	 * Get environment summary for blueprint.
	 *
	 * @return array Environment summary.
	 */
	private function get_environment_summary() {
		if ( ! isset( $this->results['environment'] ) ) {
			return array();
		}

		$env = $this->results['environment'];
		
		return array(
			'php_version'   => isset( $env['php']['version'] ) ? $env['php']['version'] : '',
			'mysql_version' => isset( $env['database']['version'] ) ? $env['database']['version'] : '',
			'wp_version'    => isset( $env['wordpress']['version'] ) ? $env['wordpress']['version'] : '',
		);
	}

	/**
	 * Validate content exports.
	 *
	 * Content files are created by ContentScanner, but we validate they exist.
	 */
	private function validate_content_exports() {
		$content_dir = $this->export_dir . 'content/';
		
		if ( ! file_exists( $content_dir ) ) {
			$this->log_error( 'content', 'Content directory not found', 'warning' );
			return;
		}

		// Check if content was exported
		if ( isset( $this->results['content'] ) && isset( $this->results['content']['exported_items'] ) ) {
			$exported_count = count( $this->results['content']['exported_items'] );
			
			if ( $exported_count === 0 ) {
				$this->log_error( 'content', 'No content items were exported', 'warning' );
			}
		}
	}

	/**
	 * Export settings files.
	 *
	 * Exports various settings JSON files from scanner results.
	 */
	private function export_settings_files() {
		// Export site settings
		if ( isset( $this->results['settings'] ) ) {
			$this->write_json_file( 'site_settings.json', $this->results['settings'] );
		}

		// Export menus
		if ( isset( $this->results['menus'] ) ) {
			$this->write_json_file( 'menus.json', $this->results['menus'] );
		}

		// Export widgets
		if ( isset( $this->results['widgets'] ) ) {
			$this->write_json_file( 'widgets.json', $this->results['widgets'] );
		}

		// Export user roles
		if ( isset( $this->results['user_roles'] ) ) {
			$this->write_json_file( 'user_roles.json', $this->results['user_roles'] );
		}

		// Export site options
		if ( isset( $this->results['site_options'] ) ) {
			$this->write_json_file( 'site_options.json', $this->results['site_options'] );
		}

		// Export ACF field groups
		if ( isset( $this->results['acf'] ) ) {
			$this->write_json_file( 'acf_field_groups.json', $this->results['acf'] );
		}

		// Export shortcodes inventory
		if ( isset( $this->results['shortcodes'] ) ) {
			$this->write_json_file( 'shortcodes_inventory.json', $this->results['shortcodes'] );
		}

		// Export forms configuration
		if ( isset( $this->results['forms'] ) ) {
			$this->write_json_file( 'forms_config.json', $this->results['forms'] );
		}

		// Export hooks registry
		if ( isset( $this->results['hooks'] ) ) {
			$this->write_json_file( 'hooks_registry.json', $this->results['hooks'] );
		}

		// Export page templates
		if ( isset( $this->results['page_templates'] ) ) {
			$this->write_json_file( 'page_templates.json', $this->results['page_templates'] );
		}

		// Export block patterns
		if ( isset( $this->results['block_patterns'] ) ) {
			$this->write_json_file( 'block_patterns.json', $this->results['block_patterns'] );
		}

		// Export REST API endpoints
		if ( isset( $this->results['rest_api'] ) ) {
			$this->write_json_file( 'rest_api_endpoints.json', $this->results['rest_api'] );
		}

		// Export redirects (CSV file is created by RedirectsScanner)
		// Just validate it exists
		$redirects_file = $this->export_dir . 'redirects_candidates.csv';
		if ( ! file_exists( $redirects_file ) && isset( $this->results['redirects'] ) ) {
			$this->log_error( 'redirects', 'Redirects CSV file not found', 'warning' );
		}

		// Export database schema (SQL file is created by DatabaseScanner)
		// Just validate it exists
		$schema_file = $this->export_dir . 'schema_mysql.sql';
		if ( ! file_exists( $schema_file ) && isset( $this->results['database'] ) ) {
			$this->log_error( 'database', 'Database schema SQL file not found', 'warning' );
		}

		// Export translations
		if ( isset( $this->results['translations'] ) ) {
			$this->write_json_file( 'translations.json', $this->results['translations'] );
		}

		// Export environment
		if ( isset( $this->results['environment'] ) ) {
			$this->write_json_file( 'site_environment.json', $this->results['environment'] );
		}

		// Export plugins fingerprint
		if ( isset( $this->results['plugins'] ) && isset( $this->results['plugins']['plugin_behaviors'] ) ) {
			$this->write_json_file( 'plugins_fingerprint.json', $this->results['plugins']['plugin_behaviors'] );
		}

		// Export block usage statistics
		if ( isset( $this->results['content'] ) && isset( $this->results['content']['block_usage'] ) ) {
			$this->write_json_file( 'blocks_usage.json', array(
				'schema_version' => self::SCHEMA_VERSION,
				'block_usage'    => $this->results['content']['block_usage'],
			) );
		}
	}

	/**
	 * Validate taxonomy export.
	 *
	 * Taxonomy file is created by TaxonomyScanner, but we validate it exists.
	 */
	private function validate_taxonomy_export() {
		$taxonomy_file = $this->export_dir . 'taxonomies.json';
		
		if ( ! file_exists( $taxonomy_file ) && isset( $this->results['taxonomies'] ) ) {
			$this->log_error( 'taxonomies', 'Taxonomies JSON file not found', 'warning' );
		}
	}

	/**
	 * Validate media export.
	 *
	 * Media files and map are created by MediaScanner, but we validate they exist.
	 */
	private function validate_media_export() {
		$media_map_file = $this->export_dir . 'media_map.json';
		
		if ( ! file_exists( $media_map_file ) && isset( $this->results['media'] ) ) {
			$this->log_error( 'media', 'Media map JSON file not found', 'warning' );
		}
	}

	/**
	 * Export error log.
	 *
	 * Creates error_log.json if there are any errors or warnings.
	 */
	private function export_error_log() {
		// Get errors from scanner results if available
		$all_errors = $this->errors;
		$all_warnings = $this->warnings;

		// Add scanner errors if available
		if ( isset( $this->results['errors'] ) && is_array( $this->results['errors'] ) ) {
			$all_errors = array_merge( $all_errors, $this->results['errors'] );
		}

		if ( isset( $this->results['warnings'] ) && is_array( $this->results['warnings'] ) ) {
			$all_warnings = array_merge( $all_warnings, $this->results['warnings'] );
		}

		// Only create error log if there are errors or warnings
		if ( ! empty( $all_errors ) || ! empty( $all_warnings ) ) {
			$error_log = array(
				'schema_version' => self::SCHEMA_VERSION,
				'generated_at'   => current_time( 'mysql', true ),
				'errors'         => $all_errors,
				'warnings'       => $all_warnings,
			);

			$this->write_json_file( 'error_log.json', $error_log );
		}
	}

	/**
	 * Write JSON data to file with proper formatting and validation.
	 *
	 * @param string $filename Filename (relative to export directory).
	 * @param mixed  $data Data to encode as JSON.
	 * @return bool True on success, false on failure.
	 */
	private function write_json_file( $filename, $data ) {
		try {
			// Add schema version if not present and data is an array
			if ( is_array( $data ) && ! isset( $data['schema_version'] ) ) {
				$data = array_merge( array( 'schema_version' => self::SCHEMA_VERSION ), $data );
			}

			/**
			 * Filters export data before it is written to a JSON file.
			 *
			 * Allows developers to modify or enhance any export data before it is
			 * saved to a file. This filter is called for every JSON file that is exported.
			 *
			 * @since 1.0.0
			 *
			 * @param mixed  $data The data to be exported.
			 * @param string $filename The filename being written to.
			 * @param Digital_Lobster_Exporter_Exporter $exporter The exporter instance.
			 */
			$data = apply_filters( 'digital_lobster_export_data', $data, $filename, $this );

			// Encode JSON with pretty printing
			$json = wp_json_encode( $data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE );

			if ( $json === false ) {
				throw new Exception( sprintf( 'Failed to encode JSON for %s: %s', $filename, json_last_error_msg() ) );
			}

			// Validate JSON
			if ( ! $this->validate_json( $json ) ) {
				throw new Exception( sprintf( 'Invalid JSON generated for %s', $filename ) );
			}

			// Check file size
			$json_size = strlen( $json );
			if ( $json_size > self::MAX_JSON_SIZE ) {
				$this->log_error(
					'exporter',
					sprintf( 'JSON file %s is large (%s MB)', $filename, round( $json_size / 1048576, 2 ) ),
					'warning'
				);
			}

			// Write to file
			$file_path = $this->export_dir . $filename;
			
			// Ensure directory exists
			$dir = dirname( $file_path );
			if ( ! file_exists( $dir ) ) {
				wp_mkdir_p( $dir );
			}

			// Write file efficiently for large data
			$result = $this->write_file_efficiently( $file_path, $json );

			if ( ! $result ) {
				throw new Exception( sprintf( 'Failed to write file %s', $filename ) );
			}

			return true;

		} catch ( Exception $e ) {
			$this->log_error( 'exporter', $e->getMessage(), 'error' );
			return false;
		}
	}

	/**
	 * Write file efficiently, handling large data sets.
	 *
	 * @param string $file_path Full file path.
	 * @param string $content File content.
	 * @return bool True on success, false on failure.
	 */
	private function write_file_efficiently( $file_path, $content ) {
		// Use direct file_put_contents for AJAX requests to avoid admin dependencies
		// WP_Filesystem requires admin includes that may not be available during AJAX
		$result = file_put_contents( $file_path, $content, LOCK_EX );
		
		if ( $result !== false ) {
			chmod( $file_path, 0644 );
			return true;
		}

		return false;
	}

	/**
	 * Validate JSON string.
	 *
	 * @param string $json JSON string to validate.
	 * @return bool True if valid, false otherwise.
	 */
	private function validate_json( $json ) {
		if ( empty( $json ) ) {
			return false;
		}

		// Try to decode to validate
		json_decode( $json );
		
		return json_last_error() === JSON_ERROR_NONE;
	}

	/**
	 * Validate JSON schema for specific file types.
	 *
	 * @param string $filename Filename.
	 * @param array  $data Data to validate.
	 * @return bool True if valid, false otherwise.
	 */
	private function validate_schema( $filename, $data ) {
		// Basic schema validation for key files
		switch ( $filename ) {
			case 'site_blueprint.json':
				return $this->validate_blueprint_schema( $data );
			
			default:
				// For other files, just check if it's an array
				return is_array( $data );
		}
	}

	/**
	 * Validate site blueprint schema.
	 *
	 * @param array $data Blueprint data.
	 * @return bool True if valid, false otherwise.
	 */
	private function validate_blueprint_schema( $data ) {
		// Check required fields
		$required_fields = array( 'schema_version', 'site', 'theme', 'plugins', 'content' );
		
		foreach ( $required_fields as $field ) {
			if ( ! isset( $data[ $field ] ) ) {
				$this->log_error(
					'exporter',
					sprintf( 'Blueprint missing required field: %s', $field ),
					'warning'
				);
				return false;
			}
		}

		// Validate schema version
		if ( $data['schema_version'] !== self::SCHEMA_VERSION ) {
			$this->log_error(
				'exporter',
				sprintf( 'Invalid schema version: %d', $data['schema_version'] ),
				'warning'
			);
			return false;
		}

		return true;
	}

	/**
	 * Log an error or warning.
	 *
	 * @param string $component Component identifier.
	 * @param string $message Error message.
	 * @param string $severity Severity level: 'error', 'warning', 'critical'.
	 */
	private function log_error( $component, $message, $severity = 'error' ) {
		$log_entry = array(
			'component'  => $component,
			'message'    => $message,
			'severity'   => $severity,
			'timestamp'  => current_time( 'timestamp' ),
		);

		if ( $severity === 'warning' ) {
			$this->warnings[] = $log_entry;
		} else {
			$this->errors[] = $log_entry;
		}

		// Also log to WordPress error log if WP_DEBUG is enabled
		if ( defined( 'WP_DEBUG' ) && WP_DEBUG ) {
			error_log( sprintf(
				'Digital Lobster Exporter [%s] %s: %s',
				strtoupper( $severity ),
				$component,
				$message
			) );
		}
	}

	/**
	 * Get errors.
	 *
	 * @return array Error log entries.
	 */
	public function get_errors() {
		return $this->errors;
	}

	/**
	 * Get warnings.
	 *
	 * @return array Warning log entries.
	 */
	public function get_warnings() {
		return $this->warnings;
	}
}
