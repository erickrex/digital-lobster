<?php
/**
 * Error Logger Trait
 *
 * Provides standardized error and warning tracking for classes that need
 * to collect and report errors during plugin operations.
 *
 * Used by Scanner_Orchestrator, Exporter, Packager, and Scanner_Base.
 *
 * @package Digital_Lobster_Exporter
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Trait Digital_Lobster_Exporter_Error_Logger
 *
 * Provides log_error(), log_warning(), get_errors(), get_warnings(),
 * and has_errors() methods with a consistent log entry format.
 *
 * Each log entry contains: component, message, severity, and timestamp.
 */
trait Digital_Lobster_Exporter_Error_Logger {

	/**
	 * Collected error log entries.
	 *
	 * @var array
	 */
	private $errors = array();

	/**
	 * Collected warning log entries.
	 *
	 * @var array
	 */
	private $warnings = array();

	/**
	 * Log an error or warning.
	 *
	 * Appends a log entry to the appropriate internal array based on severity.
	 * When WP_DEBUG is enabled, also writes to the PHP error log.
	 *
	 * @param string $component Component identifier (e.g., 'scanner', 'exporter', 'packager').
	 * @param string $message   Error or warning message.
	 * @param string $severity  Severity level: 'error', 'warning', 'critical'. Default 'error'.
	 */
	protected function log_error( $component, $message, $severity = 'error' ) {
		$log_entry = array(
			'component' => $component,
			'message'   => $message,
			'severity'  => $severity,
			'timestamp' => current_time( 'timestamp' ),
		);

		if ( $severity === 'warning' ) {
			$this->warnings[] = $log_entry;
		} else {
			$this->errors[] = $log_entry;
		}

		// Also log to WordPress error log if WP_DEBUG is enabled.
		if ( defined( 'WP_DEBUG' ) && WP_DEBUG ) {
			error_log( sprintf(
				'Digital Lobster Exporter [%s] %s: %s',
				strtoupper( $severity ),
				$component,
				$message
			) );
		}
	}

	/**
	 * Log a warning (shorthand for log_error with 'warning' severity).
	 *
	 * @param string $component Component identifier.
	 * @param string $message   Warning message.
	 */
	protected function log_warning( $component, $message ) {
		$this->log_error( $component, $message, 'warning' );
	}

	/**
	 * Get collected errors.
	 *
	 * @return array Error log entries.
	 */
	public function get_errors() {
		return $this->errors;
	}

	/**
	 * Get collected warnings.
	 *
	 * @return array Warning log entries.
	 */
	public function get_warnings() {
		return $this->warnings;
	}

	/**
	 * Check if any errors have been logged.
	 *
	 * @return bool True if errors exist, false otherwise.
	 */
	public function has_errors() {
		return ! empty( $this->errors );
	}
}
