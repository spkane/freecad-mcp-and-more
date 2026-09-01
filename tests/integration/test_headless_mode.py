"""Integration tests for FreeCAD Robust MCP Bridge functionality.

These tests verify that the MCP bridge works correctly with FreeCAD, including
object creation, manipulation, and export functionality. Most tests work in
both GUI and headless modes, with specific tests marked as headless-only.

Note: These tests require a running FreeCAD server.
      Start with: just freecad::run-gui (GUI mode)
              or: just freecad::run-headless (headless mode)

To run these tests:
    pytest tests/integration/test_headless_mode.py -v
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from tests.integration.conftest import requires_headless

if TYPE_CHECKING:
    import xmlrpc.client
    from collections.abc import Generator

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration

# Note: xmlrpc_proxy fixture is defined in conftest.py


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
    """Generate a unique suffix for document names in this test session.

    Uses timestamp format YYYYMMDDHHMMSS to ensure unique names across runs.
    """
    return _unique_suffix()


def execute_code(proxy: xmlrpc.client.ServerProxy, code: str) -> dict[str, Any]:
    """Execute Python code via the MCP bridge and return the result."""
    result: dict[str, Any] = proxy.execute(code, 30000, None)  # type: ignore[assignment]
    assert result.get("success"), f"Execution failed: {result.get('error_traceback')}"
    return result


# Common code snippet for centering viewport in GUI mode
CENTER_VIEWPORT_CODE = """
# Center viewport for GUI mode recording
if FreeCAD.GuiUp:
    import FreeCADGui
    if FreeCADGui.ActiveDocument and FreeCADGui.ActiveDocument.ActiveView:
        FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
        FreeCADGui.ActiveDocument.ActiveView.fitAll()
"""


def center_viewport(proxy: xmlrpc.client.ServerProxy) -> None:
    """Center all objects in the viewport if GUI is available.

    Call this after creating/modifying objects to keep them centered.
    Safe to call in headless mode - it will simply do nothing.
    """
    proxy.execute(  # type: ignore[union-attr]
        f"""
import FreeCAD
{CENTER_VIEWPORT_CODE}
_result_ = True
""",
        30000,
        None,
    )


class TestHeadlessConnection:
    """Tests for basic headless mode connectivity."""

    def test_ping(self, xmlrpc_proxy: xmlrpc.client.ServerProxy) -> None:
        """Test that the server responds to ping."""
        result: dict[str, Any] = xmlrpc_proxy.ping()  # type: ignore[assignment]
        assert result["pong"] is True
        assert "timestamp" in result

    @requires_headless
    def test_headless_mode_detected(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy
    ) -> None:
        """Test that FreeCAD is running in headless mode (GuiUp=False).

        This test is skipped when FreeCAD is running in GUI mode.
        """
        result = execute_code(
            xmlrpc_proxy,
            """
import FreeCAD
_result_ = {"gui_up": FreeCAD.GuiUp}
""",
        )
        # In headless mode, GuiUp should be False (0)
        assert result["result"]["gui_up"] == 0 or result["result"]["gui_up"] is False


class TestDocumentManagement:
    """Tests for document creation and management in headless mode."""

    def test_create_document(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy, unique_suffix: str
    ) -> None:
        """Test creating a new document."""
        doc_name = f"TestDoc_{unique_suffix}"
        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
doc_name = {doc_name!r}
# Close if it already exists (from a previous failed run)
if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)
_result_ = {{"name": doc.Name, "object_count": len(doc.Objects)}}
""",
        )
        assert result["result"]["name"] == doc_name
        assert result["result"]["object_count"] == 0

    def test_list_documents(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy, unique_suffix: str
    ) -> None:
        """Test listing open documents."""
        doc_name = f"ListTestDoc_{unique_suffix}"
        # First create a document
        execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
doc_name = {doc_name!r}
if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
FreeCAD.newDocument(doc_name)
_result_ = True
""",
        )

        result = execute_code(
            xmlrpc_proxy,
            """
import FreeCAD
docs = list(FreeCAD.listDocuments().keys())
_result_ = {"documents": docs, "count": len(docs)}
""",
        )
        assert result["result"]["count"] >= 1

    def test_close_document(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy, unique_suffix: str
    ) -> None:
        """Test closing a document."""
        doc_name = f"ToClose_{unique_suffix}"
        # Create a document to close
        execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
doc_name = {doc_name!r}
if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)
_result_ = True
""",
        )

        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
doc_name = {doc_name!r}
FreeCAD.closeDocument(doc_name)
_result_ = {{"closed": doc_name not in FreeCAD.listDocuments()}}
""",
        )
        assert result["result"]["closed"] is True


class TestPrimitiveCreation:
    """Tests for creating primitive shapes."""

    @pytest.fixture(autouse=True)
    def setup_document(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy, unique_suffix: str
    ) -> None:
        """Create a fresh document for each test."""
        doc_name = f"PrimitiveTestDoc_{unique_suffix}"
        execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
doc_name = {doc_name!r}
# Close any existing document with this name
if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

# Set up initial view for GUI mode
if FreeCAD.GuiUp:
    import FreeCADGui
    FreeCADGui.ActiveDocument.ActiveView.viewIsometric()

_result_ = True
""",
        )

    def test_create_box(self, xmlrpc_proxy: xmlrpc.client.ServerProxy) -> None:
        """Test creating a Part::Box primitive."""
        result = execute_code(
            xmlrpc_proxy,
            """
import FreeCAD
import Part

doc = FreeCAD.ActiveDocument
box = Part.makeBox(10, 20, 30)
obj = doc.addObject("Part::Feature", "TestBox")
obj.Shape = box

# Center viewport immediately after adding object (before it renders off-center)
if FreeCAD.GuiUp:
    import FreeCADGui
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

doc.recompute()

# Final viewport adjustment
if FreeCAD.GuiUp:
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

_result_ = {
    "name": obj.Name,
    "volume": obj.Shape.Volume,
    "valid": obj.Shape.isValid()
}
""",
        )
        assert result["result"]["name"] == "TestBox"
        # Volume should be 10 * 20 * 30 = 6000
        assert abs(result["result"]["volume"] - 6000.0) < 0.01
        assert result["result"]["valid"] is True

    def test_create_cylinder(self, xmlrpc_proxy: xmlrpc.client.ServerProxy) -> None:
        """Test creating a Part::Cylinder primitive."""
        result = execute_code(
            xmlrpc_proxy,
            """
import FreeCAD
import Part
import math

doc = FreeCAD.ActiveDocument
cylinder = Part.makeCylinder(5, 20)
obj = doc.addObject("Part::Feature", "TestCylinder")
obj.Shape = cylinder

# Center viewport immediately after adding object
if FreeCAD.GuiUp:
    import FreeCADGui
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

doc.recompute()

# Final viewport adjustment
if FreeCAD.GuiUp:
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

expected_volume = math.pi * 5**2 * 20

_result_ = {
    "name": obj.Name,
    "volume": obj.Shape.Volume,
    "expected_volume": expected_volume,
    "valid": obj.Shape.isValid()
}
""",
        )
        assert result["result"]["name"] == "TestCylinder"
        # Volume should be π * r² * h = π * 25 * 20 ≈ 1570.8
        assert (
            abs(result["result"]["volume"] - result["result"]["expected_volume"]) < 0.1
        )
        assert result["result"]["valid"] is True

    def test_create_sphere(self, xmlrpc_proxy: xmlrpc.client.ServerProxy) -> None:
        """Test creating a Part::Sphere primitive."""
        result = execute_code(
            xmlrpc_proxy,
            """
import FreeCAD
import Part
import math

doc = FreeCAD.ActiveDocument
sphere = Part.makeSphere(10)
obj = doc.addObject("Part::Feature", "TestSphere")
obj.Shape = sphere

# Center viewport immediately after adding object
if FreeCAD.GuiUp:
    import FreeCADGui
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

doc.recompute()

# Final viewport adjustment
if FreeCAD.GuiUp:
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

expected_volume = (4/3) * math.pi * 10**3

_result_ = {
    "name": obj.Name,
    "volume": obj.Shape.Volume,
    "expected_volume": expected_volume,
    "valid": obj.Shape.isValid()
}
""",
        )
        assert result["result"]["name"] == "TestSphere"
        # Volume should be (4/3) * π * r³ ≈ 4188.79
        assert (
            abs(result["result"]["volume"] - result["result"]["expected_volume"]) < 1.0
        )
        assert result["result"]["valid"] is True

    def test_create_cone(self, xmlrpc_proxy: xmlrpc.client.ServerProxy) -> None:
        """Test creating a Part::Cone primitive."""
        result = execute_code(
            xmlrpc_proxy,
            """
import FreeCAD
import Part

doc = FreeCAD.ActiveDocument
cone = Part.makeCone(10, 0, 20)  # Base radius=10, top radius=0, height=20
obj = doc.addObject("Part::Feature", "TestCone")
obj.Shape = cone

# Center viewport immediately after adding object
if FreeCAD.GuiUp:
    import FreeCADGui
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

doc.recompute()

# Final viewport adjustment
if FreeCAD.GuiUp:
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

_result_ = {
    "name": obj.Name,
    "volume": obj.Shape.Volume,
    "valid": obj.Shape.isValid()
}
""",
        )
        assert result["result"]["name"] == "TestCone"
        # Volume of a cone = (1/3) * π * r² * h ≈ 2094.4
        assert result["result"]["volume"] > 2000
        assert result["result"]["valid"] is True

    def test_create_torus(self, xmlrpc_proxy: xmlrpc.client.ServerProxy) -> None:
        """Test creating a Part::Torus primitive."""
        result = execute_code(
            xmlrpc_proxy,
            """
import FreeCAD
import Part

doc = FreeCAD.ActiveDocument
torus = Part.makeTorus(20, 5)  # Major radius=20, minor radius=5
obj = doc.addObject("Part::Feature", "TestTorus")
obj.Shape = torus

# Center viewport immediately after adding object
if FreeCAD.GuiUp:
    import FreeCADGui
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

doc.recompute()

# Final viewport adjustment
if FreeCAD.GuiUp:
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

_result_ = {
    "name": obj.Name,
    "volume": obj.Shape.Volume,
    "valid": obj.Shape.isValid()
}
""",
        )
        assert result["result"]["name"] == "TestTorus"
        assert result["result"]["volume"] > 0
        assert result["result"]["valid"] is True


class TestBooleanOperations:
    """Tests for boolean operations."""

    @pytest.fixture(autouse=True)
    def setup_document(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy, unique_suffix: str
    ) -> None:
        """Create a fresh document for each test."""
        doc_name = f"BooleanTestDoc_{unique_suffix}"
        execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
doc_name = {doc_name!r}
if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

# Set up initial view for GUI mode
if FreeCAD.GuiUp:
    import FreeCADGui
    FreeCADGui.ActiveDocument.ActiveView.viewIsometric()

_result_ = True
""",
        )

    def test_boolean_fuse(self, xmlrpc_proxy: xmlrpc.client.ServerProxy) -> None:
        """Test boolean fuse (union) operation."""
        result = execute_code(
            xmlrpc_proxy,
            """
import FreeCAD
import Part

doc = FreeCAD.ActiveDocument

# Create two overlapping boxes
box1 = Part.makeBox(10, 10, 10)
box2 = Part.makeBox(10, 10, 10, FreeCAD.Vector(5, 0, 0))

obj1 = doc.addObject("Part::Feature", "Box1")
obj1.Shape = box1
obj2 = doc.addObject("Part::Feature", "Box2")
obj2.Shape = box2

# Center viewport after adding initial objects
if FreeCAD.GuiUp:
    import FreeCADGui
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

# Fuse them
fused = box1.fuse(box2)
obj_fused = doc.addObject("Part::Feature", "Fused")
obj_fused.Shape = fused
doc.recompute()

# Final viewport adjustment
if FreeCAD.GuiUp:
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

# Fused volume should be less than 2000 (two boxes) due to overlap
_result_ = {
    "fused_volume": obj_fused.Shape.Volume,
    "valid": obj_fused.Shape.isValid()
}
""",
        )
        # Two 10x10x10 boxes overlapping by 5mm = 2000 - 500 = 1500
        assert result["result"]["fused_volume"] == pytest.approx(1500.0, rel=0.01)
        assert result["result"]["valid"] is True

    def test_boolean_cut(self, xmlrpc_proxy: xmlrpc.client.ServerProxy) -> None:
        """Test boolean cut (subtract) operation."""
        result = execute_code(
            xmlrpc_proxy,
            """
import FreeCAD
import Part

doc = FreeCAD.ActiveDocument

# Create a box and a cylinder to cut from it
box = Part.makeBox(20, 20, 20)
cylinder = Part.makeCylinder(5, 30, FreeCAD.Vector(10, 10, -5))

# Cut cylinder from box
cut = box.cut(cylinder)
obj_cut = doc.addObject("Part::Feature", "Cut")
obj_cut.Shape = cut

# Center viewport immediately after adding object
if FreeCAD.GuiUp:
    import FreeCADGui
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

doc.recompute()

# Final viewport adjustment
if FreeCAD.GuiUp:
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

box_volume = 20 * 20 * 20
import math
cylinder_volume_in_box = math.pi * 5**2 * 20  # Only 20mm of cylinder is in box

_result_ = {
    "cut_volume": obj_cut.Shape.Volume,
    "expected_volume": box_volume - cylinder_volume_in_box,
    "valid": obj_cut.Shape.isValid()
}
""",
        )
        # Volume should be box - cylinder intersection
        assert (
            abs(result["result"]["cut_volume"] - result["result"]["expected_volume"])
            < 10
        )
        assert result["result"]["valid"] is True


class TestObjectManipulation:
    """Tests for object manipulation."""

    @pytest.fixture(autouse=True)
    def setup_document(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy, unique_suffix: str
    ) -> None:
        """Create a fresh document with a test box."""
        doc_name = f"ManipTestDoc_{unique_suffix}"
        execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
import Part

doc_name = {doc_name!r}
if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

box = Part.makeBox(10, 10, 10)
obj = doc.addObject("Part::Feature", "ManipBox")
obj.Shape = box
doc.recompute()

# Center viewport for GUI mode recording
if FreeCAD.GuiUp:
    import FreeCADGui
    FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

_result_ = True
""",
        )

    def test_set_placement_position(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy
    ) -> None:
        """Test setting object position."""
        result = execute_code(
            xmlrpc_proxy,
            """
import FreeCAD

doc = FreeCAD.ActiveDocument
obj = doc.getObject("ManipBox")

# Move the object
obj.Placement.Base = FreeCAD.Vector(100, 200, 300)

# Center viewport for GUI mode recording
if FreeCAD.GuiUp:
    import FreeCADGui
    FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

_result_ = {
    "x": obj.Placement.Base.x,
    "y": obj.Placement.Base.y,
    "z": obj.Placement.Base.z
}
""",
        )
        assert result["result"]["x"] == 100.0
        assert result["result"]["y"] == 200.0
        assert result["result"]["z"] == 300.0

    def test_set_placement_rotation(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy
    ) -> None:
        """Test setting object rotation."""
        result = execute_code(
            xmlrpc_proxy,
            """
import FreeCAD

doc = FreeCAD.ActiveDocument
obj = doc.getObject("ManipBox")

# Rotate the object 45 degrees around Z axis
obj.Placement.Rotation = FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 45)
doc.recompute()

# Center viewport for GUI mode recording
if FreeCAD.GuiUp:
    import FreeCADGui
    FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

euler = obj.Placement.Rotation.toEuler()
_result_ = {
    "rotation_z": euler[0],  # Yaw
    "valid": obj.Shape.isValid()
}
""",
        )
        # Check rotation is approximately 45 degrees
        assert abs(result["result"]["rotation_z"] - 45.0) < 0.1
        assert result["result"]["valid"] is True


class TestExportOperations:
    """Tests for export functionality."""

    @pytest.fixture(autouse=True)
    def setup_document(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy, temp_dir: str, unique_suffix: str
    ) -> None:
        """Create a document with objects for export tests."""
        doc_name = f"ExportTestDoc_{unique_suffix}"
        execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
import Part

doc_name = {doc_name!r}
if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

# Create a simple box
box = Part.makeBox(10, 10, 10)
obj = doc.addObject("Part::Feature", "ExportBox")
obj.Shape = box
doc.recompute()

# Center viewport for GUI mode recording
if FreeCAD.GuiUp:
    import FreeCADGui
    FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

_result_ = True
""",
        )
        self.temp_dir = temp_dir

    def test_export_step(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy, temp_dir: str
    ) -> None:
        """Test exporting to STEP format."""
        step_path = Path(temp_dir) / "test_export.step"
        step_path_str = str(step_path)

        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD

doc = FreeCAD.ActiveDocument
obj = doc.getObject("ExportBox")
obj.Shape.exportStep({step_path_str!r})

import os
_result_ = {{"exported": os.path.exists({step_path_str!r})}}
""",
        )
        assert result["result"]["exported"] is True
        assert step_path.exists()

    def test_save_fcstd(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy, temp_dir: str
    ) -> None:
        """Test saving as FreeCAD native format."""
        fcstd_path = Path(temp_dir) / "test_save.FCStd"
        fcstd_path_str = str(fcstd_path)

        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD

doc = FreeCAD.ActiveDocument
doc.saveAs({fcstd_path_str!r})

import os
_result_ = {{
    "saved": os.path.exists({fcstd_path_str!r}),
    "path": {fcstd_path_str!r}
}}
""",
        )
        assert result["result"]["saved"] is True
        assert fcstd_path.exists()


@requires_headless
class TestGUIFeaturesInHeadless:
    """Tests to verify GUI features fail gracefully in headless mode.

    These tests are skipped when FreeCAD is running in GUI mode.
    """

    def test_gui_features_not_available(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy
    ) -> None:
        """Test that GUI-only features return appropriate errors."""
        result = execute_code(
            xmlrpc_proxy,
            """
import FreeCAD

gui_available = FreeCAD.GuiUp

if not gui_available:
    _result_ = {
        "success": False,
        "error": "GUI not available in headless mode",
        "gui_up": False
    }
else:
    _result_ = {
        "success": True,
        "gui_up": True
    }
""",
        )
        # In headless mode, GUI should not be available
        assert result["result"]["gui_up"] is False


class TestComplexWorkflow:
    """Tests for complex multi-step workflows."""

    def test_parametric_modeling_workflow(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy, unique_suffix: str
    ) -> None:
        """Test a complete parametric modeling workflow."""
        doc_name = f"WorkflowTestDoc_{unique_suffix}"
        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
import Part

# Create document
doc_name = {doc_name!r}
if doc_name in FreeCAD.listDocuments():
    FreeCAD.closeDocument(doc_name)
doc = FreeCAD.newDocument(doc_name)

# Step 1: Create base box
base_box = Part.makeBox(50, 50, 10)
base_obj = doc.addObject("Part::Feature", "Base")
base_obj.Shape = base_box

# Step 2: Create cylinder to cut
cylinder = Part.makeCylinder(5, 20, FreeCAD.Vector(25, 25, -5))

# Step 3: Cut hole in base
result_shape = base_box.cut(cylinder)
final_obj = doc.addObject("Part::Feature", "BaseWithHole")
final_obj.Shape = result_shape

# Step 4: Add fillet (rounded edges) - using Part API
# Select edges and apply fillet
try:
    filleted = final_obj.Shape.makeFillet(2, final_obj.Shape.Edges[:4])
    fillet_obj = doc.addObject("Part::Feature", "Filleted")
    fillet_obj.Shape = filleted
    fillet_success = True
except Exception:
    fillet_success = False

# Center viewport immediately after adding objects (before recompute)
if FreeCAD.GuiUp:
    import FreeCADGui
    FreeCADGui.ActiveDocument.ActiveView.viewIsometric()
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

doc.recompute()

# Final viewport adjustment after recompute
if FreeCAD.GuiUp:
    FreeCADGui.ActiveDocument.ActiveView.fitAll()

_result_ = {{
    "objects": [obj.Name for obj in doc.Objects],
    "final_volume": final_obj.Shape.Volume,
    "final_valid": final_obj.Shape.isValid(),
    "fillet_success": fillet_success
}}
""",
        )
        assert "Base" in result["result"]["objects"]
        assert "BaseWithHole" in result["result"]["objects"]
        assert result["result"]["final_valid"] is True
        # Volume should be base - cylinder hole
        assert result["result"]["final_volume"] > 0
