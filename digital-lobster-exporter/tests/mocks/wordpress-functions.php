<?php
/**
 * WordPress Function Mocks for Testing
 *
 * Provides mock implementations of WordPress functions for unit testing.
 *
 * @package Digital_Lobster_Exporter
 */

// Define WPINC constant
if ( ! defined( 'WPINC' ) ) {
	define( 'WPINC', 'wp-includes' );
}

// Define ABSPATH constant
if ( ! defined( 'ABSPATH' ) ) {
	define( 'ABSPATH', '/var/www/html/' );
}

// Define WP_PLUGIN_DIR constant
if ( ! defined( 'WP_PLUGIN_DIR' ) ) {
	define( 'WP_PLUGIN_DIR', ABSPATH . 'wp-content/plugins' );
}

// Global variables for mocking
global $wp_version, $wpdb, $wp_post_types, $wp_taxonomies, $shortcode_tags;
$wp_version = '6.4.2';
$wpdb = new stdClass();
$wpdb->prefix = 'wp_';
$wpdb->options = 'wp_options';
$wpdb->posts = 'wp_posts';
$wpdb->postmeta = 'wp_postmeta';
$wpdb->terms = 'wp_terms';
$wpdb->term_taxonomy = 'wp_term_taxonomy';
$wpdb->term_relationships = 'wp_term_relationships';
$wpdb->termmeta = 'wp_termmeta';

// Mock data storage
global $mock_options, $mock_posts, $mock_postmeta, $mock_terms, $mock_plugins, $mock_themes;
$mock_options = array();
$mock_posts = array();
$mock_postmeta = array();
$mock_terms = array();
$mock_plugins = array();
$mock_themes = array();

/**
 * Mock get_site_url()
 */
function get_site_url() {
	return 'https://example.com';
}

/**
 * Mock get_home_url()
 */
function get_home_url() {
	return 'https://example.com';
}

/**
 * Mock get_bloginfo()
 */
function get_bloginfo( $show = '' ) {
	$info = array(
		'name' => 'Test Site',
		'description' => 'Just another WordPress site',
		'language' => 'en-US',
		'charset' => 'UTF-8',
	);
	
	return isset( $info[ $show ] ) ? $info[ $show ] : '';
}

/**
 * Mock is_multisite()
 */
function is_multisite() {
	return false;
}

/**
 * Mock get_option()
 */
function get_option( $option, $default = false ) {
	global $mock_options;
	return isset( $mock_options[ $option ] ) ? $mock_options[ $option ] : $default;
}

/**
 * Mock get_post_types()
 */
function get_post_types( $args = array(), $output = 'names' ) {
	global $wp_post_types;
	
	if ( empty( $wp_post_types ) ) {
		$wp_post_types = array(
			'post' => (object) array(
				'name' => 'post',
				'label' => 'Posts',
				'labels' => (object) array( 'name' => 'Posts' ),
				'description' => 'Posts',
				'public' => true,
				'hierarchical' => false,
				'has_archive' => true,
				'rewrite' => array( 'slug' => 'blog' ),
				'menu_icon' => 'dashicons-admin-post',
				'show_in_rest' => true,
				'rest_base' => 'posts',
			),
			'page' => (object) array(
				'name' => 'page',
				'label' => 'Pages',
				'labels' => (object) array( 'name' => 'Pages' ),
				'description' => 'Pages',
				'public' => true,
				'hierarchical' => true,
				'has_archive' => false,
				'rewrite' => array( 'slug' => 'page' ),
				'menu_icon' => 'dashicons-admin-page',
				'show_in_rest' => true,
				'rest_base' => 'pages',
			),
		);
	}
	
	if ( $output === 'objects' ) {
		return $wp_post_types;
	}
	
	return array_keys( $wp_post_types );
}

/**
 * Mock get_all_post_type_supports()
 */
function get_all_post_type_supports( $post_type ) {
	return array( 'title', 'editor', 'thumbnail', 'excerpt' );
}

/**
 * Mock get_object_taxonomies()
 */
function get_object_taxonomies( $object, $output = 'names' ) {
	if ( $object === 'post' ) {
		return array( 'category', 'post_tag' );
	}
	return array();
}

/**
 * Mock get_taxonomies()
 */
function get_taxonomies( $args = array(), $output = 'names' ) {
	global $wp_taxonomies;
	
	if ( empty( $wp_taxonomies ) ) {
		$wp_taxonomies = array(
			'category' => (object) array(
				'name' => 'category',
				'label' => 'Categories',
				'labels' => (object) array( 'name' => 'Categories' ),
				'description' => 'Categories',
				'public' => true,
				'hierarchical' => true,
				'rewrite' => array( 'slug' => 'category' ),
				'object_type' => array( 'post' ),
				'show_in_rest' => true,
				'rest_base' => 'categories',
			),
			'post_tag' => (object) array(
				'name' => 'post_tag',
				'label' => 'Tags',
				'labels' => (object) array( 'name' => 'Tags' ),
				'description' => 'Tags',
				'public' => true,
				'hierarchical' => false,
				'rewrite' => array( 'slug' => 'tag' ),
				'object_type' => array( 'post' ),
				'show_in_rest' => true,
				'rest_base' => 'tags',
			),
		);
	}
	
	if ( $output === 'objects' ) {
		return $wp_taxonomies;
	}
	
	return array_keys( $wp_taxonomies );
}

/**
 * Mock wp_count_posts()
 */
function wp_count_posts( $post_type = 'post' ) {
	return (object) array(
		'publish' => 10,
		'private' => 2,
		'draft' => 3,
	);
}

/**
 * Mock wp_get_theme()
 */
function wp_get_theme() {
	global $mock_themes;
	
	if ( empty( $mock_themes ) ) {
		$theme = new stdClass();
		$theme->name = 'Twenty Twenty-Four';
		$theme->version = '1.0';
		$theme->template = 'twentytwentyfour';
		$theme->stylesheet = 'twentytwentyfour';
		
		$theme->get = function( $key ) use ( $theme ) {
			$data = array(
				'Name' => 'Twenty Twenty-Four',
				'Version' => '1.0',
				'Description' => 'A test theme',
				'Author' => 'WordPress',
				'AuthorURI' => 'https://wordpress.org',
				'ThemeURI' => 'https://wordpress.org/themes/twentytwentyfour',
				'Template' => 'twentytwentyfour',
				'TextDomain' => 'twentytwentyfour',
			);
			return isset( $data[ $key ] ) ? $data[ $key ] : '';
		};
		
		$theme->get_template = function() {
			return 'twentytwentyfour';
		};
		
		$theme->get_stylesheet = function() {
			return 'twentytwentyfour';
		};
		
		$theme->get_stylesheet_directory = function() {
			return '/var/www/html/wp-content/themes/twentytwentyfour';
		};
		
		$theme->parent = function() {
			return false;
		};
		
		$theme->get_page_templates = function() {
			return array();
		};
		
		return $theme;
	}
	
	return $mock_themes[0];
}

/**
 * Mock wp_upload_dir()
 */
function wp_upload_dir() {
	return array(
		'path' => '/var/www/html/wp-content/uploads/2024/01',
		'url' => 'https://example.com/wp-content/uploads/2024/01',
		'subdir' => '/2024/01',
		'basedir' => '/var/www/html/wp-content/uploads',
		'baseurl' => 'https://example.com/wp-content/uploads',
		'error' => false,
	);
}

/**
 * Mock trailingslashit()
 */
function trailingslashit( $string ) {
	return rtrim( $string, '/\\' ) . '/';
}

/**
 * Mock wp_mkdir_p()
 */
function wp_mkdir_p( $target ) {
	return true;
}

/**
 * Mock get_plugins()
 */
function get_plugins() {
	return array(
		'akismet/akismet.php' => array(
			'Name' => 'Akismet Anti-Spam',
			'Version' => '5.0',
			'Description' => 'Anti-spam plugin',
			'Author' => 'Automattic',
			'AuthorURI' => 'https://automattic.com',
			'PluginURI' => 'https://akismet.com',
			'TextDomain' => 'akismet',
			'Network' => false,
		),
	);
}

/**
 * Mock current_time()
 */
function current_time( $type, $gmt = 0 ) {
	if ( $type === 'mysql' ) {
		return date( 'Y-m-d H:i:s' );
	}
	return time();
}

/**
 * Mock wp_json_encode()
 */
function wp_json_encode( $data, $options = 0 ) {
	return json_encode( $data, $options );
}

/**
 * Mock parse_blocks()
 */
function parse_blocks( $content ) {
	// Simple mock - return empty array for non-block content
	if ( strpos( $content, '<!-- wp:' ) === false ) {
		return array();
	}
	
	// Return a simple block structure
	return array(
		array(
			'blockName' => 'core/paragraph',
			'attrs' => array(),
			'innerHTML' => '<p>Test content</p>',
			'innerBlocks' => array(),
		),
	);
}

/**
 * Mock get_post()
 */
function get_post( $post_id = null ) {
	global $mock_posts;
	
	if ( isset( $mock_posts[ $post_id ] ) ) {
		return $mock_posts[ $post_id ];
	}
	
	return null;
}

/**
 * Mock get_post_meta()
 */
function get_post_meta( $post_id, $key = '', $single = false ) {
	global $mock_postmeta;
	
	if ( ! isset( $mock_postmeta[ $post_id ] ) ) {
		return $single ? '' : array();
	}
	
	if ( $key ) {
		if ( isset( $mock_postmeta[ $post_id ][ $key ] ) ) {
			return $single ? $mock_postmeta[ $post_id ][ $key ] : array( $mock_postmeta[ $post_id ][ $key ] );
		}
		return $single ? '' : array();
	}
	
	// Return all meta
	$all_meta = array();
	foreach ( $mock_postmeta[ $post_id ] as $meta_key => $meta_value ) {
		$all_meta[ $meta_key ] = array( $meta_value );
	}
	return $all_meta;
}

/**
 * Mock get_terms()
 */
function get_terms( $args = array() ) {
	global $mock_terms;
	
	if ( empty( $mock_terms ) ) {
		return array();
	}
	
	return $mock_terms;
}

/**
 * Mock wp_get_post_terms()
 */
function wp_get_post_terms( $post_id, $taxonomy, $args = array() ) {
	return array( 1, 2 );
}

/**
 * Mock get_term_meta()
 */
function get_term_meta( $term_id, $key = '', $single = false ) {
	return $single ? '' : array();
}

/**
 * Mock taxonomy_exists()
 */
function taxonomy_exists( $taxonomy ) {
	global $wp_taxonomies;
	return isset( $wp_taxonomies[ $taxonomy ] );
}

/**
 * Mock get_taxonomy()
 */
function get_taxonomy( $taxonomy ) {
	global $wp_taxonomies;
	return isset( $wp_taxonomies[ $taxonomy ] ) ? $wp_taxonomies[ $taxonomy ] : false;
}

/**
 * Mock wp_get_attachment_url()
 */
function wp_get_attachment_url( $attachment_id ) {
	return 'https://example.com/wp-content/uploads/2024/01/image-' . $attachment_id . '.jpg';
}

/**
 * Mock attachment_url_to_postid()
 */
function attachment_url_to_postid( $url ) {
	// Extract ID from mock URL pattern
	if ( preg_match( '/image-(\d+)\.jpg/', $url, $matches ) ) {
		return (int) $matches[1];
	}
	return 0;
}

/**
 * Mock get_post_mime_type()
 */
function get_post_mime_type( $post_id ) {
	return 'image/jpeg';
}

/**
 * Mock wp_get_attachment_metadata()
 */
function wp_get_attachment_metadata( $attachment_id ) {
	return array(
		'width' => 1920,
		'height' => 1080,
		'file' => '2024/01/image-' . $attachment_id . '.jpg',
		'sizes' => array(
			'thumbnail' => array(
				'file' => 'image-' . $attachment_id . '-150x150.jpg',
				'width' => 150,
				'height' => 150,
			),
		),
		'image_meta' => array(
			'aperture' => '2.8',
			'camera' => 'Test Camera',
		),
	);
}

/**
 * Mock maybe_unserialize()
 */
function maybe_unserialize( $data ) {
	if ( is_serialized( $data ) ) {
		return @unserialize( $data );
	}
	return $data;
}

/**
 * Mock is_serialized()
 */
function is_serialized( $data ) {
	if ( ! is_string( $data ) ) {
		return false;
	}
	$data = trim( $data );
	if ( 'N;' === $data ) {
		return true;
	}
	if ( ! preg_match( '/^([adObis]):/', $data, $badions ) ) {
		return false;
	}
	return true;
}

/**
 * Mock is_wp_error()
 */
function is_wp_error( $thing ) {
	return ( $thing instanceof WP_Error );
}

/**
 * Mock WP_Error class
 */
class WP_Error {
	public $errors = array();
	
	public function __construct( $code = '', $message = '', $data = '' ) {
		if ( $code ) {
			$this->errors[ $code ] = array( $message );
		}
	}
	
	public function get_error_message() {
		return isset( $this->errors ) ? current( current( $this->errors ) ) : '';
	}
}

/**
 * Mock WP_Query class
 */
class WP_Query {
	public $posts = array();
	public $post_count = 0;
	public $current_post = -1;
	
	public function __construct( $args = array() ) {
		global $mock_posts;
		
		// Simple mock - return mock posts
		$this->posts = array_values( $mock_posts );
		$this->post_count = count( $this->posts );
	}
	
	public function have_posts() {
		return $this->current_post + 1 < $this->post_count;
	}
	
	public function the_post() {
		$this->current_post++;
		if ( isset( $this->posts[ $this->current_post ] ) ) {
			global $post;
			$post = $this->posts[ $this->current_post ];
		}
	}
}

/**
 * Mock wp_reset_postdata()
 */
function wp_reset_postdata() {
	global $post;
	$post = null;
}

/**
 * Mock get_permalink()
 */
function get_permalink( $post_id = 0 ) {
	return 'https://example.com/sample-post/';
}

/**
 * Mock get_userdata()
 */
function get_userdata( $user_id ) {
	$user = new stdClass();
	$user->display_name = 'Test User';
	return $user;
}

/**
 * Mock get_page_template_slug()
 */
function get_page_template_slug( $post_id ) {
	return '';
}

/**
 * Mock get_post_thumbnail_id()
 */
function get_post_thumbnail_id( $post_id ) {
	return 0;
}

/**
 * Mock sanitize_file_name()
 */
function sanitize_file_name( $filename ) {
	return preg_replace( '/[^a-z0-9\-_\.]/', '-', strtolower( $filename ) );
}

/**
 * Mock error_log() - suppress in tests
 */
if ( ! function_exists( 'error_log' ) ) {
	function error_log( $message ) {
		// Suppress in tests
		return true;
	}
}
