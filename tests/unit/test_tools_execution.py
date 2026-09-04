"""Tests for execution tools module."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from freecad_mcp.bridge.base import ConnectionStatus


class TestExecutionTools:
    """Tests for Python execution tools."""

    @pytest.fixture
    def mock_mcp(self):
        """Create a mock MCP server that captures tool registrations."""
        mcp = MagicMock()
        mcp._registered_tools = {}

        def tool_decorator():
            def wrapper(func):
                mcp._registered_tools[func.__name__] = func
                return func

            return wrapper

        mcp.tool = tool_decorator
        return mcp

    @pytest.fixture
    def mock_bridge(self):
        """Create a mock FreeCAD bridge."""
        return AsyncMock()

    @pytest.fixture
    def register_tools(self, mock_mcp, mock_bridge):
        """Register execution tools and return the registered functions."""
        from freecad_mcp.tools.execution import register_execution_tools

        async def get_bridge():
            return mock_bridge

        register_execution_tools(mock_mcp, get_bridge)
        return mock_mcp._registered_tools

    @pytest.mark.asyncio
    async def test_get_freecad_version(self, register_tools, mock_bridge):
        """get_freecad_version should return version info."""
        mock_bridge.get_freecad_version = AsyncMock(
            return_value={
                "version": "1.0.0",
                "version_tuple": [1, 0, 0],
                "build_date": "2024-01-15",
                "python_version": "3.11.6",
                "gui_available": True,
            }
        )

        get_freecad_version = register_tools["get_freecad_version"]
        result = await get_freecad_version()

        assert result["version"] == "1.0.0"
        assert result["gui_available"] is True
        mock_bridge.get_freecad_version.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_connection_status_connected(self, register_tools, mock_bridge):
        """get_connection_status should return connected status."""
        mock_bridge.get_status = AsyncMock(
            return_value=ConnectionStatus(
                connected=True,
                mode="xmlrpc",
                freecad_version="1.0.0",
                gui_available=True,
                last_ping_ms=5.5,
                error=None,
            )
        )

        get_connection_status = register_tools["get_connection_status"]
        result = await get_connection_status()

        assert result["connected"] is True
        assert result["mode"] == "xmlrpc"
        assert result["last_ping_ms"] == 5.5

    @pytest.mark.asyncio
    async def test_get_connection_status_disconnected(
        self, register_tools, mock_bridge
    ):
        """get_connection_status should return disconnected status with error."""
        mock_bridge.get_status = AsyncMock(
            return_value=ConnectionStatus(
                connected=False,
                mode="xmlrpc",
                error="Connection refused",
            )
        )

        get_connection_status = register_tools["get_connection_status"]
        result = await get_connection_status()

        assert result["connected"] is False
        assert result["error"] == "Connection refused"

    @pytest.mark.asyncio
    async def test_get_console_output(self, register_tools, mock_bridge):
        """get_console_output should return console lines."""
        mock_bridge.get_console_output = AsyncMock(
            return_value=[
                "FreeCAD started",
                "Document created: TestDoc",
                "Box created",
            ]
        )

        get_console_output = register_tools["get_console_output"]
        result = await get_console_output()

        # Returns a list directly, not a dict
        assert result == [
            "FreeCAD started",
            "Document created: TestDoc",
            "Box created",
        ]
        mock_bridge.get_console_output.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_console_output_with_lines_param(
        self, register_tools, mock_bridge
    ):
        """get_console_output should pass lines parameter."""
        mock_bridge.get_console_output = AsyncMock(return_value=["Line 1"])

        get_console_output = register_tools["get_console_output"]
        await get_console_output(lines=50)

        mock_bridge.get_console_output.assert_called_once_with(50)
