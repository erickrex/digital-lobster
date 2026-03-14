from __future__ import annotations

import re
from typing import Any, Iterable

import httpx

from src.models.strapi_types import StrapiContentTypeDefinition, StrapiFieldDefinition

HEALTH_PROBE_PATHS = ("/_health", "/admin")
ADMIN_READY_STATUS_CODES = {200, 301, 302, 307, 308}


def bearer_headers(
    token: str,
    *,
    include_json_content_type: bool = False,
) -> dict[str, str]:
    """Return standard Strapi bearer-token headers."""
    headers = {"Authorization": f"Bearer {token}"}
    if include_json_content_type:
        headers["Content-Type"] = "application/json"
    return headers


def is_healthy_probe(path: str, status_code: int) -> bool:
    """Return whether a probe response means Strapi is ready."""
    if path == "/_health":
        return status_code == 200
    if path == "/admin":
        return status_code in ADMIN_READY_STATUS_CODES
    return False


async def probe_health(
    base_url: str,
    *,
    timeout: float = 10.0,
    client: httpx.AsyncClient | None = None,
) -> tuple[str, int] | None:
    """Return the first healthy Strapi probe result, if any."""
    normalized_base_url = base_url.rstrip("/")

    async def _run(request_client: httpx.AsyncClient) -> tuple[str, int] | None:
        for path in HEALTH_PROBE_PATHS:
            resp = await request_client.get(f"{normalized_base_url}{path}")
            if is_healthy_probe(path, resp.status_code):
                return path, resp.status_code
        return None

    if client is not None:
        return await _run(client)

    async with httpx.AsyncClient(timeout=timeout) as request_client:
        return await _run(request_client)


async def describe_health_status(
    base_url: str,
    *,
    timeout: float = 10.0,
) -> str:
    """Return a human-readable health status string for Strapi."""
    try:
        result = await probe_health(base_url, timeout=timeout)
        if result is not None:
            path, status_code = result
            return f"{status_code} ({path})"

        async with httpx.AsyncClient(timeout=timeout) as client:
            last_status_code = 0
            last_path = HEALTH_PROBE_PATHS[-1]
            for path in HEALTH_PROBE_PATHS:
                resp = await client.get(f"{base_url.rstrip('/')}{path}")
                last_status_code = resp.status_code
                last_path = path
            return f"{last_status_code} ({last_path})"
    except httpx.HTTPError as exc:
        return f"unreachable ({exc})"


def build_content_type_attributes(
    fields: Iterable[StrapiFieldDefinition],
) -> dict[str, Any]:
    """Translate ``StrapiFieldDefinition`` objects into Strapi attributes."""
    attributes: dict[str, Any] = {}
    for field in fields:
        attr: dict[str, Any] = {
            "type": field.strapi_type,
            "required": field.required,
        }
        if field.relation_target:
            attr["target"] = field.relation_target
            attr["relation"] = field.relation_type or "oneToMany"
        attributes[field.name] = attr
    return attributes


def content_type_builder_payload(
    definition: StrapiContentTypeDefinition,
) -> dict[str, Any]:
    """Build the Content-Type Builder payload for a Strapi content type."""
    return {
        "contentType": {
            "displayName": definition.display_name,
            "singularName": definition.singularName,
            "pluralName": definition.pluralName,
            "attributes": build_content_type_attributes(definition.fields),
        },
    }


async def post_builder_component(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    payload: dict[str, Any],
    *,
    timeout: float = 30.0,
) -> httpx.Response:
    """POST a component payload to the Strapi Content-Type Builder API."""
    return await client.post(
        f"{base_url.rstrip('/')}/content-type-builder/components",
        json=payload,
        headers=bearer_headers(token),
        timeout=timeout,
    )


async def post_builder_content_type(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    payload: dict[str, Any],
    *,
    timeout: float = 30.0,
) -> httpx.Response:
    """POST a content type payload to the Strapi Content-Type Builder API."""
    return await client.post(
        f"{base_url.rstrip('/')}/content-type-builder/content-types",
        json=payload,
        headers=bearer_headers(token),
        timeout=timeout,
    )


def rest_endpoint_for_plural_name(plural_name: str) -> str:
    """Return the canonical Strapi REST path for a collection plural name."""
    slug = re.sub(r"[^a-z0-9]+", "-", plural_name.lower()).strip("-")
    return f"/api/{slug}"


def fallback_rest_endpoint(api_id: str) -> str:
    """Best-effort REST endpoint derivation for legacy ``api::type.type`` IDs."""
    resource = api_id.split(".")[-1] if "." in api_id else api_id
    if resource.endswith("y") and not resource.endswith("ey"):
        plural_name = resource[:-1] + "ies"
    elif resource.endswith(("s", "sh", "ch", "x", "z")):
        plural_name = resource + "es"
    else:
        plural_name = resource + "s"
    return rest_endpoint_for_plural_name(plural_name)
