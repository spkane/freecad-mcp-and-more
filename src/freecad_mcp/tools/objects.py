"""Object management tools for FreeCAD Robust MCP Server.

This module provides tools for managing FreeCAD objects:
creating, editing, deleting, and inspecting objects.
"""

import base64
import binascii
import hashlib
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from freecad_mcp.tools.utils import WORKFLOW_HELPERS
from freecad_mcp.tools.workflow_results import (
    ObjectQueryResult,
    WorkflowToolError,
    bridge_workflow_error,
)


def _query_signature(
    query: str | None,
    names: list[str],
    type_ids: list[str],
    visible_only: bool,
    detail: str,
) -> str:
    """Identify the normalized filters that a page cursor belongs to."""
    source = repr(
        (
            query,
            tuple(sorted(set(names))),
            tuple(sorted(set(type_ids))),
            visible_only,
            detail,
        )
    )
    return hashlib.sha256(source.encode()).hexdigest()[:24]


def _decode_query_cursor(cursor: str, signature: str) -> tuple[str, int]:
    """Decode and validate an opaque revision-bound query cursor."""
    try:
        padding = "=" * (-len(cursor) % 4)
        decoded = base64.b64decode(
            (cursor + padding).encode("ascii"), altchars=b"-_", validate=True
        )
        canonical_cursor = base64.urlsafe_b64encode(decoded).decode().rstrip("=")
        payload = decoded.decode()
        revision, cursor_signature, offset_text = payload.split(":", 2)
        offset = int(offset_text)
    except (binascii.Error, UnicodeDecodeError, UnicodeEncodeError, ValueError) as exc:
        msg = "Cursor is invalid"
        raise WorkflowToolError("INVALID_INPUT", msg) from exc
    if (
        cursor != canonical_cursor
        or not revision.startswith("rev_")
        or cursor_signature != signature
        or offset < 0
        or str(offset) != offset_text
    ):
        msg = "Cursor is invalid or belongs to a different query"
        raise WorkflowToolError("INVALID_INPUT", msg)
    return revision, offset


def register_object_tools(mcp: Any, get_bridge: Callable[[], Awaitable[Any]]) -> None:
    """Register object-related tools with the Robust MCP Server.

    Args:
        mcp: The FastMCP (Robust MCP Server) instance.
        get_bridge: Async function to get the active bridge.
    """

    @mcp.tool()
    async def list_objects(doc_name: str | None = None) -> list[dict[str, Any]]:
        """List all objects in a FreeCAD document.

        Args:
            doc_name: Name of document. Uses active document if None.

        Returns:
            List of dictionaries, each containing:
                - name: Object name
                - label: Display label
                - type_id: FreeCAD type identifier (e.g., "Part::Box")
                - visibility: Whether object is visible
        """
        bridge = await get_bridge()
        objects = await bridge.get_objects(doc_name)
        return [
            {
                "name": obj.name,
                "label": obj.label,
                "type_id": obj.type_id,
                "visibility": obj.visibility,
            }
            for obj in objects
        ]

    @mcp.tool()
    async def query_objects(
        query: str | None = None,
        names: list[str] | None = None,
        type_ids: list[str] | None = None,
        visible_only: bool = False,
        detail: Literal["summary", "standard", "detailed"] = "summary",
        limit: int = 25,
        cursor: str | None = None,
        expected_revision: str | None = None,
        doc_name: str | None = None,
    ) -> ObjectQueryResult:
        """Find a bounded page of objects without retrieving the whole document.

        Filters are combined. ``query`` performs a case-insensitive substring
        match on internal name, label, or type ID. ``names`` and ``type_ids``
        are exact-match filters. Use ``detailed`` only for a small result set.

        Args:
            query: Optional substring to find in name, label, or type ID.
            names: Optional exact internal names.
            type_ids: Optional exact FreeCAD type IDs.
            visible_only: Return only visible objects.
            detail: Summary, relationship, or property-and-shape detail.
            limit: Maximum page size from 1 through 100.
            cursor: Opaque cursor returned by a prior identical query.
            expected_revision: Optional revision that the document must still match.
            doc_name: Document to query. Uses the active document when omitted.

        Returns:
            A document revision, bounded items, counts, and continuation cursor.
        """
        if detail not in {"summary", "standard", "detailed"}:
            msg = "Detail must be summary, standard, or detailed"
            raise WorkflowToolError("INVALID_INPUT", msg)
        if limit < 1 or limit > 100:
            msg = "Limit must be between 1 and 100"
            raise WorkflowToolError("INVALID_INPUT", msg)
        query_text = query.strip().lower() if query is not None else None
        if query_text == "":
            query_text = None
        exact_names = names or []
        exact_type_ids = type_ids or []
        for name in exact_names:
            if not name:
                msg = "Object names must not be empty"
                raise WorkflowToolError("INVALID_INPUT", msg)
        for type_id in exact_type_ids:
            if not type_id:
                msg = "Type IDs must not be empty"
                raise WorkflowToolError("INVALID_INPUT", msg)
        if expected_revision is not None and not expected_revision.strip():
            msg = "Expected revision must not be empty"
            raise WorkflowToolError("INVALID_INPUT", msg)

        signature = _query_signature(
            query_text,
            exact_names,
            exact_type_ids,
            visible_only,
            detail,
        )
        cursor_revision = None
        offset = 0
        if cursor is not None:
            cursor_revision, offset = _decode_query_cursor(cursor, signature)

        bridge = await get_bridge()
        code = f"""
import base64

{WORKFLOW_HELPERS}

def encode_cursor(revision, signature, offset):
    payload = "%s:%s:%d" % (revision, signature, offset)
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")

def serialize_value(value):
    if value is None or isinstance(value, (bool, float)):
        return value
    if isinstance(value, int):
        if -(2 ** 31) <= value < 2 ** 31:
            return value
        return str(value)
    if isinstance(value, str):
        return value[:500]
    if hasattr(value, "Value") and isinstance(value.Value, (int, float)):
        return {{"value": float(value.Value), "display": str(value)}}
    if isinstance(value, (list, tuple)):
        return [serialize_value(item) for item in value[:50]]
    return str(value)[:500]

requested_doc_name = {doc_name!r}
doc = (
    FreeCAD.ActiveDocument
    if requested_doc_name is None
    else FreeCAD.getDocument(requested_doc_name)
)
if doc is None:
    raise ValueError("NOT_FOUND: No active document")

expected_revision = {expected_revision!r}
current_revision = require_expected_revision(doc, expected_revision)
cursor_revision = {cursor_revision!r}
if cursor_revision is not None and cursor_revision != current_revision:
    raise RuntimeError(
        "STALE_REVISION: Query cursor belongs to revision %s, found %s"
        % (cursor_revision, current_revision)
    )

query = {query_text!r}
names = set({exact_names!r})
type_ids = set({exact_type_ids!r})
visible_only = {visible_only!r}
detail = {detail!r}
limit = {limit!r}
offset = {offset!r}
query_signature = {signature!r}

matched = []
for obj in doc.Objects:
    visible = bool(getattr(getattr(obj, "ViewObject", None), "Visibility", False))
    haystack = f"{{obj.Name}}\\n{{obj.Label}}\\n{{obj.TypeId}}".lower()
    if query is not None and query not in haystack:
        continue
    if names and obj.Name not in names:
        continue
    if type_ids and obj.TypeId not in type_ids:
        continue
    if visible_only and not visible:
        continue
    matched.append(obj)

matched.sort(key=lambda item: item.Name)
page = matched[offset:offset + limit]
items = []
for obj in page:
    item = {{
        "name": obj.Name,
        "label": obj.Label,
        "type_id": obj.TypeId,
        "visibility": bool(
            getattr(getattr(obj, "ViewObject", None), "Visibility", False)
        ),
        "state": list(getattr(obj, "State", [])),
    }}
    if detail in ("standard", "detailed"):
        item["children"] = [child.Name for child in getattr(obj, "OutList", [])]
        item["parents"] = [parent.Name for parent in getattr(obj, "InList", [])]
    if detail == "detailed":
        item["properties"] = {{
            property_name: serialize_value(getattr(obj, property_name))
            for property_name in getattr(obj, "PropertiesList", [])
            if property_name not in {{"Shape", "Proxy"}}
        }}
        shape = getattr(obj, "Shape", None)
        if shape is not None and not shape.isNull():
            bounds = shape.BoundBox
            item["shape"] = {{
                "valid": bool(shape.isValid()),
                "solid_count": len(shape.Solids),
                "volume": float(shape.Volume),
                "bounds": {{
                    "x": float(bounds.XLength),
                    "y": float(bounds.YLength),
                    "z": float(bounds.ZLength),
                }},
            }}
        else:
            item["shape"] = {{
                "valid": False,
                "solid_count": 0,
                "volume": 0.0,
                "bounds": None,
            }}
    items.append(item)

next_offset = offset + len(page)
_result_ = {{
    "document_ref": {{
        "name": doc.Name,
        "revision": current_revision,
    }},
    "items": items,
    "matched_count": len(matched),
    "returned_count": len(items),
    "next_cursor": (
        encode_cursor(current_revision, query_signature, next_offset)
        if next_offset < len(matched)
        else None
    ),
    "truncated": next_offset < len(matched),
}}
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise bridge_workflow_error(result.error_traceback, "Query objects failed")

    @mcp.tool()
    async def inspect_object(
        object_name: str,
        doc_name: str | None = None,
        include_properties: bool = True,
        include_shape: bool = True,
    ) -> dict[str, Any]:
        """Get detailed information about a FreeCAD object.

        Args:
            object_name: Name of the object to inspect.
            doc_name: Document containing the object. Uses active document if None.
            include_properties: Whether to include property values.
            include_shape: Whether to include shape geometry details.

        Returns:
            Dictionary containing comprehensive object information:
                - name: Object name
                - label: Object label
                - type_id: FreeCAD type identifier
                - properties: Dictionary of property names and values (if requested)
                - shape_info: Shape details (if requested and object has shape)
                - children: List of child object names
                - parents: List of parent object names
                - visibility: Whether object is visible
        """
        bridge = await get_bridge()
        obj = await bridge.get_object(object_name, doc_name)

        result = {
            "name": obj.name,
            "label": obj.label,
            "type_id": obj.type_id,
            "children": obj.children,
            "parents": obj.parents,
            "visibility": obj.visibility,
        }

        if include_properties:
            result["properties"] = obj.properties

        if include_shape and obj.shape_info:
            result["shape_info"] = obj.shape_info

        return result

    @mcp.tool()
    async def create_object(
        type_id: str,
        name: str | None = None,
        properties: dict[str, Any] | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a new FreeCAD object.

        Args:
            type_id: FreeCAD type ID for the object. Common types include:
                - "Part::Box" - Parametric box
                - "Part::Cylinder" - Parametric cylinder
                - "Part::Sphere" - Parametric sphere
                - "Part::Cone" - Parametric cone
                - "Part::Torus" - Parametric torus
                - "Part::Feature" - Generic Part feature
                - "Sketcher::SketchObject" - Sketch
                - "PartDesign::Body" - PartDesign body
            name: Object name. Auto-generated if None.
            properties: Initial property values to set.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with created object information:
                - name: Object name
                - label: Object label
                - type_id: Object type
        """
        bridge = await get_bridge()
        obj = await bridge.create_object(type_id, name, properties, doc_name)
        return {
            "name": obj.name,
            "label": obj.label,
            "type_id": obj.type_id,
        }

    @mcp.tool()
    async def create_box(
        length: float = 10.0,
        width: float = 10.0,
        height: float = 10.0,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Part Box primitive.

        Args:
            length: Box length (X dimension). Defaults to 10.0.
            width: Box width (Y dimension). Defaults to 10.0.
            height: Box height (Z dimension). Defaults to 10.0.
            name: Object name. Auto-generated if None.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with created object information:
                - name: Object name
                - label: Object label
                - volume: Box volume
                - type_id: Object type
        """
        bridge = await get_bridge()
        obj = await bridge.create_object(
            "Part::Box",
            name,
            {"Length": length, "Width": width, "Height": height},
            doc_name,
        )
        return {
            "name": obj.name,
            "label": obj.label,
            "type_id": obj.type_id,
            "volume": length * width * height,
        }

    @mcp.tool()
    async def create_cylinder(
        radius: float = 5.0,
        height: float = 10.0,
        angle: float = 360.0,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Part Cylinder primitive.

        Args:
            radius: Cylinder radius. Defaults to 5.0.
            height: Cylinder height. Defaults to 10.0.
            angle: Sweep angle in degrees (for partial cylinder). Defaults to 360.
            name: Object name. Auto-generated if None.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with created object information:
                - name: Object name
                - label: Object label
                - type_id: Object type
        """
        bridge = await get_bridge()
        obj = await bridge.create_object(
            "Part::Cylinder",
            name,
            {"Radius": radius, "Height": height, "Angle": angle},
            doc_name,
        )
        return {
            "name": obj.name,
            "label": obj.label,
            "type_id": obj.type_id,
        }

    @mcp.tool()
    async def create_sphere(
        radius: float = 5.0,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Part Sphere primitive.

        Args:
            radius: Sphere radius. Defaults to 5.0.
            name: Object name. Auto-generated if None.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with created object information:
                - name: Object name
                - label: Object label
                - type_id: Object type
        """
        bridge = await get_bridge()
        obj = await bridge.create_object(
            "Part::Sphere",
            name,
            {"Radius": radius},
            doc_name,
        )
        return {
            "name": obj.name,
            "label": obj.label,
            "type_id": obj.type_id,
        }

    @mcp.tool()
    async def create_cone(
        radius1: float = 5.0,
        radius2: float = 0.0,
        height: float = 10.0,
        angle: float = 360.0,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Part Cone primitive.

        Args:
            radius1: Bottom radius. Defaults to 5.0.
            radius2: Top radius (0 for pointed cone). Defaults to 0.0.
            height: Cone height. Defaults to 10.0.
            angle: Sweep angle in degrees (for partial cone). Defaults to 360.
            name: Object name. Auto-generated if None.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with created object information:
                - name: Object name
                - label: Object label
                - type_id: Object type
        """
        bridge = await get_bridge()
        obj = await bridge.create_object(
            "Part::Cone",
            name,
            {"Radius1": radius1, "Radius2": radius2, "Height": height, "Angle": angle},
            doc_name,
        )
        return {
            "name": obj.name,
            "label": obj.label,
            "type_id": obj.type_id,
        }

    @mcp.tool()
    async def create_torus(
        radius1: float = 10.0,
        radius2: float = 2.0,
        angle1: float = -180.0,
        angle2: float = 180.0,
        angle3: float = 360.0,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Part Torus (donut shape) primitive.

        Args:
            radius1: Major radius (center to tube center). Defaults to 10.0.
            radius2: Minor radius (tube radius). Defaults to 2.0.
            angle1: Start angle for tube sweep. Defaults to -180.
            angle2: End angle for tube sweep. Defaults to 180.
            angle3: Rotation angle around axis. Defaults to 360.
            name: Object name. Auto-generated if None.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with created object information:
                - name: Object name
                - label: Object label
                - type_id: Object type
        """
        bridge = await get_bridge()
        obj = await bridge.create_object(
            "Part::Torus",
            name,
            {
                "Radius1": radius1,
                "Radius2": radius2,
                "Angle1": angle1,
                "Angle2": angle2,
                "Angle3": angle3,
            },
            doc_name,
        )
        return {
            "name": obj.name,
            "label": obj.label,
            "type_id": obj.type_id,
        }

    @mcp.tool()
    async def create_wedge(
        xmin: float = 0.0,
        ymin: float = 0.0,
        zmin: float = 0.0,
        x2min: float = 2.0,
        z2min: float = 2.0,
        xmax: float = 10.0,
        ymax: float = 10.0,
        zmax: float = 10.0,
        x2max: float = 8.0,
        z2max: float = 8.0,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Part Wedge primitive.

        A wedge is a tapered box shape useful for ramps and similar geometry.

        Args:
            xmin: Minimum X at base. Defaults to 0.0.
            ymin: Minimum Y (base position). Defaults to 0.0.
            zmin: Minimum Z at base. Defaults to 0.0.
            x2min: Minimum X at top. Defaults to 2.0.
            z2min: Minimum Z at top. Defaults to 2.0.
            xmax: Maximum X at base. Defaults to 10.0.
            ymax: Maximum Y (top position). Defaults to 10.0.
            zmax: Maximum Z at base. Defaults to 10.0.
            x2max: Maximum X at top. Defaults to 8.0.
            z2max: Maximum Z at top. Defaults to 8.0.
            name: Object name. Auto-generated if None.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with created object information:
                - name: Object name
                - label: Object label
                - type_id: Object type
        """
        bridge = await get_bridge()
        obj = await bridge.create_object(
            "Part::Wedge",
            name,
            {
                "Xmin": xmin,
                "Ymin": ymin,
                "Zmin": zmin,
                "X2min": x2min,
                "Z2min": z2min,
                "Xmax": xmax,
                "Ymax": ymax,
                "Zmax": zmax,
                "X2max": x2max,
                "Z2max": z2max,
            },
            doc_name,
        )
        return {
            "name": obj.name,
            "label": obj.label,
            "type_id": obj.type_id,
        }

    @mcp.tool()
    async def create_helix(
        pitch: float = 5.0,
        height: float = 20.0,
        radius: float = 5.0,
        angle: float = 0.0,
        left_handed: bool = False,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Part Helix curve.

        A helix is a spiral curve, useful as a sweep path for threads and springs.

        Args:
            pitch: Distance between turns. Defaults to 5.0.
            height: Total helix height. Defaults to 20.0.
            radius: Helix radius. Defaults to 5.0.
            angle: Taper angle in degrees. Defaults to 0.0.
            left_handed: Whether helix is left-handed. Defaults to False.
            name: Object name. Auto-generated if None.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with created object information:
                - name: Object name
                - label: Object label
                - type_id: Object type
        """
        bridge = await get_bridge()
        obj = await bridge.create_object(
            "Part::Helix",
            name,
            {
                "Pitch": pitch,
                "Height": height,
                "Radius": radius,
                "Angle": angle,
                "LocalCoord": 1 if left_handed else 0,
            },
            doc_name,
        )
        return {
            "name": obj.name,
            "label": obj.label,
            "type_id": obj.type_id,
        }

    @mcp.tool()
    async def edit_object(
        object_name: str,
        properties: dict[str, Any],
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Edit properties of an existing FreeCAD object.

        Args:
            object_name: Name of the object to edit.
            properties: Dictionary of property names and new values.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with updated object information:
                - name: Object name
                - label: Object label
                - type_id: Object type
        """
        bridge = await get_bridge()
        obj = await bridge.edit_object(object_name, properties, doc_name)
        return {
            "name": obj.name,
            "label": obj.label,
            "type_id": obj.type_id,
        }

    @mcp.tool()
    async def delete_object(
        object_name: str,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Delete an object from a FreeCAD document.

        Args:
            object_name: Name of the object to delete.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with delete result:
                - success: Whether delete was successful
        """
        bridge = await get_bridge()
        await bridge.delete_object(object_name, doc_name)
        return {"success": True}

    @mcp.tool()
    async def boolean_operation(
        operation: str,
        object1_name: str,
        object2_name: str,
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Perform a boolean operation on two FreeCAD objects.

        Args:
            operation: Boolean operation type: "fuse" (union), "cut" (subtract),
                      or "common" (intersection).
            object1_name: Name of the first object.
            object2_name: Name of the second object.
            result_name: Name for the result object. Auto-generated if None.
            doc_name: Document containing the objects. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
        """
        bridge = await get_bridge()

        operation_map = {
            "fuse": "Part::MultiFuse",
            "cut": "Part::Cut",
            "common": "Part::MultiCommon",
        }

        if operation not in operation_map:
            raise ValueError(f"Invalid operation: {operation}. Use: fuse, cut, common")

        op_type = operation_map[operation]
        result_name = result_name or f"{operation.capitalize()}"

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj1 = doc.getObject({object1_name!r})
obj2 = doc.getObject({object2_name!r})

if obj1 is None:
    raise ValueError(f"Object not found: {object1_name!r}")
if obj2 is None:
    raise ValueError(f"Object not found: {object2_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Boolean {operation.capitalize()}")
try:
    if {op_type!r} == "Part::Cut":
        result = doc.addObject({op_type!r}, {result_name!r})
        result.Base = obj1
        result.Tool = obj2
    else:
        result = doc.addObject({op_type!r}, {result_name!r})
        result.Shapes = [obj1, obj2]

    doc.recompute()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "name": result.Name,
    "label": result.Label,
    "type_id": result.TypeId,
}}
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Boolean operation failed")

    @mcp.tool()
    async def set_placement(
        object_name: str,
        position: list[float] | None = None,
        rotation: list[float] | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Set the placement (position and rotation) of a FreeCAD object.

        Args:
            object_name: Name of the object to move.
            position: Position as [x, y, z]. Keeps current if None.
            rotation: Rotation as [yaw, pitch, roll] in degrees. Keeps current if None.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with new placement:
                - position: New position [x, y, z]
                - rotation: New rotation angles
        """
        bridge = await get_bridge()

        pos_str = (
            f"FreeCAD.Vector({position[0]}, {position[1]}, {position[2]})"
            if position
            else "obj.Placement.Base"
        )
        rot_str = (
            f"FreeCAD.Rotation({rotation[0]}, {rotation[1]}, {rotation[2]})"
            if rotation
            else "obj.Placement.Rotation"
        )

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Set Placement")
try:
    pos = {pos_str}
    rot = {rot_str}

    obj.Placement = FreeCAD.Placement(pos, rot)
    doc.recompute()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "position": [obj.Placement.Base.x, obj.Placement.Base.y, obj.Placement.Base.z],
    "rotation": list(obj.Placement.Rotation.toEuler()),
}}
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Set placement failed")

    @mcp.tool()
    async def scale_object(
        object_name: str,
        scale: float | list[float],
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Scale an object uniformly or non-uniformly.

        Creates a new scaled copy using Part.Scale.

        Args:
            object_name: Name of the object to scale.
            scale: Scale factor. Can be:
                - A single float for uniform scaling
                - A list [sx, sy, sz] for non-uniform scaling
            result_name: Name for the result object. Auto-generated if None.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
        """
        bridge = await get_bridge()

        if isinstance(scale, int | float):
            scale_vec = f"FreeCAD.Vector({scale}, {scale}, {scale})"
        else:
            scale_vec = f"FreeCAD.Vector({scale[0]}, {scale[1]}, {scale[2]})"

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")

if not hasattr(obj, "Shape"):
    raise ValueError("Object has no shape to scale")

import Part

# Wrap in transaction for undo support
doc.openTransaction("Scale Object")
try:
    scale_vec = {scale_vec}
    center = obj.Shape.BoundBox.Center

    # Create scaled shape
    mat = FreeCAD.Matrix()
    mat.scale(scale_vec)
    scaled_shape = obj.Shape.transformGeometry(mat)

    # Create result object
    result_name = {result_name!r} or f"{{obj.Name}}_scaled"
    result = doc.addObject("Part::Feature", result_name)
    result.Shape = scaled_shape

    doc.recompute()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "name": result.Name,
    "label": result.Label,
    "type_id": result.TypeId,
}}
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Scale operation failed")

    @mcp.tool()
    async def rotate_object(
        object_name: str,
        axis: list[float],
        angle: float,
        center: list[float] | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Rotate an object around an axis.

        Modifies the object's placement in-place.

        Args:
            object_name: Name of the object to rotate.
            axis: Rotation axis as [x, y, z] vector.
            angle: Rotation angle in degrees.
            center: Center point for rotation [x, y, z].
                    Uses object center if None.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with new placement:
                - position: New position [x, y, z]
                - rotation: New rotation angles
        """
        bridge = await get_bridge()

        center_str = (
            f"FreeCAD.Vector({center[0]}, {center[1]}, {center[2]})"
            if center
            else "obj.Shape.BoundBox.Center if hasattr(obj, 'Shape') else FreeCAD.Vector(0,0,0)"
        )

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Rotate Object")
try:
    axis = FreeCAD.Vector({axis[0]}, {axis[1]}, {axis[2]})
    center = {center_str}

    # Create rotation
    rot = FreeCAD.Rotation(axis, {angle})

    # Apply rotation around center
    old_placement = obj.Placement
    new_rot = rot.multiply(old_placement.Rotation)

    # Adjust position for rotation around center
    pos_vec = old_placement.Base - center
    rotated_pos = rot.multVec(pos_vec) + center

    obj.Placement = FreeCAD.Placement(rotated_pos, new_rot)
    doc.recompute()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "position": [obj.Placement.Base.x, obj.Placement.Base.y, obj.Placement.Base.z],
    "rotation": list(obj.Placement.Rotation.toEuler()),
}}
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Rotate operation failed")

    @mcp.tool()
    async def copy_object(
        object_name: str,
        new_name: str | None = None,
        offset: list[float] | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a copy of an object.

        Args:
            object_name: Name of the object to copy.
            new_name: Name for the copy. Auto-generated if None.
            offset: Position offset [x, y, z] for the copy. [0,0,0] if None.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with copy object information:
                - name: Copy object name
                - label: Copy object label
                - type_id: Copy object type
        """
        bridge = await get_bridge()

        offset_str = (
            f"[{offset[0]}, {offset[1]}, {offset[2]}]" if offset else "[0, 0, 0]"
        )

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Copy Object")
try:
    # Create copy
    new_name = {new_name!r} or f"{{obj.Name}}_copy"

    if hasattr(obj, "Shape"):
        copy_obj = doc.addObject("Part::Feature", new_name)
        copy_obj.Shape = obj.Shape.copy()
    else:
        # For non-shape objects, create simple copy
        copy_obj = doc.copyObject(obj, False)
        copy_obj.Label = new_name

    # Apply offset
    offset = {offset_str}
    copy_obj.Placement.Base = FreeCAD.Vector(
        obj.Placement.Base.x + offset[0],
        obj.Placement.Base.y + offset[1],
        obj.Placement.Base.z + offset[2]
    )

    doc.recompute()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "name": copy_obj.Name,
    "label": copy_obj.Label,
    "type_id": copy_obj.TypeId,
}}
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Copy operation failed")

    @mcp.tool()
    async def mirror_object(
        object_name: str,
        plane: str = "XY",
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Mirror an object across a plane.

        Creates a new mirrored copy of the object.

        Args:
            object_name: Name of the object to mirror.
            plane: Mirror plane. Options: "XY", "XZ", "YZ".
            result_name: Name for the result object. Auto-generated if None.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
        """
        bridge = await get_bridge()

        plane_map = {
            "XY": "(0, 0, 1)",
            "XZ": "(0, 1, 0)",
            "YZ": "(1, 0, 0)",
        }

        if plane not in plane_map:
            raise ValueError(f"Invalid plane: {plane}. Use: XY, XZ, YZ")

        normal = plane_map[plane]

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")

if not hasattr(obj, "Shape"):
    raise ValueError("Object has no shape to mirror")

import Part

# Wrap in transaction for undo support
doc.openTransaction("Mirror Object")
try:
    # Create mirror matrix
    normal = FreeCAD.Vector{normal}
    center = obj.Shape.BoundBox.Center

    # Mirror the shape
    mirrored = obj.Shape.mirror(center, normal)

    # Create result object
    result_name = {result_name!r} or f"{{obj.Name}}_mirror"
    result = doc.addObject("Part::Feature", result_name)
    result.Shape = mirrored

    doc.recompute()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "name": result.Name,
    "label": result.Label,
    "type_id": result.TypeId,
}}
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Mirror operation failed")

    @mcp.tool()
    async def get_selection(doc_name: str | None = None) -> list[dict[str, Any]]:
        """Get the current selection in FreeCAD.

        Requires GUI mode.

        Args:
            doc_name: Document to check selection in. Uses active document if None.

        Returns:
            List of selected objects with:
                - name: Object name
                - label: Object label
                - type_id: Object type
                - sub_elements: List of selected sub-elements (e.g., ["Face1", "Edge2"])
        """
        bridge = await get_bridge()

        code = f"""
if not FreeCAD.GuiUp:
    _result_ = []
else:
    sel = FreeCADGui.Selection.getSelectionEx({doc_name!r})
    _result_ = []
    for s in sel:
        _result_.append({{
            "name": s.Object.Name,
            "label": s.Object.Label,
            "type_id": s.Object.TypeId,
            "sub_elements": list(s.SubElementNames) if s.SubElementNames else [],
        }})
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        return []

    @mcp.tool()
    async def set_selection(
        object_names: list[str],
        clear_existing: bool = True,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Set the selection in FreeCAD.

        Requires GUI mode.

        Args:
            object_names: List of object names to select.
            clear_existing: Whether to clear existing selection first. Defaults to True.
            doc_name: Document containing the objects. Uses active document if None.

        Returns:
            Dictionary with result:
                - success: Whether operation was successful
                - selected_count: Number of objects selected
        """
        bridge = await get_bridge()

        code = f"""
if not FreeCAD.GuiUp:
    _result_ = {{"success": False, "error": "GUI not available"}}
else:
    doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
    if doc is None:
        raise ValueError("No document found")

    if {clear_existing}:
        FreeCADGui.Selection.clearSelection()

    count = 0
    for name in {object_names!r}:
        obj = doc.getObject(name)
        if obj:
            FreeCADGui.Selection.addSelection(obj)
            count += 1

    _result_ = {{"success": True, "selected_count": count}}
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Set selection failed")

    @mcp.tool()
    async def clear_selection() -> dict[str, Any]:
        """Clear the current selection in FreeCAD.

        Requires GUI mode.

        Returns:
            Dictionary with result:
                - success: Whether operation was successful
        """
        bridge = await get_bridge()

        code = """
if not FreeCAD.GuiUp:
    _result_ = {"success": False, "error": "GUI not available"}
else:
    FreeCADGui.Selection.clearSelection()
    _result_ = {"success": True}
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Clear selection failed")

    # =========================================================================
    # Part Primitives - Additional shapes
    # =========================================================================

    @mcp.tool()
    async def create_line(
        point1: list[float],
        point2: list[float],
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Part Line (edge) between two points.

        Args:
            point1: Start point as [x, y, z].
            point2: End point as [x, y, z].
            name: Object name. Auto-generated if None.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with created object information:
                - name: Object name
                - label: Object label
                - type_id: Object type
                - length: Line length
        """
        bridge = await get_bridge()

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    doc = FreeCAD.newDocument("Unnamed")

# Wrap in transaction for undo support
doc.openTransaction("Create Line")
try:
    p1 = FreeCAD.Vector({point1[0]}, {point1[1]}, {point1[2]})
    p2 = FreeCAD.Vector({point2[0]}, {point2[1]}, {point2[2]})

    line = Part.makeLine(p1, p2)
    obj_name = {name!r} or "Line"
    obj = doc.addObject("Part::Feature", obj_name)
    obj.Shape = line

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": obj.Name,
        "label": obj.Label,
        "type_id": obj.TypeId,
        "length": line.Length,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Create line failed")

    @mcp.tool()
    async def create_plane(
        length: float = 10.0,
        width: float = 10.0,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Part Plane (flat rectangular face).

        Args:
            length: Plane length (X direction). Defaults to 10.0.
            width: Plane width (Y direction). Defaults to 10.0.
            name: Object name. Auto-generated if None.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with created object information:
                - name: Object name
                - label: Object label
                - type_id: Object type
        """
        bridge = await get_bridge()
        obj = await bridge.create_object(
            "Part::Plane",
            name,
            {"Length": length, "Width": width},
            doc_name,
        )
        return {
            "name": obj.name,
            "label": obj.label,
            "type_id": obj.type_id,
        }

    @mcp.tool()
    async def create_ellipse(
        major_radius: float = 10.0,
        minor_radius: float = 5.0,
        angle1: float = 0.0,
        angle2: float = 360.0,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Part Ellipse curve.

        Args:
            major_radius: Semi-major axis radius. Defaults to 10.0.
            minor_radius: Semi-minor axis radius. Defaults to 5.0.
            angle1: Start angle in degrees. Defaults to 0.
            angle2: End angle in degrees. Defaults to 360.
            name: Object name. Auto-generated if None.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with created object information:
                - name: Object name
                - label: Object label
                - type_id: Object type
        """
        bridge = await get_bridge()
        obj = await bridge.create_object(
            "Part::Ellipse",
            name,
            {
                "MajorRadius": major_radius,
                "MinorRadius": minor_radius,
                "Angle1": angle1,
                "Angle2": angle2,
            },
            doc_name,
        )
        return {
            "name": obj.name,
            "label": obj.label,
            "type_id": obj.type_id,
        }

    @mcp.tool()
    async def create_prism(
        polygon_sides: int = 6,
        circumradius: float = 5.0,
        height: float = 10.0,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Part Prism (extruded regular polygon).

        Args:
            polygon_sides: Number of sides (3 for triangle, 6 for hexagon, etc.).
                           Defaults to 6.
            circumradius: Radius of circumscribed circle. Defaults to 5.0.
            height: Prism height. Defaults to 10.0.
            name: Object name. Auto-generated if None.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with created object information:
                - name: Object name
                - label: Object label
                - type_id: Object type
        """
        bridge = await get_bridge()
        obj = await bridge.create_object(
            "Part::Prism",
            name,
            {"Polygon": polygon_sides, "Circumradius": circumradius, "Height": height},
            doc_name,
        )
        return {
            "name": obj.name,
            "label": obj.label,
            "type_id": obj.type_id,
        }

    @mcp.tool()
    async def create_regular_polygon(
        polygon_sides: int = 6,
        circumradius: float = 5.0,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a Part Regular Polygon (2D wire).

        Args:
            polygon_sides: Number of sides (3 for triangle, 6 for hexagon, etc.).
                           Defaults to 6.
            circumradius: Radius of circumscribed circle. Defaults to 5.0.
            name: Object name. Auto-generated if None.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with created object information:
                - name: Object name
                - label: Object label
                - type_id: Object type
        """
        bridge = await get_bridge()
        obj = await bridge.create_object(
            "Part::RegularPolygon",
            name,
            {"Polygon": polygon_sides, "Circumradius": circumradius},
            doc_name,
        )
        return {
            "name": obj.name,
            "label": obj.label,
            "type_id": obj.type_id,
        }

    # =========================================================================
    # Part Shape Operations
    # =========================================================================

    @mcp.tool()
    async def shell_object(
        object_name: str,
        thickness: float,
        faces_to_remove: list[str] | None = None,
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a shell (hollow) version of a solid by removing faces.

        Also known as "thickness" operation. Removes specified faces and
        offsets the remaining faces to create a hollow shell.

        Args:
            object_name: Name of the solid object to shell.
            thickness: Wall thickness (positive = outward, negative = inward).
            faces_to_remove: List of face names to remove (e.g., ["Face1", "Face6"]).
                            If None, tries to remove the largest face.
            result_name: Name for result object. Auto-generated if None.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
        """
        bridge = await get_bridge()

        # Use actual None or list, not string "None"
        faces_param = faces_to_remove if faces_to_remove else None

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")

if not hasattr(obj, "Shape"):
    raise ValueError("Object has no shape")

# Get faces to remove (None means find largest face)
faces_to_remove = {faces_param!r}

# Wrap in transaction for undo support
doc.openTransaction("Shell Object")
try:
    if faces_to_remove is None:
        # Find and remove the largest face
        faces = obj.Shape.Faces
        largest = max(faces, key=lambda f: f.Area)
        faces_to_remove_objs = [largest]
    else:
        # Get faces by name
        faces_to_remove_objs = []
        for fname in faces_to_remove:
            idx = int(fname.replace("Face", "")) - 1
            if 0 <= idx < len(obj.Shape.Faces):
                faces_to_remove_objs.append(obj.Shape.Faces[idx])

    shell = obj.Shape.makeThickness(faces_to_remove_objs, {thickness}, 1e-3)

    result_name = {result_name!r} or f"{{obj.Name}}_shell"
    result = doc.addObject("Part::Feature", result_name)
    result.Shape = shell

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": result.Name,
        "label": result.Label,
        "type_id": result.TypeId,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Shell operation failed")

    @mcp.tool()
    async def offset_3d(
        object_name: str,
        offset: float,
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a 3D offset of a shape.

        Offsets all faces of the shape by the specified distance.

        Args:
            object_name: Name of the object to offset.
            offset: Offset distance (positive = outward, negative = inward).
            result_name: Name for result object. Auto-generated if None.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
        """
        bridge = await get_bridge()

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")

if not hasattr(obj, "Shape"):
    raise ValueError("Object has no shape")

# Wrap in transaction for undo support
doc.openTransaction("3D Offset")
try:
    offset_shape = obj.Shape.makeOffsetShape({offset}, 1e-3)

    result_name = {result_name!r} or f"{{obj.Name}}_offset"
    result = doc.addObject("Part::Feature", result_name)
    result.Shape = offset_shape

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": result.Name,
        "label": result.Label,
        "type_id": result.TypeId,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "3D offset failed")

    @mcp.tool()
    async def slice_shape(
        object_name: str,
        plane_point: list[float],
        plane_normal: list[float],
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Slice a shape with a plane, returning the cross-section.

        Args:
            object_name: Name of the object to slice.
            plane_point: A point on the cutting plane [x, y, z].
            plane_normal: Normal vector of the cutting plane [x, y, z].
            result_name: Name for result object. Auto-generated if None.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
        """
        bridge = await get_bridge()

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")

if not hasattr(obj, "Shape"):
    raise ValueError("Object has no shape")

# Wrap in transaction for undo support
doc.openTransaction("Slice Shape")
try:
    point = FreeCAD.Vector({plane_point[0]}, {plane_point[1]}, {plane_point[2]})
    normal = FreeCAD.Vector({plane_normal[0]}, {plane_normal[1]}, {plane_normal[2]})

    # Create section
    wires = obj.Shape.slice(normal, point.dot(normal))

    if not wires:
        raise ValueError("Slice produced no result - plane may not intersect shape")

    # Make a compound of the wires
    if len(wires) == 1:
        section_shape = wires[0]
    else:
        section_shape = Part.makeCompound(wires)

    result_name = {result_name!r} or f"{{obj.Name}}_slice"
    result = doc.addObject("Part::Feature", result_name)
    result.Shape = section_shape

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": result.Name,
        "label": result.Label,
        "type_id": result.TypeId,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Slice operation failed")

    @mcp.tool()
    async def section_shape(
        object_name: str,
        plane: str = "XY",
        offset: float = 0.0,
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a cross-section of a shape at a standard plane.

        Args:
            object_name: Name of the object to section.
            plane: Section plane: "XY", "XZ", or "YZ". Defaults to "XY".
            offset: Offset from origin along the plane normal. Defaults to 0.
            result_name: Name for result object. Auto-generated if None.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
        """
        plane_normals = {
            "XY": [0, 0, 1],
            "XZ": [0, 1, 0],
            "YZ": [1, 0, 0],
        }

        if plane not in plane_normals:
            raise ValueError(f"Invalid plane: {plane}. Use: XY, XZ, YZ")

        normal = plane_normals[plane]
        point = [n * offset for n in normal]

        return await slice_shape(object_name, point, normal, result_name, doc_name)

    # =========================================================================
    # Part Compound Operations
    # =========================================================================

    @mcp.tool()
    async def make_compound(
        object_names: list[str],
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Combine multiple shapes into a single compound.

        A compound is a collection of shapes that can be manipulated together
        but are not fused (each shape remains separate).

        Args:
            object_names: List of object names to combine.
            result_name: Name for result object. Auto-generated if None.
            doc_name: Document containing the objects. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
                - shape_count: Number of shapes in compound
        """
        bridge = await get_bridge()

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

shapes = []
for obj_name in {object_names!r}:
    obj = doc.getObject(obj_name)
    if obj is None:
        raise ValueError(f"Object not found: {{obj_name}}")
    if not hasattr(obj, "Shape"):
        raise ValueError(f"Object has no shape: {{obj_name}}")
    shapes.append(obj.Shape)

# Wrap in transaction for undo support
doc.openTransaction("Make Compound")
try:
    compound = Part.makeCompound(shapes)

    result_name = {result_name!r} or "Compound"
    result = doc.addObject("Part::Feature", result_name)
    result.Shape = compound

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": result.Name,
        "label": result.Label,
        "type_id": result.TypeId,
        "shape_count": len(shapes),
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Make compound failed")

    @mcp.tool()
    async def explode_compound(
        object_name: str,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Separate a compound into individual shape objects.

        Args:
            object_name: Name of the compound object to explode.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with result:
                - success: Whether operation succeeded
                - created_objects: List of created object names
        """
        bridge = await get_bridge()

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")

if not hasattr(obj, "Shape"):
    raise ValueError("Object has no shape")

# Wrap in transaction for undo support
doc.openTransaction("Explode Compound")
try:
    created = []

    # Get solids, shells, or other sub-shapes
    solids = obj.Shape.Solids
    if solids:
        shapes = solids
    else:
        shapes = obj.Shape.Shells if obj.Shape.Shells else obj.Shape.Faces

    for i, shape in enumerate(shapes):
        new_obj = doc.addObject("Part::Feature", f"{{obj.Name}}_{{i+1}}")
        new_obj.Shape = shape
        created.append(new_obj.Name)

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "success": True,
        "created_objects": created,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Explode compound failed")

    @mcp.tool()
    async def fuse_all(
        object_names: list[str],
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Fuse (union) multiple shapes into a single solid.

        Unlike boolean_operation which works on two objects at a time,
        this fuses all specified objects at once.

        Args:
            object_names: List of object names to fuse.
            result_name: Name for result object. Auto-generated if None.
            doc_name: Document containing the objects. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
        """
        bridge = await get_bridge()

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

shapes = []
for obj_name in {object_names!r}:
    obj = doc.getObject(obj_name)
    if obj is None:
        raise ValueError(f"Object not found: {{obj_name}}")
    if not hasattr(obj, "Shape"):
        raise ValueError(f"Object has no shape: {{obj_name}}")
    shapes.append(obj.Shape)

if len(shapes) < 2:
    raise ValueError("Need at least 2 objects to fuse")

# Wrap in transaction for undo support
doc.openTransaction("Fuse All")
try:
    # Fuse all shapes
    fused = shapes[0]
    for s in shapes[1:]:
        fused = fused.fuse(s)

    result_name = {result_name!r} or "Fusion"
    result = doc.addObject("Part::Feature", result_name)
    result.Shape = fused

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": result.Name,
        "label": result.Label,
        "type_id": result.TypeId,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Fuse all failed")

    @mcp.tool()
    async def common_all(
        object_names: list[str],
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Find the common (intersection) of multiple shapes.

        Args:
            object_names: List of object names to intersect.
            result_name: Name for result object. Auto-generated if None.
            doc_name: Document containing the objects. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
        """
        bridge = await get_bridge()

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

shapes = []
for obj_name in {object_names!r}:
    obj = doc.getObject(obj_name)
    if obj is None:
        raise ValueError(f"Object not found: {{obj_name}}")
    if not hasattr(obj, "Shape"):
        raise ValueError(f"Object has no shape: {{obj_name}}")
    shapes.append(obj.Shape)

if len(shapes) < 2:
    raise ValueError("Need at least 2 objects for common operation")

# Wrap in transaction for undo support
doc.openTransaction("Common All")
try:
    # Find common of all shapes
    common = shapes[0]
    for s in shapes[1:]:
        common = common.common(s)

    result_name = {result_name!r} or "Common"
    result = doc.addObject("Part::Feature", result_name)
    result.Shape = common

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": result.Name,
        "label": result.Label,
        "type_id": result.TypeId,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Common all failed")

    # =========================================================================
    # Part Wire/Face Operations
    # =========================================================================

    @mcp.tool()
    async def make_wire(
        points: list[list[float]],
        closed: bool = False,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a wire (polyline) from a list of points.

        Args:
            points: List of points, each as [x, y, z].
            closed: Whether to close the wire. Defaults to False.
            name: Object name. Auto-generated if None.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with created object information:
                - name: Object name
                - label: Object label
                - type_id: Object type
                - length: Wire length
        """
        bridge = await get_bridge()

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    doc = FreeCAD.newDocument("Unnamed")

points = {points!r}
if len(points) < 2:
    raise ValueError("Need at least 2 points to make a wire")

# Wrap in transaction for undo support
doc.openTransaction("Make Wire")
try:
    vectors = [FreeCAD.Vector(p[0], p[1], p[2]) for p in points]

    # Create edges between consecutive points
    edges = []
    for i in range(len(vectors) - 1):
        edges.append(Part.makeLine(vectors[i], vectors[i+1]))

    # Close the wire if requested
    if {closed} and len(vectors) > 2:
        edges.append(Part.makeLine(vectors[-1], vectors[0]))

    wire = Part.Wire(edges)

    obj_name = {name!r} or "Wire"
    obj = doc.addObject("Part::Feature", obj_name)
    obj.Shape = wire

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": obj.Name,
        "label": obj.Label,
        "type_id": obj.TypeId,
        "length": wire.Length,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Make wire failed")

    @mcp.tool()
    async def make_face(
        object_name: str,
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a face from a closed wire.

        Args:
            object_name: Name of the wire object.
            result_name: Name for result object. Auto-generated if None.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
                - area: Face area
        """
        bridge = await get_bridge()

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")

if not hasattr(obj, "Shape"):
    raise ValueError("Object has no shape")

# Wrap in transaction for undo support
doc.openTransaction("Make Face")
try:
    # Get wire from shape
    wires = obj.Shape.Wires
    if not wires:
        raise ValueError("Object has no wires to make face from")

    face = Part.Face(wires[0])

    result_name = {result_name!r} or f"{{obj.Name}}_face"
    result = doc.addObject("Part::Feature", result_name)
    result.Shape = face

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": result.Name,
        "label": result.Label,
        "type_id": result.TypeId,
        "area": face.Area,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Make face failed")

    @mcp.tool()
    async def extrude_shape(
        object_name: str,
        direction: list[float],
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Extrude a wire or face along a direction vector.

        Args:
            object_name: Name of the wire or face object to extrude.
            direction: Extrusion direction and length as [x, y, z].
            result_name: Name for result object. Auto-generated if None.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
        """
        bridge = await get_bridge()

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")

if not hasattr(obj, "Shape"):
    raise ValueError("Object has no shape")

# Wrap in transaction for undo support
doc.openTransaction("Extrude Shape")
try:
    direction = FreeCAD.Vector({direction[0]}, {direction[1]}, {direction[2]})
    extruded = obj.Shape.extrude(direction)

    result_name = {result_name!r} or f"{{obj.Name}}_extruded"
    result = doc.addObject("Part::Feature", result_name)
    result.Shape = extruded

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": result.Name,
        "label": result.Label,
        "type_id": result.TypeId,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Extrude shape failed")

    @mcp.tool()
    async def revolve_shape(
        object_name: str,
        axis_point: list[float],
        axis_direction: list[float],
        angle: float = 360.0,
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Revolve a wire or face around an axis.

        Args:
            object_name: Name of the wire or face object to revolve.
            axis_point: A point on the rotation axis [x, y, z].
            axis_direction: Direction of the rotation axis [x, y, z].
            angle: Revolution angle in degrees. Defaults to 360.
            result_name: Name for result object. Auto-generated if None.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
        """
        bridge = await get_bridge()

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")

if not hasattr(obj, "Shape"):
    raise ValueError("Object has no shape")

# Wrap in transaction for undo support
doc.openTransaction("Revolve Shape")
try:
    import math

    axis_point = FreeCAD.Vector({axis_point[0]}, {axis_point[1]}, {axis_point[2]})
    axis_dir = FreeCAD.Vector({axis_direction[0]}, {axis_direction[1]}, {axis_direction[2]})
    angle_rad = math.radians({angle})

    revolved = obj.Shape.revolve(axis_point, axis_dir, {angle})

    result_name = {result_name!r} or f"{{obj.Name}}_revolved"
    result = doc.addObject("Part::Feature", result_name)
    result.Shape = revolved

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": result.Name,
        "label": result.Label,
        "type_id": result.TypeId,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Revolve shape failed")

    # =========================================================================
    # Part Loft and Sweep
    # =========================================================================

    @mcp.tool()
    async def part_loft(
        profile_names: list[str],
        solid: bool = True,
        ruled: bool = False,
        closed: bool = False,
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a loft (transition shape) between multiple profiles.

        This is the Part workbench version of loft, working directly on
        wires/faces rather than PartDesign sketches.

        Args:
            profile_names: List of wire/face object names to loft through (in order).
            solid: Whether to create a solid (True) or shell (False). Defaults to True.
            ruled: Whether to create ruled surfaces. Defaults to False.
            closed: Whether to close the loft (connect last to first). Defaults to False.
            result_name: Name for result object. Auto-generated if None.
            doc_name: Document containing the profiles. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
        """
        bridge = await get_bridge()

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

profiles = []
for name in {profile_names!r}:
    obj = doc.getObject(name)
    if obj is None:
        raise ValueError(f"Object not found: {{name}}")
    if not hasattr(obj, "Shape"):
        raise ValueError(f"Object has no shape: {{name}}")

    # Get wire from shape
    if obj.Shape.Wires:
        profiles.append(obj.Shape.Wires[0])
    else:
        raise ValueError(f"Object has no wires: {{name}}")

if len(profiles) < 2:
    raise ValueError("Need at least 2 profiles for loft")

# Wrap in transaction for undo support
doc.openTransaction("Part Loft")
try:
    loft = Part.makeLoft(profiles, {solid}, {ruled}, {closed})

    result_name = {result_name!r} or "Loft"
    result = doc.addObject("Part::Feature", result_name)
    result.Shape = loft

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": result.Name,
        "label": result.Label,
        "type_id": result.TypeId,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Part loft failed")

    @mcp.tool()
    async def part_sweep(
        profile_name: str,
        spine_name: str,
        solid: bool = True,
        frenet: bool = True,
        result_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Sweep a profile along a spine path.

        This is the Part workbench version of sweep, working directly on
        wires/faces rather than PartDesign sketches.

        Args:
            profile_name: Name of the profile wire/face object.
            spine_name: Name of the spine (path) wire object.
            solid: Whether to create a solid. Defaults to True.
            frenet: Whether to use Frenet mode for orientation. Defaults to True.
            result_name: Name for result object. Auto-generated if None.
            doc_name: Document containing the objects. Uses active document if None.

        Returns:
            Dictionary with result object information:
                - name: Result object name
                - label: Result object label
                - type_id: Result object type
        """
        bridge = await get_bridge()

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

profile_obj = doc.getObject({profile_name!r})
if profile_obj is None:
    raise ValueError(f"Profile object not found: {profile_name!r}")

spine_obj = doc.getObject({spine_name!r})
if spine_obj is None:
    raise ValueError(f"Spine object not found: {spine_name!r}")

if not hasattr(profile_obj, "Shape") or not hasattr(spine_obj, "Shape"):
    raise ValueError("Objects must have shapes")

# Wrap in transaction for undo support
doc.openTransaction("Part Sweep")
try:
    # Get profile wire
    if profile_obj.Shape.Wires:
        profile = profile_obj.Shape.Wires[0]
    else:
        raise ValueError("Profile has no wires")

    # Get spine wire
    if spine_obj.Shape.Wires:
        spine = spine_obj.Shape.Wires[0]
    else:
        raise ValueError("Spine has no wires")

    sweep = Part.Wire(spine).makePipeShell([profile], {solid}, {frenet})

    result_name = {result_name!r} or "Sweep"
    result = doc.addObject("Part::Feature", result_name)
    result.Shape = sweep

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": result.Name,
        "label": result.Label,
        "type_id": result.TypeId,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Part sweep failed")
