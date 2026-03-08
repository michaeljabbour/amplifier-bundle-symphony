"""Tests for SymphonyTool class and mount() function."""

from __future__ import annotations

import pytest

from amplifier_module_tool_symphony import SymphonyTool, mount
from amplifier_module_tool_symphony.client import SymphonyError


# ---------------------------------------------------------------------------
# SymphonyTool — static properties  (sync — NO asyncio mark needed)
# ---------------------------------------------------------------------------


def test_name(mock_symphony_client) -> None:
    """Tool name must be 'symphony'."""
    tool = SymphonyTool(mock_symphony_client)
    assert tool.name == "symphony"


def test_description_mentions_operations(mock_symphony_client) -> None:
    """Description must mention all three operations: status, issue, refresh."""
    tool = SymphonyTool(mock_symphony_client)
    desc = tool.description.lower()
    assert "status" in desc
    assert "issue" in desc
    assert "refresh" in desc


def test_input_schema_valid(mock_symphony_client) -> None:
    """input_schema must be a valid JSON Schema object with required fields."""
    tool = SymphonyTool(mock_symphony_client)
    schema = tool.input_schema
    assert schema["type"] == "object"
    assert "operation" in schema["properties"]
    assert "identifier" in schema["properties"]
    assert "operation" in schema["required"]


# ---------------------------------------------------------------------------
# SymphonyTool — execute()  (async)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_status(mock_symphony_client) -> None:
    """execute({'operation': 'status'}) returns successful ToolResult with status data."""
    tool = SymphonyTool(mock_symphony_client)
    result = await tool.execute({"operation": "status"})
    assert result.success is True
    assert result.output == mock_symphony_client.status_response


@pytest.mark.asyncio
async def test_execute_issue(mock_symphony_client) -> None:
    """execute({'operation': 'issue', 'identifier': 'MT-649'}) returns issue data."""
    tool = SymphonyTool(mock_symphony_client)
    result = await tool.execute({"operation": "issue", "identifier": "MT-649"})
    assert result.success is True
    assert result.output == mock_symphony_client.issue_response


@pytest.mark.asyncio
async def test_execute_refresh(mock_symphony_client) -> None:
    """execute({'operation': 'refresh'}) returns successful ToolResult with refresh data."""
    tool = SymphonyTool(mock_symphony_client)
    result = await tool.execute({"operation": "refresh"})
    assert result.success is True
    assert result.output == mock_symphony_client.refresh_response


@pytest.mark.asyncio
async def test_execute_issue_missing_identifier(mock_symphony_client) -> None:
    """execute({'operation': 'issue'}) without identifier returns error ToolResult."""
    tool = SymphonyTool(mock_symphony_client)
    result = await tool.execute({"operation": "issue"})
    assert result.success is False
    assert "identifier" in result.error["message"].lower()


@pytest.mark.asyncio
async def test_execute_invalid_operation(mock_symphony_client) -> None:
    """execute({'operation': 'banana'}) returns error ToolResult."""
    tool = SymphonyTool(mock_symphony_client)
    result = await tool.execute({"operation": "banana"})
    assert result.success is False


@pytest.mark.asyncio
async def test_execute_client_error(mock_symphony_client) -> None:
    """SymphonyError raised by client is caught and returned as failed ToolResult."""
    error_message = "Symphony is down"

    async def failing_get_status() -> dict:
        raise SymphonyError(error_message)

    mock_symphony_client.get_status = failing_get_status

    tool = SymphonyTool(mock_symphony_client)
    result = await tool.execute({"operation": "status"})
    assert result.success is False
    assert error_message in result.error["message"]


# ---------------------------------------------------------------------------
# mount()  (async)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mount_registers_tool(mock_coordinator) -> None:
    """mount() mounts exactly one tool named 'symphony' and returns a cleanup callable."""
    cleanup = await mount(mock_coordinator, config={})
    assert len(mock_coordinator.mounted) == 1
    assert mock_coordinator.mounted[0]["name"] == "symphony"
    assert callable(cleanup)
    await cleanup()


@pytest.mark.asyncio
async def test_mount_with_config(mock_coordinator) -> None:
    """mount() accepts a custom symphony_url in config and still mounts the tool."""
    cleanup = await mount(
        mock_coordinator,
        config={"symphony_url": "http://custom:9999"},
    )
    assert len(mock_coordinator.mounted) == 1
    await cleanup()


@pytest.mark.asyncio
async def test_mount_none_config(mock_coordinator) -> None:
    """mount() does not crash when config=None and still mounts the tool."""
    cleanup = await mount(mock_coordinator, config=None)
    assert len(mock_coordinator.mounted) == 1
    await cleanup()
