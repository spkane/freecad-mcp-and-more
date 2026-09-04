# FreeCAD Robust MCP Suite

Welcome to the FreeCAD Robust MCP Suite documentation.

This project provides an [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server and FreeCAD workbench that enable integration between AI assistants (Claude, GPT, and other MCP-compatible tools) and [FreeCAD](https://www.freecadweb.org/), allowing AI-assisted development and debugging of 3D models, macros, and workbenches.

---

## Features

- **54 focused MCP tools** - Native PartDesign, Sketcher, variable, expression,
  validation, persistence, render, and export workflow
- **Canonical CAD guidance** - Built into server instructions, prompts, and
  resources for consistent agent behavior
- **Multiple Connection Modes** - XML-RPC (recommended), JSON-RPC socket, or embedded (Linux only)
- **GUI & Headless Support** - Full modeling in headless mode, plus screenshots/colors in GUI mode

---

## Quick Start

```bash
# Install the Robust MCP Server
pip install freecad-robust-mcp

# Install the workbench via FreeCAD Addon Manager
# (search for "Robust MCP" - the package is "FreeCAD Robust MCP Suite")

# Start FreeCAD and switch to the "Robust MCP Bridge" workbench
# Click "Start Bridge" in the toolbar

# Configure your MCP client and start building!
```

See [Installation](getting-started/installation.md) for detailed setup instructions.

---

## Connection Modes

| Mode       | Description                  | Platform                    |
| ---------- | ---------------------------- | --------------------------- |
| `xmlrpc`   | XML-RPC protocol (port 9875) | All platforms (recommended) |
| `socket`   | JSON-RPC socket (port 9876)  | All platforms               |
| `embedded` | In-process FreeCAD           | Linux only                  |

See [Connection Modes](guide/connection-modes.md) for details on choosing the right mode.

---

## GUI vs Headless Mode

The Robust MCP Server works with FreeCAD in both GUI and headless mode:

| Feature                    | Headless | GUI |
| -------------------------- | -------- | --- |
| Object creation            | Yes      | Yes |
| Native PartDesign features | Yes      | Yes |
| Export (STEP, STL, etc.)   | Yes      | Yes |
| Screenshots                | No       | Yes |
| Object colors/visibility   | No       | Yes |
| Camera control             | No       | Yes |

---

## Documentation

| Section                                            | Description                                       |
| -------------------------------------------------- | ------------------------------------------------- |
| [Getting Started](getting-started/installation.md) | Installation, configuration, and quick start      |
| [User Guide](guide/connection-modes.md)            | Connection modes, workbench, macros, and tools    |
| [Tools Reference](MCP_TOOLS_REFERENCE.md)          | Default 54-tool parametric interface              |
| [API Reference](api/server.md)                     | Python API documentation                          |
| [Development](development/contributing.md)         | Contributing, architecture, and development setup |
| [Comparison](COMPARISON.md)                        | Compare with other FreeCAD MCP implementations    |

---

## Links

- [GitHub Repository](https://github.com/spkane/freecad-addon-robust-mcp-server) - Source code and issue tracker
- [PyPI Package](https://pypi.org/project/freecad-robust-mcp/) - Python package for pip installation
- [Docker Hub](https://hub.docker.com/r/spkane/freecad-robust-mcp) - Pre-built Docker images

---

!!! tip "Share This Documentation"
    Direct link: **[https://spkane.github.io/freecad-addon-robust-mcp-server/latest/](https://spkane.github.io/freecad-addon-robust-mcp-server/latest/)**
