<?php
/**
 * Source Identifier Utility
 *
 * Identifies the source (plugin, theme, or WordPress core) of a file path.
 * Consolidates the duplicated identify_source_from_file() and get_plugin_data()
 * logic from Hooks_Scanner, Shortcode_Scanner, REST_API_Scanner, and Plugin_Scanner.
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Source Identifier Utility Class
 */
class Digital_Lobster_Exporter_Source_Identifier {

	/**
	 * Identify the source of a file path.
	 *
	 * Determines whether a given absolute file path belongs to WordPress core,
	 * a plugin, the parent theme, the child theme, or is unknown.
	 *
	 * @param string $filename Absolute file path.
	 * @return array {
	 *     type: string ('plugin'|'theme'|'core'|'unknown'),
	 *     name: string,
	 *     slug?: string
	 * }
	 */
	public static function identify( $filename ) {
		$source = array(
			'type' => 'unknown',
			'name' => 'Unknown',
		);

		if ( empty( $filename ) ) {
			return $source;
		}

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
				$plugin_data = self::get_plugin_data( $plugin_slug );

				$source['type'] = 'plugin';
				$source['name'] = $plugin_data['name'];
				$source['slug'] = $plugin_slug;
			}

			return $source;
		}

		// Check if it's from the parent theme.
		if ( strpos( $filename, get_template_directory() ) !== false ) {
			$theme          = wp_get_theme( get_template() );
			$source['type'] = 'theme';
			$source['name'] = $theme->get( 'Name' );
			$source['slug'] = get_template();
			return $source;
		}

		// Check if it's from the child theme.
		if ( strpos( $filename, get_stylesheet_directory() ) !== false ) {
			$theme          = wp_get_theme();
			$source['type'] = 'theme';
			$source['name'] = $theme->get( 'Name' );
			$source['slug'] = get_stylesheet();
			return $source;
		}

		return $source;
	}

	/**
	 * Get plugin data from a plugin slug.
	 *
	 * Looks up the plugin name from get_plugins(), falling back to a humanized slug.
	 *
	 * @param string $plugin_slug Plugin directory name.
	 * @return array { name: string, file: string }
	 */
	public static function get_plugin_data( $plugin_slug ) {
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

		// Fallback: humanize the slug.
		return array(
			'name' => ucwords( str_replace( array( '-', '_' ), ' ', $plugin_slug ) ),
			'file' => '',
		);
	}
}
