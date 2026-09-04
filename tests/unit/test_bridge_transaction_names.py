"""Tests that each bridge declares a transaction for its mutating methods.

``create_object``, ``edit_object`` and ``delete_object`` are implemented
separately on every bridge. They once opened raw transactions inside their
generated code; the executor owns that boundary now, so each must declare a
name at its ``execute_python`` call instead.

The tool-level tests mock the bridge, so they never observe these arguments.
That blind spot is not hypothetical: the migration moved xmlrpc to declared
names and left socket and embedded passing ``None``, which made ``edit_object``
undoable in one mode and silently not undoable in the other two. These tests
assert the argument directly, on every bridge, so the modes cannot drift again.
"""

import pytest

from freecad_mcp.bridge.base import ExecutionResult


def _ok(result):
    return ExecutionResult(
        success=True,
        result=result,
        stdout="",
        stderr="",
        error_traceback=None,
        execution_time_ms=1.0,
    )


@pytest.fixture(
    params=["xmlrpc", "socket", "embedded"],
    ids=["XmlRpcBridge", "SocketBridge", "EmbeddedBridge"],
)
def bridge(request):
    if request.param == "xmlrpc":
        from freecad_mcp.bridge.xmlrpc import XmlRpcBridge

        return XmlRpcBridge()
    if request.param == "socket":
        from freecad_mcp.bridge.socket import SocketBridge

        return SocketBridge()
    from freecad_mcp.bridge.embedded import EmbeddedBridge

    return EmbeddedBridge()


def _record(bridge, result):
    """Capture the kwargs of the bridge's execute_python call."""
    calls = []

    async def fake_execute_python(_code, *_args, **kwargs):
        calls.append(kwargs)
        return _ok(result)

    bridge.execute_python = fake_execute_python
    return calls


@pytest.mark.asyncio
async def test_create_object_declares_its_transaction(bridge):
    """A created object must be undoable in every connection mode."""
    calls = _record(
        bridge,
        {"name": "Box", "label": "Box", "type_id": "Part::Box", "visibility": True},
    )

    await bridge.create_object("Part::Box", "Box")

    assert calls, "create_object never called execute_python"
    assert calls[-1].get("transaction") == "Create Object"


@pytest.mark.asyncio
async def test_edit_object_declares_its_transaction(bridge):
    """edit_object is a registered tool; a failed edit must roll back."""
    calls = _record(
        bridge,
        {"name": "Box", "label": "Box", "type_id": "Part::Box", "visibility": True},
    )

    await bridge.edit_object("Box", {"Length": 20})

    assert calls, "edit_object never called execute_python"
    assert calls[-1].get("transaction") == "Edit Object"


@pytest.mark.asyncio
async def test_delete_object_declares_its_transaction(bridge):
    """A deletion the user cannot undo is the worst kind to leave untransacted."""
    calls = _record(bridge, True)

    await bridge.delete_object("Box")

    assert calls, "delete_object never called execute_python"
    assert calls[-1].get("transaction") == "Delete Object"
