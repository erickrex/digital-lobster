<?php
/**
 * Scanner Base Abstract Class
 *
 * Provides a uniform interface for all 23 scanner classes. Every scanner
 * extends this base, sharing a single constructor signature and access
 * to common dependencies (export directory, context, security filters).
 *
 * @package Digital_Lobster_Exporter
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Abstract base class for all scanners.
 *
 * Subclasses implement scan() to collect site data. The orchestrator
 * instantiates every scanner with the same $deps array and calls
 * scan() / get_data() through this interface.
 */
abstract class Digital_Lobster_Exporter_Scanner_Base {

	use Digital_Lobster_Exporter_Error_Logger;

	/**
	 * Export directory path (may be empty if not needed by the scanner).
	 *
	 * @var string
	 */
	protected $export_dir = '';

	/**
	 * Scan results collected by previous scanners.
	 *
	 * The orchestrator builds this incrementally so that later scanners
	 * can reference data from earlier ones (e.g., Taxonomy_Scanner reads
	 * content data produced by Content_Scanner).
	 *
	 * @var array
	 */
	protected $context = array();

	/**
	 * Centralized security and privacy filter instance.
	 *
	 * @var Digital_Lobster_Exporter_Security_Filters
	 */
	protected $security_filters;

	/**
	 * Constructor. All scanners share this signature.
	 *
	 * @param array $deps {
	 *     Optional. Associative array of dependencies.
	 *
	 *     @type string                                   $export_dir       Path to the export directory.
	 *     @type array                                    $context          Results from previously-run scanners.
	 *     @type Digital_Lobster_Exporter_Security_Filters $security_filters Security filter instance.
	 * }
	 */
	public function __construct( array $deps = array() ) {
		$this->export_dir       = isset( $deps['export_dir'] ) ? $deps['export_dir'] : '';
		$this->context          = isset( $deps['context'] ) ? $deps['context'] : array();
		$this->security_filters = isset( $deps['security_filters'] )
			? $deps['security_filters']
			: new Digital_Lobster_Exporter_Security_Filters();
	}

	/**
	 * Run the scan. Subclasses must implement this.
	 *
	 * @return array Scan results.
	 */
	abstract public function scan();

	/**
	 * Get collected scan data.
	 *
	 * Defaults to calling scan(). Scanners that cache results internally
	 * can override this to return the cached data without re-scanning.
	 *
	 * @return array
	 */
	public function get_data() {
		return $this->scan();
	}

	/**
	 * Get deduplicated sampled content items from Content Scanner context.
	 *
	 * Later scanners should prefer these sampled items over whole-site queries
	 * so the export stays aligned with the configured sample limits.
	 *
	 * @param string[] $post_types Optional post type allow-list.
	 * @return array
	 */
	protected function get_sampled_content_items( array $post_types = array() ) {
		if ( empty( $this->context['content'] ) || ! is_array( $this->context['content'] ) ) {
			return array();
		}

		$content = $this->context['content'];
		$items   = array();
		$seen    = array();

		$item_groups = array();

		if ( ! empty( $content['posts'] ) && is_array( $content['posts'] ) ) {
			$item_groups[] = $content['posts'];
		}

		if ( ! empty( $content['pages'] ) && is_array( $content['pages'] ) ) {
			$item_groups[] = $content['pages'];
		}

		if ( ! empty( $content['custom_post_types'] ) && is_array( $content['custom_post_types'] ) ) {
			foreach ( $content['custom_post_types'] as $post_type_items ) {
				if ( is_array( $post_type_items ) ) {
					$item_groups[] = $post_type_items;
				}
			}
		}

		foreach ( $item_groups as $group ) {
			foreach ( $group as $item ) {
				if ( ! is_array( $item ) || empty( $item['id'] ) ) {
					continue;
				}

				$post_type = isset( $item['type'] ) ? $item['type'] : '';
				if ( ! empty( $post_types ) && ! in_array( $post_type, $post_types, true ) ) {
					continue;
				}

				$post_id = (int) $item['id'];
				if ( $post_id < 1 || isset( $seen[ $post_id ] ) ) {
					continue;
				}

				$seen[ $post_id ] = true;
				$items[]          = $item;
			}
		}

		return $items;
	}

	/**
	 * Resolve sampled content items into WP_Post objects.
	 *
	 * @param string[] $post_types Optional post type allow-list.
	 * @return array
	 */
	protected function get_sampled_posts( array $post_types = array() ) {
		$posts = array();

		foreach ( $this->get_sampled_content_items( $post_types ) as $item ) {
			$post = get_post( (int) $item['id'] );
			if ( $post ) {
				$posts[] = $post;
			}
		}

		return $posts;
	}
}
