"""Tests for object tools module."""

import base64
from unittest.mock import AsyncMock, MagicMock

import pytest

from freecad_mcp.bridge.base import ExecutionResult, ObjectInfo
from freecad_mcp.tools.objects import _decode_query_cursor, _query_signature


class TestObjectTools:
    """Tests for object management tools."""

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
        """Register object tools and return the registered functions."""
        from freecad_mcp.tools.objects import register_object_tools

        async def get_bridge():
            return mock_bridge

        register_object_tools(mock_mcp, get_bridge)
        return mock_mcp._registered_tools

    @pytest.mark.asyncio
    async def test_list_objects_empty(self, register_tools, mock_bridge):
        """list_objects should return empty list when no objects."""
        mock_bridge.get_objects = AsyncMock(return_value=[])

        list_objects = register_tools["list_objects"]
        result = await list_objects()

        assert result == []
        mock_bridge.get_objects.assert_called_once_with(None)

    @pytest.mark.asyncio
    async def test_list_objects_with_objects(self, register_tools, mock_bridge):
        """list_objects should return object info."""
        mock_objects = [
            ObjectInfo(
                name="Box",
                label="My Box",
                type_id="Part::Box",
                visibility=True,
                children=[],
                parents=[],
            ),
            ObjectInfo(
                name="Cylinder",
                label="My Cylinder",
                type_id="Part::Cylinder",
                visibility=False,
                children=[],
                parents=[],
            ),
        ]
        mock_bridge.get_objects = AsyncMock(return_value=mock_objects)

        list_objects = register_tools["list_objects"]
        result = await list_objects(doc_name="TestDoc")

        assert len(result) == 2
        assert result[0]["name"] == "Box"
        assert result[0]["type_id"] == "Part::Box"
        assert result[0]["visibility"] is True
        assert result[1]["name"] == "Cylinder"
        assert result[1]["visibility"] is False
        mock_bridge.get_objects.assert_called_once_with("TestDoc")

    @pytest.mark.asyncio
    async def test_query_objects_filters_and_bounds_results(
        self, register_tools, mock_bridge
    ):
        """query_objects should filter in FreeCAD and return a bounded page."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "document_ref": {"name": "TestDoc", "revision": "rev_7"},
                    "items": [
                        {
                            "name": "DoorPocket",
                            "label": "Door Pocket",
                            "type_id": "PartDesign::Pocket",
                            "visibility": True,
                        }
                    ],
                    "matched_count": 2,
                    "returned_count": 1,
                    "next_cursor": "cmV2Xzc6cXVlcnk6MQ",
                    "truncated": True,
                },
                stdout="",
                stderr="",
                execution_time_ms=5.0,
            )
        )

        query_objects = register_tools["query_objects"]
        result = await query_objects(
            query="door",
            type_ids=["PartDesign::Pocket"],
            visible_only=True,
            detail="summary",
            limit=1,
            doc_name="TestDoc",
        )

        assert result["items"][0]["name"] == "DoorPocket"
        assert result["truncated"] is True
        code = mock_bridge.execute_python.call_args.args[0]
        assert "matched.sort(key=lambda item: item.Name)" in code
        assert "page = matched[offset:offset + limit]" in code
        assert 'detail == "detailed"' in code
        assert "solid_count" in code
        assert "require_expected_revision(doc, expected_revision)" in code
        assert "cursor_revision != current_revision" in code
        assert "encode_cursor(current_revision" in code
        assert "candidate.Content" in code
        assert "-(2 ** 31) <= value < 2 ** 31" in code
        compile(code, "<query_objects>", "exec")
        mock_bridge.get_objects.assert_not_called()

    @pytest.mark.asyncio
    async def test_query_objects_rejects_bad_cursor(self, register_tools, mock_bridge):
        """A malformed page cursor should fail before reaching FreeCAD."""
        query_objects = register_tools["query_objects"]

        with pytest.raises(ValueError, match="Cursor is invalid"):
            await query_objects(cursor="not-an-offset")

        mock_bridge.execute_python.assert_not_called()

    def test_query_cursor_rejects_noncanonical_trailing_characters(self):
        """Opaque cursors should have one strict URL-safe Base64 representation."""
        signature = _query_signature(None, [], [], False, "summary")
        payload = f"rev_example:{signature}:4".encode()
        cursor = base64.urlsafe_b64encode(payload).decode().rstrip("=")

        assert _decode_query_cursor(cursor, signature) == ("rev_example", 4)
        with pytest.raises(ValueError, match="Cursor is invalid"):
            _decode_query_cursor(cursor + "!!!!", signature)

    @pytest.mark.asyncio
    async def test_inspect_object(self, register_tools, mock_bridge):
        """inspect_object should return detailed object info."""
        mock_object = ObjectInfo(
            name="Box",
            label="My Box",
            type_id="Part::Box",
            properties={"Length": 10.0, "Width": 20.0, "Height": 30.0},
            shape_info={
                "shape_type": "Solid",
                "volume": 6000.0,
                "area": 2200.0,
                "is_valid": True,
            },
            visibility=True,
            children=["Fillet001"],
            parents=[],
        )
        mock_bridge.get_object = AsyncMock(return_value=mock_object)

        inspect_object = register_tools["inspect_object"]
        result = await inspect_object(object_name="Box")

        assert result["name"] == "Box"
        assert result["type_id"] == "Part::Box"
        assert result["properties"]["Length"] == 10.0
        assert result["shape_info"]["volume"] == 6000.0
        assert result["children"] == ["Fillet001"]
        mock_bridge.get_object.assert_called_once_with("Box", None)

    @pytest.mark.asyncio
    async def test_inspect_object_without_properties(self, register_tools, mock_bridge):
        """inspect_object should exclude properties when not requested."""
        mock_object = ObjectInfo(
            name="Box",
            label="My Box",
            type_id="Part::Box",
            properties={"Length": 10.0},
            shape_info=None,
            visibility=True,
            children=[],
            parents=[],
        )
        mock_bridge.get_object = AsyncMock(return_value=mock_object)

        inspect_object = register_tools["inspect_object"]
        result = await inspect_object(
            object_name="Box", include_properties=False, include_shape=False
        )

        assert result["name"] == "Box"
        assert "properties" not in result
        assert "shape_info" not in result

    @pytest.mark.asyncio
    async def test_edit_object(self, register_tools, mock_bridge):
        """edit_object should update object properties."""
        mock_object = ObjectInfo(
            name="Box",
            label="Box",
            type_id="Part::Box",
            properties={"Length": 20.0, "Width": 10.0},
            visibility=True,
            children=[],
            parents=[],
        )
        mock_bridge.edit_object = AsyncMock(return_value=mock_object)

        edit_object = register_tools["edit_object"]
        result = await edit_object(object_name="Box", properties={"Length": 20.0})

        assert result["name"] == "Box"
        mock_bridge.edit_object.assert_called_once_with("Box", {"Length": 20.0}, None)

    # Tests for execute_python based tools

    # Tests for new Part primitives

    # Tests for Part shape operations

    # Tests for Part compound operations

    # Tests for Part wire/face operations

    # Tests for Part loft and sweep
