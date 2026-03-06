<?php
/**
 * Forms Scanner
 *
 * Detects and exports form configurations from common WordPress form plugins.
 * Supports Contact Form 7, Gravity Forms, WPForms, Ninja Forms, and Formidable Forms.
 *
 * @package Digital_Lobster_Exporter
 */

if (!defined('ABSPATH')) {
    exit;
}

class Digital_Lobster_Forms_Scanner {
    
    /**
     * Forms data collected during scan
     *
     * @var array
     */
    private $forms_data = array();
    
    /**
     * Scan and export form configurations
     *
     * @return array Forms configuration data
     */
    public function scan() {
        $forms_data = array(
            'schema_version' => 1,
            'detected_plugins' => array(),
            'forms' => array(),
            'forms_in_content' => array(),
            'summary' => array(
                'total_forms' => 0,
                'forms_by_plugin' => array()
            )
        );
        
        // Detect and export Contact Form 7
        if ($this->is_plugin_active('contact-form-7/wp-contact-form-7.php')) {
            $forms_data['detected_plugins'][] = 'contact-form-7';
            $cf7_forms = $this->export_contact_form_7();
            if (!empty($cf7_forms)) {
                $forms_data['forms']['contact_form_7'] = $cf7_forms;
                $forms_data['summary']['forms_by_plugin']['contact_form_7'] = count($cf7_forms);
            }
        }
        
        // Detect and export Gravity Forms
        if ($this->is_plugin_active('gravityforms/gravityforms.php')) {
            $forms_data['detected_plugins'][] = 'gravityforms';
            $gf_forms = $this->export_gravity_forms();
            if (!empty($gf_forms)) {
                $forms_data['forms']['gravity_forms'] = $gf_forms;
                $forms_data['summary']['forms_by_plugin']['gravity_forms'] = count($gf_forms);
            }
        }
        
        // Detect and export WPForms
        if ($this->is_plugin_active('wpforms-lite/wpforms.php') || $this->is_plugin_active('wpforms/wpforms.php')) {
            $forms_data['detected_plugins'][] = 'wpforms';
            $wpf_forms = $this->export_wpforms();
            if (!empty($wpf_forms)) {
                $forms_data['forms']['wpforms'] = $wpf_forms;
                $forms_data['summary']['forms_by_plugin']['wpforms'] = count($wpf_forms);
            }
        }
        
        // Detect and export Ninja Forms
        if ($this->is_plugin_active('ninja-forms/ninja-forms.php')) {
            $forms_data['detected_plugins'][] = 'ninja-forms';
            $nf_forms = $this->export_ninja_forms();
            if (!empty($nf_forms)) {
                $forms_data['forms']['ninja_forms'] = $nf_forms;
                $forms_data['summary']['forms_by_plugin']['ninja_forms'] = count($nf_forms);
            }
        }
        
        // Detect and export Formidable Forms
        if ($this->is_plugin_active('formidable/formidable.php')) {
            $forms_data['detected_plugins'][] = 'formidable';
            $frm_forms = $this->export_formidable_forms();
            if (!empty($frm_forms)) {
                $forms_data['forms']['formidable_forms'] = $frm_forms;
                $forms_data['summary']['forms_by_plugin']['formidable_forms'] = count($frm_forms);
            }
        }
        
        // Calculate total forms
        $forms_data['summary']['total_forms'] = array_sum($forms_data['summary']['forms_by_plugin']);
        
        // Scan content for embedded forms
        $forms_data['forms_in_content'] = $this->scan_content_for_forms();
        
        // Store for export
        $this->forms_data = $forms_data;
        
        return $forms_data;
    }
    
    /**
     * Export forms data to JSON file
     *
     * @param string $export_dir Export directory path
     * @return bool Success status
     */
    public function export($export_dir) {
        // Run scan if not already done
        if (empty($this->forms_data)) {
            $this->scan();
        }
        
        // Create export directory if it doesn't exist
        if (!file_exists($export_dir)) {
            wp_mkdir_p($export_dir);
        }
        
        // Export forms_config.json
        $json_file = trailingslashit($export_dir) . 'forms_config.json';
        $json_content = wp_json_encode($this->forms_data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
        
        if ($json_content === false) {
            error_log('Digital Lobster Exporter: Failed to encode forms data to JSON');
            return false;
        }
        
        $result = file_put_contents($json_file, $json_content);
        
        if ($result === false) {
            error_log('Digital Lobster Exporter: Failed to write forms_config.json');
            return false;
        }
        
        return true;
    }
    
    /**
     * Export Contact Form 7 configurations
     *
     * @return array CF7 forms data
     */
    private function export_contact_form_7() {
        if (!class_exists('WPCF7_ContactForm')) {
            return array();
        }
        
        $forms = array();
        $cf7_posts = get_posts(array(
            'post_type' => 'wpcf7_contact_form',
            'posts_per_page' => -1,
            'post_status' => 'publish'
        ));
        
        foreach ($cf7_posts as $post) {
            $contact_form = WPCF7_ContactForm::get_instance($post->ID);
            if (!$contact_form) {
                continue;
            }
            
            $properties = $contact_form->get_properties();
            $mail = isset($properties['mail']) ? $properties['mail'] : array();
            $mail_2 = isset($properties['mail_2']) ? $properties['mail_2'] : array();
            
            $form_data = array(
                'id' => $post->ID,
                'title' => $post->post_title,
                'slug' => $post->post_name,
                'form_template' => isset($properties['form']) ? $properties['form'] : '',
                'fields' => $this->parse_cf7_fields(isset($properties['form']) ? $properties['form'] : ''),
                'mail_settings' => array(
                    'active' => !empty($mail['active']),
                    'recipient' => isset($mail['recipient']) ? $mail['recipient'] : '',
                    'sender' => isset($mail['sender']) ? $mail['sender'] : '',
                    'subject' => isset($mail['subject']) ? $mail['subject'] : '',
                    'body' => isset($mail['body']) ? $mail['body'] : '',
                    'additional_headers' => isset($mail['additional_headers']) ? $mail['additional_headers'] : ''
                ),
                'mail_2_settings' => array(
                    'active' => !empty($mail_2['active']),
                    'recipient' => isset($mail_2['recipient']) ? $mail_2['recipient'] : '',
                    'subject' => isset($mail_2['subject']) ? $mail_2['subject'] : ''
                ),
                'messages' => isset($properties['messages']) ? $properties['messages'] : array(),
                'shortcode' => '[contact-form-7 id="' . $post->ID . '" title="' . esc_attr($post->post_title) . '"]'
            );
            
            $forms[] = $form_data;
        }
        
        return $forms;
    }
    
    /**
     * Parse Contact Form 7 field tags
     *
     * @param string $form_template CF7 form template
     * @return array Parsed fields
     */
    private function parse_cf7_fields($form_template) {
        $fields = array();
        
        // Match CF7 field tags like [text* your-name] or [email* your-email]
        preg_match_all('/\[([^\]]+)\]/', $form_template, $matches);
        
        if (!empty($matches[1])) {
            foreach ($matches[1] as $tag) {
                $parts = preg_split('/\s+/', $tag);
                if (empty($parts)) {
                    continue;
                }
                
                $type = $parts[0];
                $required = false;
                
                // Check if required (marked with *)
                if (substr($type, -1) === '*') {
                    $required = true;
                    $type = substr($type, 0, -1);
                }
                
                $name = isset($parts[1]) ? $parts[1] : '';
                
                // Skip submit buttons
                if ($type === 'submit') {
                    continue;
                }
                
                $field = array(
                    'type' => $type,
                    'name' => $name,
                    'required' => $required,
                    'options' => array_slice($parts, 2)
                );
                
                $fields[] = $field;
            }
        }
        
        return $fields;
    }
    
    /**
     * Export Gravity Forms configurations
     *
     * @return array Gravity Forms data
     */
    private function export_gravity_forms() {
        if (!class_exists('GFAPI')) {
            return array();
        }
        
        $forms = array();
        $gf_forms = GFAPI::get_forms();
        
        foreach ($gf_forms as $form) {
            $form_data = array(
                'id' => $form['id'],
                'title' => $form['title'],
                'description' => isset($form['description']) ? $form['description'] : '',
                'fields' => array(),
                'notifications' => isset($form['notifications']) ? $form['notifications'] : array(),
                'confirmations' => isset($form['confirmations']) ? $form['confirmations'] : array(),
                'is_active' => isset($form['is_active']) ? $form['is_active'] : true,
                'shortcode' => '[gravityform id="' . $form['id'] . '" title="false"]'
            );
            
            // Export fields
            if (!empty($form['fields'])) {
                foreach ($form['fields'] as $field) {
                    $field_data = array(
                        'id' => $field->id,
                        'type' => $field->type,
                        'label' => $field->label,
                        'description' => isset($field->description) ? $field->description : '',
                        'is_required' => !empty($field->isRequired),
                        'placeholder' => isset($field->placeholder) ? $field->placeholder : '',
                        'default_value' => isset($field->defaultValue) ? $field->defaultValue : '',
                        'css_class' => isset($field->cssClass) ? $field->cssClass : ''
                    );
                    
                    // Add choices for select/radio/checkbox fields
                    if (isset($field->choices) && !empty($field->choices)) {
                        $field_data['choices'] = $field->choices;
                    }
                    
                    // Add validation rules
                    if (isset($field->validation)) {
                        $field_data['validation'] = $field->validation;
                    }
                    
                    $form_data['fields'][] = $field_data;
                }
            }
            
            $forms[] = $form_data;
        }
        
        return $forms;
    }
    
    /**
     * Export WPForms configurations
     *
     * @return array WPForms data
     */
    private function export_wpforms() {
        $forms = array();
        $wpf_posts = get_posts(array(
            'post_type' => 'wpforms',
            'posts_per_page' => -1,
            'post_status' => 'publish'
        ));
        
        foreach ($wpf_posts as $post) {
            $form_data_raw = get_post_meta($post->ID, 'wpforms', true);
            
            if (empty($form_data_raw)) {
                continue;
            }
            
            $form_data = maybe_unserialize($form_data_raw);
            
            $export_data = array(
                'id' => $post->ID,
                'title' => $post->post_title,
                'description' => isset($form_data['settings']['form_desc']) ? $form_data['settings']['form_desc'] : '',
                'fields' => array(),
                'settings' => isset($form_data['settings']) ? $form_data['settings'] : array(),
                'notifications' => isset($form_data['settings']['notifications']) ? $form_data['settings']['notifications'] : array(),
                'shortcode' => '[wpforms id="' . $post->ID . '"]'
            );
            
            // Export fields
            if (!empty($form_data['fields'])) {
                foreach ($form_data['fields'] as $field_id => $field) {
                    $field_export = array(
                        'id' => $field_id,
                        'type' => isset($field['type']) ? $field['type'] : '',
                        'label' => isset($field['label']) ? $field['label'] : '',
                        'description' => isset($field['description']) ? $field['description'] : '',
                        'required' => !empty($field['required']),
                        'placeholder' => isset($field['placeholder']) ? $field['placeholder'] : '',
                        'default_value' => isset($field['default_value']) ? $field['default_value'] : '',
                        'css' => isset($field['css']) ? $field['css'] : ''
                    );
                    
                    // Add choices for select/radio/checkbox fields
                    if (isset($field['choices']) && !empty($field['choices'])) {
                        $field_export['choices'] = $field['choices'];
                    }
                    
                    // Add validation
                    if (isset($field['validation'])) {
                        $field_export['validation'] = $field['validation'];
                    }
                    
                    $export_data['fields'][] = $field_export;
                }
            }
            
            $forms[] = $export_data;
        }
        
        return $forms;
    }
    
    /**
     * Export Ninja Forms configurations
     *
     * @return array Ninja Forms data
     */
    private function export_ninja_forms() {
        if (!class_exists('Ninja_Forms')) {
            return array();
        }
        
        $forms = array();
        
        // Get all Ninja Forms
        $nf_forms = Ninja_Forms()->form()->get_forms();
        
        foreach ($nf_forms as $form) {
            $form_id = $form->get_id();
            $form_settings = $form->get_settings();
            
            $form_data = array(
                'id' => $form_id,
                'title' => $form->get_setting('title'),
                'fields' => array(),
                'actions' => array(),
                'settings' => $form_settings,
                'shortcode' => '[ninja_form id="' . $form_id . '"]'
            );
            
            // Export fields
            $fields = Ninja_Forms()->form($form_id)->get_fields();
            foreach ($fields as $field) {
                $field_settings = $field->get_settings();
                
                $field_data = array(
                    'id' => $field->get_id(),
                    'type' => $field->get_setting('type'),
                    'label' => $field->get_setting('label'),
                    'key' => $field->get_setting('key'),
                    'required' => !empty($field->get_setting('required')),
                    'placeholder' => $field->get_setting('placeholder'),
                    'default_value' => $field->get_setting('default'),
                    'description' => $field->get_setting('desc_text'),
                    'settings' => $field_settings
                );
                
                // Add options for select/radio/checkbox fields
                $options = $field->get_setting('options');
                if (!empty($options)) {
                    $field_data['options'] = $options;
                }
                
                $form_data['fields'][] = $field_data;
            }
            
            // Export actions (email notifications, etc.)
            $actions = Ninja_Forms()->form($form_id)->get_actions();
            foreach ($actions as $action) {
                $action_settings = $action->get_settings();
                
                $action_data = array(
                    'id' => $action->get_id(),
                    'type' => $action->get_setting('type'),
                    'active' => !empty($action->get_setting('active')),
                    'settings' => $action_settings
                );
                
                $form_data['actions'][] = $action_data;
            }
            
            $forms[] = $form_data;
        }
        
        return $forms;
    }
    
    /**
     * Export Formidable Forms configurations
     *
     * @return array Formidable Forms data
     */
    private function export_formidable_forms() {
        if (!class_exists('FrmForm')) {
            return array();
        }
        
        $forms = array();
        $frm_forms = FrmForm::get_published_forms();
        
        foreach ($frm_forms as $form) {
            $form_data = array(
                'id' => $form->id,
                'key' => $form->form_key,
                'title' => $form->name,
                'description' => $form->description,
                'fields' => array(),
                'actions' => array(),
                'options' => maybe_unserialize($form->options),
                'shortcode' => '[formidable id="' . $form->id . '"]'
            );
            
            // Export fields
            if (class_exists('FrmField')) {
                $fields = FrmField::get_all_for_form($form->id);
                
                foreach ($fields as $field) {
                    $field_data = array(
                        'id' => $field->id,
                        'key' => $field->field_key,
                        'type' => $field->type,
                        'name' => $field->name,
                        'description' => $field->description,
                        'required' => !empty($field->required),
                        'placeholder' => $field->placeholder,
                        'default_value' => $field->default_value,
                        'options' => maybe_unserialize($field->options),
                        'field_options' => maybe_unserialize($field->field_options)
                    );
                    
                    $form_data['fields'][] = $field_data;
                }
            }
            
            // Export actions (email notifications, etc.)
            if (class_exists('FrmFormAction')) {
                $actions = FrmFormAction::get_action_for_form($form->id);
                
                foreach ($actions as $action) {
                    $action_data = array(
                        'id' => $action->ID,
                        'type' => $action->post_excerpt,
                        'settings' => maybe_unserialize($action->post_content)
                    );
                    
                    $form_data['actions'][] = $action_data;
                }
            }
            
            $forms[] = $form_data;
        }
        
        return $forms;
    }
    
    /**
     * Scan content for embedded forms
     *
     * @return array Forms found in content
     */
    private function scan_content_for_forms() {
        $forms_in_content = array();
        
        // Get sample content (posts, pages, custom post types)
        $post_types = get_post_types(array('public' => true), 'names');
        
        $posts = get_posts(array(
            'post_type' => $post_types,
            'posts_per_page' => 100,
            'post_status' => 'publish'
        ));
        
        foreach ($posts as $post) {
            $content = $post->post_content;
            $found_forms = array();
            
            // Check for Contact Form 7 shortcodes
            if (preg_match_all('/\[contact-form-7[^\]]*id=["\']?(\d+)["\']?[^\]]*\]/', $content, $matches)) {
                foreach ($matches[1] as $form_id) {
                    $found_forms[] = array(
                        'plugin' => 'contact_form_7',
                        'form_id' => $form_id,
                        'shortcode' => $matches[0][0]
                    );
                }
            }
            
            // Check for Gravity Forms shortcodes
            if (preg_match_all('/\[gravityform[^\]]*id=["\']?(\d+)["\']?[^\]]*\]/', $content, $matches)) {
                foreach ($matches[1] as $form_id) {
                    $found_forms[] = array(
                        'plugin' => 'gravity_forms',
                        'form_id' => $form_id,
                        'shortcode' => $matches[0][0]
                    );
                }
            }
            
            // Check for WPForms shortcodes
            if (preg_match_all('/\[wpforms[^\]]*id=["\']?(\d+)["\']?[^\]]*\]/', $content, $matches)) {
                foreach ($matches[1] as $form_id) {
                    $found_forms[] = array(
                        'plugin' => 'wpforms',
                        'form_id' => $form_id,
                        'shortcode' => $matches[0][0]
                    );
                }
            }
            
            // Check for Ninja Forms shortcodes
            if (preg_match_all('/\[ninja_form[^\]]*id=["\']?(\d+)["\']?[^\]]*\]/', $content, $matches)) {
                foreach ($matches[1] as $form_id) {
                    $found_forms[] = array(
                        'plugin' => 'ninja_forms',
                        'form_id' => $form_id,
                        'shortcode' => $matches[0][0]
                    );
                }
            }
            
            // Check for Formidable Forms shortcodes
            if (preg_match_all('/\[formidable[^\]]*id=["\']?(\d+)["\']?[^\]]*\]/', $content, $matches)) {
                foreach ($matches[1] as $form_id) {
                    $found_forms[] = array(
                        'plugin' => 'formidable_forms',
                        'form_id' => $form_id,
                        'shortcode' => $matches[0][0]
                    );
                }
            }
            
            // Check for form blocks in Gutenberg content
            if (has_blocks($content)) {
                $blocks = parse_blocks($content);
                $this->scan_blocks_for_forms($blocks, $found_forms);
            }
            
            if (!empty($found_forms)) {
                $forms_in_content[] = array(
                    'post_id' => $post->ID,
                    'post_type' => $post->post_type,
                    'post_title' => $post->post_title,
                    'post_url' => get_permalink($post->ID),
                    'forms' => $found_forms
                );
            }
        }
        
        return $forms_in_content;
    }
    
    /**
     * Recursively scan blocks for form references
     *
     * @param array $blocks Parsed blocks
     * @param array &$found_forms Reference to found forms array
     */
    private function scan_blocks_for_forms($blocks, &$found_forms) {
        foreach ($blocks as $block) {
            // Check for form blocks
            if (isset($block['blockName'])) {
                // Contact Form 7 block
                if ($block['blockName'] === 'contact-form-7/contact-form-selector' && isset($block['attrs']['id'])) {
                    $found_forms[] = array(
                        'plugin' => 'contact_form_7',
                        'form_id' => $block['attrs']['id'],
                        'block' => $block['blockName']
                    );
                }
                
                // Gravity Forms block
                if ($block['blockName'] === 'gravityforms/form' && isset($block['attrs']['formId'])) {
                    $found_forms[] = array(
                        'plugin' => 'gravity_forms',
                        'form_id' => $block['attrs']['formId'],
                        'block' => $block['blockName']
                    );
                }
                
                // WPForms block
                if ($block['blockName'] === 'wpforms/form-selector' && isset($block['attrs']['formId'])) {
                    $found_forms[] = array(
                        'plugin' => 'wpforms',
                        'form_id' => $block['attrs']['formId'],
                        'block' => $block['blockName']
                    );
                }
                
                // Ninja Forms block
                if ($block['blockName'] === 'ninja-forms/form' && isset($block['attrs']['formID'])) {
                    $found_forms[] = array(
                        'plugin' => 'ninja_forms',
                        'form_id' => $block['attrs']['formID'],
                        'block' => $block['blockName']
                    );
                }
                
                // Formidable Forms block
                if ($block['blockName'] === 'formidable/simple-form' && isset($block['attrs']['formId'])) {
                    $found_forms[] = array(
                        'plugin' => 'formidable_forms',
                        'form_id' => $block['attrs']['formId'],
                        'block' => $block['blockName']
                    );
                }
            }
            
            // Recursively check inner blocks
            if (!empty($block['innerBlocks'])) {
                $this->scan_blocks_for_forms($block['innerBlocks'], $found_forms);
            }
        }
    }
    
    /**
     * Check if a plugin is active
     *
     * @param string $plugin Plugin path
     * @return bool
     */
    private function is_plugin_active($plugin) {
        if (!function_exists('is_plugin_active')) {
            include_once(ABSPATH . 'wp-admin/includes/plugin.php');
        }
        return is_plugin_active($plugin);
    }
}
