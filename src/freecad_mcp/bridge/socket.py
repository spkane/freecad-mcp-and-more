"""Socket bridge for FreeCAD communication via JSON-RPC.

This bridge communicates with FreeCAD using JSON-RPC over TCP sockets,
providing a modern, lightweight alternative to XML-RPC.

Based on learnings from competitive analysis:
- Simple socket-based approach (inspired by bonninr/freecad_mcp)
- Connection recovery mechanisms (from jango-blockchained)
- Automatic reconnection on connection loss
"""

import asyncio
import contextlib
import json
import time
import uuid
from typing import Any

from freecad_mcp.bridge.base import (
    PROPERTY_VALUE_SERIALIZER,
    ConnectionStatus,
    DocumentInfo,
    ExecutionResult,
    FreecadBridge,
    ObjectInfo,
    ScreenshotResult,
    ViewAngle,
    WorkbenchInfo,
)
from freecad_mcp.bridge.view_code import build_feature_view_code

DEFAULT_SOCKET_HOST = "localhost"
DEFAULT_SOCKET_PORT = 9876
DEFAULT_TIMEOUT = 30.0


class JsonRpcError(Exception):
    """JSON-RPC error response."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        """Initialize JSON-RPC error.

        Args:
            code: Error code.
            message: Error message.
            data: Additional error data.
        """
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


class SocketBridge(FreecadBridge):
    """Bridge that communicates with FreeCAD via JSON-RPC over sockets.

    This bridge provides a lightweight, modern protocol for FreeCAD
    communication. It supports automatic reconnection and connection
    health monitoring.

    Attributes:
        host: Socket server hostname.
        port: Socket server port.
        timeout: Connection and request timeout in seconds.
    """

    def __init__(
        self,
        host: str = DEFAULT_SOCKET_HOST,
        port: int = DEFAULT_SOCKET_PORT,
        timeout: float = DEFAULT_TIMEOUT,
        auto_reconnect: bool = True,
    ) -> None:
        """Initialize the socket bridge.

        Args:
            host: Socket server hostname.
            port: Socket server port.
            timeout: Connection and request timeout in seconds.
            auto_reconnect: Whether to automatically reconnect on connection loss.
        """
        self._host = host
        self._port = port
        self._timeout = timeout
        self._auto_reconnect = auto_reconnect
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """Establish connection to FreeCAD socket server.

        Raises:
            ConnectionError: If connection cannot be established.
        """
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=self._timeout,
            )
            self._connected = True

            # Verify connection with a ping
            await self.ping()
        except TimeoutError as e:
            msg = f"Connection to {self._host}:{self._port} timed out"
            raise ConnectionError(msg) from e
        except Exception as e:
            self._connected = False
            msg = f"Failed to connect to {self._host}:{self._port}: {e}"
            raise ConnectionError(msg) from e

    async def disconnect(self) -> None:
        """Close connection to FreeCAD socket server."""
        if self._writer:
            self._writer.close()
            with contextlib.suppress(Exception):
                await self._writer.wait_closed()
        self._reader = None
        self._writer = None
        self._connected = False

    async def is_connected(self) -> bool:
        """Check if bridge is connected to FreeCAD."""
        if not self._connected or self._writer is None:
            return False

        try:
            await self.ping()
            return True
        except Exception:
            self._connected = False
            return False

    async def _send_request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Send a JSON-RPC request and wait for response.

        Args:
            method: Method name to call.
            params: Method parameters.

        Returns:
            Result from the JSON-RPC response.

        Raises:
            ConnectionError: If not connected.
            JsonRpcError: If server returns an error.
        """
        if self._writer is None or self._reader is None:
            msg = "Not connected to socket server"
            raise ConnectionError(msg)

        # Build JSON-RPC request
        request_id = str(uuid.uuid4())
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }

        async with self._lock:
            try:
                # Send request
                request_data = json.dumps(request).encode("utf-8") + b"\n"
                self._writer.write(request_data)
                await self._writer.drain()

                # Read response
                response_data = await asyncio.wait_for(
                    self._reader.readline(),
                    timeout=self._timeout,
                )

                if not response_data:
                    self._connected = False
                    msg = "Connection closed by server"
                    raise ConnectionError(msg)

                response = json.loads(response_data.decode("utf-8"))

                # Check for error
                if "error" in response:
                    error = response["error"]
                    raise JsonRpcError(
                        code=error.get("code", -1),
                        message=error.get("message", "Unknown error"),
                        data=error.get("data"),
                    )

                return response.get("result")

            except TimeoutError as e:
                msg = "Request timed out"
                raise ConnectionError(msg) from e
            except json.JSONDecodeError as e:
                msg = f"Invalid JSON response: {e}"
                raise ConnectionError(msg) from e
            except (ConnectionResetError, BrokenPipeError) as e:
                self._connected = False
                if self._auto_reconnect:
                    # Try to reconnect
                    try:
                        await self.connect()
                        return await self._send_request(method, params)
                    except Exception:
                        pass
                msg = f"Connection lost: {e}"
                raise ConnectionError(msg) from e

    async def ping(self) -> float:
        """Ping FreeCAD to check connection and measure latency.

        Returns:
            Round-trip time in milliseconds.

        Raises:
            ConnectionError: If not connected.
        """
        start = time.perf_counter()
        await self._send_request("ping")
        return (time.perf_counter() - start) * 1000

    async def get_status(self) -> ConnectionStatus:
        """Get detailed connection status.

        Returns:
            ConnectionStatus with full status information.
        """
        if not self._connected:
            return ConnectionStatus(
                connected=False,
                mode="socket",
                error="Not connected",
            )

        try:
            ping_ms = await self.ping()
            version_info = await self.get_freecad_version()
            gui_available = await self.is_gui_available()

            return ConnectionStatus(
                connected=True,
                mode="socket",
                freecad_version=version_info.get("version", "unknown"),
                gui_available=gui_available,
                last_ping_ms=ping_ms,
            )
        except Exception as e:
            return ConnectionStatus(
                connected=False,
                mode="socket",
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
        """Execute Python code in FreeCAD context via socket.

        Args:
            code: Python code to execute.
            timeout_ms: Maximum execution time in milliseconds.
            transaction: Undo transaction name to arm around this call, or None
                for a read-only call. Keyword-only and required, so every call
                site declares whether it mutates.

        Returns:
            ExecutionResult with execution outcome.
        """
        start = time.perf_counter()

        try:
            result = await asyncio.wait_for(
                self._send_request(
                    "execute",
                    {"code": code, "transaction": transaction},
                ),
                timeout=timeout_ms / 1000,
            )
            elapsed = (time.perf_counter() - start) * 1000

            if isinstance(result, dict):
                return ExecutionResult(
                    success=result.get("success", False),
                    result=result.get("result"),
                    stdout=result.get("stdout", ""),
                    stderr=result.get("stderr", ""),
                    execution_time_ms=elapsed,
                    error_type=result.get("error_type"),
                    error_traceback=result.get("error_traceback"),
                )
            else:
                return ExecutionResult(
                    success=True,
                    result=result,
                    stdout="",
                    stderr="",
                    execution_time_ms=elapsed,
                )

        except TimeoutError:
            return ExecutionResult(
                success=False,
                result=None,
                stdout="",
                stderr=f"Execution timed out after {timeout_ms}ms",
                execution_time_ms=float(timeout_ms),
                error_type="TimeoutError",
            )
        except JsonRpcError as e:
            elapsed = (time.perf_counter() - start) * 1000
            return ExecutionResult(
                success=False,
                result=None,
                stdout="",
                stderr=e.message,
                execution_time_ms=elapsed,
                error_type="JsonRpcError",
            )
        except ConnectionError as e:
            return ExecutionResult(
                success=False,
                result=None,
                stdout="",
                stderr=str(e),
                execution_time_ms=0,
                error_type="ConnectionError",
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
        result = await self.execute_python(code, transaction="Create Object")

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
        result = await self.execute_python(code, transaction="Edit Object")

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

doc.removeObject({obj_name!r})
_result_ = True
"""
        result = await self.execute_python(code, transaction="Delete Object")

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
        """Capture a screenshot of the 3D view via socket."""
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

# Check view type
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

    async def capture_feature_view(
        self,
        normal_source: str,
        side: str,
        focus: list[str] | None,
        padding: float,
        hide_construction: bool,
        width: int,
        height: int,
        doc_name: str | None,
    ) -> ScreenshotResult:
        """Capture a screenshot aimed along a named support's normal."""
        code = build_feature_view_code(
            normal_source=normal_source,
            side=side,
            focus=focus,
            padding=padding,
            hide_construction=hide_construction,
            width=width,
            height=height,
            doc_name=doc_name,
        )
        result = await self.execute_python(code, transaction=None)

        if result.success and result.result and result.result.get("success"):
            return ScreenshotResult(
                success=True,
                data=result.result["data"],
                format=result.result["format"],
                width=result.result["width"],
                height=result.result["height"],
            )

        error = (
            (result.result or {}).get("error")
            if result.success and result.result
            else None
        )
        return ScreenshotResult(
            success=False,
            error=error
            or result.error_traceback
            or result.stderr
            or "Failed to capture feature view",
            width=width,
            height=height,
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
    _result_ = True
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
    _result_ = True
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
output_lines = []

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
