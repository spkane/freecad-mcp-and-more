# FreeCAD Robust MCP Server

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI Version](https://img.shields.io/pypi/v/freecad-robust-mcp)](https://pypi.org/project/freecad-robust-mcp/)
[![Python Versions](https://img.shields.io/pypi/pyversions/freecad-robust-mcp)](https://pypi.org/project/freecad-robust-mcp/)
[![Docker Image Version](https://img.shields.io/docker/v/spkane/freecad-robust-mcp?sort=semver&label=docker)](https://hub.docker.com/r/spkane/freecad-robust-mcp)
[![Documentation](https://img.shields.io/badge/docs-latest-blue.svg)](https://spkane.github.io/freecad-addon-robust-mcp-server/)

[![CI Tests](https://github.com/spkane/freecad-addon-robust-mcp-server/actions/workflows/test.yaml/badge.svg)](https://github.com/spkane/freecad-addon-robust-mcp-server/actions/workflows/test.yaml)
[![Docker Build](https://github.com/spkane/freecad-addon-robust-mcp-server/actions/workflows/docker.yaml/badge.svg)](https://github.com/spkane/freecad-addon-robust-mcp-server/actions/workflows/docker.yaml)
[![Pre-commit](https://github.com/spkane/freecad-addon-robust-mcp-server/actions/workflows/pre-commit.yaml/badge.svg)](https://github.com/spkane/freecad-addon-robust-mcp-server/actions/workflows/pre-commit.yaml)
[![CodeQL](https://github.com/spkane/freecad-addon-robust-mcp-server/actions/workflows/codeql.yaml/badge.svg)](https://github.com/spkane/freecad-addon-robust-mcp-server/actions/workflows/codeql.yaml)

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that enables integration between AI assistants (Claude, GPT, and other MCP-compatible tools) and [FreeCAD](https://www.freecadweb.org/), allowing AI-assisted development and debugging of 3D models, macros, and workbenches.

## Table of Contents

<!--TOC-->

- [FreeCAD Robust MCP Server](#freecad-robust-mcp-server)
  - [Table of Contents](#table-of-contents)
  - [Features](#features)
  - [Installation Requirements / Dependencies](#installation-requirements--dependencies)
  - [For Users](#for-users)
    - [Quick Links](#quick-links)
  - [Robust MCP Server](#robust-mcp-server)
    - [Installation](#installation)
      - [Using pip](#using-pip)
      - [Using mise and just (from source)](#using-mise-and-just-from-source)
      - [Using Docker](#using-docker)
    - [Configuration](#configuration)
      - [Environment Variables](#environment-variables)
      - [Connection Modes](#connection-modes)
      - [MCP Client Configuration](#mcp-client-configuration)
    - [Usage](#usage)
      - [Starting the MCP Bridge in FreeCAD](#starting-the-mcp-bridge-in-freecad)
        - [Option A: Using the Workbench (Recommended)](#option-a-using-the-workbench-recommended)
        - [Option B: Using just commands (from source)](#option-b-using-just-commands-from-source)
      - [Uninstalling the MCP Bridge](#uninstalling-the-mcp-bridge)
        - [Checking for Legacy Components](#checking-for-legacy-components)
        - [Manual Cleanup (if needed)](#manual-cleanup-if-needed)
      - [Running Modes](#running-modes)
        - [XML-RPC Mode (Recommended)](#xml-rpc-mode-recommended)
        - [Socket Mode (JSON-RPC)](#socket-mode-json-rpc)
        - [Headless Mode](#headless-mode)
        - [Embedded Mode (Linux Only)](#embedded-mode-linux-only)
    - [Parametric Tool Profile](#parametric-tool-profile)
  - [For Developers](#for-developers)
  - [Robust MCP Server Development](#robust-mcp-server-development)
    - [Prerequisites](#prerequisites)
    - [Initial Setup](#initial-setup)
    - [MCP Client Configuration (Development)](#mcp-client-configuration-development)
    - [Development Workflow](#development-workflow)
    - [Running FreeCAD with the MCP Bridge](#running-freecad-with-the-mcp-bridge)
      - [GUI Mode (recommended for development)](#gui-mode-recommended-for-development)
      - [Headless Mode (for automation/CI)](#headless-mode-for-automationci)
    - [Running Tests](#running-tests)
    - [Code Quality](#code-quality)
  - [Architecture](#architecture)
  - [Acknowledgements](#acknowledgements)
    - [Related Projects](#related-projects)
  - [License](#license)

<!--TOC-->

> The macros that were originally in this repo under the `/macros` directory have been permanently moved to two new GitHub repos:
>
> - [spkane/freecad-macro-cut-for-magnets](https://github.com/spkane/freecad-macro-cut-for-magnets)
> - [spkane/freecad-macro-3d-print-multi-export](https://github.com/spkane/freecad-macro-3d-print-multi-export)

**FreeCAD Forum:** [addon discussion post](https://forum.freecad.org/viewtopic.php?p=866012)

## Features

- **54 focused MCP tools**: Native Body, sketch, constraint, feature, variable,
  validation, persistence, rendering, and export operations
- **Built-in CAD guidance**: Prompts and resources encode planning, PartDesign,
  validation, parameter-variant, reopen, export, and visual-review practices
- **Task-oriented PartDesign workflow**: Build complete constrained sketches,
  expression batches, and validated features through typed MCP commands
- **Multiple Connection Modes**: XML-RPC (recommended), JSON-RPC socket, or embedded
- **GUI & Headless Support**: Full modeling in headless mode, plus screenshots/colors in GUI mode

## Installation Requirements / Dependencies

- [FreeCAD](https://www.freecadweb.org/) 1.0+
- Python 3.11 (required for FreeCAD ABI compatibility)

---

## For Users

This section covers installation and usage for end users who want to use the Robust MCP Server with AI assistants.

### Quick Links

| Resource                                                                              | Description                                   |
| ------------------------------------------------------------------------------------- | --------------------------------------------- |
| [**Documentation**](https://spkane.github.io/freecad-addon-robust-mcp-server/)        | Full documentation, guides, and API reference |
| [Docker Hub](https://hub.docker.com/r/spkane/freecad-robust-mcp)                      | Pre-built Docker images for easy deployment   |
| [PyPI](https://pypi.org/project/freecad-robust-mcp/)                                  | Python package for pip installation           |
| [GitHub Releases](https://github.com/spkane/freecad-addon-robust-mcp-server/releases) | Release archives and changelogs               |

## Robust MCP Server

> **Note**: The Linux container and PyPI package are both named `freecad-robust-mcp` which differs slightly from this git repository name.

### Installation

#### Using pip

```bash
pip install freecad-robust-mcp
```

For the FreeCAD workbench, use the Addon Manager or install this repository
from source. The Python package alone does not install the in-FreeCAD bridge.

#### Using mise and just (from source)

```bash
git clone https://github.com/spkane/freecad-addon-robust-mcp-server.git
cd freecad-addon-robust-mcp-server

# Install mise via the Official mise installer script (if not already installed)
curl https://mise.run | sh

mise trust
mise install
just setup
```

#### Using Docker

Run the Robust MCP Server in a container. This is useful for isolated environments or when you don't want to install Python dependencies on your host.

```bash
# Pull from Docker Hub (when published)
docker pull spkane/freecad-robust-mcp

# Or build locally
git clone https://github.com/spkane/freecad-addon-robust-mcp-server.git
cd freecad-addon-robust-mcp-server
docker build -t freecad-robust-mcp .

# Or use just commands (if you have mise/just installed)
just docker::build        # Build for local architecture
just docker::build-multi  # Build multi-arch (amd64 + arm64)
```

**Note:** The containerized Robust MCP Server only supports `xmlrpc` and `socket` modes since FreeCAD runs on your host machine (not in the container). The container connects to FreeCAD via `host.docker.internal`.

### Configuration

#### Environment Variables

| Variable              | Description                                          | Default     |
| --------------------- | ---------------------------------------------------- | ----------- |
| `FREECAD_MODE`        | Connection mode: `xmlrpc`, `socket`, or `embedded`   | `xmlrpc`    |
| `FREECAD_PATH`        | Path to FreeCAD's lib directory (embedded mode only) | Auto-detect |
| `FREECAD_SOCKET_HOST` | Socket/XML-RPC server hostname                       | `localhost` |
| `FREECAD_SOCKET_PORT` | JSON-RPC socket server port                          | `9876`      |
| `FREECAD_XMLRPC_PORT` | XML-RPC server port                                  | `9875`      |
| `FREECAD_TIMEOUT_MS`  | Execution timeout in ms                              | `30000`     |

#### Connection Modes

| Mode       | Description                                 | Platform Support                  |
| ---------- | ------------------------------------------- | --------------------------------- |
| `xmlrpc`   | Connects to FreeCAD via XML-RPC (port 9875) | **All platforms** (recommended)   |
| `socket`   | Connects via JSON-RPC socket (port 9876)    | **All platforms**                 |
| `embedded` | Imports FreeCAD directly into process       | **Linux only** (crashes on macOS) |

**Note:** Embedded mode crashes on macOS because FreeCAD's `FreeCAD.so` links to `@rpath/libpython3.11.dylib`, which conflicts with external Python interpreters. Use `xmlrpc` or `socket` mode on macOS and Windows.

#### MCP Client Configuration

Add something like the following to your MCP client settings. For Claude Code, this is `~/.claude/claude_desktop_config.json` or a project `.mcp.json` file:

```json
{
  "mcpServers": {
    "freecad": {
      "command": "freecad-mcp",
      "env": {
        "FREECAD_MODE": "xmlrpc"
      }
    }
  }
}
```

If installed from source with mise/uv:

```json
{
  "mcpServers": {
    "freecad": {
      "command": "/path/to/mise/shims/uv",
      "args": ["run", "--project", "/path/to/freecad-addon-robust-mcp-server", "freecad-mcp"],
      "env": {
        "FREECAD_MODE": "xmlrpc"
      }
    }
  }
}
```

If using Docker:

```json
{
  "mcpServers": {
    "freecad": {
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "--add-host=host.docker.internal:host-gateway",
        "-e", "FREECAD_MODE=xmlrpc",
        "-e", "FREECAD_SOCKET_HOST=host.docker.internal",
        "spkane/freecad-robust-mcp"
      ]
    }
  }
}
```

**Docker configuration notes:**

- `--rm` removes the container after it exits
- `-i` keeps stdin open for MCP communication
- `--add-host=host.docker.internal:host-gateway` allows the container to connect to FreeCAD on your host (Linux only; macOS/Windows have this built-in)
- `FREECAD_SOCKET_HOST=host.docker.internal` tells the Robust MCP Server to connect to FreeCAD on your host machine

### Usage

#### Starting the MCP Bridge in FreeCAD

Before your AI assistant can connect, you need to start the MCP bridge inside FreeCAD:

##### Option A: Using the Workbench (Recommended)

1. Install the Robust MCP Bridge workbench via FreeCAD's Addon Manager:

   - **Edit -> Preferences -> Addon Manager**
   - Search for "Robust MCP Bridge"
   - Install and restart FreeCAD

1. Start the bridge:

   - Switch to the Robust MCP Bridge workbench
   - Click the **Start MCP Bridge** button in the toolbar
   - Or use the menu: **MCP Bridge -> Start Bridge**

1. You should see in the FreeCAD console:

   ```text
   MCP Bridge started!
     - XML-RPC: localhost:9875
     - Socket: localhost:9876
   ```

##### Option B: Using just commands (from source)

```bash
# Start FreeCAD with MCP bridge auto-started
just freecad::run-gui

# Or for headless/automation mode:
just freecad::run-headless
```

After starting the bridge, start/restart your MCP client (Claude Code, etc.) - it will connect automatically

#### Uninstalling the MCP Bridge

To uninstall the Robust MCP Bridge workbench:

1. Open FreeCAD
1. Go to **Edit -> Preferences -> Addon Manager**
1. Find "Robust MCP Bridge" in the list
1. Click **Uninstall**
1. Restart FreeCAD

##### Checking for Legacy Components

If you previously used older versions of this project, you may have legacy components installed. Run this command to check what's installed and get cleanup instructions:

```bash
just install::status
```

##### Manual Cleanup (if needed)

Remove any legacy files that may conflict with the workbench:

```bash
# macOS - remove legacy plugin and macro
rm -rf ~/Library/Application\ Support/FreeCAD/Mod/MCPBridge/
rm -f ~/Library/Application\ Support/FreeCAD/Macro/StartMCPBridge.FCMacro

# Linux - remove legacy plugin and macro
rm -rf ~/.local/share/FreeCAD/Mod/MCPBridge/
rm -f ~/.local/share/FreeCAD/Macro/StartMCPBridge.FCMacro
```

#### Running Modes

##### XML-RPC Mode (Recommended)

Connects to a running FreeCAD instance via XML-RPC. Works on all platforms.

```bash
FREECAD_MODE=xmlrpc freecad-mcp
```

##### Socket Mode (JSON-RPC)

Connects via JSON-RPC socket. Works on all platforms.

```bash
FREECAD_MODE=socket freecad-mcp
```

##### Headless Mode

Run FreeCAD in console mode without GUI. Useful for automation.

```bash
# If installed from source:
just freecad::run-headless
```

**Note:** Screenshot and view features are not available in headless mode.

##### Embedded Mode (Linux Only)

Runs FreeCAD in-process. **Only works on Linux** - crashes on macOS/Windows.

```bash
FREECAD_MODE=embedded freecad-mcp
```

### Parametric Tool Profile

The default profile exposes 54 tools. It keeps the native PartDesign path while
removing unrelated primitives, arbitrary Python execution, macros, Draft tools,
and less common operations from the model's tool context.

- **Document**: `create_document`, `save_document`, `open_document`
- **Variables**: `define_variables`, `get_variables`, `bind_expressions`
- **Sketch**: `create_constrained_sketch`, plus granular repair helpers
- **Features**: `pad_sketch`, `pocket_sketch`, `revolution_sketch`,
  `polar_pattern`
- **Inspect**: `query_objects`, `get_sketch_info`, `validate_document`
- **Deliver**: `get_screenshot`, `export_step`, `export_stl`

The primary workflow creates a native `PartDesign::Body`, fully constrained
sketches, native variable-driven expressions, and ordered additive or subtractive
features through MCP commands. Read `freecad://parametric-parts/guide` or invoke
`design_parametric_part` for the complete workflow.

---

## For Developers

This section covers development setup, contributing, and working with the codebase.

## Robust MCP Server Development

### Prerequisites

- [mise](https://mise.jdx.dev/) - Tool version manager
- [FreeCAD](https://www.freecadweb.org/) 1.0+

### Initial Setup

```bash
# Clone the repository
git clone https://github.com/spkane/freecad-addon-robust-mcp-server.git
cd freecad-addon-robust-mcp-server

# Install mise via the Official mise installer script (if not already installed)
curl https://mise.run | sh

# Install all tools (Python 3.11, uv, just, pre-commit)
mise trust
mise install

# Set up the development environment
just setup
```

This installs:

- **Python 3.11** - Required for FreeCAD ABI compatibility
- **uv** - Fast Python package manager
- **just** - Command runner for development workflows
- **pre-commit** - Git hooks for code quality

### MCP Client Configuration (Development)

Create a `.mcp.json` file in the project directory:

```json
{
  "mcpServers": {
    "freecad": {
      "command": "/path/to/mise/shims/uv",
      "args": ["run", "--project", "/path/to/freecad-addon-robust-mcp-server", "freecad-mcp"],
      "env": {
        "FREECAD_MODE": "xmlrpc",
        "FREECAD_SOCKET_HOST": "localhost",
        "FREECAD_XMLRPC_PORT": "9875",
        "PATH": "/path/to/mise/shims:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
      }
    }
  }
}
```

**Replace the paths with your actual paths:**

| Placeholder                                 | Description                     | Example                                        |
| ------------------------------------------- | ------------------------------- | ---------------------------------------------- |
| `/path/to/mise/shims/uv`                    | Full path to uv via mise shims  | `~/.local/share/mise/shims/uv`                 |
| `/path/to/freecad-addon-robust-mcp-server`  | Project directory               | `/home/me/dev/freecad-addon-robust-mcp-server` |
| `/path/to/mise/shims`                       | mise shims directory for PATH   | `~/.local/share/mise/shims`                    |

**Finding your mise shims path:**

```bash
mise where uv | sed 's|/installs/.*|/shims|'
# Example: /home/user/.local/share/mise/shims (on Linux) or ~/.local/share/mise/shims (on macOS)
```

### Development Workflow

Commands are organized into modules. Use `just` to see top-level commands, or `just list-<module>` to see module-specific commands.

```bash
# Show top-level commands and available modules
just

# Show commands in a specific module
just list-mcp           # Robust MCP Server commands
just list-freecad       # FreeCAD plugin/macro commands
just list-install       # Installation commands
just list-quality       # Code quality commands
just list-testing       # Test commands
just list-docker        # Docker commands
just list-documentation # Documentation commands
just list-dev           # Development utilities

# List ALL commands from all modules
just list-all

# Install/update dependencies
just install::mcp-server

# Run all checks (linting, type checking, tests)
just all

# Quality commands
just quality::lint       # Run ruff linter
just quality::typecheck  # Run mypy type checker
just quality::format     # Format code
just quality::check      # Run all pre-commit hooks

# Testing commands
just testing::unit       # Run unit tests
just testing::cov        # Run tests with coverage
just testing::integration # Run integration tests

# Run the Robust MCP Server (or with debug logging)
just mcp::run
just mcp::run-debug

# Docker commands
just docker::build        # Build image for local architecture
just docker::build-multi  # Build multi-arch image (amd64 + arm64)
just docker::run          # Run container
```

### Running FreeCAD with the MCP Bridge

#### GUI Mode (recommended for development)

```bash
# Start FreeCAD with auto-started bridge
just freecad::run-gui
```

#### Headless Mode (for automation/CI)

```bash
just freecad::run-headless
```

### Running Tests

```bash
# Unit tests only (no FreeCAD required)
just testing::unit

# Unit tests with coverage
just testing::cov

# Integration tests (requires running FreeCAD bridge)
just testing::integration

# Integration tests with automatic FreeCAD startup
just testing::integration-auto
```

### Code Quality

The project uses strict code quality checks via pre-commit:

- **Ruff** - Linting and formatting
- **MyPy** - Type checking
- **Bandit** - Security scanning
- **Codespell** - Spell checking
- **Secrets scanning** - Gitleaks, detect-secrets, TruffleHog

```bash
# Run all pre-commit hooks
just quality::check

# Run security/secrets scans
just quality::security
just quality::secrets
```

---

## Architecture

See the [detailed architecture document](docs/development/architecture-detailed.md) for design documentation covering:

- Module structure
- Bridge communication protocols
- Tool registration patterns
- FreeCAD plugin architecture

---

## Acknowledgements

This project was developed after analyzing several existing FreeCAD Robust MCP implementations. We are grateful to these projects for their pioneering work and the ideas they contributed to the FreeCAD + AI ecosystem:

### Related Projects

- **[neka-nat/freecad-mcp](https://github.com/neka-nat/freecad-mcp)** (MIT License) - The queue-based thread safety pattern and XML-RPC protocol design (port 9875) were directly inspired by this project. Our implementation maintains protocol compatibility while being a complete rewrite with additional features.

- **[jango-blockchained/mcp-freecad](https://github.com/jango-blockchained/mcp-freecad)** - Inspired our connection recovery mechanisms and multi-mode architecture approach.

- **[contextform/freecad-mcp](https://github.com/contextform/freecad-mcp)** - Informed our comprehensive PartDesign and Part workbench tool coverage.

- **[ATOI-Ming/FreeCAD-MCP](https://github.com/ATOI-Ming/FreeCAD-MCP)** - Inspired our macro development toolkit including templates, validation, and automatic imports.

- **[bonninr/freecad_mcp](https://github.com/bonninr/freecad_mcp)** - Influenced our simple socket-based communication approach.

See [docs/COMPARISON.md](docs/COMPARISON.md) for a detailed analysis of these implementations and the design decisions they informed.

---

## License

MIT License - see [LICENSE](LICENSE) for details.
