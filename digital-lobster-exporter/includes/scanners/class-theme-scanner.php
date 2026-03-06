<?php
/**
 * Theme Scanner Class
 *
 * Collects theme information including active theme details, parent theme,
 * block theme detection, and exports theme files (style.css, theme.json,
 * templates, functions.php).
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Theme Scanner Class
 */
class Digital_Lobster_Exporter_Theme_Scanner {

	/**
	 * Export directory path.
	 *
	 * @var string
	 */
	private $export_dir;

	/**
	 * Theme directory path in export.
	 *
	 * @var string
	 */
	private $theme_export_dir;

	/**
	 * Active theme object.
	 *
	 * @var WP_Theme
	 */
	private $theme;

	/**
	 * Parent theme object (if exists).
	 *
	 * @var WP_Theme|null
	 */
	private $parent_theme;

	/**
	 * Constructor.
	 */
	public function __construct() {
		$this->theme = wp_get_theme();
		$this->parent_theme = $this->theme->parent();
		$this->setup_export_directories();
	}

	/**
	 * Setup export directories.
	 */
	private function setup_export_directories() {
		$upload_dir = wp_upload_dir();
		$this->export_dir = trailingslashit( $upload_dir['basedir'] ) . 'ai_migration_artifacts/';
		$this->theme_export_dir = $this->export_dir . 'theme/';
	}

	/**
	 * Scan and collect theme information.
	 *
	 * @return array Theme information and file export results.
	 */
	public function scan() {
		// Create theme export directory
		$this->create_export_directory();

		$theme_info = $this->collect_theme_info();
		$exported_files = $this->export_theme_files();
		
		// Generate template hierarchy documentation
		$template_hierarchy = $this->generate_template_hierarchy();
		
		// Export theme customizations and global styles
		$theme_mods = $this->export_theme_mods();
		$customizer_css = $this->export_customizer_css();
		$global_styles = $this->export_global_styles();
		$css_sources = $this->scan_custom_css_sources();
		$editor_settings = $this->export_editor_settings();
		
		// Create assets manifest
		$assets_manifest = $this->create_assets_manifest();
		
		return array(
			'theme_info'          => $theme_info,
			'exported_files'      => $exported_files,
			'template_hierarchy'  => $template_hierarchy,
			'theme_mods'          => $theme_mods,
			'customizer_css'      => $customizer_css,
			'global_styles'       => $global_styles,
			'css_sources'         => $css_sources,
			'editor_settings'     => $editor_settings,
			'assets_manifest'     => $assets_manifest,
		);
	}

	/**
	 * Create export directory if it doesn't exist.
	 */
	private function create_export_directory() {
		if ( ! file_exists( $this->theme_export_dir ) ) {
			wp_mkdir_p( $this->theme_export_dir );
		}

		// Create templates subdirectory
		$templates_dir = $this->theme_export_dir . 'templates/';
		if ( ! file_exists( $templates_dir ) ) {
			wp_mkdir_p( $templates_dir );
		}
	}

	/**
	 * Collect theme information.
	 *
	 * @return array Theme metadata.
	 */
	private function collect_theme_info() {
		$theme_data = array(
			'name'         => $this->theme->get( 'Name' ),
			'version'      => $this->theme->get( 'Version' ),
			'description'  => $this->theme->get( 'Description' ),
			'author'       => $this->theme->get( 'Author' ),
			'author_uri'   => $this->theme->get( 'AuthorURI' ),
			'theme_uri'    => $this->theme->get( 'ThemeURI' ),
			'template'     => $this->theme->get_template(),
			'stylesheet'   => $this->theme->get_stylesheet(),
			'is_child_theme' => $this->theme->parent() !== false,
			'parent_theme' => null,
			'block_theme'  => $this->is_block_theme(),
			'text_domain'  => $this->theme->get( 'TextDomain' ),
		);

		// Add parent theme info if this is a child theme
		if ( $this->parent_theme ) {
			$theme_data['parent_theme'] = array(
				'name'       => $this->parent_theme->get( 'Name' ),
				'version'    => $this->parent_theme->get( 'Version' ),
				'template'   => $this->parent_theme->get_template(),
				'stylesheet' => $this->parent_theme->get_stylesheet(),
			);
		}

		return $theme_data;
	}

	/**
	 * Check if the theme is a block theme.
	 *
	 * @return bool True if block theme, false otherwise.
	 */
	private function is_block_theme() {
		// Check if theme.json exists in the theme root
		$theme_json_path = $this->theme->get_stylesheet_directory() . '/theme.json';
		
		// Also check for templates directory (block themes have HTML templates)
		$templates_dir = $this->theme->get_stylesheet_directory() . '/templates';
		
		return file_exists( $theme_json_path ) || ( file_exists( $templates_dir ) && $this->has_html_templates( $templates_dir ) );
	}

	/**
	 * Check if directory contains HTML template files.
	 *
	 * @param string $dir Directory path.
	 * @return bool True if HTML templates found.
	 */
	private function has_html_templates( $dir ) {
		if ( ! is_dir( $dir ) ) {
			return false;
		}

		$files = scandir( $dir );
		foreach ( $files as $file ) {
			if ( pathinfo( $file, PATHINFO_EXTENSION ) === 'html' ) {
				return true;
			}
		}

		return false;
	}

	/**
	 * Export theme files.
	 *
	 * @return array List of exported files with status.
	 */
	private function export_theme_files() {
		$exported = array();

		// Export style.css
		$exported['style.css'] = $this->export_style_css();

		// Export theme.json if it exists
		$exported['theme.json'] = $this->export_theme_json();

		// Export functions.php
		$exported['functions.php'] = $this->export_functions_php();

		// Export template files
		$exported['templates'] = $this->export_template_files();

		// Export template parts if they exist
		$exported['template_parts'] = $this->export_template_parts();

		// If child theme, also export parent theme files
		if ( $this->parent_theme ) {
			$exported['parent_theme_files'] = $this->export_parent_theme_files();
		}

		return $exported;
	}

	/**
	 * Export style.css file.
	 *
	 * @return array Export status.
	 */
	private function export_style_css() {
		$source = $this->theme->get_stylesheet_directory() . '/style.css';
		$destination = $this->theme_export_dir . 'style.css';

		if ( file_exists( $source ) ) {
			$copied = copy( $source, $destination );
			return array(
				'success' => $copied,
				'path'    => $copied ? 'theme/style.css' : null,
				'size'    => $copied ? filesize( $destination ) : 0,
			);
		}

		return array(
			'success' => false,
			'error'   => 'style.css not found',
		);
	}

	/**
	 * Export theme.json file.
	 *
	 * @return array Export status.
	 */
	private function export_theme_json() {
		$source = $this->theme->get_stylesheet_directory() . '/theme.json';
		$destination = $this->theme_export_dir . 'theme.json';

		if ( file_exists( $source ) ) {
			$copied = copy( $source, $destination );
			return array(
				'success' => $copied,
				'path'    => $copied ? 'theme/theme.json' : null,
				'size'    => $copied ? filesize( $destination ) : 0,
			);
		}

		return array(
			'success' => false,
			'message' => 'theme.json not found (not a block theme)',
		);
	}

	/**
	 * Export functions.php file.
	 *
	 * @return array Export status.
	 */
	private function export_functions_php() {
		$source = $this->theme->get_stylesheet_directory() . '/functions.php';
		$destination = $this->theme_export_dir . 'functions.php';

		if ( file_exists( $source ) ) {
			$copied = copy( $source, $destination );
			return array(
				'success' => $copied,
				'path'    => $copied ? 'theme/functions.php' : null,
				'size'    => $copied ? filesize( $destination ) : 0,
			);
		}

		return array(
			'success' => false,
			'message' => 'functions.php not found',
		);
	}

	/**
	 * Export template files (PHP and HTML).
	 *
	 * @return array Export status with list of exported templates.
	 */
	private function export_template_files() {
		$theme_dir = $this->theme->get_stylesheet_directory();
		$templates_export_dir = $this->theme_export_dir . 'templates/';
		$exported_templates = array();

		// Common PHP template files
		$php_templates = array(
			'index.php',
			'header.php',
			'footer.php',
			'sidebar.php',
			'single.php',
			'page.php',
			'archive.php',
			'category.php',
			'tag.php',
			'author.php',
			'search.php',
			'404.php',
			'home.php',
			'front-page.php',
			'attachment.php',
			'comments.php',
		);

		// Export PHP templates from theme root
		foreach ( $php_templates as $template ) {
			$source = $theme_dir . '/' . $template;
			if ( file_exists( $source ) ) {
				$destination = $templates_export_dir . $template;
				if ( copy( $source, $destination ) ) {
					$exported_templates[] = array(
						'file' => $template,
						'type' => 'php',
						'path' => 'theme/templates/' . $template,
					);
				}
			}
		}

		// Export custom page templates
		$page_templates = $this->theme->get_page_templates();
		foreach ( $page_templates as $template_file => $template_name ) {
			$source = $theme_dir . '/' . $template_file;
			if ( file_exists( $source ) && ! in_array( $template_file, $php_templates, true ) ) {
				$destination = $templates_export_dir . basename( $template_file );
				if ( copy( $source, $destination ) ) {
					$exported_templates[] = array(
						'file'         => $template_file,
						'name'         => $template_name,
						'type'         => 'page_template',
						'path'         => 'theme/templates/' . basename( $template_file ),
					);
				}
			}
		}

		// Export HTML templates for block themes
		$html_templates_dir = $theme_dir . '/templates';
		if ( is_dir( $html_templates_dir ) ) {
			$html_templates = $this->scan_directory_for_files( $html_templates_dir, 'html' );
			foreach ( $html_templates as $template_file ) {
				$relative_path = str_replace( $html_templates_dir . '/', '', $template_file );
				$destination = $templates_export_dir . $relative_path;
				
				// Create subdirectories if needed
				$destination_dir = dirname( $destination );
				if ( ! file_exists( $destination_dir ) ) {
					wp_mkdir_p( $destination_dir );
				}

				if ( copy( $template_file, $destination ) ) {
					$exported_templates[] = array(
						'file' => $relative_path,
						'type' => 'html',
						'path' => 'theme/templates/' . $relative_path,
					);
				}
			}
		}

		return array(
			'success' => ! empty( $exported_templates ),
			'count'   => count( $exported_templates ),
			'files'   => $exported_templates,
		);
	}

	/**
	 * Export template parts.
	 *
	 * @return array Export status with list of exported template parts.
	 */
	private function export_template_parts() {
		$theme_dir = $this->theme->get_stylesheet_directory();
		$template_parts_dir = $theme_dir . '/template-parts';
		$exported_parts = array();

		if ( ! is_dir( $template_parts_dir ) ) {
			return array(
				'success' => false,
				'message' => 'No template-parts directory found',
			);
		}

		// Create template-parts export directory
		$parts_export_dir = $this->theme_export_dir . 'template-parts/';
		if ( ! file_exists( $parts_export_dir ) ) {
			wp_mkdir_p( $parts_export_dir );
		}

		// Scan for PHP and HTML template parts
		$template_part_files = $this->scan_directory_recursive( $template_parts_dir, array( 'php', 'html' ) );

		foreach ( $template_part_files as $part_file ) {
			$relative_path = str_replace( $template_parts_dir . '/', '', $part_file );
			$destination = $parts_export_dir . $relative_path;

			// Create subdirectories if needed
			$destination_dir = dirname( $destination );
			if ( ! file_exists( $destination_dir ) ) {
				wp_mkdir_p( $destination_dir );
			}

			if ( copy( $part_file, $destination ) ) {
				$exported_parts[] = array(
					'file' => $relative_path,
					'type' => pathinfo( $part_file, PATHINFO_EXTENSION ),
					'path' => 'theme/template-parts/' . $relative_path,
				);
			}
		}

		return array(
			'success' => ! empty( $exported_parts ),
			'count'   => count( $exported_parts ),
			'files'   => $exported_parts,
		);
	}

	/**
	 * Export parent theme files if this is a child theme.
	 *
	 * @return array Export status.
	 */
	private function export_parent_theme_files() {
		if ( ! $this->parent_theme ) {
			return array(
				'success' => false,
				'message' => 'Not a child theme',
			);
		}

		$parent_dir = $this->parent_theme->get_stylesheet_directory();
		$parent_export_dir = $this->theme_export_dir . 'parent-theme/';
		
		if ( ! file_exists( $parent_export_dir ) ) {
			wp_mkdir_p( $parent_export_dir );
		}

		$exported_files = array();

		// Export parent style.css
		$parent_style = $parent_dir . '/style.css';
		if ( file_exists( $parent_style ) ) {
			if ( copy( $parent_style, $parent_export_dir . 'style.css' ) ) {
				$exported_files[] = 'style.css';
			}
		}

		// Export parent theme.json if exists
		$parent_theme_json = $parent_dir . '/theme.json';
		if ( file_exists( $parent_theme_json ) ) {
			if ( copy( $parent_theme_json, $parent_export_dir . 'theme.json' ) ) {
				$exported_files[] = 'theme.json';
			}
		}

		// Export parent functions.php
		$parent_functions = $parent_dir . '/functions.php';
		if ( file_exists( $parent_functions ) ) {
			if ( copy( $parent_functions, $parent_export_dir . 'functions.php' ) ) {
				$exported_files[] = 'functions.php';
			}
		}

		return array(
			'success' => ! empty( $exported_files ),
			'count'   => count( $exported_files ),
			'files'   => $exported_files,
		);
	}

	/**
	 * Scan directory for files with specific extension.
	 *
	 * @param string $dir Directory path.
	 * @param string $extension File extension to look for.
	 * @return array List of file paths.
	 */
	private function scan_directory_for_files( $dir, $extension ) {
		$files = array();

		if ( ! is_dir( $dir ) ) {
			return $files;
		}

		$items = scandir( $dir );
		foreach ( $items as $item ) {
			if ( $item === '.' || $item === '..' ) {
				continue;
			}

			$path = $dir . '/' . $item;
			
			if ( is_file( $path ) && pathinfo( $path, PATHINFO_EXTENSION ) === $extension ) {
				$files[] = $path;
			}
		}

		return $files;
	}

	/**
	 * Recursively scan directory for files with specific extensions.
	 *
	 * @param string $dir Directory path.
	 * @param array  $extensions File extensions to look for.
	 * @return array List of file paths.
	 */
	private function scan_directory_recursive( $dir, $extensions ) {
		$files = array();

		if ( ! is_dir( $dir ) ) {
			return $files;
		}

		$items = scandir( $dir );
		foreach ( $items as $item ) {
			if ( $item === '.' || $item === '..' ) {
				continue;
			}

			$path = $dir . '/' . $item;

			if ( is_dir( $path ) ) {
				// Recursively scan subdirectories
				$files = array_merge( $files, $this->scan_directory_recursive( $path, $extensions ) );
			} elseif ( is_file( $path ) ) {
				$ext = pathinfo( $path, PATHINFO_EXTENSION );
				if ( in_array( $ext, $extensions, true ) ) {
					$files[] = $path;
				}
			}
		}

		return $files;
	}

	/**
	 * Generate template hierarchy documentation.
	 *
	 * Documents which templates are used for which content types
	 * according to WordPress template hierarchy.
	 *
	 * @return array Template hierarchy data.
	 */
	private function generate_template_hierarchy() {
		$theme_dir = $this->theme->get_stylesheet_directory();
		$hierarchy = array();

		// Define WordPress template hierarchy
		$template_mappings = array(
			'front_page' => array(
				'description' => 'Front page of the site',
				'templates'   => array( 'front-page.php', 'home.php', 'index.php' ),
			),
			'home' => array(
				'description' => 'Blog posts index page',
				'templates'   => array( 'home.php', 'index.php' ),
			),
			'single_post' => array(
				'description' => 'Single blog post',
				'templates'   => array( 'single.php', 'singular.php', 'index.php' ),
			),
			'page' => array(
				'description' => 'Static page',
				'templates'   => array( 'page.php', 'singular.php', 'index.php' ),
			),
			'archive' => array(
				'description' => 'Archive pages (category, tag, date, author)',
				'templates'   => array( 'archive.php', 'index.php' ),
			),
			'category' => array(
				'description' => 'Category archive',
				'templates'   => array( 'category.php', 'archive.php', 'index.php' ),
			),
			'tag' => array(
				'description' => 'Tag archive',
				'templates'   => array( 'tag.php', 'archive.php', 'index.php' ),
			),
			'author' => array(
				'description' => 'Author archive',
				'templates'   => array( 'author.php', 'archive.php', 'index.php' ),
			),
			'date' => array(
				'description' => 'Date archive',
				'templates'   => array( 'date.php', 'archive.php', 'index.php' ),
			),
			'search' => array(
				'description' => 'Search results',
				'templates'   => array( 'search.php', 'index.php' ),
			),
			'404' => array(
				'description' => 'Not found error page',
				'templates'   => array( '404.php', 'index.php' ),
			),
			'attachment' => array(
				'description' => 'Attachment page',
				'templates'   => array( 'attachment.php', 'single.php', 'singular.php', 'index.php' ),
			),
		);

		// Check which templates exist for each content type
		foreach ( $template_mappings as $type => $config ) {
			$found_template = null;
			
			foreach ( $config['templates'] as $template ) {
				if ( file_exists( $theme_dir . '/' . $template ) ) {
					$found_template = $template;
					break;
				}
			}

			$hierarchy[ $type ] = array(
				'description'     => $config['description'],
				'template_used'   => $found_template,
				'fallback_chain'  => $config['templates'],
			);
		}

		// Add custom page templates
		$page_templates = $this->theme->get_page_templates();
		if ( ! empty( $page_templates ) ) {
			$hierarchy['custom_page_templates'] = array();
			foreach ( $page_templates as $template_file => $template_name ) {
				$hierarchy['custom_page_templates'][ $template_file ] = array(
					'name'        => $template_name,
					'file'        => $template_file,
					'exists'      => file_exists( $theme_dir . '/' . $template_file ),
				);
			}
		}

		// Add custom post type templates if any exist
		$post_types = get_post_types( array( 'public' => true, '_builtin' => false ), 'objects' );
		if ( ! empty( $post_types ) ) {
			$hierarchy['custom_post_types'] = array();
			
			foreach ( $post_types as $post_type ) {
				$cpt_templates = array(
					'single-' . $post_type->name . '.php',
					'archive-' . $post_type->name . '.php',
				);

				$found_single = null;
				$found_archive = null;

				foreach ( $cpt_templates as $template ) {
					if ( file_exists( $theme_dir . '/' . $template ) ) {
						if ( strpos( $template, 'single-' ) === 0 ) {
							$found_single = $template;
						} elseif ( strpos( $template, 'archive-' ) === 0 ) {
							$found_archive = $template;
						}
					}
				}

				$hierarchy['custom_post_types'][ $post_type->name ] = array(
					'label'            => $post_type->label,
					'single_template'  => $found_single,
					'archive_template' => $found_archive,
				);
			}
		}

		// Save template hierarchy to JSON file
		$hierarchy_json = wp_json_encode( $hierarchy, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES );
		if ( $hierarchy_json ) {
			file_put_contents( $this->theme_export_dir . 'template_hierarchy.json', $hierarchy_json );
		}

		return $hierarchy;
	}

	/**
	 * Export theme mods (theme customizer settings).
	 *
	 * @return array Export status and data.
	 */
	private function export_theme_mods() {
		$theme_slug = $this->theme->get_stylesheet();
		$theme_mods = get_theme_mods();

		if ( empty( $theme_mods ) ) {
			return array(
				'success' => false,
				'message' => 'No theme mods found',
			);
		}

		// Save theme mods to JSON file
		$theme_mods_data = array(
			'theme_slug' => $theme_slug,
			'mods'       => $theme_mods,
		);

		$json = wp_json_encode( $theme_mods_data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES );
		if ( $json ) {
			$file_path = $this->theme_export_dir . 'theme_mods.json';
			$written = file_put_contents( $file_path, $json );
			
			return array(
				'success' => $written !== false,
				'path'    => 'theme/theme_mods.json',
				'count'   => count( $theme_mods ),
			);
		}

		return array(
			'success' => false,
			'error'   => 'Failed to encode theme mods to JSON',
		);
	}

	/**
	 * Export customizer custom CSS.
	 *
	 * @return array Export status.
	 */
	private function export_customizer_css() {
		// Get the custom CSS post ID from options
		$custom_css_post_id = get_option( 'custom_css_post_id' );

		if ( ! $custom_css_post_id ) {
			return array(
				'success' => false,
				'message' => 'No customizer custom CSS found',
			);
		}

		// Get the custom CSS post
		$custom_css_post = get_post( $custom_css_post_id );

		if ( ! $custom_css_post || $custom_css_post->post_type !== 'custom_css' ) {
			return array(
				'success' => false,
				'message' => 'Custom CSS post not found or invalid',
			);
		}

		// Get the CSS content
		$css_content = $custom_css_post->post_content;

		if ( empty( $css_content ) ) {
			return array(
				'success' => false,
				'message' => 'Custom CSS content is empty',
			);
		}

		// Save CSS to file
		$file_path = $this->theme_export_dir . 'customizer_custom.css';
		$written = file_put_contents( $file_path, $css_content );

		return array(
			'success' => $written !== false,
			'path'    => 'theme/customizer_custom.css',
			'size'    => $written !== false ? $written : 0,
		);
	}

	/**
	 * Export global styles for block themes.
	 *
	 * @return array Export status and data.
	 */
	private function export_global_styles() {
		// Query for wp_global_styles posts
		$global_styles_posts = get_posts(
			array(
				'post_type'      => 'wp_global_styles',
				'posts_per_page' => -1,
				'post_status'    => 'publish',
			)
		);

		if ( empty( $global_styles_posts ) ) {
			return array(
				'success' => false,
				'message' => 'No global styles found (not a block theme or no custom styles)',
			);
		}

		$global_styles_data = array();

		foreach ( $global_styles_posts as $post ) {
			$styles_data = array(
				'id'            => $post->ID,
				'title'         => $post->post_title,
				'content'       => json_decode( $post->post_content, true ),
				'status'        => $post->post_status,
				'date_modified' => $post->post_modified_gmt,
			);

			$global_styles_data[] = $styles_data;
		}

		// Save global styles to JSON file
		$json = wp_json_encode( $global_styles_data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES );
		if ( $json ) {
			$file_path = $this->theme_export_dir . 'global_styles.json';
			$written = file_put_contents( $file_path, $json );

			return array(
				'success' => $written !== false,
				'path'    => 'theme/global_styles.json',
				'count'   => count( $global_styles_data ),
			);
		}

		return array(
			'success' => false,
			'error'   => 'Failed to encode global styles to JSON',
		);
	}

	/**
	 * Scan for custom CSS in various locations.
	 *
	 * @return array Export status and CSS sources documentation.
	 */
	private function scan_custom_css_sources() {
		$css_sources = array();

		// 1. Check for custom CSS in theme options
		$theme_slug = $this->theme->get_stylesheet();
		$theme_options = get_option( 'theme_mods_' . $theme_slug );
		
		if ( is_array( $theme_options ) ) {
			foreach ( $theme_options as $key => $value ) {
				if ( ( strpos( $key, 'css' ) !== false || strpos( $key, 'style' ) !== false ) && is_string( $value ) && ! empty( $value ) ) {
					$css_sources[] = array(
						'source'      => 'theme_options',
						'option_name' => $key,
						'location'    => 'wp_options: theme_mods_' . $theme_slug,
						'has_content' => true,
					);

					// Save this CSS to a file
					$safe_key = sanitize_file_name( $key );
					$file_path = $this->theme_export_dir . 'theme_option_' . $safe_key . '.css';
					file_put_contents( $file_path, $value );
				}
			}
		}

		// 2. Check for common custom CSS plugins
		$css_plugins = array(
			'simple-custom-css'           => 'custom-css-js',
			'wp-add-custom-css'           => 'wp-add-custom-css',
			'custom-css-js'               => 'custom-css-js',
			'yellow-pencil-visual-theme-customizer' => 'waspthemes_yellow_pencil',
		);

		foreach ( $css_plugins as $plugin_slug => $option_prefix ) {
			if ( is_plugin_active( $plugin_slug . '/' . $plugin_slug . '.php' ) || is_plugin_active( $plugin_slug . '/index.php' ) ) {
				// Try to get CSS from common option names
				$possible_options = array(
					$option_prefix . '_custom_css',
					$option_prefix . '_css',
					$option_prefix,
				);

				foreach ( $possible_options as $option_name ) {
					$css_content = get_option( $option_name );
					if ( ! empty( $css_content ) && is_string( $css_content ) ) {
						$css_sources[] = array(
							'source'      => 'plugin',
							'plugin_slug' => $plugin_slug,
							'option_name' => $option_name,
							'location'    => 'wp_options: ' . $option_name,
							'has_content' => true,
						);

						// Save this CSS to a file
						$safe_slug = sanitize_file_name( $plugin_slug );
						$file_path = $this->theme_export_dir . 'plugin_' . $safe_slug . '_custom.css';
						file_put_contents( $file_path, $css_content );
					}
				}
			}
		}

		// 3. Check for page builder custom CSS (Elementor, Beaver Builder, etc.)
		$page_builders = array(
			'elementor' => array(
				'option' => 'elementor_custom_css',
				'check'  => 'elementor/elementor.php',
			),
			'beaver-builder' => array(
				'option' => '_fl_builder_custom_css',
				'check'  => 'beaver-builder-lite-version/fl-builder.php',
			),
		);

		foreach ( $page_builders as $builder_slug => $config ) {
			if ( is_plugin_active( $config['check'] ) ) {
				$css_content = get_option( $config['option'] );
				if ( ! empty( $css_content ) && is_string( $css_content ) ) {
					$css_sources[] = array(
						'source'      => 'page_builder',
						'builder'     => $builder_slug,
						'option_name' => $config['option'],
						'location'    => 'wp_options: ' . $config['option'],
						'has_content' => true,
					);

					// Save this CSS to a file
					$safe_slug = sanitize_file_name( $builder_slug );
					$file_path = $this->theme_export_dir . 'pagebuilder_' . $safe_slug . '_custom.css';
					file_put_contents( $file_path, $css_content );
				}
			}
		}

		// 4. Check for Additional CSS in customizer (already handled by customizer_custom.css)
		$custom_css_post_id = get_option( 'custom_css_post_id' );
		if ( $custom_css_post_id ) {
			$css_sources[] = array(
				'source'      => 'customizer',
				'option_name' => 'custom_css_post_id',
				'location'    => 'wp_posts (custom_css post type)',
				'has_content' => true,
				'file'        => 'customizer_custom.css',
			);
		}

		// Save CSS sources documentation to JSON
		$css_sources_data = array(
			'schema_version' => 1,
			'scan_date'      => current_time( 'mysql' ),
			'sources_found'  => count( $css_sources ),
			'sources'        => $css_sources,
		);

		$json = wp_json_encode( $css_sources_data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES );
		if ( $json ) {
			$file_path = $this->theme_export_dir . 'css_sources.json';
			file_put_contents( $file_path, $json );
		}

		return array(
			'success'       => true,
			'sources_found' => count( $css_sources ),
			'sources'       => $css_sources,
			'path'          => 'theme/css_sources.json',
		);
	}

	/**
	 * Export block editor color palettes and typography settings.
	 *
	 * @return array Export status and settings data.
	 */
	private function export_editor_settings() {
		$editor_settings = array();

		// Get theme support for editor color palette
		$color_palette = get_theme_support( 'editor-color-palette' );
		if ( $color_palette && is_array( $color_palette ) ) {
			$editor_settings['color_palette'] = $color_palette[0];
		}

		// Get theme support for editor gradient presets
		$gradient_presets = get_theme_support( 'editor-gradient-presets' );
		if ( $gradient_presets && is_array( $gradient_presets ) ) {
			$editor_settings['gradient_presets'] = $gradient_presets[0];
		}

		// Get theme support for editor font sizes
		$font_sizes = get_theme_support( 'editor-font-sizes' );
		if ( $font_sizes && is_array( $font_sizes ) ) {
			$editor_settings['font_sizes'] = $font_sizes[0];
		}

		// Get theme support for custom line height
		$custom_line_height = get_theme_support( 'custom-line-height' );
		if ( $custom_line_height ) {
			$editor_settings['custom_line_height'] = true;
		}

		// Get theme support for custom spacing
		$custom_spacing = get_theme_support( 'custom-spacing' );
		if ( $custom_spacing ) {
			$editor_settings['custom_spacing'] = true;
		}

		// Get theme support for custom units
		$custom_units = get_theme_support( 'custom-units' );
		if ( $custom_units && is_array( $custom_units ) ) {
			$editor_settings['custom_units'] = $custom_units[0];
		}

		// For block themes, parse theme.json for additional settings
		if ( $this->is_block_theme() ) {
			$theme_json_path = $this->theme->get_stylesheet_directory() . '/theme.json';
			if ( file_exists( $theme_json_path ) ) {
				$theme_json_content = file_get_contents( $theme_json_path );
				$theme_json_data = json_decode( $theme_json_content, true );

				if ( $theme_json_data && isset( $theme_json_data['settings'] ) ) {
					// Extract color settings
					if ( isset( $theme_json_data['settings']['color'] ) ) {
						$editor_settings['theme_json_color_settings'] = $theme_json_data['settings']['color'];
					}

					// Extract typography settings
					if ( isset( $theme_json_data['settings']['typography'] ) ) {
						$editor_settings['theme_json_typography_settings'] = $theme_json_data['settings']['typography'];
					}

					// Extract spacing settings
					if ( isset( $theme_json_data['settings']['spacing'] ) ) {
						$editor_settings['theme_json_spacing_settings'] = $theme_json_data['settings']['spacing'];
					}

					// Extract layout settings
					if ( isset( $theme_json_data['settings']['layout'] ) ) {
						$editor_settings['theme_json_layout_settings'] = $theme_json_data['settings']['layout'];
					}
				}
			}
		}

		if ( empty( $editor_settings ) ) {
			return array(
				'success' => false,
				'message' => 'No editor settings found',
			);
		}

		// Save editor settings to JSON file
		$editor_settings_data = array(
			'schema_version' => 1,
			'settings'       => $editor_settings,
		);

		$json = wp_json_encode( $editor_settings_data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES );
		if ( $json ) {
			$file_path = $this->theme_export_dir . 'editor_settings.json';
			$written = file_put_contents( $file_path, $json );

			return array(
				'success'        => $written !== false,
				'path'           => 'theme/editor_settings.json',
				'settings_count' => count( $editor_settings ),
			);
		}

		return array(
			'success' => false,
			'error'   => 'Failed to encode editor settings to JSON',
		);
	}

	/**
	 * Create manifest of theme assets directory.
	 *
	 * Scans the theme's /assets/ directory and creates a manifest
	 * documenting all asset files with their paths, types, and metadata.
	 *
	 * @return array Export status and manifest data.
	 */
	private function create_assets_manifest() {
		$theme_dir = $this->theme->get_stylesheet_directory();
		$assets_dir = $theme_dir . '/assets';

		// Check if assets directory exists
		if ( ! is_dir( $assets_dir ) ) {
			return array(
				'success' => false,
				'message' => 'No assets directory found in theme',
			);
		}

		// Scan assets directory recursively
		$assets = $this->scan_assets_directory( $assets_dir, $assets_dir );

		if ( empty( $assets ) ) {
			return array(
				'success' => false,
				'message' => 'No assets found in assets directory',
			);
		}

		// Organize assets by type
		$assets_by_type = array(
			'css'    => array(),
			'js'     => array(),
			'images' => array(),
			'fonts'  => array(),
			'other'  => array(),
		);

		foreach ( $assets as $asset ) {
			$type = $this->categorize_asset_type( $asset['extension'] );
			$assets_by_type[ $type ][] = $asset;
		}

		// Create manifest data
		$manifest_data = array(
			'schema_version' => 1,
			'scan_date'      => current_time( 'mysql' ),
			'theme_slug'     => $this->theme->get_stylesheet(),
			'assets_dir'     => 'assets/',
			'total_files'    => count( $assets ),
			'assets_by_type' => array(
				'css'    => count( $assets_by_type['css'] ),
				'js'     => count( $assets_by_type['js'] ),
				'images' => count( $assets_by_type['images'] ),
				'fonts'  => count( $assets_by_type['fonts'] ),
				'other'  => count( $assets_by_type['other'] ),
			),
			'assets'         => $assets_by_type,
		);

		// Save manifest to JSON file
		$json = wp_json_encode( $manifest_data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES );
		if ( $json ) {
			$file_path = $this->export_dir . 'assets_manifest.json';
			$written = file_put_contents( $file_path, $json );

			return array(
				'success'     => $written !== false,
				'path'        => 'assets_manifest.json',
				'total_files' => count( $assets ),
				'by_type'     => $manifest_data['assets_by_type'],
			);
		}

		return array(
			'success' => false,
			'error'   => 'Failed to encode assets manifest to JSON',
		);
	}

	/**
	 * Recursively scan assets directory for files.
	 *
	 * @param string $dir Current directory being scanned.
	 * @param string $base_dir Base assets directory for relative path calculation.
	 * @return array List of asset files with metadata.
	 */
	private function scan_assets_directory( $dir, $base_dir ) {
		$assets = array();

		if ( ! is_dir( $dir ) ) {
			return $assets;
		}

		$items = scandir( $dir );
		foreach ( $items as $item ) {
			if ( $item === '.' || $item === '..' ) {
				continue;
			}

			$path = $dir . '/' . $item;

			if ( is_dir( $path ) ) {
				// Recursively scan subdirectories
				$assets = array_merge( $assets, $this->scan_assets_directory( $path, $base_dir ) );
			} elseif ( is_file( $path ) ) {
				// Get relative path from assets directory
				$relative_path = str_replace( $base_dir . '/', '', $path );

				// Get file information
				$file_info = array(
					'path'      => $relative_path,
					'filename'  => basename( $path ),
					'extension' => strtolower( pathinfo( $path, PATHINFO_EXTENSION ) ),
					'size'      => filesize( $path ),
					'modified'  => date( 'Y-m-d H:i:s', filemtime( $path ) ),
				);

				$assets[] = $file_info;
			}
		}

		return $assets;
	}

	/**
	 * Categorize asset by file extension.
	 *
	 * @param string $extension File extension.
	 * @return string Asset category (css, js, images, fonts, other).
	 */
	private function categorize_asset_type( $extension ) {
		$type_map = array(
			'css'  => array( 'css', 'scss', 'sass', 'less' ),
			'js'   => array( 'js', 'jsx', 'ts', 'tsx', 'mjs' ),
			'images' => array( 'jpg', 'jpeg', 'png', 'gif', 'svg', 'webp', 'ico', 'bmp' ),
			'fonts' => array( 'woff', 'woff2', 'ttf', 'otf', 'eot' ),
		);

		foreach ( $type_map as $type => $extensions ) {
			if ( in_array( $extension, $extensions, true ) ) {
				return $type;
			}
		}

		return 'other';
	}
}
