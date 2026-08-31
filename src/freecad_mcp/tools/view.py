"""View and screenshot tools for FreeCAD Robust MCP Server.

This module provides tools for controlling the 3D view and
capturing screenshots. Based on learnings from neka-nat which
has excellent screenshot handling with view type detection.
"""

import base64
import binascii
import itertools
import json
import os
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from mcp.types import CallToolResult, ImageContent, TextContent

_SCREENSHOT_SEQUENCE = itertools.count(1)
"""Per-process counter keeping successive captures from overwriting each other."""


def _screenshot_directory() -> Path:
    """Resolve where retained screenshot evidence is written."""
    configured = os.environ.get("FREECAD_MCP_SCREENSHOT_DIR")
    if configured:
        return Path(configured)
    return Path.cwd() / "screenshots"


def _safe_path_component(value: str) -> str:
    """Reduce a document or view name to a filesystem-safe component."""
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return cleaned or "unnamed"


def _persist_screenshot(
    payload: bytes,
    doc_name: str | None,
    view_angle: str,
    sequence: int,
) -> str | None:
    """Write one capture into the run directory, or None if it cannot be kept.

    Persistence is best-effort: an unwritable directory must never cost the
    model the image it just asked for.
    """
    directory = _screenshot_directory()
    document = _safe_path_component(doc_name or "active")
    view = _safe_path_component(view_angle)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{sequence:03d}_{document}_{view}.png"
        target.write_bytes(payload)
    except OSError:
        return None
    return str(target)


def _screenshot_error(
    message: str, view_angle: str, doc_name: str | None
) -> CallToolResult:
    """Report a failed capture as an explicit tool error."""
    return CallToolResult(
        isError=True,
        content=[
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "success": False,
                        "error": message,
                        "view_angle": view_angle,
                        "document": doc_name,
                    },
                    indent=2,
                ),
            )
        ],
    )


def register_view_tools(mcp: Any, get_bridge: Callable[[], Awaitable[Any]]) -> None:
    """Register view-related tools with the Robust MCP Server.

    Args:
        mcp: The FastMCP (Robust MCP Server) instance.
        get_bridge: Async function to get the active bridge.
    """

    @mcp.tool()
    async def get_screenshot(
        view_angle: str = "Isometric",
        width: int = 800,
        height: int = 600,
        doc_name: str | None = None,
    ) -> CallToolResult:
        """Capture a screenshot of the FreeCAD 3D view and return it as an image.

        The image is returned as a viewable image content block and is also
        written to disk as retained run evidence. Use this to visually check
        that a feature you just created has the silhouette you intended.

        Requires GUI mode - will return an error in headless mode.

        Args:
            view_angle: View angle to set before capture. Options:
                - "Isometric" - 3D isometric view (default)
                - "Front" - Front view (XZ plane)
                - "Back" - Back view
                - "Top" - Top view (XY plane)
                - "Bottom" - Bottom view
                - "Left" - Left view (YZ plane)
                - "Right" - Right view
                - "FitAll" - Fit all objects in view
            width: Image width in pixels. Defaults to 800.
            height: Image height in pixels. Defaults to 600.
            doc_name: Document to capture. Uses active document if None.

        Returns:
            A PNG image content block the model can look at, plus a text block
            of JSON metadata: format, width, height, view_angle, document, and
            path (the retained PNG, or null when it could not be written).
        """
        from freecad_mcp.bridge.base import ViewAngle

        # Map string to ViewAngle enum
        angle_map = {
            "Isometric": ViewAngle.ISOMETRIC,
            "Front": ViewAngle.FRONT,
            "Back": ViewAngle.BACK,
            "Top": ViewAngle.TOP,
            "Bottom": ViewAngle.BOTTOM,
            "Left": ViewAngle.LEFT,
            "Right": ViewAngle.RIGHT,
            "FitAll": ViewAngle.FIT_ALL,
        }

        if view_angle not in angle_map:
            return _screenshot_error(
                f"Invalid view_angle: {view_angle}. Options: {list(angle_map.keys())}",
                view_angle,
                doc_name,
            )

        bridge = await get_bridge()
        result = await bridge.get_screenshot(
            view_angle=angle_map[view_angle],
            width=width,
            height=height,
            doc_name=doc_name,
        )

        if not result.success or not result.data:
            return _screenshot_error(
                result.error or "Screenshot capture failed",
                view_angle,
                doc_name,
            )

        try:
            payload = base64.b64decode(result.data, validate=True)
        except (binascii.Error, ValueError):
            return _screenshot_error(
                "Screenshot capture returned malformed image data",
                view_angle,
                doc_name,
            )

        path = _persist_screenshot(
            payload, doc_name, view_angle, next(_SCREENSHOT_SEQUENCE)
        )
        metadata = {
            "success": True,
            "format": result.format or "png",
            "width": result.width,
            "height": result.height,
            "view_angle": view_angle,
            "document": doc_name,
            "path": path,
        }
        return CallToolResult(
            content=[
                TextContent(type="text", text=json.dumps(metadata, indent=2)),
                ImageContent(type="image", data=result.data, mimeType="image/png"),
            ]
        )

    @mcp.tool()
    async def set_view_angle(
        view_angle: str,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Set the 3D view angle.

        Args:
            view_angle: View angle to set. Options:
                - "Isometric" - 3D isometric view
                - "Front" - Front view (XZ plane)
                - "Back" - Back view
                - "Top" - Top view (XY plane)
                - "Bottom" - Bottom view
                - "Left" - Left view (YZ plane)
                - "Right" - Right view
                - "FitAll" - Fit all objects in view
            doc_name: Document to set view for. Uses active document if None.

        Returns:
            Dictionary with result:
                - success: Whether operation was successful
        """
        from freecad_mcp.bridge.base import ViewAngle

        angle_map = {
            "Isometric": ViewAngle.ISOMETRIC,
            "Front": ViewAngle.FRONT,
            "Back": ViewAngle.BACK,
            "Top": ViewAngle.TOP,
            "Bottom": ViewAngle.BOTTOM,
            "Left": ViewAngle.LEFT,
            "Right": ViewAngle.RIGHT,
            "FitAll": ViewAngle.FIT_ALL,
        }

        if view_angle not in angle_map:
            return {
                "success": False,
                "error": f"Invalid view_angle: {view_angle}. Options: {list(angle_map.keys())}",
            }

        bridge = await get_bridge()
        await bridge.set_view(angle_map[view_angle], doc_name)
        return {"success": True}

    @mcp.tool()
    async def list_workbenches() -> list[dict[str, Any]]:
        """List all available FreeCAD workbenches.

        Returns:
            List of dictionaries, each containing:
                - name: Workbench internal name
                - label: Display label
                - is_active: Whether workbench is currently active
        """
        bridge = await get_bridge()
        workbenches = await bridge.get_workbenches()
        return [
            {
                "name": wb.name,
                "label": wb.label,
                "is_active": wb.is_active,
            }
            for wb in workbenches
        ]

    @mcp.tool()
    async def activate_workbench(workbench_name: str) -> dict[str, Any]:
        """Activate a FreeCAD workbench.

        Args:
            workbench_name: Internal name of the workbench to activate.
                Common workbenches:
                - "PartWorkbench" - Part modeling
                - "PartDesignWorkbench" - Parametric part design
                - "SketcherWorkbench" - 2D sketching
                - "DraftWorkbench" - 2D drafting
                - "MeshWorkbench" - Mesh operations
                - "SpreadsheetWorkbench" - Spreadsheet

        Returns:
            Dictionary with result:
                - success: Whether activation was successful
        """
        bridge = await get_bridge()
        await bridge.activate_workbench(workbench_name)
        return {"success": True}

    @mcp.tool()
    async def fit_all(doc_name: str | None = None) -> dict[str, Any]:
        """Fit all objects in the current view.

        Adjusts the camera to show all visible objects in the document.

        Args:
            doc_name: Document to fit view for. Uses active document if None.

        Returns:
            Dictionary with result:
                - success: Whether operation was successful
        """
        from freecad_mcp.bridge.base import ViewAngle

        bridge = await get_bridge()
        await bridge.set_view(ViewAngle.FIT_ALL, doc_name)
        return {"success": True}

    @mcp.tool()
    async def set_object_visibility(
        object_name: str,
        visible: bool,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Set the visibility of a FreeCAD object.

        Args:
            object_name: Name of the object.
            visible: Whether object should be visible.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with result:
                - success: Whether operation was successful
                - visible: New visibility state
        """
        bridge = await get_bridge()

        code = f"""
if not FreeCAD.GuiUp:
    _result_ = {{"success": False, "error": "GUI not available - visibility cannot be set in headless mode"}}
else:
    doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
    if doc is None:
        _result_ = {{"success": False, "error": "No document found"}}
    else:
        obj = doc.getObject({object_name!r})
        if obj is None:
            _result_ = {{"success": False, "error": f"Object not found: {object_name!r}"}}
        elif hasattr(obj, "ViewObject") and obj.ViewObject:
            obj.ViewObject.Visibility = {visible}
            _result_ = {{"success": True, "visible": {visible}}}
        else:
            _result_ = {{"success": False, "error": "Object has no ViewObject"}}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        return {
            "success": False,
            "error": result.error_traceback or "Set visibility failed",
        }

    @mcp.tool()
    async def set_display_mode(
        object_name: str,
        mode: str,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Set the display mode of a FreeCAD object.

        Args:
            object_name: Name of the object.
            mode: Display mode. Common options:
                - "Flat Lines" - Solid with edges
                - "Shaded" - Solid without edges
                - "Wireframe" - Wire frame only
                - "Points" - Points only
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with result:
                - success: Whether operation was successful
                - mode: New display mode
        """
        bridge = await get_bridge()

        code = f"""
if not FreeCAD.GuiUp:
    _result_ = {{"success": False, "error": "GUI not available - display mode cannot be set in headless mode"}}
else:
    doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
    if doc is None:
        _result_ = {{"success": False, "error": "No document found"}}
    else:
        obj = doc.getObject({object_name!r})
        if obj is None:
            _result_ = {{"success": False, "error": f"Object not found: {object_name!r}"}}
        elif hasattr(obj, "ViewObject") and obj.ViewObject:
            obj.ViewObject.DisplayMode = {mode!r}
            _result_ = {{"success": True, "mode": {mode!r}}}
        else:
            _result_ = {{"success": False, "error": "Object has no ViewObject"}}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        return {
            "success": False,
            "error": result.error_traceback or "Set display mode failed",
        }

    @mcp.tool()
    async def set_object_color(
        object_name: str,
        color: list[float],
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Set the color of a FreeCAD object.

        Args:
            object_name: Name of the object.
            color: RGB color as [r, g, b] where each value is 0.0-1.0.
                   Example: [1.0, 0.0, 0.0] for red.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with result:
                - success: Whether operation was successful
                - color: New color values
        """
        bridge = await get_bridge()

        if len(color) != 3:
            return {
                "success": False,
                "error": "Color must be [r, g, b] with values 0.0-1.0",
            }

        code = f"""
if not FreeCAD.GuiUp:
    _result_ = {{"success": False, "error": "GUI not available - color cannot be set in headless mode"}}
else:
    doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
    if doc is None:
        _result_ = {{"success": False, "error": "No document found"}}
    else:
        obj = doc.getObject({object_name!r})
        if obj is None:
            _result_ = {{"success": False, "error": f"Object not found: {object_name!r}"}}
        elif hasattr(obj, "ViewObject") and obj.ViewObject:
            obj.ViewObject.ShapeColor = ({color[0]}, {color[1]}, {color[2]})
            _result_ = {{"success": True, "color": {color}}}
        else:
            _result_ = {{"success": False, "error": "Object has no ViewObject"}}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        return {
            "success": False,
            "error": result.error_traceback or "Set color failed",
        }

    @mcp.tool()
    async def zoom_in(
        factor: float = 1.5, doc_name: str | None = None
    ) -> dict[str, Any]:
        """Zoom in the 3D view.

        Requires GUI mode.

        Args:
            factor: Zoom factor (>1 zooms in). Defaults to 1.5.
            doc_name: Document to zoom in. Uses active document if None.

        Returns:
            Dictionary with result:
                - success: Whether operation was successful
        """
        bridge = await get_bridge()

        code = f"""
if not FreeCAD.GuiUp:
    _result_ = {{"success": False, "error": "GUI not available - zoom requires GUI mode"}}
else:
    doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
    if doc is None:
        _result_ = {{"success": False, "error": "No document found"}}
    elif FreeCADGui.ActiveDocument is None or FreeCADGui.ActiveDocument.ActiveView is None:
        _result_ = {{"success": False, "error": "No active view"}}
    else:
        view = FreeCADGui.ActiveDocument.ActiveView
        cam = view.getCameraNode()
        if hasattr(cam, "scaleHeight"):
            # For orthographic views
            cam.scaleHeight(1.0 / {factor})
        else:
            # For perspective views - move camera closer
            view.zoomIn()
        _result_ = {{"success": True}}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        return {
            "success": False,
            "error": result.error_traceback or "Zoom in failed",
        }

    @mcp.tool()
    async def zoom_out(
        factor: float = 1.5, doc_name: str | None = None
    ) -> dict[str, Any]:
        """Zoom out the 3D view.

        Requires GUI mode.

        Args:
            factor: Zoom factor (>1 zooms out). Defaults to 1.5.
            doc_name: Document to zoom out. Uses active document if None.

        Returns:
            Dictionary with result:
                - success: Whether operation was successful
        """
        bridge = await get_bridge()

        code = f"""
if not FreeCAD.GuiUp:
    _result_ = {{"success": False, "error": "GUI not available - zoom requires GUI mode"}}
else:
    doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
    if doc is None:
        _result_ = {{"success": False, "error": "No document found"}}
    elif FreeCADGui.ActiveDocument is None or FreeCADGui.ActiveDocument.ActiveView is None:
        _result_ = {{"success": False, "error": "No active view"}}
    else:
        view = FreeCADGui.ActiveDocument.ActiveView
        cam = view.getCameraNode()
        if hasattr(cam, "scaleHeight"):
            # For orthographic views
            cam.scaleHeight({factor})
        else:
            # For perspective views - move camera farther
            view.zoomOut()
        _result_ = {{"success": True}}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        return {
            "success": False,
            "error": result.error_traceback or "Zoom out failed",
        }

    @mcp.tool()
    async def set_camera_position(
        position: list[float],
        look_at: list[float] | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Set the camera position and orientation.

        Requires GUI mode.

        Args:
            position: Camera position as [x, y, z].
            look_at: Point to look at as [x, y, z]. Uses origin if None.
            doc_name: Document to set camera for. Uses active document if None.

        Returns:
            Dictionary with result:
                - success: Whether operation was successful
        """
        bridge = await get_bridge()

        look_str = (
            f"FreeCAD.Vector({look_at[0]}, {look_at[1]}, {look_at[2]})"
            if look_at
            else "FreeCAD.Vector(0, 0, 0)"
        )

        code = f"""
if not FreeCAD.GuiUp:
    _result_ = {{"success": False, "error": "GUI not available - camera position requires GUI mode"}}
else:
    doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
    if doc is None:
        _result_ = {{"success": False, "error": "No document found"}}
    elif FreeCADGui.ActiveDocument is None or FreeCADGui.ActiveDocument.ActiveView is None:
        _result_ = {{"success": False, "error": "No active view"}}
    else:
        view = FreeCADGui.ActiveDocument.ActiveView
        pos = FreeCAD.Vector({position[0]}, {position[1]}, {position[2]})
        look_at = {look_str}

        # Calculate direction
        direction = look_at - pos
        direction.normalize()

        # Set camera
        view.setCameraOrientation(FreeCAD.Rotation(FreeCAD.Vector(0, 0, -1), direction))
        cam = view.getCameraNode()
        cam.position.setValue(pos.x, pos.y, pos.z)

        _result_ = {{"success": True}}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        return {
            "success": False,
            "error": result.error_traceback or "Set camera position failed",
        }

    @mcp.tool()
    async def undo(doc_name: str | None = None) -> dict[str, Any]:
        """Undo the last operation.

        Args:
            doc_name: Document to undo in. Uses active document if None.

        Returns:
            Dictionary with result:
                - success: Whether undo was performed
                - can_undo: Whether more undos are available
        """
        bridge = await get_bridge()

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    _result_ = {{"success": False, "can_undo": False, "error": "No document found"}}
elif doc.UndoCount > 0:
    doc.undo()
    _result_ = {{"success": True, "can_undo": doc.UndoCount > 0}}
else:
    _result_ = {{"success": False, "can_undo": False, "error": "Nothing to undo"}}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        return {
            "success": False,
            "can_undo": False,
            "error": result.error_traceback or "Undo failed",
        }

    @mcp.tool()
    async def redo(doc_name: str | None = None) -> dict[str, Any]:
        """Redo the last undone operation.

        Args:
            doc_name: Document to redo in. Uses active document if None.

        Returns:
            Dictionary with result:
                - success: Whether redo was performed
                - can_redo: Whether more redos are available
        """
        bridge = await get_bridge()

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    _result_ = {{"success": False, "can_redo": False, "error": "No document found"}}
elif doc.RedoCount > 0:
    doc.redo()
    _result_ = {{"success": True, "can_redo": doc.RedoCount > 0}}
else:
    _result_ = {{"success": False, "can_redo": False, "error": "Nothing to redo"}}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        return {
            "success": False,
            "can_redo": False,
            "error": result.error_traceback or "Redo failed",
        }

    @mcp.tool()
    async def get_undo_redo_status(doc_name: str | None = None) -> dict[str, Any]:
        """Get the current undo/redo status.

        Args:
            doc_name: Document to check. Uses active document if None.

        Returns:
            Dictionary with status:
                - undo_count: Number of undoable operations
                - redo_count: Number of redoable operations
                - undo_names: List of undo operation names (if available)
        """
        bridge = await get_bridge()

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    _result_ = {{"error": "No document found", "undo_count": 0, "redo_count": 0, "undo_names": []}}
else:
    _result_ = {{
        "undo_count": doc.UndoCount,
        "redo_count": doc.RedoCount,
        "undo_names": list(doc.UndoNames) if hasattr(doc, "UndoNames") else [],
    }}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        return {
            "error": result.error_traceback or "Get undo/redo status failed",
            "undo_count": 0,
            "redo_count": 0,
            "undo_names": [],
        }

    @mcp.tool()
    async def list_parts_library() -> list[dict[str, Any]]:
        """List available parts from the FreeCAD parts library.

        Returns:
            List of parts with:
                - name: Part filename
                - path: Full path to part file
                - category: Part category/folder
        """
        bridge = await get_bridge()

        code = """
import os

parts = []

# Get parts library paths
try:
    # Standard library path
    lib_path = FreeCAD.getResourceDir() + "Mod/Parts_Library"
    if not os.path.exists(lib_path):
        lib_path = os.path.expanduser("~/.FreeCAD/Mod/PartsLibrary")

    if os.path.exists(lib_path):
        for root, dirs, files in os.walk(lib_path):
            category = os.path.relpath(root, lib_path)
            if category == ".":
                category = "Root"

            for f in files:
                if f.endswith((".FCStd", ".step", ".stp", ".iges", ".igs")):
                    parts.append({
                        "name": f,
                        "path": os.path.join(root, f),
                        "category": category,
                    })
except Exception as e:
    pass

_result_ = parts
"""
        result = await bridge.execute_python(code)
        if result.success:
            return result.result
        return []

    @mcp.tool()
    async def insert_part_from_library(
        part_path: str,
        name: str | None = None,
        position: list[float] | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Insert a part from the parts library into the document.

        Args:
            part_path: Path to the part file.
            name: Name for the inserted part. Auto-generated if None.
            position: Initial position [x, y, z]. Origin if None.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with inserted part information:
                - name: Part name
                - label: Part label
                - type_id: Part type
        """
        bridge = await get_bridge()

        pos_str = (
            f"FreeCAD.Vector({position[0]}, {position[1]}, {position[2]})"
            if position
            else "FreeCAD.Vector(0, 0, 0)"
        )

        code = f"""
import os
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    doc = FreeCAD.newDocument("Unnamed")

part_path = {part_path!r}
if not os.path.exists(part_path):
    raise FileNotFoundError(f"Part file not found: {{part_path}}")

ext = os.path.splitext(part_path)[1].lower()
part_name = {name!r} or os.path.splitext(os.path.basename(part_path))[0]

# Wrap in transaction for undo support
doc.openTransaction("Insert Part from Library")
try:
    new_obj = None
    if ext == ".fcstd":
        # Import FreeCAD document
        src_doc = FreeCAD.openDocument(part_path)
        for obj in src_doc.Objects:
            if hasattr(obj, "Shape"):
                new_obj = doc.addObject("Part::Feature", part_name)
                new_obj.Shape = obj.Shape.copy()
                break
        FreeCAD.closeDocument(src_doc.Name)
    else:
        # Import STEP/IGES
        shape = Part.read(part_path)
        new_obj = doc.addObject("Part::Feature", part_name)
        new_obj.Shape = shape

    if new_obj is None:
        raise ValueError(f"No importable shape found in {{part_path}}")

    # Set position
    new_obj.Placement.Base = {pos_str}

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": new_obj.Name,
        "label": new_obj.Label,
        "type_id": new_obj.TypeId,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        return {
            "success": False,
            "error": result.error_traceback or "Insert part from library failed",
        }

    @mcp.tool()
    async def get_console_log(lines: int = 50) -> dict[str, Any]:
        """Get recent console output from FreeCAD.

        Args:
            lines: Maximum number of lines to return. Defaults to 50.

        Returns:
            Dictionary with:
                - messages: List of console messages
                - warnings: List of warning messages
                - errors: List of error messages
        """
        bridge = await get_bridge()
        console_lines = await bridge.get_console_output(lines)

        return {
            "messages": console_lines,
            "warnings": [line for line in console_lines if "warning" in line.lower()],
            "errors": [line for line in console_lines if "error" in line.lower()],
        }

    @mcp.tool()
    async def recompute(doc_name: str | None = None) -> dict[str, Any]:
        """Force recompute of all objects in a document.

        Args:
            doc_name: Document to recompute. Uses active document if None.

        Returns:
            Dictionary with result:
                - success: Whether recompute completed
                - touch_count: Number of objects that were recomputed
        """
        bridge = await get_bridge()

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    _result_ = {{"success": False, "error": "No document found", "touch_count": 0}}
else:
    # Touch all objects to force recompute
    touch_count = 0
    for obj in doc.Objects:
        if hasattr(obj, "touch"):
            obj.touch()
            touch_count += 1

    doc.recompute()

    _result_ = {{"success": True, "touch_count": touch_count}}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        return {
            "success": False,
            "error": result.error_traceback or "Recompute failed",
            "touch_count": 0,
        }
