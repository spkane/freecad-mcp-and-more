"""FreeCAD status and console tools for the Robust MCP Server.

This module registers tools for querying FreeCAD version information,
connection status, and recent console output. Python execution is handled
by the bridge layer, not by any tool registered here.
"""

from collections.abc import Awaitable, Callable
from typing import Any


def register_execution_tools(
    mcp: Any, get_bridge: Callable[[], Awaitable[Any]]
) -> None:
    """Register execution-related tools with the Robust MCP Server.

    Args:
        mcp: The FastMCP (Robust MCP Server) instance.
        get_bridge: Async function to get the active bridge.
    """

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
