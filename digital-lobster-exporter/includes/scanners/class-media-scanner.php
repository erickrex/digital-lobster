<?php
/**
 * Media Scanner Class
 *
 * Scans exported content for media references and exports only referenced media files.
 * Creates a media map for URL rewriting and exports attachment metadata.
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * Media Scanner Class
 */
class Digital_Lobster_Exporter_Media_Scanner {

	/**
	 * Exported content data (from ContentScanner).
	 *
	 * @var array
	 */
	private $exported_content = array();

	/**
	 * Export directory path.
	 *
	 * @var string
	 */
	private $export_dir = '';

	/**
	 * Referenced media items.
	 *
	 * @var array
	 */
	private $referenced_media = array();

	/**
	 * Media map for URL rewriting.
	 *
	 * @var array
	 */
	private $media_map = array();

	/**
	 * WordPress uploads directory info.
	 *
	 * @var array
	 */
	private $upload_dir = array();

	/**
	 * Constructor.
	 *
	 * @param array  $exported_content Content data from ContentScanner.
	 * @param string $export_dir Export directory path.
	 */
	public function __construct( $exported_content = array(), $export_dir = '' ) {
		$this->exported_content = $exported_content;
		$this->export_dir = $export_dir;
		$this->upload_dir = wp_upload_dir();
	}

	/**
	 * Scan and collect media data.
	 *
	 * @return array Media data including map and metadata.
	 */
	public function scan() {
		// Identify all referenced media
		$this->identify_referenced_media();

		// Copy media files to export directory
		$this->copy_media_files();

		// Generate media map
		$this->generate_media_map();

		// Return media data
		return array(
			'media_map' => $this->media_map,
			'total_files' => count( $this->referenced_media ),
		);
	}

	/**
	 * Identify all media referenced in exported content.
	 */
	private function identify_referenced_media() {
		$this->referenced_media = array();

		// Scan posts
		if ( isset( $this->exported_content['posts'] ) && is_array( $this->exported_content['posts'] ) ) {
			foreach ( $this->exported_content['posts'] as $post ) {
				$this->scan_content_item( $post );
			}
		}

		// Scan pages
		if ( isset( $this->exported_content['pages'] ) && is_array( $this->exported_content['pages'] ) ) {
			foreach ( $this->exported_content['pages'] as $page ) {
				$this->scan_content_item( $page );
			}
		}

		// Scan custom post types
		if ( isset( $this->exported_content['custom_post_types'] ) && is_array( $this->exported_content['custom_post_types'] ) ) {
			foreach ( $this->exported_content['custom_post_types'] as $post_type => $items ) {
				if ( is_array( $items ) ) {
					foreach ( $items as $item ) {
						$this->scan_content_item( $item );
					}
				}
			}
		}

		// Remove duplicates
		$this->referenced_media = array_unique( $this->referenced_media, SORT_REGULAR );
	}

	/**
	 * Scan a single content item for media references.
	 *
	 * @param array $content_item Content item data.
	 */
	private function scan_content_item( $content_item ) {
		// 1. Featured image
		if ( isset( $content_item['featured_media'] ) && ! empty( $content_item['featured_media'] ) ) {
			$this->add_media_reference( $content_item['featured_media'] );
		}

		// 2. Inline images in blocks
		if ( isset( $content_item['blocks'] ) && is_array( $content_item['blocks'] ) ) {
			$this->scan_blocks_for_media( $content_item['blocks'] );
		}

		// 3. Images in raw HTML content
		if ( isset( $content_item['raw_html'] ) && ! empty( $content_item['raw_html'] ) ) {
			$this->scan_html_for_media( $content_item['raw_html'] );
		}
	}

	/**
	 * Add a media reference to the list.
	 *
	 * @param array $media_data Media data with id, url, and optional alt.
	 */
	private function add_media_reference( $media_data ) {
		if ( ! isset( $media_data['id'] ) || ! isset( $media_data['url'] ) ) {
			return;
		}

		// Check if already added
		foreach ( $this->referenced_media as $existing ) {
			if ( $existing['id'] === $media_data['id'] ) {
				return;
			}
		}

		$this->referenced_media[] = $media_data;
	}

	/**
	 * Recursively scan blocks for media references.
	 *
	 * @param array $blocks Blocks array.
	 */
	private function scan_blocks_for_media( $blocks ) {
		foreach ( $blocks as $block ) {
			// Check block name for media-related blocks
			if ( isset( $block['name'] ) ) {
				$this->scan_block_for_media( $block );
			}

			// Recursively scan inner blocks
			if ( isset( $block['innerBlocks'] ) && is_array( $block['innerBlocks'] ) ) {
				$this->scan_blocks_for_media( $block['innerBlocks'] );
			}
		}
	}

	/**
	 * Scan a single block for media references.
	 *
	 * @param array $block Block data.
	 */
	private function scan_block_for_media( $block ) {
		$block_name = $block['name'];

		// Core image block
		if ( 'core/image' === $block_name && isset( $block['attrs']['id'] ) ) {
			$attachment_id = $block['attrs']['id'];
			$this->add_attachment_by_id( $attachment_id );
		}

		// Core gallery block
		if ( 'core/gallery' === $block_name && isset( $block['attrs']['ids'] ) && is_array( $block['attrs']['ids'] ) ) {
			foreach ( $block['attrs']['ids'] as $attachment_id ) {
				$this->add_attachment_by_id( $attachment_id );
			}
		}

		// Core media-text block
		if ( 'core/media-text' === $block_name && isset( $block['attrs']['mediaId'] ) ) {
			$attachment_id = $block['attrs']['mediaId'];
			$this->add_attachment_by_id( $attachment_id );
		}

		// Core cover block
		if ( 'core/cover' === $block_name && isset( $block['attrs']['id'] ) ) {
			$attachment_id = $block['attrs']['id'];
			$this->add_attachment_by_id( $attachment_id );
		}

		// Scan block HTML for image URLs
		if ( isset( $block['html'] ) && ! empty( $block['html'] ) ) {
			$this->scan_html_for_media( $block['html'] );
		}
	}

	/**
	 * Add an attachment by ID.
	 *
	 * @param int $attachment_id Attachment ID.
	 */
	private function add_attachment_by_id( $attachment_id ) {
		$attachment_id = absint( $attachment_id );
		if ( ! $attachment_id ) {
			return;
		}

		$attachment_url = wp_get_attachment_url( $attachment_id );
		if ( ! $attachment_url ) {
			return;
		}

		$alt_text = get_post_meta( $attachment_id, '_wp_attachment_image_alt', true );

		$this->add_media_reference( array(
			'id'  => $attachment_id,
			'url' => $attachment_url,
			'alt' => $alt_text,
		) );
	}

	/**
	 * Scan HTML content for media URLs.
	 *
	 * @param string $html HTML content.
	 */
	private function scan_html_for_media( $html ) {
		// Match img tags
		preg_match_all( '/<img[^>]+src=["\']([^"\']+)["\'][^>]*>/i', $html, $img_matches );
		
		if ( ! empty( $img_matches[1] ) ) {
			foreach ( $img_matches[1] as $img_url ) {
				$this->add_media_by_url( $img_url );
			}
		}

		// Match background images in style attributes
		preg_match_all( '/background-image:\s*url\(["\']?([^"\')\s]+)["\']?\)/i', $html, $bg_matches );
		
		if ( ! empty( $bg_matches[1] ) ) {
			foreach ( $bg_matches[1] as $bg_url ) {
				$this->add_media_by_url( $bg_url );
			}
		}

		// Match srcset attributes for responsive images
		preg_match_all( '/srcset=["\']([^"\']+)["\']/i', $html, $srcset_matches );
		
		if ( ! empty( $srcset_matches[1] ) ) {
			foreach ( $srcset_matches[1] as $srcset ) {
				// Parse srcset (format: "url1 1x, url2 2x" or "url1 100w, url2 200w")
				$srcset_urls = preg_split( '/,\s*/', $srcset );
				foreach ( $srcset_urls as $srcset_item ) {
					// Extract URL (everything before the descriptor)
					$parts = preg_split( '/\s+/', trim( $srcset_item ) );
					if ( ! empty( $parts[0] ) ) {
						$this->add_media_by_url( $parts[0] );
					}
				}
			}
		}
	}

	/**
	 * Add media by URL.
	 *
	 * @param string $url Media URL.
	 */
	private function add_media_by_url( $url ) {
		// Check if this is a local upload URL
		if ( ! $this->is_local_upload_url( $url ) ) {
			// Handle CDN URLs - add to map but don't copy
			if ( $this->is_cdn_url( $url ) ) {
				$this->add_cdn_reference( $url );
			}
			return;
		}

		// Try to get attachment ID from URL
		$attachment_id = attachment_url_to_postid( $url );
		
		if ( $attachment_id ) {
			$this->add_attachment_by_id( $attachment_id );
		} else {
			// Add by URL even if we can't find the attachment ID
			// This handles edge cases where attachment_url_to_postid fails
			$this->add_media_reference( array(
				'id'  => 0,
				'url' => $url,
				'alt' => '',
			) );
		}
	}

	/**
	 * Check if URL is a local upload URL.
	 *
	 * @param string $url URL to check.
	 * @return bool True if local upload URL.
	 */
	private function is_local_upload_url( $url ) {
		$upload_url = $this->upload_dir['baseurl'];
		
		// Check if URL starts with upload URL
		if ( strpos( $url, $upload_url ) === 0 ) {
			return true;
		}

		// Check if it's a relative URL to uploads
		if ( strpos( $url, '/wp-content/uploads/' ) !== false ) {
			return true;
		}

		return false;
	}

	/**
	 * Check if URL is a CDN URL.
	 *
	 * @param string $url URL to check.
	 * @return bool True if CDN URL.
	 */
	private function is_cdn_url( $url ) {
		// Common CDN patterns
		$cdn_patterns = array(
			'cloudfront.net',
			'cloudflare.com',
			'cdn.',
			'amazonaws.com',
			'googleusercontent.com',
		);

		foreach ( $cdn_patterns as $pattern ) {
			if ( strpos( $url, $pattern ) !== false ) {
				return true;
			}
		}

		return false;
	}

	/**
	 * Add CDN reference to media map.
	 *
	 * @param string $url CDN URL.
	 */
	private function add_cdn_reference( $url ) {
		// Add to media map with note that it's a CDN URL
		$this->media_map[] = array(
			'wp_src'   => $url,
			'artifact' => null,
			'type'     => 'cdn',
			'note'     => 'External CDN resource - not copied',
		);
	}

	/**
	 * Copy media files to export directory.
	 */
	private function copy_media_files() {
		if ( empty( $this->export_dir ) ) {
			return;
		}

		// Create media directory
		$media_dir = trailingslashit( $this->export_dir ) . 'media';
		if ( ! file_exists( $media_dir ) ) {
			wp_mkdir_p( $media_dir );
		}

		foreach ( $this->referenced_media as $media ) {
			$this->copy_single_media_file( $media, $media_dir );
		}
	}

	/**
	 * Copy a single media file.
	 *
	 * @param array  $media Media data.
	 * @param string $media_dir Media directory path.
	 */
	private function copy_single_media_file( $media, $media_dir ) {
		$url = $media['url'];

		// Get the file path from URL
		$file_path = $this->get_file_path_from_url( $url );
		
		if ( ! $file_path || ! file_exists( $file_path ) ) {
			error_log( sprintf(
				'Digital Lobster Exporter: Media file not found: %s',
				$url
			) );
			return;
		}

		// Get relative path to preserve directory structure
		$relative_path = $this->get_relative_upload_path( $url );
		
		if ( ! $relative_path ) {
			error_log( sprintf(
				'Digital Lobster Exporter: Could not determine relative path for: %s',
				$url
			) );
			return;
		}

		// Create destination path
		$dest_path = trailingslashit( $media_dir ) . $relative_path;
		$dest_dir = dirname( $dest_path );

		// Create subdirectories if needed
		if ( ! file_exists( $dest_dir ) ) {
			wp_mkdir_p( $dest_dir );
		}

		// Copy file
		$result = copy( $file_path, $dest_path );

		if ( ! $result ) {
			error_log( sprintf(
				'Digital Lobster Exporter: Failed to copy media file: %s to %s',
				$file_path,
				$dest_path
			) );
		}
	}

	/**
	 * Get file path from URL.
	 *
	 * @param string $url Media URL.
	 * @return string|false File path or false on failure.
	 */
	private function get_file_path_from_url( $url ) {
		$upload_url = $this->upload_dir['baseurl'];
		$upload_path = $this->upload_dir['basedir'];

		// Replace upload URL with upload path
		if ( strpos( $url, $upload_url ) === 0 ) {
			return str_replace( $upload_url, $upload_path, $url );
		}

		// Handle relative URLs
		if ( strpos( $url, '/wp-content/uploads/' ) !== false ) {
			$relative = substr( $url, strpos( $url, '/wp-content/uploads/' ) + strlen( '/wp-content/uploads/' ) );
			return trailingslashit( $upload_path ) . $relative;
		}

		return false;
	}

	/**
	 * Get relative upload path from URL.
	 *
	 * @param string $url Media URL.
	 * @return string|false Relative path or false on failure.
	 */
	private function get_relative_upload_path( $url ) {
		$upload_url = $this->upload_dir['baseurl'];

		// Get path relative to uploads directory
		if ( strpos( $url, $upload_url ) === 0 ) {
			return str_replace( trailingslashit( $upload_url ), '', $url );
		}

		// Handle relative URLs
		if ( strpos( $url, '/wp-content/uploads/' ) !== false ) {
			return substr( $url, strpos( $url, '/wp-content/uploads/' ) + strlen( '/wp-content/uploads/' ) );
		}

		return false;
	}

	/**
	 * Generate media map JSON.
	 */
	private function generate_media_map() {
		$this->media_map = array();

		foreach ( $this->referenced_media as $media ) {
			$url = $media['url'];
			$relative_path = $this->get_relative_upload_path( $url );

			if ( ! $relative_path ) {
				continue;
			}

			$map_entry = array(
				'wp_src'   => $url,
				'artifact' => 'media/' . $relative_path,
			);

			// Add attachment metadata if available
			if ( isset( $media['id'] ) && $media['id'] > 0 ) {
				$metadata = $this->get_attachment_metadata( $media['id'] );
				if ( ! empty( $metadata ) ) {
					$map_entry['metadata'] = $metadata;
				}
			}

			$this->media_map[] = $map_entry;
		}
	}

	/**
	 * Get attachment metadata.
	 *
	 * @param int $attachment_id Attachment ID.
	 * @return array Attachment metadata.
	 */
	private function get_attachment_metadata( $attachment_id ) {
		$attachment = get_post( $attachment_id );
		
		if ( ! $attachment ) {
			return array();
		}

		$metadata = array(
			'id'       => $attachment_id,
			'title'    => $attachment->post_title,
			'caption'  => $attachment->post_excerpt,
			'alt'      => get_post_meta( $attachment_id, '_wp_attachment_image_alt', true ),
			'mime_type' => get_post_mime_type( $attachment_id ),
		);

		// Get attachment metadata (dimensions, file info, etc.)
		$wp_metadata = wp_get_attachment_metadata( $attachment_id );
		
		if ( ! empty( $wp_metadata ) ) {
			// Add dimensions for images
			if ( isset( $wp_metadata['width'] ) && isset( $wp_metadata['height'] ) ) {
				$metadata['width'] = $wp_metadata['width'];
				$metadata['height'] = $wp_metadata['height'];
			}

			// Add file info
			if ( isset( $wp_metadata['file'] ) ) {
				$metadata['file'] = $wp_metadata['file'];
			}

			// Add EXIF data if available (for photos)
			if ( isset( $wp_metadata['image_meta'] ) && ! empty( $wp_metadata['image_meta'] ) ) {
				$metadata['exif'] = $this->filter_exif_data( $wp_metadata['image_meta'] );
			}

			// Add sizes info
			if ( isset( $wp_metadata['sizes'] ) && ! empty( $wp_metadata['sizes'] ) ) {
				$metadata['sizes'] = $wp_metadata['sizes'];
			}
		}

		return $metadata;
	}

	/**
	 * Filter EXIF data to remove sensitive information.
	 *
	 * @param array $exif_data EXIF data.
	 * @return array Filtered EXIF data.
	 */
	private function filter_exif_data( $exif_data ) {
		// Remove GPS coordinates and other potentially sensitive data
		$exclude_keys = array(
			'latitude',
			'longitude',
			'gps',
		);

		$filtered = array();

		foreach ( $exif_data as $key => $value ) {
			$key_lower = strtolower( $key );
			
			$is_excluded = false;
			foreach ( $exclude_keys as $exclude ) {
				if ( strpos( $key_lower, $exclude ) !== false ) {
					$is_excluded = true;
					break;
				}
			}

			if ( ! $is_excluded && ! empty( $value ) ) {
				$filtered[ $key ] = $value;
			}
		}

		return $filtered;
	}

	/**
	 * Save media map to JSON file.
	 *
	 * @return bool True on success, false on failure.
	 */
	public function save_media_map() {
		if ( empty( $this->export_dir ) ) {
			return false;
		}

		$media_dir = trailingslashit( $this->export_dir ) . 'media';
		$map_file = trailingslashit( $media_dir ) . 'media_map.json';

		$json = wp_json_encode( $this->media_map, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES );

		if ( false === $json ) {
			error_log( 'Digital Lobster Exporter: Failed to encode media map to JSON' );
			return false;
		}

		$result = file_put_contents( $map_file, $json );

		if ( false === $result ) {
			error_log( 'Digital Lobster Exporter: Failed to write media_map.json' );
			return false;
		}

		return true;
	}
}
