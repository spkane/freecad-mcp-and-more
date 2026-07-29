"""Embedded bridge - runs FreeCAD in-process.

This bridge imports FreeCAD directly into the Robust MCP Server process,
providing the fastest execution but limited to headless mode.

Based on learnings from competitive analysis:
- Thread-safe execution using ThreadPoolExecutor (from neka-nat)
- Comprehensive object info including shape geometry
- Macro support with templates and validation
"""

import asyncio
import io
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

from freecad_mcp.bridge.base import (
    ConnectionStatus,
    DocumentInfo,
    ExecutionResult,
    FreecadBridge,
    MacroInfo,
    ObjectInfo,
    ScreenshotResult,
    ViewAngle,
    WorkbenchInfo,
)


class EmbeddedBridge(FreecadBridge):
    """Bridge that runs FreeCAD embedded in the Robust MCP Server process.

    This bridge imports FreeCAD directly, providing fast execution
    but only supports headless mode (no GUI).

    Attributes:
        freecad_path: Optional path to FreeCAD's lib directory.
    """

    def __init__(self, freecad_path: str | None = None) -> None:
        """Initialize the embedded bridge.

        Args:
            freecad_path: Path to FreeCAD's lib directory. If provided,
                this path will be added to sys.path before importing.
        """
        self._freecad_path = freecad_path
        self._fc_module: Any = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="freecad")
        self._connected = False

    async def connect(self) -> None:
        """Import and initialize FreeCAD.

        Raises:
            ConnectionError: If FreeCAD cannot be imported.
        """
        if self._freecad_path:
            sys.path.insert(0, self._freecad_path)

        loop = asyncio.get_event_loop()
        try:
            self._fc_module = await loop.run_in_executor(
                self._executor,
                self._import_freecad,
            )
            self._connected = True
        except ImportError as e:
            msg = f"Failed to import FreeCAD: {e}"
            raise ConnectionError(msg) from e

    def _import_freecad(self) -> Any:
        """Import FreeCAD module (runs in thread pool)."""
        import FreeCAD

        return FreeCAD

    async def disconnect(self) -> None:
        """Clean up resources."""
        self._connected = False
        self._executor.shutdown(wait=True)

    async def is_connected(self) -> bool:
        """Check if FreeCAD is imported and available."""
        return self._connected and self._fc_module is not None

    async def execute_python(
        self,
        code: str,
        timeout_ms: int = 30000,
    ) -> ExecutionResult:
        """Execute Python code in FreeCAD context.

        Args:
            code: Python code to execute.
            timeout_ms: Maximum execution time in milliseconds.

        Returns:
            ExecutionResult with execution outcome.
        """
        if not self._connected:
            return ExecutionResult(
                success=False,
                result=None,
                stdout="",
                stderr="FreeCAD bridge not connected",
                execution_time_ms=0,
                error_type="ConnectionError",
                error_traceback=None,
            )

        loop = asyncio.get_event_loop()

        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    self._executor,
                    lambda: self._execute_code(code),
                ),
                timeout=timeout_ms / 1000,
            )
        except TimeoutError:
            return ExecutionResult(
                success=False,
                result=None,
                stdout="",
                stderr=f"Execution timed out after {timeout_ms}ms",
                execution_time_ms=float(timeout_ms),
                error_type="TimeoutError",
                error_traceback=None,
            )

        return result

    def _execute_code(self, code: str) -> ExecutionResult:
        """Execute code synchronously (runs in thread pool)."""
        start = time.perf_counter()
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        # Build execution context
        exec_globals: dict[str, Any] = {
            "FreeCAD": self._fc_module,
            "App": self._fc_module,
            "__builtins__": __builtins__,
        }

        # Try to add GUI module if available
        try:
            import FreeCADGui

            exec_globals["FreeCADGui"] = FreeCADGui
            exec_globals["Gui"] = FreeCADGui
        except ImportError:
            pass

        try:
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                compiled = compile(code, "<mcp>", "exec")
                exec(compiled, exec_globals)  # noqa: S102

            elapsed = (time.perf_counter() - start) * 1000

            return ExecutionResult(
                success=True,
                result=exec_globals.get("_result_"),
                stdout=stdout_capture.getvalue(),
                stderr=stderr_capture.getvalue(),
                execution_time_ms=elapsed,
            )

        except Exception as e:
            import traceback

            elapsed = (time.perf_counter() - start) * 1000

            return ExecutionResult(
                success=False,
                result=None,
                stdout=stdout_capture.getvalue(),
                stderr=stderr_capture.getvalue(),
                execution_time_ms=elapsed,
                error_type=type(e).__name__,
                error_traceback=traceback.format_exc(),
            )

    async def get_documents(self) -> list[DocumentInfo]:
        """Get list of open documents."""
        result = await self.execute_python(
            """
_result_ = []
for doc in FreeCAD.listDocuments().values():
    _result_.append({
        "name": doc.Name,
        "path": doc.FileName or None,
        "objects": [obj.Name for obj in doc.Objects],
        "is_modified": doc.Modified if hasattr(doc, "Modified") else False,
        "label": doc.Label,
    })
"""
        )

        if result.success and result.result:
            return [DocumentInfo(**doc) for doc in result.result]
        return []

    async def get_active_document(self) -> DocumentInfo | None:
        """Get the active document."""
        result = await self.execute_python(
            """
doc = FreeCAD.ActiveDocument
if doc:
    _result_ = {
        "name": doc.Name,
        "path": doc.FileName or None,
        "objects": [obj.Name for obj in doc.Objects],
        "is_modified": doc.Modified if hasattr(doc, "Modified") else False,
        "label": doc.Label,
    }
else:
    _result_ = None
"""
        )

        if result.success and result.result:
            return DocumentInfo(**result.result)
        return None

    async def get_object(
        self,
        obj_name: str,
        doc_name: str | None = None,
    ) -> ObjectInfo:
        """Get detailed object information."""
        result = await self.execute_python(
            f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({obj_name!r})
if obj is None:
    raise ValueError(f"Object not found: {obj_name!r}")

props = {{}}
for prop in obj.PropertiesList:
    try:
        val = getattr(obj, prop)
        if hasattr(val, '__class__') and val.__class__.__module__ != 'builtins':
            val = str(val)
        props[prop] = val
    except Exception:
        props[prop] = "<unreadable>"

shape_info = None
if hasattr(obj, "Shape"):
    shape = obj.Shape
    shape_info = {{
        "type": shape.ShapeType,
        "volume": shape.Volume if hasattr(shape, "Volume") else None,
        "area": shape.Area if hasattr(shape, "Area") else None,
        "is_valid": shape.isValid(),
    }}

_result_ = {{
    "name": obj.Name,
    "label": obj.Label,
    "type_id": obj.TypeId,
    "properties": props,
    "shape_info": shape_info,
    "children": [c.Name for c in obj.OutList] if hasattr(obj, "OutList") else [],
}}
"""
        )

        if result.success and result.result:
            return ObjectInfo(**result.result)

        error_msg = result.error_traceback or "Failed to get object"
        raise ValueError(error_msg)

    async def get_console_output(
        self,
        lines: int = 100,
    ) -> list[str]:
        """Get recent console output.

        Note: In embedded mode, we don't have direct access to FreeCAD's
        console history, so we return an empty list or captured output.
        """
        return []

    async def get_freecad_version(self) -> dict[str, Any]:
        """Get FreeCAD version information."""
        result = await self.execute_python(
            """
import sys
_result_ = {
    "version": ".".join(str(x) for x in FreeCAD.Version()[:3]),
    "version_tuple": FreeCAD.Version()[:3],
    "build_date": FreeCAD.Version()[3] if len(FreeCAD.Version()) > 3 else "unknown",
    "python_version": sys.version,
    "gui_available": hasattr(FreeCAD, "GuiUp") and FreeCAD.GuiUp,
}
"""
        )

        if result.success and result.result:
            return result.result

        return {
            "version": "unknown",
            "version_tuple": [],
            "build_date": "unknown",
            "python_version": sys.version,
            "gui_available": False,
        }

    async def is_gui_available(self) -> bool:
        """Check if GUI is available."""
        result = await self.execute_python(
            "_result_ = hasattr(FreeCAD, 'GuiUp') and FreeCAD.GuiUp"
        )
        return bool(result.success and result.result)

    async def ping(self) -> float:
        """Ping FreeCAD to check connection and measure latency.

        Returns:
            Round-trip time in milliseconds.

        Raises:
            ConnectionError: If not connected.
        """
        if not self._connected:
            msg = "Not connected to FreeCAD"
            raise ConnectionError(msg)

        start = time.perf_counter()
        result = await self.execute_python("_result_ = True")
        elapsed = (time.perf_counter() - start) * 1000

        if not result.success:
            msg = "Ping failed"
            raise ConnectionError(msg)

        return elapsed

    async def get_status(self) -> ConnectionStatus:
        """Get detailed connection status.

        Returns:
            ConnectionStatus with full status information.
        """
        if not self._connected:
            return ConnectionStatus(
                connected=False,
                mode="embedded",
                error="Not connected",
            )

        try:
            ping_ms = await self.ping()
            version_info = await self.get_freecad_version()
            gui_available = await self.is_gui_available()

            return ConnectionStatus(
                connected=True,
                mode="embedded",
                freecad_version=version_info.get("version", "unknown"),
                gui_available=gui_available,
                last_ping_ms=ping_ms,
            )
        except Exception as e:
            return ConnectionStatus(
                connected=False,
                mode="embedded",
                error=str(e),
            )

    # =========================================================================
    # Document Management
    # =========================================================================

    async def create_document(
        self, name: str, label: str | None = None
    ) -> DocumentInfo:
        """Create a new document.

        Args:
            name: Internal document name (no spaces).
            label: Display label (optional, defaults to name).

        Returns:
            DocumentInfo for the created document.
        """
        label = label or name
        result = await self.execute_python(
            f"""
doc = FreeCAD.newDocument({name!r})
doc.Label = {label!r}
_result_ = {{
    "name": doc.Name,
    "label": doc.Label,
    "path": doc.FileName or None,
    "objects": [],
    "is_modified": False,
}}
"""
        )

        if result.success and result.result:
            return DocumentInfo(**result.result)

        error_msg = result.error_traceback or "Failed to create document"
        raise ValueError(error_msg)

    async def open_document(self, path: str) -> DocumentInfo:
        """Open an existing document.

        Args:
            path: Path to the .FCStd file.

        Returns:
            DocumentInfo for the opened document.

        Raises:
            FileNotFoundError: If file doesn't exist.
            ValueError: If file is not a valid FreeCAD document.
        """
        if not Path(path).exists():
            msg = f"File not found: {path}"
            raise FileNotFoundError(msg)

        result = await self.execute_python(
            f"""
doc = FreeCAD.openDocument({path!r})
_result_ = {{
    "name": doc.Name,
    "label": doc.Label,
    "path": doc.FileName or None,
    "objects": [obj.Name for obj in doc.Objects],
    "is_modified": doc.Modified if hasattr(doc, "Modified") else False,
}}
"""
        )

        if result.success and result.result:
            return DocumentInfo(**result.result)

        error_msg = result.error_traceback or "Failed to open document"
        raise ValueError(error_msg)

    async def save_document(
        self,
        doc_name: str | None = None,
        path: str | None = None,
    ) -> str:
        """Save a document.

        Args:
            doc_name: Document name (uses active if None).
            path: Save path (uses existing path if None).

        Returns:
            Path where document was saved.

        Raises:
            ValueError: If document not found or no path specified for new doc.
        """
        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No active document" if {doc_name!r} is None else f"Document not found: {doc_name!r}")

save_path = {path!r} or doc.FileName
if not save_path:
    raise ValueError("No path specified for new document")

doc.saveAs(save_path)
_result_ = save_path
"""

        result = await self.execute_python(code)

        if result.success and result.result:
            return result.result

        error_msg = result.error_traceback or "Failed to save document"
        raise ValueError(error_msg)

    async def close_document(self, doc_name: str | None = None) -> None:
        """Close a document.

        Args:
            doc_name: Document name (uses active if None).
        """
        code = f"""
doc_name = {doc_name!r}
if doc_name is None:
    doc = FreeCAD.ActiveDocument
    if doc:
        doc_name = doc.Name
    else:
        raise ValueError("No active document")

FreeCAD.closeDocument(doc_name)
_result_ = True
"""
        result = await self.execute_python(code)

        if not result.success:
            error_msg = result.error_traceback or "Failed to close document"
            raise ValueError(error_msg)

    # =========================================================================
    # Object Management
    # =========================================================================

    async def get_objects(self, doc_name: str | None = None) -> list[ObjectInfo]:
        """Get all objects in a document.

        Args:
            doc_name: Document name (uses active if None).

        Returns:
            List of ObjectInfo for each object.
        """
        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

objects = []
for obj in doc.Objects:
    obj_info = {{
        "name": obj.Name,
        "label": obj.Label,
        "type_id": obj.TypeId,
        "visibility": obj.ViewObject.Visibility if hasattr(obj, "ViewObject") and obj.ViewObject else True,
        "children": [c.Name for c in obj.OutList] if hasattr(obj, "OutList") else [],
        "parents": [p.Name for p in obj.InList] if hasattr(obj, "InList") else [],
    }}
    objects.append(obj_info)

_result_ = objects
"""
        result = await self.execute_python(code)

        if result.success and result.result:
            return [ObjectInfo(**obj) for obj in result.result]
        return []

    async def create_object(
        self,
        type_id: str,
        name: str | None = None,
        properties: dict[str, Any] | None = None,
        doc_name: str | None = None,
    ) -> ObjectInfo:
        """Create a new object.

        Args:
            type_id: FreeCAD type ID (e.g., "Part::Box", "Part::Cylinder").
            name: Object name (auto-generated if None).
            properties: Initial property values.
            doc_name: Target document (uses active if None).

        Returns:
            ObjectInfo for the created object.
        """
        properties = properties or {}
        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.addObject({type_id!r}, {name!r} or "")

# Set properties
for prop_name, prop_val in {properties!r}.items():
    if hasattr(obj, prop_name):
        setattr(obj, prop_name, prop_val)

doc.recompute()

_result_ = {{
    "name": obj.Name,
    "label": obj.Label,
    "type_id": obj.TypeId,
    "visibility": True,
    "children": [c.Name for c in obj.OutList] if hasattr(obj, "OutList") else [],
    "parents": [p.Name for p in obj.InList] if hasattr(obj, "InList") else [],
}}
"""
        result = await self.execute_python(code)

        if result.success and result.result:
            return ObjectInfo(**result.result)

        error_msg = result.error_traceback or "Failed to create object"
        raise ValueError(error_msg)

    async def edit_object(
        self,
        obj_name: str,
        properties: dict[str, Any],
        doc_name: str | None = None,
    ) -> ObjectInfo:
        """Edit object properties.

        Args:
            obj_name: Name of the object to edit.
            properties: Property values to set.
            doc_name: Document name (uses active if None).

        Returns:
            Updated ObjectInfo.

        Raises:
            ValueError: If object not found.
        """
        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({obj_name!r})
if obj is None:
    raise ValueError(f"Object not found: {obj_name!r}")

# Set properties
for prop_name, prop_val in {properties!r}.items():
    if hasattr(obj, prop_name):
        setattr(obj, prop_name, prop_val)

doc.recompute()

_result_ = {{
    "name": obj.Name,
    "label": obj.Label,
    "type_id": obj.TypeId,
    "visibility": obj.ViewObject.Visibility if hasattr(obj, "ViewObject") and obj.ViewObject else True,
    "children": [c.Name for c in obj.OutList] if hasattr(obj, "OutList") else [],
    "parents": [p.Name for p in obj.InList] if hasattr(obj, "InList") else [],
}}
"""
        result = await self.execute_python(code)

        if result.success and result.result:
            return ObjectInfo(**result.result)

        error_msg = result.error_traceback or "Failed to edit object"
        raise ValueError(error_msg)

    async def delete_object(
        self,
        obj_name: str,
        doc_name: str | None = None,
    ) -> None:
        """Delete an object.

        Args:
            obj_name: Name of the object to delete.
            doc_name: Document name (uses active if None).

        Raises:
            ValueError: If object not found.
        """
        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({obj_name!r})
if obj is None:
    raise ValueError(f"Object not found: {obj_name!r}")

doc.removeObject({obj_name!r})
_result_ = True
"""
        result = await self.execute_python(code)

        if not result.success:
            error_msg = result.error_traceback or "Failed to delete object"
            raise ValueError(error_msg)

    # =========================================================================
    # View and Screenshot
    # =========================================================================

    async def get_screenshot(
        self,
        view_angle: ViewAngle | None = None,
        width: int = 800,
        height: int = 600,
        doc_name: str | None = None,
    ) -> ScreenshotResult:
        """Capture a screenshot of the 3D view.

        Note: In embedded headless mode, screenshots are typically not available.

        Args:
            view_angle: View angle to set before capture.
            width: Image width in pixels.
            height: Image height in pixels.
            doc_name: Document name (uses active if None).

        Returns:
            ScreenshotResult with image data or error.
        """
        # Check if GUI is available
        gui_available = await self.is_gui_available()

        if not gui_available:
            return ScreenshotResult(
                success=False,
                error="Screenshots not available in headless mode",
                width=width,
                height=height,
                view_angle=view_angle,
            )

        # If GUI is available, attempt screenshot
        view_angle_str = view_angle.value if view_angle else "Isometric"
        code = f"""
import base64
import tempfile
import os

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

view = FreeCADGui.ActiveDocument.ActiveView
if view is None:
    raise ValueError("No active view")

# Set view angle
view_type = {view_angle_str!r}
if view_type == "FitAll":
    view.fitAll()
elif view_type == "Isometric":
    view.viewIsometric()
elif view_type == "Front":
    view.viewFront()
elif view_type == "Back":
    view.viewRear()
elif view_type == "Top":
    view.viewTop()
elif view_type == "Bottom":
    view.viewBottom()
elif view_type == "Left":
    view.viewLeft()
elif view_type == "Right":
    view.viewRight()

# Save to temp file and read
with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
    temp_path = f.name

# Flush pending paint events and frame the geometry, otherwise the grab
# can race the renderer and produce an image with no model in it.
FreeCADGui.updateGui()
_saved_camera = view.getCamera()
view.fitAll()
FreeCADGui.updateGui()

view.saveImage(temp_path, {width}, {height}, "Current")

# Restore the camera so a read-only screenshot does not move the user's
# view, and so zoom/camera tools stay observable across captures.
view.setCamera(_saved_camera)
FreeCADGui.updateGui()

with open(temp_path, "rb") as f:
    image_data = base64.b64encode(f.read()).decode("utf-8")

os.unlink(temp_path)

_result_ = {{
    "success": True,
    "data": image_data,
    "format": "png",
    "width": {width},
    "height": {height},
}}
"""
        result = await self.execute_python(code)

        if result.success and result.result:
            return ScreenshotResult(
                success=True,
                data=result.result["data"],
                format=result.result["format"],
                width=result.result["width"],
                height=result.result["height"],
                view_angle=view_angle,
            )

        return ScreenshotResult(
            success=False,
            error=result.error_traceback or "Failed to capture screenshot",
            width=width,
            height=height,
            view_angle=view_angle,
        )

    async def set_view(
        self,
        view_angle: ViewAngle,
        doc_name: str | None = None,
    ) -> None:
        """Set the 3D view angle.

        Args:
            view_angle: View angle to set.
            doc_name: Document name (uses active if None).
        """
        gui_available = await self.is_gui_available()

        if not gui_available:
            return  # Silently ignore in headless mode

        view_angle_str = view_angle.value
        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

view = FreeCADGui.ActiveDocument.ActiveView
if view is None:
    raise ValueError("No active view")

view_type = {view_angle_str!r}
if view_type == "FitAll":
    view.fitAll()
elif view_type == "Isometric":
    view.viewIsometric()
elif view_type == "Front":
    view.viewFront()
elif view_type == "Back":
    view.viewRear()
elif view_type == "Top":
    view.viewTop()
elif view_type == "Bottom":
    view.viewBottom()
elif view_type == "Left":
    view.viewLeft()
elif view_type == "Right":
    view.viewRight()

_result_ = True
"""
        await self.execute_python(code)

    # =========================================================================
    # Macros
    # =========================================================================

    def _get_macro_path(self) -> Path:
        """Get the FreeCAD macro directory path."""
        # Default FreeCAD macro locations
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "FreeCAD" / "Macro"
        elif sys.platform == "win32":
            return Path(os.environ.get("APPDATA", "")) / "FreeCAD" / "Macro"
        else:
            return Path.home() / ".local" / "share" / "FreeCAD" / "Macro"

    async def get_macros(self) -> list[MacroInfo]:
        """Get list of available macros.

        Returns:
            List of MacroInfo for each macro.
        """
        macro_path = self._get_macro_path()

        if not macro_path.exists():
            return []

        macros = []
        for macro_file in macro_path.glob("*.FCMacro"):
            description = ""
            try:
                content = macro_file.read_text()
                # Extract description from first comment block
                for line in content.split("\n"):
                    if line.startswith("#"):
                        desc_line = line.lstrip("#").strip()
                        if desc_line and not desc_line.startswith("!"):
                            description = desc_line
                            break
            except Exception:
                pass

            macros.append(
                MacroInfo(
                    name=macro_file.stem,
                    path=str(macro_file),
                    description=description,
                    is_system=False,
                )
            )

        return macros

    async def run_macro(
        self,
        macro_name: str,
        args: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        """Run a macro by name.

        Args:
            macro_name: Macro name (without .FCMacro extension).
            args: Arguments to pass to the macro.

        Returns:
            ExecutionResult from macro execution.
        """
        macro_path = self._get_macro_path() / f"{macro_name}.FCMacro"

        if not macro_path.exists():
            return ExecutionResult(
                success=False,
                result=None,
                stdout="",
                stderr=f"Macro not found: {macro_name}",
                execution_time_ms=0,
                error_type="FileNotFoundError",
            )

        try:
            macro_code = macro_path.read_text()
        except Exception as e:
            return ExecutionResult(
                success=False,
                result=None,
                stdout="",
                stderr=f"Failed to read macro: {e}",
                execution_time_ms=0,
                error_type=type(e).__name__,
            )

        # Prepend argument setup if provided
        if args:
            args_setup = "\n".join(f"{k} = {v!r}" for k, v in args.items())
            macro_code = args_setup + "\n" + macro_code

        return await self.execute_python(macro_code)

    async def create_macro(
        self,
        name: str,
        code: str,
        description: str = "",
    ) -> MacroInfo:
        """Create a new macro.

        Args:
            name: Macro name (without extension).
            code: Python code for the macro.
            description: Macro description.

        Returns:
            MacroInfo for the created macro.
        """
        macro_path = self._get_macro_path()
        macro_path.mkdir(parents=True, exist_ok=True)

        macro_file = macro_path / f"{name}.FCMacro"

        # Add description as header comment
        header = f"# {description}\n\n" if description else ""

        # Add standard imports
        full_code = f"""{header}# -*- coding: utf-8 -*-
# FreeCAD Macro: {name}
# Created via MCP Bridge

import FreeCAD
import FreeCADGui

{code}
"""
        macro_file.write_text(full_code)

        return MacroInfo(
            name=name,
            path=str(macro_file),
            description=description,
            is_system=False,
        )

    # =========================================================================
    # Workbenches
    # =========================================================================

    async def get_workbenches(self) -> list[WorkbenchInfo]:
        """Get list of available workbenches.

        Returns:
            List of WorkbenchInfo for each workbench.
        """
        gui_available = await self.is_gui_available()

        if not gui_available:
            # Return common workbenches for headless mode
            common_workbenches = [
                "StartWorkbench",
                "PartWorkbench",
                "PartDesignWorkbench",
                "DraftWorkbench",
                "SketcherWorkbench",
                "MeshWorkbench",
                "SpreadsheetWorkbench",
            ]
            return [
                WorkbenchInfo(name=wb, label=wb.replace("Workbench", ""))
                for wb in common_workbenches
            ]

        code = """
workbenches = []
active_wb = FreeCADGui.activeWorkbench()
active_name = active_wb.__class__.__name__ if active_wb else None

for name in FreeCADGui.listWorkbenches():
    wb = FreeCADGui.getWorkbench(name)
    workbenches.append({
        "name": name,
        "label": wb.MenuText if hasattr(wb, "MenuText") else name,
        "icon": wb.Icon if hasattr(wb, "Icon") else "",
        "is_active": name == active_name,
    })

_result_ = workbenches
"""
        result = await self.execute_python(code)

        if result.success and result.result:
            return [WorkbenchInfo(**wb) for wb in result.result]
        return []

    async def activate_workbench(self, workbench_name: str) -> None:
        """Activate a workbench.

        Args:
            workbench_name: Workbench internal name.

        Raises:
            ValueError: If workbench not found.
        """
        gui_available = await self.is_gui_available()

        if not gui_available:
            return  # Silently ignore in headless mode

        code = f"""
try:
    FreeCADGui.activateWorkbench({workbench_name!r})
    _result_ = True
except Exception as e:
    raise ValueError(f"Failed to activate workbench: {{e}}")
"""
        result = await self.execute_python(code)

        if not result.success:
            error_msg = result.error_traceback or "Failed to activate workbench"
            raise ValueError(error_msg)
