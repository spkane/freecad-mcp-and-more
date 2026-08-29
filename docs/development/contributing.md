# Contributing

Thank you for your interest in contributing to FreeCAD Robust MCP Server!

---

## Development Setup

### Prerequisites

- Python 3.11 (must match FreeCAD's bundled version)
- [mise](https://mise.jdx.dev/) for tool management
- FreeCAD 1.0+ installed

### Initial Setup

```bash
git clone https://github.com/spkane/freecad-addon-robust-mcp-server.git
cd freecad-addon-robust-mcp-server

# Install mise if not already installed
curl https://mise.run | sh

# Install project tools and dependencies
mise trust
mise install
just setup
```

### Safety CLI Account (Required for Security Scanning)

This project uses [Safety CLI](https://safetycli.com/) for dependency vulnerability scanning. Safety requires a **free account** for the `safety scan` command used in pre-commit hooks.

```bash
# Register for a free account (interactive)
uv run safety auth

# Or login if you already have an account
uv run safety auth --login
```

**Note:** Authentication is stored locally and only needs to be done once per machine. If you skip this step, the `safety` pre-commit hook will fail with an authentication prompt.

**CI/CD:** Safety runs in CI using the `SAFETY_API_KEY` repository secret.

### Running Tests

```bash
# Run unit tests
just testing::unit

# Run with coverage
just testing::cov

# Run all tests including integration
just testing::all

# Run type checking
uv run mypy src/
```

### Code Quality

```bash
# Run all pre-commit checks
just quality::check

# Run linting
just quality::lint

# Format code
just quality::format

# Run security checks
just quality::security
```

---

## Project Structure

```text
freecad-addon-robust-mcp-server/
├── src/freecad_mcp/           # Main package
│   ├── bridge/                # FreeCAD connection bridges
│   ├── tools/                 # MCP tool implementations
│   ├── resources/             # MCP resource implementations
│   ├── prompts/               # MCP prompt templates
│   └── server.py              # Main server entry point
├── freecad/                   # FreeCAD addon namespace package
│   └── RobustMCPBridge/       # Workbench files
├── tests/                     # Test suite
│   ├── unit/                  # Unit tests
│   └── integration/           # Integration tests
├── docs/                      # Documentation
└── just/                      # Justfile modules
```

---

## Contribution Guidelines

### Code Style

- Follow PEP 8 with 88-character line length (ruff/black)
- Use type hints for all function signatures
- Write Google-style docstrings
- Run `just quality::format` before committing

### Testing

- Write tests for all new functionality
- Maintain test coverage
- Run `just all` before submitting PRs (runs quality checks + unit tests)
- Integration tests require FreeCAD (run via CI)

### Documentation

- Update docstrings for API changes
- Update user docs for feature changes
- Run `just documentation::build` to build and verify

### Commits

- Use conventional commit format
- Keep commits focused and atomic
- Reference issues when applicable

---

## Adding New MCP Tools

1. **Choose the right module** in `src/freecad_mcp/tools/`
1. **Add the tool function** with proper docstring:

```python
@mcp.tool()
async def my_new_tool(
    param1: str,
    param2: int = 10,
    doc_name: str | None = None,
) -> dict[str, Any]:
    """Short description of what the tool does.

    Args:
        param1: Description of param1.
        param2: Description of param2.
        doc_name: Document name. Uses active if None.

    Returns:
        Dictionary with result information.
    """
    bridge = await get_bridge()
    code = f'''
# FreeCAD Python code here
_result_ = {{"success": True}}
'''
    result = await bridge.execute_python(code)
    return result.result or {"success": False}
```

1. **Add tests** in the appropriate test file
1. **Update documentation** in `docs/guide/tools.md`
1. **Update capabilities resource** in `src/freecad_mcp/resources/freecad.py`

---

## Adding New Connection Modes

1. Create a new bridge class in `src/freecad_mcp/bridge/`
1. Inherit from `FreecadBridge` base class
1. Implement all abstract methods
1. Add to bridge factory in `src/freecad_mcp/bridge/__init__.py`
1. Add configuration option in `src/freecad_mcp/config.py`
1. Update documentation

---

## Release Process

Releases are automated via GitHub Actions:

1. Update the component's `RELEASE_NOTES.md` file (see [Releasing](releasing.md) for details)
1. Bump versions for workbench/macros (MCP Server auto-bumps from tag)
1. Commit and push changes
1. Create release tag with `just release::tag-<component> X.Y.Z`
1. CI builds and publishes:
   - PyPI package and Docker images (MCP Server)
   - GitHub Release archives (workbench and macros)

---

## Future Work

The following items are on the roadmap and welcome contributions:

### Embedded Mode Integration Tests

<!-- TODO: Add live FreeCAD integration tests for embedded mode -->

Currently, embedded mode has only mocked unit tests. Adding live integration tests would require:

1. CI workflow that runs on Linux (embedded mode is Linux-only)
1. Uses FreeCAD AppImage's bundled Python interpreter
1. Sets up `PYTHONPATH` and `LD_LIBRARY_PATH` to point to AppImage libs
1. Runs tests with `FREECAD_MODE=embedded`

**Challenge:** The AppImage bundles Python 3.11, so tests must run using that interpreter (not the system Python) to avoid ABI incompatibility.

**Reference:** See `macro-test.yaml` for how integration tests currently work with xmlrpc mode.

---

## Getting Help

- **Issues:** [GitHub Issues](https://github.com/spkane/freecad-addon-robust-mcp-server/issues)

---

## License

This project is licensed under the MIT License. See [LICENSE](https://github.com/spkane/freecad-addon-robust-mcp-server/blob/main/LICENSE) for details.
