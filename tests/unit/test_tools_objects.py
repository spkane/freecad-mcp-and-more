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
    async def test_create_object(self, register_tools, mock_bridge):
        """create_object should create and return object info."""
        mock_object = ObjectInfo(
            name="Box",
            label="Box",
            type_id="Part::Box",
            visibility=True,
            children=[],
            parents=[],
        )
        mock_bridge.create_object = AsyncMock(return_value=mock_object)

        create_object = register_tools["create_object"]
        result = await create_object(type_id="Part::Box", name="Box")

        assert result["name"] == "Box"
        assert result["type_id"] == "Part::Box"
        mock_bridge.create_object.assert_called_once()

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

    @pytest.mark.asyncio
    async def test_delete_object(self, register_tools, mock_bridge):
        """delete_object should delete and return success."""
        mock_bridge.delete_object = AsyncMock(return_value=True)

        delete_object = register_tools["delete_object"]
        result = await delete_object(object_name="Box")

        assert result["success"] is True
        mock_bridge.delete_object.assert_called_once_with("Box", None)

    @pytest.mark.asyncio
    async def test_create_box(self, register_tools, mock_bridge):
        """create_box should create a box primitive via create_object."""
        mock_object = ObjectInfo(
            name="Box",
            label="Box",
            type_id="Part::Box",
            visibility=True,
            children=[],
            parents=[],
        )
        mock_bridge.create_object = AsyncMock(return_value=mock_object)

        create_box = register_tools["create_box"]
        result = await create_box(length=20.0, width=10.0, height=5.0)

        assert result["name"] == "Box"
        assert result["volume"] == 20.0 * 10.0 * 5.0
        mock_bridge.create_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_cylinder(self, register_tools, mock_bridge):
        """create_cylinder should create a cylinder primitive via create_object."""
        mock_object = ObjectInfo(
            name="Cylinder",
            label="Cylinder",
            type_id="Part::Cylinder",
            visibility=True,
            children=[],
            parents=[],
        )
        mock_bridge.create_object = AsyncMock(return_value=mock_object)

        create_cylinder = register_tools["create_cylinder"]
        result = await create_cylinder(radius=5.0, height=20.0)

        assert result["name"] == "Cylinder"
        mock_bridge.create_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_sphere(self, register_tools, mock_bridge):
        """create_sphere should create a sphere primitive via create_object."""
        mock_object = ObjectInfo(
            name="Sphere",
            label="Sphere",
            type_id="Part::Sphere",
            visibility=True,
            children=[],
            parents=[],
        )
        mock_bridge.create_object = AsyncMock(return_value=mock_object)

        create_sphere = register_tools["create_sphere"]
        result = await create_sphere(radius=10.0)

        assert result["name"] == "Sphere"
        mock_bridge.create_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_cone(self, register_tools, mock_bridge):
        """create_cone should create a cone primitive via create_object."""
        mock_object = ObjectInfo(
            name="Cone",
            label="Cone",
            type_id="Part::Cone",
            visibility=True,
            children=[],
            parents=[],
        )
        mock_bridge.create_object = AsyncMock(return_value=mock_object)

        create_cone = register_tools["create_cone"]
        result = await create_cone(radius1=10.0, radius2=0.0, height=20.0)

        assert result["name"] == "Cone"
        mock_bridge.create_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_torus(self, register_tools, mock_bridge):
        """create_torus should create a torus primitive via create_object."""
        mock_object = ObjectInfo(
            name="Torus",
            label="Torus",
            type_id="Part::Torus",
            visibility=True,
            children=[],
            parents=[],
        )
        mock_bridge.create_object = AsyncMock(return_value=mock_object)

        create_torus = register_tools["create_torus"]
        result = await create_torus(radius1=20.0, radius2=5.0)

        assert result["name"] == "Torus"
        mock_bridge.create_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_wedge(self, register_tools, mock_bridge):
        """create_wedge should create a wedge primitive via create_object."""
        mock_object = ObjectInfo(
            name="Wedge",
            label="Wedge",
            type_id="Part::Wedge",
            visibility=True,
            children=[],
            parents=[],
        )
        mock_bridge.create_object = AsyncMock(return_value=mock_object)

        create_wedge = register_tools["create_wedge"]
        result = await create_wedge()

        assert result["name"] == "Wedge"
        mock_bridge.create_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_helix(self, register_tools, mock_bridge):
        """create_helix should create a helix primitive via create_object."""
        mock_object = ObjectInfo(
            name="Helix",
            label="Helix",
            type_id="Part::Helix",
            visibility=True,
            children=[],
            parents=[],
        )
        mock_bridge.create_object = AsyncMock(return_value=mock_object)

        create_helix = register_tools["create_helix"]
        result = await create_helix(pitch=5.0, height=20.0)

        assert result["name"] == "Helix"
        mock_bridge.create_object.assert_called_once()

    # Tests for execute_python based tools

    @pytest.mark.asyncio
    async def test_boolean_operation_fuse(self, register_tools, mock_bridge):
        """boolean_operation should perform union operation via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Fusion",
                    "label": "Fusion",
                    "type_id": "Part::MultiFuse",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        boolean_operation = register_tools["boolean_operation"]
        result = await boolean_operation(
            operation="fuse", object1_name="Box", object2_name="Cylinder"
        )

        assert result["name"] == "Fusion"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_placement(self, register_tools, mock_bridge):
        """set_placement should set position and rotation via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"position": [10.0, 20.0, 30.0], "rotation": [0.0, 0.0, 45.0]},
                stdout="",
                stderr="",
                execution_time_ms=5.0,
            )
        )

        set_placement = register_tools["set_placement"]
        result = await set_placement(object_name="Box", position=[10.0, 20.0, 30.0])

        assert result["position"] == [10.0, 20.0, 30.0]
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_scale_object(self, register_tools, mock_bridge):
        """scale_object should scale an object via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "ScaledBox",
                    "label": "ScaledBox",
                    "type_id": "Part::Feature",
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        scale_object = register_tools["scale_object"]
        result = await scale_object(object_name="Box", scale=2.0)

        assert result["name"] == "ScaledBox"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_rotate_object(self, register_tools, mock_bridge):
        """rotate_object should rotate an object via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 45.0]},
                stdout="",
                stderr="",
                execution_time_ms=5.0,
            )
        )

        rotate_object = register_tools["rotate_object"]
        result = await rotate_object(
            object_name="Box", axis=[0.0, 0.0, 1.0], angle=45.0
        )

        assert result["rotation"] == [0.0, 0.0, 45.0]
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_copy_object(self, register_tools, mock_bridge):
        """copy_object should create a copy via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"name": "Box001", "label": "Box001", "type_id": "Part::Box"},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        copy_object = register_tools["copy_object"]
        result = await copy_object(object_name="Box")

        assert result["name"] == "Box001"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_mirror_object(self, register_tools, mock_bridge):
        """mirror_object should mirror across a plane via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "MirroredBox",
                    "label": "MirroredBox",
                    "type_id": "Part::Feature",
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        mirror_object = register_tools["mirror_object"]
        result = await mirror_object(object_name="Box", plane="XY")

        assert result["name"] == "MirroredBox"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_selection(self, register_tools, mock_bridge):
        """get_selection should return selected objects via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result=[
                    {
                        "name": "Box",
                        "label": "Box",
                        "type_id": "Part::Box",
                        "sub_elements": ["Face1"],
                    }
                ],
                stdout="",
                stderr="",
                execution_time_ms=5.0,
            )
        )

        get_selection = register_tools["get_selection"]
        result = await get_selection()

        assert len(result) == 1
        assert result[0]["name"] == "Box"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_selection(self, register_tools, mock_bridge):
        """set_selection should select objects via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"success": True, "selected_count": 2},
                stdout="",
                stderr="",
                execution_time_ms=5.0,
            )
        )

        set_selection = register_tools["set_selection"]
        result = await set_selection(object_names=["Box", "Cylinder"])

        assert result["success"] is True
        assert result["selected_count"] == 2
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_selection(self, register_tools, mock_bridge):
        """clear_selection should clear selections via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"success": True},
                stdout="",
                stderr="",
                execution_time_ms=5.0,
            )
        )

        clear_selection = register_tools["clear_selection"]
        result = await clear_selection()

        assert result["success"] is True
        mock_bridge.execute_python.assert_called_once()

    # Tests for new Part primitives

    @pytest.mark.asyncio
    async def test_create_line(self, register_tools, mock_bridge):
        """create_line should create a line between two points."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"name": "Line", "label": "Line", "type_id": "Part::Feature"},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        create_line = register_tools["create_line"]
        result = await create_line(point1=[0.0, 0.0, 0.0], point2=[10.0, 10.0, 10.0])

        assert result["name"] == "Line"
        assert result["type_id"] == "Part::Feature"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_plane(self, register_tools, mock_bridge):
        """create_plane should create a planar surface via create_object."""
        mock_object = ObjectInfo(
            name="Plane",
            label="Plane",
            type_id="Part::Plane",
            visibility=True,
            children=[],
            parents=[],
        )
        mock_bridge.create_object = AsyncMock(return_value=mock_object)

        create_plane = register_tools["create_plane"]
        result = await create_plane(length=20.0, width=15.0)

        assert result["name"] == "Plane"
        assert result["type_id"] == "Part::Plane"
        mock_bridge.create_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_ellipse(self, register_tools, mock_bridge):
        """create_ellipse should create an ellipse curve via create_object."""
        mock_object = ObjectInfo(
            name="Ellipse",
            label="Ellipse",
            type_id="Part::Ellipse",
            visibility=True,
            children=[],
            parents=[],
        )
        mock_bridge.create_object = AsyncMock(return_value=mock_object)

        create_ellipse = register_tools["create_ellipse"]
        result = await create_ellipse(major_radius=10.0, minor_radius=5.0)

        assert result["name"] == "Ellipse"
        assert result["type_id"] == "Part::Ellipse"
        mock_bridge.create_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_prism(self, register_tools, mock_bridge):
        """create_prism should create a prism via create_object."""
        mock_object = ObjectInfo(
            name="Prism",
            label="Prism",
            type_id="Part::Prism",
            visibility=True,
            children=[],
            parents=[],
        )
        mock_bridge.create_object = AsyncMock(return_value=mock_object)

        create_prism = register_tools["create_prism"]
        result = await create_prism(polygon_sides=6, circumradius=10.0, height=20.0)

        assert result["name"] == "Prism"
        assert result["type_id"] == "Part::Prism"
        mock_bridge.create_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_regular_polygon(self, register_tools, mock_bridge):
        """create_regular_polygon should create a flat polygon via create_object."""
        mock_object = ObjectInfo(
            name="RegularPolygon",
            label="RegularPolygon",
            type_id="Part::RegularPolygon",
            visibility=True,
            children=[],
            parents=[],
        )
        mock_bridge.create_object = AsyncMock(return_value=mock_object)

        create_regular_polygon = register_tools["create_regular_polygon"]
        result = await create_regular_polygon(polygon_sides=8, circumradius=15.0)

        assert result["name"] == "RegularPolygon"
        assert result["type_id"] == "Part::RegularPolygon"
        mock_bridge.create_object.assert_called_once()

    # Tests for Part shape operations

    @pytest.mark.asyncio
    async def test_shell_object(self, register_tools, mock_bridge):
        """shell_object should create a hollow shell from a solid."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Shell",
                    "label": "Shell",
                    "type_id": "Part::Feature",
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        shell_object = register_tools["shell_object"]
        result = await shell_object(
            object_name="Box", thickness=2.0, faces_to_remove=["Face1"]
        )

        assert result["name"] == "Shell"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_offset_3d(self, register_tools, mock_bridge):
        """offset_3d should create an offset copy of a shape."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Offset",
                    "label": "Offset",
                    "type_id": "Part::Feature",
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        offset_3d = register_tools["offset_3d"]
        result = await offset_3d(object_name="Box", offset=2.0)

        assert result["name"] == "Offset"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_slice_shape(self, register_tools, mock_bridge):
        """slice_shape should slice a shape with a plane."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Slice",
                    "label": "Slice",
                    "type_id": "Part::Feature",
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        slice_shape = register_tools["slice_shape"]
        result = await slice_shape(
            object_name="Box",
            plane_point=[0.0, 0.0, 5.0],
            plane_normal=[0.0, 0.0, 1.0],
        )

        assert result["name"] == "Slice"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_section_shape(self, register_tools, mock_bridge):
        """section_shape should create a section of a shape."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Section",
                    "label": "Section",
                    "type_id": "Part::Feature",
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        section_shape = register_tools["section_shape"]
        result = await section_shape(object_name="Box", plane="XY", offset=5.0)

        assert result["name"] == "Section"
        mock_bridge.execute_python.assert_called_once()

    # Tests for Part compound operations

    @pytest.mark.asyncio
    async def test_make_compound(self, register_tools, mock_bridge):
        """make_compound should combine objects into a compound."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Compound",
                    "label": "Compound",
                    "type_id": "Part::Compound",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        make_compound = register_tools["make_compound"]
        result = await make_compound(object_names=["Box", "Cylinder"])

        assert result["name"] == "Compound"
        assert result["type_id"] == "Part::Compound"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_explode_compound(self, register_tools, mock_bridge):
        """explode_compound should separate a compound into parts."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "success": True,
                    "parts": ["Part001", "Part002", "Part003"],
                    "count": 3,
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        explode_compound = register_tools["explode_compound"]
        result = await explode_compound(object_name="Compound")

        assert result["success"] is True
        assert len(result["parts"]) == 3
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_fuse_all(self, register_tools, mock_bridge):
        """fuse_all should fuse multiple objects into one."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Fusion",
                    "label": "Fusion",
                    "type_id": "Part::MultiFuse",
                },
                stdout="",
                stderr="",
                execution_time_ms=20.0,
            )
        )

        fuse_all = register_tools["fuse_all"]
        result = await fuse_all(object_names=["Box", "Cylinder", "Sphere"])

        assert result["name"] == "Fusion"
        assert result["type_id"] == "Part::MultiFuse"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_common_all(self, register_tools, mock_bridge):
        """common_all should find intersection of multiple objects."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Common",
                    "label": "Common",
                    "type_id": "Part::MultiCommon",
                },
                stdout="",
                stderr="",
                execution_time_ms=20.0,
            )
        )

        common_all = register_tools["common_all"]
        result = await common_all(object_names=["Box", "Cylinder"])

        assert result["name"] == "Common"
        assert result["type_id"] == "Part::MultiCommon"
        mock_bridge.execute_python.assert_called_once()

    # Tests for Part wire/face operations

    @pytest.mark.asyncio
    async def test_make_wire(self, register_tools, mock_bridge):
        """make_wire should create a wire from points."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Wire",
                    "label": "Wire",
                    "type_id": "Part::Feature",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        make_wire = register_tools["make_wire"]
        result = await make_wire(
            points=[[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]],
            closed=True,
        )

        assert result["name"] == "Wire"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_make_face(self, register_tools, mock_bridge):
        """make_face should create a face from a wire."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Face",
                    "label": "Face",
                    "type_id": "Part::Feature",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        make_face = register_tools["make_face"]
        result = await make_face(object_name="Wire")

        assert result["name"] == "Face"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_extrude_shape(self, register_tools, mock_bridge):
        """extrude_shape should extrude a 2D shape along a direction."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Extrusion",
                    "label": "Extrusion",
                    "type_id": "Part::Feature",
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        extrude_shape = register_tools["extrude_shape"]
        result = await extrude_shape(object_name="Face", direction=[0, 0, 20])

        assert result["name"] == "Extrusion"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_revolve_shape(self, register_tools, mock_bridge):
        """revolve_shape should revolve a shape around an axis."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Revolution",
                    "label": "Revolution",
                    "type_id": "Part::Feature",
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        revolve_shape = register_tools["revolve_shape"]
        result = await revolve_shape(
            object_name="Face",
            axis_point=[0, 0, 0],
            axis_direction=[0, 0, 1],
            angle=360.0,
        )

        assert result["name"] == "Revolution"
        mock_bridge.execute_python.assert_called_once()

    # Tests for Part loft and sweep

    @pytest.mark.asyncio
    async def test_part_loft(self, register_tools, mock_bridge):
        """part_loft should create a loft through profiles."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Loft",
                    "label": "Loft",
                    "type_id": "Part::Loft",
                },
                stdout="",
                stderr="",
                execution_time_ms=20.0,
            )
        )

        part_loft = register_tools["part_loft"]
        result = await part_loft(
            profile_names=["Circle1", "Circle2", "Circle3"],
            solid=True,
        )

        assert result["name"] == "Loft"
        assert result["type_id"] == "Part::Loft"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_part_sweep(self, register_tools, mock_bridge):
        """part_sweep should sweep a profile along a spine."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Sweep",
                    "label": "Sweep",
                    "type_id": "Part::Sweep",
                },
                stdout="",
                stderr="",
                execution_time_ms=20.0,
            )
        )

        part_sweep = register_tools["part_sweep"]
        result = await part_sweep(
            profile_name="Circle",
            spine_name="Helix",
            solid=True,
        )

        assert result["name"] == "Sweep"
        assert result["type_id"] == "Part::Sweep"
        mock_bridge.execute_python.assert_called_once()
