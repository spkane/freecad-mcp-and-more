"""Regression tests for XML-RPC execution timeout propagation."""

from __future__ import annotations

import asyncio
import sys
import threading
import xmlrpc.client
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from freecad_mcp.bridge.base import ExecutionResult
from freecad_mcp.bridge.xmlrpc import XmlRpcBridge


def _clear_workbench_server() -> None:
    """Remove cached workbench server imports before mocking FreeCAD."""
    for module_name in list(sys.modules):
        if module_name.endswith("freecad_mcp_bridge.server"):
            del sys.modules[module_name]


@pytest.mark.asyncio
async def test_xmlrpc_client_forwards_execution_timeout() -> None:
    """The client should pass its requested timeout and transaction to the bridge server."""
    bridge = XmlRpcBridge()
    proxy = MagicMock()
    proxy.execute.return_value = {
        "success": True,
        "result": "ok",
        "stdout": "",
        "stderr": "",
        "execution_time_ms": 1.0,
    }
    bridge._proxy = proxy

    result = await bridge.execute_python(
        "_result_ = 'ok'", timeout_ms=120000, transaction=None
    )

    assert result.success is True
    assert proxy.execute.call_args_list == [
        call("_result_ = 'ok'", 120000, None),
    ]


@pytest.mark.asyncio
async def test_xmlrpc_client_preserves_server_error_message() -> None:
    """Structured server timeout details should reach MCP tool callers."""
    bridge = XmlRpcBridge()
    proxy = MagicMock()
    proxy.execute.return_value = {
        "success": False,
        "result": None,
        "error_type": "TimeoutError",
        "error_message": "Execution timed out after 120000ms",
        "execution_continues": True,
    }
    bridge._proxy = proxy

    result = await bridge.execute_python(
        "slow_operation()", timeout_ms=120000, transaction=None
    )

    assert result.success is False
    assert result.error_type == "TimeoutError"
    assert result.error_traceback == "Execution timed out after 120000ms"
    assert result.execution_continues is True


@pytest.mark.asyncio
async def test_xmlrpc_client_preserves_transport_exception_details() -> None:
    """Marshaller failures should reach the bridge method that requested data."""
    bridge = XmlRpcBridge()
    proxy = MagicMock()
    proxy.execute.side_effect = [
        TypeError("cannot marshal FreeCAD property wrapper"),
    ]
    bridge._proxy = proxy

    with pytest.raises(ValueError, match="cannot marshal FreeCAD property wrapper"):
        await bridge.get_object("Groove")


@pytest.mark.asyncio
async def test_get_object_recursively_serializes_property_values() -> None:
    """Nested FreeCAD values should be safe before crossing XML-RPC."""
    bridge = XmlRpcBridge()
    execute_python = AsyncMock(
        return_value=ExecutionResult(
            success=True,
            result={
                "name": "Groove",
                "label": "Groove",
                "type_id": "PartDesign::Groove",
            },
            stdout="",
            stderr="",
            execution_time_ms=1.0,
        )
    )

    with patch.object(bridge, "execute_python", execute_python):
        await bridge.get_object("Groove")

    code = execute_python.call_args.args[0]
    serializer_source = code.split("doc =", 1)[0]
    namespace: dict[str, object] = {}
    exec(serializer_source, namespace)  # noqa: S102

    class WrappedValue:
        def __str__(self) -> str:
            return "<PartDesign::Feature reference>"

    serialize = namespace["serialize_property_value"]
    serialized = serialize(  # type: ignore[operator]
        {"Profile": (WrappedValue(), ["Edge1", WrappedValue()])}
    )

    assert serialized == {
        "Profile": [
            "<PartDesign::Feature reference>",
            ["Edge1", "<PartDesign::Feature reference>"],
        ]
    }
    xmlrpc.client.dumps((serialized,), allow_none=True)


@pytest.mark.asyncio
async def test_timed_out_client_call_does_not_reuse_busy_proxy() -> None:
    """A request waiting behind a timed-out call must not execute later."""
    bridge = XmlRpcBridge()
    proxy = MagicMock()
    entered = threading.Event()
    release = threading.Event()

    def blocking_execute(*_args: object) -> dict[str, object]:
        entered.set()
        release.wait(timeout=1)
        return {"success": True, "result": "late"}

    proxy.execute.side_effect = blocking_execute
    bridge._proxy = proxy

    first = asyncio.create_task(
        bridge.execute_python("first()", timeout_ms=100, transaction=None)
    )
    assert await asyncio.to_thread(entered.wait, 1)
    second = asyncio.create_task(
        bridge.execute_python("second()", timeout_ms=10, transaction=None)
    )
    await asyncio.sleep(0.05)
    release.set()
    first_result, second_result = await asyncio.gather(first, second)

    await asyncio.sleep(0.05)
    assert first_result.success is True
    assert second_result.error_type == "TimeoutError"
    # With no probe call, only the first request reaches proxy.execute.
    assert proxy.execute.call_count == 1


def test_xmlrpc_server_uses_requested_execution_timeout() -> None:
    """The server should not replace a caller timeout with 30 seconds."""
    freecad = MagicMock()
    freecad.GuiUp = False
    with patch.dict(
        sys.modules,
        {"FreeCAD": freecad, "FreeCADGui": MagicMock()},
    ):
        _clear_workbench_server()
        from freecad.RobustMCPBridge.freecad_mcp_bridge import server

        plugin = server.FreecadMCPPlugin()
        execute = MagicMock(return_value={"success": True})
        with patch.object(plugin, "_execute_via_queue", execute):
            result = plugin._xmlrpc_execute("_result_ = True", 120000, None)

    assert result == {"success": True}
    execute.assert_called_once_with("_result_ = True", 120000, None)


def test_xmlrpc_server_sanitizes_unrepresentable_results() -> None:
    """Responses should survive XML 1.0 parsing after successful execution."""

    class WrappedValue:
        def __str__(self) -> str:
            return "<PartDesign::Feature reference>"

    freecad = MagicMock()
    freecad.GuiUp = False
    with patch.dict(
        sys.modules,
        {"FreeCAD": freecad, "FreeCADGui": MagicMock()},
    ):
        _clear_workbench_server()
        from freecad.RobustMCPBridge.freecad_mcp_bridge import server

        plugin = server.FreecadMCPPlugin()
        execute = MagicMock(
            return_value={
                "success": True,
                "result": {
                    "label": "control\x00character\x01",
                    "large_integer": 2**40,
                    "nested_wrapper": (WrappedValue(), [WrappedValue()]),
                },
            }
        )
        with patch.object(plugin, "_execute_via_queue", execute):
            result = plugin._xmlrpc_execute("_result_ = True", 30000, None)
        payload = xmlrpc.client.dumps((result,), allow_none=True)
        decoded, _ = xmlrpc.client.loads(payload)

    assert result["result"]["label"] == "control\ufffdcharacter\ufffd"
    assert result["result"]["large_integer"] == str(2**40)
    assert result["result"]["nested_wrapper"] == [
        "<PartDesign::Feature reference>",
        ["<PartDesign::Feature reference>"],
    ]
    assert decoded[0] == result


def test_timed_out_queued_request_is_not_executed_later() -> None:
    """A request that expires in the queue must not execute after its caller left."""
    freecad = MagicMock()
    freecad.GuiUp = False
    with patch.dict(
        sys.modules,
        {"FreeCAD": freecad, "FreeCADGui": MagicMock()},
    ):
        _clear_workbench_server()
        from freecad.RobustMCPBridge.freecad_mcp_bridge import server

        plugin = server.FreecadMCPPlugin()
        plugin._running = True
        execute = MagicMock(return_value={"success": True})
        with patch.object(plugin, "_execute_code_sync", execute):
            result = plugin._execute_via_queue("_result_ = True", 1, None)
            plugin._process_queue()

    assert result["error_type"] == "TimeoutError"
    execute.assert_not_called()


def test_started_request_blocks_follow_up_execution() -> None:
    """A timed-out running request should keep the bridge busy until completion."""
    freecad = MagicMock()
    freecad.GuiUp = False
    with patch.dict(
        sys.modules,
        {"FreeCAD": freecad, "FreeCADGui": MagicMock()},
    ):
        _clear_workbench_server()
        from freecad.RobustMCPBridge.freecad_mcp_bridge import server

        plugin = server.FreecadMCPPlugin()
        request = server.ExecutionRequest("first()")
        assert request.start_if_pending()
        with patch.object(server, "ExecutionRequest", return_value=request):
            first = plugin._execute_via_queue("first()", 1, None)
            second = plugin._execute_via_queue("second()", 1, None)

    assert first["execution_continues"] is True
    assert second["error_type"] == "BusyError"
