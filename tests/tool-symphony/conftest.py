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


@pytest.fixture
def mock_coordinator() -> MockCoordinator:
    return MockCoordinator()
