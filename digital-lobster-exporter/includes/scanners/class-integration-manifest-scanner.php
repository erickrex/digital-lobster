<?php
/**
 * Integration Manifest Scanner Class
 *
 * Produces a normalized integration_manifest.json artifact containing
 * an inventory of external integrations: form destinations, webhooks,
 * CRM/newsletter targets, embed providers, runtime APIs, and
 * third-party scripts.
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Integration Manifest Scanner Class
 */
class Digital_Lobster_Exporter_Integration_Manifest_Scanner extends Digital_Lobster_Exporter_Scanner_Base {

	/**
	 * Collected integrations.
	 *
	 * @var array
	 */
	private $integrations = array();

	/**
	 * Scan external integrations.
	 *
	 * @return array Integration manifest data matching IntegrationManifestArtifact schema.
	 */
	public function scan() {
		$this->integrations = array();

		$this->scan_form_destinations();
		$this->scan_webhooks();
		$this->scan_crm_newsletter();
		$this->scan_embed_providers();
		$this->scan_runtime_apis();
		$this->scan_third_party_scripts();

		return array(
			'schema_version' => '1.0.0',
			'integrations'   => array_values( $this->integrations ),
		);
	}

	/**
	 * Scan form submission destinations.
	 */
	private function scan_form_destinations() {
		// Contact Form 7 mail destinations.
		if ( class_exists( 'WPCF7_ContactForm' ) ) {
			$forms = get_posts( array(
				'post_type'      => 'wpcf7_contact_form',
				'posts_per_page' => -1,
				'post_status'    => 'publish',
			) );

			foreach ( $forms as $form ) {
				$mail = get_post_meta( $form->ID, '_mail', true );
				if ( ! empty( $mail ) && ! empty( $mail['recipient'] ) ) {
					$this->add_integration(
						'cf7:mail:' . $form->ID,
						'form_destination',
						$this->security_filters->filter_value( $mail['recipient'] ),
						array( 'form_title' => $form->post_title ),
						true
					);
				}

				// Check for additional services (e.g., Flamingo, external APIs).
				$additional = get_post_meta( $form->ID, '_additional_settings', true );
				if ( ! empty( $additional ) && strpos( $additional, 'skip_mail' ) !== false ) {
					$this->add_integration(
						'cf7:custom_handler:' . $form->ID,
						'form_destination',
						'custom_handler',
						array( 'form_title' => $form->post_title ),
						true
					);
				}
			}
		}

		// Gravity Forms notifications and feeds.
		if ( class_exists( 'GFAPI' ) ) {
			try {
				$forms = \GFAPI::get_forms();
				foreach ( $forms as $form ) {
					if ( ! empty( $form['notifications'] ) ) {
						foreach ( $form['notifications'] as $notification ) {
							$this->add_integration(
								'gf:notification:' . $form['id'] . ':' . $notification['id'],
								'form_destination',
								$this->security_filters->filter_value(
									isset( $notification['to'] ) ? $notification['to'] : 'unknown'
								),
								array( 'form_title' => $form['title'] ),
								true
							);
						}
					}
				}
			} catch ( \Exception $e ) {
				$this->log_warning( 'integration_manifest', 'Failed to scan Gravity Forms: ' . $e->getMessage() );
			}
		}
	}

	/**
	 * Scan webhook integrations.
	 */
	private function scan_webhooks() {
		// Ensure is_plugin_active() is available.
		if ( ! function_exists( 'is_plugin_active' ) ) {
			require_once ABSPATH . 'wp-admin/includes/plugin.php';
		}

		// Check for WP Webhooks plugin.
		if ( class_exists( 'WP_Webhooks_Pro' ) || class_exists( 'WP_Webhooks' ) ) {
			$this->add_integration(
				'wp_webhooks:global',
				'webhook',
				'wp_webhooks_plugin',
				array(),
				true
			);
		}

		// Check for Zapier plugin.
		if ( is_plugin_active( 'zapier/zapier.php' ) || is_plugin_active( 'wp-zapier/wp-zapier.php' ) ) {
			$this->add_integration(
				'zapier:global',
				'webhook',
				'zapier',
				array(),
				true
			);
		}

		// Check for webhook URLs in options.
		$webhook_options = array( 'webhook_url', 'zapier_webhook', 'slack_webhook_url' );
		foreach ( $webhook_options as $opt ) {
			$value = get_option( $opt, '' );
			if ( ! empty( $value ) && filter_var( $value, FILTER_VALIDATE_URL ) ) {
				$this->add_integration(
					'option:webhook:' . $opt,
					'webhook',
					$this->security_filters->filter_value( $value ),
					array( 'option_name' => $opt ),
					true
				);
			}
		}
	}

	/**
	 * Scan CRM and newsletter integrations.
	 */
	private function scan_crm_newsletter() {
		// Ensure is_plugin_active() is available.
		if ( ! function_exists( 'is_plugin_active' ) ) {
			require_once ABSPATH . 'wp-admin/includes/plugin.php';
		}

		// Mailchimp.
		$mc_api_key = get_option( 'mc4wp_api_key', '' );
		if ( ! empty( $mc_api_key ) || is_plugin_active( 'mailchimp-for-wp/mailchimp-for-wp.php' ) ) {
			$this->add_integration(
				'mailchimp:global',
				'crm',
				'mailchimp',
				array(),
				true
			);
		}

		// HubSpot.
		if ( is_plugin_active( 'leadin/leadin.php' ) || is_plugin_active( 'hubspot-all-in-one-marketing/leadin.php' ) ) {
			$this->add_integration(
				'hubspot:global',
				'crm',
				'hubspot',
				array(),
				true
			);
		}

		// ActiveCampaign.
		$ac_url = get_option( 'activecampaign_url', '' );
		if ( ! empty( $ac_url ) ) {
			$this->add_integration(
				'activecampaign:global',
				'crm',
				'activecampaign',
				array(),
				true
			);
		}

		// ConvertKit.
		if ( is_plugin_active( 'convertkit/convertkit.php' ) ) {
			$this->add_integration(
				'convertkit:global',
				'crm',
				'convertkit',
				array(),
				false
			);
		}
	}

	/**
	 * Scan embed providers from post content.
	 */
	private function scan_embed_providers() {
		global $wpdb;

		// Detect common embed patterns in post content.
		$embed_patterns = array(
			'youtube'     => array( 'youtube.com/embed', 'youtu.be', 'youtube.com/watch' ),
			'vimeo'       => array( 'vimeo.com' ),
			'twitter'     => array( 'twitter.com', 'x.com' ),
			'instagram'   => array( 'instagram.com' ),
			'google_maps' => array( 'maps.google.com', 'google.com/maps' ),
			'spotify'     => array( 'open.spotify.com' ),
		);

		foreach ( $embed_patterns as $provider => $patterns ) {
			foreach ( $patterns as $pattern ) {
				// phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery, WordPress.DB.DirectDatabaseQuery.NoCaching
				$found = $wpdb->get_var(
					$wpdb->prepare(
						"SELECT COUNT(*) FROM {$wpdb->posts}
						WHERE post_content LIKE %s
						AND post_status IN ('publish', 'draft')
						LIMIT 1",
						'%' . $wpdb->esc_like( $pattern ) . '%'
					)
				);

				if ( (int) $found > 0 ) {
					$this->add_integration(
						'embed:' . $provider,
						'embed',
						$provider,
						array( 'pattern' => $pattern ),
						false
					);
					break; // One match per provider is enough.
				}
			}
		}
	}

	/**
	 * Scan runtime API integrations.
	 */
	private function scan_runtime_apis() {
		// Google Analytics / Tag Manager.
		$ga_id = get_option( 'google_analytics_id', '' );
		if ( empty( $ga_id ) ) {
			$ga_id = get_option( 'ga_tracking_id', '' );
		}
		if ( ! empty( $ga_id ) ) {
			$this->add_integration(
				'google_analytics:global',
				'runtime_api',
				'google_analytics',
				array( 'tracking_id' => $this->security_filters->filter_value( $ga_id ) ),
				false
			);
		}

		// Google Tag Manager.
		$gtm_id = get_option( 'gtm_id', '' );
		if ( ! empty( $gtm_id ) ) {
			$this->add_integration(
				'google_tag_manager:global',
				'runtime_api',
				'google_tag_manager',
				array(),
				false
			);
		}

		// Google reCAPTCHA.
		$recaptcha_key = get_option( 'recaptcha_site_key', '' );
		if ( empty( $recaptcha_key ) ) {
			$recaptcha_key = get_option( 'wpcf7_recaptcha', '' );
		}
		if ( ! empty( $recaptcha_key ) ) {
			$this->add_integration(
				'recaptcha:global',
				'runtime_api',
				'google_recaptcha',
				array(),
				true
			);
		}
	}

	/**
	 * Scan third-party scripts from theme and plugin output.
	 */
	private function scan_third_party_scripts() {
		// Check for common third-party script patterns in options.
		$script_options = array(
			'header_scripts',
			'footer_scripts',
			'custom_css_js',
			'insert_headers_and_footers_scripts_in_header',
			'insert_headers_and_footers_scripts_in_footer',
		);

		$external_domains = array(
			'cdn.jsdelivr.net',
			'cdnjs.cloudflare.com',
			'unpkg.com',
			'fonts.googleapis.com',
			'connect.facebook.net',
			'platform.twitter.com',
			'www.googletagmanager.com',
		);

		foreach ( $script_options as $opt ) {
			$value = get_option( $opt, '' );
			if ( empty( $value ) ) {
				continue;
			}

			foreach ( $external_domains as $domain ) {
				if ( strpos( $value, $domain ) !== false ) {
					$this->add_integration(
						'script:' . str_replace( '.', '_', $domain ),
						'third_party_script',
						$domain,
						array( 'found_in' => $opt ),
						false
					);
				}
			}
		}
	}

	/**
	 * Add an integration to the collection.
	 *
	 * @param string $integration_id   Stable integration identifier.
	 * @param string $integration_type Integration type classification.
	 * @param string $target           Integration target.
	 * @param array  $config           Integration configuration.
	 * @param bool   $business_critical Whether this is business-critical.
	 */
	private function add_integration( $integration_id, $integration_type, $target, $config, $business_critical ) {
		$this->integrations[ $integration_id ] = array(
			'integration_id'    => $integration_id,
			'integration_type'  => $integration_type,
			'target'            => $target,
			'config'            => $config,
			'business_critical' => $business_critical,
		);
	}
}
