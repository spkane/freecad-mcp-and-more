"""Export tools for FreeCAD Robust MCP Server.

This module provides tools for exporting FreeCAD documents and objects
to various file formats: STEP, STL, 3MF, OBJ, IGES, and FreeCAD native.
"""

from collections.abc import Awaitable, Callable
from typing import Any


def _build_object_selection_code(object_names: list[str] | None) -> str:
    """Generate Python code for GUI-aware object selection.

    This helper eliminates code duplication across export functions by
    generating the common object selection logic that handles both GUI
    and headless modes appropriately.

    Args:
        object_names: Optional list of specific object names to select.

    Returns:
        Python code string for object selection logic.
    """
    return f"""
# Get objects to export
if {object_names!r} is not None:
    objects = [doc.getObject(n) for n in {object_names!r}]
elif FreeCAD.GuiUp:
    # GUI mode: export visible objects with shapes
    objects = [
        obj for obj in doc.Objects
        if hasattr(obj, 'Shape') and obj.ViewObject and obj.ViewObject.Visibility
    ]
else:
    # Headless mode: export all objects with shapes
    objects = [obj for obj in doc.Objects if hasattr(obj, 'Shape')]
objects = [obj for obj in objects if obj is not None and hasattr(obj, 'Shape')]

if not objects:
    raise ValueError("No exportable objects found")
"""


def register_export_tools(mcp: Any, get_bridge: Callable[[], Awaitable[Any]]) -> None:
    """Register export-related tools with the Robust MCP Server.

    Args:
        mcp: The FastMCP (Robust MCP Server) instance (Any due to lack of stubs).
        get_bridge: Async function returning the active bridge connection.
    """

    @mcp.tool()
    async def export_step(
        file_path: str,
        object_names: list[str] | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Export objects to STEP format.

        STEP (Standard for the Exchange of Product Data) is an ISO standard
        for CAD data exchange, widely supported by CAD software.

        Args:
            file_path: Path for the output .step file.
            object_names: List of object names to export. Exports all visible if None.
            doc_name: Document to export from. Uses active document if None.

        Returns:
            Dictionary with export result:
                - success: Whether export was successful
                - path: Path to exported file
                - object_count: Number of objects exported
        """
        bridge = await get_bridge()

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")
{_build_object_selection_code(object_names)}
# Combine shapes
if len(objects) == 1:
    shape = objects[0].Shape
else:
    shape = Part.makeCompound([obj.Shape for obj in objects])

shape.exportStep({file_path!r})

_result_ = {{
    "success": True,
    "path": {file_path!r},
    "object_count": len(objects),
}}
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "STEP export failed")

    @mcp.tool()
    async def export_stl(
        file_path: str,
        object_names: list[str] | None = None,
        doc_name: str | None = None,
        mesh_tolerance: float = 0.1,
    ) -> dict[str, Any]:
        """Export objects to STL format.

        STL (Stereolithography) is commonly used for 3D printing and
        rapid prototyping. It represents surfaces as triangular meshes.

        Args:
            file_path: Path for the output .stl file.
            object_names: List of object names to export. Exports all visible if None.
            doc_name: Document to export from. Uses active document if None.
            mesh_tolerance: Mesh approximation tolerance. Lower = finer mesh.

        Returns:
            Dictionary with export result:
                - success: Whether export was successful
                - path: Path to exported file
                - object_count: Number of objects exported
        """
        bridge = await get_bridge()

        code = f"""
import Mesh
import MeshPart
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")
{_build_object_selection_code(object_names)}
# Create mesh from shapes using MeshPart (more reliable than manual tessellation)
meshes = []
for obj in objects:
    mesh = MeshPart.meshFromShape(obj.Shape, LinearDeflection={mesh_tolerance})
    meshes.append(mesh)

# Combine meshes
if len(meshes) == 1:
    final_mesh = meshes[0]
else:
    final_mesh = Mesh.Mesh()
    for m in meshes:
        final_mesh.addMesh(m)

final_mesh.write({file_path!r})

_result_ = {{
    "success": True,
    "path": {file_path!r},
    "object_count": len(objects),
}}
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "STL export failed")

    @mcp.tool()
    async def export_3mf(
        file_path: str,
        object_names: list[str] | None = None,
        doc_name: str | None = None,
        mesh_tolerance: float = 0.1,
    ) -> dict[str, Any]:
        """Export objects to 3MF format.

        3MF (3D Manufacturing Format) is a modern 3D printing format that
        supports richer data than STL, including colors, materials, and
        print settings. It is increasingly preferred over STL for 3D printing.

        Args:
            file_path: Path for the output .3mf file.
            object_names: List of object names to export. Exports all visible if None.
            doc_name: Document to export from. Uses active document if None.
            mesh_tolerance: Mesh approximation tolerance. Lower = finer mesh.

        Returns:
            Dictionary with export result:
                - success: Whether export was successful
                - path: Path to exported file
                - object_count: Number of objects exported
        """
        bridge = await get_bridge()

        code = f"""
import Mesh
import MeshPart
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")
{_build_object_selection_code(object_names)}
# Create mesh from shapes using MeshPart (more reliable than manual tessellation)
meshes = []
for obj in objects:
    mesh = MeshPart.meshFromShape(obj.Shape, LinearDeflection={mesh_tolerance})
    meshes.append(mesh)

# Combine meshes
if len(meshes) == 1:
    final_mesh = meshes[0]
else:
    final_mesh = Mesh.Mesh()
    for m in meshes:
        final_mesh.addMesh(m)

# Export to 3MF format
final_mesh.write({file_path!r})

_result_ = {{
    "success": True,
    "path": {file_path!r},
    "object_count": len(objects),
}}
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "3MF export failed")

    @mcp.tool()
    async def export_obj(
        file_path: str,
        object_names: list[str] | None = None,
        doc_name: str | None = None,
        mesh_tolerance: float = 0.1,
    ) -> dict[str, Any]:
        """Export objects to OBJ format.

        OBJ (Wavefront) is a common 3D model format supported by many
        3D graphics applications and game engines.

        Args:
            file_path: Path for the output .obj file.
            object_names: List of object names to export. Exports all visible if None.
            doc_name: Document to export from. Uses active document if None.
            mesh_tolerance: Mesh approximation tolerance. Lower = finer mesh.

        Returns:
            Dictionary with export result:
                - success: Whether export was successful
                - path: Path to exported file
                - object_count: Number of objects exported
        """
        bridge = await get_bridge()

        code = f"""
import Mesh
import MeshPart

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")
{_build_object_selection_code(object_names)}
# Create mesh from shapes using MeshPart (more reliable than manual tessellation)
meshes = []
for obj in objects:
    mesh = MeshPart.meshFromShape(obj.Shape, LinearDeflection={mesh_tolerance})
    meshes.append(mesh)

# Combine meshes
if len(meshes) == 1:
    final_mesh = meshes[0]
else:
    final_mesh = Mesh.Mesh()
    for m in meshes:
        final_mesh.addMesh(m)

final_mesh.write({file_path!r})

_result_ = {{
    "success": True,
    "path": {file_path!r},
    "object_count": len(objects),
}}
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "OBJ export failed")

    @mcp.tool()
    async def export_iges(
        file_path: str,
        object_names: list[str] | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Export objects to IGES format.

        IGES (Initial Graphics Exchange Specification) is an older but still
        widely supported CAD data exchange format.

        Args:
            file_path: Path for the output .iges file.
            object_names: List of object names to export. Exports all visible if None.
            doc_name: Document to export from. Uses active document if None.

        Returns:
            Dictionary with export result:
                - success: Whether export was successful
                - path: Path to exported file
                - object_count: Number of objects exported
        """
        bridge = await get_bridge()

        code = f"""
import Part

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")
{_build_object_selection_code(object_names)}
# Combine shapes
if len(objects) == 1:
    shape = objects[0].Shape
else:
    shape = Part.makeCompound([obj.Shape for obj in objects])

shape.exportIges({file_path!r})

_result_ = {{
    "success": True,
    "path": {file_path!r},
    "object_count": len(objects),
}}
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "IGES export failed")

    @mcp.tool()
    async def import_step(
        file_path: str,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Import a STEP file into FreeCAD.

        Args:
            file_path: Path to the .step file to import.
            doc_name: Document to import into. Creates new if None.

        Returns:
            Dictionary with import result:
                - success: Whether import was successful
                - document: Name of document containing imported objects
                - objects: List of imported object names
        """
        bridge = await get_bridge()

        code = f"""
import Part
import os

if not os.path.exists({file_path!r}):
    raise FileNotFoundError(f"File not found: {file_path!r}")

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    doc = FreeCAD.newDocument("Imported")

# Get object count before import
before_count = len(doc.Objects)

Part.insert({file_path!r}, doc.Name)
doc.recompute()

# Get new objects
new_objects = [obj.Name for obj in doc.Objects[before_count:]]

_result_ = {{
    "success": True,
    "document": doc.Name,
    "objects": new_objects,
}}
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "STEP import failed")

    @mcp.tool()
    async def import_stl(
        file_path: str,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Import an STL file into FreeCAD.

        Args:
            file_path: Path to the .stl file to import.
            doc_name: Document to import into. Creates new if None.

        Returns:
            Dictionary with import result:
                - success: Whether import was successful
                - document: Name of document containing imported object
                - object: Name of imported mesh object
        """
        bridge = await get_bridge()

        code = f"""
import Mesh
import os

if not os.path.exists({file_path!r}):
    raise FileNotFoundError(f"File not found: {file_path!r}")

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    doc = FreeCAD.newDocument("Imported")

Mesh.insert({file_path!r}, doc.Name)
doc.recompute()

# Get the last added object (the imported mesh)
mesh_obj = doc.Objects[-1]

_result_ = {{
    "success": True,
    "document": doc.Name,
    "object": mesh_obj.Name,
}}
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "STL import failed")
