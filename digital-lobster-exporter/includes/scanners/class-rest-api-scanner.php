<?php
/**
 * REST API Scanner Class
 *
 * Documents all registered REST API endpoints including routes, methods,
 * namespaces, arguments, authentication requirements, and source identification.
 *
 * @package Digital_Lobster_Exporter
 */

// If this file is called directly, abort.
if ( ! defined( 'WPINC' ) ) {
	die;
}

/**
 * REST API Scanner Class
 */
class Digital_Lobster_Exporter_REST_API_Scanner extends Digital_Lobster_Exporter_Scanner_Base {

	/**
	 * WordPress core namespaces.
	 *
	 * @var array
	 */
	private $core_namespaces = array(
		'wp/v2',
		'wp-site-health/v1',
		'wp-block-editor/v1',
		'oembed/1.0',
	);

	/**
	 * Constructor.
	 *
	 * @param array $deps Optional. Associative array of dependencies.
	 */
	public function __construct( array $deps = array() ) {
		parent::__construct( $deps );
	}

	/**
	 * Run the REST API scan.
	 *
	 * @return array Scan results.
	 */
	public function scan() {
		$results = array(
			'success' => true,
			'message' => 'REST API endpoints scan completed',
			'data'    => array(),
		);

		try {
			// Get REST server instance.
			$rest_server = rest_get_server();

			// Get all registered routes.
			$routes = $rest_server->get_routes();

			// Build the endpoints documentation.
			$documentation = $this->build_documentation( $routes );

			$results['data'] = array(
				'total_routes'       => count( $routes ),
				'core_endpoints'     => $documentation['summary']['core_endpoints'],
				'custom_endpoints'   => $documentation['summary']['custom_endpoints'],
				'total_namespaces'   => count( $documentation['namespaces'] ),
			);

		} catch ( Exception $e ) {
			$results['success'] = false;
			$results['message'] = 'REST API scan failed: ' . $e->getMessage();
		}

		return $results;
	}

	/**
	 * Build complete REST API documentation.
	 *
	 * @param array $routes All registered routes.
	 * @return array Documentation structure.
	 */
	private function build_documentation( $routes ) {
		$endpoints = array();
		$namespaces = array();
		$core_count = 0;
		$custom_count = 0;

		foreach ( $routes as $route => $route_data ) {
			// Parse route information.
			$endpoint_info = $this->parse_endpoint( $route, $route_data );

			if ( $endpoint_info ) {
				$endpoints[] = $endpoint_info;

				// Track namespaces.
				$namespace = $endpoint_info['namespace'];
				if ( ! isset( $namespaces[ $namespace ] ) ) {
					$namespaces[ $namespace ] = array(
						'namespace'  => $namespace,
						'is_core'    => $this->is_core_namespace( $namespace ),
						'endpoints'  => array(),
						'source'     => $endpoint_info['source'],
					);
				}
				$namespaces[ $namespace ]['endpoints'][] = $route;

				// Count core vs custom.
				if ( $endpoint_info['is_core'] ) {
					$core_count++;
				} else {
					$custom_count++;
				}
			}
		}

		// Sort endpoints by route.
		usort( $endpoints, function( $a, $b ) {
			return strcmp( $a['route'], $b['route'] );
		});

		// Convert namespaces to array and sort.
		$namespaces_array = array_values( $namespaces );
		usort( $namespaces_array, function( $a, $b ) {
			return strcmp( $a['namespace'], $b['namespace'] );
		});

		return array(
			'schema_version' => 1,
			'generated_at'   => current_time( 'mysql', true ),
			'summary'        => array(
				'total_endpoints'  => count( $endpoints ),
				'core_endpoints'   => $core_count,
				'custom_endpoints' => $custom_count,
				'total_namespaces' => count( $namespaces_array ),
			),
			'namespaces'     => $namespaces_array,
			'endpoints'      => $endpoints,
			'core_endpoints' => $this->filter_endpoints( $endpoints, true ),
			'custom_endpoints' => $this->filter_endpoints( $endpoints, false ),
		);
	}

	/**
	 * Parse endpoint information from route data.
	 *
	 * @param string $route Route path.
	 * @param array  $route_data Route configuration.
	 * @return array|null Endpoint information.
	 */
	private function parse_endpoint( $route, $route_data ) {
		if ( empty( $route_data ) || ! is_array( $route_data ) ) {
			return null;
		}

		// Extract namespace from route.
		$namespace = $this->extract_namespace( $route );
		$is_core = $this->is_core_namespace( $namespace );

		// Get methods and their configurations.
		$methods = array();
		foreach ( $route_data as $endpoint ) {
			if ( ! isset( $endpoint['methods'] ) ) {
				continue;
			}

			$endpoint_methods = $this->parse_methods( $endpoint['methods'] );

			foreach ( $endpoint_methods as $method ) {
				if ( ! isset( $methods[ $method ] ) ) {
					$methods[ $method ] = array(
						'method'              => $method,
						'callback'            => $this->get_callback_info( $endpoint ),
						'permission_callback' => $this->get_permission_info( $endpoint ),
						'args'                => $this->parse_arguments( $endpoint ),
						'authentication'      => $this->determine_authentication( $endpoint ),
					);
				}
			}
		}

		if ( empty( $methods ) ) {
			return null;
		}

		return array(
			'route'       => $route,
			'namespace'   => $namespace,
			'is_core'     => $is_core,
			'methods'     => array_values( $methods ),
			'source'      => $this->identify_endpoint_source( $route_data ),
			'description' => $this->extract_description( $route_data ),
		);
	}

	/**
	 * Extract namespace from route path.
	 *
	 * @param string $route Route path.
	 * @return string Namespace.
	 */
	private function extract_namespace( $route ) {
		// Remove leading slash.
		$route = ltrim( $route, '/' );

		// Extract namespace (everything before the second slash or end).
		$parts = explode( '/', $route );

		if ( count( $parts ) >= 2 ) {
			return $parts[0] . '/' . $parts[1];
		} elseif ( count( $parts ) === 1 ) {
			return $parts[0];
		}

		return 'unknown';
	}

	/**
	 * Check if namespace is from WordPress core.
	 *
	 * @param string $namespace Namespace.
	 * @return bool True if core namespace.
	 */
	private function is_core_namespace( $namespace ) {
		return in_array( $namespace, $this->core_namespaces, true );
	}

	/**
	 * Parse HTTP methods from endpoint configuration.
	 *
	 * @param mixed $methods Methods configuration.
	 * @return array Array of method names.
	 */
	private function parse_methods( $methods ) {
		$parsed = array();

		if ( is_string( $methods ) ) {
			$parsed[] = strtoupper( $methods );
		} elseif ( is_array( $methods ) ) {
			foreach ( $methods as $method => $enabled ) {
				if ( $enabled ) {
					$parsed[] = strtoupper( $method );
				}
			}
		}

		return $parsed;
	}

	/**
	 * Get callback information.
	 *
	 * @param array $endpoint Endpoint configuration.
	 * @return array Callback info.
	 */
	private function get_callback_info( $endpoint ) {
		if ( ! isset( $endpoint['callback'] ) ) {
			return array(
				'type' => 'unknown',
				'name' => 'Unknown',
			);
		}

		return Digital_Lobster_Exporter_Callback_Resolver::resolve( $endpoint['callback'] );
	}

	/**
	 * Get permission callback information.
	 *
	 * @param array $endpoint Endpoint configuration.
	 * @return array Permission info.
	 */
	private function get_permission_info( $endpoint ) {
		if ( ! isset( $endpoint['permission_callback'] ) ) {
			return array(
				'type'        => 'none',
				'description' => 'No permission callback defined',
			);
		}

		$callback = $endpoint['permission_callback'];

		// Check for common permission callbacks.
		if ( $callback === '__return_true' ) {
			return array(
				'type'        => 'public',
				'description' => 'Public endpoint - no authentication required',
			);
		}

		$info = array(
			'type'        => 'custom',
			'description' => 'Custom permission callback',
		);

		if ( is_string( $callback ) ) {
			$info['callback'] = $callback;

			// Check for common WordPress permission functions.
			if ( strpos( $callback, 'current_user_can' ) !== false ) {
				$info['type'] = 'capability';
				$info['description'] = 'Requires user capability';
			} elseif ( strpos( $callback, 'is_user_logged_in' ) !== false ) {
				$info['type'] = 'authenticated';
				$info['description'] = 'Requires authenticated user';
			}
		} elseif ( is_array( $callback ) && count( $callback ) === 2 ) {
			$class  = is_object( $callback[0] ) ? get_class( $callback[0] ) : $callback[0];
			$method = $callback[1];
			$info['callback'] = $class . '::' . $method;
		}

		return $info;
	}

	/**
	 * Parse endpoint arguments.
	 *
	 * @param array $endpoint Endpoint configuration.
	 * @return array Arguments information.
	 */
	private function parse_arguments( $endpoint ) {
		if ( ! isset( $endpoint['args'] ) || ! is_array( $endpoint['args'] ) ) {
			return array();
		}

		$args = array();

		foreach ( $endpoint['args'] as $arg_name => $arg_config ) {
			$arg_info = array(
				'name'     => $arg_name,
				'required' => isset( $arg_config['required'] ) ? (bool) $arg_config['required'] : false,
			);

			// Add type information.
			if ( isset( $arg_config['type'] ) ) {
				$arg_info['type'] = $arg_config['type'];
			}

			// Add description.
			if ( isset( $arg_config['description'] ) ) {
				$arg_info['description'] = $arg_config['description'];
			}

			// Add default value.
			if ( isset( $arg_config['default'] ) ) {
				$arg_info['default'] = $arg_config['default'];
			}

			// Add enum values.
			if ( isset( $arg_config['enum'] ) && is_array( $arg_config['enum'] ) ) {
				$arg_info['enum'] = $arg_config['enum'];
			}

			// Add format.
			if ( isset( $arg_config['format'] ) ) {
				$arg_info['format'] = $arg_config['format'];
			}

			// Add validation callback info.
			if ( isset( $arg_config['validate_callback'] ) ) {
				$arg_info['has_validation'] = true;
			}

			// Add sanitization callback info.
			if ( isset( $arg_config['sanitize_callback'] ) ) {
				$arg_info['has_sanitization'] = true;
			}

			$args[] = $arg_info;
		}

		return $args;
	}

	/**
	 * Determine authentication requirements.
	 *
	 * @param array $endpoint Endpoint configuration.
	 * @return array Authentication info.
	 */
	private function determine_authentication( $endpoint ) {
		$auth = array(
			'required' => false,
			'type'     => 'none',
		);

		// Check permission callback.
		if ( isset( $endpoint['permission_callback'] ) ) {
			$callback = $endpoint['permission_callback'];

			if ( $callback !== '__return_true' ) {
				$auth['required'] = true;
				$auth['type'] = 'custom';

				// Try to determine auth type from callback.
				if ( is_string( $callback ) ) {
					if ( strpos( $callback, 'current_user_can' ) !== false ) {
						$auth['type'] = 'cookie';
						$auth['description'] = 'WordPress cookie authentication';
					} elseif ( strpos( $callback, 'is_user_logged_in' ) !== false ) {
						$auth['type'] = 'cookie';
						$auth['description'] = 'Requires logged-in user';
					}
				}
			}
		}

		return $auth;
	}

	/**
	 * Identify the source plugin or theme for an endpoint.
	 *
	 * @param array $route_data Route configuration.
	 * @return array Source information.
	 */
	private function identify_endpoint_source( $route_data ) {
		// Try to identify from the first endpoint's callback.
		foreach ( $route_data as $endpoint ) {
			if ( ! isset( $endpoint['callback'] ) ) {
				continue;
			}

			$resolved = Digital_Lobster_Exporter_Callback_Resolver::resolve( $endpoint['callback'] );

			if ( isset( $resolved['file'] ) && ! empty( $resolved['file'] ) ) {
				return Digital_Lobster_Exporter_Source_Identifier::identify( $resolved['file'] );
			}
		}

		return array(
			'type' => 'unknown',
			'name' => 'Unknown',
		);
	}

	/**
	 * Extract description from route data.
	 *
	 * @param array $route_data Route configuration.
	 * @return string Description.
	 */
	private function extract_description( $route_data ) {
		foreach ( $route_data as $endpoint ) {
			if ( isset( $endpoint['schema']['description'] ) ) {
				return $endpoint['schema']['description'];
			}
		}

		return '';
	}

	/**
	 * Filter endpoints by core/custom status.
	 *
	 * @param array $endpoints All endpoints.
	 * @param bool  $is_core True for core, false for custom.
	 * @return array Filtered endpoints.
	 */
	private function filter_endpoints( $endpoints, $is_core ) {
		return array_values( array_filter( $endpoints, function( $endpoint ) use ( $is_core ) {
			return $endpoint['is_core'] === $is_core;
		}));
	}

}
