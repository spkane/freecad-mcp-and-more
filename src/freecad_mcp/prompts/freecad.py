"""FreeCAD Robust MCP prompts for common CAD tasks.

This module provides reusable prompt templates that help Claude
understand FreeCAD concepts and guide users through complex tasks.

Prompt Categories:
    - Design Workflows: Part design, sketching, modeling
    - Export/Import: File format handling
    - Analysis: Shape inspection, validation
    - Macro Development: Scripting guidance
    - Troubleshooting: Common issues and solutions
"""

from typing import Any


def register_prompts(mcp: Any, get_bridge: Any) -> None:  # noqa: ARG001
    """Register FreeCAD prompts with the Robust MCP Server.

    Args:
        mcp: The FastMCP (Robust MCP Server) instance.
        get_bridge: Async function to get the active bridge (unused but kept
            for interface consistency with other register functions).
    """
    # =========================================================================
    # Session Initialization Prompt (RECOMMENDED: Auto-load on connection)
    # =========================================================================

    @mcp.prompt()
    async def freecad_startup() -> str:
        """Essential startup guidance for AI assistants.

        **RECOMMENDED**: Configure your MCP client to automatically invoke
        this prompt when connecting to the FreeCAD MCP server. This provides
        critical context for reliable FreeCAD operations.

        This prompt provides:
        - Session initialization checklist
        - Critical patterns to follow
        - Version compatibility notes
        - Quick reference for common operations

        Returns:
            Essential startup guidance for FreeCAD MCP sessions.

        Example:
            Invoke via MCP prompt mechanism::

                # In an MCP client
                guidance = await mcp.get_prompt("freecad_startup")
                print(guidance)  # Displays session initialization checklist
        """
        return """# FreeCAD MCP Session Initialized

## IMPORTANT: Read Before Starting

You are connected to the FreeCAD Robust MCP Server. Follow these guidelines for reliable operations.

---

## Session Checklist (Do These First)

1. **Verify connection**: Call `get_connection_status()` to confirm FreeCAD is responding
2. **Check capabilities**: Read `freecad://best-practices` resource for detailed guidance
3. **Check GUI mode**: Call `get_freecad_version()` - note `gui_available` field
   - If `false`: Screenshot and visibility tools won't work (this is OK for modeling)

---

## Critical Rules

### Transaction Support (Undo/Redo)
**ALL tool operations are wrapped in transactions** - every change can be undone:
- Use `undo()` to revert any operation
- Use `redo()` to redo after undo
- Use `get_undo_redo_status()` to see available undo steps

### For Parametric Parts (PartDesign)
```
1. ALWAYS create Body first: create_partdesign_body(name="Body")
2. Create sketches ON the body: create_sketch(body_name="Body", plane="XY_Plane")
   # Note: On FreeCAD 1.x, sketch Support attribute is accessed differently
3. Extrude with: pad_sketch(sketch_name="...", length=...)
4. VALIDATE after each feature: validate_object(object_name="...")
```

### For Error Prevention
- **All operations support undo** - simply call `undo()` if something goes wrong
- **Use safe_execute()** for risky operations - auto-undoes on failure
- **Use validate_document()** to check all objects after complex operations
- **Ensure required modules are imported** (e.g., `import Sketcher, Part, FreeCAD`)
- **For FreeCAD 1.x compatibility**: Use `hasattr()` checks before accessing deprecated attributes like `Support`

### Version Compatibility
The MCP tools automatically handle FreeCAD version differences (1.0 vs older).
No special handling needed on your part.

---

## Quick Reference

| Task | Tool(s) |
|------|---------|
| Create parametric part | `create_partdesign_body` → `create_sketch` → `pad_sketch` |
| Simple primitive | `create_box`, `create_cylinder`, `create_sphere` |
| Combine shapes | `boolean_operation(operation="fuse/cut/common")` or `fuse_all` |
| Add sketch constraints | `constrain_horizontal`, `constrain_distance`, etc. |
| Check for errors | `validate_object` or `validate_document` |
| Debug issues | `get_console_output(lines=50)` |
| Undo any operation | `undo()` (all operations are undoable) |
| Safe execution | `safe_execute(code="...", validate_after=True)` |

---

## GUI-Only Tools (Skip in Headless Mode)

These require `gui_available=true`:
- `get_screenshot()`, `set_object_visibility()`, `set_object_color()`
- Camera controls: `zoom_in()`, `zoom_out()`, `set_view_angle()`

All other tools work in both GUI and headless modes.

---

For detailed guidance on specific tasks, use the `freecad-guidance` prompt with:
- `task_type="partdesign"` - Parametric modeling workflow
- `task_type="sketching"` - 2D sketch creation
- `task_type="boolean"` - Boolean operations
- `task_type="debugging"` - Troubleshooting
- `task_type="validation"` - Checking model health

Or read the full `freecad://best-practices` resource for comprehensive documentation.
"""

    # =========================================================================
    # AI Guidance Prompts
    # =========================================================================

    @mcp.prompt()
    async def freecad_guidance(task_type: str = "general") -> str:
        """Get AI guidance for specific FreeCAD task types.

        This prompt provides targeted best practices and reminders
        for different types of FreeCAD operations. Use at the start
        of a task to get relevant guidance.

        Args:
            task_type: Type of task - one of:
                - "general": Overall best practices
                - "partdesign": Parametric part creation
                - "sketching": 2D sketch creation
                - "boolean": Boolean operations
                - "export": File export operations
                - "debugging": Troubleshooting issues
                - "validation": Checking model health

        Returns:
            Targeted guidance for the task type.

        Example:
            Get PartDesign workflow guidance::

                guidance = await freecad_guidance(task_type="partdesign")
        """
        guidance = {
            "general": """# FreeCAD AI Assistant Guidance

## Before Starting Any Task
1. **Check connection**: Use `get_connection_status()` to verify FreeCAD connection
2. **Check GUI**: Use `get_freecad_version()` - GUI features only work if gui_available=true
3. **Check document**: Use `get_active_document()` or create one with `create_document()`

## Key Principles
- **All Operations are Undoable**: Every tool operation is wrapped in a transaction
- **Validate Early**: After any geometry creation, use `validate_object()` to check validity
- **Use safe_execute()**: For risky operations with automatic rollback on failure
- **Check Version Compatibility**: FreeCAD 1.x changed some APIs (see best-practices resource)

## Undo/Redo Support
All tool operations support undo:
- `undo()` - Reverts the last operation
- `redo()` - Redoes after undo
- `get_undo_redo_status()` - Shows available undo/redo steps
- `undo_if_invalid()` - Checks and reverts if geometry is invalid

## Error Recovery
- If something breaks: `undo()` reverts the last operation
- For batch issues: `undo_if_invalid()` checks and reverts if needed
- Always check `get_console_output()` for error messages

## GUI vs Headless
These tools require GUI mode (fail gracefully in headless):
- `get_screenshot()`, `set_object_visibility()`, `set_object_color()`
- Camera controls: `zoom_in()`, `zoom_out()`, `set_camera_position()`
All other tools work in both modes.""",
            "partdesign": """# PartDesign Workflow Guidance

## Undo Support
All PartDesign operations are wrapped in transactions - use `undo()` to revert any operation.

## Critical Rules
1. **Always create a Body first** - PartDesign features MUST be inside a Body
2. **Use body.newObject()** - Don't use doc.addObject() for PartDesign objects
3. **Attach sketches to planes** - XY_Plane, XZ_Plane, YZ_Plane, or existing faces

## Correct Workflow
```
1. create_document(name="MyPart")
2. create_partdesign_body(name="Body")
3. create_sketch(body_name="Body", plane="XY_Plane", name="BaseSketch")
4. add_sketch_rectangle(sketch_name="BaseSketch", x=-10, y=-10, width=20, height=20)
5. pad_sketch(sketch_name="BaseSketch", length=15)
6. validate_object(object_name="Pad")  # Check the result
```

## Version Compatibility
FreeCAD 1.x changed sketch attachment:
- Old: `sketch.Support = (plane, [''])`
- New: `sketch.AttachmentSupport = [(plane, '')]`
The MCP tools handle this automatically.

## Adding Features
- **Additive**: pad_sketch, revolution_sketch, loft_sketches, sweep_sketch
- **Subtractive**: pocket_sketch, groove_sketch, create_hole, subtractive_loft, subtractive_pipe
- **Modifiers**: fillet_edges, chamfer_edges, draft_feature, thickness_feature
- **Patterns**: linear_pattern, polar_pattern, mirrored_feature
- **Datums**: create_datum_plane, create_datum_line, create_datum_point

## Sketch Constraints
Use constraints to fully define sketches:
- Geometric: constrain_horizontal, constrain_vertical, constrain_parallel, constrain_perpendicular
- Dimensional: constrain_distance, constrain_radius, constrain_angle
- Special: constrain_coincident, constrain_tangent, constrain_equal, constrain_fix

## Common Mistakes
- Creating sketch without a body (will fail on pad)
- Using wrong plane name (must be exact: "XY_Plane" not "XY")
- Not closing sketch contour (pad requires closed profile)
- Not constraining sketches (use get_sketch_info to check degrees of freedom)""",
            "sketching": """# Sketch Creation Guidance

## Undo Support
All sketch operations are wrapped in transactions - use `undo()` to revert any operation.

## Basic Workflow
1. Create sketch attached to plane or face
2. Add geometry (rectangle, circle, line, arc, point, ellipse, polygon, slot, bspline)
3. Add constraints to fully define the geometry
4. Ensure sketch is closed for Pad/Pocket operations

## Available Sketch Geometry Tools
- `add_sketch_rectangle(sketch_name, x, y, width, height)`
- `add_sketch_circle(sketch_name, center_x, center_y, radius)`
- `add_sketch_line(sketch_name, x1, y1, x2, y2)`
- `add_sketch_arc(sketch_name, center_x, center_y, radius, start_angle, end_angle)`
- `add_sketch_point(sketch_name, x, y)` - for hole placement
- `add_sketch_ellipse(sketch_name, center_x, center_y, major_radius, minor_radius)`
- `add_sketch_polygon(sketch_name, center_x, center_y, sides, radius)`
- `add_sketch_slot(sketch_name, x1, y1, x2, y2, width)` - rounded rectangle
- `add_sketch_bspline(sketch_name, points)` - smooth curve through points

## Constraint Tools
- `constrain_horizontal(sketch_name, geometry_index)` - make line horizontal
- `constrain_vertical(sketch_name, geometry_index)` - make line vertical
- `constrain_distance(sketch_name, value, geo1, point1, ...)` - set distance
- `constrain_radius(sketch_name, geometry_index, value)` - set radius
- `constrain_coincident(sketch_name, geo1, point1, geo2, point2)` - join points
- `constrain_parallel(sketch_name, geo1, geo2)` - make lines parallel
- `constrain_perpendicular(sketch_name, geo1, geo2)` - make lines perpendicular
- `get_sketch_info(sketch_name)` - check degrees of freedom

## Coordinate System
- X, Y coordinates are in the sketch plane
- Origin (0, 0) is at plane center
- Use negative values for left/down from center

## Closed Profiles
For Pad/Pocket operations, sketches must be closed:
- Rectangle, Circle, Ellipse, Polygon: automatically closed
- Lines/Arcs: must connect to form closed loop

## Tips
- Start simple: rectangle or circle first
- Build complex shapes with multiple sketch elements
- Use `add_sketch_point` for hole features (then `create_hole`)
- Use `get_sketch_info` to check if fully constrained (0 DOF)
- Use `toggle_construction` for reference geometry""",
            "boolean": """# Boolean Operations Guidance

## Available Operations
- **fuse** (union): Combines shapes into one
- **cut** (difference): Removes second shape from first
- **common** (intersection): Keeps only overlapping region

## Tool Usage
```
boolean_operation(
    operation="fuse",  # or "cut" or "common"
    object1="Box",     # Base shape
    object2="Cylinder", # Tool shape
    result_name="FusedShape"  # Optional result name
)
```

## Prerequisites
- Both shapes must be **solids** (not curves, meshes, or compounds)
- Shapes should **overlap** for meaningful results
- Both objects must have **valid geometry**

## Validation Pattern
```
# Before boolean
validate_object(object_name="Box")
validate_object(object_name="Cylinder")

# Perform operation
boolean_operation(operation="fuse", object1="Box", object2="Cylinder")

# After boolean
validate_object(object_name="Fused")  # Check result is valid
```

## Common Issues
- **Empty result**: Shapes don't overlap - check positions
- **Invalid result**: Source shape has bad geometry
- **Fails completely**: Wrong shape type (mesh vs solid)

## Recovery
If boolean fails:
1. `undo()` to revert
2. Check source shapes with `validate_object()`
3. Ensure shapes actually intersect
4. Try simplifying geometry""",
            "export": """# Export Operations Guidance

## Available Formats
| Format | Tool | Best For |
|--------|------|----------|
| STEP | `export_step()` | CAD interchange, precise geometry |
| STL | `export_stl()` | 3D printing (mesh format) |
| 3MF | `export_3mf()` | 3D printing with color/material |
| OBJ | `export_obj()` | Graphics, rendering, games |
| IGES | `export_iges()` | Legacy CAD systems |

## Pre-Export Checklist
1. `validate_document()` - Ensure all objects are valid
2. `list_objects()` - Verify correct objects will export
3. `recompute_document()` - Force update before export

## Export Tips
- Specify `object_names` list to export specific objects
- Omit `object_names` to export all visible objects
- Use absolute paths for `file_path`

## Import Formats
- `import_step()` - Preserves precise CAD geometry
- `import_stl()` - Imports as mesh (may need conversion for CAD ops)

## Common Issues
- **Export fails**: Object has invalid shape
- **Missing objects**: Object not visible or wrong document
- **Wrong file**: Path error or permission issue""",
            "debugging": """# Debugging Guidance

## First Steps
1. `get_console_output(lines=50)` - Check for error messages
2. `validate_document()` - Find all invalid objects
3. `list_objects()` - See document structure

## Object Investigation
```
inspect_object(object_name="ProblemObject")
```
Check these fields:
- `state`: Should be empty; "Error" or "Invalid" indicates problems
- `is_valid` in shape_info: Geometry validity
- `type_id`: Ensure correct object type

## Common Problems

### "Object not found"
- Wrong name (case-sensitive)
- Wrong document (check `get_active_document()`)
- Object was deleted

### Invalid Shape
- Geometry computation failed
- Check parent objects (sketch, body)
- `undo()` and try simpler approach

### Recompute Errors
- Circular dependencies
- Invalid parent objects
- `recompute_document()` after fixing

## Recovery Steps
1. `undo()` - Revert last operation
2. `validate_document()` - Check what's broken
3. Fix or delete problem objects
4. `recompute_document()` - Refresh everything

## Using safe_execute
For risky operations:
```
safe_execute(
    code="... risky Python code ...",
    validate_after=True,
    auto_undo_on_failure=True
)
```
Automatically reverts if validation fails.""",
            "validation": """# Validation Guidance

## Transaction Support
**All MCP tool operations are wrapped in transactions** - this means:
- Every operation can be undone with `undo()`
- Use `get_undo_redo_status()` to see available undo steps
- Transaction names appear in FreeCAD's Edit > Undo menu

## Validation Tools

### validate_object(object_name, doc_name)
Checks a single object:
- `is_valid`: Shape geometry is valid
- `has_shape`: Object has geometry
- `state`: Error flags from FreeCAD
- `error_messages`: Human-readable errors

### validate_document(doc_name)
Checks all objects in document:
- `overall_valid`: True if ALL objects valid
- `invalid_count`: Number of problem objects
- `invalid_objects`: List of problem object names
- `objects`: Detailed status of each object

### undo_if_invalid(doc_name)
Checks document and auto-undoes if problems:
- Runs validation
- If invalid objects found, calls undo()
- Returns both validation and undo results

### safe_execute(code, validate_after, auto_undo_on_failure)
Protected code execution:
- Wraps code in transaction
- Validates result if validate_after=True
- Auto-reverts if validation fails and auto_undo_on_failure=True

## Validation Pattern
After any operation:
```
# Option 1: Simple undo if something goes wrong
create_box(length=10, width=10, height=10)
# Oops, wrong size
undo()  # Reverts the box creation

# Option 2: Manual validation
result = validate_object(object_name="NewFeature")
if not result["is_valid"]:
    undo()
    # Try different approach

# Option 3: Automatic protection
safe_execute(
    code="...",
    validate_after=True,
    auto_undo_on_failure=True
)
```

## What Gets Checked
- Shape.isValid() - Geometry integrity
- Object.State - FreeCAD error flags
- Shape existence - Object has geometry
- Recompute state - Object up to date""",
        }

        return guidance.get(task_type, guidance["general"])

    # =========================================================================
    # Design Workflow Prompts
    # =========================================================================

    @mcp.prompt()
    async def design_part(
        description: str,
        units: str = "mm",
    ) -> str:
        """Generate a guided workflow for designing a parametric part.

        Use this prompt when a user wants to create a new part from scratch.
        It provides step-by-step guidance for the PartDesign workflow.

        Args:
            description: Natural language description of the desired part.
            units: Unit system to use (mm, cm, m, in).

        Returns:
            Structured prompt guiding through part design.
        """
        return f"""# FreeCAD Part Design Workflow

## Part Description
{description}

## Recommended Approach

### 1. Create a New Document
First, create a new document for this part:
- Use `create_document` with a descriptive name

### 2. Set Up PartDesign Body
Create a PartDesign body to contain the parametric features:
- Use `create_partdesign_body` to create the body container
- This enables the parametric workflow with features

### 3. Create Base Sketch
Design the base profile:
- Use `create_sketch` on the XY plane (or appropriate plane)
- Add geometry with `add_sketch_rectangle`, `add_sketch_circle`, etc.
- Close the sketch when complete

### 4. Extrude the Base
Create the base 3D shape:
- Use `pad_sketch` to extrude the sketch
- Specify length in {units}

### 5. Add Features
Add additional features as needed:
- `pocket_sketch` for cuts/holes
- `fillet_edges` for rounded edges
- `chamfer_edges` for beveled edges

### 6. Verify and Export
When complete:
- Use `inspect_object` to verify dimensions
- Use `get_screenshot` to visualize the result
- Export with `export_step` or `export_stl` as needed

## Units
All dimensions should be specified in **{units}**.
"""

    @mcp.prompt()
    async def create_sketch_guide(
        shape_type: str = "rectangle",
        plane: str = "XY",
    ) -> str:
        """Guide for creating 2D sketches for part design.

        Args:
            shape_type: Type of shape (rectangle, circle, polygon).
            plane: Sketch plane (XY, XZ, YZ).

        Returns:
            Sketch creation guidance.
        """
        return f"""# FreeCAD Sketch Creation Guide

## Target Shape: {shape_type}
## Sketch Plane: {plane}

### Step 1: Create Sketch
Use `create_sketch` with plane="{plane}" to start a new sketch.

### Step 2: Add Geometry

{"#### Rectangle" if shape_type == "rectangle" else ""}
{"Use `add_sketch_rectangle` with:" if shape_type == "rectangle" else ""}
{"- x, y: Starting corner position" if shape_type == "rectangle" else ""}
{"- width, height: Rectangle dimensions" if shape_type == "rectangle" else ""}

{"#### Circle" if shape_type == "circle" else ""}
{"Use `add_sketch_circle` with:" if shape_type == "circle" else ""}
{"- x, y: Center position" if shape_type == "circle" else ""}
{"- radius: Circle radius" if shape_type == "circle" else ""}

{"#### Custom Polygon" if shape_type == "polygon" else ""}
{"Use `execute_python` with Part.makePolygon() for custom shapes." if shape_type == "polygon" else ""}

### Step 3: Constrain the Sketch
For a fully constrained sketch:
- All geometry should have defined positions
- No free degrees of freedom

### Step 4: Close and Use
The sketch can then be:
- Padded (extruded) with `pad_sketch`
- Pocketed (cut) with `pocket_sketch`
- Revolved with `execute_python` using PartDesign Revolution
"""

    @mcp.prompt()
    async def boolean_operations_guide() -> str:
        """Guide for performing boolean operations on shapes.

        Returns:
            Boolean operations guidance.
        """
        return """# FreeCAD Boolean Operations Guide

Boolean operations combine two or more shapes into a new shape.

## Available Operations

### 1. Fuse (Union)
Combines two shapes into one:
```
boolean_operation(
    object1="Box",
    object2="Cylinder",
    operation="fuse",
    result_name="FusedShape"
)
```

### 2. Cut (Difference)
Removes the second shape from the first:
```
boolean_operation(
    object1="Box",
    object2="Cylinder",
    operation="cut",
    result_name="CutShape"
)
```

### 3. Common (Intersection)
Keeps only the overlapping region:
```
boolean_operation(
    object1="Box",
    object2="Cylinder",
    operation="common",
    result_name="CommonShape"
)
```

## Tips
- Shapes must overlap for meaningful results
- The original objects remain in the document
- Use `set_object_visibility` to hide originals after operation
- Recompute the document after boolean operations
"""

    # =========================================================================
    # Export/Import Prompts
    # =========================================================================

    @mcp.prompt()
    async def export_guide(target_format: str = "STEP") -> str:
        """Guide for exporting FreeCAD models to various formats.

        Args:
            target_format: Target export format (STEP, STL, OBJ, IGES).

        Returns:
            Export guidance for the specified format.
        """
        format_info = {
            "STEP": {
                "tool": "export_step",
                "extension": ".step",
                "description": "Standard for exchanging 3D CAD data between systems",
                "best_for": "CAD interchange, preserves geometry precisely",
                "params": "file_path, object_names (optional)",
            },
            "STL": {
                "tool": "export_stl",
                "extension": ".stl",
                "description": "Triangulated mesh format",
                "best_for": "3D printing, mesh-based workflows",
                "params": "file_path, object_names (optional), mesh_tolerance (default 0.1)",
            },
            "OBJ": {
                "tool": "export_obj",
                "extension": ".obj",
                "description": "Wavefront OBJ mesh format",
                "best_for": "3D graphics, rendering, game engines",
                "params": "file_path, object_names (optional)",
            },
            "IGES": {
                "tool": "export_iges",
                "extension": ".iges",
                "description": "Initial Graphics Exchange Specification",
                "best_for": "Legacy CAD systems, surface data",
                "params": "file_path, object_names (optional)",
            },
        }

        info = format_info.get(target_format.upper(), format_info["STEP"])

        return f"""# FreeCAD Export Guide: {target_format.upper()}

## Format: {target_format.upper()} ({info["extension"]})
{info["description"]}

**Best for:** {info["best_for"]}

## Export Command
Use the `{info["tool"]}` tool with parameters:
- {info["params"]}

## Example
```python
{info["tool"]}(
    file_path="/path/to/output{info["extension"]}",
    object_names=["Part1", "Part2"]  # Optional: exports all if not specified
)
```

## Pre-Export Checklist
1. Verify all objects are visible with `list_objects`
2. Check object validity with `inspect_object`
3. Recompute document if needed: `recompute_document`
4. Consider using `fit_all` and `get_screenshot` to verify visually

## Post-Export
- Verify the exported file exists
- Check file size is reasonable
- Test import in target application if possible
"""

    @mcp.prompt()
    async def import_guide(source_format: str = "STEP") -> str:
        """Guide for importing models into FreeCAD.

        Args:
            source_format: Source file format (STEP, STL).

        Returns:
            Import guidance for the specified format.
        """
        format_info = {
            "STEP": {
                "tool": "import_step",
                "description": "Imports precise CAD geometry",
                "notes": "Preserves feature boundaries, faces, and edges",
            },
            "STL": {
                "tool": "import_stl",
                "description": "Imports triangulated mesh",
                "notes": "Results in Mesh object, may need conversion for CAD operations",
            },
        }

        info = format_info.get(source_format.upper(), format_info["STEP"])

        return f"""# FreeCAD Import Guide: {source_format.upper()}

## Format: {source_format.upper()}
{info["description"]}

**Notes:** {info["notes"]}

## Import Command
Use the `{info["tool"]}` tool:
```python
{info["tool"]}(
    file_path="/path/to/file.{source_format.lower()}",
    doc_name="TargetDocument"  # Optional
)
```

## Post-Import Steps
1. List imported objects: `list_objects`
2. Inspect geometry: `inspect_object` on each object
3. Adjust view: `fit_all` to see all imported geometry
4. Take screenshot: `get_screenshot` to verify import

## Common Issues
- Large files may take time to process
- Complex geometry may create many objects
- STL meshes need conversion for boolean operations
"""

    # =========================================================================
    # Analysis Prompts
    # =========================================================================

    @mcp.prompt()
    async def analyze_shape() -> str:
        """Guide for analyzing shape geometry and properties.

        Returns:
            Shape analysis guidance.
        """
        return """# FreeCAD Shape Analysis Guide

## Quick Analysis
Use `inspect_object` with `include_shape=True` to get:
- Volume
- Surface area
- Bounding box
- Vertex/edge/face counts
- Validity status

## Detailed Analysis with Python

### Bounding Box
```python
execute_python('''
obj = FreeCAD.ActiveDocument.getObject("ObjectName")
bb = obj.Shape.BoundBox
_result_ = {
    "min": [bb.XMin, bb.YMin, bb.ZMin],
    "max": [bb.XMax, bb.YMax, bb.ZMax],
    "size": [bb.XLength, bb.YLength, bb.ZLength],
    "center": [bb.Center.x, bb.Center.y, bb.Center.z]
}
''')
```

### Center of Mass
```python
execute_python('''
obj = FreeCAD.ActiveDocument.getObject("ObjectName")
com = obj.Shape.CenterOfMass
_result_ = {"x": com.x, "y": com.y, "z": com.z}
''')
```

### Moments of Inertia
```python
execute_python('''
obj = FreeCAD.ActiveDocument.getObject("ObjectName")
moi = obj.Shape.MatrixOfInertia
_result_ = {
    "Ixx": moi.A11, "Iyy": moi.A22, "Izz": moi.A33,
    "Ixy": moi.A12, "Ixz": moi.A13, "Iyz": moi.A23
}
''')
```

## Validation
Check for geometry issues:
```python
execute_python('''
obj = FreeCAD.ActiveDocument.getObject("ObjectName")
shape = obj.Shape
_result_ = {
    "is_valid": shape.isValid(),
    "is_closed": shape.isClosed() if hasattr(shape, 'isClosed') else None,
    "has_shape": shape.ShapeType != "Compound" or len(shape.Solids) > 0
}
''')
```
"""

    @mcp.prompt()
    async def debug_model() -> str:
        """Guide for debugging FreeCAD model issues.

        Returns:
            Model debugging guidance.
        """
        return """# FreeCAD Model Debugging Guide

## Common Issues and Solutions

### 1. Recompute Errors
**Symptom:** Objects show error state, model doesn't update
**Solution:**
```python
recompute_document()  # Force full recompute
```

### 2. Invalid Shape
**Symptom:** Boolean operations fail, export errors
**Diagnosis:**
```python
execute_python('''
obj = FreeCAD.ActiveDocument.getObject("ObjectName")
_result_ = {
    "valid": obj.Shape.isValid(),
    "type": obj.Shape.ShapeType,
    "check": obj.Shape.check() if hasattr(obj.Shape, 'check') else "N/A"
}
''')
```

### 3. Sketch Not Fully Constrained
**Symptom:** Sketch geometry moves unexpectedly
**Check constraints:**
```python
execute_python('''
sketch = FreeCAD.ActiveDocument.getObject("SketchName")
_result_ = {
    "dof": sketch.solve(),  # Degrees of freedom
    "constraint_count": sketch.ConstraintCount,
    "geometry_count": sketch.GeometryCount
}
''')
```

### 4. Object Dependencies
**Symptom:** Can't delete object, unexpected behavior
**Check dependencies:**
```python
inspect_object("ObjectName")  # Check children and parents
```

### 5. View Not Updating
**Symptom:** Display doesn't match model
**Solution:**
```python
fit_all()  # Reset view
get_screenshot()  # Force view update
```

## Diagnostic Workflow
1. `list_objects` - See all objects and their states
2. `inspect_object` on problematic objects
3. `get_console_output` - Check for error messages
4. `recompute_document` - Force update
5. `get_screenshot` - Visual verification
"""

    # =========================================================================
    # Macro Development Prompts
    # =========================================================================

    @mcp.prompt()
    async def macro_development() -> str:
        """Guide for developing FreeCAD macros.

        Returns:
            Macro development guidance.
        """
        return """# FreeCAD Macro Development Guide

## Macro Structure
A FreeCAD macro is a Python script that automates tasks.

### Basic Template
```python
# -*- coding: utf-8 -*-
# Macro: MacroName
# Description: What the macro does

import FreeCAD
import FreeCADGui

def main():
    # Get active document
    doc = FreeCAD.ActiveDocument
    if doc is None:
        FreeCAD.Console.PrintError("No active document\\n")
        return

    # Your code here

    doc.recompute()
    FreeCAD.Console.PrintMessage("Macro completed\\n")

if __name__ == "__main__":
    main()
```

## Creating a Macro
Use `create_macro` to save a macro:
```python
create_macro(
    name="MyMacro",
    code="... macro code ...",
    description="What it does"
)
```

Or use a template:
```python
create_macro_from_template(
    template_name="part",  # basic, part, sketch, gui, selection
    macro_name="MyPartMacro"
)
```

## Available Templates
- **basic**: Minimal template
- **part**: Part creation with primitives
- **sketch**: 2D sketch operations
- **gui**: GUI interaction with message boxes
- **selection**: Working with selected objects

## Running Macros
```python
run_macro("MacroName")
```

## Best Practices
1. Always check for active document
2. Use FreeCAD.Console for output
3. Call doc.recompute() after changes
4. Handle exceptions gracefully
5. Add descriptive comments
"""

    @mcp.prompt()
    async def python_api_reference() -> str:
        """Quick reference for common FreeCAD Python API operations.

        Returns:
            Python API reference.
        """
        return """# FreeCAD Python API Quick Reference

## Document Operations
```python
# Create/get documents
doc = FreeCAD.newDocument("Name")
doc = FreeCAD.ActiveDocument
doc = FreeCAD.getDocument("Name")

# Document methods
doc.recompute()
doc.save()
doc.saveAs("/path/to/file.FCStd")
```

## Object Operations
```python
# Create objects
box = doc.addObject("Part::Box", "MyBox")
cyl = doc.addObject("Part::Cylinder", "MyCyl")

# Get objects
obj = doc.getObject("ObjectName")
all_objs = doc.Objects

# Modify properties
obj.Length = 100
obj.Placement = FreeCAD.Placement(
    FreeCAD.Vector(x, y, z),
    FreeCAD.Rotation(axis, angle)
)

# Delete
doc.removeObject("ObjectName")
```

## Part Module
```python
import Part

# Primitives
box = Part.makeBox(l, w, h)
cyl = Part.makeCylinder(r, h)
sphere = Part.makeSphere(r)

# Boolean operations
fused = shape1.fuse(shape2)
cut = shape1.cut(shape2)
common = shape1.common(shape2)

# Create from shape
Part.show(shape, "Name")
```

## Sketcher Module
```python
import Sketcher

# Create sketch
sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
sketch.MapMode = "FlatFace"

# Add geometry
sketch.addGeometry(Part.LineSegment(p1, p2))
sketch.addGeometry(Part.Circle(center, normal, radius))

# Add constraints
sketch.addConstraint(Sketcher.Constraint("Coincident", 0, 1, 1, 2))
sketch.addConstraint(Sketcher.Constraint("Horizontal", 0))
```

## GUI Operations
```python
import FreeCADGui as Gui

# View control
view = Gui.ActiveDocument.ActiveView
view.viewIsometric()
view.fitAll()
view.saveImage("/path/to/image.png", 800, 600)

# Object visibility
obj.ViewObject.Visibility = True/False
obj.ViewObject.ShapeColor = (r, g, b)  # 0.0-1.0
```

## Vectors and Placement
```python
# Vector operations
v = FreeCAD.Vector(x, y, z)
v.Length
v.normalize()
v1.cross(v2)
v1.dot(v2)

# Placement
p = FreeCAD.Placement()
p.Base = FreeCAD.Vector(x, y, z)
p.Rotation = FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 45)
```
"""

    # =========================================================================
    # Troubleshooting Prompts
    # =========================================================================

    @mcp.prompt()
    async def troubleshooting() -> str:
        """General troubleshooting guide for FreeCAD Robust MCP.

        Returns:
            Troubleshooting guidance.
        """
        return """# FreeCAD Robust MCP Troubleshooting Guide

## Connection Issues

### Cannot Connect to FreeCAD
1. Verify FreeCAD is running (for socket/xmlrpc modes)
2. Check the MCP plugin is started in FreeCAD
3. Verify port numbers match (default: 9876 socket, 9875 xmlrpc)

**Check status:**
```python
get_connection_status()
```

### Connection Drops
- FreeCAD may be busy with long operations
- Try increasing timeout values
- Check FreeCAD console for errors

## Execution Issues

### Code Execution Timeout
- Increase timeout_ms parameter
- Break complex operations into smaller steps
- Check for infinite loops in code

### No Result Returned
- Ensure you set `_result_ = value` in your code
- Check for exceptions in stderr

**Debug execution:**
```python
execute_python('''
try:
    # Your code
    _result_ = {"success": True, "data": result}
except Exception as e:
    _result_ = {"success": False, "error": str(e)}
''')
```

## GUI Issues

### Screenshots Fail
- Ensure GUI mode is available: `get_freecad_version()`
- Check for active document and view
- Verify view type supports screenshots

### View Not Updating
```python
recompute_document()
fit_all()
```

## Model Issues

### Boolean Operation Fails
- Check shapes are valid
- Ensure shapes overlap
- Try with simpler geometry first

### Export Fails
- Verify objects have valid shapes
- Check file path is writable
- Ensure correct format for geometry type

## Getting Help
1. Check console output: `get_console_output()`
2. Inspect problematic objects: `inspect_object()`
3. Verify document state: `list_documents()`, `list_objects()`
"""
