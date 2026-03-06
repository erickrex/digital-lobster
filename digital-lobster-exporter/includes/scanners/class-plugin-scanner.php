<?php
/**
 * Plugin Scanner Class
 *
 * Collects comprehensive plugin information including installed plugins,
 * active status, versions, README files, behavioral fingerprints,
 * registered custom post types, taxonomies, shortcodes, blocks,
 * and database tables created by plugins.
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Plugin Scanner Class
 */
class Digital_Lobster_Exporter_Plugin_Scanner {

	/**
	 * Export directory path.
	 *
	 * @var string
	 */
	private $export_dir;

	/**
	 * Plugins directory path in export.
	 *
	 * @var string
	 */
	private $plugins_export_dir;

	/**
	 * List of all plugins.
	 *
	 * @var array
	 */
	private $all_plugins = array();

	/**
	 * List of active plugins.
	 *
	 * @var array
	 */
	private $active_plugins = array();

	/**
	 * Constructor.
	 */
	public function __construct() {
		$this->setup_export_directories();
		$this->load_plugin_data();
	}

	/**
	 * Setup export directories.
	 */
	private function setup_export_directories() {
		$upload_dir = wp_upload_dir();
		$this->export_dir = trailingslashit( $upload_dir['basedir'] ) . 'ai_migration_artifacts/';
		$this->plugins_export_dir = $this->export_dir . 'plugins/';
	}

	/**
	 * Load plugin data.
	 */
	private function load_plugin_data() {
		if ( ! function_exists( 'get_plugins' ) ) {
			require_once ABSPATH . 'wp-admin/includes/plugin.php';
		}

		$this->all_plugins = get_plugins();
		$this->active_plugins = get_option( 'active_plugins', array() );
	}

	/**
	 * Scan and collect plugin information.
	 *
	 * @return array Plugin information and export results.
	 */
	public function scan() {
		// Create plugins export directory
		$this->create_export_directories();

		$plugins_list = $this->collect_plugins_list();
		$readme_exports = $this->export_readme_files();
		$behavioral_fingerprints = $this->create_behavioral_fingerprints();
		$custom_post_types = $this->document_custom_post_types();
		$taxonomies = $this->document_taxonomies();
		$shortcodes = $this->document_shortcodes();
		$blocks = $this->document_blocks();
		$database_tables = $this->identify_database_tables();
		$enhanced_detection = $this->detect_known_plugins();
		$template_exports = $this->export_plugin_templates();

		return array(
			'plugins_list'            => $plugins_list,
			'readme_exports'          => $readme_exports,
			'behavioral_fingerprints' => $behavioral_fingerprints,
			'custom_post_types'       => $custom_post_types,
			'taxonomies'              => $taxonomies,
			'shortcodes'              => $shortcodes,
			'blocks'                  => $blocks,
			'database_tables'         => $database_tables,
			'enhanced_detection'      => $enhanced_detection,
			'template_exports'        => $template_exports,
		);
	}

	/**
	 * Create export directories if they don't exist.
	 */
	private function create_export_directories() {
		$directories = array(
			$this->plugins_export_dir,
			$this->plugins_export_dir . 'readmes/',
			$this->plugins_export_dir . 'feature_maps/',
			$this->plugins_export_dir . 'templates/',
		);

		foreach ( $directories as $dir ) {
			if ( ! file_exists( $dir ) ) {
				wp_mkdir_p( $dir );
			}
		}
	}

	/**
	 * Collect list of all installed plugins with metadata.
	 *
	 * @return array Plugins list with metadata.
	 */
	private function collect_plugins_list() {
		$plugins_data = array();

		foreach ( $this->all_plugins as $plugin_file => $plugin_data ) {
			$is_active = in_array( $plugin_file, $this->active_plugins, true );
			$plugin_slug = dirname( $plugin_file );
			
			// Handle single-file plugins
			if ( $plugin_slug === '.' ) {
				$plugin_slug = basename( $plugin_file, '.php' );
			}

			$plugins_data[] = array(
				'file'        => $plugin_file,
				'slug'        => $plugin_slug,
				'name'        => $plugin_data['Name'],
				'version'     => $plugin_data['Version'],
				'description' => $plugin_data['Description'],
				'author'      => $plugin_data['Author'],
				'author_uri'  => $plugin_data['AuthorURI'],
				'plugin_uri'  => $plugin_data['PluginURI'],
				'text_domain' => $plugin_data['TextDomain'],
				'network'     => $plugin_data['Network'],
				'active'      => $is_active,
			);
		}

		return array(
			'total_count'  => count( $plugins_data ),
			'active_count' => count( $this->active_plugins ),
			'plugins'      => $plugins_data,
		);
	}

	/**
	 * Export README.txt files for all plugins.
	 *
	 * @return array Export status with list of exported READMEs.
	 */
	private function export_readme_files() {
		$exported_readmes = array();
		$readmes_dir = $this->plugins_export_dir . 'readmes/';

		foreach ( $this->all_plugins as $plugin_file => $plugin_data ) {
			$plugin_slug = dirname( $plugin_file );
			
			// Handle single-file plugins
			if ( $plugin_slug === '.' ) {
				$plugin_slug = basename( $plugin_file, '.php' );
			}

			$plugin_dir = WP_PLUGIN_DIR . '/' . $plugin_slug;
			
			// Look for README files (case-insensitive)
			$readme_files = array( 'readme.txt', 'README.txt', 'readme.md', 'README.md' );
			$readme_found = false;

			foreach ( $readme_files as $readme_file ) {
				$readme_path = $plugin_dir . '/' . $readme_file;
				
				if ( file_exists( $readme_path ) ) {
					$destination = $readmes_dir . $plugin_slug . '_' . $readme_file;
					
					if ( copy( $readme_path, $destination ) ) {
						$exported_readmes[] = array(
							'plugin_slug' => $plugin_slug,
							'plugin_name' => $plugin_data['Name'],
							'readme_file' => $readme_file,
							'path'        => 'plugins/readmes/' . $plugin_slug . '_' . $readme_file,
						);
						$readme_found = true;
						break; // Only export the first README found
					}
				}
			}

			if ( ! $readme_found ) {
				$exported_readmes[] = array(
					'plugin_slug' => $plugin_slug,
					'plugin_name' => $plugin_data['Name'],
					'readme_file' => null,
					'message'     => 'No README file found',
				);
			}
		}

		return array(
			'success'        => true,
			'exported_count' => count( array_filter( $exported_readmes, function( $item ) {
				return isset( $item['path'] );
			} ) ),
			'readmes'        => $exported_readmes,
		);
	}

	/**
	 * Create behavioral fingerprints for plugins.
	 *
	 * @return array Behavioral fingerprints data.
	 */
	private function create_behavioral_fingerprints() {
		$fingerprints = array();

		foreach ( $this->all_plugins as $plugin_file => $plugin_data ) {
			$plugin_slug = dirname( $plugin_file );
			
			// Handle single-file plugins
			if ( $plugin_slug === '.' ) {
				$plugin_slug = basename( $plugin_file, '.php' );
			}

			$is_active = in_array( $plugin_file, $this->active_plugins, true );

			$fingerprint = array(
				'plugin_slug'       => $plugin_slug,
				'plugin_name'       => $plugin_data['Name'],
				'version'           => $plugin_data['Version'],
				'active'            => $is_active,
				'features'          => array(),
			);

			// Only collect detailed features for active plugins
			if ( $is_active ) {
				$fingerprint['features'] = $this->collect_plugin_features( $plugin_slug, $plugin_file );
			}

			$fingerprints[] = $fingerprint;
		}

		// Save fingerprints to JSON file
		$fingerprints_data = array(
			'schema_version' => 1,
			'scan_date'      => current_time( 'mysql' ),
			'plugins_count'  => count( $fingerprints ),
			'fingerprints'   => $fingerprints,
		);

		$json = wp_json_encode( $fingerprints_data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES );
		if ( $json ) {
			file_put_contents( $this->plugins_export_dir . 'plugins_fingerprint.json', $json );
		}

		return array(
			'success' => true,
			'count'   => count( $fingerprints ),
			'path'    => 'plugins/plugins_fingerprint.json',
		);
	}

	/**
	 * Collect features for a specific plugin.
	 *
	 * @param string $plugin_slug Plugin slug.
	 * @param string $plugin_file Plugin file path.
	 * @return array Plugin features.
	 */
	private function collect_plugin_features( $plugin_slug, $plugin_file ) {
		$features = array();

		// Check for common plugin capabilities
		$features['has_settings_page'] = $this->plugin_has_settings_page( $plugin_slug );
		$features['has_admin_menu'] = $this->plugin_has_admin_menu( $plugin_slug );
		$features['has_widgets'] = $this->plugin_has_widgets( $plugin_slug );
		$features['has_rest_api'] = $this->plugin_has_rest_api( $plugin_slug );
		$features['has_cron_jobs'] = $this->plugin_has_cron_jobs( $plugin_slug );

		// Check for specific plugin types
		$features['plugin_type'] = $this->detect_plugin_type( $plugin_slug );

		// Get plugin options from database
		$features['options'] = $this->get_plugin_options( $plugin_slug );

		return $features;
	}

	/**
	 * Check if plugin has a settings page.
	 *
	 * @param string $plugin_slug Plugin slug.
	 * @return bool True if has settings page.
	 */
	private function plugin_has_settings_page( $plugin_slug ) {
		global $submenu;
		
		if ( ! isset( $submenu['options-general.php'] ) ) {
			return false;
		}

		foreach ( $submenu['options-general.php'] as $item ) {
			if ( strpos( $item[2], $plugin_slug ) !== false ) {
				return true;
			}
		}

		return false;
	}

	/**
	 * Check if plugin has an admin menu.
	 *
	 * @param string $plugin_slug Plugin slug.
	 * @return bool True if has admin menu.
	 */
	private function plugin_has_admin_menu( $plugin_slug ) {
		global $menu;

		if ( ! is_array( $menu ) ) {
			return false;
		}

		foreach ( $menu as $item ) {
			if ( isset( $item[2] ) && strpos( $item[2], $plugin_slug ) !== false ) {
				return true;
			}
		}

		return false;
	}

	/**
	 * Check if plugin registers widgets.
	 *
	 * @param string $plugin_slug Plugin slug.
	 * @return bool True if has widgets.
	 */
	private function plugin_has_widgets( $plugin_slug ) {
		global $wp_widget_factory;

		if ( ! isset( $wp_widget_factory->widgets ) ) {
			return false;
		}

		foreach ( $wp_widget_factory->widgets as $widget ) {
			$widget_class = get_class( $widget );
			if ( strpos( strtolower( $widget_class ), str_replace( '-', '_', $plugin_slug ) ) !== false ) {
				return true;
			}
		}

		return false;
	}

	/**
	 * Check if plugin has REST API endpoints.
	 *
	 * @param string $plugin_slug Plugin slug.
	 * @return bool True if has REST API endpoints.
	 */
	private function plugin_has_rest_api( $plugin_slug ) {
		$rest_server = rest_get_server();
		$namespaces = $rest_server->get_namespaces();

		$plugin_namespace = str_replace( '-', '_', $plugin_slug );

		foreach ( $namespaces as $namespace ) {
			if ( strpos( $namespace, $plugin_namespace ) !== false || strpos( $namespace, $plugin_slug ) !== false ) {
				return true;
			}
		}

		return false;
	}

	/**
	 * Check if plugin has cron jobs.
	 *
	 * @param string $plugin_slug Plugin slug.
	 * @return bool True if has cron jobs.
	 */
	private function plugin_has_cron_jobs( $plugin_slug ) {
		$cron_jobs = _get_cron_array();

		if ( ! is_array( $cron_jobs ) ) {
			return false;
		}

		$plugin_identifier = str_replace( '-', '_', $plugin_slug );

		foreach ( $cron_jobs as $timestamp => $cron ) {
			foreach ( $cron as $hook => $details ) {
				if ( strpos( $hook, $plugin_identifier ) !== false || strpos( $hook, $plugin_slug ) !== false ) {
					return true;
				}
			}
		}

		return false;
	}

	/**
	 * Detect plugin type based on common patterns.
	 *
	 * @param string $plugin_slug Plugin slug.
	 * @return string Plugin type.
	 */
	private function detect_plugin_type( $plugin_slug ) {
		$types = array();

		// Check for common plugin types
		if ( strpos( $plugin_slug, 'seo' ) !== false || strpos( $plugin_slug, 'yoast' ) !== false ) {
			$types[] = 'seo';
		}

		if ( strpos( $plugin_slug, 'cache' ) !== false || strpos( $plugin_slug, 'speed' ) !== false ) {
			$types[] = 'performance';
		}

		if ( strpos( $plugin_slug, 'security' ) !== false || strpos( $plugin_slug, 'firewall' ) !== false ) {
			$types[] = 'security';
		}

		if ( strpos( $plugin_slug, 'form' ) !== false || strpos( $plugin_slug, 'contact' ) !== false ) {
			$types[] = 'forms';
		}

		if ( strpos( $plugin_slug, 'backup' ) !== false ) {
			$types[] = 'backup';
		}

		if ( strpos( $plugin_slug, 'ecommerce' ) !== false || strpos( $plugin_slug, 'woocommerce' ) !== false || strpos( $plugin_slug, 'shop' ) !== false ) {
			$types[] = 'ecommerce';
		}

		if ( strpos( $plugin_slug, 'social' ) !== false || strpos( $plugin_slug, 'share' ) !== false ) {
			$types[] = 'social';
		}

		if ( strpos( $plugin_slug, 'gallery' ) !== false || strpos( $plugin_slug, 'image' ) !== false ) {
			$types[] = 'media';
		}

		return ! empty( $types ) ? implode( ', ', $types ) : 'general';
	}

	/**
	 * Get plugin options from database.
	 *
	 * @param string $plugin_slug Plugin slug.
	 * @return array Plugin options.
	 */
	private function get_plugin_options( $plugin_slug ) {
		global $wpdb;

		$plugin_identifier = str_replace( '-', '_', $plugin_slug );
		
		// Query for options that match the plugin slug
		$options = $wpdb->get_results(
			$wpdb->prepare(
				"SELECT option_name FROM {$wpdb->options} 
				WHERE option_name LIKE %s 
				OR option_name LIKE %s
				LIMIT 20",
				$wpdb->esc_like( $plugin_slug ) . '%',
				$wpdb->esc_like( $plugin_identifier ) . '%'
			)
		);

		$option_names = array();
		if ( $options ) {
			foreach ( $options as $option ) {
				$option_names[] = $option->option_name;
			}
		}

		return $option_names;
	}

	/**
	 * Document custom post types registered by each plugin.
	 *
	 * @return array Custom post types by plugin.
	 */
	private function document_custom_post_types() {
		global $wp_post_types;

		$plugin_post_types = array();

		// Get all registered post types
		foreach ( $wp_post_types as $post_type_name => $post_type_obj ) {
			// Skip built-in WordPress post types
			if ( in_array( $post_type_name, array( 'post', 'page', 'attachment', 'revision', 'nav_menu_item', 'custom_css', 'customize_changeset', 'oembed_cache', 'user_request', 'wp_block', 'wp_template', 'wp_template_part', 'wp_global_styles', 'wp_navigation' ), true ) ) {
				continue;
			}

			// Try to identify which plugin registered this post type
			$plugin_slug = $this->identify_plugin_for_post_type( $post_type_name, $post_type_obj );

			if ( ! isset( $plugin_post_types[ $plugin_slug ] ) ) {
				$plugin_post_types[ $plugin_slug ] = array();
			}

			$plugin_post_types[ $plugin_slug ][] = array(
				'name'         => $post_type_name,
				'label'        => $post_type_obj->label,
				'labels'       => (array) $post_type_obj->labels,
				'public'       => $post_type_obj->public,
				'hierarchical' => $post_type_obj->hierarchical,
				'has_archive'  => $post_type_obj->has_archive,
				'rewrite'      => $post_type_obj->rewrite,
				'supports'     => get_all_post_type_supports( $post_type_name ),
				'taxonomies'   => get_object_taxonomies( $post_type_name ),
			);
		}

		// Save to JSON file
		$cpt_data = array(
			'schema_version'     => 1,
			'scan_date'          => current_time( 'mysql' ),
			'total_cpts'         => array_sum( array_map( 'count', $plugin_post_types ) ),
			'post_types_by_plugin' => $plugin_post_types,
		);

		$json = wp_json_encode( $cpt_data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES );
		if ( $json ) {
			file_put_contents( $this->plugins_export_dir . 'custom_post_types.json', $json );
		}

		return array(
			'success'    => true,
			'total_cpts' => array_sum( array_map( 'count', $plugin_post_types ) ),
			'by_plugin'  => $plugin_post_types,
			'path'       => 'plugins/custom_post_types.json',
		);
	}

	/**
	 * Identify which plugin registered a post type.
	 *
	 * @param string $post_type_name Post type name.
	 * @param object $post_type_obj Post type object.
	 * @return string Plugin slug or 'unknown'.
	 */
	private function identify_plugin_for_post_type( $post_type_name, $post_type_obj ) {
		// Check if post type name contains a known plugin identifier
		foreach ( $this->all_plugins as $plugin_file => $plugin_data ) {
			$plugin_slug = dirname( $plugin_file );
			
			if ( $plugin_slug === '.' ) {
				$plugin_slug = basename( $plugin_file, '.php' );
			}

			$plugin_identifier = str_replace( '-', '_', $plugin_slug );

			// Check if post type name starts with plugin identifier
			if ( strpos( $post_type_name, $plugin_identifier ) === 0 || strpos( $post_type_name, $plugin_slug ) === 0 ) {
				return $plugin_slug;
			}

			// Check if post type name contains plugin slug
			if ( strpos( $post_type_name, $plugin_slug ) !== false ) {
				return $plugin_slug;
			}
		}

		// Check if it's a theme-registered post type
		if ( isset( $post_type_obj->_edit_link ) && strpos( $post_type_obj->_edit_link, 'theme' ) !== false ) {
			return 'theme';
		}

		return 'unknown';
	}

	/**
	 * Document taxonomies registered by each plugin.
	 *
	 * @return array Taxonomies by plugin.
	 */
	private function document_taxonomies() {
		global $wp_taxonomies;

		$plugin_taxonomies = array();

		// Get all registered taxonomies
		foreach ( $wp_taxonomies as $taxonomy_name => $taxonomy_obj ) {
			// Skip built-in WordPress taxonomies
			if ( in_array( $taxonomy_name, array( 'category', 'post_tag', 'nav_menu', 'link_category', 'post_format' ), true ) ) {
				continue;
			}

			// Try to identify which plugin registered this taxonomy
			$plugin_slug = $this->identify_plugin_for_taxonomy( $taxonomy_name, $taxonomy_obj );

			if ( ! isset( $plugin_taxonomies[ $plugin_slug ] ) ) {
				$plugin_taxonomies[ $plugin_slug ] = array();
			}

			$plugin_taxonomies[ $plugin_slug ][] = array(
				'name'         => $taxonomy_name,
				'label'        => $taxonomy_obj->label,
				'labels'       => (array) $taxonomy_obj->labels,
				'public'       => $taxonomy_obj->public,
				'hierarchical' => $taxonomy_obj->hierarchical,
				'rewrite'      => $taxonomy_obj->rewrite,
				'object_types' => $taxonomy_obj->object_type,
			);
		}

		// Save to JSON file
		$taxonomy_data = array(
			'schema_version'        => 1,
			'scan_date'             => current_time( 'mysql' ),
			'total_taxonomies'      => array_sum( array_map( 'count', $plugin_taxonomies ) ),
			'taxonomies_by_plugin'  => $plugin_taxonomies,
		);

		$json = wp_json_encode( $taxonomy_data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES );
		if ( $json ) {
			file_put_contents( $this->plugins_export_dir . 'taxonomies.json', $json );
		}

		return array(
			'success'          => true,
			'total_taxonomies' => array_sum( array_map( 'count', $plugin_taxonomies ) ),
			'by_plugin'        => $plugin_taxonomies,
			'path'             => 'plugins/taxonomies.json',
		);
	}

	/**
	 * Identify which plugin registered a taxonomy.
	 *
	 * @param string $taxonomy_name Taxonomy name.
	 * @param object $taxonomy_obj Taxonomy object.
	 * @return string Plugin slug or 'unknown'.
	 */
	private function identify_plugin_for_taxonomy( $taxonomy_name, $taxonomy_obj ) {
		// Check if taxonomy name contains a known plugin identifier
		foreach ( $this->all_plugins as $plugin_file => $plugin_data ) {
			$plugin_slug = dirname( $plugin_file );
			
			if ( $plugin_slug === '.' ) {
				$plugin_slug = basename( $plugin_file, '.php' );
			}

			$plugin_identifier = str_replace( '-', '_', $plugin_slug );

			// Check if taxonomy name starts with plugin identifier
			if ( strpos( $taxonomy_name, $plugin_identifier ) === 0 || strpos( $taxonomy_name, $plugin_slug ) === 0 ) {
				return $plugin_slug;
			}

			// Check if taxonomy name contains plugin slug
			if ( strpos( $taxonomy_name, $plugin_slug ) !== false ) {
				return $plugin_slug;
			}
		}

		return 'unknown';
	}

	/**
	 * Document shortcodes registered by each plugin.
	 *
	 * @return array Shortcodes by plugin.
	 */
	private function document_shortcodes() {
		global $shortcode_tags;

		$plugin_shortcodes = array();

		if ( ! is_array( $shortcode_tags ) || empty( $shortcode_tags ) ) {
			return array(
				'success' => false,
				'message' => 'No shortcodes registered',
			);
		}

		// Get all registered shortcodes
		foreach ( $shortcode_tags as $shortcode_tag => $callback ) {
			// Try to identify which plugin registered this shortcode
			$plugin_slug = $this->identify_plugin_for_shortcode( $shortcode_tag, $callback );

			if ( ! isset( $plugin_shortcodes[ $plugin_slug ] ) ) {
				$plugin_shortcodes[ $plugin_slug ] = array();
			}

			$callback_info = $this->get_callback_info( $callback );

			$plugin_shortcodes[ $plugin_slug ][] = array(
				'tag'      => $shortcode_tag,
				'callback' => $callback_info,
			);
		}

		// Save to JSON file
		$shortcodes_data = array(
			'schema_version'       => 1,
			'scan_date'            => current_time( 'mysql' ),
			'total_shortcodes'     => array_sum( array_map( 'count', $plugin_shortcodes ) ),
			'shortcodes_by_plugin' => $plugin_shortcodes,
		);

		$json = wp_json_encode( $shortcodes_data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES );
		if ( $json ) {
			file_put_contents( $this->plugins_export_dir . 'shortcodes.json', $json );
		}

		return array(
			'success'          => true,
			'total_shortcodes' => array_sum( array_map( 'count', $plugin_shortcodes ) ),
			'by_plugin'        => $plugin_shortcodes,
			'path'             => 'plugins/shortcodes.json',
		);
	}

	/**
	 * Identify which plugin registered a shortcode.
	 *
	 * @param string $shortcode_tag Shortcode tag.
	 * @param mixed  $callback Shortcode callback.
	 * @return string Plugin slug or 'unknown'.
	 */
	private function identify_plugin_for_shortcode( $shortcode_tag, $callback ) {
		// Try to get the callback source
		$callback_info = $this->get_callback_info( $callback );

		// Check if callback contains plugin path
		if ( isset( $callback_info['file'] ) && strpos( $callback_info['file'], WP_PLUGIN_DIR ) !== false ) {
			$relative_path = str_replace( WP_PLUGIN_DIR . '/', '', $callback_info['file'] );
			$plugin_slug = explode( '/', $relative_path )[0];
			return $plugin_slug;
		}

		// Check if shortcode tag contains a known plugin identifier
		foreach ( $this->all_plugins as $plugin_file => $plugin_data ) {
			$plugin_slug = dirname( $plugin_file );
			
			if ( $plugin_slug === '.' ) {
				$plugin_slug = basename( $plugin_file, '.php' );
			}

			$plugin_identifier = str_replace( '-', '_', $plugin_slug );

			// Check if shortcode tag starts with plugin identifier
			if ( strpos( $shortcode_tag, $plugin_identifier ) === 0 || strpos( $shortcode_tag, $plugin_slug ) === 0 ) {
				return $plugin_slug;
			}

			// Check if shortcode tag contains plugin slug
			if ( strpos( $shortcode_tag, $plugin_slug ) !== false ) {
				return $plugin_slug;
			}
		}

		// Check if it's a theme shortcode
		if ( isset( $callback_info['file'] ) && strpos( $callback_info['file'], get_template_directory() ) !== false ) {
			return 'theme';
		}

		return 'unknown';
	}

	/**
	 * Get callback information.
	 *
	 * @param mixed $callback Callback function.
	 * @return array Callback information.
	 */
	private function get_callback_info( $callback ) {
		$info = array();

		if ( is_string( $callback ) ) {
			$info['type'] = 'function';
			$info['name'] = $callback;

			if ( function_exists( $callback ) ) {
				$reflection = new ReflectionFunction( $callback );
				$info['file'] = $reflection->getFileName();
				$info['line'] = $reflection->getStartLine();
			}
		} elseif ( is_array( $callback ) && count( $callback ) === 2 ) {
			$info['type'] = 'method';
			
			if ( is_object( $callback[0] ) ) {
				$info['class'] = get_class( $callback[0] );
			} elseif ( is_string( $callback[0] ) ) {
				$info['class'] = $callback[0];
			}
			
			$info['method'] = $callback[1];

			if ( isset( $info['class'] ) && method_exists( $info['class'], $info['method'] ) ) {
				$reflection = new ReflectionMethod( $info['class'], $info['method'] );
				$info['file'] = $reflection->getFileName();
				$info['line'] = $reflection->getStartLine();
			}
		} elseif ( is_object( $callback ) && ( $callback instanceof Closure ) ) {
			$info['type'] = 'closure';
			$reflection = new ReflectionFunction( $callback );
			$info['file'] = $reflection->getFileName();
			$info['line'] = $reflection->getStartLine();
		} else {
			$info['type'] = 'unknown';
		}

		return $info;
	}

	/**
	 * Document blocks registered by each plugin.
	 *
	 * @return array Blocks by plugin.
	 */
	private function document_blocks() {
		$plugin_blocks = array();

		// Get all registered blocks
		if ( function_exists( 'WP_Block_Type_Registry::get_instance' ) ) {
			$block_registry = WP_Block_Type_Registry::get_instance();
			$registered_blocks = $block_registry->get_all_registered();

			foreach ( $registered_blocks as $block_name => $block_type ) {
				// Skip core blocks
				if ( strpos( $block_name, 'core/' ) === 0 ) {
					continue;
				}

				// Try to identify which plugin registered this block
				$plugin_slug = $this->identify_plugin_for_block( $block_name, $block_type );

				if ( ! isset( $plugin_blocks[ $plugin_slug ] ) ) {
					$plugin_blocks[ $plugin_slug ] = array();
				}

				$block_info = array(
					'name'        => $block_name,
					'title'       => isset( $block_type->title ) ? $block_type->title : '',
					'description' => isset( $block_type->description ) ? $block_type->description : '',
					'category'    => isset( $block_type->category ) ? $block_type->category : '',
					'icon'        => isset( $block_type->icon ) ? $block_type->icon : '',
					'keywords'    => isset( $block_type->keywords ) ? $block_type->keywords : array(),
					'supports'    => isset( $block_type->supports ) ? $block_type->supports : array(),
					'attributes'  => isset( $block_type->attributes ) ? array_keys( $block_type->attributes ) : array(),
				);

				$plugin_blocks[ $plugin_slug ][] = $block_info;
			}
		}

		if ( empty( $plugin_blocks ) ) {
			return array(
				'success' => false,
				'message' => 'No custom blocks registered',
			);
		}

		// Save to JSON file
		$blocks_data = array(
			'schema_version'   => 1,
			'scan_date'        => current_time( 'mysql' ),
			'total_blocks'     => array_sum( array_map( 'count', $plugin_blocks ) ),
			'blocks_by_plugin' => $plugin_blocks,
		);

		$json = wp_json_encode( $blocks_data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES );
		if ( $json ) {
			file_put_contents( $this->plugins_export_dir . 'blocks.json', $json );
		}

		return array(
			'success'      => true,
			'total_blocks' => array_sum( array_map( 'count', $plugin_blocks ) ),
			'by_plugin'    => $plugin_blocks,
			'path'         => 'plugins/blocks.json',
		);
	}

	/**
	 * Identify which plugin registered a block.
	 *
	 * @param string $block_name Block name.
	 * @param object $block_type Block type object.
	 * @return string Plugin slug or 'unknown'.
	 */
	private function identify_plugin_for_block( $block_name, $block_type ) {
		// Extract namespace from block name (e.g., 'kadence/rowlayout' -> 'kadence')
		$namespace = explode( '/', $block_name )[0];

		// Check if namespace matches a known plugin
		foreach ( $this->all_plugins as $plugin_file => $plugin_data ) {
			$plugin_slug = dirname( $plugin_file );
			
			if ( $plugin_slug === '.' ) {
				$plugin_slug = basename( $plugin_file, '.php' );
			}

			// Check if namespace matches plugin slug
			if ( $namespace === $plugin_slug || $namespace === str_replace( '-', '', $plugin_slug ) ) {
				return $plugin_slug;
			}

			// Check if plugin slug contains namespace
			if ( strpos( $plugin_slug, $namespace ) !== false ) {
				return $plugin_slug;
			}
		}

		// Check if it's a theme block
		if ( strpos( $block_name, get_template() ) !== false ) {
			return 'theme';
		}

		return $namespace;
	}

	/**
	 * Identify database tables created by plugins.
	 *
	 * @return array Database tables by plugin.
	 */
	private function identify_database_tables() {
		global $wpdb;

		// Get all tables in the database
		$all_tables = $wpdb->get_col( 'SHOW TABLES' );

		// Standard WordPress tables
		$wp_core_tables = array(
			$wpdb->prefix . 'commentmeta',
			$wpdb->prefix . 'comments',
			$wpdb->prefix . 'links',
			$wpdb->prefix . 'options',
			$wpdb->prefix . 'postmeta',
			$wpdb->prefix . 'posts',
			$wpdb->prefix . 'term_relationships',
			$wpdb->prefix . 'term_taxonomy',
			$wpdb->prefix . 'termmeta',
			$wpdb->prefix . 'terms',
			$wpdb->prefix . 'usermeta',
			$wpdb->prefix . 'users',
		);

		// Filter out core tables
		$custom_tables = array_diff( $all_tables, $wp_core_tables );

		$plugin_tables = array();

		foreach ( $custom_tables as $table_name ) {
			// Try to identify which plugin created this table
			$plugin_slug = $this->identify_plugin_for_table( $table_name );

			if ( ! isset( $plugin_tables[ $plugin_slug ] ) ) {
				$plugin_tables[ $plugin_slug ] = array();
			}

			// Get table structure
			$table_structure = $wpdb->get_results( "DESCRIBE {$table_name}" );
			
			$columns = array();
			foreach ( $table_structure as $column ) {
				$columns[] = array(
					'field'   => $column->Field,
					'type'    => $column->Type,
					'null'    => $column->Null,
					'key'     => $column->Key,
					'default' => $column->Default,
					'extra'   => $column->Extra,
				);
			}

			// Get row count
			$row_count = $wpdb->get_var( "SELECT COUNT(*) FROM {$table_name}" );

			$plugin_tables[ $plugin_slug ][] = array(
				'table_name' => $table_name,
				'columns'    => $columns,
				'row_count'  => (int) $row_count,
			);
		}

		// Save to JSON file
		$tables_data = array(
			'schema_version'   => 1,
			'scan_date'        => current_time( 'mysql' ),
			'total_tables'     => count( $custom_tables ),
			'tables_by_plugin' => $plugin_tables,
		);

		$json = wp_json_encode( $tables_data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES );
		if ( $json ) {
			file_put_contents( $this->plugins_export_dir . 'database_tables.json', $json );
		}

		return array(
			'success'      => true,
			'total_tables' => count( $custom_tables ),
			'by_plugin'    => $plugin_tables,
			'path'         => 'plugins/database_tables.json',
		);
	}

	/**
	 * Identify which plugin created a database table.
	 *
	 * @param string $table_name Table name.
	 * @return string Plugin slug or 'unknown'.
	 */
	private function identify_plugin_for_table( $table_name ) {
		global $wpdb;

		// Remove WordPress prefix
		$table_without_prefix = str_replace( $wpdb->prefix, '', $table_name );

		// Check if table name contains a known plugin identifier
		foreach ( $this->all_plugins as $plugin_file => $plugin_data ) {
			$plugin_slug = dirname( $plugin_file );
			
			if ( $plugin_slug === '.' ) {
				$plugin_slug = basename( $plugin_file, '.php' );
			}

			$plugin_identifier = str_replace( '-', '_', $plugin_slug );

			// Check if table name starts with plugin identifier
			if ( strpos( $table_without_prefix, $plugin_identifier ) === 0 || strpos( $table_without_prefix, $plugin_slug ) === 0 ) {
				return $plugin_slug;
			}

			// Check if table name contains plugin slug
			if ( strpos( $table_without_prefix, $plugin_slug ) !== false || strpos( $table_without_prefix, $plugin_identifier ) !== false ) {
				return $plugin_slug;
			}
		}

		return 'unknown';
	}

	/**
	 * Detect known plugins and create detailed feature maps.
	 *
	 * @return array Enhanced detection results.
	 */
	private function detect_known_plugins() {
		$known_plugins = array();

		// Detect GeoDirectory
		$geodirectory = $this->detect_geodirectory();
		if ( $geodirectory ) {
			$known_plugins['geodirectory'] = $geodirectory;
		}

		// Detect Advanced Custom Fields (ACF)
		$acf = $this->detect_acf();
		if ( $acf ) {
			$known_plugins['acf'] = $acf;
		}

		// Detect Kadence Blocks
		$kadence = $this->detect_kadence_blocks();
		if ( $kadence ) {
			$known_plugins['kadence-blocks'] = $kadence;
		}

		// Save feature maps to individual JSON files
		foreach ( $known_plugins as $plugin_slug => $feature_map ) {
			$json = wp_json_encode( $feature_map, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES );
			if ( $json ) {
				file_put_contents( 
					$this->plugins_export_dir . 'feature_maps/' . $plugin_slug . '.json', 
					$json 
				);
			}
		}

		return array(
			'success'       => true,
			'detected'      => array_keys( $known_plugins ),
			'feature_maps'  => $known_plugins,
			'path'          => 'plugins/feature_maps/',
		);
	}

	/**
	 * Detect GeoDirectory plugin and identify all its custom post types dynamically.
	 *
	 * @return array|null GeoDirectory feature map or null if not detected.
	 */
	private function detect_geodirectory() {
		// Check if GeoDirectory is installed and active
		$geodir_plugin = null;
		foreach ( $this->all_plugins as $plugin_file => $plugin_data ) {
			if ( strpos( $plugin_file, 'geodirectory' ) !== false ) {
				$geodir_plugin = array(
					'file'    => $plugin_file,
					'name'    => $plugin_data['Name'],
					'version' => $plugin_data['Version'],
					'active'  => in_array( $plugin_file, $this->active_plugins, true ),
				);
				break;
			}
		}

		if ( ! $geodir_plugin || ! $geodir_plugin['active'] ) {
			return null;
		}

		// Detect all GeoDirectory custom post types dynamically
		// GeoDirectory CPTs are identified by the 'geodir_cpt' taxonomy
		$geodir_cpts = array();
		
		if ( taxonomy_exists( 'geodir_cpt' ) ) {
			// Get all terms in the geodir_cpt taxonomy
			$cpt_terms = get_terms( array(
				'taxonomy'   => 'geodir_cpt',
				'hide_empty' => false,
			) );

			if ( ! is_wp_error( $cpt_terms ) && ! empty( $cpt_terms ) ) {
				foreach ( $cpt_terms as $term ) {
					$geodir_cpts[] = $term->slug;
				}
			}
		}

		// Fallback: Check for common GeoDirectory post types
		if ( empty( $geodir_cpts ) ) {
			$common_geodir_cpts = array( 'gd_place', 'gd_event' );
			foreach ( $common_geodir_cpts as $cpt ) {
				if ( post_type_exists( $cpt ) ) {
					$geodir_cpts[] = $cpt;
				}
			}
		}

		// Get taxonomies associated with GeoDirectory
		$geodir_taxonomies = array();
		foreach ( $geodir_cpts as $cpt ) {
			$taxonomies = get_object_taxonomies( $cpt, 'objects' );
			foreach ( $taxonomies as $taxonomy ) {
				if ( ! isset( $geodir_taxonomies[ $taxonomy->name ] ) ) {
					$geodir_taxonomies[ $taxonomy->name ] = array(
						'name'         => $taxonomy->name,
						'label'        => $taxonomy->label,
						'hierarchical' => $taxonomy->hierarchical,
						'post_types'   => array(),
					);
				}
				$geodir_taxonomies[ $taxonomy->name ]['post_types'][] = $cpt;
			}
		}

		// Check for GeoDirectory custom tables
		global $wpdb;
		$geodir_tables = array();
		$all_tables = $wpdb->get_col( 'SHOW TABLES' );
		
		foreach ( $all_tables as $table ) {
			if ( strpos( $table, $wpdb->prefix . 'geodir_' ) === 0 ) {
				$geodir_tables[] = str_replace( $wpdb->prefix, '', $table );
			}
		}

		return array(
			'schema_version'    => 1,
			'plugin_info'       => $geodir_plugin,
			'custom_post_types' => $geodir_cpts,
			'taxonomies'        => array_values( $geodir_taxonomies ),
			'custom_tables'     => $geodir_tables,
			'features'          => array(
				'has_custom_tables'  => ! empty( $geodir_tables ),
				'has_custom_cpts'    => ! empty( $geodir_cpts ),
				'dynamic_cpt_count'  => count( $geodir_cpts ),
				'location_based'     => true,
				'uses_geodir_cpt_taxonomy' => taxonomy_exists( 'geodir_cpt' ),
			),
			'notes' => 'GeoDirectory can have any number of custom CPTs beyond default place/event. CPTs detected dynamically via geodir_cpt taxonomy.',
		);
	}

	/**
	 * Detect Advanced Custom Fields (ACF) plugin and prepare for field group export.
	 *
	 * @return array|null ACF feature map or null if not detected.
	 */
	private function detect_acf() {
		// Check if ACF is installed and active
		$acf_plugin = null;
		foreach ( $this->all_plugins as $plugin_file => $plugin_data ) {
			if ( strpos( $plugin_file, 'advanced-custom-fields' ) !== false || 
			     strpos( $plugin_data['Name'], 'Advanced Custom Fields' ) !== false ) {
				$acf_plugin = array(
					'file'    => $plugin_file,
					'name'    => $plugin_data['Name'],
					'version' => $plugin_data['Version'],
					'active'  => in_array( $plugin_file, $this->active_plugins, true ),
				);
				break;
			}
		}

		if ( ! $acf_plugin || ! $acf_plugin['active'] ) {
			return null;
		}

		// Detect ACF version (free vs pro)
		$is_pro = strpos( $acf_plugin['file'], 'acf-pro' ) !== false || 
		          strpos( $acf_plugin['name'], 'PRO' ) !== false;

		// Count field groups
		$field_groups_count = 0;
		if ( post_type_exists( 'acf-field-group' ) ) {
			$field_groups = get_posts( array(
				'post_type'      => 'acf-field-group',
				'posts_per_page' => -1,
				'post_status'    => 'publish',
			) );
			$field_groups_count = count( $field_groups );
		}

		// Check for ACF options pages
		$has_options_pages = false;
		if ( function_exists( 'acf_get_options_pages' ) ) {
			$options_pages = acf_get_options_pages();
			$has_options_pages = ! empty( $options_pages );
		}

		// Check for ACF blocks
		$acf_blocks = array();
		if ( function_exists( 'acf_get_block_types' ) ) {
			$block_types = acf_get_block_types();
			if ( ! empty( $block_types ) ) {
				foreach ( $block_types as $block ) {
					$acf_blocks[] = array(
						'name'  => isset( $block['name'] ) ? $block['name'] : '',
						'title' => isset( $block['title'] ) ? $block['title'] : '',
					);
				}
			}
		}

		return array(
			'schema_version'     => 1,
			'plugin_info'        => $acf_plugin,
			'version_type'       => $is_pro ? 'pro' : 'free',
			'field_groups_count' => $field_groups_count,
			'features'           => array(
				'has_field_groups'   => $field_groups_count > 0,
				'has_options_pages'  => $has_options_pages,
				'has_acf_blocks'     => ! empty( $acf_blocks ),
				'acf_blocks_count'   => count( $acf_blocks ),
			),
			'acf_blocks'         => $acf_blocks,
			'notes'              => 'Field group configurations will be exported separately in task 20.',
		);
	}

	/**
	 * Detect Kadence Blocks plugin.
	 *
	 * @return array|null Kadence Blocks feature map or null if not detected.
	 */
	private function detect_kadence_blocks() {
		// Check if Kadence Blocks is installed and active
		$kadence_plugin = null;
		foreach ( $this->all_plugins as $plugin_file => $plugin_data ) {
			if ( strpos( $plugin_file, 'kadence-blocks' ) !== false || 
			     strpos( $plugin_data['Name'], 'Kadence Blocks' ) !== false ) {
				$kadence_plugin = array(
					'file'    => $plugin_file,
					'name'    => $plugin_data['Name'],
					'version' => $plugin_data['Version'],
					'active'  => in_array( $plugin_file, $this->active_plugins, true ),
				);
				break;
			}
		}

		if ( ! $kadence_plugin || ! $kadence_plugin['active'] ) {
			return null;
		}

		// Detect Kadence blocks
		$kadence_blocks = array();
		if ( function_exists( 'WP_Block_Type_Registry::get_instance' ) ) {
			$block_registry = WP_Block_Type_Registry::get_instance();
			$registered_blocks = $block_registry->get_all_registered();

			foreach ( $registered_blocks as $block_name => $block_type ) {
				if ( strpos( $block_name, 'kadence/' ) === 0 ) {
					$kadence_blocks[] = array(
						'name'        => $block_name,
						'title'       => isset( $block_type->title ) ? $block_type->title : '',
						'description' => isset( $block_type->description ) ? $block_type->description : '',
						'category'    => isset( $block_type->category ) ? $block_type->category : '',
					);
				}
			}
		}

		// Check for Kadence custom post types (templates, etc.)
		$kadence_cpts = array();
		$kadence_cpt_names = array( 'kadence_lottie', 'kadence_element', 'kadence_conversions' );
		foreach ( $kadence_cpt_names as $cpt ) {
			if ( post_type_exists( $cpt ) ) {
				$kadence_cpts[] = $cpt;
			}
		}

		return array(
			'schema_version' => 1,
			'plugin_info'    => $kadence_plugin,
			'blocks_count'   => count( $kadence_blocks ),
			'blocks'         => $kadence_blocks,
			'custom_post_types' => $kadence_cpts,
			'features'       => array(
				'has_blocks'         => ! empty( $kadence_blocks ),
				'has_custom_cpts'    => ! empty( $kadence_cpts ),
				'block_library'      => true,
			),
		);
	}

	/**
	 * Export plugin template files.
	 *
	 * @return array Template export results.
	 */
	private function export_plugin_templates() {
		$exported_templates = array();
		$templates_dir = $this->plugins_export_dir . 'templates/';

		// Only export templates for active plugins
		foreach ( $this->all_plugins as $plugin_file => $plugin_data ) {
			if ( ! in_array( $plugin_file, $this->active_plugins, true ) ) {
				continue;
			}

			$plugin_slug = dirname( $plugin_file );
			if ( $plugin_slug === '.' ) {
				$plugin_slug = basename( $plugin_file, '.php' );
			}

			$plugin_dir = WP_PLUGIN_DIR . '/' . $plugin_slug;
			
			// Look for template directories
			$template_paths = array(
				$plugin_dir . '/templates/',
				$plugin_dir . '/template-parts/',
				$plugin_dir . '/views/',
			);

			$plugin_templates = array();

			foreach ( $template_paths as $template_path ) {
				if ( ! is_dir( $template_path ) ) {
					continue;
				}

				// Get all template files
				$template_files = $this->get_template_files( $template_path );

				if ( ! empty( $template_files ) ) {
					$plugin_template_dir = $templates_dir . $plugin_slug . '/';
					
					if ( ! file_exists( $plugin_template_dir ) ) {
						wp_mkdir_p( $plugin_template_dir );
					}

					foreach ( $template_files as $template_file ) {
						$relative_path = str_replace( $plugin_dir . '/', '', $template_file );
						$destination = $plugin_template_dir . basename( dirname( $relative_path ) ) . '/' . basename( $template_file );
						
						// Create subdirectory if needed
						$dest_dir = dirname( $destination );
						if ( ! file_exists( $dest_dir ) ) {
							wp_mkdir_p( $dest_dir );
						}

						if ( copy( $template_file, $destination ) ) {
							$plugin_templates[] = array(
								'source'      => $relative_path,
								'destination' => str_replace( $this->export_dir, '', $destination ),
								'size'        => filesize( $template_file ),
							);
						}
					}
				}
			}

			if ( ! empty( $plugin_templates ) ) {
				$exported_templates[ $plugin_slug ] = array(
					'plugin_name'    => $plugin_data['Name'],
					'plugin_version' => $plugin_data['Version'],
					'template_count' => count( $plugin_templates ),
					'templates'      => $plugin_templates,
				);
			}
		}

		// Create manifest file
		$manifest = array(
			'schema_version'  => 1,
			'scan_date'       => current_time( 'mysql' ),
			'plugins_count'   => count( $exported_templates ),
			'total_templates' => array_sum( array_column( $exported_templates, 'template_count' ) ),
			'plugins'         => $exported_templates,
		);

		$json = wp_json_encode( $manifest, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES );
		if ( $json ) {
			file_put_contents( $this->plugins_export_dir . 'plugins_templates_manifest.json', $json );
		}

		return array(
			'success'         => true,
			'plugins_count'   => count( $exported_templates ),
			'total_templates' => array_sum( array_column( $exported_templates, 'template_count' ) ),
			'exported'        => $exported_templates,
			'path'            => 'plugins/plugins_templates_manifest.json',
		);
	}

	/**
	 * Get all template files from a directory recursively.
	 *
	 * @param string $dir Directory path.
	 * @return array Array of template file paths.
	 */
	private function get_template_files( $dir ) {
		$template_files = array();
		
		if ( ! is_dir( $dir ) ) {
			return $template_files;
		}

		$iterator = new RecursiveIteratorIterator(
			new RecursiveDirectoryIterator( $dir, RecursiveDirectoryIterator::SKIP_DOTS ),
			RecursiveIteratorIterator::SELF_FIRST
		);

		foreach ( $iterator as $file ) {
			if ( $file->isFile() ) {
				$extension = $file->getExtension();
				// Only include template files (php, html, twig, etc.)
				if ( in_array( $extension, array( 'php', 'html', 'twig', 'blade.php' ), true ) ) {
					$template_files[] = $file->getPathname();
				}
			}
		}

		return $template_files;
	}
}
