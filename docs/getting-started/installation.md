# Installation

This guide covers installing the FreeCAD Robust MCP Server and connecting it to your AI assistant.

---

## Requirements

- **FreeCAD** 0.21+ or 1.0+ (with Python 3.11)
- **Python 3.11** (must match FreeCAD's bundled Python version)
- An **MCP-compatible AI assistant** (Claude Code, Cursor, etc.)

---

## Installation Methods

### Method 1: pip (Recommended)

The simplest way to install the Robust MCP Server:

```bash
pip install freecad-robust-mcp
```

### Method 2: From Source (for Development)

```bash
git clone https://github.com/spkane/freecad-addon-robust-mcp-server.git
cd freecad-addon-robust-mcp-server

# Install mise (if not already installed)
curl https://mise.run | sh

mise trust
mise install
just setup
```

### Method 3: Docker

Run the Robust MCP Server in a container:

```bash
# Pull from Docker Hub
docker pull spkane/freecad-robust-mcp

# Or build locally
docker build -t freecad-robust-mcp .
```

**Note:** The Docker container runs the Robust MCP Server only—it does not include FreeCAD itself. You must run FreeCAD with the Robust MCP Bridge workbench on your host machine (or in a separate container) and configure the Robust MCP Server to connect via `xmlrpc` or `socket` mode.

**Why embedded mode doesn't work with Docker:** Embedded mode requires FreeCAD and the Robust MCP Server to run in the same process, which is impossible when FreeCAD runs on the host and the Robust MCP Server runs inside a Docker container. Additionally, embedded mode fails on macOS due to ABI incompatibility with FreeCAD's bundled Python libraries (`libpython3.11.dylib`). Always use `xmlrpc` or `socket` mode for Docker deployments.

---

## Installing the Robust MCP Bridge Workbench

The Robust MCP Bridge Workbench runs inside FreeCAD and provides the connection point for the Robust MCP Server.

### Via FreeCAD Addon Manager (Recommended)

1. Open FreeCAD
1. Go to **Tools > Addon Manager**
1. Search for "FreeCAD Robust MCP Suite" or "Robust MCP Bridge"
1. Click **Install**
1. Restart FreeCAD

### Manual Installation

1. Download the latest release from [GitHub Releases](https://github.com/spkane/freecad-addon-robust-mcp-server/releases)
1. Extract to your FreeCAD Mod directory:
   - **Linux:** `~/.local/share/FreeCAD/Mod/`
   - **macOS:** `~/Library/Application Support/FreeCAD/Mod/`
   - **Windows:** `%APPDATA%\FreeCAD\Mod\`
1. Restart FreeCAD

---

## Verifying Installation

After installation, verify everything is working:

### Step 1: Start FreeCAD with the Robust MCP Bridge

1. **Start FreeCAD** and select the **Robust MCP Bridge** workbench from the workbench selector dropdown
1. **Click "Start MCP Bridge"** in the toolbar (or use the MCP Bridge menu)
1. Check the FreeCAD console for confirmation messages:

```text
MCP Bridge started!
  - XML-RPC: localhost:9875
  - Socket:  localhost:9876
```

### Step 2: Verify the Robust MCP Server

Test that the Robust MCP Server command is available:

```bash
# With pip installation
freecad-mcp --help

# With source installation
uv run freecad-mcp --help
```

### Step 3: Test the Connection

With FreeCAD running and the bridge started, you can verify connectivity:

```bash
# Quick connectivity test using curl (XML-RPC)
curl -X POST http://localhost:9875 \
  -H "Content-Type: text/xml" \
  -d '<?xml version="1.0"?><methodCall><methodName>ping</methodName></methodCall>'
```

A successful response indicates the bridge is working correctly.

---

## Next Steps

- [Configuration](configuration.md) - Set up environment variables and MCP client settings
- [Quick Start](quickstart.md) - Create your first model with AI assistance
