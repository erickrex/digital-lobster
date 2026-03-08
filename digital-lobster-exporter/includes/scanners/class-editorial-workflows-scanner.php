<?php
/**
 * Editorial Workflows Scanner Class
 *
 * Produces a normalized editorial_workflows.json artifact containing
 * editorial behavior: statuses in use, scheduled publishing, draft
 * behavior, preview expectations, revision policy, comments settings,
 * and authoring model.
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Editorial Workflows Scanner Class
 */
class Digital_Lobster_Exporter_Editorial_Workflows_Scanner extends Digital_Lobster_Exporter_Scanner_Base {

	/**
	 * Scan editorial workflow configuration and behavior.
	 *
	 * @return array Editorial workflows data matching EditorialWorkflowsArtifact schema.
	 */
	public function scan() {
		return array(
			'schema_version'       => '1.0.0',
			'statuses_in_use'      => $this->detect_statuses_in_use(),
			'scheduled_publishing' => $this->detect_scheduled_publishing(),
			'draft_behavior'       => $this->detect_draft_behavior(),
			'preview_expectations' => $this->detect_preview_expectations(),
			'revision_policy'      => $this->detect_revision_policy(),
			'comments_enabled'     => $this->detect_comments_enabled(),
			'authoring_model'      => $this->detect_authoring_model(),
		);
	}

	/**
	 * Detect post statuses actually in use across all public post types.
	 *
	 * @return array List of status slugs.
	 */
	private function detect_statuses_in_use() {
		global $wpdb;

		// phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery, WordPress.DB.DirectDatabaseQuery.NoCaching
		$statuses = $wpdb->get_col(
			"SELECT DISTINCT post_status
			FROM {$wpdb->posts}
			WHERE post_type IN (
				SELECT DISTINCT post_type FROM {$wpdb->posts}
				WHERE post_status NOT IN ('auto-draft', 'inherit', 'trash')
			)
			AND post_status NOT IN ('auto-draft', 'inherit', 'trash')
			ORDER BY post_status"
		);

		if ( empty( $statuses ) ) {
			return array( 'publish' );
		}

		return array_values( array_unique( $statuses ) );
	}

	/**
	 * Detect whether scheduled publishing is in use.
	 *
	 * @return bool True if any future-dated posts exist.
	 */
	private function detect_scheduled_publishing() {
		global $wpdb;

		// phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery, WordPress.DB.DirectDatabaseQuery.NoCaching
		$count = $wpdb->get_var(
			"SELECT COUNT(*) FROM {$wpdb->posts}
			WHERE post_status = 'future'
			LIMIT 1"
		);

		return ( (int) $count > 0 );
	}

	/**
	 * Detect draft behavior based on draft post presence and patterns.
	 *
	 * @return string Description of draft behavior.
	 */
	private function detect_draft_behavior() {
		global $wpdb;

		// phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery, WordPress.DB.DirectDatabaseQuery.NoCaching
		$draft_count = (int) $wpdb->get_var(
			"SELECT COUNT(*) FROM {$wpdb->posts}
			WHERE post_status = 'draft'
			AND post_type NOT IN ('revision', 'nav_menu_item')"
		);

		// phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery, WordPress.DB.DirectDatabaseQuery.NoCaching
		$pending_count = (int) $wpdb->get_var(
			"SELECT COUNT(*) FROM {$wpdb->posts}
			WHERE post_status = 'pending'
			AND post_type NOT IN ('revision', 'nav_menu_item')"
		);

		if ( $pending_count > 0 ) {
			return 'drafts_with_pending_review';
		}
		if ( $draft_count > 10 ) {
			return 'active_drafting';
		}
		if ( $draft_count > 0 ) {
			return 'minimal_drafts';
		}

		return 'publish_only';
	}

	/**
	 * Detect preview expectations.
	 *
	 * @return string Description of preview behavior.
	 */
	private function detect_preview_expectations() {
		// Check if a preview plugin is active.
		if ( is_plugin_active( 'public-post-preview/public-post-preview.php' ) ) {
			return 'public_preview_links';
		}

		// Check for draft/pending content indicating preview usage.
		global $wpdb;

		// phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery, WordPress.DB.DirectDatabaseQuery.NoCaching
		$draft_count = (int) $wpdb->get_var(
			"SELECT COUNT(*) FROM {$wpdb->posts}
			WHERE post_status IN ('draft', 'pending')
			AND post_type NOT IN ('revision', 'nav_menu_item')"
		);

		if ( $draft_count > 5 ) {
			return 'standard_wp_preview';
		}

		return 'minimal_preview';
	}

	/**
	 * Detect revision policy.
	 *
	 * @return string Description of revision policy.
	 */
	private function detect_revision_policy() {
		// Check WP_POST_REVISIONS constant.
		if ( defined( 'WP_POST_REVISIONS' ) ) {
			$revisions = WP_POST_REVISIONS;
			if ( false === $revisions || 0 === $revisions ) {
				return 'revisions_disabled';
			}
			if ( is_numeric( $revisions ) ) {
				return 'limited_revisions:' . (int) $revisions;
			}
		}

		// Check actual revision count to infer policy.
		global $wpdb;

		// phpcs:ignore WordPress.DB.DirectDatabaseQuery.DirectQuery, WordPress.DB.DirectDatabaseQuery.NoCaching
		$revision_count = (int) $wpdb->get_var(
			"SELECT COUNT(*) FROM {$wpdb->posts}
			WHERE post_type = 'revision'"
		);

		if ( 0 === $revision_count ) {
			return 'revisions_disabled';
		}

		return 'unlimited_revisions';
	}

	/**
	 * Detect whether comments are enabled site-wide.
	 *
	 * @return bool True if comments are enabled.
	 */
	private function detect_comments_enabled() {
		$default_status = get_option( 'default_comment_status', 'closed' );
		return ( 'open' === $default_status );
	}

	/**
	 * Detect the authoring model based on user count and roles.
	 *
	 * @return string "single_editor" or "two_editor".
	 */
	private function detect_authoring_model() {
		$editors = get_users( array(
			'role__in' => array( 'administrator', 'editor', 'author' ),
			'fields'   => 'ID',
		) );

		$editor_count = count( $editors );

		if ( $editor_count <= 1 ) {
			return 'single_editor';
		}

		return 'two_editor';
	}
}
