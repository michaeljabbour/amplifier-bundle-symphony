"""Symphony orchestration service tool module."""

from __future__ import annotations

import os
from typing import Any

__amplifier_module_type__ = "tool"


# ---------------------------------------------------------------------------
# Fallback ToolResult (used when amplifier_core is not installed)
# Mirrors amplifier_core.ToolResult: output (not data), error as dict | None.
# ---------------------------------------------------------------------------


class _FallbackToolResult:
    """Minimal ToolResult stand-in for environments without amplifier_core."""

    def __init__(
        self,
        *,
        success: bool,
        output: Any = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        self.success = success
        self.output = output
        self.error = error


# ---------------------------------------------------------------------------
# SymphonyTool
# ---------------------------------------------------------------------------


class SymphonyTool:
    """Amplifier tool for the Symphony orchestration service.

    Supports three operations:
    - ``status``  — fetch current running/retrying issue status.
    - ``issue``   — fetch details for a specific issue by identifier.
    - ``refresh`` — trigger a Symphony refresh cycle.
    """

    name = "symphony"

    def __init__(self, client: Any) -> None:
        self._client = client

    @property
    def description(self) -> str:
        return (
            "Interact with the Symphony orchestration service. "
            "Supported operations: "
            "'status' — get current running/retrying issue status; "
            "'issue' — get details for a specific issue by identifier; "
            "'refresh' — trigger a Symphony refresh."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["status", "issue", "refresh"],
                    "description": "The operation to perform.",
                },
                "identifier": {
                    "type": "string",
                    "description": (
                        "Issue identifier (required for the 'issue' operation, "
                        "e.g. 'MT-649')."
                    ),
                },
            },
            "required": ["operation"],
        }

    async def execute(self, input: dict[str, Any]) -> Any:  # -> ToolResult
        try:
            from amplifier_core import ToolResult  # type: ignore[import]
        except ImportError:
            ToolResult = _FallbackToolResult  # type: ignore[assignment,misc]

        operation = input.get("operation")

        try:
            if operation == "status":
                data = await self._client.get_status()
            elif operation == "issue":
                identifier = input.get("identifier")
                if not identifier:
                    return ToolResult(
                        success=False,
                        error={"message": "Missing required parameter: identifier"},
                    )
                data = await self._client.get_issue(identifier)
            elif operation == "refresh":
                data = await self._client.refresh()
            else:
                return ToolResult(
                    success=False,
                    error={
                        "message": (
                            f"Unknown operation: {operation!r}. "
                            "Valid operations: status, issue, refresh."
                        )
                    },
                )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error={"message": str(exc)})

        return ToolResult(success=True, output=data)


# ---------------------------------------------------------------------------
# mount()
# ---------------------------------------------------------------------------


async def mount(coordinator: Any, config: dict[str, Any] | None = None) -> Any:
    """Register :class:`SymphonyTool` with *coordinator* and return a cleanup callable.

    Config keys
    -----------
    symphony_url
        Base URL for the Symphony API.
        Falls back to the ``SYMPHONY_URL`` environment variable, then
        ``http://localhost:4000``.
    timeout_seconds
        Request timeout in seconds (default: 30).
    connect_timeout_seconds
        Connection timeout in seconds (default: 5).

    Returns
    -------
    Async callable that closes the underlying HTTP client when awaited.
    """
    from amplifier_module_tool_symphony.client import SymphonyClient

    cfg: dict[str, Any] = config or {}
    url: str = cfg.get("symphony_url") or os.environ.get(
        "SYMPHONY_URL", "http://localhost:4000"
    )
    timeout: float = float(cfg.get("timeout_seconds", 30))
    connect_timeout: float = float(cfg.get("connect_timeout_seconds", 5))

    client = SymphonyClient(url, timeout=timeout, connect_timeout=connect_timeout)
    tool = SymphonyTool(client)

    await coordinator.mount("tools", tool, name=tool.name)

    async def cleanup() -> None:
        await client.close()

    return cleanup
