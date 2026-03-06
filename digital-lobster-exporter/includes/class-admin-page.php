<?php
/**
 * Admin Page Class
 *
 * Handles the admin interface and AJAX requests.
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Admin Page Class
 */
class Digital_Lobster_Exporter_Admin_Page {

	/**
	 * Initialize the admin page.
	 */
	public function init() {
		// Register AJAX handlers (always needed)
		add_action( 'wp_ajax_digital_lobster_start_scan', array( $this, 'handle_ajax_start_scan' ) );
		add_action( 'wp_ajax_digital_lobster_get_progress', array( $this, 'handle_ajax_get_progress' ) );
		add_action( 'wp_ajax_digital_lobster_download', array( $this, 'handle_ajax_download' ) );
		
		// Only register admin UI hooks when in admin context
		if ( is_admin() && ! wp_doing_ajax() ) {
			// Add admin menu
			add_action( 'admin_menu', array( $this, 'add_admin_menu' ) );
			
			// Enqueue admin assets
			add_action( 'admin_enqueue_scripts', array( $this, 'enqueue_assets' ) );
			
			// Register settings
			add_action( 'admin_init', array( $this, 'register_settings' ) );
		}
	}

	/**
	 * Add admin menu item.
	 */
	public function add_admin_menu() {
		add_menu_page(
			__( 'AI Website Exporter', 'digital-lobster-exporter' ),
			__( '🧠 Export with AI Agents', 'digital-lobster-exporter' ),
			'manage_options',
			'digital-lobster-exporter',
			array( $this, 'render_page' ),
			'dashicons-migrate',
			80
		);

		// Add settings submenu
		add_submenu_page(
			'digital-lobster-exporter',
			__( 'Settings', 'digital-lobster-exporter' ),
			__( 'Settings', 'digital-lobster-exporter' ),
			'manage_options',
			'digital-lobster-exporter-settings',
			array( $this, 'render_settings_page' )
		);
	}

	/**
	 * Enqueue admin CSS and JavaScript.
	 *
	 * @param string $hook The current admin page hook.
	 */
	public function enqueue_assets( $hook ) {
		// Don't run during AJAX requests
		if ( wp_doing_ajax() ) {
			return;
		}
		
		// Only load on our plugin page
		if ( 'toplevel_page_digital-lobster-exporter' !== $hook ) {
			return;
		}

		wp_enqueue_style(
			'digital-lobster-exporter-admin',
			DIGITAL_LOBSTER_EXPORTER_URL . 'assets/css/admin.css',
			array(),
			DIGITAL_LOBSTER_EXPORTER_VERSION
		);

		wp_enqueue_script(
			'digital-lobster-exporter-admin',
			DIGITAL_LOBSTER_EXPORTER_URL . 'assets/js/admin.js',
			array( 'jquery' ),
			DIGITAL_LOBSTER_EXPORTER_VERSION,
			true
		);

		// Localize script with AJAX URL and nonce
		wp_localize_script(
			'digital-lobster-exporter-admin',
			'digitalLobsterExporter',
			array(
				'ajaxUrl' => admin_url( 'admin-ajax.php' ),
				'nonce'   => wp_create_nonce( 'digital_lobster_exporter_nonce' ),
			)
		);
	}

	/**
	 * Render the admin page.
	 */
	public function render_page() {
		// Check user capabilities
		if ( ! current_user_can( 'manage_options' ) ) {
			wp_die( esc_html__( 'You do not have sufficient permissions to access this page.', 'digital-lobster-exporter' ) );
		}

		// Load template
		require_once DIGITAL_LOBSTER_EXPORTER_PATH . 'templates/admin-page.php';
	}

	/**
	 * Register plugin settings.
	 */
	public function register_settings() {
		register_setting(
			'digital_lobster_settings_group',
			'digital_lobster_settings',
			array( $this, 'sanitize_settings' )
		);

		add_settings_section(
			'digital_lobster_content_settings',
			__( 'Content Export Settings', 'digital-lobster-exporter' ),
			array( $this, 'render_content_settings_section' ),
			'digital-lobster-exporter-settings'
		);

		add_settings_field(
			'max_posts',
			__( 'Max Posts', 'digital-lobster-exporter' ),
			array( $this, 'render_max_posts_field' ),
			'digital-lobster-exporter-settings',
			'digital_lobster_content_settings'
		);

		add_settings_field(
			'max_pages',
			__( 'Max Pages', 'digital-lobster-exporter' ),
			array( $this, 'render_max_pages_field' ),
			'digital-lobster-exporter-settings',
			'digital_lobster_content_settings'
		);

		add_settings_field(
			'max_per_custom_post_type',
			__( 'Max Per Custom Post Type', 'digital-lobster-exporter' ),
			array( $this, 'render_max_custom_post_type_field' ),
			'digital-lobster-exporter-settings',
			'digital_lobster_content_settings'
		);

		add_settings_field(
			'include_html_snapshots',
			__( 'Include HTML Snapshots', 'digital-lobster-exporter' ),
			array( $this, 'render_include_html_snapshots_field' ),
			'digital-lobster-exporter-settings',
			'digital_lobster_content_settings'
		);

		add_settings_field(
			'batch_size',
			__( 'Batch Size', 'digital-lobster-exporter' ),
			array( $this, 'render_batch_size_field' ),
			'digital-lobster-exporter-settings',
			'digital_lobster_content_settings'
		);

		add_settings_field(
			'cleanup_after_hours',
			__( 'Cleanup After (Hours)', 'digital-lobster-exporter' ),
			array( $this, 'render_cleanup_after_hours_field' ),
			'digital-lobster-exporter-settings',
			'digital_lobster_content_settings'
		);
	}

	/**
	 * Sanitize settings input.
	 *
	 * @param array $input Settings input.
	 * @return array Sanitized settings.
	 */
	public function sanitize_settings( $input ) {
		$sanitized = array();

		if ( isset( $input['max_posts'] ) ) {
			$sanitized['max_posts'] = absint( $input['max_posts'] );
		}

		if ( isset( $input['max_pages'] ) ) {
			$sanitized['max_pages'] = absint( $input['max_pages'] );
		}

		if ( isset( $input['max_per_custom_post_type'] ) ) {
			$sanitized['max_per_custom_post_type'] = absint( $input['max_per_custom_post_type'] );
		}

		if ( isset( $input['include_html_snapshots'] ) ) {
			$sanitized['include_html_snapshots'] = (bool) $input['include_html_snapshots'];
		} else {
			// If checkbox is not checked, it won't be in the input array
			$sanitized['include_html_snapshots'] = false;
		}

		if ( isset( $input['batch_size'] ) ) {
			$sanitized['batch_size'] = absint( $input['batch_size'] );
		}

		if ( isset( $input['cleanup_after_hours'] ) ) {
			$sanitized['cleanup_after_hours'] = absint( $input['cleanup_after_hours'] );
		}

		return $sanitized;
	}

	/**
	 * Render content settings section description.
	 */
	public function render_content_settings_section() {
		echo '<p>' . esc_html__( 'Configure how many sample content items to export for each content type.', 'digital-lobster-exporter' ) . '</p>';
	}

	/**
	 * Render max posts field.
	 */
	public function render_max_posts_field() {
		$settings = get_option( 'digital_lobster_settings', array() );
		$value = isset( $settings['max_posts'] ) ? $settings['max_posts'] : 5;
		?>
		<input type="number" name="digital_lobster_settings[max_posts]" value="<?php echo esc_attr( $value ); ?>" min="1" max="100" />
		<p class="description"><?php esc_html_e( 'Maximum number of posts to export (default: 5)', 'digital-lobster-exporter' ); ?></p>
		<?php
	}

	/**
	 * Render max pages field.
	 */
	public function render_max_pages_field() {
		$settings = get_option( 'digital_lobster_settings', array() );
		$value = isset( $settings['max_pages'] ) ? $settings['max_pages'] : 2;
		?>
		<input type="number" name="digital_lobster_settings[max_pages]" value="<?php echo esc_attr( $value ); ?>" min="1" max="100" />
		<p class="description"><?php esc_html_e( 'Maximum number of pages to export (default: 2)', 'digital-lobster-exporter' ); ?></p>
		<?php
	}

	/**
	 * Render max custom post type field.
	 */
	public function render_max_custom_post_type_field() {
		$settings = get_option( 'digital_lobster_settings', array() );
		$value = isset( $settings['max_per_custom_post_type'] ) ? $settings['max_per_custom_post_type'] : 10;
		?>
		<input type="number" name="digital_lobster_settings[max_per_custom_post_type]" value="<?php echo esc_attr( $value ); ?>" min="1" max="100" />
		<p class="description"><?php esc_html_e( 'Maximum number of items to export per custom post type (default: 10)', 'digital-lobster-exporter' ); ?></p>
		<?php
	}

	/**
	 * Render include HTML snapshots field.
	 */
	public function render_include_html_snapshots_field() {
		$settings = get_option( 'digital_lobster_settings', array() );
		$value = isset( $settings['include_html_snapshots'] ) ? $settings['include_html_snapshots'] : true;
		?>
		<label>
			<input type="checkbox" name="digital_lobster_settings[include_html_snapshots]" value="1" <?php checked( $value, true ); ?> />
			<?php esc_html_e( 'Generate HTML snapshots of content', 'digital-lobster-exporter' ); ?>
		</label>
		<p class="description"><?php esc_html_e( 'Enable to capture rendered HTML for each content item. Disable for faster exports on large sites (default: enabled)', 'digital-lobster-exporter' ); ?></p>
		<?php
	}

	/**
	 * Render batch size field.
	 */
	public function render_batch_size_field() {
		$settings = get_option( 'digital_lobster_settings', array() );
		$value = isset( $settings['batch_size'] ) ? $settings['batch_size'] : 50;
		?>
		<input type="number" name="digital_lobster_settings[batch_size]" value="<?php echo esc_attr( $value ); ?>" min="10" max="200" />
		<p class="description"><?php esc_html_e( 'Batch size for processing large datasets (default: 50)', 'digital-lobster-exporter' ); ?></p>
		<?php
	}

	/**
	 * Render cleanup after hours field.
	 */
	public function render_cleanup_after_hours_field() {
		$settings = get_option( 'digital_lobster_settings', array() );
		$value = isset( $settings['cleanup_after_hours'] ) ? $settings['cleanup_after_hours'] : 24;
		?>
		<input type="number" name="digital_lobster_settings[cleanup_after_hours]" value="<?php echo esc_attr( $value ); ?>" min="1" max="168" />
		<p class="description"><?php esc_html_e( 'Automatically delete old artifacts after this many hours (default: 24)', 'digital-lobster-exporter' ); ?></p>
		<?php
	}

	/**
	 * Render settings page.
	 */
	public function render_settings_page() {
		// Check user capabilities
		if ( ! current_user_can( 'manage_options' ) ) {
			wp_die( esc_html__( 'You do not have sufficient permissions to access this page.', 'digital-lobster-exporter' ) );
		}
		?>
		<div class="wrap">
			<h1><?php echo esc_html( get_admin_page_title() ); ?></h1>
			<form method="post" action="options.php">
				<?php
				settings_fields( 'digital_lobster_settings_group' );
				do_settings_sections( 'digital-lobster-exporter-settings' );
				submit_button();
				?>
			</form>
		</div>
		<?php
	}

	/**
	 * Handle AJAX request to start scan.
	 */
	public function handle_ajax_start_scan() {
		// Suppress ALL output - critical for clean JSON response
		@ini_set( 'display_errors', '0' );
		@ini_set( 'log_errors', '1' );
		error_reporting( 0 );
		
		// Clear any existing output buffers that may contain warnings
		while ( ob_get_level() > 0 ) {
			ob_end_clean();
		}
		
		// Start fresh output buffer to catch any stray output
		ob_start();
		
		// Enable error logging (not display) for debugging
		if ( defined( 'WP_DEBUG' ) && WP_DEBUG ) {
			error_log( 'Digital Lobster Exporter: Starting AJAX scan request' );
		}

		try {
			// Load security filters
			require_once DIGITAL_LOBSTER_EXPORTER_PATH . 'includes/class-security-filters.php';

			// Verify nonce
			$nonce = isset( $_POST['nonce'] ) ? sanitize_text_field( $_POST['nonce'] ) : '';
			if ( ! Digital_Lobster_Exporter_Security_Filters::verify_nonce( $nonce ) ) {
				ob_end_clean();
				wp_send_json_error( array( 'message' => __( 'Security check failed.', 'digital-lobster-exporter' ) ) );
			}

			// Check user capabilities
			if ( ! Digital_Lobster_Exporter_Security_Filters::verify_capability( 'manage_options' ) ) {
				ob_end_clean();
				wp_send_json_error( array( 'message' => __( 'Insufficient permissions.', 'digital-lobster-exporter' ) ) );
			}

			// Load scanner class
			require_once DIGITAL_LOBSTER_EXPORTER_PATH . 'includes/class-scanner.php';

			// Initialize scanner orchestrator
			if ( defined( 'WP_DEBUG' ) && WP_DEBUG ) {
				error_log( 'Digital Lobster Exporter: Initializing scanner' );
			}
			$scanner = new Digital_Lobster_Exporter_Scanner();

			// Run the scan process
			if ( defined( 'WP_DEBUG' ) && WP_DEBUG ) {
				error_log( 'Digital Lobster Exporter: Running scan' );
			}
			$result = $scanner->run_scan();
			
			// Clear any unwanted output
			ob_end_clean();
			
		} catch ( Exception $e ) {
			if ( defined( 'WP_DEBUG' ) && WP_DEBUG ) {
				error_log( 'Digital Lobster Exporter: Exception caught: ' . $e->getMessage() );
				error_log( 'Digital Lobster Exporter: Stack trace: ' . $e->getTraceAsString() );
			}
			ob_end_clean();
			wp_send_json_error( array( 
				'message' => sprintf( 
					__( 'Fatal error: %s', 'digital-lobster-exporter' ), 
					$e->getMessage() 
				) 
			) );
			return;
		} catch ( Error $e ) {
			if ( defined( 'WP_DEBUG' ) && WP_DEBUG ) {
				error_log( 'Digital Lobster Exporter: PHP Error caught: ' . $e->getMessage() );
				error_log( 'Digital Lobster Exporter: Stack trace: ' . $e->getTraceAsString() );
			}
			ob_end_clean();
			wp_send_json_error( array( 
				'message' => sprintf( 
					__( 'PHP Error: %s', 'digital-lobster-exporter' ), 
					$e->getMessage() 
				) 
			) );
			return;
		}

		// Discard any captured output (warnings, notices, etc.)
		ob_end_clean();
		
		if ( $result['success'] ) {
			// Get download URL from results
			$download_url = isset( $result['results']['download_url'] ) ? $result['results']['download_url'] : '';
			$zip_filename = isset( $result['results']['zip_filename'] ) ? $result['results']['zip_filename'] : '';
			$zip_size = isset( $result['results']['zip_size'] ) ? $result['results']['zip_size'] : 0;

			// Format success message
			$message = __( 'Scan completed successfully!', 'digital-lobster-exporter' );
			
			// Add warnings count if any
			$warnings_count = isset( $result['warnings'] ) ? count( $result['warnings'] ) : 0;
			$errors_count = isset( $result['errors'] ) ? count( $result['errors'] ) : 0;
			
			if ( $warnings_count > 0 || $errors_count > 0 ) {
				$message .= ' ' . sprintf(
					__( '(%d warning(s), %d non-critical error(s) - see error_log.json in the export)', 'digital-lobster-exporter' ),
					$warnings_count,
					$errors_count
				);
			}

			wp_send_json_success( array( 
				'message' => $message,
				'completed' => true,
				'download_url' => $download_url,
				'zip_filename' => $zip_filename,
				'zip_size' => $zip_size,
				'errors' => $result['errors'],
				'warnings' => $result['warnings'],
				'has_issues' => ( $warnings_count > 0 || $errors_count > 0 ),
			) );
		} else {
			// Format error message with helpful context
			$error_message = isset( $result['error'] ) ? $result['error'] : __( 'An unknown error occurred.', 'digital-lobster-exporter' );
			
			// Add troubleshooting tips
			$error_message .= ' ' . __( 'Please check the WordPress debug log for more details.', 'digital-lobster-exporter' );

			wp_send_json_error( array( 
				'message' => $error_message,
				'errors' => isset( $result['errors'] ) ? $result['errors'] : array(),
			) );
		}
	}

	/**
	 * Handle AJAX request to get progress.
	 */
	public function handle_ajax_get_progress() {
		// Load security filters
		require_once DIGITAL_LOBSTER_EXPORTER_PATH . 'includes/class-security-filters.php';

		// Verify nonce
		$nonce = isset( $_POST['nonce'] ) ? sanitize_text_field( $_POST['nonce'] ) : '';
		if ( ! Digital_Lobster_Exporter_Security_Filters::verify_nonce( $nonce ) ) {
			wp_send_json_error( array( 'message' => __( 'Security check failed.', 'digital-lobster-exporter' ) ) );
		}

		// Check user capabilities
		if ( ! Digital_Lobster_Exporter_Security_Filters::verify_capability( 'manage_options' ) ) {
			wp_send_json_error( array( 'message' => __( 'Insufficient permissions.', 'digital-lobster-exporter' ) ) );
		}

		// Get current progress from transient
		$progress = get_transient( 'digital_lobster_scan_progress' );

		if ( ! $progress ) {
			wp_send_json_error( array( 'message' => __( 'No scan in progress.', 'digital-lobster-exporter' ) ) );
		}

		wp_send_json_success( $progress );
	}

	/**
	 * Handle AJAX request to download artifacts.
	 */
	public function handle_ajax_download() {
		// Load security filters
		require_once DIGITAL_LOBSTER_EXPORTER_PATH . 'includes/class-security-filters.php';

		// Get token and nonce from request
		$token = isset( $_GET['token'] ) ? sanitize_text_field( $_GET['token'] ) : '';
		$nonce = isset( $_GET['nonce'] ) ? sanitize_text_field( $_GET['nonce'] ) : '';

		// Check user capabilities
		if ( ! Digital_Lobster_Exporter_Security_Filters::verify_capability( 'manage_options' ) ) {
			wp_die( esc_html__( 'Insufficient permissions.', 'digital-lobster-exporter' ), 'Access Denied', array( 'response' => 403 ) );
		}

		// Validate token
		if ( empty( $token ) || empty( $nonce ) ) {
			wp_die( esc_html__( 'Invalid download request.', 'digital-lobster-exporter' ), 'Invalid Request', array( 'response' => 400 ) );
		}

		// Load packager class
		require_once DIGITAL_LOBSTER_EXPORTER_PATH . 'includes/class-packager.php';
		$packager = new Digital_Lobster_Exporter_Packager();

		// Verify download token
		$download_data = $packager->verify_download_token( $token, $nonce );

		if ( ! $download_data ) {
			wp_die( esc_html__( 'Invalid or expired download link.', 'digital-lobster-exporter' ), 'Invalid Link', array( 'response' => 404 ) );
		}

		// Serve the file
		$packager->serve_download( $download_data['zip_path'], $download_data['zip_filename'] );
	}
}
