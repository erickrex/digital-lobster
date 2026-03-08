/**
 * Admin JavaScript for Digital Lobster Exporter
 *
 * @package Digital_Lobster_Exporter
 */

(function($) {
	'use strict';

	$(document).ready(function() {
		const $settingsToggle = $('#digital-lobster-settings-toggle');
		const $settingsPanel = $('#digital-lobster-settings-panel');
		const $saveSettingsBtn = $('#digital-lobster-save-settings-btn');
		const $settingsStatus = $('#digital-lobster-settings-status');
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

		let settingsOpen = false;

		$settingsToggle.on('click', function() {
			settingsOpen = !settingsOpen;
			$settingsPanel.slideToggle(200);
			$settingsToggle.text(settingsOpen ? 'Settings ▲' : 'Settings ▼');
		});

		$saveSettingsBtn.on('click', function() {
			$saveSettingsBtn.prop('disabled', true);
			$settingsStatus.text('Saving...').css('color', '');

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
					$saveSettingsBtn.prop('disabled', false);
					if (response.success) {
						$settingsStatus.text('Settings saved.').css('color', '#46b450');
					} else {
						$settingsStatus.text(getResponseMessage(response, 'Error saving settings.')).css('color', '#dc3232');
					}
					setTimeout(function() { $settingsStatus.text(''); }, 3000);
				},
				error: function() {
					$saveSettingsBtn.prop('disabled', false);
					$settingsStatus.text('Error saving settings.').css('color', '#dc3232');
					setTimeout(function() { $settingsStatus.text(''); }, 3000);
				}
			});
		});

		/**
		 * Handle export button click.
		 */
		$migrateBtn.on('click', function() {
			showBusyState();

			$.ajax({
				url: digitalLobsterExporter.ajaxUrl,
				type: 'POST',
				data: {
					action: 'digital_lobster_start_scan',
					nonce: digitalLobsterExporter.nonce
				},
				success: function(response) {
					if (!response.success) {
						showError(getResponseMessage(response, 'An error occurred.'));
						return;
					}

					showSuccess(response.data || {});
				},
				error: function(xhr, status, error) {
					showError(buildAjaxErrorMessage(xhr, error));
				}
			});
		});

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
		 * Show the synchronous export busy state.
		 */
		function showBusyState() {
			$migrateBtn.prop('disabled', true);
			$successContainer.hide();
			$errorContainer.hide();
			$warningContainer.hide();
			$progressContainer.show();
			$progressFill.addClass('is-busy').css('width', '100%');
			$progressStage.text('Export running');
			$progressText.text('This export runs in a single request. Keep this page open until the server responds.');
		}

		/**
		 * Show the final success state.
		 */
		function showSuccess(data) {
			$progressFill.removeClass('is-busy').css('width', '100%');
			$progressStage.text('Export complete');
			$progressText.text(data.message || 'Export completed successfully.');

			if (data.download_url) {
				$downloadBtn.data('download-url', data.download_url);
			}

			if (data.has_issues && (data.warnings || data.errors)) {
				showWarnings(data.warnings, data.errors);
			}

			setTimeout(function() {
				$progressContainer.hide();
				$successContainer.show();
				$migrateBtn.prop('disabled', false);
			}, 300);
		}

		/**
		 * Show an error message.
		 */
		function showError(message) {
			$migrateBtn.prop('disabled', false);
			$progressFill.removeClass('is-busy').css('width', '0%');
			$progressStage.text('');
			$progressText.text('');
			$progressContainer.hide();
			$successContainer.hide();
			$warningContainer.hide();
			$errorMessage.html('<strong>Error:</strong> ' + escapeHtml(message));
			$errorContainer.show();
		}

		/**
		 * Show warnings and non-critical errors.
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
		 * Build a human-readable AJAX error message.
		 */
		function buildAjaxErrorMessage(xhr, error) {
			let errorMsg = 'AJAX error: ' + error;

			if (xhr.status === 500) {
				errorMsg = 'Server error (500): The exporter hit a fatal PHP error. ';
				errorMsg += 'Please check your WordPress debug log (wp-content/debug.log) for details. ';

				if (xhr.responseText) {
					const match = xhr.responseText.match(/Fatal error:([^<]+)/i);
					if (match) {
						errorMsg += 'Error: ' + match[1].trim();
					}
				}
			} else if (xhr.status === 0) {
				errorMsg = 'Network error: Could not connect to the server.';
			} else if (xhr.status === 403) {
				errorMsg = 'Permission denied (403): You do not have permission to perform this action.';
			} else if (xhr.status === 404) {
				errorMsg = 'Not found (404): The AJAX endpoint was not found. Please ensure the plugin is activated.';
			} else {
				errorMsg = 'HTTP ' + xhr.status + ' error: ' + error;
			}

			return errorMsg;
		}

		/**
		 * Extract a message from a WordPress AJAX response.
		 */
		function getResponseMessage(response, fallback) {
			return response && response.data && response.data.message
				? response.data.message
				: fallback;
		}

		/**
		 * Escape HTML to prevent XSS.
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
