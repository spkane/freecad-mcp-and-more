"""Tests for FreeCAD Robust MCP resources."""

import json
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from freecad_mcp.bridge.base import (
    ConnectionStatus,
    DocumentInfo,
    ObjectInfo,
    WorkbenchInfo,
)


class TestFreecadResources:
    """Tests for FreeCAD Robust MCP resources."""

    @pytest.fixture
    def mock_mcp(self) -> MagicMock:
        """Create a mock MCP server that captures resource registrations."""
        mcp = MagicMock()
        mcp._registered_resources = {}

        def resource_decorator(
            uri: str,
        ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
            def wrapper(func: Callable[..., Any]) -> Callable[..., Any]:
                mcp._registered_resources[uri] = func
                return func

            return wrapper

        mcp.resource = resource_decorator
        return mcp

    @pytest.fixture
    def mock_bridge(self) -> AsyncMock:
        """Create a mock FreeCAD bridge."""
        return AsyncMock()

    @pytest.fixture
    def register_resources(
        self, mock_mcp: MagicMock, mock_bridge: AsyncMock
    ) -> dict[str, Callable[..., Any]]:
        """Register resources and return the registered functions."""
        from freecad_mcp.resources.freecad import register_resources

        async def get_bridge() -> AsyncMock:
            return mock_bridge

        register_resources(mock_mcp, get_bridge)
        return mock_mcp._registered_resources

    @pytest.mark.asyncio
    async def test_resource_version(
        self, register_resources: dict[str, Callable[..., Any]], mock_bridge: AsyncMock
    ) -> None:
        """freecad://version should return version info."""
        mock_bridge.get_freecad_version = AsyncMock(
            return_value={
                "version": "1.0.0",
                "build_date": "2024-01-15",
                "python_version": "3.11.6",
                "gui_available": True,
            }
        )

        resource_version = register_resources["freecad://version"]
        result = await resource_version()
        data = json.loads(result)

        assert data["version"] == "1.0.0"
        assert data["gui_available"] is True
        mock_bridge.get_freecad_version.assert_called_once()

    @pytest.mark.asyncio
    async def test_resource_status_connected(
        self, register_resources: dict[str, Callable[..., Any]], mock_bridge: AsyncMock
    ) -> None:
        """freecad://status should return connected status."""
        mock_bridge.get_status = AsyncMock(
            return_value=ConnectionStatus(
                connected=True,
                mode="xmlrpc",
                freecad_version="1.0.0",
                gui_available=True,
                last_ping_ms=5.5,
                error=None,
            )
        )

        resource_status = register_resources["freecad://status"]
        result = await resource_status()
        data = json.loads(result)

        assert data["connected"] is True
        assert data["mode"] == "xmlrpc"
        assert data["last_ping_ms"] == 5.5
        assert data["error"] is None

    @pytest.mark.asyncio
    async def test_resource_status_disconnected(
        self, register_resources: dict[str, Callable[..., Any]], mock_bridge: AsyncMock
    ) -> None:
        """freecad://status should return error when disconnected."""
        mock_bridge.get_status = AsyncMock(
            return_value=ConnectionStatus(
                connected=False,
                mode="xmlrpc",
                error="Connection refused",
            )
        )

        resource_status = register_resources["freecad://status"]
        result = await resource_status()
        data = json.loads(result)

        assert data["connected"] is False
        assert data["error"] == "Connection refused"

    @pytest.mark.asyncio
    async def test_resource_documents_empty(
        self, register_resources: dict[str, Callable[..., Any]], mock_bridge: AsyncMock
    ) -> None:
        """freecad://documents should return empty list when no documents."""
        mock_bridge.get_documents = AsyncMock(return_value=[])

        resource_documents = register_resources["freecad://documents"]
        result = await resource_documents()
        data = json.loads(result)

        assert data == []

    @pytest.mark.asyncio
    async def test_resource_documents_with_docs(
        self, register_resources: dict[str, Callable[..., Any]], mock_bridge: AsyncMock
    ) -> None:
        """freecad://documents should return document list."""
        mock_docs = [
            DocumentInfo(
                name="Doc1",
                label="Document 1",
                path="/tmp/doc1.FCStd",
                objects=["Box", "Cylinder"],
                is_modified=False,
                active_object="Box",
            ),
            DocumentInfo(
                name="Doc2",
                label="Document 2",
                path=None,
                objects=["Sphere"],
                is_modified=True,
                active_object=None,
            ),
        ]
        mock_bridge.get_documents = AsyncMock(return_value=mock_docs)

        resource_documents = register_resources["freecad://documents"]
        result = await resource_documents()
        data = json.loads(result)

        assert len(data) == 2
        assert data[0]["name"] == "Doc1"
        assert data[0]["object_count"] == 2
        assert data[1]["name"] == "Doc2"
        assert data[1]["is_modified"] is True

    @pytest.mark.asyncio
    async def test_resource_document_found(
        self, register_resources: dict[str, Callable[..., Any]], mock_bridge: AsyncMock
    ) -> None:
        """freecad://documents/{name} should return document info."""
        mock_docs = [
            DocumentInfo(
                name="TestDoc",
                label="Test Document",
                path="/tmp/test.FCStd",
                objects=["Part1", "Part2"],
                is_modified=False,
                active_object="Part1",
            ),
        ]
        mock_bridge.get_documents = AsyncMock(return_value=mock_docs)

        resource_document = register_resources["freecad://documents/{name}"]
        result = await resource_document(name="TestDoc")
        data = json.loads(result)

        assert data["name"] == "TestDoc"
        assert data["objects"] == ["Part1", "Part2"]

    @pytest.mark.asyncio
    async def test_resource_document_not_found(
        self, register_resources: dict[str, Callable[..., Any]], mock_bridge: AsyncMock
    ) -> None:
        """freecad://documents/{name} should return error when not found."""
        mock_bridge.get_documents = AsyncMock(return_value=[])

        resource_document = register_resources["freecad://documents/{name}"]
        result = await resource_document(name="NonExistent")
        data = json.loads(result)

        assert "error" in data
        assert "not found" in data["error"]

    @pytest.mark.asyncio
    async def test_resource_document_objects(
        self, register_resources: dict[str, Callable[..., Any]], mock_bridge: AsyncMock
    ) -> None:
        """freecad://documents/{name}/objects should return object list."""
        mock_objects = [
            ObjectInfo(
                name="Box",
                label="My Box",
                type_id="Part::Box",
                visibility=True,
                children=[],
                parents=[],
            ),
            ObjectInfo(
                name="Cylinder",
                label="My Cylinder",
                type_id="Part::Cylinder",
                visibility=False,
                children=[],
                parents=[],
            ),
        ]
        mock_bridge.get_objects = AsyncMock(return_value=mock_objects)

        resource_objects = register_resources["freecad://documents/{name}/objects"]
        result = await resource_objects(name="TestDoc")
        data = json.loads(result)

        assert len(data) == 2
        assert data[0]["name"] == "Box"
        assert data[0]["type_id"] == "Part::Box"
        assert data[1]["visibility"] is False

    @pytest.mark.asyncio
    async def test_resource_object_details(
        self, register_resources: dict[str, Callable[..., Any]], mock_bridge: AsyncMock
    ) -> None:
        """freecad://objects/{doc_name}/{obj_name} should return object details."""
        mock_object = ObjectInfo(
            name="Box",
            label="My Box",
            type_id="Part::Box",
            properties={"Length": 10.0, "Width": 20.0, "Height": 30.0},
            shape_info={
                "shape_type": "Solid",
                "volume": 6000.0,
                "area": 2200.0,
                "is_valid": True,
            },
            visibility=True,
            children=[],
            parents=[],
        )
        mock_bridge.get_object = AsyncMock(return_value=mock_object)

        resource_object = register_resources["freecad://objects/{doc_name}/{obj_name}"]
        result = await resource_object(doc_name="TestDoc", obj_name="Box")
        data = json.loads(result)

        assert data["name"] == "Box"
        assert data["type_id"] == "Part::Box"
        assert data["properties"]["Length"] == 10.0
        assert data["shape_info"]["volume"] == 6000.0

    @pytest.mark.asyncio
    async def test_resource_active_document(
        self, register_resources: dict[str, Callable[..., Any]], mock_bridge: AsyncMock
    ) -> None:
        """freecad://active-document should return active document."""
        mock_doc = DocumentInfo(
            name="ActiveDoc",
            label="Active Document",
            path="/tmp/active.FCStd",
            objects=["Part1"],
            is_modified=True,
            active_object="Part1",
        )
        mock_bridge.get_active_document = AsyncMock(return_value=mock_doc)

        resource_active = register_resources["freecad://active-document"]
        result = await resource_active()
        data = json.loads(result)

        assert data["name"] == "ActiveDoc"
        assert data["is_modified"] is True

    @pytest.mark.asyncio
    async def test_resource_active_document_none(
        self, register_resources: dict[str, Callable[..., Any]], mock_bridge: AsyncMock
    ) -> None:
        """freecad://active-document should return null when no active document."""
        mock_bridge.get_active_document = AsyncMock(return_value=None)

        resource_active = register_resources["freecad://active-document"]
        result = await resource_active()
        data = json.loads(result)

        # Implementation returns json.dumps(None) which deserializes to Python None
        assert data is None

    @pytest.mark.asyncio
    async def test_resource_workbenches(
        self, register_resources: dict[str, Callable[..., Any]], mock_bridge: AsyncMock
    ) -> None:
        """freecad://workbenches should return workbench list."""
        mock_workbenches = [
            WorkbenchInfo(
                name="PartDesignWorkbench",
                label="Part Design",
                icon="",
                is_active=True,
            ),
            WorkbenchInfo(
                name="SketcherWorkbench",
                label="Sketcher",
                icon="",
                is_active=False,
            ),
        ]
        mock_bridge.get_workbenches = AsyncMock(return_value=mock_workbenches)

        resource_workbenches = register_resources["freecad://workbenches"]
        result = await resource_workbenches()
        data = json.loads(result)

        assert len(data) == 2
        assert data[0]["name"] == "PartDesignWorkbench"
        assert data[0]["is_active"] is True

    @pytest.mark.asyncio
    async def test_resource_active_workbench(
        self, register_resources: dict[str, Callable[..., Any]], mock_bridge: AsyncMock
    ) -> None:
        """freecad://workbenches/active should return active workbench."""
        mock_workbenches = [
            WorkbenchInfo(
                name="PartDesignWorkbench",
                label="Part Design",
                icon="",
                is_active=True,
            ),
            WorkbenchInfo(
                name="SketcherWorkbench",
                label="Sketcher",
                icon="",
                is_active=False,
            ),
        ]
        mock_bridge.get_workbenches = AsyncMock(return_value=mock_workbenches)

        resource_active_wb = register_resources["freecad://workbenches/active"]
        result = await resource_active_wb()
        data = json.loads(result)

        assert data["name"] == "PartDesignWorkbench"
        assert data["label"] == "Part Design"

    @pytest.mark.asyncio
    async def test_resource_console(
        self, register_resources: dict[str, Callable[..., Any]], mock_bridge: AsyncMock
    ) -> None:
        """freecad://console should return console output."""
        mock_bridge.get_console_output = AsyncMock(
            return_value=[
                "FreeCAD started",
                "Document created",
                "Box created",
            ]
        )

        resource_console = register_resources["freecad://console"]
        result = await resource_console()
        data = json.loads(result)

        assert "lines" in data
        assert len(data["lines"]) == 3
        assert data["count"] == 3

    @pytest.mark.asyncio
    async def test_resource_best_practices(
        self, register_resources: dict[str, Callable[..., Any]], mock_bridge: AsyncMock
    ) -> None:
        """freecad://best-practices should return AI guidance."""
        resource_best_practices = register_resources["freecad://best-practices"]
        result = await resource_best_practices()
        data = json.loads(result)

        # Should have description
        assert "description" in data
        assert "Best Practices" in data["description"]

        # Should have critical patterns section
        assert "critical_patterns" in data
        assert "validation_first" in data["critical_patterns"]
        assert "partdesign_workflow" in data["critical_patterns"]
        assert "transaction_safety" in data["critical_patterns"]

        # Should have version compatibility section
        assert "version_compatibility" in data
        assert "critical_changes" in data["version_compatibility"]
        assert "sketch_attachment" in data["version_compatibility"]["critical_changes"]

        # Should have GUI vs headless guidance
        assert "gui_vs_headless" in data
        assert "gui_only_features" in data["gui_vs_headless"]
        assert "headless_safe_features" in data["gui_vs_headless"]

        # Should have common pitfalls
        assert "common_pitfalls" in data
        assert "standalone_features" in data["common_pitfalls"]

        # Should have recommended workflows
        assert "recommended_workflows" in data
        assert "creating_parts" in data["recommended_workflows"]
        assert "debugging_issues" in data["recommended_workflows"]

        # Should have error recovery section
        assert "error_recovery" in data

        # Should have performance tips
        assert "performance_tips" in data

    @pytest.mark.asyncio
    async def test_resource_capabilities(
        self, register_resources: dict[str, Callable[..., Any]], mock_bridge: AsyncMock
    ) -> None:
        """freecad://capabilities should return server capabilities."""
        resource_capabilities = register_resources["freecad://capabilities"]
        result = await resource_capabilities()
        data = json.loads(result)

        # Should have tools section
        assert "tools" in data
        assert "execution" in data["tools"]
        assert "documents" in data["tools"]

        # Should have resources section - list of dicts with uri/description
        assert "resources" in data
        assert any("capabilities" in r.get("uri", "") for r in data["resources"])

        # Should have prompts section
        assert "prompts" in data

    @pytest.mark.asyncio
    async def test_resource_capabilities_includes_all_resources(
        self, register_resources: dict[str, Callable[..., Any]], mock_bridge: AsyncMock
    ) -> None:
        """freecad://capabilities should include all registered resources.

        This test ensures the capabilities resource stays in sync when new
        resources are added. Per CLAUDE.md: "When adding new MCP tools or
        resources, you MUST also update the freecad://capabilities resource."
        """
        resource_capabilities = register_resources["freecad://capabilities"]
        result = await resource_capabilities()
        data = json.loads(result)

        # Get all registered resource URIs (excluding capabilities itself)
        registered_uris = {
            uri for uri in register_resources if uri != "freecad://capabilities"
        }

        # Get URIs listed in the capabilities response (filter out None values)
        capability_uris = {
            r.get("uri") for r in data.get("resources", []) if r.get("uri") is not None
        }

        # All registered resources should be listed in capabilities
        missing_resources = registered_uris - capability_uris
        assert not missing_resources, (
            f"Resources registered but not in capabilities: {missing_resources}. "
            f"Update resource_capabilities() in src/freecad_mcp/resources/freecad.py"
        )

        # Reverse check: capabilities should not list stale/phantom resources
        # that are no longer registered (excluding capabilities itself)
        stale_resources = capability_uris - registered_uris - {"freecad://capabilities"}
        assert not stale_resources, (
            f"Stale resources in capabilities (not registered): {stale_resources}. "
            f"Remove these from resource_capabilities() in "
            f"src/freecad_mcp/resources/freecad.py"
        )
