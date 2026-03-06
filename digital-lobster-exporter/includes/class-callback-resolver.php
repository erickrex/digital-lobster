<?php
/**
 * Callback Resolver Utility
 *
 * Resolves PHP callables to descriptive arrays containing type, name,
 * and optional class, method, file, and line information.
 *
 * Consolidates the duplicated get_callback_info() logic from
 * Hooks_Scanner, Shortcode_Scanner, REST_API_Scanner, and Plugin_Scanner.
 *
 * @package Digital_Lobster_Exporter
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Class Digital_Lobster_Exporter_Callback_Resolver
 *
 * Static utility that resolves any PHP callable to a descriptive array.
 */
class Digital_Lobster_Exporter_Callback_Resolver {

	/**
	 * Resolve a PHP callable to a descriptive array.
	 *
	 * Handles all callback forms: string function names, array [class/object, method]
	 * pairs, Closure instances, invokable objects, and unknown types.
	 *
	 * @param mixed $callback Any PHP callable.
	 * @return array {
	 *     type:    string ('function'|'method'|'closure'|'invokable'|'unknown'),
	 *     name:    string,
	 *     class?:  string,
	 *     method?: string,
	 *     file?:   string,
	 *     line?:   int
	 * }
	 */
	public static function resolve( $callback ) {
		if ( is_string( $callback ) ) {
			return self::resolve_string( $callback );
		}

		if ( is_array( $callback ) && count( $callback ) === 2 ) {
			return self::resolve_array( $callback );
		}

		if ( is_object( $callback ) && ( $callback instanceof Closure ) ) {
			return self::resolve_closure( $callback );
		}

		if ( is_object( $callback ) ) {
			return self::resolve_invokable( $callback );
		}

		return array(
			'type' => 'unknown',
			'name' => 'Unknown',
		);
	}

	/**
	 * Resolve a string function name callback.
	 *
	 * @param string $callback Function name.
	 * @return array Callback description.
	 */
	private static function resolve_string( $callback ) {
		$info = array(
			'type' => 'function',
			'name' => $callback,
		);

		try {
			if ( function_exists( $callback ) ) {
				$reflection    = new ReflectionFunction( $callback );
				$info['file'] = $reflection->getFileName();
				$info['line'] = $reflection->getStartLine();
			}
		} catch ( Exception $e ) {
			// Reflection failed, continue without file/line.
		}

		return $info;
	}

	/**
	 * Resolve an array [class/object, method] callback.
	 *
	 * @param array $callback Array with class/object and method name.
	 * @return array Callback description.
	 */
	private static function resolve_array( $callback ) {
		$class  = is_object( $callback[0] ) ? get_class( $callback[0] ) : $callback[0];
		$method = $callback[1];

		$info = array(
			'type'   => 'method',
			'class'  => $class,
			'method' => $method,
			'name'   => $class . '::' . $method,
		);

		try {
			if ( method_exists( $class, $method ) ) {
				$reflection    = new ReflectionMethod( $class, $method );
				$info['file'] = $reflection->getFileName();
				$info['line'] = $reflection->getStartLine();
			}
		} catch ( Exception $e ) {
			// Reflection failed, continue without file/line.
		}

		return $info;
	}

	/**
	 * Resolve a Closure callback.
	 *
	 * @param Closure $callback Closure instance.
	 * @return array Callback description.
	 */
	private static function resolve_closure( $callback ) {
		$info = array(
			'type' => 'closure',
			'name' => 'Closure',
		);

		try {
			$reflection    = new ReflectionFunction( $callback );
			$info['file'] = $reflection->getFileName();
			$info['line'] = $reflection->getStartLine();
		} catch ( Exception $e ) {
			// Reflection failed, continue without file/line.
		}

		return $info;
	}

	/**
	 * Resolve an invokable object callback.
	 *
	 * @param object $callback Invokable object with __invoke method.
	 * @return array Callback description.
	 */
	private static function resolve_invokable( $callback ) {
		$class = get_class( $callback );

		$info = array(
			'type'  => 'invokable',
			'class' => $class,
			'name'  => $class . '::__invoke',
		);

		try {
			$reflection    = new ReflectionMethod( $callback, '__invoke' );
			$info['file'] = $reflection->getFileName();
			$info['line'] = $reflection->getStartLine();
		} catch ( Exception $e ) {
			// Reflection failed, continue without file/line.
		}

		return $info;
	}
}
