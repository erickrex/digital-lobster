<?php
/**
 * Regression checks for exporting per-item content JSON files.
 *
 * Run with:
 * php tests/content_export_regression.php
 */

if ( ! defined( 'WPINC' ) ) {
	define( 'WPINC', 'wp-includes' );
}

require_once dirname( __DIR__ ) . '/includes/trait-error-logger.php';

function trailingslashit( $string ) {
	return rtrim( $string, '/\\' ) . '/';
}

function wp_mkdir_p( $target ) {
	return is_dir( $target ) || mkdir( $target, 0777, true );
}

function current_time( $type, $gmt = 0 ) {
	if ( 'timestamp' === $type || 'U' === $type ) {
		return time();
	}

	if ( 'mysql' === $type ) {
		return gmdate( 'Y-m-d H:i:s' );
	}

	return gmdate( $type ?: 'Y-m-d H:i:s' );
}

function wp_json_encode( $data, $options = 0 ) {
	return json_encode( $data, $options );
}

function do_action( $tag ) {
	return null;
}

function apply_filters( $tag, $value ) {
	return $value;
}

function sanitize_file_name( $filename ) {
	return preg_replace( '/[^a-z0-9\\-_\\.]/', '-', strtolower( (string) $filename ) );
}

require_once dirname( __DIR__ ) . '/includes/class-exporter.php';

function assert_true( $condition, $message ) {
	if ( ! $condition ) {
		fwrite( STDERR, "Assertion failed: {$message}\n" );
		exit( 1 );
	}
}

$export_dir = sys_get_temp_dir() . '/digital_lobster_content_export_' . uniqid();
$results = array(
	'site'    => array(
		'site' => array( 'name' => 'Test Site' ),
	),
	'content' => array(
		'posts'             => array(
			array(
				'id'     => 101,
				'type'   => 'post',
				'slug'   => 'sample-post',
				'title'  => 'Sample Post',
				'status' => 'publish',
			),
		),
		'pages'             => array(
			array(
				'id'     => 202,
				'type'   => 'page',
				'slug'   => 'about-us',
				'title'  => 'About Us',
				'status' => 'publish',
			),
		),
		'custom_post_types' => array(
			'gd_place' => array(
				array(
					'id'     => 303,
					'type'   => 'gd_place',
					'slug'   => 'sample-cafe',
					'title'  => 'Sample Cafe',
					'status' => 'publish',
				),
			),
		),
		'block_usage'       => array(),
	),
);

$exporter = new Digital_Lobster_Exporter_Exporter( $export_dir, $results );
$result   = $exporter->export_all();

assert_true( ! empty( $result['success'] ), 'Exporter should complete successfully.' );
assert_true( file_exists( $export_dir . '/content/post/sample-post.json' ), 'Post JSON should be written under content/post/.' );
assert_true( file_exists( $export_dir . '/content/page/about-us.json' ), 'Page JSON should be written under content/page/.' );
assert_true( file_exists( $export_dir . '/content/gd_place/sample-cafe.json' ), 'CPT JSON should be written under content/gd_place/.' );

$place_data = json_decode( file_get_contents( $export_dir . '/content/gd_place/sample-cafe.json' ), true );
assert_true( is_array( $place_data ), 'Exported content file should contain valid JSON.' );
assert_true( (int) $place_data['id'] === 303, 'Exported content JSON should preserve the content payload.' );

function remove_tree( $path ) {
	if ( ! file_exists( $path ) ) {
		return;
	}
	if ( is_file( $path ) ) {
		unlink( $path );
		return;
	}
	foreach ( scandir( $path ) as $item ) {
		if ( '.' === $item || '..' === $item ) {
			continue;
		}
		remove_tree( $path . DIRECTORY_SEPARATOR . $item );
	}
	rmdir( $path );
}

remove_tree( $export_dir );

fwrite( STDOUT, "content_export_regression: ok\n" );
