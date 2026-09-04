"""FreeCAD Robust MCP prompts for common CAD tasks.

This module provides reusable prompt templates that help Claude
understand FreeCAD concepts and guide users through complex tasks.

Prompt Categories:
    - Design Workflows: Part design, sketching, modeling
    - Export/Import: File format handling
    - Analysis: Shape inspection, validation
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
Document mutation tools use transactions where FreeCAD supports undo:
- Use `undo()` to revert any operation
- Use `redo()` to redo after undo

### For Parametric Parts (PartDesign)
```
1. ALWAYS create Body first: create_partdesign_body(name="Body")
2. Create sketches ON the body: create_sketch(body_name="Body", plane="XY_Plane")
3. Extrude with: pad_sketch(sketch_name="...", length=...)
4. VALIDATE after each feature: validate_object(object_name="...")
```

### For Error Prevention
- **Use transactional mutation tools** so failed changes can roll back
- **Use validate_document()** to check all objects after complex operations

### Version Compatibility
FreeCAD 1.0 or newer is required. The server rejects older releases because the
native PartDesign, attachment, and variable APIs are not compatible.

---

## Quick Reference

| Task | Tool(s) |
|------|---------|
| Create parametric part | `create_partdesign_body` → `create_sketch` → `pad_sketch` |
| Add sketch constraints | `constrain_horizontal`, `constrain_distance`, etc. |
| Check for errors | `validate_object` or `validate_document` |
| Debug issues | `get_console_output(lines=50)` |
| Undo a document mutation | `undo()` when the tool uses a transaction |

---

## GUI-Only Tools (Skip in Headless Mode)

These require `gui_available=true`:
- `get_screenshot()`, `set_object_visibility()`
- View angle: `set_view_angle()`

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
- **Check Version Compatibility**: FreeCAD 1.x changed some APIs (see best-practices resource)

## Undo/Redo Support
All tool operations support undo:
- `undo()` - Reverts the last operation
- `redo()` - Redoes after undo

## Error Recovery
- If something breaks: `undo()` reverts the last operation
- Always check `get_console_output()` for error messages

## GUI vs Headless
These tools require GUI mode (fail gracefully in headless):
- `get_screenshot()`, `set_object_visibility()`
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

## Version Requirement
FreeCAD 1.0 or newer is required. Sketch attachment uses the native
`sketch.AttachmentSupport = [(plane, '')]` property.

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

""",
            "validation": """# Validation Guidance

## Transaction Support
**All MCP tool operations are wrapped in transactions** - this means:
- Every operation can be undone with `undo()`
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

## Validation Pattern
After any operation:
```
# Simple undo if something goes wrong
undo()  # Reverts the last operation

# Manual validation
result = validate_object(object_name="NewFeature")
if not result["is_valid"]:
    undo()
    # Try different approach
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
{"Use add_sketch_polygon() for regular polygons, or use Python code for custom shapes." if shape_type == "polygon" else ""}

### Step 3: Constrain the Sketch
For a fully constrained sketch:
- All geometry should have defined positions
- No free degrees of freedom

### Step 4: Close and Use
The sketch can then be:
- Padded (extruded) with `pad_sketch`
- Pocketed (cut) with `pocket_sketch`
- Revolved with `revolution_sketch`
"""

    @mcp.prompt()
    async def boolean_operations_guide() -> str:
        """Guide for performing boolean operations on shapes.

        Returns:
            Boolean operations guidance.
        """
        return """# FreeCAD Boolean Operations Guide

Boolean operations for PartDesign are performed through native PartDesign features
(pad, pocket, revolution, groove) or through Python code using Part module operations.

## Available PartDesign Operations

### Additive (Fuse-like)
- `pad_sketch` - Extrude a sketch to add material
- `revolution_sketch` - Revolve a sketch to add material
- `loft_sketches` - Loft between sketches to add material

### Subtractive (Cut-like)
- `pocket_sketch` - Cut material using a sketch
- `groove_sketch` - Remove material by revolving a sketch
- `create_hole` - Create parametric holes

## Tips
- Use `set_object_visibility` to show/hide objects
- Validate after each feature with `validate_object`
- Use `validate_document` to check all objects at once
"""

    # =========================================================================
    # Export/Import Prompts
    # =========================================================================

    @mcp.prompt()
    async def export_guide(target_format: str = "STEP") -> str:
        """Guide for exporting FreeCAD models to various formats.

        Args:
            target_format: Target export format (STEP, STL).

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
            source_format: Source file format (STEP).

        Returns:
            Import guidance for the specified format.
        """
        format_info = {
            "STEP": {
                "tool": "import_step",
                "description": "Imports precise CAD geometry",
                "notes": "Preserves feature boundaries, faces, and edges",
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

## Validation
Use `validate_object` to check geometry:
- `validate_object(object_name="ObjectName")` returns shape validity, volume, area, and error state.
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
**Solution:** Use `recompute_document()` to force a full recompute.

### 2. Invalid Shape
**Symptom:** Export fails, operations fail
**Diagnosis:**
```python
validate_object(object_name="ObjectName")
```

### 3. Sketch Not Fully Constrained
**Symptom:** Sketch geometry moves unexpectedly
**Check constraints:**
```python
get_sketch_info(sketch_name="SketchName")  # Check degrees of freedom
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
