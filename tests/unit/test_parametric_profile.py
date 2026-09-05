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
    register_tools,
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

    register_tools(mcp, get_bridge)

    assert set(mcp._registered_tools) == set(PARAMETRIC_TOOL_NAMES)
    assert len(mcp._registered_tools) == 55
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


def test_server_instructions_are_the_parametric_guidance() -> None:
    """The server presents the parametric guidance; there is no other profile."""
    from freecad_mcp.server import mcp

    assert mcp.instructions == PARAMETRIC_PARTS_GUIDANCE


def test_guidance_contains_cross_workflow_quality_gates() -> None:
    """The shared guide should preserve the benchmark-proven quality gates."""
    from freecad_mcp.guidance import GUIDE_TOPICS, load_guide

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

    # Build corpus: core + all 7 topic guides
    corpus = PARAMETRIC_PARTS_GUIDANCE
    for topic in GUIDE_TOPICS:
        corpus += "\n" + load_guide(topic)

    for phrase in required_phrases:
        assert phrase in corpus, (
            f"Required phrase missing from delivered corpus: {phrase!r}"
        )


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
    assert PARAMETRIC_PARTS_GUIDANCE in design
    assert "build(doc, parameters)" not in design

    review = await mcp._registered_prompts["review_parametric_part"]("fixture")
    assert "Review Parametric FreeCAD Part: fixture" in review
    assert "Body Tip" in review
    assert "reopen" in review


@pytest.mark.asyncio
async def test_parametric_resources_match_registered_interface() -> None:
    """Capability metadata should exactly describe the reduced interface."""
    from freecad_mcp.guidance import GUIDE_TOPICS
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
    } | {f"freecad://guide/{topic}" for topic in GUIDE_TOPICS}

    capabilities = json.loads(
        await mcp._registered_resources["freecad://capabilities"]()
    )
    assert capabilities["profile"] == "parametric"
    assert capabilities["tool_count"] == 55
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


class TestGuideResources:
    """The progressive guide topics must be reachable as resources."""

    @pytest.mark.asyncio
    async def test_every_topic_is_registered(self):
        """Each topic in GUIDE_TOPICS has its own resource URI."""
        from freecad_mcp.guidance import GUIDE_TOPICS
        from freecad_mcp.resources.parametric import register_resources

        mcp = _resource_registry()
        register_resources(mcp, AsyncMock())

        for topic in GUIDE_TOPICS:
            assert f"freecad://guide/{topic}" in mcp._registered_resources

    @pytest.mark.asyncio
    async def test_topic_resource_returns_its_document(self):
        """Reading a topic resource returns that topic's markdown."""
        from freecad_mcp.guidance import load_guide
        from freecad_mcp.resources.parametric import register_resources

        mcp = _resource_registry()
        register_resources(mcp, AsyncMock())

        reader = mcp._registered_resources["freecad://guide/repair"]
        assert await reader() == load_guide("repair")

    @pytest.mark.asyncio
    async def test_core_alias_is_retained(self):
        """Existing configurations keep working."""
        from freecad_mcp.resources.parametric import register_resources

        mcp = _resource_registry()
        register_resources(mcp, AsyncMock())

        assert "freecad://parametric-parts/guide" in mcp._registered_resources

    @pytest.mark.asyncio
    async def test_capabilities_workflow_is_the_core_guides_workflow(self):
        """The catalog cannot state a workflow the instructions contradict.

        The catalog once carried its own hand-maintained eleven-step list.
        The core guide was rewritten and the copy was not, so a client
        reading `freecad://capabilities` was told to "inspect deterministic
        renders" while the instructions told it to capture along a support
        normal. Assert the served list against the guide itself.
        """
        import re

        from freecad_mcp.guidance import (
            PARAMETRIC_PARTS_GUIDANCE,
            REQUIRED_WORKFLOW_SCALING_RULE,
            REQUIRED_WORKFLOW_STEPS,
        )
        from freecad_mcp.resources.parametric import register_resources

        mcp = _resource_registry()
        register_resources(mcp, AsyncMock())

        catalog = json.loads(
            await mcp._registered_resources["freecad://capabilities"]()
        )
        assert catalog["workflow"] == list(REQUIRED_WORKFLOW_STEPS)
        assert catalog["workflow_scaling_rule"] == REQUIRED_WORKFLOW_SCALING_RULE

        # Guard against a future copy being pasted back in: every served
        # step has to be text the core guide actually contains.
        collapsed = re.sub(r"\s+", " ", PARAMETRIC_PARTS_GUIDANCE)
        for step in catalog["workflow"]:
            assert step in collapsed, f"workflow step not in the core guide: {step!r}"

        # The pre-branch list named steps the rewritten core dropped.
        assert "inspect deterministic renders" not in catalog["workflow"]
        assert "plan named parameters and datums" not in catalog["workflow"]

    @pytest.mark.asyncio
    async def test_capabilities_lists_every_registered_resource(self):
        """The catalog cannot advertise a resource set it does not register."""
        from freecad_mcp.resources.parametric import register_resources

        mcp = _resource_registry()
        register_resources(mcp, AsyncMock())

        catalog = json.loads(
            await mcp._registered_resources["freecad://capabilities"]()
        )
        assert sorted(catalog["resources"]) == sorted(mcp._registered_resources.keys())


def test_capture_feature_view_is_in_the_parametric_profile():
    """The visual gate's tool must be in the default surface."""
    assert "capture_feature_view" in PARAMETRIC_TOOL_NAMES
    assert len(PARAMETRIC_TOOL_NAMES) == 55


def test_design_prompt_carries_the_core_guidance():
    """The prompt and the instructions must not drift apart."""
    from freecad_mcp.guidance import PARAMETRIC_PARTS_GUIDANCE

    mcp = _prompt_registry()
    from freecad_mcp.prompts.parametric import register_prompts

    register_prompts(mcp, AsyncMock())
    prompt = mcp._registered_prompts["design_parametric_part"]

    import asyncio

    text = asyncio.run(prompt(description="a bracket"))
    assert PARAMETRIC_PARTS_GUIDANCE in text
    assert "a bracket" in text
