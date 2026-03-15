<?php
/**
 * Page Composition Scanner Class
 *
 * Produces a normalized page_composition.json artifact containing
 * per-page resolved composition: canonical URL, template, blocks,
 * shortcodes, widget placements, forms embedded, plugin components,
 * enqueued assets, content sections, and snapshot references.
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Page Composition Scanner Class
 */
class Digital_Lobster_Exporter_Page_Composition_Scanner extends Digital_Lobster_Exporter_Scanner_Base {

	/**
	 * Collected page compositions.
	 *
	 * @var array
	 */
	private $pages = array();

	/**
	 * Scan per-page composition for sampled content.
	 *
	 * @return array Page composition data matching PageCompositionArtifact schema.
	 */
	public function scan() {
		$this->pages = array();
		$posts       = $this->get_sampled_posts();

		if ( empty( $posts ) ) {
			$post_types = get_post_types( array( 'public' => true ), 'names' );

			foreach ( $post_types as $post_type ) {
				if ( 'attachment' === $post_type ) {
					continue;
				}

				$posts = array_merge(
					$posts,
					get_posts(
						array(
							'post_type'      => $post_type,
							'posts_per_page' => -1,
							'post_status'    => array( 'publish', 'draft' ),
						)
					)
				);
			}
		}

		foreach ( $posts as $post ) {
			if ( empty( $post ) || 'attachment' === $post->post_type ) {
				continue;
			}

			$this->scan_page( $post );
		}

		return array(
			'schema_version' => '1.0.0',
			'pages'          => array_values( $this->pages ),
		);
	}

	/**
	 * Scan a single page/post for its composition.
	 *
	 * @param WP_Post $post The post object.
	 */
	private function scan_page( $post ) {
		$canonical_url = wp_make_link_relative( get_permalink( $post->ID ) );
		if ( empty( $canonical_url ) ) {
			$canonical_url = '/' . $post->post_name;
		}

		$template = $this->detect_template( $post );
		$blocks   = $this->extract_blocks( $post->post_content );
		$shortcodes     = $this->extract_shortcodes( $post->post_content );
		$widget_placements = $this->get_widget_placements( $post );
		$forms_embedded    = $this->detect_embedded_forms( $post->post_content );
		$plugin_components = $this->detect_plugin_components( $post->post_content );
		$enqueued_assets   = $this->detect_enqueued_assets( $post );
		$content_sections  = $this->extract_content_sections( $post->post_content, $blocks );
		$snapshot_ref      = $this->resolve_snapshot_ref( $post );

		$this->pages[] = array(
			'canonical_url'     => $canonical_url,
			'template'          => $template,
			'blocks'            => $blocks,
			'shortcodes'        => $shortcodes,
			'widget_placements' => $widget_placements,
			'forms_embedded'    => $forms_embedded,
			'plugin_components' => $plugin_components,
			'enqueued_assets'   => $enqueued_assets,
			'content_sections'  => $content_sections,
			'snapshot_ref'      => $snapshot_ref,
		);
	}

	/**
	 * Detect the template assigned to a post.
	 *
	 * @param WP_Post $post The post object.
	 * @return string Template identifier.
	 */
	private function detect_template( $post ) {
		$template = get_page_template_slug( $post->ID );
		if ( ! empty( $template ) ) {
			return $template;
		}

		if ( 'page' === $post->post_type ) {
			return 'default';
		}

		return 'single-' . $post->post_type;
	}

	/**
	 * Extract parsed blocks from post content.
	 *
	 * @param string $content Post content.
	 * @return array List of block descriptors.
	 */
	private function extract_blocks( $content ) {
		if ( empty( $content ) || ! has_blocks( $content ) ) {
			return array();
		}

		$parsed = parse_blocks( $content );
		$blocks = array();

		foreach ( $parsed as $block ) {
			$this->collect_blocks( $block, $blocks );
		}

		return $blocks;
	}

	/**
	 * Recursively collect block descriptors.
	 *
	 * @param array $block  Parsed block.
	 * @param array $blocks Collected blocks (by reference).
	 */
	private function collect_blocks( $block, &$blocks ) {
		if ( empty( $block['blockName'] ) ) {
			return;
		}

		$entry = array(
			'block_name' => $block['blockName'],
			'attrs'      => ! empty( $block['attrs'] ) ? $block['attrs'] : new \stdClass(),
		);

		if ( ! empty( $block['innerBlocks'] ) ) {
			$entry['inner_block_count'] = count( $block['innerBlocks'] );
		}

		$blocks[] = $entry;

		if ( ! empty( $block['innerBlocks'] ) ) {
			foreach ( $block['innerBlocks'] as $inner ) {
				$this->collect_blocks( $inner, $blocks );
			}
		}
	}

	/**
	 * Extract shortcodes from post content.
	 *
	 * @param string $content Post content.
	 * @return array List of shortcode descriptors.
	 */
	private function extract_shortcodes( $content ) {
		if ( empty( $content ) ) {
			return array();
		}

		$shortcodes = array();
		$pattern    = get_shortcode_regex();

		if ( preg_match_all( '/' . $pattern . '/s', $content, $matches, PREG_SET_ORDER ) ) {
			foreach ( $matches as $match ) {
				$tag  = $match[2];
				$atts = shortcode_parse_atts( $match[3] );

				$shortcodes[] = array(
					'tag'        => $tag,
					'attributes' => is_array( $atts ) ? $atts : array(),
				);
			}
		}

		return $shortcodes;
	}

	/**
	 * Get widget placements relevant to a post's template.
	 *
	 * @param WP_Post $post The post object.
	 * @return array Widget placement descriptors.
	 */
	private function get_widget_placements( $post ) {
		$sidebars = wp_get_sidebars_widgets();
		if ( empty( $sidebars ) ) {
			return array();
		}

		$placements = array();
		foreach ( $sidebars as $sidebar_id => $widgets ) {
			if ( 'wp_inactive_widgets' === $sidebar_id || empty( $widgets ) ) {
				continue;
			}

			foreach ( $widgets as $widget_id ) {
				$placements[] = array(
					'sidebar'   => $sidebar_id,
					'widget_id' => $widget_id,
				);
			}
		}

		return $placements;
	}

	/**
	 * Detect forms embedded in post content.
	 *
	 * @param string $content Post content.
	 * @return array List of stable form IDs.
	 */
	private function detect_embedded_forms( $content ) {
		if ( empty( $content ) ) {
			return array();
		}

		$forms = array();

		// Contact Form 7.
		if ( preg_match_all( '/\[contact-form-7[^\]]*id="(\d+)"/', $content, $matches ) ) {
			foreach ( $matches[1] as $id ) {
				$forms[] = 'cf7:form:' . $id;
			}
		}

		// WPForms.
		if ( preg_match_all( '/\[wpforms[^\]]*id="(\d+)"/', $content, $matches ) ) {
			foreach ( $matches[1] as $id ) {
				$forms[] = 'wpforms:form:' . $id;
			}
		}

		// Gravity Forms.
		if ( preg_match_all( '/\[gravityform[^\]]*id="(\d+)"/', $content, $matches ) ) {
			foreach ( $matches[1] as $id ) {
				$forms[] = 'gravityforms:form:' . $id;
			}
		}

		// Ninja Forms.
		if ( preg_match_all( '/\[ninja_form[^\]]*id="?(\d+)"?/', $content, $matches ) ) {
			foreach ( $matches[1] as $id ) {
				$forms[] = 'ninjaforms:form:' . $id;
			}
		}

		return array_unique( $forms );
	}

	/**
	 * Detect plugin-specific components in post content.
	 *
	 * @param string $content Post content.
	 * @return array Plugin component descriptors.
	 */
	private function detect_plugin_components( $content ) {
		if ( empty( $content ) ) {
			return array();
		}

		$components = array();

		// Kadence Blocks.
		if ( preg_match_all( '/<!-- wp:kadence\/([a-z-]+)/', $content, $matches ) ) {
			foreach ( array_unique( $matches[1] ) as $block_type ) {
				$components[] = array(
					'source_plugin' => 'kadence_blocks',
					'component_type' => 'block',
					'identifier'     => 'kadence/' . $block_type,
				);
			}
		}

		// GeoDirectory shortcodes.
		if ( preg_match_all( '/\[gd_([a-z_]+)/', $content, $matches ) ) {
			foreach ( array_unique( $matches[1] ) as $gd_tag ) {
				$components[] = array(
					'source_plugin'  => 'geodirectory',
					'component_type' => 'shortcode',
					'identifier'     => 'gd_' . $gd_tag,
				);
			}
		}

		return $components;
	}

	/**
	 * Detect enqueued assets relevant to a post.
	 *
	 * Returns asset handles from context if available.
	 *
	 * @param WP_Post $post The post object.
	 * @return array List of asset identifiers.
	 */
	private function detect_enqueued_assets( $post ) {
		$assets_context = isset( $this->context['assets'] ) ? $this->context['assets'] : array();
		if ( empty( $assets_context ) ) {
			return array();
		}

		$assets = array();

		// Collect stylesheet handles.
		if ( ! empty( $assets_context['stylesheets'] ) && is_array( $assets_context['stylesheets'] ) ) {
			foreach ( $assets_context['stylesheets'] as $style ) {
				$handle = is_array( $style ) ? ( isset( $style['handle'] ) ? $style['handle'] : '' ) : (string) $style;
				if ( ! empty( $handle ) ) {
					$assets[] = 'css:' . $handle;
				}
			}
		}

		// Collect script handles.
		if ( ! empty( $assets_context['scripts'] ) && is_array( $assets_context['scripts'] ) ) {
			foreach ( $assets_context['scripts'] as $script ) {
				$handle = is_array( $script ) ? ( isset( $script['handle'] ) ? $script['handle'] : '' ) : (string) $script;
				if ( ! empty( $handle ) ) {
					$assets[] = 'js:' . $handle;
				}
			}
		}

		return $assets;
	}

	/**
	 * Extract content sections from post content.
	 *
	 * Infers sections from block groups and heading structure.
	 *
	 * @param string $content Post content.
	 * @param array  $blocks  Extracted blocks.
	 * @return array Content section descriptors.
	 */
	private function extract_content_sections( $content, $blocks ) {
		if ( empty( $content ) ) {
			return array();
		}

		$sections = array();

		// Group by heading blocks to infer sections.
		$current_section = null;
		$section_blocks  = array();

		foreach ( $blocks as $block ) {
			if ( isset( $block['block_name'] ) && in_array( $block['block_name'], array( 'core/heading', 'core/group' ), true ) ) {
				if ( null !== $current_section ) {
					$sections[] = array(
						'heading'     => $current_section,
						'block_count' => count( $section_blocks ),
					);
				}
				$current_section = $block['block_name'];
				$section_blocks  = array( $block );
			} else {
				$section_blocks[] = $block;
			}
		}

		// Final section.
		if ( null !== $current_section ) {
			$sections[] = array(
				'heading'     => $current_section,
				'block_count' => count( $section_blocks ),
			);
		}

		return $sections;
	}

	/**
	 * Resolve snapshot reference for a post.
	 *
	 * @param WP_Post $post The post object.
	 * @return string|null Path to snapshot HTML or null.
	 */
	private function resolve_snapshot_ref( $post ) {
		if ( empty( $this->export_dir ) ) {
			return null;
		}

		$snapshot_path = $this->export_dir . '/snapshots/' . $post->post_type . '-' . $post->ID . '.html';
		if ( file_exists( $snapshot_path ) ) {
			return 'snapshots/' . $post->post_type . '-' . $post->ID . '.html';
		}

		return null;
	}
}
