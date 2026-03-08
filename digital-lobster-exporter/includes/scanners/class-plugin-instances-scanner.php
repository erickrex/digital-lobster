<?php
/**
 * Plugin Instances Scanner Class
 *
 * Produces a normalized plugin_instances.json artifact containing
 * an inventory of actual plugin constructs in use, scoped to
 * Supported_Plugin_Family plugins: forms (CF7, WPForms, Gravity Forms,
 * Ninja Forms), directories (GeoDirectory), SEO objects (Yoast, Rank Math,
 * AIOSEO), widgets, and singletons.
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Plugin Instances Scanner Class
 */
class Digital_Lobster_Exporter_Plugin_Instances_Scanner extends Digital_Lobster_Exporter_Scanner_Base {

	/**
	 * Collected plugin instances.
	 *
	 * @var array
	 */
	private $instances = array();

	/**
	 * Scan plugin constructs in use.
	 *
	 * @return array Plugin instances data matching PluginInstancesArtifact schema.
	 */
	public function scan() {
		$this->instances = array();

		$this->scan_contact_form_7();
		$this->scan_wpforms();
		$this->scan_gravity_forms();
		$this->scan_ninja_forms();
		$this->scan_geodirectory();
		$this->scan_yoast_seo();
		$this->scan_rank_math();
		$this->scan_aioseo();
		$this->scan_active_widgets();

		return array(
			'schema_version' => '1.0.0',
			'instances'      => array_values( $this->instances ),
		);
	}

	/**
	 * Scan Contact Form 7 forms.
	 */
	private function scan_contact_form_7() {
		if ( ! class_exists( 'WPCF7_ContactForm' ) ) {
			return;
		}

		$forms = get_posts( array(
			'post_type'      => 'wpcf7_contact_form',
			'posts_per_page' => -1,
			'post_status'    => 'publish',
		) );

		foreach ( $forms as $form ) {
			$config = array(
				'title' => $form->post_title,
				'form'  => $form->post_content,
			);

			$mail = get_post_meta( $form->ID, '_mail', true );
			if ( $mail ) {
				$config['mail_recipient'] = $this->security_filters->filter_value(
					isset( $mail['recipient'] ) ? $mail['recipient'] : ''
				);
			}

			$this->add_instance(
				'cf7:form:' . $form->ID,
				'contact_form_7',
				'form',
				$config,
				$this->find_form_references( $form->ID, 'wpcf7' )
			);
		}
	}

	/**
	 * Scan WPForms forms.
	 */
	private function scan_wpforms() {
		if ( ! function_exists( 'wpforms' ) ) {
			return;
		}

		$forms = get_posts( array(
			'post_type'      => 'wpforms',
			'posts_per_page' => -1,
			'post_status'    => 'publish',
		) );

		foreach ( $forms as $form ) {
			$form_data = json_decode( $form->post_content, true );
			$config    = array(
				'title'  => $form->post_title,
				'fields' => isset( $form_data['fields'] ) ? count( $form_data['fields'] ) : 0,
			);

			$this->add_instance(
				'wpforms:form:' . $form->ID,
				'wpforms',
				'form',
				$config,
				$this->find_form_references( $form->ID, 'wpforms' )
			);
		}
	}

	/**
	 * Scan Gravity Forms forms.
	 */
	private function scan_gravity_forms() {
		if ( ! class_exists( 'GFAPI' ) ) {
			return;
		}

		try {
			$forms = \GFAPI::get_forms();
		} catch ( \Exception $e ) {
			$this->log_warning( 'plugin_instances', 'Failed to load Gravity Forms: ' . $e->getMessage() );
			return;
		}

		if ( empty( $forms ) ) {
			return;
		}

		foreach ( $forms as $form ) {
			$config = array(
				'title'  => isset( $form['title'] ) ? $form['title'] : '',
				'fields' => isset( $form['fields'] ) ? count( $form['fields'] ) : 0,
			);

			$this->add_instance(
				'gravityforms:form:' . $form['id'],
				'gravity_forms',
				'form',
				$config,
				array()
			);
		}
	}

	/**
	 * Scan Ninja Forms forms.
	 */
	private function scan_ninja_forms() {
		if ( ! function_exists( 'Ninja_Forms' ) ) {
			return;
		}

		try {
			$forms = Ninja_Forms()->form()->get_forms();
		} catch ( \Exception $e ) {
			$this->log_warning( 'plugin_instances', 'Failed to load Ninja Forms: ' . $e->getMessage() );
			return;
		}

		if ( empty( $forms ) ) {
			return;
		}

		foreach ( $forms as $form ) {
			$form_id    = $form->get_id();
			$form_title = $form->get_setting( 'title' );

			$this->add_instance(
				'ninjaforms:form:' . $form_id,
				'ninja_forms',
				'form',
				array( 'title' => $form_title ? $form_title : '' ),
				array()
			);
		}
	}

	/**
	 * Scan GeoDirectory listings.
	 */
	private function scan_geodirectory() {
		if ( ! class_exists( 'GeoDirectory' ) ) {
			return;
		}

		$gd_post_types = function_exists( 'geodir_get_posttypes' ) ? geodir_get_posttypes( 'array' ) : array();

		foreach ( $gd_post_types as $slug => $info ) {
			$count = wp_count_posts( $slug );
			$this->add_instance(
				'geodirectory:directory:' . $slug,
				'geodirectory',
				'directory',
				array(
					'post_type'      => $slug,
					'label'          => isset( $info['labels']['name'] ) ? $info['labels']['name'] : $slug,
					'published_count' => isset( $count->publish ) ? (int) $count->publish : 0,
				),
				array()
			);
		}
	}

	/**
	 * Scan Yoast SEO configuration.
	 */
	private function scan_yoast_seo() {
		if ( ! defined( 'WPSEO_VERSION' ) ) {
			return;
		}

		$options = get_option( 'wpseo', array() );
		$titles  = get_option( 'wpseo_titles', array() );

		$this->add_instance(
			'yoast:seo:global',
			'yoast',
			'seo_object',
			array(
				'version'          => WPSEO_VERSION,
				'enable_xml_sitemap' => ! empty( $options['enable_xml_sitemap'] ),
				'breadcrumbs'      => ! empty( $titles['breadcrumbs-enable'] ),
			),
			array()
		);
	}

	/**
	 * Scan Rank Math SEO configuration.
	 */
	private function scan_rank_math() {
		if ( ! class_exists( 'RankMath' ) ) {
			return;
		}

		$general = get_option( 'rank-math-options-general', array() );

		$this->add_instance(
			'rankmath:seo:global',
			'rank_math',
			'seo_object',
			array(
				'breadcrumbs' => ! empty( $general['breadcrumbs'] ),
				'sitemap'     => ! empty( $general['sitemap'] ),
			),
			array()
		);
	}

	/**
	 * Scan All in One SEO configuration.
	 */
	private function scan_aioseo() {
		if ( ! defined( 'AIOSEO_VERSION' ) ) {
			return;
		}

		$this->add_instance(
			'aioseo:seo:global',
			'aioseo',
			'seo_object',
			array(
				'version' => AIOSEO_VERSION,
			),
			array()
		);
	}

	/**
	 * Scan active widget instances.
	 */
	private function scan_active_widgets() {
		$sidebars = wp_get_sidebars_widgets();
		if ( empty( $sidebars ) ) {
			return;
		}

		foreach ( $sidebars as $sidebar_id => $widgets ) {
			if ( 'wp_inactive_widgets' === $sidebar_id || empty( $widgets ) ) {
				continue;
			}

			foreach ( $widgets as $widget_id ) {
				$this->add_instance(
					'widget:' . $sidebar_id . ':' . $widget_id,
					'core',
					'widget',
					array(
						'sidebar'   => $sidebar_id,
						'widget_id' => $widget_id,
					),
					array()
				);
			}
		}
	}

	/**
	 * Find pages/posts that reference a form by ID.
	 *
	 * @param int    $form_id     Form post ID.
	 * @param string $plugin_slug Plugin slug for shortcode pattern.
	 * @return array List of stable post IDs referencing this form.
	 */
	private function find_form_references( $form_id, $plugin_slug ) {
		global $wpdb;

		$patterns = array(
			'wpcf7'   => '[contact-form-7 id="' . $form_id . '"',
			'wpforms' => '[wpforms id="' . $form_id . '"',
		);

		if ( ! isset( $patterns[ $plugin_slug ] ) ) {
			return array();
		}

		$pattern = $patterns[ $plugin_slug ];

		// phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery, WordPress.DB.DirectDatabaseQuery.NoCaching
		$post_ids = $wpdb->get_col(
			$wpdb->prepare(
				"SELECT ID FROM {$wpdb->posts}
				WHERE post_content LIKE %s
				AND post_status IN ('publish', 'draft')
				LIMIT 100",
				'%' . $wpdb->esc_like( $pattern ) . '%'
			)
		);

		$refs = array();
		foreach ( $post_ids as $pid ) {
			$refs[] = 'post:' . $pid;
		}
		return $refs;
	}

	/**
	 * Add a plugin instance to the collection.
	 *
	 * @param string $instance_id   Stable instance identifier.
	 * @param string $source_plugin Source plugin family.
	 * @param string $instance_type Instance type classification.
	 * @param array  $config        Instance configuration.
	 * @param array  $references    Related entity stable IDs.
	 */
	private function add_instance( $instance_id, $source_plugin, $instance_type, $config, $references ) {
		$this->instances[ $instance_id ] = array(
			'instance_id'   => $instance_id,
			'source_plugin' => $source_plugin,
			'instance_type' => $instance_type,
			'config'        => $config,
			'references'    => $references,
		);
	}
}
