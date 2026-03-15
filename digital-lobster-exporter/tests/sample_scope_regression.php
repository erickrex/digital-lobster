<?php
/**
 * Regression checks for scanners that should honor sampled content context.
 *
 * Run with:
 * php tests/sample_scope_regression.php
 */

require_once __DIR__ . '/mocks/wordpress-functions.php';
require_once dirname( __DIR__ ) . '/includes/trait-error-logger.php';
require_once dirname( __DIR__ ) . '/includes/class-security-filters.php';
require_once dirname( __DIR__ ) . '/includes/class-scanner-base.php';

if ( ! defined( 'WPSEO_VERSION' ) ) {
	define( 'WPSEO_VERSION', '23.0' );
}

if ( ! function_exists( 'get_posts' ) ) {
	function get_posts( $args = array() ) {
		global $mock_posts, $test_get_posts_calls;

		$test_get_posts_calls[] = $args;

		$post_types = isset( $args['post_type'] ) ? (array) $args['post_type'] : array();
		$posts      = array_values( $mock_posts );

		if ( empty( $post_types ) ) {
			return $posts;
		}

		return array_values(
			array_filter(
				$posts,
				function( $post ) use ( $post_types ) {
					return in_array( $post->post_type, $post_types, true );
				}
			)
		);
	}
}

if ( ! function_exists( 'wp_make_link_relative' ) ) {
	function wp_make_link_relative( $url ) {
		$parts = parse_url( $url );
		return isset( $parts['path'] ) ? $parts['path'] : '/';
	}
}

if ( ! function_exists( 'get_the_title' ) ) {
	function get_the_title( $post_id ) {
		$post = get_post( $post_id );
		return $post ? $post->post_title : '';
	}
}

require_once dirname( __DIR__ ) . '/includes/scanners/class-seo-full-scanner.php';

/**
 * @param bool   $condition Condition to assert.
 * @param string $message Failure message.
 */
function assert_true( $condition, $message ) {
	if ( ! $condition ) {
		fwrite( STDERR, "Assertion failed: {$message}\n" );
		exit( 1 );
	}
}

global $mock_posts, $test_get_posts_calls;
$mock_posts = array(
	11 => (object) array(
		'ID'           => 11,
		'post_type'    => 'post',
		'post_name'    => 'sample-post',
		'post_title'   => 'Sample Post',
		'post_content' => 'Sample content',
	),
	12 => (object) array(
		'ID'           => 12,
		'post_type'    => 'page',
		'post_name'    => 'sample-page',
		'post_title'   => 'Sample Page',
		'post_content' => 'Sample content',
	),
);

$test_get_posts_calls = array();
$scanner = new Digital_Lobster_Exporter_Seo_Full_Scanner(
	array(
		'context' => array(
			'content' => array(
				'posts'             => array(
					array(
						'id'   => 11,
						'type' => 'post',
					),
				),
				'pages'             => array(),
				'custom_post_types' => array(),
			),
		),
	)
);

$result = $scanner->scan();
assert_true( count( $result['pages'] ) === 1, 'SEO scanner should only process sampled posts when content context exists.' );
assert_true( empty( $test_get_posts_calls ), 'SEO scanner should not query all posts when sampled content is available.' );

$test_get_posts_calls = array();
$fallback_scanner     = new Digital_Lobster_Exporter_Seo_Full_Scanner( array() );
$fallback_result      = $fallback_scanner->scan();

assert_true( count( $fallback_result['pages'] ) === 2, 'SEO scanner fallback should scan available public posts.' );
assert_true( count( $test_get_posts_calls ) === 2, 'SEO scanner fallback should query per post type when no sampled content exists.' );

fwrite( STDOUT, "sample_scope_regression: ok\n" );
