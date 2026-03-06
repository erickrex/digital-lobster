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
class Digital_Lobster_Exporter_Hooks_Scanner extends Digital_Lobster_Exporter_Scanner_Base {

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
	 * @param array $deps Optional. Associative array of dependencies.
	 */
	public function __construct( array $deps = array() ) {
		parent::__construct( $deps );
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
		return Digital_Lobster_Exporter_Callback_Resolver::resolve( $callback );
	}

	/**
	 * Identify the source plugin or theme for a hook.
	 *
	 * @param mixed $callback Callback function.
	 * @return array Source information.
	 */
	private function identify_hook_source( $callback ) {
		$resolved = Digital_Lobster_Exporter_Callback_Resolver::resolve( $callback );

		if ( isset( $resolved['file'] ) && ! empty( $resolved['file'] ) ) {
			return Digital_Lobster_Exporter_Source_Identifier::identify( $resolved['file'] );
		}

		return array(
			'type' => 'unknown',
			'name' => 'Unknown',
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
}
