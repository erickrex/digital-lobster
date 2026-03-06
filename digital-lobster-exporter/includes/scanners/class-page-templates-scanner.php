<?php
/**
 * Page Templates Scanner
 *
 * Exports page templates and their assignments.
 *
 * @package Digital_Lobster_Exporter
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Class Digital_Lobster_Exporter_Page_Templates_Scanner
 *
 * Collects WordPress page templates including:
 * - All available page templates
 * - Template assignments for each page
 * - Template metadata and descriptions
 */
class Digital_Lobster_Exporter_Page_Templates_Scanner extends Digital_Lobster_Exporter_Scanner_Base {

	/**
	 * Constructor.
	 *
	 * @param array $deps Optional. Associative array of dependencies.
	 */
	public function __construct( array $deps = array() ) {
		parent::__construct( $deps );
	}

	/**
	 * Scan and collect page template data
	 *
	 * @return array Page template data
	 */
	public function scan() {
		$data = array(
			'schema_version'      => 1,
			'available_templates' => $this->get_available_templates(),
			'template_assignments' => $this->get_template_assignments(),
		);

		return $data;
	}

	/**
	 * Get all available page templates
	 *
	 * @return array Available templates
	 */
	private function get_available_templates() {
		$templates = array();

		// Get templates from active theme
		$theme_templates = wp_get_theme()->get_page_templates();

		// Add default template
		$templates['default'] = array(
			'filename'    => 'page.php',
			'name'        => 'Default Template',
			'description' => 'Default page template',
			'source'      => 'core',
		);

		// Add theme templates
		foreach ( $theme_templates as $filename => $name ) {
			$templates[ $filename ] = array(
				'filename'    => $filename,
				'name'        => $name,
				'description' => '',
				'source'      => 'theme',
			);
		}

		// Get block theme templates if applicable
		if ( wp_is_block_theme() ) {
			$block_templates = $this->get_block_theme_templates();
			$templates = array_merge( $templates, $block_templates );
		}

		return $templates;
	}

	/**
	 * Get block theme templates
	 *
	 * @return array Block theme templates
	 */
	private function get_block_theme_templates() {
		$templates = array();

		if ( ! function_exists( 'get_block_templates' ) ) {
			return $templates;
		}

		$block_templates = get_block_templates( array(), 'wp_template' );

		foreach ( $block_templates as $template ) {
			$slug = $template->slug;
			
			$templates[ $slug ] = array(
				'filename'    => $slug,
				'name'        => $template->title,
				'description' => $template->description ?? '',
				'source'      => $template->source ?? 'theme',
				'type'        => 'block_template',
				'area'        => $template->area ?? '',
			);
		}

		return $templates;
	}

	/**
	 * Get template assignments for all pages
	 *
	 * @return array Template assignments
	 */
	private function get_template_assignments() {
		$assignments = array();

		// Query all pages
		$pages = get_posts(
			array(
				'post_type'      => 'page',
				'posts_per_page' => -1,
				'post_status'    => array( 'publish', 'draft', 'private' ),
				'orderby'        => 'title',
				'order'          => 'ASC',
			)
		);

		foreach ( $pages as $page ) {
			$template = get_page_template_slug( $page->ID );
			
			// If no template is set, it uses the default
			if ( empty( $template ) ) {
				$template = 'default';
			}

			$assignments[] = array(
				'page_id'   => $page->ID,
				'page_slug' => $page->post_name,
				'page_title' => $page->post_title,
				'template'  => $template,
			);
		}

		return $assignments;
	}
}
