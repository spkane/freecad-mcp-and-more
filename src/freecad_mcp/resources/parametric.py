"""Focused MCP resources for parametric FreeCAD part workflows."""

import json
from collections.abc import Awaitable, Callable
from typing import Any

from freecad_mcp.guidance import (
    GUIDE_TOPICS,
    PARAMETRIC_PARTS_GUIDANCE,
    load_guide,
)
from freecad_mcp.tools import PARAMETRIC_TOOL_NAMES


def _make_guide_reader(topic: str) -> Callable[[], Awaitable[str]]:
    """Build a zero-argument resource reader bound to one guide topic.

    Args:
        topic: A topic name from ``GUIDE_TOPICS``.

    Returns:
        An async callable that returns that topic's markdown document.
    """

    async def resource_guide_topic() -> str:
        """Return one progressive guide topic document."""
        return load_guide(topic)

    resource_guide_topic.__name__ = f"resource_guide_{topic.replace('-', '_')}"
    return resource_guide_topic


def register_resources(mcp: Any, get_bridge: Any) -> None:
    """Register compact runtime and parametric-guidance resources.

    Args:
        mcp: The FastMCP server instance.
        get_bridge: Async function returning the active bridge.
    """

    @mcp.resource("freecad://parametric-parts/guide")
    async def resource_parametric_parts_guide() -> str:
        """Return the native incremental PartDesign modeling guide."""
        return PARAMETRIC_PARTS_GUIDANCE

    for topic in GUIDE_TOPICS:
        mcp.resource(f"freecad://guide/{topic}")(_make_guide_reader(topic))

    @mcp.resource("freecad://capabilities")
    async def resource_capabilities() -> str:
        """Return the exact default tool, prompt, and resource interface."""
        return json.dumps(
            {
                "profile": "parametric",
                "purpose": "Native parametric FreeCAD parts through MCP commands",
                "tool_count": len(PARAMETRIC_TOOL_NAMES),
                "tools": sorted(PARAMETRIC_TOOL_NAMES),
                "prompts": [
                    "design_parametric_part",
                    "review_parametric_part",
                ],
                "resources": sorted(
                    [
                        "freecad://active-document",
                        "freecad://capabilities",
                        "freecad://parametric-parts/guide",
                        "freecad://status",
                    ]
                    + [f"freecad://guide/{topic}" for topic in GUIDE_TOPICS]
                ),
                "modeling_contract": {
                    "authoritative_artifact": "native FCStd PartDesign feature tree",
                    "construction": "task-oriented MCP sketch and feature tools",
                    "mutations": (
                        "transactional recompute with Body-tip, solid-count, "
                        "and material-effect validation"
                    ),
                    "expression_failures": (
                        "property-scoped diagnostics with complete rollback"
                    ),
                    "python_execution_exposed": False,
                },
                "workflow": [
                    "plan named parameters and datums",
                    "create a document, Body, and native variable set",
                    "create complete constrained sketches with symbolic IDs",
                    "bind related expressions in atomic batches",
                    "pad, pocket, revolve, groove, and pattern native features",
                    "use local mutation validation and bounded object queries",
                    "validate the document after meaningful feature groups",
                    "edit governing variables and verify their response",
                    "save, close, reopen, edit, and validate",
                    "export and re-import STEP",
                    "inspect deterministic renders",
                ],
            },
            indent=2,
        )

    @mcp.resource("freecad://status")
    async def resource_status() -> str:
        """Return current bridge connection and FreeCAD runtime status."""
        bridge = await get_bridge()
        status = await bridge.get_status()
        return json.dumps(
            {
                "connected": status.connected,
                "mode": status.mode,
                "freecad_version": status.freecad_version,
                "gui_available": status.gui_available,
                "last_ping_ms": status.last_ping_ms,
                "error": status.error,
            },
            indent=2,
        )

    @mcp.resource("freecad://active-document")
    async def resource_active_document() -> str:
        """Return the active document and its object names."""
        bridge = await get_bridge()
        document = await bridge.get_active_document()
        if document is None:
            return json.dumps(None)
        return json.dumps(
            {
                "name": document.name,
                "label": document.label,
                "path": document.path,
                "objects": document.objects,
                "is_modified": document.is_modified,
                "active_object": document.active_object,
            },
            indent=2,
        )
