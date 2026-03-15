<?php
/**
 * Security and Privacy Filters Class
 *
 * Provides centralized security and privacy filtering for all exported data.
 * This class ensures that sensitive information like passwords, API keys, tokens,
 * and PII are never included in the migration artifacts.
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Security Filters Class
 */
class Digital_Lobster_Exporter_Security_Filters {

	/**
	 * Sensitive option keys that should never be exported.
	 *
	 * @var array
	 */
	private static $sensitive_option_keys = array(
		// WordPress core sensitive options
		'secret_key',
		'auth_key',
		'secure_auth_key',
		'logged_in_key',
		'nonce_key',
		'auth_salt',
		'secure_auth_salt',
		'logged_in_salt',
		'nonce_salt',
		'secret',
		'password',
		'pwd',
		'pass',
		'api_key',
		'apikey',
		'api_secret',
		'access_token',
		'refresh_token',
		'oauth_token',
		'consumer_key',
		'consumer_secret',
		'private_key',
		'public_key',
		'license_key',
		'activation_key',
		
		// Database credentials
		'db_password',
		'db_host',
		'db_user',
		'db_name',
		
		// Email/SMTP credentials
		'smtp_password',
		'smtp_pass',
		'mail_password',
		'mailgun_api_key',
		'sendgrid_api_key',
		'ses_access_key',
		'ses_secret_key',
		
		// Payment gateway credentials
		'stripe_secret_key',
		'stripe_publishable_key',
		'paypal_api_password',
		'paypal_api_signature',
		'paypal_api_username',
		
		// Social media credentials
		'facebook_app_secret',
		'twitter_consumer_secret',
		'twitter_access_token_secret',
		'google_client_secret',
		
		// Security plugins
		'recaptcha_secret_key',
		'recaptcha_private_key',
		
		// Backup/storage credentials
		'aws_access_key',
		'aws_secret_key',
		's3_access_key',
		's3_secret_key',
		'dropbox_token',
		'google_drive_token',
		
		// Other sensitive data
		'encryption_key',
		'salt',
		'hash',
		'token',
		'bearer',
		'jwt',
		'session_token',
	);

	/**
	 * Sensitive meta keys that should never be exported.
	 *
	 * @var array
	 */
	private static $sensitive_meta_keys = array(
		'_password',
		'_user_pass',
		'_api_key',
		'_secret',
		'_token',
		'_access_token',
		'_refresh_token',
		'_private_key',
		'_license_key',
		'_activation_key',
	);

	/**
	 * PII-related meta keys that should be filtered.
	 *
	 * @var array
	 */
	private static $pii_meta_keys = array(
		'_billing_email',
		'_billing_phone',
		'_billing_address',
		'_shipping_address',
		'_customer_email',
		'_customer_phone',
		'_user_email',
		'_contact_email',
		'_phone_number',
		'_mobile_number',
		'_social_security',
		'_tax_id',
		'_credit_card',
		'_bank_account',
		'_ip_address',
		'_user_ip',
	);

	/**
	 * Temporary and cache-related keys to exclude.
	 *
	 * @var array
	 */
	private static $temporary_keys = array(
		'_transient',
		'_site_transient',
		'_cache',
		'_temp',
		'_tmp',
		'_session',
	);

	/**
	 * Check if an option key is sensitive and should be excluded.
	 *
	 * @param string $key Option key to check.
	 * @return bool True if sensitive, false otherwise.
	 */
	public static function is_sensitive_option( $key ) {
		$key_lower = strtolower( $key );
		
		// Check exact matches
		foreach ( self::$sensitive_option_keys as $sensitive_key ) {
			if ( strpos( $key_lower, strtolower( $sensitive_key ) ) !== false ) {
				return true;
			}
		}
		
		return false;
	}

	/**
	 * Check if a meta key is sensitive and should be excluded.
	 *
	 * @param string $key Meta key to check.
	 * @return bool True if sensitive, false otherwise.
	 */
	public static function is_sensitive_meta( $key ) {
		$key_lower = strtolower( $key );
		
		// Check exact matches
		foreach ( self::$sensitive_meta_keys as $sensitive_key ) {
			if ( strpos( $key_lower, strtolower( $sensitive_key ) ) !== false ) {
				return true;
			}
		}
		
		return false;
	}

	/**
	 * Check if a meta key contains PII.
	 *
	 * @param string $key Meta key to check.
	 * @return bool True if contains PII, false otherwise.
	 */
	public static function is_pii_meta( $key ) {
		$key_lower = strtolower( $key );
		
		// Check exact matches
		foreach ( self::$pii_meta_keys as $pii_key ) {
			if ( strpos( $key_lower, strtolower( $pii_key ) ) !== false ) {
				return true;
			}
		}
		
		return false;
	}

	/**
	 * Check if a key is temporary/cache data.
	 *
	 * @param string $key Key to check.
	 * @return bool True if temporary, false otherwise.
	 */
	public static function is_temporary_key( $key ) {
		$key_lower = strtolower( $key );
		
		// Check for temporary key patterns
		foreach ( self::$temporary_keys as $temp_key ) {
			if ( strpos( $key_lower, strtolower( $temp_key ) ) !== false ) {
				return true;
			}
		}
		
		return false;
	}

	/**
	 * Filter wp_options data to remove sensitive information.
	 *
	 * @param array $options Array of options to filter.
	 * @return array Filtered options.
	 */
	public static function filter_options( $options ) {
		if ( ! is_array( $options ) ) {
			return $options;
		}

		$filtered = array();

		foreach ( $options as $key => $value ) {
			// Skip sensitive options
			if ( self::is_sensitive_option( $key ) ) {
				continue;
			}

			// Skip temporary/cache data
			if ( self::is_temporary_key( $key ) ) {
				continue;
			}

			// Recursively filter array values
			if ( is_array( $value ) ) {
				$value = self::filter_array_recursive( $value );
			}

			$filtered[ $key ] = $value;
		}

		return $filtered;
	}

	/**
	 * Filter post meta data to remove sensitive information and PII.
	 *
	 * @param array $meta Array of meta data to filter.
	 * @return array Filtered meta data.
	 */
	public static function filter_post_meta( $meta ) {
		if ( ! is_array( $meta ) ) {
			return $meta;
		}

		$filtered = array();

		foreach ( $meta as $key => $value ) {
			// Skip sensitive meta
			if ( self::is_sensitive_meta( $key ) ) {
				continue;
			}

			// Skip PII meta
			if ( self::is_pii_meta( $key ) ) {
				continue;
			}

			// Skip temporary data
			if ( self::is_temporary_key( $key ) ) {
				continue;
			}

			// Recursively filter array values
			if ( is_array( $value ) ) {
				$value = self::filter_array_recursive( $value );
			}

			$filtered[ $key ] = $value;
		}

		return $filtered;
	}

	/**
	 * Filter user data to remove passwords and sensitive information.
	 *
	 * @param array $user_data User data array.
	 * @return array Filtered user data.
	 */
	public static function filter_user_data( $user_data ) {
		if ( ! is_array( $user_data ) ) {
			return $user_data;
		}

		// Remove sensitive user fields
		$sensitive_fields = array(
			'user_pass',
			'user_activation_key',
			'user_email', // PII
			'user_login', // PII
		);

		foreach ( $sensitive_fields as $field ) {
			unset( $user_data[ $field ] );
		}

		return $user_data;
	}

	/**
	 * Recursively filter arrays to remove sensitive data.
	 *
	 * @param array $data Array to filter.
	 * @return array Filtered array.
	 */
	private static function filter_array_recursive( $data ) {
		if ( ! is_array( $data ) ) {
			return $data;
		}

		$filtered = array();

		foreach ( $data as $key => $value ) {
			// Check if key is sensitive
			if ( self::is_sensitive_option( $key ) || self::is_sensitive_meta( $key ) ) {
				continue;
			}

			// Recursively filter nested arrays
			if ( is_array( $value ) ) {
				$value = self::filter_array_recursive( $value );
			}

			$filtered[ $key ] = $value;
		}

		return $filtered;
	}

	/**
	 * Sanitize text content for export.
	 *
	 * @param string $content Content to sanitize.
	 * @return string Sanitized content.
	 */
	public static function sanitize_content( $content ) {
		if ( ! is_string( $content ) ) {
			return $content;
		}

		// Remove email addresses (PII)
		$content = preg_replace( '/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/', '[email]', $content );

		// Remove phone numbers (PII)
		$content = preg_replace( '/\b\d{3}[-.]?\d{3}[-.]?\d{4}\b/', '[phone]', $content );
		$content = preg_replace( '/\b\(\d{3}\)\s*\d{3}[-.]?\d{4}\b/', '[phone]', $content );

		// Remove IP addresses
		$content = preg_replace( '/\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b/', '[ip_address]', $content );

		// Remove credit card numbers
		$content = preg_replace( '/\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b/', '[credit_card]', $content );

		return $content;
	}

	/**
	 * Sanitize URL to remove sensitive query parameters.
	 *
	 * @param string $url URL to sanitize.
	 * @return string Sanitized URL.
	 */
	public static function sanitize_url( $url ) {
		if ( ! is_string( $url ) || empty( $url ) ) {
			return $url;
		}

		$parsed = parse_url( $url );
		
		if ( ! isset( $parsed['query'] ) ) {
			return $url;
		}

		parse_str( $parsed['query'], $query_params );

		// Remove sensitive query parameters
		$sensitive_params = array( 'api_key', 'token', 'access_token', 'key', 'secret', 'password' );
		
		foreach ( $sensitive_params as $param ) {
			unset( $query_params[ $param ] );
		}

		// Rebuild URL
		$parsed['query'] = http_build_query( $query_params );
		
		return self::build_url( $parsed );
	}

	/**
	 * Build URL from parsed components.
	 *
	 * @param array $parsed Parsed URL components.
	 * @return string Rebuilt URL.
	 */
	private static function build_url( $parsed ) {
		$url = '';
		
		if ( isset( $parsed['scheme'] ) ) {
			$url .= $parsed['scheme'] . '://';
		}
		
		if ( isset( $parsed['user'] ) ) {
			$url .= $parsed['user'];
			if ( isset( $parsed['pass'] ) ) {
				$url .= ':' . $parsed['pass'];
			}
			$url .= '@';
		}
		
		if ( isset( $parsed['host'] ) ) {
			$url .= $parsed['host'];
		}
		
		if ( isset( $parsed['port'] ) ) {
			$url .= ':' . $parsed['port'];
		}
		
		if ( isset( $parsed['path'] ) ) {
			$url .= $parsed['path'];
		}
		
		if ( isset( $parsed['query'] ) && ! empty( $parsed['query'] ) ) {
			$url .= '?' . $parsed['query'];
		}
		
		if ( isset( $parsed['fragment'] ) ) {
			$url .= '#' . $parsed['fragment'];
		}
		
		return $url;
	}

	/**
	 * Filter widget data to remove PII.
	 *
	 * @param array $widget_data Widget data array.
	 * @return array Filtered widget data.
	 */
	public static function filter_widget_data( $widget_data ) {
		if ( ! is_array( $widget_data ) ) {
			return $widget_data;
		}

		// Recursively sanitize text content in widgets
		foreach ( $widget_data as $key => $value ) {
			if ( is_string( $value ) ) {
				$widget_data[ $key ] = self::sanitize_content( $value );
			} elseif ( is_array( $value ) ) {
				$widget_data[ $key ] = self::filter_widget_data( $value );
			}
		}

		return $widget_data;
	}

	/**
	 * Filter form data to remove submission data and PII.
	 *
	 * @param array $form_data Form configuration data.
	 * @return array Filtered form data.
	 */
	public static function filter_form_data( $form_data ) {
		if ( ! is_array( $form_data ) ) {
			return $form_data;
		}

		// Remove submission data if present
		unset( $form_data['submissions'] );
		unset( $form_data['entries'] );
		unset( $form_data['leads'] );

		// Sanitize notification emails
		if ( isset( $form_data['notifications'] ) && is_array( $form_data['notifications'] ) ) {
			foreach ( $form_data['notifications'] as $key => $notification ) {
				if ( isset( $notification['to'] ) ) {
					$form_data['notifications'][ $key ]['to'] = '[email]';
				}
				if ( isset( $notification['from'] ) ) {
					$form_data['notifications'][ $key ]['from'] = '[email]';
				}
			}
		}

		return $form_data;
	}

	/**
	 * Verify nonce for AJAX requests.
	 *
	 * @param string $nonce Nonce value to verify.
	 * @param string $action Nonce action.
	 * @return bool True if valid, false otherwise.
	 */
	public static function verify_nonce( $nonce, $action = 'digital_lobster_exporter_nonce' ) {
		return wp_verify_nonce( $nonce, $action );
	}

	/**
	 * Verify user has required capability.
	 *
	 * @param string $capability Capability to check (default: manage_options).
	 * @return bool True if user has capability, false otherwise.
	 */
	public static function verify_capability( $capability = 'manage_options' ) {
		return current_user_can( $capability );
	}

	/**
	 * Filter a single value, redacting PII and sensitive data.
	 *
	 * Works on strings, arrays, and scalar types.
	 *
	 * @param mixed $value The value to filter.
	 * @return mixed The filtered value.
	 */
	public function filter_value( $value ) {
		if ( is_array( $value ) ) {
			return self::filter_array_recursive( $value );
		}

		if ( is_string( $value ) ) {
			return self::sanitize_content( $value );
		}

		return $value;
	}

	/**
	 * Sanitize export data before saving.
	 *
	 * @param mixed $data Data to sanitize.
	 * @return mixed Sanitized data.
	 */
	public static function sanitize_export_data( $data ) {
		if ( is_array( $data ) ) {
			return self::filter_array_recursive( $data );
		} elseif ( is_string( $data ) ) {
			return self::sanitize_content( $data );
		}

		return $data;
	}

	/**
	 * Add custom sensitive keys to the filter list.
	 *
	 * @param array $keys Array of sensitive keys to add.
	 */
	public static function add_sensitive_keys( $keys ) {
		if ( is_array( $keys ) ) {
			self::$sensitive_option_keys = array_merge( self::$sensitive_option_keys, $keys );
		}
	}

	/**
	 * Add custom PII keys to the filter list.
	 *
	 * @param array $keys Array of PII keys to add.
	 */
	public static function add_pii_keys( $keys ) {
		if ( is_array( $keys ) ) {
			self::$pii_meta_keys = array_merge( self::$pii_meta_keys, $keys );
		}
	}
}
