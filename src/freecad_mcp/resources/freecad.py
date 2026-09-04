"""FreeCAD Robust MCP resources for exposing FreeCAD state.

This module provides MCP resources that expose FreeCAD's current state
as read-only data. Resources are URI-addressable data that Claude can
access to understand the current FreeCAD environment.

Resource URIs:
    - freecad://capabilities - Complete list of all available tools/resources
    - freecad://version - FreeCAD version information
    - freecad://status - Connection and runtime status
    - freecad://documents - List of open documents
    - freecad://documents/{name} - Single document details
    - freecad://documents/{name}/objects - Objects in a document
    - freecad://objects/{doc_name}/{obj_name} - Object details
    - freecad://active-document - Currently active document
    - freecad://workbenches - Available workbenches
    - freecad://workbenches/active - Currently active workbench
    - freecad://console - Recent console output
"""

import json
from typing import Any


def register_resources(mcp: Any, get_bridge: Any) -> None:
    """Register FreeCAD resources with the Robust MCP Server.

    Args:
        mcp: The FastMCP (Robust MCP Server) instance.
        get_bridge: Async function to get the active bridge.
    """

    @mcp.resource("freecad://version")
    async def resource_version() -> str:
        """Get FreeCAD version and build information.

        Returns:
            JSON string containing:
                - version: FreeCAD version string
                - build_date: Build timestamp
                - python_version: Python interpreter version
                - gui_available: Whether GUI mode is active
        """
        bridge = await get_bridge()
        version_info = await bridge.get_freecad_version()
        return json.dumps(version_info, indent=2)

    @mcp.resource("freecad://status")
    async def resource_status() -> str:
        """Get current FreeCAD connection and runtime status.

        Returns:
            JSON string containing:
                - connected: Connection state
                - mode: Bridge mode (embedded, xmlrpc, socket)
                - freecad_version: Version string
                - gui_available: GUI availability
                - last_ping_ms: Connection latency
                - error: Any error message
        """
        bridge = await get_bridge()
        status = await bridge.get_status()
        return json.dumps(
            {
                "connected": status.connected,
                "mode": status.mode,
                "freecad_version": status.freecad_version,
                "gui_available": status.gui_available,
                "last_ping_ms": status.last_ping_ms,
                "error": status.error,
            },
            indent=2,
        )

    @mcp.resource("freecad://documents")
    async def resource_documents() -> str:
        """Get list of all open FreeCAD documents.

        Returns:
            JSON string containing list of documents, each with:
                - name: Internal document name
                - label: Display label
                - path: File path (null if unsaved)
                - object_count: Number of objects
                - is_modified: Has unsaved changes
                - active_object: Currently selected object
        """
        bridge = await get_bridge()
        docs = await bridge.get_documents()
        doc_list = [
            {
                "name": doc.name,
                "label": doc.label,
                "path": doc.path,
                "object_count": len(doc.objects),
                "is_modified": doc.is_modified,
                "active_object": doc.active_object,
            }
            for doc in docs
        ]
        return json.dumps(doc_list, indent=2)

    @mcp.resource("freecad://documents/{name}")
    async def resource_document(name: str) -> str:
        """Get detailed information about a specific document.

        Args:
            name: Document name to query.

        Returns:
            JSON string containing:
                - name: Internal document name
                - label: Display label
                - path: File path (null if unsaved)
                - objects: List of object names
                - is_modified: Has unsaved changes
                - active_object: Currently selected object
        """
        bridge = await get_bridge()
        docs = await bridge.get_documents()

        for doc in docs:
            if doc.name == name:
                return json.dumps(
                    {
                        "name": doc.name,
                        "label": doc.label,
                        "path": doc.path,
                        "objects": doc.objects,
                        "is_modified": doc.is_modified,
                        "active_object": doc.active_object,
                    },
                    indent=2,
                )

        return json.dumps({"error": f"Document '{name}' not found"}, indent=2)

    @mcp.resource("freecad://documents/{name}/objects")
    async def resource_document_objects(name: str) -> str:
        """Get list of objects in a specific document.

        Args:
            name: Document name to query.

        Returns:
            JSON string containing list of objects, each with:
                - name: Object name
                - label: Display label
                - type_id: FreeCAD type identifier
                - visibility: Whether object is visible
        """
        bridge = await get_bridge()
        objects = await bridge.get_objects(doc_name=name)
        obj_list = [
            {
                "name": obj.name,
                "label": obj.label,
                "type_id": obj.type_id,
                "visibility": obj.visibility,
            }
            for obj in objects
        ]
        return json.dumps(obj_list, indent=2)

    @mcp.resource("freecad://objects/{doc_name}/{obj_name}")
    async def resource_object(doc_name: str, obj_name: str) -> str:
        """Get detailed information about a specific object.

        Args:
            doc_name: Document containing the object.
            obj_name: Object name to query.

        Returns:
            JSON string containing:
                - name: Object name
                - label: Display label
                - type_id: FreeCAD type identifier
                - properties: Dictionary of property values
                - shape_info: Shape geometry (if applicable)
                - children: Dependent object names
                - parents: Parent object names
                - visibility: Display visibility
        """
        bridge = await get_bridge()
        obj = await bridge.get_object(obj_name, doc_name=doc_name)

        # Filter properties to only include serializable values
        safe_properties = _make_json_safe(obj.properties)

        return json.dumps(
            {
                "name": obj.name,
                "label": obj.label,
                "type_id": obj.type_id,
                "properties": safe_properties,
                "shape_info": obj.shape_info,
                "children": obj.children,
                "parents": obj.parents,
                "visibility": obj.visibility,
            },
            indent=2,
        )

    @mcp.resource("freecad://workbenches")
    async def resource_workbenches() -> str:
        """Get list of available FreeCAD workbenches.

        Returns:
            JSON string containing list of workbenches, each with:
                - name: Workbench internal name
                - label: Display label
                - is_active: Whether currently active
        """
        bridge = await get_bridge()
        workbenches = await bridge.get_workbenches()
        wb_list = [
            {
                "name": wb.name,
                "label": wb.label,
                "is_active": wb.is_active,
            }
            for wb in workbenches
        ]
        return json.dumps(wb_list, indent=2)

    @mcp.resource("freecad://workbenches/active")
    async def resource_active_workbench() -> str:
        """Get the currently active workbench.

        Returns:
            JSON string containing active workbench info or null.
        """
        bridge = await get_bridge()
        workbenches = await bridge.get_workbenches()
        for wb in workbenches:
            if wb.is_active:
                return json.dumps(
                    {
                        "name": wb.name,
                        "label": wb.label,
                    },
                    indent=2,
                )
        return json.dumps(None)

    @mcp.resource("freecad://console")
    async def resource_console() -> str:
        """Get recent FreeCAD console output.

        Returns:
            JSON string containing:
                - lines: List of console output lines
                - count: Number of lines
        """
        bridge = await get_bridge()
        lines = await bridge.get_console_output(lines=100)
        return json.dumps(
            {
                "lines": lines,
                "count": len(lines),
            },
            indent=2,
        )

    @mcp.resource("freecad://active-document")
    async def resource_active_document() -> str:
        """Get the currently active document.

        Returns:
            JSON string containing active document info or null.
        """
        bridge = await get_bridge()
        doc = await bridge.get_active_document()
        if doc is None:
            return json.dumps(None)
        return json.dumps(
            {
                "name": doc.name,
                "label": doc.label,
                "path": doc.path,
                "objects": doc.objects,
                "is_modified": doc.is_modified,
                "active_object": doc.active_object,
            },
            indent=2,
        )

    @mcp.resource("freecad://best-practices")
    async def resource_best_practices() -> str:
        """Get FreeCAD best practices and AI guidance.

        This resource provides comprehensive guidance for AI assistants
        working with FreeCAD, covering API patterns, version compatibility,
        validation workflows, and common pitfalls.

        Use this resource at the start of a FreeCAD session to understand
        best practices for reliable CAD operations.

        Returns:
            JSON string containing best practices and guidance.

        Example:
            Read via MCP resource mechanism::

                # In an MCP client
                best_practices = await mcp.read_resource("freecad://best-practices")
                data = json.loads(best_practices)
                print(data["critical_patterns"])  # Shows validation_first, partdesign_workflow
        """
        best_practices = {
            "description": "FreeCAD Best Practices and AI Guidance",
            "purpose": "Reference for AI assistants working with FreeCAD MCP tools",
            "critical_patterns": {
                "validation_first": {
                    "description": "Always validate objects after creation or modification",
                    "pattern": """After any operation that creates or modifies geometry:
1. Call validate_object(object_name) to check shape validity
2. Check the 'is_valid' field in the response
3. If invalid, use undo() to revert and try a different approach""",
                    "tools": ["validate_object", "validate_document"],
                },
                "partdesign_workflow": {
                    "description": "Proper PartDesign workflow for parametric parts",
                    "pattern": """For parametric modeling (recommended for most parts):
1. Create a PartDesign::Body - this is the container for all features
2. Create sketches INSIDE the body using body.newObject() not doc.addObject()
3. Attach sketches to planes (XY_Plane, XZ_Plane, YZ_Plane) or existing faces
4. Use Pad/Pocket/Revolution to create features from sketches
5. Features must be inside a body - standalone features won't work

Example sequence:
- create_document()
- create_partdesign_body(name="Body")
- create_sketch(body_name="Body", plane="XY_Plane")
- add_sketch_rectangle(...)
- pad_sketch(sketch_name="...", length=10)""",
                    "tools": [
                        "create_partdesign_body",
                        "create_sketch",
                        "pad_sketch",
                        "pocket_sketch",
                    ],
                },
                "transaction_safety": {
                    "description": "All tool operations support undo/redo",
                    "pattern": """IMPORTANT: All MCP tool operations are wrapped in FreeCAD transactions,
meaning every operation can be undone with the undo() tool.

Built-in transaction support:
1. Every tool that modifies the document opens a transaction
2. Operations can be undone with undo() and redone with redo()
3. Transaction names appear in FreeCAD's undo history

For complex or risky operations:
1. Every mutating tool runs inside its own transaction, opened and closed by
   the executor. A tool that raises aborts its transaction, so a failed call
   leaves the document exactly as it was - no manual rollback needed.
2. For a call that succeeds but produces bad geometry, use validate_object()
   or validate_document(), then undo() to revert.

Example - manual undo:
pad_sketch(sketch_name="Sketch", length=10)  # Can be undone
undo()  # Reverts the pad""",
                    "tools": [
                        "undo",
                        "redo",
                    ],
                },
            },
            "version_compatibility": {
                "description": "FreeCAD 1.0+ API requirements",
                "critical_changes": {
                    "sketch_attachment": {
                        "supported_version": "FreeCAD 1.0+",
                        "api": "sketch.AttachmentSupport = [(plane_obj, '')]",
                        "pattern": """sketch.AttachmentSupport = [(plane_obj, '')]
sketch.MapMode = 'FlatFace'""",
                    },
                    "body_object_creation": {
                        "description": "Creating objects inside PartDesign bodies",
                        "correct": "sketch = body.newObject('Sketcher::SketchObject', 'Sketch')",
                        "incorrect": "sketch = doc.addObject('...'); body.addObject(sketch)",
                        "reason": "body.newObject() ensures proper parent-child relationships",
                    },
                },
            },
            "gui_vs_headless": {
                "description": "Understanding GUI mode limitations",
                "check_gui": "Use get_freecad_version() - check 'gui_available' field",
                "gui_only_features": [
                    "get_screenshot() - capturing views",
                    "set_object_visibility() - show/hide objects",
                    "Camera controls (zoom, view angles)",
                ],
                "headless_safe_features": [
                    "All document operations",
                    "All object creation/modification",
                    "All export/import operations",
                    "Validation and inspection",
                    "Python code execution",
                ],
                "graceful_degradation": """GUI tools return structured errors in headless mode:
{
    "success": false,
    "error": "GUI not available - ... cannot be set in headless mode"
}
Check for this pattern and handle gracefully.""",
            },
            "common_pitfalls": {
                "standalone_features": {
                    "problem": "Creating PartDesign features outside a Body",
                    "symptom": "Features fail to compute or show errors",
                    "solution": "Always create a Body first, then features inside it",
                },
                "unconstrained_sketches": {
                    "problem": "Sketches with free degrees of freedom",
                    "symptom": "Geometry moves unexpectedly on recompute",
                    "solution": """Add constraints or use the construction mode.
Check with: sketch.solve() returns DoF count (0 = fully constrained)""",
                },
                "invalid_booleans": {
                    "problem": "Boolean operations on non-overlapping shapes",
                    "symptom": "Empty or invalid result shape",
                    "solution": """Verify shapes overlap before boolean:
1. Check bounding boxes overlap
2. Use validate_object() on result
3. Have fallback strategy if boolean fails""",
                },
                "shape_type_mismatch": {
                    "problem": "Operations require specific shape types",
                    "symptom": "Error about wrong shape type",
                    "examples": {
                        "fillet_edges": "Requires solid shape, not mesh or compound",
                        "export_stl": "Works with any shape but quality depends on tessellation",
                        "boolean_operation": "Requires solid shapes, not curves or faces",
                    },
                },
                "document_state": {
                    "problem": "Operating on wrong or no active document",
                    "symptom": "Object not found or wrong object modified",
                    "solution": """Always:
1. Check get_active_document() returns expected document
2. Use explicit doc_name parameter when available
3. Create new document if starting fresh work""",
                },
            },
            "recommended_workflows": {
                "creating_parts": {
                    "steps": [
                        "1. create_document(name='...')",
                        "2. create_partdesign_body(name='Body')",
                        "3. create_sketch(body_name='Body', plane='XY_Plane')",
                        "4. Add geometry: add_sketch_rectangle/circle/line",
                        "5. pad_sketch(sketch_name='...', length=...)",
                        "6. Add features: fillets, chamfers, pockets",
                        "7. validate_document() to check health",
                        "8. Export: export_step/stl/3mf",
                    ],
                },
                "modifying_existing": {
                    "steps": [
                        "1. open_document(path='...')",
                        "2. list_objects() to see what exists",
                        "3. inspect_object(name='...') for details",
                        "4. edit_object(name='...') for modifications",
                        "5. validate_document() after changes",
                        "6. save_document()",
                    ],
                },
                "debugging_issues": {
                    "steps": [
                        "1. get_console_output(lines=50) for error messages",
                        "2. validate_document() to find invalid objects",
                        "3. inspect_object() on problem objects",
                        "4. Check object State - look for 'Error' entries",
                        "5. Use undo() to revert to known good state",
                        "6. recompute_document() to refresh all objects",
                    ],
                },
                "safe_experimentation": {
                    "description": "When trying operations that might fail",
                    "steps": [
                        "1. save_document() first (backup)",
                        "2. Run the operation - a failure aborts its own transaction",
                        "3. validate_document() to confirm the result is sound",
                        "4. undo() if the result is unwanted",
                    ],
                },
            },
            "error_recovery": {
                "invalid_geometry": {
                    "detection": "validate_object() returns is_valid=false",
                    "recovery": [
                        "1. undo() to revert last operation",
                        "2. Try different parameters (larger fillet radius, etc.)",
                        "3. Simplify the operation (fewer features at once)",
                        "4. Check source sketch is closed and valid",
                    ],
                },
                "recompute_failure": {
                    "detection": "object State contains 'Error' or 'Invalid'",
                    "recovery": [
                        "1. inspect_object() to see error details",
                        "2. Check parent objects are valid",
                        "3. May need to delete and recreate feature",
                        "4. recompute_document() after fixes",
                    ],
                },
                "sketch_errors": {
                    "detection": "Sketch won't close or pad fails",
                    "common_causes": [
                        "Open contour (lines don't connect)",
                        "Self-intersection",
                        "Zero-length elements",
                        "Overlapping geometry",
                    ],
                    "recovery": "Recreate sketch with simpler geometry",
                },
            },
            "performance_tips": {
                "minimize_recomputes": "Group multiple changes, recompute once at end",
                "batch_operations": "Use execute_python for multiple related operations",
                "use_validate_document": "Check all objects at once vs individual validate_object calls",
                "incremental_building": "Build complex models step-by-step, validating each step",
            },
        }
        return json.dumps(best_practices, indent=2)

    @mcp.resource("freecad://capabilities")
    async def resource_capabilities() -> str:
        """Get comprehensive list of all MCP capabilities.

        This resource provides a complete catalog of all available tools,
        resources, and prompts. Use this to discover what functionality
        is available when working with the FreeCAD Robust MCP Server.

        Returns:
            JSON string containing:
                - tools: Dict of tool categories with tool definitions
                - resources: List of available resource URIs
                - prompts: List of available prompt names
                - examples: Common usage patterns
        """
        capabilities = {
            "description": "FreeCAD Robust MCP Server - Control FreeCAD via Model Context Protocol",
            "tools": {
                "execution": {
                    "description": "Execute Python code and access console",
                    "tools": [
                        {
                            "name": "get_console_output",
                            "description": "Get recent FreeCAD console output for debugging",
                            "key_params": ["lines"],
                        },
                        {
                            "name": "get_freecad_version",
                            "description": "Get FreeCAD version, build date, Python version",
                            "key_params": [],
                        },
                        {
                            "name": "get_connection_status",
                            "description": "Check MCP bridge connection status and latency",
                            "key_params": [],
                        },
                    ],
                },
                "documents": {
                    "description": "Document management",
                    "tools": [
                        {
                            "name": "list_documents",
                            "description": "List all open FreeCAD documents",
                            "key_params": [],
                        },
                        {
                            "name": "get_active_document",
                            "description": "Get info about currently active document",
                            "key_params": [],
                        },
                        {
                            "name": "create_document",
                            "description": "Create a new FreeCAD document",
                            "key_params": ["name"],
                        },
                        {
                            "name": "open_document",
                            "description": "Open an existing .FCStd file",
                            "key_params": ["path"],
                        },
                        {
                            "name": "save_document",
                            "description": "Save document to disk",
                            "key_params": ["doc_name", "path"],
                        },
                        {
                            "name": "close_document",
                            "description": "Close a document",
                            "key_params": ["doc_name"],
                        },
                        {
                            "name": "recompute_document",
                            "description": "Force recomputation of document features",
                            "key_params": ["doc_name"],
                        },
                    ],
                },
                "objects": {
                    "description": "Object creation and manipulation",
                    "note": "The executor opens a transaction per mutating call and aborts it on failure, so each appears as one undo step",
                    "tools": [
                        {
                            "name": "list_objects",
                            "description": "List all objects in a document",
                            "key_params": ["doc_name"],
                        },
                        {
                            "name": "query_objects",
                            "description": "Filter and page through document objects",
                            "key_params": ["query", "names", "type_ids", "limit"],
                        },
                        {
                            "name": "inspect_object",
                            "description": "Get detailed info about an object",
                            "key_params": ["object_name", "doc_name"],
                        },
                        {
                            "name": "edit_object",
                            "description": "Modify object properties",
                            "key_params": ["object_name", "properties"],
                        },
                    ],
                },
                "partdesign": {
                    "description": "Parametric modeling with PartDesign workbench",
                    "note": "The executor opens a transaction per mutating call and aborts it on failure, so each appears as one undo step",
                    "tools": [
                        {
                            "name": "create_partdesign_body",
                            "description": "Create a PartDesign::Body container",
                            "key_params": ["name"],
                        },
                        {
                            "name": "create_sketch",
                            "description": "Create sketch on plane or face",
                            "key_params": ["body_name", "plane"],
                        },
                        {
                            "name": "create_constrained_sketch",
                            "description": "Create typed geometry and constraints atomically",
                            "key_params": ["body_name", "sketch_name", "entities"],
                        },
                        {
                            "name": "add_sketch_rectangle",
                            "description": "Add rectangle to sketch",
                            "key_params": ["sketch_name", "x", "y", "width", "height"],
                        },
                        {
                            "name": "add_sketch_circle",
                            "description": "Add circle to sketch",
                            "key_params": ["sketch_name", "x", "y", "radius"],
                        },
                        {
                            "name": "add_sketch_line",
                            "description": "Add line to sketch",
                            "key_params": ["sketch_name", "x1", "y1", "x2", "y2"],
                        },
                        {
                            "name": "add_sketch_arc",
                            "description": "Add arc to sketch",
                            "key_params": [
                                "sketch_name",
                                "center_x",
                                "center_y",
                                "radius",
                            ],
                        },
                        {
                            "name": "add_sketch_point",
                            "description": "Add point to sketch (for holes)",
                            "key_params": ["sketch_name", "x", "y"],
                        },
                        {
                            "name": "pad_sketch",
                            "description": "Extrude sketch (additive)",
                            "key_params": ["sketch_name", "length"],
                        },
                        {
                            "name": "pocket_sketch",
                            "description": "Cut using sketch (subtractive)",
                            "key_params": ["sketch_name", "length"],
                        },
                        {
                            "name": "revolution_sketch",
                            "description": "Revolve sketch around axis",
                            "key_params": ["sketch_name", "axis", "angle"],
                        },
                        {
                            "name": "groove_sketch",
                            "description": "Cut by revolving sketch (subtractive revolve)",
                            "key_params": ["sketch_name", "axis", "angle"],
                        },
                        {
                            "name": "loft_sketches",
                            "description": "Create additive loft between sketches",
                            "key_params": ["sketch_names"],
                        },
                        {
                            "name": "create_hole",
                            "description": "Create parametric hole feature",
                            "key_params": ["sketch_name", "diameter", "depth"],
                        },
                        {
                            "name": "fillet_edges",
                            "description": "Add fillets to edges",
                            "key_params": ["object_name", "radius", "edges"],
                        },
                        {
                            "name": "chamfer_edges",
                            "description": "Add chamfers to edges",
                            "key_params": ["object_name", "size", "edges"],
                        },
                        {
                            "name": "create_datum_plane",
                            "description": "Create reference plane for sketches",
                            "key_params": ["body_name", "offset", "plane"],
                        },
                    ],
                },
                "patterns": {
                    "description": "Pattern and transform features",
                    "note": "The executor opens a transaction per mutating call and aborts it on failure, so each appears as one undo step",
                    "tools": [
                        {
                            "name": "linear_pattern",
                            "description": "Create linear pattern",
                            "key_params": [
                                "feature_name",
                                "direction",
                                "occurrences",
                                "length",
                            ],
                        },
                        {
                            "name": "polar_pattern",
                            "description": "Create circular/polar pattern",
                            "key_params": [
                                "feature_name",
                                "axis",
                                "occurrences",
                                "angle",
                            ],
                        },
                        {
                            "name": "mirrored_feature",
                            "description": "Mirror feature across plane",
                            "key_params": ["feature_name", "plane"],
                        },
                    ],
                },
                "sketcher_constraints": {
                    "description": "Sketcher constraint tools for fully defining geometry",
                    "note": "The executor opens a transaction per mutating call and aborts it on failure, so each appears as one undo step",
                    "tools": [
                        {
                            "name": "add_sketch_constraint",
                            "description": "Add generic constraint (flexible API)",
                            "key_params": ["sketch_name", "constraint_type", "params"],
                        },
                        {
                            "name": "delete_sketch_geometry",
                            "description": "Delete geometry from sketch",
                            "key_params": ["sketch_name", "geometry_index"],
                        },
                        {
                            "name": "delete_sketch_constraint",
                            "description": "Delete constraint from sketch",
                            "key_params": ["sketch_name", "constraint_index"],
                        },
                        {
                            "name": "get_sketch_info",
                            "description": "Get sketch geometry and constraint info",
                            "key_params": ["sketch_name"],
                        },
                        {
                            "name": "toggle_construction",
                            "description": "Toggle geometry construction mode",
                            "key_params": ["sketch_name", "geometry_index"],
                        },
                    ],
                },
                "view": {
                    "description": "View and GUI control (some require GUI mode)",
                    "tools": [
                        {
                            "name": "get_screenshot",
                            "description": "Capture 3D view screenshot (GUI only)",
                            "key_params": ["file_path", "width", "height"],
                        },
                        {
                            "name": "set_view_angle",
                            "description": "Set camera to standard views",
                            "key_params": ["angle"],
                        },
                        {
                            "name": "fit_all",
                            "description": "Zoom to fit all objects",
                            "key_params": [],
                        },
                        {
                            "name": "set_object_visibility",
                            "description": "Show/hide objects (GUI only)",
                            "key_params": ["object_name", "visible"],
                        },
                    ],
                },
                "undo_redo": {
                    "description": "Undo/redo operations",
                    "tools": [
                        {
                            "name": "undo",
                            "description": "Undo last operation",
                            "key_params": ["doc_name"],
                        },
                        {
                            "name": "redo",
                            "description": "Redo undone operation",
                            "key_params": ["doc_name"],
                        },
                    ],
                },
                "variables": {
                    "description": "Native variables and expression bindings",
                    "tools": [
                        {
                            "name": "define_variables",
                            "description": "Create or update an App::VarSet batch",
                            "key_params": ["variable_set_name", "variables"],
                        },
                        {
                            "name": "get_variables",
                            "description": "Inspect native variable values and expressions",
                            "key_params": ["variable_set_name"],
                        },
                        {
                            "name": "bind_expressions",
                            "description": "Apply expression bindings atomically",
                            "key_params": ["bindings", "expected_revision"],
                        },
                        {
                            "name": "set_expression",
                            "description": "Set or clear one expression binding",
                            "key_params": [
                                "object_name",
                                "property_path",
                                "expression",
                            ],
                        },
                    ],
                },
                "export_import": {
                    "description": "File export and import",
                    "tools": [
                        {
                            "name": "export_step",
                            "description": "Export to STEP format",
                            "key_params": ["object_names", "file_path"],
                        },
                        {
                            "name": "export_stl",
                            "description": "Export to STL format (3D printing)",
                            "key_params": ["object_names", "file_path"],
                        },
                        {
                            "name": "import_step",
                            "description": "Import STEP file",
                            "key_params": ["file_path"],
                        },
                    ],
                },
                "validation": {
                    "description": "Object and document validation for error detection",
                    "tools": [
                        {
                            "name": "validate_object",
                            "description": "Check object health (shape validity, errors, state)",
                            "key_params": ["object_name", "doc_name"],
                        },
                        {
                            "name": "validate_document",
                            "description": "Check health of all objects in document",
                            "key_params": ["doc_name"],
                        },
                    ],
                },
            },
            "resources": [
                {
                    "uri": "freecad://capabilities",
                    "description": "This resource - lists all available capabilities",
                },
                {
                    "uri": "freecad://best-practices",
                    "description": "★ RECOMMENDED: Read first - AI guidance, best practices, version compatibility, common pitfalls",
                },
                {
                    "uri": "freecad://version",
                    "description": "FreeCAD version and build information",
                },
                {
                    "uri": "freecad://status",
                    "description": "Connection status, mode, GUI availability",
                },
                {
                    "uri": "freecad://documents",
                    "description": "List of all open documents",
                },
                {
                    "uri": "freecad://documents/{name}",
                    "description": "Details of a specific document",
                },
                {
                    "uri": "freecad://documents/{name}/objects",
                    "description": "Objects in a specific document",
                },
                {
                    "uri": "freecad://objects/{doc_name}/{obj_name}",
                    "description": "Detailed object info with properties",
                },
                {
                    "uri": "freecad://active-document",
                    "description": "Currently active document",
                },
                {
                    "uri": "freecad://workbenches",
                    "description": "Available FreeCAD workbenches",
                },
                {
                    "uri": "freecad://workbenches/active",
                    "description": "Currently active workbench",
                },
                {
                    "uri": "freecad://console",
                    "description": "Recent console output (debugging)",
                },
            ],
            "prompts": [
                {
                    "name": "freecad_startup",
                    "description": "★ RECOMMENDED: Auto-load on connection - Essential startup guidance and session checklist",
                    "key_params": [],
                },
                {
                    "name": "freecad_guidance",
                    "description": "Task-specific AI guidance (general, partdesign, sketching, boolean, export, debugging, validation)",
                    "key_params": ["task_type"],
                },
                {
                    "name": "design_part",
                    "description": "Guided workflow for designing parametric parts",
                    "key_params": ["description", "units"],
                },
                {
                    "name": "create_sketch_guide",
                    "description": "Guide for creating 2D sketches",
                    "key_params": ["shape_type", "plane"],
                },
                {
                    "name": "boolean_operations_guide",
                    "description": "Guide for boolean operations (fuse, cut, common)",
                },
                {
                    "name": "export_guide",
                    "description": "Guide for exporting models (STEP, STL, OBJ, IGES)",
                    "key_params": ["target_format"],
                },
                {
                    "name": "import_guide",
                    "description": "Guide for importing files",
                    "key_params": ["source_format"],
                },
                {
                    "name": "analyze_shape",
                    "description": "Guide for shape analysis (volume, area, etc.)",
                },
                {
                    "name": "debug_model",
                    "description": "Troubleshooting guide for model issues",
                },
                {
                    "name": "python_api_reference",
                    "description": "Quick reference for FreeCAD Python API",
                },
                {
                    "name": "troubleshooting",
                    "description": "General troubleshooting for FreeCAD MCP",
                },
            ],
            "examples": {
                "create_simple_part": {
                    "description": "Create a basic parametric part",
                    "steps": [
                        "create_document(name='MyPart')",
                        "create_partdesign_body(name='Body')",
                        "create_sketch(body_name='Body', plane='XY_Plane')",
                        "add_sketch_rectangle(...)",
                        "pad_sketch(...)",
                    ],
                },
                "export_for_printing": {
                    "description": "Export model for 3D printing",
                    "steps": [
                        "export_stl(object_names=['Body'], file_path='...')",
                    ],
                },
            },
        }
        return json.dumps(capabilities, indent=2)


def _make_json_safe(obj: Any) -> Any:
    """Convert an object to be JSON serializable.

    Args:
        obj: Object to convert.

    Returns:
        JSON-safe representation of the object.
    """
    if obj is None:
        return None
    if isinstance(obj, str | int | float | bool):
        return obj
    if isinstance(obj, list | tuple):
        return [_make_json_safe(item) for item in obj]
    if isinstance(obj, dict):
        return {str(k): _make_json_safe(v) for k, v in obj.items()}
    # Convert other types to string representation
    return str(obj)
