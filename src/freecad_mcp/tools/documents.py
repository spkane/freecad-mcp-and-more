"""Document management tools for FreeCAD Robust MCP Server.

This module provides tools for managing FreeCAD documents:
creating, opening, saving, closing, and listing documents.
"""

from collections.abc import Awaitable, Callable
from typing import Any


def register_document_tools(mcp: Any, get_bridge: Callable[[], Awaitable[Any]]) -> None:
    """Register document-related tools with the Robust MCP Server.

    Args:
        mcp: The FastMCP (Robust MCP Server) instance.
        get_bridge: Async function to get the active bridge.
    """

    @mcp.tool()
    async def list_documents() -> list[dict[str, Any]]:
        """List all open FreeCAD documents.

        Returns:
            List of dictionaries, each containing:
                - name: Internal document name
                - label: Display label
                - path: File path (None if not saved)
                - is_modified: Whether document has unsaved changes
                - object_count: Number of objects in document
                - active_object: Name of currently active object (None if none)
        """
        bridge = await get_bridge()
        docs = await bridge.get_documents()
        return [
            {
                "name": doc.name,
                "label": doc.label,
                "path": doc.path,
                "is_modified": doc.is_modified,
                "object_count": len(doc.objects),
                "active_object": doc.active_object,
            }
            for doc in docs
        ]

    @mcp.tool()
    async def get_active_document() -> dict[str, Any] | None:
        """Get the currently active FreeCAD document.

        Returns:
            Dictionary with document information, or None if no active document:
                - name: Internal document name
                - label: Display label
                - path: File path (None if not saved)
                - is_modified: Whether document has unsaved changes
                - objects: List of object names
                - active_object: Name of currently active object (None if none)
        """
        bridge = await get_bridge()
        doc = await bridge.get_active_document()
        if doc is None:
            return None
        return {
            "name": doc.name,
            "label": doc.label,
            "path": doc.path,
            "is_modified": doc.is_modified,
            "objects": doc.objects,
            "active_object": doc.active_object,
        }

    @mcp.tool()
    async def create_document(
        name: str = "Unnamed",
        label: str | None = None,
    ) -> dict[str, Any]:
        """Create a new FreeCAD document.

        Args:
            name: Internal document name (no spaces allowed, will be sanitized).
            label: Display label (can contain spaces). Defaults to name.

        Returns:
            Dictionary with created document information:
                - name: Internal document name
                - label: Display label
                - path: File path (None for new document)
        """
        bridge = await get_bridge()
        doc = await bridge.create_document(name, label)
        return {
            "name": doc.name,
            "label": doc.label,
            "path": doc.path,
        }

    @mcp.tool()
    async def open_document(path: str) -> dict[str, Any]:
        """Open an existing FreeCAD document from file.

        Args:
            path: Full path to the .FCStd file to open.

        Returns:
            Dictionary with opened document information:
                - name: Internal document name
                - label: Display label
                - path: File path
                - objects: List of object names

        Raises:
            FileNotFoundError: If the file doesn't exist.
            ValueError: If the file is not a valid FreeCAD document.
        """
        bridge = await get_bridge()
        doc = await bridge.open_document(path)
        return {
            "name": doc.name,
            "label": doc.label,
            "path": doc.path,
            "objects": doc.objects,
        }

    @mcp.tool()
    async def save_document(
        doc_name: str | None = None,
        path: str | None = None,
    ) -> dict[str, Any]:
        """Save a FreeCAD document.

        Args:
            doc_name: Name of document to save. Uses active document if None.
            path: File path to save to. Uses existing path if None.
                  Required for new (unsaved) documents.

        Returns:
            Dictionary with save result:
                - success: Whether save was successful
                - path: Path where document was saved

        Raises:
            ValueError: If document not found or no path specified for new doc.
        """
        bridge = await get_bridge()
        saved_path = await bridge.save_document(doc_name, path)
        return {
            "success": True,
            "path": saved_path,
        }

    @mcp.tool()
    async def close_document(
        doc_name: str | None = None,
        save_changes: bool = False,
    ) -> dict[str, Any]:
        """Close a FreeCAD document.

        Args:
            doc_name: Name of document to close. Uses active document if None.
            save_changes: Whether to save changes before closing. Defaults to False.

        Returns:
            Dictionary with close result:
                - success: Whether close was successful
                - saved: Whether document was saved before closing
        """
        bridge = await get_bridge()

        saved = False
        if save_changes:
            try:
                await bridge.save_document(doc_name)
                saved = True
            except Exception:
                pass

        await bridge.close_document(doc_name)
        return {
            "success": True,
            "saved": saved,
        }

    @mcp.tool()
    async def recompute_document(doc_name: str | None = None) -> dict[str, Any]:
        """Recompute a FreeCAD document to update all dependent objects.

        Args:
            doc_name: Name of document to recompute. Uses active document if None.

        Returns:
            Dictionary with recompute result:
                - success: Whether recompute was successful
        """
        bridge = await get_bridge()
        code = f"""
requested_doc_name = {doc_name!r}
doc = FreeCAD.ActiveDocument if requested_doc_name is None else FreeCAD.getDocument(requested_doc_name)
if doc is None:
    raise ValueError("No document found")
doc.recompute()
_result_ = True
"""
        result = await bridge.execute_python(code, transaction=None)
        return {
            "success": result.success,
            "error": result.error_traceback if not result.success else None,
        }
