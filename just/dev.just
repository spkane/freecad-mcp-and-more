# Development utility commands
# Usage: just dev::clean, just dev::repl, etc.
#
# Miscellaneous development tools and utilities.

# Project root directory (justfile_directory() returns the main justfile's directory)
project_root := justfile_directory()

# =============================================================================
# Setup & Dependencies
# =============================================================================

# Install all project dependencies (Python packages + dev tools)
install-deps:
    cd {{project_root}} && uv sync
    @echo ""
    @echo "Dependencies installed!"
    @echo ""
    @echo "To run the Robust MCP Server:"
    @echo "  just mcp::run              # stdio mode"
    @echo "  just mcp::run-debug        # with debug logging"
    @echo "  just mcp::run-http         # HTTP mode for remote access"

# Install pre-commit hooks (for git commit/push integration)
install-pre-commit:
    cd {{project_root}} && uv run pre-commit install
    cd {{project_root}} && uv run pre-commit install --hook-type commit-msg

# Update all dependencies to latest versions (mise tools, uv.lock, pre-commit hooks)
update-deps:
    #!/usr/bin/env bash
    set -euo pipefail
    cd "{{project_root}}"

    echo "Updating mise-managed tools..."
    mise upgrade
    echo ""

    echo "Updating Python dependencies..."
    uv lock --upgrade
    uv sync

    echo ""
    echo "Updating pre-commit hooks..."
    uv run pre-commit autoupdate

    echo ""
    echo "All dependencies updated!"
    echo "  - mise tools: updated (see .mise.toml)"
    echo "  - Python deps: updated (see uv.lock)"
    echo "  - pre-commit hooks: updated (see .pre-commit-config.yaml)"

# =============================================================================
# Development Utilities
# =============================================================================

# Clean build artifacts and caches
clean:
    rm -rf {{project_root}}/.pytest_cache {{project_root}}/.mypy_cache {{project_root}}/.ruff_cache {{project_root}}/.coverage {{project_root}}/htmlcov {{project_root}}/dist {{project_root}}/build
    find {{project_root}} -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find {{project_root}} -type f -name "*.pyc" -delete 2>/dev/null || true

# Open Python REPL with project modules available
repl:
    cd {{project_root}} && uv run python -c "import freecad_mcp; print('FreeCAD Robust MCP loaded')" && uv run python

# Show project structure (tree view, requires 'tree' command)
tree:
    #!/usr/bin/env bash
    if ! command -v tree &> /dev/null; then
        echo "The 'tree' command is not installed."
        echo "Install it with: brew install tree (macOS) or apt install tree (Linux)"
        exit 1
    fi
    cd "{{project_root}}" && tree -I '__pycache__|*.egg-info|.git|.mypy_cache|.pytest_cache|.ruff_cache|htmlcov|dist|build|.venv|site' -a

# Validate project configuration files (pyproject.toml, etc.)
validate:
    cd {{project_root}} && uv pip check
    @echo "Package dependencies are valid."
