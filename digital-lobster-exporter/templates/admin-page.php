<?php
/**
 * Admin Page Template
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

$defaults = array(
	'max_posts'                => 100,
	'max_pages'                => 50,
	'max_per_custom_post_type' => 50,
	'include_html_snapshots'   => false,
	'batch_size'               => 50,
	'cleanup_after_hours'      => 24,
);
$settings = get_option( 'digital_lobster_settings', $defaults );
$settings = wp_parse_args( $settings, $defaults );
?>

<div class="wrap digital-lobster-exporter-wrap">
	<h1><?php echo esc_html( 'AI Website Exporter' ); ?></h1>
	
	<div class="digital-lobster-exporter-container">
		<div class="digital-lobster-exporter-header">
			<p class="digital-lobster-exporter-tagline">
				<?php echo esc_html( 'Collects everything needed to recreate your website in a modern Python architecture using AI Agents' ); ?>
			</p>
			
			<p class="digital-lobster-exporter-description">
				<?php
				echo esc_html(
					'This plugin will scan your WordPress site and export all necessary data including content, theme files, plugin configurations, and database schema. All data is packaged into a downloadable ZIP file. No user data, passwords, or API keys are included in the export.'
				);
				?>
			</p>
		</div>

		<!-- Collapsible Settings Section -->
		<div class="digital-lobster-exporter-settings-section">
			<button type="button" id="digital-lobster-settings-toggle" class="button" style="margin-bottom: 10px;">
				<?php echo esc_html( 'Settings ▼' ); ?>
			</button>

			<div id="digital-lobster-settings-panel" style="display: none; background: #fff; border: 1px solid #ccd0d4; padding: 15px; margin-bottom: 20px;">
				<table class="form-table" role="presentation">
					<tr>
						<th scope="row">
							<label for="digital-lobster-max-posts"><?php echo esc_html( 'Max Posts' ); ?></label>
						</th>
						<td>
							<input type="number" id="digital-lobster-max-posts" value="<?php echo esc_attr( $settings['max_posts'] ); ?>" min="1" max="1000" class="small-text" />
							<p class="description"><?php echo esc_html( 'Maximum number of posts to export (default: 100)' ); ?></p>
						</td>
					</tr>
					<tr>
						<th scope="row">
							<label for="digital-lobster-max-pages"><?php echo esc_html( 'Max Pages' ); ?></label>
						</th>
						<td>
							<input type="number" id="digital-lobster-max-pages" value="<?php echo esc_attr( $settings['max_pages'] ); ?>" min="1" max="1000" class="small-text" />
							<p class="description"><?php echo esc_html( 'Maximum number of pages to export (default: 50)' ); ?></p>
						</td>
					</tr>
					<tr>
						<th scope="row">
							<label for="digital-lobster-max-cpt"><?php echo esc_html( 'Max per Custom Post Type' ); ?></label>
						</th>
						<td>
							<input type="number" id="digital-lobster-max-cpt" value="<?php echo esc_attr( $settings['max_per_custom_post_type'] ); ?>" min="1" max="1000" class="small-text" />
							<p class="description"><?php echo esc_html( 'Maximum number of items to export per custom post type (default: 50)' ); ?></p>
						</td>
					</tr>
					<tr>
						<th scope="row">
							<label for="digital-lobster-html-snapshots"><?php echo esc_html( 'Include HTML Snapshots' ); ?></label>
						</th>
						<td>
							<label>
								<input type="checkbox" id="digital-lobster-html-snapshots" value="1" <?php checked( $settings['include_html_snapshots'], true ); ?> />
								<?php echo esc_html( 'Generate HTML snapshots of content' ); ?>
							</label>
							<p class="description"><?php echo esc_html( 'Enable to capture rendered HTML for each content item (default: off)' ); ?></p>
						</td>
					</tr>
					<tr>
						<th scope="row">
							<label for="digital-lobster-batch-size"><?php echo esc_html( 'Batch Size' ); ?></label>
						</th>
						<td>
							<input type="number" id="digital-lobster-batch-size" value="<?php echo esc_attr( $settings['batch_size'] ); ?>" min="10" max="500" class="small-text" />
							<p class="description"><?php echo esc_html( 'Batch size for processing large datasets (default: 50)' ); ?></p>
						</td>
					</tr>
					<tr>
						<th scope="row">
							<label for="digital-lobster-cleanup-hours"><?php echo esc_html( 'Cleanup After (Hours)' ); ?></label>
						</th>
						<td>
							<input type="number" id="digital-lobster-cleanup-hours" value="<?php echo esc_attr( $settings['cleanup_after_hours'] ); ?>" min="1" max="168" class="small-text" />
							<p class="description"><?php echo esc_html( 'Automatically delete old artifacts after this many hours (default: 24)' ); ?></p>
						</td>
					</tr>
				</table>

				<p>
					<button type="button" id="digital-lobster-save-settings-btn" class="button button-primary">
						<?php echo esc_html( 'Save Settings' ); ?>
					</button>
					<span id="digital-lobster-settings-status" style="margin-left: 10px;"></span>
				</p>
			</div>
		</div>

		<div class="digital-lobster-exporter-actions">
			<button id="digital-lobster-migrate-btn" class="button button-primary button-hero">
				<?php echo esc_html( 'Export' ); ?>
			</button>
		</div>

		<div id="digital-lobster-progress-container" class="digital-lobster-progress-container" style="display: none;">
			<div class="digital-lobster-progress-bar">
				<div id="digital-lobster-progress-fill" class="digital-lobster-progress-fill"></div>
			</div>
			<p id="digital-lobster-progress-stage" class="digital-lobster-progress-stage"></p>
			<p id="digital-lobster-progress-text" class="digital-lobster-progress-text"></p>
		</div>

		<div id="digital-lobster-success-container" class="digital-lobster-success-container" style="display: none;">
			<p class="digital-lobster-success-message">
				<?php echo esc_html( 'Export artifacts created successfully!' ); ?>
			</p>
			<button id="digital-lobster-download-btn" class="button button-primary">
				<?php echo esc_html( 'Download Artifacts (.zip)' ); ?>
			</button>
		</div>

		<div id="digital-lobster-warning-container" class="digital-lobster-warning-container notice notice-warning" style="display: none; margin-top: 20px; padding: 10px 15px;">
			<p id="digital-lobster-warning-message" class="digital-lobster-warning-message"></p>
		</div>

		<div id="digital-lobster-error-container" class="digital-lobster-error-container notice notice-error" style="display: none; margin-top: 20px; padding: 10px 15px;">
			<p id="digital-lobster-error-message" class="digital-lobster-error-message"></p>
		</div>
	</div>
</div>

<script type="text/javascript">
(function($) {
	'use strict';

	$(document).ready(function() {
		var $toggle = $('#digital-lobster-settings-toggle');
		var $panel = $('#digital-lobster-settings-panel');
		var isOpen = false;

		// Toggle settings panel
		$toggle.on('click', function() {
			isOpen = !isOpen;
			$panel.slideToggle(200);
			$toggle.text(isOpen ? '<?php echo esc_js( 'Settings ▲' ); ?>' : '<?php echo esc_js( 'Settings ▼' ); ?>');
		});

		// Save settings via AJAX
		$('#digital-lobster-save-settings-btn').on('click', function() {
			var $btn = $(this);
			var $status = $('#digital-lobster-settings-status');

			$btn.prop('disabled', true);
			$status.text('<?php echo esc_js( 'Saving...' ); ?>').css('color', '');

			$.ajax({
				url: digitalLobsterExporter.ajaxUrl,
				type: 'POST',
				data: {
					action: 'digital_lobster_save_settings',
					nonce: digitalLobsterExporter.nonce,
					max_posts: $('#digital-lobster-max-posts').val(),
					max_pages: $('#digital-lobster-max-pages').val(),
					max_per_custom_post_type: $('#digital-lobster-max-cpt').val(),
					include_html_snapshots: $('#digital-lobster-html-snapshots').is(':checked') ? 1 : 0,
					batch_size: $('#digital-lobster-batch-size').val(),
					cleanup_after_hours: $('#digital-lobster-cleanup-hours').val()
				},
				success: function(response) {
					$btn.prop('disabled', false);
					if (response.success) {
						$status.text('<?php echo esc_js( 'Settings saved.' ); ?>').css('color', '#46b450');
					} else {
						$status.text(response.data.message || '<?php echo esc_js( 'Error saving settings.' ); ?>').css('color', '#dc3232');
					}
					setTimeout(function() { $status.text(''); }, 3000);
				},
				error: function() {
					$btn.prop('disabled', false);
					$status.text('<?php echo esc_js( 'Error saving settings.' ); ?>').css('color', '#dc3232');
					setTimeout(function() { $status.text(''); }, 3000);
				}
			});
		});
	});
})(jQuery);
</script>
