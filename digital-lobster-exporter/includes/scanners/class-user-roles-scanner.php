<?php
/**
 * User Roles Scanner
 *
 * Exports user roles and capabilities without exporting actual user accounts.
 *
 * @package Digital_Lobster_Exporter
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Class Digital_Lobster_Exporter_User_Roles_Scanner
 *
 * Collects user roles and capabilities data.
 */
class Digital_Lobster_Exporter_User_Roles_Scanner extends Digital_Lobster_Exporter_Scanner_Base {

	/**
	 * Default WordPress roles
	 *
	 * @var array
	 */
	private $default_roles = array(
		'administrator',
		'editor',
		'author',
		'contributor',
		'subscriber',
	);

	/**
	 * Known role management plugins
	 *
	 * @var array
	 */
	private $role_plugins = array(
		'members/members.php'                              => 'Members',
		'user-role-editor/user-role-editor.php'            => 'User Role Editor',
		'capability-manager-enhanced/capsman-enhanced.php' => 'Capability Manager Enhanced',
		'advanced-access-manager/aam.php'                  => 'Advanced Access Manager',
		'user-role-editor-pro/user-role-editor-pro.php'    => 'User Role Editor Pro',
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
	 * Scan user roles and capabilities
	 *
	 * @return array User roles data
	 */
	public function scan() {
		global $wp_roles;

		if ( ! isset( $wp_roles ) ) {
			$wp_roles = new WP_Roles();
		}

		$data = array(
			'schema_version'          => 1,
			'roles'                   => array(),
			'custom_roles'            => array(),
			'modified_default_roles'  => array(),
			'role_management_plugins' => array(),
			'total_roles'             => 0,
			'scan_timestamp'          => current_time( 'mysql' ),
		);

		// Get all roles
		$roles = $wp_roles->roles;
		$data['total_roles'] = count( $roles );

		// Detect role management plugins
		$data['role_management_plugins'] = $this->detect_role_plugins();

		// Process each role
		foreach ( $roles as $role_slug => $role_data ) {
			$role_info = array(
				'slug'             => $role_slug,
				'name'             => $role_data['name'],
				'capabilities'     => $role_data['capabilities'],
				'is_default'       => in_array( $role_slug, $this->default_roles, true ),
				'is_custom'        => ! in_array( $role_slug, $this->default_roles, true ),
				'capability_count' => count( $role_data['capabilities'] ),
			);

			// Add to roles array
			$data['roles'][ $role_slug ] = $role_info;

			// Track custom roles
			if ( $role_info['is_custom'] ) {
				$data['custom_roles'][] = $role_slug;
			}

			// Check if default role has been modified
			if ( $role_info['is_default'] ) {
				$modifications = $this->detect_role_modifications( $role_slug, $role_data['capabilities'] );
				if ( ! empty( $modifications ) ) {
					$data['modified_default_roles'][ $role_slug ] = $modifications;
				}
			}
		}

		return $data;
	}

	/**
	 * Detect installed role management plugins
	 *
	 * @return array List of detected role management plugins
	 */
	private function detect_role_plugins() {
		$detected = array();

		if ( ! function_exists( 'get_plugins' ) ) {
			require_once ABSPATH . 'wp-admin/includes/plugin.php';
		}

		$active_plugins = get_option( 'active_plugins', array() );

		foreach ( $this->role_plugins as $plugin_file => $plugin_name ) {
			if ( in_array( $plugin_file, $active_plugins, true ) ) {
				$detected[] = array(
					'name'   => $plugin_name,
					'file'   => $plugin_file,
					'active' => true,
				);
			} else {
				// Check if plugin exists but is inactive
				$all_plugins = get_plugins();
				if ( isset( $all_plugins[ $plugin_file ] ) ) {
					$detected[] = array(
						'name'   => $plugin_name,
						'file'   => $plugin_file,
						'active' => false,
					);
				}
			}
		}

		return $detected;
	}

	/**
	 * Detect modifications to default WordPress roles
	 *
	 * @param string $role_slug    Role slug.
	 * @param array  $current_caps Current capabilities.
	 * @return array Modifications detected.
	 */
	private function detect_role_modifications( $role_slug, $current_caps ) {
		$default_caps = $this->get_default_capabilities( $role_slug );

		if ( empty( $default_caps ) ) {
			return array();
		}

		$modifications = array(
			'added_capabilities'    => array(),
			'removed_capabilities'  => array(),
			'modified_capabilities' => array(),
		);

		// Find added capabilities
		foreach ( $current_caps as $cap => $granted ) {
			if ( ! isset( $default_caps[ $cap ] ) ) {
				$modifications['added_capabilities'][] = $cap;
			} elseif ( $default_caps[ $cap ] !== $granted ) {
				$modifications['modified_capabilities'][] = array(
					'capability'    => $cap,
					'default_value' => $default_caps[ $cap ],
					'current_value' => $granted,
				);
			}
		}

		// Find removed capabilities
		foreach ( $default_caps as $cap => $granted ) {
			if ( ! isset( $current_caps[ $cap ] ) ) {
				$modifications['removed_capabilities'][] = $cap;
			}
		}

		// Only return if there are actual modifications
		if ( empty( $modifications['added_capabilities'] ) &&
			empty( $modifications['removed_capabilities'] ) &&
			empty( $modifications['modified_capabilities'] ) ) {
			return array();
		}

		return $modifications;
	}

	/**
	 * Get default capabilities for WordPress roles
	 *
	 * @param string $role_slug Role slug.
	 * @return array Default capabilities.
	 */
	private function get_default_capabilities( $role_slug ) {
		$defaults = array(
			'administrator' => array(
				'switch_themes'          => true,
				'edit_themes'            => true,
				'activate_plugins'       => true,
				'edit_plugins'           => true,
				'edit_users'             => true,
				'edit_files'             => true,
				'manage_options'         => true,
				'moderate_comments'      => true,
				'manage_categories'      => true,
				'manage_links'           => true,
				'upload_files'           => true,
				'import'                 => true,
				'unfiltered_html'        => true,
				'edit_posts'             => true,
				'edit_others_posts'      => true,
				'edit_published_posts'   => true,
				'publish_posts'          => true,
				'edit_pages'             => true,
				'read'                   => true,
				'level_10'               => true,
				'level_9'                => true,
				'level_8'                => true,
				'level_7'                => true,
				'level_6'                => true,
				'level_5'                => true,
				'level_4'                => true,
				'level_3'                => true,
				'level_2'                => true,
				'level_1'                => true,
				'level_0'                => true,
				'edit_others_pages'      => true,
				'edit_published_pages'   => true,
				'publish_pages'          => true,
				'delete_pages'           => true,
				'delete_others_pages'    => true,
				'delete_published_pages' => true,
				'delete_posts'           => true,
				'delete_others_posts'    => true,
				'delete_published_posts' => true,
				'delete_private_posts'   => true,
				'edit_private_posts'     => true,
				'read_private_posts'     => true,
				'delete_private_pages'   => true,
				'edit_private_pages'     => true,
				'read_private_pages'     => true,
				'delete_users'           => true,
				'create_users'           => true,
				'unfiltered_upload'      => true,
				'edit_dashboard'         => true,
				'update_plugins'         => true,
				'delete_plugins'         => true,
				'install_plugins'        => true,
				'update_themes'          => true,
				'install_themes'         => true,
				'update_core'            => true,
				'list_users'             => true,
				'remove_users'           => true,
				'promote_users'          => true,
				'edit_theme_options'     => true,
				'delete_themes'          => true,
				'export'                 => true,
			),
			'editor' => array(
				'moderate_comments'      => true,
				'manage_categories'      => true,
				'manage_links'           => true,
				'upload_files'           => true,
				'unfiltered_html'        => true,
				'edit_posts'             => true,
				'edit_others_posts'      => true,
				'edit_published_posts'   => true,
				'publish_posts'          => true,
				'edit_pages'             => true,
				'read'                   => true,
				'level_7'                => true,
				'level_6'                => true,
				'level_5'                => true,
				'level_4'                => true,
				'level_3'                => true,
				'level_2'                => true,
				'level_1'                => true,
				'level_0'                => true,
				'edit_others_pages'      => true,
				'edit_published_pages'   => true,
				'publish_pages'          => true,
				'delete_pages'           => true,
				'delete_others_pages'    => true,
				'delete_published_pages' => true,
				'delete_posts'           => true,
				'delete_others_posts'    => true,
				'delete_published_posts' => true,
				'delete_private_posts'   => true,
				'edit_private_posts'     => true,
				'read_private_posts'     => true,
				'delete_private_pages'   => true,
				'edit_private_pages'     => true,
				'read_private_pages'     => true,
			),
			'author' => array(
				'upload_files'           => true,
				'edit_posts'             => true,
				'edit_published_posts'   => true,
				'publish_posts'          => true,
				'read'                   => true,
				'level_2'                => true,
				'level_1'                => true,
				'level_0'                => true,
				'delete_posts'           => true,
				'delete_published_posts' => true,
			),
			'contributor' => array(
				'edit_posts'   => true,
				'read'         => true,
				'level_1'      => true,
				'level_0'      => true,
				'delete_posts' => true,
			),
			'subscriber' => array(
				'read'    => true,
				'level_0' => true,
			),
		);

		return isset( $defaults[ $role_slug ] ) ? $defaults[ $role_slug ] : array();
	}
}
