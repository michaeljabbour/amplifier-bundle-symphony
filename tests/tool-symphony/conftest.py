"""Shared fixtures for tool-symphony tests."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

# Ensure the module package is importable without installing it.
_MODULE_ROOT = (
    Path(__file__).resolve().parent.parent.parent / "modules" / "tool-symphony"
)
if str(_MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(_MODULE_ROOT))


class MockCoordinator:
    """Records what gets mounted without needing the real Amplifier runtime."""

    def __init__(self) -> None:
        self.mounted: list[dict[str, Any]] = []

    async def mount(self, category: str, tool: Any, name: str = "") -> None:
        self.mounted.append({"category": category, "tool": tool, "name": name})


class MockSymphonyClient:
    """Minimal stand-in for SymphonyClient used in tool-level tests."""

    def __init__(self) -> None:
        self.status_response: dict[str, Any] = {
            "running": [],
            "retrying": [],
            "codex_totals": {},
        }
        self.issue_response: dict[str, Any] = {
            "issue_identifier": "MT-649",
            "status": "running",
        }
        self.refresh_response: dict[str, Any] = {"queued": True}
        self.closed: bool = False

    async def get_status(self) -> dict[str, Any]:
        return self.status_response

    async def get_issue(self, identifier: str) -> dict[str, Any]:
        return self.issue_response

    async def refresh(self) -> dict[str, Any]:
        return self.refresh_response

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def mock_coordinator() -> MockCoordinator:
    return MockCoordinator()


@pytest.fixture
def mock_symphony_client() -> MockSymphonyClient:
    return MockSymphonyClient()
