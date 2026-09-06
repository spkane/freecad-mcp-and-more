"""Tests for PartDesign tools module."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from freecad_mcp.bridge.base import ExecutionResult, ObjectInfo


class TestPartDesignTools:
    """Tests for PartDesign tools."""

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
        """Register PartDesign tools and return the registered functions."""
        from freecad_mcp.tools.partdesign import register_partdesign_tools

        async def get_bridge():
            return mock_bridge

        register_partdesign_tools(mock_mcp, get_bridge)
        return mock_mcp._registered_tools

    @pytest.mark.asyncio
    async def test_create_partdesign_body(self, register_tools, mock_bridge):
        """create_partdesign_body should create a body container via create_object."""
        mock_object = ObjectInfo(
            name="Body",
            label="Body",
            type_id="PartDesign::Body",
            visibility=True,
            children=[],
            parents=[],
        )
        mock_bridge.create_object = AsyncMock(return_value=mock_object)

        create_body = register_tools["create_partdesign_body"]
        result = await create_body(name="Body")

        assert result["name"] == "Body"
        assert result["type_id"] == "PartDesign::Body"
        mock_bridge.create_object.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_sketch(self, register_tools, mock_bridge):
        """create_sketch should create a sketch via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Sketch",
                    "label": "Sketch",
                    "type_id": "Sketcher::SketchObject",
                    "support": "XY_Plane",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        create_sketch = register_tools["create_sketch"]
        result = await create_sketch(body_name="Body", plane="XY_Plane")

        assert result["name"] == "Sketch"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_sketch_rectangle(self, register_tools, mock_bridge):
        """add_sketch_rectangle should add a rectangle via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"constraint_count": 8, "geometry_count": 4},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        add_rectangle = register_tools["add_sketch_rectangle"]
        result = await add_rectangle(
            sketch_name="Sketch", x=-10, y=-10, width=20, height=20
        )

        assert result["constraint_count"] == 8
        assert result["geometry_count"] == 4
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_sketch_circle(self, register_tools, mock_bridge):
        """add_sketch_circle should add a circle via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"geometry_index": 0, "geometry_count": 1},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        add_circle = register_tools["add_sketch_circle"]
        result = await add_circle(
            sketch_name="Sketch", center_x=0, center_y=0, radius=10
        )

        assert result["geometry_index"] == 0
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_sketch_line(self, register_tools, mock_bridge):
        """add_sketch_line should add a line via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"geometry_index": 0, "geometry_count": 1},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        add_line = register_tools["add_sketch_line"]
        result = await add_line(sketch_name="Sketch", x1=0, y1=0, x2=10, y2=10)

        assert result["geometry_index"] == 0
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_sketch_arc(self, register_tools, mock_bridge):
        """add_sketch_arc should add an arc via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"geometry_index": 0, "geometry_count": 1},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        add_arc = register_tools["add_sketch_arc"]
        result = await add_arc(
            sketch_name="Sketch",
            center_x=0,
            center_y=0,
            radius=10,
            start_angle=0,
            end_angle=90,
        )

        assert result["geometry_index"] == 0
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_sketch_point(self, register_tools, mock_bridge):
        """add_sketch_point should add a point via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"geometry_index": 0, "geometry_count": 1},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        add_point = register_tools["add_sketch_point"]
        result = await add_point(sketch_name="Sketch", x=5, y=5)

        assert result["geometry_index"] == 0
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_pad_sketch(self, register_tools, mock_bridge):
        """pad_sketch should extrude a sketch via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"name": "Pad", "label": "Pad", "type_id": "PartDesign::Pad"},
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        pad_sketch = register_tools["pad_sketch"]
        result = await pad_sketch(sketch_name="Sketch", length=10)

        assert result["name"] == "Pad"
        assert result["type_id"] == "PartDesign::Pad"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_pocket_sketch(self, register_tools, mock_bridge):
        """pocket_sketch should cut into solid via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Pocket",
                    "label": "Pocket",
                    "type_id": "PartDesign::Pocket",
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        pocket_sketch = register_tools["pocket_sketch"]
        result = await pocket_sketch(sketch_name="Sketch", length=5)

        assert result["name"] == "Pocket"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_revolution_sketch(self, register_tools, mock_bridge):
        """revolution_sketch should revolve a sketch via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Revolution",
                    "label": "Revolution",
                    "type_id": "PartDesign::Revolution",
                },
                stdout="",
                stderr="",
                execution_time_ms=20.0,
            )
        )

        revolution = register_tools["revolution_sketch"]
        result = await revolution(sketch_name="Sketch", angle=360)

        assert result["name"] == "Revolution"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_groove_sketch(self, register_tools, mock_bridge):
        """groove_sketch should cut by revolving via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Groove",
                    "label": "Groove",
                    "type_id": "PartDesign::Groove",
                },
                stdout="",
                stderr="",
                execution_time_ms=20.0,
            )
        )

        groove = register_tools["groove_sketch"]
        result = await groove(sketch_name="Sketch", angle=180)

        assert result["name"] == "Groove"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_fillet_edges(self, register_tools, mock_bridge):
        """fillet_edges should add rounded edges via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Fillet",
                    "label": "Fillet",
                    "type_id": "PartDesign::Fillet",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        fillet = register_tools["fillet_edges"]
        result = await fillet(object_name="Pad", radius=2.0)

        assert result["name"] == "Fillet"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_chamfer_edges(self, register_tools, mock_bridge):
        """chamfer_edges should add beveled edges via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Chamfer",
                    "label": "Chamfer",
                    "type_id": "PartDesign::Chamfer",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        chamfer = register_tools["chamfer_edges"]
        result = await chamfer(object_name="Pad", size=1.0)

        assert result["name"] == "Chamfer"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_hole(self, register_tools, mock_bridge):
        """create_hole should create parametric holes via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"name": "Hole", "label": "Hole", "type_id": "PartDesign::Hole"},
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        create_hole = register_tools["create_hole"]
        result = await create_hole(sketch_name="HoleSketch", diameter=6.0, depth=10.0)

        assert result["name"] == "Hole"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_linear_pattern(self, register_tools, mock_bridge):
        """linear_pattern should create linear pattern via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "LinearPattern",
                    "label": "LinearPattern",
                    "type_id": "PartDesign::LinearPattern",
                },
                stdout="",
                stderr="",
                execution_time_ms=20.0,
            )
        )

        pattern = register_tools["linear_pattern"]
        result = await pattern(
            feature_name="Pad", direction="X", length=50, occurrences=5
        )

        assert result["name"] == "LinearPattern"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_polar_pattern(self, register_tools, mock_bridge):
        """polar_pattern should create circular pattern via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "PolarPattern",
                    "label": "PolarPattern",
                    "type_id": "PartDesign::PolarPattern",
                },
                stdout="",
                stderr="",
                execution_time_ms=20.0,
            )
        )

        pattern = register_tools["polar_pattern"]
        result = await pattern(feature_name="Pad", axis="Z", angle=360, occurrences=6)

        assert result["name"] == "PolarPattern"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_mirrored_feature(self, register_tools, mock_bridge):
        """mirrored_feature should mirror a feature via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Mirrored",
                    "label": "Mirrored",
                    "type_id": "PartDesign::Mirrored",
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        mirrored = register_tools["mirrored_feature"]
        result = await mirrored(feature_name="Pad", plane="XY")

        assert result["name"] == "Mirrored"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_loft_sketches(self, register_tools, mock_bridge):
        """loft_sketches should create a loft via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Loft",
                    "label": "Loft",
                    "type_id": "PartDesign::AdditiveLoft",
                },
                stdout="",
                stderr="",
                execution_time_ms=25.0,
            )
        )

        loft = register_tools["loft_sketches"]
        result = await loft(sketch_names=["Sketch", "Sketch001"])

        assert result["name"] == "Loft"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_sweep_sketch(self, register_tools, mock_bridge):
        """sweep_sketch should sweep a profile via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Sweep",
                    "label": "Sweep",
                    "type_id": "PartDesign::AdditivePipe",
                },
                stdout="",
                stderr="",
                execution_time_ms=25.0,
            )
        )

        sweep = register_tools["sweep_sketch"]
        result = await sweep(profile_sketch="Profile", spine_sketch="Spine")

        assert result["name"] == "Sweep"
        mock_bridge.execute_python.assert_called_once()

    # Tests for PartDesign datum features

    @pytest.mark.asyncio
    async def test_create_datum_plane(self, register_tools, mock_bridge):
        """create_datum_plane should create a reference plane."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "DatumPlane",
                    "label": "DatumPlane",
                    "type_id": "PartDesign::Plane",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        create_datum_plane = register_tools["create_datum_plane"]
        result = await create_datum_plane(
            body_name="Body", offset=10.0, base_plane="XY_Plane"
        )

        assert result["name"] == "DatumPlane"
        assert result["type_id"] == "PartDesign::Plane"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_datum_line(self, register_tools, mock_bridge):
        """create_datum_line should create a reference line."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "DatumLine",
                    "label": "DatumLine",
                    "type_id": "PartDesign::Line",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        create_datum_line = register_tools["create_datum_line"]
        result = await create_datum_line(body_name="Body", base_axis="X_Axis")

        assert result["name"] == "DatumLine"
        assert result["type_id"] == "PartDesign::Line"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_datum_point(self, register_tools, mock_bridge):
        """create_datum_point should create a reference point."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "DatumPoint",
                    "label": "DatumPoint",
                    "type_id": "PartDesign::Point",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        create_datum_point = register_tools["create_datum_point"]
        result = await create_datum_point(body_name="Body", position=[10.0, 20.0, 30.0])

        assert result["name"] == "DatumPoint"
        assert result["type_id"] == "PartDesign::Point"
        mock_bridge.execute_python.assert_called_once()

    # Tests for PartDesign dress-up features

    @pytest.mark.asyncio
    async def test_draft_feature(self, register_tools, mock_bridge):
        """draft_feature should add draft angle to faces."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Draft",
                    "label": "Draft",
                    "type_id": "PartDesign::Draft",
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        draft_feature = register_tools["draft_feature"]
        result = await draft_feature(
            object_name="Pad", angle=5.0, plane="XY", faces=["Face1", "Face2"]
        )

        assert result["name"] == "Draft"
        assert result["type_id"] == "PartDesign::Draft"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_thickness_feature(self, register_tools, mock_bridge):
        """thickness_feature should shell a solid."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Thickness",
                    "label": "Thickness",
                    "type_id": "PartDesign::Thickness",
                },
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        thickness_feature = register_tools["thickness_feature"]
        result = await thickness_feature(
            object_name="Pad", thickness=2.0, faces_to_remove=["Face1"]
        )

        assert result["name"] == "Thickness"
        assert result["type_id"] == "PartDesign::Thickness"
        mock_bridge.execute_python.assert_called_once()

    # Tests for PartDesign subtractive features

    @pytest.mark.asyncio
    async def test_subtractive_loft(self, register_tools, mock_bridge):
        """subtractive_loft should cut material with a loft."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "SubtractiveLoft",
                    "label": "SubtractiveLoft",
                    "type_id": "PartDesign::SubtractiveLoft",
                },
                stdout="",
                stderr="",
                execution_time_ms=25.0,
            )
        )

        subtractive_loft = register_tools["subtractive_loft"]
        result = await subtractive_loft(sketch_names=["Sketch", "Sketch001"])

        assert result["name"] == "SubtractiveLoft"
        assert result["type_id"] == "PartDesign::SubtractiveLoft"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_subtractive_pipe(self, register_tools, mock_bridge):
        """subtractive_pipe should cut material by sweeping."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "SubtractivePipe",
                    "label": "SubtractivePipe",
                    "type_id": "PartDesign::SubtractivePipe",
                },
                stdout="",
                stderr="",
                execution_time_ms=25.0,
            )
        )

        subtractive_pipe = register_tools["subtractive_pipe"]
        result = await subtractive_pipe(profile_sketch="Profile", spine_sketch="Spine")

        assert result["name"] == "SubtractivePipe"
        assert result["type_id"] == "PartDesign::SubtractivePipe"
        mock_bridge.execute_python.assert_called_once()

    # Tests for Sketcher geometry tools

    @pytest.mark.asyncio
    async def test_add_sketch_ellipse(self, register_tools, mock_bridge):
        """add_sketch_ellipse should add an ellipse to a sketch."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"geometry_index": 0, "geometry_count": 1},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        add_ellipse = register_tools["add_sketch_ellipse"]
        result = await add_ellipse(
            sketch_name="Sketch",
            center_x=0,
            center_y=0,
            major_radius=20,
            minor_radius=10,
        )

        assert result["geometry_index"] == 0
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_sketch_polygon(self, register_tools, mock_bridge):
        """add_sketch_polygon should add a regular polygon to a sketch."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"geometry_count": 6, "constraint_count": 12},
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        add_polygon = register_tools["add_sketch_polygon"]
        result = await add_polygon(
            sketch_name="Sketch", center_x=0, center_y=0, radius=10, sides=6
        )

        assert result["geometry_count"] == 6
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_sketch_slot(self, register_tools, mock_bridge):
        """add_sketch_slot should add a slot to a sketch."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"geometry_count": 4, "constraint_count": 8},
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        add_slot = register_tools["add_sketch_slot"]
        result = await add_slot(
            sketch_name="Sketch",
            center1_x=-10,
            center1_y=0,
            center2_x=10,
            center2_y=0,
            radius=5,
        )

        assert result["geometry_count"] == 4
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_sketch_bspline(self, register_tools, mock_bridge):
        """add_sketch_bspline should add a B-spline to a sketch."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"geometry_index": 0, "geometry_count": 1},
                stdout="",
                stderr="",
                execution_time_ms=15.0,
            )
        )

        add_bspline = register_tools["add_sketch_bspline"]
        result = await add_bspline(
            sketch_name="Sketch",
            points=[[0, 0], [10, 5], [20, 0], [30, -5]],
            closed=False,
        )

        assert result["geometry_index"] == 0
        mock_bridge.execute_python.assert_called_once()

    # Tests for Sketcher constraint tools

    @pytest.mark.asyncio
    async def test_add_sketch_constraint(self, register_tools, mock_bridge):
        """add_sketch_constraint should add a constraint to a sketch."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"constraint_index": 0, "constraint_count": 1},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        add_constraint = register_tools["add_sketch_constraint"]
        result = await add_constraint(
            sketch_name="Sketch",
            constraint_type="Horizontal",
            geometry1=0,
        )

        assert result["constraint_index"] == 0
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_constrain_horizontal(self, register_tools, mock_bridge):
        """constrain_horizontal should add a horizontal constraint."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"constraint_index": 0, "constraint_count": 1},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        constrain = register_tools["constrain_horizontal"]
        result = await constrain(sketch_name="Sketch", geometry_index=0)

        assert result["constraint_index"] == 0
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_constrain_vertical(self, register_tools, mock_bridge):
        """constrain_vertical should add a vertical constraint."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"constraint_index": 0, "constraint_count": 1},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        constrain = register_tools["constrain_vertical"]
        result = await constrain(sketch_name="Sketch", geometry_index=0)

        assert result["constraint_index"] == 0
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_constrain_coincident(self, register_tools, mock_bridge):
        """constrain_coincident should make two points coincident."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"constraint_index": 0, "constraint_count": 1},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        constrain = register_tools["constrain_coincident"]
        result = await constrain(
            sketch_name="Sketch", geometry1=0, point1=1, geometry2=1, point2=2
        )

        assert result["constraint_index"] == 0
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_constrain_parallel(self, register_tools, mock_bridge):
        """constrain_parallel should make two lines parallel."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"constraint_index": 0, "constraint_count": 1},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        constrain = register_tools["constrain_parallel"]
        result = await constrain(sketch_name="Sketch", geometry1=0, geometry2=1)

        assert result["constraint_index"] == 0
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_constrain_perpendicular(self, register_tools, mock_bridge):
        """constrain_perpendicular should make two lines perpendicular."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"constraint_index": 0, "constraint_count": 1},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        constrain = register_tools["constrain_perpendicular"]
        result = await constrain(sketch_name="Sketch", geometry1=0, geometry2=1)

        assert result["constraint_index"] == 0
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_constrain_tangent(self, register_tools, mock_bridge):
        """constrain_tangent should make two curves tangent."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"constraint_index": 0, "constraint_count": 1},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        constrain = register_tools["constrain_tangent"]
        result = await constrain(sketch_name="Sketch", geometry1=0, geometry2=1)

        assert result["constraint_index"] == 0
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_constrain_equal(self, register_tools, mock_bridge):
        """constrain_equal should make two elements equal."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"constraint_index": 0, "constraint_count": 1},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        constrain = register_tools["constrain_equal"]
        result = await constrain(sketch_name="Sketch", geometry1=0, geometry2=1)

        assert result["constraint_index"] == 0
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_constrain_distance(self, register_tools, mock_bridge):
        """constrain_distance should set distance between elements."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"constraint_index": 0, "constraint_count": 1},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        constrain = register_tools["constrain_distance"]
        result = await constrain(sketch_name="Sketch", geometry1=0, distance=25.0)

        assert result["constraint_index"] == 0
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_constrain_distance_x(self, register_tools, mock_bridge):
        """constrain_distance_x should set horizontal distance."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"constraint_index": 0, "constraint_count": 1},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        constrain = register_tools["constrain_distance_x"]
        result = await constrain(
            sketch_name="Sketch", geometry=0, point=1, distance=15.0
        )

        assert result["constraint_index"] == 0
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_constrain_distance_y(self, register_tools, mock_bridge):
        """constrain_distance_y should set vertical distance."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"constraint_index": 0, "constraint_count": 1},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        constrain = register_tools["constrain_distance_y"]
        result = await constrain(
            sketch_name="Sketch", geometry=0, point=1, distance=20.0
        )

        assert result["constraint_index"] == 0
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_constrain_radius(self, register_tools, mock_bridge):
        """constrain_radius should set radius of a circle/arc."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"constraint_index": 0, "constraint_count": 1},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        constrain = register_tools["constrain_radius"]
        result = await constrain(sketch_name="Sketch", geometry_index=0, radius=12.5)

        assert result["constraint_index"] == 0
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_constrain_angle(self, register_tools, mock_bridge):
        """constrain_angle should set angle of a line."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"constraint_index": 0, "constraint_count": 1},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        constrain = register_tools["constrain_angle"]
        result = await constrain(sketch_name="Sketch", geometry1=0, angle=45.0)

        assert result["constraint_index"] == 0
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_constrain_fix(self, register_tools, mock_bridge):
        """constrain_fix should fix a point at its position."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"constraint_index": 0, "constraint_count": 1},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        constrain = register_tools["constrain_fix"]
        result = await constrain(sketch_name="Sketch", geometry_index=0, point_index=1)

        assert result["constraint_index"] == 0
        mock_bridge.execute_python.assert_called_once()

    # Tests for Sketcher operations

    @pytest.mark.asyncio
    async def test_add_external_geometry(self, register_tools, mock_bridge):
        """add_external_geometry should reference external edges."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"geometry_index": -3, "success": True},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        add_external = register_tools["add_external_geometry"]
        result = await add_external(
            sketch_name="Sketch", object_name="Box", element="Edge1"
        )

        assert result["success"] is True
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_sketch_geometry(self, register_tools, mock_bridge):
        """delete_sketch_geometry should delete geometry from sketch."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"success": True, "geometry_count": 3},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        delete_geometry = register_tools["delete_sketch_geometry"]
        result = await delete_geometry(sketch_name="Sketch", geometry_index=0)

        assert result["success"] is True
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_sketch_constraint(self, register_tools, mock_bridge):
        """delete_sketch_constraint should delete constraint from sketch."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"success": True, "constraint_count": 5},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        delete_constraint = register_tools["delete_sketch_constraint"]
        result = await delete_constraint(sketch_name="Sketch", constraint_index=0)

        assert result["success"] is True
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_sketch_info(self, register_tools, mock_bridge):
        """get_sketch_info should return sketch geometry and constraints."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Sketch",
                    "geometry_count": 4,
                    "constraint_count": 8,
                    "is_fully_constrained": True,
                    "degrees_of_freedom": 0,
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        get_info = register_tools["get_sketch_info"]
        result = await get_info(sketch_name="Sketch")

        assert result["geometry_count"] == 4
        assert result["constraint_count"] == 8
        assert result["is_fully_constrained"] is True
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_toggle_construction(self, register_tools, mock_bridge):
        """toggle_construction should toggle geometry mode."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"success": True, "is_construction": True},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        toggle = register_tools["toggle_construction"]
        result = await toggle(sketch_name="Sketch", geometry_index=0)

        assert result["success"] is True
        assert result["is_construction"] is True
        mock_bridge.execute_python.assert_called_once()


class TestExternalGeometryCount:
    """External geometry must be counted by subelement, not by linked object.

    `Sketch.ExternalGeometryCount` was removed in FreeCAD 1.1. Its replacement is
    not `len(sketch.ExternalGeometry)`: that property is an
    App::PropertyLinkSubList holding one entry per linked *object*, with the
    referenced subelements collapsed into a tuple. Three edges taken from one
    solid therefore give len() == 1, so the subelements have to be summed.
    """

    @pytest.fixture
    def mock_mcp(self):
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
        bridge = AsyncMock()
        bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"success": True, "external_geometry_count": 0},
                stdout="",
                stderr="",
                error_traceback=None,
                execution_time_ms=1.0,
            )
        )
        return bridge

    @pytest.fixture
    def register_tools(self, mock_mcp, mock_bridge):
        from freecad_mcp.tools.partdesign import register_partdesign_tools

        async def get_bridge():
            return mock_bridge

        register_partdesign_tools(mock_mcp, get_bridge)
        return mock_mcp._registered_tools

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("tool", "kwargs"),
        [
            ("get_sketch_info", {"sketch_name": "Sketch"}),
            (
                "add_external_geometry",
                {"sketch_name": "Sketch", "object_name": "Box", "element": "Edge1"},
            ),
        ],
    )
    async def test_counts_subelements_not_linked_objects(
        self, register_tools, mock_bridge, tool, kwargs
    ):
        await register_tools[tool](**kwargs)
        code = mock_bridge.execute_python.call_args[0][0]
        compile(code, "<generated>", "exec")

        assert "ExternalGeometryCount" not in code, "removed in FreeCAD 1.1"
        assert "sum(len(_s) for _, _s in sketch.ExternalGeometry)" in code

    def test_summing_matches_freecad_link_sub_list_shape(self):
        """Pin the semantics the generated expression relies on.

        Mirrors what FreeCAD 1.1.3 returns after three addExternal() calls
        against one object: a single entry whose subelements are a 3-tuple.
        """
        external_geometry = [(object(), ("Edge1", "Edge2", "Edge3"))]

        assert len(external_geometry) == 1  # the tempting but wrong answer
        assert sum(len(_s) for _, _s in external_geometry) == 3
