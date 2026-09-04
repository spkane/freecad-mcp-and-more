# Installation commands for users
# Usage: just install::mcp-server, just install::mcp-bridge-workbench, etc.
#
# This module installs components for end users:
# - Robust MCP Server (as a uv tool, available system-wide)
# - Robust MCP Bridge Workbench (FreeCAD addon)
#
# For developer setup (Python dependencies in virtualenv), use: just dev::install-deps

# Project root directory (justfile_directory() returns the main justfile's directory)
project_root := justfile_directory()

# =============================================================================
# Helper: FreeCAD Directory Detection
# =============================================================================
# This function sets MOD_DIR and MACRO_DIR based on the current OS.
# Source it at the start of any recipe that needs FreeCAD paths.
#
# Usage in recipes:
#   eval "$(just install::_freecad-dirs)"
#   echo "Mod directory: $MOD_DIR"
#   echo "Macro directory: $MACRO_DIR"

# Private recipe that outputs shell code to set FreeCAD directories
# FreeCAD 1.x uses versioned directories (v1-1, v1-2, etc.) for user data.
# This helper detects the latest versioned directory if present.
[private]
_freecad-dirs:
    #!/usr/bin/env bash
    cat << 'DIRS_EOF'
    # Determine base FreeCAD directory based on OS
    if [[ "$OSTYPE" == "darwin"* ]]; then
        FREECAD_BASE="$HOME/Library/Application Support/FreeCAD"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        FREECAD_BASE="$HOME/.local/share/FreeCAD"
    else
        # Windows: validate APPDATA or use fallback
        if [[ -n "$APPDATA" ]]; then
            FREECAD_BASE="$APPDATA/FreeCAD"
        elif [[ -n "$HOME" ]]; then
            FREECAD_BASE="$HOME/AppData/Roaming/FreeCAD"
            echo "Warning: APPDATA not set, using fallback: $FREECAD_BASE" >&2
        else
            echo "Error: Neither APPDATA nor HOME is set. Cannot determine FreeCAD directory." >&2
            exit 1
        fi
    fi

    # FreeCAD 1.x+ uses versioned directories (v1-1, v1-2, v2-0, etc.)
    # Find the latest versioned directory if present
    VERSIONED_DIR=""
    if [[ -d "$FREECAD_BASE" ]]; then
        # Find directories matching v*-* pattern (supports v1-*, v2-*, etc.)
        # Use sort -t- -k1.2 -k2 -n to sort by major then minor version
        LATEST_VERSION=$(ls -d "$FREECAD_BASE"/v*-* 2>/dev/null | sort -t- -k1.2 -k2 -n | tail -n 1)
        if [[ -n "$LATEST_VERSION" && -d "$LATEST_VERSION" ]]; then
            VERSIONED_DIR="$LATEST_VERSION"
        fi
    fi

    # Use versioned directory if found, otherwise use base directory
    if [[ -n "$VERSIONED_DIR" ]]; then
        MOD_DIR="$VERSIONED_DIR/Mod"
        MACRO_DIR="$VERSIONED_DIR/Macro"
        echo "Note: Using FreeCAD versioned directory: $VERSIONED_DIR" >&2
    else
        MOD_DIR="$FREECAD_BASE/Mod"
        MACRO_DIR="$FREECAD_BASE/Macro"
    fi
    DIRS_EOF

# =============================================================================
# Robust MCP Server Installation
# =============================================================================

# Install the Robust MCP Server as a user tool (available system-wide via uv)
# Uses cached builds for faster installation. For development with uncommitted
# changes, use mcp-server-clean instead.
mcp-server:
    #!/usr/bin/env bash
    set -euo pipefail
    PROJECT_DIR="{{project_root}}"

    echo "Installing Robust MCP Server as a uv tool..."
    echo ""

    # Install from the local project directory
    # --force handles reinstallation automatically, no need to uninstall first
    uv tool install --force "$PROJECT_DIR"

    echo ""
    echo "=========================================="
    echo "Robust MCP Server installed!"
    echo "=========================================="
    echo ""
    echo "The 'freecad-mcp' command is now available system-wide."
    echo ""
    echo "To run:"
    echo "  freecad-mcp                    # stdio mode (for Claude Code)"
    echo "  freecad-mcp --help             # show all options"
    echo ""
    echo "To configure Claude Code, add to your MCP settings:"
    echo '  "freecad": {'
    echo '    "command": "freecad-mcp"'
    echo '  }'
    echo ""
    echo "Note: If you have uncommitted local changes, use 'just install::mcp-server-clean'"
    echo ""

# Install with cache clearing (for development with uncommitted changes)
# Clears uv cache first to ensure the build picks up all local changes.
mcp-server-clean:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Clearing uv cache for fresh build..."
    uv cache clean --force 2>/dev/null || true
    just install::mcp-server

# Uninstall the Robust MCP Server tool
uninstall-mcp-server:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Uninstalling Robust MCP Server..."
    uv tool uninstall freecad-robust-mcp || echo "Robust MCP Server was not installed as a uv tool"

# =============================================================================
# Robust MCP Bridge Workbench Installation
# =============================================================================

# Install the FreeCAD Robust MCP workbench addon to FreeCAD's Mod directory
# Uses new-style namespace package format: Mod/RobustMCPBridge/freecad/RobustMCPBridge/
mcp-bridge-workbench:
    #!/usr/bin/env bash
    set -euo pipefail
    PROJECT_DIR="{{project_root}}"
    # New-style namespace package: freecad/RobustMCPBridge
    ADDON_NAMESPACE="freecad"
    ADDON_NAME="RobustMCPBridge"

    # Set FreeCAD directories
    eval "$(just install::_freecad-dirs)"

    # Install to Mod/RobustMCPBridge/ (addon folder at Mod root)
    # The namespace package structure is created inside: freecad/RobustMCPBridge/
    ADDON_DEST="$MOD_DIR/$ADDON_NAME"

    # Remove existing installation if present
    if [[ -d "$ADDON_DEST" ]]; then
        echo "Removing existing installation at: $ADDON_DEST"
        rm -rf "$ADDON_DEST"
    fi

    # Also remove old-style installations if present
    OLD_STYLE_DEST="$MOD_DIR/FreecadRobustMCPBridge"
    if [[ -d "$OLD_STYLE_DEST" ]]; then
        echo "Removing legacy old-style installation at: $OLD_STYLE_DEST"
        rm -rf "$OLD_STYLE_DEST"
    fi

    # Also remove incorrect namespace installation (Mod/freecad/RobustMCPBridge)
    WRONG_NS_DEST="$MOD_DIR/$ADDON_NAMESPACE/$ADDON_NAME"
    if [[ -d "$WRONG_NS_DEST" ]]; then
        echo "Removing incorrect namespace installation at: $WRONG_NS_DEST"
        rm -rf "$WRONG_NS_DEST"
        # Clean up empty freecad directory if it exists
        if [[ -d "$MOD_DIR/$ADDON_NAMESPACE" ]] && [[ -z "$(ls -A "$MOD_DIR/$ADDON_NAMESPACE")" ]]; then
            rmdir "$MOD_DIR/$ADDON_NAMESPACE"
        fi
    fi

    # Verify source exists before copying
    ADDON_SRC="${PROJECT_DIR}/$ADDON_NAMESPACE/$ADDON_NAME"
    if [[ ! -d "$ADDON_SRC" ]]; then
        echo "Error: Addon source directory not found: $ADDON_SRC" >&2
        exit 1
    fi

    # Create addon directory with namespace package structure
    mkdir -p "$ADDON_DEST/$ADDON_NAMESPACE"

    # Copy the workbench code to the namespace package location
    cp -r "$ADDON_SRC" "$ADDON_DEST/$ADDON_NAMESPACE/"

    # Generate package.xml for the workbench from root package.xml
    # FreeCAD requires package.xml in the addon directory for proper workbench detection
    ROOT_PACKAGE_XML="${PROJECT_DIR}/package.xml"
    if [[ -f "$ROOT_PACKAGE_XML" ]]; then
        echo "Generating package.xml from root package.xml..."
        export ROOT_PACKAGE_XML ADDON_DEST
        python3 << 'PYEOF'
    import xml.etree.ElementTree as ET
    import sys
    import os

    try:
        root_pkg = os.environ.get('ROOT_PACKAGE_XML', '')
        addon_dest = os.environ.get('ADDON_DEST', '')

        tree = ET.parse(root_pkg)
        root = tree.getroot()
        ns = {'pkg': 'https://wiki.freecad.org/Package_Metadata'}

        # Find the workbench content element
        workbench = root.find('.//pkg:content/pkg:workbench', ns)
        if workbench is None:
            print("Warning: No workbench found in root package.xml", file=sys.stderr)
            sys.exit(0)

        # Extract workbench metadata
        wb_name = workbench.find('pkg:name', ns)
        wb_version = workbench.find('pkg:version', ns)
        wb_date = workbench.find('pkg:date', ns)
        wb_description = workbench.find('pkg:description', ns)
        wb_classname = workbench.find('pkg:classname', ns)
        wb_icon = workbench.find('pkg:icon', ns)
        wb_freecadmin = workbench.find('pkg:freecadmin', ns)

        # Get maintainer and license from root
        maintainer = root.find('pkg:maintainer', ns)
        license_el = root.find('pkg:license', ns)
        repo_url = root.find('pkg:url[@type="repository"]', ns)
        readme_url = root.find('pkg:url[@type="readme"]', ns)

        # Create standalone package.xml
        standalone = ET.Element('package', {
            'format': '1',
            'xmlns': 'https://wiki.freecad.org/Package_Metadata'
        })

        # Add metadata
        name_text = wb_name.text if wb_name is not None else 'Robust MCP Bridge'
        ET.SubElement(standalone, 'name').text = name_text
        desc_text = wb_description.text if wb_description is not None else 'MCP Bridge for FreeCAD'
        ET.SubElement(standalone, 'description').text = desc_text
        ver_text = wb_version.text if wb_version is not None else '0.0.0'
        ET.SubElement(standalone, 'version').text = ver_text
        # Fall back to today's date if not specified
        from datetime import date
        date_text = wb_date.text if wb_date is not None else date.today().isoformat()
        ET.SubElement(standalone, 'date').text = date_text

        if maintainer is not None:
            m = ET.SubElement(standalone, 'maintainer')
            m.text = maintainer.text
            if maintainer.get('email'):
                m.set('email', maintainer.get('email'))

        if license_el is not None:
            l = ET.SubElement(standalone, 'license')
            l.text = license_el.text
            if license_el.get('file'):
                l.set('file', license_el.get('file'))

        if repo_url is not None:
            u = ET.SubElement(standalone, 'url', type='repository')
            u.text = repo_url.text
            if repo_url.get('branch'):
                u.set('branch', repo_url.get('branch'))

        if readme_url is not None:
            u = ET.SubElement(standalone, 'url', type='readme')
            u.text = readme_url.text

        icon_text = wb_icon.text if wb_icon is not None else 'Resources/Icons/FreecadRobustMCPBridge.svg'
        ET.SubElement(standalone, 'icon').text = icon_text
        fcmin_text = wb_freecadmin.text if wb_freecadmin is not None else '1.0'
        ET.SubElement(standalone, 'freecadmin').text = fcmin_text

        # Add content/workbench section
        content = ET.SubElement(standalone, 'content')
        wb_el = ET.SubElement(content, 'workbench')
        cls_text = wb_classname.text if wb_classname is not None else 'FreecadRobustMCPBridgeWorkbench'
        ET.SubElement(wb_el, 'classname').text = cls_text
        ET.SubElement(wb_el, 'subdirectory').text = './freecad/RobustMCPBridge/'

        # Add tags
        for tag in ['MCP', 'AI', 'automation', 'Claude', 'bridge', 'headless']:
            ET.SubElement(wb_el, 'tag').text = tag

        # Helper to indent XML for Python < 3.9 compatibility
        def indent_xml(elem, level=0, space='    '):
            """Indent XML element tree (fallback for Python < 3.9)."""
            indent_str = '\n' + level * space
            if len(elem):
                if not elem.text or not elem.text.strip():
                    elem.text = indent_str + space
                for child in elem:
                    indent_xml(child, level + 1, space)
                if not child.tail or not child.tail.strip():
                    child.tail = indent_str
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = indent_str

        # Write the standalone package.xml
        # Use ET.indent if available (Python 3.9+), otherwise use fallback
        if hasattr(ET, 'indent'):
            ET.indent(standalone, space='    ')
        else:
            indent_xml(standalone)
        tree = ET.ElementTree(standalone)
        output_path = os.path.join(addon_dest, 'package.xml')
        tree.write(output_path, encoding='UTF-8', xml_declaration=True)
        print("Generated package.xml successfully")

    except Exception as e:
        print(f"Warning: Could not generate package.xml: {e}", file=sys.stderr)
        # Don't fail the installation if package.xml generation fails
    PYEOF
    else
        echo "Warning: Root package.xml not found, skipping package.xml generation"
    fi

    echo ""
    echo "=========================================="
    echo "FreeCAD Robust MCP Workbench installed!"
    echo "=========================================="
    echo ""
    echo "Installation path: $ADDON_DEST"
    echo ""
    echo "To use:"
    echo "  1. Start FreeCAD"
    echo "  2. Select the 'Robust MCP Bridge' workbench from the workbench selector"
    echo "  3. Click 'Start MCP Bridge' in the toolbar"
    echo "  4. Connect your MCP client (Claude Code, etc.) to FreeCAD"
    echo ""

# Uninstall the FreeCAD Robust MCP workbench addon
uninstall-mcp-bridge-workbench:
    #!/usr/bin/env bash
    set -euo pipefail
    # New-style namespace package: Mod/RobustMCPBridge/freecad/RobustMCPBridge/
    ADDON_NAMESPACE="freecad"
    ADDON_NAME="RobustMCPBridge"

    # Set FreeCAD directories
    eval "$(just install::_freecad-dirs)"

    # Current correct location: Mod/RobustMCPBridge/
    ADDON_DEST="$MOD_DIR/$ADDON_NAME"

    if [[ -d "$ADDON_DEST" ]]; then
        rm -rf "$ADDON_DEST"
        echo "FreeCAD Robust MCP Workbench uninstalled from: $ADDON_DEST"
    else
        echo "Workbench not found at: $ADDON_DEST"
    fi

    # Also remove incorrect namespace installation (Mod/freecad/RobustMCPBridge)
    WRONG_NS_DEST="$MOD_DIR/$ADDON_NAMESPACE/$ADDON_NAME"
    if [[ -d "$WRONG_NS_DEST" ]]; then
        rm -rf "$WRONG_NS_DEST"
        echo "Incorrect namespace installation uninstalled from: $WRONG_NS_DEST"
        # Clean up empty freecad directory if it exists
        if [[ -d "$MOD_DIR/$ADDON_NAMESPACE" ]] && [[ -z "$(ls -A "$MOD_DIR/$ADDON_NAMESPACE")" ]]; then
            rmdir "$MOD_DIR/$ADDON_NAMESPACE"
        fi
    fi

    # Also remove old-style installation if present
    OLD_STYLE_DEST="$MOD_DIR/FreecadRobustMCPBridge"
    if [[ -d "$OLD_STYLE_DEST" ]]; then
        rm -rf "$OLD_STYLE_DEST"
        echo "Legacy old-style workbench uninstalled from: $OLD_STYLE_DEST"
    fi

# =============================================================================
# Status Check
# =============================================================================

# Check installation status of all components
status:
    #!/usr/bin/env bash
    set -euo pipefail

    # Set FreeCAD directories
    eval "$(just install::_freecad-dirs)"

    # Helper function to get file modification time (cross-platform)
    get_mod_time() {
        local file="$1"
        if [[ "$OSTYPE" == "darwin"* ]]; then
            stat -f "%Sm" -t "%Y-%m-%d %H:%M" "$file" 2>/dev/null || echo "unknown"
        else
            stat -c "%y" "$file" 2>/dev/null | cut -d'.' -f1 || echo "unknown"
        fi
    }

    echo "=========================================="
    echo "Installation Status"
    echo "=========================================="
    echo ""

    # Check Robust MCP Server (installed as uv tool)
    if command -v freecad-mcp &> /dev/null; then
        MCP_VERSION=$(freecad-mcp --version 2>/dev/null || echo "unknown")
        MCP_PATH=$(command -v freecad-mcp)
        MCP_MOD_TIME=$(get_mod_time "$MCP_PATH")
        echo "✓ Robust MCP Server: INSTALLED (as uv tool)"
        echo "  Version: $MCP_VERSION"
        echo "  Updated: $MCP_MOD_TIME"
        echo "  Run: freecad-mcp"
    elif [[ -f "{{project_root}}/pyproject.toml" ]] && grep -q 'name = "freecad-robust-mcp"' "{{project_root}}/pyproject.toml" 2>/dev/null; then
        # Dev environment exists - check if synced by looking for .venv
        if [[ -d "{{project_root}}/.venv" ]]; then
            DEV_VERSION=$(cd "{{project_root}}" && uv run python -c "from freecad_mcp import __version__; print(__version__)" 2>/dev/null || echo "unknown")
            echo "✓ Robust MCP Server: AVAILABLE (via dev environment)"
            echo "  Version: $DEV_VERSION"
            echo "  Run: just mcp::run"
            echo "  For system-wide install: just install::mcp-server"
        else
            echo "○ Robust MCP Server: DEV SOURCE AVAILABLE (needs setup)"
            echo "  Setup: uv sync"
            echo "  Then run: just mcp::run"
        fi
    else
        echo "✗ Robust MCP Server: NOT INSTALLED"
        echo "  Install: just install::mcp-server"
    fi
    echo ""

    # Helper function to extract version from package.xml files
    # Uses environment variable to pass file path safely to Python (avoids shell interpolation)
    extract_package_version() {
        local package_file="$1"
        PACKAGE_FILE="$package_file" python3 -c '
    import os
    import xml.etree.ElementTree as ET
    try:
        package_file = os.environ.get("PACKAGE_FILE", "")
        tree = ET.parse(package_file)
        root = tree.getroot()
        ns = {"pkg": "https://wiki.freecad.org/Package_Metadata"}
        # Try with namespace first, then without (use is not None, not truthiness)
        ver = root.find("pkg:version", ns)
        if ver is None:
            ver = root.find("version")
        print(ver.text if ver is not None else "unknown")
    except Exception:
        print("unknown")
    ' 2>/dev/null || echo "unknown"
    }

    # Check workbench (new-style namespace package: Mod/RobustMCPBridge/freecad/RobustMCPBridge/)
    WB_PATH="$MOD_DIR/RobustMCPBridge"
    WB_CODE_PATH="$WB_PATH/freecad/RobustMCPBridge"
    if [[ -d "$WB_PATH" ]]; then
        WB_VERSION="unknown"
        if [[ -f "$WB_PATH/package.xml" ]]; then
            WB_VERSION=$(extract_package_version "$WB_PATH/package.xml")
        fi
        WB_MOD_TIME=$(get_mod_time "$WB_CODE_PATH/init_gui.py")
        echo "✓ Robust MCP Bridge Workbench: INSTALLED"
        echo "  Version: $WB_VERSION"
        echo "  Updated: $WB_MOD_TIME"
        echo "  Path: $WB_PATH"
    # Check for incorrect namespace installation (Mod/freecad/RobustMCPBridge)
    elif [[ -d "$MOD_DIR/freecad/RobustMCPBridge" ]]; then
        WB_VERSION="unknown"
        if [[ -f "$MOD_DIR/freecad/RobustMCPBridge/package.xml" ]]; then
            WB_VERSION=$(extract_package_version "$MOD_DIR/freecad/RobustMCPBridge/package.xml")
        fi
        WB_MOD_TIME=$(get_mod_time "$MOD_DIR/freecad/RobustMCPBridge/init_gui.py")
        echo "⚠ Robust MCP Bridge Workbench: INSTALLED (incorrect namespace format)"
        echo "  Version: $WB_VERSION"
        echo "  Updated: $WB_MOD_TIME"
        echo "  Path: $MOD_DIR/freecad/RobustMCPBridge"
        echo "  Note: Reinstall to fix: just install::mcp-bridge-workbench"
    # Also check old-style installation
    elif [[ -d "$MOD_DIR/FreecadRobustMCPBridge" ]]; then
        WB_VERSION="unknown"
        if [[ -f "$MOD_DIR/FreecadRobustMCPBridge/package.xml" ]]; then
            WB_VERSION=$(extract_package_version "$MOD_DIR/FreecadRobustMCPBridge/package.xml")
        fi
        WB_MOD_TIME=$(get_mod_time "$MOD_DIR/FreecadRobustMCPBridge/InitGui.py")
        echo "⚠ Robust MCP Bridge Workbench: INSTALLED (legacy format)"
        echo "  Version: $WB_VERSION"
        echo "  Updated: $WB_MOD_TIME"
        echo "  Path: $MOD_DIR/FreecadRobustMCPBridge"
        echo "  Note: Reinstall to upgrade to new format: just install::mcp-bridge-workbench"
    else
        echo "✗ Robust MCP Bridge Workbench: NOT INSTALLED"
        echo "  Install: just install::mcp-bridge-workbench"
    fi
    echo ""

    # Check for legacy installations
    LEGACY_COUNT=0

    if [[ -d "$MOD_DIR/MCPBridge" ]]; then
        echo "⚠ Legacy plugin found: $MOD_DIR/MCPBridge"
        echo "  Run: rm -rf \"$MOD_DIR/MCPBridge\""
        ((LEGACY_COUNT++)) || true
    fi

    if [[ -f "$MACRO_DIR/StartMCPBridge.FCMacro" ]]; then
        echo "⚠ Legacy macro found: $MACRO_DIR/StartMCPBridge.FCMacro"
        echo "  Run: rm \"$MACRO_DIR/StartMCPBridge.FCMacro\""
        ((LEGACY_COUNT++)) || true
    fi

    if [[ $LEGACY_COUNT -gt 0 ]]; then
        echo ""
        echo "Note: Legacy installations can be removed. The workbench replaces them."
    fi

    echo "=========================================="

# =============================================================================
# Convenience Commands
# =============================================================================

# Uninstall all components (MCP server and workbench)
uninstall:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Uninstalling all Robust MCP components..."
    echo ""
    just install::uninstall-mcp-server
    echo ""
    just install::uninstall-mcp-bridge-workbench
    echo ""
    echo "All components uninstalled."

# Clean up everything (uninstall all + remove legacy installations)
cleanup:
    #!/usr/bin/env bash
    set -euo pipefail

    # Set FreeCAD directories
    eval "$(just install::_freecad-dirs)"

    echo "Cleaning up all Robust MCP installations..."
    echo ""

    # Uninstall current components
    just install::uninstall

    echo ""
    echo "Removing legacy installations..."

    # Remove legacy MCPBridge if present
    if [[ -d "$MOD_DIR/MCPBridge" ]]; then
        rm -rf "$MOD_DIR/MCPBridge"
        echo "  Removed: $MOD_DIR/MCPBridge"
    fi

    # Remove legacy macro if present
    if [[ -f "$MACRO_DIR/StartMCPBridge.FCMacro" ]]; then
        rm "$MACRO_DIR/StartMCPBridge.FCMacro"
        echo "  Removed: $MACRO_DIR/StartMCPBridge.FCMacro"
    fi

    echo ""
    echo "Cleanup complete."
