"""RED test: verifies the module scaffold exists and has correct metadata."""

from __future__ import annotations


def test_module_type_marker() -> None:
    """__amplifier_module_type__ must be 'tool'."""
    from amplifier_module_tool_symphony import __amplifier_module_type__

    assert __amplifier_module_type__ == "tool"
