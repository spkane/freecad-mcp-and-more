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

    # =========================================================================
    # Part Primitives - Additional shapes
    # =========================================================================

    # =========================================================================
    # Part Shape Operations
    # =========================================================================

    # =========================================================================
    # Part Compound Operations
    # =========================================================================

    # =========================================================================
    # Part Wire/Face Operations
    # =========================================================================

    # =========================================================================
    # Part Loft and Sweep
    # =========================================================================
