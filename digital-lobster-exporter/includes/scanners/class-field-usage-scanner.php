<?php
/**
 * Field Usage Scanner Class
 *
 * Produces a normalized field_usage_report.json artifact containing
 * per-content-type field analysis: field name, source plugin/system,
 * inferred type, nullability, cardinality, distinct value count,
 * sample values, and behavioral classification (behaves_as).
 *
 * Detects fields from ACF, Pods, Meta Box, Carbon Fields, and core postmeta.
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Field Usage Scanner Class
 */
class Digital_Lobster_Exporter_Field_Usage_Scanner extends Digital_Lobster_Exporter_Scanner_Base {

	/**
	 * Maximum sample values to collect per field.
	 *
	 * @var int
	 */
	const MAX_SAMPLE_VALUES = 5;

	/**
	 * Collected field entries.
	 *
	 * @var array
	 */
	private $fields = array();

	/**
	 * Known ACF field definitions keyed by field name.
	 *
	 * @var array
	 */
	private $acf_field_defs = array();

	/**
	 * Known Pods field definitions keyed by pod_name.field_name.
	 *
	 * @var array
	 */
	private $pods_field_defs = array();

	/**
	 * Scan field usage across all public post types.
	 *
	 * @return array Field usage data matching FieldUsageReportArtifact schema.
	 */
	public function scan() {
		$this->fields = array();

		$this->load_acf_field_definitions();
		$this->load_pods_field_definitions();

		$post_types = get_post_types( array( 'public' => true ), 'names' );

		foreach ( $post_types as $post_type ) {
			$this->scan_post_type_fields( $post_type );
		}

		return array(
			'schema_version' => '1.0.0',
			'fields'         => array_values( $this->fields ),
		);
	}

	/**
	 * Load ACF field definitions for type inference.
	 */
	private function load_acf_field_definitions() {
		if ( ! function_exists( 'acf_get_field_groups' ) ) {
			return;
		}

		$groups = acf_get_field_groups();
		if ( empty( $groups ) ) {
			return;
		}

		foreach ( $groups as $group ) {
			$fields = acf_get_fields( $group['key'] );
			if ( empty( $fields ) ) {
				continue;
			}
			foreach ( $fields as $field ) {
				$this->acf_field_defs[ $field['name'] ] = $field;
			}
		}
	}

	/**
	 * Load Pods field definitions for type inference.
	 */
	private function load_pods_field_definitions() {
		if ( ! function_exists( 'pods_api' ) ) {
			return;
		}

		try {
			$api  = pods_api();
			$pods = $api->load_pods( array( 'names' => true ) );
		} catch ( \Exception $e ) {
			$this->log_warning( 'field_usage', 'Failed to load Pods API: ' . $e->getMessage() );
			return;
		}

		if ( empty( $pods ) || ! is_array( $pods ) ) {
			return;
		}

		foreach ( $pods as $pod_name => $pod_label ) {
			try {
				$pod = pods_api()->load_pod( array( 'name' => $pod_name ) );
			} catch ( \Exception $e ) {
				continue;
			}
			if ( empty( $pod['fields'] ) ) {
				continue;
			}
			foreach ( $pod['fields'] as $field ) {
				$this->pods_field_defs[ $pod_name . '.' . $field['name'] ] = $field;
			}
		}
	}

	/**
	 * Scan all meta fields for a given post type.
	 *
	 * @param string $post_type Post type slug.
	 */
	private function scan_post_type_fields( $post_type ) {
		global $wpdb;

		// Get all distinct meta keys used by this post type.
		// phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery, WordPress.DB.DirectDatabaseQuery.NoCaching
		$meta_keys = $wpdb->get_col(
			$wpdb->prepare(
				"SELECT DISTINCT pm.meta_key
				FROM {$wpdb->postmeta} pm
				INNER JOIN {$wpdb->posts} p ON p.ID = pm.post_id
				WHERE p.post_type = %s
				AND pm.meta_key NOT LIKE %s
				LIMIT 500",
				$post_type,
				'\_%'
			)
		);

		if ( empty( $meta_keys ) ) {
			return;
		}

		foreach ( $meta_keys as $meta_key ) {
			$this->analyze_field( $post_type, $meta_key );
		}
	}

	/**
	 * Analyze a single field for a post type.
	 *
	 * @param string $post_type Post type slug.
	 * @param string $meta_key  Meta key name.
	 */
	private function analyze_field( $post_type, $meta_key ) {
		global $wpdb;

		// Get distinct values and count.
		// phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery, WordPress.DB.DirectDatabaseQuery.NoCaching
		$stats = $wpdb->get_row(
			$wpdb->prepare(
				"SELECT
					COUNT(DISTINCT pm.meta_value) AS distinct_count,
					COUNT(*) AS total_count,
					SUM(CASE WHEN pm.meta_value IS NULL OR pm.meta_value = '' THEN 1 ELSE 0 END) AS null_count
				FROM {$wpdb->postmeta} pm
				INNER JOIN {$wpdb->posts} p ON p.ID = pm.post_id
				WHERE p.post_type = %s AND pm.meta_key = %s",
				$post_type,
				$meta_key
			),
			ARRAY_A
		);

		if ( empty( $stats ) ) {
			return;
		}

		$distinct_count = (int) $stats['distinct_count'];
		$total_count    = (int) $stats['total_count'];
		$null_count     = (int) $stats['null_count'];
		$nullable       = $null_count > 0;

		// Get sample values.
		// phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery, WordPress.DB.DirectDatabaseQuery.NoCaching
		$samples = $wpdb->get_col(
			$wpdb->prepare(
				"SELECT DISTINCT pm.meta_value
				FROM {$wpdb->postmeta} pm
				INNER JOIN {$wpdb->posts} p ON p.ID = pm.post_id
				WHERE p.post_type = %s AND pm.meta_key = %s
				AND pm.meta_value IS NOT NULL AND pm.meta_value != ''
				LIMIT %d",
				$post_type,
				$meta_key,
				self::MAX_SAMPLE_VALUES
			)
		);

		$sample_values = array();
		foreach ( $samples as $sample ) {
			$sample_values[] = $this->security_filters->filter_value( $sample );
		}

		// Determine source system and plugin.
		$source_info = $this->detect_source( $post_type, $meta_key );

		// Determine cardinality.
		$cardinality = $this->detect_cardinality( $post_type, $meta_key, $source_info );

		// Infer type.
		$inferred_type = $this->infer_type( $meta_key, $samples, $source_info );

		// Determine behavioral classification.
		$behaves_as = $this->classify_behavior( $meta_key, $inferred_type, $distinct_count, $source_info );

		$key = $post_type . '::' . $meta_key;
		$this->fields[ $key ] = array(
			'post_type'            => $post_type,
			'field_name'           => $meta_key,
			'source_plugin'        => $source_info['plugin'],
			'source_system'        => $source_info['system'],
			'inferred_type'        => $inferred_type,
			'nullable'             => $nullable,
			'cardinality'          => $cardinality,
			'distinct_value_count' => $distinct_count,
			'sample_values'        => $sample_values,
			'behaves_as'           => $behaves_as,
		);
	}

	/**
	 * Detect the source system and plugin for a meta key.
	 *
	 * @param string $post_type Post type slug.
	 * @param string $meta_key  Meta key name.
	 * @return array { system: string, plugin: string|null }
	 */
	private function detect_source( $post_type, $meta_key ) {
		// ACF.
		if ( isset( $this->acf_field_defs[ $meta_key ] ) ) {
			return array(
				'system' => 'acf',
				'plugin' => 'acf',
			);
		}

		// Pods.
		$pods_key = $post_type . '.' . $meta_key;
		if ( isset( $this->pods_field_defs[ $pods_key ] ) ) {
			return array(
				'system' => 'pods',
				'plugin' => 'pods',
			);
		}

		// Meta Box — fields registered via rwmb_meta_boxes filter.
		if ( function_exists( 'rwmb_get_registry' ) ) {
			try {
				$registry = rwmb_get_registry( 'field' );
				$field    = $registry->get( $meta_key, $post_type );
				if ( $field ) {
					return array(
						'system' => 'meta_box',
						'plugin' => 'meta_box',
					);
				}
			} catch ( \Exception $e ) {
				// Ignore — fall through to next check.
			}
		}

		// Carbon Fields — fields stored with _carbon_ prefix pattern.
		if ( strpos( $meta_key, '_carbon_' ) === 0 || ( function_exists( '\\Carbon_Fields\\Carbon_Fields::resolve' ) ) ) {
			// Check if Carbon Fields is active and recognizes this field.
			if ( function_exists( 'carbon_get_post_meta' ) ) {
				return array(
					'system' => 'carbon_fields',
					'plugin' => 'carbon_fields',
				);
			}
		}

		// Core postmeta.
		return array(
			'system' => 'core',
			'plugin' => null,
		);
	}

	/**
	 * Detect field cardinality (single vs multiple).
	 *
	 * @param string $post_type   Post type slug.
	 * @param string $meta_key    Meta key name.
	 * @param array  $source_info Source system info.
	 * @return string "single" or "multiple"
	 */
	private function detect_cardinality( $post_type, $meta_key, $source_info ) {
		// ACF repeater/flexible_content are always multiple.
		if ( 'acf' === $source_info['system'] && isset( $this->acf_field_defs[ $meta_key ] ) ) {
			$acf_type = $this->acf_field_defs[ $meta_key ]['type'];
			if ( in_array( $acf_type, array( 'repeater', 'flexible_content', 'gallery', 'relationship' ), true ) ) {
				return 'multiple';
			}
		}

		// Pods pick fields can be multiple.
		$pods_key = $post_type . '.' . $meta_key;
		if ( 'pods' === $source_info['system'] && isset( $this->pods_field_defs[ $pods_key ] ) ) {
			$pods_field = $this->pods_field_defs[ $pods_key ];
			if ( isset( $pods_field['type'] ) && 'pick' === $pods_field['type'] ) {
				return 'multiple';
			}
		}

		// Check if multiple meta rows exist for the same post + key.
		global $wpdb;
		// phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery, WordPress.DB.DirectDatabaseQuery.NoCaching
		$multi_check = $wpdb->get_var(
			$wpdb->prepare(
				"SELECT COUNT(*) FROM (
					SELECT pm.post_id
					FROM {$wpdb->postmeta} pm
					INNER JOIN {$wpdb->posts} p ON p.ID = pm.post_id
					WHERE p.post_type = %s AND pm.meta_key = %s
					GROUP BY pm.post_id
					HAVING COUNT(*) > 1
					LIMIT 1
				) AS multi",
				$post_type,
				$meta_key
			)
		);

		return ( (int) $multi_check > 0 ) ? 'multiple' : 'single';
	}

	/**
	 * Infer the field type from sample values and source definitions.
	 *
	 * @param string $meta_key    Meta key name.
	 * @param array  $samples     Sample values.
	 * @param array  $source_info Source system info.
	 * @return string Inferred type.
	 */
	private function infer_type( $meta_key, $samples, $source_info ) {
		// Use ACF field type if available.
		if ( 'acf' === $source_info['system'] && isset( $this->acf_field_defs[ $meta_key ] ) ) {
			return $this->map_acf_type( $this->acf_field_defs[ $meta_key ]['type'] );
		}

		// Infer from sample values.
		if ( empty( $samples ) ) {
			return 'text';
		}

		$all_numeric  = true;
		$all_boolean  = true;
		$all_date     = true;
		$all_serialized = true;

		foreach ( $samples as $val ) {
			if ( ! is_numeric( $val ) ) {
				$all_numeric = false;
			}
			if ( ! in_array( strtolower( (string) $val ), array( '0', '1', 'true', 'false', 'yes', 'no' ), true ) ) {
				$all_boolean = false;
			}
			if ( ! preg_match( '/^\d{4}-\d{2}-\d{2}/', (string) $val ) ) {
				$all_date = false;
			}
			if ( ! is_serialized( (string) $val ) ) {
				$all_serialized = false;
			}
		}

		if ( $all_boolean ) {
			return 'boolean';
		}
		if ( $all_numeric ) {
			return 'number';
		}
		if ( $all_date ) {
			return 'date';
		}
		if ( $all_serialized ) {
			return 'object';
		}

		return 'text';
	}

	/**
	 * Map ACF field type to a normalized inferred type.
	 *
	 * @param string $acf_type ACF field type.
	 * @return string Normalized type.
	 */
	private function map_acf_type( $acf_type ) {
		$map = array(
			'text'             => 'text',
			'textarea'         => 'text',
			'number'           => 'number',
			'range'            => 'number',
			'email'            => 'text',
			'url'              => 'text',
			'password'         => 'text',
			'image'            => 'reference',
			'file'             => 'reference',
			'wysiwyg'          => 'text',
			'oembed'           => 'text',
			'gallery'          => 'reference',
			'select'           => 'enum',
			'checkbox'         => 'enum',
			'radio'            => 'enum',
			'button_group'     => 'enum',
			'true_false'       => 'boolean',
			'link'             => 'object',
			'post_object'      => 'reference',
			'page_link'        => 'reference',
			'relationship'     => 'reference',
			'taxonomy'         => 'reference',
			'user'             => 'reference',
			'google_map'       => 'object',
			'date_picker'      => 'date',
			'date_time_picker' => 'date',
			'time_picker'      => 'text',
			'color_picker'     => 'text',
			'group'            => 'object',
			'repeater'         => 'repeater',
			'flexible_content' => 'flexible',
			'clone'            => 'object',
			'tab'              => 'text',
			'message'          => 'text',
			'accordion'        => 'text',
		);

		return isset( $map[ $acf_type ] ) ? $map[ $acf_type ] : 'text';
	}

	/**
	 * Classify the behavioral role of a field.
	 *
	 * @param string      $meta_key       Meta key name.
	 * @param string      $inferred_type  Inferred type.
	 * @param int         $distinct_count Distinct value count.
	 * @param array       $source_info    Source system info.
	 * @return string|null Behavioral classification or null.
	 */
	private function classify_behavior( $meta_key, $inferred_type, $distinct_count, $source_info ) {
		if ( in_array( $inferred_type, array( 'repeater' ), true ) ) {
			return 'repeater';
		}
		if ( in_array( $inferred_type, array( 'flexible' ), true ) ) {
			return 'flexible';
		}
		if ( in_array( $inferred_type, array( 'reference' ), true ) ) {
			return 'reference';
		}
		if ( in_array( $inferred_type, array( 'object' ), true ) ) {
			return 'object';
		}
		if ( in_array( $inferred_type, array( 'enum' ), true ) ) {
			return 'enum';
		}

		// Heuristic: low distinct count relative to usage suggests enum behavior.
		if ( $distinct_count > 0 && $distinct_count <= 20 && 'text' === $inferred_type ) {
			return 'enum';
		}

		return null;
	}
}
