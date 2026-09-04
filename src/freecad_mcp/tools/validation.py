"""Validation tools for FreeCAD Robust MCP Server.

This module provides tools for validating FreeCAD objects and documents,
checking for errors, and providing automatic rollback capabilities.

These tools are essential for robust CAD workflows where operations
may fail or create invalid geometry.
"""

from collections.abc import Awaitable, Callable
from typing import Any


def register_validation_tools(
    mcp: Any, get_bridge: Callable[[], Awaitable[Any]]
) -> None:
    """Register validation-related tools with the Robust MCP Server.

    Args:
        mcp: The FastMCP (Robust MCP Server) instance.
        get_bridge: Async function to get the active bridge.
    """

    @mcp.tool()
    async def validate_object(
        object_name: str,
        doc_name: str | None = None,
        require_single_solid: bool = False,
    ) -> dict[str, Any]:
        """Check the health and validity of a FreeCAD object.

        This tool inspects an object to determine if it is in a valid state,
        has any computation errors, or needs recomputation. Use this after
        performing operations to verify they succeeded.

        Args:
            object_name: Name of the object to validate.
            doc_name: Document containing the object. Uses active document if None.
            require_single_solid: Mark the result invalid unless the shape has
                exactly one solid.

        Returns:
            Dictionary containing:
                - valid: Overall validity (True if shape is valid and no errors)
                - object_name: Name of the validated object
                - shape_valid: Whether the shape geometry is valid
                - has_errors: Whether the object has error states
                - state: List of state flags (e.g., ["Invalid", "Touched"])
                - recompute_needed: Whether recomputation is needed
                - volume: Shape volume if applicable (None otherwise)
                - area: Shape surface area if applicable (None otherwise)
                - solid_count: Number of solids in the shape, if it has a shape
                - single_solid: Whether the shape has exactly one solid
                - error_messages: List of any error messages
                - warnings: List of any warnings

        Example:
            Validate an object after creating it::

                result = await validate_object("MyBox")
                if not result["valid"]:
                    print(f"Errors: {result['error_messages']}")
        """
        bridge = await get_bridge()

        code = f"""
import FreeCAD

doc_name = {doc_name!r}
object_name = {object_name!r}
require_single_solid = {require_single_solid!r}

# Get document
if doc_name:
    doc = FreeCAD.getDocument(doc_name)
else:
    doc = FreeCAD.ActiveDocument

if doc is None:
    _result_ = {{
        "valid": False,
        "object_name": object_name,
        "error_messages": ["No active document found"],
        "shape_valid": False,
        "has_errors": True,
        "state": [],
        "recompute_needed": False,
        "volume": None,
        "area": None,
        "solid_count": None,
        "single_solid": None,
        "warnings": []
    }}
else:
    obj = doc.getObject(object_name)
    if obj is None:
        _result_ = {{
            "valid": False,
            "object_name": object_name,
            "error_messages": [f"Object '{{object_name}}' not found in document '{{doc.Name}}'"],
            "shape_valid": False,
            "has_errors": True,
            "state": [],
            "recompute_needed": False,
            "volume": None,
            "area": None,
            "solid_count": None,
            "single_solid": None,
            "warnings": []
        }}
    else:
        # Check object state
        state = list(obj.State) if hasattr(obj, 'State') else []
        has_errors = "Invalid" in state or "Error" in state
        recompute_needed = "Touched" in state

        # Check shape validity
        shape_valid = False
        volume = None
        area = None
        solid_count = None
        single_solid = None
        warnings = []
        error_messages = []

        shape = getattr(obj, 'Shape', None)
        shape_exempt_type_ids = {{
            "PartDesign::Body",
            "PartDesign::Plane",
            "PartDesign::Line",
            "PartDesign::Point",
            "PartDesign::CoordinateSystem",
        }}
        expects_shape = (
            obj.TypeId.startswith("Part::")
            or (
                obj.TypeId.startswith("PartDesign::")
                and obj.TypeId not in shape_exempt_type_ids
            )
        )
        if shape is not None and not shape.isNull():
            try:
                shape_valid = shape.isValid()
                if not shape_valid:
                    error_messages.append("Shape geometry is invalid")

                # Get volume if shape is a solid
                if hasattr(shape, 'Volume'):
                    volume = shape.Volume
                    if volume <= 0:
                        warnings.append(f"Shape has non-positive volume: {{volume}}")

                # Get surface area
                if hasattr(shape, 'Area'):
                    area = shape.Area

                solid_count = len(shape.Solids)
                single_solid = solid_count == 1
                if require_single_solid and not single_solid:
                    error_messages.append(
                        f"Expected exactly one solid, found {{solid_count}}"
                    )

            except Exception as e:
                error_messages.append(f"Error checking shape: {{str(e)}}")
                shape_valid = False
        else:
            shape_valid = not expects_shape
            solid_count = 0
            single_solid = False
            if expects_shape:
                error_messages.append("Object has no result shape")
            if require_single_solid:
                error_messages.append("Expected exactly one solid, found 0")

        if recompute_needed:
            error_messages.append("Object still needs recompute")

        # Check for PartDesign-specific issues
        if hasattr(obj, 'BaseFeature') and obj.BaseFeature is None:
            if obj.TypeId not in ["PartDesign::Body", "Sketcher::SketchObject"]:
                warnings.append("PartDesign feature has no base feature")

        # Overall validity
        valid = (
            shape_valid
            and not has_errors
            and not recompute_needed
            and not error_messages
        )

        _result_ = {{
            "valid": valid,
            "object_name": obj.Name,
            "shape_valid": shape_valid,
            "has_errors": has_errors,
            "state": state,
            "recompute_needed": recompute_needed,
            "volume": volume,
            "area": area,
            "solid_count": solid_count,
            "single_solid": single_solid,
            "error_messages": error_messages,
            "warnings": warnings
        }}
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success and result.result:
            return result.result
        return {
            "valid": False,
            "object_name": object_name,
            "error_messages": [result.error_traceback or "Validation failed"],
            "shape_valid": False,
            "has_errors": True,
            "state": [],
            "recompute_needed": False,
            "volume": None,
            "area": None,
            "solid_count": None,
            "single_solid": None,
            "warnings": [],
        }

    @mcp.tool()
    async def validate_document(
        doc_name: str | None = None,
        require_single_solid: bool = False,
    ) -> dict[str, Any]:
        """Check the health of all objects in a FreeCAD document.

        This tool validates every object in the document and provides
        a summary of the document's overall health. Use this after
        complex operations or before saving/exporting.

        Args:
            doc_name: Name of document to validate. Uses active document if None.
            require_single_solid: Require each PartDesign Body to contain exactly
                one solid.

        Returns:
            Dictionary containing:
                - valid: Overall document validity (True if all objects valid)
                - doc_name: Name of the validated document
                - total_objects: Total number of objects in document
                - valid_objects: Count of valid objects
                - invalid_objects: List of names of invalid objects
                - objects_with_errors: List of names with error states
                - objects_needing_recompute: List of objects that need recompute
                - recompute_needed: Whether document needs recomputation
                - solid_counts: Solid count for every shape-bearing object
                - single_solid_violations: PartDesign Bodies without one solid
                - summary: Human-readable summary of document health

        Example:
            Check document health before saving::

                result = await validate_document()
                if result["valid"]:
                    await save_document()
                else:
                    print(f"Issues: {result['invalid_objects']}")
        """
        bridge = await get_bridge()

        code = f"""
import FreeCAD

doc_name = {doc_name!r}
require_single_solid = {require_single_solid!r}

# Get document
if doc_name:
    doc = FreeCAD.getDocument(doc_name)
else:
    doc = FreeCAD.ActiveDocument

if doc is None:
    _result_ = {{
        "valid": False,
        "doc_name": None,
        "total_objects": 0,
        "valid_objects": 0,
        "invalid_objects": [],
        "objects_with_errors": [],
        "objects_needing_recompute": [],
        "recompute_needed": False,
        "solid_counts": {{}},
        "single_solid_violations": [],
        "summary": "No active document found"
    }}
else:
    total_objects = len(doc.Objects)
    valid_count = 0
    invalid_objects = []
    objects_with_errors = []
    objects_needing_recompute = []
    solid_counts = {{}}
    single_solid_violations = []

    for obj in doc.Objects:
        is_valid = True

        # Check state
        state = list(obj.State) if hasattr(obj, 'State') else []

        if "Invalid" in state or "Error" in state:
            objects_with_errors.append(obj.Name)
            is_valid = False

        if "Touched" in state:
            objects_needing_recompute.append(obj.Name)
            is_valid = False

        # Check shape validity for objects that should have shapes
        shape = getattr(obj, 'Shape', None)
        shape_exempt_type_ids = {{
            "PartDesign::Body",
            "PartDesign::Plane",
            "PartDesign::Line",
            "PartDesign::Point",
            "PartDesign::CoordinateSystem",
        }}
        expects_shape = (
            obj.TypeId.startswith("Part::")
            or (
                obj.TypeId.startswith("PartDesign::")
                and obj.TypeId not in shape_exempt_type_ids
            )
        )
        if shape is None or shape.isNull():
            if obj.TypeId == "PartDesign::Body":
                solid_counts[obj.Name] = 0
                if require_single_solid:
                    single_solid_violations.append(obj.Name)
                    is_valid = False
            if expects_shape:
                invalid_objects.append(obj.Name)
                is_valid = False
        else:
            try:
                solid_count = len(shape.Solids)
                solid_counts[obj.Name] = solid_count
                if (
                    require_single_solid
                    and obj.TypeId == "PartDesign::Body"
                    and solid_count != 1
                ):
                    single_solid_violations.append(obj.Name)
                    is_valid = False
                if not shape.isValid():
                    invalid_objects.append(obj.Name)
                    is_valid = False
            except Exception:
                invalid_objects.append(obj.Name)
                is_valid = False

        if is_valid:
            valid_count += 1

    # Build summary
    if valid_count == total_objects and not objects_with_errors:
        summary = f"Document '{{doc.Name}}' is healthy: all {{total_objects}} objects are valid"
    else:
        issues = []
        if invalid_objects:
            issues.append(f"{{len(invalid_objects)}} invalid objects")
        if objects_with_errors:
            issues.append(f"{{len(objects_with_errors)}} objects with errors")
        if objects_needing_recompute:
            issues.append(f"{{len(objects_needing_recompute)}} objects need recompute")
        if single_solid_violations:
            issues.append(
                f"{{len(single_solid_violations)}} single-solid violations"
            )
        summary = f"Document '{{doc.Name}}' has issues: " + ", ".join(issues)

    overall_valid = (
        (valid_count == total_objects)
        and not objects_with_errors
        and not objects_needing_recompute
        and not single_solid_violations
    )

    _result_ = {{
        "valid": overall_valid,
        "doc_name": doc.Name,
        "total_objects": total_objects,
        "valid_objects": valid_count,
        "invalid_objects": invalid_objects,
        "objects_with_errors": objects_with_errors,
        "objects_needing_recompute": objects_needing_recompute,
        "recompute_needed": len(objects_needing_recompute) > 0,
        "solid_counts": solid_counts,
        "single_solid_violations": single_solid_violations,
        "summary": summary
    }}
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success and result.result:
            return result.result
        return {
            "valid": False,
            "doc_name": doc_name,
            "total_objects": 0,
            "valid_objects": 0,
            "invalid_objects": [],
            "objects_with_errors": [],
            "objects_needing_recompute": [],
            "recompute_needed": False,
            "solid_counts": {},
            "single_solid_violations": [],
            "summary": result.error_traceback or "Validation failed",
        }
