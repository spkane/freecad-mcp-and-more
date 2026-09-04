# FreeCAD Robust MCP Server Architecture

## Executive Summary

This document describes the architecture for a Model Context Protocol (MCP) server that enables tight integration between AI assistants (Claude, GPT, and other MCP-compatible tools) and FreeCAD. The server provides AI assistants with full access to FreeCAD's Python console capabilities in both GUI and headless modes, enabling AI-assisted development and debugging of models, macros, and workbenches.

---

## Table of Contents

<!--TOC-->

- [FreeCAD Robust MCP Server Architecture](#freecad-robust-mcp-server-architecture)
  - [Executive Summary](#executive-summary)
  - [Table of Contents](#table-of-contents)
  - [Competitive Analysis](#competitive-analysis)
    - [Existing FreeCAD Robust MCP Servers](#existing-freecad-robust-mcp-servers)
    - [Our Differentiators](#our-differentiators)
    - [Key Learnings Applied](#key-learnings-applied)
  - [System Overview](#system-overview)
    - [What is MCP?](#what-is-mcp)
    - [What is FreeCAD?](#what-is-freecad)
    - [Integration Vision](#integration-vision)
  - [Architecture Goals](#architecture-goals)
    - [Primary Goals](#primary-goals)
    - [Secondary Goals](#secondary-goals)
  - [High-Level Architecture](#high-level-architecture)
    - [Architecture Pattern: Bridge with Adapter](#architecture-pattern-bridge-with-adapter)
    - [Module Structure](#module-structure)
  - [Component Design](#component-design)
    - [1. MCP Server (`server.py`)](#1-mcp-server-serverpy)
    - [2. Bridge Interface (`bridge/base.py`)](#2-bridge-interface-bridgebasepy)
    - [3. Embedded Bridge (`bridge/embedded.py`)](#3-embedded-bridge-bridgeembeddedpy)
    - [4. Socket Bridge (`bridge/socket.py`)](#4-socket-bridge-bridgesocketpy)
    - [5. FreeCAD Plugin (`freecad_plugin/server.py`)](#5-freecad-plugin-freecad_pluginserverpy)
  - [MCP Tools Specification](#mcp-tools-specification)
    - [Core Execution Tools](#core-execution-tools)
      - [`execute_python`](#execute_python)
      - [`execute_macro`](#execute_macro)
    - [Document Management Tools](#document-management-tools)
      - [`create_document`](#create_document)
      - [`open_document`](#open_document)
      - [`save_document`](#save_document)
    - [Object Creation Tools](#object-creation-tools)
      - [`create_primitive`](#create_primitive)
      - [`create_sketch`](#create_sketch)
    - [Geometry Tools](#geometry-tools)
      - [`add_sketch_geometry`](#add_sketch_geometry)
      - [`boolean_operation`](#boolean_operation)
    - [Export/Import Tools](#exportimport-tools)
      - [`export_mesh`](#export_mesh)
      - [`export_step`](#export_step)
    - [Debugging Tools](#debugging-tools)
      - [`inspect_object`](#inspect_object)
      - [`validate_model`](#validate_model)
    - [Workbench Tools](#workbench-tools)
      - [`activate_workbench`](#activate_workbench)
      - [`list_workbench_commands`](#list_workbench_commands)
  - [MCP Resources Specification](#mcp-resources-specification)
    - [Document Resources](#document-resources)
    - [Console Resources](#console-resources)
    - [Environment Resources](#environment-resources)
  - [Communication Patterns](#communication-patterns)
    - [Pattern 1: Stdio Transport (Default for MCP Clients)](#pattern-1-stdio-transport-default-for-mcp-clients)
    - [Pattern 2: HTTP Transport (Remote/Shared)](#pattern-2-http-transport-remoteshared)
    - [Pattern 3: GUI Integration](#pattern-3-gui-integration)
  - [Security Considerations](#security-considerations)
    - [Code Execution Sandboxing](#code-execution-sandboxing)
    - [Resource Limits](#resource-limits)
    - [Authentication (for HTTP transport)](#authentication-for-http-transport)
  - [Deployment Modes](#deployment-modes)
    - [Mode 1: XML-RPC Mode (Recommended)](#mode-1-xml-rpc-mode-recommended)
    - [Mode 2: Local Embedded (Linux Only)](#mode-2-local-embedded-linux-only)
    - [Mode 3: Local GUI with Plugin](#mode-3-local-gui-with-plugin)
    - [Mode 4: Remote/Docker](#mode-4-remotedocker)
  - [Error Handling](#error-handling)
    - [Error Categories](#error-categories)
    - [Error Response Format](#error-response-format)
  - [Future Extensibility](#future-extensibility)
    - [Planned Features](#planned-features)
    - [Extension Points](#extension-points)
  - [Summary](#summary)

<!--TOC-->

---

## Competitive Analysis

See [COMPARISON.md](../COMPARISON.md) for detailed analysis of existing implementations.

### Existing FreeCAD Robust MCP Servers

| Project                                                                             | Stars | Approach       | Strengths                                         |
| ----------------------------------------------------------------------------------- | ----- | -------------- | ------------------------------------------------- |
| [neka-nat/freecad-mcp](https://github.com/neka-nat/freecad-mcp)                     | 380+  | XML-RPC        | Thread-safe GUI ops, screenshots, parts library   |
| [jango-blockchained/mcp-freecad](https://github.com/jango-blockchained/mcp-freecad) | -     | Multi-mode     | 6 connection modes, multi-AI, connection recovery |
| [contextform/freecad-mcp](https://github.com/contextform/freecad-mcp)               | -     | Node.js bridge | 31+ CAD operations, installer, demos              |
| [ATOI-Ming/FreeCAD-MCP](https://github.com/ATOI-Ming/FreeCAD-MCP)                   | -     | Macro-centric  | GUI panel, macro templates, validation            |
| [bonninr/freecad_mcp](https://github.com/bonninr/freecad_mcp)                       | -     | Simple socket  | Minimal, lightweight                              |

### Our Differentiators

1. **True Headless Mode**: Embedded bridge runs FreeCAD in-process (unique)
1. **Dual Protocol**: XML-RPC (compatibility) + JSON-RPC (modern)
1. **MCP Resources**: Document/object introspection (no other impl has this)
1. **MCP Prompts**: Guided workflow templates (unique)
1. **Developer Focus**: Debugging tools, console access, macro development
1. **Thread-Safe Design**: Queue-based GUI operations (learned from neka-nat)
1. **Connection Resilience**: Auto-reconnect with health monitoring

### Key Learnings Applied

1. **From neka-nat**: Queue-based GUI thread safety, smart screenshot handling
1. **From jango**: Multiple connection modes, connection recovery
1. **From contextform**: Comprehensive PartDesign/Part operations
1. **From ATOI-Ming**: Macro templates, validation, automatic imports

---

## System Overview

### What is MCP?

The [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) is a standardized protocol that allows LLM applications (like Claude Code, GPT-based tools, and other MCP clients) to interact with external systems through:

- **Tools**: Executable functions that perform actions (like POST endpoints)
- **Resources**: Data sources that provide context (like GET endpoints)
- **Prompts**: Reusable templates for LLM interactions

### What is FreeCAD?

[FreeCAD](https://www.freecadweb.org/) is an open-source parametric 3D CAD modeler with:

- A comprehensive Python API for scripting
- GUI mode with interactive Python console
- Headless mode (`freecadcmd`) for batch processing
- Workbench architecture for domain-specific tools
- Full access to geometry, constraints, and document structure via Python

### Integration Vision

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                           Claude Code                                    │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  User Request: "Create a parametric gear with 20 teeth"         │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                │                                         │
│                                ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │               MCP Client (Claude Code, GPT, etc.)                │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                 │
                     MCP Protocol (stdio/HTTP)
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      FreeCAD Robust MCP Server                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                   │
│  │    Tools     │  │  Resources   │  │   Prompts    │                   │
│  │ - execute_py │  │ - documents  │  │ - modeling   │                   │
│  │ - create_obj │  │ - objects    │  │ - debugging  │                   │
│  │ - export     │  │ - console    │  │ - macros     │                   │
│  └──────────────┘  └──────────────┘  └──────────────┘                   │
│                                │                                         │
│                    ┌───────────┴───────────┐                            │
│                    ▼                       ▼                            │
│         ┌──────────────────┐    ┌──────────────────┐                    │
│         │  FreeCAD Bridge  │    │  FreeCAD Bridge  │                    │
│         │   (GUI Mode)     │    │ (Headless Mode)  │                    │
│         └──────────────────┘    └──────────────────┘                    │
└─────────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         FreeCAD Instance                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │  Documents  │  │   Objects   │  │ Workbenches │  │   Macros    │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Architecture Goals

### Primary Goals

1. **Full Python Console Access**: Execute arbitrary Python code in FreeCAD's context
1. **Bidirectional Communication**: Send commands and receive results/errors
1. **Dual Mode Support**: Work with both GUI and headless FreeCAD instances
1. **Real-time Feedback**: Stream console output and execution results
1. **Document Introspection**: Query and understand FreeCAD document structure
1. **Safe Execution**: Sandboxed execution with timeout and resource limits

### Secondary Goals

1. **Macro Development**: Assist in writing, testing, and debugging macros
1. **Workbench Integration**: Access workbench-specific functionality
1. **Model Validation**: Check model integrity and constraints
1. **Export Capabilities**: Generate various output formats (STEP, STL, etc.)
1. **Version Compatibility**: Support FreeCAD 1.0+

---

## High-Level Architecture

### Architecture Pattern: Bridge with Adapter

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                         MCP Server Layer                                 │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                     FastMCP Application                             │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │ │
│  │  │ Tool     │  │ Resource │  │ Prompt   │  │ Lifecycle│           │ │
│  │  │ Registry │  │ Registry │  │ Registry │  │ Manager  │           │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘           │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                    │                                     │
│                                    ▼                                     │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                    FreeCAD Bridge Interface                         │ │
│  │                    (Abstract Base Class)                            │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                    ╱                               ╲                     │
│                   ╱                                 ╲                    │
│  ┌─────────────────────────────┐  ┌─────────────────────────────┐      │
│  │   EmbeddedBridge            │  │   SocketBridge              │      │
│  │   (In-process FreeCAD)      │  │   (Remote FreeCAD)          │      │
│  │                             │  │                             │      │
│  │ - Direct Python API access  │  │ - TCP/Unix socket comm      │      │
│  │ - Headless mode only        │  │ - GUI or headless mode      │      │
│  │ - Fastest execution         │  │ - Process isolation         │      │
│  └─────────────────────────────┘  └─────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────────┘
```

### Module Structure

```text
freecad_mcp/
├── __init__.py
├── server.py                 # Main MCP server entry point
├── config.py                 # Configuration management
│
├── bridge/                   # FreeCAD communication layer
│   ├── __init__.py
│   ├── base.py              # Abstract bridge interface
│   ├── embedded.py          # In-process FreeCAD bridge (Linux only)
│   ├── socket.py            # JSON-RPC socket bridge
│   ├── xmlrpc.py            # XML-RPC bridge (recommended)
│   └── protocol.py          # Wire protocol for socket communication
│
├── tools/                    # MCP tool implementations (150+ tools)
│   ├── __init__.py
│   ├── execution.py         # Python execution & debugging (4 tools)
│   ├── documents.py         # Document management (7 tools)
│   ├── objects.py           # Object creation/manipulation (12 tools)
│   ├── partdesign.py        # PartDesign parametric modeling (19 tools)
│   ├── view.py              # View, camera, display (11 tools)
│   ├── export.py            # Export/import operations (7 tools)
│   └── macros.py            # Macro management (6 tools)
│
├── resources/                # MCP resource implementations
│   ├── __init__.py
│   └── freecad.py           # Document, console, capabilities resources
│
├── prompts/                  # MCP prompt templates
│   ├── __init__.py
│   └── freecad.py           # Modeling and debugging prompts
│
├── freecad_plugin/          # Plugin to install IN FreeCAD
│   ├── __init__.py
│   ├── server.py            # XML-RPC/JSON-RPC server
│   ├── handlers.py          # Request handlers
│   ├── blocking_bridge.py   # Blocking server (keeps FreeCAD running)
│   └── startup_bridge.py    # Non-blocking startup (for interactive GUI)
│
└── utils/                    # Utility modules
    └── __init__.py
```

---

## Component Design

### 1. MCP Server (`server.py`)

The main entry point using FastMCP from the official MCP Python SDK.

```python
"""FreeCAD Robust MCP Server - Main entry point."""

from mcp.server.fastmcp import FastMCP

from freecad_mcp.config import ServerConfig
from freecad_mcp.bridge import create_bridge
from freecad_mcp.tools import register_tools
from freecad_mcp.resources import register_all_resources
from freecad_mcp.prompts import register_all_prompts

mcp = FastMCP(
    name="freecad-mcp",
    version="0.1.0",
    description="MCP server for FreeCAD integration with AI assistants"
)

# Bridge instance (initialized on startup)
bridge = None

@mcp.on_startup
async def startup():
    """Initialize FreeCAD bridge on server startup."""
    global bridge
    config = ServerConfig.from_env()
    bridge = await create_bridge(config)

@mcp.on_shutdown
async def shutdown():
    """Clean up FreeCAD bridge on server shutdown."""
    if bridge:
        await bridge.close()
```

### 2. Bridge Interface (`bridge/base.py`)

Abstract interface for FreeCAD communication.

```python
"""Abstract bridge interface for FreeCAD communication."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

@dataclass
class ExecutionResult:
    """Result of Python code execution."""
    success: bool
    result: Any
    stdout: str
    stderr: str
    execution_time_ms: float
    error_type: str | None = None
    error_traceback: str | None = None

@dataclass
class DocumentInfo:
    """Information about a FreeCAD document."""
    name: str
    path: str | None
    objects: list[str]
    is_modified: bool

@dataclass
class ObjectInfo:
    """Information about a FreeCAD object."""
    name: str
    label: str
    type_id: str
    properties: dict[str, Any]
    shape_info: dict[str, Any] | None
    children: list[str]

class FreecadBridge(ABC):
    """Abstract base class for FreeCAD bridges."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to FreeCAD."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to FreeCAD."""
        pass

    @abstractmethod
    async def is_connected(self) -> bool:
        """Check if bridge is connected."""
        pass

    @abstractmethod
    async def execute_python(
        self,
        code: str,
        timeout_ms: int = 30000
    ) -> ExecutionResult:
        """Execute Python code in FreeCAD context."""
        pass

    @abstractmethod
    async def get_documents(self) -> list[DocumentInfo]:
        """Get list of open documents."""
        pass

    @abstractmethod
    async def get_active_document(self) -> DocumentInfo | None:
        """Get the active document."""
        pass

    @abstractmethod
    async def get_object(
        self,
        doc_name: str,
        obj_name: str
    ) -> ObjectInfo:
        """Get detailed object information."""
        pass

    @abstractmethod
    async def get_console_output(
        self,
        lines: int = 100
    ) -> list[str]:
        """Get recent console output."""
        pass

    @abstractmethod
    async def get_freecad_version(self) -> dict[str, Any]:
        """Get FreeCAD version information."""
        pass

    @abstractmethod
    async def is_gui_available(self) -> bool:
        """Check if GUI is available."""
        pass
```

### 3. Embedded Bridge (`bridge/embedded.py`)

For running FreeCAD in-process (headless mode).

```python
"""Embedded bridge - runs FreeCAD in-process."""

import asyncio
import sys
import io
from contextlib import redirect_stdout, redirect_stderr
from typing import Any

from freecad_mcp.bridge.base import (
    FreecadBridge,
    ExecutionResult,
    DocumentInfo,
    ObjectInfo,
)

class EmbeddedBridge(FreecadBridge):
    """Bridge that runs FreeCAD embedded in the MCP server process."""

    def __init__(self, freecad_path: str | None = None):
        self._freecad_path = freecad_path
        self._fc_module = None
        self._executor = None

    async def connect(self) -> None:
        """Import and initialize FreeCAD."""
        if self._freecad_path:
            sys.path.insert(0, self._freecad_path)

        # Run import in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        self._fc_module = await loop.run_in_executor(
            None, self._import_freecad
        )

    def _import_freecad(self):
        """Import FreeCAD module."""
        import FreeCAD
        return FreeCAD

    async def execute_python(
        self,
        code: str,
        timeout_ms: int = 30000
    ) -> ExecutionResult:
        """Execute Python code in FreeCAD context."""
        import time

        start = time.perf_counter()
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        # Build execution context with FreeCAD modules
        exec_globals = {
            "FreeCAD": self._fc_module,
            "App": self._fc_module,
            "__builtins__": __builtins__,
        }

        # Add GUI module if available
        if await self.is_gui_available():
            import FreeCADGui
            exec_globals["FreeCADGui"] = FreeCADGui
            exec_globals["Gui"] = FreeCADGui

        try:
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                # Execute with timeout
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: exec(compile(code, "<mcp>", "exec"), exec_globals)
                    ),
                    timeout=timeout_ms / 1000
                )

            elapsed = (time.perf_counter() - start) * 1000

            return ExecutionResult(
                success=True,
                result=exec_globals.get("_result_"),  # Convention for return values
                stdout=stdout_capture.getvalue(),
                stderr=stderr_capture.getvalue(),
                execution_time_ms=elapsed,
            )

        except asyncio.TimeoutError:
            return ExecutionResult(
                success=False,
                result=None,
                stdout=stdout_capture.getvalue(),
                stderr=stderr_capture.getvalue(),
                execution_time_ms=timeout_ms,
                error_type="TimeoutError",
                error_traceback=f"Execution timed out after {timeout_ms}ms",
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
```

### 4. Socket Bridge (`bridge/socket.py`)

For communicating with a running FreeCAD instance (GUI or remote).

```python
"""Socket bridge - communicates with FreeCAD over TCP/Unix socket."""

import asyncio
import json
from typing import Any

from freecad_mcp.bridge.base import (
    FreecadBridge,
    ExecutionResult,
    DocumentInfo,
    ObjectInfo,
)
from freecad_mcp.bridge.protocol import MCPWireProtocol

class SocketBridge(FreecadBridge):
    """Bridge that communicates with FreeCAD over sockets."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 9876,
        unix_socket: str | None = None,
    ):
        self._host = host
        self._port = port
        self._unix_socket = unix_socket
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._protocol = MCPWireProtocol()
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}

    async def connect(self) -> None:
        """Connect to FreeCAD socket server."""
        if self._unix_socket:
            self._reader, self._writer = await asyncio.open_unix_connection(
                self._unix_socket
            )
        else:
            self._reader, self._writer = await asyncio.open_connection(
                self._host, self._port
            )

        # Start response reader task
        asyncio.create_task(self._read_responses())

    async def _read_responses(self) -> None:
        """Background task to read responses from FreeCAD."""
        while self._reader:
            try:
                data = await self._reader.readline()
                if not data:
                    break

                response = self._protocol.decode(data)
                request_id = response.get("id")

                if request_id in self._pending:
                    self._pending[request_id].set_result(response)

            except Exception as e:
                # Handle connection errors
                break

    async def _send_request(
        self,
        method: str,
        params: dict[str, Any]
    ) -> dict[str, Any]:
        """Send a request and wait for response."""
        self._request_id += 1
        request_id = self._request_id

        request = {
            "id": request_id,
            "method": method,
            "params": params,
        }

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future

        try:
            data = self._protocol.encode(request)
            self._writer.write(data)
            await self._writer.drain()

            response = await asyncio.wait_for(future, timeout=60.0)
            return response

        finally:
            del self._pending[request_id]

    async def execute_python(
        self,
        code: str,
        timeout_ms: int = 30000
    ) -> ExecutionResult:
        """Execute Python code in FreeCAD context."""
        response = await self._send_request("execute", {
            "code": code,
            "timeout_ms": timeout_ms,
        })

        if "error" in response:
            return ExecutionResult(
                success=False,
                result=None,
                stdout="",
                stderr=response["error"]["message"],
                execution_time_ms=0,
                error_type=response["error"].get("type", "Error"),
                error_traceback=response["error"].get("traceback"),
            )

        result = response["result"]
        return ExecutionResult(
            success=True,
            result=result.get("value"),
            stdout=result.get("stdout", ""),
            stderr=result.get("stderr", ""),
            execution_time_ms=result.get("execution_time_ms", 0),
        )
```

### 5. FreeCAD Plugin (`freecad_plugin/server.py`)

Plugin that runs inside FreeCAD to accept socket connections.

```python
"""FreeCAD plugin - Socket server running inside FreeCAD."""

import asyncio
import json
import threading
import io
from contextlib import redirect_stdout, redirect_stderr
import FreeCAD
import FreeCADGui

class FreecadMCPPlugin:
    """Plugin that runs inside FreeCAD to handle MCP bridge requests."""

    def __init__(self, host: str = "localhost", port: int = 9876):
        self._host = host
        self._port = port
        self._server = None
        self._loop = None
        self._thread = None

    def start(self) -> None:
        """Start the socket server in a background thread."""
        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()
        FreeCAD.Console.PrintMessage(
            f"MCP Bridge server started on {self._host}:{self._port}\n"
        )

    def _run_server(self) -> None:
        """Run the asyncio event loop in background thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        self._loop.run_until_complete(self._start_server())
        self._loop.run_forever()

    async def _start_server(self) -> None:
        """Start the TCP server."""
        self._server = await asyncio.start_server(
            self._handle_client,
            self._host,
            self._port,
        )

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter
    ) -> None:
        """Handle a connected client."""
        try:
            while True:
                data = await reader.readline()
                if not data:
                    break

                request = json.loads(data.decode())
                response = await self._process_request(request)

                writer.write(json.dumps(response).encode() + b"\n")
                await writer.drain()

        except Exception as e:
            FreeCAD.Console.PrintError(f"MCP client error: {e}\n")
        finally:
            writer.close()

    async def _process_request(self, request: dict) -> dict:
        """Process a single request."""
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        try:
            if method == "execute":
                result = await self._execute_python(params)
            elif method == "get_documents":
                result = self._get_documents()
            elif method == "get_object":
                result = self._get_object(params)
            elif method == "get_version":
                result = self._get_version()
            else:
                return {
                    "id": request_id,
                    "error": {"message": f"Unknown method: {method}"}
                }

            return {"id": request_id, "result": result}

        except Exception as e:
            import traceback
            return {
                "id": request_id,
                "error": {
                    "type": type(e).__name__,
                    "message": str(e),
                    "traceback": traceback.format_exc(),
                }
            }

    async def _execute_python(self, params: dict) -> dict:
        """Execute Python code in FreeCAD's main thread."""
        import time

        code = params["code"]
        timeout_ms = params.get("timeout_ms", 30000)

        # Must execute in main thread for FreeCAD compatibility
        result_holder = {}

        def execute():
            start = time.perf_counter()
            stdout_capture = io.StringIO()
            stderr_capture = io.StringIO()

            exec_globals = {
                "FreeCAD": FreeCAD,
                "App": FreeCAD,
                "FreeCADGui": FreeCADGui,
                "Gui": FreeCADGui,
                "__builtins__": __builtins__,
            }

            try:
                with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                    exec(compile(code, "<mcp>", "exec"), exec_globals)

                result_holder["value"] = exec_globals.get("_result_")
                result_holder["stdout"] = stdout_capture.getvalue()
                result_holder["stderr"] = stderr_capture.getvalue()
                result_holder["execution_time_ms"] = (
                    time.perf_counter() - start
                ) * 1000
                result_holder["success"] = True

            except Exception as e:
                import traceback
                result_holder["success"] = False
                result_holder["error_type"] = type(e).__name__
                result_holder["error_message"] = str(e)
                result_holder["error_traceback"] = traceback.format_exc()
                result_holder["stdout"] = stdout_capture.getvalue()
                result_holder["stderr"] = stderr_capture.getvalue()
                result_holder["execution_time_ms"] = (
                    time.perf_counter() - start
                ) * 1000

        # Schedule execution in FreeCAD's main thread
        # Use FreeCAD's timer mechanism for thread safety
        from PySide2 import QtCore

        event = threading.Event()

        def main_thread_execute():
            execute()
            event.set()

        QtCore.QTimer.singleShot(0, main_thread_execute)

        # Wait for execution with timeout
        if not event.wait(timeout=timeout_ms / 1000):
            return {
                "success": False,
                "error_type": "TimeoutError",
                "error_message": f"Execution timed out after {timeout_ms}ms",
            }

        return result_holder
```

---

## MCP Tools Specification

### Core Execution Tools

#### `execute_python`

Execute arbitrary Python code in FreeCAD's context.

```python
@mcp.tool()
async def execute_python(
    code: str,
    timeout_ms: int = 30000,
    capture_result: bool = True,
) -> dict:
    """Execute Python code in FreeCAD's Python console context.

    Args:
        code: Python code to execute. Use `_result_ = value` to return data.
        timeout_ms: Maximum execution time in milliseconds.
        capture_result: Whether to capture and return the result value.

    Returns:
        Dictionary containing:
        - success: Whether execution completed without errors
        - result: The value assigned to `_result_` if capture_result is True
        - stdout: Captured standard output
        - stderr: Captured standard error
        - execution_time_ms: Time taken in milliseconds
        - error_type: Type of exception if failed
        - error_traceback: Full traceback if failed

    Example:
        >>> execute_python('''
        ... import Part
        ... box = Part.makeBox(10, 10, 10)
        ... _result_ = {"volume": box.Volume, "area": box.Area}
        ... ''')
    """
    result = await bridge.execute_python(code, timeout_ms)
    return result.__dict__
```

#### `execute_macro`

Run a FreeCAD macro file.

```python
@mcp.tool()
async def execute_macro(
    macro_name: str,
    args: dict | None = None,
) -> dict:
    """Execute a FreeCAD macro by name.

    Args:
        macro_name: Name of the macro (without .FCMacro extension)
        args: Optional arguments to pass to the macro as variables

    Returns:
        Execution result with stdout/stderr and any errors
    """
    # Build code that loads and runs the macro
    code = f'''
import FreeCAD
macro_path = FreeCAD.getUserMacroDir(True) + "/{macro_name}.FCMacro"
with open(macro_path) as f:
    macro_code = f.read()
exec(macro_code)
'''
    return await bridge.execute_python(code)
```

### Document Management Tools

#### `create_document`

```python
@mcp.tool()
async def create_document(
    name: str = "Unnamed",
    label: str | None = None,
) -> dict:
    """Create a new FreeCAD document.

    Args:
        name: Internal document name (no spaces)
        label: Display label (can contain spaces)

    Returns:
        Document information including name and path
    """
    code = f'''
doc = FreeCAD.newDocument("{name}")
if {repr(label)}:
    doc.Label = {repr(label)}
_result_ = {{"name": doc.Name, "label": doc.Label}}
'''
    return await bridge.execute_python(code)
```

#### `open_document`

```python
@mcp.tool()
async def open_document(path: str) -> dict:
    """Open an existing FreeCAD document.

    Args:
        path: Full path to the .FCStd file

    Returns:
        Document information
    """
    code = f'''
doc = FreeCAD.openDocument({repr(path)})
_result_ = {{
    "name": doc.Name,
    "label": doc.Label,
    "path": doc.FileName,
    "objects": [obj.Name for obj in doc.Objects],
}}
'''
    return await bridge.execute_python(code)
```

#### `save_document`

```python
@mcp.tool()
async def save_document(
    doc_name: str | None = None,
    path: str | None = None,
) -> dict:
    """Save a FreeCAD document.

    Args:
        doc_name: Document name (uses active document if None)
        path: Save path (uses existing path if None)

    Returns:
        Save status and path
    """
    code = f'''
doc = FreeCAD.getDocument({repr(doc_name)}) if {repr(doc_name)} else FreeCAD.ActiveDocument
if {repr(path)}:
    doc.saveAs({repr(path)})
else:
    doc.save()
_result_ = {{"saved": True, "path": doc.FileName}}
'''
    return await bridge.execute_python(code)
```

### Object Creation Tools

#### `create_primitive`

```python
@mcp.tool()
async def create_primitive(
    primitive_type: str,
    name: str | None = None,
    parameters: dict | None = None,
    doc_name: str | None = None,
) -> dict:
    """Create a Part primitive object.

    Args:
        primitive_type: One of 'Box', 'Cylinder', 'Sphere', 'Cone', 'Torus'
        name: Object name (auto-generated if None)
        parameters: Primitive-specific parameters (e.g., {"Length": 10, "Width": 5})
        doc_name: Target document (active document if None)

    Returns:
        Created object information
    """
    params = parameters or {}
    code = f'''
import Part
doc = FreeCAD.getDocument({repr(doc_name)}) if {repr(doc_name)} else FreeCAD.ActiveDocument
obj = doc.addObject("Part::{primitive_type}", {repr(name) if name else repr(primitive_type)})
for key, value in {repr(params)}.items():
    setattr(obj, key, value)
doc.recompute()
_result_ = {{
    "name": obj.Name,
    "label": obj.Label,
    "type": obj.TypeId,
    "properties": {{p: getattr(obj, p) for p in obj.PropertiesList[:20]}},
}}
'''
    return await bridge.execute_python(code)
```

#### `create_sketch`

```python
@mcp.tool()
async def create_sketch(
    plane: str = "XY",
    name: str | None = None,
    doc_name: str | None = None,
) -> dict:
    """Create a new sketch on a standard plane.

    Args:
        plane: One of 'XY', 'XZ', 'YZ'
        name: Sketch name
        doc_name: Target document

    Returns:
        Sketch object information
    """
    plane_vectors = {
        "XY": "FreeCAD.Vector(0, 0, 1)",
        "XZ": "FreeCAD.Vector(0, 1, 0)",
        "YZ": "FreeCAD.Vector(1, 0, 0)",
    }
    code = f'''
doc = FreeCAD.getDocument({repr(doc_name)}) if {repr(doc_name)} else FreeCAD.ActiveDocument
sketch = doc.addObject("Sketcher::SketchObject", {repr(name) or '"Sketch"'})
sketch.MapMode = "Deactivated"
sketch.Placement = FreeCAD.Placement(
    FreeCAD.Vector(0, 0, 0),
    FreeCAD.Rotation({plane_vectors[plane]}, 0)
)
doc.recompute()
_result_ = {{"name": sketch.Name, "geometry_count": sketch.GeometryCount}}
'''
    return await bridge.execute_python(code)
```

### Geometry Tools

#### `add_sketch_geometry`

```python
@mcp.tool()
async def add_sketch_geometry(
    sketch_name: str,
    geometry_type: str,
    parameters: dict,
    doc_name: str | None = None,
) -> dict:
    """Add geometry to a sketch.

    Args:
        sketch_name: Name of the sketch object
        geometry_type: One of 'line', 'circle', 'arc', 'rectangle', 'point'
        parameters: Geometry-specific parameters
        doc_name: Document containing the sketch

    Returns:
        Geometry index and sketch state

    Example parameters:
        line: {"start": [0, 0], "end": [10, 10]}
        circle: {"center": [0, 0], "radius": 5}
        rectangle: {"corner1": [0, 0], "corner2": [10, 10]}
    """
    pass  # Implementation depends on geometry_type
```

#### `boolean_operation`

```python
@mcp.tool()
async def boolean_operation(
    operation: str,
    base_object: str,
    tool_objects: list[str],
    doc_name: str | None = None,
) -> dict:
    """Perform boolean operation on Part objects.

    Args:
        operation: One of 'fuse' (union), 'cut' (subtract), 'common' (intersect)
        base_object: Name of the base object
        tool_objects: List of tool object names
        doc_name: Document name

    Returns:
        Resulting object information
    """
    pass
```

### Export/Import Tools

#### `export_mesh`

```python
@mcp.tool()
async def export_mesh(
    objects: list[str],
    path: str,
    format: str = "stl",
    options: dict | None = None,
    doc_name: str | None = None,
) -> dict:
    """Export objects as mesh (STL, OBJ, etc.).

    Args:
        objects: List of object names to export
        path: Output file path
        format: Export format ('stl', 'obj', 'ply', 'off')
        options: Format-specific options (e.g., mesh deflection)
        doc_name: Document name

    Returns:
        Export status and file info
    """
    pass
```

#### `export_step`

```python
@mcp.tool()
async def export_step(
    objects: list[str],
    path: str,
    doc_name: str | None = None,
) -> dict:
    """Export objects as STEP file.

    Args:
        objects: List of object names to export
        path: Output file path (.step or .stp)
        doc_name: Document name

    Returns:
        Export status
    """
    pass
```

### Debugging Tools

#### `inspect_object`

```python
@mcp.tool()
async def inspect_object(
    object_name: str,
    doc_name: str | None = None,
    include_shape: bool = True,
) -> dict:
    """Get detailed information about an object.

    Args:
        object_name: Name of the object
        doc_name: Document name
        include_shape: Include shape geometry details

    Returns:
        Comprehensive object information including:
        - All properties and their values
        - Shape information (if applicable)
        - Parent/child relationships
        - Placement/position data
    """
    pass
```

#### `validate_model`

```python
@mcp.tool()
async def validate_model(
    doc_name: str | None = None,
    check_geometry: bool = True,
    check_constraints: bool = True,
) -> dict:
    """Validate model integrity and constraints.

    Args:
        doc_name: Document to validate
        check_geometry: Check for geometry errors
        check_constraints: Check sketch constraints

    Returns:
        Validation results with any issues found
    """
    pass
```

### Workbench Tools

#### `activate_workbench`

```python
@mcp.tool()
async def activate_workbench(workbench_name: str) -> dict:
    """Activate a FreeCAD workbench.

    Args:
        workbench_name: Workbench identifier (e.g., 'PartDesignWorkbench')

    Returns:
        Activation status and available commands
    """
    pass
```

#### `list_workbench_commands`

```python
@mcp.tool()
async def list_workbench_commands(
    workbench_name: str | None = None,
) -> dict:
    """List available commands in a workbench.

    Args:
        workbench_name: Workbench to query (active if None)

    Returns:
        List of commands with descriptions
    """
    pass
```

---

## MCP Resources Specification

### Document Resources

```python
@mcp.resource("freecad://documents")
async def list_documents() -> str:
    """List all open FreeCAD documents."""
    docs = await bridge.get_documents()
    return json.dumps([d.__dict__ for d in docs], indent=2)

@mcp.resource("freecad://documents/{doc_name}")
async def get_document(doc_name: str) -> str:
    """Get detailed document information."""
    pass

@mcp.resource("freecad://documents/{doc_name}/objects")
async def list_objects(doc_name: str) -> str:
    """List all objects in a document with hierarchy."""
    pass

@mcp.resource("freecad://documents/{doc_name}/objects/{obj_name}")
async def get_object_details(doc_name: str, obj_name: str) -> str:
    """Get full object details including properties and shape."""
    pass
```

### Console Resources

```python
@mcp.resource("freecad://console/history")
async def get_console_history() -> str:
    """Get Python console command history."""
    pass

@mcp.resource("freecad://console/output")
async def get_console_output() -> str:
    """Get recent console output (stdout/stderr)."""
    pass
```

### Environment Resources

```python
@mcp.resource("freecad://version")
async def get_version() -> str:
    """Get FreeCAD version and build information."""
    pass

@mcp.resource("freecad://workbenches")
async def list_workbenches() -> str:
    """List installed workbenches with status."""
    pass

@mcp.resource("freecad://macros")
async def list_macros() -> str:
    """List installed macros."""
    pass

@mcp.resource("freecad://preferences/{path}")
async def get_preference(path: str) -> str:
    """Get FreeCAD preference value."""
    pass
```

---

## Communication Patterns

### Pattern 1: Stdio Transport (Default for MCP Clients)

```text
MCP Client <--stdio--> MCP Server <--embedded/socket--> FreeCAD
```

Configuration in Claude Code settings (similar for other MCP clients):

```json
{
  "mcpServers": {
    "freecad": {
      "command": "uv",
      "args": ["run", "freecad-mcp"],
      "env": {
        "FREECAD_MODE": "xmlrpc"
      }
    }
  }
}
```

### Pattern 2: HTTP Transport (Remote/Shared)

```text
MCP Client <--HTTP--> MCP Server <--socket--> FreeCAD
```

For shared or remote setups:

```json
{
  "mcpServers": {
    "freecad": {
      "url": "http://localhost:8000/mcp",
      "transport": "streamable-http"
    }
  }
}
```

### Pattern 3: GUI Integration

When FreeCAD GUI is running:

1. User installs FreeCAD plugin via Addon Manager
1. Plugin starts socket server on FreeCAD startup
1. MCP server connects via socket bridge
1. Full GUI access including view manipulation

```text
┌─────────────────────────────────────────────────────────────┐
│                    FreeCAD GUI                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              MCP Bridge Plugin                       │    │
│  │         (Socket Server on port 9876)                │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                           ▲
                           │ TCP Socket
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              MCP Server (SocketBridge mode)                  │
└─────────────────────────────────────────────────────────────┘
                           ▲
                           │ stdio
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                MCP Client (Claude Code, etc.)                │
└─────────────────────────────────────────────────────────────┘
```

---

## Security Considerations

### Code Execution Sandboxing

```python
class CodeSandbox:
    """Sandbox for restricting Python code execution."""

    FORBIDDEN_MODULES = {
        "subprocess", "os.system", "pty", "socket",  # System access
        "pickle", "marshal",  # Serialization attacks
        "__import__",  # Dynamic imports
    }

    FORBIDDEN_BUILTINS = {
        "exec", "eval", "compile",  # Meta-execution
        "open", "__import__",  # File/module access
    }

    def validate_code(self, code: str) -> list[str]:
        """Check code for dangerous patterns."""
        import ast

        issues = []
        tree = ast.parse(code)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in self.FORBIDDEN_MODULES:
                        issues.append(f"Forbidden import: {alias.name}")

            elif isinstance(node, ast.ImportFrom):
                if node.module in self.FORBIDDEN_MODULES:
                    issues.append(f"Forbidden import: {node.module}")

        return issues
```

### Resource Limits

```python
@dataclass
class ExecutionLimits:
    """Resource limits for code execution."""

    max_execution_time_ms: int = 30000  # 30 seconds
    max_memory_mb: int = 512
    max_output_size_bytes: int = 1_000_000  # 1 MB
    max_objects_created: int = 1000
```

### Authentication (for HTTP transport)

```python
# OAuth 2.1 resource server implementation
from mcp.server.auth import ResourceServer

auth = ResourceServer(
    issuer="https://auth.example.com",
    audience="freecad-mcp",
)

@mcp.middleware
async def auth_middleware(request, call_next):
    """Validate OAuth tokens for HTTP transport."""
    if mcp.transport_type == "http":
        await auth.validate_request(request)
    return await call_next(request)
```

---

## Deployment Modes

### Mode 1: XML-RPC Mode (Recommended)

Connects to FreeCAD via XML-RPC protocol. Works on all platforms (macOS, Linux, Windows).

```yaml
# .mise.toml
[tools]
python = "3.11"  # Required for FreeCAD ABI compatibility
uv = "latest"

[env]
FREECAD_MODE = "xmlrpc"
FREECAD_XMLRPC_PORT = "9875"
```

**Setup:**

1. Install the Robust MCP Bridge workbench via FreeCAD Addon Manager, or run `just freecad::run-gui` from source
1. Start the bridge using the workbench toolbar button or menu
1. The bridge starts both XML-RPC (port 9875) and JSON-RPC (port 9876) servers

### Mode 2: Local Embedded (Linux Only)

Runs FreeCAD in-process for fastest execution. **Only works on Linux** - crashes on macOS/Windows due to `@rpath/libpython3.11.dylib` conflicts.

```yaml
# .mise.toml
[tools]
python = "3.11"  # Must match FreeCAD's bundled Python version
uv = "latest"

[env]
FREECAD_MODE = "embedded"
FREECAD_PATH = "/usr/lib/freecad/lib"  # Linux only
```

### Mode 3: Local GUI with Plugin

1. Install FreeCAD plugin:

   ```bash
   just install-freecad-plugin
   ```

1. Configure MCP server:

   ```yaml
   FREECAD_MODE = "socket"
   FREECAD_SOCKET_HOST = "localhost"
   FREECAD_SOCKET_PORT = "9876"
   ```

### Mode 4: Remote/Docker

```dockerfile
FROM freecad/freecad:latest

# Install MCP plugin
COPY freecad_plugin /root/.FreeCAD/Mod/MCPBridge

# Expose socket port
EXPOSE 9876

CMD ["freecadcmd", "-c", "from freecad_mcp.plugin import start; start()"]
```

---

## Error Handling

### Error Categories

```python
class MCPError(Exception):
    """Base MCP error."""
    pass

class ConnectionError(MCPError):
    """Failed to connect to FreeCAD."""
    pass

class ExecutionError(MCPError):
    """Python code execution failed."""
    pass

class TimeoutError(MCPError):
    """Execution timed out."""
    pass

class ValidationError(MCPError):
    """Input validation failed."""
    pass

class ResourceNotFoundError(MCPError):
    """Requested resource does not exist."""
    pass
```

### Error Response Format

```json
{
  "success": false,
  "error": {
    "type": "ExecutionError",
    "message": "NameError: name 'foo' is not defined",
    "traceback": "Traceback (most recent call last):\n  File \"<mcp>\", line 1, in <module>\nNameError: name 'foo' is not defined",
    "context": {
      "code_snippet": "foo.bar()",
      "line_number": 1
    }
  }
}
```

---

## Future Extensibility

### Planned Features

1. **Streaming Execution Output**: Real-time stdout/stderr streaming for long operations
1. **View Manipulation**: Camera control, section views, rendering in GUI mode
1. **Parametric Updates**: Modify parameters and observe model updates
1. **Assembly Support**: Integration with Assembly3/4 workbenches
1. **FEM Integration**: Finite Element Analysis setup and results
1. **Path/CAM Support**: CAM toolpath generation and simulation
1. **Multi-Document**: Work across multiple documents simultaneously
1. **Undo/Redo**: Transaction management with rollback capability

### Extension Points

```python
# Plugin system for custom tools
class ToolPlugin(Protocol):
    """Protocol for tool plugins."""

    @property
    def name(self) -> str: ...

    @property
    def tools(self) -> list[Callable]: ...

    async def initialize(self, bridge: FreecadBridge) -> None: ...

# Register custom plugins
mcp.register_plugin(MyCustomToolPlugin())
```

---

## Summary

This architecture provides:

1. **Full Python Console Access**: Execute any FreeCAD Python code
1. **Dual Mode Support**: Works with GUI and headless FreeCAD
1. **Comprehensive Tooling**: Document, object, geometry, export tools
1. **Rich Resources**: Query documents, objects, console, workbenches
1. **Secure Execution**: Sandboxing, timeouts, resource limits
1. **Flexible Deployment**: Embedded, socket, remote modes
1. **Extensible Design**: Plugin system for custom functionality

The MCP server acts as a powerful bridge enabling AI assistants to become intelligent FreeCAD development partners.
