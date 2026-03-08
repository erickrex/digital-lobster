from typing import Any

REDACTED = "***REDACTED***"

# Case-insensitive key patterns that indicate sensitive data
_SENSITIVE_KEY_PATTERNS: set[str] = {
    "do_token",
    "strapi_admin_password",
    "strapi_api_token",
    "ssh_private_key",
    "api_token",
    "password",
    "secret",
    "token",
}

_SSH_PRIVATE_KEY_MARKER = "-----BEGIN"

def _is_sensitive_key(key: str) -> bool:
    """Check if a dict key matches any sensitive pattern (case-insensitive)."""
    lower = key.lower()
    return any(pattern in lower for pattern in _SENSITIVE_KEY_PATTERNS)

def _contains_ssh_key(value: str) -> bool:
    """Check if a string value looks like an SSH private key."""
    return _SSH_PRIVATE_KEY_MARKER in value

def scrub_credentials(data: Any) -> Any:
    """Recursively scrub sensitive credentials from data structures.

    Walks dicts and lists, redacting values for keys matching sensitive
    patterns and string values containing SSH private key markers.

    Args:
        data: Any data structure (dict, list, str, or primitive).

    Returns:
        A copy of the data with sensitive values replaced by REDACTED.
    """
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if isinstance(key, str) and _is_sensitive_key(key):
                result[key] = REDACTED
            else:
                result[key] = scrub_credentials(value)
        return result
    elif isinstance(data, list):
        return [scrub_credentials(item) for item in data]
    elif isinstance(data, str) and _contains_ssh_key(data):
        return REDACTED
    return data
