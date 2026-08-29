"""Contract tests for the reduced parametric MCP interface."""

import json
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from freecad_mcp.bridge.base import ConnectionStatus, DocumentInfo
from freecad_mcp.guidance import PARAMETRIC_PARTS_GUIDANCE
from freecad_mcp.tools import (
    PARAMETRIC_TOOL_NAMES,
    register_all_tools,
    register_parametric_tools,
)


def _tool_registry() -> MagicMock:
    """Create an MCP registry that captures tool names."""
    mcp = MagicMock()
    mcp._registered_tools = {}

    def tool_decorator() -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def register(func: Callable[..., Any]) -> Callable[..., Any]:
            mcp._registered_tools[func.__name__] = func
            return func

        return register

    mcp.tool = tool_decorator
    return mcp


def _prompt_registry() -> MagicMock:
    """Create an MCP registry that captures prompt names."""
    mcp = MagicMock()
    mcp._registered_prompts = {}

    def prompt_decorator() -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def register(func: Callable[..., Any]) -> Callable[..., Any]:
            mcp._registered_prompts[func.__name__] = func
            return func

        return register

    mcp.prompt = prompt_decorator
    return mcp


def _resource_registry() -> MagicMock:
    """Create an MCP registry that captures resource URIs."""
    mcp = MagicMock()
    mcp._registered_resources = {}

    def resource_decorator(
        uri: str,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def register(func: Callable[..., Any]) -> Callable[..., Any]:
            mcp._registered_resources[uri] = func
            return func

        return register

    mcp.resource = resource_decorator
    return mcp


def test_parametric_profile_registers_only_declared_tools() -> None:
    """The default profile should expose the native PartDesign workflow."""
    mcp = _tool_registry()

    async def get_bridge() -> AsyncMock:
        return AsyncMock()

    register_parametric_tools(mcp, get_bridge)

    assert set(mcp._registered_tools) == set(PARAMETRIC_TOOL_NAMES)
    assert len(mcp._registered_tools) == 54
    assert "create_partdesign_body" in mcp._registered_tools
    assert "create_sketch" in mcp._registered_tools
    assert "add_sketch_constraint" in mcp._registered_tools
    assert "pad_sketch" in mcp._registered_tools
    assert "pocket_sketch" in mcp._registered_tools
    assert "define_variables" in mcp._registered_tools
    assert "get_variables" in mcp._registered_tools
    assert "bind_expressions" in mcp._registered_tools
    assert "set_expression" in mcp._registered_tools
    assert "query_objects" in mcp._registered_tools
    assert "create_constrained_sketch" in mcp._registered_tools
    assert "import_step" in mcp._registered_tools
    assert "run_freecad_script" not in mcp._registered_tools
    assert "execute_python" not in mcp._registered_tools
    assert "safe_execute" not in mcp._registered_tools
    assert "create_box" not in mcp._registered_tools
    assert "run_macro" not in mcp._registered_tools
    assert "spreadsheet_create" not in mcp._registered_tools
    assert "spreadsheet_set_cell" not in mcp._registered_tools


def test_full_profile_preserves_historical_tool_surface() -> None:
    """The opt-in full profile should retain all existing typed tools."""
    mcp = _tool_registry()

    async def get_bridge() -> AsyncMock:
        return AsyncMock()

    register_all_tools(mcp, get_bridge)

    assert len(mcp._registered_tools) == 158
    assert "execute_python" in mcp._registered_tools
    assert "run_macro" in mcp._registered_tools
    assert "run_freecad_script" not in mcp._registered_tools


@pytest.mark.asyncio
async def test_full_capabilities_match_registered_tools_and_prompts() -> None:
    """The full-profile discovery catalog must not advertise stale names."""
    from freecad_mcp.prompts.freecad import register_prompts
    from freecad_mcp.resources.freecad import register_resources

    async def get_bridge() -> AsyncMock:
        return AsyncMock()

    tool_mcp = _tool_registry()
    register_all_tools(tool_mcp, get_bridge)

    resource_mcp = _resource_registry()
    register_resources(resource_mcp, get_bridge)
    capabilities = json.loads(
        await resource_mcp._registered_resources["freecad://capabilities"]()
    )
    catalog_tools = {
        tool["name"]
        for category in capabilities["tools"].values()
        for tool in category["tools"]
    }

    prompt_mcp = _prompt_registry()
    register_prompts(prompt_mcp, get_bridge)
    catalog_prompts = {prompt["name"] for prompt in capabilities["prompts"]}

    assert catalog_tools == set(tool_mcp._registered_tools)
    assert catalog_prompts == set(prompt_mcp._registered_prompts)


def test_server_instructions_follow_selected_profile() -> None:
    """The full profile should not receive parametric-only instructions."""
    from freecad_mcp.server import _instructions_for_profile

    assert _instructions_for_profile("parametric") == PARAMETRIC_PARTS_GUIDANCE
    assert _instructions_for_profile("full") is None


def test_guidance_contains_cross_workflow_quality_gates() -> None:
    """The shared guide should preserve the benchmark-proven quality gates."""
    required_phrases = [
        "coordinate frame",
        "governing parameters",
        "PartDesign::Body",
        "FullyConstrained",
        "create_sketch",
        "create_constrained_sketch",
        "add_sketch_constraint",
        "define_variables",
        "App::VarSet",
        "set_expression",
        "bind_expressions",
        "query_objects",
        "pad_sketch",
        "validate_document",
        "close it, reopen",
        "re-import",
        "Pixels do not prove",
        "native feature tree",
    ]

    for phrase in required_phrases:
        assert phrase in PARAMETRIC_PARTS_GUIDANCE


@pytest.mark.asyncio
async def test_parametric_prompts_are_focused_and_task_specific() -> None:
    """Only design and review prompts should be registered by default."""
    from freecad_mcp.prompts.parametric import register_prompts

    mcp = _prompt_registry()
    register_prompts(mcp, AsyncMock())

    assert set(mcp._registered_prompts) == {
        "design_parametric_part",
        "review_parametric_part",
    }
    design = await mcp._registered_prompts["design_parametric_part"](
        "A slotted motor plate", "/tmp/fixture"
    )
    assert "A slotted motor plate" in design
    assert "/tmp/fixture" in design
    assert "create_sketch" in design
    assert "pad_sketch" in design
    assert "build(doc, parameters)" not in design

    review = await mcp._registered_prompts["review_parametric_part"]("fixture")
    assert "Review Parametric FreeCAD Part: fixture" in review
    assert "Body Tip" in review
    assert "reopen" in review


@pytest.mark.asyncio
async def test_parametric_resources_match_registered_interface() -> None:
    """Capability metadata should exactly describe the reduced interface."""
    from freecad_mcp.resources.parametric import register_resources

    mcp = _resource_registry()
    bridge = AsyncMock()
    bridge.get_status = AsyncMock(
        return_value=ConnectionStatus(
            connected=True,
            mode="xmlrpc",
            freecad_version="1.1.3",
            gui_available=True,
            last_ping_ms=3.5,
        )
    )
    bridge.get_active_document = AsyncMock(
        return_value=DocumentInfo(
            name="Fixture",
            label="Fixture",
            path="/tmp/fixture.FCStd",
            objects=["Body"],
            is_modified=False,
            active_object="Body",
        )
    )

    async def get_bridge() -> AsyncMock:
        return bridge

    register_resources(mcp, get_bridge)
    assert set(mcp._registered_resources) == {
        "freecad://active-document",
        "freecad://capabilities",
        "freecad://parametric-parts/guide",
        "freecad://status",
    }

    capabilities = json.loads(
        await mcp._registered_resources["freecad://capabilities"]()
    )
    assert capabilities["profile"] == "parametric"
    assert capabilities["tool_count"] == 54
    assert set(capabilities["tools"]) == set(PARAMETRIC_TOOL_NAMES)
    assert capabilities["modeling_contract"]["authoritative_artifact"] == (
        "native FCStd PartDesign feature tree"
    )
    assert capabilities["modeling_contract"]["python_execution_exposed"] is False

    guide = await mcp._registered_resources["freecad://parametric-parts/guide"]()
    assert guide == PARAMETRIC_PARTS_GUIDANCE

    status = json.loads(await mcp._registered_resources["freecad://status"]())
    assert status["connected"] is True
    assert status["freecad_version"] == "1.1.3"

    active = json.loads(await mcp._registered_resources["freecad://active-document"]())
    assert active["name"] == "Fixture"
    assert active["objects"] == ["Body"]
