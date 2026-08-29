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

    @pytest.mark.asyncio
    async def test_undo_if_invalid_already_valid(self, register_tools, mock_bridge):
        """undo_if_invalid should not undo when document is already valid."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "was_valid": True,
                    "undone": False,
                    "invalid_objects": [],
                    "objects_with_errors": [],
                    "message": "Document is valid, no undo needed",
                    "validation_after": None,
                },
                stdout="",
                stderr="",
                execution_time_ms=1.0,
                error_traceback=None,
            )
        )

        undo_if_invalid = register_tools["undo_if_invalid"]
        result = await undo_if_invalid()

        assert result["was_valid"] is True
        assert result["undone"] is False
        assert "no undo needed" in result["message"]

    @pytest.mark.asyncio
    async def test_undo_if_invalid_performs_undo(self, register_tools, mock_bridge):
        """undo_if_invalid should undo when invalid objects exist."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "was_valid": False,
                    "undone": True,
                    "invalid_objects": ["BrokenBox"],
                    "objects_with_errors": [],
                    "message": "Undid last operation. Document is now valid.",
                    "validation_after": {
                        "valid": True,
                        "invalid_objects": [],
                        "objects_with_errors": [],
                    },
                },
                stdout="",
                stderr="",
                execution_time_ms=1.0,
                error_traceback=None,
            )
        )

        undo_if_invalid = register_tools["undo_if_invalid"]
        result = await undo_if_invalid()

        assert result["was_valid"] is False
        assert result["undone"] is True
        assert "BrokenBox" in result["invalid_objects"]
        assert result["validation_after"]["valid"] is True

    @pytest.mark.asyncio
    async def test_undo_if_invalid_still_invalid_after_undo(
        self, register_tools, mock_bridge
    ):
        """undo_if_invalid should report when still invalid after undo."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "was_valid": False,
                    "undone": True,
                    "invalid_objects": ["BrokenBox", "BrokenCylinder"],
                    "objects_with_errors": [],
                    "message": "Undid last operation, but document still has issues.",
                    "validation_after": {
                        "valid": False,
                        "invalid_objects": ["BrokenBox"],
                        "objects_with_errors": [],
                    },
                },
                stdout="",
                stderr="",
                execution_time_ms=1.0,
                error_traceback=None,
            )
        )

        undo_if_invalid = register_tools["undo_if_invalid"]
        result = await undo_if_invalid()

        assert result["undone"] is True
        assert result["validation_after"]["valid"] is False
        assert "still has issues" in result["message"]

    @pytest.mark.asyncio
    async def test_undo_if_invalid_with_doc_name(self, register_tools, mock_bridge):
        """undo_if_invalid should accept doc_name parameter."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "was_valid": True,
                    "undone": False,
                    "invalid_objects": [],
                    "objects_with_errors": [],
                    "message": "Document is valid, no undo needed",
                    "validation_after": None,
                },
                stdout="",
                stderr="",
                execution_time_ms=1.0,
                error_traceback=None,
            )
        )

        undo_if_invalid = register_tools["undo_if_invalid"]
        result = await undo_if_invalid(doc_name="SpecificDoc")

        assert result["was_valid"] is True
        # Verify the doc_name was passed in the code
        call_args = mock_bridge.execute_python.call_args[0][0]
        assert "SpecificDoc" in call_args

    # ========== safe_execute tests ==========

    @pytest.mark.asyncio
    async def test_safe_execute_success(self, register_tools, mock_bridge):
        """safe_execute should succeed with valid code."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "success": True,
                    "result": {"created": "Box"},
                    "rolled_back": False,
                    "execution_success": True,
                    "execution_error": None,
                    "validation": {
                        "valid": True,
                        "invalid_objects": [],
                        "objects_with_errors": [],
                    },
                    "message": "Operation completed successfully",
                },
                stdout="",
                stderr="",
                execution_time_ms=1.0,
                error_traceback=None,
            )
        )

        safe_execute = register_tools["safe_execute"]
        result = await safe_execute('_result_ = {"created": "Box"}')

        assert result["success"] is True
        assert result["result"]["created"] == "Box"
        assert result["rolled_back"] is False
        assert result["execution_success"] is True
        assert result["validation"]["valid"] is True

    @pytest.mark.asyncio
    async def test_safe_execute_execution_failure(self, register_tools, mock_bridge):
        """safe_execute should rollback on execution failure."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "success": False,
                    "result": None,
                    "rolled_back": True,
                    "execution_success": False,
                    "execution_error": "NameError: name 'undefined' is not defined",
                    "validation": None,
                    "message": "Execution failed: NameError (rolled back)",
                },
                stdout="",
                stderr="",
                execution_time_ms=1.0,
                error_traceback=None,
            )
        )

        safe_execute = register_tools["safe_execute"]
        result = await safe_execute("undefined_function()")

        assert result["success"] is False
        assert result["rolled_back"] is True
        assert result["execution_success"] is False
        assert "NameError" in result["execution_error"]

    @pytest.mark.asyncio
    async def test_safe_execute_validation_failure(self, register_tools, mock_bridge):
        """safe_execute should rollback on validation failure."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "success": False,
                    "result": None,
                    "rolled_back": True,
                    "execution_success": True,
                    "execution_error": None,
                    "validation": {
                        "valid": False,
                        "invalid_objects": ["BrokenBox"],
                        "objects_with_errors": [],
                    },
                    "message": "Validation failed: 1 invalid objects (rolled back)",
                },
                stdout="",
                stderr="",
                execution_time_ms=1.0,
                error_traceback=None,
            )
        )

        safe_execute = register_tools["safe_execute"]
        result = await safe_execute("create_broken_box()")

        assert result["success"] is False
        assert result["rolled_back"] is True
        assert result["execution_success"] is True
        assert result["validation"]["valid"] is False

    @pytest.mark.asyncio
    async def test_safe_execute_no_auto_undo(self, register_tools, mock_bridge):
        """safe_execute should not rollback when auto_undo_on_failure is False."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "success": False,
                    "result": None,
                    "rolled_back": False,
                    "execution_success": True,
                    "execution_error": None,
                    "validation": {
                        "valid": False,
                        "invalid_objects": ["BrokenBox"],
                        "objects_with_errors": [],
                    },
                    "message": "Validation failed: 1 invalid objects",
                },
                stdout="",
                stderr="",
                execution_time_ms=1.0,
                error_traceback=None,
            )
        )

        safe_execute = register_tools["safe_execute"]
        result = await safe_execute("create_broken_box()", auto_undo_on_failure=False)

        assert result["success"] is False
        assert result["rolled_back"] is False

    @pytest.mark.asyncio
    async def test_safe_execute_no_validation(self, register_tools, mock_bridge):
        """safe_execute should skip validation when validate_after is False."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "success": True,
                    "result": {"done": True},
                    "rolled_back": False,
                    "execution_success": True,
                    "execution_error": None,
                    "validation": None,
                    "message": "Operation completed successfully",
                },
                stdout="",
                stderr="",
                execution_time_ms=1.0,
                error_traceback=None,
            )
        )

        safe_execute = register_tools["safe_execute"]
        result = await safe_execute('_result_ = {"done": True}', validate_after=False)

        assert result["success"] is True
        assert result["validation"] is None

    @pytest.mark.asyncio
    async def test_safe_execute_with_doc_name(self, register_tools, mock_bridge):
        """safe_execute should accept doc_name parameter."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "success": True,
                    "result": None,
                    "rolled_back": False,
                    "execution_success": True,
                    "execution_error": None,
                    "validation": {
                        "valid": True,
                        "invalid_objects": [],
                        "objects_with_errors": [],
                    },
                    "message": "Operation completed successfully",
                },
                stdout="",
                stderr="",
                execution_time_ms=1.0,
                error_traceback=None,
            )
        )

        safe_execute = register_tools["safe_execute"]
        result = await safe_execute("pass", doc_name="MyDocument")

        assert result["success"] is True
        # Verify doc_name was passed
        call_args = mock_bridge.execute_python.call_args[0][0]
        assert "MyDocument" in call_args


class TestValidationToolsRegistration:
    """Tests for validation tools registration."""

    def test_all_tools_registered(self):
        """Verify all validation tools are registered."""
        from unittest.mock import MagicMock

        from freecad_mcp.tools.validation import register_validation_tools

        mcp = MagicMock()
        registered_tools = {}

        def tool_decorator():
            def wrapper(func):
                registered_tools[func.__name__] = func
                return func

            return wrapper

        mcp.tool = tool_decorator

        async def get_bridge():
            return MagicMock()

        register_validation_tools(mcp, get_bridge)

        expected_tools = [
            "validate_object",
            "validate_document",
            "undo_if_invalid",
            "safe_execute",
        ]

        for tool_name in expected_tools:
            assert tool_name in registered_tools, f"Tool {tool_name} not registered"

        assert len(registered_tools) == len(expected_tools)
