"""Shared guidance for native parametric FreeCAD modeling."""

from pathlib import Path

PARAMETRIC_PARTS_GUIDE_PATH = Path(__file__).with_name("PARAMETRIC_PARTS_GUIDE.md")


def get_parametric_parts_guidance() -> str:
    """Return the canonical parametric-parts guidance bundled with the server."""
    return PARAMETRIC_PARTS_GUIDE_PATH.read_text(encoding="utf-8")


PARAMETRIC_PARTS_GUIDANCE = get_parametric_parts_guidance()

GUIDE_DIRECTORY = Path(__file__).with_name("guides")

GUIDE_TOPICS: tuple[str, ...] = (
    "brief",
    "visual-evidence",
    "parameters",
    "features",
    "variants",
    "repair",
    "delivery",
)


def load_guide(topic: str) -> str:
    """Return one progressive guide topic document.

    Args:
        topic: A topic name from ``GUIDE_TOPICS``.

    Returns:
        The topic's markdown source.

    Raises:
        KeyError: If the topic is not in ``GUIDE_TOPICS``.
    """
    if topic not in GUIDE_TOPICS:
        raise KeyError(f"unknown guide topic: {topic}")
    return (GUIDE_DIRECTORY / f"{topic}.md").read_text(encoding="utf-8")
