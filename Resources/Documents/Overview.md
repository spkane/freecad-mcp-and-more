# FreeCAD Robust MCP Suite

## Overview

The FreeCAD Robust MCP Suite enables AI assistants like Claude Code and Cursor
to interact with FreeCAD through the Model Context Protocol (MCP).

## Components

### Robust MCP Bridge (Workbench)

A FreeCAD workbench that exposes FreeCAD's functionality via XML-RPC and
JSON-RPC protocols. Install via the FreeCAD Addon Manager.

**Features:**

- Auto-start on FreeCAD launch (configurable)
- Status bar indicator showing connection state
- Toolbar buttons to start/stop the bridge
- Works in both GUI and headless modes

### Robust MCP Server

A standalone MCP server that connects AI assistants to the bridge.
Install via `pip install freecad-robust-mcp` or `uv tool install freecad-robust-mcp`.

**Capabilities:**

- 54 focused tools for native PartDesign and Sketcher workflows
- Typed sketch, constraint, feature, expression, and validation commands
- FCStd persistence plus STEP and STL export
- Screenshot capture for visual review (GUI mode)
- Opt-in legacy full tool profile for existing integrations

## Quick Start

1. Install the Robust MCP Bridge workbench via FreeCAD Addon Manager
2. Start FreeCAD (bridge starts automatically if enabled)
3. Install the MCP server: `pip install freecad-robust-mcp`
4. Configure your AI assistant to use `freecad-mcp --mode xmlrpc`

## Documentation

For full documentation, visit:
<https://spkane.github.io/freecad-addon-robust-mcp-server/latest/>

## License

- Code: MIT License
- Icons: CC-BY-NC-SA-4.0
