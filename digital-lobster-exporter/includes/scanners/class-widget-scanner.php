<?php
/**
 * Widget Scanner
 *
 * Exports widget and sidebar configurations.
 *
 * @package Digital_Lobster_Exporter
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Class Widget_Scanner
 *
 * Collects and exports WordPress widgets and sidebars including:
 * - All registered sidebars
 * - All active widgets with settings
 * - Text widget content including HTML and shortcodes
 * - Filters out widgets with PII
 */
class Widget_Scanner {

	/**
	 * PII-sensitive widget types to filter
	 *
	 * @var array
	 */
	private $sensitive_widgets = array(
		'recent-comments',
		'rss',
	);

	/**
	 * Scan and collect widget data
	 *
	 * @return array Widget data
	 */
	public function scan() {
		$data = array(
			'schema_version' => 1,
			'sidebars'       => $this->get_sidebars(),
			'widgets'        => $this->get_widgets(),
		);

		return $data;
	}

	/**
	 * Get all registered sidebars
	 *
	 * @return array Sidebars
	 */
	private function get_sidebars() {
		global $wp_registered_sidebars;
		
		$sidebars = array();
		
		if ( empty( $wp_registered_sidebars ) ) {
			return $sidebars;
		}
		
		foreach ( $wp_registered_sidebars as $sidebar ) {
			$sidebars[ $sidebar['id'] ] = array(
				'name'          => $sidebar['name'],
				'id'            => $sidebar['id'],
				'description'   => isset( $sidebar['description'] ) ? $sidebar['description'] : '',
				'class'         => isset( $sidebar['class'] ) ? $sidebar['class'] : '',
				'before_widget' => isset( $sidebar['before_widget'] ) ? $sidebar['before_widget'] : '',
				'after_widget'  => isset( $sidebar['after_widget'] ) ? $sidebar['after_widget'] : '',
				'before_title'  => isset( $sidebar['before_title'] ) ? $sidebar['before_title'] : '',
				'after_title'   => isset( $sidebar['after_title'] ) ? $sidebar['after_title'] : '',
			);
		}
		
		return $sidebars;
	}

	/**
	 * Get all active widgets
	 *
	 * @return array Widgets organized by sidebar
	 */
	private function get_widgets() {
		$sidebars_widgets = wp_get_sidebars_widgets();
		$result = array();
		
		if ( empty( $sidebars_widgets ) ) {
			return $result;
		}
		
		foreach ( $sidebars_widgets as $sidebar_id => $widget_ids ) {
			// Skip inactive widgets and wp_inactive_widgets
			if ( 'wp_inactive_widgets' === $sidebar_id || empty( $widget_ids ) ) {
				continue;
			}
			
			$result[ $sidebar_id ] = array();
			
			foreach ( $widget_ids as $widget_id ) {
				$widget_data = $this->get_widget_data( $widget_id );
				
				if ( $widget_data ) {
					$result[ $sidebar_id ][] = $widget_data;
				}
			}
		}
		
		return $result;
	}

	/**
	 * Get data for a specific widget
	 *
	 * @param string $widget_id Widget ID
	 * @return array|null Widget data or null if filtered
	 */
	private function get_widget_data( $widget_id ) {
		global $wp_registered_widgets;
		
		if ( ! isset( $wp_registered_widgets[ $widget_id ] ) ) {
			return null;
		}
		
		$widget = $wp_registered_widgets[ $widget_id ];
		
		// Parse widget ID to get base ID and instance number
		$parsed = $this->parse_widget_id( $widget_id );
		
		if ( ! $parsed ) {
			return null;
		}
		
		// Check if this is a sensitive widget type
		if ( $this->is_sensitive_widget( $parsed['base'] ) ) {
			return array(
				'id'       => $widget_id,
				'type'     => $parsed['base'],
				'name'     => $widget['name'],
				'filtered' => true,
				'reason'   => 'Contains potentially sensitive information',
			);
		}
		
		// Get widget settings
		$settings = $this->get_widget_settings( $parsed['base'], $parsed['number'] );
		
		// Filter PII from settings
		$settings = $this->filter_pii_from_settings( $settings );
		
		$widget_data = array(
			'id'       => $widget_id,
			'type'     => $parsed['base'],
			'name'     => $widget['name'],
			'settings' => $settings,
		);
		
		// Add additional metadata
		if ( isset( $widget['classname'] ) ) {
			$widget_data['classname'] = $widget['classname'];
		}
		
		return $widget_data;
	}

	/**
	 * Parse widget ID into base and number
	 *
	 * @param string $widget_id Widget ID (e.g., 'text-2')
	 * @return array|null Parsed data or null
	 */
	private function parse_widget_id( $widget_id ) {
		if ( preg_match( '/^(.+)-(\d+)$/', $widget_id, $matches ) ) {
			return array(
				'base'   => $matches[1],
				'number' => (int) $matches[2],
			);
		}
		
		return null;
	}

	/**
	 * Check if widget type is sensitive
	 *
	 * @param string $widget_base Widget base ID
	 * @return bool True if sensitive
	 */
	private function is_sensitive_widget( $widget_base ) {
		return in_array( $widget_base, $this->sensitive_widgets, true );
	}

	/**
	 * Get widget settings from options
	 *
	 * @param string $widget_base Widget base ID
	 * @param int    $widget_number Widget instance number
	 * @return array Widget settings
	 */
	private function get_widget_settings( $widget_base, $widget_number ) {
		$option_name = 'widget_' . $widget_base;
		$all_instances = get_option( $option_name, array() );
		
		if ( isset( $all_instances[ $widget_number ] ) ) {
			return $all_instances[ $widget_number ];
		}
		
		return array();
	}

	/**
	 * Filter PII from widget settings
	 *
	 * @param array $settings Widget settings
	 * @return array Filtered settings
	 */
	private function filter_pii_from_settings( $settings ) {
		if ( empty( $settings ) || ! is_array( $settings ) ) {
			return $settings;
		}
		
		// List of keys that might contain PII
		$pii_keys = array(
			'email',
			'author_email',
			'user_email',
			'contact_email',
			'phone',
			'telephone',
			'address',
			'street',
			'city',
			'zip',
			'postal_code',
		);
		
		foreach ( $pii_keys as $key ) {
			if ( isset( $settings[ $key ] ) ) {
				$settings[ $key ] = '[filtered-pii]';
			}
		}
		
		// Filter email addresses from text content
		if ( isset( $settings['text'] ) ) {
			$settings['text'] = $this->filter_emails_from_text( $settings['text'] );
		}
		
		if ( isset( $settings['content'] ) ) {
			$settings['content'] = $this->filter_emails_from_text( $settings['content'] );
		}
		
		return $settings;
	}

	/**
	 * Filter email addresses from text content
	 *
	 * @param string $text Text content
	 * @return string Filtered text
	 */
	private function filter_emails_from_text( $text ) {
		if ( empty( $text ) ) {
			return $text;
		}
		
		// Replace email addresses with placeholder
		$text = preg_replace(
			'/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/',
			'[email]',
			$text
		);
		
		return $text;
	}

	/**
	 * Export widgets to JSON file
	 *
	 * @param string $export_dir Export directory path
	 * @return bool Success status
	 */
	public function export( $export_dir ) {
		$widgets = $this->scan();

		$file_path = trailingslashit( $export_dir ) . 'widgets.json';

		$json = wp_json_encode( $widgets, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES );

		if ( false === $json ) {
			error_log( 'Digital Lobster Exporter: Failed to encode widgets to JSON' );
			return false;
		}

		$result = file_put_contents( $file_path, $json );

		if ( false === $result ) {
			error_log( 'Digital Lobster Exporter: Failed to write widgets.json' );
			return false;
		}

		return true;
	}
}
