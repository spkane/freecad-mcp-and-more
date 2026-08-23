# FreeCAD Robust MCP Suite - Quick Start

This guide gets you up and running quickly. For comprehensive documentation, visit our **[Full Documentation](https://spkane.github.io/freecad-addon-robust-mcp-server/latest/)**.

## Overview

The FreeCAD Robust MCP Suite consists of two components:

| Component              | Purpose                                            |
| ---------------------- | -------------------------------------------------- |
| **Robust MCP Bridge**  | FreeCAD workbench that exposes FreeCAD via XML-RPC |
| **Robust MCP Server**  | MCP server that connects AI assistants to FreeCAD  |

## Quick Start

### 1. Install the MCP Bridge in FreeCAD

#### Option A: FreeCAD Addon Manager (Recommended)

1. Open FreeCAD
2. Go to **Tools → Addon Manager**
3. Search for "Robust MCP Bridge"
4. Click **Install**
5. Restart FreeCAD

#### Option B: Manual Installation

```bash
# Clone the repository
git clone https://github.com/spkane/freecad-addon-robust-mcp-server.git
cd freecad-addon-robust-mcp-server

# Install the workbench
just install::mcp-bridge-workbench
```

### 2. Start the MCP Bridge

1. Open FreeCAD
2. The bridge starts automatically (if auto-start is enabled), or
3. Click the **Start MCP Bridge** button in the toolbar

The bridge listens on:

- **XML-RPC**: `http://localhost:9875`
- **Socket**: `localhost:9876`

### 3. Install the MCP Server

```bash
# Install via uv (recommended)
uv tool install freecad-robust-mcp

# Or via pip
pip install freecad-robust-mcp
```

### 4. Configure Your AI Assistant

Add to your MCP client configuration (e.g., Claude Desktop):

```json
{
  "mcpServers": {
    "freecad": {
      "command": "freecad-mcp",
      "args": ["--mode", "xmlrpc"]
    }
  }
}
```

### 5. Start Using It

Your AI assistant can now:

- Create and modify 3D models
- Work with sketches and constraints
- Export to STEP, STL, 3MF formats
- Execute Python code in FreeCAD
- And much more...

## Connection Modes

| Mode     | Description                      | Best For                    |
| -------- | -------------------------------- | --------------------------- |
| `xmlrpc` | XML-RPC connection (port 9875)   | Most users (recommended)    |
| `socket` | JSON-RPC socket (port 9876)      | Alternative protocol        |

## Verify Installation

```bash
# Check MCP server installation
freecad-mcp --version

# Check connection status (with FreeCAD running)
freecad-mcp --mode xmlrpc --test-connection
```

## Full Documentation

For detailed guides, API reference, and advanced configuration:

**[https://spkane.github.io/freecad-addon-robust-mcp-server/latest/](https://spkane.github.io/freecad-addon-robust-mcp-server/latest/)**

### Quick Links

- [Installation Guide](https://spkane.github.io/freecad-addon-robust-mcp-server/latest/getting-started/installation/)
- [Configuration Options](https://spkane.github.io/freecad-addon-robust-mcp-server/latest/getting-started/configuration/)
- [MCP Tools Reference](https://spkane.github.io/freecad-addon-robust-mcp-server/latest/guide/tools/)
- [Troubleshooting](https://spkane.github.io/freecad-addon-robust-mcp-server/latest/guide/troubleshooting/)
- [API Reference](https://spkane.github.io/freecad-addon-robust-mcp-server/latest/reference/api/)

## Need Help?

- [GitHub Issues](https://github.com/spkane/freecad-addon-robust-mcp-server/issues)
- [Full Documentation](https://spkane.github.io/freecad-addon-robust-mcp-server/latest/)
