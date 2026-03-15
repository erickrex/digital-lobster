<?php
/**
 * Regression checks for keeping export data out of the ZIP storage root.
 *
 * Run with:
 * php tests/export_directory_regression.php
 */

if ( ! defined( 'WPINC' ) ) {
	define( 'WPINC', 'wp-includes' );
}

if ( ! defined( 'ABSPATH' ) ) {
	define( 'ABSPATH', sys_get_temp_dir() . '/digital-lobster-tests/' );
}

if ( ! defined( 'DIGITAL_LOBSTER_EXPORTER_PATH' ) ) {
	define( 'DIGITAL_LOBSTER_EXPORTER_PATH', dirname( __DIR__ ) . '/' );
}

$test_upload_base = sys_get_temp_dir() . '/digital_lobster_export_dir_test_' . uniqid();

if ( ! defined( 'HOUR_IN_SECONDS' ) ) {
	define( 'HOUR_IN_SECONDS', 3600 );
}

function trailingslashit( $string ) {
	return rtrim( $string, '/\\' ) . '/';
}

function wp_upload_dir() {
	global $test_upload_base;

	return array(
		'basedir' => $test_upload_base,
		'baseurl' => 'https://example.com/uploads',
	);
}

function get_option( $option, $default = false ) {
	return $default;
}

function current_time( $type, $gmt = 0 ) {
	if ( 'timestamp' === $type || 'U' === $type ) {
		return time();
	}

	return gmdate( $type ?: 'Y-m-d H:i:s' );
}

function wp_mkdir_p( $target ) {
	return is_dir( $target ) || mkdir( $target, 0777, true );
}

require_once dirname( __DIR__ ) . '/includes/trait-error-logger.php';
require_once dirname( __DIR__ ) . '/includes/class-security-filters.php';
require_once dirname( __DIR__ ) . '/includes/class-packager.php';
require_once dirname( __DIR__ ) . '/includes/class-scanner.php';

function assert_true( $condition, $message ) {
	if ( ! $condition ) {
		fwrite( STDERR, "Assertion failed: {$message}\n" );
		exit( 1 );
	}
}

$reflection = new ReflectionClass( 'Digital_Lobster_Exporter_Scanner' );
$scanner    = $reflection->newInstanceWithoutConstructor();
$method     = $reflection->getMethod( 'setup_export_directory' );
$method->setAccessible( true );
$method->invoke( $scanner );

$property   = $reflection->getProperty( 'export_dir' );
$property->setAccessible( true );
$export_dir = $property->getValue( $scanner );
$base_dir   = trailingslashit( $test_upload_base ) . 'ai_migration_artifacts';

assert_true( is_dir( $export_dir ), 'Scanner should create an export directory.' );
assert_true( $export_dir !== $base_dir, 'Scanner export directory must not equal the ZIP storage root.' );
assert_true( strpos( $export_dir, $base_dir . '/' ) === 0, 'Scanner export directory should live under the artifacts root.' );

$packager = new Digital_Lobster_Exporter_Packager();
assert_true( $packager->cleanup_temp_files( $base_dir ), 'Cleanup guard should not fail for the base artifacts directory.' );
assert_true( is_dir( $base_dir ), 'Cleanup guard must not delete the base artifacts directory.' );

rmdir( $export_dir . '/assets/js' );
rmdir( $export_dir . '/assets/css' );
rmdir( $export_dir . '/assets' );
rmdir( $export_dir . '/plugins/readmes' );
rmdir( $export_dir . '/plugins/feature_maps' );
rmdir( $export_dir . '/plugins/templates' );
rmdir( $export_dir . '/plugins' );
rmdir( $export_dir . '/theme/templates' );
rmdir( $export_dir . '/theme' );
rmdir( $export_dir . '/snapshots' );
rmdir( $export_dir . '/media' );
rmdir( $export_dir . '/content' );
rmdir( $export_dir );
rmdir( $base_dir );
rmdir( $test_upload_base );

fwrite( STDOUT, "export_directory_regression: ok\n" );
