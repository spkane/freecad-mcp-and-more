"""Thread safety tests for FreeCAD Robust MCP Bridge.

These tests verify that code execution happens on the correct thread
depending on FreeCAD's mode (GUI vs headless).

CRITICAL: In GUI mode, code MUST execute on the main Qt thread.
Executing Qt operations from background threads causes crashes.
This was discovered when Init.py started the bridge before FreeCAD.GuiUp
was True, causing the bridge to use a background thread even in GUI mode.

The tests in this module cover:
    - Thread context verification (main thread vs background thread)
    - Queue processor mode detection and validation
    - Safe execution of GUI operations (document creation, view operations)

See Also:
    freecad/RobustMCPBridge/__init__.py: The fix for the GUI startup race condition
    freecad/RobustMCPBridge/freecad_mcp_bridge/bridge_utils.py: GuiWaiter helper
"""

from __future__ import annotations

import logging
import uuid
import xmlrpc.client
from typing import Any

import pytest

logger = logging.getLogger(__name__)


def _check_gui_available() -> bool:
    """Check if FreeCAD GUI is available via the bridge.

    This function runs at test collection time to determine which tests to skip.
    Connection errors and timeouts are expected when FreeCAD isn't running
    and indicate GUI unavailability.
    """
    try:
        proxy = xmlrpc.client.ServerProxy("http://localhost:9875", allow_none=True)
        result: dict[str, Any] = proxy.execute(  # type: ignore[assignment]
            """
import FreeCAD
_result_ = {"gui_up": bool(FreeCAD.GuiUp)}
""",
            30000,
            None,
        )
        if result.get("success") and result.get("result"):
            return result["result"].get("gui_up", False)
    except (OSError, xmlrpc.client.Fault, TimeoutError) as e:
        # Expected when bridge isn't running - log at debug level
        logger.debug("Bridge GUI check failed (expected if not running): %s", e)
    except Exception as e:
        # Unexpected exceptions - log as warning for debugging
        logger.warning("Unexpected error checking GUI availability: %s", e)
    return False


def _check_headless_mode() -> bool:
    """Check if FreeCAD is running in headless mode.

    Returns True if GUI is not available (either headless mode or bridge unreachable).
    See _check_gui_available() for details on exception handling.
    """
    return not _check_gui_available()


# Skip markers for mode-specific tests
# These are evaluated at test collection time, so _check_gui_available() runs early.
# If the bridge isn't reachable, GUI tests are skipped and headless tests run.
requires_gui = pytest.mark.skipif(
    _check_headless_mode(),
    reason="Test requires FreeCAD GUI mode (running in headless mode)",
)

requires_headless = pytest.mark.skipif(
    _check_gui_available(),
    reason="Test requires FreeCAD headless mode (running in GUI mode)",
)


class TestThreadSafety:
    """Tests to verify thread-safe code execution in FreeCAD MCP Bridge.

    These tests ensure that Python code executed via the MCP bridge runs on
    the appropriate thread depending on FreeCAD's mode:

    - GUI mode: Code must execute on the main Qt thread to safely perform
      Qt operations (document creation, view manipulation, etc.)
    - Headless mode: Code runs on a background thread since there's no
      Qt event loop

    The bridge uses a queue processor that chooses its execution strategy
    based on FreeCAD.GuiUp at startup time. If the bridge starts before
    GuiUp is True, it incorrectly uses a background thread even in GUI mode,
    causing crashes when Qt operations are attempted.
    """

    def test_execution_thread_info(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy
    ) -> None:
        """Test that we can get thread information from executed code.

        This test verifies the thread context regardless of mode.
        """
        code = """
import threading
import FreeCAD

_result_ = {
    "gui_up": FreeCAD.GuiUp,
    "is_main_thread": threading.current_thread() is threading.main_thread(),
    "thread_name": threading.current_thread().name,
}
"""
        result: dict[str, Any] = xmlrpc_proxy.execute(code, 30000, None)  # type: ignore[assignment]

        assert result["success"], f"Execution failed: {result.get('stderr', '')}"
        assert result["result"] is not None

        thread_info = result["result"]
        assert "gui_up" in thread_info
        assert "is_main_thread" in thread_info
        assert "thread_name" in thread_info

    @requires_gui
    def test_gui_mode_executes_on_main_thread(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy
    ) -> None:
        """CRITICAL: In GUI mode, code MUST execute on the main thread.

        If this test fails, it indicates the bridge started before
        FreeCAD.GuiUp was True, causing it to use a background thread
        for queue processing instead of a Qt timer.

        This bug caused SIGABRT crashes when creating documents or
        doing any Qt operations from the background thread.

        See: freecad/RobustMCPBridge/__init__.py for the fix.
        """
        code = """
import threading
import FreeCAD

_result_ = {
    "gui_up": FreeCAD.GuiUp,
    "is_main_thread": threading.current_thread() is threading.main_thread(),
    "thread_name": threading.current_thread().name,
}
"""
        result: dict[str, Any] = xmlrpc_proxy.execute(code, 30000, None)  # type: ignore[assignment]

        assert result["success"], f"Execution failed: {result.get('stderr', '')}"
        assert result["result"] is not None

        thread_info = result["result"]

        # Verify GUI is up
        assert thread_info["gui_up"], "FreeCAD should be in GUI mode for this test"

        # CRITICAL: Code must execute on main thread in GUI mode
        # The is_main_thread check is the authoritative test - thread names can vary
        # by Python version and platform, but main thread identity is reliable.
        assert thread_info["is_main_thread"], (
            f"CRITICAL BUG: In GUI mode, code is executing on background thread "
            f"'{thread_info['thread_name']}' instead of main thread!\n"
            f"This will cause crashes when doing Qt operations.\n"
            f"Check that Init.py waits for FreeCAD.GuiUp before starting the bridge."
        )

    @requires_gui
    def test_gui_mode_can_create_document_safely(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy
    ) -> None:
        """Test that document creation works in GUI mode.

        Document creation involves Qt operations internally. If the bridge
        is executing on a background thread, this will crash FreeCAD.
        """
        # Use unique document name to avoid collisions with parallel tests
        doc_name = f"TestThreadSafety_{uuid.uuid4().hex[:8]}"
        code = f"""
import FreeCAD

doc_name = {doc_name!r}
doc = None
created = False

try:
    # Create a temporary document
    doc = FreeCAD.newDocument(doc_name)

    # Verify it was created
    created = doc is not None and doc.Name == doc_name
finally:
    # Clean up - always close document if it exists
    if doc_name in [d.Name for d in FreeCAD.listDocuments().values()]:
        FreeCAD.closeDocument(doc_name)

_result_ = {{"success": created, "doc_name": doc_name}}
"""
        result: dict[str, Any] = xmlrpc_proxy.execute(code, 30000, None)  # type: ignore[assignment]

        # If we get here without crash, the test passed
        assert result["success"], f"Execution failed: {result.get('stderr', '')}"
        assert result["result"] is not None
        assert result["result"]["success"], "Failed to create document"

    @requires_headless
    def test_headless_mode_uses_background_thread(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy
    ) -> None:
        """In headless mode, the bridge uses a background thread for queue processing.

        This is expected behavior in headless mode since there's no Qt event loop.
        """
        code = """
import threading
import FreeCAD

_result_ = {
    "gui_up": FreeCAD.GuiUp,
    "is_main_thread": threading.current_thread() is threading.main_thread(),
    "thread_name": threading.current_thread().name,
}
"""
        result: dict[str, Any] = xmlrpc_proxy.execute(code, 30000, None)  # type: ignore[assignment]

        assert result["success"], f"Execution failed: {result.get('stderr', '')}"
        assert result["result"] is not None

        thread_info = result["result"]

        # Verify headless mode
        assert not thread_info["gui_up"], (
            "FreeCAD should be in headless mode for this test"
        )

        # In headless mode, background thread is expected
        assert not thread_info["is_main_thread"], (
            "In headless mode, expected background thread for queue processing"
        )

    @requires_gui
    def test_gui_mode_view_operations_safe(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy
    ) -> None:
        """Test that view operations work safely in GUI mode.

        View operations require the GUI and must be on the main thread.
        """
        # Use unique document name to avoid collisions with parallel tests
        doc_name = f"TestViewOps_{uuid.uuid4().hex[:8]}"
        code = f"""
import FreeCAD
import FreeCADGui

doc_name = {doc_name!r}
has_view = False
visible = None

try:
    # Create a document
    doc = FreeCAD.newDocument(doc_name)

    # Create an object
    box = doc.addObject("Part::Box", "TestBox")
    doc.recompute()

    # Try to access view properties (will fail on background thread)
    view_obj = box.ViewObject
    has_view = view_obj is not None

    # Check visibility
    visible = view_obj.Visibility if has_view else None
finally:
    # Clean up - always close document if it exists
    if doc_name in [d.Name for d in FreeCAD.listDocuments().values()]:
        FreeCAD.closeDocument(doc_name)

_result_ = {{
    "has_view_object": has_view,
    "visibility": visible,
}}
"""
        result: dict[str, Any] = xmlrpc_proxy.execute(code, 30000, None)  # type: ignore[assignment]

        assert result["success"], f"Execution failed: {result.get('stderr', '')}"
        assert result["result"] is not None
        assert result["result"]["has_view_object"], "Should have ViewObject in GUI mode"
        assert result["result"]["visibility"] is True, (
            "Object should be visible by default"
        )


class TestBridgeQueueProcessor:
    """Tests for the bridge's queue processor mode detection.

    The queue processor is responsible for executing Python code in FreeCAD.
    Its mode (Qt timer vs background thread) must match FreeCAD's GUI state:

    - FreeCAD.GuiUp = True → Queue processor uses Qt timer (main thread)
    - FreeCAD.GuiUp = False → Queue processor uses background thread

    A mismatch between these indicates a race condition bug where the bridge
    started before FreeCAD.GuiUp was properly set, which was the root cause
    of SIGABRT crashes in GUI mode.
    """

    def test_queue_processor_mode_matches_gui_state(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy
    ) -> None:
        """Verify the queue processor mode matches FreeCAD's GUI state.

        The bridge should use:
        - Qt timer (main thread) when FreeCAD.GuiUp is True
        - Background thread when FreeCAD.GuiUp is False

        A mismatch indicates the bridge started before FreeCAD.GuiUp
        was set, which is the root cause of the GUI crash bug.
        """
        code = """
import threading
import FreeCAD

gui_up = FreeCAD.GuiUp
is_main_thread = threading.current_thread() is threading.main_thread()
thread_name = threading.current_thread().name

# Expected behavior:
# - GUI mode (GuiUp=True) -> Main thread (Qt timer)
# - Headless mode (GuiUp=False) -> Background thread

mode_correct = (gui_up and is_main_thread) or (not gui_up and not is_main_thread)

_result_ = {
    "gui_up": gui_up,
    "is_main_thread": is_main_thread,
    "thread_name": thread_name,
    "mode_correct": mode_correct,
}
"""
        result: dict[str, Any] = xmlrpc_proxy.execute(code, 30000, None)  # type: ignore[assignment]

        assert result["success"], f"Execution failed: {result.get('stderr', '')}"
        assert result["result"] is not None

        info = result["result"]

        assert info["mode_correct"], (
            f"Queue processor mode mismatch!\n"
            f"  FreeCAD.GuiUp: {info['gui_up']}\n"
            f"  is_main_thread: {info['is_main_thread']}\n"
            f"  thread_name: {info['thread_name']}\n"
            f"Expected: GUI mode uses main thread, headless uses background thread.\n"
            f"This mismatch indicates Init.py started the bridge before "
            f"FreeCAD.GuiUp was True."
        )
