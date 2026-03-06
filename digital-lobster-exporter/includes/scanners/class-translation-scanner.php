<?php
/**
 * Translation Scanner Class
 *
 * Detects multilingual plugins and exports translation configurations,
 * language mappings, and content relationships for multilingual sites.
 *
 * Supports: WPML, Polylang, TranslatePress, Weglot
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Translation Scanner Class
 */
class Digital_Lobster_Exporter_Translation_Scanner {

	/**
	 * Detected multilingual plugin.
	 *
	 * @var string|null
	 */
	private $detected_plugin = null;

	/**
	 * Scan and collect translation data.
	 *
	 * @return array|null Translation data or null if no multilingual plugin detected.
	 */
	public function scan() {
		// Detect which multilingual plugin is active
		$this->detect_multilingual_plugin();

		// If no multilingual plugin detected, return null
		if ( ! $this->detected_plugin ) {
			return null;
		}

		$data = array(
			'plugin'                => $this->detected_plugin,
			'languages'             => array(),
			'default_language'      => '',
			'content_relationships' => array(),
			'string_translations'   => array(),
			'language_switcher'     => array(),
			'url_structure'         => array(),
		);

		// Collect data based on detected plugin
		switch ( $this->detected_plugin ) {
			case 'wpml':
				$data = $this->scan_wpml( $data );
				break;
			case 'polylang':
				$data = $this->scan_polylang( $data );
				break;
			case 'translatepress':
				$data = $this->scan_translatepress( $data );
				break;
			case 'weglot':
				$data = $this->scan_weglot( $data );
				break;
		}

		return $data;
	}

	/**
	 * Detect which multilingual plugin is active.
	 */
	private function detect_multilingual_plugin() {
		// Check for WPML
		if ( defined( 'ICL_SITEPRESS_VERSION' ) || class_exists( 'SitePress' ) ) {
			$this->detected_plugin = 'wpml';
			return;
		}

		// Check for Polylang
		if ( defined( 'POLYLANG_VERSION' ) || function_exists( 'pll_languages_list' ) ) {
			$this->detected_plugin = 'polylang';
			return;
		}

		// Check for TranslatePress
		if ( defined( 'TRP_PLUGIN_VERSION' ) || class_exists( 'TRP_Translate_Press' ) ) {
			$this->detected_plugin = 'translatepress';
			return;
		}

		// Check for Weglot
		if ( defined( 'WEGLOT_VERSION' ) || class_exists( 'Weglot\Client\Client' ) ) {
			$this->detected_plugin = 'weglot';
			return;
		}
	}

	/**
	 * Scan WPML configuration.
	 *
	 * @param array $data Base data array.
	 * @return array Updated data array.
	 */
	private function scan_wpml( $data ) {
		global $sitepress;

		if ( ! $sitepress ) {
			return $data;
		}

		// Get active languages
		$active_languages = $sitepress->get_active_languages();
		$default_language = $sitepress->get_default_language();

		$data['default_language'] = $default_language;

		// Collect language information
		foreach ( $active_languages as $lang_code => $language ) {
			$data['languages'][ $lang_code ] = array(
				'code'         => $lang_code,
				'name'         => isset( $language['display_name'] ) ? $language['display_name'] : $language['native_name'],
				'native_name'  => isset( $language['native_name'] ) ? $language['native_name'] : '',
				'locale'       => isset( $language['default_locale'] ) ? $language['default_locale'] : '',
				'is_default'   => ( $lang_code === $default_language ),
				'flag'         => isset( $language['country_flag_url'] ) ? $language['country_flag_url'] : '',
			);
		}

		// Get content relationships
		$data['content_relationships'] = $this->get_wpml_content_relationships();

		// Get string translations
		$data['string_translations'] = $this->get_wpml_string_translations();

		// Get language switcher configuration
		$data['language_switcher'] = $this->get_wpml_language_switcher_config();

		// Get URL structure
		$data['url_structure'] = $this->get_wpml_url_structure();

		return $data;
	}

	/**
	 * Get WPML content relationships.
	 *
	 * @return array Content translation relationships.
	 */
	private function get_wpml_content_relationships() {
		global $wpdb;

		$relationships = array();

		// Query translation relationships from icl_translations table
		$query = "
			SELECT 
				t.element_id,
				t.element_type,
				t.language_code,
				t.trid,
				t.source_language_code
			FROM {$wpdb->prefix}icl_translations t
			WHERE t.element_type LIKE 'post_%'
			ORDER BY t.trid, t.language_code
		";

		$results = $wpdb->get_results( $query );

		if ( $results ) {
			$grouped = array();
			
			foreach ( $results as $row ) {
				$trid = $row->trid;
				
				if ( ! isset( $grouped[ $trid ] ) ) {
					$grouped[ $trid ] = array();
				}
				
				$grouped[ $trid ][ $row->language_code ] = array(
					'post_id'              => $row->element_id,
					'element_type'         => $row->element_type,
					'source_language_code' => $row->source_language_code,
				);
			}

			$relationships = $grouped;
		}

		return $relationships;
	}

	/**
	 * Get WPML string translations.
	 *
	 * @return array String translations.
	 */
	private function get_wpml_string_translations() {
		global $wpdb;

		$strings = array();

		// Query string translations (limit to avoid huge exports)
		$query = "
			SELECT 
				s.name,
				s.value as original_value,
				s.context,
				st.value as translated_value,
				st.language
			FROM {$wpdb->prefix}icl_strings s
			LEFT JOIN {$wpdb->prefix}icl_string_translations st ON s.id = st.string_id
			WHERE s.context IN ('admin_texts_plugin', 'Widgets', 'Theme Options')
			LIMIT 500
		";

		$results = $wpdb->get_results( $query );

		if ( $results ) {
			foreach ( $results as $row ) {
				$key = $row->context . '::' . $row->name;
				
				if ( ! isset( $strings[ $key ] ) ) {
					$strings[ $key ] = array(
						'name'           => $row->name,
						'context'        => $row->context,
						'original_value' => $row->original_value,
						'translations'   => array(),
					);
				}
				
				if ( $row->language && $row->translated_value ) {
					$strings[ $key ]['translations'][ $row->language ] = $row->translated_value;
				}
			}
		}

		return array_values( $strings );
	}

	/**
	 * Get WPML language switcher configuration.
	 *
	 * @return array Language switcher settings.
	 */
	private function get_wpml_language_switcher_config() {
		$settings = get_option( 'icl_sitepress_settings', array() );

		return array(
			'skip_missing_translations' => isset( $settings['skip_missing'] ) ? $settings['skip_missing'] : false,
			'show_flags'                => isset( $settings['icl_lso_flags'] ) ? $settings['icl_lso_flags'] : false,
			'show_native_names'         => isset( $settings['icl_lso_native_lang'] ) ? $settings['icl_lso_native_lang'] : false,
			'show_display_names'        => isset( $settings['icl_lso_display_lang'] ) ? $settings['icl_lso_display_lang'] : false,
		);
	}

	/**
	 * Get WPML URL structure.
	 *
	 * @return array URL structure configuration.
	 */
	private function get_wpml_url_structure() {
		$settings = get_option( 'icl_sitepress_settings', array() );

		$language_negotiation = isset( $settings['language_negotiation_type'] ) ? $settings['language_negotiation_type'] : 1;

		$types = array(
			1 => 'directory',      // example.com/en/
			2 => 'domain',         // en.example.com
			3 => 'parameter',      // example.com?lang=en
		);

		return array(
			'type'                => isset( $types[ $language_negotiation ] ) ? $types[ $language_negotiation ] : 'directory',
			'directory_for_default_language' => isset( $settings['urls']['directory_for_default_language'] ) ? $settings['urls']['directory_for_default_language'] : false,
		);
	}

	/**
	 * Scan Polylang configuration.
	 *
	 * @param array $data Base data array.
	 * @return array Updated data array.
	 */
	private function scan_polylang( $data ) {
		if ( ! function_exists( 'pll_languages_list' ) ) {
			return $data;
		}

		// Get languages
		$languages = pll_languages_list( array( 'fields' => '' ) );
		$default_language = pll_default_language();

		$data['default_language'] = $default_language;

		// Collect language information
		foreach ( $languages as $language ) {
			$lang_code = $language->slug;
			
			$data['languages'][ $lang_code ] = array(
				'code'        => $lang_code,
				'name'        => $language->name,
				'locale'      => $language->locale,
				'is_default'  => ( $lang_code === $default_language ),
				'is_rtl'      => (bool) $language->is_rtl,
				'flag'        => $language->flag_url,
				'home_url'    => $language->home_url,
			);
		}

		// Get content relationships
		$data['content_relationships'] = $this->get_polylang_content_relationships();

		// Get string translations
		$data['string_translations'] = $this->get_polylang_string_translations();

		// Get language switcher configuration
		$data['language_switcher'] = $this->get_polylang_language_switcher_config();

		// Get URL structure
		$data['url_structure'] = $this->get_polylang_url_structure();

		return $data;
	}

	/**
	 * Get Polylang content relationships.
	 *
	 * @return array Content translation relationships.
	 */
	private function get_polylang_content_relationships() {
		if ( ! function_exists( 'pll_get_post_translations' ) ) {
			return array();
		}

		global $wpdb;

		$relationships = array();

		// Get all posts with translations
		$query = "
			SELECT DISTINCT tr.object_id as post_id
			FROM {$wpdb->term_relationships} tr
			INNER JOIN {$wpdb->term_taxonomy} tt ON tr.term_taxonomy_id = tt.term_taxonomy_id
			WHERE tt.taxonomy = 'language'
			LIMIT 1000
		";

		$post_ids = $wpdb->get_col( $query );

		foreach ( $post_ids as $post_id ) {
			$translations = pll_get_post_translations( $post_id );
			
			if ( $translations && count( $translations ) > 1 ) {
				// Create a unique key for this translation group
				$group_key = md5( serialize( array_values( $translations ) ) );
				
				if ( ! isset( $relationships[ $group_key ] ) ) {
					$relationships[ $group_key ] = array();
					
					foreach ( $translations as $lang => $translated_post_id ) {
						$relationships[ $group_key ][ $lang ] = array(
							'post_id' => $translated_post_id,
						);
					}
				}
			}
		}

		return $relationships;
	}

	/**
	 * Get Polylang string translations.
	 *
	 * @return array String translations.
	 */
	private function get_polylang_string_translations() {
		if ( ! function_exists( 'pll_languages_list' ) ) {
			return array();
		}

		global $wpdb;

		$strings = array();

		// Query string translations from Polylang's strings table
		$table_name = $wpdb->prefix . 'polylang_strings';
		
		if ( $wpdb->get_var( "SHOW TABLES LIKE '{$table_name}'" ) !== $table_name ) {
			return array();
		}

		$query = "
			SELECT 
				name,
				context,
				string as original_value
			FROM {$table_name}
			LIMIT 500
		";

		$results = $wpdb->get_results( $query );

		if ( $results ) {
			foreach ( $results as $row ) {
				$strings[] = array(
					'name'           => $row->name,
					'context'        => $row->context,
					'original_value' => $row->original_value,
					'translations'   => array(), // Polylang stores translations differently
				);
			}
		}

		return $strings;
	}

	/**
	 * Get Polylang language switcher configuration.
	 *
	 * @return array Language switcher settings.
	 */
	private function get_polylang_language_switcher_config() {
		$options = get_option( 'polylang', array() );

		return array(
			'hide_default'     => isset( $options['hide_default'] ) ? $options['hide_default'] : false,
			'force_lang'       => isset( $options['force_lang'] ) ? $options['force_lang'] : 0,
			'hide_current'     => isset( $options['hide_current'] ) ? $options['hide_current'] : false,
			'dropdown'         => isset( $options['dropdown'] ) ? $options['dropdown'] : false,
			'show_flags'       => isset( $options['show_flags'] ) ? $options['show_flags'] : true,
			'show_names'       => isset( $options['show_names'] ) ? $options['show_names'] : false,
		);
	}

	/**
	 * Get Polylang URL structure.
	 *
	 * @return array URL structure configuration.
	 */
	private function get_polylang_url_structure() {
		$options = get_option( 'polylang', array() );

		$force_lang = isset( $options['force_lang'] ) ? $options['force_lang'] : 0;

		$types = array(
			0 => 'none',           // No language information in URL
			1 => 'directory',      // example.com/en/
			2 => 'subdomain',      // en.example.com
			3 => 'domain',         // example.en
		);

		return array(
			'type'                           => isset( $types[ $force_lang ] ) ? $types[ $force_lang ] : 'none',
			'hide_default'                   => isset( $options['hide_default'] ) ? $options['hide_default'] : false,
			'rewrite'                        => isset( $options['rewrite'] ) ? $options['rewrite'] : 1,
		);
	}

	/**
	 * Scan TranslatePress configuration.
	 *
	 * @param array $data Base data array.
	 * @return array Updated data array.
	 */
	private function scan_translatepress( $data ) {
		$settings = get_option( 'trp_settings', array() );

		if ( empty( $settings ) ) {
			return $data;
		}

		// Get default language
		$default_language = isset( $settings['default-language'] ) ? $settings['default-language'] : '';
		$data['default_language'] = $default_language;

		// Get publish languages
		$publish_languages = isset( $settings['publish-languages'] ) ? $settings['publish-languages'] : array();

		// Get all languages (published + default)
		$all_languages = array_unique( array_merge( array( $default_language ), $publish_languages ) );

		// Collect language information
		foreach ( $all_languages as $lang_code ) {
			if ( empty( $lang_code ) ) {
				continue;
			}

			$data['languages'][ $lang_code ] = array(
				'code'       => $lang_code,
				'name'       => $this->get_language_name( $lang_code ),
				'is_default' => ( $lang_code === $default_language ),
			);
		}

		// TranslatePress doesn't have traditional content relationships
		// It translates on-the-fly and stores in custom tables
		$data['content_relationships'] = array();

		// Get string translations from TranslatePress tables
		$data['string_translations'] = $this->get_translatepress_string_translations( $all_languages );

		// Get language switcher configuration
		$data['language_switcher'] = array(
			'shortcode_enabled'  => isset( $settings['shortcode-enabled'] ) ? $settings['shortcode-enabled'] : 'yes',
			'floater_enabled'    => isset( $settings['trp_advanced_settings']['enable_language_switcher'] ) ? $settings['trp_advanced_settings']['enable_language_switcher'] : 'yes',
			'flags_in_menu'      => isset( $settings['add-flags-to-menu'] ) ? $settings['add-flags-to-menu'] : 'yes',
		);

		// Get URL structure
		$data['url_structure'] = array(
			'type'                           => 'directory',
			'add_subdirectory_to_default_language' => isset( $settings['add-subdirectory-to-default-language'] ) ? $settings['add-subdirectory-to-default-language'] : 'no',
			'force_language_in_custom_links' => isset( $settings['force-language-to-custom-links'] ) ? $settings['force-language-to-custom-links'] : 'no',
		);

		return $data;
	}

	/**
	 * Get TranslatePress string translations.
	 *
	 * @param array $languages List of language codes.
	 * @return array String translations.
	 */
	private function get_translatepress_string_translations( $languages ) {
		global $wpdb;

		$strings = array();

		foreach ( $languages as $lang_code ) {
			if ( empty( $lang_code ) ) {
				continue;
			}

			$table_name = $wpdb->prefix . 'trp_dictionary_' . strtolower( str_replace( '-', '_', $lang_code ) );

			// Check if table exists
			if ( $wpdb->get_var( "SHOW TABLES LIKE '{$table_name}'" ) !== $table_name ) {
				continue;
			}

			// Get sample translations (limit to avoid huge exports)
			$query = $wpdb->prepare(
				"SELECT original, translated, status FROM {$table_name} WHERE status = %d LIMIT 500",
				2 // Status 2 = translated
			);

			$results = $wpdb->get_results( $query );

			if ( $results ) {
				foreach ( $results as $row ) {
					$key = md5( $row->original );
					
					if ( ! isset( $strings[ $key ] ) ) {
						$strings[ $key ] = array(
							'original_value' => $row->original,
							'translations'   => array(),
						);
					}
					
					$strings[ $key ]['translations'][ $lang_code ] = $row->translated;
				}
			}
		}

		return array_values( $strings );
	}

	/**
	 * Scan Weglot configuration.
	 *
	 * @param array $data Base data array.
	 * @return array Updated data array.
	 */
	private function scan_weglot( $data ) {
		$options = get_option( 'weglot_options', array() );

		if ( empty( $options ) ) {
			return $data;
		}

		// Get original language
		$original_language = isset( $options['language_from'] ) ? $options['language_from'] : '';
		$data['default_language'] = $original_language;

		// Get destination languages
		$destination_languages = isset( $options['destination_language'] ) ? $options['destination_language'] : array();

		// Add original language
		if ( $original_language ) {
			$data['languages'][ $original_language ] = array(
				'code'       => $original_language,
				'name'       => $this->get_language_name( $original_language ),
				'is_default' => true,
			);
		}

		// Add destination languages
		foreach ( $destination_languages as $lang_code ) {
			$data['languages'][ $lang_code ] = array(
				'code'       => $lang_code,
				'name'       => $this->get_language_name( $lang_code ),
				'is_default' => false,
			);
		}

		// Weglot is a cloud-based service, no local content relationships
		$data['content_relationships'] = array();
		$data['string_translations'] = array();

		// Get language switcher configuration
		$data['language_switcher'] = array(
			'is_dropdown'           => isset( $options['is_dropdown'] ) ? $options['is_dropdown'] : false,
			'with_flags'            => isset( $options['with_flags'] ) ? $options['with_flags'] : true,
			'with_name'             => isset( $options['with_name'] ) ? $options['with_name'] : true,
			'flag_css'              => isset( $options['flag_css'] ) ? $options['flag_css'] : '',
		);

		// Get URL structure
		$data['url_structure'] = array(
			'type'                  => 'directory',
			'exclude_urls'          => isset( $options['exclude_urls'] ) ? $options['exclude_urls'] : array(),
			'auto_redirect'         => isset( $options['auto_redirect'] ) ? $options['auto_redirect'] : false,
		);

		return $data;
	}

	/**
	 * Get language name from code.
	 *
	 * @param string $code Language code.
	 * @return string Language name.
	 */
	private function get_language_name( $code ) {
		// Common language codes to names mapping
		$languages = array(
			'en'    => 'English',
			'en_US' => 'English (United States)',
			'en_GB' => 'English (United Kingdom)',
			'es'    => 'Spanish',
			'es_ES' => 'Spanish (Spain)',
			'fr'    => 'French',
			'fr_FR' => 'French (France)',
			'de'    => 'German',
			'de_DE' => 'German (Germany)',
			'it'    => 'Italian',
			'it_IT' => 'Italian (Italy)',
			'pt'    => 'Portuguese',
			'pt_BR' => 'Portuguese (Brazil)',
			'pt_PT' => 'Portuguese (Portugal)',
			'nl'    => 'Dutch',
			'nl_NL' => 'Dutch (Netherlands)',
			'ru'    => 'Russian',
			'ru_RU' => 'Russian (Russia)',
			'zh'    => 'Chinese',
			'zh_CN' => 'Chinese (Simplified)',
			'ja'    => 'Japanese',
			'ja_JP' => 'Japanese (Japan)',
			'ar'    => 'Arabic',
			'ar_AR' => 'Arabic',
		);

		return isset( $languages[ $code ] ) ? $languages[ $code ] : $code;
	}

	/**
	 * Export translation data to JSON file.
	 *
	 * @param string $export_dir Export directory path.
	 */
	public function export( $export_dir ) {
		$data = $this->scan();

		// If no multilingual plugin detected, don't create the file
		if ( ! $data ) {
			return;
		}

		$file_path = trailingslashit( $export_dir ) . 'translations.json';

		$json_data = wp_json_encode( $data, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES );

		if ( $json_data ) {
			file_put_contents( $file_path, $json_data );
		}
	}
}
