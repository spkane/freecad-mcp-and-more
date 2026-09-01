"""MCP tool profiles and implementations for FreeCAD.

The default parametric profile presents a focused native PartDesign interface.
The full historical surface remains available for compatibility.

- execution: Python code execution tools
- documents: Document management tools
- objects: Object creation and manipulation tools
- partdesign: PartDesign workbench tools
- variables: Native variable-set and expression tools
- export: Export functionality tools
- view: View and screenshot tools
- validation: Object and document validation tools
"""

from collections.abc import Awaitable, Callable
from typing import Any

from freecad_mcp.tools.documents import register_document_tools
from freecad_mcp.tools.execution import register_execution_tools
from freecad_mcp.tools.export import register_export_tools
from freecad_mcp.tools.objects import register_object_tools
from freecad_mcp.tools.partdesign import register_partdesign_tools
from freecad_mcp.tools.validation import register_validation_tools
from freecad_mcp.tools.variables import register_variable_tools
from freecad_mcp.tools.view import register_view_tools

__all__ = [
    "PARAMETRIC_TOOL_NAMES",
    "register_all_tools",
    "register_document_tools",
    "register_execution_tools",
    "register_export_tools",
    "register_object_tools",
    "register_parametric_tools",
    "register_partdesign_tools",
    "register_validation_tools",
    "register_variable_tools",
    "register_view_tools",
]

PARAMETRIC_TOOL_NAMES = frozenset(
    {
        "add_sketch_arc",
        "add_sketch_circle",
        "add_sketch_constraint",
        "add_sketch_line",
        "add_sketch_point",
        "add_sketch_rectangle",
        "bind_expressions",
        "chamfer_edges",
        "close_document",
        "create_constrained_sketch",
        "create_datum_plane",
        "create_document",
        "create_hole",
        "create_partdesign_body",
        "create_sketch",
        "delete_sketch_constraint",
        "delete_sketch_geometry",
        "define_variables",
        "edit_object",
        "export_step",
        "export_stl",
        "fillet_edges",
        "fit_all",
        "get_active_document",
        "get_connection_status",
        "get_console_output",
        "get_freecad_version",
        "get_screenshot",
        "get_sketch_info",
        "get_variables",
        "import_step",
        "inspect_object",
        "linear_pattern",
        "list_documents",
        "list_objects",
        "loft_sketches",
        "mirrored_feature",
        "open_document",
        "pad_sketch",
        "pocket_sketch",
        "polar_pattern",
        "query_objects",
        "recompute_document",
        "redo",
        "revolution_sketch",
        "save_document",
        "set_object_visibility",
        "set_expression",
        "set_view_angle",
        "toggle_construction",
        "undo",
        "validate_object",
        "validate_document",
        "groove_sketch",
    }
)


class _FilteredToolRegistry:
    """Forward only named decorators to an MCP tool registry."""

    def __init__(self, mcp: Any, allowed_names: frozenset[str]) -> None:
        self._mcp = mcp
        self._allowed_names = allowed_names
        self.seen_names: set[str] = set()

    def tool(self, *args: Any, **kwargs: Any) -> Callable[[Any], Any]:
        """Return a decorator that registers only allowed function names."""
        register = self._mcp.tool(*args, **kwargs)

        def decorator(func: Any) -> Any:
            self.seen_names.add(func.__name__)
            if func.__name__ in self._allowed_names:
                return register(func)
            return func

        return decorator


def register_parametric_tools(
    mcp: Any, get_bridge_func: Callable[[], Awaitable[Any]]
) -> None:
    """Register the focused native PartDesign tool interface.

    Args:
        mcp: The FastMCP server instance.
        get_bridge_func: Async function returning the active bridge connection.
    """
    filtered = _FilteredToolRegistry(mcp, PARAMETRIC_TOOL_NAMES)
    register_execution_tools(filtered, get_bridge_func)
    register_document_tools(filtered, get_bridge_func)
    register_object_tools(filtered, get_bridge_func)
    register_export_tools(filtered, get_bridge_func)
    register_view_tools(filtered, get_bridge_func)
    register_validation_tools(filtered, get_bridge_func)
    register_partdesign_tools(filtered, get_bridge_func)
    register_variable_tools(filtered, get_bridge_func)

    missing = PARAMETRIC_TOOL_NAMES - filtered.seen_names
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise RuntimeError(
            f"Parametric tool profile contains unknown tools: {missing_list}"
        )


def register_all_tools(mcp: Any, get_bridge_func: Callable[[], Awaitable[Any]]) -> None:
    """Register all FreeCAD tools with the Robust MCP Server.

    Args:
        mcp: The FastMCP (Robust MCP Server) instance (Any due to lack of stubs).
        get_bridge_func: Async function returning the active bridge connection.
    """
    register_execution_tools(mcp, get_bridge_func)
    register_document_tools(mcp, get_bridge_func)
    register_object_tools(mcp, get_bridge_func)
    register_partdesign_tools(mcp, get_bridge_func)
    register_variable_tools(mcp, get_bridge_func)
    register_export_tools(mcp, get_bridge_func)
    register_view_tools(mcp, get_bridge_func)
    register_validation_tools(mcp, get_bridge_func)
