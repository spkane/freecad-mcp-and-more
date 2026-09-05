"""FreeCAD Robust MCP Bridge Plugin - Socket Server with Queue-based Thread Safety.

This module provides a socket server that runs inside FreeCAD to handle
MCP bridge requests. It must be executed within FreeCAD's Python environment.

Design inspired by neka-nat/freecad-mcp (MIT License):
- Queue-based GUI communication for thread safety
- XML-RPC compatibility mode (port 9875)
- Screenshot capture with view type detection

Attribution:
    The queue-based thread safety pattern and XML-RPC protocol design were
    inspired by neka-nat/freecad-mcp (https://github.com/neka-nat/freecad-mcp),
    which is licensed under the MIT License. This implementation is a complete
    rewrite with additional features (JSON-RPC 2.0, async socket server).
"""

from __future__ import annotations

import asyncio
import atexit
import contextlib
import errno
import io
import json
import os
import queue
import sys
import tempfile
import threading
import time
import traceback
import uuid
import weakref
import xmlrpc.server
from contextlib import redirect_stderr, redirect_stdout
from typing import Any

# Global registry of active servers for cleanup on Python exit
# Uses weak references to avoid preventing garbage collection
_activeServers: weakref.WeakSet[FreecadMCPPlugin] = weakref.WeakSet()
_atexitRegistered = False


def _xmlrpc_safe_text(value: str) -> str:
    """Replace characters that XML 1.0 cannot represent."""
    return "".join(
        character
        if (
            ord(character) in {0x09, 0x0A, 0x0D}
            or 0x20 <= ord(character) <= 0xD7FF
            or 0xE000 <= ord(character) <= 0xFFFD
            or 0x10000 <= ord(character) <= 0x10FFFF
        )
        else "\N{REPLACEMENT CHARACTER}"
        for character in value
    )


def _xmlrpc_safe_value(value: Any) -> Any:
    """Recursively normalize a value for Python's XML-RPC marshaller."""
    if isinstance(value, str):
        return _xmlrpc_safe_text(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return value if -(2**31) <= value < 2**31 else str(value)
    if isinstance(value, dict):
        return {
            _xmlrpc_safe_text(str(key)): _xmlrpc_safe_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple | set):
        return [_xmlrpc_safe_value(item) for item in value]
    if value is None or isinstance(value, bool | float):
        return value
    return _xmlrpc_safe_text(str(value))


def _get_shiboken_delete() -> Any:
    """Get the shiboken delete function for explicit Qt object destruction.

    Returns:
        The shiboken delete function, or None if not available.
    """
    # Try shiboken6 first (PySide6), then shiboken2 (PySide2)
    with contextlib.suppress(ImportError):
        import shiboken6

        return shiboken6.delete  # type: ignore[attr-defined]

    with contextlib.suppress(ImportError):
        import shiboken2

        return shiboken2.delete  # type: ignore[attr-defined]

    return None


def _cleanup_all_servers() -> None:
    """Clean up all active MCP servers before Python exits.

    This is registered with atexit to ensure QTimer objects are properly
    destroyed BEFORE Python's garbage collector runs during Py_FinalizeEx.

    QTimer objects are only created when ``FreeCAD.GuiUp`` is True (GUI mode).
    In headless mode no Qt timers exist, so this function is effectively a
    no-op—each server's ``_cleanup_for_exit`` will find no timers to destroy.

    This atexit handler **must** run before ``Py_FinalizeEx`` to avoid Qt
    signal-disconnect crashes.  During startup there is a race window where
    timers may not yet exist if the GUI has not finished initialising; the
    cleanup is safe regardless because ``_cleanup_for_exit`` guards every
    timer operation with ``if self._timer`` / ``if self._status_timer``.

    The key insight is that ``deleteLater()`` doesn't work during shutdown
    because:

    1. ``deleteLater()`` schedules deletion for the next event loop iteration
    2. The event loop isn't running during atexit
    3. So Python's GC tries to finalize the PySide wrapper objects
    4. The PySide destructor triggers Qt's ``disconnectNotify`` callback
    5. ``disconnectNotify`` tries to do Python operations → crash

    The fix is to use ``shiboken.delete()`` to explicitly destroy the Qt/C++
    object immediately, which marks the PySide wrapper as invalid so Python's
    GC won't try to destroy it again.

    IMPORTANT: This runs during Python finalization when Qt GUI elements
    (like QMainWindow) may already be destroyed. We must NOT access any
    GUI elements here - only stop timers and threads.
    """
    for server in list(_activeServers):
        # Always call _cleanup_for_exit, even if server._running is False.
        # A server may have timers allocated from a failed startup that
        # still need explicit shiboken.delete() to avoid GC crashes.
        # _cleanup_for_exit is safe to call multiple times.
        # Ignore errors during cleanup - we're shutting down anyway.
        with contextlib.suppress(Exception):
            server._cleanup_for_exit()


# These imports only work inside FreeCAD
try:
    import FreeCAD
    import FreeCADGui

    FREECAD_AVAILABLE = True
except ImportError:
    FREECAD_AVAILABLE = False

# Default configuration
DEFAULT_SOCKET_PORT = 9876
DEFAULT_XMLRPC_PORT = 9875
QUEUE_POLL_INTERVAL_MS = 50
STATUS_UPDATE_INTERVAL_MS = 5000  # Update status bar every 5 seconds
HEADLESS_POLL_INTERVAL_S = 0.1  # Headless mode poll interval in seconds


def _get_qt_core() -> Any:
    """Get the QtCore module if GUI mode is available.

    This helper checks if FreeCAD is available with GUI enabled and
    attempts to import QtCore from PySide2 or PySide6.

    Returns:
        The QtCore module if available in GUI mode, None otherwise.
    """
    if not (FREECAD_AVAILABLE and FreeCAD.GuiUp):
        return None

    # Try PySide2 first, then PySide6
    with contextlib.suppress(ImportError):
        from PySide2 import QtCore

        return QtCore

    with contextlib.suppress(ImportError):
        from PySide6 import QtCore

        return QtCore

    return None


class ExecutionRequest:
    """Represents a code execution request."""

    def __init__(
        self,
        code: str,
        timeout_ms: int = 30000,
        request_id: str | None = None,
        transaction: str | None = None,
    ) -> None:
        """Initialize execution request.

        Args:
            code: Python code to execute.
            timeout_ms: Execution timeout in milliseconds.
            request_id: Optional request ID for tracking.
            transaction: Undo transaction name to arm, or None for read-only.
        """
        self.code = code
        self.timeout_ms = timeout_ms
        self.request_id = request_id
        self.transaction = transaction
        self.result: dict[str, Any] | None = None
        self.completed = threading.Event()
        self._state_lock = threading.Lock()
        self._started = False
        self._cancelled = False

    def start_if_pending(self) -> bool:
        """Mark this request started unless its caller already timed out."""
        with self._state_lock:
            if self._cancelled:
                return False
            self._started = True
            return True

    def cancel_if_pending(self) -> bool:
        """Cancel a queued request, returning False if execution has started."""
        with self._state_lock:
            if self._started:
                return False
            self._cancelled = True
            return True


class _ConsoleCapture:
    """Capture FreeCAD's own console output for one execution.

    FreeCAD prints its most useful diagnoses -- "Wire is not closed",
    "Revolve axis intersects the sketch", "Remove the following redundant
    constraint: 7" -- from C++, so `contextlib.redirect_stderr` never sees
    them. `FreeCAD.Console` exposes no `AddObserver`, so no Python observer
    can be registered either. Redirecting the process file descriptors is
    the only route that works in both GUI and headless mode, and unlike
    reading the Report view widget it captures exactly the window of one
    execution rather than an accumulating buffer.

    Failing to capture must never fail the execution, so every step is
    guarded and the capture degrades to an empty string.
    """

    MAX_CHARS = 4000

    def __init__(self) -> None:
        self._saved: list[tuple[int, int]] = []
        self._temp: Any = None
        self.text = ""

    def __enter__(self) -> _ConsoleCapture:
        try:
            self._temp = tempfile.TemporaryFile()
            for fd in (1, 2):
                self._saved.append((fd, os.dup(fd)))
                os.dup2(self._temp.fileno(), fd)
        except Exception:
            self._restore()
        return self

    def _restore(self) -> None:
        for fd, saved_fd in self._saved:
            try:
                os.dup2(saved_fd, fd)
                os.close(saved_fd)
            except Exception:
                pass
        self._saved = []

    def __exit__(self, *_exc: Any) -> None:
        self._restore()
        try:
            if self._temp is not None:
                self._temp.seek(0)
                captured = self._temp.read().decode("utf-8", "replace")
                self.text = captured[-self.MAX_CHARS :].strip()
        except Exception:
            self.text = ""
        finally:
            try:
                if self._temp is not None:
                    self._temp.close()
            except Exception:
                pass


class FreecadMCPPlugin:
    """Plugin that runs inside FreeCAD to handle MCP bridge requests.

    This class creates servers that accept connections from the MCP server
    and executes commands in FreeCAD's context using a thread-safe queue
    system for GUI operations.

    Attributes:
        socket_host: Hostname for socket server.
        socket_port: Port for JSON-RPC socket server.
        xmlrpc_port: Port for XML-RPC server.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = DEFAULT_SOCKET_PORT,
        xmlrpc_port: int = DEFAULT_XMLRPC_PORT,
        enable_xmlrpc: bool = True,
    ) -> None:
        """Initialize the plugin.

        Args:
            host: Hostname to bind to.
            port: Port for JSON-RPC socket server.
            xmlrpc_port: Port for XML-RPC server.
            enable_xmlrpc: Whether to enable XML-RPC server.
        """
        # Generate unique instance ID for this server
        self._instance_id = str(uuid.uuid4())

        self._host = host
        self._port = port
        self._xmlrpc_port = xmlrpc_port
        self._enable_xmlrpc = enable_xmlrpc

        # Server instances
        self._socket_server: asyncio.Server | None = None
        self._xmlrpc_server: xmlrpc.server.SimpleXMLRPCServer | None = None
        self._socket_loop: asyncio.AbstractEventLoop | None = None

        # Threading
        self._socket_thread: threading.Thread | None = None
        self._xmlrpc_thread: threading.Thread | None = None
        self._running = False

        # Queue-based execution for thread safety (learned from neka-nat)
        self._request_queue: queue.Queue[ExecutionRequest] = queue.Queue()
        self._active_request_lock = threading.Lock()
        self._active_request: ExecutionRequest | None = None
        self._timer = None
        self._queue_thread: threading.Thread | None = None
        self._headless = False

        # Status bar tracking
        self._status_timer = None
        self._request_count = 0
        self._last_request_time: float | None = None

        # Register this server for cleanup on Python exit
        # This prevents crashes when Python's GC tries to clean up QTimer
        # objects during Py_FinalizeEx
        global _atexitRegistered
        _activeServers.add(self)
        if not _atexitRegistered:
            atexit.register(_cleanup_all_servers)
            _atexitRegistered = True

    # =========================================================================
    # Public API (for external access without using private attributes)
    # =========================================================================

    @property
    def is_running(self) -> bool:
        """Check if the MCP bridge server is currently running.

        Returns:
            True if the server is running, False otherwise.
        """
        return self._running

    @property
    def instance_id(self) -> str:
        """Get the unique instance ID for this server.

        Returns:
            UUID string identifying this server instance.
        """
        return self._instance_id

    @property
    def socket_port(self) -> int:
        """Get the JSON-RPC socket server port.

        Returns:
            Port number for the socket server.
        """
        return self._port

    @property
    def xmlrpc_port(self) -> int:
        """Get the XML-RPC server port.

        Returns:
            Port number for the XML-RPC server.
        """
        return self._xmlrpc_port

    @property
    def request_count(self) -> int:
        """Get the total number of requests processed.

        Returns:
            Number of requests processed since server start.
        """
        return self._request_count

    def get_status(self) -> dict[str, Any]:
        """Get the current status of the MCP bridge server.

        Returns:
            Dictionary containing:
                - running: Whether the server is running
                - instance_id: Unique server instance ID
                - socket_port: JSON-RPC socket port
                - xmlrpc_port: XML-RPC port
                - xmlrpc_enabled: Whether XML-RPC is enabled
                - request_count: Total requests processed
                - last_request_time: Timestamp of last request (or None)
                - headless: Whether running in headless mode
                - execution_in_progress: Whether code is currently running
        """
        return {
            "running": self._running,
            "instance_id": self._instance_id,
            "socket_port": self._port,
            "xmlrpc_port": self._xmlrpc_port,
            "xmlrpc_enabled": self._enable_xmlrpc,
            "request_count": self._request_count,
            "last_request_time": self._last_request_time,
            "headless": self._headless,
            "execution_in_progress": self._execution_in_progress(),
        }

    def start(self) -> None:
        """Start all servers."""
        if self._running:
            return

        self._running = True

        # Print instance ID to stderr only for test automation (when env var is set).
        # This avoids red error text in FreeCAD's console during normal use.
        if os.environ.get("FREECAD_MCP_TESTING"):
            print(
                f"FREECAD_MCP_BRIDGE_INSTANCE_ID={self._instance_id}",
                file=sys.stderr,
                flush=True,
            )

        # Start the queue processing timer on the main thread
        self._start_queue_processor()

        # Start socket server
        self._socket_thread = threading.Thread(
            target=self._run_socket_server,
            daemon=True,
            name="MCP-Socket",
        )
        self._socket_thread.start()

        # Start XML-RPC server if enabled
        if self._enable_xmlrpc:
            self._xmlrpc_thread = threading.Thread(
                target=self._run_xmlrpc_server,
                daemon=True,
                name="MCP-XMLRPC",
            )
            self._xmlrpc_thread.start()

        if FREECAD_AVAILABLE:
            FreeCAD.Console.PrintMessage(
                f"MCP Bridge started (Instance ID: {self._instance_id}):\n"
            )
            FreeCAD.Console.PrintMessage(f"  - JSON-RPC: {self._host}:{self._port}\n")
            if self._enable_xmlrpc:
                FreeCAD.Console.PrintMessage(
                    f"  - XML-RPC: {self._host}:{self._xmlrpc_port}\n"
                )

        # Start status bar updates in GUI mode
        self._start_status_updates()

    def stop(self) -> None:
        """Stop all servers.

        This method properly cleans up QTimer objects by stopping them,
        disconnecting their signals, and scheduling them for deletion with
        deleteLater(). This prevents crashes during Python finalization when
        Qt tries to disconnect signals from partially-destroyed Python objects.
        """
        self._running = False

        # Stop status bar updates
        self._stop_status_updates()

        # Stop queue processor timer (GUI mode)
        # Must disconnect signal before deleteLater to avoid crash during cleanup
        if self._timer:
            with contextlib.suppress(Exception):
                self._timer.stop()
                self._timer.timeout.disconnect()
                self._timer.deleteLater()
            self._timer = None

        # Stop XML-RPC server by closing its socket directly
        # This will cause handle_request() to raise an exception and exit
        # Keep server reference until thread exits to avoid race condition
        if self._xmlrpc_server:
            with contextlib.suppress(Exception):
                self._xmlrpc_server.socket.close()

        # Stop socket server - close the server and stop the event loop
        if self._socket_loop and self._socket_server:
            self._socket_loop.call_soon_threadsafe(self._socket_server.close)
            self._socket_loop.call_soon_threadsafe(self._socket_loop.stop)

        # Wait briefly for threads - they're daemon threads so they'll
        # be killed when the main thread exits anyway
        if self._queue_thread and self._queue_thread.is_alive():
            self._queue_thread.join(timeout=0.5)
        self._queue_thread = None

        if self._socket_thread and self._socket_thread.is_alive():
            self._socket_thread.join(timeout=0.5)
        self._socket_thread = None

        # Wait for XML-RPC thread to exit before clearing server reference
        if self._xmlrpc_thread and self._xmlrpc_thread.is_alive():
            self._xmlrpc_thread.join(timeout=0.5)
        self._xmlrpc_thread = None
        # Now safe to clear the server reference
        self._xmlrpc_server = None

        if FREECAD_AVAILABLE:
            FreeCAD.Console.PrintMessage("MCP Bridge stopped\n")

    def _cleanup_for_exit(self) -> None:
        """Clean up server resources during Python exit (atexit handler).

        This is a minimal cleanup that ONLY stops timers and threads without
        accessing any GUI elements.  During Python finalization, Qt GUI objects
        like ``QMainWindow`` may already be destroyed, so accessing them would
        crash.

        QTimer objects (``self._timer`` and ``self._status_timer``) are only
        created when ``FreeCAD.GuiUp`` is True (GUI mode).  In headless mode
        these attributes remain ``None``, making this method a safe no-op for
        timer-related cleanup.  During startup there is a race window where
        timers may not yet be allocated if the GUI has not finished
        initialising; the guards (``if self._timer``) handle that gracefully.

        CRITICAL: We must use ``shiboken.delete()`` to explicitly destroy
        QTimer objects, NOT ``deleteLater()``.  ``deleteLater()`` schedules
        deletion for the next event loop iteration, but the event loop isn't
        running during atexit.  This causes Python's GC to try to finalize
        the PySide wrapper, which triggers Qt's ``disconnectNotify`` callback
        into partially-finalized Python, causing a crash.

        This atexit handler **must** run before ``Py_FinalizeEx``.  It is
        called unconditionally by ``_cleanup_all_servers``—even when
        ``_running`` is False—to handle timers left over from failed startups.
        It is safe to call multiple times.

        This method is called by the atexit handler.  For normal shutdown, use
        ``stop()`` instead which also clears the status bar.
        """
        self._running = False

        # Get shiboken delete function for explicit Qt object destruction
        shiboken_delete = _get_shiboken_delete()

        # Stop queue processor timer - use shiboken.delete() for immediate destruction
        if self._timer:
            timer = self._timer
            self._timer = None  # Clear reference first
            with contextlib.suppress(Exception):
                timer.stop()
            with contextlib.suppress(Exception):
                timer.timeout.disconnect()
            # Explicitly delete the C++ object to prevent GC crash
            if shiboken_delete is not None:
                with contextlib.suppress(Exception):
                    shiboken_delete(timer)

        # Stop status timer - use shiboken.delete() for immediate destruction
        if self._status_timer:
            timer = self._status_timer
            self._status_timer = None  # Clear reference first
            with contextlib.suppress(Exception):
                timer.stop()
            with contextlib.suppress(Exception):
                timer.timeout.disconnect()
            # Explicitly delete the C++ object to prevent GC crash
            if shiboken_delete is not None:
                with contextlib.suppress(Exception):
                    shiboken_delete(timer)

        # Stop XML-RPC server
        if self._xmlrpc_server:
            with contextlib.suppress(Exception):
                self._xmlrpc_server.socket.close()

        # Stop socket server
        if self._socket_loop and self._socket_server:
            with contextlib.suppress(Exception):
                self._socket_loop.call_soon_threadsafe(self._socket_server.close)
                self._socket_loop.call_soon_threadsafe(self._socket_loop.stop)

        # Don't wait for threads during exit - they're daemon threads
        # and will be killed anyway. Waiting can cause hangs.
        self._queue_thread = None
        self._socket_thread = None
        self._xmlrpc_thread = None
        self._xmlrpc_server = None

    def run_forever(self) -> None:
        """Run the server indefinitely.

        This method blocks until interrupted (Ctrl+C) or stop() is called.
        Works in both GUI and headless modes:
        - GUI mode: Uses Qt event loop to allow timers to fire
        - Headless mode: Uses short sleep intervals for responsive shutdown
        """
        self.start()
        if FREECAD_AVAILABLE:
            FreeCAD.Console.PrintMessage("Server running. Press Ctrl+C to stop.\n")

        # Check if we're in GUI mode and have Qt available
        QtCore = _get_qt_core()

        try:
            if QtCore is not None:
                # GUI mode: use Qt's processEvents to keep the event loop running
                # This allows QTimers to fire for queue processing
                app = QtCore.QCoreApplication.instance()
                if app is not None:
                    while self._running:
                        # Process Qt events (including our QTimer callbacks)
                        app.processEvents()
                        # Small sleep to prevent busy-waiting
                        time.sleep(0.01)
                else:
                    # No QApplication - fall back to headless behavior
                    self._run_forever_headless()
            else:
                # Headless mode
                self._run_forever_headless()
        except KeyboardInterrupt:
            pass  # Normal exit via Ctrl+C
        finally:
            if FREECAD_AVAILABLE:
                FreeCAD.Console.PrintMessage("\nShutting down...\n")
            self.stop()

    def _run_forever_headless(self) -> None:
        """Run forever in headless mode using short sleep intervals.

        Uses a short sleep interval to allow responsive shutdown when
        stop() sets _running to False.
        """
        while self._running:
            # Use short sleep to allow responsive shutdown
            # This is more portable than signal.pause() and responds
            # quickly when stop() sets _running = False
            time.sleep(HEADLESS_POLL_INTERVAL_S)

    # =========================================================================
    # Status Bar Updates (GUI mode only)
    # =========================================================================

    def _start_status_updates(self) -> None:
        """Start periodic status bar updates in GUI mode.

        Creates a ``QTimer`` that fires every ``STATUS_UPDATE_INTERVAL_MS``
        to refresh the FreeCAD main-window status bar.  Only runs when
        ``FreeCAD.GuiUp`` is True; returns immediately in headless mode.

        The timer created here is destroyed during shutdown by
        ``_cleanup_for_exit`` (via ``shiboken.delete()``) or by
        ``_stop_status_updates`` (via ``deleteLater()``).
        """
        QtCore = _get_qt_core()
        if QtCore is None:
            return

        # Create timer for status updates
        timer = QtCore.QTimer()
        timer.timeout.connect(self._update_status_bar)
        timer.start(STATUS_UPDATE_INTERVAL_MS)
        self._status_timer = timer

        # Show initial status
        self._update_status_bar()

    def _stop_status_updates(self) -> None:
        """Stop status bar updates and clear the status.

        Properly disconnects signals and schedules timer for deletion to
        prevent crashes during Python finalization.
        """
        if self._status_timer:
            with contextlib.suppress(Exception):
                self._status_timer.stop()
                self._status_timer.timeout.disconnect()
                self._status_timer.deleteLater()
            self._status_timer = None

        # Clear status bar message
        if FREECAD_AVAILABLE and FreeCAD.GuiUp:
            self._set_status_bar("")

    def _update_status_bar(self) -> None:
        """Update the FreeCAD status bar with MCP bridge status."""
        if not (FREECAD_AVAILABLE and FreeCAD.GuiUp):
            return

        # Build status message
        ports = f"XML-RPC:{self._xmlrpc_port}" if self._enable_xmlrpc else ""
        if ports:
            ports = f" ({ports})"

        if self._request_count > 0:
            # Show activity info
            if self._last_request_time:
                elapsed = time.time() - self._last_request_time
                if elapsed < 60:
                    time_ago = f"{int(elapsed)}s ago"
                else:
                    time_ago = f"{int(elapsed / 60)}m ago"
                status = f"🔌 MCP Bridge active{ports} | {self._request_count} requests | last: {time_ago}"
            else:
                status = f"🔌 MCP Bridge active{ports} | {self._request_count} requests"
        else:
            status = f"🔌 MCP Bridge running{ports} | waiting for connections..."

        self._set_status_bar(status)

    def _set_status_bar(self, message: str) -> None:
        """Set the FreeCAD main window status bar message.

        Args:
            message: Message to display in status bar.
        """
        if not (FREECAD_AVAILABLE and FreeCAD.GuiUp):
            return

        try:
            main_window = FreeCADGui.getMainWindow()
            if main_window:
                status_bar = main_window.statusBar()
                if status_bar:
                    if message:
                        # Show message persistently (0 = no timeout)
                        status_bar.showMessage(message, 0)
                    else:
                        status_bar.clearMessage()
        except Exception:
            # Silently ignore status bar errors
            pass

    def _record_request(self) -> None:
        """Record that a request was processed (for status tracking)."""
        self._request_count += 1
        self._last_request_time = time.time()

    # =========================================================================
    # Queue-based Thread Safety (from neka-nat)
    # =========================================================================

    def _start_queue_processor(self) -> None:
        """Start the queue processor on the main GUI thread or as background thread.

        In GUI mode (``FreeCAD.GuiUp`` is True) this creates a ``QTimer``
        that fires every ``QUEUE_POLL_INTERVAL_MS`` to process the request
        queue on the main thread—required because Qt widgets must only be
        touched from the thread that owns them.

        In headless mode (``FreeCAD.GuiUp`` is False, or Qt is unavailable)
        a daemon background thread polls the queue instead.  No QTimer is
        created, so no timer cleanup is needed at shutdown.

        Note: The timer created here is destroyed during shutdown by
        ``_cleanup_for_exit`` (via ``shiboken.delete()``) or by ``stop()``
        (via ``deleteLater()``).
        """
        # Check if we're in GUI mode using FreeCAD.GuiUp
        # Note: Qt (PySide) may be available even in headless mode, but without
        # a running event loop, Qt timers won't fire. Use GuiUp to detect this.
        gui_available = FREECAD_AVAILABLE and FreeCAD.GuiUp

        if gui_available:
            # GUI mode: use Qt timer for thread-safe GUI operations
            try:
                from PySide2 import QtCore
            except ImportError:
                try:
                    from PySide6 import QtCore
                except ImportError:
                    QtCore = None  # type: ignore[assignment]

            if QtCore is not None:
                timer = QtCore.QTimer()
                timer.timeout.connect(self._process_queue)
                timer.start(QUEUE_POLL_INTERVAL_MS)
                self._timer = timer
                return

        # Headless mode: use a background thread for queue processing
        # In headless mode, there's no GUI thread concern, so direct
        # processing in a background thread is safe
        self._headless = True
        self._queue_thread = threading.Thread(
            target=self._run_queue_processor_loop,
            daemon=True,
            name="MCP-QueueProcessor",
        )
        self._queue_thread.start()
        if FREECAD_AVAILABLE:
            FreeCAD.Console.PrintMessage(
                "Running in headless mode (queue processor thread started)\n"
            )

    def _run_queue_processor_loop(self) -> None:
        """Run queue processor in a loop for headless mode."""
        while self._running:
            self._process_queue()
            time.sleep(QUEUE_POLL_INTERVAL_MS / 1000.0)

    def _execution_in_progress(self) -> bool:
        """Return whether an execution request is still active."""
        with self._active_request_lock:
            return (
                self._active_request is not None
                and not self._active_request.completed.is_set()
            )

    def _claim_execution_request(self, request: ExecutionRequest) -> bool:
        """Claim the single execution slot for a request."""
        with self._active_request_lock:
            if (
                self._active_request is not None
                and not self._active_request.completed.is_set()
            ):
                return False
            self._active_request = request
            return True

    def _release_execution_request(self, request: ExecutionRequest) -> None:
        """Release the execution slot if it still belongs to the request."""
        with self._active_request_lock:
            if self._active_request is request:
                self._active_request = None

    def _process_queue(self) -> None:
        """Process pending execution requests on the main thread.

        This method is called periodically by a Qt timer to ensure
        GUI operations happen on the main thread.
        """
        while not self._request_queue.empty():
            try:
                request = self._request_queue.get_nowait()
            except queue.Empty:
                break

            if not request.start_if_pending():
                self._release_execution_request(request)
                request.completed.set()
                continue

            try:
                result = self._execute_code_sync(request.code, request.transaction)
                request.result = result
                self._record_request()
            except Exception as e:
                request.result = {
                    "success": False,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                }
                if FREECAD_AVAILABLE:
                    FreeCAD.Console.PrintError(f"Queue processing error: {e}\n")
            finally:
                self._release_execution_request(request)
                request.completed.set()

    def _execute_via_queue(
        self,
        code: str,
        timeout_ms: int,
        transaction: str | None,
    ) -> dict[str, Any]:
        """Execute code via the queue system for thread safety.

        Args:
            code: Python code to execute.
            timeout_ms: Execution timeout in milliseconds.
            transaction: Undo transaction name to arm, or None for read-only.

        Returns:
            Execution result dictionary.
        """
        request = ExecutionRequest(code, timeout_ms, transaction=transaction)
        if not self._claim_execution_request(request):
            return {
                "success": False,
                "error_type": "BusyError",
                "error_message": "Another FreeCAD execution is still in progress",
                "execution_time_ms": 0,
                "execution_continues": True,
            }
        self._request_queue.put(request)

        # Wait for completion
        if request.completed.wait(timeout=timeout_ms / 1000):
            return request.result or {
                "success": False,
                "error_type": "InternalError",
                "error_message": "No result returned",
            }
        else:
            cancelled = request.cancel_if_pending()
            if cancelled:
                self._release_execution_request(request)
            message = f"Execution timed out after {timeout_ms}ms"
            if not cancelled:
                message += "; the operation started and may still be running"
            return {
                "success": False,
                "error_type": "TimeoutError",
                "error_message": message,
                "execution_time_ms": timeout_ms,
                "execution_continues": not cancelled,
            }

    def _execute_code_sync(self, code: str, transaction: str | None) -> dict[str, Any]:
        """Execute Python code synchronously (call on main thread only).

        Args:
            code: Python code to execute.
            transaction: Name of the undo transaction to arm for this call, or
                None for a read-only call that must not open one.

        Returns:
            Execution result dictionary.
        """
        start = time.perf_counter()
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        exec_globals: dict[str, Any] = {
            "__builtins__": __builtins__,
        }

        if FREECAD_AVAILABLE:
            exec_globals["FreeCAD"] = FreeCAD
            exec_globals["App"] = FreeCAD
            exec_globals["FreeCADGui"] = FreeCADGui
            exec_globals["Gui"] = FreeCADGui

        armed = False
        if transaction is not None and FREECAD_AVAILABLE:
            active = FreeCAD.getActiveTransaction()
            if isinstance(active, tuple | list) and len(active) > 1 and active[1]:
                return {
                    "success": False,
                    "result": None,
                    "stdout": "",
                    "stderr": "",
                    "execution_time_ms": 0.0,
                    "error_type": "TransactionConflict",
                    "error_message": (
                        "TRANSACTION_CONFLICT: application transaction "
                        f"{active[0]!r} is already active; refusing to mutate"
                    ),
                    "error_traceback": None,
                }
            # Undo must be ON before arming. A document's UndoMode defaults to 0,
            # and with undo disabled closeActiveTransaction(abort=True) silently
            # keeps the mutation instead of rolling it back. Verified live.
            for open_document in FreeCAD.listDocuments().values():
                if getattr(open_document, "UndoMode", 1) == 0:
                    open_document.UndoMode = 1  # type: ignore[attr-defined]
            FreeCAD.setActiveTransaction(transaction, True)
            armed = True

        succeeded = False
        console = _ConsoleCapture()
        try:
            try:
                with (
                    console,
                    redirect_stdout(stdout_capture),
                    redirect_stderr(stderr_capture),
                ):
                    compiled = compile(code, "<mcp>", "exec")
                    exec(compiled, exec_globals)  # noqa: S102

                succeeded = True
                elapsed = (time.perf_counter() - start) * 1000
                return {
                    "success": True,
                    "result": exec_globals.get("_result_"),
                    "stdout": stdout_capture.getvalue(),
                    "stderr": stderr_capture.getvalue(),
                    "console": console.text,
                    "execution_time_ms": elapsed,
                }

            except Exception as e:
                elapsed = (time.perf_counter() - start) * 1000
                traceback_text = traceback.format_exc()
                # FreeCAD named the cause on its own console. Attach it to the
                # traceback so it reaches the caller, which is the only place
                # an MCP client can see anything at all.
                if console.text:
                    traceback_text += "\nFreeCAD reported:\n" + console.text
                return {
                    "success": False,
                    "result": None,
                    "stdout": stdout_capture.getvalue(),
                    "stderr": stderr_capture.getvalue(),
                    "console": console.text,
                    "execution_time_ms": elapsed,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "error_traceback": traceback_text,
                }
        finally:
            if armed:
                FreeCAD.closeActiveTransaction(not succeeded)

    # =========================================================================
    # Socket Server (JSON-RPC 2.0)
    # =========================================================================

    def _run_socket_server(self) -> None:
        """Run the asyncio event loop in background thread."""
        self._socket_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._socket_loop)

        try:
            self._socket_loop.run_until_complete(self._start_socket_server())
            self._socket_loop.run_forever()
        except OSError as e:
            # Server failed to start - mark as not running
            self._running = False
            if e.errno == errno.EADDRINUSE:
                if FREECAD_AVAILABLE:
                    FreeCAD.Console.PrintWarning(
                        f"MCP Bridge: JSON-RPC port {self._port} already in use. "
                        f"Another instance may be running.\n"
                    )
            elif FREECAD_AVAILABLE:
                FreeCAD.Console.PrintError(
                    f"MCP Bridge: Failed to start JSON-RPC server: {e}\n"
                )
        finally:
            self._socket_loop.close()

    async def _start_socket_server(self) -> None:
        """Start the TCP server."""
        self._socket_server = await asyncio.start_server(
            self._handle_socket_client,
            self._host,
            self._port,
        )

    async def _handle_socket_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a connected socket client.

        Args:
            reader: Stream reader for incoming data.
            writer: Stream writer for outgoing data.
        """
        try:
            while self._running:
                data = await reader.readline()
                if not data:
                    break

                try:
                    request = json.loads(data.decode("utf-8"))
                    response = await self._process_jsonrpc_request(request)
                except json.JSONDecodeError as e:
                    response = {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {
                            "code": -32700,
                            "message": "Parse error",
                            "data": str(e),
                        },
                    }

                response_data = json.dumps(response).encode("utf-8") + b"\n"
                writer.write(response_data)
                await writer.drain()

        except Exception as e:
            if FREECAD_AVAILABLE:
                FreeCAD.Console.PrintError(f"MCP socket error: {e}\n")
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def _process_jsonrpc_request(
        self,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        """Process a JSON-RPC 2.0 request.

        Args:
            request: JSON-RPC request dictionary.

        Returns:
            JSON-RPC response dictionary.
        """
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        # Handle ping specially (no queue needed)
        if method == "ping":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "pong": True,
                    "timestamp": time.time(),
                    "instance_id": self._instance_id,
                },
            }

        # Handle get_instance_id specially (no queue needed)
        if method == "get_instance_id":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"instance_id": self._instance_id},
            }

        # Handle execute via queue
        if method == "execute":
            if "transaction" not in params:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32602,
                        "message": "Invalid params",
                        "data": "Missing required parameter: transaction",
                    },
                }
            code = params.get("code", "")
            timeout_ms = params.get("timeout_ms", 30000)
            transaction = params["transaction"]

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._execute_via_queue(code, timeout_ms, transaction),
            )

            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result,
            }

        # Unknown method
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32601,
                "message": "Method not found",
                "data": f"Unknown method: {method}",
            },
        }

    # =========================================================================
    # XML-RPC Server (neka-nat compatible)
    # =========================================================================

    def _run_xmlrpc_server(self) -> None:
        """Run the XML-RPC server."""

        # Custom request handler that silently handles GET requests
        # instead of logging "Unsupported method ('GET')" errors
        class QuietXMLRPCRequestHandler(xmlrpc.server.SimpleXMLRPCRequestHandler):
            """XML-RPC handler that responds gracefully to GET requests."""

            def do_GET(self) -> None:
                """Handle GET requests with a friendly plain-text response.

                Responds to HTTP GET requests with a simple message instead of
                logging "Unsupported method ('GET')" errors. This is useful for
                health checks and browser probing.

                Args:
                    self: The request handler instance.

                Returns:
                    None. Writes response directly to wfile.

                Side Effects:
                    Sends HTTP 200 response with Content-type: text/plain header
                    and writes response body to self.wfile.

                Example:
                    A simple GET request to check if the bridge is running::

                        curl http://localhost:9875/
                        # Returns: FreeCAD MCP Bridge - XML-RPC endpoint (POST only)
                """
                response = b"FreeCAD MCP Bridge - XML-RPC endpoint (POST only)"
                self.send_response(200)
                self.send_header("Content-type", "text/plain")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

            def log_message(self, format: str, *args: Any) -> None:
                """Suppress HTTP request logging to keep console output clean.

                Overrides the parent class method to prevent logging of every
                HTTP request, which would clutter the FreeCAD console.

                Args:
                    self: The request handler instance.
                    format: The format string for the log message (ignored).
                    *args: Arguments to format into the message (ignored).

                Returns:
                    None. No logging is performed.

                Behavior:
                    All log messages are silently discarded. No output is
                    produced regardless of the format or arguments passed.

                Example:
                    Calling log_message produces no output::

                        handler.log_message("%s - %s", "GET", "/")
                        # No output is produced
                """
                pass

        try:
            self._xmlrpc_server = xmlrpc.server.SimpleXMLRPCServer(
                (self._host, self._xmlrpc_port),
                requestHandler=QuietXMLRPCRequestHandler,
                allow_none=True,
                logRequests=False,
            )
        except OSError as e:
            if e.errno == errno.EADDRINUSE:
                if FREECAD_AVAILABLE:
                    FreeCAD.Console.PrintWarning(
                        f"MCP Bridge: XML-RPC port {self._xmlrpc_port} already in use. "
                        f"Another instance may be running.\n"
                    )
            elif FREECAD_AVAILABLE:
                FreeCAD.Console.PrintError(
                    f"MCP Bridge: Failed to start XML-RPC server: {e}\n"
                )
            return

        # Set a timeout so handle_request() doesn't block forever
        # This allows the server to check self._running periodically
        self._xmlrpc_server.timeout = 0.5

        # Register methods (type: ignore needed - xmlrpc types are overly restrictive)
        self._xmlrpc_server.register_function(self._xmlrpc_execute, "execute")  # type: ignore[arg-type]
        self._xmlrpc_server.register_function(self._xmlrpc_ping, "ping")  # type: ignore[arg-type]
        self._xmlrpc_server.register_function(
            self._xmlrpc_get_instance_id, "get_instance_id"
        )  # type: ignore[arg-type]
        self._xmlrpc_server.register_function(self._xmlrpc_get_view, "get_view")  # type: ignore[arg-type]
        self._xmlrpc_server.register_introspection_functions()

        while self._running:
            try:
                self._xmlrpc_server.handle_request()
            except OSError:
                # Socket was closed during shutdown - this is expected
                break

    def _xmlrpc_ping(self) -> dict[str, Any]:
        """XML-RPC ping handler."""
        return {
            "pong": True,
            "timestamp": time.time(),
            "instance_id": self._instance_id,
        }

    def _xmlrpc_get_instance_id(self) -> dict[str, Any]:
        """XML-RPC get_instance_id handler.

        Returns:
            Dictionary containing the unique instance ID for this bridge.
        """
        return {"instance_id": self._instance_id}

    def _xmlrpc_execute(
        self,
        code: str,
        timeout_ms: int,
        transaction: str | None,
    ) -> dict[str, Any]:
        """XML-RPC execute handler.

        Args:
            code: Python code to execute.
            timeout_ms: Maximum time to wait for execution in milliseconds.
            transaction: Undo transaction name to arm, or None for read-only.

        Returns:
            Execution result dictionary.
        """
        return _xmlrpc_safe_value(
            self._execute_via_queue(code, timeout_ms, transaction)
        )

    # Valid view types for screenshot capture
    _VALID_VIEW_TYPES = frozenset(
        {"FitAll", "Isometric", "Front", "Back", "Top", "Bottom", "Left", "Right"}
    )

    def _xmlrpc_get_view(
        self,
        width: int = 800,
        height: int = 600,
        view_type: str = "Isometric",
    ) -> dict[str, Any]:
        """XML-RPC get_view handler for screenshots (neka-nat compatible).

        Args:
            width: Image width.
            height: Image height.
            view_type: View angle type.

        Returns:
            Dictionary with base64 image data or error.
        """
        # Validate inputs to prevent code injection
        # Type hints don't enforce at runtime, so explicit conversion is needed
        try:
            width = int(width)
            height = int(height)
        except (ValueError, TypeError) as e:
            return {"success": False, "error": f"Invalid dimensions: {e}"}

        if view_type not in self._VALID_VIEW_TYPES:
            return {
                "success": False,
                "error": f"Invalid view_type: {view_type}. "
                f"Must be one of: {', '.join(sorted(self._VALID_VIEW_TYPES))}",
            }

        code = f"""
import base64
import tempfile
import os

if not FreeCAD.GuiUp:
    _result_ = {{"success": False, "error": "GUI not available"}}
else:
    doc = FreeCAD.ActiveDocument
    if doc is None:
        _result_ = {{"success": False, "error": "No active document"}}
    else:
        view = FreeCADGui.ActiveDocument.ActiveView
        if view is None:
            _result_ = {{"success": False, "error": "No active view"}}
        else:
            # Check view type
            # Note: Use type() instead of __class__ because FreeCAD's View3DInventor
            # has a broken __class__ attribute that returns a dict of methods.
            view_class = type(view).__name__
            if view_class not in ["View3DInventor", "View3DInventorPy"]:
                _result_ = {{"success": False, "error": f"Cannot capture from {{view_class}}"}}
            else:
                # Set view angle
                view_type = {view_type!r}
                if view_type == "FitAll":
                    view.fitAll()
                elif view_type == "Isometric":
                    view.viewIsometric()
                elif view_type == "Front":
                    view.viewFront()
                elif view_type == "Back":
                    view.viewRear()
                elif view_type == "Top":
                    view.viewTop()
                elif view_type == "Bottom":
                    view.viewBottom()
                elif view_type == "Left":
                    view.viewLeft()
                elif view_type == "Right":
                    view.viewRight()

                # Capture screenshot
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                    temp_path = f.name

                view.saveImage(temp_path, {width}, {height}, "Current")

                with open(temp_path, "rb") as f:
                    image_data = base64.b64encode(f.read()).decode("utf-8")

                os.unlink(temp_path)

                _result_ = {{
                    "success": True,
                    "data": image_data,
                    "format": "png",
                    "width": {width},
                    "height": {height},
                }}
"""
        result = self._execute_via_queue(code, 30000, None)
        if result.get("success") and result.get("result"):
            return result["result"]
        return {"success": False, "error": result.get("error_message", "Unknown error")}


# Backwards compatibility
start = FreecadMCPPlugin
