/**
 * Admin JavaScript for Digital Lobster Exporter
 *
 * @package Digital_Lobster_Exporter
 */

(function($) {
	'use strict';

	$(document).ready(function() {
		const $migrateBtn = $('#digital-lobster-migrate-btn');
		const $progressContainer = $('#digital-lobster-progress-container');
		const $progressFill = $('#digital-lobster-progress-fill');
		const $progressText = $('#digital-lobster-progress-text');
		const $progressStage = $('#digital-lobster-progress-stage');
		const $successContainer = $('#digital-lobster-success-container');
		const $downloadBtn = $('#digital-lobster-download-btn');
		const $errorContainer = $('#digital-lobster-error-container');
		const $errorMessage = $('#digital-lobster-error-message');
		const $warningContainer = $('#digital-lobster-warning-container');
		const $warningMessage = $('#digital-lobster-warning-message');

		let progressInterval = null;

		// Stage labels for display
		const stageLabels = {
			'starting': 'Starting',
			'site': 'Site Information',
			'theme': 'Theme & Assets',
			'plugins': 'Plugins',
			'content': 'Content Sampling',
			'taxonomies': 'Taxonomies',
			'media': 'Media Files',
			'settings': 'Settings & Configuration',
			'database': 'Database Schema',
			'environment': 'Environment',
			'translation': 'Translations',
			'exporting': 'Generating Files',
			'packaging': 'Creating ZIP Archive',
			'completed': 'Complete'
		};

		/**
		 * Handle migrate button click
		 */
		$migrateBtn.on('click', function() {
			// Disable button and show progress
			$migrateBtn.prop('disabled', true);
			$progressContainer.show();
			$successContainer.hide();
			$errorContainer.hide();
			$progressFill.css('width', '0%');
			$progressText.text('Starting scan...');
			$progressStage.text('');

			// Start scan via AJAX
			$.ajax({
				url: digitalLobsterExporter.ajaxUrl,
				type: 'POST',
				data: {
					action: 'digital_lobster_start_scan',
					nonce: digitalLobsterExporter.nonce
				},
				success: function(response) {
					if (response.success) {
						// Start polling for progress
						startProgressPolling();
					} else {
						showError(response.data.message || 'An error occurred.');
					}
				},
				error: function(xhr, status, error) {
					// Try to extract more detailed error information
					let errorMsg = 'AJAX error: ' + error;
					
					if (xhr.status === 500) {
						errorMsg = 'Server error (500): The plugin encountered a fatal PHP error. ';
						errorMsg += 'Please check your WordPress debug log (wp-content/debug.log) for details. ';
						
						// Try to extract error from response
						if (xhr.responseText) {
							const match = xhr.responseText.match(/Fatal error:([^<]+)/i);
							if (match) {
								errorMsg += 'Error: ' + match[1].trim();
							}
						}
					} else if (xhr.status === 0) {
						errorMsg = 'Network error: Could not connect to server. Please check your internet connection.';
					} else if (xhr.status === 403) {
						errorMsg = 'Permission denied (403): You do not have permission to perform this action.';
					} else if (xhr.status === 404) {
						errorMsg = 'Not found (404): The AJAX endpoint was not found. Please ensure the plugin is activated.';
					} else {
						errorMsg = 'HTTP ' + xhr.status + ' error: ' + error;
					}
					
					showError(errorMsg);
				}
			});
		});

		/**
		 * Start polling for progress updates
		 */
		function startProgressPolling() {
			// Clear any existing interval
			if (progressInterval) {
				clearInterval(progressInterval);
			}

			// Poll every 1 second
			progressInterval = setInterval(function() {
				$.ajax({
					url: digitalLobsterExporter.ajaxUrl,
					type: 'POST',
					data: {
						action: 'digital_lobster_get_progress',
						nonce: digitalLobsterExporter.nonce
					},
					success: function(response) {
						if (response.success) {
							updateProgress(response.data);
						} else {
							stopProgressPolling();
							showError(response.data.message || 'Failed to get progress.');
						}
					},
					error: function(xhr, status, error) {
						stopProgressPolling();
						showError('Progress polling error: ' + error);
					}
				});
			}, 1000);
		}

		/**
		 * Stop polling for progress updates
		 */
		function stopProgressPolling() {
			if (progressInterval) {
				clearInterval(progressInterval);
				progressInterval = null;
			}
		}

		/**
		 * Update progress display
		 */
		function updateProgress(data) {
			// Update progress bar
			$progressFill.css('width', data.percent + '%');
			
			// Update progress text
			$progressText.text(data.message);
			
			// Update stage indicator
			const stageLabel = stageLabels[data.stage] || data.stage;
			$progressStage.text('Stage: ' + stageLabel);

			// Check if completed
			if (data.completed) {
				stopProgressPolling();
				
				// Check for errors
				if (data.error) {
					showError(data.error);
				} else {
					// Store download URL for later use
					if (data.download_url) {
						$downloadBtn.data('download-url', data.download_url);
					}
					
					// Show warnings if any
					if (data.has_issues && (data.warnings || data.errors)) {
						showWarnings(data.warnings, data.errors);
					}
					
					// Show success message
					setTimeout(function() {
						$progressContainer.hide();
						$successContainer.show();
						$migrateBtn.prop('disabled', false);
					}, 500);
				}
			}
		}

		/**
		 * Handle download button click
		 */
		$downloadBtn.on('click', function() {
			// Get download URL from button data
			const downloadUrl = $downloadBtn.data('download-url');
			
			if (downloadUrl) {
				// Redirect to download URL
				window.location.href = downloadUrl;
			} else {
				showError('Download URL not available. Please try running the migration again.');
			}
		});

		/**
		 * Show error message
		 */
		function showError(message) {
			stopProgressPolling();
			$migrateBtn.prop('disabled', false);
			$progressContainer.hide();
			$successContainer.hide();
			$warningContainer.hide();
			$errorMessage.html('<strong>Error:</strong> ' + escapeHtml(message));
			$errorContainer.show();
		}

		/**
		 * Show warnings and non-critical errors
		 */
		function showWarnings(warnings, errors) {
			let message = '<strong>Note:</strong> The export completed with some issues:<br><br>';
			
			if (errors && errors.length > 0) {
				message += '<strong>Non-critical errors (' + errors.length + '):</strong><br>';
				message += '<ul style="margin: 5px 0 10px 20px;">';
				errors.slice(0, 3).forEach(function(error) {
					message += '<li>' + escapeHtml(error.message || error) + '</li>';
				});
				if (errors.length > 3) {
					message += '<li><em>... and ' + (errors.length - 3) + ' more</em></li>';
				}
				message += '</ul>';
			}
			
			if (warnings && warnings.length > 0) {
				message += '<strong>Warnings (' + warnings.length + '):</strong><br>';
				message += '<ul style="margin: 5px 0 10px 20px;">';
				warnings.slice(0, 3).forEach(function(warning) {
					message += '<li>' + escapeHtml(warning.message || warning) + '</li>';
				});
				if (warnings.length > 3) {
					message += '<li><em>... and ' + (warnings.length - 3) + ' more</em></li>';
				}
				message += '</ul>';
			}
			
			message += '<br><em>Full details are available in error_log.json within the downloaded ZIP file.</em>';
			
			$warningMessage.html(message);
			$warningContainer.show();
		}

		/**
		 * Escape HTML to prevent XSS
		 */
		function escapeHtml(text) {
			const map = {
				'&': '&amp;',
				'<': '&lt;',
				'>': '&gt;',
				'"': '&quot;',
				"'": '&#039;'
			};
			return String(text).replace(/[&<>"']/g, function(m) { return map[m]; });
		}
	});

})(jQuery);
