"""Shared guidance for native parametric FreeCAD modeling."""

from pathlib import Path

PARAMETRIC_PARTS_GUIDE_PATH = Path(__file__).with_name("PARAMETRIC_PARTS_GUIDE.md")


def get_parametric_parts_guidance() -> str:
    """Return the canonical parametric-parts guidance bundled with the server."""
    return PARAMETRIC_PARTS_GUIDE_PATH.read_text(encoding="utf-8")


PARAMETRIC_PARTS_GUIDANCE = get_parametric_parts_guidance()
