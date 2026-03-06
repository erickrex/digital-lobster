<?php
/**
 * ACF and Custom Fields Scanner Class
 *
 * Detects and exports Advanced Custom Fields (ACF) field group configurations,
 * as well as other custom field plugins like Pods, Metabox, and Carbon Fields.
 * Exports field types, settings, conditional logic, and location rules.
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * ACF and Custom Fields Scanner Class
 */
class Digital_Lobster_Exporter_ACF_Scanner {

	/**
	 * Export directory path.
	 *
	 * @var string
	 */
	private $export_dir;

	/**
	 * Detected custom field plugins.
	 *
	 * @var array
	 */
	private $detected_plugins = array();

	/**
	 * Constructor.
	 *
	 * @param string $export_dir Export directory path.
	 */
	public function __construct( $export_dir = '' ) {
		$this->export_dir = $export_dir;
		$this->detect_custom_field_plugins();
	}

	/**
	 * Detect which custom field plugins are active.
	 */
	private function detect_custom_field_plugins() {
		// Check for ACF
		if ( class_exists( 'ACF' ) || function_exists( 'acf' ) ) {
			$this->detected_plugins['acf'] = true;
		}

		// Check for ACF Pro
		if ( defined( 'ACF_PRO' ) && ACF_PRO ) {
			$this->detected_plugins['acf_pro'] = true;
		}

		// Check for Pods
		if ( class_exists( 'Pods' ) || function_exists( 'pods' ) ) {
			$this->detected_plugins['pods'] = true;
		}

		// Check for Metabox
		if ( class_exists( 'RWMB_Core' ) || function_exists( 'rwmb_meta' ) ) {
			$this->detected_plugins['metabox'] = true;
		}

		// Check for Carbon Fields
		if ( class_exists( 'Carbon_Fields\\Container' ) ) {
			$this->detected_plugins['carbon_fields'] = true;
		}
	}

	/**
	 * Scan and collect ACF and custom field configurations.
	 *
	 * @return array Scan results.
	 */
	public function scan() {
		$results = array(
			'detected_plugins' => $this->detected_plugins,
			'acf_field_groups' => array(),
			'custom_fields_config' => array(),
		);

		// Export ACF field groups if ACF is active
		if ( ! empty( $this->detected_plugins['acf'] ) ) {
			$results['acf_field_groups'] = $this->export_acf_field_groups();
		}

		// Export other custom field configurations
		$results['custom_fields_config'] = $this->export_other_custom_fields();

		// Save to JSON files
		$this->save_to_files( $results );

		return $results;
	}

	/**
	 * Export ACF field groups with full configuration.
	 *
	 * @return array ACF field groups data.
	 */
	private function export_acf_field_groups() {
		$field_groups = array();

		// Check if ACF functions are available
		if ( ! function_exists( 'acf_get_field_groups' ) ) {
			return $field_groups;
		}

		// Get all field groups
		$groups = acf_get_field_groups();

		if ( empty( $groups ) ) {
			return $field_groups;
		}

		foreach ( $groups as $group ) {
			$group_data = array(
				'key' => $group['key'],
				'title' => $group['title'],
				'fields' => array(),
				'location' => isset( $group['location'] ) ? $group['location'] : array(),
				'menu_order' => isset( $group['menu_order'] ) ? $group['menu_order'] : 0,
				'position' => isset( $group['position'] ) ? $group['position'] : 'normal',
				'style' => isset( $group['style'] ) ? $group['style'] : 'default',
				'label_placement' => isset( $group['label_placement'] ) ? $group['label_placement'] : 'top',
				'instruction_placement' => isset( $group['instruction_placement'] ) ? $group['instruction_placement'] : 'label',
				'hide_on_screen' => isset( $group['hide_on_screen'] ) ? $group['hide_on_screen'] : array(),
				'description' => isset( $group['description'] ) ? $group['description'] : '',
				'active' => isset( $group['active'] ) ? $group['active'] : true,
			);

			// Get fields for this group
			if ( function_exists( 'acf_get_fields' ) ) {
				$fields = acf_get_fields( $group['key'] );
				
				if ( ! empty( $fields ) ) {
					$group_data['fields'] = $this->process_acf_fields( $fields );
				}
			}

			$field_groups[] = $group_data;
		}

		return $field_groups;
	}

	/**
	 * Process ACF fields recursively (handles nested fields).
	 *
	 * @param array $fields ACF fields array.
	 * @return array Processed fields data.
	 */
	private function process_acf_fields( $fields ) {
		$processed_fields = array();

		foreach ( $fields as $field ) {
			$field_data = array(
				'key' => $field['key'],
				'label' => $field['label'],
				'name' => $field['name'],
				'type' => $field['type'],
				'instructions' => isset( $field['instructions'] ) ? $field['instructions'] : '',
				'required' => isset( $field['required'] ) ? $field['required'] : false,
				'conditional_logic' => isset( $field['conditional_logic'] ) ? $field['conditional_logic'] : false,
				'wrapper' => isset( $field['wrapper'] ) ? $field['wrapper'] : array(),
				'default_value' => isset( $field['default_value'] ) ? $field['default_value'] : '',
			);

			// Add type-specific settings
			$field_data['type_settings'] = $this->get_field_type_settings( $field );

			// Handle sub-fields for repeater, group, flexible content, etc.
			if ( isset( $field['sub_fields'] ) && ! empty( $field['sub_fields'] ) ) {
				$field_data['sub_fields'] = $this->process_acf_fields( $field['sub_fields'] );
			}

			// Handle layouts for flexible content
			if ( isset( $field['layouts'] ) && ! empty( $field['layouts'] ) ) {
				$field_data['layouts'] = $this->process_acf_layouts( $field['layouts'] );
			}

			// Filter out sensitive data
			$field_data = $this->filter_sensitive_field_data( $field_data );

			$processed_fields[] = $field_data;
		}

		return $processed_fields;
	}

	/**
	 * Get type-specific settings for an ACF field.
	 *
	 * @param array $field ACF field array.
	 * @return array Type-specific settings.
	 */
	private function get_field_type_settings( $field ) {
		$settings = array();
		$type = $field['type'];

		// Common settings for many field types
		$common_keys = array(
			'placeholder',
			'prepend',
			'append',
			'maxlength',
			'readonly',
			'disabled',
		);

		foreach ( $common_keys as $key ) {
			if ( isset( $field[ $key ] ) ) {
				$settings[ $key ] = $field[ $key ];
			}
		}

		// Type-specific settings
		switch ( $type ) {
			case 'text':
			case 'textarea':
			case 'email':
			case 'url':
			case 'password':
				if ( isset( $field['maxlength'] ) ) {
					$settings['maxlength'] = $field['maxlength'];
				}
				if ( isset( $field['rows'] ) ) {
					$settings['rows'] = $field['rows'];
				}
				if ( isset( $field['new_lines'] ) ) {
					$settings['new_lines'] = $field['new_lines'];
				}
				break;

			case 'number':
			case 'range':
				if ( isset( $field['min'] ) ) {
					$settings['min'] = $field['min'];
				}
				if ( isset( $field['max'] ) ) {
					$settings['max'] = $field['max'];
				}
				if ( isset( $field['step'] ) ) {
					$settings['step'] = $field['step'];
				}
				break;

			case 'select':
			case 'checkbox':
			case 'radio':
			case 'button_group':
				if ( isset( $field['choices'] ) ) {
					$settings['choices'] = $field['choices'];
				}
				if ( isset( $field['allow_null'] ) ) {
					$settings['allow_null'] = $field['allow_null'];
				}
				if ( isset( $field['multiple'] ) ) {
					$settings['multiple'] = $field['multiple'];
				}
				if ( isset( $field['ui'] ) ) {
					$settings['ui'] = $field['ui'];
				}
				if ( isset( $field['ajax'] ) ) {
					$settings['ajax'] = $field['ajax'];
				}
				if ( isset( $field['layout'] ) ) {
					$settings['layout'] = $field['layout'];
				}
				if ( isset( $field['toggle'] ) ) {
					$settings['toggle'] = $field['toggle'];
				}
				if ( isset( $field['allow_custom'] ) ) {
					$settings['allow_custom'] = $field['allow_custom'];
				}
				break;

			case 'true_false':
				if ( isset( $field['message'] ) ) {
					$settings['message'] = $field['message'];
				}
				if ( isset( $field['ui'] ) ) {
					$settings['ui'] = $field['ui'];
				}
				if ( isset( $field['ui_on_text'] ) ) {
					$settings['ui_on_text'] = $field['ui_on_text'];
				}
				if ( isset( $field['ui_off_text'] ) ) {
					$settings['ui_off_text'] = $field['ui_off_text'];
				}
				break;

			case 'image':
			case 'file':
				if ( isset( $field['return_format'] ) ) {
					$settings['return_format'] = $field['return_format'];
				}
				if ( isset( $field['library'] ) ) {
					$settings['library'] = $field['library'];
				}
				if ( isset( $field['min_size'] ) ) {
					$settings['min_size'] = $field['min_size'];
				}
				if ( isset( $field['max_size'] ) ) {
					$settings['max_size'] = $field['max_size'];
				}
				if ( isset( $field['mime_types'] ) ) {
					$settings['mime_types'] = $field['mime_types'];
				}
				if ( isset( $field['preview_size'] ) ) {
					$settings['preview_size'] = $field['preview_size'];
				}
				if ( isset( $field['min_width'] ) ) {
					$settings['min_width'] = $field['min_width'];
				}
				if ( isset( $field['min_height'] ) ) {
					$settings['min_height'] = $field['min_height'];
				}
				if ( isset( $field['max_width'] ) ) {
					$settings['max_width'] = $field['max_width'];
				}
				if ( isset( $field['max_height'] ) ) {
					$settings['max_height'] = $field['max_height'];
				}
				break;

			case 'gallery':
				if ( isset( $field['min'] ) ) {
					$settings['min'] = $field['min'];
				}
				if ( isset( $field['max'] ) ) {
					$settings['max'] = $field['max'];
				}
				if ( isset( $field['insert'] ) ) {
					$settings['insert'] = $field['insert'];
				}
				if ( isset( $field['library'] ) ) {
					$settings['library'] = $field['library'];
				}
				if ( isset( $field['preview_size'] ) ) {
					$settings['preview_size'] = $field['preview_size'];
				}
				break;

			case 'wysiwyg':
				if ( isset( $field['tabs'] ) ) {
					$settings['tabs'] = $field['tabs'];
				}
				if ( isset( $field['toolbar'] ) ) {
					$settings['toolbar'] = $field['toolbar'];
				}
				if ( isset( $field['media_upload'] ) ) {
					$settings['media_upload'] = $field['media_upload'];
				}
				if ( isset( $field['delay'] ) ) {
					$settings['delay'] = $field['delay'];
				}
				break;

			case 'oembed':
				if ( isset( $field['width'] ) ) {
					$settings['width'] = $field['width'];
				}
				if ( isset( $field['height'] ) ) {
					$settings['height'] = $field['height'];
				}
				break;

			case 'google_map':
				if ( isset( $field['center_lat'] ) ) {
					$settings['center_lat'] = $field['center_lat'];
				}
				if ( isset( $field['center_lng'] ) ) {
					$settings['center_lng'] = $field['center_lng'];
				}
				if ( isset( $field['zoom'] ) ) {
					$settings['zoom'] = $field['zoom'];
				}
				if ( isset( $field['height'] ) ) {
					$settings['height'] = $field['height'];
				}
				break;

			case 'date_picker':
			case 'date_time_picker':
			case 'time_picker':
				if ( isset( $field['display_format'] ) ) {
					$settings['display_format'] = $field['display_format'];
				}
				if ( isset( $field['return_format'] ) ) {
					$settings['return_format'] = $field['return_format'];
				}
				if ( isset( $field['first_day'] ) ) {
					$settings['first_day'] = $field['first_day'];
				}
				break;

			case 'color_picker':
				if ( isset( $field['enable_opacity'] ) ) {
					$settings['enable_opacity'] = $field['enable_opacity'];
				}
				if ( isset( $field['return_format'] ) ) {
					$settings['return_format'] = $field['return_format'];
				}
				break;

			case 'relationship':
			case 'post_object':
				if ( isset( $field['post_type'] ) ) {
					$settings['post_type'] = $field['post_type'];
				}
				if ( isset( $field['taxonomy'] ) ) {
					$settings['taxonomy'] = $field['taxonomy'];
				}
				if ( isset( $field['filters'] ) ) {
					$settings['filters'] = $field['filters'];
				}
				if ( isset( $field['return_format'] ) ) {
					$settings['return_format'] = $field['return_format'];
				}
				if ( isset( $field['min'] ) ) {
					$settings['min'] = $field['min'];
				}
				if ( isset( $field['max'] ) ) {
					$settings['max'] = $field['max'];
				}
				if ( isset( $field['multiple'] ) ) {
					$settings['multiple'] = $field['multiple'];
				}
				break;

			case 'taxonomy':
				if ( isset( $field['taxonomy'] ) ) {
					$settings['taxonomy'] = $field['taxonomy'];
				}
				if ( isset( $field['field_type'] ) ) {
					$settings['field_type'] = $field['field_type'];
				}
				if ( isset( $field['allow_null'] ) ) {
					$settings['allow_null'] = $field['allow_null'];
				}
				if ( isset( $field['add_term'] ) ) {
					$settings['add_term'] = $field['add_term'];
				}
				if ( isset( $field['save_terms'] ) ) {
					$settings['save_terms'] = $field['save_terms'];
				}
				if ( isset( $field['load_terms'] ) ) {
					$settings['load_terms'] = $field['load_terms'];
				}
				if ( isset( $field['return_format'] ) ) {
					$settings['return_format'] = $field['return_format'];
				}
				if ( isset( $field['multiple'] ) ) {
					$settings['multiple'] = $field['multiple'];
				}
				break;

			case 'user':
				if ( isset( $field['role'] ) ) {
					$settings['role'] = $field['role'];
				}
				if ( isset( $field['allow_null'] ) ) {
					$settings['allow_null'] = $field['allow_null'];
				}
				if ( isset( $field['multiple'] ) ) {
					$settings['multiple'] = $field['multiple'];
				}
				if ( isset( $field['return_format'] ) ) {
					$settings['return_format'] = $field['return_format'];
				}
				break;

			case 'repeater':
				if ( isset( $field['min'] ) ) {
					$settings['min'] = $field['min'];
				}
				if ( isset( $field['max'] ) ) {
					$settings['max'] = $field['max'];
				}
				if ( isset( $field['layout'] ) ) {
					$settings['layout'] = $field['layout'];
				}
				if ( isset( $field['button_label'] ) ) {
					$settings['button_label'] = $field['button_label'];
				}
				if ( isset( $field['collapsed'] ) ) {
					$settings['collapsed'] = $field['collapsed'];
				}
				break;

			case 'group':
				if ( isset( $field['layout'] ) ) {
					$settings['layout'] = $field['layout'];
				}
				break;

			case 'flexible_content':
				if ( isset( $field['min'] ) ) {
					$settings['min'] = $field['min'];
				}
				if ( isset( $field['max'] ) ) {
					$settings['max'] = $field['max'];
				}
				if ( isset( $field['button_label'] ) ) {
					$settings['button_label'] = $field['button_label'];
				}
				break;

			case 'clone':
				if ( isset( $field['clone'] ) ) {
					$settings['clone'] = $field['clone'];
				}
				if ( isset( $field['display'] ) ) {
					$settings['display'] = $field['display'];
				}
				if ( isset( $field['layout'] ) ) {
					$settings['layout'] = $field['layout'];
				}
				if ( isset( $field['prefix_label'] ) ) {
					$settings['prefix_label'] = $field['prefix_label'];
				}
				if ( isset( $field['prefix_name'] ) ) {
					$settings['prefix_name'] = $field['prefix_name'];
				}
				break;

			case 'link':
				if ( isset( $field['return_format'] ) ) {
					$settings['return_format'] = $field['return_format'];
				}
				break;
		}

		return $settings;
	}

	/**
	 * Process ACF flexible content layouts.
	 *
	 * @param array $layouts ACF layouts array.
	 * @return array Processed layouts data.
	 */
	private function process_acf_layouts( $layouts ) {
		$processed_layouts = array();

		foreach ( $layouts as $layout ) {
			$layout_data = array(
				'key' => $layout['key'],
				'name' => $layout['name'],
				'label' => $layout['label'],
				'display' => isset( $layout['display'] ) ? $layout['display'] : 'block',
				'min' => isset( $layout['min'] ) ? $layout['min'] : '',
				'max' => isset( $layout['max'] ) ? $layout['max'] : '',
			);

			// Process sub-fields for this layout
			if ( isset( $layout['sub_fields'] ) && ! empty( $layout['sub_fields'] ) ) {
				$layout_data['sub_fields'] = $this->process_acf_fields( $layout['sub_fields'] );
			}

			$processed_layouts[] = $layout_data;
		}

		return $processed_layouts;
	}

	/**
	 * Filter sensitive data from field configuration.
	 *
	 * @param array $field_data Field data array.
	 * @return array Filtered field data.
	 */
	private function filter_sensitive_field_data( $field_data ) {
		// Check if field name or label contains sensitive keywords
		$sensitive_keywords = array( 'password', 'api_key', 'secret', 'token', 'private_key', 'apikey' );
		
		$field_name_lower = strtolower( $field_data['name'] );
		$field_label_lower = strtolower( $field_data['label'] );

		foreach ( $sensitive_keywords as $keyword ) {
			if ( strpos( $field_name_lower, $keyword ) !== false || strpos( $field_label_lower, $keyword ) !== false ) {
				// Mark as sensitive but keep the configuration
				$field_data['_sensitive'] = true;
				// Remove default value for sensitive fields
				$field_data['default_value'] = '[REDACTED]';
				break;
			}
		}

		return $field_data;
	}

	/**
	 * Export configurations from other custom field plugins.
	 *
	 * @return array Custom fields configurations.
	 */
	private function export_other_custom_fields() {
		$custom_fields = array();

		// Export Pods configuration
		if ( ! empty( $this->detected_plugins['pods'] ) ) {
			$custom_fields['pods'] = $this->export_pods_config();
		}

		// Export Metabox configuration
		if ( ! empty( $this->detected_plugins['metabox'] ) ) {
			$custom_fields['metabox'] = $this->export_metabox_config();
		}

		// Export Carbon Fields configuration
		if ( ! empty( $this->detected_plugins['carbon_fields'] ) ) {
			$custom_fields['carbon_fields'] = $this->export_carbon_fields_config();
		}

		return $custom_fields;
	}

	/**
	 * Export Pods configuration.
	 *
	 * @return array Pods configuration data.
	 */
	private function export_pods_config() {
		$pods_config = array();

		// Check if Pods API is available
		if ( ! function_exists( 'pods_api' ) ) {
			return $pods_config;
		}

		try {
			$api = pods_api();
			$pods = $api->load_pods();

			if ( ! empty( $pods ) ) {
				foreach ( $pods as $pod ) {
					$pod_data = array(
						'name' => $pod['name'],
						'label' => isset( $pod['label'] ) ? $pod['label'] : '',
						'type' => isset( $pod['type'] ) ? $pod['type'] : '',
						'storage' => isset( $pod['storage'] ) ? $pod['storage'] : '',
						'fields' => array(),
					);

					// Get fields for this pod
					$fields = $api->load_fields( array( 'pod' => $pod['name'] ) );
					
					if ( ! empty( $fields ) ) {
						foreach ( $fields as $field ) {
							$pod_data['fields'][] = array(
								'name' => $field['name'],
								'label' => isset( $field['label'] ) ? $field['label'] : '',
								'type' => isset( $field['type'] ) ? $field['type'] : '',
								'required' => isset( $field['required'] ) ? $field['required'] : false,
								'options' => isset( $field['options'] ) ? $field['options'] : array(),
							);
						}
					}

					$pods_config[] = $pod_data;
				}
			}
		} catch ( Exception $e ) {
			error_log( 'Digital Lobster Exporter: Error exporting Pods config: ' . $e->getMessage() );
		}

		return $pods_config;
	}

	/**
	 * Export Metabox configuration.
	 *
	 * @return array Metabox configuration data.
	 */
	private function export_metabox_config() {
		$metabox_config = array();

		// Metabox stores configuration in a global variable
		global $meta_boxes;

		if ( ! empty( $meta_boxes ) ) {
			foreach ( $meta_boxes as $post_type => $boxes ) {
				foreach ( $boxes as $context => $priority_boxes ) {
					foreach ( $priority_boxes as $priority => $box_list ) {
						foreach ( $box_list as $box ) {
							$box_data = array(
								'id' => isset( $box['id'] ) ? $box['id'] : '',
								'title' => isset( $box['title'] ) ? $box['title'] : '',
								'post_types' => isset( $box['post_types'] ) ? $box['post_types'] : array(),
								'context' => $context,
								'priority' => $priority,
								'fields' => array(),
							);

							if ( isset( $box['fields'] ) && ! empty( $box['fields'] ) ) {
								foreach ( $box['fields'] as $field ) {
									$box_data['fields'][] = array(
										'id' => isset( $field['id'] ) ? $field['id'] : '',
										'name' => isset( $field['name'] ) ? $field['name'] : '',
										'type' => isset( $field['type'] ) ? $field['type'] : '',
										'desc' => isset( $field['desc'] ) ? $field['desc'] : '',
										'required' => isset( $field['required'] ) ? $field['required'] : false,
										'options' => isset( $field['options'] ) ? $field['options'] : array(),
									);
								}
							}

							$metabox_config[] = $box_data;
						}
					}
				}
			}
		}

		return $metabox_config;
	}

	/**
	 * Export Carbon Fields configuration.
	 *
	 * @return array Carbon Fields configuration data.
	 */
	private function export_carbon_fields_config() {
		$carbon_config = array();

		// Carbon Fields doesn't provide a direct API to export configurations
		// We can only document that it's active and note the limitation
		$carbon_config['note'] = 'Carbon Fields is active. Configuration export requires custom implementation based on theme/plugin code.';
		$carbon_config['detected'] = true;

		return $carbon_config;
	}

	/**
	 * Save scan results to JSON files.
	 *
	 * @param array $results Scan results.
	 */
	private function save_to_files( $results ) {
		if ( empty( $this->export_dir ) ) {
			return;
		}

		// Ensure export directory exists
		if ( ! file_exists( $this->export_dir ) ) {
			wp_mkdir_p( $this->export_dir );
		}

		// Save ACF field groups
		if ( ! empty( $results['acf_field_groups'] ) ) {
			$acf_file = trailingslashit( $this->export_dir ) . 'acf_field_groups.json';
			$acf_data = array(
				'schema_version' => 1,
				'exported_at' => current_time( 'mysql' ),
				'field_groups' => $results['acf_field_groups'],
			);
			file_put_contents( $acf_file, wp_json_encode( $acf_data, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE ) );
		}

		// Save other custom fields config
		if ( ! empty( $results['custom_fields_config'] ) ) {
			$custom_fields_file = trailingslashit( $this->export_dir ) . 'custom_fields_config.json';
			$custom_fields_data = array(
				'schema_version' => 1,
				'exported_at' => current_time( 'mysql' ),
				'detected_plugins' => $results['detected_plugins'],
				'configurations' => $results['custom_fields_config'],
			);
			file_put_contents( $custom_fields_file, wp_json_encode( $custom_fields_data, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE ) );
		}
	}
}
