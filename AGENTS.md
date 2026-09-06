# CLAUDE.md - AI Assistant Guidelines for This Project

## Project Overview

This is a Python project that provides an MCP (Model Context Protocol) server for FreeCAD integration. It follows strict code quality, security, and documentation standards.

### Critical: Python Version Must Match FreeCAD

**CRITICAL**: This project **MUST** use the same Python version that the current stable FreeCAD release bundles internally. FreeCAD embeds a specific Python version (e.g., `libpython3.11.dylib`), and using a different Python version causes **fatal crashes** (SIGSEGV) due to ABI incompatibility.

Before changing the Python version in `.mise.toml` or `pyproject.toml`:

1. Check which Python version FreeCAD bundles:
   - macOS: `ls /Applications/FreeCAD.app/Contents/Resources/lib/libpython*`
   - Linux: `ls /usr/lib/freecad/lib/libpython*` or check FreeCAD's Python console
1. The Python minor version (e.g., 3.11) **must match exactly**
1. Using Python 3.12+ with FreeCAD that bundles Python 3.11 will crash on `import FreeCAD`

Current requirement: **Python 3.11** (matching FreeCAD 1.0.x bundled Python)

### FreeCAD Connection Modes

This MCP server supports three connection modes. **Embedded mode does NOT work on macOS** due to how FreeCAD's libraries are linked.

| Mode       | Description                                 | Platform Support                  | Testing Level    |
| ---------- | ------------------------------------------- | --------------------------------- | ---------------- |
| `xmlrpc`   | Connects to FreeCAD via XML-RPC (port 9875) | **All platforms** (recommended)   | Full integration |
| `socket`   | Connects via JSON-RPC socket (port 9876)    | **All platforms**                 | Full integration |
| `embedded` | Imports FreeCAD directly into process       | **Linux only** (crashes on macOS) | Unit tests only  |

**Embedded mode testing:** Embedded mode is tested via mocked unit tests in CI. It does not have integration tests with actual FreeCAD because that would require running FreeCAD in-process on Linux CI runners. For production use, prefer `xmlrpc` or `socket` modes which have full integration test coverage.

**Why embedded mode fails on macOS:**
FreeCAD's `FreeCAD.so` library links to `@rpath/libpython3.11.dylib` (FreeCAD's bundled Python). When you try to import it from a different Python interpreter (even the same version), it causes a crash because the Python runtime state is incompatible.

**Recommended setup for macOS/Windows:**

1. Use `xmlrpc` or `socket` mode in your configuration

1. Start FreeCAD and start the MCP bridge:

   - Install the Robust MCP Bridge workbench via Addon Manager, or
   - Use `just freecad::run-gui` from the source repository

1. The MCP server will then connect to FreeCAD over the network

---

## Development Environment Setup

### Required Tools (managed via `mise`)

This project uses [`mise`](https://mise.jdx.dev/) for local development tool management. All tool versions are pinned in `.mise.toml`.

```bash
# Install mise via the Official mise installer script (if not already installed)
curl https://mise.run | sh

# Install all project tools
mise install

# Activate mise in your shell (add to .bashrc/.zshrc)
eval "$(mise activate bash)"  # or zsh/fish
```

### Package Management (via `uv`)

This project uses [`uv`](https://docs.astral.sh/uv/) for Python package and virtual environment management.

**CRITICAL**: All Python tools (pytest, ruff, mypy, etc.) are installed in the virtual environment managed by `uv`. You must use `uv run` to execute them.

```bash
# Install dependencies
uv sync --all-extras

# Run any Python tool
uv run pytest              # Run tests
uv run ruff check src      # Run linter
uv run mypy src            # Run type checker
uv run pre-commit run      # Run pre-commit

# Run the project
uv run freecad-mcp
```

**Why `uv run` is required:**

- Tools like `pytest`, `ruff`, `mypy` are NOT installed globally
- They exist only in the project's virtual environment
- Running `pytest` directly will fail with "command not found"
- Always prefix with `uv run` when running Python tools directly

### Safety CLI Account (for Security Scanning)

This project uses [Safety CLI](https://safetycli.com/) for dependency vulnerability scanning. Safety requires a **free account** for the `safety scan` command.

**First-time setup:**

```bash
# Register for a free account (interactive)
uv run safety auth

# Or login if you already have an account
uv run safety auth --login
```

**Note:** The Safety CLI authentication is stored locally and only needs to be done once per machine. If you skip this step, `just quality::check` will show a clear error message with instructions. The `safety` pre-commit hook will also fail with an authentication prompt.

**CI/CD:** Safety runs in CI using the `SAFETY_API_KEY` repository secret. The API key is passed via environment variable to the pre-commit hook.

### CodeRabbit CLI (for AI Code Reviews)

This project supports [CodeRabbit CLI](https://www.coderabbit.ai/cli) for AI-powered code reviews in your terminal. The CLI is optional for local development - the CodeRabbit GitHub App automatically reviews all PRs.

**First-time setup:**

```bash
# Install CodeRabbit CLI
just coderabbit::install

# Authenticate (opens browser)
just coderabbit::login
```

**Usage:**

```bash
# Review staged changes (most common)
just coderabbit::review

# Review with auto-fix suggestions
just coderabbit::review-fix

# Review changes since main branch
just coderabbit::review-branch

# See all available commands
just --list coderabbit
```

**Rate limits:** Free tier allows 1 review per hour. Pro tier allows 5 reviews per hour.

**CI/CD:** The CodeRabbit GitHub App handles PR reviews automatically. The CLI is skipped in CI since it's for local development workflow only.

### Workflow Commands (via `just`)

This project uses [`just`](https://just.systems/) as a command runner. Always prefer `just` commands over raw commands.

Commands are organized into modules for better organization:

```bash
# List top-level commands and available modules
just

# List commands in a specific module (use list-<module>)
just list-mcp           # MCP server commands
just list-freecad       # FreeCAD plugin/macro commands
just list-install       # Installation commands
just list-quality       # Code quality commands
just list-testing       # Test commands
just list-docker        # Docker commands
just list-documentation # Documentation commands
just list-dev           # Development utilities
just list-release       # Release and tagging commands
just list-coderabbit    # AI code review commands

# List ALL commands from all modules at once
just list-all

# MCP server commands
just mcp::run              # Run the MCP server (stdio mode)
just mcp::run-debug        # Run with debug logging
just mcp::run-http         # Run in HTTP mode for remote access

# FreeCAD commands
just freecad::run-gui      # Run FreeCAD GUI with MCP bridge
just freecad::run-headless # Run FreeCAD headless with MCP bridge

# Installation commands (for end users)
just install::mcp-server           # Install MCP server system-wide (via uv tool)
just install::mcp-bridge-workbench # Install FreeCAD workbench addon
just install::status               # Check installation status

# Quality commands
just quality::check        # Run all pre-commit checks
just quality::lint         # Run linting
just quality::format       # Format code
just quality::typecheck    # Run type checking
just quality::security     # Run security scanning
just quality::scan         # Run all secrets scanners

# Testing commands
just testing::unit         # Run unit tests
just testing::cov          # Run tests with coverage
just testing::quick         # Run tests without slow markers
just testing::integration  # Run integration tests
just testing::integration-freecad-auto # Integration tests with auto FreeCAD startup
just testing::watch        # Run tests in watch mode
just testing::all          # Run all tests including integration

# Documentation commands
just documentation::build  # Build documentation
just documentation::serve  # Serve documentation locally
just documentation::serve-versioned  # Serve versioned docs (from gh-pages)
just documentation::list-versions    # List deployed doc versions

# Docker commands
just docker::build         # Build Docker image for local architecture
just docker::build-multi   # Build multi-arch image (amd64 + arm64)
just docker::run           # Run Docker container
just docker::clean         # Remove local Docker image
just docker::clean-all     # Remove images and build cache

# Development utilities
just dev::install-deps     # Install all project dependencies
just dev::install-pre-commit # Install pre-commit hooks
just dev::update-deps      # Update all dependencies
just dev::clean            # Clean build artifacts and caches
just dev::repl             # Open Python REPL with project loaded
just dev::tree             # Show project structure
just dev::validate         # Validate project configuration

# AI code review commands
just coderabbit::review    # Review staged changes
just coderabbit::review-fix # Review with auto-fix suggestions

# Release commands (component-specific tagging)
just release::status                  # Show unreleased changes across all components
just release::tag-mcp-server 1.0.0    # Release MCP server (PyPI + Docker)
just release::tag-workbench 1.0.0     # Release Robust MCP Bridge workbench
just release::list-tags               # List all release tags
just release::latest-versions         # Show latest version of each component
just release::delete-tag <tag>        # Delete a release tag (local and remote)

# Combined workflows
just setup                 # Full dev setup (install deps + hooks)
just all                   # Run all quality checks and unit/coverage tests
just all-with-integration  # Run all checks and integration tests
```

#### Just Module Structure

| Module          | Description                           | Key Commands                                         |
| --------------- | ------------------------------------- | ---------------------------------------------------- |
| `mcp`           | MCP server commands                   | `run`, `run-debug`, `run-http`                       |
| `freecad`       | FreeCAD running commands              | `run-gui`, `run-headless`, `run-gui-custom`          |
| `install`       | User installation commands            | `mcp-server`, `mcp-bridge-workbench`, `status`       |
| `quality`       | Code quality and linting              | `check`, `lint`, `format`, `scan`                    |
| `testing`       | Test execution                        | `unit`, `cov`, `integration-freecad-auto`, `watch`   |
| `docker`        | Docker build and run commands         | `build`, `build-multi`, `run`, `clean-all`           |
| `documentation` | Documentation building and deployment | `build`, `serve`, `serve-versioned`, `list-versions` |
| `dev`           | Development utilities                 | `install-deps`, `update-deps`, `clean`               |
| `release`       | Release and tagging                   | `status`, `tag-mcp-server`, `delete-tag`             |
| `coderabbit`    | AI code reviews (local)               | `install`, `login`, `review`, `review-fix`           |

Module files are located in the `just/` directory.

---

## Code Quality Standards

### Pre-commit Hooks

**CRITICAL**: This project uses `pre-commit` for all code quality checks. Before finishing ANY code changes:

1. Run `just quality::check` or `uv run pre-commit run --all-files`
1. Fix ALL issues reported
1. Re-run until all checks pass

Pre-commit runs these checks:

**Python Quality:**

- **Ruff**: Linting and import sorting (replaces flake8, isort, pyupgrade)
- **Ruff Format**: Code formatting (replaces black)
- **MyPy**: Static type checking
- **Bandit**: Security vulnerability scanning
- **Safety**: Dependency vulnerability checking (requires `.safety-policy.yml`)

**Secrets Detection (Multi-Layer):**

- **Gitleaks**: Fast regex-based secrets scanning
- **detect-secrets**: Baseline tracking for known/approved secrets
- **TruffleHog**: Verified secrets detection (skipped in CI due to wasm bugs)

**Documentation & Config:**

- **Markdownlint**: Markdown linting with auto-fix
- **md-toc**: Table of contents generation for README
- **Codespell**: Spell checking in code and docs
- **MkDocs build**: Validates documentation builds successfully
- **YAML/TOML/JSON/XML validation**: Config file validation
- **check-json5**: JSONC validation for VS Code config files

**Infrastructure:**

- **Hadolint**: Dockerfile linting
- **Trivy**: Dockerfile security misconfiguration scanning
- **Shellcheck**: Shell script linting
- **Actionlint**: GitHub Actions workflow linting
- **validate-pyproject**: Python project configuration validation
- **check-github-workflows**: GitHub workflow schema validation
- **check-dependabot**: Dependabot config validation

**Other:**

- **Trailing whitespace and EOF fixes**: File hygiene
- **Commitizen**: Commit message format validation (commit-msg stage)
- **no-commit-to-branch**: Prevents commits to main/master
- **CodeRabbit**: AI code review (manual stage only)

### Linting Rules

- Follow PEP 8 style guidelines
- Use type hints for ALL function signatures
- Maximum line length: 88 characters (ruff/black default)
- Use modern Python syntax (3.10+ features encouraged)

### Accessible Language

> This isn't about politics—it's about clarity. Literal terms translate better, search better, and are understood by more people regardless of cultural background. Good communication is good engineering.

Use clear, literal language in code, comments, documentation, and commit messages. Avoid idioms, metaphors, and jargon that may be unclear, exclusionary, or carry unintended connotations:

| Avoid                                      | Prefer                                           |
| ------------------------------------------ | ------------------------------------------------ |
| sanity check, sanity test                  | validation, verification, smoke test, quick test |
| sane defaults, insane behavior             | sensible defaults, unexpected behavior           |
| whitelist, blacklist                       | allowlist, blocklist                             |
| master, slave                              | main, primary, replica, secondary                |
| kill, abort, nuke (as metaphors)           | stop, terminate, cancel, remove                  |
| war room, battle-tested                    | operations center, production-tested             |
| cripple, blind to                          | disable, unaware of, ignore                      |
| dummy, handicapped                         | placeholder, stub, limited                       |

**Note:** Actual command names (e.g., `kill -9`, `kill_port()`, `git rebase --abort`) are fine when discussing or documenting those specific commands. The guidance above applies to metaphorical usage in prose, comments, and naming.

**Why this matters:**

- Literal terms are clearer to non-native speakers and those unfamiliar with idioms
- Avoids unintentionally alienating contributors
- Makes code more accessible and professional
- Many organizations and open-source projects have adopted similar guidelines

### Security Scanning

- Bandit scans for common security issues
- Never commit secrets, API keys, or credentials
- Use environment variables for sensitive configuration
- Safety checks dependencies for known vulnerabilities

### Secrets Detection (Multi-Layer)

This project uses a comprehensive, multi-layer approach to secrets detection:

| Tool               | Purpose                                            | Config File         |
| ------------------ | -------------------------------------------------- | ------------------- |
| **Gitleaks**       | Fast regex-based scanning of files and git history | `.gitleaks.toml`    |
| **detect-secrets** | Baseline tracking for known/approved secrets       | `.secrets.baseline` |
| **TruffleHog**     | Verified secrets (actually tests if they work)     | CLI args            |

```bash
# Run all secrets scanners
just quality::scan

# Individual scanners
just quality::scan-gitleaks         # Fast pattern matching
just quality::scan-gitleaks-history # Scan git history
just quality::scan-detect           # Check against baseline
just quality::scan-audit            # Interactive baseline audit
just quality::scan-trufflehog       # Verified secrets only
```

**Managing False Positives:**

1. **Gitleaks**: Add patterns to `.gitleaks.toml` allowlist section
1. **detect-secrets**: Run `just quality::scan-audit` to mark false positives in baseline
1. **TruffleHog**: Uses `--only-verified` to minimize false positives

### Markdown Linting

All markdown files are linted for consistency:

```bash
just quality::markdown-lint  # Check markdown files
just quality::markdown-fix   # Auto-fix markdown issues
```

Configuration: `.markdownlint.yaml`

---

## Documentation Requirements

### Code Documentation

**ALL code must be documented** for auto-documentation building:

1. **Module docstrings**: Every Python file must have a module-level docstring explaining its purpose

1. **Class docstrings**: Use Google-style or NumPy-style docstrings

   ```python
   class Example:
       """Short description of the class.

       Longer description if needed, explaining the purpose
       and usage of this class.

       Attributes:
           name: Description of the name attribute.
           value: Description of the value attribute.

       Example:
           >>> obj = Example("test", 42)
           >>> obj.process()
       """
   ```

1. **Function/Method docstrings**: Document all public functions

   ```python
   def calculate_total(items: list[Item], tax_rate: float = 0.0) -> Decimal:
       """Calculate the total price including optional tax.

       Args:
           items: List of Item objects to sum.
           tax_rate: Tax rate as a decimal (e.g., 0.08 for 8%).

       Returns:
           The total price as a Decimal, including tax.

       Raises:
           ValueError: If tax_rate is negative.

       Example:
           >>> items = [Item(price=10), Item(price=20)]
           >>> calculate_total(items, tax_rate=0.1)
           Decimal('33.00')
       """
   ```

1. **Inline comments**: Use sparingly, only for complex logic

### Documentation Building

Documentation is auto-generated using MkDocs with the Material theme. Run:

```bash
just documentation::build  # Build documentation
just documentation::serve  # Serve documentation locally
just documentation::open   # Open docs in browser
```

### MkDocs Configuration

**Theme**: Material for MkDocs with dark mode default, deep purple color scheme.

**Key Plugins**:

- **mkdocstrings**: Auto-generates API docs from Python docstrings
- **mkdocs-macros-plugin**: Variables and templating in markdown
- **git-revision-date-localized**: Shows "Last updated" on pages
- **glightbox**: Image lightbox/zoom functionality

**Macros Plugin - Custom Delimiters**:

To avoid conflicts with Python dict literals in code blocks, this project uses custom delimiters:

```markdown
<!-- Standard Jinja2 (DON'T USE): {{ variable }} -->
<!-- Use instead: -->
{{@ variable @}}

<!-- For blocks: -->
{%@ if condition @%}
...
{%@ endif @%}
```

Variables are defined in `docs/variables.yaml`:

```yaml
project_name: FreeCAD Robust MCP Suite
xmlrpc_port: 9875
socket_port: 9876
```

**Reference**: See `docs/development/mkdocs-guide.md` for complete documentation on available extensions (admonitions, tabs, code annotations, mermaid diagrams, etc.).

### Documentation Deployment (GitHub Pages)

Documentation is deployed to GitHub Pages with versioning via **mike**:

- **Automatic deployment**: The `docs.yaml` workflow deploys docs automatically
- **Version selector**: Users can switch between versions in the docs UI
- **"latest" version**: Always reflects the current `main` branch (default landing page)
- **Versioned releases**: Created when MCP server tags (`robust-mcp-server-vX.Y.Z`) are pushed

**Deployment triggers**:

| Trigger                      | Version Deployed | Sets Default?  |
| ---------------------------- | ---------------- | -------------- |
| Push to `main`               | `latest`         | Yes            |
| Tag `robust-mcp-server-v1.0` | `1.0.0`          | No             |
| Manual workflow dispatch     | User-specified   | User choice    |

**Local testing commands**:

```bash
just documentation::serve-versioned  # Serve versioned docs locally
just documentation::list-versions    # List deployed versions
just documentation::deploy-dev       # Deploy "dev" version locally
just documentation::deploy-latest 1.0.0  # Deploy version and set as latest
```

**Note**: Local `deploy-*` commands modify the `gh-pages` branch locally. The GitHub Actions workflow handles actual deployment to GitHub Pages.

**Initial GitHub Pages Setup**:

This repo uses **mike** for versioned documentation, which requires a `gh-pages` branch:

1. **Create the gh-pages branch** (if it doesn't exist):

   ```bash
   git checkout --orphan gh-pages
   git reset --hard
   git commit --allow-empty -m "Initialize gh-pages branch"
   git push origin gh-pages
   git checkout main
   ```

2. **Configure GitHub Pages** in repo Settings → Pages:
   - Source: **Deploy from a branch**
   - Branch: `gh-pages` / `/ (root)`

3. **First deployment**: Push to `main` or manually trigger the `docs.yaml` workflow

---

## Testing Requirements

### Test Coverage

**ALL code must have tests**. Create tests for:

1. **Unit tests**: Test individual functions and methods
1. **Integration tests**: Test component interactions
1. **Edge cases**: Test boundary conditions and error handling
1. **Regression tests**: Add tests when fixing bugs

### Test Structure

```text
tests/
├── __init__.py
├── conftest.py          # Shared fixtures
├── unit/                # Unit tests
│   ├── __init__.py
│   └── test_*.py
├── integration/         # Integration tests
│   ├── __init__.py
│   └── test_*.py
├── just_commands/       # Just command tests
│   ├── __init__.py
│   ├── conftest.py      # Just test fixtures
│   └── test_*.py        # Tests for each just module
└── fixtures/            # Test data files
```

### Writing Tests

- Use `pytest` as the test framework
- Use descriptive test names: `test_calculate_total_with_empty_list_returns_zero`
- Use fixtures for common test data
- Use parametrize for testing multiple inputs
- Aim for high coverage but prioritize meaningful tests

```python
import pytest
from myproject import calculate_total

class TestCalculateTotal:
    """Tests for the calculate_total function."""

    def test_empty_list_returns_zero(self):
        """Empty item list should return zero total."""
        assert calculate_total([]) == Decimal("0")

    @pytest.mark.parametrize("tax_rate,expected", [
        (0.0, Decimal("100")),
        (0.1, Decimal("110")),
    ])
    def test_tax_calculation(self, sample_items, tax_rate, expected):
        """Tax should be correctly applied to total."""
        result = calculate_total(sample_items, tax_rate=tax_rate)
        assert result == expected
```

### Running Tests

```bash
just testing::unit              # Run unit tests
just testing::cov               # Run tests with coverage report
just testing::quick              # Run tests without slow markers
just testing::all               # Run all tests including integration
uv run pytest tests/unit/       # Run specific test directory
uv run pytest -k "test_name"    # Run specific test by name
```

### Integration Tests with Auto-Start FreeCAD

**IMPORTANT**: The following commands **automatically start FreeCAD** and run the integration tests. You do NOT need to manually start FreeCAD first:

```bash
just testing::integration-gui-release      # Starts FreeCAD GUI, runs tests, stops FreeCAD
just testing::integration-headless-release # Starts FreeCAD headless, runs tests, stops FreeCAD
```

These commands handle the full lifecycle:

1. Start FreeCAD with the MCP bridge
2. Wait for the bridge to be ready
3. Run integration tests
4. Stop FreeCAD when done

Use these commands when you need to verify integration tests pass. They are the recommended way to run integration tests during development.

For manual testing (when you want FreeCAD to stay running), use:

```bash
just freecad::run-gui      # Start FreeCAD GUI with bridge (stays running)
just freecad::run-headless # Start FreeCAD headless with bridge (stays running)
# Then in another terminal:
just testing::integration  # Run integration tests against running FreeCAD
```

### Just Command Testing

The project includes a comprehensive test suite for all `just` commands in `tests/just_commands/`. This ensures that justfile syntax errors, missing dependencies, and runtime failures are caught early.

**Test Categories:**

| Marker           | Description                                          | Command                           |
| ---------------- | ---------------------------------------------------- | --------------------------------- |
| `just_syntax`    | Validates just can parse commands (--dry-run)        | `just testing::just-syntax`       |
| `just_runtime`   | Actually executes commands and verifies behavior     | `just testing::just-runtime`      |
| `just_release`   | Release command tests with cleanup                   | `just testing::just-release`      |
| (all)            | Run all just command tests                           | `just testing::just-all`          |

**Running Just Command Tests:**

```bash
just testing::just-syntax    # Fast syntax validation (recommended before commits)
just testing::just-runtime   # Runtime tests (slower, actually runs commands)
just testing::just-release   # Release command tests with cleanup
just testing::just-all       # All just command tests
```

#### Updating Tests When Changing Just Commands

**MANDATORY**: When you add, modify, or remove a just command, you MUST update the corresponding test file:

| Module         | Test File                                   |
| -------------- | ------------------------------------------- |
| Main justfile  | `tests/just_commands/test_main.py`          |
| coderabbit     | `tests/just_commands/test_coderabbit.py`    |
| dev            | `tests/just_commands/test_dev.py`           |
| docker         | `tests/just_commands/test_docker.py`        |
| documentation  | `tests/just_commands/test_documentation.py` |
| freecad        | `tests/just_commands/test_freecad.py`       |
| install        | `tests/just_commands/test_install.py`       |
| mcp            | `tests/just_commands/test_mcp.py`           |
| quality        | `tests/just_commands/test_quality.py`       |
| release        | `tests/just_commands/test_release.py`       |
| testing        | `tests/just_commands/test_testing.py`       |

**What to Update:**

1. **New command**: Add to `COMMANDS` list in syntax tests, add runtime test if applicable
2. **Modified command**: Update any tests that depend on command behavior/output
3. **Removed command**: Remove from `COMMANDS` list and delete related tests
4. **Changed arguments**: Update parametrized tests with correct arguments

**Release Command Testing Strategy:**

Release commands are tested carefully to avoid accidental releases:

- **Syntax tests**: Use `--dry-run` for all commands
- **Read-only tests**: Safe commands like `status`, `list-tags`, `latest-versions`
- **Version bump tests**: Test bump commands (modify local files, restored after test)
- **Tag validation**: Test version format validation, dirty tree detection
- **Skip push tests**: Commands that push to remote are only syntax-tested

For actual release testing with cleanup, tests use:

- Test versions like `99.99.99-test` that are clearly non-production
- Backup and restore of modified files
- Tag prefixes like `test-release-XXXXXX` with random suffixes

---

## Workflow for Code Changes

### Before Making Changes

1. Ensure you're on the latest code
1. Run `just install::mcp-server` to update dependencies
1. Run `just all` to verify clean starting state

### After Making Changes

**MANDATORY CHECKLIST** - Complete ALL steps before finishing:

1. [ ] **Add/update docstrings** for all new/modified code
1. [ ] **Add/update tests** for all new/modified functionality
1. [ ] **Run formatting**: `just quality::format`
1. [ ] **Run linting**: `just quality::lint` - fix ALL issues
1. [ ] **Run type checking**: `just quality::typecheck` - fix ALL issues
1. [ ] **Run security checks**: `just quality::security` - fix ALL issues
1. [ ] **Run tests**: `just testing::unit` - ALL tests must pass
1. [ ] **Run pre-commit**: `just quality::check` - ALL checks must pass

### Quick Verification Command

```bash
# Run everything at once - must complete with no errors
just all
```

### Running Pre-commit on Specific Files

**IMPORTANT**: After editing any files, always run pre-commit hooks on those specific files before considering the task complete:

```bash
# Run pre-commit on specific files you edited
uv run pre-commit run --files path/to/file1.py path/to/file2.py

# Or run on all files (slower but comprehensive)
uv run pre-commit run --all-files
```

This catches issues early and ensures code quality standards are met. Never skip this step - fix all reported issues before finishing.

---

## Library and Tool Versions

### Version Policy

- **Always use the most recent stable releases** of all libraries and tools
- **Dependency specification follows Python best practices**:
  - `pyproject.toml` uses `>=` minimum version constraints (e.g., `pydantic>=2.0`)
  - `uv.lock` contains exact pinned versions for reproducible builds
  - This allows the package to work as a library while ensuring reproducibility
  - **Do not change `>=` to `==` in pyproject.toml** - this would break library usability
- Regularly update dependencies with `just update-deps` (updates uv.lock)
- Check for security vulnerabilities with `just quality::security`

### Core Dependencies

Keep these tools at their latest stable versions:

- Python: **3.11** (must match FreeCAD's bundled Python - see "Critical: Python Version Must Match FreeCAD" above)
- Ruff: Latest stable
- MyPy: Latest stable
- Pytest: Latest stable
- Pre-commit: Latest stable

---

## File Structure Conventions

```text
project-root/
├── .github/
│   ├── ISSUE_TEMPLATE/       # GitHub issue templates
│   │   └── *.yaml
│   ├── workflows/            # GitHub Actions workflows
│   │   ├── codeql.yaml           # Security analysis
│   │   ├── docker.yaml           # Docker build (CI)
│   │   ├── docs.yaml             # Documentation deployment
│   │   ├── mcp-server-release.yaml         # MCP server → PyPI/Docker
│   │   ├── mcp-workbench-release.yaml      # Workbench → GitHub Release
│   │   ├── pre-commit.yaml       # Pre-commit checks
│   │   └── test.yaml             # Unit/integration tests
│   └── dependabot.yaml       # Dependency updates
├── freecad/                  # FreeCAD addon namespace package
│   └── RobustMCPBridge/      # Robust MCP Bridge workbench
│       ├── Qt/               # Qt/PySide UI components
│       │   ├── status_widget.py      # Status bar widget
│       │   └── preferences_page.py   # Preferences dialog
│       ├── freecad_mcp_bridge/   # Bridge Python package
│       ├── Resources/
│       │   ├── Icons/        # Workbench icons (SVG)
│       │   └── Media/        # Screenshots (PNG)
│       ├── __init__.py       # FreeCAD workbench init (was Init.py)
│       └── init_gui.py       # FreeCAD GUI init (was InitGui.py)
├── docs/                     # MkDocs documentation source
│   ├── assets/               # Images, diagrams
│   ├── development/          # Developer guides
│   ├── getting-started/      # Installation, quickstart
│   ├── guide/                # User guides
│   ├── reference/            # API reference
│   ├── variables.yaml        # MkDocs macro variables
│   └── index.md              # Documentation home
├── just/                     # Just module files
│   ├── coderabbit.just       # AI code review commands
│   ├── dev.just              # Development utilities
│   ├── docker.just           # Docker build/run commands
│   ├── documentation.just    # Documentation commands
│   ├── freecad.just          # FreeCAD running commands
│   ├── install.just          # Installation commands
│   ├── mcp.just              # MCP server commands
│   ├── quality.just          # Code quality commands
│   ├── release.just          # Release/tagging commands
│   └── testing.just          # Test commands
├── src/
│   └── freecad_mcp/          # Main MCP server package
│       ├── bridge/           # FreeCAD connection bridges
│       ├── prompts/          # MCP prompt templates
│       ├── resources/        # MCP resources
│       ├── tools/            # MCP tools (document, object, etc.)
│       ├── __init__.py
│       ├── server.py         # Main MCP server
│       └── settings.py       # Configuration settings
├── tests/
│   ├── fixtures/             # Test data files (.FCStd, etc.)
│   ├── integration/          # Integration tests (require FreeCAD)
│   ├── unit/                 # Unit tests
│   └── conftest.py           # Shared pytest fixtures
├── .codespell-ignore-words.txt  # Spell checker exceptions
├── .gitleaks.toml            # Gitleaks secrets config
├── .markdownlint.yaml        # Markdown linting rules
├── .mise.toml                # Tool version management
├── .pre-commit-config.yaml   # Pre-commit hook configuration
├── .safety-policy.yml        # Safety CLI scan policy
├── .secrets.baseline         # detect-secrets baseline
├── CLAUDE.md                 # This file (AI assistant guidelines)
├── Dockerfile                # Docker image definition
├── justfile                  # Main task runner (imports modules)
├── mkdocs.yaml               # MkDocs configuration
├── package.xml               # FreeCAD addon metadata
├── pyproject.toml            # Project configuration and dependencies
└── uv.lock                   # Locked dependency versions
```

---

## File Extension Conventions

**Use full file extensions, not DOS-style shortened versions:**

| Correct Extension | Incorrect (DOS-style) |
| ----------------- | --------------------- |
| `.yaml`           | `.yml`                |
| `.jpeg`           | `.jpg`                |
| `.html`           | `.htm`                |
| `.conf`           | (varies)              |

This applies to:

- GitHub workflow files: `.github/workflows/*.yaml`
- GitHub issue templates: `.github/ISSUE_TEMPLATE/*.yaml`
- Dependabot config: `.github/dependabot.yaml`
- MkDocs config: `mkdocs.yaml`
- Any other YAML, JPEG, or similar files

When creating new files, always use the full extension.

---

## Configuration Files Reference

This section describes the purpose and key settings in each configuration file.

### Tool Management

| File             | Purpose                                                                                                                                                                                                       |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `.mise.toml`     | Pins versions for Python, uv, just, pre-commit, and security tools (trivy, gitleaks, actionlint, markdownlint-cli2). Also sets environment variables for FreeCAD connection settings.                         |
| `pyproject.toml` | Python project configuration: dependencies, build system, tool configs (ruff, mypy, pytest, bandit, codespell, commitizen).                                                                                   |
| `uv.lock`        | Exact locked versions of all Python dependencies for reproducible builds.                                                                                                                                     |

### Code Quality

| File                          | Purpose                                                                               |
| ----------------------------- | ------------------------------------------------------------------------------------- |
| `.pre-commit-config.yaml`     | Pre-commit hook definitions. See [Pre-commit Hooks](#pre-commit-hooks) for details.   |
| `.markdownlint.yaml`          | Markdown linting rules (heading style, list indentation, code block style, etc.).     |
| `.codespell-ignore-words.txt` | Words to ignore during spell checking (technical terms, tool names).                  |

### Security Scanning

| File                  | Purpose                                                                                                       |
| --------------------- | ------------------------------------------------------------------------------------------------------------- |
| `.gitleaks.toml`      | Gitleaks secrets scanner configuration with allowlist patterns for false positives.                           |
| `.secrets.baseline`   | detect-secrets baseline tracking known/approved secrets and their locations.                                  |
| `.safety-policy.yml`  | Safety CLI scan policy - excludes `.venv`, `node_modules`, and other directories from vulnerability scanning. |

### Documentation

| File                  | Purpose                                                                                                        |
| --------------------- | -------------------------------------------------------------------------------------------------------------- |
| `mkdocs.yaml`         | MkDocs configuration: Material theme, plugins (macros, mkdocstrings, git-revision-date), navigation structure. |
| `docs/variables.yaml` | Variables for MkDocs macros plugin (project name, ports, paths). Use `{{@ variable @}}` syntax in docs.        |

### FreeCAD Addon

| File          | Purpose                                                                                           |
| ------------- | ------------------------------------------------------------------------------------------------- |
| `package.xml` | FreeCAD addon metadata with per-component versioning. Updated automatically by release workflows. |

### GitHub

| File                       | Purpose                                                                         |
| -------------------------- | ------------------------------------------------------------------------------- |
| `.github/dependabot.yaml`  | Dependabot configuration for automated dependency updates.                      |
| `.github/workflows/*.yaml` | CI/CD workflows. See [GitHub Workflows](#github-actions-workflows) for details. |

---

## Justfile HEREDOC Syntax

**CRITICAL**: When writing heredocs in justfile recipes, the content must be indented to match the recipe body (4 spaces). Just parses non-indented lines as justfile syntax, which causes errors with Python code containing dots (e.g., `sys.path`).

**Important**: Just automatically strips leading indentation from heredoc content when executing. So while you write indented code in the justfile, the output will be properly unindented. Use `just --dry-run recipe-name` to verify the output.

### Correct Pattern

```just
# Recipe with heredoc - content MUST be indented with 4 spaces
my-recipe:
    #!/usr/bin/env bash
    cat > "$FILE" << EOF
    # Python code goes here - indented with 4 spaces
    import sys
    if project_path not in sys.path:
        sys.path.insert(0, project_path)
    EOF
```

When executed, just strips the 4-space indent, producing valid Python:

```python
# Python code goes here - indented with 4 spaces
import sys
if project_path not in sys.path:
    sys.path.insert(0, project_path)
```

### Incorrect Pattern (Will Fail)

```just
# This FAILS - just interprets sys.path as justfile syntax
my-recipe:
    #!/usr/bin/env bash
    cat > "$FILE" << EOF
import sys
if project_path not in sys.path:  # ERROR: Unknown start of token '.'
    sys.path.insert(0, project_path)
EOF
```

### Key Rules

1. **Indent heredoc content with 4 spaces**: Match the recipe body indentation
2. **Indent the EOF marker**: The closing `EOF` must also be indented
3. **Do NOT double-indent**: 4 spaces is correct; 8 spaces would produce indented output
4. **Variable expansion**: `${VAR}` works inside heredocs for bash variables
5. **Use `\\n` for newlines**: In heredoc strings that need literal `\n`, use `\\n`

See the recipes in `just/freecad.just` (e.g., `run-gui`, `run-headless`) for working examples.

---

## Justfile Working Directory in Modules

**CRITICAL**: When writing recipes in just modules (files in the `just/` directory), be aware that the working directory behavior can be surprising.

### The Problem

When you use `$(pwd)` in a module recipe, it returns the **module's directory** (e.g., `/path/to/project/just/`), NOT the project root. This causes path errors like:

```text
Exception while processing file: /path/to/project/just/src/freecad_mcp/...
```

The path incorrectly includes `just/` because `$(pwd)` returned the module directory.

### The Solution

Use `justfile_directory()` to get the project root. In modules, this function returns the directory of the **main justfile** (project root), not the module file's directory.

```just
# At the top of your module file (e.g., just/freecad.just)
project_root := justfile_directory()

# In recipes, use the variable instead of $(pwd)
my-recipe:
    #!/usr/bin/env bash
    PROJECT_DIR="{{project_root}}"  # Correct: /path/to/project
    # NOT: PROJECT_DIR="$(pwd)"     # Wrong: /path/to/project/just
```

### Key Points

1. **`$(pwd)` in modules**: Returns the module's directory (`just/`), not project root
1. **`justfile_directory()` in modules**: Returns the main justfile's directory (project root)
1. **Always define `project_root`**: Add `project_root := justfile_directory()` at the top of module files
1. **Use `{{project_root}}`**: Reference paths relative to the project root using this variable

### Example Fix

Before (broken):

```just
run-headless:
    #!/usr/bin/env bash
    PROJECT_DIR="$(pwd)"  # Returns /path/to/project/just/ - WRONG!
    SCRIPT="${PROJECT_DIR}/src/script.py"  # /path/to/project/just/src/script.py
```

After (correct):

```just
project_root := justfile_directory()

run-headless:
    #!/usr/bin/env bash
    PROJECT_DIR="{{project_root}}"  # Returns /path/to/project/ - CORRECT!
    SCRIPT="${PROJECT_DIR}/src/script.py"  # /path/to/project/src/script.py
```

---

## FreeCAD GUI vs Headless Mode

FreeCAD can run in two modes:

1. **GUI mode**: Full graphical interface with 3D view, accessed via `FreeCAD.app` or `freecad`
1. **Headless mode**: Console-only, no GUI, accessed via `FreeCADCmd` or `freecadcmd`

### FreeCAD Workbench Addon Loading (Critical)

**CRITICAL**: For FreeCAD **workbench addons**, `Init.py` does **NOT** run at FreeCAD startup. Only `InitGui.py` module-level code runs when FreeCAD GUI starts.

| File         | When It Runs                                       | Use Case                                 |
| ------------ | -------------------------------------------------- | ---------------------------------------- |
| `Init.py`    | Only when workbench is **selected** by user        | Workbench-specific initialization        |
| `InitGui.py` | **Module-level code** runs at FreeCAD GUI startup  | Auto-start features, status bar setup    |
| `InitGui.py` | `Initialize()` method runs when workbench selected | Toolbar/menu setup, command registration |

**Why this matters for auto-start:**

If you put auto-start logic in `Init.py`, it will only run when the user manually selects the workbench - NOT when FreeCAD starts. To auto-start the MCP bridge at FreeCAD startup:

1. Put auto-start code in `InitGui.py` **module-level code** (outside any class/method)
2. Use `QTimer.singleShot()` to defer execution until GUI is fully ready
3. The `Initialize()` method is too late - it only runs when workbench is selected

**Note on GuiWaiter vs QTimer.singleShot:**

- `GuiWaiter` works well when called from `Init.py` (workbench selection) or `startup_bridge.py`
- However, `GuiWaiter` has timing issues when used from `InitGui.py` module-level code
- For `InitGui.py`, use `QTimer.singleShot()` with a sufficient delay (e.g., 3 seconds)

**Example pattern in InitGui.py:**

```python
# Module-level code - runs at FreeCAD GUI startup
try:
    from PySide2 import QtCore
except ImportError:
    from PySide6 import QtCore

def _auto_start_bridge() -> None:
    """Auto-start bridge after GUI is fully ready."""
    # ... auto-start logic here ...

# Schedule auto-start after GUI initializes (3 second delay)
from preferences import get_auto_start
if get_auto_start():
    QtCore.QTimer.singleShot(3000, _auto_start_bridge)
```

**This is different from regular Python packages** where `__init__.py` runs on import. FreeCAD workbenches have special loading behavior.

### Detecting GUI Availability

**CRITICAL**: Always use `FreeCAD.GuiUp` to check if the GUI is available. **Never** check for Qt/PySide availability as a proxy for GUI mode.

```python
if FreeCAD.GuiUp:
    # GUI is available - can use FreeCADGui, ViewObjects, screenshots
    import FreeCADGui
    view = FreeCADGui.ActiveDocument.ActiveView
else:
    # Headless mode - no GUI features available
    pass
```

### MCP Bridge Startup Race Condition (Critical Bug Pattern)

**CRITICAL BUG PATTERN**: The MCP bridge must wait for `FreeCAD.GuiUp` to be `True` before starting in GUI mode. Starting the bridge while `FreeCAD.GuiUp` is `False` causes a race condition that leads to crashes.

**The Problem:**

When FreeCAD starts in GUI mode, there's a timing window where:

1. `InitGui.py` module-level code runs when `FreeCAD.GuiUp = False` (GUI not yet initialized)
2. Qt/PySide is available (can import successfully)
3. The bridge starts, sees `GuiUp = False`, and starts a background thread for queue processing
4. FreeCAD GUI finishes initializing (`GuiUp` becomes `True`)
5. Code execution still happens on the background thread
6. Qt operations from the background thread cause SIGABRT crashes

**Symptoms:**

- FreeCAD crashes with `SIGABRT` in `QCocoaWindow::createNSWindow` (macOS)
- Integration tests pass initial connection, then crash on first document operation
- Thread check shows `is_main_thread: False` with `thread_name: 'MCP-QueueProcessor'` even when `gui_up: True`

**The Fix:**

The approach depends on where the code runs:

**For `InitGui.py` module-level code:** Use `QTimer.singleShot()` with a delay:

```python
# WRONG - starts bridge immediately, GUI may not be ready
_auto_start_bridge()

# CORRECT - defer with sufficient delay for GUI to stabilize
QtCore.QTimer.singleShot(3000, _auto_start_bridge)
```

**For `startup_bridge.py` or `Init.py`:** Use `GuiWaiter` to poll for `FreeCAD.GuiUp`:

```python
# CORRECT - poll for GuiUp to be True, then start
from freecad_mcp_bridge.bridge_utils import GuiWaiter
_gui_waiter = GuiWaiter(callback=_start_bridge, log_prefix="Startup Bridge")
_gui_waiter.start()
```

**Note:** `GuiWaiter` has timing issues when used from `InitGui.py` module-level code due to how FreeCAD loads workbenches. Use `QTimer.singleShot()` for `InitGui.py` instead.

**Note:** These wait patterns are **only for GUI startup scenarios**. In headless mode (`freecadcmd`), the bridge starts directly without waiting because there is no Qt event loop to wait for. The four startup paths are:

1. **GUI already up** (`FreeCAD.GuiUp = True`): Start bridge immediately with Qt timer
2. **True headless** (`QCoreApplication` exists but is NOT a `QApplication`): Start directly with background thread
3. **GUI starting** (Qt available but no app yet, or `QApplication` initializing): Use GuiWaiter to wait for GUI
4. **No Qt available** (unusual state): Start directly

**IMPORTANT - Detecting True Headless vs Early GUI Startup:**

Simply checking `QApplication.instance() is None` is NOT sufficient because:

- In true headless mode (`freecadcmd`): `QCoreApplication` exists but NOT `QApplication`
- In early GUI startup: No application exists yet, but GUI will be available soon

The correct detection uses `isinstance` to distinguish these cases:

```python
# Check for QApplication first
qapp = QtWidgets.QApplication.instance()
if qapp is not None:
    # QApplication exists - GUI is available or starting
    _has_qapp = True
else:
    # No QApplication - check if QCoreApplication exists
    qcore_app = QtCore.QCoreApplication.instance()
    if qcore_app is not None and not isinstance(qcore_app, QtWidgets.QApplication):
        # QCoreApplication exists but is NOT a QApplication = true headless
        _is_true_headless = True
    # If no app at all, assume early GUI startup (will use GuiWaiter)
```

This logic is implemented in both `Init.py` and `startup_bridge.py` and MUST be kept in sync.

**Testing:**

An integration test in `tests/integration/test_thread_safety.py` verifies that:

- In GUI mode, code executes on the main thread (not `MCP-QueueProcessor`)
- The queue processor mode matches `FreeCAD.GuiUp` state
- Document creation works without crashing

**Key Lesson:** Never assume Qt availability means GUI is ready. Always check `FreeCAD.GuiUp` before doing operations that depend on the Qt event loop running on the main thread.

### Keeping Startup Scripts in Sync (Critical)

**CRITICAL**: The MCP bridge can be started from THREE different entry points. They must use compatible detection logic:

| File                                               | Purpose                                          |
| -------------------------------------------------- | ------------------------------------------------ |
| `freecad/RobustMCPBridge/init_gui.py`              | Auto-start at FreeCAD GUI startup (if enabled)   |
| `freecad/RobustMCPBridge/__init__.py`              | Fallback auto-start when workbench selected      |
| `freecad/.../freecad_mcp_bridge/startup_bridge.py` | Manual start via `just freecad::run-gui`         |

**When modifying startup logic in one file, you MUST update the others to match.**

All files must have compatible logic for:

1. **QApplication detection** - Use `QApplication.instance()` to detect GUI vs headless
2. **GuiWaiter usage** - Wait for `GuiUp` before starting in GUI mode
3. **Headless detection** - Start directly when no QApplication exists
4. **Diagnostic logging** - Log `GuiUp`, `QtCore`, and `QApp` state
5. **Already running check** - Skip start if bridge already running

**Why these files exist:**

- `init_gui.py` module-level code runs at FreeCAD GUI startup (primary auto-start location)
- `__init__.py` runs when workbench is selected (fallback if init_gui didn't auto-start)
- `startup_bridge.py` is passed as a command-line argument for `just freecad::run-gui`
- All check if a bridge is already running to avoid conflicts

**Test command to verify both work:**

```bash
# Test headless mode (uses blocking_bridge.py)
just testing::integration-headless-release

# Test GUI mode (uses startup_bridge.py, InitGui.py auto-start may also be active)
just testing::integration-gui-release
```

### Why NOT to Check for PySide/Qt

**WRONG** - Do not use Qt availability to detect GUI mode:

```python
# WRONG - PySide is available even in headless mode!
try:
    from PySide6 import QtCore
    # This will be True even in headless mode
    is_gui_mode = True
except ImportError:
    is_gui_mode = False
```

**RIGHT** - Use `FreeCAD.GuiUp`:

```python
# CORRECT - GuiUp is False in headless mode
is_gui_mode = FreeCAD.GuiUp
```

**Why this matters**: FreeCAD bundles PySide6 even in headless mode (`freecadcmd`), but without a running Qt event loop:

- Qt timers (`QTimer`) will never fire
- GUI widgets cannot be created or displayed
- Any code relying on Qt events will hang indefinitely

This caused a bug where the MCP bridge queue processor used a `QTimer` in headless mode, resulting in `execute` calls hanging forever because the timer callbacks never ran.

### GUI-Only Features

These features **only work in GUI mode** and will fail or crash in headless mode:

| Feature             | Requires GUI | Alternative in Headless |
| ------------------- | ------------ | ----------------------- |
| `FreeCADGui` module | Yes          | Not available           |
| `obj.ViewObject`    | Yes          | Returns `None`          |
| Screenshots         | Yes          | Not available           |
| Camera/view control | Yes          | Not available           |
| Display mode/color  | Yes          | Not available           |
| Object visibility   | Yes          | Not available           |
| Zoom in/out         | Yes          | Not available           |

### Implementing GUI-Safe Tools

**CRITICAL**: All MCP tools that use GUI features must check `FreeCAD.GuiUp` and return a structured error response instead of crashing.

#### Pattern for GUI-Safe Tools

```python
@mcp.tool()
async def set_object_visibility(object_name: str, visible: bool) -> dict[str, Any]:
    """Set object visibility. Requires GUI mode."""
    bridge = await get_bridge()

    code = f"""
if not FreeCAD.GuiUp:
    _result_ = {{"success": False, "error": "GUI not available - visibility cannot be set in headless mode"}}
else:
    doc = FreeCAD.ActiveDocument
    obj = doc.getObject({object_name!r})
    if obj is None:
        _result_ = {{"success": False, "error": f"Object not found: {object_name!r}"}}
    elif hasattr(obj, "ViewObject") and obj.ViewObject:
        obj.ViewObject.Visibility = {visible}
        _result_ = {{"success": True, "visible": {visible}}}
    else:
        _result_ = {{"success": False, "error": "Object has no ViewObject"}}
"""
    result = await bridge.execute_python(code)
    if result.success and result.result:
        return result.result
    return {{"success": False, "error": result.error_traceback or "Operation failed"}}
```

#### Key Requirements

1. **Check `FreeCAD.GuiUp` first**: Before accessing any GUI features
1. **Return structured errors**: Use `{"success": False, "error": "..."}` format
1. **Never raise exceptions**: Return error dicts instead of raising `ValueError`
1. **Document GUI requirement**: Add "Requires GUI mode" to docstrings

### Tools Updated for GUI Safety

The following tools in `src/freecad_mcp/tools/view.py` check `FreeCAD.GuiUp`:

- `set_object_visibility`
- `set_display_mode`
- `set_object_color`
- `zoom_in` / `zoom_out`
- `set_camera_position`
- `get_screenshot`

### Implementing Transaction Support for Undo/Redo

**CRITICAL**: All MCP tools that modify the FreeCAD document MUST wrap their operations in transactions to enable undo/redo functionality.

FreeCAD transactions allow users to undo operations if something goes wrong. Without transaction wrapping, changes cannot be undone and users may lose work.

#### Transaction Pattern

```python
# Wrap modifying operations in a transaction
doc.openTransaction("Operation Name")
try:
    # ... perform modifications ...
    obj = doc.addObject("Part::Box", "MyBox")
    obj.Length = 10
    doc.recompute()
    doc.commitTransaction()
except Exception as _txn_err:
    doc.abortTransaction()
    raise _txn_err
```

#### Key Requirements

1. **Wrap all modifying operations**: Any code that creates, modifies, or deletes objects
2. **Use descriptive transaction names**: The name appears in FreeCAD's Edit > Undo menu
3. **Commit on success**: Call `doc.commitTransaction()` after successful modifications
4. **Abort on failure**: Call `doc.abortTransaction()` in the exception handler to rollback changes
5. **Recompute before commit**: Call `doc.recompute()` to update dependent features

#### Helper Function

The project provides a utility function in `src/freecad_mcp/tools/utils.py`:

```python
from freecad_mcp.tools.utils import wrap_with_transaction

# Wrap code string with transaction handling
code = wrap_with_transaction(
    code="obj = doc.addObject('Part::Box', 'MyBox')\n_result_ = {'name': obj.Name}",
    transaction_name="Create Box",
    doc_expr="FreeCAD.ActiveDocument",
)
```

#### Tools Requiring Transactions

The following categories of tools MUST use transaction wrapping:

- **Object creation**: `create_box`, `create_cylinder`, `create_object`, etc.
- **Object modification**: `edit_object`, `set_placement`, `rotate_object`, `scale_object`
- **Object deletion**: `delete_object`
- **Boolean operations**: `boolean_operation`, `copy_object`, `mirror_object`
- **PartDesign operations**: `pad_sketch`, `pocket_sketch`, `fillet_edges`, etc.
- **Sketch operations**: `add_sketch_rectangle`, `add_sketch_circle`, etc.
- **Import operations**: `insert_part_from_library`

#### Tools NOT Requiring Transactions

- **Read-only operations**: `list_objects`, `inspect_object`, `get_screenshot`
- **Export operations**: `export_step`, `export_stl` (writes to external files, not the document)
- **View operations**: `set_view_angle`, `zoom_in`, `fit_all` (don't modify document model)
- **Undo/redo tools**: `undo`, `redo` (manage transactions themselves)

### Running FreeCAD in Each Mode

```bash
# GUI mode - with MCP bridge auto-started
just freecad::run-gui

# Headless mode - console only
just freecad::run-headless

# Or manually:
# GUI: /Applications/FreeCAD.app (macOS) or freecad (Linux)
# Headless: FreeCADCmd or freecadcmd
```

### FreeCAD Plugin Import Restrictions

**CRITICAL**: Code running inside FreeCAD's Python environment cannot import packages that aren't available in FreeCAD's bundled Python (like `mcp`, `pydantic`, etc.).

The `blocking_bridge.py` script in the workbench addon imports the plugin directly from the module file to avoid triggering the `mcp` import:

```python
# CORRECT - import directly from the module file in the same directory
script_dir = str(Path(__file__).resolve().parent)
sys.path.insert(0, script_dir)
from server import FreecadMCPPlugin  # Direct module import
```

This pattern is required because:

1. The MCP SDK is installed in the project's virtualenv, not in FreeCAD's Python
1. Python processes parent package `__init__.py` files when importing nested modules
1. Importing from `freecad_mcp/__init__.py` would trigger MCP SDK imports that don't exist in FreeCAD

---

## Common Issues and Solutions

### Pre-commit Failing

```bash
# Update pre-commit hooks
uv run pre-commit autoupdate

# Clear pre-commit cache
uv run pre-commit clean

# Run specific hook for debugging
uv run pre-commit run <hook-id> --all-files
```

### Type Checking Errors

- Ensure all function parameters and return types have type hints
- Use `typing` module for complex types
- Add `# type: ignore[error-code]` only as last resort with explanation

### Test Failures

- Read the full error message and traceback
- Check if fixtures are properly defined
- Verify test isolation (no shared state between tests)

---

## Pre-commit Hook Requirements

This section documents specific requirements for each pre-commit hook to avoid common issues.

### Ruff Linting

- **UP038**: Use modern union syntax for isinstance: `isinstance(obj, str | int)` NOT `isinstance(obj, (str, int))`
- **Line length**: 88 characters max (but `E501` is ignored for embedded code strings)
- **Import sorting**: Ruff handles this automatically with `ruff --fix`

### MyPy Type Checking

This project uses relaxed mypy settings because FastMCP lacks proper type stubs.

- **Type ignores**: When needed, use specific error codes: `# type: ignore[attr-defined]`
- **FastMCP methods**: `on_startup`, `on_shutdown`, and some `run()` args need type ignores
- **XML-RPC**: `register_function` has overly restrictive types, use `# type: ignore[arg-type]`
- **Lambda captures**: If mypy complains about union types in lambdas, assign to a local variable first

### Codespell

- **Technical terms**: Add legitimate technical terms to `.codespell-ignore-words.txt`
- **FreeCAD API**: "vertexes" is valid FreeCAD terminology (not "vertices")
- **Tool names**: Add tool/library names that look like typos

### Markdownlint (MD035)

- **Horizontal rules**: Must use `---` format (3 dashes)

### Markdownlint (MD060) - Table Formatting

- **Table column style**: All Markdown tables must use the "padded/aligned" style
- Every row in a table must have the same total character width
- Column separators (`|`) must align vertically across all rows
- The separator row dashes must match the column width set by the widest content

**Example - Correct (aligned):**

```markdown
| File             | Purpose                                      |
| ---------------- | -------------------------------------------- |
| `.mise.toml`     | Tool version management configuration.       |
| `pyproject.toml` | Python project configuration and deps.       |
```

**Example - Incorrect (misaligned):**

```markdown
| File | Purpose |
|------|---------|
| `.mise.toml` | Tool version management configuration. |
| `pyproject.toml` | Python project configuration and deps. |
```

When editing tables, ensure all columns align by adding padding spaces before the closing `|`.

### Bandit Security

These checks are intentionally skipped in `pyproject.toml`:

- **B101**: Asserts allowed (needed for validation)
- **B102**: `exec()` required for FreeCAD Python execution
- **B110**: `try-except-pass` used for optional cleanup operations
- **B411**: XML-RPC required for FreeCAD compatibility

### detect-secrets

- **False positives**: Add `# pragma: allowlist secret` comment to lines with false positives
- **Baseline updates**: Run `just quality::scan-audit` to update `.secrets.baseline`

### no-commit-to-branch

- This hook fails when on `main` or `master` branch - this is expected behavior
- Always work on feature branches for actual commits

### check-json5 (JSONC Support)

- VS Code configuration files (`.vscode/*.json`) use JSONC format (JSON with Comments)
- These files are excluded from the strict `check-json` hook
- The `check-json5` hook validates these files instead, allowing `//` comments

---

## GitHub Actions Workflows

This project uses component-specific release workflows along with CI/CD pipelines.

### CI Workflows

| Workflow          | Trigger                       | Purpose                                                   |
| ----------------- | ----------------------------- | --------------------------------------------------------- |
| `test.yaml`       | Push, PR                      | Runs unit tests and integration tests on Ubuntu and macOS |
| `test-gui.yaml`   | Push, PR                      | Runs GUI integration tests using Docker + Xvfb            |
| `pre-commit.yaml` | Push, PR                      | Runs all pre-commit hooks for code quality                |
| `docker.yaml`     | Push, PR                      | Builds Docker image to verify Dockerfile works            |
| `codeql.yaml`     | Push, PR, scheduled           | GitHub CodeQL security analysis                           |
| `docs.yaml`       | Push to main, MCP server tags | Deploys versioned documentation to GitHub Pages           |

**IMPORTANT - test.yaml Workflow**: The `test.yaml` workflow **automatically starts FreeCAD** in headless mode for integration tests. It:

1. Installs FreeCAD via the custom `setup-freecad` action
2. Starts FreeCAD headless with the MCP bridge (`blocking_bridge.py`)
3. Waits for the bridge to be ready (pings the XML-RPC endpoint)
4. Runs integration tests
5. Stops FreeCAD and shows logs on failure

You do NOT need to manually start FreeCAD when the CI workflow runs. The workflow handles the full lifecycle automatically.

**IMPORTANT - test-gui.yaml Workflow**: The `test-gui.yaml` workflow runs **GUI integration tests** using Docker and Xvfb. It:

1. Builds the `tests/ci-test/Dockerfile.gui-test` image (with caching)
2. Starts Xvfb (virtual framebuffer) and openbox (window manager)
3. Starts FreeCAD GUI mode with the MCP bridge
4. Uses xdotool to send synthetic mouse/keyboard events (helps GUI initialization)
5. Verifies `FreeCAD.GuiUp == True` before running tests
6. Runs `tests/integration/test_gui_mode.py` for GUI-specific tests
7. Collects artifacts (screenshots, logs, test results) for debugging

This workflow tests GUI-only features like screenshots, visibility, display modes, and camera operations that cannot be tested in headless mode.

### Release Workflows

| Workflow                     | Trigger                        | Purpose                                                |
| ---------------------------- | ------------------------------ | ------------------------------------------------------ |
| `mcp-server-release.yaml`    | Tag: `robust-mcp-server-v*`    | Builds and publishes MCP server to PyPI and Docker Hub |
| `mcp-workbench-release.yaml` | Tag: `robust-mcp-workbench-v*` | Creates GitHub Release with workbench addon archive    |

### Release Workflow Features

**MCP Server Release** (`mcp-server-release.yaml`):

- Validates SemVer tag format
- Builds Python wheel and sdist
- Tests installation on Ubuntu and macOS
- Publishes to PyPI (stable) or TestPyPI (alpha, beta, rc)
- Builds multi-arch Docker image (amd64 + arm64)
- Pushes to Docker Hub with version tags
- Creates GitHub Release with artifacts and changelog

**Workbench/Macro Releases**:

- Validates tag format
- Updates version in source files automatically
- Updates `package.xml` per-component version
- Creates tar.gz and zip archives
- Extracts changelog section for release notes
- Creates GitHub Release with archives

---

## Release Process

This project uses **component-specific versioning**. Each component has its own git tag and release workflow:

| Component         | Tag Format                    | Releases To                                |
| ----------------- | ----------------------------- | ------------------------------------------ |
| MCP Server        | `robust-mcp-server-vX.Y.Z`    | PyPI/TestPyPI*, Docker Hub, GitHub Release |
| Robust MCP Bridge | `robust-mcp-workbench-vX.Y.Z` | GitHub Release (archive)                   |

*Stable releases (`X.Y.Z`) publish to PyPI; non-stable releases (alpha, beta, rc) publish to TestPyPI only.

### Release Notes Management

Each component has its own `RELEASE_NOTES.md` file. Release workflows automatically extract the relevant section for GitHub Releases.

| Component         | Release Notes File                             |
| ----------------- | ---------------------------------------------- |
| MCP Server        | `src/freecad_mcp/RELEASE_NOTES.md`             |
| Robust MCP Bridge | `freecad/RobustMCPBridge/RELEASE_NOTES.md`     |

**Before releasing a component:**

1. **Draft release notes** from git commits since the last release:

   ```bash
   just release::draft-notes mcp-server
   just release::draft-notes workbench
   ```

2. **Edit the component's RELEASE_NOTES.md** file, adding a new version section at the top:

   ```markdown
   ## Version X.Y.Z (YYYY-MM-DD)

   Release notes for changes between vA.B.C and vX.Y.Z.

   ### Added

   - New feature description

   ### Changed

   - Change description

   ### Fixed

   - Bug fix description
   ```

3. The release workflow automatically extracts the version section for GitHub Releases.

### Creating a Release

**Step 1: Run release tests** to ensure everything passes:

```bash
just testing::release-test
```

This runs unit tests, integration tests (headless + GUI), Docker tests, and just command tests. All must pass before proceeding.

**Step 2: Update release notes** for each component you're releasing:

```bash
# Generate draft notes from git commits
just release::draft-notes mcp-server

# Edit the RELEASE_NOTES.md file (add version section at top)
# See "Release Notes Management" above for format
```

**Step 3: Bump versions** (for workbench only - MCP server auto-bumps from tag):

```bash
just release::bump-workbench 1.0.0
```

**Step 4: Commit and push** your RELEASE_NOTES.md and version bump changes.

**Step 5: Create release tags** (this triggers the release workflows):

```bash
# Release the MCP server (triggers PyPI, Docker, GitHub release)
just release::tag-mcp-server 1.0.0

# Release the Robust MCP Bridge workbench
just release::tag-workbench 1.0.0
```

**Utility commands:**

```bash
# Check what has unreleased changes
just release::status

# Preview changes since last release
just release::changes-since mcp-server

# View release tags
just release::list-tags
just release::latest-versions

# Extract changelog for a version (for testing)
just release::extract-changelog mcp-server 1.0.0
```

### Version Format

All versions follow SemVer 2.0:

- `X.Y.Z` - Stable release (PyPI only)
- `X.Y.Z-alpha` or `X.Y.Z-alpha.N` - Alpha (TestPyPI only)
- `X.Y.Z-beta` or `X.Y.Z-beta.N` - Beta (TestPyPI only)
- `X.Y.Z-rc.N` - Release candidate (TestPyPI only)

### What Happens on Release

**MCP Server Release:**

1. Validates tag format
2. Builds Python wheel and sdist
3. Tests installation on Ubuntu and macOS
4. Publishes to PyPI (or TestPyPI for alpha, beta, rc)
5. Builds multi-arch Docker image
6. Pushes to Docker Hub
7. Creates GitHub release with artifacts

**Workbench/Macro Release:**

1. Validates tag format
2. Updates version in source files
3. Updates version in package.xml
4. Creates archive (tar.gz + zip)
5. Creates GitHub release with archives

### Package.xml Versioning

The `package.xml` file contains metadata for the FreeCAD addon:

```xml
<content>
    <workbench>
        <name>Robust MCP Bridge</name>
        <version>1.0.0</version>
        ...
    </workbench>
</content>
```

The release workflow automatically updates the version when the workbench is released.

---

## Release Notes Maintenance

Each component has its own `RELEASE_NOTES.md` file that is updated before releases. Release workflows automatically extract the relevant version section for GitHub Releases.

**When preparing a release:**

1. Use `just release::draft-notes <component>` to generate draft notes from commits
2. Edit the component's `RELEASE_NOTES.md` file, adding a new version section at the top
3. Follow the format: `## Version X.Y.Z (YYYY-MM-DD)` with `### Added`, `### Changed`, `### Fixed` sections

**Release notes files:**

| Component         | File                                           |
| ----------------- | ---------------------------------------------- |
| MCP Server        | `src/freecad_mcp/RELEASE_NOTES.md`             |
| Robust MCP Bridge | `freecad/RobustMCPBridge/RELEASE_NOTES.md`     |

---

## FreeCAD Robust MCP Tools Reference

When Claude Code is connected to the FreeCAD Robust MCP server, the following tools are available for interacting with FreeCAD. Use these tools to control FreeCAD, create/modify objects, and debug issues.

### Discovering Capabilities at Runtime

The MCP server provides a `freecad://capabilities` resource that returns a complete JSON catalog of all available tools, resources, and prompts. This is the authoritative source for what's available.

### Updating Documentation When Tools Change

**CRITICAL**: When adding, modifying, or removing MCP tools, you MUST update ALL of these files:

| File                                   | What to Update                                    |
| -------------------------------------- | ------------------------------------------------- |
| `src/freecad_mcp/resources/freecad.py` | `freecad://capabilities` resource (tool catalog)  |
| `src/freecad_mcp/prompts/freecad.py`   | AI guidance prompts (tool references, workflows)  |
| `docs/guide/tools.md`                  | User-facing tool reference (categories, tables)   |
| `CLAUDE.md` (this file)                | Tools Reference section (if adding new category)  |

**What to update in each file:**

1. **`freecad://capabilities` resource** (`src/freecad_mcp/resources/freecad.py`):
   - Add tool to the appropriate category in `resource_capabilities()`
   - Include `name`, `description`, and `key_params` for each tool
   - Add new categories if the tool doesn't fit existing ones

2. **Prompts** (`src/freecad_mcp/prompts/freecad.py`):
   - Update relevant guidance sections (partdesign, sketching, validation, etc.)
   - Add workflow examples if the tool introduces new patterns
   - Update quick reference tables in `freecad_startup` prompt

3. **Tools documentation** (`docs/guide/tools.md`):
   - Update the tool count in the header
   - Add tool to appropriate category table
   - Create new section if adding a new category
   - Update the category summary table

4. **CLAUDE.md** (this file):
   - Only update if adding a completely new tool category
   - The Tools Reference section serves as quick reference for AI agents

**Note on transaction support**: All tool operations are wrapped in FreeCAD transactions for undo support. Document this in the `transaction_safety` section of capabilities and in relevant prompts.

### Execution & Debugging Tools

| Tool                         | Description                                                                                                                                           |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `execute_python`             | Execute arbitrary Python code in FreeCAD's context. Use `_result_ = value` to return data. Has access to FreeCAD, App, Part, and all FreeCAD modules. |
| `get_console_output`         | **Get recent FreeCAD console output** - useful for debugging macros and seeing error messages. Returns up to N lines of console history.              |
| `get_console_log`            | Alternative console log access with different formatting.                                                                                             |
| `get_freecad_version`        | Get FreeCAD version, build date, Python version, and GUI availability.                                                                                |
| `get_connection_status`      | Check MCP bridge connection status, mode, and latency.                                                                                                |
| `get_mcp_server_environment` | Get MCP server environment info (OS, hostname, Docker detection). Useful for verifying container vs host.                                             |

### Document Management Tools

| Tool                  | Description                                          |
| --------------------- | ---------------------------------------------------- |
| `list_documents`      | List all open FreeCAD documents.                     |
| `get_active_document` | Get information about the currently active document. |
| `create_document`     | Create a new FreeCAD document.                       |
| `open_document`       | Open an existing .FCStd file.                        |
| `save_document`       | Save a document to disk.                             |
| `close_document`      | Close a document.                                    |
| `recompute_document`  | Force recomputation of document features.            |

### Object Creation Tools (Part Workbench)

| Tool                      | Description                                                     |
| ------------------------- | --------------------------------------------------------------- |
| `list_objects`            | List all objects in a document with their types and properties. |
| `inspect_object`          | Get detailed information about a specific object.               |
| `create_object`           | Create a generic FreeCAD object.                                |
| `create_box`              | Create a Part::Box primitive.                                   |
| `create_cylinder`         | Create a Part::Cylinder primitive.                              |
| `create_sphere`           | Create a Part::Sphere primitive.                                |
| `create_cone`             | Create a Part::Cone primitive.                                  |
| `create_torus`            | Create a Part::Torus primitive.                                 |
| `create_wedge`            | Create a Part::Wedge primitive.                                 |
| `create_helix`            | Create a Part::Helix primitive.                                 |
| `create_line`             | Create a Part::Line between two points.                         |
| `create_plane`            | Create a Part::Plane surface.                                   |
| `create_ellipse`          | Create a Part::Ellipse curve.                                   |
| `create_prism`            | Create a Part::Prism (extruded polygon).                        |
| `create_regular_polygon`  | Create a Part::RegularPolygon (flat polygon face).              |

### Part Shape Operations

| Tool            | Description                                                       |
| --------------- | ----------------------------------------------------------------- |
| `shell_object`  | Create a hollow shell from a solid (remove faces, add thickness). |
| `offset_3d`     | Create an offset copy of a shape (expand/shrink).                 |
| `slice_shape`   | Slice a shape with a plane, returning cross-section edges.        |
| `section_shape` | Create a section (intersection) of a shape with a standard plane. |

### Part Compound Operations

| Tool               | Description                                           |
| ------------------ | ----------------------------------------------------- |
| `make_compound`    | Combine multiple objects into a single compound.      |
| `explode_compound` | Separate a compound into individual shape objects.    |
| `fuse_all`         | Fuse (union) multiple objects into one solid.         |
| `common_all`       | Create intersection (common volume) of all objects.   |

### Part Wire and Face Operations

| Tool             | Description                                            |
| ---------------- | ------------------------------------------------------ |
| `make_wire`      | Create a wire (connected edges) from a list of points. |
| `make_face`      | Create a face from a closed wire or edge object.       |
| `extrude_shape`  | Extrude a 2D shape along a direction vector.           |
| `revolve_shape`  | Revolve a 2D shape around an axis.                     |

### Part Loft and Sweep

| Tool         | Description                                           |
| ------------ | ----------------------------------------------------- |
| `part_loft`  | Create a loft (skin) through multiple profile shapes. |
| `part_sweep` | Sweep a profile along a spine path.                   |

### Object Manipulation Tools

| Tool                | Description                                     |
| ------------------- | ----------------------------------------------- |
| `edit_object`       | Modify object properties.                       |
| `delete_object`     | Delete an object from the document.             |
| `boolean_operation` | Perform union, cut, or intersection operations. |
| `set_placement`     | Set object position and rotation.               |
| `scale_object`      | Scale an object by a factor.                    |
| `rotate_object`     | Rotate an object around an axis.                |
| `copy_object`       | Create a copy of an object.                     |
| `mirror_object`     | Mirror an object across a plane.                |

### Selection Tools

| Tool              | Description                     |
| ----------------- | ------------------------------- |
| `get_selection`   | Get currently selected objects. |
| `set_selection`   | Select specific objects.        |
| `clear_selection` | Clear the current selection.    |

### PartDesign Tools (Parametric Modeling)

| Tool                     | Description                                       |
| ------------------------ | ------------------------------------------------- |
| `create_partdesign_body` | Create a new PartDesign::Body container.          |
| `create_sketch`          | Create a sketch attached to a plane or face.      |
| `pad_sketch`             | Extrude a sketch (additive).                      |
| `pocket_sketch`          | Cut into solid using a sketch (subtractive).      |
| `revolution_sketch`      | Revolve a sketch around an axis (additive).       |
| `groove_sketch`          | Cut by revolving a sketch (subtractive).          |
| `loft_sketches`          | Create a loft between multiple sketches.          |
| `sweep_sketch`           | Sweep a sketch along a path.                      |
| `subtractive_loft`       | Cut material with a loft through sketches.        |
| `subtractive_pipe`       | Cut material by sweeping a sketch along a path.   |
| `create_hole`            | Create parametric holes from sketch points.       |
| `fillet_edges`           | Add fillets (rounded edges).                      |
| `chamfer_edges`          | Add chamfers (beveled edges).                     |
| `draft_feature`          | Add draft angle to faces (for mold release).      |
| `thickness_feature`      | Shell a solid by removing faces and adding walls. |

### PartDesign Datum Features

| Tool                  | Description                                             |
| --------------------- | ------------------------------------------------------- |
| `create_datum_plane`  | Create a reference plane offset from a base plane.      |
| `create_datum_line`   | Create a reference line/axis in the body.               |
| `create_datum_point`  | Create a reference point at a specific position.        |

### Pattern Tools

| Tool               | Description                                |
| ------------------ | ------------------------------------------ |
| `linear_pattern`   | Create linear pattern of features.         |
| `polar_pattern`    | Create polar/circular pattern of features. |
| `mirrored_feature` | Mirror a feature across a plane.           |

### Sketcher Geometry Tools

| Tool                   | Description                                       |
| ---------------------- | ------------------------------------------------- |
| `add_sketch_line`      | Add a line to a sketch.                           |
| `add_sketch_rectangle` | Add a rectangle to a sketch.                      |
| `add_sketch_circle`    | Add a circle to a sketch.                         |
| `add_sketch_arc`       | Add an arc to a sketch.                           |
| `add_sketch_point`     | Add a point to a sketch (for hole placement).     |
| `add_sketch_ellipse`   | Add an ellipse to a sketch.                       |
| `add_sketch_polygon`   | Add a regular polygon to a sketch.                |
| `add_sketch_slot`      | Add a slot (rounded rectangle) to a sketch.       |
| `add_sketch_bspline`   | Add a B-spline curve through control points.      |

### Sketcher Constraint Tools

| Tool                       | Description                                         |
| -------------------------- | --------------------------------------------------- |
| `add_sketch_constraint`    | Add any constraint type (general interface).        |
| `constrain_horizontal`     | Constrain a line to be horizontal.                  |
| `constrain_vertical`       | Constrain a line to be vertical.                    |
| `constrain_coincident`     | Make two points coincident (same location).         |
| `constrain_parallel`       | Constrain two lines to be parallel.                 |
| `constrain_perpendicular`  | Constrain two lines to be perpendicular.            |
| `constrain_tangent`        | Constrain two curves to be tangent.                 |
| `constrain_equal`          | Constrain two elements to have equal length/radius. |
| `constrain_distance`       | Set distance between two elements.                  |
| `constrain_distance_x`     | Set horizontal distance from a point.               |
| `constrain_distance_y`     | Set vertical distance from a point.                 |
| `constrain_radius`         | Set the radius of a circle or arc.                  |
| `constrain_angle`          | Set the angle of a line or between two lines.       |
| `constrain_fix`            | Fix a point or geometry at its current position.    |

### Sketcher Operations

| Tool                       | Description                                              |
| -------------------------- | -------------------------------------------------------- |
| `add_external_geometry`    | Reference external geometry (edges/faces) in sketch.     |
| `delete_sketch_geometry`   | Delete a geometry element from a sketch.                 |
| `delete_sketch_constraint` | Delete a constraint from a sketch.                       |
| `get_sketch_info`          | Get detailed info about sketch geometry and constraints. |
| `toggle_construction`      | Toggle geometry between normal and construction mode.    |

### Spreadsheet Tools (Parametric Design)

| Tool                         | Description                                              |
| ---------------------------- | -------------------------------------------------------- |
| `spreadsheet_create`         | Create a new Spreadsheet object for parametric design.   |
| `spreadsheet_set_cell`       | Set cell value (number, string, or formula like =A1*2).  |
| `spreadsheet_get_cell`       | Get cell value and computed result.                      |
| `spreadsheet_set_alias`      | Set alias for cell (e.g., "Length") for expressions.     |
| `spreadsheet_get_aliases`    | Get all aliases defined in a spreadsheet.                |
| `spreadsheet_clear_cell`     | Clear a cell content and alias.                          |
| `spreadsheet_bind_property`  | Bind object property to spreadsheet cell via expression. |
| `spreadsheet_get_cell_range` | Get values from a range of cells.                        |
| `spreadsheet_import_csv`     | Import data from CSV file into spreadsheet.              |
| `spreadsheet_export_csv`     | Export spreadsheet data to CSV file.                     |

### Draft Tools (3D Text/ShapeString)

| Tool                          | Description                                           |
| ----------------------------- | ----------------------------------------------------- |
| `draft_shapestring`           | Create 3D text geometry from a string and font.       |
| `draft_list_fonts`            | List available system fonts for ShapeString.          |
| `draft_shapestring_to_sketch` | Convert ShapeString to Sketch for PartDesign use.     |
| `draft_shapestring_to_face`   | Convert ShapeString to Face for boolean operations.   |
| `draft_text_on_surface`       | Emboss or engrave text directly on a surface.         |
| `draft_extrude_shapestring`   | Extrude ShapeString to create 3D solid text.          |

### View & GUI Tools (Require GUI Mode)

| Tool                    | Description                                                 |
| ----------------------- | ----------------------------------------------------------- |
| `get_screenshot`        | Capture a screenshot of the 3D view. **Requires GUI mode.** |
| `set_view_angle`        | Set camera to standard views (front, top, isometric, etc.). |
| `fit_all`               | Zoom to fit all objects in view.                            |
| `zoom_in` / `zoom_out`  | Adjust zoom level.                                          |
| `set_camera_position`   | Set exact camera position and orientation.                  |
| `set_object_visibility` | Show/hide objects. **Requires GUI mode.**                   |
| `set_display_mode`      | Set display mode (wireframe, shaded, etc.).                 |
| `set_object_color`      | Change object colors. **Requires GUI mode.**                |
| `list_workbenches`      | List available FreeCAD workbenches.                         |
| `activate_workbench`    | Switch to a different workbench.                            |

### Undo/Redo Tools

| Tool                   | Description                         |
| ---------------------- | ----------------------------------- |
| `undo`                 | Undo the last operation.            |
| `redo`                 | Redo an undone operation.           |
| `get_undo_redo_status` | Get available undo/redo operations. |

### Validation Tools

| Tool                | Description                                                                           |
| ------------------- | ------------------------------------------------------------------------------------- |
| `validate_object`   | Check object health (shape validity, error states, recompute status).                 |
| `validate_document` | Check health of all objects in document, return summary of invalid/error objects.     |
| `undo_if_invalid`   | Check document health and automatically undo last operation if invalid objects exist. |
| `safe_execute`      | Execute Python code with automatic validation and rollback on failure.                |

### Export/Import Tools

| Tool          | Description                                        |
| ------------- | -------------------------------------------------- |
| `export_step` | Export objects to STEP format.                     |
| `export_stl`  | Export objects to STL format (for 3D printing).    |
| `export_3mf`  | Export objects to 3MF format (modern 3D printing). |
| `export_obj`  | Export objects to OBJ format.                      |
| `export_iges` | Export objects to IGES format.                     |
| `import_step` | Import STEP files.                                 |
| `import_stl`  | Import STL files.                                  |

### Macro Tools

| Tool                         | Description                     |
| ---------------------------- | ------------------------------- |
| `list_macros`                | List available FreeCAD macros.  |
| `run_macro`                  | Execute a macro by name.        |
| `create_macro`               | Create a new macro file.        |
| `read_macro`                 | Read macro source code.         |
| `delete_macro`               | Delete a macro file.            |
| `create_macro_from_template` | Create a macro from a template. |

### Parts Library Tools

| Tool                       | Description                                      |
| -------------------------- | ------------------------------------------------ |
| `list_parts_library`       | List available parts in FreeCAD's parts library. |
| `insert_part_from_library` | Insert a part from the library.                  |

### Example: Debugging a Macro

To debug issues with a macro running in FreeCAD:

```python
# Get recent console output to see errors
console_output = await get_console_output(lines=50)

# Or execute Python to check state
result = await execute_python('''
doc = FreeCAD.ActiveDocument
if doc:
    _result_ = {
        "doc_name": doc.Name,
        "objects": [obj.Name for obj in doc.Objects],
        "errors": [obj.Name for obj in doc.Objects if hasattr(obj, 'isValid') and not obj.isValid()]
    }
else:
    _result_ = {"error": "No active document"}
''')
```

### Example: Creating a Simple Part

```python
# Create a document
await create_document(name="MyPart")

# Create a PartDesign body
await create_partdesign_body(name="Body")

# Create a sketch on the XY plane
await create_sketch(body_name="Body", plane="XY_Plane", sketch_name="Sketch")

# Add a rectangle to the sketch
await add_sketch_rectangle(sketch_name="Sketch", x=-10, y=-10, width=20, height=20)

# Extrude the sketch
await pad_sketch(body_name="Body", sketch_name="Sketch", length=15)

# Add fillets
await fillet_edges(body_name="Body", edges=["Edge1", "Edge2"], radius=2)

# Export to STL
await export_stl(object_names=["Body"], file_path="/tmp/mypart.stl")
```

---

## Summary Checklist

When working on this project, ALWAYS:

- [ ] Use `mise` for tool management
- [ ] Use `just` commands for workflows
- [ ] Write comprehensive docstrings (Google-style)
- [ ] Write tests for all new code
- [ ] Run `just all` before finishing - everything must pass
- [ ] Use latest stable library versions
- [ ] Follow security best practices
- [ ] Update component `RELEASE_NOTES.md` files before releases
