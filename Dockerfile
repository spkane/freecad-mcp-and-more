# syntax=docker/dockerfile:1.7

# FreeCAD Robust MCP Server Dockerfile
# Multi-stage build with BuildKit optimizations for multi-arch support
#
# Uses Alpine Linux for minimal image size and reduced CVE surface.
# Alpine has significantly fewer vulnerabilities than Debian-based images.
#
# Build:
#   docker build -t freecad-mcp .
#
# Build multi-arch:
#   docker buildx build --platform linux/amd64,linux/arm64 -t freecad-mcp .
#
# Run:
#   docker run --rm -i freecad-mcp

# =============================================================================
# Stage 1: Builder - Install dependencies and build the package
# =============================================================================
FROM python:3.14-alpine AS builder

# Install build dependencies for compiling Python packages with native extensions
# hadolint ignore=DL3018
RUN apk add --no-cache \
    build-base \
    libffi-dev

# Set up working directory
WORKDIR /app

# Upgrade pip to fix CVE-2025-8869, then install uv for fast dependency management
# hadolint ignore=DL3013
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir --upgrade "pip>=25.3" && \
    pip install --no-cache-dir --no-compile uv

# Copy only dependency files first for better layer caching
# Include uv.lock for reproducible builds with locked dependency versions
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

# Version for setuptools-scm when building without git (e.g., in Docker)
# This can be overridden at build time with --build-arg VERSION=x.y.z
ARG VERSION=0.0.0.dev0
ENV SETUPTOOLS_SCM_PRETEND_VERSION=${VERSION}

# Create virtual environment and install dependencies using locked versions
# Using uv cache mount for faster rebuilds
# --frozen ensures uv.lock is used exactly without updates
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /opt/venv && \
    UV_PROJECT_ENVIRONMENT=/opt/venv uv sync --frozen --no-dev --no-editable

# =============================================================================
# Stage 2: Runtime - Minimal image for running the server
# =============================================================================
FROM python:3.14-alpine AS runtime

# Labels for container metadata (OCI Image Spec)
# Note: version, revision, and created are set dynamically in CI/CD workflows
LABEL org.opencontainers.image.title="FreeCAD Robust MCP Server" \
      org.opencontainers.image.description="Robust MCP Server for FreeCAD integration with AI assistants" \
      org.opencontainers.image.url="https://github.com/spkane/freecad-robust-mcp-and-more" \
      org.opencontainers.image.source="https://github.com/spkane/freecad-robust-mcp-and-more" \
      org.opencontainers.image.documentation="https://github.com/spkane/freecad-robust-mcp-and-more#readme" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.vendor="Sean P. Kane" \
      org.opencontainers.image.authors="Sean P. Kane <spkane@gmail.com>" \
      org.opencontainers.image.base.name="python:3.14-alpine"

# Upgrade all Alpine packages to fix CVEs in base image (zlib, busybox, etc.)
# This ensures we get security patches even if the base image is slightly stale
# hadolint ignore=DL3018
RUN apk upgrade --no-cache

# Create non-root user for security (Alpine uses addgroup/adduser)
RUN addgroup -g 1000 mcpuser && \
    adduser -u 1000 -G mcpuser -s /bin/sh -D mcpuser

# Remove pip, setuptools, and wheel from system Python to fix CVEs
# - The base image has pip with CVE-2025-8869
# - setuptools vendors jaraco.context 5.3.0 with GHSA-58pv-8j8x-9vj2
# Since we use a pre-built venv, we don't need these in system Python at runtime.
# This eliminates the vulnerabilities without affecting functionality.
# hadolint ignore=DL3013
RUN pip uninstall -y pip setuptools wheel 2>/dev/null || true && \
    rm -rf /usr/local/lib/python3.14/site-packages/pip* \
           /usr/local/lib/python3.14/site-packages/setuptools* \
           /usr/local/lib/python3.14/site-packages/wheel* \
           /usr/local/lib/python3.14/site-packages/pkg_resources*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Default to xmlrpc mode (requires FreeCAD running externally)
    FREECAD_MODE="xmlrpc" \
    FREECAD_SOCKET_HOST="host.docker.internal" \
    FREECAD_SOCKET_PORT="9876" \
    FREECAD_XMLRPC_PORT="9875" \
    FREECAD_TIMEOUT_MS="30000"

# Switch to non-root user
USER mcpuser
WORKDIR /home/mcpuser

# Health check - verify the server can start
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import freecad_mcp; print('ok')" || exit 1

# Default command - run the MCP server in stdio mode
ENTRYPOINT ["freecad-mcp"]
