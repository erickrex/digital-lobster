<?php
/**
 * Plugin Table Exports Scanner Class
 *
 * Produces plugin_table_exports data containing structured exports of
 * custom database tables for Supported_Plugin_Family plugins only
 * (GeoDirectory, Forminator, etc.). Includes table name, schema version,
 * row count, primary key, foreign-key candidates, and row payloads
 * with stable IDs.
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Plugin Table Exports Scanner Class
 */
class Digital_Lobster_Exporter_Plugin_Table_Exports_Scanner extends Digital_Lobster_Exporter_Scanner_Base {

	/**
	 * Maximum rows to export per table.
	 *
	 * @var int
	 */
	const MAX_ROWS_PER_TABLE = 5000;

	/**
	 * Supported plugin families and their known custom table prefixes.
	 *
	 * @var array
	 */
	private $supported_table_map = array();

	/**
	 * Collected table exports.
	 *
	 * @var array
	 */
	private $exports = array();

	/**
	 * Constructor.
	 *
	 * @param array $deps Optional. Associative array of dependencies.
	 */
	public function __construct( array $deps = array() ) {
		parent::__construct( $deps );
		$this->init_supported_table_map();
	}

	/**
	 * Initialize the mapping of supported plugins to their custom table patterns.
	 */
	private function init_supported_table_map() {
		global $wpdb;
		$prefix = $wpdb->prefix;

		$this->supported_table_map = array(
			'geodirectory' => array(
				'detect'  => 'GeoDirectory',
				'tables'  => array(
					$prefix . 'geodir_gd_place_detail',
					$prefix . 'geodir_attachments',
					$prefix . 'geodir_post_review',
				),
			),
			'gravity_forms' => array(
				'detect'  => 'GFAPI',
				'tables'  => array(
					$prefix . 'gf_form',
					$prefix . 'gf_form_meta',
					$prefix . 'gf_entry',
					$prefix . 'gf_entry_meta',
				),
			),
			'ninja_forms' => array(
				'detect'  => 'Ninja_Forms',
				'tables'  => array(
					$prefix . 'nf3_forms',
					$prefix . 'nf3_fields',
					$prefix . 'nf3_actions',
					$prefix . 'nf3_form_meta',
				),
			),
			'forminator' => array(
				'detect'  => 'Forminator',
				'tables'  => array(
					$prefix . 'frmt_form_entry',
					$prefix . 'frmt_form_entry_meta',
				),
			),
		);
	}

	/**
	 * Scan custom database tables for supported plugins.
	 *
	 * @return array List of PluginTableExport entries.
	 */
	public function scan() {
		$this->exports = array();

		foreach ( $this->supported_table_map as $plugin_family => $config ) {
			if ( ! $this->is_plugin_active( $config['detect'] ) ) {
				continue;
			}

			foreach ( $config['tables'] as $table_name ) {
				$this->export_table( $table_name, $plugin_family );
			}
		}

		// Also scan tables from database context if available.
		$this->scan_context_tables();

		return $this->exports;
	}

	/**
	 * Check if a plugin is active by class or function existence.
	 *
	 * @param string $detect Class or function name to check.
	 * @return bool True if active.
	 */
	private function is_plugin_active( $detect ) {
		return class_exists( $detect ) || function_exists( $detect );
	}

	/**
	 * Export a single database table.
	 *
	 * @param string $table_name    Full table name.
	 * @param string $source_plugin Plugin family identifier.
	 */
	private function export_table( $table_name, $source_plugin ) {
		global $wpdb;

		// Check table exists.
		// phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery, WordPress.DB.DirectDatabaseQuery.NoCaching
		$table_exists = $wpdb->get_var(
			$wpdb->prepare( 'SHOW TABLES LIKE %s', $table_name )
		);

		if ( ! $table_exists ) {
			return;
		}

		// Get row count.
		$safe_table = esc_sql( $table_name );
		// phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery, WordPress.DB.DirectDatabaseQuery.NoCaching, WordPress.DB.PreparedSQL.InterpolatedNotPrepared
		$row_count = (int) $wpdb->get_var( "SELECT COUNT(*) FROM `{$safe_table}`" );

		// Get table schema for primary key and column info.
		$schema_info   = $this->get_table_schema( $table_name );
		$primary_key   = $schema_info['primary_key'];
		$fk_candidates = $schema_info['foreign_key_candidates'];

		// Get rows (limited).
		// phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery, WordPress.DB.DirectDatabaseQuery.NoCaching, WordPress.DB.PreparedSQL.InterpolatedNotPrepared
		$rows = $wpdb->get_results(
			$wpdb->prepare(
				"SELECT * FROM `{$safe_table}` LIMIT %d",
				self::MAX_ROWS_PER_TABLE
			),
			ARRAY_A
		);

		if ( ! is_array( $rows ) ) {
			$rows = array();
		}

		// Filter sensitive data from rows.
		$filtered_rows = array();
		foreach ( $rows as $row ) {
			$filtered = array();
			foreach ( $row as $col => $val ) {
				$filtered[ $col ] = $this->security_filters->filter_value( $val );
			}
			$filtered_rows[] = $filtered;
		}

		$this->exports[] = array(
			'table_name'             => $table_name,
			'schema_version'         => '1.0.0',
			'source_plugin'          => $source_plugin,
			'row_count'              => $row_count,
			'primary_key'            => $primary_key,
			'foreign_key_candidates' => $fk_candidates,
			'rows'                   => $filtered_rows,
		);
	}

	/**
	 * Get table schema information.
	 *
	 * @param string $table_name Full table name.
	 * @return array { primary_key: string, foreign_key_candidates: string[] }
	 */
	private function get_table_schema( $table_name ) {
		global $wpdb;

		$primary_key   = 'id';
		$fk_candidates = array();

		$safe_table = esc_sql( $table_name );
		// phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery, WordPress.DB.DirectDatabaseQuery.NoCaching, WordPress.DB.PreparedSQL.InterpolatedNotPrepared
		$columns = $wpdb->get_results( "SHOW COLUMNS FROM `{$safe_table}`", ARRAY_A );

		if ( empty( $columns ) ) {
			return array(
				'primary_key'            => $primary_key,
				'foreign_key_candidates' => $fk_candidates,
			);
		}

		$post_ref_patterns = array( 'post_id', 'object_id', 'item_id', 'entry_id', 'form_id', 'user_id' );

		foreach ( $columns as $col ) {
			// Detect primary key.
			if ( isset( $col['Key'] ) && 'PRI' === $col['Key'] ) {
				$primary_key = $col['Field'];
			}

			// Detect foreign key candidates.
			$col_lower = strtolower( $col['Field'] );
			foreach ( $post_ref_patterns as $pattern ) {
				if ( $col_lower === $pattern || substr( $col_lower, -strlen( '_' . $pattern ) ) === '_' . $pattern ) {
					$fk_candidates[] = $col['Field'];
					break;
				}
			}
		}

		return array(
			'primary_key'            => $primary_key,
			'foreign_key_candidates' => array_unique( $fk_candidates ),
		);
	}

	/**
	 * Scan tables from database context for supported plugins.
	 *
	 * Uses context['database']['custom_tables'] if available.
	 */
	private function scan_context_tables() {
		$database_context = isset( $this->context['database'] ) ? $this->context['database'] : array();
		if ( empty( $database_context ) ) {
			return;
		}

		$custom_tables = isset( $database_context['custom_tables'] ) ? $database_context['custom_tables'] : array();
		if ( empty( $custom_tables ) || ! is_array( $custom_tables ) ) {
			return;
		}

		// Build a set of already-exported table names.
		$exported = array();
		foreach ( $this->exports as $export ) {
			$exported[ $export['table_name'] ] = true;
		}

		foreach ( $custom_tables as $table_info ) {
			$table_name    = isset( $table_info['name'] ) ? $table_info['name'] : '';
			$source_plugin = isset( $table_info['source_plugin'] ) ? $table_info['source_plugin'] : null;

			if ( empty( $table_name ) || empty( $source_plugin ) ) {
				continue;
			}

			// Only export for supported plugin families.
			if ( ! isset( $this->supported_table_map[ $source_plugin ] ) ) {
				continue;
			}

			// Skip already exported.
			if ( isset( $exported[ $table_name ] ) ) {
				continue;
			}

			$this->export_table( $table_name, $source_plugin );
		}
	}
}
