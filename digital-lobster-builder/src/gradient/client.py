from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from gradient import (
    AsyncGradient,
    AuthenticationError,
    APITimeoutError,
    RateLimitError,
)
from pydantic import BaseModel

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "llama-3.3-70b-versatile"
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1.0
BACKOFF_MULTIPLIER = 2.0


class GradientClient:
    """Thin wrapper around gradientai-sdk for LLM inference."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        max_retries: int = MAX_RETRIES,
        initial_backoff: float = INITIAL_BACKOFF_SECONDS,
    ) -> None:
        self._sdk = AsyncGradient(
            model_access_key=api_key,
            max_retries=0,  # We handle retries ourselves
        )
        self._default_model = model
        self._max_retries = max_retries
        self._initial_backoff = initial_backoff

    async def complete(
        self,
        messages: list[dict],
        model: str | None = None,
        response_format: type | None = None,
    ) -> str:
        """Send a chat completion request to Gradient AI Platform.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            model: Model identifier. Falls back to the default model.
            response_format: Optional type hint (unused by SDK directly,
                reserved for future JSON-mode support).

        Returns:
            The assistant's response text.

        Raises:
            AuthenticationError: Immediately on 401/403 responses.
            APITimeoutError: After exhausting all retries on timeout.
            RateLimitError: After exhausting all retries on rate limit.
        """
        extra_body: dict[str, Any] | None = None
        if response_format is not None:
            extra_body = {
                "response_format": {"type": "json_object"},
            }

        return await self._call_with_retry(
            model=model or self._default_model,
            messages=messages,
            extra_body=extra_body,
        )

    async def complete_structured(
        self,
        messages: list[dict],
        schema: type[BaseModel],
        model: str | None = None,
    ) -> dict:
        """Request structured JSON output conforming to a Pydantic model.

        Instructs the LLM to return JSON matching the provided Pydantic
        schema, then validates and returns the parsed dict.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            schema: A Pydantic BaseModel subclass describing the output shape.
            model: Model identifier. Falls back to the default model.

        Returns:
            A dict conforming to the Pydantic schema.

        Raises:
            AuthenticationError: Immediately on 401/403 responses.
            ValueError: If the LLM response is not valid JSON or doesn't
                conform to the schema.
        """
        json_schema = schema.model_json_schema()
        system_msg = (
            "You MUST respond with valid JSON that conforms to this schema:\n"
            f"{json.dumps(json_schema, indent=2)}\n"
            "Return ONLY the JSON object, no other text."
        )

        augmented: list[dict] = [
            {"role": "system", "content": system_msg},
            *messages,
        ]

        raw = await self._call_with_retry(
            model=model or self._default_model,
            messages=augmented,
            extra_body={"response_format": {"type": "json_object"}},
        )

        parsed = json.loads(raw)
        # Validate against the schema — raises ValidationError on mismatch
        validated = schema.model_validate(parsed)
        return validated.model_dump()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _call_with_retry(
        self,
        *,
        model: str,
        messages: list[dict],
        extra_body: dict[str, Any] | None = None,
    ) -> str:
        """Execute a chat completion with retry logic.

        - Authentication errors (401/403): fail immediately.
        - Timeouts: retry up to ``_max_retries`` with exponential backoff.
        - Rate limits (429): respect ``Retry-After`` header, then retry.
        """
        backoff = self._initial_backoff

        for attempt in range(1, self._max_retries + 1):
            try:
                response = await self._sdk.chat.completions.create(
                    model=model,
                    messages=messages,
                    extra_body=extra_body,
                )
                content = response.choices[0].message.content
                if content is None:
                    return ""
                return content

            except AuthenticationError:
                # Never retry auth failures — surface immediately
                logger.error("Gradient authentication failed. Check your API key.")
                raise

            except APITimeoutError:
                if attempt == self._max_retries:
                    logger.error(
                        "Gradient request timed out after %d attempts.", attempt
                    )
                    raise
                logger.warning(
                    "Gradient timeout (attempt %d/%d), retrying in %.1fs…",
                    attempt,
                    self._max_retries,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff *= BACKOFF_MULTIPLIER

            except RateLimitError as exc:
                if attempt == self._max_retries:
                    logger.error(
                        "Gradient rate limit exceeded after %d attempts.", attempt
                    )
                    raise
                retry_after = self._parse_retry_after(exc)
                wait = retry_after if retry_after is not None else backoff
                logger.warning(
                    "Gradient rate limited (attempt %d/%d), retrying in %.1fs…",
                    attempt,
                    self._max_retries,
                    wait,
                )
                await asyncio.sleep(wait)
                backoff *= BACKOFF_MULTIPLIER

        # Should be unreachable, but satisfy the type checker
        raise RuntimeError("Exhausted retries without raising")  # pragma: no cover

    @staticmethod
    def _parse_retry_after(exc: RateLimitError) -> float | None:
        """Extract Retry-After seconds from a RateLimitError response."""
        try:
            header = exc.response.headers.get("Retry-After")
            if header is not None:
                return float(header)
        except (AttributeError, ValueError):
            pass
        return None

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._sdk.close()
