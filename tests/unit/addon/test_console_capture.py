"""Tests for capturing FreeCAD's own console output during an execution."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest


def _load_server():  # type: ignore[no-untyped-def]
    """Import the workbench server module with FreeCAD mocked out."""
    for module_name in list(sys.modules):
        if module_name.endswith("freecad_mcp_bridge.server"):
            del sys.modules[module_name]
    freecad = MagicMock()
    freecad.GuiUp = False
    with patch.dict(sys.modules, {"FreeCAD": freecad, "FreeCADGui": MagicMock()}):
        from freecad.RobustMCPBridge.freecad_mcp_bridge import server

        return server


@pytest.fixture
def capture_class():  # type: ignore[no-untyped-def]
    """Return the console capture helper from the workbench server."""
    return _load_server()._ConsoleCapture


def test_captures_writes_to_the_process_file_descriptors(capture_class) -> None:  # type: ignore[no-untyped-def]
    """FreeCAD prints its diagnoses from C++, below Python's stdout object.

    `redirect_stderr` cannot see them and `FreeCAD.Console` exposes no
    `AddObserver`, so the file descriptors are the only route that works in
    both GUI and headless mode.
    """
    with capture_class() as capture:
        os.write(2, b"Roof001: Wire is not closed.\n")

    assert "Wire is not closed." in capture.text


def test_restores_the_descriptors_afterwards(capture_class) -> None:  # type: ignore[no-untyped-def]
    """A capture that leaked its redirect would silence FreeCAD permanently."""
    before = (os.fstat(1).st_dev, os.fstat(1).st_ino)

    with capture_class():
        os.write(1, b"noise\n")

    assert (os.fstat(1).st_dev, os.fstat(1).st_ino) == before


def test_restores_the_descriptors_when_the_body_raises(capture_class) -> None:  # type: ignore[no-untyped-def]
    """The failing path is the one that matters; it must still restore."""
    before = (os.fstat(2).st_dev, os.fstat(2).st_ino)

    with pytest.raises(RuntimeError):
        with capture_class():
            os.write(2, b"Spire: Wire is not closed.\n")
            raise RuntimeError("recompute failed")

    assert (os.fstat(2).st_dev, os.fstat(2).st_ino) == before


def test_truncates_a_flood_to_the_most_recent_output(capture_class) -> None:  # type: ignore[no-untyped-def]
    """A runaway recompute must not return megabytes to the caller."""
    with capture_class() as capture:
        os.write(2, b"x" * 10_000)
        os.write(2, b"\nRoof001: Wire is not closed.\n")

    assert len(capture.text) <= capture_class.MAX_CHARS
    assert "Wire is not closed." in capture.text
