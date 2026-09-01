"""Live regressions for the Stage C parametric workflow hardening."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import pytest

from freecad_mcp.bridge.xmlrpc import XmlRpcBridge
from freecad_mcp.tools.partdesign import register_partdesign_tools
from freecad_mcp.tools.variables import VariableDefinition, register_variable_tools
from freecad_mcp.tools.workflow_results import WorkflowToolError

pytestmark = pytest.mark.integration

RegisteredTool = Callable[..., Awaitable[Any]]
ToolRegistrar = Callable[[Any, Callable[[], Awaitable[Any]]], None]


class _ToolRegistry:
    """Capture FastMCP tool registrations for direct live invocation."""

    def __init__(self) -> None:
        self.tools: dict[str, RegisteredTool] = {}

    def tool(self) -> Callable[[RegisteredTool], RegisteredTool]:
        """Return the decorator used by tool registration functions."""

        def register(function: RegisteredTool) -> RegisteredTool:
            self.tools[function.__name__] = function
            return function

        return register


@pytest.fixture
async def bridge() -> AsyncIterator[XmlRpcBridge]:
    """Connect to the preflighted operator bridge for one regression test."""
    live_bridge = XmlRpcBridge(timeout=10)
    await live_bridge.connect()
    try:
        yield live_bridge
    finally:
        await live_bridge.disconnect()


def _registered_tools(
    bridge: XmlRpcBridge,
    registrar: ToolRegistrar,
) -> dict[str, RegisteredTool]:
    """Register one tool group against a connected live bridge."""
    registry = _ToolRegistry()

    async def get_bridge() -> XmlRpcBridge:
        return bridge

    registrar(registry, get_bridge)
    return registry.tools


async def _close_document(bridge: XmlRpcBridge, doc_name: str) -> None:
    """Close a disposable live-test document without saving it."""
    result = await bridge.execute_python(
        f"""
if {doc_name!r} in FreeCAD.listDocuments():
    FreeCAD.closeDocument({doc_name!r})
_result_ = True
""",
        transaction=None,
    )
    assert result.success, result.error_traceback


@pytest.mark.asyncio
async def test_additive_pad_rejects_no_material_and_rolls_back(
    bridge: XmlRpcBridge,
) -> None:
    """A fully enclosed additive Pad must leave the prior Body unchanged."""
    doc_name = f"StageCAdditive_{uuid.uuid4().hex[:8]}"
    try:
        setup = await bridge.execute_python(
            f"""
import Part
import Sketcher

doc = FreeCAD.newDocument({doc_name!r})
body = doc.addObject("PartDesign::Body", "Body")
base_sketch = body.newObject("Sketcher::SketchObject", "BaseSketch")
base_sketch.AttachmentSupport = [(body.Origin.getObject("XY_Plane"), "")]
base_sketch.MapMode = "FlatFace"
base_sketch.addGeometry(
    Part.Circle(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 10),
    False,
)
base_pad = body.newObject("PartDesign::Pad", "BasePad")
base_pad.Profile = base_sketch
base_pad.Length = 10
doc.recompute()

enclosed_sketch = body.newObject("Sketcher::SketchObject", "EnclosedSketch")
enclosed_sketch.AttachmentSupport = [(body.Origin.getObject("XY_Plane"), "")]
enclosed_sketch.MapMode = "FlatFace"
enclosed_sketch.addGeometry(
    Part.Circle(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 2),
    False,
)
doc.recompute()
_result_ = {{
    "tip": body.Tip.Name,
    "volume": float(body.Shape.Volume),
}}
""",
            transaction="Set Up Regression Fixture",
        )
        assert setup.success, setup.error_traceback

        pad_sketch = _registered_tools(bridge, register_partdesign_tools)["pad_sketch"]
        with pytest.raises(WorkflowToolError) as error:
            await pad_sketch(
                sketch_name="EnclosedSketch",
                length=5,
                name="NoMaterialPad",
                doc_name=doc_name,
            )

        assert error.value.payload.category == "VALIDATION_FAILED"
        assert "Additive feature added no material" in error.value.payload.message
        assert error.value.payload.transaction_committed is False

        inspection = await bridge.execute_python(
            f"""
doc = FreeCAD.getDocument({doc_name!r})
body = doc.getObject("Body")
_result_ = {{
    "feature_exists": doc.getObject("NoMaterialPad") is not None,
    "tip": body.Tip.Name,
    "volume": float(body.Shape.Volume),
}}
""",
            transaction=None,
        )
        assert inspection.success, inspection.error_traceback
        assert inspection.result == {
            "feature_exists": False,
            "tip": setup.result["tip"],
            "volume": setup.result["volume"],
        }
    finally:
        await _close_document(bridge, doc_name)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("variables", "expected_fragments", "unit_mismatch_count"),
    [
        pytest.param(
            [
                VariableDefinition(
                    name="wall_thickness",
                    kind="length",
                    value="4 mm",
                ),
                VariableDefinition(
                    name="window_pocket_depth",
                    kind="length",
                    expression="wall_thickness + 1.0",
                ),
                VariableDefinition(
                    name="door_pocket_depth",
                    kind="length",
                    expression="wall_thickness + 2.0",
                ),
            ],
            (
                "window_pocket_depth",
                "wall_thickness + 1.0",
                "door_pocket_depth",
                "wall_thickness + 2.0",
            ),
            2,
            id="recompute-failures",
        ),
        pytest.param(
            [
                VariableDefinition(
                    name="first_bad_length",
                    kind="length",
                    expression="1 mm +",
                ),
                VariableDefinition(
                    name="second_bad_length",
                    kind="length",
                    expression="(2 mm",
                ),
            ],
            (
                "first_bad_length",
                "1 mm +",
                "second_bad_length",
                "(2 mm",
            ),
            0,
            id="assignment-failures",
        ),
        pytest.param(
            [
                VariableDefinition(
                    name="wall_thickness",
                    kind="length",
                    value="4 mm",
                ),
                VariableDefinition(
                    name="immediate_bad",
                    kind="length",
                    expression="1 mm +",
                ),
                VariableDefinition(
                    name="delayed_bad",
                    kind="length",
                    expression="wall_thickness + 3.0",
                ),
            ],
            (
                "immediate_bad",
                "1 mm +",
                "delayed_bad",
                "wall_thickness + 3.0",
            ),
            1,
            id="mixed-failures",
        ),
    ],
)
async def test_define_variables_reports_each_bad_expression_and_rolls_back(
    bridge: XmlRpcBridge,
    variables: list[VariableDefinition],
    expected_fragments: tuple[str, ...],
    unit_mismatch_count: int,
) -> None:
    """A failed variable batch should identify every invalid expression."""
    doc_name = f"StageCVariables_{uuid.uuid4().hex[:8]}"
    try:
        setup = await bridge.execute_python(
            f"""
doc = FreeCAD.newDocument({doc_name!r})
_result_ = {{"name": doc.Name}}
""",
            transaction="Set Up Regression Fixture",
        )
        assert setup.success, setup.error_traceback

        define_variables = _registered_tools(bridge, register_variable_tools)[
            "define_variables"
        ]
        with pytest.raises(WorkflowToolError) as error:
            await define_variables(
                variable_set_name="Variables",
                variables=variables,
                doc_name=doc_name,
            )

        assert error.value.payload.category == "VALIDATION_FAILED"
        assert error.value.payload.transaction_committed is False
        message = error.value.payload.message
        for fragment in expected_fragments:
            assert fragment in message
        assert message.count("Unit mismatch") == unit_mismatch_count

        inspection = await bridge.execute_python(
            f"""
doc = FreeCAD.getDocument({doc_name!r})
_result_ = {{"variable_set_exists": doc.getObject("Variables") is not None}}
""",
            transaction=None,
        )
        assert inspection.success, inspection.error_traceback
        assert inspection.result == {"variable_set_exists": False}
    finally:
        await _close_document(bridge, doc_name)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "arguments", "pattern_name"),
    [
        (
            "linear_pattern",
            {"direction": "X", "length": 8, "occurrences": 2},
            "LiveLinearPattern",
        ),
        (
            "polar_pattern",
            {"axis": "Z", "angle": 360, "occurrences": 4},
            "LivePolarPattern",
        ),
    ],
)
async def test_pattern_becomes_body_tip_in_live_freecad(
    tool_name: str,
    arguments: dict[str, Any],
    pattern_name: str,
    bridge: XmlRpcBridge,
) -> None:
    """A connected one-solid pattern should become the native Body tip."""
    doc_name = f"StageCPattern_{uuid.uuid4().hex[:8]}"
    try:
        setup = await bridge.execute_python(
            f"""
import Part
import Sketcher

doc = FreeCAD.newDocument({doc_name!r})
body = doc.addObject("PartDesign::Body", "Body")
base_sketch = body.newObject("Sketcher::SketchObject", "BaseSketch")
base_sketch.AttachmentSupport = [(body.Origin.getObject("XY_Plane"), "")]
base_sketch.MapMode = "FlatFace"
base_sketch.addGeometry(
    Part.Circle(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 20),
    False,
)
base_pad = body.newObject("PartDesign::Pad", "BasePad")
base_pad.Profile = base_sketch
base_pad.Length = 5
doc.recompute()

top_plane = body.newObject("PartDesign::Plane", "TopPlane")
top_plane.AttachmentSupport = [(body.Origin.getObject("XY_Plane"), "")]
top_plane.MapMode = "FlatFace"
top_plane.AttachmentOffset = FreeCAD.Placement(
    FreeCAD.Vector(0, 0, 5),
    FreeCAD.Rotation(0, 0, 0, 1),
)
bump_sketch = body.newObject("Sketcher::SketchObject", "BumpSketch")
bump_sketch.AttachmentSupport = [(top_plane, "")]
bump_sketch.MapMode = "FlatFace"
bump_sketch.addGeometry(
    Part.Circle(FreeCAD.Vector(8, 0, 0), FreeCAD.Vector(0, 0, 1), 2),
    False,
)
bump = body.newObject("PartDesign::Pad", "Bump")
bump.Profile = bump_sketch
bump.Length = 3
doc.recompute()
_result_ = {{
    "tip": body.Tip.Name,
    "solid_count": len(body.Shape.Solids),
}}
""",
            transaction="Set Up Regression Fixture",
        )
        assert setup.success, setup.error_traceback
        assert setup.result == {"tip": "Bump", "solid_count": 1}

        pattern_tool = _registered_tools(bridge, register_partdesign_tools)[tool_name]
        result = await pattern_tool(
            feature_name="Bump",
            name=pattern_name,
            doc_name=doc_name,
            **arguments,
        )

        assert result["name"] == pattern_name
        assert result["validation"]["body_tip"] == pattern_name
        assert result["validation"]["solid_count"] == 1
        inspection = await bridge.execute_python(
            f"""
doc = FreeCAD.getDocument({doc_name!r})
body = doc.getObject("Body")
_result_ = {{
    "tip": body.Tip.Name,
    "solid_count": len(body.Shape.Solids),
}}
""",
            transaction=None,
        )
        assert inspection.success, inspection.error_traceback
        assert inspection.result == {"tip": pattern_name, "solid_count": 1}
    finally:
        await _close_document(bridge, doc_name)
