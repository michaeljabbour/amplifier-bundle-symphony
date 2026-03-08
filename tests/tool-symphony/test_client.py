"""Tests for amplifier_module_tool_symphony.client"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio
import respx

from amplifier_module_tool_symphony.client import SymphonyClient, SymphonyError

BASE_URL = "http://symphony-test:4000"

# pytest-asyncio runs in STRICT mode when invoked from the repo root
# (asyncio_mode="auto" lives in the module's pyproject.toml which is not the
# rootdir config file at that point). Apply the marker to every test in this
# module so we don't need per-function decorators.
pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def client() -> SymphonyClient:  # type: ignore[misc]
    """Yield a fresh SymphonyClient and close it after each test."""
    c = SymphonyClient(BASE_URL)
    yield c  # type: ignore[misc]
    await c.close()


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_status_success(client: SymphonyClient) -> None:
    """GET /api/v1/state returns the parsed JSON dict."""
    payload = {"running": 3, "retrying": 1, "codex_totals": {"total": 42}}
    respx.get(f"{BASE_URL}/api/v1/state").mock(
        return_value=httpx.Response(200, json=payload)
    )

    result = await client.get_status()

    assert result["running"] == 3
    assert result["retrying"] == 1
    assert result["codex_totals"]["total"] == 42


@respx.mock
async def test_get_issue_success(client: SymphonyClient) -> None:
    """GET /api/v1/MT-649 returns the parsed issue dict."""
    payload = {"id": "MT-649", "title": "Fix auth bug", "status": "open"}
    respx.get(f"{BASE_URL}/api/v1/MT-649").mock(
        return_value=httpx.Response(200, json=payload)
    )

    result = await client.get_issue("MT-649")

    assert result["id"] == "MT-649"
    assert result["title"] == "Fix auth bug"
    assert result["status"] == "open"


@respx.mock
async def test_refresh_success(client: SymphonyClient) -> None:
    """POST /api/v1/refresh returns the parsed dict."""
    payload = {"queued": True}
    respx.post(f"{BASE_URL}/api/v1/refresh").mock(
        return_value=httpx.Response(200, json=payload)
    )

    result = await client.refresh()

    assert result["queued"] is True


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_issue_not_found(client: SymphonyClient) -> None:
    """404 raises SymphonyError immediately (no retry) with the status code."""
    respx.get(f"{BASE_URL}/api/v1/NOPE").mock(
        return_value=httpx.Response(404, json={"error": "not found"})
    )

    with pytest.raises(SymphonyError) as exc_info:
        await client.get_issue("NOPE")

    assert exc_info.value.status_code == 404


@respx.mock
async def test_retry_on_503(client: SymphonyClient) -> None:
    """503 on first attempt triggers a retry; succeeds on the second attempt."""
    payload = {"running": 1, "retrying": 0, "codex_totals": {}}
    route = respx.get(f"{BASE_URL}/api/v1/state")
    route.side_effect = [
        httpx.Response(503),
        httpx.Response(200, json=payload),
    ]

    with patch("asyncio.sleep"):  # skip real backoff delays in tests
        result = await client.get_status()

    assert result["running"] == 1
    assert route.call_count == 2


@respx.mock
async def test_connection_error(client: SymphonyClient) -> None:
    """Connection errors exhaust all retries then raise SymphonyError."""
    respx.get(f"{BASE_URL}/api/v1/state").mock(
        side_effect=httpx.ConnectError("Connection refused")
    )

    with patch("asyncio.sleep"):
        with pytest.raises(SymphonyError) as exc_info:
            await client.get_status()

    assert "Connection refused" in str(exc_info.value)


@respx.mock
async def test_timeout_error(client: SymphonyClient) -> None:
    """Read timeout exhausts all retries then raises SymphonyError."""
    respx.get(f"{BASE_URL}/api/v1/state").mock(
        side_effect=httpx.ReadTimeout("timed out")
    )

    with patch("asyncio.sleep"):
        with pytest.raises(SymphonyError) as exc_info:
            await client.get_status()

    assert "timed out" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@respx.mock
async def test_close(client: SymphonyClient) -> None:
    """Client can be closed without raising, and close() is idempotent."""
    # Initialise the underlying httpx client by making one real request.
    respx.get(f"{BASE_URL}/api/v1/state").mock(
        return_value=httpx.Response(200, json={"running": 0})
    )
    await client.get_status()

    # First explicit close — should not raise.
    await client.close()

    # Second close — must also be safe (idempotent).
    await client.close()
    # (the fixture also calls close() a third time during teardown — still fine)
