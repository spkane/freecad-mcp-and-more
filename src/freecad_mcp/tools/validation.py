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

    @mcp.tool()
    async def undo_if_invalid(
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Check document health and undo the last operation if invalid objects exist.

        This tool first validates all objects in the document. If any objects
        are invalid or have errors, it automatically performs an undo operation.
        Use this after risky operations to ensure the model stays in a valid state.

        Args:
            doc_name: Name of document to check. Uses active document if None.

        Returns:
            Dictionary containing:
                - was_valid: Whether the document was valid before any undo
                - undone: Whether an undo operation was performed
                - invalid_objects: List of invalid objects found (before undo)
                - objects_with_errors: List of objects with errors (before undo)
                - message: Human-readable description of what happened
                - validation_after: Validation result after undo (if performed)

        Example:
            Auto-recover from a failed boolean operation::

                await boolean_operation("cut", "Box", "InvalidShape")
                result = await undo_if_invalid()
                if result["undone"]:
                    print("Recovered from invalid operation")
        """
        bridge = await get_bridge()

        code = f"""
import FreeCAD

doc_name = {doc_name!r}

# Get document
if doc_name:
    doc = FreeCAD.getDocument(doc_name)
else:
    doc = FreeCAD.ActiveDocument

if doc is None:
    _result_ = {{
        "was_valid": False,
        "undone": False,
        "invalid_objects": [],
        "objects_with_errors": [],
        "message": "No active document found",
        "validation_after": None
    }}
else:
    # First, check current state
    invalid_objects = []
    objects_with_errors = []

    for obj in doc.Objects:
        state = list(obj.State) if hasattr(obj, 'State') else []

        if "Invalid" in state or "Error" in state:
            objects_with_errors.append(obj.Name)

        if hasattr(obj, 'Shape') and obj.Shape:
            try:
                if not obj.Shape.isValid():
                    invalid_objects.append(obj.Name)
            except Exception:
                invalid_objects.append(obj.Name)

    was_valid = len(invalid_objects) == 0 and len(objects_with_errors) == 0

    if was_valid:
        _result_ = {{
            "was_valid": True,
            "undone": False,
            "invalid_objects": [],
            "objects_with_errors": [],
            "message": "Document is valid, no undo needed",
            "validation_after": None
        }}
    else:
        # Perform undo
        try:
            doc.undo()
            doc.recompute()
            undone = True

            # Re-validate after undo
            invalid_after = []
            errors_after = []

            for obj in doc.Objects:
                state = list(obj.State) if hasattr(obj, 'State') else []

                if "Invalid" in state or "Error" in state:
                    errors_after.append(obj.Name)

                if hasattr(obj, 'Shape') and obj.Shape:
                    try:
                        if not obj.Shape.isValid():
                            invalid_after.append(obj.Name)
                    except Exception:
                        invalid_after.append(obj.Name)

            valid_after = len(invalid_after) == 0 and len(errors_after) == 0

            if valid_after:
                message = f"Undid last operation. Document is now valid."
            else:
                message = f"Undid last operation, but document still has issues."

            validation_after = {{
                "valid": valid_after,
                "invalid_objects": invalid_after,
                "objects_with_errors": errors_after
            }}

        except Exception as e:
            undone = False
            message = f"Failed to undo: {{str(e)}}"
            validation_after = None

        _result_ = {{
            "was_valid": False,
            "undone": undone,
            "invalid_objects": invalid_objects,
            "objects_with_errors": objects_with_errors,
            "message": message,
            "validation_after": validation_after
        }}
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success and result.result:
            return result.result
        return {
            "was_valid": False,
            "undone": False,
            "invalid_objects": [],
            "objects_with_errors": [],
            "message": result.error_traceback or "Operation failed",
            "validation_after": None,
        }

    @mcp.tool()
    async def safe_execute(
        code: str,
        doc_name: str | None = None,
        validate_after: bool = True,
        auto_undo_on_failure: bool = True,
    ) -> dict[str, Any]:
        """Execute Python code with automatic validation and rollback on failure.

        This tool provides transactional semantics for FreeCAD operations:
        1. Opens an undo transaction
        2. Executes the provided code
        3. Validates all objects
        4. Automatically rolls back if validation fails (optional)

        Use this for complex operations where you want automatic error recovery.

        Args:
            code: Python code to execute. Use _result_ = value to return data.
            doc_name: Target document. Uses active document if None.
            validate_after: Whether to validate objects after execution.
            auto_undo_on_failure: Whether to automatically undo if validation fails.

        Returns:
            Dictionary containing:
                - success: Whether the operation succeeded (execution + validation)
                - result: The value assigned to _result_ in the code (if any)
                - rolled_back: Whether a rollback was performed
                - execution_success: Whether the code executed without exceptions
                - execution_error: Any execution error message
                - validation: Validation results (if validate_after is True)
                - message: Human-readable summary

        Example:
            Execute code with automatic rollback on failure::

                result = await safe_execute('''
                box = doc.addObject("Part::Box", "MyBox")
                box.Length = 100
                _result_ = {"created": box.Name}
                ''')
                if result["success"]:
                    print(f"Created: {result['result']['created']}")
        """
        bridge = await get_bridge()

        # Escape the user code for embedding in the wrapper
        escaped_code = code.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')

        wrapper_code = f"""
import FreeCAD

doc_name = {doc_name!r}
validate_after = {validate_after!r}
auto_undo_on_failure = {auto_undo_on_failure!r}

# Get document
if doc_name:
    doc = FreeCAD.getDocument(doc_name)
else:
    doc = FreeCAD.ActiveDocument

if doc is None:
    _result_ = {{
        "success": False,
        "result": None,
        "rolled_back": False,
        "execution_success": False,
        "execution_error": "No active document found",
        "validation": None,
        "message": "No active document found"
    }}
else:
    # Start transaction
    doc.openTransaction("SafeExecute")

    execution_success = False
    execution_error = None
    user_result = None

    # Execute user code
    try:
        user_code = \"\"\"{escaped_code}\"\"\"
        exec_globals = {{"FreeCAD": FreeCAD, "App": FreeCAD, "doc": doc}}

        # Try to import common modules
        try:
            import Part
            exec_globals["Part"] = Part
        except ImportError:
            pass
        try:
            import PartDesign
            exec_globals["PartDesign"] = PartDesign
        except ImportError:
            pass
        try:
            import Sketcher
            exec_globals["Sketcher"] = Sketcher
        except ImportError:
            pass

        exec(user_code, exec_globals)

        if "_result_" in exec_globals:
            user_result = exec_globals["_result_"]

        execution_success = True
        doc.recompute()

    except Exception as e:
        execution_error = str(e)
        execution_success = False

    # Validate if requested
    validation = None
    validation_passed = True

    if validate_after and execution_success:
        invalid_objects = []
        objects_with_errors = []

        for obj in doc.Objects:
            state = list(obj.State) if hasattr(obj, 'State') else []

            if "Invalid" in state or "Error" in state:
                objects_with_errors.append(obj.Name)

            if hasattr(obj, 'Shape') and obj.Shape:
                try:
                    if not obj.Shape.isValid():
                        invalid_objects.append(obj.Name)
                except Exception:
                    invalid_objects.append(obj.Name)

        validation_passed = len(invalid_objects) == 0 and len(objects_with_errors) == 0
        validation = {{
            "valid": validation_passed,
            "invalid_objects": invalid_objects,
            "objects_with_errors": objects_with_errors
        }}

    # Determine if we need to rollback
    rolled_back = False
    if not execution_success or (validate_after and not validation_passed and auto_undo_on_failure):
        doc.abortTransaction()
        doc.recompute()
        rolled_back = True
    else:
        doc.commitTransaction()

    # Build message
    if execution_success and validation_passed:
        message = "Operation completed successfully"
    elif not execution_success:
        message = f"Execution failed: {{execution_error}}"
        if rolled_back:
            message += " (rolled back)"
    else:
        message = f"Validation failed: {{len(validation.get('invalid_objects', []))}} invalid objects"
        if rolled_back:
            message += " (rolled back)"

    overall_success = execution_success and (not validate_after or validation_passed)

    _result_ = {{
        "success": overall_success,
        "result": user_result,
        "rolled_back": rolled_back,
        "execution_success": execution_success,
        "execution_error": execution_error,
        "validation": validation,
        "message": message
    }}
"""
        result = await bridge.execute_python(wrapper_code, transaction=None)
        if result.success and result.result:
            return result.result
        return {
            "success": False,
            "result": None,
            "rolled_back": False,
            "execution_success": False,
            "execution_error": result.error_traceback or "Safe execute failed",
            "validation": None,
            "message": result.error_traceback or "Safe execute failed",
        }
