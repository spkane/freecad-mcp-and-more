"""Tests for bridge base classes."""

from unittest.mock import AsyncMock, patch

import pytest

from freecad_mcp.bridge.base import (
    DocumentInfo,
    ExecutionResult,
    FreecadBridge,
    ObjectInfo,
)
from freecad_mcp.bridge.embedded import EmbeddedBridge
from freecad_mcp.bridge.socket import SocketBridge
from freecad_mcp.bridge.xmlrpc import XmlRpcBridge


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    def test_successful_result(self):
        """Successful execution result should have correct attributes."""
        result = ExecutionResult(
            success=True,
            result={"value": 42},
            stdout="output",
            stderr="",
            execution_time_ms=10.5,
        )

        assert result.success is True
        assert result.result == {"value": 42}
        assert result.stdout == "output"
        assert result.stderr == ""
        assert result.execution_time_ms == 10.5
        assert result.error_type is None
        assert result.error_traceback is None

    def test_failed_result(self):
        """Failed execution result should include error details."""
        result = ExecutionResult(
            success=False,
            result=None,
            stdout="",
            stderr="error occurred",
            execution_time_ms=5.0,
            error_type="ValueError",
            error_traceback="Traceback...",
        )

        assert result.success is False
        assert result.result is None
        assert result.error_type == "ValueError"
        assert result.error_traceback == "Traceback..."


class TestDocumentInfo:
    """Tests for DocumentInfo dataclass."""

    def test_document_with_all_fields(self):
        """DocumentInfo should store all fields correctly."""
        doc = DocumentInfo(
            name="TestDoc",
            path="/path/to/doc.FCStd",
            objects=["Box", "Cylinder"],
            is_modified=True,
            label="Test Document",
        )

        assert doc.name == "TestDoc"
        assert doc.path == "/path/to/doc.FCStd"
        assert doc.objects == ["Box", "Cylinder"]
        assert doc.is_modified is True
        assert doc.label == "Test Document"

    def test_document_with_defaults(self):
        """DocumentInfo should use sensible defaults."""
        doc = DocumentInfo(name="Doc", path=None)

        assert doc.name == "Doc"
        assert doc.path is None
        assert doc.objects == []
        assert doc.is_modified is False
        assert doc.label == "Doc"  # Label defaults to name


class TestObjectInfo:
    """Tests for ObjectInfo dataclass."""

    def test_object_with_shape(self):
        """ObjectInfo should store shape information correctly."""
        obj = ObjectInfo(
            name="Box",
            label="My Box",
            type_id="Part::Box",
            properties={"Length": 10.0},
            shape_info={"type": "Solid", "volume": 1000.0},
            children=["Child1"],
        )

        assert obj.name == "Box"
        assert obj.label == "My Box"
        assert obj.type_id == "Part::Box"
        assert obj.properties == {"Length": 10.0}
        assert obj.shape_info == {"type": "Solid", "volume": 1000.0}
        assert obj.children == ["Child1"]

    def test_object_with_defaults(self):
        """ObjectInfo should use sensible defaults."""
        obj = ObjectInfo(name="Obj", label="Obj", type_id="Part::Feature")

        assert obj.properties == {}
        assert obj.shape_info is None
        assert obj.children == []


class TestFreecadBridgeInterface:
    """Tests for FreecadBridge abstract interface."""

    def test_cannot_instantiate_abstract_class(self):
        """FreecadBridge should not be instantiable directly."""
        with pytest.raises(TypeError):
            FreecadBridge()  # type: ignore[abstract]

    def test_subclass_must_implement_methods(self):
        """Subclass must implement all abstract methods."""

        class IncompleteBridge(FreecadBridge):
            pass

        with pytest.raises(TypeError):
            IncompleteBridge()  # type: ignore[abstract]


@pytest.mark.asyncio
@pytest.mark.parametrize("bridge_type", [XmlRpcBridge, SocketBridge, EmbeddedBridge])
async def test_get_object_preserves_transport_stderr(bridge_type) -> None:
    """Object inspection should expose transport failures from every bridge."""
    bridge = bridge_type()
    execute_python = AsyncMock(
        return_value=ExecutionResult(
            success=False,
            result=None,
            stdout="",
            stderr="bridge transport unavailable",
            execution_time_ms=1.0,
            error_type="ConnectionError",
        )
    )

    try:
        with (
            patch.object(bridge, "execute_python", execute_python),
            pytest.raises(ValueError, match="bridge transport unavailable"),
        ):
            await bridge.get_object("Body")
    finally:
        if isinstance(bridge, EmbeddedBridge):
            await bridge.disconnect()
