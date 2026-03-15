<?php
/**
 * Packager Class
 *
 * Handles ZIP archive creation for all migration artifacts.
 * Creates organized directory structure and generates secure download URLs.
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Packager Class
 */
class Digital_Lobster_Exporter_Packager {

	use Digital_Lobster_Exporter_Error_Logger;

	/**
	 * Base artifacts directory path.
	 *
	 * @var string
	 */
	private $artifacts_base_dir = '';

	/**
	 * Export directory path (temporary uncompressed files).
	 *
	 * @var string
	 */
	private $export_dir = '';

	/**
	 * ZIP file path.
	 *
	 * @var string
	 */
	private $zip_file_path = '';

	/**
	 * ZIP filename.
	 *
	 * @var string
	 */
	private $zip_filename = '';

	/**
	 * Cleanup after hours (configurable).
	 *
	 * @var int
	 */
	private $cleanup_after_hours = 24;

	/**
	 * Constructor.
	 */
	public function __construct() {
		// Set base artifacts directory in wp-content/uploads/
		$upload_dir = wp_upload_dir();
		$this->artifacts_base_dir = trailingslashit( $upload_dir['basedir'] ) . 'ai_migration_artifacts/';

		// Get cleanup setting from options
		$settings = get_option( 'digital_lobster_settings', array() );
		if ( isset( $settings['cleanup_after_hours'] ) ) {
			$this->cleanup_after_hours = absint( $settings['cleanup_after_hours'] );
		}
	}

	/**
	 * Create artifacts directory structure.
	 *
	 * @return string|false Export directory path on success, false on failure.
	 */
	public function create_artifacts_directory() {
		try {
			// Create base directory if it doesn't exist
			if ( ! file_exists( $this->artifacts_base_dir ) ) {
				if ( ! wp_mkdir_p( $this->artifacts_base_dir ) ) {
					throw new Exception( 'Failed to create artifacts base directory' );
				}
			}

			// Create unique export directory with timestamp
			$timestamp = current_time( 'Y-m-d_H-i-s' );
			$unique_id = substr( md5( uniqid( '', true ) ), 0, 8 );
			$export_dirname = 'export_' . $timestamp . '_' . $unique_id;
			
			$this->export_dir = trailingslashit( $this->artifacts_base_dir . $export_dirname );

			// Create export directory
			if ( ! wp_mkdir_p( $this->export_dir ) ) {
				throw new Exception( 'Failed to create export directory' );
			}

			// Create subdirectories for organized structure
			$subdirs = array(
				'content',
				'snapshots',
				'media',
				'theme',
				'theme/templates',
				'plugins',
				'plugins/readmes',
				'plugins/feature_maps',
				'plugins/templates',
				'assets',
				'assets/js',
				'assets/css',
			);

			foreach ( $subdirs as $subdir ) {
				$subdir_path = $this->export_dir . $subdir;
				if ( ! file_exists( $subdir_path ) ) {
					wp_mkdir_p( $subdir_path );
				}
			}

			return $this->export_dir;

		} catch ( Exception $e ) {
			$this->log_error( 'packager', $e->getMessage(), 'error' );
			return false;
		}
	}

	/**
	 * Create ZIP archive from export directory.
	 *
	 * @param string $export_dir Export directory path.
	 * @return array Result with success status, zip_path, and download_url.
	 */
	public function create_zip( $export_dir = '' ) {
		try {
			// Use provided export_dir or the one set in the instance
			if ( empty( $export_dir ) ) {
				$export_dir = $this->export_dir;
			} else {
				$this->export_dir = trailingslashit( $export_dir );
			}

			// Validate export directory exists
			if ( ! file_exists( $this->export_dir ) ) {
				throw new Exception( 'Export directory does not exist' );
			}

			// Check if ZipArchive is available
			if ( ! class_exists( 'ZipArchive' ) ) {
				throw new Exception( 'ZipArchive extension is not available' );
			}

			// Generate ZIP filename with timestamp
			$timestamp = current_time( 'Y-m-d_H-i-s' );
			$this->zip_filename = 'migration-artifacts-' . $timestamp . '.zip';
			$this->zip_file_path = $this->artifacts_base_dir . $this->zip_filename;

			// Create ZIP archive
			$zip = new ZipArchive();
			$result = $zip->open( $this->zip_file_path, ZipArchive::CREATE | ZipArchive::OVERWRITE );

			if ( $result !== true ) {
				throw new Exception( 'Failed to create ZIP archive: ' . $this->get_zip_error_message( $result ) );
			}

			// Add all files from export directory to ZIP
			$files_added = $this->add_directory_to_zip( $zip, $this->export_dir, '' );

			// Close ZIP archive
			$zip->close();

			if ( $files_added === 0 ) {
				throw new Exception( 'No files were added to ZIP archive' );
			}

			// Verify ZIP file was created
			if ( ! file_exists( $this->zip_file_path ) ) {
				throw new Exception( 'ZIP file was not created' );
			}

			// Get ZIP file size
			$zip_size = filesize( $this->zip_file_path );

			// Generate secure download URL
			$download_url = $this->generate_download_url();

			// Clean up temporary uncompressed files
			$this->cleanup_temp_files( $this->export_dir );

			return array(
				'success'      => true,
				'zip_path'     => $this->zip_file_path,
				'zip_filename' => $this->zip_filename,
				'zip_size'     => $zip_size,
				'download_url' => $download_url,
				'files_added'  => $files_added,
			);

		} catch ( Exception $e ) {
			$this->log_error( 'packager', $e->getMessage(), 'error' );
			
			return array(
				'success' => false,
				'error'   => $e->getMessage(),
			);
		}
	}

	/**
	 * Add directory contents to ZIP archive recursively.
	 *
	 * @param ZipArchive $zip ZIP archive object.
	 * @param string     $source_dir Source directory path.
	 * @param string     $zip_path Path within ZIP archive.
	 * @return int Number of files added.
	 */
	private function add_directory_to_zip( $zip, $source_dir, $zip_path ) {
		$files_added = 0;
		$source_dir = trailingslashit( $source_dir );

		try {
			// Open directory
			$dir = opendir( $source_dir );
			
			if ( ! $dir ) {
				throw new Exception( 'Failed to open directory: ' . $source_dir );
			}

			// Iterate through directory contents
			while ( false !== ( $file = readdir( $dir ) ) ) {
				// Skip . and ..
				if ( $file === '.' || $file === '..' ) {
					continue;
				}

				$source_path = $source_dir . $file;
				$zip_file_path = $zip_path . $file;

				if ( is_dir( $source_path ) ) {
					// Add directory to ZIP
					$zip->addEmptyDir( $zip_file_path );
					
					// Recursively add directory contents
					$files_added += $this->add_directory_to_zip( $zip, $source_path, $zip_file_path . '/' );
				} else {
					// Add file to ZIP
					if ( $zip->addFile( $source_path, $zip_file_path ) ) {
						$files_added++;
					} else {
						$this->log_error(
							'packager',
							sprintf( 'Failed to add file to ZIP: %s', $file ),
							'warning'
						);
					}
				}
			}

			closedir( $dir );

		} catch ( Exception $e ) {
			$this->log_error( 'packager', $e->getMessage(), 'warning' );
		}

		return $files_added;
	}

	/**
	 * Generate secure download URL with time-limited token.
	 *
	 * @return string Download URL.
	 */
	public function generate_download_url() {
		$expiration = $this->cleanup_after_hours * HOUR_IN_SECONDS;
		$expires_at = current_time( 'timestamp' ) + $expiration;
		$signature  = $this->build_download_signature( $this->zip_filename, $expires_at );

		// Keep the legacy transient-backed token as a fallback for older links.
		$token = $this->generate_download_token();
		set_transient(
			'digital_lobster_download_' . $token,
			array(
				'zip_path'     => $this->zip_file_path,
				'zip_filename' => $this->zip_filename,
				'created_at'   => current_time( 'timestamp' ),
			),
			$expiration
		);

		// Generate download URL
		$download_url = add_query_arg(
			array(
				'action'    => 'digital_lobster_download',
				'file'      => rawurlencode( $this->zip_filename ),
				'expires'   => $expires_at,
				'signature' => $signature,
				'token'     => $token,
				'nonce'     => wp_create_nonce( 'digital_lobster_download_' . $token ),
			),
			admin_url( 'admin-ajax.php' )
		);

		return $download_url;
	}

	/**
	 * Generate secure download token.
	 *
	 * @return string Download token.
	 */
	private function generate_download_token() {
		// Generate random token
		$token = wp_generate_password( 32, false );
		
		// Hash token for additional security
		$token = hash( 'sha256', $token . wp_salt() );

		return $token;
	}

	/**
	 * Build a stateless signature for a downloadable ZIP file.
	 *
	 * @param string $zip_filename ZIP filename.
	 * @param int    $expires_at Absolute expiration timestamp.
	 * @return string
	 */
	private function build_download_signature( $zip_filename, $expires_at ) {
		return hash_hmac( 'sha256', $zip_filename . '|' . (int) $expires_at, wp_salt( 'auth' ) );
	}

	/**
	 * Resolve a ZIP filename into a safe absolute path inside the artifacts directory.
	 *
	 * @param string $zip_filename ZIP filename.
	 * @return string|false
	 */
	private function get_zip_path_from_filename( $zip_filename ) {
		$zip_filename = basename( rawurldecode( (string) $zip_filename ) );

		if ( empty( $zip_filename ) || substr( $zip_filename, -4 ) !== '.zip' ) {
			return false;
		}

		$zip_path = $this->artifacts_base_dir . $zip_filename;
		$real_dir = realpath( $this->artifacts_base_dir );
		$real_zip = realpath( $zip_path );

		if ( false === $real_dir || false === $real_zip ) {
			return false;
		}

		if ( strpos( $real_zip, $real_dir . DIRECTORY_SEPARATOR ) !== 0 && $real_zip !== $real_dir . DIRECTORY_SEPARATOR . $zip_filename ) {
			return false;
		}

		return $real_zip;
	}

	/**
	 * Verify a stateless signed download request.
	 *
	 * @param string $zip_filename ZIP filename.
	 * @param int    $expires_at Expiration timestamp.
	 * @param string $signature Provided signature.
	 * @return array|false
	 */
	private function verify_signed_download( $zip_filename, $expires_at, $signature ) {
		$expires_at = (int) $expires_at;

		if ( empty( $zip_filename ) || empty( $signature ) || $expires_at < 1 ) {
			$this->debug_log_download_failure( 'Signed download request is missing required fields.' );
			return false;
		}

		if ( current_time( 'timestamp' ) > $expires_at ) {
			$this->debug_log_download_failure( 'Signed download request expired for file ' . basename( rawurldecode( (string) $zip_filename ) ) );
			return false;
		}

		$expected_signature = $this->build_download_signature( basename( rawurldecode( (string) $zip_filename ) ), $expires_at );
		if ( ! hash_equals( $expected_signature, (string) $signature ) ) {
			$this->debug_log_download_failure( 'Signed download request failed signature verification.' );
			return false;
		}

		$zip_path = $this->get_zip_path_from_filename( $zip_filename );
		if ( false === $zip_path || ! file_exists( $zip_path ) ) {
			$this->debug_log_download_failure( 'Signed download request points to a missing ZIP: ' . basename( rawurldecode( (string) $zip_filename ) ) );
			return false;
		}

		return array(
			'zip_path'     => $zip_path,
			'zip_filename' => basename( $zip_path ),
		);
	}

	/**
	 * Verify a download request using either the stateless signature or the legacy transient token.
	 *
	 * @param array $request Request arguments.
	 * @return array|false
	 */
	public function verify_download_request( array $request ) {
		if ( ! empty( $request['file'] ) && ! empty( $request['expires'] ) && ! empty( $request['signature'] ) ) {
			$verified = $this->verify_signed_download( $request['file'], $request['expires'], $request['signature'] );
			if ( false !== $verified ) {
				return $verified;
			}
		}

		if ( ! empty( $request['token'] ) && ! empty( $request['nonce'] ) ) {
			return $this->verify_download_token( $request['token'], $request['nonce'] );
		}

		$this->debug_log_download_failure( 'Download request did not include a valid verification mechanism.' );
		return false;
	}

	/**
	 * Verify download token and get ZIP file path.
	 *
	 * @param string $token Download token.
	 * @param string $nonce Nonce for verification.
	 * @return array|false Array with zip_path and zip_filename on success, false on failure.
	 */
	public function verify_download_token( $token, $nonce ) {
		// Verify nonce
		if ( ! wp_verify_nonce( $nonce, 'digital_lobster_download_' . $token ) ) {
			$this->debug_log_download_failure( 'Legacy download nonce verification failed.' );
			return false;
		}

		// Get transient data
		$transient_key = 'digital_lobster_download_' . $token;
		$transient_data = get_transient( $transient_key );

		if ( ! $transient_data || ! is_array( $transient_data ) ) {
			$this->debug_log_download_failure( 'Legacy download transient was missing for token ' . substr( $token, 0, 12 ) . '...' );
			return false;
		}

		// Verify ZIP file exists
		if ( ! isset( $transient_data['zip_path'] ) || ! file_exists( $transient_data['zip_path'] ) ) {
			$this->debug_log_download_failure( 'Legacy download ZIP path was missing on disk for token ' . substr( $token, 0, 12 ) . '...' );
			return false;
		}

		return $transient_data;
	}

	/**
	 * Emit download verification failures to the PHP error log when WP_DEBUG is enabled.
	 *
	 * @param string $message Message to log.
	 * @return void
	 */
	private function debug_log_download_failure( $message ) {
		if ( defined( 'WP_DEBUG' ) && WP_DEBUG ) {
			error_log( 'Digital Lobster Exporter: Download verification failed: ' . $message );
		}
	}

	/**
	 * Serve ZIP file for download.
	 *
	 * @param string $zip_path ZIP file path.
	 * @param string $zip_filename ZIP filename for download.
	 */
	public function serve_download( $zip_path, $zip_filename ) {
		// Verify file exists
		if ( ! file_exists( $zip_path ) ) {
			wp_die( 'File not found', 'Download Error', array( 'response' => 404 ) );
		}

		// Get file size
		$file_size = filesize( $zip_path );

		// Set headers for download
		header( 'Content-Type: application/zip' );
		header( 'Content-Disposition: attachment; filename="' . $zip_filename . '"' );
		header( 'Content-Length: ' . $file_size );
		header( 'Cache-Control: no-cache, must-revalidate' );
		header( 'Expires: 0' );
		header( 'Pragma: public' );

		// Clear output buffer
		if ( ob_get_level() ) {
			ob_end_clean();
		}

		// Read and output file in chunks to handle large files
		$chunk_size = 1024 * 1024; // 1MB chunks
		$handle = fopen( $zip_path, 'rb' );

		if ( $handle === false ) {
			wp_die( 'Failed to open file', 'Download Error', array( 'response' => 500 ) );
		}

		while ( ! feof( $handle ) ) {
			echo fread( $handle, $chunk_size );
			flush();
		}

		fclose( $handle );
		exit;
	}

	/**
	 * Clean up temporary uncompressed files.
	 *
	 * @param string $export_dir Export directory to clean up.
	 * @return bool True on success, false on failure.
	 */
	public function cleanup_temp_files( $export_dir = '' ) {
		try {
			// Use provided export_dir or the one set in the instance
			if ( empty( $export_dir ) ) {
				$export_dir = $this->export_dir;
			}

			$real_export_dir = realpath( $export_dir );
			$real_artifacts_dir = realpath( $this->artifacts_base_dir );

			// Never recursively delete the base artifacts directory that stores ZIP files.
			if ( false !== $real_export_dir && false !== $real_artifacts_dir && $real_export_dir === $real_artifacts_dir ) {
				$this->debug_log_download_failure( 'Refused to delete the base artifacts directory during temporary cleanup.' );
				return true;
			}

			// Validate directory exists
			if ( empty( $export_dir ) || ! file_exists( $export_dir ) ) {
				return true; // Already cleaned up
			}

			// Use direct file operations for AJAX requests to avoid admin dependencies
			// WP_Filesystem requires admin includes that may not be available during AJAX
			$result = $this->delete_directory_recursive( $export_dir );

			if ( ! $result ) {
				$this->log_error(
					'packager',
					'Failed to clean up temporary files: ' . $export_dir,
					'warning'
				);
				return false;
			}

			return true;

		} catch ( Exception $e ) {
			$this->log_error( 'packager', $e->getMessage(), 'warning' );
			return false;
		}
	}

	/**
	 * Delete directory recursively (fallback method).
	 *
	 * @param string $dir Directory path.
	 * @return bool True on success, false on failure.
	 */
	private function delete_directory_recursive( $dir ) {
		if ( ! file_exists( $dir ) ) {
			return true;
		}

		if ( ! is_dir( $dir ) ) {
			return unlink( $dir );
		}

		foreach ( scandir( $dir ) as $item ) {
			if ( $item === '.' || $item === '..' ) {
				continue;
			}

			if ( ! $this->delete_directory_recursive( $dir . DIRECTORY_SEPARATOR . $item ) ) {
				return false;
			}
		}

		return rmdir( $dir );
	}

	/**
	 * Clean up old artifacts based on cleanup time setting.
	 *
	 * @return array Cleanup results with count of deleted files.
	 */
	public function cleanup_old_artifacts() {
		$deleted_count = 0;
		$errors = array();

		try {
			// Check if base directory exists
			if ( ! file_exists( $this->artifacts_base_dir ) ) {
				return array(
					'success' => true,
					'deleted' => 0,
					'message' => 'No artifacts directory found',
				);
			}

			// Get current time
			$current_time = current_time( 'timestamp' );
			$cleanup_threshold = $current_time - ( $this->cleanup_after_hours * HOUR_IN_SECONDS );

			// Scan for ZIP files and export directories
			$items = scandir( $this->artifacts_base_dir );

			foreach ( $items as $item ) {
				if ( $item === '.' || $item === '..' ) {
					continue;
				}

				$item_path = $this->artifacts_base_dir . $item;

				// Get file/directory modification time
				$mtime = filemtime( $item_path );

				// Delete if older than cleanup threshold
				if ( $mtime < $cleanup_threshold ) {
					if ( is_dir( $item_path ) ) {
						// Delete export directory
						if ( $this->cleanup_temp_files( $item_path ) ) {
							$deleted_count++;
						} else {
							$errors[] = 'Failed to delete directory: ' . $item;
						}
					} elseif ( is_file( $item_path ) && pathinfo( $item_path, PATHINFO_EXTENSION ) === 'zip' ) {
						// Delete ZIP file
						if ( unlink( $item_path ) ) {
							$deleted_count++;
						} else {
							$errors[] = 'Failed to delete file: ' . $item;
						}
					}
				}
			}

			return array(
				'success' => true,
				'deleted' => $deleted_count,
				'errors'  => $errors,
				'message' => sprintf( 'Cleaned up %d old artifact(s)', $deleted_count ),
			);

		} catch ( Exception $e ) {
			$this->log_error( 'packager', $e->getMessage(), 'error' );
			
			return array(
				'success' => false,
				'error'   => $e->getMessage(),
			);
		}
	}

	/**
	 * Get ZIP error message from error code.
	 *
	 * @param int $error_code ZipArchive error code.
	 * @return string Error message.
	 */
	private function get_zip_error_message( $error_code ) {
		$error_messages = array(
			ZipArchive::ER_EXISTS => 'File already exists',
			ZipArchive::ER_INCONS => 'Zip archive inconsistent',
			ZipArchive::ER_INVAL  => 'Invalid argument',
			ZipArchive::ER_MEMORY => 'Memory allocation failure',
			ZipArchive::ER_NOENT  => 'No such file',
			ZipArchive::ER_NOZIP  => 'Not a zip archive',
			ZipArchive::ER_OPEN   => 'Cannot open file',
			ZipArchive::ER_READ   => 'Read error',
			ZipArchive::ER_SEEK   => 'Seek error',
		);

		return isset( $error_messages[ $error_code ] ) 
			? $error_messages[ $error_code ] 
			: 'Unknown error (' . $error_code . ')';
	}

	/**
	 * Get artifacts base directory path.
	 *
	 * @return string Artifacts base directory path.
	 */
	public function get_artifacts_base_dir() {
		return $this->artifacts_base_dir;
	}

	/**
	 * Get export directory path.
	 *
	 * @return string Export directory path.
	 */
	public function get_export_dir() {
		return $this->export_dir;
	}

	/**
	 * Get ZIP file path.
	 *
	 * @return string ZIP file path.
	 */
	public function get_zip_file_path() {
		return $this->zip_file_path;
	}

	/**
	 * Get ZIP filename.
	 *
	 * @return string ZIP filename.
	 */
	public function get_zip_filename() {
		return $this->zip_filename;
	}

}
