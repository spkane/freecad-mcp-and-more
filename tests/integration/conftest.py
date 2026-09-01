"""Pytest configuration for integration tests.

This module handles connection checking and provides hard error behavior
when the FreeCAD Robust MCP Bridge is not available. Connection failures are
treated as test errors, not skips.

Instance ID Verification:
    The FreeCAD Robust MCP Bridge generates a unique instance ID at startup which is
    printed to stdout. Tests can capture this ID and verify they're connected
    to the expected instance using the `bridge_instance_id` fixture or by
    calling proxy.get_instance_id().
"""

from __future__ import annotations

import os
import xmlrpc.client
from typing import Any

import pytest

# Global flag to track bridge availability (checked once per session)
_bridge_available: bool | None = None
_bridge_error: str | None = None
_bridge_instance_id: str | None = None
_gui_available: bool | None = None
_connection_checked: bool = False


def _check_bridge_connection() -> tuple[bool, str | None, str | None]:
    """Check if the FreeCAD Robust MCP Bridge is available and get its instance ID.

    Returns:
        Tuple of (is_available, error_message, instance_id)
    """
    global _bridge_available, _bridge_error, _bridge_instance_id, _gui_available

    if _bridge_available is not None:
        return _bridge_available, _bridge_error, _bridge_instance_id

    try:
        proxy = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
        result: dict[str, Any] = proxy.ping()  # type: ignore[assignment]
        if result.get("pong"):
            _bridge_available = True
            _bridge_error = None
            # The ping response includes instance_id
            _bridge_instance_id = result.get("instance_id")

            # Check if GUI is available by executing code to check FreeCAD.GuiUp
            try:
                gui_check: dict[str, Any] = proxy.execute(  # type: ignore[assignment]
                    """
import FreeCAD
_result_ = {"gui_up": bool(FreeCAD.GuiUp)}
""",
                    30000,
                    None,
                )
                if gui_check.get("success") and gui_check.get("result"):
                    _gui_available = gui_check["result"].get("gui_up", False)
                else:
                    # Execution failed, assume headless
                    _gui_available = False
            except Exception:
                # If execute fails, assume headless
                _gui_available = False
        else:
            _bridge_available = False
            _bridge_error = "FreeCAD Robust MCP Bridge not responding to ping"
            _bridge_instance_id = None
            _gui_available = None
    except ConnectionRefusedError:
        _bridge_available = False
        _bridge_error = "Connection refused - FreeCAD Robust MCP Bridge not running"
        _bridge_instance_id = None
        _gui_available = None
    except Exception as e:
        _bridge_available = False
        _bridge_error = f"Cannot connect to FreeCAD Robust MCP Bridge: {e}"
        _bridge_instance_id = None
        _gui_available = None

    return _bridge_available, _bridge_error, _bridge_instance_id


def is_gui_available() -> bool:
    """Check if FreeCAD GUI is available.

    Returns:
        True if running in GUI mode, False if headless or bridge unavailable.

    Note:
        When the bridge is unavailable, this returns False. The
        pytest_collection_modifyitems hook will raise a hard error in this case,
        so tests won't actually run with an incorrect skip condition.
    """
    # Ensure bridge check has been performed
    _check_bridge_connection()
    return _gui_available is True


def is_headless_mode() -> bool:
    """Check if FreeCAD is running in headless mode.

    Returns:
        True if running in headless mode, False if GUI is available.

    Note:
        When the bridge is unavailable, this returns True (assumes headless).
        The pytest_collection_modifyitems hook will raise a hard error before
        any tests run, so this assumption doesn't affect actual test execution.
    """
    return not is_gui_available()


def _should_skip_for_gui_requirement() -> bool:
    """Return True if test should be skipped due to requiring GUI mode.

    Returns False when:
    - Bridge is available and in GUI mode

    Returns True when:
    - Bridge is unavailable (will fail anyway, skip is irrelevant)
    - Bridge is available and in headless mode
    """
    _check_bridge_connection()
    return _gui_available is not True


def _should_skip_for_headless_requirement() -> bool:
    """Return True if test should be skipped due to requiring headless mode.

    Returns False when:
    - Bridge is unavailable (collection will fail anyway)
    - Bridge is available and in headless mode

    Returns True when:
    - Bridge is available and in GUI mode
    """
    _check_bridge_connection()
    if not _bridge_available:
        return False  # Don't skip, let collection error handle it
    return _gui_available is True  # Skip if in GUI mode


# Skip markers for mode-specific tests
# These markers handle the bridge unavailable case by deferring to
# pytest_collection_modifyitems which raises a hard error.
requires_gui = pytest.mark.skipif(
    _should_skip_for_gui_requirement(),
    reason="Test requires FreeCAD GUI mode (running in headless mode)",
)

requires_headless = pytest.mark.skipif(
    _should_skip_for_headless_requirement(),
    reason="Test requires FreeCAD headless mode (running in GUI mode)",
)


def pytest_collection_modifyitems(
    config: pytest.Config,  # noqa: ARG001
    items: list[pytest.Item],
) -> None:
    """Verify bridge connection for integration tests.

    This runs once during test collection. If the bridge is not available,
    this raises a hard error instead of skipping tests.

    Exception: Tests marked with `standalone_freecad` start their own FreeCAD
    process and don't require a pre-existing bridge connection.
    """
    global _connection_checked

    # Filter to only integration tests in this directory
    integration_tests = [
        item for item in items if "tests/integration" in str(item.fspath)
    ]

    if not integration_tests:
        return

    # Check if all tests are standalone (they start their own FreeCAD)
    # These tests don't need a pre-existing bridge connection
    nonStandaloneTests = [
        item
        for item in integration_tests
        if not any(mark.name == "standalone_freecad" for mark in item.iter_markers())
    ]

    # If all tests are standalone, skip the bridge check entirely
    if not nonStandaloneTests:
        return

    # Check bridge connection once
    is_available, error, _instance_id = _check_bridge_connection()

    if not is_available and not _connection_checked:
        _connection_checked = True
        pytest.fail(
            f"\n\n{'=' * 60}\n"
            f"INTEGRATION TEST ERROR: FreeCAD Robust MCP Bridge not available\n"
            f"{'=' * 60}\n\n"
            f"Error: {error}\n\n"
            f"To run integration tests, start FreeCAD with the MCP bridge:\n"
            f"  • GUI mode:      just freecad::run-gui\n"
            f"  • Headless mode: just freecad::run-headless\n\n"
            f"Then run the tests again.\n"
            f"{'=' * 60}\n",
            pytrace=False,
        )


def pytest_terminal_summary(
    terminalreporter: Any,
    exitstatus: int,  # noqa: ARG001
    config: pytest.Config,  # noqa: ARG001
) -> None:
    """Print a summary of FreeCAD connection status at the end of test run.

    This provides clear visibility into which mode was used and confirms
    successful connection.
    """
    # Only show summary if we ran integration tests that needed the bridge.
    # _connection_checked is set when non-standalone tests required a bridge;
    # _bridge_available is None when no check was performed at all.
    # When only standalone_freecad tests ran, skip the summary to avoid a
    # misleading "FAILED" message (standalone tests manage their own FreeCAD).
    if _bridge_available is None:
        return
    if not _connection_checked and not _bridge_available:
        return

    # Build the summary message
    terminalreporter.write_sep("=", "FreeCAD Robust MCP Bridge Status")

    if _bridge_available:
        mode = "GUI" if _gui_available else "Headless"
        terminalreporter.write_line("  Connection: SUCCESS")
        terminalreporter.write_line(f"  Mode:       {mode}")
        if _bridge_instance_id:
            terminalreporter.write_line(f"  Instance:   {_bridge_instance_id}")
    else:
        terminalreporter.write_line("  Connection: FAILED")
        if _bridge_error:
            terminalreporter.write_line(f"  Warning:    {_bridge_error}")

    terminalreporter.write_line("")


@pytest.fixture(scope="module")
def xmlrpc_proxy() -> xmlrpc.client.ServerProxy:
    """Create XML-RPC proxy to FreeCAD Robust MCP Bridge.

    This fixture is shared across all integration test modules.
    The connection check has already been performed during collection.
    """
    is_available, error, _ = _check_bridge_connection()
    if not is_available:
        pytest.skip(error or "FreeCAD Robust MCP Bridge not available")

    return xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)


@pytest.fixture(scope="module")
def bridge_instance_id() -> str | None:
    """Get the instance ID of the connected FreeCAD Robust MCP Bridge.

    This fixture returns the unique instance ID that was generated when
    the bridge started. Use this to verify you're connected to the expected
    bridge instance.

    Returns:
        The instance ID string, or None if not available.
    """
    is_available, _, instance_id = _check_bridge_connection()
    if not is_available:
        return None
    return instance_id


@pytest.fixture(scope="module")
def expected_bridge_instance_id() -> str | None:
    """Get the expected bridge instance ID from environment variable.

    When running tests that start the bridge themselves (e.g., in CI),
    the startup script can capture the instance ID from the bridge's
    stdout and set it as EXPECTED_BRIDGE_INSTANCE_ID environment variable.

    Returns:
        The expected instance ID from env, or None if not set.
    """
    return os.environ.get("EXPECTED_BRIDGE_INSTANCE_ID")


@pytest.fixture(scope="module")
def freecad_gui_available() -> bool:
    """Check if FreeCAD GUI is available.

    This fixture returns True if FreeCAD is running in GUI mode,
    False if running in headless mode. Use this to conditionally
    skip tests that require GUI features.

    Returns:
        True if GUI is available, False if headless.

    Example:
        def test_screenshot(freecad_gui_available):
            if not freecad_gui_available:
                pytest.skip("Test requires GUI mode")
            # ... test that needs GUI
    """
    return is_gui_available()


@pytest.fixture(scope="module")
def freecad_is_headless() -> bool:
    """Check if FreeCAD is running in headless mode.

    This fixture returns True if FreeCAD is running in headless mode
    (no GUI), False if GUI is available.

    Returns:
        True if headless, False if GUI is available.

    Example:
        def test_some_feature(freecad_is_headless):
            if freecad_is_headless:
                pytest.skip("Test requires GUI mode")
            # ... test that needs GUI
    """
    return is_headless_mode()


def verify_bridge_instance(
    proxy: xmlrpc.client.ServerProxy,
    expected_id: str | None,
) -> bool:
    """Verify we're connected to the expected bridge instance.

    Args:
        proxy: XML-RPC proxy to the bridge.
        expected_id: Expected instance ID, or None to skip verification.

    Returns:
        True if verification passed or was skipped (no expected_id).

    Raises:
        AssertionError: If instance ID doesn't match expected.
    """
    if expected_id is None:
        return True

    result: dict[str, Any] = proxy.get_instance_id()  # type: ignore[assignment]
    actual_id = result.get("instance_id")

    if actual_id != expected_id:
        msg = (
            f"Bridge instance ID mismatch!\n"
            f"  Expected: {expected_id}\n"
            f"  Actual:   {actual_id}\n"
            f"This may indicate you're connected to a different bridge instance."
        )
        raise AssertionError(msg)

    return True
