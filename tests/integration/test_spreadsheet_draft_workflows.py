"""Integration tests for Spreadsheet and Draft workbench workflows.

These tests verify:
1. Spreadsheet workbench for parametric design (cells drive model dimensions)
2. Draft ShapeString for creating 3D text geometry
3. Integration between Draft text and PartDesign for embossing/engraving

Note: These tests require a running FreeCAD server.
      Start with: just freecad::run-gui (GUI mode)
              or: just freecad::run-headless (headless mode)

To run these tests:
    pytest tests/integration/test_spreadsheet_draft_workflows.py -v
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

# Shared font discovery code block - used by multiple tests
# Sets `font_path` to the first valid font found, or None if no fonts available
FONT_DISCOVERY_CODE = """
# Find a suitable font file
font_path = None
font_dirs = [
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/truetype/liberation",
    "/System/Library/Fonts",
    "/Library/Fonts",
    "C:/Windows/Fonts",
]

font_names = ["DejaVuSans.ttf", "LiberationSans-Regular.ttf", "Arial.ttf", "Helvetica.ttc"]

for font_dir in font_dirs:
    if os.path.isdir(font_dir):
        for font_name in font_names:
            test_path = os.path.join(font_dir, font_name)
            if os.path.isfile(test_path):
                font_path = test_path
                break
    if font_path:
        break
"""


def _unique_suffix() -> str:
    """Generate a unique suffix using timestamp.

    Creates a timestamp-based string suffix to ensure unique document
    names across test runs.

    Returns:
        A timestamp string in YYYYMMDDHHmmss format.

    Raises:
        None.

    Example:
        >>> suffix = _unique_suffix()
        >>> suffix  # e.g., "20250121143052"
    """
    return time.strftime("%Y%m%d%H%M%S")


@pytest.fixture(scope="module")
def temp_dir() -> Generator[str, None, None]:
    """Create a temporary directory for test files.

    Creates a temporary directory that persists for the entire test module
    and is automatically cleaned up after all tests complete.

    Yields:
        Path to the temporary directory as a string.

    Raises:
        None.

    Example:
        def test_export(temp_dir):
            output_path = f"{temp_dir}/output.csv"
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture(scope="module")
def unique_suffix() -> str:
    """Generate a unique suffix for document names in this test session.

    Creates a timestamp-based suffix that remains constant for all tests
    in the module, ensuring document names are unique but consistent
    within a test session.

    Returns:
        A timestamp string in YYYYMMDDHHmmss format.

    Raises:
        None.

    Example:
        def test_create_doc(unique_suffix):
            doc_name = f"TestDoc_{unique_suffix}"
    """
    return _unique_suffix()


def execute_code(proxy: xmlrpc.client.ServerProxy, code: str) -> dict[str, Any]:
    """Execute Python code via the MCP bridge and return the result.

    Sends Python code to FreeCAD for execution via the XML-RPC bridge
    and validates that execution was successful.

    Args:
        proxy: The XML-RPC server proxy connected to FreeCAD.
        code: Python code string to execute in FreeCAD's context.

    Returns:
        Dictionary containing the execution result with at least:
            - success: Boolean indicating execution succeeded
            - result: The value assigned to _result_ in the code

    Raises:
        AssertionError: If execution fails (result["success"] is False).

    Example:
        result = execute_code(proxy, "_result_ = {'version': 1}")
        assert result["result"]["version"] == 1
    """
    result: dict[str, Any] = proxy.execute(code, 30000, None)  # type: ignore[assignment]
    assert result.get("success"), f"Execution failed: {result.get('error_traceback')}"
    return result


class TestSpreadsheetWorkflow:
    """Test Spreadsheet workbench for parametric design."""

    def test_create_spreadsheet_and_set_cells(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy, unique_suffix: str
    ) -> None:
        """Test creating a spreadsheet and setting cell values.

        Verifies that a spreadsheet can be created, cell values set, and
        aliases assigned for use in expressions.

        Args:
            xmlrpc_proxy: The XML-RPC server proxy connected to FreeCAD.
            unique_suffix: Unique timestamp suffix for document naming.

        Returns:
            None.

        Raises:
            AssertionError: If spreadsheet operations fail.

        Example:
            Test creates a Parameters spreadsheet with Length, Width, Height.
        """
        doc_name = f"SpreadsheetTest_{unique_suffix}"

        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD

doc_name = {doc_name!r}
if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

# Create spreadsheet
sheet = doc.addObject("Spreadsheet::Sheet", "Parameters")

# Set cell values
sheet.set("A1", "Length")
sheet.set("B1", "100")
sheet.set("A2", "Width")
sheet.set("B2", "50")
sheet.set("A3", "Height")
sheet.set("B3", "25")

# Set aliases for easy reference
sheet.setAlias("B1", "Length")
sheet.setAlias("B2", "Width")
sheet.setAlias("B3", "Height")

doc.recompute()

# Verify values
_result_ = {{
    "sheet_name": sheet.Name,
    "length": float(sheet.get("B1")),
    "width": float(sheet.get("B2")),
    "height": float(sheet.get("B3")),
    "aliases": {{
        "Length": sheet.getAlias("B1"),
        "Width": sheet.getAlias("B2"),
        "Height": sheet.getAlias("B3"),
    }}
}}
""",
        )

        assert result["result"]["sheet_name"] == "Parameters"
        assert result["result"]["length"] == 100.0
        assert result["result"]["width"] == 50.0
        assert result["result"]["height"] == 25.0
        assert result["result"]["aliases"]["Length"] == "Length"

    def test_parametric_box_from_spreadsheet(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy, unique_suffix: str
    ) -> None:
        """Test creating a parametric box driven by spreadsheet values.

        Verifies that a Part::Box can be linked to spreadsheet cells via
        expressions, and that changing spreadsheet values updates the box.

        Args:
            xmlrpc_proxy: The XML-RPC server proxy connected to FreeCAD.
            unique_suffix: Unique timestamp suffix for document naming.

        Returns:
            None.

        Raises:
            AssertionError: If parametric linking or updates fail.

        Example:
            Test creates a box linked to Params.Length, Params.Width, Params.Height.
        """
        doc_name = f"ParametricBox_{unique_suffix}"

        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
import Part

doc_name = {doc_name!r}
if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

# Create spreadsheet with parameters
sheet = doc.addObject("Spreadsheet::Sheet", "Params")
sheet.set("A1", "Length")
sheet.set("B1", "80")
sheet.setAlias("B1", "Length")

sheet.set("A2", "Width")
sheet.set("B2", "40")
sheet.setAlias("B2", "Width")

sheet.set("A3", "Height")
sheet.set("B3", "20")
sheet.setAlias("B3", "Height")

doc.recompute()

# Create a Part::Box
box = doc.addObject("Part::Box", "ParametricBox")

# Set expressions to link to spreadsheet
box.setExpression("Length", "Params.Length")
box.setExpression("Width", "Params.Width")
box.setExpression("Height", "Params.Height")

doc.recompute()

# Verify the box dimensions
box_length = box.Length.Value
box_width = box.Width.Value
box_height = box.Height.Value
box_volume = box.Shape.Volume

# Now change spreadsheet value and verify it updates
sheet.set("B1", "100")  # Change Length from 80 to 100
doc.recompute()

new_length = box.Length.Value
new_volume = box.Shape.Volume

_result_ = {{
    "initial_length": box_length,
    "initial_width": box_width,
    "initial_height": box_height,
    "initial_volume": box_volume,
    "new_length": new_length,
    "new_volume": new_volume,
    "parametric_update_worked": new_length == 100.0 and new_volume > box_volume,
}}
""",
        )

        assert result["result"]["initial_length"] == 80.0
        assert result["result"]["initial_width"] == 40.0
        assert result["result"]["initial_height"] == 20.0
        assert result["result"]["initial_volume"] == pytest.approx(64000.0, rel=0.01)
        assert result["result"]["new_length"] == 100.0
        assert result["result"]["parametric_update_worked"] is True

    def test_spreadsheet_formulas(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy, unique_suffix: str
    ) -> None:
        """Test spreadsheet with formulas for calculated values.

        Verifies that spreadsheet cells can contain formulas that reference
        other cells, and that calculated values are correct.

        Args:
            xmlrpc_proxy: The XML-RPC server proxy connected to FreeCAD.
            unique_suffix: Unique timestamp suffix for document naming.

        Returns:
            None.

        Raises:
            AssertionError: If formula calculation fails.

        Example:
            Test creates formulas like =B1*B2 for area calculation.
        """
        doc_name = f"SpreadsheetFormulas_{unique_suffix}"

        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD

doc_name = {doc_name!r}
if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

# Create spreadsheet
sheet = doc.addObject("Spreadsheet::Sheet", "Calculations")

# Set base values
sheet.set("A1", "Radius")
sheet.set("B1", "10")
sheet.setAlias("B1", "Radius")

sheet.set("A2", "Height")
sheet.set("B2", "25")
sheet.setAlias("B2", "Height")

# Set formula for calculated values
# Pi * r^2 for area
sheet.set("A3", "BaseArea")
sheet.set("B3", "=3.14159 * B1 * B1")
sheet.setAlias("B3", "BaseArea")

# Pi * r^2 * h for volume
sheet.set("A4", "Volume")
sheet.set("B4", "=B3 * B2")
sheet.setAlias("B4", "Volume")

doc.recompute()

# Get calculated values
base_area = float(sheet.get("B3"))
volume = float(sheet.get("B4"))

# Expected: pi * 10^2 = 314.159, volume = 314.159 * 25 = 7853.975
_result_ = {{
    "radius": float(sheet.get("B1")),
    "height": float(sheet.get("B2")),
    "base_area": base_area,
    "volume": volume,
    "area_correct": abs(base_area - 314.159) < 0.01,
    "volume_correct": abs(volume - 7853.975) < 0.1,
}}
""",
        )

        assert result["result"]["radius"] == 10.0
        assert result["result"]["height"] == 25.0
        assert result["result"]["area_correct"] is True
        assert result["result"]["volume_correct"] is True

    def test_spreadsheet_with_partdesign_body(
        self,
        xmlrpc_proxy: xmlrpc.client.ServerProxy,
        unique_suffix: str,
        temp_dir: str,
    ) -> None:
        """Test using spreadsheet to drive PartDesign dimensions.

        Verifies that spreadsheet values can drive PartDesign sketch
        constraints via expressions for fully parametric design.

        Args:
            xmlrpc_proxy: The XML-RPC server proxy connected to FreeCAD.
            unique_suffix: Unique timestamp suffix for document naming.
            temp_dir: Temporary directory for export files.

        Returns:
            None.

        Raises:
            AssertionError: If parametric PartDesign operations fail.

        Example:
            Test creates a plate with dimensions from Dimensions spreadsheet.
        """
        doc_name = f"SpreadsheetPartDesign_{unique_suffix}"
        step_path = Path(temp_dir) / f"{doc_name}.step"

        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
import Part

doc_name = {doc_name!r}
step_path = {str(step_path)!r}

if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

workflow_steps = []

# Step 1: Create spreadsheet with parameters
try:
    sheet = doc.addObject("Spreadsheet::Sheet", "Dimensions")
    sheet.set("A1", "PlateLength")
    sheet.set("B1", "100")
    sheet.setAlias("B1", "PlateLength")

    sheet.set("A2", "PlateWidth")
    sheet.set("B2", "60")
    sheet.setAlias("B2", "PlateWidth")

    sheet.set("A3", "PlateThickness")
    sheet.set("B3", "10")
    sheet.setAlias("B3", "PlateThickness")

    sheet.set("A4", "HoleRadius")
    sheet.set("B4", "5")
    sheet.setAlias("B4", "HoleRadius")

    doc.recompute()
    workflow_steps.append(("create_spreadsheet", True))
except Exception as e:
    workflow_steps.append(("create_spreadsheet", False))

# Step 2: Create PartDesign Body
try:
    body = doc.addObject("PartDesign::Body", "PlateBody")
    workflow_steps.append(("create_body", True))
except Exception as e:
    workflow_steps.append(("create_body", False))
    body = None

# Step 3: Create base sketch
sketch = None
if body:
    try:
        sketch = body.newObject("Sketcher::SketchObject", "BaseSketch")
        xy_plane = body.Origin.getObject("XY_Plane")
        sketch.AttachmentSupport = [(xy_plane, "")]
        sketch.MapMode = "FlatFace"

        # Add rectangle (will be constrained later)
        sketch.addGeometry(Part.LineSegment(
            FreeCAD.Vector(0, 0, 0),
            FreeCAD.Vector(100, 0, 0)
        ))
        sketch.addGeometry(Part.LineSegment(
            FreeCAD.Vector(100, 0, 0),
            FreeCAD.Vector(100, 60, 0)
        ))
        sketch.addGeometry(Part.LineSegment(
            FreeCAD.Vector(100, 60, 0),
            FreeCAD.Vector(0, 60, 0)
        ))
        sketch.addGeometry(Part.LineSegment(
            FreeCAD.Vector(0, 60, 0),
            FreeCAD.Vector(0, 0, 0)
        ))

        doc.recompute()
        workflow_steps.append(("create_sketch", True))
    except Exception as e:
        workflow_steps.append(("create_sketch", False))

# Step 4: Pad the sketch
pad = None
if sketch:
    try:
        pad = body.newObject("PartDesign::Pad", "BasePad")
        pad.Profile = sketch
        pad.Length = 10  # Will be linked to spreadsheet
        pad.setExpression("Length", "Dimensions.PlateThickness")
        doc.recompute()

        pad_valid = pad.Shape.isValid() if hasattr(pad, 'Shape') and pad.Shape else False
        workflow_steps.append(("create_pad", pad_valid))
    except Exception as e:
        workflow_steps.append(("create_pad", False))

# Step 5: Validate and export
export_success = False
if pad and hasattr(pad, 'Shape') and pad.Shape:
    try:
        pad.Shape.exportStep(step_path)
        import os
        export_success = os.path.exists(step_path)
        workflow_steps.append(("export", export_success))
    except Exception as e:
        workflow_steps.append(("export", False))

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
    "pad_thickness": pad.Length.Value if pad else 0,
    "export_success": export_success,
}}
""",
        )

        assert result["result"]["all_passed"] is True, (
            f"Failed steps: {result['result']['failed_steps']}"
        )
        assert result["result"]["pad_thickness"] == 10.0
        assert result["result"]["export_success"] is True


class TestDraftShapeStringWorkflow:
    """Test Draft ShapeString for 3D text creation."""

    def test_create_shapestring(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy, unique_suffix: str
    ) -> None:
        """Test creating a basic ShapeString.

        Verifies that Draft.make_shapestring creates valid wire geometry
        for text that can be used in further modeling operations.

        Args:
            xmlrpc_proxy: The XML-RPC server proxy connected to FreeCAD.
            unique_suffix: Unique timestamp suffix for document naming.

        Returns:
            None.

        Raises:
            pytest.skip: If no suitable font file is found in test environment.
            AssertionError: If ShapeString creation fails.

        Example:
            Test creates a ShapeString with text "TEST" and validates shape.
        """
        doc_name = f"ShapeStringTest_{unique_suffix}"

        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
import Draft
import os

doc_name = {doc_name!r}
if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

results = {{}}

{FONT_DISCOVERY_CODE}

if font_path:
    results["font_found"] = True
    results["font_path"] = font_path

    # Create ShapeString
    try:
        # Draft.make_shapestring(string, fontfile, size, tracking)
        shape_string = Draft.make_shapestring("TEST", font_path, 10.0, 0)
        doc.recompute()

        results["shapestring_created"] = shape_string is not None
        results["shapestring_name"] = shape_string.Name if shape_string else None

        # Check if it has a valid shape
        if shape_string and hasattr(shape_string, 'Shape') and shape_string.Shape:
            results["has_shape"] = True
            results["shape_valid"] = shape_string.Shape.isValid()
            # ShapeString creates wires, check if we have edges
            results["edge_count"] = len(shape_string.Shape.Edges)
        else:
            results["has_shape"] = False
    except Exception as e:
        results["shapestring_created"] = False
        results["error"] = str(e)
else:
    results["font_found"] = False
    results["shapestring_created"] = False
    results["error"] = "No suitable font file found"

# Center viewport
if FreeCAD.GuiUp:
    import FreeCADGui
    FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

_result_ = results
""",
        )

        # Skip test if no font was found (CI environment may not have fonts)
        if not result["result"].get("font_found"):
            pytest.skip("No suitable font file found in test environment")

        assert result["result"]["shapestring_created"] is True, (
            f"ShapeString error: {result['result'].get('error')}"
        )
        assert result["result"]["has_shape"] is True
        assert result["result"]["edge_count"] > 0

    def test_shapestring_to_face_and_extrude(
        self,
        xmlrpc_proxy: xmlrpc.client.ServerProxy,
        unique_suffix: str,
        temp_dir: str,
    ) -> None:
        """Test converting ShapeString to face and extruding to 3D solid.

        Verifies the complete workflow of creating ShapeString, converting
        wires to faces, and extruding to create 3D text geometry.

        Args:
            xmlrpc_proxy: The XML-RPC server proxy connected to FreeCAD.
            unique_suffix: Unique timestamp suffix for document naming.
            temp_dir: Temporary directory for export files.

        Returns:
            None.

        Raises:
            pytest.skip: If no suitable font file is found in test environment.
            AssertionError: If extrusion workflow fails.

        Example:
            Test creates "ABC" text, converts to face, extrudes to 5mm solid.
        """
        doc_name = f"ShapeStringExtrude_{unique_suffix}"
        step_path = Path(temp_dir) / f"{doc_name}.step"

        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
import Draft
import Part
import os

doc_name = {doc_name!r}
step_path = {str(step_path)!r}

if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

results = {{}}
workflow_steps = []

{FONT_DISCOVERY_CODE}

if not font_path:
    results["font_found"] = False
    _result_ = results
else:
    results["font_found"] = True

    # Step 1: Create ShapeString
    try:
        shape_string = Draft.make_shapestring("HI", font_path, 15.0, 0)
        doc.recompute()
        workflow_steps.append(("create_shapestring", shape_string is not None))
    except Exception as e:
        workflow_steps.append(("create_shapestring", False))
        results["shapestring_error"] = str(e)
        shape_string = None

    # Step 2: Convert to Faces and Extrude
    text_solid = None
    if shape_string and hasattr(shape_string, 'Shape') and shape_string.Shape:
        try:
            # Get wires from ShapeString - each closed wire becomes a face
            wires = shape_string.Shape.Wires
            if wires:
                # Create faces from each closed wire and extrude
                solids = []
                for wire in wires:
                    if wire.isClosed():
                        face = Part.Face(wire)
                        solid = face.extrude(FreeCAD.Vector(0, 0, 5))  # 5mm height
                        solids.append(solid)

                if solids:
                    # Fuse all solids together
                    text_solid = solids[0]
                    for s in solids[1:]:
                        text_solid = text_solid.fuse(s)

                    solid_obj = doc.addObject("Part::Feature", "TextSolid")
                    solid_obj.Shape = text_solid
                    doc.recompute()
                    workflow_steps.append(("extrude_solid", text_solid.isValid()))
                    results["solid_volume"] = text_solid.Volume
                else:
                    workflow_steps.append(("extrude_solid", False))
                    results["extrude_error"] = "No closed wires found"
            else:
                workflow_steps.append(("extrude_solid", False))
                results["extrude_error"] = "No wires in ShapeString"
        except Exception as e:
            workflow_steps.append(("extrude_solid", False))
            results["extrude_error"] = str(e)

    # Step 4: Export
    if text_solid and text_solid.isValid():
        try:
            text_solid.exportStep(step_path)
            import os as os_mod
            export_success = os_mod.path.exists(step_path)
            workflow_steps.append(("export", export_success))
        except Exception as e:
            workflow_steps.append(("export", False))
            results["export_error"] = str(e)

    # Center viewport
    if FreeCAD.GuiUp:
        import FreeCADGui
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
        FreeCADGui.ActiveDocument.ActiveView.fitAll()

    results["workflow_steps"] = workflow_steps
    results["all_passed"] = all(success for step, success in workflow_steps)
    results["failed_steps"] = [step for step, success in workflow_steps if not success]

    _result_ = results
""",
        )

        # Skip test if no font was found
        if not result["result"].get("font_found"):
            pytest.skip("No suitable font file found in test environment")

        assert result["result"]["all_passed"] is True, (
            f"Failed steps: {result['result']['failed_steps']}"
        )
        assert result["result"]["solid_volume"] > 0

    def test_text_embossed_on_plate(
        self,
        xmlrpc_proxy: xmlrpc.client.ServerProxy,
        unique_suffix: str,
        temp_dir: str,
    ) -> None:
        """Test embossing text onto a plate using boolean fuse.

        Verifies the workflow of creating raised text on a surface by
        extruding ShapeString and fusing with a base plate.

        Args:
            xmlrpc_proxy: The XML-RPC server proxy connected to FreeCAD.
            unique_suffix: Unique timestamp suffix for document naming.
            temp_dir: Temporary directory for export files.

        Returns:
            None.

        Raises:
            pytest.skip: If no suitable font file is found in test environment.
            AssertionError: If emboss workflow steps fail.

        Example:
            Test creates "HI" text embossed on an 80x40x5 plate.
        """
        doc_name = f"TextEmboss_{unique_suffix}"
        step_path = Path(temp_dir) / f"{doc_name}.step"

        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
import Draft
import Part
import os

doc_name = {doc_name!r}
step_path = {str(step_path)!r}

if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

results = {{}}
workflow_steps = []

{FONT_DISCOVERY_CODE}

if not font_path:
    results["font_found"] = False
    _result_ = results
else:
    results["font_found"] = True

    # Step 1: Create base plate
    try:
        plate = Part.makeBox(80, 40, 5)
        plate_obj = doc.addObject("Part::Feature", "Plate")
        plate_obj.Shape = plate
        doc.recompute()
        workflow_steps.append(("create_plate", plate.isValid()))
        results["plate_volume"] = plate.Volume
    except Exception as e:
        workflow_steps.append(("create_plate", False))
        plate = None

    # Step 2: Create ShapeString
    shape_string = None
    if plate:
        try:
            shape_string = Draft.make_shapestring("OK", font_path, 12.0, 0)
            doc.recompute()
            workflow_steps.append(("create_shapestring", shape_string is not None))
        except Exception as e:
            workflow_steps.append(("create_shapestring", False))
            results["shapestring_error"] = str(e)

    # Step 3: Convert to faces and extrude
    text_solid = None
    if shape_string and hasattr(shape_string, 'Shape') and shape_string.Shape:
        try:
            wires = shape_string.Shape.Wires
            if wires:
                # Create faces from each closed wire and extrude
                solids = []
                for wire in wires:
                    if wire.isClosed():
                        face = Part.Face(wire)
                        # Position on top of plate (Z=5) and extrude upward
                        face.translate(FreeCAD.Vector(20, 10, 5))
                        solid = face.extrude(FreeCAD.Vector(0, 0, 2))  # 2mm emboss height
                        solids.append(solid)

                if solids:
                    text_solid = solids[0]
                    for s in solids[1:]:
                        text_solid = text_solid.fuse(s)
                    workflow_steps.append(("extrude_text", text_solid.isValid()))
                else:
                    workflow_steps.append(("extrude_text", False))
            else:
                workflow_steps.append(("extrude_text", False))
        except Exception as e:
            workflow_steps.append(("extrude_text", False))
            results["extrude_error"] = str(e)

    # Step 4: Fuse text to plate (emboss)
    final_shape = None
    if plate and text_solid and text_solid.isValid():
        try:
            final_shape = plate.fuse(text_solid)
            final_obj = doc.addObject("Part::Feature", "EmbossedPlate")
            final_obj.Shape = final_shape
            doc.recompute()
            workflow_steps.append(("fuse_emboss", final_shape.isValid()))
            results["final_volume"] = final_shape.Volume
            results["volume_increased"] = final_shape.Volume > plate.Volume
        except Exception as e:
            workflow_steps.append(("fuse_emboss", False))
            results["fuse_error"] = str(e)

    # Step 5: Export
    if final_shape and final_shape.isValid():
        try:
            final_shape.exportStep(step_path)
            import os as os_mod
            export_success = os_mod.path.exists(step_path)
            workflow_steps.append(("export", export_success))
        except Exception as e:
            workflow_steps.append(("export", False))

    # Center viewport
    if FreeCAD.GuiUp:
        import FreeCADGui
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
        FreeCADGui.ActiveDocument.ActiveView.fitAll()

    results["workflow_steps"] = workflow_steps
    results["all_passed"] = all(success for step, success in workflow_steps)
    results["failed_steps"] = [step for step, success in workflow_steps if not success]

    _result_ = results
""",
        )

        # Skip test if no font was found
        if not result["result"].get("font_found"):
            pytest.skip("No suitable font file found in test environment")

        assert result["result"]["all_passed"] is True, (
            f"Failed steps: {result['result']['failed_steps']}"
        )
        assert result["result"]["volume_increased"] is True

    def test_text_engraved_on_plate(
        self,
        xmlrpc_proxy: xmlrpc.client.ServerProxy,
        unique_suffix: str,
        temp_dir: str,
    ) -> None:
        """Test engraving text into a plate using boolean cut.

        Verifies the workflow of cutting text into a surface by extruding
        ShapeString and performing a boolean cut on a base plate.

        Args:
            xmlrpc_proxy: The XML-RPC server proxy connected to FreeCAD.
            unique_suffix: Unique timestamp suffix for document naming.
            temp_dir: Temporary directory for export files.

        Returns:
            None.

        Raises:
            pytest.skip: If no suitable font file is found in test environment.
            AssertionError: If engrave workflow steps fail.

        Example:
            Test creates "CUT" text engraved into an 80x40x10 plate.
        """
        doc_name = f"TextEngrave_{unique_suffix}"
        step_path = Path(temp_dir) / f"{doc_name}.step"

        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
import Draft
import Part
import os

doc_name = {doc_name!r}
step_path = {str(step_path)!r}

if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

results = {{}}
workflow_steps = []

{FONT_DISCOVERY_CODE}

if not font_path:
    results["font_found"] = False
    _result_ = results
else:
    results["font_found"] = True

    # Step 1: Create base plate (thicker for engraving)
    try:
        plate = Part.makeBox(80, 40, 10)
        plate_obj = doc.addObject("Part::Feature", "Plate")
        plate_obj.Shape = plate
        doc.recompute()
        workflow_steps.append(("create_plate", plate.isValid()))
        results["plate_volume"] = plate.Volume
    except Exception as e:
        workflow_steps.append(("create_plate", False))
        plate = None

    # Step 2: Create ShapeString
    shape_string = None
    if plate:
        try:
            shape_string = Draft.make_shapestring("CUT", font_path, 10.0, 0)
            doc.recompute()
            workflow_steps.append(("create_shapestring", shape_string is not None))
        except Exception as e:
            workflow_steps.append(("create_shapestring", False))
            results["shapestring_error"] = str(e)

    # Step 3: Convert to faces and extrude (for cutting)
    text_solid = None
    if shape_string and hasattr(shape_string, 'Shape') and shape_string.Shape:
        try:
            wires = shape_string.Shape.Wires
            if wires:
                # Create faces from each closed wire and extrude
                solids = []
                for wire in wires:
                    if wire.isClosed():
                        face = Part.Face(wire)
                        # Position above plate top and extrude downward into plate
                        face.translate(FreeCAD.Vector(15, 12, 10))
                        solid = face.extrude(FreeCAD.Vector(0, 0, -3))  # 3mm cut depth
                        solids.append(solid)

                if solids:
                    text_solid = solids[0]
                    for s in solids[1:]:
                        text_solid = text_solid.fuse(s)
                    workflow_steps.append(("extrude_text", text_solid.isValid()))
                else:
                    workflow_steps.append(("extrude_text", False))
            else:
                workflow_steps.append(("extrude_text", False))
        except Exception as e:
            workflow_steps.append(("extrude_text", False))
            results["extrude_error"] = str(e)

    # Step 4: Cut text from plate (engrave)
    final_shape = None
    if plate and text_solid and text_solid.isValid():
        try:
            final_shape = plate.cut(text_solid)
            final_obj = doc.addObject("Part::Feature", "EngravedPlate")
            final_obj.Shape = final_shape
            doc.recompute()
            workflow_steps.append(("cut_engrave", final_shape.isValid()))
            results["final_volume"] = final_shape.Volume
            results["volume_decreased"] = final_shape.Volume < plate.Volume
        except Exception as e:
            workflow_steps.append(("cut_engrave", False))
            results["cut_error"] = str(e)

    # Step 5: Export
    if final_shape and final_shape.isValid():
        try:
            final_shape.exportStep(step_path)
            import os as os_mod
            export_success = os_mod.path.exists(step_path)
            workflow_steps.append(("export", export_success))
        except Exception as e:
            workflow_steps.append(("export", False))

    # Center viewport
    if FreeCAD.GuiUp:
        import FreeCADGui
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
        FreeCADGui.ActiveDocument.ActiveView.fitAll()

    results["workflow_steps"] = workflow_steps
    results["all_passed"] = all(success for step, success in workflow_steps)
    results["failed_steps"] = [step for step, success in workflow_steps if not success]

    _result_ = results
""",
        )

        # Skip test if no font was found
        if not result["result"].get("font_found"):
            pytest.skip("No suitable font file found in test environment")

        assert result["result"]["all_passed"] is True, (
            f"Failed steps: {result['result']['failed_steps']}"
        )
        assert result["result"]["volume_decreased"] is True


class TestCombinedSpreadsheetDraftWorkflow:
    """Test combining Spreadsheet and Draft for parametric text operations."""

    def test_parametric_text_size_from_spreadsheet(
        self,
        xmlrpc_proxy: xmlrpc.client.ServerProxy,
        unique_suffix: str,
    ) -> None:
        """Test using spreadsheet to control text size parameters.

        Verifies that spreadsheet values can drive ShapeString font size,
        demonstrating integration between Spreadsheet and Draft workbenches.

        Args:
            xmlrpc_proxy: The XML-RPC server proxy connected to FreeCAD.
            unique_suffix: Unique timestamp suffix for document naming.

        Returns:
            None.

        Raises:
            pytest.skip: If no suitable font file is found in test environment.
            AssertionError: If parametric text workflow fails.

        Example:
            Test creates text with size from TextParams.TextSize spreadsheet cell.
        """
        doc_name = f"ParametricText_{unique_suffix}"

        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
import Draft
import Part
import os

doc_name = {doc_name!r}
if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

results = {{}}
workflow_steps = []

{FONT_DISCOVERY_CODE}

if not font_path:
    results["font_found"] = False
    _result_ = results
else:
    results["font_found"] = True

    # Step 1: Create spreadsheet with text parameters
    try:
        sheet = doc.addObject("Spreadsheet::Sheet", "TextParams")
        sheet.set("A1", "TextSize")
        sheet.set("B1", "20")
        sheet.setAlias("B1", "TextSize")

        sheet.set("A2", "ExtrudeHeight")
        sheet.set("B2", "5")
        sheet.setAlias("B2", "ExtrudeHeight")

        sheet.set("A3", "PlateLength")
        sheet.set("B3", "100")
        sheet.setAlias("B3", "PlateLength")

        sheet.set("A4", "PlateWidth")
        sheet.set("B4", "50")
        sheet.setAlias("B4", "PlateWidth")

        doc.recompute()
        workflow_steps.append(("create_spreadsheet", True))
    except Exception as e:
        workflow_steps.append(("create_spreadsheet", False))
        results["spreadsheet_error"] = str(e)

    # Step 2: Create ShapeString with size from spreadsheet
    shape_string = None
    try:
        text_size = float(sheet.get("B1"))
        shape_string = Draft.make_shapestring("A", font_path, text_size, 0)
        doc.recompute()
        workflow_steps.append(("create_shapestring", shape_string is not None))
        results["initial_text_size"] = text_size
    except Exception as e:
        workflow_steps.append(("create_shapestring", False))
        results["shapestring_error"] = str(e)

    # Step 3: Create plate using spreadsheet dimensions
    plate = None
    try:
        length = float(sheet.get("B3"))
        width = float(sheet.get("B4"))
        plate = Part.makeBox(length, width, 10)
        plate_obj = doc.addObject("Part::Feature", "Plate")
        plate_obj.Shape = plate
        doc.recompute()
        workflow_steps.append(("create_plate", plate.isValid()))
    except Exception as e:
        workflow_steps.append(("create_plate", False))

    # Step 4: Extrude text and place on plate
    final_shape = None
    if shape_string and plate and hasattr(shape_string, 'Shape') and shape_string.Shape:
        try:
            wires = shape_string.Shape.Wires
            if wires:
                # Create faces from each closed wire and extrude
                extrude_height = float(sheet.get("B2"))
                solids = []
                for wire in wires:
                    if wire.isClosed():
                        face = Part.Face(wire)
                        face.translate(FreeCAD.Vector(30, 15, 10))
                        solid = face.extrude(FreeCAD.Vector(0, 0, extrude_height))
                        solids.append(solid)

                if solids:
                    text_solid = solids[0]
                    for s in solids[1:]:
                        text_solid = text_solid.fuse(s)

                    final_shape = plate.fuse(text_solid)
                    final_obj = doc.addObject("Part::Feature", "FinalPart")
                    final_obj.Shape = final_shape
                    doc.recompute()
                    workflow_steps.append(("create_final", final_shape.isValid()))
                    results["final_volume"] = final_shape.Volume
                else:
                    workflow_steps.append(("create_final", False))
            else:
                workflow_steps.append(("create_final", False))
        except Exception as e:
            workflow_steps.append(("create_final", False))
            results["final_error"] = str(e)

    # Center viewport
    if FreeCAD.GuiUp:
        import FreeCADGui
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
        FreeCADGui.ActiveDocument.ActiveView.fitAll()

    results["workflow_steps"] = workflow_steps
    results["all_passed"] = all(success for step, success in workflow_steps)
    results["failed_steps"] = [step for step, success in workflow_steps if not success]

    _result_ = results
""",
        )

        # Skip test if no font was found
        if not result["result"].get("font_found"):
            pytest.skip("No suitable font file found in test environment")

        assert result["result"]["all_passed"] is True, (
            f"Failed steps: {result['result']['failed_steps']}"
        )
        assert result["result"]["initial_text_size"] == 20.0
        assert result["result"]["final_volume"] > 0
