"""Tests for view and GUI tools module."""

import base64
import hashlib
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.types import CallToolResult

from freecad_mcp.bridge.base import (
    ExecutionResult,
    FeatureViewResult,
    ScreenshotResult,
)


class TestViewTools:
    """Tests for view and GUI tools."""

    @pytest.fixture(autouse=True)
    def _isolate_screenshot_dir(self, tmp_path, monkeypatch):
        """Keep screenshot persistence out of the working tree."""
        monkeypatch.setenv("FREECAD_MCP_SCREENSHOT_DIR", str(tmp_path / "screenshots"))

    @pytest.fixture
    def mock_mcp(self):
        """Create a mock MCP server that captures tool registrations."""
        mcp = MagicMock()
        mcp._registered_tools = {}

        def tool_decorator():
            def wrapper(func):
                mcp._registered_tools[func.__name__] = func
                return func

            return wrapper

        mcp.tool = tool_decorator
        return mcp

    @pytest.fixture
    def mock_bridge(self):
        """Create a mock FreeCAD bridge."""
        return AsyncMock()

    @pytest.fixture
    def register_tools(self, mock_mcp, mock_bridge):
        """Register view tools and return the registered functions."""
        from freecad_mcp.tools.view import register_view_tools

        async def get_bridge():
            return mock_bridge

        register_view_tools(mock_mcp, get_bridge)
        return mock_mcp._registered_tools

    @pytest.mark.asyncio
    async def test_get_screenshot_success(self, register_tools, mock_bridge):
        """get_screenshot should return base64 image data."""
        # get_screenshot calls bridge.get_screenshot which returns ScreenshotResult
        mock_bridge.get_screenshot = AsyncMock(
            return_value=ScreenshotResult(
                success=True,
                data="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
                "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
                format="png",
                width=800,
                height=600,
                error=None,
            )
        )

        get_screenshot = register_tools["get_screenshot"]
        result = await get_screenshot(view_angle="Isometric")

        assert result.isError is False
        assert any(block.type == "image" for block in result.content)
        metadata = json.loads(
            next(block for block in result.content if block.type == "text").text
        )
        assert metadata["success"] is True
        assert metadata["format"] == "png"
        mock_bridge.get_screenshot.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_screenshot_custom_size(self, register_tools, mock_bridge):
        """get_screenshot should accept width and height parameters."""
        mock_bridge.get_screenshot = AsyncMock(
            return_value=ScreenshotResult(
                success=True,
                data="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
                "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
                format="png",
                width=1920,
                height=1080,
                error=None,
            )
        )

        get_screenshot = register_tools["get_screenshot"]
        result = await get_screenshot(width=1920, height=1080)

        metadata = json.loads(
            next(block for block in result.content if block.type == "text").text
        )
        assert metadata["width"] == 1920
        assert metadata["height"] == 1080

    @pytest.mark.asyncio
    async def test_get_screenshot_headless_error(self, register_tools, mock_bridge):
        """get_screenshot should return error in headless mode."""
        mock_bridge.get_screenshot = AsyncMock(
            return_value=ScreenshotResult(
                success=False,
                data=None,
                format="png",
                width=0,
                height=0,
                error="GUI not available - screenshot cannot be captured in headless mode",
            )
        )

        get_screenshot = register_tools["get_screenshot"]
        result = await get_screenshot()

        assert result.isError is True
        assert json.loads(result.content[0].text)["success"] is False
        assert "headless" in json.loads(result.content[0].text)["error"]

    @pytest.mark.asyncio
    async def test_get_screenshot_invalid_view_angle(self, register_tools, mock_bridge):
        """get_screenshot should return error for invalid view angle."""
        get_screenshot = register_tools["get_screenshot"]
        result = await get_screenshot(view_angle="InvalidAngle")

        assert result.isError is True
        assert json.loads(result.content[0].text)["success"] is False
        assert "Invalid view_angle" in json.loads(result.content[0].text)["error"]

    @pytest.mark.asyncio
    async def test_set_view_angle(self, register_tools, mock_bridge):
        """set_view_angle should set the camera view via bridge.set_view."""
        mock_bridge.set_view = AsyncMock(return_value=None)

        set_view_angle = register_tools["set_view_angle"]
        result = await set_view_angle(view_angle="Front")

        assert result["success"] is True
        mock_bridge.set_view.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_view_angle_invalid(self, register_tools, mock_bridge):
        """set_view_angle should return error for invalid view angle."""
        set_view_angle = register_tools["set_view_angle"]
        result = await set_view_angle(view_angle="InvalidAngle")

        assert result["success"] is False
        assert "Invalid view_angle" in result["error"]

    @pytest.mark.asyncio
    async def test_fit_all(self, register_tools, mock_bridge):
        """fit_all should zoom to fit all objects via bridge.set_view."""
        mock_bridge.set_view = AsyncMock(return_value=None)

        fit_all = register_tools["fit_all"]
        result = await fit_all()

        assert result["success"] is True
        mock_bridge.set_view.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_object_visibility(self, register_tools, mock_bridge):
        """set_object_visibility should show/hide objects via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"success": True, "visible": False},
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        set_visibility = register_tools["set_object_visibility"]
        result = await set_visibility(object_name="Box", visible=False)

        assert result["success"] is True
        assert result["visible"] is False
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_object_visibility_headless(self, register_tools, mock_bridge):
        """set_object_visibility should return error in headless mode."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "success": False,
                    "error": "GUI not available - visibility cannot be set in headless mode",
                },
                stdout="",
                stderr="",
                execution_time_ms=5.0,
            )
        )

        set_visibility = register_tools["set_object_visibility"]
        result = await set_visibility(object_name="Box", visible=True)

        assert result["success"] is False
        assert "headless" in result["error"]

    @pytest.mark.asyncio
    async def test_undo(self, register_tools, mock_bridge):
        """undo should undo the last operation via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"success": True, "can_undo": True},
                stdout="",
                stderr="",
                execution_time_ms=5.0,
            )
        )

        undo = register_tools["undo"]
        result = await undo()

        assert result["success"] is True
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_redo(self, register_tools, mock_bridge):
        """redo should redo an undone operation via execute_python."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={"success": True, "can_redo": False},
                stdout="",
                stderr="",
                execution_time_ms=5.0,
            )
        )

        redo = register_tools["redo"]
        result = await redo()

        assert result["success"] is True
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_capture_feature_view_returns_image_and_metadata(
        self, register_tools, mock_bridge
    ):
        """A capture returns a viewable image plus its camera metadata."""
        mock_bridge.capture_feature_view = AsyncMock(
            return_value=ScreenshotResult(
                success=True,
                data="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
                "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
                format="png",
                width=800,
                height=600,
                error=None,
            )
        )

        capture = register_tools["capture_feature_view"]
        result = await capture(normal_source="WindowSketch")

        assert result.isError is False
        assert any(block.type == "image" for block in result.content)
        metadata = json.loads(
            next(block for block in result.content if block.type == "text").text
        )
        assert metadata["normal_source"] == "WindowSketch"
        assert metadata["side"] == "front"
        assert metadata["path"].endswith(".png")

    @pytest.mark.asyncio
    async def test_capture_feature_view_reports_the_full_evidence_metadata(
        self, register_tools, mock_bridge
    ):
        """Every field the bridge resolved has to reach the caller.

        The camera direction and the hidden objects are decided inside
        FreeCAD, so the metadata block is the only record of which of
        +/-normal was looked along and whose datums were hidden to get the
        shot. They were computed and then dropped once already; a model
        cannot state its visual comparison without them.
        """
        image = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
            "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        mock_bridge.capture_feature_view = AsyncMock(
            return_value=FeatureViewResult(
                success=True,
                data=image,
                format="png",
                width=800,
                height=600,
                normal_source="WindowSketch",
                side="back",
                camera_direction=(0.0, -1.0, 0.0),
                placement={
                    "position": [1.0, 2.0, 3.0],
                    "axis": [1.0, 0.0, 0.0],
                    "angle_deg": 90.0,
                    "normal": [0.0, -1.0, 0.0],
                },
                focus=["Pad"],
                hidden_objects=["WindowSketch", "Origin"],
                padding=0.25,
            )
        )

        capture = register_tools["capture_feature_view"]
        result = await capture(
            normal_source="WindowSketch",
            side="back",
            focus=["Pad"],
            padding=0.25,
        )

        assert result.isError is False
        metadata = json.loads(
            next(block for block in result.content if block.type == "text").text
        )
        assert metadata["camera_direction"] == [0.0, -1.0, 0.0]
        assert metadata["placement"]["angle_deg"] == 90.0
        assert metadata["placement"]["normal"] == [0.0, -1.0, 0.0]
        assert metadata["focus"] == ["Pad"]
        assert metadata["hidden_objects"] == ["WindowSketch", "Origin"]
        assert metadata["padding"] == 0.25
        assert metadata["side"] == "back"
        assert (
            metadata["image_sha256"]
            == hashlib.sha256(base64.b64decode(image)).hexdigest()
        )

    @pytest.mark.asyncio
    async def test_capture_feature_view_error_states_no_view_angle(
        self, register_tools, mock_bridge
    ):
        """A support-normal capture has no fixed view angle to report.

        Reporting the `normal_source` under a `view_angle` key told the
        model something untrue about what it had asked for.
        """
        mock_bridge.capture_feature_view = AsyncMock(
            return_value=FeatureViewResult(
                success=False,
                data=None,
                error="focus objects not found: NoSuchSketch",
                width=800,
                height=600,
            )
        )

        capture = register_tools["capture_feature_view"]
        result = await capture(normal_source="WindowSketch", side="back")

        assert result.isError is True
        payload = json.loads(result.content[0].text)
        assert "view_angle" not in payload
        assert payload["normal_source"] == "WindowSketch"
        assert payload["side"] == "back"
        assert payload["error"] == "focus objects not found: NoSuchSketch"

    @pytest.mark.asyncio
    async def test_capture_feature_view_rejects_unknown_side(
        self, register_tools, mock_bridge
    ):
        """An invalid side is refused before the bridge is touched."""
        mock_bridge.capture_feature_view = AsyncMock()

        capture = register_tools["capture_feature_view"]
        result = await capture(normal_source="S", side="sideways")

        assert result.isError is True
        mock_bridge.capture_feature_view.assert_not_called()

    @pytest.mark.asyncio
    async def test_capture_feature_view_failure_is_reported_as_error(
        self, register_tools, mock_bridge
    ):
        """A bridge failure surfaces as a tool error, not a silent success."""
        mock_bridge.capture_feature_view = AsyncMock(
            return_value=ScreenshotResult(
                success=False,
                data=None,
                error="Sketch has no resolvable support placement",
                width=800,
                height=600,
            )
        )

        capture = register_tools["capture_feature_view"]
        result = await capture(normal_source="Missing")

        assert result.isError is True


class TestScreenshotEvidenceTransport:
    """get_screenshot must deliver a viewable image and a retained PNG."""

    @pytest.fixture
    def mock_mcp(self):
        mcp = MagicMock()
        mcp._registered_tools = {}

        def tool_decorator():
            def wrapper(func):
                mcp._registered_tools[func.__name__] = func
                return func

            return wrapper

        mcp.tool = tool_decorator
        return mcp

    @pytest.fixture
    def mock_bridge(self):
        return AsyncMock()

    @pytest.fixture
    def register_tools(self, mock_mcp, mock_bridge):
        from freecad_mcp.tools.view import register_view_tools

        async def get_bridge():
            return mock_bridge

        register_view_tools(mock_mcp, get_bridge)
        return mock_mcp._registered_tools

    PNG_B64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
        "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )

    @pytest.fixture
    def shot_bridge(self, mock_bridge):
        mock_bridge.get_screenshot = AsyncMock(
            return_value=ScreenshotResult(
                success=True,
                data=self.PNG_B64,
                format="png",
                width=640,
                height=480,
                error=None,
            )
        )
        return mock_bridge

    @pytest.mark.asyncio
    async def test_returns_image_content_block(
        self, register_tools, shot_bridge, tmp_path, monkeypatch
    ):
        """The model must receive a real ImageContent block, not base64 text."""
        monkeypatch.setenv("FREECAD_MCP_SCREENSHOT_DIR", str(tmp_path))
        result = await register_tools["get_screenshot"](view_angle="Isometric")

        assert isinstance(result, CallToolResult)
        assert result.isError is False
        kinds = [block.type for block in result.content]
        assert "image" in kinds, f"no image content block, got {kinds}"
        image = next(b for b in result.content if b.type == "image")
        assert image.mimeType == "image/png"
        assert image.data == self.PNG_B64

    @pytest.mark.asyncio
    async def test_persists_png_into_run_directory(
        self, register_tools, shot_bridge, tmp_path, monkeypatch
    ):
        """A deterministic PNG must be retained as run evidence."""
        monkeypatch.setenv("FREECAD_MCP_SCREENSHOT_DIR", str(tmp_path))
        result = await register_tools["get_screenshot"](
            view_angle="Right", doc_name="Lighthouse"
        )

        written = sorted(tmp_path.glob("*.png"))
        assert len(written) == 1, f"expected one retained PNG, got {written}"
        assert written[0].read_bytes() == base64.b64decode(self.PNG_B64)
        assert "Right" in written[0].name
        assert "Lighthouse" in written[0].name

        meta = json.loads(next(b for b in result.content if b.type == "text").text)
        assert meta["path"] == str(written[0])
        assert meta["view_angle"] == "Right"
        assert meta["width"] == 640

    @pytest.mark.asyncio
    async def test_metadata_block_excludes_base64_payload(
        self, register_tools, shot_bridge, tmp_path, monkeypatch
    ):
        """Base64 must not be duplicated into the text block."""
        monkeypatch.setenv("FREECAD_MCP_SCREENSHOT_DIR", str(tmp_path))
        result = await register_tools["get_screenshot"]()

        text = next(b for b in result.content if b.type == "text").text
        assert self.PNG_B64 not in text
        assert "data" not in json.loads(text)

    @pytest.mark.asyncio
    async def test_successive_captures_do_not_overwrite(
        self, register_tools, shot_bridge, tmp_path, monkeypatch
    ):
        """Each capture is retained separately so evidence is not lost."""
        monkeypatch.setenv("FREECAD_MCP_SCREENSHOT_DIR", str(tmp_path))
        await register_tools["get_screenshot"](view_angle="Front")
        await register_tools["get_screenshot"](view_angle="Front")

        assert len(sorted(tmp_path.glob("*.png"))) == 2

    @pytest.mark.asyncio
    async def test_capture_failure_is_reported_as_error(
        self, register_tools, mock_bridge, tmp_path, monkeypatch
    ):
        """A headless or failed capture must be an explicit tool error."""
        monkeypatch.setenv("FREECAD_MCP_SCREENSHOT_DIR", str(tmp_path))
        mock_bridge.get_screenshot = AsyncMock(
            return_value=ScreenshotResult(
                success=False,
                data=None,
                format="png",
                width=0,
                height=0,
                error="GUI not available",
            )
        )
        result = await register_tools["get_screenshot"]()

        assert result.isError is True
        assert all(b.type == "text" for b in result.content)
        assert "GUI not available" in result.content[0].text
        assert not sorted(tmp_path.glob("*.png"))

    @pytest.mark.asyncio
    async def test_unwritable_directory_still_returns_image(
        self, register_tools, shot_bridge, tmp_path, monkeypatch
    ):
        """Losing persistence must not cost the model its view of the model."""
        target = tmp_path / "blocked"
        target.write_text("not a directory")
        monkeypatch.setenv("FREECAD_MCP_SCREENSHOT_DIR", str(target))

        result = await register_tools["get_screenshot"]()

        assert result.isError is False
        assert any(b.type == "image" for b in result.content)
        meta = json.loads(next(b for b in result.content if b.type == "text").text)
        assert meta["path"] is None
