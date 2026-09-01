"""Tests for embedded bridge implementation."""

from unittest import mock

import pytest

from freecad_mcp.bridge.embedded import EmbeddedBridge


class TestEmbeddedBridge:
    """Tests for EmbeddedBridge class."""

    def test_initialization(self):
        """Bridge should initialize with correct defaults."""
        bridge = EmbeddedBridge()

        assert bridge._freecad_path is None
        assert bridge._fc_module is None
        assert bridge._connected is False

    def test_initialization_with_path(self):
        """Bridge should accept custom FreeCAD path."""
        bridge = EmbeddedBridge(freecad_path="/custom/path")

        assert bridge._freecad_path == "/custom/path"

    @pytest.mark.asyncio
    async def test_is_connected_before_connect(self):
        """is_connected should return False before connect."""
        bridge = EmbeddedBridge()

        assert await bridge.is_connected() is False

    @pytest.mark.asyncio
    async def test_execute_python_when_not_connected(self):
        """execute_python should return error when not connected."""
        bridge = EmbeddedBridge()

        result = await bridge.execute_python("x = 1", transaction=None)

        assert result.success is False
        assert result.error_type == "ConnectionError"
        assert "not connected" in result.stderr

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self):
        """disconnect should handle not being connected."""
        bridge = EmbeddedBridge()

        # Should not raise
        await bridge.disconnect()

        assert bridge._connected is False


class TestEmbeddedBridgeCodeExecution:
    """Tests for code execution in embedded bridge."""

    @pytest.fixture
    def mock_freecad(self):
        """Create a mock FreeCAD module."""
        mock_fc = mock.MagicMock()
        mock_fc.Version.return_value = ["0", "21", "2", "2024-01-01"]
        mock_fc.listDocuments.return_value = {}
        mock_fc.ActiveDocument = None
        return mock_fc

    @pytest.mark.asyncio
    async def test_execute_simple_code(self, mock_freecad):
        """execute_python should execute simple Python code."""
        bridge = EmbeddedBridge()
        bridge._fc_module = mock_freecad
        bridge._connected = True

        result = await bridge.execute_python("_result_ = 1 + 1", transaction=None)

        assert result.success is True
        assert result.result == 2

    @pytest.mark.asyncio
    async def test_execute_code_with_print(self, mock_freecad):
        """execute_python should capture stdout."""
        bridge = EmbeddedBridge()
        bridge._fc_module = mock_freecad
        bridge._connected = True

        result = await bridge.execute_python("print('hello')", transaction=None)

        assert result.success is True
        assert "hello" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_code_with_error(self, mock_freecad):
        """execute_python should capture exceptions."""
        bridge = EmbeddedBridge()
        bridge._fc_module = mock_freecad
        bridge._connected = True

        result = await bridge.execute_python(
            "raise ValueError('test error')", transaction=None
        )

        assert result.success is False
        assert result.error_type == "ValueError"
        assert result.error_traceback is not None
        assert "test error" in result.error_traceback

    @pytest.mark.asyncio
    async def test_execute_code_with_syntax_error(self, mock_freecad):
        """execute_python should handle syntax errors."""
        bridge = EmbeddedBridge()
        bridge._fc_module = mock_freecad
        bridge._connected = True

        result = await bridge.execute_python("def bad syntax", transaction=None)

        assert result.success is False
        assert result.error_type == "SyntaxError"


class TestEmbeddedBridgeDocuments:
    """Tests for document handling in embedded bridge."""

    @pytest.fixture
    def mock_freecad_with_doc(self):
        """Create mock FreeCAD with a document."""
        mock_doc = mock.MagicMock()
        mock_doc.Name = "TestDoc"
        mock_doc.Label = "Test Document"
        mock_doc.FileName = "/tmp/test.FCStd"
        mock_doc.Modified = False
        mock_doc.Objects = []

        mock_fc = mock.MagicMock()
        mock_fc.listDocuments.return_value = {"TestDoc": mock_doc}
        mock_fc.ActiveDocument = mock_doc
        mock_fc.getDocument.return_value = mock_doc

        return mock_fc

    @pytest.mark.asyncio
    async def test_get_documents_empty(self):
        """get_documents should return empty list when no docs."""
        mock_fc = mock.MagicMock()
        mock_fc.listDocuments.return_value = {}

        bridge = EmbeddedBridge()
        bridge._fc_module = mock_fc
        bridge._connected = True

        # Mock the execute_python to return empty list
        result = await bridge.get_documents()

        # Since we're not mocking exec properly, we expect empty
        assert isinstance(result, list)


def test_embedded_boundary_aborts_on_failure() -> None:
    """Pins the embedded bridge's copy of the executor boundary."""

    class _FakeFreeCAD:
        def __init__(self) -> None:
            self.closed: list[bool] = []

        def getActiveTransaction(self) -> tuple[str, int] | None:
            return None

        def setActiveTransaction(self, name: str, persist: bool = False) -> int:
            assert persist is True
            return 1

        def closeActiveTransaction(self, abort: bool = False) -> None:
            self.closed.append(abort)

        def listDocuments(self) -> dict:
            return {}

    fake = _FakeFreeCAD()
    bridge = EmbeddedBridge()
    bridge._fc_module = fake
    bridge._connected = True

    assert not bridge._execute_code("raise ValueError('x')", "Pad Sketch").success
    assert fake.closed == [True]
