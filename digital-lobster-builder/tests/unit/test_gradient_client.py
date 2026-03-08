from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from gradient import AuthenticationError, APITimeoutError, RateLimitError

from src.gradient.client import (
    BACKOFF_MULTIPLIER,
    DEFAULT_MODEL,
    GradientClient,
    INITIAL_BACKOFF_SECONDS,
    MAX_RETRIES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_completion_response(content: str = "hello") -> MagicMock:
    """Build a mock CompletionCreateResponse."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _make_rate_limit_error(retry_after: str | None = None) -> RateLimitError:
    """Build a RateLimitError with an optional Retry-After header."""
    headers = {}
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    response = httpx.Response(
        status_code=429,
        headers=headers,
        request=httpx.Request("POST", "https://api.gradient.ai"),
    )
    return RateLimitError("rate limited", response=response, body=None)


def _make_auth_error() -> AuthenticationError:
    response = httpx.Response(
        status_code=401,
        request=httpx.Request("POST", "https://api.gradient.ai"),
    )
    return AuthenticationError("unauthorized", response=response, body=None)


def _make_timeout_error() -> APITimeoutError:
    request = httpx.Request("POST", "https://api.gradient.ai")
    return APITimeoutError(request=request)


# ---------------------------------------------------------------------------
# Tests — complete()
# ---------------------------------------------------------------------------

class TestComplete:
    """Tests for GradientClient.complete()."""

    async def test_returns_content_on_success(self):
        client = GradientClient(api_key="test-key")
        mock_resp = _make_completion_response("world")
        client._sdk.chat.completions.create = AsyncMock(return_value=mock_resp)

        result = await client.complete([{"role": "user", "content": "hi"}])
        assert result == "world"

    async def test_uses_default_model(self):
        client = GradientClient(api_key="test-key")
        mock_resp = _make_completion_response()
        client._sdk.chat.completions.create = AsyncMock(return_value=mock_resp)

        await client.complete([{"role": "user", "content": "hi"}])
        call_kwargs = client._sdk.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == DEFAULT_MODEL

    async def test_uses_custom_model(self):
        client = GradientClient(api_key="test-key")
        mock_resp = _make_completion_response()
        client._sdk.chat.completions.create = AsyncMock(return_value=mock_resp)

        await client.complete(
            [{"role": "user", "content": "hi"}], model="custom-model"
        )
        call_kwargs = client._sdk.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "custom-model"

    async def test_returns_empty_string_on_none_content(self):
        client = GradientClient(api_key="test-key")
        mock_resp = _make_completion_response("ignored")
        mock_resp.choices[0].message.content = None
        client._sdk.chat.completions.create = AsyncMock(return_value=mock_resp)

        result = await client.complete([{"role": "user", "content": "hi"}])
        assert result == ""

    async def test_passes_json_response_format(self):
        client = GradientClient(api_key="test-key")
        mock_resp = _make_completion_response('{"a":1}')
        client._sdk.chat.completions.create = AsyncMock(return_value=mock_resp)

        await client.complete(
            [{"role": "user", "content": "hi"}], response_format=dict
        )
        call_kwargs = client._sdk.chat.completions.create.call_args.kwargs
        assert call_kwargs["extra_body"] == {
            "response_format": {"type": "json_object"}
        }


# ---------------------------------------------------------------------------
# Tests — complete_structured()
# ---------------------------------------------------------------------------

class TestCompleteStructured:
    """Tests for GradientClient.complete_structured()."""

    async def test_returns_validated_dict(self):
        from pydantic import BaseModel

        class MySchema(BaseModel):
            name: str
            count: int

        client = GradientClient(api_key="test-key")
        mock_resp = _make_completion_response('{"name": "foo", "count": 42}')
        client._sdk.chat.completions.create = AsyncMock(return_value=mock_resp)

        result = await client.complete_structured(
            [{"role": "user", "content": "give me data"}], schema=MySchema
        )
        assert result == {"name": "foo", "count": 42}

    async def test_raises_on_invalid_json(self):
        from pydantic import BaseModel

        class MySchema(BaseModel):
            name: str

        client = GradientClient(api_key="test-key")
        mock_resp = _make_completion_response("not json at all")
        client._sdk.chat.completions.create = AsyncMock(return_value=mock_resp)

        with pytest.raises(Exception):
            await client.complete_structured(
                [{"role": "user", "content": "hi"}], schema=MySchema
            )

    async def test_raises_on_schema_mismatch(self):
        from pydantic import BaseModel, ValidationError

        class MySchema(BaseModel):
            name: str
            count: int

        client = GradientClient(api_key="test-key")
        # Valid JSON but missing required 'count' field
        mock_resp = _make_completion_response('{"name": "foo"}')
        client._sdk.chat.completions.create = AsyncMock(return_value=mock_resp)

        with pytest.raises(ValidationError):
            await client.complete_structured(
                [{"role": "user", "content": "hi"}], schema=MySchema
            )

    async def test_prepends_system_message_with_schema(self):
        from pydantic import BaseModel

        class MySchema(BaseModel):
            value: str

        client = GradientClient(api_key="test-key")
        mock_resp = _make_completion_response('{"value": "ok"}')
        client._sdk.chat.completions.create = AsyncMock(return_value=mock_resp)

        await client.complete_structured(
            [{"role": "user", "content": "hi"}], schema=MySchema
        )
        call_kwargs = client._sdk.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert "value" in messages[0]["content"]
        assert messages[1] == {"role": "user", "content": "hi"}


# ---------------------------------------------------------------------------
# Tests — retry logic
# ---------------------------------------------------------------------------

class TestRetryLogic:
    """Tests for retry behavior on timeouts, rate limits, and auth errors."""

    async def test_auth_error_fails_immediately(self):
        client = GradientClient(api_key="bad-key")
        client._sdk.chat.completions.create = AsyncMock(
            side_effect=_make_auth_error()
        )

        with pytest.raises(AuthenticationError):
            await client.complete([{"role": "user", "content": "hi"}])

        # Should have been called exactly once — no retries
        assert client._sdk.chat.completions.create.call_count == 1

    async def test_timeout_retries_up_to_max(self):
        client = GradientClient(
            api_key="test-key", max_retries=3, initial_backoff=0.0
        )
        client._sdk.chat.completions.create = AsyncMock(
            side_effect=_make_timeout_error()
        )

        with pytest.raises(APITimeoutError):
            await client.complete([{"role": "user", "content": "hi"}])

        assert client._sdk.chat.completions.create.call_count == 3

    async def test_timeout_succeeds_on_later_attempt(self):
        client = GradientClient(
            api_key="test-key", max_retries=3, initial_backoff=0.0
        )
        mock_resp = _make_completion_response("recovered")
        client._sdk.chat.completions.create = AsyncMock(
            side_effect=[_make_timeout_error(), mock_resp]
        )

        result = await client.complete([{"role": "user", "content": "hi"}])
        assert result == "recovered"
        assert client._sdk.chat.completions.create.call_count == 2

    async def test_rate_limit_retries_with_retry_after_header(self):
        client = GradientClient(
            api_key="test-key", max_retries=3, initial_backoff=0.0
        )
        mock_resp = _make_completion_response("ok")
        client._sdk.chat.completions.create = AsyncMock(
            side_effect=[_make_rate_limit_error(retry_after="0.0"), mock_resp]
        )

        with patch("src.gradient.client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await client.complete([{"role": "user", "content": "hi"}])

        assert result == "ok"
        # Should have slept with the Retry-After value (0.0)
        mock_sleep.assert_called_once_with(0.0)

    async def test_rate_limit_falls_back_to_backoff_without_header(self):
        client = GradientClient(
            api_key="test-key", max_retries=3, initial_backoff=0.5
        )
        mock_resp = _make_completion_response("ok")
        client._sdk.chat.completions.create = AsyncMock(
            side_effect=[_make_rate_limit_error(retry_after=None), mock_resp]
        )

        with patch("src.gradient.client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await client.complete([{"role": "user", "content": "hi"}])

        assert result == "ok"
        # Should have slept with the initial backoff
        mock_sleep.assert_called_once_with(0.5)

    async def test_rate_limit_exhausts_retries(self):
        client = GradientClient(
            api_key="test-key", max_retries=2, initial_backoff=0.0
        )
        client._sdk.chat.completions.create = AsyncMock(
            side_effect=_make_rate_limit_error()
        )

        with pytest.raises(RateLimitError):
            await client.complete([{"role": "user", "content": "hi"}])

        assert client._sdk.chat.completions.create.call_count == 2

    async def test_exponential_backoff_on_timeout(self):
        client = GradientClient(
            api_key="test-key", max_retries=3, initial_backoff=1.0
        )
        client._sdk.chat.completions.create = AsyncMock(
            side_effect=_make_timeout_error()
        )

        with patch("src.gradient.client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(APITimeoutError):
                await client.complete([{"role": "user", "content": "hi"}])

        # Backoff: 1.0, then 2.0 (1.0 * 2.0)
        sleep_values = [call.args[0] for call in mock_sleep.call_args_list]
        assert sleep_values == [1.0, 2.0]


# ---------------------------------------------------------------------------
# Tests — _parse_retry_after
# ---------------------------------------------------------------------------

class TestParseRetryAfter:
    """Tests for Retry-After header parsing."""

    def test_parses_numeric_header(self):
        exc = _make_rate_limit_error(retry_after="2.5")
        assert GradientClient._parse_retry_after(exc) == 2.5

    def test_returns_none_for_missing_header(self):
        exc = _make_rate_limit_error(retry_after=None)
        assert GradientClient._parse_retry_after(exc) is None

    def test_returns_none_for_non_numeric_header(self):
        exc = _make_rate_limit_error(retry_after="not-a-number")
        assert GradientClient._parse_retry_after(exc) is None
