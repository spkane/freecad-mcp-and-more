"""FreeCAD Robust MCP Server - Main entry point.

This module provides the main Robust MCP Server implementation for FreeCAD
integration with AI assistants (Claude, GPT, and other MCP-compatible tools).
It exposes tools, resources, and prompts for interacting with FreeCAD.

Features:
    - Full Python console access (GUI and headless modes)
    - Document and object management
    - PartDesign workflow (sketches, pads, pockets, fillets)
    - Import/export (STEP, STL, OBJ, IGES)
    - Macro management
    - Screenshot capture
    - Multiple connection modes (embedded, XML-RPC, socket)

Example:
    Run as a module::

        $ python -m freecad_mcp.server

    Or use the installed command::

        $ freecad-mcp

    With environment variables::

        $ FREECAD_MODE=socket FREECAD_SOCKET_HOST=localhost freecad-mcp

    Show help::

        $ freecad-mcp --help
"""

import argparse
import logging
import os
import sys
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import FastMCP

from freecad_mcp.config import FreecadMode, TransportType, get_config

if TYPE_CHECKING:
    from freecad_mcp.bridge.base import FreecadBridge

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Generate unique instance ID at module load time
# This ID is stable for the lifetime of this server process
INSTANCE_ID: str = str(uuid.uuid4())

# Global bridge instance (initialized on startup via lifespan)
_bridge: Any = None


def get_instance_id() -> str:
    """Get the unique instance ID for this Robust MCP Server process.

    Returns:
        The UUID string that uniquely identifies this server instance.
    """
    return INSTANCE_ID


async def get_bridge() -> "FreecadBridge":
    """Get the active FreeCAD bridge.

    Returns:
        The active FreecadBridge instance.

    Raises:
        RuntimeError: If bridge is not initialized.
    """
    if _bridge is None:
        msg = "FreeCAD bridge not initialized"
        raise RuntimeError(msg)
    return _bridge


@asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[None]:
    """Manage FreeCAD bridge lifecycle.

    This async context manager initializes the FreeCAD bridge on startup
    and disconnects it on shutdown.

    Args:
        _server: The FastMCP server instance (unused).

    Yields:
        None - the bridge is stored in the global _bridge variable.
    """
    global _bridge
    config = get_config()

    logger.info("Initializing FreeCAD bridge...")

    if config.mode == FreecadMode.EMBEDDED:
        from freecad_mcp.bridge.embedded import EmbeddedBridge

        _bridge = EmbeddedBridge(
            freecad_path=str(config.freecad_path) if config.freecad_path else None,
        )
        logger.info("Using embedded bridge (headless mode)")

    elif config.mode == FreecadMode.XMLRPC:
        from freecad_mcp.bridge.xmlrpc import XmlRpcBridge

        _bridge = XmlRpcBridge(
            host=config.socket_host,
            port=config.xmlrpc_port,
        )
        logger.info(
            "Using XML-RPC bridge: %s:%d", config.socket_host, config.xmlrpc_port
        )

    else:  # SOCKET mode
        from freecad_mcp.bridge.socket import SocketBridge

        _bridge = SocketBridge(
            host=config.socket_host,
            port=config.socket_port,
        )
        logger.info(
            "Using socket bridge: %s:%d", config.socket_host, config.socket_port
        )

    await _bridge.connect()
    logger.info("FreeCAD bridge connected")

    # Log FreeCAD version
    try:
        version = await _bridge.get_freecad_version()
        logger.info(
            "FreeCAD %s (GUI: %s)",
            version.get("version", "unknown"),
            "available" if version.get("gui_available") else "headless",
        )
    except Exception as e:
        logger.warning("Could not get FreeCAD version: %s", e)

    try:
        yield
    finally:
        # Shutdown
        if _bridge:
            logger.info("Disconnecting FreeCAD bridge...")
            await _bridge.disconnect()
            _bridge = None


# Create the Robust MCP Server instance with lifespan
mcp = FastMCP(
    name="freecad-mcp",
    lifespan=lifespan,
)


def register_all_components() -> None:
    """Register all MCP components (tools, resources, prompts)."""
    # Register tools
    from freecad_mcp.tools import register_all_tools

    register_all_tools(mcp, get_bridge)

    # Register resources
    from freecad_mcp.resources import register_resources

    register_resources(mcp, get_bridge)

    # Register prompts
    from freecad_mcp.prompts import register_prompts

    register_prompts(mcp, get_bridge)


# Register all components
register_all_components()


async def check_freecad_connection(
    mode: str | None = None, host: str | None = None, port: int | None = None
) -> bool:
    """Test FreeCAD bridge connection.

    Args:
        mode: Connection mode override (xmlrpc, socket, embedded).
        host: Host override for connection.
        port: Port override for connection.

    Returns:
        True if connection successful, False otherwise.
    """
    import os

    # Apply overrides to env
    if mode:
        os.environ["FREECAD_MODE"] = mode
    if host:
        os.environ["FREECAD_SOCKET_HOST"] = host
    if port:
        mode_val = mode or os.environ.get("FREECAD_MODE", "xmlrpc")
        if mode_val == "xmlrpc":
            os.environ["FREECAD_XMLRPC_PORT"] = str(port)
        else:
            os.environ["FREECAD_SOCKET_PORT"] = str(port)

    config = get_config()
    print(f"Testing connection to FreeCAD ({config.mode.value} mode)...")

    try:
        bridge: FreecadBridge
        if config.mode == FreecadMode.EMBEDDED:
            from freecad_mcp.bridge.embedded import EmbeddedBridge

            bridge = EmbeddedBridge(
                freecad_path=(
                    str(config.freecad_path) if config.freecad_path else None
                ),
            )
        elif config.mode == FreecadMode.XMLRPC:
            from freecad_mcp.bridge.xmlrpc import XmlRpcBridge

            bridge = XmlRpcBridge(
                host=config.socket_host,
                port=config.xmlrpc_port,
            )
            print(f"  Host: {config.socket_host}:{config.xmlrpc_port}")
        else:
            from freecad_mcp.bridge.socket import SocketBridge

            bridge = SocketBridge(
                host=config.socket_host,
                port=config.socket_port,
            )
            print(f"  Host: {config.socket_host}:{config.socket_port}")

        await bridge.connect()
        version_info = await bridge.get_freecad_version()
        await bridge.disconnect()

        print("✓ Connection successful!")
        print(f"  FreeCAD version: {version_info.get('version', 'unknown')}")
        print(f"  GUI available: {version_info.get('gui_available', 'unknown')}")
        return True
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return False


def apply_cli_args_to_env(args: argparse.Namespace) -> None:
    """Apply CLI arguments as environment variables.

    CLI arguments override existing environment variables.

    Args:
        args: Parsed command-line arguments.
    """
    import os

    if args.mode:
        os.environ["FREECAD_MODE"] = args.mode
    if args.transport:
        os.environ["FREECAD_TRANSPORT"] = args.transport
    if args.host:
        os.environ["FREECAD_SOCKET_HOST"] = args.host
    if args.port:
        # Set appropriate port based on mode
        mode = os.environ.get("FREECAD_MODE", "xmlrpc")
        if mode == "xmlrpc":
            os.environ["FREECAD_XMLRPC_PORT"] = str(args.port)
        else:
            os.environ["FREECAD_SOCKET_PORT"] = str(args.port)
    if args.http_port:
        os.environ["FREECAD_HTTP_PORT"] = str(args.http_port)
    if args.log_level:
        os.environ["FREECAD_LOG_LEVEL"] = args.log_level


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        prog="freecad-mcp",
        description="FreeCAD Robust MCP Server - Connect AI assistants to FreeCAD",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  FREECAD_MODE           Connection mode: xmlrpc, socket, or embedded
                         (default: xmlrpc)
  FREECAD_SOCKET_HOST    Host for socket/XML-RPC connection (default: localhost)
  FREECAD_SOCKET_PORT    Port for socket connection (default: 9876)
  FREECAD_XMLRPC_PORT    Port for XML-RPC connection (default: 9875)
  FREECAD_TRANSPORT      Transport type: stdio or http (default: stdio)
  FREECAD_HTTP_PORT      Port for HTTP transport (default: 8000)
  FREECAD_LOG_LEVEL      Logging level: DEBUG, INFO, WARNING, ERROR
                         (default: INFO)

Examples:
  # Start with default settings (XML-RPC mode, stdio transport)
  freecad-mcp

  # Use socket mode
  FREECAD_MODE=socket freecad-mcp

  # Use HTTP transport for remote access
  FREECAD_TRANSPORT=http FREECAD_HTTP_PORT=8080 freecad-mcp

  # Connect to remote FreeCAD instance
  FREECAD_SOCKET_HOST=192.168.1.100 freecad-mcp

Prerequisites:
  The FreeCAD Robust MCP Bridge must be running before starting this server.
  Start it via:
    - FreeCAD GUI: Install Robust MCP Bridge workbench, enable auto-start
    - Headless: just freecad::run-headless
    - Development: just freecad::run-gui
""",
    )

    parser.add_argument(
        "--version",
        action="store_true",
        help="Show version information and exit",
    )

    parser.add_argument(
        "--check",
        action="store_true",
        help="Test FreeCAD connection and exit (doesn't start MCP server)",
    )

    parser.add_argument(
        "--mode",
        choices=["xmlrpc", "socket", "embedded"],
        help="Connection mode (overrides FREECAD_MODE env var)",
    )

    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        help="Transport type (overrides FREECAD_TRANSPORT env var)",
    )

    parser.add_argument(
        "--host",
        help="Host for FreeCAD connection (overrides FREECAD_SOCKET_HOST)",
    )

    parser.add_argument(
        "--port",
        type=int,
        help="Port for FreeCAD connection (mode-dependent)",
    )

    parser.add_argument(
        "--http-port",
        type=int,
        help="Port for HTTP transport (overrides FREECAD_HTTP_PORT)",
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (overrides FREECAD_LOG_LEVEL)",
    )

    return parser.parse_args()


def main() -> None:
    """Run the FreeCAD Robust MCP Server."""
    # Parse arguments first - this handles --help without connecting to FreeCAD
    args = parse_args()

    # Handle --version
    if args.version:
        try:
            from importlib.metadata import version

            ver = version("freecad-mcp")
        except Exception:
            ver = "unknown"
        print(f"freecad-mcp {ver}")
        print(f"Instance ID: {INSTANCE_ID}")
        sys.exit(0)

    # Handle --check (test connection without starting MCP server)
    if args.check:
        import asyncio

        success = asyncio.run(
            check_freecad_connection(mode=args.mode, host=args.host, port=args.port)
        )
        sys.exit(0 if success else 1)

    # Apply CLI arguments as environment variables (they override existing ones)
    apply_cli_args_to_env(args)

    # Now get config (which reads from environment)
    config = get_config()

    # Set up logging
    logging.getLogger().setLevel(config.log_level)

    # Print instance ID to stderr only for test automation (when env var is set).
    # This avoids unwanted output during normal use.
    # Must use stderr because stdout is reserved for JSON-RPC in stdio mode.
    if os.environ.get("FREECAD_MCP_TESTING"):
        print(f"FREECAD_MCP_INSTANCE_ID={INSTANCE_ID}", file=sys.stderr, flush=True)

    logger.info("Starting FreeCAD Robust MCP Server")
    logger.info("Instance ID: %s", INSTANCE_ID)
    logger.info("Mode: %s", config.mode.value)
    logger.info("Transport: %s", config.transport.value)

    # Run the server
    if config.transport == TransportType.HTTP:
        logger.info("Starting HTTP transport on port %d", config.http_port)
        mcp.settings.host = "0.0.0.0"  # noqa: S104
        mcp.settings.port = config.http_port
        mcp.run(transport="streamable-http")
    else:
        logger.info("Starting stdio transport")
        logger.info(
            "Waiting for MCP client connection (FreeCAD connection tested on first request)..."
        )
        logger.info(
            "Tip: Use 'freecad-mcp --check' to test FreeCAD connection directly"
        )
        mcp.run()


if __name__ == "__main__":
    main()
