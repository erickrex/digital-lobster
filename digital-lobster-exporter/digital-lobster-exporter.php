<?php
/**
 * Plugin Name: Digital Lobster Exporter
 * Plugin URI: https://github.com/yourusername/digital-lobster-exporter
 * Description: Export comprehensive WordPress site data for migration to Strapi CMS on Digital Ocean. One-click solution to collect all artifacts including database schema, content structure, plugin fingerprints, theme information, and assets.
 * Version: 1.0.0
 * Author: Your Name
 * Author URI: https://yourwebsite.com
 * License: GPL v2 or later
 * License URI: https://www.gnu.org/licenses/gpl-2.0.html
 * Requires at least: 5.9
 * Requires PHP: 7.4
 * Tested up to: 6.4
 * Network: false
 * 
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Currently plugin version.
 */
define( 'DIGITAL_LOBSTER_EXPORTER_VERSION', '1.0.0' );

/**
 * Plugin directory path.
 */
define( 'DIGITAL_LOBSTER_EXPORTER_PATH', plugin_dir_path( __FILE__ ) );

/**
 * Plugin directory URL.
 */
define( 'DIGITAL_LOBSTER_EXPORTER_URL', plugin_dir_url( __FILE__ ) );

/**
 * The code that runs during plugin activation.
 */
function activate_digital_lobster_exporter() {
	require_once DIGITAL_LOBSTER_EXPORTER_PATH . 'includes/trait-error-logger.php';
	require_once DIGITAL_LOBSTER_EXPORTER_PATH . 'includes/class-packager.php';
	$packager = new Digital_Lobster_Exporter_Packager();
	$packager->cleanup_old_artifacts();
}

/**
 * The code that runs during plugin deactivation.
 */
function deactivate_digital_lobster_exporter() {
	// Clean up transients
	delete_transient( 'digital_lobster_scan_progress' );
	delete_transient( 'digital_lobster_scan_results' );
}

register_activation_hook( __FILE__, 'activate_digital_lobster_exporter' );
register_deactivation_hook( __FILE__, 'deactivate_digital_lobster_exporter' );

/**
 * Initialize the plugin.
 */
function digital_lobster_exporter_init() {
	// Load shared trait and utilities (needed by Scanner_Base, Packager, Exporter, Scanner_Orchestrator)
	require_once DIGITAL_LOBSTER_EXPORTER_PATH . 'includes/trait-error-logger.php';
	require_once DIGITAL_LOBSTER_EXPORTER_PATH . 'includes/class-callback-resolver.php';
	require_once DIGITAL_LOBSTER_EXPORTER_PATH . 'includes/class-source-identifier.php';
	require_once DIGITAL_LOBSTER_EXPORTER_PATH . 'includes/class-scanner-base.php';

	// Load security filters class (always available)
	require_once DIGITAL_LOBSTER_EXPORTER_PATH . 'includes/class-security-filters.php';

	// Load scanner orchestrator class
	require_once DIGITAL_LOBSTER_EXPORTER_PATH . 'includes/class-scanner.php';

	// Load admin page class (needed for AJAX handlers too)
	require_once DIGITAL_LOBSTER_EXPORTER_PATH . 'includes/class-admin-page.php';

	// Initialize admin page (registers AJAX handlers and admin UI)
	$admin_page = new Digital_Lobster_Exporter_Admin_Page();
	$admin_page->init();
}
add_action( 'init', 'digital_lobster_exporter_init' );
