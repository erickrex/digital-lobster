<?php
/**
 * Scanner Orchestrator Class
 *
 * Coordinates all scanning phases and manages the overall scan process.
 *
 * This class orchestrates the execution of multiple scanner classes, manages
 * progress tracking via WordPress transients, handles error logging, and
 * supports batch processing for large datasets.
 *
 * Scanner classes extend Digital_Lobster_Exporter_Scanner_Base and implement:
 * - scan() method (required): Returns scan results
 * - supports_batching() method (optional): Returns true if scanner supports batching
 * - scan_batch($batch_number, $batch_size) method (optional): Scans a single batch
 * - has_more_batches() method (optional): Returns true if more batches exist
 * - get_batch_size() method (optional): Returns preferred batch size
 * - merge_batch_results($batch_results) method (optional): Merges batch results
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Scanner Orchestrator Class
 */
class Digital_Lobster_Exporter_Scanner {

	use Digital_Lobster_Exporter_Error_Logger;

	/**
	 * Registered scanner classes.
	 *
	 * @var array
	 */
	private $scanners = array();

	/**
	 * Collected scan results.
	 *
	 * @var array
	 */
	private $results = array();

	/**
	 * Batch size for processing.
	 *
	 * @var int
	 */
	private $batch_size = 50;

	/**
	 * Export directory path.
	 *
	 * @var string
	 */
	private $export_dir = '';

	/**
	 * Security filters instance.
	 *
	 * @var Digital_Lobster_Exporter_Security_Filters
	 */
	private $security_filters;

	/**
	 * Constructor.
	 */
	public function __construct() {
		try {
			$this->load_settings();
			$this->setup_export_directory();
			$this->security_filters = new Digital_Lobster_Exporter_Security_Filters();
			$this->register_default_scanners();
		} catch ( Exception $e ) {
			if ( defined( 'WP_DEBUG' ) && WP_DEBUG ) {
				error_log( 'Digital Lobster Exporter Scanner Constructor Error: ' . $e->getMessage() );
			}
			throw $e;
		}
	}

	/**
	 * Load settings from wp_options.
	 */
	private function load_settings() {
		$settings = get_option( 'digital_lobster_settings', array() );
		
		if ( isset( $settings['batch_size'] ) ) {
			$this->batch_size = absint( $settings['batch_size'] );
		}
	}

	/**
	 * Setup export directory.
	 */
	private function setup_export_directory() {
		$upload_dir = wp_upload_dir();
		$this->export_dir = trailingslashit( $upload_dir['basedir'] ) . 'ai_migration_artifacts';
		
		// Create directory if it doesn't exist
		if ( ! file_exists( $this->export_dir ) ) {
			wp_mkdir_p( $this->export_dir );
		}
	}

	/**
	 * Get the declarative scanner registry.
	 *
	 * Returns an associative array mapping scanner names to their class
	 * names and priorities. This replaces the old register_default_scanners()
	 * approach with individual register_scanner() calls.
	 *
	 * @return array Scanner registry keyed by scanner name.
	 */
	private function get_scanner_registry() {
		return array(
			'site' => array( 'class' => 'Digital_Lobster_Exporter_Site_Scanner', 'file' => 'class-site-scanner.php', 'priority' => 10 ),
			'theme' => array( 'class' => 'Digital_Lobster_Exporter_Theme_Scanner', 'file' => 'class-theme-scanner.php', 'priority' => 20 ),
			'plugins' => array( 'class' => 'Digital_Lobster_Exporter_Plugin_Scanner', 'file' => 'class-plugin-scanner.php', 'priority' => 30 ),
			'content' => array( 'class' => 'Digital_Lobster_Exporter_Content_Scanner', 'file' => 'class-content-scanner.php', 'priority' => 40 ),
			'taxonomies' => array( 'class' => 'Digital_Lobster_Exporter_Taxonomy_Scanner', 'file' => 'class-taxonomy-scanner.php', 'priority' => 50 ),
			'media' => array( 'class' => 'Digital_Lobster_Exporter_Media_Scanner', 'file' => 'class-media-scanner.php', 'priority' => 60 ),
			'settings' => array( 'class' => 'Digital_Lobster_Exporter_Settings_Scanner', 'file' => 'class-settings-scanner.php', 'priority' => 70 ),
			'menus' => array( 'class' => 'Digital_Lobster_Exporter_Menu_Scanner', 'file' => 'class-menu-scanner.php', 'priority' => 80 ),
			'widgets' => array( 'class' => 'Digital_Lobster_Exporter_Widget_Scanner', 'file' => 'class-widget-scanner.php', 'priority' => 90 ),
			'user_roles' => array( 'class' => 'Digital_Lobster_Exporter_User_Roles_Scanner', 'file' => 'class-user-roles-scanner.php', 'priority' => 100 ),
			'site_options' => array( 'class' => 'Digital_Lobster_Exporter_Site_Options_Scanner', 'file' => 'class-site-options-scanner.php', 'priority' => 110 ),
			'acf' => array( 'class' => 'Digital_Lobster_Exporter_ACF_Scanner', 'file' => 'class-acf-scanner.php', 'priority' => 115 ),
			'shortcodes' => array( 'class' => 'Digital_Lobster_Exporter_Shortcode_Scanner', 'file' => 'class-shortcode-scanner.php', 'priority' => 120 ),
			'forms' => array( 'class' => 'Digital_Lobster_Exporter_Forms_Scanner', 'file' => 'class-forms-scanner.php', 'priority' => 125 ),
			'hooks' => array( 'class' => 'Digital_Lobster_Exporter_Hooks_Scanner', 'file' => 'class-hooks-scanner.php', 'priority' => 130 ),
			'assets' => array( 'class' => 'Digital_Lobster_Exporter_Assets_Scanner', 'file' => 'class-assets-scanner.php', 'priority' => 132 ),
			'page_templates' => array( 'class' => 'Digital_Lobster_Exporter_Page_Templates_Scanner', 'file' => 'class-page-templates-scanner.php', 'priority' => 135 ),
			'block_patterns' => array( 'class' => 'Digital_Lobster_Exporter_Block_Patterns_Scanner', 'file' => 'class-block-patterns-scanner.php', 'priority' => 140 ),
			'rest_api' => array( 'class' => 'Digital_Lobster_Exporter_REST_API_Scanner', 'file' => 'class-rest-api-scanner.php', 'priority' => 145 ),
			'redirects' => array( 'class' => 'Digital_Lobster_Exporter_Redirects_Scanner', 'file' => 'class-redirects-scanner.php', 'priority' => 150 ),
			'database' => array( 'class' => 'Digital_Lobster_Exporter_Database_Scanner', 'file' => 'class-database-scanner.php', 'priority' => 155 ),
			'translations' => array( 'class' => 'Digital_Lobster_Exporter_Translation_Scanner', 'file' => 'class-translation-scanner.php', 'priority' => 160 ),
			'environment' => array( 'class' => 'Digital_Lobster_Exporter_Environment_Scanner', 'file' => 'class-environment-scanner.php', 'priority' => 165 ),
			'content_relationships' => array( 'class' => 'Digital_Lobster_Exporter_Content_Relationships_Scanner', 'file' => 'class-content-relationships-scanner.php', 'priority' => 170 ),
			'field_usage' => array( 'class' => 'Digital_Lobster_Exporter_Field_Usage_Scanner', 'file' => 'class-field-usage-scanner.php', 'priority' => 175 ),
			'plugin_instances' => array( 'class' => 'Digital_Lobster_Exporter_Plugin_Instances_Scanner', 'file' => 'class-plugin-instances-scanner.php', 'priority' => 180 ),
			'page_composition' => array( 'class' => 'Digital_Lobster_Exporter_Page_Composition_Scanner', 'file' => 'class-page-composition-scanner.php', 'priority' => 185 ),
			'seo_full' => array( 'class' => 'Digital_Lobster_Exporter_Seo_Full_Scanner', 'file' => 'class-seo-full-scanner.php', 'priority' => 190 ),
			'editorial_workflows' => array( 'class' => 'Digital_Lobster_Exporter_Editorial_Workflows_Scanner', 'file' => 'class-editorial-workflows-scanner.php', 'priority' => 195 ),
			'plugin_table_exports' => array( 'class' => 'Digital_Lobster_Exporter_Plugin_Table_Exports_Scanner', 'file' => 'class-plugin-table-exports-scanner.php', 'priority' => 200 ),
			'search_config' => array( 'class' => 'Digital_Lobster_Exporter_Search_Config_Scanner', 'file' => 'class-search-config-scanner.php', 'priority' => 205 ),
			'integration_manifest' => array( 'class' => 'Digital_Lobster_Exporter_Integration_Manifest_Scanner', 'file' => 'class-integration-manifest-scanner.php', 'priority' => 210 ),
		);
	}

	/**
	 * Register default scanner classes.
	 */
	private function register_default_scanners() {
		// Load scanner classes
		$this->load_scanner_classes();

		// Build scanner list from declarative registry
		$this->scanners = $this->get_scanner_registry();

		/**
		 * Filters the registered scanner classes.
		 *
		 * Allows developers to register custom scanner classes or modify the list
		 * of scanners that will be executed during the scan process.
		 *
		 * Each scanner in the array should have the following structure:
		 * array(
		 *     'class'    => 'Scanner_Class_Name',
		 *     'priority' => 10,
		 * )
		 *
		 * Scanner classes must extend Digital_Lobster_Exporter_Scanner_Base and
		 * implement a scan() method that returns scan results.
		 * Optional methods for batch processing:
		 * - supports_batching(): Returns true if scanner supports batching
		 * - scan_batch($batch_number, $batch_size): Scans a single batch
		 * - has_more_batches(): Returns true if more batches exist
		 * - get_batch_size(): Returns preferred batch size
		 * - merge_batch_results($batch_results): Merges batch results
		 *
		 * Example usage:
		 * ```php
		 * add_filter( 'digital_lobster_scanner_classes', function( $scanners ) {
		 *     $scanners['my_custom_scanner'] = array(
		 *         'class'    => 'My_Custom_Scanner',
		 *         'priority' => 200,
		 *     );
		 *     return $scanners;
		 * } );
		 * ```
		 *
		 * @since 1.0.0
		 *
		 * @param array $scanners Array of registered scanner configurations.
		 */
		$this->scanners = apply_filters( 'digital_lobster_scanner_classes', $this->scanners );
	}

	/**
	 * Load scanner class files.
	 */
	private function load_scanner_classes() {
		// Suppress any output during file loading
		ob_start();
		
		try {
			// Load shared constructs first (trait must come before classes that use it)
			require_once DIGITAL_LOBSTER_EXPORTER_PATH . 'includes/trait-error-logger.php';
			require_once DIGITAL_LOBSTER_EXPORTER_PATH . 'includes/class-callback-resolver.php';
			require_once DIGITAL_LOBSTER_EXPORTER_PATH . 'includes/class-source-identifier.php';
			require_once DIGITAL_LOBSTER_EXPORTER_PATH . 'includes/class-scanner-base.php';

			// Load security filters class
			require_once DIGITAL_LOBSTER_EXPORTER_PATH . 'includes/class-security-filters.php';
			
			// Load exporter and packager classes
			require_once DIGITAL_LOBSTER_EXPORTER_PATH . 'includes/class-exporter.php';
			require_once DIGITAL_LOBSTER_EXPORTER_PATH . 'includes/class-packager.php';

			$scanner_files = array();
			foreach ( $this->get_scanner_registry() as $scanner_config ) {
				if ( isset( $scanner_config['file'] ) ) {
					$scanner_files[] = $scanner_config['file'];
				}
			}
			$scanner_files = array_values( array_unique( $scanner_files ) );

			foreach ( $scanner_files as $file ) {
				$file_path = DIGITAL_LOBSTER_EXPORTER_PATH . 'includes/scanners/' . $file;
				if ( file_exists( $file_path ) ) {
					try {
						require_once $file_path;
					} catch ( Exception $e ) {
						if ( defined( 'WP_DEBUG' ) && WP_DEBUG ) {
							error_log( 'Digital Lobster Exporter: Error loading scanner file ' . $file . ': ' . $e->getMessage() );
						}
						// Continue loading other files
					}
				} else {
					if ( defined( 'WP_DEBUG' ) && WP_DEBUG ) {
						error_log( 'Digital Lobster Exporter: Scanner file not found: ' . $file_path );
					}
				}
			}
		} finally {
			// Discard any output that occurred during file loading
			$unwanted_output = ob_get_clean();
			if ( ! empty( $unwanted_output ) && defined( 'WP_DEBUG' ) && WP_DEBUG ) {
				error_log( 'Digital Lobster Exporter: Unwanted output during scanner loading: ' . $unwanted_output );
			}
		}
	}

	/**
	 * Register a scanner class.
	 *
	 * @param string $name Scanner identifier.
	 * @param string $class_name Scanner class name.
	 * @param int    $priority Priority order (lower runs first).
	 */
	public function register_scanner( $name, $class_name, $priority = 10 ) {
		$this->scanners[ $name ] = array(
			'class'    => $class_name,
			'priority' => $priority,
		);
	}

	/**
	 * Run the complete scan process.
	 *
	 * @return array Scan results or error information.
	 */
	public function run_scan() {
		// Initialize results
		$this->results = array();

		// Update progress to starting state
		$this->update_progress( 'starting', 0, 'Starting scan process...' );

		/**
		 * Fires before the scan process begins.
		 *
		 * Allows developers to perform actions before any scanning starts.
		 *
		 * @since 1.0.0
		 *
		 * @param Digital_Lobster_Exporter_Scanner $scanner The scanner instance.
		 */
		do_action( 'digital_lobster_before_scan', $this );

		try {
			// Check system requirements before starting
			$this->check_system_requirements();

			// Sort scanners by priority
			uasort( $this->scanners, function( $a, $b ) {
				return $a['priority'] - $b['priority'];
			});

			$total_scanners = count( $this->scanners );
			$current_scanner = 0;

			// Execute each scanner
			foreach ( $this->scanners as $name => $scanner_config ) {
				$current_scanner++;
				$percent = ( $current_scanner / $total_scanners ) * 90; // Reserve 10% for final packaging

				/**
				 * Fires before an individual scanner executes.
				 *
				 * @since 1.0.0
				 *
				 * @param string $name Scanner identifier.
				 * @param array  $scanner_config Scanner configuration.
				 * @param Digital_Lobster_Exporter_Scanner $scanner The scanner orchestrator instance.
				 */
				do_action( 'digital_lobster_before_scanner', $name, $scanner_config, $this );

				try {
					// Check memory and time limits before each scanner
					$this->check_resource_limits( $name );
					
					$this->execute_scanner( $name, $scanner_config, $percent );

					/**
					 * Fires after an individual scanner completes successfully.
					 *
					 * @since 1.0.0
					 *
					 * @param string $name Scanner identifier.
					 * @param mixed  $results Scanner results.
					 * @param Digital_Lobster_Exporter_Scanner $scanner The scanner orchestrator instance.
					 */
					do_action( 'digital_lobster_after_scanner', $name, isset( $this->results[ $name ] ) ? $this->results[ $name ] : null, $this );

				} catch ( Exception $e ) {
					// Log error but continue with other scanners
					$error_message = $this->get_user_friendly_error_message( $e->getMessage(), $name );
					$this->log_error( $name, $error_message, 'error' );

					/**
					 * Fires when a scanner fails with an exception.
					 *
					 * @since 1.0.0
					 *
					 * @param string    $name Scanner identifier.
					 * @param Exception $e The exception that was thrown.
					 * @param Digital_Lobster_Exporter_Scanner $scanner The scanner orchestrator instance.
					 */
					do_action( 'digital_lobster_scanner_error', $name, $e, $this );
				}
			}

			// Export all data to JSON files
			$this->update_progress(
				'exporting',
				95,
				'Exporting data to JSON files...'
			);

			$export_result = $this->export_data();

			if ( ! $export_result['success'] ) {
				$this->log_error( 'exporter', 'Failed to export data', 'error' );
			}

			// Store download information in results
			if ( isset( $export_result['download_url'] ) ) {
				$this->results['download_url'] = $export_result['download_url'];
				$this->results['zip_filename'] = $export_result['zip_filename'];
				$this->results['zip_size'] = $export_result['zip_size'];
			}

			// Mark scan as complete
			$this->update_progress( 
				'completed', 
				100, 
				'Scan completed successfully!',
				true
			);

			// Store results in transient
			$this->store_results();

			/**
			 * Fires after the scan process completes successfully.
			 *
			 * @since 1.0.0
			 *
			 * @param array $results Complete scan results.
			 * @param array $errors Error log entries.
			 * @param array $warnings Warning log entries.
			 * @param Digital_Lobster_Exporter_Scanner $scanner The scanner instance.
			 */
			do_action( 'digital_lobster_after_scan', $this->results, $this->get_errors(), $this->get_warnings(), $this );

			return array(
				'success'  => true,
				'results'  => $this->results,
				'errors'   => $this->get_errors(),
				'warnings' => $this->get_warnings(),
			);

		} catch ( Exception $e ) {
			// Critical error - scan failed
			$this->update_progress(
				'failed',
				0,
				sprintf( 'Scan failed: %s', $e->getMessage() ),
				false,
				$e->getMessage()
			);

			$this->log_error( 'scanner', $e->getMessage(), 'critical' );

			/**
			 * Fires when the scan process fails with a critical error.
			 *
			 * @since 1.0.0
			 *
			 * @param Exception $e The exception that caused the failure.
			 * @param array $errors Error log entries.
			 * @param Digital_Lobster_Exporter_Scanner $scanner The scanner instance.
			 */
			do_action( 'digital_lobster_scan_failed', $e, $this->get_errors(), $this );

			return array(
				'success' => false,
				'error'   => $e->getMessage(),
				'errors'  => $this->get_errors(),
			);
		}
	}

	/**
	 * Execute a single scanner with uniform instantiation.
	 *
	 * Every scanner receives the same $deps array and is instantiated through
	 * the Scanner_Base constructor. No special-case logic per scanner.
	 *
	 * @param string $name Scanner identifier.
	 * @param array  $scanner_config Scanner configuration.
	 * @param float  $percent Current progress percentage.
	 * @throws Exception If scanner execution fails critically.
	 */
	private function execute_scanner( $name, $scanner_config, $percent ) {
		$class_name = $scanner_config['class'];

		// Update progress
		$this->update_progress(
			$name,
			$percent,
			sprintf( 'Running %s...', $name )
		);

		// Check if class exists
		if ( ! class_exists( $class_name ) ) {
			$this->log_error( $name, sprintf( 'Scanner class %s not found', $class_name ), 'error' );
			return;
		}

		// Build deps — same for every scanner
		$deps = array(
			'export_dir'       => $this->export_dir,
			'context'          => $this->results,
			'security_filters' => $this->security_filters,
		);

		$scanner = new $class_name( $deps );

		// Check if scanner has required method
		if ( ! method_exists( $scanner, 'scan' ) ) {
			$this->log_error(
				$name,
				sprintf( 'Scanner class %s does not have a scan() method', $class_name ),
				'error'
			);
			return;
		}

		// Execute scanner with batch processing support
		$scanner_results = $this->execute_with_batch_processing( $scanner, $name );

		// Store results
		if ( $scanner_results !== false ) {
			/**
			 * Filters scanner results before they are stored.
			 *
			 * Allows developers to modify or enhance scanner results before they are
			 * added to the final export data.
			 *
			 * @since 1.0.0
			 *
			 * @param mixed  $scanner_results The results from the scanner.
			 * @param string $name Scanner identifier.
			 * @param string $class_name Scanner class name.
			 */
			$scanner_results = apply_filters( 'digital_lobster_scanner_results', $scanner_results, $name, $class_name );

			$this->results[ $name ] = $scanner_results;
			
			// If this is MediaScanner, save the media map
			if ( $class_name === 'Digital_Lobster_Exporter_Media_Scanner' && method_exists( $scanner, 'save_media_map' ) ) {
				$scanner->save_media_map();
			}
		}

		// Merge scanner errors/warnings into orchestrator
		$scanner_errors = $scanner->get_errors();
		$scanner_warnings = $scanner->get_warnings();

		if ( ! empty( $scanner_errors ) ) {
			foreach ( $scanner_errors as $error ) {
				$this->log_error(
					isset( $error['component'] ) ? $error['component'] : $name,
					isset( $error['message'] ) ? $error['message'] : '',
					isset( $error['severity'] ) ? $error['severity'] : 'error'
				);
			}
		}

		if ( ! empty( $scanner_warnings ) ) {
			foreach ( $scanner_warnings as $warning ) {
				$this->log_warning(
					isset( $warning['component'] ) ? $warning['component'] : $name,
					isset( $warning['message'] ) ? $warning['message'] : ''
				);
			}
		}
	}

	/**
	 * Execute scanner with batch processing support.
	 *
	 * @param object $scanner Scanner instance.
	 * @param string $name Scanner identifier.
	 * @return mixed Scanner results or false on failure.
	 */
	private function execute_with_batch_processing( $scanner, $name ) {
		// Check if scanner supports batch processing
		if ( method_exists( $scanner, 'supports_batching' ) && $scanner->supports_batching() ) {
			return $this->execute_batched_scanner( $scanner, $name );
		}

		// Execute scanner normally
		try {
			return $scanner->scan();
		} catch ( Exception $e ) {
			$this->log_error( $name, $e->getMessage(), 'error' );
			return false;
		}
	}

	/**
	 * Execute scanner with batch processing.
	 *
	 * @param object $scanner Scanner instance.
	 * @param string $name Scanner identifier.
	 * @return mixed Combined scanner results.
	 */
	private function execute_batched_scanner( $scanner, $name ) {
		$batch_results = array();
		$batch_number = 0;
		$has_more = true;

		try {
			while ( $has_more ) {
				$batch_number++;

				// Get batch size from scanner or use default
				$batch_size = method_exists( $scanner, 'get_batch_size' ) 
					? $scanner->get_batch_size() 
					: $this->batch_size;

				// Execute batch
				$batch_result = $scanner->scan_batch( $batch_number, $batch_size );

				if ( $batch_result !== false && ! empty( $batch_result ) ) {
					$batch_results[] = $batch_result;
				}

				// Check if there are more batches
				$has_more = method_exists( $scanner, 'has_more_batches' ) 
					? $scanner->has_more_batches() 
					: false;

				// Prevent infinite loops
				if ( $batch_number > 1000 ) {
					$this->log_error(
						$name,
						'Batch processing exceeded maximum iterations',
						'warning'
					);
					break;
				}

				// Allow memory cleanup
				if ( function_exists( 'wp_cache_flush' ) ) {
					wp_cache_flush();
				}
			}

			// Merge batch results if scanner has merge method
			if ( method_exists( $scanner, 'merge_batch_results' ) ) {
				return $scanner->merge_batch_results( $batch_results );
			}

			return $batch_results;

		} catch ( Exception $e ) {
			$this->log_error( $name, $e->getMessage(), 'error' );
			return false;
		}
	}

	/**
	 * Update progress state.
	 *
	 * @param string $stage Current stage identifier.
	 * @param float  $percent Progress percentage (0-100).
	 * @param string $message Progress message.
	 * @param bool   $completed Whether scan is completed.
	 * @param string $error Error message if any.
	 */
	public function update_progress( $stage, $percent, $message, $completed = false, $error = '' ) {
		$progress = array(
			'stage'      => $stage,
			'percent'    => min( 100, max( 0, $percent ) ),
			'message'    => $message,
			'started_at' => $this->get_start_time(),
			'updated_at' => current_time( 'timestamp' ),
			'completed'  => $completed,
			'error'      => $error ? $error : false,
		);

		set_transient( 'digital_lobster_scan_progress', $progress, HOUR_IN_SECONDS );
	}

	/**
	 * Get scan start time.
	 *
	 * @return int Timestamp of scan start.
	 */
	private function get_start_time() {
		$progress = get_transient( 'digital_lobster_scan_progress' );
		
		if ( $progress && isset( $progress['started_at'] ) ) {
			return $progress['started_at'];
		}

		return current_time( 'timestamp' );
	}

	/**
	 * Get current progress.
	 *
	 * @return array|false Progress data or false if not found.
	 */
	public function get_progress() {
		return get_transient( 'digital_lobster_scan_progress' );
	}

	/**
	 * Get scan results.
	 *
	 * @return array Scan results.
	 */
	public function get_scan_results() {
		// Try to get from memory first
		if ( ! empty( $this->results ) ) {
			return $this->results;
		}

		// Try to get from transient
		$stored_results = get_transient( 'digital_lobster_scan_results' );
		
		if ( $stored_results ) {
			return $stored_results;
		}

		return array();
	}

	/**
	 * Store results in transient.
	 */
	private function store_results() {
		$data = array(
			'results'   => $this->results,
			'errors'    => $this->get_errors(),
			'warnings'  => $this->get_warnings(),
			'timestamp' => current_time( 'timestamp' ),
		);

		set_transient( 'digital_lobster_scan_results', $data, HOUR_IN_SECONDS );
	}

	/**
	 * Clear all scan data.
	 */
	public function clear_scan_data() {
		delete_transient( 'digital_lobster_scan_progress' );
		delete_transient( 'digital_lobster_scan_results' );
		
		$this->results = array();
	}

	/**
	 * Get batch size setting.
	 *
	 * @return int Batch size.
	 */
	public function get_batch_size() {
		return $this->batch_size;
	}

	/**
	 * Check system requirements before starting scan.
	 *
	 * @throws Exception If critical requirements are not met.
	 */
	private function check_system_requirements() {
		// Check if ZipArchive is available
		if ( ! class_exists( 'ZipArchive' ) ) {
			throw new Exception( 'ZipArchive PHP extension is required but not available. Please contact your hosting provider to enable it.' );
		}

		// Check if export directory is writable
		if ( ! is_writable( dirname( $this->export_dir ) ) ) {
			throw new Exception( 'Export directory is not writable. Please check file permissions.' );
		}

		// Check available disk space (require at least 100MB)
		$free_space = @disk_free_space( dirname( $this->export_dir ) );
		if ( $free_space !== false && $free_space < 104857600 ) {
			$this->log_error(
				'system',
				sprintf( 'Low disk space: %s MB available', round( $free_space / 1048576, 2 ) ),
				'warning'
			);
		}

		// Log memory limit
		$memory_limit = ini_get( 'memory_limit' );
		if ( defined( 'WP_DEBUG' ) && WP_DEBUG ) {
			error_log( sprintf( 'Digital Lobster Exporter: Starting scan with memory limit: %s', $memory_limit ) );
		}
	}

	/**
	 * Check resource limits (memory and execution time).
	 *
	 * @param string $scanner_name Current scanner name.
	 * @throws Exception If resource limits are critically low.
	 */
	private function check_resource_limits( $scanner_name ) {
		// Check memory usage
		$memory_limit = $this->get_memory_limit_bytes();
		$memory_used = memory_get_usage( true );
		$memory_available = $memory_limit - $memory_used;
		$memory_percent = ( $memory_used / $memory_limit ) * 100;

		// Warn if memory usage is high
		if ( $memory_percent > 80 ) {
			$this->log_error(
				$scanner_name,
				sprintf(
					'High memory usage: %d%% (%s of %s used)',
					round( $memory_percent ),
					$this->format_bytes( $memory_used ),
					$this->format_bytes( $memory_limit )
				),
				'warning'
			);

			// Try to free up memory
			if ( function_exists( 'wp_cache_flush' ) ) {
				wp_cache_flush();
			}
			if ( function_exists( 'gc_collect_cycles' ) ) {
				gc_collect_cycles();
			}
		}

		// Critical memory threshold (95%)
		if ( $memory_percent > 95 ) {
			throw new Exception(
				sprintf(
					'Memory limit nearly exhausted (%d%% used). Please increase PHP memory_limit or reduce batch size in settings.',
					round( $memory_percent )
				)
			);
		}

		// Check execution time (if max_execution_time is set)
		$max_execution_time = ini_get( 'max_execution_time' );
		if ( $max_execution_time > 0 ) {
			// Get progress to check elapsed time
			$progress = $this->get_progress();
			if ( $progress && isset( $progress['started_at'] ) ) {
				$elapsed_time = current_time( 'timestamp' ) - $progress['started_at'];
				$time_percent = ( $elapsed_time / $max_execution_time ) * 100;

				// Warn if approaching time limit
				if ( $time_percent > 80 ) {
					$this->log_error(
						$scanner_name,
						sprintf(
							'Approaching execution time limit: %d seconds elapsed of %d maximum',
							$elapsed_time,
							$max_execution_time
						),
						'warning'
					);
				}
			}
		}
	}

	/**
	 * Get memory limit in bytes.
	 *
	 * @return int Memory limit in bytes.
	 */
	private function get_memory_limit_bytes() {
		$memory_limit = ini_get( 'memory_limit' );
		
		if ( $memory_limit === '-1' ) {
			// Unlimited
			return PHP_INT_MAX;
		}

		// Convert to bytes
		$unit = strtolower( substr( $memory_limit, -1 ) );
		$value = (int) $memory_limit;

		switch ( $unit ) {
			case 'g':
				$value *= 1024 * 1024 * 1024;
				break;
			case 'm':
				$value *= 1024 * 1024;
				break;
			case 'k':
				$value *= 1024;
				break;
		}

		return $value;
	}

	/**
	 * Format bytes to human-readable format.
	 *
	 * @param int $bytes Bytes.
	 * @return string Formatted string.
	 */
	private function format_bytes( $bytes ) {
		$units = array( 'B', 'KB', 'MB', 'GB' );
		$bytes = max( $bytes, 0 );
		$pow = floor( ( $bytes ? log( $bytes ) : 0 ) / log( 1024 ) );
		$pow = min( $pow, count( $units ) - 1 );
		$bytes /= pow( 1024, $pow );

		return round( $bytes, 2 ) . ' ' . $units[ $pow ];
	}

	/**
	 * Get user-friendly error message.
	 *
	 * @param string $error_message Original error message.
	 * @param string $scanner_name Scanner name.
	 * @return string User-friendly error message.
	 */
	private function get_user_friendly_error_message( $error_message, $scanner_name ) {
		// Map technical errors to user-friendly messages
		$error_patterns = array(
			'/memory.*exhausted/i' => 'The scan ran out of memory. Try increasing PHP memory_limit in your hosting settings or reduce the batch size in plugin settings.',
			'/maximum execution time/i' => 'The scan took too long and timed out. Try increasing max_execution_time in your hosting settings or reduce the amount of content to export.',
			'/permission denied/i' => 'Permission denied when accessing files. Please check file permissions on your server.',
			'/disk.*full/i' => 'Not enough disk space available. Please free up space on your server.',
			'/failed to open stream/i' => 'Could not access a required file. This may be a temporary issue or a file permission problem.',
			'/database/i' => 'Database connection or query error. Please check your database connection.',
		);

		foreach ( $error_patterns as $pattern => $friendly_message ) {
			if ( preg_match( $pattern, $error_message ) ) {
				return $friendly_message . sprintf( ' (Scanner: %s)', $scanner_name );
			}
		}

		// Return original message with scanner context
		return sprintf( '%s (Scanner: %s)', $error_message, $scanner_name );
	}

	/**
	 * Export all collected data to JSON files.
	 *
	 * @return array Export results.
	 */
	private function export_data() {
		try {
			// Create exporter instance
			$exporter = new Digital_Lobster_Exporter_Exporter( $this->export_dir, $this->results );

			// Export all data
			$result = $exporter->export_all();

			// Merge exporter errors and warnings
			$exporter_errors = $exporter->get_errors();
			if ( ! empty( $exporter_errors ) ) {
				foreach ( $exporter_errors as $error ) {
					$this->log_error(
						isset( $error['component'] ) ? $error['component'] : 'exporter',
						isset( $error['message'] ) ? $error['message'] : '',
						isset( $error['severity'] ) ? $error['severity'] : 'error'
					);
				}
			}

			$exporter_warnings = $exporter->get_warnings();
			if ( ! empty( $exporter_warnings ) ) {
				foreach ( $exporter_warnings as $warning ) {
					$this->log_warning(
						isset( $warning['component'] ) ? $warning['component'] : 'exporter',
						isset( $warning['message'] ) ? $warning['message'] : ''
					);
				}
			}

			// Package into ZIP archive
			if ( $result['success'] ) {
				$this->update_progress(
					'packaging',
					98,
					'Creating ZIP archive...'
				);

				$package_result = $this->package_artifacts();

				if ( $package_result['success'] ) {
					// Store download URL in results
					$result['download_url'] = $package_result['download_url'];
					$result['zip_filename'] = $package_result['zip_filename'];
					$result['zip_size'] = $package_result['zip_size'];
				} else {
					$this->log_error( 'packager', $package_result['error'], 'error' );
				}
			}

			return $result;

		} catch ( Exception $e ) {
			$this->log_error( 'exporter', $e->getMessage(), 'error' );
			
			return array(
				'success' => false,
				'error'   => $e->getMessage(),
			);
		}
	}

	/**
	 * Package artifacts into ZIP archive.
	 *
	 * @return array Package results.
	 */
	private function package_artifacts() {
		try {
			// Create packager instance
			$packager = new Digital_Lobster_Exporter_Packager();

			// Create ZIP archive
			$result = $packager->create_zip( $this->export_dir );

			// Merge packager errors and warnings
			$packager_errors = $packager->get_errors();
			if ( ! empty( $packager_errors ) ) {
				foreach ( $packager_errors as $error ) {
					$this->log_error(
						isset( $error['component'] ) ? $error['component'] : 'packager',
						isset( $error['message'] ) ? $error['message'] : '',
						isset( $error['severity'] ) ? $error['severity'] : 'error'
					);
				}
			}

			$packager_warnings = $packager->get_warnings();
			if ( ! empty( $packager_warnings ) ) {
				foreach ( $packager_warnings as $warning ) {
					$this->log_warning(
						isset( $warning['component'] ) ? $warning['component'] : 'packager',
						isset( $warning['message'] ) ? $warning['message'] : ''
					);
				}
			}

			return $result;

		} catch ( Exception $e ) {
			$this->log_error( 'packager', $e->getMessage(), 'error' );
			
			return array(
				'success' => false,
				'error'   => $e->getMessage(),
			);
		}
	}
}
