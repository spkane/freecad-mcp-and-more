"""Tests for execution tools module."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from freecad_mcp.bridge.base import ConnectionStatus, ExecutionResult


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
    async def test_execute_python_success(self, register_tools, mock_bridge):
        """execute_python should return success result."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"value": 42, "type": "int"},
                stdout="",
                stderr="",
                execution_time_ms=10.5,
            )
        )

        execute_python = register_tools["execute_python"]
        result = await execute_python(code="_result_ = {'value': 42, 'type': 'int'}")

        assert result["success"] is True
        assert result["result"] == {"value": 42, "type": "int"}
        assert result["execution_time_ms"] == 10.5
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_python_with_timeout(self, register_tools, mock_bridge):
        """execute_python should pass timeout to bridge."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result=True,
                stdout="",
                stderr="",
                execution_time_ms=5.0,
            )
        )

        execute_python = register_tools["execute_python"]
        await execute_python(code="_result_ = True", timeout_ms=60000)

        mock_bridge.execute_python.assert_called_once()
        call_args = mock_bridge.execute_python.call_args
        assert call_args.kwargs.get("timeout_ms") == 60000 or call_args.args[1] == 60000

    @pytest.mark.asyncio
    async def test_execute_python_failure(self, register_tools, mock_bridge):
        """execute_python should return error on failure."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=False,
                result=None,
                stdout="",
                stderr="NameError: name 'foo' is not defined",
                execution_time_ms=2.0,
                error_type="NameError",
                error_traceback="Traceback...\nNameError: name 'foo' is not defined",
            )
        )

        execute_python = register_tools["execute_python"]
        result = await execute_python(code="foo")

        assert result["success"] is False
        assert result["error_type"] == "NameError"
        assert "foo" in result["error_traceback"]

    @pytest.mark.asyncio
    async def test_execute_python_reports_continuing_timeout(
        self, register_tools, mock_bridge
    ):
        """Callers must know when timed-out mutation code is still running."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=False,
                result=None,
                stdout="",
                stderr="Execution timed out",
                execution_time_ms=1000.0,
                error_type="TimeoutError",
                execution_continues=True,
            )
        )

        result = await register_tools["execute_python"]("mutate()", timeout_ms=1000)

        assert result["execution_continues"] is True

    @pytest.mark.asyncio
    async def test_execute_python_with_stdout(self, register_tools, mock_bridge):
        """execute_python should capture stdout."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result=None,
                stdout="Hello, World!\n",
                stderr="",
                execution_time_ms=1.0,
            )
        )

        execute_python = register_tools["execute_python"]
        result = await execute_python(code="print('Hello, World!')")

        assert result["success"] is True
        assert result["stdout"] == "Hello, World!\n"

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

    @pytest.mark.asyncio
    async def test_get_mcp_server_environment(self, register_tools, mock_bridge):
        """get_mcp_server_environment should return environment info."""
        mock_bridge.get_status = AsyncMock(
            return_value=ConnectionStatus(
                connected=True,
                mode="xmlrpc",
                freecad_version="1.0.0",
                gui_available=True,
                last_ping_ms=5.0,
                error=None,
            )
        )

        get_env = register_tools["get_mcp_server_environment"]
        result = await get_env()

        # Should have standard fields
        assert "instance_id" in result
        assert "hostname" in result
        assert "os_name" in result
        assert "python_version" in result
        assert "platform" in result
        assert "os_version" in result

        # Verify removed fields are not present (prevent regressions)
        assert "in_docker" not in result
        assert "docker_container_id" not in result

        # Should have freecad status
        assert "freecad" in result
        assert result["freecad"]["connected"] is True
        assert result["freecad"]["mode"] == "xmlrpc"
        assert result["freecad"]["is_headless"] is False

        # Should have env vars
        assert "env_vars" in result
        mock_bridge.get_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_mcp_server_environment_headless(
        self, register_tools, mock_bridge
    ):
        """get_mcp_server_environment should detect headless mode."""
        mock_bridge.get_status = AsyncMock(
            return_value=ConnectionStatus(
                connected=True,
                mode="embedded",
                freecad_version="1.0.0",
                gui_available=False,
                last_ping_ms=0.0,
                error=None,
            )
        )

        get_env = register_tools["get_mcp_server_environment"]
        result = await get_env()

        assert result["freecad"]["gui_available"] is False
        assert result["freecad"]["is_headless"] is True
