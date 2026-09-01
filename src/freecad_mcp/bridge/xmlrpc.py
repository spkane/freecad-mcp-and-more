"""XML-RPC bridge for FreeCAD GUI mode communication.

This bridge connects to a FreeCAD instance running an XML-RPC server,
allowing remote control while FreeCAD has its GUI open.

Compatible with neka-nat/freecad-mcp XML-RPC protocol, providing
interoperability with existing FreeCAD Robust MCP addons.

Design inspired by neka-nat/freecad-mcp (MIT License):
- Uses neka-nat's proven XML-RPC protocol (port 9875)
- Connection health monitoring and auto-reconnect
- Timeout handling for long operations

Attribution:
    The XML-RPC protocol design and port selection (9875) were inspired by
    neka-nat/freecad-mcp (https://github.com/neka-nat/freecad-mcp), which is
    licensed under the MIT License. This implementation is a complete rewrite
    that maintains protocol compatibility.
"""

import asyncio
import threading
import time
import xmlrpc.client
from typing import Any

from freecad_mcp.bridge.base import (
    PROPERTY_VALUE_SERIALIZER,
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

DEFAULT_XMLRPC_HOST = "localhost"
DEFAULT_XMLRPC_PORT = 9875
DEFAULT_TIMEOUT = 30.0
TIMEOUT_GRACE_SECONDS = 1.0
_EXPIRED_REQUEST = object()


class XmlRpcBridge(FreecadBridge):
    """Bridge that communicates with FreeCAD via XML-RPC.

    This bridge connects to a FreeCAD instance that is running the
    XML-RPC server addon. It provides full access to FreeCAD functionality
    including GUI operations like screenshots.

    Attributes:
        host: XML-RPC server hostname.
        port: XML-RPC server port.
        timeout: Connection and request timeout in seconds.
    """

    def __init__(
        self,
        host: str = DEFAULT_XMLRPC_HOST,
        port: int = DEFAULT_XMLRPC_PORT,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize the XML-RPC bridge.

        Args:
            host: XML-RPC server hostname.
            port: XML-RPC server port.
            timeout: Connection and request timeout in seconds.
        """
        self._host = host
        self._port = port
        self._timeout = timeout
        self._proxy: xmlrpc.client.ServerProxy | None = None
        self._proxy_lock = threading.Lock()
        self._connected = False

    @property
    def _server_url(self) -> str:
        """Get the XML-RPC server URL."""
        return f"http://{self._host}:{self._port}"

    async def connect(self) -> None:
        """Establish connection to FreeCAD XML-RPC server.

        Raises:
            ConnectionError: If connection cannot be established.
        """
        loop = asyncio.get_event_loop()
        try:
            self._proxy = await loop.run_in_executor(
                None,
                lambda: xmlrpc.client.ServerProxy(
                    self._server_url,
                    allow_none=True,
                ),
            )
            # Test connection with a ping
            await self.ping()
            self._connected = True
        except ConnectionRefusedError as e:
            self._connected = False
            msg = self._get_connection_refused_message()
            raise ConnectionError(msg) from e
        except Exception as e:
            self._connected = False
            error_str = str(e)
            if "Connection refused" in error_str or "Errno 61" in error_str:
                msg = self._get_connection_refused_message()
            else:
                msg = f"Failed to connect to XML-RPC server at {self._server_url}: {e}"
            raise ConnectionError(msg) from e

    def _get_connection_refused_message(self) -> str:
        """Get a helpful error message when connection is refused."""
        return f"""
================================================================================
CONNECTION REFUSED: Cannot connect to FreeCAD at {self._server_url}

The FreeCAD Robust MCP Bridge server is not running. To fix this:

1. Start FreeCAD (the GUI application)

2. Start the MCP bridge using one of these methods:

   Option A: Using the Robust MCP Bridge Workbench (recommended)
   - Install via FreeCAD Addon Manager: Tools → Addon Manager
   - Search for "Robust MCP Bridge" and install
   - Switch to the Robust MCP Bridge workbench
   - Click "Start MCP Bridge" in the toolbar

   Option B: From source (for developers)
   - Run: just freecad::run-gui

3. You should see: "MCP Bridge started!"
   - XML-RPC: localhost:{self._port}
   - Socket: localhost:9876

4. Then restart your MCP client (e.g., restart Claude Code)
================================================================================
"""

    async def disconnect(self) -> None:
        """Close connection to FreeCAD XML-RPC server."""
        self._proxy = None
        self._connected = False

    async def is_connected(self) -> bool:
        """Check if bridge is connected to FreeCAD."""
        if not self._connected or self._proxy is None:
            return False

        try:
            await self.ping()
            return True
        except Exception:
            self._connected = False
            return False

    async def ping(self) -> float:
        """Ping FreeCAD to check connection and measure latency.

        Returns:
            Round-trip time in milliseconds.

        Raises:
            ConnectionError: If not connected.
        """
        if self._proxy is None:
            msg = "Not connected to XML-RPC server"
            raise ConnectionError(msg)

        loop = asyncio.get_event_loop()
        start = time.perf_counter()

        try:
            # Try standard system.listMethods or a simple execute
            if self._proxy is None:
                msg = "Not connected"
                raise ConnectionError(msg)
            proxy = self._proxy
            request_cancelled = threading.Event()
            deadline = time.perf_counter() + self._timeout

            def ping_request() -> Any:
                with self._proxy_lock:
                    if request_cancelled.is_set() or time.perf_counter() >= deadline:
                        return _EXPIRED_REQUEST
                    return proxy.execute("_result_ = True", 30000, None)

            result = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    ping_request,
                ),
                timeout=self._timeout,
            )
            if result is _EXPIRED_REQUEST:
                raise TimeoutError
        except TimeoutError as e:
            request_cancelled.set()
            msg = "Ping timed out"
            raise ConnectionError(msg) from e
        except Exception as e:
            msg = f"Ping failed: {e}"
            raise ConnectionError(msg) from e

        return (time.perf_counter() - start) * 1000

    async def get_status(self) -> ConnectionStatus:
        """Get detailed connection status.

        Returns:
            ConnectionStatus with full status information.
        """
        if not self._connected or self._proxy is None:
            return ConnectionStatus(
                connected=False,
                mode="xmlrpc",
                error="Not connected",
            )

        try:
            ping_ms = await self.ping()
            version_info = await self.get_freecad_version()
            gui_available = await self.is_gui_available()

            return ConnectionStatus(
                connected=True,
                mode="xmlrpc",
                freecad_version=version_info.get("version", "unknown"),
                gui_available=gui_available,
                last_ping_ms=ping_ms,
            )
        except Exception as e:
            return ConnectionStatus(
                connected=False,
                mode="xmlrpc",
                error=str(e),
            )

    # =========================================================================
    # Code Execution
    # =========================================================================

    async def execute_python(
        self,
        code: str,
        timeout_ms: int = 30000,
        *,
        transaction: str | None,
    ) -> ExecutionResult:
        """Execute Python code in FreeCAD context via XML-RPC.

        Args:
            code: Python code to execute.
            timeout_ms: Maximum execution time in milliseconds.
            transaction: Undo transaction name to arm around this call, or None
                for a read-only call. Keyword-only and required, so every call
                site declares whether it mutates.

        Returns:
            ExecutionResult with execution outcome.
        """
        if self._proxy is None:
            return ExecutionResult(
                success=False,
                result=None,
                stdout="",
                stderr="Not connected to XML-RPC server",
                execution_time_ms=0,
                error_type="ConnectionError",
            )

        loop = asyncio.get_event_loop()
        start = time.perf_counter()
        proxy = self._proxy
        client_timeout = (timeout_ms / 1000) + TIMEOUT_GRACE_SECONDS
        request_cancelled = threading.Event()
        request_started = threading.Event()
        execution_deadline = start + (timeout_ms / 1000)

        try:

            def execute_request() -> Any:
                with self._proxy_lock:
                    if (
                        request_cancelled.is_set()
                        or time.perf_counter() >= execution_deadline
                    ):
                        return _EXPIRED_REQUEST
                    if (
                        request_cancelled.is_set()
                        or time.perf_counter() >= execution_deadline
                    ):
                        return _EXPIRED_REQUEST
                    request_started.set()
                    return proxy.execute(code, timeout_ms, transaction)

            result = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    execute_request,
                ),
                timeout=client_timeout,
            )
            if result is _EXPIRED_REQUEST:
                raise TimeoutError
            elapsed = (time.perf_counter() - start) * 1000

            # Parse result from XML-RPC server
            if isinstance(result, dict):
                return ExecutionResult(
                    success=result.get("success", False),
                    result=result.get("result"),
                    stdout=result.get("stdout", ""),
                    stderr=result.get("stderr", ""),
                    execution_time_ms=elapsed,
                    error_type=result.get("error_type"),
                    error_traceback=(
                        result.get("error_traceback") or result.get("error_message")
                    ),
                    execution_continues=result.get("execution_continues", False),
                )
            else:
                # Simple result format
                return ExecutionResult(
                    success=True,
                    result=result,
                    stdout="",
                    stderr="",
                    execution_time_ms=elapsed,
                )

        except TimeoutError:
            request_cancelled.set()
            return ExecutionResult(
                success=False,
                result=None,
                stdout="",
                stderr=f"Execution timed out after {timeout_ms}ms",
                execution_time_ms=float(timeout_ms),
                error_type="TimeoutError",
                execution_continues=request_started.is_set(),
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            return ExecutionResult(
                success=False,
                result=None,
                stdout="",
                stderr=str(e),
                execution_time_ms=elapsed,
                error_type=type(e).__name__,
                error_traceback=str(e),
            )

    # =========================================================================
    # Document Management
    # =========================================================================

    async def get_documents(self) -> list[DocumentInfo]:
        """Get list of open documents."""
        result = await self.execute_python(
            """
_result_ = []
for doc in FreeCAD.listDocuments().values():
    _result_.append({
        "name": doc.Name,
        "label": doc.Label,
        "path": doc.FileName or None,
        "objects": [obj.Name for obj in doc.Objects],
        "is_modified": doc.Modified if hasattr(doc, "Modified") else False,
        "active_object": doc.ActiveObject.Name if doc.ActiveObject else None,
    })
""",
            transaction=None,
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
        "label": doc.Label,
        "path": doc.FileName or None,
        "objects": [obj.Name for obj in doc.Objects],
        "is_modified": doc.Modified if hasattr(doc, "Modified") else False,
        "active_object": doc.ActiveObject.Name if doc.ActiveObject else None,
    }
else:
    _result_ = None
""",
            transaction=None,
        )

        if result.success and result.result:
            return DocumentInfo(**result.result)
        return None

    async def create_document(
        self, name: str, label: str | None = None
    ) -> DocumentInfo:
        """Create a new document."""
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
""",
            transaction=None,
        )

        if result.success and result.result:
            return DocumentInfo(**result.result)

        error_msg = result.error_traceback or "Failed to create document"
        raise ValueError(error_msg)

    async def open_document(self, path: str) -> DocumentInfo:
        """Open an existing document."""
        result = await self.execute_python(
            f"""
import os
if not os.path.exists({path!r}):
    raise FileNotFoundError(f"File not found: {path!r}")

doc = FreeCAD.openDocument({path!r})
_result_ = {{
    "name": doc.Name,
    "label": doc.Label,
    "path": doc.FileName or None,
    "objects": [obj.Name for obj in doc.Objects],
    "is_modified": doc.Modified if hasattr(doc, "Modified") else False,
}}
""",
            transaction=None,
        )

        if result.success and result.result:
            return DocumentInfo(**result.result)

        if "FileNotFoundError" in (result.error_type or ""):
            raise FileNotFoundError(result.stderr)

        error_msg = result.error_traceback or "Failed to open document"
        raise ValueError(error_msg)

    async def save_document(
        self,
        doc_name: str | None = None,
        path: str | None = None,
    ) -> str:
        """Save a document."""
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
        result = await self.execute_python(code, transaction=None)

        if result.success and result.result:
            return result.result

        error_msg = result.error_traceback or "Failed to save document"
        raise ValueError(error_msg)

    async def close_document(self, doc_name: str | None = None) -> None:
        """Close a document."""
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
        result = await self.execute_python(code, transaction=None)

        if not result.success:
            error_msg = result.error_traceback or "Failed to close document"
            raise ValueError(error_msg)

    # =========================================================================
    # Object Management
    # =========================================================================

    async def get_objects(self, doc_name: str | None = None) -> list[ObjectInfo]:
        """Get all objects in a document."""
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
        result = await self.execute_python(code, transaction=None)

        if result.success and result.result:
            return [ObjectInfo(**obj) for obj in result.result]
        return []

    async def get_object(
        self,
        obj_name: str,
        doc_name: str | None = None,
    ) -> ObjectInfo:
        """Get detailed object information."""
        code = f"""
{PROPERTY_VALUE_SERIALIZER}

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({obj_name!r})
if obj is None:
    raise ValueError(f"Object not found: {obj_name!r}")

props = {{}}
for prop in obj.PropertiesList:
    try:
        props[prop] = serialize_property_value(getattr(obj, prop))
    except Exception:
        props[prop] = "<unreadable>"

shape_info = None
if hasattr(obj, "Shape"):
    shape = obj.Shape
    shape_info = {{
        "shape_type": shape.ShapeType,
        "volume": shape.Volume if hasattr(shape, "Volume") else None,
        "area": shape.Area if hasattr(shape, "Area") else None,
        "is_valid": shape.isValid(),
        "is_closed": shape.isClosed() if hasattr(shape, "isClosed") else False,
        "vertex_count": len(shape.Vertexes) if hasattr(shape, "Vertexes") else 0,
        "edge_count": len(shape.Edges) if hasattr(shape, "Edges") else 0,
        "face_count": len(shape.Faces) if hasattr(shape, "Faces") else 0,
    }}

_result_ = {{
    "name": obj.Name,
    "label": obj.Label,
    "type_id": obj.TypeId,
    "properties": props,
    "shape_info": shape_info,
    "children": [c.Name for c in obj.OutList] if hasattr(obj, "OutList") else [],
    "parents": [p.Name for p in obj.InList] if hasattr(obj, "InList") else [],
    "visibility": obj.ViewObject.Visibility if hasattr(obj, "ViewObject") and obj.ViewObject else True,
}}
"""
        result = await self.execute_python(code, transaction=None)

        if result.success and result.result:
            return ObjectInfo(**result.result)

        error_msg = result.error_traceback or result.stderr or "Failed to get object"
        raise ValueError(error_msg)

    async def create_object(
        self,
        type_id: str,
        name: str | None = None,
        properties: dict[str, Any] | None = None,
        doc_name: str | None = None,
    ) -> ObjectInfo:
        """Create a new object."""
        properties = properties or {}
        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

# Wrap in transaction for undo support
doc.openTransaction("Create Object")
try:
    obj = doc.addObject({type_id!r}, {name!r} or "")

    # Set properties
    for prop_name, prop_val in {properties!r}.items():
        if hasattr(obj, prop_name):
            setattr(obj, prop_name, prop_val)

    doc.recompute()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "name": obj.Name,
    "label": obj.Label,
    "type_id": obj.TypeId,
    "visibility": True,
    "children": [c.Name for c in obj.OutList] if hasattr(obj, "OutList") else [],
    "parents": [p.Name for p in obj.InList] if hasattr(obj, "InList") else [],
}}
"""
        result = await self.execute_python(code, transaction=None)

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
        """Edit object properties."""
        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({obj_name!r})
if obj is None:
    raise ValueError(f"Object not found: {obj_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Edit Object")
try:
    # Set properties
    for prop_name, prop_val in {properties!r}.items():
        if hasattr(obj, prop_name):
            setattr(obj, prop_name, prop_val)

    doc.recompute()
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = {{
    "name": obj.Name,
    "label": obj.Label,
    "type_id": obj.TypeId,
    "visibility": obj.ViewObject.Visibility if hasattr(obj, "ViewObject") and obj.ViewObject else True,
    "children": [c.Name for c in obj.OutList] if hasattr(obj, "OutList") else [],
    "parents": [p.Name for p in obj.InList] if hasattr(obj, "InList") else [],
}}
"""
        result = await self.execute_python(code, transaction=None)

        if result.success and result.result:
            return ObjectInfo(**result.result)

        error_msg = result.error_traceback or "Failed to edit object"
        raise ValueError(error_msg)

    async def delete_object(
        self,
        obj_name: str,
        doc_name: str | None = None,
    ) -> None:
        """Delete an object."""
        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

obj = doc.getObject({obj_name!r})
if obj is None:
    raise ValueError(f"Object not found: {obj_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Delete Object")
try:
    doc.removeObject({obj_name!r})
    doc.commitTransaction()
except Exception:
    doc.abortTransaction()
    raise

_result_ = True
"""
        result = await self.execute_python(code, transaction=None)

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
        """Capture a screenshot of the 3D view via XML-RPC."""
        view_angle_str = view_angle.value if view_angle else "Isometric"
        code = f"""
import base64
import tempfile
import os

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

# Check if GUI is available
if not FreeCAD.GuiUp:
    raise RuntimeError("GUI not available")


# Act on the document that was asked for, not whichever tab the GUI happens
# to be showing. Without this, a named document that is not already active
# targets a different model entirely.
_previous_doc = (
    FreeCADGui.ActiveDocument.Document.Name if FreeCADGui.ActiveDocument else None
)
if _previous_doc != doc.Name:
    FreeCADGui.setActiveDocument(doc.Name)
    FreeCADGui.updateGui()

view = FreeCADGui.ActiveDocument.ActiveView
if view is None:
    raise ValueError("No active view")

# Check if this is a 3D view (not TechDraw, Spreadsheet, etc.)
# Note: Use type() instead of __class__ because FreeCAD's View3DInventor
# has a broken __class__ attribute that returns a dict of methods.
view_type = type(view).__name__
if view_type not in ["View3DInventor", "View3DInventorPy"]:
    raise ValueError(f"Cannot capture screenshot from {{view_type}} view")

# Set view angle
view_type_str = {view_angle_str!r}
if view_type_str == "FitAll":
    view.fitAll()
elif view_type_str == "Isometric":
    view.viewIsometric()
elif view_type_str == "Front":
    view.viewFront()
elif view_type_str == "Back":
    view.viewRear()
elif view_type_str == "Top":
    view.viewTop()
elif view_type_str == "Bottom":
    view.viewBottom()
elif view_type_str == "Left":
    view.viewLeft()
elif view_type_str == "Right":
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

# Put the operator's document back; a read-only capture must not switch tabs.
if _previous_doc is not None and _previous_doc != doc.Name:
    FreeCADGui.setActiveDocument(_previous_doc)
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
        result = await self.execute_python(code, transaction=None)

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
            error=result.error_traceback
            or result.stderr
            or "Failed to capture screenshot",
            width=width,
            height=height,
            view_angle=view_angle,
        )

    async def set_view(
        self,
        view_angle: ViewAngle,
        doc_name: str | None = None,
    ) -> None:
        """Set the 3D view angle."""
        view_angle_str = view_angle.value
        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

if not FreeCAD.GuiUp:
    _result_ = True  # Silently succeed in headless mode
else:

    # Act on the document that was asked for, not whichever tab the GUI happens
    # to be showing. Without this, a named document that is not already active
    # targets a different model entirely.
    _previous_doc = (
        FreeCADGui.ActiveDocument.Document.Name if FreeCADGui.ActiveDocument else None
    )
    if _previous_doc != doc.Name:
        FreeCADGui.setActiveDocument(doc.Name)
        FreeCADGui.updateGui()

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
        await self.execute_python(code, transaction=None)

    # =========================================================================
    # Macros
    # =========================================================================

    async def get_macros(self) -> list[MacroInfo]:
        """Get list of available macros."""
        code = """
import os

# Get macro paths
macro_paths = []

# User macro path
user_path = FreeCAD.getUserMacroDir(True)
if os.path.exists(user_path):
    macro_paths.append(("user", user_path))

# System macro path
system_path = FreeCAD.getResourceDir() + "Macro"
if os.path.exists(system_path):
    macro_paths.append(("system", system_path))

macros = []
for source, path in macro_paths:
    for filename in os.listdir(path):
        if filename.endswith(".FCMacro"):
            macro_file = os.path.join(path, filename)
            description = ""
            try:
                with open(macro_file, "r") as f:
                    for line in f:
                        if line.startswith("#"):
                            desc = line.lstrip("#").strip()
                            if desc and not desc.startswith("!") and not desc.startswith("-*-"):
                                description = desc
                                break
            except Exception:
                pass

            macros.append({
                "name": filename[:-8],  # Remove .FCMacro
                "path": macro_file,
                "description": description,
                "is_system": source == "system",
            })

_result_ = macros
"""
        result = await self.execute_python(code, transaction=None)

        if result.success and result.result:
            return [MacroInfo(**m) for m in result.result]
        return []

    async def run_macro(
        self,
        macro_name: str,
        args: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        """Run a macro by name."""
        args = args or {}
        code = f"""
import os

# Find macro file
macro_name = {macro_name!r}
macro_file = None

# Check user macros first
user_path = FreeCAD.getUserMacroDir(True)
user_macro = os.path.join(user_path, macro_name + ".FCMacro")
if os.path.exists(user_macro):
    macro_file = user_macro

# Check system macros
if not macro_file:
    system_path = FreeCAD.getResourceDir() + "Macro"
    system_macro = os.path.join(system_path, macro_name + ".FCMacro")
    if os.path.exists(system_macro):
        macro_file = system_macro

if not macro_file:
    raise FileNotFoundError(f"Macro not found: {{macro_name}}")

# Set up arguments
args = {args!r}
for k, v in args.items():
    exec(f"{{k}} = {{v!r}}")

# Execute macro
with open(macro_file, "r") as f:
    macro_code = f.read()

exec(macro_code)
_result_ = True
"""
        return await self.execute_python(code, transaction=None)

    async def create_macro(
        self,
        name: str,
        code: str,
        description: str = "",
    ) -> MacroInfo:
        """Create a new macro."""
        create_code = f"""
import os

macro_path = FreeCAD.getUserMacroDir(True)
os.makedirs(macro_path, exist_ok=True)

macro_file = os.path.join(macro_path, {name!r} + ".FCMacro")

header = ""
if {description!r}:
    header = f"# {description!r}\\n\\n"

full_code = header + '''# -*- coding: utf-8 -*-
# FreeCAD Macro: {name}
# Created via MCP Bridge

import FreeCAD
import FreeCADGui

''' + {code!r}

with open(macro_file, "w") as f:
    f.write(full_code)

_result_ = {{
    "name": {name!r},
    "path": macro_file,
    "description": {description!r},
    "is_system": False,
}}
"""
        result = await self.execute_python(create_code, transaction=None)

        if result.success and result.result:
            return MacroInfo(**result.result)

        error_msg = result.error_traceback or "Failed to create macro"
        raise ValueError(error_msg)

    # =========================================================================
    # Workbenches
    # =========================================================================

    async def get_workbenches(self) -> list[WorkbenchInfo]:
        """Get list of available workbenches."""
        code = """
workbenches = []
active_wb = FreeCADGui.activeWorkbench() if FreeCAD.GuiUp else None
active_name = type(active_wb).__name__ if active_wb else None

if FreeCAD.GuiUp:
    for name in FreeCADGui.listWorkbenches():
        wb = FreeCADGui.getWorkbench(name)
        workbenches.append({
            "name": name,
            "label": wb.MenuText if hasattr(wb, "MenuText") else name,
            "icon": wb.Icon if hasattr(wb, "Icon") else "",
            "is_active": name == active_name,
        })
else:
    # Return common workbenches for headless mode
    common = ["StartWorkbench", "PartWorkbench", "PartDesignWorkbench",
              "DraftWorkbench", "SketcherWorkbench", "MeshWorkbench"]
    for name in common:
        workbenches.append({
            "name": name,
            "label": name.replace("Workbench", ""),
            "icon": "",
            "is_active": False,
        })

_result_ = workbenches
"""
        result = await self.execute_python(code, transaction=None)

        if result.success and result.result:
            return [WorkbenchInfo(**wb) for wb in result.result]
        return []

    async def activate_workbench(self, workbench_name: str) -> None:
        """Activate a workbench."""
        code = f"""
if FreeCAD.GuiUp:
    try:
        FreeCADGui.activateWorkbench({workbench_name!r})
        _result_ = True
    except Exception as e:
        raise ValueError(f"Failed to activate workbench: {{e}}")
else:
    _result_ = True  # Silently succeed in headless mode
"""
        result = await self.execute_python(code, transaction=None)

        if not result.success:
            error_msg = result.error_traceback or "Failed to activate workbench"
            raise ValueError(error_msg)

    # =========================================================================
    # Version and Environment
    # =========================================================================

    async def get_freecad_version(self) -> dict[str, Any]:
        """Get FreeCAD version information."""
        code = """
import sys
_result_ = {
    "version": ".".join(str(x) for x in FreeCAD.Version()[:3]),
    "version_tuple": FreeCAD.Version()[:3],
    "build_date": FreeCAD.Version()[3] if len(FreeCAD.Version()) > 3 else "unknown",
    "python_version": sys.version,
    "gui_available": FreeCAD.GuiUp,
}
"""
        result = await self.execute_python(code, transaction=None)

        if result.success and result.result:
            return result.result

        return {
            "version": "unknown",
            "version_tuple": [],
            "build_date": "unknown",
            "python_version": "",
            "gui_available": False,
        }

    async def is_gui_available(self) -> bool:
        """Check if FreeCAD GUI is available."""
        result = await self.execute_python("_result_ = FreeCAD.GuiUp", transaction=None)
        return bool(result.success and result.result)

    # =========================================================================
    # Console
    # =========================================================================

    async def get_console_output(self, lines: int = 100) -> list[str]:
        """Get recent console output."""
        code = f"""
# Try to get console output from FreeCAD
output_lines = []

# Try FreeCAD.Console if available
if hasattr(FreeCAD, 'Console'):
    console = FreeCAD.Console
    if hasattr(console, 'GetLog'):
        log = console.GetLog()
        if log:
            output_lines = log.split('\\n')[-{lines}:]

_result_ = output_lines
"""
        result = await self.execute_python(code, transaction=None)

        if result.success and result.result:
            return result.result
        return []
