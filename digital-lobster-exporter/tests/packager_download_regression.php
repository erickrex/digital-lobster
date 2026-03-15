<?php
/**
 * Regression checks for stateless download link verification.
 *
 * Run with:
 * php tests/packager_download_regression.php
 */

if ( ! defined( 'WPINC' ) ) {
	define( 'WPINC', 'wp-includes' );
}

if ( ! defined( 'HOUR_IN_SECONDS' ) ) {
	define( 'HOUR_IN_SECONDS', 3600 );
}

$test_upload_base = sys_get_temp_dir() . '/digital_lobster_packager_test_' . uniqid();
$test_transients  = array();

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

function set_transient( $key, $value, $expiration ) {
	global $test_transients;
	$test_transients[ $key ] = $value;
	return true;
}

function get_transient( $key ) {
	global $test_transients;
	return isset( $test_transients[ $key ] ) ? $test_transients[ $key ] : false;
}

function admin_url( $path = '' ) {
	return 'https://example.com/wp-admin/' . ltrim( $path, '/' );
}

function add_query_arg( $args, $url ) {
	return $url . '?' . http_build_query( $args, '', '&', PHP_QUERY_RFC3986 );
}

function wp_generate_password( $length = 12, $special_chars = true ) {
	return str_repeat( 'a', $length );
}

function wp_salt( $scheme = '' ) {
	return 'test-salt-' . $scheme;
}

function wp_create_nonce( $action = -1 ) {
	return hash( 'sha256', 'nonce|' . $action );
}

function wp_verify_nonce( $nonce, $action = -1 ) {
	return hash_equals( wp_create_nonce( $action ), (string) $nonce );
}

require_once dirname( __DIR__ ) . '/includes/trait-error-logger.php';
require_once dirname( __DIR__ ) . '/includes/class-packager.php';

function assert_true( $condition, $message ) {
	if ( ! $condition ) {
		fwrite( STDERR, "Assertion failed: {$message}\n" );
		exit( 1 );
	}
}

wp_mkdir_p( $test_upload_base . '/ai_migration_artifacts' );
$zip_filename = 'migration-artifacts-test.zip';
$zip_path     = $test_upload_base . '/ai_migration_artifacts/' . $zip_filename;
file_put_contents( $zip_path, 'zip-test' );

$reflection = new ReflectionClass( 'Digital_Lobster_Exporter_Packager' );
$packager   = $reflection->newInstance();

$zip_filename_property = $reflection->getProperty( 'zip_filename' );
$zip_filename_property->setAccessible( true );
$zip_filename_property->setValue( $packager, $zip_filename );

$zip_path_property = $reflection->getProperty( 'zip_file_path' );
$zip_path_property->setAccessible( true );
$zip_path_property->setValue( $packager, $zip_path );

$download_url = $packager->generate_download_url();
parse_str( parse_url( $download_url, PHP_URL_QUERY ), $query );

$verified = $packager->verify_download_request( $query );
assert_true( is_array( $verified ), 'Signed download request should verify successfully.' );
assert_true( $verified['zip_filename'] === $zip_filename, 'Verified download should resolve the expected ZIP filename.' );

$query['signature'] = 'broken';
assert_true( false === $packager->verify_download_request( $query ), 'Tampered signature must be rejected.' );

unlink( $zip_path );
rmdir( dirname( $zip_path ) );
rmdir( $test_upload_base );

fwrite( STDOUT, "packager_download_regression: ok\n" );
