<?php
/**
 * Database Scanner Class
 *
 * Exports database schema information and custom table data for migration.
 * Executes SHOW CREATE TABLE for all tables, identifies custom tables created
 * by plugins, and exports sample data from custom tables related to content.
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Database Scanner Class
 */
class Digital_Lobster_Exporter_Database_Scanner {

	/**
	 * WordPress database object.
	 *
	 * @var wpdb
	 */
	private $wpdb;

	/**
	 * WordPress table prefix.
	 *
	 * @var string
	 */
	private $table_prefix;

	/**
	 * List of core WordPress tables.
	 *
	 * @var array
	 */
	private $core_tables = array();

	/**
	 * List of custom tables.
	 *
	 * @var array
	 */
	private $custom_tables = array();

	/**
	 * Custom tables manifest data.
	 *
	 * @var array
	 */
	private $custom_tables_manifest = array();

	/**
	 * Sensitive table patterns to exclude from data export.
	 *
	 * @var array
	 */
	private $sensitive_patterns = array(
		'users',
		'usermeta',
		'user_',
		'sessions',
		'login',
		'password',
		'token',
		'auth',
	);

	/**
	 * Constructor.
	 */
	public function __construct() {
		global $wpdb;
		$this->wpdb = $wpdb;
		$this->table_prefix = $wpdb->prefix;
		$this->initialize_core_tables();
	}

	/**
	 * Initialize list of core WordPress tables.
	 */
	private function initialize_core_tables() {
		$this->core_tables = array(
			$this->table_prefix . 'commentmeta',
			$this->table_prefix . 'comments',
			$this->table_prefix . 'links',
			$this->table_prefix . 'options',
			$this->table_prefix . 'postmeta',
			$this->table_prefix . 'posts',
			$this->table_prefix . 'term_relationships',
			$this->table_prefix . 'term_taxonomy',
			$this->table_prefix . 'termmeta',
			$this->table_prefix . 'terms',
			$this->table_prefix . 'usermeta',
			$this->table_prefix . 'users',
		);
	}

	/**
	 * Scan and collect database information.
	 *
	 * @return array Database information data.
	 */
	public function scan() {
		$this->identify_custom_tables();

		return array(
			'database_info' => $this->collect_database_info(),
			'custom_tables' => $this->custom_tables,
			'custom_tables_manifest' => $this->custom_tables_manifest,
		);
	}

	/**
	 * Export database schema and custom table data to files.
	 *
	 * @param string $export_dir Export directory path.
	 */
	public function export( $export_dir ) {
		// Export schema SQL
		$this->export_schema( $export_dir );

		// Export custom tables manifest
		$this->export_custom_tables_manifest( $export_dir );

		// Export sample data from custom tables
		$this->export_custom_tables_data( $export_dir );
	}

	/**
	 * Collect basic database information.
	 *
	 * @return array Database information.
	 */
	private function collect_database_info() {
		$db_version = $this->wpdb->get_var( 'SELECT VERSION()' );
		$charset = $this->wpdb->charset;
		$collate = $this->wpdb->collate;

		return array(
			'version' => $db_version,
			'charset' => $charset,
			'collate' => $collate,
			'prefix'  => $this->table_prefix,
		);
	}

	/**
	 * Identify custom tables created by plugins.
	 */
	private function identify_custom_tables() {
		// Get all tables in the database
		$all_tables = $this->wpdb->get_col( 'SHOW TABLES' );

		foreach ( $all_tables as $table ) {
			// Skip core WordPress tables
			if ( in_array( $table, $this->core_tables, true ) ) {
				continue;
			}

			// Skip tables that don't have the WordPress prefix
			if ( strpos( $table, $this->table_prefix ) !== 0 ) {
				continue;
			}

			// This is a custom table
			$this->custom_tables[] = $table;

			// Analyze table structure
			$table_info = $this->analyze_table_structure( $table );
			$this->custom_tables_manifest[ $table ] = $table_info;
		}
	}

	/**
	 * Analyze table structure and relationships.
	 *
	 * @param string $table Table name.
	 * @return array Table information.
	 */
	private function analyze_table_structure( $table ) {
		// Get table columns
		$columns = $this->wpdb->get_results( "DESCRIBE `{$table}`", ARRAY_A );

		// Get table row count
		$row_count = $this->wpdb->get_var( "SELECT COUNT(*) FROM `{$table}`" );

		// Get table indexes
		$indexes = $this->wpdb->get_results( "SHOW INDEX FROM `{$table}`", ARRAY_A );

		// Identify potential plugin source
		$plugin_source = $this->identify_plugin_source( $table );

		// Check if table is related to content
		$is_content_related = $this->is_content_related_table( $table, $columns );

		return array(
			'name'               => $table,
			'row_count'          => (int) $row_count,
			'columns'            => $this->format_columns( $columns ),
			'indexes'            => $this->format_indexes( $indexes ),
			'plugin_source'      => $plugin_source,
			'is_content_related' => $is_content_related,
			'is_sensitive'       => $this->is_sensitive_table( $table ),
		);
	}

	/**
	 * Format column information.
	 *
	 * @param array $columns Raw column data.
	 * @return array Formatted column data.
	 */
	private function format_columns( $columns ) {
		$formatted = array();

		foreach ( $columns as $column ) {
			$formatted[] = array(
				'name'    => $column['Field'],
				'type'    => $column['Type'],
				'null'    => $column['Null'] === 'YES',
				'key'     => $column['Key'],
				'default' => $column['Default'],
				'extra'   => $column['Extra'],
			);
		}

		return $formatted;
	}

	/**
	 * Format index information.
	 *
	 * @param array $indexes Raw index data.
	 * @return array Formatted index data.
	 */
	private function format_indexes( $indexes ) {
		$formatted = array();
		$processed = array();

		foreach ( $indexes as $index ) {
			$key_name = $index['Key_name'];

			if ( ! isset( $processed[ $key_name ] ) ) {
				$formatted[] = array(
					'name'       => $key_name,
					'unique'     => $index['Non_unique'] == 0,
					'type'       => $index['Index_type'],
					'columns'    => array( $index['Column_name'] ),
				);
				$processed[ $key_name ] = count( $formatted ) - 1;
			} else {
				$formatted[ $processed[ $key_name ] ]['columns'][] = $index['Column_name'];
			}
		}

		return $formatted;
	}

	/**
	 * Identify which plugin likely created this table.
	 *
	 * @param string $table Table name.
	 * @return string|null Plugin identifier or null if unknown.
	 */
	private function identify_plugin_source( $table ) {
		// Remove prefix for pattern matching
		$table_suffix = str_replace( $this->table_prefix, '', $table );

		// Known plugin table patterns
		$plugin_patterns = array(
			'geodir_'           => 'GeoDirectory',
			'gd_'               => 'GeoDirectory',
			'wc_'               => 'WooCommerce',
			'woocommerce_'      => 'WooCommerce',
			'yoast_'            => 'Yoast SEO',
			'rank_math_'        => 'Rank Math',
			'icl_'              => 'WPML',
			'wpml_'             => 'WPML',
			'acf_'              => 'Advanced Custom Fields',
			'cf7_'              => 'Contact Form 7',
			'gf_'               => 'Gravity Forms',
			'frm_'              => 'Formidable Forms',
			'wpforms_'          => 'WPForms',
			'ninja_forms_'      => 'Ninja Forms',
			'edd_'              => 'Easy Digital Downloads',
			'memberpress_'      => 'MemberPress',
			'pmpro_'            => 'Paid Memberships Pro',
			'redirection_'      => 'Redirection',
			'wpmm_'             => 'WP Maintenance Mode',
			'actionscheduler_'  => 'Action Scheduler',
		);

		foreach ( $plugin_patterns as $pattern => $plugin_name ) {
			if ( strpos( $table_suffix, $pattern ) === 0 ) {
				return $plugin_name;
			}
		}

		return 'Unknown';
	}

	/**
	 * Check if table is related to content.
	 *
	 * @param string $table Table name.
	 * @param array  $columns Table columns.
	 * @return bool True if content-related.
	 */
	private function is_content_related_table( $table, $columns ) {
		// Check for common content-related column names
		$content_indicators = array( 'post_id', 'post_title', 'post_content', 'content', 'description' );

		foreach ( $columns as $column ) {
			if ( in_array( strtolower( $column['Field'] ), $content_indicators, true ) ) {
				return true;
			}
		}

		// Check for GeoDirectory detail tables
		if ( strpos( $table, 'geodir_' ) !== false && strpos( $table, '_detail' ) !== false ) {
			return true;
		}

		return false;
	}

	/**
	 * Check if table contains sensitive data.
	 *
	 * @param string $table Table name.
	 * @return bool True if sensitive.
	 */
	private function is_sensitive_table( $table ) {
		$table_lower = strtolower( $table );

		foreach ( $this->sensitive_patterns as $pattern ) {
			if ( strpos( $table_lower, $pattern ) !== false ) {
				return true;
			}
		}

		return false;
	}

	/**
	 * Export database schema to SQL file.
	 *
	 * @param string $export_dir Export directory path.
	 */
	private function export_schema( $export_dir ) {
		$schema_file = trailingslashit( $export_dir ) . 'schema_mysql.sql';
		$schema_content = "-- WordPress Database Schema Export\n";
		$schema_content .= "-- Generated: " . current_time( 'mysql' ) . "\n";
		$schema_content .= "-- Database: " . DB_NAME . "\n";
		$schema_content .= "-- Table Prefix: " . $this->table_prefix . "\n\n";

		// Get all tables
		$all_tables = $this->wpdb->get_col( 'SHOW TABLES' );

		foreach ( $all_tables as $table ) {
			// Skip tables without WordPress prefix
			if ( strpos( $table, $this->table_prefix ) !== 0 ) {
				continue;
			}

			// Get CREATE TABLE statement
			$create_table = $this->wpdb->get_row( "SHOW CREATE TABLE `{$table}`", ARRAY_N );

			if ( $create_table ) {
				$schema_content .= "-- Table: {$table}\n";
				$schema_content .= "DROP TABLE IF EXISTS `{$table}`;\n";
				$schema_content .= $create_table[1] . ";\n\n";
			}
		}

		// Write to file
		file_put_contents( $schema_file, $schema_content );
	}

	/**
	 * Export custom tables manifest to JSON file.
	 *
	 * @param string $export_dir Export directory path.
	 */
	private function export_custom_tables_manifest( $export_dir ) {
		$manifest_file = trailingslashit( $export_dir ) . 'custom_tables_manifest.json';

		$manifest = array(
			'schema_version' => 1,
			'generated_at'   => current_time( 'mysql' ),
			'total_custom_tables' => count( $this->custom_tables ),
			'tables'         => $this->custom_tables_manifest,
		);

		file_put_contents(
			$manifest_file,
			wp_json_encode( $manifest, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES )
		);
	}

	/**
	 * Export sample data from custom tables.
	 *
	 * @param string $export_dir Export directory path.
	 */
	private function export_custom_tables_data( $export_dir ) {
		$data_file = trailingslashit( $export_dir ) . 'custom_tables_data.json';
		$custom_data = array(
			'schema_version' => 1,
			'generated_at'   => current_time( 'mysql' ),
			'tables'         => array(),
		);

		foreach ( $this->custom_tables as $table ) {
			$table_info = $this->custom_tables_manifest[ $table ];

			// Skip sensitive tables
			if ( $table_info['is_sensitive'] ) {
				continue;
			}

			// Only export sample data from content-related tables
			if ( ! $table_info['is_content_related'] ) {
				continue;
			}

			// Export sample rows (limit to 10 per table)
			$sample_data = $this->export_sample_table_data( $table, 10 );

			if ( ! empty( $sample_data ) ) {
				$custom_data['tables'][ $table ] = array(
					'plugin_source' => $table_info['plugin_source'],
					'row_count'     => $table_info['row_count'],
					'sample_rows'   => $sample_data,
				);
			}
		}

		file_put_contents(
			$data_file,
			wp_json_encode( $custom_data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES )
		);
	}

	/**
	 * Export sample data from a table.
	 *
	 * @param string $table Table name.
	 * @param int    $limit Number of rows to export.
	 * @return array Sample data rows.
	 */
	private function export_sample_table_data( $table, $limit = 10 ) {
		$results = $this->wpdb->get_results(
			$this->wpdb->prepare(
				"SELECT * FROM `{$table}` LIMIT %d",
				$limit
			),
			ARRAY_A
		);

		if ( ! $results ) {
			return array();
		}

		// Sanitize data - remove any potential PII
		return $this->sanitize_table_data( $results );
	}

	/**
	 * Sanitize table data to remove PII.
	 *
	 * @param array $data Table data rows.
	 * @return array Sanitized data.
	 */
	private function sanitize_table_data( $data ) {
		$sensitive_fields = array(
			'email',
			'user_email',
			'user_login',
			'user_pass',
			'password',
			'api_key',
			'token',
			'secret',
			'phone',
			'telephone',
			'mobile',
			'ip_address',
			'ip',
		);

		foreach ( $data as &$row ) {
			foreach ( $row as $key => $value ) {
				$key_lower = strtolower( $key );

				// Check if field name contains sensitive keywords
				foreach ( $sensitive_fields as $sensitive_field ) {
					if ( strpos( $key_lower, $sensitive_field ) !== false ) {
						$row[ $key ] = '[REDACTED]';
						break;
					}
				}
			}
		}

		return $data;
	}
}
