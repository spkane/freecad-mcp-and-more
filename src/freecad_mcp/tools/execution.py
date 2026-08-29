"""Execution tools for FreeCAD Robust MCP Server.

This module provides tools for executing Python code in FreeCAD's context,
getting version information, and accessing the console.
"""

import os
import platform
import socket
from collections.abc import Awaitable, Callable
from typing import Any

from freecad_mcp.server import get_instance_id


def register_execution_tools(
    mcp: Any, get_bridge: Callable[[], Awaitable[Any]]
) -> None:
    """Register execution-related tools with the Robust MCP Server.

    Args:
        mcp: The FastMCP (Robust MCP Server) instance.
        get_bridge: Async function to get the active bridge.
    """

    @mcp.tool()
    async def execute_python(
        code: str,
        timeout_ms: int = 30000,
    ) -> dict[str, Any]:
        """Execute Python code in FreeCAD's Python console context.

        This tool allows you to run arbitrary Python code within FreeCAD's
        environment, with access to all FreeCAD modules and the active document.

        Args:
            code: Python code to execute. Use `_result_ = value` to return data
                to the caller. The code has access to FreeCAD, App, FreeCADGui,
                and Gui modules.
            timeout_ms: Maximum execution time in milliseconds. Defaults to 30000.

        Returns:
            Dictionary containing execution results:
                - success: Whether execution completed without errors
                - result: The value assigned to `_result_` variable
                - stdout: Captured standard output
                - stderr: Captured standard error
                - execution_time_ms: Time taken in milliseconds
                - error_type: Type of exception if failed (None if success)
                - error_traceback: Full traceback if failed (None if success)
                - execution_continues: Whether timed-out code is still running

        Example:
            Create a simple box and return its volume::

                execute_python('''
                import Part
                box = Part.makeBox(10, 20, 30)
                _result_ = {"volume": box.Volume, "area": box.Area}
                ''')

            List all objects in the active document::

                execute_python('''
                doc = FreeCAD.ActiveDocument
                if doc:
                    _result_ = [obj.Name for obj in doc.Objects]
                else:
                    _result_ = []
                ''')
        """
        bridge = await get_bridge()
        result = await bridge.execute_python(code, timeout_ms)
        return {
            "success": result.success,
            "result": result.result,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "execution_time_ms": result.execution_time_ms,
            "error_type": result.error_type,
            "error_traceback": result.error_traceback,
            "execution_continues": result.execution_continues,
        }

    @mcp.tool()
    async def get_freecad_version() -> dict[str, Any]:
        """Get FreeCAD version and build information.

        Returns:
            Dictionary containing version information:
                - version: Version string (e.g., "1.0.0")
                - version_tuple: Version as list of integers
                - build_date: Build date string
                - python_version: Embedded Python version
                - gui_available: Whether GUI is available
        """
        bridge = await get_bridge()
        return await bridge.get_freecad_version()

    @mcp.tool()
    async def get_connection_status() -> dict[str, Any]:
        """Get the current FreeCAD connection status.

        Returns:
            Dictionary containing connection information:
                - connected: Whether bridge is connected
                - mode: Connection mode (embedded, xmlrpc, socket)
                - freecad_version: FreeCAD version string
                - gui_available: Whether GUI is available
                - last_ping_ms: Last ping latency in milliseconds
                - error: Error message if not connected
        """
        bridge = await get_bridge()
        status = await bridge.get_status()
        return {
            "connected": status.connected,
            "mode": status.mode,
            "freecad_version": status.freecad_version,
            "gui_available": status.gui_available,
            "last_ping_ms": status.last_ping_ms,
            "error": status.error,
        }

    @mcp.tool()
    async def get_console_output(lines: int = 100) -> list[str]:
        """Get recent FreeCAD console output.

        Args:
            lines: Maximum number of lines to return. Defaults to 100.

        Returns:
            List of console output lines, most recent last.
        """
        bridge = await get_bridge()
        return await bridge.get_console_output(lines)

    @mcp.tool()
    async def get_mcp_server_environment() -> dict[str, Any]:
        """Get environment info about the MCP Server and FreeCAD connection.

        This tool returns information about the environment where the MCP Server
        is running and the FreeCAD connection state, which is useful for debugging,
        verifying which MCP Server instance you are connected to, and determining
        if GUI features are available.

        Returns:
            Dictionary containing environment information:
                - instance_id: Unique UUID for this server instance (generated at
                    startup). Use this to verify you're connected to the expected
                    server instance in tests and automation.
                - hostname: Machine hostname
                - os_name: Operating system name (Linux, Darwin, Windows)
                - os_version: Operating system version
                - platform: Platform identifier string
                - python_version: Python version running the MCP Server
                - freecad: FreeCAD connection information:
                    - connected: Whether bridge is connected to FreeCAD
                    - mode: Connection mode (embedded, xmlrpc, socket)
                    - version: FreeCAD version string
                    - gui_available: Whether FreeCAD GUI is available (False in
                        headless mode). Use this to skip GUI-only tests.
                    - is_headless: Convenience boolean, True when GUI is NOT
                        available (opposite of gui_available)
                - env_vars: Selected environment variables for debugging:
                    - FREECAD_MODE: Connection mode
                    - FREECAD_SOCKET_HOST: Socket host
                    - FREECAD_SOCKET_PORT: Socket port
                    - FREECAD_XMLRPC_PORT: XML-RPC port

        Example:
            Verify you're connected to the expected server instance::

                env = get_mcp_server_environment()
                expected_id = "abc123..."  # Captured from server startup output
                assert env["instance_id"] == expected_id

            Skip GUI-only tests in headless mode::

                env = get_mcp_server_environment()
                if env["freecad"]["is_headless"]:
                    pytest.skip("Test requires GUI mode")
        """
        # Get FreeCAD connection status
        bridge = await get_bridge()
        status = await bridge.get_status()

        return {
            "instance_id": get_instance_id(),
            "hostname": socket.gethostname(),
            "os_name": platform.system(),
            "os_version": platform.release(),
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "freecad": {
                "connected": status.connected,
                "mode": status.mode,
                "version": status.freecad_version,
                "gui_available": status.gui_available,
                "is_headless": not status.gui_available,
            },
            "env_vars": {
                "FREECAD_MODE": os.environ.get("FREECAD_MODE", ""),
                "FREECAD_SOCKET_HOST": os.environ.get("FREECAD_SOCKET_HOST", ""),
                "FREECAD_SOCKET_PORT": os.environ.get("FREECAD_SOCKET_PORT", ""),
                "FREECAD_XMLRPC_PORT": os.environ.get("FREECAD_XMLRPC_PORT", ""),
            },
        }
