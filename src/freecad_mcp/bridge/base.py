"""Abstract bridge interface for FreeCAD communication.

This module defines the abstract base class and data types for all FreeCAD
bridge implementations. Bridges provide the communication layer between
the Robust MCP Server and FreeCAD instances.

Based on learnings from existing implementations:
- neka-nat: Queue-based thread safety for GUI operations
- jango: Multiple connection modes with recovery
- contextform: Comprehensive CAD operations
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

PROPERTY_VALUE_SERIALIZER = """
def serialize_property_value(value):
    if value is None or isinstance(value, (bool, float, str)):
        return value
    if isinstance(value, int):
        return value if -(2 ** 31) <= value < 2 ** 31 else str(value)
    if isinstance(value, dict):
        return {
            str(key): serialize_property_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [serialize_property_value(item) for item in value]
    return str(value)
"""


class ViewAngle(str, Enum):
    """Standard view angles for screenshots."""

    ISOMETRIC = "Isometric"
    FRONT = "Front"
    BACK = "Back"
    TOP = "Top"
    BOTTOM = "Bottom"
    LEFT = "Left"
    RIGHT = "Right"
    FIT_ALL = "FitAll"


class ObjectType(str, Enum):
    """FreeCAD object type categories."""

    PART = "Part"
    PART_DESIGN = "PartDesign"
    DRAFT = "Draft"
    SKETCHER = "Sketcher"
    FEM = "Fem"
    MESH = "Mesh"
    SPREADSHEET = "Spreadsheet"


@dataclass
class ExecutionResult:
    """Result of Python code execution in FreeCAD.

    Attributes:
        success: Whether execution completed without errors.
        result: The value assigned to `_result_` variable, or None.
        stdout: Captured standard output.
        stderr: Captured standard error.
        execution_time_ms: Time taken in milliseconds.
        error_type: Type of exception if failed, None otherwise.
        error_traceback: Full traceback if failed, None otherwise.
        execution_continues: Whether timed-out work is still running in FreeCAD.
    """

    success: bool
    result: Any
    stdout: str
    stderr: str
    execution_time_ms: float
    error_type: str | None = None
    error_traceback: str | None = None
    execution_continues: bool = False


@dataclass
class DocumentInfo:
    """Information about a FreeCAD document.

    Attributes:
        name: Internal document name (identifier).
        label: Display label (may differ from name).
        path: File path if saved, None otherwise.
        objects: List of object names in the document.
        is_modified: Whether document has unsaved changes.
        active_object: Name of the currently active object.
    """

    name: str
    label: str = ""
    path: str | None = None
    objects: list[str] = field(default_factory=list)
    is_modified: bool = False
    active_object: str | None = None

    def __post_init__(self) -> None:
        """Set label to name if not provided."""
        if not self.label:
            self.label = self.name


@dataclass
class ObjectInfo:
    """Information about a FreeCAD object.

    Attributes:
        name: Object name (identifier).
        label: Display label.
        type_id: FreeCAD TypeId string (e.g., "Part::Box").
        properties: Dictionary of property names to values.
        shape_info: Shape geometry details if applicable.
        children: List of child object names (OutList).
        parents: List of parent object names (InList).
        visibility: Whether object is visible in the view.
    """

    name: str
    label: str
    type_id: str
    properties: dict[str, Any] = field(default_factory=dict)
    shape_info: dict[str, Any] | None = None
    children: list[str] = field(default_factory=list)
    parents: list[str] = field(default_factory=list)
    visibility: bool = True


@dataclass
class ShapeInfo:
    """Detailed shape geometry information.

    Attributes:
        shape_type: Type of shape (Solid, Shell, Face, etc.).
        volume: Volume of the shape (for solids).
        area: Surface area of the shape.
        center_of_mass: Center of mass coordinates.
        bounding_box: Bounding box as (min, max) tuples.
        is_valid: Whether the shape is geometrically valid.
        is_closed: Whether the shape is closed.
        vertex_count: Number of vertices.
        edge_count: Number of edges.
        face_count: Number of faces.
    """

    shape_type: str
    volume: float | None = None
    area: float | None = None
    center_of_mass: tuple[float, float, float] | None = None
    bounding_box: (
        tuple[tuple[float, float, float], tuple[float, float, float]] | None
    ) = None
    is_valid: bool = True
    is_closed: bool = False
    vertex_count: int = 0
    edge_count: int = 0
    face_count: int = 0


@dataclass
class ScreenshotResult:
    """Result of a screenshot capture.

    Attributes:
        success: Whether screenshot was captured successfully.
        data: Base64-encoded image data.
        format: Image format (png, jpg).
        width: Image width in pixels.
        height: Image height in pixels.
        view_angle: The view angle used.
        error: Error message if failed.
    """

    success: bool
    data: str | None = None
    format: str = "png"
    width: int = 0
    height: int = 0
    view_angle: ViewAngle | None = None
    error: str | None = None


@dataclass
@dataclass
class WorkbenchInfo:
    """Information about a FreeCAD workbench.

    Attributes:
        name: Workbench internal name.
        label: Display label.
        icon: Icon resource path.
        is_active: Whether workbench is currently active.
    """

    name: str
    label: str
    icon: str = ""
    is_active: bool = False


@dataclass
class ConnectionStatus:
    """Status of the FreeCAD connection.

    Attributes:
        connected: Whether connection is established.
        mode: Connection mode (embedded, xmlrpc, socket).
        freecad_version: FreeCAD version string.
        gui_available: Whether GUI is available.
        last_ping_ms: Last ping latency in milliseconds.
        error: Connection error message if any.
    """

    connected: bool
    mode: str
    freecad_version: str = ""
    gui_available: bool = False
    last_ping_ms: float = 0
    error: str | None = None


class FreecadBridge(ABC):
    """Abstract base class for FreeCAD bridges.

    A bridge provides communication between the Robust MCP Server and a FreeCAD
    instance. Implementations may run FreeCAD in-process (embedded),
    communicate via XML-RPC, or use JSON-RPC over sockets.

    Thread Safety:
        GUI operations must be executed on the main thread. Implementations
        should use queue-based communication for thread safety (learned from
        neka-nat implementation).
    """

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to FreeCAD.

        Raises:
            ConnectionError: If connection cannot be established.
        """

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to FreeCAD.

        Should be called during cleanup to release resources.
        """

    @abstractmethod
    async def is_connected(self) -> bool:
        """Check if bridge is connected to FreeCAD.

        Returns:
            True if connected, False otherwise.
        """

    @abstractmethod
    async def ping(self) -> float:
        """Ping FreeCAD to check connection and measure latency.

        Returns:
            Round-trip time in milliseconds.

        Raises:
            ConnectionError: If not connected.
        """

    @abstractmethod
    async def get_status(self) -> ConnectionStatus:
        """Get detailed connection status.

        Returns:
            ConnectionStatus with full status information.
        """

    # =========================================================================
    # Code Execution
    # =========================================================================

    @abstractmethod
    async def execute_python(
        self,
        code: str,
        timeout_ms: int = 30000,
        *,
        transaction: str | None,
    ) -> ExecutionResult:
        """Execute Python code in FreeCAD context.

        The code runs with access to FreeCAD modules (FreeCAD, App, Gui).
        To return a value, assign it to the `_result_` variable.

        Args:
            code: Python code to execute.
            timeout_ms: Maximum execution time in milliseconds.
            transaction: Undo transaction name to arm around this call, or None
                for a read-only call. Keyword-only and required, so every call
                site declares whether it mutates.

        Returns:
            ExecutionResult with success status, output, and any errors.
        """

    # =========================================================================
    # Document Management
    # =========================================================================

    @abstractmethod
    async def get_documents(self) -> list[DocumentInfo]:
        """Get list of open documents.

        Returns:
            List of DocumentInfo for each open document.
        """

    @abstractmethod
    async def get_active_document(self) -> DocumentInfo | None:
        """Get the active document.

        Returns:
            DocumentInfo for active document, or None if no document is active.
        """

    @abstractmethod
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

    @abstractmethod
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

    @abstractmethod
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

    @abstractmethod
    async def close_document(self, doc_name: str | None = None) -> None:
        """Close a document.

        Args:
            doc_name: Document name (uses active if None).
        """

    # =========================================================================
    # Object Management
    # =========================================================================

    @abstractmethod
    async def get_objects(self, doc_name: str | None = None) -> list[ObjectInfo]:
        """Get all objects in a document.

        Args:
            doc_name: Document name (uses active if None).

        Returns:
            List of ObjectInfo for each object.
        """

    @abstractmethod
    async def get_object(
        self,
        obj_name: str,
        doc_name: str | None = None,
    ) -> ObjectInfo:
        """Get detailed object information.

        Args:
            obj_name: Name of the object.
            doc_name: Document name (uses active if None).

        Returns:
            ObjectInfo with full object details.

        Raises:
            ValueError: If object not found.
        """

    @abstractmethod
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

    @abstractmethod
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

    @abstractmethod
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

    # =========================================================================
    # View and Screenshot
    # =========================================================================

    @abstractmethod
    async def get_screenshot(
        self,
        view_angle: ViewAngle | None = None,
        width: int = 800,
        height: int = 600,
        doc_name: str | None = None,
    ) -> ScreenshotResult:
        """Capture a screenshot of the 3D view.

        Args:
            view_angle: View angle to set before capture.
            width: Image width in pixels.
            height: Image height in pixels.
            doc_name: Document name (uses active if None).

        Returns:
            ScreenshotResult with image data or error.
        """

    @abstractmethod
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

    # =========================================================================
    # Workbenches
    # =========================================================================

    @abstractmethod
    async def get_workbenches(self) -> list[WorkbenchInfo]:
        """Get list of available workbenches.

        Returns:
            List of WorkbenchInfo for each workbench.
        """

    @abstractmethod
    async def activate_workbench(self, workbench_name: str) -> None:
        """Activate a workbench.

        Args:
            workbench_name: Workbench internal name.

        Raises:
            ValueError: If workbench not found.
        """

    # =========================================================================
    # Version and Environment
    # =========================================================================

    @abstractmethod
    async def get_freecad_version(self) -> dict[str, Any]:
        """Get FreeCAD version information.

        Returns:
            Dictionary with version, build_date, python_version, gui_available.
        """

    @abstractmethod
    async def is_gui_available(self) -> bool:
        """Check if FreeCAD GUI is available.

        Returns:
            True if GUI is available, False for headless mode.
        """

    # =========================================================================
    # Console
    # =========================================================================

    @abstractmethod
    async def get_console_output(self, lines: int = 100) -> list[str]:
        """Get recent console output.

        Args:
            lines: Maximum number of lines to return.

        Returns:
            List of console output lines, most recent last.
        """
