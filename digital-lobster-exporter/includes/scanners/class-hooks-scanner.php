<?php
/**
 * Hooks Scanner Class
 *
 * Creates an inventory of all registered WordPress actions and filters,
 * including hook names, callbacks, priorities, and source identification.
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Hooks Scanner Class
 */
class Digital_Lobster_Exporter_Hooks_Scanner {

	/**
	 * Export directory path.
	 *
	 * @var string
	 */
	private $export_dir = '';

	/**
	 * Hook categories for classification.
	 *
	 * @var array
	 */
	private $hook_categories = array(
		'content'  => array( 'save_post', 'wp_insert_post', 'delete_post', 'post_updated', 'transition_post_status', 'the_content', 'the_title', 'the_excerpt' ),
		'admin'    => array( 'admin_init', 'admin_menu', 'admin_enqueue_scripts', 'admin_notices', 'admin_head', 'admin_footer', 'load-' ),
		'frontend' => array( 'wp_enqueue_scripts', 'wp_head', 'wp_footer', 'wp_body_open', 'template_redirect', 'get_header', 'get_footer' ),
		'api'      => array( 'rest_api_init', 'rest_', 'xmlrpc_', 'wp_ajax_', 'wp_ajax_nopriv_' ),
		'init'     => array( 'init', 'plugins_loaded', 'after_setup_theme', 'wp_loaded', 'setup_theme' ),
		'user'     => array( 'user_register', 'profile_update', 'wp_login', 'wp_logout', 'login_', 'register_' ),
		'media'    => array( 'add_attachment', 'edit_attachment', 'delete_attachment', 'wp_generate_attachment_metadata' ),
		'taxonomy' => array( 'create_term', 'edit_term', 'delete_term', 'created_', 'edited_', 'delete_' ),
		'comment'  => array( 'comment_post', 'edit_comment', 'delete_comment', 'wp_insert_comment', 'comment_' ),
		'cron'     => array( 'wp_cron', 'cron_schedules' ),
	);

	/**
	 * Constructor.
	 *
	 * @param string $export_dir Export directory path.
	 */
	public function __construct( $export_dir = '' ) {
		$this->export_dir = $export_dir;
	}

	/**
	 * Run the hooks scan.
	 *
	 * @return array Scan results.
	 */
	public function scan() {
		$results = array(
			'success' => true,
			'message' => 'Hooks registry scan completed',
			'data'    => array(),
		);

		try {
			// Get all registered hooks.
			$actions = $this->get_registered_hooks( 'action' );
			$filters = $this->get_registered_hooks( 'filter' );

			// Build the registry.
			$registry = $this->build_registry( $actions, $filters );

			// Export to JSON.
			$this->export_registry( $registry );

			$results['data'] = array(
				'total_actions' => count( $actions ),
				'total_filters' => count( $filters ),
				'total_hooks'   => count( $actions ) + count( $filters ),
			);

		} catch ( Exception $e ) {
			$results['success'] = false;
			$results['message'] = 'Hooks scan failed: ' . $e->getMessage();
		}

		return $results;
	}

	/**
	 * Get all registered hooks (actions or filters).
	 *
	 * @param string $type Hook type: 'action' or 'filter'.
	 * @return array Registered hooks.
	 */
	private function get_registered_hooks( $type = 'action' ) {
		global $wp_filter;

		$hooks = array();

		if ( empty( $wp_filter ) || ! is_array( $wp_filter ) ) {
			return $hooks;
		}

		foreach ( $wp_filter as $hook_name => $hook_object ) {
			if ( ! ( $hook_object instanceof WP_Hook ) ) {
				continue;
			}

			$callbacks = $hook_object->callbacks;

			foreach ( $callbacks as $priority => $priority_callbacks ) {
				foreach ( $priority_callbacks as $callback_id => $callback_data ) {
					$hook_info = array(
						'hook_name'        => $hook_name,
						'type'             => $type,
						'priority'         => $priority,
						'accepted_args'    => isset( $callback_data['accepted_args'] ) ? $callback_data['accepted_args'] : 1,
						'callback'         => $this->get_callback_info( $callback_data['function'] ),
						'callback_id'      => $callback_id,
						'source'           => $this->identify_hook_source( $callback_data['function'] ),
						'category'         => $this->categorize_hook( $hook_name ),
					);

					$hooks[] = $hook_info;
				}
			}
		}

		return $hooks;
	}

	/**
	 * Get callback information without exposing actual code.
	 *
	 * @param mixed $callback Callback function.
	 * @return array Callback description.
	 */
	private function get_callback_info( $callback ) {
		$info = array(
			'type' => 'unknown',
			'name' => 'Unknown',
		);

		if ( is_string( $callback ) ) {
			$info['type'] = 'function';
			$info['name'] = $callback;
		} elseif ( is_array( $callback ) && count( $callback ) === 2 ) {
			$class  = is_object( $callback[0] ) ? get_class( $callback[0] ) : $callback[0];
			$method = $callback[1];
			
			$info['type']   = 'method';
			$info['class']  = $class;
			$info['method'] = $method;
			$info['name']   = $class . '::' . $method;
		} elseif ( is_object( $callback ) && ( $callback instanceof Closure ) ) {
			$info['type'] = 'closure';
			$info['name'] = 'Closure';
			
			// Try to get closure location.
			try {
				$reflection = new ReflectionFunction( $callback );
				$info['file'] = basename( $reflection->getFileName() );
				$info['line'] = $reflection->getStartLine();
			} catch ( Exception $e ) {
				// Reflection failed.
			}
		} elseif ( is_object( $callback ) ) {
			$info['type']  = 'invokable';
			$info['class'] = get_class( $callback );
			$info['name']  = get_class( $callback ) . '::__invoke';
		}

		return $info;
	}

	/**
	 * Identify the source plugin or theme for a hook.
	 *
	 * @param mixed $callback Callback function.
	 * @return array Source information.
	 */
	private function identify_hook_source( $callback ) {
		$source = array(
			'type' => 'unknown',
			'name' => 'Unknown',
		);

		// Try to identify from reflection.
		try {
			$reflection = null;

			if ( is_array( $callback ) && count( $callback ) === 2 ) {
				$reflection = is_object( $callback[0] )
					? new ReflectionClass( $callback[0] )
					: new ReflectionClass( $callback[0] );
			} elseif ( is_string( $callback ) && function_exists( $callback ) ) {
				$reflection = new ReflectionFunction( $callback );
			} elseif ( is_object( $callback ) && ( $callback instanceof Closure ) ) {
				$reflection = new ReflectionFunction( $callback );
			} elseif ( is_object( $callback ) ) {
				$reflection = new ReflectionClass( $callback );
			}

			if ( $reflection ) {
				$filename = $reflection->getFileName();

				if ( $filename ) {
					$source = $this->identify_source_from_file( $filename );
				}
			}
		} catch ( Exception $e ) {
			// Reflection failed, keep unknown.
		}

		return $source;
	}

	/**
	 * Identify source from file path.
	 *
	 * @param string $filename File path.
	 * @return array Source information.
	 */
	private function identify_source_from_file( $filename ) {
		$source = array(
			'type' => 'unknown',
			'name' => 'Unknown',
		);

		// Check if it's from WordPress core.
		if ( strpos( $filename, ABSPATH . 'wp-includes' ) !== false || strpos( $filename, ABSPATH . 'wp-admin' ) !== false ) {
			$source['type'] = 'core';
			$source['name'] = 'WordPress Core';
			return $source;
		}

		// Check if it's from a plugin.
		if ( strpos( $filename, WP_PLUGIN_DIR ) !== false ) {
			$relative = str_replace( WP_PLUGIN_DIR . '/', '', $filename );
			$parts    = explode( '/', $relative );

			if ( ! empty( $parts[0] ) ) {
				$plugin_slug = $parts[0];
				$plugin_data = $this->get_plugin_data( $plugin_slug );

				$source['type'] = 'plugin';
				$source['name'] = $plugin_data['name'];
				$source['slug'] = $plugin_slug;
			}
		} elseif ( strpos( $filename, get_template_directory() ) !== false ) {
			// From parent theme.
			$theme          = wp_get_theme( get_template() );
			$source['type'] = 'theme';
			$source['name'] = $theme->get( 'Name' );
			$source['slug'] = get_template();
		} elseif ( strpos( $filename, get_stylesheet_directory() ) !== false ) {
			// From child theme.
			$theme          = wp_get_theme();
			$source['type'] = 'theme';
			$source['name'] = $theme->get( 'Name' );
			$source['slug'] = get_stylesheet();
		}

		return $source;
	}

	/**
	 * Get plugin data from slug.
	 *
	 * @param string $plugin_slug Plugin slug.
	 * @return array Plugin data.
	 */
	private function get_plugin_data( $plugin_slug ) {
		if ( ! function_exists( 'get_plugins' ) ) {
			require_once ABSPATH . 'wp-admin/includes/plugin.php';
		}

		$all_plugins = get_plugins();

		foreach ( $all_plugins as $plugin_file => $plugin_data ) {
			if ( strpos( $plugin_file, $plugin_slug . '/' ) === 0 || $plugin_file === $plugin_slug . '.php' ) {
				return array(
					'name' => $plugin_data['Name'],
					'file' => $plugin_file,
				);
			}
		}

		return array(
			'name' => ucwords( str_replace( array( '-', '_' ), ' ', $plugin_slug ) ),
			'file' => '',
		);
	}

	/**
	 * Categorize a hook based on its name.
	 *
	 * @param string $hook_name Hook name.
	 * @return string Category name.
	 */
	private function categorize_hook( $hook_name ) {
		foreach ( $this->hook_categories as $category => $patterns ) {
			foreach ( $patterns as $pattern ) {
				if ( strpos( $hook_name, $pattern ) !== false ) {
					return $category;
				}
			}
		}

		return 'other';
	}

	/**
	 * Identify if a hook is custom (not from WordPress core).
	 *
	 * @param string $hook_name Hook name.
	 * @return bool True if custom hook.
	 */
	private function is_custom_hook( $hook_name ) {
		// List of common WordPress core hook prefixes.
		$core_prefixes = array(
			'wp_',
			'admin_',
			'login_',
			'register_',
			'comment_',
			'post_',
			'page_',
			'attachment_',
			'user_',
			'term_',
			'category_',
			'tag_',
			'link_',
			'option_',
			'blog_',
			'site_',
			'network_',
			'delete_',
			'edit_',
			'save_',
			'update_',
			'create_',
			'add_',
			'remove_',
			'set_',
			'get_',
			'the_',
			'rest_',
			'xmlrpc_',
			'cron_',
			'widget_',
			'sidebar_',
			'nav_menu_',
			'customize_',
			'theme_',
			'template_',
			'stylesheet_',
			'plugins_',
			'activated_',
			'deactivated_',
			'upgrader_',
			'http_',
			'pre_',
			'post_',
			'before_',
			'after_',
		);

		foreach ( $core_prefixes as $prefix ) {
			if ( strpos( $hook_name, $prefix ) === 0 ) {
				return false;
			}
		}

		return true;
	}

	/**
	 * Build the complete registry.
	 *
	 * @param array $actions Action hooks.
	 * @param array $filters Filter hooks.
	 * @return array Complete registry.
	 */
	private function build_registry( $actions, $filters ) {
		$registry = array(
			'schema_version' => 1,
			'generated_at'   => current_time( 'mysql', true ),
			'summary'        => array(
				'total_actions' => count( $actions ),
				'total_filters' => count( $filters ),
				'total_hooks'   => count( $actions ) + count( $filters ),
			),
			'hooks'          => array(
				'actions' => $this->group_hooks_by_category( $actions ),
				'filters' => $this->group_hooks_by_category( $filters ),
			),
			'custom_hooks'   => $this->identify_custom_hooks( array_merge( $actions, $filters ) ),
		);

		return $registry;
	}

	/**
	 * Group hooks by category.
	 *
	 * @param array $hooks Hooks to group.
	 * @return array Grouped hooks.
	 */
	private function group_hooks_by_category( $hooks ) {
		$grouped = array();

		foreach ( $hooks as $hook ) {
			$category = $hook['category'];

			if ( ! isset( $grouped[ $category ] ) ) {
				$grouped[ $category ] = array();
			}

			$grouped[ $category ][] = $hook;
		}

		// Sort each category by hook name.
		foreach ( $grouped as $category => $category_hooks ) {
			usort( $grouped[ $category ], function( $a, $b ) {
				return strcmp( $a['hook_name'], $b['hook_name'] );
			});
		}

		return $grouped;
	}

	/**
	 * Identify custom hooks (not from WordPress core).
	 *
	 * @param array $all_hooks All hooks.
	 * @return array Custom hooks.
	 */
	private function identify_custom_hooks( $all_hooks ) {
		$custom_hooks = array();
		$seen_hooks   = array();

		foreach ( $all_hooks as $hook ) {
			$hook_name = $hook['hook_name'];

			// Skip if already processed.
			if ( isset( $seen_hooks[ $hook_name ] ) ) {
				continue;
			}

			// Check if it's a custom hook.
			if ( $this->is_custom_hook( $hook_name ) ) {
				$custom_hooks[] = array(
					'hook_name'   => $hook_name,
					'type'        => $hook['type'],
					'category'    => $hook['category'],
					'sources'     => $this->get_hook_sources( $hook_name, $all_hooks ),
					'description' => $this->generate_hook_description( $hook_name ),
				);

				$seen_hooks[ $hook_name ] = true;
			}
		}

		// Sort by hook name.
		usort( $custom_hooks, function( $a, $b ) {
			return strcmp( $a['hook_name'], $b['hook_name'] );
		});

		return $custom_hooks;
	}

	/**
	 * Get all sources that register a specific hook.
	 *
	 * @param string $hook_name Hook name.
	 * @param array  $all_hooks All hooks.
	 * @return array Sources.
	 */
	private function get_hook_sources( $hook_name, $all_hooks ) {
		$sources = array();
		$seen    = array();

		foreach ( $all_hooks as $hook ) {
			if ( $hook['hook_name'] === $hook_name ) {
				$source_key = $hook['source']['type'] . ':' . $hook['source']['name'];

				if ( ! isset( $seen[ $source_key ] ) ) {
					$sources[]            = $hook['source'];
					$seen[ $source_key ] = true;
				}
			}
		}

		return $sources;
	}

	/**
	 * Generate a description for a custom hook based on its name.
	 *
	 * @param string $hook_name Hook name.
	 * @return string Description.
	 */
	private function generate_hook_description( $hook_name ) {
		// Try to infer purpose from hook name.
		$descriptions = array(
			'_init'      => 'Initialization hook',
			'_loaded'    => 'Fires after loading',
			'_save'      => 'Fires when saving',
			'_update'    => 'Fires when updating',
			'_delete'    => 'Fires when deleting',
			'_create'    => 'Fires when creating',
			'_before'    => 'Fires before action',
			'_after'     => 'Fires after action',
			'_process'   => 'Fires during processing',
			'_render'    => 'Fires during rendering',
			'_display'   => 'Fires during display',
			'_enqueue'   => 'Fires when enqueueing assets',
			'_register'  => 'Fires when registering',
			'_settings'  => 'Related to settings',
			'_options'   => 'Related to options',
			'_meta'      => 'Related to metadata',
			'_query'     => 'Related to queries',
			'_content'   => 'Related to content',
			'_form'      => 'Related to forms',
			'_ajax'      => 'AJAX handler',
			'_api'       => 'API endpoint',
			'_shortcode' => 'Related to shortcodes',
			'_widget'    => 'Related to widgets',
			'_block'     => 'Related to blocks',
		);

		foreach ( $descriptions as $suffix => $description ) {
			if ( strpos( $hook_name, $suffix ) !== false ) {
				return $description;
			}
		}

		return 'Custom hook';
	}

	/**
	 * Export registry to JSON file.
	 *
	 * @param array $registry Registry data.
	 */
	private function export_registry( $registry ) {
		$file_path = $this->export_dir . '/hooks_registry.json';

		$json = wp_json_encode( $registry, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES );

		if ( $json === false ) {
			throw new Exception( 'Failed to encode hooks registry to JSON' );
		}

		$result = file_put_contents( $file_path, $json );

		if ( $result === false ) {
			throw new Exception( 'Failed to write hooks_registry.json' );
		}
	}
}
