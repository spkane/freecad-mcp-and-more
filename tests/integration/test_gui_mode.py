"""Integration tests for FreeCAD Robust MCP GUI mode.

These tests verify that the MCP bridge works correctly when FreeCAD is running
in GUI mode (with full graphical interface). They test GUI-specific features
like visibility, display modes, colors, and camera operations.

Note: These tests require a running FreeCAD GUI server.
      Start it with: just freecad::run-gui

To run these tests:
    pytest tests/integration/test_gui_mode.py -v
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from tests.integration.conftest import requires_gui

if TYPE_CHECKING:
    import xmlrpc.client
    from collections.abc import Generator

# Mark all tests in this module as integration tests, gui tests, and require GUI mode
pytestmark = [pytest.mark.integration, pytest.mark.gui, requires_gui]

# Note: xmlrpc_proxy fixture is defined in conftest.py


@pytest.fixture(scope="module")
def temp_dir() -> Generator[str, None, None]:
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def execute_code(proxy: xmlrpc.client.ServerProxy, code: str) -> dict[str, Any]:
    """Execute Python code via the MCP bridge and return the result."""
    result: dict[str, Any] = proxy.execute(code, 30000, None)  # type: ignore[assignment]
    assert result.get("success"), f"Execution failed: {result.get('error_traceback')}"
    return result


class TestGUIConnection:
    """Tests for GUI mode connectivity and detection."""

    def test_ping(self, xmlrpc_proxy: xmlrpc.client.ServerProxy) -> None:
        """Test that the server responds to ping."""
        result: dict[str, Any] = xmlrpc_proxy.ping()  # type: ignore[assignment]
        assert result["pong"] is True
        assert "timestamp" in result

    def test_gui_mode_detected(self, xmlrpc_proxy: xmlrpc.client.ServerProxy) -> None:
        """Test that FreeCAD is running in GUI mode (GuiUp=True)."""
        result = execute_code(
            xmlrpc_proxy,
            """
import FreeCAD
_result_ = {"gui_up": FreeCAD.GuiUp}
""",
        )
        # In GUI mode, GuiUp should be True (1)
        assert result["result"]["gui_up"] == 1 or result["result"]["gui_up"] is True


class TestGUIObjectCreation:
    """Tests for object creation in GUI mode."""

    @pytest.fixture(autouse=True)
    def setup_document(self, xmlrpc_proxy: xmlrpc.client.ServerProxy) -> None:
        """Create a fresh document for each test."""
        execute_code(
            xmlrpc_proxy,
            """
import FreeCAD
# Close any existing GUITestDoc
if "GUITestDoc" in FreeCAD.listDocuments():
    FreeCAD.closeDocument("GUITestDoc")
doc = FreeCAD.newDocument("GUITestDoc")
_result_ = True
""",
        )

    def test_create_box_with_view_object(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy
    ) -> None:
        """Test creating a box with ViewObject in GUI mode."""
        result = execute_code(
            xmlrpc_proxy,
            """
import FreeCAD
import Part

doc = FreeCAD.ActiveDocument
box = Part.makeBox(10, 20, 30)
obj = doc.addObject("Part::Feature", "GUIBox")
obj.Shape = box
doc.recompute()

has_view_object = hasattr(obj, "ViewObject") and obj.ViewObject is not None

_result_ = {
    "name": obj.Name,
    "volume": obj.Shape.Volume,
    "has_view_object": has_view_object,
    "valid": obj.Shape.isValid()
}
""",
        )
        assert result["result"]["name"] == "GUIBox"
        assert abs(result["result"]["volume"] - 6000.0) < 0.01
        assert result["result"]["has_view_object"] is True
        assert result["result"]["valid"] is True


class TestVisibility:
    """Tests for object visibility operations in GUI mode."""

    @pytest.fixture(autouse=True)
    def setup_document(self, xmlrpc_proxy: xmlrpc.client.ServerProxy) -> None:
        """Create a document with test objects."""
        execute_code(
            xmlrpc_proxy,
            """
import FreeCAD
import Part

if "VisibilityTestDoc" in FreeCAD.listDocuments():
    FreeCAD.closeDocument("VisibilityTestDoc")
doc = FreeCAD.newDocument("VisibilityTestDoc")

box = Part.makeBox(10, 10, 10)
obj = doc.addObject("Part::Feature", "VisBox")
obj.Shape = box
doc.recompute()
_result_ = True
""",
        )

    def test_hide_object(self, xmlrpc_proxy: xmlrpc.client.ServerProxy) -> None:
        """Test hiding an object."""
        result = execute_code(
            xmlrpc_proxy,
            """
import FreeCAD

doc = FreeCAD.ActiveDocument
obj = doc.getObject("VisBox")

# Hide the object
obj.ViewObject.Visibility = False

_result_ = {
    "visible": obj.ViewObject.Visibility
}
""",
        )
        assert result["result"]["visible"] is False

    def test_show_object(self, xmlrpc_proxy: xmlrpc.client.ServerProxy) -> None:
        """Test showing an object."""
        result = execute_code(
            xmlrpc_proxy,
            """
import FreeCAD

doc = FreeCAD.ActiveDocument
obj = doc.getObject("VisBox")

# First hide, then show
obj.ViewObject.Visibility = False
obj.ViewObject.Visibility = True

_result_ = {
    "visible": obj.ViewObject.Visibility
}
""",
        )
        assert result["result"]["visible"] is True


class TestDisplayMode:
    """Tests for display mode operations in GUI mode."""

    @pytest.fixture(autouse=True)
    def setup_document(self, xmlrpc_proxy: xmlrpc.client.ServerProxy) -> None:
        """Create a document with test objects."""
        execute_code(
            xmlrpc_proxy,
            """
import FreeCAD
import Part

if "DisplayModeTestDoc" in FreeCAD.listDocuments():
    FreeCAD.closeDocument("DisplayModeTestDoc")
doc = FreeCAD.newDocument("DisplayModeTestDoc")

box = Part.makeBox(10, 10, 10)
obj = doc.addObject("Part::Feature", "DisplayBox")
obj.Shape = box
doc.recompute()
_result_ = True
""",
        )

    def test_get_display_modes(self, xmlrpc_proxy: xmlrpc.client.ServerProxy) -> None:
        """Test getting available display modes."""
        result = execute_code(
            xmlrpc_proxy,
            """
import FreeCAD

doc = FreeCAD.ActiveDocument
obj = doc.getObject("DisplayBox")

modes = obj.ViewObject.listDisplayModes()

_result_ = {
    "modes": list(modes),
    "current": obj.ViewObject.DisplayMode
}
""",
        )
        # Typical modes: "Flat Lines", "Shaded", "Wireframe", etc.
        assert len(result["result"]["modes"]) > 0
        assert result["result"]["current"] is not None

    def test_set_display_mode(self, xmlrpc_proxy: xmlrpc.client.ServerProxy) -> None:
        """Test setting display mode."""
        result = execute_code(
            xmlrpc_proxy,
            """
import FreeCAD

doc = FreeCAD.ActiveDocument
obj = doc.getObject("DisplayBox")

modes = obj.ViewObject.listDisplayModes()
# Set to a different mode if available
target_mode = "Wireframe" if "Wireframe" in modes else modes[0]
obj.ViewObject.DisplayMode = target_mode

_result_ = {
    "mode_set": obj.ViewObject.DisplayMode,
    "target_mode": target_mode
}
""",
        )
        assert result["result"]["mode_set"] == result["result"]["target_mode"]


class TestObjectColor:
    """Tests for object color operations in GUI mode."""

    @pytest.fixture(autouse=True)
    def setup_document(self, xmlrpc_proxy: xmlrpc.client.ServerProxy) -> None:
        """Create a document with test objects."""
        execute_code(
            xmlrpc_proxy,
            """
import FreeCAD
import Part

if "ColorTestDoc" in FreeCAD.listDocuments():
    FreeCAD.closeDocument("ColorTestDoc")
doc = FreeCAD.newDocument("ColorTestDoc")

box = Part.makeBox(10, 10, 10)
obj = doc.addObject("Part::Feature", "ColorBox")
obj.Shape = box
doc.recompute()
_result_ = True
""",
        )

    def test_set_shape_color(self, xmlrpc_proxy: xmlrpc.client.ServerProxy) -> None:
        """Test setting object shape color."""
        result = execute_code(
            xmlrpc_proxy,
            """
import FreeCAD

doc = FreeCAD.ActiveDocument
obj = doc.getObject("ColorBox")

# Set color to red (RGB as tuple of floats 0-1)
obj.ViewObject.ShapeColor = (1.0, 0.0, 0.0)

color = obj.ViewObject.ShapeColor

_result_ = {
    "r": color[0],
    "g": color[1],
    "b": color[2]
}
""",
        )
        assert result["result"]["r"] == pytest.approx(1.0, rel=0.01)
        assert result["result"]["g"] == pytest.approx(0.0, abs=0.01)
        assert result["result"]["b"] == pytest.approx(0.0, abs=0.01)

    def test_set_transparency(self, xmlrpc_proxy: xmlrpc.client.ServerProxy) -> None:
        """Test setting object transparency."""
        result = execute_code(
            xmlrpc_proxy,
            """
import FreeCAD

doc = FreeCAD.ActiveDocument
obj = doc.getObject("ColorBox")

# Set 50% transparency
obj.ViewObject.Transparency = 50

_result_ = {
    "transparency": obj.ViewObject.Transparency
}
""",
        )
        assert result["result"]["transparency"] == 50


class TestCameraOperations:
    """Tests for camera/view operations in GUI mode."""

    @pytest.fixture(autouse=True)
    def setup_document(self, xmlrpc_proxy: xmlrpc.client.ServerProxy) -> None:
        """Create a document with test objects."""
        execute_code(
            xmlrpc_proxy,
            """
import FreeCAD
import Part

if "CameraTestDoc" in FreeCAD.listDocuments():
    FreeCAD.closeDocument("CameraTestDoc")
doc = FreeCAD.newDocument("CameraTestDoc")

box = Part.makeBox(10, 10, 10)
obj = doc.addObject("Part::Feature", "CameraBox")
obj.Shape = box
doc.recompute()
_result_ = True
""",
        )

    def test_fit_all(self, xmlrpc_proxy: xmlrpc.client.ServerProxy) -> None:
        """Test fit all view operation."""
        result = execute_code(
            xmlrpc_proxy,
            """
import FreeCAD
import FreeCADGui

doc = FreeCAD.ActiveDocument
view = FreeCADGui.ActiveDocument.ActiveView

# Fit all objects in view
view.fitAll()

_result_ = {"success": True}
""",
        )
        assert result["result"]["success"] is True

    def test_set_view_direction(self, xmlrpc_proxy: xmlrpc.client.ServerProxy) -> None:
        """Test setting view direction (front, top, etc.)."""
        result = execute_code(
            xmlrpc_proxy,
            """
import FreeCAD
import FreeCADGui

doc = FreeCAD.ActiveDocument
view = FreeCADGui.ActiveDocument.ActiveView

# Set to front view
view.viewFront()

# Get camera orientation
cam = view.getCameraOrientation()

_result_ = {
    "success": True,
    "camera_orientation": [cam.Q[0], cam.Q[1], cam.Q[2], cam.Q[3]]
}
""",
        )
        assert result["result"]["success"] is True


class TestScreenshot:
    """Tests for screenshot functionality in GUI mode."""

    def test_capture_screenshot(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy, temp_dir: str
    ) -> None:
        """Test capturing a screenshot."""
        # First create a document with objects
        execute_code(
            xmlrpc_proxy,
            """
import FreeCAD
import Part

if "ScreenshotTestDoc" in FreeCAD.listDocuments():
    FreeCAD.closeDocument("ScreenshotTestDoc")
doc = FreeCAD.newDocument("ScreenshotTestDoc")

box = Part.makeBox(20, 20, 20)
obj = doc.addObject("Part::Feature", "ScreenshotBox")
obj.Shape = box
obj.ViewObject.ShapeColor = (0.0, 0.5, 1.0)  # Blue color
doc.recompute()
_result_ = True
""",
        )

        screenshot_path = Path(temp_dir) / "test_screenshot.png"
        screenshot_path_str = str(screenshot_path)

        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
import FreeCADGui
import os

doc = FreeCAD.ActiveDocument
view = FreeCADGui.ActiveDocument.ActiveView

# Fit objects in view
view.fitAll()

# Save screenshot
view.saveImage({screenshot_path_str!r}, 800, 600, "White")

_result_ = {{
    "saved": os.path.exists({screenshot_path_str!r}),
    "path": {screenshot_path_str!r}
}}
""",
        )
        assert result["result"]["saved"] is True
        assert screenshot_path.exists()
        # Verify file has content
        assert screenshot_path.stat().st_size > 0


class TestComplexGUIWorkflow:
    """Tests for complex workflows that combine GUI and modeling features."""

    def test_create_assembly_with_colors(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy
    ) -> None:
        """Test creating multiple objects with different colors."""
        result = execute_code(
            xmlrpc_proxy,
            """
import FreeCAD
import Part

if "AssemblyTestDoc" in FreeCAD.listDocuments():
    FreeCAD.closeDocument("AssemblyTestDoc")
doc = FreeCAD.newDocument("AssemblyTestDoc")

# Create base plate (gray)
base = Part.makeBox(100, 100, 5)
base_obj = doc.addObject("Part::Feature", "BasePlate")
base_obj.Shape = base
base_obj.ViewObject.ShapeColor = (0.5, 0.5, 0.5)

# Create pillar 1 (red)
pillar1 = Part.makeBox(10, 10, 50, FreeCAD.Vector(10, 10, 5))
pillar1_obj = doc.addObject("Part::Feature", "Pillar1")
pillar1_obj.Shape = pillar1
pillar1_obj.ViewObject.ShapeColor = (1.0, 0.0, 0.0)

# Create pillar 2 (green)
pillar2 = Part.makeBox(10, 10, 50, FreeCAD.Vector(80, 10, 5))
pillar2_obj = doc.addObject("Part::Feature", "Pillar2")
pillar2_obj.Shape = pillar2
pillar2_obj.ViewObject.ShapeColor = (0.0, 1.0, 0.0)

# Create pillar 3 (blue)
pillar3 = Part.makeBox(10, 10, 50, FreeCAD.Vector(80, 80, 5))
pillar3_obj = doc.addObject("Part::Feature", "Pillar3")
pillar3_obj.Shape = pillar3
pillar3_obj.ViewObject.ShapeColor = (0.0, 0.0, 1.0)

# Create pillar 4 (yellow)
pillar4 = Part.makeBox(10, 10, 50, FreeCAD.Vector(10, 80, 5))
pillar4_obj = doc.addObject("Part::Feature", "Pillar4")
pillar4_obj.Shape = pillar4
pillar4_obj.ViewObject.ShapeColor = (1.0, 1.0, 0.0)

# Create top plate (semi-transparent gray)
top = Part.makeBox(100, 100, 5, FreeCAD.Vector(0, 0, 55))
top_obj = doc.addObject("Part::Feature", "TopPlate")
top_obj.Shape = top
top_obj.ViewObject.ShapeColor = (0.5, 0.5, 0.5)
top_obj.ViewObject.Transparency = 30

doc.recompute()

_result_ = {
    "object_count": len(doc.Objects),
    "objects": [obj.Name for obj in doc.Objects],
    "all_visible": all(obj.ViewObject.Visibility for obj in doc.Objects)
}
""",
        )
        assert result["result"]["object_count"] == 6
        assert "BasePlate" in result["result"]["objects"]
        assert "TopPlate" in result["result"]["objects"]
        assert result["result"]["all_visible"] is True

    def test_export_with_screenshot(
        self, xmlrpc_proxy: xmlrpc.client.ServerProxy, temp_dir: str
    ) -> None:
        """Test creating model, setting view, taking screenshot, and exporting."""
        step_path = Path(temp_dir) / "workflow_export.step"
        screenshot_path = Path(temp_dir) / "workflow_screenshot.png"
        step_path_str = str(step_path)
        screenshot_path_str = str(screenshot_path)

        result = execute_code(
            xmlrpc_proxy,
            f"""
import FreeCAD
import FreeCADGui
import Part
import os

if "WorkflowTestDoc" in FreeCAD.listDocuments():
    FreeCAD.closeDocument("WorkflowTestDoc")
doc = FreeCAD.newDocument("WorkflowTestDoc")

# Create a simple bracket shape
# Base
base = Part.makeBox(50, 30, 5)
# Vertical support
vertical = Part.makeBox(5, 30, 40, FreeCAD.Vector(0, 0, 5))
# Top flange with hole
top_flange = Part.makeBox(20, 30, 5, FreeCAD.Vector(0, 0, 45))
hole = Part.makeCylinder(4, 10, FreeCAD.Vector(10, 15, 40))

# Combine and cut
bracket = base.fuse(vertical).fuse(top_flange).cut(hole)
bracket_obj = doc.addObject("Part::Feature", "Bracket")
bracket_obj.Shape = bracket
bracket_obj.ViewObject.ShapeColor = (0.2, 0.4, 0.8)

doc.recompute()

# Set isometric view
view = FreeCADGui.ActiveDocument.ActiveView
view.viewIsometric()
view.fitAll()

# Take screenshot
view.saveImage({screenshot_path_str!r}, 800, 600, "White")

# Export to STEP
bracket_obj.Shape.exportStep({step_path_str!r})

_result_ = {{
    "bracket_valid": bracket_obj.Shape.isValid(),
    "bracket_volume": bracket_obj.Shape.Volume,
    "screenshot_exists": os.path.exists({screenshot_path_str!r}),
    "step_exists": os.path.exists({step_path_str!r})
}}
""",
        )
        assert result["result"]["bracket_valid"] is True
        assert result["result"]["bracket_volume"] > 0
        assert result["result"]["screenshot_exists"] is True
        assert result["result"]["step_exists"] is True
        assert screenshot_path.exists()
        assert step_path.exists()
