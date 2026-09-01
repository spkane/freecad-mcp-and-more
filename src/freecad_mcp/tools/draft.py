"""Draft tools for FreeCAD Robust MCP Server.

This module provides tools for the Draft workbench, with a focus on
ShapeString for creating 3D text geometry that can be used with PartDesign.
"""

from collections.abc import Awaitable, Callable
from typing import Any


def _validate_vector(
    value: list[float] | None,
    expected_len: int,
    name: str,
    default: list[float],
    *,
    allow_zero: bool = True,
) -> list[float]:
    """Validate a vector parameter.

    Args:
        value: The vector value to validate, or None to use default.
        expected_len: Expected number of elements (e.g., 2 for 2D, 3 for 3D).
        name: Parameter name for error messages.
        default: Default value to return when value is None.
        allow_zero: Whether to allow zero-magnitude vectors. Defaults to True.

    Returns:
        The validated vector as a list of floats.

    Raises:
        ValueError: If vector length doesn't match expected_len.
        ValueError: If allow_zero is False and all components are zero.

    Example:
        Validate a 3D position vector::

            pos = _validate_vector([1.0, 2.0, 3.0], 3, "position", [0, 0, 0])
            # Returns [1.0, 2.0, 3.0]

            pos = _validate_vector(None, 3, "position", [0, 0, 0])
            # Returns default [0, 0, 0]

            _validate_vector([1.0, 2.0], 3, "position", [0, 0, 0])
            # Raises ValueError: position must have exactly 3 elements
    """
    if value is None:
        return default
    if len(value) != expected_len:
        raise ValueError(
            f"{name} must have exactly {expected_len} elements, got {len(value)}"
        )
    if not allow_zero and all(v == 0 for v in value):
        raise ValueError(f"{name} cannot be a zero vector")
    return value


def register_draft_tools(mcp: Any, get_bridge: Callable[[], Awaitable[Any]]) -> None:
    """Register Draft-related tools with the Robust MCP Server.

    Registers tools for the Draft workbench, primarily focused on ShapeString
    functionality for creating 3D text geometry that can be used with
    PartDesign for embossing, engraving, and extrusion workflows.

    Args:
        mcp: The FastMCP (Robust MCP Server) instance.
        get_bridge: Async function to get the active bridge.

    Returns:
        None. Tools are registered as side effect on the mcp instance.

    Raises:
        TypeError: If mcp does not have a tool() decorator method.
        TypeError: If get_bridge is not callable.

    Example:
        Register draft tools with an MCP server::

            from freecad_mcp.tools.draft import register_draft_tools

            register_draft_tools(mcp, get_bridge)
            # Now draft_shapestring, draft_list_fonts, etc. are available
    """
    # Validate mcp parameter has a callable tool attribute
    if not hasattr(mcp, "tool") or not callable(mcp.tool):
        raise TypeError("mcp must have a callable 'tool' attribute (decorator method)")

    # Validate get_bridge is callable
    if not callable(get_bridge):
        raise TypeError(
            "get_bridge must be a callable that returns an awaitable bridge"
        )

    @mcp.tool()
    async def draft_shapestring(
        text: str,
        font_path: str | None = None,
        size: float = 10.0,
        position: list[float] | None = None,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a ShapeString (3D text geometry) using Draft workbench.

        ShapeString creates text as 3D wire geometry that can be extruded,
        converted to a sketch, or used with PartDesign for embossing/engraving.

        Args:
            text: The text string to create.
            font_path: Path to a TrueType (.ttf) or OpenType (.otf) font file.
                If None, uses FreeCAD's default font.
            size: Font size in mm. Defaults to 10.0.
            position: Position as [x, y, z]. Defaults to origin [0, 0, 0].
            name: Object name. Auto-generated if None.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with created ShapeString information:
                - name: Object name (prefers Label if set, falls back to Name)
                - label: Object label
                - type_id: Object type
                - text: The text that was created
                - size: Font size used
                - font: Font path used

        Raises:
            ValueError: If position has incorrect number of elements (not 3).
            ValueError: If font_path is specified but file does not exist.
            ValueError: If no font_path is specified and no default font found.
            ValueError: If ShapeString creation fails (e.g., invalid font).

        Example:
            Create 3D text::

                result = await draft_shapestring(
                    text="Hello",
                    size=15.0,
                    position=[0, 0, 0]
                )
        """
        bridge = await get_bridge()
        pos = _validate_vector(position, 3, "position", [0, 0, 0])

        code = f"""
import Draft
import os

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    doc = FreeCAD.newDocument("Unnamed")

# Wrap in transaction for undo support
doc.openTransaction("Create ShapeString")
try:
    text = {text!r}
    size = {size!r}
    pos = FreeCAD.Vector({pos[0]}, {pos[1]}, {pos[2]})

    # Determine font path
    font_path = {font_path!r}
    if font_path is None:
        # Try to find a default font
        # Common locations on different platforms
        default_fonts = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
            "/usr/share/fonts/TTF/DejaVuSans.ttf",  # Arch Linux
            "/System/Library/Fonts/Helvetica.ttc",  # macOS
            "/Library/Fonts/Arial.ttf",  # macOS alternative
            "C:/Windows/Fonts/arial.ttf",  # Windows
        ]
        for fp in default_fonts:
            if os.path.exists(fp):
                font_path = fp
                break
        if font_path is None:
            raise ValueError("No font file specified and no default font found. "
                           "Please provide a font_path parameter.")

    if not os.path.exists(font_path):
        raise ValueError(f"Font file not found: {{font_path}}")

    # Create the ShapeString
    shape_string = Draft.make_shapestring(text, font_path, size)

    if shape_string is None:
        raise ValueError("Failed to create ShapeString - check font file and text")

    # Set position
    shape_string.Placement.Base = pos

    # Rename if custom name provided
    if {name!r}:
        shape_string.Label = {name!r}

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": shape_string.Label if shape_string.Label else shape_string.Name,
        "label": shape_string.Label,
        "type_id": shape_string.TypeId,
        "text": text,
        "size": size,
        "font": font_path,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success and result.result:
            return result.result
        raise ValueError(result.error_traceback or "Failed to create ShapeString")

    @mcp.tool()
    async def draft_list_fonts() -> dict[str, Any]:
        """List available font files on the system.

        Searches common font directories for TrueType (.ttf), OpenType (.otf),
        and TrueType Collection (.ttc) fonts that can be used with ShapeString.

        Note: For .ttc files, FreeCAD only uses the first font in the collection.

        Args:
            None.

        Returns:
            Dictionary with font information:
                - fonts: List of dictionaries with font details:
                    - name: Font filename
                    - path: Full path to font file
                    - type: Font type ("ttf", "otf", or "ttc")
                - count: Total number of fonts found
                - directories: Directories that were searched

        Raises:
            ValueError: If the bridge fails to execute the font search.

        Example:
            List available fonts::

                result = await draft_list_fonts()
                for font in result["fonts"][:10]:  # First 10 fonts
                    print(f"{font['name']}: {font['path']}")
        """
        bridge = await get_bridge()

        code = """
import os

# Common font directories by platform
font_dirs = [
    # Linux
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    os.path.expanduser("~/.fonts"),
    os.path.expanduser("~/.local/share/fonts"),
    # macOS
    "/System/Library/Fonts",
    "/Library/Fonts",
    os.path.expanduser("~/Library/Fonts"),
    # Windows
    "C:/Windows/Fonts",
]

fonts = []
searched_dirs = []

for font_dir in font_dirs:
    if os.path.isdir(font_dir):
        searched_dirs.append(font_dir)
        for root, dirs, files in os.walk(font_dir):
            for file in files:
                ext = file.lower().split('.')[-1] if '.' in file else ''
                if ext in ('ttf', 'otf', 'ttc'):
                    full_path = os.path.join(root, file)
                    fonts.append({
                        "name": file,
                        "path": full_path,
                        "type": ext,
                    })

# Sort by name
fonts.sort(key=lambda x: x["name"].lower())

_result_ = {
    "fonts": fonts,
    "count": len(fonts),
    "directories": searched_dirs,
}
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success and result.result:
            return result.result
        raise ValueError(result.error_traceback or "Failed to list fonts")

    @mcp.tool()
    async def draft_shapestring_to_sketch(
        shapestring_name: str,
        body_name: str | None = None,
        plane: str = "XY_Plane",
        sketch_name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Convert a ShapeString to a Sketch for use with PartDesign.

        This converts the 3D wire geometry of a ShapeString into a
        Sketcher::SketchObject that can be used with Pad, Pocket, etc.

        Args:
            shapestring_name: Name of the ShapeString object to convert.
            body_name: Name of PartDesign Body to add sketch to. Optional.
            plane: Plane for the sketch if creating standalone.
                Options: "XY_Plane", "XZ_Plane", "YZ_Plane".
            sketch_name: Name for the created sketch. Auto-generated if None.
            doc_name: Document containing the ShapeString. Uses active if None.

        Returns:
            Dictionary with created sketch information:
                - name: Sketch object name
                - label: Sketch label
                - type_id: Object type
                - wire_count: Number of wires added to sketch
                - source: Name of source ShapeString

        Raises:
            ValueError: If no document is found.
            ValueError: If the ShapeString object is not found.
            ValueError: If the ShapeString has no shape data.
            ValueError: If the specified Body is not found.
            ValueError: If conversion fails.

        Example:
            Convert ShapeString to sketch for extrusion::

                await draft_shapestring("Hello", size=10)
                result = await draft_shapestring_to_sketch(
                    "ShapeString",
                    body_name="Body"
                )
                # Now use pad_sketch to extrude the text
        """
        bridge = await get_bridge()

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

shape_string = doc.getObject({shapestring_name!r})
if shape_string is None:
    raise ValueError(f"ShapeString not found: {shapestring_name!r}")

if not hasattr(shape_string, 'Shape') or shape_string.Shape is None:
    raise ValueError(f"Object has no shape: {shapestring_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Convert ShapeString to Sketch")
try:
    body_name = {body_name!r}
    sketch_name = {sketch_name!r} or "TextSketch"
    plane = {plane!r}

    # Create sketch - either in body or standalone
    if body_name:
        body = doc.getObject(body_name)
        if body is None:
            raise ValueError(f"Body not found: {{body_name}}")
        sketch = doc.addObject("Sketcher::SketchObject", sketch_name)
        # Attach to body's XY plane
        sketch.AttachmentSupport = [(body.Origin.OriginFeatures[0], '')]
        sketch.MapMode = 'FlatFace'
        body.addObject(sketch)
    else:
        sketch = doc.addObject("Sketcher::SketchObject", sketch_name)
        # Set plane orientation
        if plane == "XY_Plane":
            sketch.Placement = FreeCAD.Placement(
                FreeCAD.Vector(0, 0, 0),
                FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 0)
            )
        elif plane == "XZ_Plane":
            sketch.Placement = FreeCAD.Placement(
                FreeCAD.Vector(0, 0, 0),
                FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 90)
            )
        elif plane == "YZ_Plane":
            sketch.Placement = FreeCAD.Placement(
                FreeCAD.Vector(0, 0, 0),
                FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), 90)
            )
        else:
            raise ValueError(
                f"Invalid plane: '{{plane}}'. Must be one of: XY_Plane, XZ_Plane, YZ_Plane"
            )

    # Get the shape and convert wires to sketch geometry
    shape = shape_string.Shape
    wire_count = 0

    for wire in shape.Wires:
        for edge in wire.Edges:
            # Add each edge to the sketch
            # Use the sketch's addGeometry method
            try:
                # Convert edge to sketch geometry
                # This handles lines, arcs, and bezier curves
                sketch.addGeometry(edge.Curve, False)
            except Exception:
                # Some edge types might not convert directly
                # Try to approximate with line segments
                try:
                    # Discretize the edge into points and add as lines
                    points = edge.discretize(Number=20)
                    for i in range(len(points) - 1):
                        line = Part.LineSegment(points[i], points[i + 1])
                        sketch.addGeometry(line, False)
                except Exception:
                    pass
        # Count each wire once (not each edge)
        wire_count += 1

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": sketch.Name,
        "label": sketch.Label,
        "type_id": sketch.TypeId,
        "wire_count": wire_count,
        "source": shape_string.Name,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success and result.result:
            return result.result
        raise ValueError(
            result.error_traceback or "Failed to convert ShapeString to sketch"
        )

    @mcp.tool()
    async def draft_shapestring_to_face(
        shapestring_name: str,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Convert a ShapeString to a Face for direct use with Part operations.

        Creates a Part::Feature with a face from the ShapeString wires.
        This can be used directly with Part boolean operations or
        for creating solids.

        Args:
            shapestring_name: Name of the ShapeString object to convert.
            name: Name for the created face object. Auto-generated if None.
            doc_name: Document containing the ShapeString. Uses active if None.

        Returns:
            Dictionary with created face information:
                - name: Face object name
                - label: Face label
                - type_id: Object type
                - face_count: Number of faces created
                - area: Total face area
                - source: Name of source ShapeString

        Raises:
            ValueError: If no document is found.
            ValueError: If the ShapeString object is not found.
            ValueError: If the ShapeString has no shape data.
            ValueError: If the ShapeString has no wires.
            ValueError: If no faces could be created from the wires.
            ValueError: If conversion fails.

        Example:
            Convert ShapeString to face for boolean operations::

                await draft_shapestring("A", size=20)
                result = await draft_shapestring_to_face("ShapeString")
                # Now extrude or use with boolean operations
        """
        bridge = await get_bridge()

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

shape_string = doc.getObject({shapestring_name!r})
if shape_string is None:
    raise ValueError(f"ShapeString not found: {shapestring_name!r}")

if not hasattr(shape_string, 'Shape') or shape_string.Shape is None:
    raise ValueError(f"Object has no shape: {shapestring_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Convert ShapeString to Face")
try:
    obj_name = {name!r} or "TextFace"

    shape = shape_string.Shape

    # Get wires and create faces
    wires = shape.Wires
    if not wires:
        raise ValueError("ShapeString has no wires")

    # Filter to closed wires only
    closed_wires = [w for w in wires if w.isClosed()]
    if not closed_wires:
        raise ValueError("ShapeString has no closed wires")

    # Use FaceMakerBullseye to properly handle nested wires (outer + holes)
    # This correctly creates faces where inner wires become holes in outer wires
    try:
        result_shape = Part.makeFace(closed_wires, "Part::FaceMakerBullseye")
    except Exception as e:
        raise ValueError(f"Failed to create face from wires: {{e}}")

    if not result_shape.Faces:
        raise ValueError("Could not create any faces from ShapeString")

    # Create Part::Feature to hold the face
    face_obj = doc.addObject("Part::Feature", obj_name)
    face_obj.Shape = result_shape

    # Copy placement from source
    face_obj.Placement = shape_string.Placement

    doc.recompute()
    doc.commitTransaction()

    faces = result_shape.Faces
    total_area = sum(f.Area for f in faces)

    _result_ = {{
        "name": face_obj.Name,
        "label": face_obj.Label,
        "type_id": face_obj.TypeId,
        "face_count": len(faces),
        "area": total_area,
        "source": shape_string.Name,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success and result.result:
            return result.result
        raise ValueError(
            result.error_traceback or "Failed to convert ShapeString to face"
        )

    @mcp.tool()
    async def draft_text_on_surface(
        text: str,
        target_face: str,
        target_object: str,
        depth: float = 2.0,
        font_path: str | None = None,
        size: float = 10.0,
        position: list[float] | None = None,
        operation: str = "engrave",
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create embossed or engraved text on a surface.

        This is a high-level tool that combines ShapeString creation,
        face conversion, extrusion, and boolean operation to create
        text directly on a surface.

        Args:
            text: The text string to create.
            target_face: Face name to place text on (e.g., "Face1", "Face6").
            target_object: Name of the object containing the face.
            depth: Depth of emboss/engrave in mm. Defaults to 2.0.
            font_path: Path to font file. Uses system default if None.
            size: Font size in mm. Defaults to 10.0.
            position: Text position offset [x, y] on the face. Defaults to [0, 0].
            operation: "emboss" (raised) or "engrave" (cut into). Defaults to "engrave".
            name: Name for the result object. Auto-generated if None.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with result information:
                - name: Result object name
                - label: Result label
                - type_id: Object type
                - operation: Operation performed (emboss/engrave)
                - text: Text that was created
                - depth: Depth used

        Raises:
            ValueError: If position has incorrect number of elements (not 2).
            ValueError: If no document is found.
            ValueError: If target_object is not found.
            ValueError: If target_object has no shape.
            ValueError: If target_face is not found on target_object.
            ValueError: If operation is not "emboss" or "engrave".
            ValueError: If font_path is invalid or no default font found.
            ValueError: If text creation or boolean operation fails.

        Example:
            Engrave text on top of a box::

                await create_box(length=100, width=50, height=20)
                result = await draft_text_on_surface(
                    text="SAMPLE",
                    target_face="Face6",  # Top face
                    target_object="Box",
                    depth=1.5,
                    size=8,
                    operation="engrave"
                )
        """
        bridge = await get_bridge()
        pos = _validate_vector(position, 2, "position", [0, 0])

        code = f"""
import Draft
import Part
import os

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

target = doc.getObject({target_object!r})
if target is None:
    raise ValueError(f"Target object not found: {target_object!r}")

if not hasattr(target, 'Shape') or target.Shape is None:
    raise ValueError(f"Target object has no shape: {target_object!r}")

# Get the target face
face_name = {target_face!r}
try:
    face = getattr(target.Shape, face_name)
except Exception:
    raise ValueError(f"Face not found: {{face_name}} on {target_object!r}")

# Wrap in transaction for undo support
doc.openTransaction("Text on Surface")
try:
    text = {text!r}
    size = {size!r}
    depth = {depth!r}
    operation = {operation!r}.lower()
    pos_offset = {pos}
    result_name = {name!r} or f"Text_{{target.Name}}"

    if operation not in ("emboss", "engrave"):
        raise ValueError(f"Invalid operation: {{operation}}. Use 'emboss' or 'engrave'.")

    # Determine font path
    font_path = {font_path!r}
    if font_path is None:
        default_fonts = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Arial.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]
        for fp in default_fonts:
            if os.path.exists(fp):
                font_path = fp
                break
        if font_path is None:
            raise ValueError("No font file specified and no default font found.")

    if not os.path.exists(font_path):
        raise ValueError(f"Font file not found: {{font_path}}")

    # Get face center and normal
    face_center = face.CenterOfMass
    face_normal = face.normalAt(0, 0)

    # Create ShapeString at the face position
    shape_string = Draft.make_shapestring(text, font_path, size)
    if shape_string is None:
        raise ValueError("Failed to create ShapeString")

    doc.recompute()

    # Position the ShapeString on the face
    # Create placement aligned with face
    if abs(face_normal.z) > 0.9:
        # Horizontal face (top/bottom)
        rotation = FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 0)
        if face_normal.z < 0:
            rotation = FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 180)
    elif abs(face_normal.x) > 0.9:
        # YZ face
        rotation = FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), 90 if face_normal.x > 0 else -90)
    else:
        # XZ face
        rotation = FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 90 if face_normal.y < 0 else -90)

    # Apply position offset
    offset = FreeCAD.Vector(pos_offset[0], pos_offset[1], 0)
    text_pos = face_center + offset

    # For engraving, position slightly above surface; for emboss, at surface
    if operation == "engrave":
        text_pos = text_pos + face_normal * 0.1
    else:
        text_pos = text_pos - face_normal * depth

    shape_string.Placement = FreeCAD.Placement(text_pos, rotation)
    doc.recompute()

    # Convert ShapeString wires to faces
    wires = shape_string.Shape.Wires
    if not wires:
        raise ValueError("ShapeString has no wires")

    # Filter to closed wires only
    closed_wires = [w for w in wires if w.isClosed()]
    if not closed_wires:
        raise ValueError("Could not create faces from text - no closed wires")

    # Use FaceMakerBullseye to properly handle nested wires (outer + holes)
    # This correctly creates faces where inner wires become holes in outer wires
    try:
        text_face = Part.makeFace(closed_wires, "Part::FaceMakerBullseye")
    except Exception as e:
        raise ValueError(f"Could not create faces from text: {{e}}")

    if not text_face.Faces:
        raise ValueError("Could not create faces from text")

    # Extrude the text face
    extrude_dir = face_normal * depth
    if operation == "engrave":
        extrude_dir = face_normal * (-depth)

    text_solid = text_face.extrude(extrude_dir)

    # Apply the ShapeString placement to the solid
    text_solid.Placement = shape_string.Placement

    # Perform boolean operation
    if operation == "engrave":
        # Cut text from target
        result_shape = target.Shape.cut(text_solid)
    else:
        # Fuse text with target
        result_shape = target.Shape.fuse(text_solid)

    # Create result object
    result_obj = doc.addObject("Part::Feature", result_name)
    result_obj.Shape = result_shape

    # Hide intermediate objects (only in GUI mode where ViewObject exists)
    if FreeCAD.GuiUp:
        shape_string.ViewObject.Visibility = False
        target.ViewObject.Visibility = False

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": result_obj.Name,
        "label": result_obj.Label,
        "type_id": result_obj.TypeId,
        "operation": operation,
        "text": text,
        "depth": depth,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success and result.result:
            return result.result
        raise ValueError(result.error_traceback or "Failed to create text on surface")

    @mcp.tool()
    async def draft_extrude_shapestring(
        shapestring_name: str,
        height: float = 10.0,
        direction: list[float] | None = None,
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Extrude a ShapeString to create a 3D solid text object.

        This directly extrudes the ShapeString faces into a 3D solid,
        useful for creating standalone 3D text objects.

        Args:
            shapestring_name: Name of the ShapeString object to extrude.
            height: Extrusion height in mm. Defaults to 10.0.
            direction: Extrusion direction as [x, y, z]. Defaults to [0, 0, 1] (up).
            name: Name for the extruded object. Auto-generated if None.
            doc_name: Document containing the ShapeString. Uses active if None.

        Returns:
            Dictionary with extruded object information:
                - name: Object name
                - label: Object label
                - type_id: Object type
                - volume: Solid volume
                - height: Extrusion height used
                - source: Name of source ShapeString

        Raises:
            ValueError: If direction has incorrect number of elements (not 3).
            ValueError: If direction is a zero vector.
            ValueError: If no document is found.
            ValueError: If the ShapeString object is not found.
            ValueError: If the ShapeString has no shape data.
            ValueError: If the ShapeString has no wires.
            ValueError: If no faces could be created from the wires.
            ValueError: If extrusion fails.

        Example:
            Create extruded 3D text::

                await draft_shapestring("FreeCAD", size=20)
                result = await draft_extrude_shapestring(
                    "ShapeString",
                    height=5.0
                )
        """
        bridge = await get_bridge()
        dir_vec = _validate_vector(
            direction, 3, "direction", [0, 0, 1], allow_zero=False
        )

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

shape_string = doc.getObject({shapestring_name!r})
if shape_string is None:
    raise ValueError(f"ShapeString not found: {shapestring_name!r}")

if not hasattr(shape_string, 'Shape') or shape_string.Shape is None:
    raise ValueError(f"Object has no shape: {shapestring_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Extrude ShapeString")
try:
    height = {height!r}
    direction = FreeCAD.Vector({dir_vec[0]}, {dir_vec[1]}, {dir_vec[2]})
    direction.normalize()
    extrude_vec = direction * height
    obj_name = {name!r} or "ExtrudedText"

    shape = shape_string.Shape

    # Get wires and create faces
    wires = shape.Wires
    if not wires:
        raise ValueError("ShapeString has no wires")

    # Filter to closed wires only
    closed_wires = [w for w in wires if w.isClosed()]
    if not closed_wires:
        raise ValueError("ShapeString has no closed wires")

    # Use FaceMakerBullseye to properly handle nested wires (outer + holes)
    # This correctly creates faces where inner wires become holes in outer wires
    try:
        text_face = Part.makeFace(closed_wires, "Part::FaceMakerBullseye")
    except Exception as e:
        raise ValueError(f"Could not create faces from ShapeString: {{e}}")

    if not text_face.Faces:
        raise ValueError("Could not create any faces from ShapeString")

    # Extrude the face(s) - this preserves holes properly
    try:
        result_shape = text_face.extrude(extrude_vec)
    except Exception as e:
        raise ValueError(f"Could not extrude faces: {{e}}")

    # Create Part::Feature to hold the result
    extruded_obj = doc.addObject("Part::Feature", obj_name)
    extruded_obj.Shape = result_shape

    # Copy placement from source
    extruded_obj.Placement = shape_string.Placement

    doc.recompute()
    doc.commitTransaction()

    volume = result_shape.Volume if hasattr(result_shape, 'Volume') else 0

    _result_ = {{
        "name": extruded_obj.Name,
        "label": extruded_obj.Label,
        "type_id": extruded_obj.TypeId,
        "volume": volume,
        "height": height,
        "source": shape_string.Name,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success and result.result:
            return result.result
        raise ValueError(result.error_traceback or "Failed to extrude ShapeString")
