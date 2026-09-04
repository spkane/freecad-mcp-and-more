"""FreeCAD bridge implementations.

This package provides bridge implementations for communicating with FreeCAD
in different modes (embedded, XML-RPC, and socket-based).

Bridge Modes:
- EmbeddedBridge: In-process FreeCAD for headless operation (fastest)
- XmlRpcBridge: XML-RPC protocol for GUI mode (neka-nat compatible)
- SocketBridge: JSON-RPC over TCP for modern, lightweight communication
"""

from freecad_mcp.bridge.base import (
    ConnectionStatus,
    DocumentInfo,
    ExecutionResult,
    FreecadBridge,
    ObjectInfo,
    ObjectType,
    ScreenshotResult,
    ShapeInfo,
    ViewAngle,
    WorkbenchInfo,
)
from freecad_mcp.bridge.embedded import EmbeddedBridge
from freecad_mcp.bridge.socket import JsonRpcError, SocketBridge
from freecad_mcp.bridge.xmlrpc import XmlRpcBridge

__all__ = [
    # Base classes and types
    "ConnectionStatus",
    "DocumentInfo",
    "ExecutionResult",
    "FreecadBridge",
    "ObjectInfo",
    "ObjectType",
    "ScreenshotResult",
    "ShapeInfo",
    "ViewAngle",
    "WorkbenchInfo",
    # Bridge implementations
    "EmbeddedBridge",
    "XmlRpcBridge",
    "SocketBridge",
    # Exceptions
    "JsonRpcError",
]
