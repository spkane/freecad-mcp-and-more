"""View and screenshot tools for FreeCAD Robust MCP Server.

This module provides tools for controlling the 3D view and
capturing screenshots. Based on learnings from neka-nat which
has excellent screenshot handling with view type detection.
"""

import base64
import binascii
import hashlib
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


def _feature_view_error(
    message: str,
    normal_source: str,
    side: str,
    doc_name: str | None,
) -> CallToolResult:
    """Report a failed support-normal capture as an explicit tool error.

    A feature view has no `view_angle`: the camera direction is derived from
    a placement, not chosen from the eight fixed angles. Reporting the
    `normal_source` under a `view_angle` key told the model something untrue
    about what it had asked for, so this path has its own shape.

    Args:
        message: The failure to report.
        normal_source: The object whose placement the capture asked for.
        side: The requested side, `"front"` or `"back"`.
        doc_name: The requested document, or None for the active one.

    Returns:
        A `CallToolResult` marked as an error, carrying the failure as JSON.
    """
    return CallToolResult(
        isError=True,
        content=[
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "success": False,
                        "error": message,
                        "normal_source": normal_source,
                        "side": side,
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
    async def capture_feature_view(
        normal_source: str,
        side: str = "front",
        focus: list[str] | None = None,
        padding: float = 0.1,
        hide_construction: bool = True,
        width: int = 800,
        height: int = 600,
        doc_name: str | None = None,
    ) -> CallToolResult:
        """Capture the model looking along a named support's own normal.

        A feature seen edge-on is not evidence about its shape. Use this for
        every semantic opening or profile: pass the sketch, datum, or feature
        that supports it as normal_source.

        Requires GUI mode - will return an error in headless mode.

        Args:
            normal_source: Name of the sketch, datum, or feature whose support
                placement defines the view normal.
            side: "front" looks against the normal; "back" looks along it.
            focus: Object names to frame. Frames the whole model if None.
            padding: Fractional padding around the framed objects.
            hide_construction: Hide datums, origins, and construction helpers
                for the capture, then restore them.
            width: Image width in pixels.
            height: Image height in pixels.
            doc_name: Document to capture. Uses the active document if None.

        Returns:
            A PNG image content block plus a JSON metadata block carrying the
            sign-resolved camera_direction, the normal_source and side, the
            resolved placement, the focus names, the hidden_objects that were
            hidden and restored, the padding, the retained path, and the
            image's sha256.
        """
        if side not in ("front", "back"):
            return _feature_view_error(
                f"Invalid side: {side}. Options: ['front', 'back']",
                normal_source,
                side,
                doc_name,
            )

        bridge = await get_bridge()
        result = await bridge.capture_feature_view(
            normal_source=normal_source,
            side=side,
            focus=focus,
            padding=padding,
            hide_construction=hide_construction,
            width=width,
            height=height,
            doc_name=doc_name,
        )

        if not result.success or not result.data:
            return _feature_view_error(
                result.error or "Feature view capture failed",
                normal_source,
                side,
                doc_name,
            )

        try:
            payload = base64.b64decode(result.data, validate=True)
        except (binascii.Error, ValueError):
            return _feature_view_error(
                "Feature view capture returned malformed image data",
                normal_source,
                side,
                doc_name,
            )

        path = _persist_screenshot(
            payload, doc_name, f"{normal_source}_{side}", next(_SCREENSHOT_SEQUENCE)
        )
        # The bridge resolves the camera server-side, so these fields are the
        # only record of which of +/-normal was actually looked along and
        # which of the operator's objects were hidden to get the shot. A
        # model asked to state its visual comparison explicitly cannot do so
        # without them, so they are reported, not recomputed.
        metadata = {
            "success": True,
            "format": result.format or "png",
            "width": result.width,
            "height": result.height,
            "normal_source": getattr(result, "normal_source", None) or normal_source,
            "side": getattr(result, "side", None) or side,
            "camera_direction": getattr(result, "camera_direction", None),
            "placement": getattr(result, "placement", None),
            "focus": getattr(result, "focus", None) if focus else None,
            "hidden_objects": list(getattr(result, "hidden_objects", None) or []),
            "padding": (
                result.padding
                if getattr(result, "padding", None) is not None
                else padding
            ),
            "document": doc_name,
            "path": path,
            "image_sha256": hashlib.sha256(payload).hexdigest(),
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
        result = await bridge.execute_python(code, transaction=None)
        if result.success and result.result:
            return result.result
        return {
            "success": False,
            "error": result.error_traceback or "Set visibility failed",
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
        result = await bridge.execute_python(code, transaction=None)
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
        result = await bridge.execute_python(code, transaction=None)
        if result.success and result.result:
            return result.result
        return {
            "success": False,
            "can_redo": False,
            "error": result.error_traceback or "Redo failed",
        }
