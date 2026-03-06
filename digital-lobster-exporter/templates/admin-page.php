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
?>

<div class="wrap digital-lobster-exporter-wrap">
	<h1><?php echo esc_html__( 'AI Website Exporter', 'digital-lobster-exporter' ); ?></h1>
	
	<div class="digital-lobster-exporter-container">
		<div class="digital-lobster-exporter-header">
			<p class="digital-lobster-exporter-tagline">
				<?php echo esc_html__( 'Collects everything needed to recreate your website in a modern Python architecture using AI Agents', 'digital-lobster-exporter' ); ?>
			</p>
			
			<p class="digital-lobster-exporter-description">
				<?php
				echo esc_html__(
					'This plugin will scan your WordPress site and export all necessary data including content, theme files, plugin configurations, and database schema. All data is packaged into a downloadable ZIP file. No user data, passwords, or API keys are included in the export.',
					'digital-lobster-exporter'
				);
				?>
			</p>
		</div>

		<div class="digital-lobster-exporter-actions">
			<button id="digital-lobster-migrate-btn" class="button button-primary button-hero">
				<?php echo esc_html__( 'Export', 'digital-lobster-exporter' ); ?>
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
				<?php echo esc_html__( 'Export artifacts created successfully!', 'digital-lobster-exporter' ); ?>
			</p>
			<button id="digital-lobster-download-btn" class="button button-primary">
				<?php echo esc_html__( 'Download Artifacts (.zip)', 'digital-lobster-exporter' ); ?>
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
