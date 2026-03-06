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
 * Scanner classes should implement:
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
	 * Constructor.
	 */
	public function __construct() {
		try {
			$this->load_settings();
			$this->setup_export_directory();
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
	 * Register default scanner classes.
	 */
	private function register_default_scanners() {
		// Load scanner classes
		$this->load_scanner_classes();
		
		// Register scanners in priority order
		$this->register_scanner( 'site', 'Digital_Lobster_Exporter_Site_Scanner', 10 );
		$this->register_scanner( 'theme', 'Digital_Lobster_Exporter_Theme_Scanner', 20 );
		$this->register_scanner( 'plugins', 'Digital_Lobster_Exporter_Plugin_Scanner', 30 );
		$this->register_scanner( 'content', 'Digital_Lobster_Exporter_Content_Scanner', 40 );
		$this->register_scanner( 'taxonomies', 'Digital_Lobster_Exporter_Taxonomy_Scanner', 50 );
		$this->register_scanner( 'media', 'Digital_Lobster_Exporter_Media_Scanner', 60 );
		$this->register_scanner( 'settings', 'Settings_Scanner', 70 );
		$this->register_scanner( 'menus', 'Menu_Scanner', 80 );
		$this->register_scanner( 'widgets', 'Widget_Scanner', 90 );
		$this->register_scanner( 'user_roles', 'Digital_Lobster_User_Roles_Scanner', 100 );
		$this->register_scanner( 'site_options', 'Site_Options_Scanner', 110 );
		$this->register_scanner( 'acf', 'Digital_Lobster_Exporter_ACF_Scanner', 115 );
		$this->register_scanner( 'shortcodes', 'Digital_Lobster_Exporter_Shortcode_Scanner', 120 );
		$this->register_scanner( 'forms', 'Digital_Lobster_Forms_Scanner', 125 );
		$this->register_scanner( 'hooks', 'Digital_Lobster_Exporter_Hooks_Scanner', 130 );
		$this->register_scanner( 'assets', 'Digital_Lobster_Exporter_Assets_Scanner', 132 );
		$this->register_scanner( 'page_templates', 'Page_Templates_Scanner', 135 );
		$this->register_scanner( 'block_patterns', 'Block_Patterns_Scanner', 140 );
		$this->register_scanner( 'rest_api', 'Digital_Lobster_Exporter_REST_API_Scanner', 145 );
		$this->register_scanner( 'redirects', 'Digital_Lobster_Exporter_Redirects_Scanner', 150 );
		$this->register_scanner( 'database', 'Digital_Lobster_Exporter_Database_Scanner', 155 );
		$this->register_scanner( 'translations', 'Digital_Lobster_Exporter_Translation_Scanner', 160 );
		$this->register_scanner( 'environment', 'Digital_Lobster_Exporter_Environment_Scanner', 165 );
		
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
		 * Scanner classes must implement a scan() method that returns scan results.
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
			// Load security filters class
			require_once DIGITAL_LOBSTER_EXPORTER_PATH . 'includes/class-security-filters.php';
			
			// Load exporter and packager classes
			require_once DIGITAL_LOBSTER_EXPORTER_PATH . 'includes/class-exporter.php';
			require_once DIGITAL_LOBSTER_EXPORTER_PATH . 'includes/class-packager.php';

			$scanner_files = array(
				'class-site-scanner.php',
				'class-theme-scanner.php',
				'class-plugin-scanner.php',
				'class-content-scanner.php',
				'class-taxonomy-scanner.php',
				'class-media-scanner.php',
				'class-settings-scanner.php',
				'class-menu-scanner.php',
				'class-widget-scanner.php',
				'class-user-roles-scanner.php',
				'class-site-options-scanner.php',
				'class-acf-scanner.php',
				'class-shortcode-scanner.php',
				'class-forms-scanner.php',
				'class-hooks-scanner.php',
				'class-page-templates-scanner.php',
				'class-block-patterns-scanner.php',
				'class-rest-api-scanner.php',
				'class-redirects-scanner.php',
				'class-database-scanner.php',
				'class-translation-scanner.php',
				'class-environment-scanner.php',
				'class-assets-scanner.php',
			);

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
		// Initialize results and error tracking
		$this->results = array();
		$this->errors = array();
		$this->warnings = array();

		// Update progress to starting state
		$this->update_progress( 'starting', 0, __( 'Starting scan process...', 'digital-lobster-exporter' ) );

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
				__( 'Exporting data to JSON files...', 'digital-lobster-exporter' )
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
				__( 'Scan completed successfully!', 'digital-lobster-exporter' ),
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
			do_action( 'digital_lobster_after_scan', $this->results, $this->errors, $this->warnings, $this );

			return array(
				'success' => true,
				'results' => $this->results,
				'errors'  => $this->errors,
				'warnings' => $this->warnings,
			);

		} catch ( Exception $e ) {
			// Critical error - scan failed
			$this->update_progress(
				'failed',
				0,
				sprintf( __( 'Scan failed: %s', 'digital-lobster-exporter' ), $e->getMessage() ),
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
			do_action( 'digital_lobster_scan_failed', $e, $this->errors, $this );

			return array(
				'success' => false,
				'error'   => $e->getMessage(),
				'errors'  => $this->errors,
			);
		}
	}

	/**
	 * Execute a single scanner.
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
			sprintf( __( 'Running %s...', 'digital-lobster-exporter' ), $name )
		);

		// Check if class exists
		if ( ! class_exists( $class_name ) ) {
			$this->log_error( 
				$name, 
				sprintf( __( 'Scanner class %s not found', 'digital-lobster-exporter' ), $class_name ),
				'error'
			);
			return;
		}

		// Instantiate scanner with appropriate parameters
		if ( $class_name === 'Digital_Lobster_Exporter_Content_Scanner' ) {
			$scanner = new $class_name( $this->export_dir );
		} elseif ( $class_name === 'Digital_Lobster_Exporter_Taxonomy_Scanner' ) {
			// Pass content data to TaxonomyScanner
			$content_data = isset( $this->results['content'] ) ? $this->results['content'] : array();
			$scanner = new $class_name( $content_data );
		} elseif ( $class_name === 'Digital_Lobster_Exporter_Media_Scanner' ) {
			// Pass content data and export_dir to MediaScanner
			$content_data = isset( $this->results['content'] ) ? $this->results['content'] : array();
			$scanner = new $class_name( $content_data, $this->export_dir );
		} elseif ( $class_name === 'Digital_Lobster_Exporter_ACF_Scanner' ) {
			// Pass export_dir to ACF Scanner
			$scanner = new $class_name( $this->export_dir );
		} elseif ( $class_name === 'Digital_Lobster_Exporter_Shortcode_Scanner' ) {
			// Pass export_dir to Shortcode Scanner
			$scanner = new $class_name( $this->export_dir );
		} elseif ( $class_name === 'Digital_Lobster_Forms_Scanner' ) {
			// Forms Scanner doesn't need constructor params
			$scanner = new $class_name();
		} elseif ( $class_name === 'Digital_Lobster_Exporter_Redirects_Scanner' ) {
			// Pass export_dir to Redirects Scanner
			$scanner = new $class_name( $this->export_dir );
		} elseif ( $class_name === 'Digital_Lobster_Exporter_Environment_Scanner' ) {
			// Pass export_dir to Environment Scanner
			$scanner = new $class_name( $this->export_dir );
		} elseif ( $class_name === 'Digital_Lobster_Exporter_Assets_Scanner' ) {
			// Pass export_dir to Assets Scanner
			$scanner = new $class_name( $this->export_dir );
		} else {
			$scanner = new $class_name();
		}

		// Export to file if scanner has export method
		if ( method_exists( $scanner, 'export' ) ) {
			$scanner->export( $this->export_dir );
		}

		// Check if scanner has required method
		if ( ! method_exists( $scanner, 'scan' ) ) {
			$this->log_error(
				$name,
				sprintf( __( 'Scanner class %s does not have a scan() method', 'digital-lobster-exporter' ), $class_name ),
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
			if ( $class_name === 'Digital_Lobster_Exporter_Media_Scanner' ) {
				$scanner->save_media_map();
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
			// Special handling for Redirects Scanner - pass content data
			if ( $name === 'redirects' ) {
				$content_data = isset( $this->results['content'] ) ? $this->results['content'] : array();
				return $scanner->scan( $content_data );
			}
			
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
						__( 'Batch processing exceeded maximum iterations', 'digital-lobster-exporter' ),
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
			'results'  => $this->results,
			'errors'   => $this->errors,
			'warnings' => $this->warnings,
			'timestamp' => current_time( 'timestamp' ),
		);

		set_transient( 'digital_lobster_scan_results', $data, HOUR_IN_SECONDS );
	}

	/**
	 * Log an error or warning.
	 *
	 * @param string $scanner Scanner identifier.
	 * @param string $message Error message.
	 * @param string $severity Severity level: 'error', 'warning', 'critical'.
	 */
	private function log_error( $scanner, $message, $severity = 'error' ) {
		$log_entry = array(
			'scanner'   => $scanner,
			'message'   => $message,
			'severity'  => $severity,
			'timestamp' => current_time( 'timestamp' ),
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
				$scanner,
				$message
			) );
		}
	}

	/**
	 * Get error log.
	 *
	 * @return array Error log entries.
	 */
	public function get_errors() {
		return $this->errors;
	}

	/**
	 * Get warning log.
	 *
	 * @return array Warning log entries.
	 */
	public function get_warnings() {
		return $this->warnings;
	}

	/**
	 * Clear all scan data.
	 */
	public function clear_scan_data() {
		delete_transient( 'digital_lobster_scan_progress' );
		delete_transient( 'digital_lobster_scan_results' );
		
		$this->results = array();
		$this->errors = array();
		$this->warnings = array();
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
			throw new Exception( __( 'ZipArchive PHP extension is required but not available. Please contact your hosting provider to enable it.', 'digital-lobster-exporter' ) );
		}

		// Check if export directory is writable
		if ( ! is_writable( dirname( $this->export_dir ) ) ) {
			throw new Exception( __( 'Export directory is not writable. Please check file permissions.', 'digital-lobster-exporter' ) );
		}

		// Check available disk space (require at least 100MB)
		$free_space = @disk_free_space( dirname( $this->export_dir ) );
		if ( $free_space !== false && $free_space < 104857600 ) {
			$this->log_error(
				'system',
				sprintf( __( 'Low disk space: %s MB available', 'digital-lobster-exporter' ), round( $free_space / 1048576, 2 ) ),
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
					__( 'High memory usage: %d%% (%s of %s used)', 'digital-lobster-exporter' ),
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
					__( 'Memory limit nearly exhausted (%d%% used). Please increase PHP memory_limit or reduce batch size in settings.', 'digital-lobster-exporter' ),
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
							__( 'Approaching execution time limit: %d seconds elapsed of %d maximum', 'digital-lobster-exporter' ),
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
			'/memory.*exhausted/i' => __( 'The scan ran out of memory. Try increasing PHP memory_limit in your hosting settings or reduce the batch size in plugin settings.', 'digital-lobster-exporter' ),
			'/maximum execution time/i' => __( 'The scan took too long and timed out. Try increasing max_execution_time in your hosting settings or reduce the amount of content to export.', 'digital-lobster-exporter' ),
			'/permission denied/i' => __( 'Permission denied when accessing files. Please check file permissions on your server.', 'digital-lobster-exporter' ),
			'/disk.*full/i' => __( 'Not enough disk space available. Please free up space on your server.', 'digital-lobster-exporter' ),
			'/failed to open stream/i' => __( 'Could not access a required file. This may be a temporary issue or a file permission problem.', 'digital-lobster-exporter' ),
			'/database/i' => __( 'Database connection or query error. Please check your database connection.', 'digital-lobster-exporter' ),
		);

		foreach ( $error_patterns as $pattern => $friendly_message ) {
			if ( preg_match( $pattern, $error_message ) ) {
				return $friendly_message . ' ' . sprintf( __( '(Scanner: %s)', 'digital-lobster-exporter' ), $scanner_name );
			}
		}

		// Return original message with scanner context
		return sprintf( __( '%s (Scanner: %s)', 'digital-lobster-exporter' ), $error_message, $scanner_name );
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

			// Merge exporter errors and warnings with scanner errors
			if ( ! empty( $exporter->get_errors() ) ) {
				$this->errors = array_merge( $this->errors, $exporter->get_errors() );
			}

			if ( ! empty( $exporter->get_warnings() ) ) {
				$this->warnings = array_merge( $this->warnings, $exporter->get_warnings() );
			}

			// Package into ZIP archive
			if ( $result['success'] ) {
				$this->update_progress(
					'packaging',
					98,
					__( 'Creating ZIP archive...', 'digital-lobster-exporter' )
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
			if ( ! empty( $packager->get_errors() ) ) {
				$this->errors = array_merge( $this->errors, $packager->get_errors() );
			}

			if ( ! empty( $packager->get_warnings() ) ) {
				$this->warnings = array_merge( $this->warnings, $packager->get_warnings() );
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
