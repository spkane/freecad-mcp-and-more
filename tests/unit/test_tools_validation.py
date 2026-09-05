"""Tests for validation tools module."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from freecad_mcp.bridge.base import ExecutionResult


class TestValidationTools:
    """Tests for validation tools."""

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
        """Register validation tools and return the registered functions."""
        from freecad_mcp.tools.validation import register_validation_tools

        async def get_bridge():
            return mock_bridge

        register_validation_tools(mock_mcp, get_bridge)
        return mock_mcp._registered_tools

    # ========== validate_object tests ==========

    @pytest.mark.asyncio
    async def test_validate_object_valid(self, register_tools, mock_bridge):
        """validate_object should return valid status for valid object."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "valid": True,
                    "object_name": "Box",
                    "shape_valid": True,
                    "has_errors": False,
                    "state": [],
                    "recompute_needed": False,
                    "volume": 1000.0,
                    "area": 600.0,
                    "error_messages": [],
                    "warnings": [],
                },
                stdout="",
                stderr="",
                execution_time_ms=1.0,
                error_traceback=None,
            )
        )

        validate_object = register_tools["validate_object"]
        result = await validate_object("Box")

        assert result["valid"] is True
        assert result["object_name"] == "Box"
        assert result["shape_valid"] is True
        assert result["has_errors"] is False
        assert result["volume"] == 1000.0
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_object_invalid_shape(self, register_tools, mock_bridge):
        """validate_object should detect invalid shape geometry."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "valid": False,
                    "object_name": "BrokenBox",
                    "shape_valid": False,
                    "has_errors": False,
                    "state": [],
                    "recompute_needed": False,
                    "volume": 0.0,
                    "area": 0.0,
                    "error_messages": ["Shape geometry is invalid"],
                    "warnings": [],
                },
                stdout="",
                stderr="",
                execution_time_ms=1.0,
                error_traceback=None,
            )
        )

        validate_object = register_tools["validate_object"]
        result = await validate_object("BrokenBox")

        assert result["valid"] is False
        assert result["shape_valid"] is False
        assert "Shape geometry is invalid" in result["error_messages"]

    @pytest.mark.asyncio
    async def test_validate_object_with_errors(self, register_tools, mock_bridge):
        """validate_object should detect error states."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "valid": False,
                    "object_name": "ErrorBox",
                    "shape_valid": True,
                    "has_errors": True,
                    "state": ["Invalid", "Touched"],
                    "recompute_needed": True,
                    "volume": 1000.0,
                    "area": 600.0,
                    "error_messages": [],
                    "warnings": [],
                },
                stdout="",
                stderr="",
                execution_time_ms=1.0,
                error_traceback=None,
            )
        )

        validate_object = register_tools["validate_object"]
        result = await validate_object("ErrorBox")

        assert result["valid"] is False
        assert result["has_errors"] is True
        assert "Invalid" in result["state"]
        assert result["recompute_needed"] is True

    @pytest.mark.asyncio
    async def test_validate_object_not_found(self, register_tools, mock_bridge):
        """validate_object should handle object not found."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "valid": False,
                    "object_name": "NonExistent",
                    "shape_valid": False,
                    "has_errors": True,
                    "state": [],
                    "recompute_needed": False,
                    "volume": None,
                    "area": None,
                    "error_messages": [
                        "Object 'NonExistent' not found in document 'TestDoc'"
                    ],
                    "warnings": [],
                },
                stdout="",
                stderr="",
                execution_time_ms=1.0,
                error_traceback=None,
            )
        )

        validate_object = register_tools["validate_object"]
        result = await validate_object("NonExistent", doc_name="TestDoc")

        assert result["valid"] is False
        assert "not found" in result["error_messages"][0]

    @pytest.mark.asyncio
    async def test_validate_object_with_warnings(self, register_tools, mock_bridge):
        """validate_object should report warnings."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "valid": True,
                    "object_name": "ThinBox",
                    "shape_valid": True,
                    "has_errors": False,
                    "state": [],
                    "recompute_needed": False,
                    "volume": 0.001,
                    "area": 1.0,
                    "error_messages": [],
                    "warnings": ["Shape has non-positive volume: 0.001"],
                },
                stdout="",
                stderr="",
                execution_time_ms=1.0,
                error_traceback=None,
            )
        )

        validate_object = register_tools["validate_object"]
        result = await validate_object("ThinBox")

        assert result["valid"] is True  # Valid but with warnings
        assert len(result["warnings"]) > 0

    @pytest.mark.asyncio
    async def test_validate_object_can_require_one_solid(
        self, register_tools, mock_bridge
    ):
        """validate_object should enforce an explicit single-solid policy."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "valid": False,
                    "object_name": "Body",
                    "shape_valid": True,
                    "has_errors": False,
                    "state": [],
                    "recompute_needed": False,
                    "volume": 1000.0,
                    "area": 600.0,
                    "solid_count": 2,
                    "single_solid": False,
                    "error_messages": ["Expected exactly one solid, found 2"],
                    "warnings": [],
                },
                stdout="",
                stderr="",
                execution_time_ms=1.0,
                error_traceback=None,
            )
        )

        validate_object = register_tools["validate_object"]
        result = await validate_object("Body", require_single_solid=True)

        assert result["solid_count"] == 2
        assert result["single_solid"] is False
        assert result["valid"] is False
        code = mock_bridge.execute_python.call_args.args[0]
        assert "len(shape.Solids)" in code
        assert "Expected exactly one solid" in code

    @pytest.mark.asyncio
    async def test_validate_object_rejects_null_and_touched_geometry(
        self, register_tools, mock_bridge
    ):
        """Null feature shapes and unrecomputed state must not pass validation."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"valid": False},
                stdout="",
                stderr="",
                execution_time_ms=1.0,
            )
        )

        await register_tools["validate_object"]("Pad")

        code = mock_bridge.execute_python.call_args.args[0]
        assert "shape.isNull()" in code
        assert 'error_messages.append("Object still needs recompute")' in code
        assert "and not recompute_needed" in code
        assert '"PartDesign::Plane"' in code
        assert "obj.TypeId not in shape_exempt_type_ids" in code

    # ========== validate_document tests ==========

    @pytest.mark.asyncio
    async def test_validate_document_healthy(self, register_tools, mock_bridge):
        """validate_document should return valid for healthy document."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "valid": True,
                    "doc_name": "TestDoc",
                    "total_objects": 3,
                    "valid_objects": 3,
                    "invalid_objects": [],
                    "objects_with_errors": [],
                    "objects_needing_recompute": [],
                    "recompute_needed": False,
                    "summary": "Document 'TestDoc' is healthy: all 3 objects are valid",
                },
                stdout="",
                stderr="",
                execution_time_ms=1.0,
                error_traceback=None,
            )
        )

        validate_document = register_tools["validate_document"]
        result = await validate_document()

        assert result["valid"] is True
        assert result["total_objects"] == 3
        assert result["valid_objects"] == 3
        assert len(result["invalid_objects"]) == 0
        assert "healthy" in result["summary"]

    @pytest.mark.asyncio
    async def test_validate_document_with_invalid_objects(
        self, register_tools, mock_bridge
    ):
        """validate_document should detect invalid objects."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "valid": False,
                    "doc_name": "TestDoc",
                    "total_objects": 5,
                    "valid_objects": 3,
                    "invalid_objects": ["BrokenBox", "BadCylinder"],
                    "objects_with_errors": ["BrokenBox"],
                    "objects_needing_recompute": ["BadCylinder"],
                    "recompute_needed": True,
                    "summary": "Document 'TestDoc' has issues: 2 invalid objects",
                },
                stdout="",
                stderr="",
                execution_time_ms=1.0,
                error_traceback=None,
            )
        )

        validate_document = register_tools["validate_document"]
        result = await validate_document("TestDoc")

        assert result["valid"] is False
        assert result["total_objects"] == 5
        assert result["valid_objects"] == 3
        assert "BrokenBox" in result["invalid_objects"]
        assert "BadCylinder" in result["invalid_objects"]
        assert result["recompute_needed"] is True

    @pytest.mark.asyncio
    async def test_validate_document_empty(self, register_tools, mock_bridge):
        """validate_document should handle empty document."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "valid": True,
                    "doc_name": "EmptyDoc",
                    "total_objects": 0,
                    "valid_objects": 0,
                    "invalid_objects": [],
                    "objects_with_errors": [],
                    "objects_needing_recompute": [],
                    "recompute_needed": False,
                    "summary": "Document 'EmptyDoc' is healthy: all 0 objects are valid",
                },
                stdout="",
                stderr="",
                execution_time_ms=1.0,
                error_traceback=None,
            )
        )

        validate_document = register_tools["validate_document"]
        result = await validate_document("EmptyDoc")

        assert result["valid"] is True
        assert result["total_objects"] == 0

    @pytest.mark.asyncio
    async def test_validate_document_no_active(self, register_tools, mock_bridge):
        """validate_document should handle no active document."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "valid": False,
                    "doc_name": None,
                    "total_objects": 0,
                    "valid_objects": 0,
                    "invalid_objects": [],
                    "objects_with_errors": [],
                    "objects_needing_recompute": [],
                    "recompute_needed": False,
                    "summary": "No active document found",
                },
                stdout="",
                stderr="",
                execution_time_ms=1.0,
                error_traceback=None,
            )
        )

        validate_document = register_tools["validate_document"]
        result = await validate_document()

        assert result["valid"] is False
        assert "No active document" in result["summary"]

    @pytest.mark.asyncio
    async def test_validate_document_reports_solid_counts(
        self, register_tools, mock_bridge
    ):
        """Document validation should expose solid counts and policy failures."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "valid": False,
                    "doc_name": "TestDoc",
                    "total_objects": 2,
                    "valid_objects": 2,
                    "invalid_objects": [],
                    "objects_with_errors": [],
                    "objects_needing_recompute": [],
                    "recompute_needed": False,
                    "solid_counts": {"Body": 2},
                    "single_solid_violations": ["Body"],
                    "summary": "Document 'TestDoc' has issues: 1 single-solid violation",
                },
                stdout="",
                stderr="",
                execution_time_ms=1.0,
                error_traceback=None,
            )
        )

        validate_document = register_tools["validate_document"]
        result = await validate_document(require_single_solid=True)

        assert result["solid_counts"] == {"Body": 2}
        assert result["single_solid_violations"] == ["Body"]
        code = mock_bridge.execute_python.call_args.args[0]
        assert "single_solid_violations" in code
        assert 'obj.TypeId == "PartDesign::Body"' in code

    @pytest.mark.asyncio
    async def test_validate_document_rejects_touched_and_null_bodies(
        self, register_tools, mock_bridge
    ):
        """Document health must fail until Bodies have a current single solid."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"valid": False},
                stdout="",
                stderr="",
                execution_time_ms=1.0,
            )
        )

        await register_tools["validate_document"](require_single_solid=True)

        code = mock_bridge.execute_python.call_args.args[0]
        assert 'if "Touched" in state:' in code
        assert "is_valid = False" in code
        assert "shape is None or shape.isNull()" in code
        assert "solid_counts[obj.Name] = 0" in code
        assert "and not objects_needing_recompute" in code

    # ========== undo_if_invalid tests ==========

    # ========== safe_execute tests ==========

    @pytest.mark.asyncio
    async def test_validate_document_reports_why_each_object_is_invalid(
        self, register_tools, mock_bridge
    ):
        """A name alone does not tell an agent what to repair.

        `validate_document` is the tool an agent reaches for when it wants
        to know what is wrong, so it must carry FreeCAD's own reason next
        to each flagged name, not just the name.
        """
        mock_bridge.execute_python.return_value = ExecutionResult(
            success=True,
            result={"valid": True, "doc_name": "Lighthouse", "diagnostics": {}},
            stdout="",
            stderr="",
            execution_time_ms=5.0,
        )

        validate_document = register_tools["validate_document"]
        await validate_document(doc_name="Lighthouse")

        code = mock_bridge.execute_python.call_args.args[0]
        assert "object_diagnostics(candidate)" in code
        assert '"diagnostics": diagnostics' in code
        compile(code, "<validate_document>", "exec")


class TestValidationToolsRegistration:
    """Tests for validation tools registration."""
