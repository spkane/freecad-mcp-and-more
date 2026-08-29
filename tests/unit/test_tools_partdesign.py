"""Tests for PartDesign tools module."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from freecad_mcp.bridge.base import ExecutionResult, ObjectInfo
from freecad_mcp.tools.partdesign import (
    SketchArc,
    SketchCircle,
    SketchConstraint,
    SketchLine,
    SketchPoint,
    SketchRectangle,
    SketchReference,
    SketchValidation,
)
from freecad_mcp.tools.workflow_results import ConstrainedSketchResult


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
    async def test_create_sketch_supports_named_datum_plane(
        self, register_tools, mock_bridge
    ):
        """create_sketch should resolve a named datum plane in the document."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "GallerySketch",
                    "label": "GallerySketch",
                    "type_id": "Sketcher::SketchObject",
                    "support": "GalleryDatum",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        create_sketch = register_tools["create_sketch"]
        await create_sketch(
            body_name="Body",
            plane="GalleryDatum",
            name="GallerySketch",
        )

        code = mock_bridge.execute_python.call_args.args[0]
        assert "support_obj = doc.getObject(plane)" in code
        assert "Unsupported sketch support" in code

    @pytest.mark.asyncio
    async def test_create_constrained_sketch_is_one_symbolic_transaction(
        self, register_tools, mock_bridge
    ):
        """A complete sketch should map symbolic IDs in one transaction."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "document_ref": {"name": "TestDoc", "revision": "rev_2"},
                    "name": "Profile",
                    "label": "Profile",
                    "type_id": "Sketcher::SketchObject",
                    "entity_indices": {
                        "base": 0,
                        "outer": 1,
                        "arch": 2,
                        "origin": 3,
                        "frame": [4, 5, 6, 7],
                    },
                    "constraint_indices": {"base_horizontal": 8},
                    "generated_constraint_indices": {},
                    "solved_geometry": {
                        "base": {
                            "kind": "line",
                            "indices": [0],
                            "geometry": [
                                {
                                    "index": 0,
                                    "type": "LineSegment",
                                    "start": [0.0, 0.0],
                                    "end": [20.0, 0.0],
                                }
                            ],
                            "bounds": {
                                "min_x": 0.0,
                                "min_y": 0.0,
                                "max_x": 20.0,
                                "max_y": 0.0,
                            },
                        }
                    },
                    "geometry_count": 8,
                    "constraint_count": 9,
                    "solver": {
                        "status": 0,
                        "fully_constrained": False,
                        "degrees_of_freedom": None,
                    },
                    "closed_profiles": 2,
                    "warnings": ["Sketch is not fully constrained"],
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        create_constrained_sketch = register_tools["create_constrained_sketch"]
        result = await create_constrained_sketch(
            body_name="Body",
            sketch_name="Profile",
            support="XY_Plane",
            entities=[
                SketchLine(id="base", start=(0, 0), end=(20, 0)),
                SketchCircle(id="outer", center=(0, 0), radius=10),
                SketchArc(
                    id="arch",
                    center=(0, 0),
                    radius=5,
                    start_angle=0,
                    end_angle=180,
                ),
                SketchPoint(id="origin", position=(0, 0)),
                SketchRectangle(id="frame", origin=(-10, -5), width=20, height=10),
            ],
            constraints=[
                SketchConstraint(
                    id="base_horizontal",
                    kind="horizontal",
                    first=SketchReference(entity="base"),
                )
            ],
            validation=SketchValidation(
                require_fully_constrained=False,
                require_closed_profiles=True,
            ),
            expected_revision="rev_1",
            doc_name="TestDoc",
        )

        assert result["entity_indices"]["base"] == 0
        assert result["solved_geometry"]["base"]["geometry"][0]["end"] == [
            20.0,
            0.0,
        ]
        code = mock_bridge.execute_python.call_args.args[0]
        assert (
            code.count('open_owned_transaction(doc, "Create Constrained Sketch")') == 1
        )
        assert 'kind == "line"' in code
        assert 'kind == "circle"' in code
        assert 'kind == "arc"' in code
        assert 'kind == "point"' in code
        assert 'kind == "rectangle"' in code
        assert "entity_lookup" in code
        assert "sketch.addConstraint(constraint)" in code
        assert "sketch.setExpression" in code
        assert "require_fully_constrained" in code
        assert "require_closed_profiles" in code
        assert "STALE_REVISION" in code
        assert "candidate.Content" in code
        assert 'hasattr(sketch, "DoF")' in code
        assert "getLastDoF()" in code
        assert "solver_status = int(sketch.solve())" in code
        assert "if reject_solver_errors and solver_status != 0:" in code
        assert "degrees_of_freedom = int(sketch.solve())" not in code
        assert "def describe_solved_geometry(geometry_index):" in code
        assert '"solved_geometry": solved_geometry' in code
        assert code.index('"solved_geometry": solved_geometry') < code.index(
            "doc.commitTransaction()"
        )
        assert "abort_owned_transaction(doc)" in code
        assert code.index('"solver": {') < code.index("doc.commitTransaction()")
        compile(code, "<create_constrained_sketch>", "exec")

    def test_sketch_constraint_schema_documents_signed_offsets(self):
        """The tool schema should explain FreeCAD's signed offset ordering."""
        description = " ".join(
            SketchConstraint.model_json_schema()["description"].split()
        )

        assert "end minus start" in description
        assert "second minus first" in description
        assert "signed coordinate from the sketch origin" in description

    def test_constrained_sketch_result_declares_solved_geometry(self):
        """The response contract should expose solver-adjusted geometry."""
        properties = ConstrainedSketchResult.model_json_schema()["properties"]

        assert "solved_geometry" in properties

    @pytest.mark.asyncio
    async def test_create_constrained_sketch_rejects_duplicate_symbolic_ids(
        self, register_tools, mock_bridge
    ):
        """Symbolic IDs must resolve to one deterministic native entity."""
        create_constrained_sketch = register_tools["create_constrained_sketch"]

        with pytest.raises(ValueError, match="Duplicate sketch entity IDs"):
            await create_constrained_sketch(
                body_name="Body",
                sketch_name="Profile",
                entities=[
                    SketchLine(id="edge", start=(0, 0), end=(10, 0)),
                    SketchLine(id="edge", start=(10, 0), end=(10, 10)),
                ],
            )

        mock_bridge.execute_python.assert_not_called()

    def test_sketch_constraint_requires_dimensional_value(self):
        """Dimensional constraints should have one literal or expression."""
        with pytest.raises(ValueError, match="exactly one of value or expression"):
            SketchConstraint(
                id="length",
                kind="distance",
                first=SketchReference(entity="edge"),
            )

    @pytest.mark.parametrize(
        "constraint",
        [
            SketchConstraint(
                id="horizontal",
                kind="horizontal",
                first=SketchReference(entity="edge"),
            ).model_dump()
            | {"first": {"entity": "edge", "point": "start"}},
            {
                "id": "coincident",
                "kind": "coincident",
                "first": {"entity": "a", "point": "whole"},
                "second": {"entity": "b", "point": "end"},
            },
            {
                "id": "angle",
                "kind": "angle",
                "first": {"entity": "a", "point": "start"},
                "second": {"entity": "b", "point": "whole"},
                "value": 45,
            },
        ],
    )
    def test_sketch_constraint_rejects_ignored_point_roles(self, constraint):
        """Typed constraints must not silently discard reference point roles."""
        with pytest.raises(ValueError, match="reference"):
            SketchConstraint.model_validate(constraint)

    def test_sketch_constraint_accepts_native_point_curve_overloads(self):
        """Perpendicular, tangent, and distance should retain point references."""
        tangent = SketchConstraint(
            id="tangent",
            kind="tangent",
            first=SketchReference(entity="arc", point="end"),
            second=SketchReference(entity="line"),
        )
        point_to_line = SketchConstraint(
            id="offset",
            kind="distance",
            first=SketchReference(entity="line", point="start"),
            second=SketchReference(entity="datum"),
            value=5,
        )

        assert tangent.first.point == "end"
        assert point_to_line.second is not None
        assert point_to_line.second.point == "whole"

    def test_sketch_constraint_rejects_single_point_distance(self):
        """Generic Distance has no native point-to-origin overload."""
        with pytest.raises(ValueError, match="whole geometry"):
            SketchConstraint(
                id="distance",
                kind="distance",
                first=SketchReference(entity="line", point="start"),
                value=5,
            )

    @pytest.mark.asyncio
    async def test_create_constrained_sketch_validates_entity_point_roles(
        self, register_tools, mock_bridge
    ):
        """A circle endpoint reference should fail before reaching FreeCAD."""
        create_constrained_sketch = register_tools["create_constrained_sketch"]

        with pytest.raises(ValueError, match="does not support point role start"):
            await create_constrained_sketch(
                body_name="Body",
                sketch_name="Profile",
                entities=[SketchCircle(id="circle", center=(0, 0), radius=10)],
                constraints=[
                    SketchConstraint(
                        id="distance",
                        kind="distance_x",
                        first=SketchReference(entity="circle", point="start"),
                        value=10,
                    )
                ],
            )

        mock_bridge.execute_python.assert_not_called()

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
        code = mock_bridge.execute_python.call_args.args[0]
        assert '"geometry_indices": list(range(n, n + 4))' in code
        assert '"constraint_indices": list(' in code

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
        code = mock_bridge.execute_python.call_args.args[0]
        assert "Feature validation failed" in code
        assert "len(body_shape.Solids) != 1" in code
        assert '"Touched" in feature_state' in code
        assert '"Touched" in body_state' in code
        assert '"document_ref"' in code
        assert '"next_inputs"' in code
        assert 'open_owned_transaction(doc, "Pad Sketch")' in code
        assert "abort_owned_transaction(doc)" in code
        assert code.index('"next_inputs"') < code.index("doc.commitTransaction()")
        assert code.count("doc.recompute()") == 2
        compile(code, "<pad_sketch>", "exec")

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
        code = mock_bridge.execute_python.call_args.args[0]
        assert "fillet.UseAllEdges = True" in code
        assert (
            "obj.Shape.Edges"
            not in code.split("# PartDesign Fillet", 1)[1].split("# Part Fillet", 1)[0]
        )
        assert "fillet.Base = obj" in code
        assert "fillet.Edges = edge_list" in code

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
        code = mock_bridge.execute_python.call_args.args[0]
        assert "chamfer.UseAllEdges = True" in code
        assert (
            "obj.Shape.Edges"
            not in code.split("# PartDesign Chamfer", 1)[1].split("# Part Chamfer", 1)[
                0
            ]
        )
        assert "chamfer.Base = obj" in code
        assert "chamfer.Edges = edge_list" in code

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
    @pytest.mark.parametrize(
        ("tool_name", "arguments"),
        [
            ("linear_pattern", {"feature_name": "Pad"}),
            ("polar_pattern", {"feature_name": "Pad"}),
        ],
    )
    async def test_patterns_promote_created_feature_to_body_tip(
        self,
        register_tools: dict[str, Any],
        mock_bridge: AsyncMock,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> None:
        """Native patterns should expose their result as the Body shape."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"name": "Pattern"},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        await register_tools[tool_name](**arguments)

        code = mock_bridge.execute_python.call_args.args[0]
        assert "body.Tip = pattern" in code
        assert code.index("body.Tip = pattern") < code.index("doc.recompute()")
        assert "Created feature is not the Body tip" in code
        compile(code, f"<{tool_name}>", "exec")

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
    @pytest.mark.parametrize(
        ("tool_name", "arguments"),
        [
            ("pad_sketch", {"sketch_name": "Sketch", "length": 10}),
            ("pocket_sketch", {"sketch_name": "Sketch", "length": 5}),
            ("fillet_edges", {"object_name": "Pad", "radius": 2}),
            ("chamfer_edges", {"object_name": "Pad", "size": 1}),
            ("revolution_sketch", {"sketch_name": "Sketch"}),
            ("groove_sketch", {"sketch_name": "Sketch"}),
            ("create_hole", {"sketch_name": "HoleSketch"}),
            ("linear_pattern", {"feature_name": "Pad"}),
            ("polar_pattern", {"feature_name": "Pad"}),
            ("mirrored_feature", {"feature_name": "Pad"}),
            ("loft_sketches", {"sketch_names": ["Sketch", "Sketch001"]}),
        ],
    )
    async def test_focused_feature_mutations_return_validated_result_contract(
        self, register_tools, mock_bridge, tool_name, arguments
    ):
        """Focused feature mutations should reject invalid local geometry."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"name": "Feature", "validation": {"valid": True}},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        await register_tools[tool_name](**arguments)

        code = mock_bridge.execute_python.call_args.args[0]
        assert "Feature validation failed" in code
        assert "PartDesign Body must contain exactly one solid" in code
        assert '"document_ref"' in code
        assert '"next_inputs"' in code
        assert "require_expected_revision(doc, expected_revision)" in code
        assert "open_owned_transaction(doc," in code
        assert "abort_owned_transaction(doc)" in code
        assert "candidate.Content" in code
        assert code.index('"next_inputs"') < code.index("doc.commitTransaction()")
        compile(code, f"<{tool_name}>", "exec")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("tool_name", "arguments"),
        [
            ("pad_sketch", {"sketch_name": "Sketch", "length": 10}),
            ("revolution_sketch", {"sketch_name": "Sketch"}),
            ("loft_sketches", {"sketch_names": ["Sketch", "Sketch001"]}),
            (
                "sweep_sketch",
                {"profile_sketch": "Profile", "spine_sketch": "Spine"},
            ),
        ],
    )
    async def test_additive_features_reject_non_positive_material_gain(
        self,
        register_tools: dict[str, Any],
        mock_bridge: AsyncMock,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> None:
        """Additive features must increase the Body volume meaningfully."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"name": "Feature"},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        await register_tools[tool_name](**arguments)

        code = mock_bridge.execute_python.call_args.args[0]
        assert "input_volume" in code
        assert "added_volume = float(feature_shape.Volume) - input_volume" in code
        assert "Additive feature added no material" in code
        assert "open_owned_transaction(doc," in code
        assert "abort_owned_transaction(doc)" in code
        assert code.index("added_volume =") < code.index("doc.commitTransaction()")
        compile(code, f"<{tool_name}>", "exec")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("tool_name", "arguments"),
        [
            ("pocket_sketch", {"sketch_name": "Sketch", "length": 5}),
            ("groove_sketch", {"sketch_name": "Sketch"}),
            ("create_hole", {"sketch_name": "HoleSketch"}),
            (
                "subtractive_loft",
                {"sketch_names": ["Sketch", "Sketch001"]},
            ),
            (
                "subtractive_pipe",
                {"profile_sketch": "Profile", "spine_sketch": "Spine"},
            ),
        ],
    )
    async def test_subtractive_features_reject_no_op_results(
        self, register_tools, mock_bridge, tool_name, arguments
    ):
        """Subtractive features must remove a meaningful material volume."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"name": "Feature"},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        await register_tools[tool_name](**arguments)

        code = mock_bridge.execute_python.call_args.args[0]
        assert "input_volume = float(body.Shape.Volume)" in code
        assert "removed_volume = input_volume - float(shape.Volume)" in code
        assert "Subtractive feature removed no material" in code
        assert "open_owned_transaction(doc," in code
        assert "abort_owned_transaction(doc)" in code
        assert code.index("removed_volume =") < code.index("doc.commitTransaction()")
        compile(code, f"<{tool_name}>", "exec")

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
    async def test_create_datum_plane_binds_offset_expression(
        self, register_tools, mock_bridge
    ):
        """Datum creation should bind the native attachment offset directly."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "GalleryDatum",
                    "label": "GalleryDatum",
                    "type_id": "PartDesign::Plane",
                    "offset_expression": "Variables.tower_height",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        create_datum_plane = register_tools["create_datum_plane"]
        result = await create_datum_plane(
            body_name="Body",
            name="GalleryDatum",
            offset_expression="Variables.tower_height",
        )

        assert result["offset_expression"] == "Variables.tower_height"
        code = mock_bridge.execute_python.call_args.args[0]
        assert (
            'datum.setExpression("AttachmentOffset.Base.z", offset_expression)' in code
        )
        assert "STALE_REVISION" in code
        assert "candidate.Content" in code
        assert '"operation_id"' in code
        assert '"document_ref"' in code
        assert "for candidate in (datum, body)" in code
        assert 'open_owned_transaction(doc, "Create Datum Plane")' in code
        assert code.index('"operation_id"') < code.index("doc.commitTransaction()")
        compile(code, "<create_datum_plane>", "exec")

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
    async def test_add_sketch_constraint_converts_angles_and_supports_point_on_object(
        self, register_tools, mock_bridge
    ):
        """The general repair tool should use native units and overloads."""
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

        await add_constraint(
            sketch_name="Sketch",
            constraint_type="PointOnObject",
            geometry1=0,
            point1=1,
            geometry2=1,
        )

        code = mock_bridge.execute_python.call_args.args[0]
        assert 'Sketcher.Constraint("PointOnObject", g1, p1, g2)' in code
        assert "math.radians(value)" in code
        assert 'open_owned_transaction(doc, "Add Sketch Constraint")' in code
        compile(code, "<add_sketch_constraint>", "exec")

    @pytest.mark.asyncio
    async def test_add_sketch_constraint_supports_point_curve_overloads(
        self, register_tools, mock_bridge
    ):
        """Granular repair should preserve native point-to-curve signatures."""
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

        await add_constraint(
            sketch_name="Sketch",
            constraint_type="Distance",
            geometry1=0,
            point1=1,
            geometry2=1,
            value=5,
        )
        await add_constraint(
            sketch_name="Sketch",
            constraint_type="Tangent",
            geometry1=0,
            point1=2,
            geometry2=1,
        )

        code = mock_bridge.execute_python.call_args.args[0]
        assert "Sketcher.Constraint(ctype, g1, p1, g2, value)" in code
        assert "Sketcher.Constraint(ctype, g1, p1, g2)" in code

    @pytest.mark.asyncio
    async def test_add_sketch_constraint_rejects_single_point_distance(
        self, register_tools, mock_bridge
    ):
        """Generic Distance cannot use the DistanceX/Y point-origin signature."""
        add_constraint = register_tools["add_sketch_constraint"]

        with pytest.raises(ValueError, match="point-to-origin"):
            await add_constraint(
                sketch_name="Sketch",
                constraint_type="Distance",
                geometry1=0,
                point1=1,
                value=5,
            )

        mock_bridge.execute_python.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_sketch_constraint_rejects_point_block(
        self, register_tools, mock_bridge
    ):
        """FreeCAD Block accepts a whole geometry, not a point position."""
        add_constraint = register_tools["add_sketch_constraint"]

        with pytest.raises(ValueError, match="whole geometry"):
            await add_constraint(
                sketch_name="Sketch",
                constraint_type="Block",
                geometry1=0,
                point1=1,
            )

        mock_bridge.execute_python.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_symmetric_sketch_constraint(self, register_tools, mock_bridge):
        """Symmetric constraints should accept a separate symmetry line."""
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
        await add_constraint(
            sketch_name="Sketch",
            constraint_type="Symmetric",
            geometry1=0,
            point1=1,
            geometry2=1,
            point2=1,
            geometry3=2,
        )

        code = mock_bridge.execute_python.call_args.args[0]
        assert "Sketcher.Constraint(ctype, g1, p1, g2, p2, g3)" in code

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
        code = mock_bridge.execute_python.call_args.args[0]
        assert 'Sketcher.Constraint(\n                "DistanceX"' in code
        assert 'Sketcher.Constraint(\n                "DistanceY"' in code
        assert 'Sketcher.Constraint("Block", 0, 1)' not in code

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
                    "fully_constrained": True,
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
        assert result["fully_constrained"] is True
        mock_bridge.execute_python.assert_called_once()
        code = mock_bridge.execute_python.call_args.args[0]
        assert '"geometry": geometry' in code
        assert '"constraints": constraints' in code
        assert '"expressions": expressions' in code
        assert "driving_constraint_types" in code
        assert "if str(item.Type) in driving_constraint_types:" in code
        assert 'details["driving"] = None' in code
        assert "driving_error" not in code
        assert 'hasattr(sketch, "DoF")' in code
        assert "sketch.getLastDoF()" in code

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


class TestSymmetricExtrudeCompatibility:
    """Test FreeCAD 1.1 compatibility for PartDesign and sketch geometry.

    PartDesign::Pad has never had a `Symmetric` property. FreeCAD exposes
    `Midplane`, and 1.1+ supersedes that with `SideType`, emitting a deprecation
    warning when `Midplane` is set. Generated code therefore probes for the
    property rather than assuming one, so a single build works across versions.

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
                result={"success": True, "name": "F", "label": "F", "type_id": "T"},
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

    @staticmethod
    def _generated(mock_bridge):
        code = mock_bridge.execute_python.call_args[0][0]
        # Generated code is exec'd inside FreeCAD, so it must at least parse.
        compile(code, "<generated>", "exec")
        return code

    @pytest.mark.asyncio
    async def test_pad_prefers_sidetype_and_falls_back(
        self, register_tools, mock_bridge
    ):
        await register_tools["pad_sketch"](
            sketch_name="Sketch", length=10.0, symmetric=True
        )
        code = self._generated(mock_bridge)

        assert 'hasattr(pad, "SideType")' in code
        assert 'pad.SideType = "Symmetric" if _symmetric else "One side"' in code
        assert 'elif hasattr(pad, "Midplane")' in code
        assert "pad.Midplane = _symmetric" in code
        # SideType must be tried first, or 1.1 emits a deprecation warning.
        assert code.index("SideType") < code.index("Midplane")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("tool", "var"),
        [("revolution_sketch", "rev"), ("groove_sketch", "groove")],
    )
    async def test_revolution_and_groove_use_midplane(
        self, register_tools, mock_bridge, tool, var
    ):
        """Revolution and Groove have no SideType, so Midplane is correct there."""
        await register_tools[tool](sketch_name="Sketch", angle=360.0, symmetric=True)
        code = self._generated(mock_bridge)

        assert f'hasattr({var}, "Midplane")' in code
        assert f"{var}.Midplane = _symmetric" in code
        assert "SideType" not in code

    @pytest.mark.asyncio
    @pytest.mark.parametrize("symmetric", [True, False])
    async def test_symmetric_value_is_bound_once(
        self, register_tools, mock_bridge, symmetric
    ):
        """The flag is bound to a local, so each branch reads the same value."""
        await register_tools["pad_sketch"](
            sketch_name="Sketch", length=10.0, symmetric=symmetric
        )
        code = self._generated(mock_bridge)

        assert f"_symmetric = {symmetric}" in code

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
