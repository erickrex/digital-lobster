<?php
/**
 * Menu Scanner
 *
 * Exports navigation menus with full hierarchy and structure.
 *
 * @package Digital_Lobster_Exporter
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Class Digital_Lobster_Exporter_Menu_Scanner
 *
 * Collects WordPress navigation menus including:
 * - All registered navigation menus with full hierarchy
 * - Menu item types, URLs, CSS classes, relationships
 * - Menu locations and assignments
 */
class Digital_Lobster_Exporter_Menu_Scanner extends Digital_Lobster_Exporter_Scanner_Base {

	/**
	 * Constructor.
	 *
	 * @param array $deps Optional. Associative array of dependencies.
	 */
	public function __construct( array $deps = array() ) {
		parent::__construct( $deps );
	}

	/**
	 * Scan and collect menu data
	 *
	 * @return array Menu data
	 */
	public function scan() {
		$data = array(
			'schema_version' => 1,
			'menu_locations' => $this->get_menu_locations(),
			'menus'          => $this->get_all_menus(),
		);

		return $data;
	}

	/**
	 * Get registered menu locations
	 *
	 * @return array Menu locations
	 */
	private function get_menu_locations() {
		$locations = get_registered_nav_menus();
		$theme_locations = get_nav_menu_locations();
		
		$result = array();
		
		foreach ( $locations as $location => $description ) {
			$result[ $location ] = array(
				'description' => $description,
				'assigned_menu' => isset( $theme_locations[ $location ] ) ? $theme_locations[ $location ] : null,
			);
		}
		
		return $result;
	}

	/**
	 * Get all navigation menus
	 *
	 * @return array All menus with items
	 */
	private function get_all_menus() {
		$menus = wp_get_nav_menus();
		$result = array();
		
		foreach ( $menus as $menu ) {
			$menu_data = array(
				'term_id'     => $menu->term_id,
				'name'        => $menu->name,
				'slug'        => $menu->slug,
				'description' => $menu->description,
				'count'       => $menu->count,
				'locations'   => $this->get_menu_assigned_locations( $menu->term_id ),
				'items'       => $this->get_menu_items( $menu->term_id ),
			);
			
			$result[] = $menu_data;
		}
		
		return $result;
	}

	/**
	 * Get locations where a menu is assigned
	 *
	 * @param int $menu_id Menu term ID
	 * @return array Assigned locations
	 */
	private function get_menu_assigned_locations( $menu_id ) {
		$theme_locations = get_nav_menu_locations();
		$assigned = array();
		
		foreach ( $theme_locations as $location => $assigned_menu_id ) {
			if ( $assigned_menu_id === $menu_id ) {
				$assigned[] = $location;
			}
		}
		
		return $assigned;
	}

	/**
	 * Get menu items with full hierarchy
	 *
	 * @param int $menu_id Menu term ID
	 * @return array Menu items
	 */
	private function get_menu_items( $menu_id ) {
		$items = wp_get_nav_menu_items( $menu_id );
		
		if ( ! $items || is_wp_error( $items ) ) {
			return array();
		}
		
		$result = array();
		
		foreach ( $items as $item ) {
			$item_data = array(
				'id'               => $item->ID,
				'title'            => $item->title,
				'url'              => $item->url,
				'target'           => $item->target,
				'attr_title'       => $item->attr_title,
				'description'      => $item->description,
				'classes'          => is_array( $item->classes ) ? $item->classes : array(),
				'xfn'              => $item->xfn,
				'menu_order'       => $item->menu_order,
				'parent_id'        => $item->menu_item_parent,
				'type'             => $item->type,
				'type_label'       => $item->type_label,
				'object'           => $item->object,
				'object_id'        => $item->object_id,
			);
			
			// Add additional context based on item type
			$item_data['context'] = $this->get_item_context( $item );
			
			$result[] = $item_data;
		}
		
		return $result;
	}

	/**
	 * Get additional context for menu item
	 *
	 * @param object $item Menu item object
	 * @return array Context information
	 */
	private function get_item_context( $item ) {
		$context = array();
		
		switch ( $item->type ) {
			case 'post_type':
				if ( $item->object_id ) {
					$post = get_post( $item->object_id );
					if ( $post ) {
						$context['post_type'] = $post->post_type;
						$context['post_slug'] = $post->post_name;
						$context['post_status'] = $post->post_status;
					}
				}
				break;
				
			case 'taxonomy':
				if ( $item->object_id ) {
					$term = get_term( $item->object_id, $item->object );
					if ( $term && ! is_wp_error( $term ) ) {
						$context['taxonomy'] = $term->taxonomy;
						$context['term_slug'] = $term->slug;
					}
				}
				break;
				
			case 'custom':
				$context['custom_url'] = true;
				break;
		}
		
		return $context;
	}
}
