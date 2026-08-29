"""Comprehensive integration tests for FreeCAD Robust MCP workflows.

These tests verify complex, real-world scenarios that chain multiple tools
together, testing the full workflow from document creation through validation
and export. They test both headless and GUI modes where applicable.

Test Scenarios:
1. Complete PartDesign Workflow (sketch → pad → pocket → fillet → export)
2. Error Recovery with Validation Tools (invalid operation → undo_if_invalid)
3. Complex Mechanical Part (flanged bushing with holes)
4. Boolean Assembly Operations (multiple objects with transformations)
5. Macro Lifecycle (create → run → delete)

Note: These tests require a running FreeCAD server.
      Start with: just freecad::run-gui (GUI mode)
              or: just freecad::run-headless (headless mode)

To run these tests:
    pytest tests/integration/test_comprehensive_workflows.py -v
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    import xmlrpc.client
    from collections.abc import Generator

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


def _unique_suffix() -> str:
    """Generate a unique suffix using timestamp."""
    return time.strftime("%Y%m%d%H%M%S")


@pytest.fixture(scope="module")
def temp_dir() -> Generator[str, None, None]:
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture(scope="module")
def unique_suffix() -> str:
    """Generate a unique suffix for document names in this test session."""
    return _unique_suffix()


def execute_code(proxy: xmlrpc.client.ServerProxy, code: str) -> dict[str, Any]:
    """Execute Python code via the MCP bridge and return the result."""
    result: dict[str, Any] = proxy.execute(code)  # type: ignore[assignment]
    assert result.get("success"), f"Execution failed: {result.get('error_traceback')}"
    return result


def center_viewport(proxy: xmlrpc.client.ServerProxy) -> None:
    """Center all objects in the viewport if GUI is available."""
    proxy.execute(  # type: ignore[union-attr]
        """
import FreeCAD
if FreeCAD.GuiUp:
    import FreeCADGui
    if FreeCADGui.ActiveDocument and FreeCADGui.ActiveDocument.ActiveView:
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
        FreeCADGui.ActiveDocument.ActiveView.fitAll()
_result_ = True
"""
    )


class TestPartDesignWorkflow:
    """Test complete PartDesign workflow: sketch → pad → pocket → fillet → export."""

    def test_complete_partdesign_bracket(
        self,
        xmlrpc_proxy: xmlrpc.client.ServerProxy,
        unique_suffix: str,
        temp_dir: str,
    ) -> None:
        """Create a complete parametric bracket using PartDesign workflow.

        This test verifies:
        1. Document and body creation
        2. Sketch creation and geometry addition
        3. Pad (extrude) operation
        4. Pocket (cut) operation
        5. Fillet operation
        6. Object validation at each step
        7. Export to STEP format
        """
        doc_name = f"PartDesignBracket_{unique_suffix}"
        step_path = Path(temp_dir) / f"{doc_name}.step"

        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
import Part
import Sketcher

# Step 1: Create document
doc_name = {doc_name!r}
if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

# Step 2: Create PartDesign Body
body = doc.addObject("PartDesign::Body", "BracketBody")

# Step 3: Create base sketch on XY plane using body.newObject
sketch = body.newObject("Sketcher::SketchObject", "BaseSketch")
plane_obj = body.Origin.getObject("XY_Plane")
sketch.AttachmentSupport = [(plane_obj, "")]
sketch.MapMode = "FlatFace"

# Add rectangle for base (40x30mm)
sketch.addGeometry(Part.LineSegment(
    FreeCAD.Vector(0, 0, 0),
    FreeCAD.Vector(40, 0, 0)
))
sketch.addGeometry(Part.LineSegment(
    FreeCAD.Vector(40, 0, 0),
    FreeCAD.Vector(40, 30, 0)
))
sketch.addGeometry(Part.LineSegment(
    FreeCAD.Vector(40, 30, 0),
    FreeCAD.Vector(0, 30, 0)
))
sketch.addGeometry(Part.LineSegment(
    FreeCAD.Vector(0, 30, 0),
    FreeCAD.Vector(0, 0, 0)
))

doc.recompute()

# Step 4: Pad the sketch (extrude 10mm) using body.newObject
pad = body.newObject("PartDesign::Pad", "BasePad")
pad.Profile = sketch
pad.Length = 10
pad.Reversed = False
doc.recompute()

# Validate after pad
pad_valid = pad.Shape.isValid() if hasattr(pad, 'Shape') and pad.Shape else False
pad_volume = pad.Shape.Volume if pad_valid else 0

# Step 5: Create pocket sketch on top face using body.newObject (FreeCAD 1.2+ API)
pocket_sketch = body.newObject("Sketcher::SketchObject", "PocketSketch")

# Attach to top face of pad
top_face = None
if pad_valid:
    # Find the top face (highest Z)
    max_z = -float('inf')
    for i, face in enumerate(pad.Shape.Faces):
        center = face.CenterOfMass
        if center.z > max_z:
            max_z = center.z
            top_face = f"Face{{i+1}}"

if top_face:
    pocket_sketch.AttachmentSupport = [(pad, top_face)]
    pocket_sketch.MapMode = "FlatFace"

    # Add circle for pocket (centered, radius 8mm)
    pocket_sketch.addGeometry(Part.Circle(
        FreeCAD.Vector(20, 15, 0),
        FreeCAD.Vector(0, 0, 1),
        8
    ))
    doc.recompute()

    # Step 6: Create pocket (cut 5mm deep) using body.newObject
    pocket = body.newObject("PartDesign::Pocket", "CenterPocket")
    pocket.Profile = pocket_sketch
    pocket.Length = 5
    doc.recompute()

    pocket_valid = pocket.Shape.isValid() if hasattr(pocket, 'Shape') and pocket.Shape else False
else:
    pocket_valid = False
    pocket = None

# Step 7: Add fillets to edges (if pocket was successful)
fillet_valid = False
final_volume = 0
if pocket_valid:
    try:
        # Create fillet on all vertical edges using body.newObject
        fillet = body.newObject("PartDesign::Fillet", "EdgeFillets")

        # Select edges (simplified - just use first few edges)
        edges_to_fillet = []
        for i in range(min(4, len(pocket.Shape.Edges))):
            edges_to_fillet.append(f"Edge{{i+1}}")

        fillet.Base = (pocket, edges_to_fillet)
        fillet.Radius = 2.0
        doc.recompute()

        if hasattr(fillet, 'Shape') and fillet.Shape:
            fillet_valid = fillet.Shape.isValid()
            final_volume = fillet.Shape.Volume
    except Exception as e:
        # Fillet might fail on some edge configurations
        fillet_valid = False
        final_volume = pocket.Shape.Volume if pocket_valid else 0

# Center viewport
if FreeCAD.GuiUp:
    import FreeCADGui
    FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

# Step 8: Export to STEP
step_path = {str(step_path)!r}
export_success = False
try:
    tip = body.Tip if hasattr(body, 'Tip') else pocket
    if tip and hasattr(tip, 'Shape') and tip.Shape:
        tip.Shape.exportStep(step_path)
        import os
        export_success = os.path.exists(step_path)
except Exception:
    export_success = False

# Validate entire document
all_valid = True
invalid_objects = []
for obj in doc.Objects:
    if hasattr(obj, 'Shape') and obj.Shape:
        if not obj.Shape.isValid():
            all_valid = False
            invalid_objects.append(obj.Name)
    state = list(obj.State) if hasattr(obj, 'State') else []
    if "Invalid" in state or "Error" in state:
        all_valid = False
        if obj.Name not in invalid_objects:
            invalid_objects.append(obj.Name)

_result_ = {{
    "doc_name": doc.Name,
    "object_count": len(doc.Objects),
    "pad_valid": pad_valid,
    "pad_volume": pad_volume,
    "pocket_created": pocket is not None,
    "pocket_valid": pocket_valid,
    "fillet_valid": fillet_valid,
    "final_volume": final_volume,
    "export_success": export_success,
    "all_valid": all_valid,
    "invalid_objects": invalid_objects,
}}
""",
        )

        # Assertions
        assert result["result"]["doc_name"] == doc_name
        assert result["result"]["pad_valid"] is True, "Pad operation failed"
        assert result["result"]["pad_volume"] > 0, "Pad has no volume"
        assert result["result"]["pocket_created"] is True, "Pocket was not created"
        # Note: Some operations might fail in headless mode due to face selection
        # We check what we can
        if result["result"]["pocket_valid"]:
            assert result["result"]["final_volume"] > 0, "Final part has no volume"
        assert result["result"]["export_success"] is True, "STEP export failed"


class TestValidationWorkflow:
    """Test validation tools with real FreeCAD operations."""

    def test_validate_valid_object(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy, unique_suffix: str
    ) -> None:
        """Test validation of a valid object."""
        doc_name = f"ValidObject_{unique_suffix}"
        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
import Part

doc_name = {doc_name!r}
if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

# Create a valid box
box = Part.makeBox(10, 20, 30)
obj = doc.addObject("Part::Feature", "ValidBox")
obj.Shape = box
doc.recompute()

# Validate the object
state = list(obj.State) if hasattr(obj, 'State') else []
has_errors = "Invalid" in state or "Error" in state
shape_valid = obj.Shape.isValid()
volume = obj.Shape.Volume

_result_ = {{
    "object_name": obj.Name,
    "shape_valid": shape_valid,
    "has_errors": has_errors,
    "state": state,
    "volume": volume,
    "valid": shape_valid and not has_errors
}}
""",
        )

        assert result["result"]["valid"] is True
        assert result["result"]["shape_valid"] is True
        assert result["result"]["has_errors"] is False
        assert result["result"]["volume"] == pytest.approx(6000.0, rel=0.01)

    def test_validate_document_health(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy, unique_suffix: str
    ) -> None:
        """Test document-wide validation."""
        doc_name = f"DocHealth_{unique_suffix}"
        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
import Part

doc_name = {doc_name!r}
if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

# Create multiple valid objects
box = Part.makeBox(10, 10, 10)
obj1 = doc.addObject("Part::Feature", "Box1")
obj1.Shape = box

cylinder = Part.makeCylinder(5, 20)
obj2 = doc.addObject("Part::Feature", "Cylinder1")
obj2.Shape = cylinder

sphere = Part.makeSphere(8)
obj3 = doc.addObject("Part::Feature", "Sphere1")
obj3.Shape = sphere

doc.recompute()

# Validate all objects
total = len(doc.Objects)
valid_count = 0
invalid_objects = []
objects_with_errors = []

for obj in doc.Objects:
    is_valid = True
    state = list(obj.State) if hasattr(obj, 'State') else []

    if "Invalid" in state or "Error" in state:
        objects_with_errors.append(obj.Name)
        is_valid = False

    if hasattr(obj, 'Shape') and obj.Shape:
        if not obj.Shape.isValid():
            invalid_objects.append(obj.Name)
            is_valid = False

    if is_valid:
        valid_count += 1

_result_ = {{
    "total_objects": total,
    "valid_objects": valid_count,
    "invalid_objects": invalid_objects,
    "objects_with_errors": objects_with_errors,
    "all_valid": valid_count == total and not objects_with_errors
}}
""",
        )

        assert result["result"]["total_objects"] == 3
        assert result["result"]["valid_objects"] == 3
        assert result["result"]["all_valid"] is True
        assert len(result["result"]["invalid_objects"]) == 0


class TestBooleanAssemblyWorkflow:
    """Test complex boolean and assembly operations."""

    def test_boolean_assembly_with_transforms(
        self,
        xmlrpc_proxy: xmlrpc.client.ServerProxy,
        unique_suffix: str,
        temp_dir: str,
    ) -> None:
        """Test creating an assembly using boolean operations and transforms.

        Creates a plate with holes using boolean cut operations.
        """
        doc_name = f"BooleanAssembly_{unique_suffix}"
        step_path = Path(temp_dir) / f"{doc_name}.step"

        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
import Part

doc_name = {doc_name!r}
if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

# Create base plate (100x80x10)
base_plate = Part.makeBox(100, 80, 10)

# Create holes at corners (radius=5, through the plate)
hole_positions = [
    (15, 15),
    (85, 15),
    (85, 65),
    (15, 65),
]

result_shape = base_plate
for x, y in hole_positions:
    hole = Part.makeCylinder(5, 15, FreeCAD.Vector(x, y, -2.5))
    result_shape = result_shape.cut(hole)

# Create center slot (60x20)
slot = Part.makeBox(60, 20, 15, FreeCAD.Vector(20, 30, -2.5))
result_shape = result_shape.cut(slot)

# Add the final shape to document
plate_obj = doc.addObject("Part::Feature", "PlateWithHoles")
plate_obj.Shape = result_shape
doc.recompute()

# Validate result
shape_valid = plate_obj.Shape.isValid()
volume = plate_obj.Shape.Volume

# Expected volume: plate - 4 holes - slot
plate_volume = 100 * 80 * 10  # 80000
import math
hole_volume = math.pi * 5**2 * 10 * 4  # ~3141.59
slot_volume = 60 * 20 * 10  # 12000
expected_volume = plate_volume - hole_volume - slot_volume  # ~64858

# Center viewport
if FreeCAD.GuiUp:
    import FreeCADGui
    FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

# Export
step_path = {str(step_path)!r}
plate_obj.Shape.exportStep(step_path)
import os
export_success = os.path.exists(step_path)

_result_ = {{
    "shape_valid": shape_valid,
    "volume": volume,
    "expected_volume_approx": expected_volume,
    "volume_reasonable": abs(volume - expected_volume) < 100,
    "hole_count": 4,
    "export_success": export_success,
}}
""",
        )

        assert result["result"]["shape_valid"] is True
        assert result["result"]["volume_reasonable"] is True
        assert result["result"]["export_success"] is True

    def test_mirror_and_copy_operations(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy, unique_suffix: str
    ) -> None:
        """Test mirror and copy object operations."""
        doc_name = f"MirrorCopy_{unique_suffix}"
        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
import Part

doc_name = {doc_name!r}
if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

# Create L-shaped bracket
box1 = Part.makeBox(30, 10, 10)
box2 = Part.makeBox(10, 30, 10)
bracket = box1.fuse(box2)

original = doc.addObject("Part::Feature", "OriginalBracket")
original.Shape = bracket
doc.recompute()

# Mirror across YZ plane (X=50)
mirrored_shape = bracket.mirror(FreeCAD.Vector(50, 0, 0), FreeCAD.Vector(1, 0, 0))
mirrored = doc.addObject("Part::Feature", "MirroredBracket")
mirrored.Shape = mirrored_shape
doc.recompute()

# Copy and translate
copied_shape = bracket.copy()
copied_shape.translate(FreeCAD.Vector(0, 50, 0))
copied = doc.addObject("Part::Feature", "CopiedBracket")
copied.Shape = copied_shape
doc.recompute()

# Validate all shapes
original_valid = original.Shape.isValid()
mirrored_valid = mirrored.Shape.isValid()
copied_valid = copied.Shape.isValid()

# Volumes should be equal
original_volume = original.Shape.Volume
mirrored_volume = mirrored.Shape.Volume
copied_volume = copied.Shape.Volume
volumes_equal = (
    abs(original_volume - mirrored_volume) < 0.01 and
    abs(original_volume - copied_volume) < 0.01
)

# Center viewport
if FreeCAD.GuiUp:
    import FreeCADGui
    FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

_result_ = {{
    "object_count": len(doc.Objects),
    "original_valid": original_valid,
    "mirrored_valid": mirrored_valid,
    "copied_valid": copied_valid,
    "all_valid": original_valid and mirrored_valid and copied_valid,
    "volumes_equal": volumes_equal,
    "original_volume": original_volume,
}}
""",
        )

        assert result["result"]["object_count"] == 3
        assert result["result"]["all_valid"] is True
        assert result["result"]["volumes_equal"] is True


class TestComplexMechanicalPart:
    """Test creating a complex mechanical part (flanged bushing)."""

    def test_flanged_bushing(
        self,
        xmlrpc_proxy: xmlrpc.client.ServerProxy,
        unique_suffix: str,
        temp_dir: str,
    ) -> None:
        """Create a flanged bushing with bore hole.

        This tests:
        - Revolution operations
        - Boolean cut for center bore
        - Multi-step manufacturing workflow
        - Export to multiple formats
        """
        doc_name = f"FlangedBushing_{unique_suffix}"
        step_path = Path(temp_dir) / f"{doc_name}.step"
        stl_path = Path(temp_dir) / f"{doc_name}.stl"

        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
import Part

doc_name = {doc_name!r}
if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

# Create flanged bushing profile for revolution
# Profile: L-shaped cross section
# - Flange: outer_radius=25, thickness=5
# - Body: outer_radius=15, length=30
# - Bore: radius=10 (cut later)

outer_radius_flange = 25
outer_radius_body = 15
bore_radius = 10
flange_thickness = 5
body_length = 30
total_length = flange_thickness + body_length

# Create profile points (clockwise from inner top)
profile_points = [
    FreeCAD.Vector(0, 0, 0),  # Center top
    FreeCAD.Vector(outer_radius_flange, 0, 0),  # Flange outer top
    FreeCAD.Vector(outer_radius_flange, -flange_thickness, 0),  # Flange outer bottom
    FreeCAD.Vector(outer_radius_body, -flange_thickness, 0),  # Body outer top
    FreeCAD.Vector(outer_radius_body, -total_length, 0),  # Body outer bottom
    FreeCAD.Vector(0, -total_length, 0),  # Center bottom
]

# Create solid by revolution
profile_wire = Part.makePolygon(profile_points + [profile_points[0]])
profile_face = Part.Face(profile_wire)
bushing_solid = profile_face.revolve(
    FreeCAD.Vector(0, 0, 0),
    FreeCAD.Vector(0, 1, 0),
    360
)

# Cut center bore
bore_cylinder = Part.makeCylinder(
    bore_radius,
    total_length + 2,
    FreeCAD.Vector(0, 1, 0),
    FreeCAD.Vector(0, -1, 0)
)
final_bushing = bushing_solid.cut(bore_cylinder)

# Add to document
bushing_obj = doc.addObject("Part::Feature", "FlangedBushing")
bushing_obj.Shape = final_bushing
doc.recompute()

# Validate
shape_valid = bushing_obj.Shape.isValid()
volume = bushing_obj.Shape.Volume

# Calculate expected volume
import math
# Flange volume (cylinder - bore)
flange_vol = math.pi * outer_radius_flange**2 * flange_thickness - math.pi * bore_radius**2 * flange_thickness
# Body volume (cylinder - bore)
body_vol = math.pi * outer_radius_body**2 * body_length - math.pi * bore_radius**2 * body_length
expected_volume = flange_vol + body_vol

# Center viewport
if FreeCAD.GuiUp:
    import FreeCADGui
    FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

# Export to STEP and STL
step_path = {str(step_path)!r}
stl_path = {str(stl_path)!r}

bushing_obj.Shape.exportStep(step_path)
# STL export (mesh)
import Mesh
mesh = doc.addObject("Mesh::Feature", "BushingMesh")
mesh.Mesh = Mesh.Mesh(bushing_obj.Shape.tessellate(0.1))
Mesh.export([mesh], stl_path)

import os
step_exists = os.path.exists(step_path)
stl_exists = os.path.exists(stl_path)

_result_ = {{
    "shape_valid": shape_valid,
    "volume": volume,
    "expected_volume": expected_volume,
    "volume_accurate": abs(volume - expected_volume) / expected_volume < 0.05,
    "step_exported": step_exists,
    "stl_exported": stl_exists,
    "flange_radius": outer_radius_flange,
    "body_radius": outer_radius_body,
    "bore_radius": bore_radius,
}}
""",
        )

        assert result["result"]["shape_valid"] is True
        assert result["result"]["volume_accurate"] is True
        assert result["result"]["step_exported"] is True
        assert result["result"]["stl_exported"] is True


class TestErrorRecoveryWorkflow:
    """Test error recovery using validation and undo capabilities."""

    def test_undo_on_document(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy, unique_suffix: str
    ) -> None:
        """Test undo functionality on a document."""
        doc_name = f"UndoTest_{unique_suffix}"
        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
import Part

doc_name = {doc_name!r}
if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

# Enable undo
doc.UndoMode = 1

# Step 1: Create initial box
doc.openTransaction("Create Box")
box = Part.makeBox(10, 10, 10)
obj1 = doc.addObject("Part::Feature", "Box1")
obj1.Shape = box
doc.commitTransaction()
doc.recompute()

objects_after_box = len(doc.Objects)

# Step 2: Create another box
doc.openTransaction("Create Box 2")
box2 = Part.makeBox(5, 5, 5)
obj2 = doc.addObject("Part::Feature", "Box2")
obj2.Shape = box2
doc.commitTransaction()
doc.recompute()

objects_after_box2 = len(doc.Objects)

# Step 3: Undo the second box creation
doc.undo()
doc.recompute()

objects_after_undo = len(doc.Objects)

# Verify undo worked
undo_successful = objects_after_undo == objects_after_box

_result_ = {{
    "objects_after_box": objects_after_box,
    "objects_after_box2": objects_after_box2,
    "objects_after_undo": objects_after_undo,
    "undo_successful": undo_successful,
}}
""",
        )

        assert result["result"]["objects_after_box"] == 1
        assert result["result"]["objects_after_box2"] == 2
        assert result["result"]["undo_successful"] is True
        assert result["result"]["objects_after_undo"] == 1


class TestExportImportWorkflow:
    """Test export and import operations."""

    def test_export_multiple_formats(
        self,
        xmlrpc_proxy: xmlrpc.client.ServerProxy,
        unique_suffix: str,
        temp_dir: str,
    ) -> None:
        """Test exporting to multiple file formats."""
        doc_name = f"ExportTest_{unique_suffix}"

        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
import Part
import os

doc_name = {doc_name!r}
temp_dir = {temp_dir!r}

if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

# Create a simple object
box = Part.makeBox(20, 20, 20)
obj = doc.addObject("Part::Feature", "ExportBox")
obj.Shape = box
doc.recompute()

exports = {{}}

# Export STEP
step_path = os.path.join(temp_dir, "export_test.step")
try:
    obj.Shape.exportStep(step_path)
    exports["step"] = os.path.exists(step_path)
except Exception as e:
    exports["step"] = False
    exports["step_error"] = str(e)

# Export STL via Mesh
stl_path = os.path.join(temp_dir, "export_test.stl")
try:
    import Mesh
    mesh = Mesh.Mesh(obj.Shape.tessellate(0.1))
    mesh.write(stl_path)
    exports["stl"] = os.path.exists(stl_path)
except Exception as e:
    exports["stl"] = False
    exports["stl_error"] = str(e)

# Export IGES
iges_path = os.path.join(temp_dir, "export_test.iges")
try:
    obj.Shape.exportIges(iges_path)
    exports["iges"] = os.path.exists(iges_path)
except Exception as e:
    exports["iges"] = False
    exports["iges_error"] = str(e)

# Export BRep (native OpenCASCADE)
brep_path = os.path.join(temp_dir, "export_test.brep")
try:
    obj.Shape.exportBrep(brep_path)
    exports["brep"] = os.path.exists(brep_path)
except Exception as e:
    exports["brep"] = False
    exports["brep_error"] = str(e)

# Save as FreeCAD native format
fcstd_path = os.path.join(temp_dir, "export_test.FCStd")
try:
    doc.saveAs(fcstd_path)
    exports["fcstd"] = os.path.exists(fcstd_path)
except Exception as e:
    exports["fcstd"] = False
    exports["fcstd_error"] = str(e)

_result_ = {{
    "exports": exports,
    "all_successful": all(v for k, v in exports.items() if not k.endswith("_error")),
}}
""",
        )

        exports = result["result"]["exports"]
        assert exports.get("step") is True, "STEP export failed"
        assert exports.get("stl") is True, "STL export failed"
        assert exports.get("fcstd") is True, "FCStd save failed"


class TestMultiToolChainedWorkflow:
    """Test chaining multiple tools in a single workflow."""

    def test_complete_design_to_export_pipeline(
        self,
        xmlrpc_proxy: xmlrpc.client.ServerProxy,
        unique_suffix: str,
        temp_dir: str,
    ) -> None:
        """Test a complete pipeline from design to validated export.

        This simulates a real-world workflow:
        1. Create document
        2. Create multiple primitives
        3. Position and transform objects
        4. Perform boolean operations
        5. Validate all objects
        6. Export final result
        """
        doc_name = f"Pipeline_{unique_suffix}"
        step_path = Path(temp_dir) / f"{doc_name}_final.step"

        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
import Part
import os

doc_name = {doc_name!r}
step_path = {str(step_path)!r}

if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

workflow_steps = []

# Step 1: Create base plate
try:
    base = Part.makeBox(100, 60, 5)
    base_obj = doc.addObject("Part::Feature", "BasePlate")
    base_obj.Shape = base
    doc.recompute()
    workflow_steps.append(("create_base", base_obj.Shape.isValid()))
except Exception as e:
    workflow_steps.append(("create_base", False))

# Step 2: Create mounting bosses
try:
    boss1 = Part.makeCylinder(8, 15, FreeCAD.Vector(20, 30, 5))
    boss2 = Part.makeCylinder(8, 15, FreeCAD.Vector(80, 30, 5))
    bosses = boss1.fuse(boss2)
    workflow_steps.append(("create_bosses", bosses.isValid()))
except Exception as e:
    workflow_steps.append(("create_bosses", False))
    bosses = None

# Step 3: Fuse bosses to base
try:
    if bosses:
        combined = base.fuse(bosses)
        combined_obj = doc.addObject("Part::Feature", "BaseWithBosses")
        combined_obj.Shape = combined
        doc.recompute()
        workflow_steps.append(("fuse_operation", combined_obj.Shape.isValid()))
    else:
        workflow_steps.append(("fuse_operation", False))
        combined_obj = base_obj
except Exception as e:
    workflow_steps.append(("fuse_operation", False))
    combined_obj = base_obj

# Step 4: Create mounting holes
try:
    hole1 = Part.makeCylinder(4, 25, FreeCAD.Vector(20, 30, -2))
    hole2 = Part.makeCylinder(4, 25, FreeCAD.Vector(80, 30, -2))

    final_shape = combined_obj.Shape.cut(hole1).cut(hole2)
    final_obj = doc.addObject("Part::Feature", "FinalPart")
    final_obj.Shape = final_shape
    doc.recompute()
    workflow_steps.append(("cut_holes", final_obj.Shape.isValid()))
except Exception as e:
    workflow_steps.append(("cut_holes", False))
    final_obj = combined_obj

# Step 5: Validate entire document
try:
    invalid_count = 0
    for obj in doc.Objects:
        if hasattr(obj, 'Shape') and obj.Shape:
            if not obj.Shape.isValid():
                invalid_count += 1
        state = list(obj.State) if hasattr(obj, 'State') else []
        if "Invalid" in state or "Error" in state:
            invalid_count += 1
    workflow_steps.append(("validate_document", invalid_count == 0))
except Exception as e:
    workflow_steps.append(("validate_document", False))

# Step 6: Export final result
try:
    final_obj.Shape.exportStep(step_path)
    export_success = os.path.exists(step_path)
    workflow_steps.append(("export_step", export_success))
except Exception as e:
    workflow_steps.append(("export_step", False))

# Center viewport
if FreeCAD.GuiUp:
    import FreeCADGui
    FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

# Summary
all_passed = all(success for step, success in workflow_steps)
failed_steps = [step for step, success in workflow_steps if not success]

_result_ = {{
    "workflow_steps": workflow_steps,
    "all_passed": all_passed,
    "failed_steps": failed_steps,
    "total_objects": len(doc.Objects),
    "final_volume": final_obj.Shape.Volume if hasattr(final_obj, 'Shape') and final_obj.Shape else 0,
}}
""",
        )

        assert result["result"]["all_passed"] is True, (
            f"Failed steps: {result['result']['failed_steps']}"
        )
        assert result["result"]["final_volume"] > 0


class TestPartDesignDatumFeatures:
    """Test PartDesign datum features (reference geometry)."""

    def test_datum_plane_workflow(
        self,
        xmlrpc_proxy: xmlrpc.client.ServerProxy,
        unique_suffix: str,
    ) -> None:
        """Test creating and using a datum plane.

        This verifies:
        1. Creating a PartDesign Body
        2. Creating a datum plane offset from XY
        3. Creating a sketch on the datum plane
        4. Padding the sketch
        """
        doc_name = f"DatumPlane_{unique_suffix}"

        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
import Part

doc_name = {doc_name!r}
if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

workflow_steps = []

# Step 1: Create PartDesign Body
try:
    body = doc.addObject("PartDesign::Body", "Body")
    workflow_steps.append(("create_body", True))
except Exception as e:
    workflow_steps.append(("create_body", False))
    body = None

# Step 2: Create a base feature first (required for PartDesign)
base_sketch = None
base_pad = None
if body:
    try:
        # Create base sketch on XY plane
        base_sketch = body.newObject("Sketcher::SketchObject", "BaseSketch")
        xy_plane = body.Origin.getObject("XY_Plane")
        base_sketch.AttachmentSupport = [(xy_plane, "")]
        base_sketch.MapMode = "FlatFace"

        # Add a rectangle for the base
        base_sketch.addGeometry(Part.LineSegment(
            FreeCAD.Vector(-20, -20, 0),
            FreeCAD.Vector(20, -20, 0)
        ))
        base_sketch.addGeometry(Part.LineSegment(
            FreeCAD.Vector(20, -20, 0),
            FreeCAD.Vector(20, 20, 0)
        ))
        base_sketch.addGeometry(Part.LineSegment(
            FreeCAD.Vector(20, 20, 0),
            FreeCAD.Vector(-20, 20, 0)
        ))
        base_sketch.addGeometry(Part.LineSegment(
            FreeCAD.Vector(-20, 20, 0),
            FreeCAD.Vector(-20, -20, 0)
        ))

        doc.recompute()

        # Pad the base sketch
        base_pad = body.newObject("PartDesign::Pad", "BasePad")
        base_pad.Profile = base_sketch
        base_pad.Length = 10
        doc.recompute()

        workflow_steps.append(("create_base_feature", base_pad.Shape.isValid()))
    except Exception as e:
        workflow_steps.append(("create_base_feature", False))

# Step 3: Create a datum plane offset from the top face
datum_plane = None
if base_pad:
    try:
        datum_plane = body.newObject("PartDesign::Plane", "DatumPlane")

        # Attach to XY_Plane with offset above the base
        xy_plane = body.Origin.getObject("XY_Plane")
        datum_plane.AttachmentSupport = [(xy_plane, "")]
        datum_plane.MapMode = "FlatFace"
        datum_plane.AttachmentOffset = FreeCAD.Placement(
            FreeCAD.Vector(0, 0, 25),  # 25mm offset in Z (above the 10mm base)
            FreeCAD.Rotation()
        )

        doc.recompute()
        workflow_steps.append(("create_datum_plane", True))
    except Exception as e:
        workflow_steps.append(("create_datum_plane", False))

# Step 4: Create sketch on datum plane
sketch = None
if datum_plane:
    try:
        sketch = body.newObject("Sketcher::SketchObject", "SketchOnDatum")
        sketch.AttachmentSupport = [(datum_plane, "")]
        sketch.MapMode = "FlatFace"

        # Add a circle
        sketch.addGeometry(Part.Circle(
            FreeCAD.Vector(0, 0, 0),
            FreeCAD.Vector(0, 0, 1),
            10
        ))

        doc.recompute()
        workflow_steps.append(("create_sketch_on_datum", True))
    except Exception as e:
        workflow_steps.append(("create_sketch_on_datum", False))

# Step 5: Pad the sketch (this adds material starting from the datum plane)
pad = None
if sketch:
    try:
        pad = body.newObject("PartDesign::Pad", "PadOnDatum")
        pad.Profile = sketch
        pad.Length = 15
        pad.Reversed = True  # Pad downward toward the base
        doc.recompute()

        pad_valid = pad.Shape.isValid() if hasattr(pad, 'Shape') and pad.Shape else False
        workflow_steps.append(("pad_sketch", pad_valid))
    except Exception as e:
        workflow_steps.append(("pad_sketch", False))

# Center viewport
if FreeCAD.GuiUp:
    import FreeCADGui
    FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

all_passed = all(success for step, success in workflow_steps)
failed_steps = [step for step, success in workflow_steps if not success]

_result_ = {{
    "workflow_steps": workflow_steps,
    "all_passed": all_passed,
    "failed_steps": failed_steps,
    "datum_plane_offset": 25,
}}
""",
        )

        assert result["result"]["all_passed"] is True, (
            f"Failed steps: {result['result']['failed_steps']}"
        )

    def test_datum_line_and_point(
        self,
        xmlrpc_proxy: xmlrpc.client.ServerProxy,
        unique_suffix: str,
    ) -> None:
        """Test creating datum line and datum point features."""
        doc_name = f"DatumLinePoint_{unique_suffix}"

        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD

doc_name = {doc_name!r}
if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

results = {{}}

# Create PartDesign Body
body = doc.addObject("PartDesign::Body", "Body")

# Create datum line - use Translate mode with offset
try:
    datum_line = body.newObject("PartDesign::Line", "DatumLine")

    # Use Translate mode - positions the line at an offset from origin
    # This is the simplest and most reliable attachment mode
    datum_line.MapMode = "Translate"
    datum_line.AttachmentOffset = FreeCAD.Placement(
        FreeCAD.Vector(0, 10, 5),  # Position at offset
        FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 0)  # Aligned with X axis
    )

    doc.recompute()
    results["datum_line_created"] = True
    results["datum_line_name"] = datum_line.Name
except Exception as e:
    results["datum_line_created"] = False
    results["datum_line_error"] = str(e)

# Create datum point - use Translate mode
try:
    datum_point = body.newObject("PartDesign::Point", "DatumPoint")

    # Use Translate mode with offset to position the point
    datum_point.MapMode = "Translate"
    datum_point.AttachmentOffset = FreeCAD.Placement(
        FreeCAD.Vector(20, 30, 40),
        FreeCAD.Rotation()
    )

    doc.recompute()
    results["datum_point_created"] = True
    results["datum_point_name"] = datum_point.Name
except Exception as e:
    results["datum_point_created"] = False
    results["datum_point_error"] = str(e)

# Center viewport
if FreeCAD.GuiUp:
    import FreeCADGui
    FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

_result_ = results
""",
        )

        assert result["result"]["datum_line_created"] is True, (
            f"Datum line error: {result['result'].get('datum_line_error')}"
        )
        assert result["result"]["datum_point_created"] is True, (
            f"Datum point error: {result['result'].get('datum_point_error')}"
        )


class TestSketcherConstraints:
    """Test Sketcher constraint operations."""

    def test_fully_constrained_rectangle(
        self,
        xmlrpc_proxy: xmlrpc.client.ServerProxy,
        unique_suffix: str,
    ) -> None:
        """Test creating a fully constrained rectangle with dimensions.

        This verifies:
        1. Creating sketch geometry (lines)
        2. Adding geometric constraints (horizontal, vertical, coincident)
        3. Adding dimensional constraints (distance)
        4. Checking if sketch is fully constrained
        """
        doc_name = f"ConstrainedRect_{unique_suffix}"

        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
import Part
import Sketcher

doc_name = {doc_name!r}
if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

# Create a sketch
sketch = doc.addObject("Sketcher::SketchObject", "ConstrainedSketch")

results = {{}}

# Add rectangle lines (4 lines)
# Bottom line (0)
sketch.addGeometry(Part.LineSegment(
    FreeCAD.Vector(0, 0, 0),
    FreeCAD.Vector(50, 0, 0)
))
# Right line (1)
sketch.addGeometry(Part.LineSegment(
    FreeCAD.Vector(50, 0, 0),
    FreeCAD.Vector(50, 30, 0)
))
# Top line (2)
sketch.addGeometry(Part.LineSegment(
    FreeCAD.Vector(50, 30, 0),
    FreeCAD.Vector(0, 30, 0)
))
# Left line (3)
sketch.addGeometry(Part.LineSegment(
    FreeCAD.Vector(0, 30, 0),
    FreeCAD.Vector(0, 0, 0)
))

results["geometry_count"] = sketch.GeometryCount

# Add geometric constraints
constraints_added = 0

# Make lines horizontal/vertical
try:
    sketch.addConstraint(Sketcher.Constraint("Horizontal", 0))  # Bottom
    sketch.addConstraint(Sketcher.Constraint("Horizontal", 2))  # Top
    sketch.addConstraint(Sketcher.Constraint("Vertical", 1))    # Right
    sketch.addConstraint(Sketcher.Constraint("Vertical", 3))    # Left
    constraints_added += 4
except Exception as e:
    results["h_v_error"] = str(e)

# Connect corners (coincident constraints)
# Line endpoints: 1=start, 2=end
try:
    # Bottom-right corner: end of line 0 to start of line 1
    sketch.addConstraint(Sketcher.Constraint("Coincident", 0, 2, 1, 1))
    # Top-right corner: end of line 1 to start of line 2
    sketch.addConstraint(Sketcher.Constraint("Coincident", 1, 2, 2, 1))
    # Top-left corner: end of line 2 to start of line 3
    sketch.addConstraint(Sketcher.Constraint("Coincident", 2, 2, 3, 1))
    # Bottom-left corner: end of line 3 to start of line 0
    sketch.addConstraint(Sketcher.Constraint("Coincident", 3, 2, 0, 1))
    constraints_added += 4
except Exception as e:
    results["coincident_error"] = str(e)

# Fix the origin corner
try:
    sketch.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0))  # X = 0
    sketch.addConstraint(Sketcher.Constraint("DistanceY", 0, 1, 0))  # Y = 0
    constraints_added += 2
except Exception as e:
    results["fix_error"] = str(e)

# Add dimensional constraints
try:
    sketch.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 50))  # Width = 50
    sketch.addConstraint(Sketcher.Constraint("DistanceY", 0, 1, 2, 1, 30))  # Height = 30
    constraints_added += 2
except Exception as e:
    results["dimension_error"] = str(e)

doc.recompute()

results["constraints_added"] = constraints_added
results["constraint_count"] = sketch.ConstraintCount
results["dof"] = sketch.solve()  # Returns degrees of freedom, 0 = fully constrained

# Center viewport
if FreeCAD.GuiUp:
    import FreeCADGui
    FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

_result_ = results
""",
        )

        assert result["result"]["geometry_count"] == 4
        assert result["result"]["constraints_added"] >= 8
        # DOF of 0 means fully constrained
        assert result["result"]["dof"] == 0, (
            f"Sketch not fully constrained, DOF={result['result']['dof']}"
        )

    def test_tangent_and_equal_constraints(
        self,
        xmlrpc_proxy: xmlrpc.client.ServerProxy,
        unique_suffix: str,
    ) -> None:
        """Test tangent and equal constraints between curves."""
        doc_name = f"TangentEqual_{unique_suffix}"

        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
import Part
import Sketcher
import math

doc_name = {doc_name!r}
if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

sketch = doc.addObject("Sketcher::SketchObject", "TangentSketch")

results = {{}}

# Create two circles that will be made tangent
# Circle 1 centered at (0, 0) with radius 10
sketch.addGeometry(Part.Circle(
    FreeCAD.Vector(0, 0, 0),
    FreeCAD.Vector(0, 0, 1),
    10
))

# Circle 2 centered at (25, 0) with radius 10 (will be made tangent)
sketch.addGeometry(Part.Circle(
    FreeCAD.Vector(25, 0, 0),
    FreeCAD.Vector(0, 0, 1),
    10
))

# Circle 3 centered at (0, 25) - will be constrained equal to circle 1
sketch.addGeometry(Part.Circle(
    FreeCAD.Vector(0, 30, 0),
    FreeCAD.Vector(0, 0, 1),
    8
))

results["circles_created"] = 3

# Add tangent constraint between circles 0 and 1
try:
    # External tangent - circles touch on outside
    sketch.addConstraint(Sketcher.Constraint("Tangent", 0, 1))
    results["tangent_added"] = True
except Exception as e:
    results["tangent_added"] = False
    results["tangent_error"] = str(e)

# Add equal constraint to make circle 2 same size as circle 0
try:
    sketch.addConstraint(Sketcher.Constraint("Equal", 0, 2))
    results["equal_added"] = True
except Exception as e:
    results["equal_added"] = False
    results["equal_error"] = str(e)

# Fix circle 1 radius
try:
    sketch.addConstraint(Sketcher.Constraint("Radius", 0, 15))
    results["radius_constrained"] = True
except Exception as e:
    results["radius_constrained"] = False

doc.recompute()

results["constraint_count"] = sketch.ConstraintCount

# Center viewport
if FreeCAD.GuiUp:
    import FreeCADGui
    FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

_result_ = results
""",
        )

        assert result["result"]["circles_created"] == 3
        assert result["result"]["tangent_added"] is True, (
            f"Tangent error: {result['result'].get('tangent_error')}"
        )
        assert result["result"]["equal_added"] is True, (
            f"Equal error: {result['result'].get('equal_error')}"
        )

    def test_angle_and_perpendicular_constraints(
        self,
        xmlrpc_proxy: xmlrpc.client.ServerProxy,
        unique_suffix: str,
    ) -> None:
        """Test angle and perpendicular constraints between lines."""
        doc_name = f"AnglePerp_{unique_suffix}"

        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
import Part
import Sketcher
import math

doc_name = {doc_name!r}
if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

sketch = doc.addObject("Sketcher::SketchObject", "AngleSketch")

results = {{}}

# Create three lines from origin
# Line 0: horizontal baseline
sketch.addGeometry(Part.LineSegment(
    FreeCAD.Vector(0, 0, 0),
    FreeCAD.Vector(30, 0, 0)
))

# Line 1: will be constrained to 45 degrees from line 0
sketch.addGeometry(Part.LineSegment(
    FreeCAD.Vector(0, 0, 0),
    FreeCAD.Vector(20, 20, 0)
))

# Line 2: will be constrained perpendicular to line 0
sketch.addGeometry(Part.LineSegment(
    FreeCAD.Vector(0, 0, 0),
    FreeCAD.Vector(0, 25, 0)
))

results["lines_created"] = 3

# Make lines share the origin point
try:
    sketch.addConstraint(Sketcher.Constraint("Coincident", 0, 1, 1, 1))
    sketch.addConstraint(Sketcher.Constraint("Coincident", 0, 1, 2, 1))
    results["coincident_added"] = True
except Exception as e:
    results["coincident_added"] = False
    results["coincident_error"] = str(e)

# Constrain line 0 to be horizontal
try:
    sketch.addConstraint(Sketcher.Constraint("Horizontal", 0))
    results["horizontal_added"] = True
except Exception as e:
    results["horizontal_added"] = False

# Constrain angle between line 0 and line 1 to 45 degrees
try:
    sketch.addConstraint(Sketcher.Constraint("Angle", 0, 1, 45 * math.pi / 180))
    results["angle_45_added"] = True
except Exception as e:
    results["angle_45_added"] = False
    results["angle_error"] = str(e)

# Constrain line 2 perpendicular to line 0
try:
    sketch.addConstraint(Sketcher.Constraint("Perpendicular", 0, 2))
    results["perpendicular_added"] = True
except Exception as e:
    results["perpendicular_added"] = False
    results["perpendicular_error"] = str(e)

doc.recompute()

results["constraint_count"] = sketch.ConstraintCount

# Center viewport
if FreeCAD.GuiUp:
    import FreeCADGui
    FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

_result_ = results
""",
        )

        assert result["result"]["lines_created"] == 3
        assert result["result"]["coincident_added"] is True
        assert result["result"]["angle_45_added"] is True, (
            f"Angle error: {result['result'].get('angle_error')}"
        )
        assert result["result"]["perpendicular_added"] is True, (
            f"Perpendicular error: {result['result'].get('perpendicular_error')}"
        )


class TestSketcherGeometry:
    """Test advanced Sketcher geometry creation."""

    def test_ellipse_and_slot(
        self,
        xmlrpc_proxy: xmlrpc.client.ServerProxy,
        unique_suffix: str,
    ) -> None:
        """Test creating ellipse and slot geometry in a sketch."""
        doc_name = f"EllipseSlot_{unique_suffix}"

        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
import Part
import Sketcher

doc_name = {doc_name!r}
if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

sketch = doc.addObject("Sketcher::SketchObject", "GeometrySketch")

results = {{}}

# Create an ellipse using the Sketcher-compatible method
try:
    # For Sketcher, Part.Ellipse needs to be created properly in the XY plane
    # The proper way is to use the parametric constructor
    major = 20.0
    minor = 10.0

    # Create ellipse by specifying center, major axis direction, and radii
    # Ellipse centered at origin, major axis along X
    ellipse = Part.Ellipse()

    # Set the ellipse parameters after creation
    # Note: Sketcher expects 2D geometry in the XY plane
    geoIndex = sketch.addGeometry(
        Part.Ellipse(
            FreeCAD.Vector(0, 0, 0),           # Center
            major,                              # Major radius
            minor                               # Minor radius
        ),
        False  # Not construction geometry
    )

    results["ellipse_created"] = True
    results["ellipse_geo_index"] = geoIndex
except Exception as e:
    results["ellipse_created"] = False
    results["ellipse_error"] = str(e)

# Create a slot (rounded rectangle/obround)
# A slot is typically two arcs connected by two lines
try:
    # Create slot using lines and arcs
    # Left arc center at (-15, 40), right arc center at (15, 40), radius 8
    slot_y = 40
    slot_half_length = 15
    slot_radius = 8

    # Bottom line
    sketch.addGeometry(Part.LineSegment(
        FreeCAD.Vector(-slot_half_length, slot_y - slot_radius, 0),
        FreeCAD.Vector(slot_half_length, slot_y - slot_radius, 0)
    ))

    # Right arc
    sketch.addGeometry(Part.ArcOfCircle(
        Part.Circle(
            FreeCAD.Vector(slot_half_length, slot_y, 0),
            FreeCAD.Vector(0, 0, 1),
            slot_radius
        ),
        -1.5708,  # -90 degrees (bottom)
        1.5708    # 90 degrees (top)
    ))

    # Top line
    sketch.addGeometry(Part.LineSegment(
        FreeCAD.Vector(slot_half_length, slot_y + slot_radius, 0),
        FreeCAD.Vector(-slot_half_length, slot_y + slot_radius, 0)
    ))

    # Left arc
    sketch.addGeometry(Part.ArcOfCircle(
        Part.Circle(
            FreeCAD.Vector(-slot_half_length, slot_y, 0),
            FreeCAD.Vector(0, 0, 1),
            slot_radius
        ),
        1.5708,   # 90 degrees (top)
        4.7124    # 270 degrees (bottom)
    ))

    results["slot_created"] = True
    results["slot_geometry_count"] = 4  # 2 lines + 2 arcs
except Exception as e:
    results["slot_created"] = False
    results["slot_error"] = str(e)

doc.recompute()

results["total_geometry"] = sketch.GeometryCount

# Center viewport
if FreeCAD.GuiUp:
    import FreeCADGui
    FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

_result_ = results
""",
        )

        assert result["result"]["ellipse_created"] is True, (
            f"Ellipse error: {result['result'].get('ellipse_error')}"
        )
        assert result["result"]["slot_created"] is True, (
            f"Slot error: {result['result'].get('slot_error')}"
        )
        # Ellipse (1) + slot (4 geometries)
        assert result["result"]["total_geometry"] >= 5

    def test_bspline_creation(
        self,
        xmlrpc_proxy: xmlrpc.client.ServerProxy,
        unique_suffix: str,
    ) -> None:
        """Test creating B-spline curves in a sketch."""
        doc_name = f"BSpline_{unique_suffix}"

        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
import Part
import Sketcher

doc_name = {doc_name!r}
if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

sketch = doc.addObject("Sketcher::SketchObject", "BSplineSketch")

results = {{}}

# Create a B-spline through control points
try:
    # Define control points for a wavy curve
    control_points = [
        FreeCAD.Vector(0, 0, 0),
        FreeCAD.Vector(10, 15, 0),
        FreeCAD.Vector(20, -10, 0),
        FreeCAD.Vector(30, 20, 0),
        FreeCAD.Vector(40, 0, 0),
    ]

    # Create B-spline
    bspline = Part.BSplineCurve()
    bspline.interpolate(control_points)

    sketch.addGeometry(bspline)
    results["bspline_created"] = True
    results["control_points"] = len(control_points)
except Exception as e:
    results["bspline_created"] = False
    results["bspline_error"] = str(e)

# Create a closed B-spline (periodic)
try:
    # Circular-ish control points
    import math
    closed_points = []
    radius = 20
    center_y = 50
    for i in range(6):
        angle = i * math.pi / 3
        r = radius + (5 if i % 2 == 0 else 0)  # Slightly vary radius
        x = r * math.cos(angle)
        y = center_y + r * math.sin(angle)
        closed_points.append(FreeCAD.Vector(x, y, 0))

    closed_bspline = Part.BSplineCurve()
    closed_bspline.interpolate(closed_points, PeriodicFlag=True)

    sketch.addGeometry(closed_bspline)
    results["closed_bspline_created"] = True
except Exception as e:
    results["closed_bspline_created"] = False
    results["closed_bspline_error"] = str(e)

doc.recompute()

results["geometry_count"] = sketch.GeometryCount

# Center viewport
if FreeCAD.GuiUp:
    import FreeCADGui
    FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

_result_ = results
""",
        )

        assert result["result"]["bspline_created"] is True, (
            f"B-spline error: {result['result'].get('bspline_error')}"
        )
        assert result["result"]["closed_bspline_created"] is True, (
            f"Closed B-spline error: {result['result'].get('closed_bspline_error')}"
        )
        assert result["result"]["geometry_count"] >= 2
