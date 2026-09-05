"""Shared guidance for native parametric FreeCAD modeling."""

import re
from pathlib import Path

PARAMETRIC_PARTS_GUIDE_PATH = Path(__file__).with_name("PARAMETRIC_PARTS_GUIDE.md")

REQUIRED_WORKFLOW_HEADING = "## Required Workflow"

_ORDERED_ITEM = re.compile(r"^\d+\.\s+(?P<body>.+)$")


def get_parametric_parts_guidance() -> str:
    """Return the canonical parametric-parts guidance bundled with the server."""
    return PARAMETRIC_PARTS_GUIDE_PATH.read_text(encoding="utf-8")


PARAMETRIC_PARTS_GUIDANCE = get_parametric_parts_guidance()


def parse_required_workflow(markdown: str) -> tuple[str, tuple[str, ...]]:
    """Extract the required workflow from the core guide's markdown.

    The `freecad://capabilities` resource has to state the same workflow the
    server's own instructions state. Reading it out of the guide keeps one
    source of record: a second hand-maintained copy drifted once already,
    leaving the catalog advertising a workflow the instructions contradicted.

    Args:
        markdown: The core guide's markdown source.

    Returns:
        A pair of the scaling rule -- the prose paragraph that opens the
        section -- and the ordered workflow steps. Each step joins its
        wrapped continuation lines into one whitespace-normalized string.

    Raises:
        ValueError: If the section or its ordered list is absent, so a
            renamed heading fails loudly instead of serving an empty
            workflow.
    """
    in_section = False
    intro: list[str] = []
    steps: list[list[str]] = []

    for line in markdown.splitlines():
        if line.startswith("## "):
            if in_section:
                break
            in_section = line.strip() == REQUIRED_WORKFLOW_HEADING
            continue
        if not in_section or not line.strip():
            continue

        item = _ORDERED_ITEM.match(line)
        if item is not None:
            steps.append([item.group("body").strip()])
        elif steps:
            steps[-1].append(line.strip())
        else:
            intro.append(line.strip())

    if not steps:
        raise ValueError(f"no ordered steps found under {REQUIRED_WORKFLOW_HEADING!r}")
    return " ".join(intro), tuple(" ".join(parts) for parts in steps)


_SCALING_RULE, _WORKFLOW_STEPS = parse_required_workflow(PARAMETRIC_PARTS_GUIDANCE)

REQUIRED_WORKFLOW_SCALING_RULE: str = _SCALING_RULE
"""The rule that opens the required workflow: how far to scale the protocol."""

REQUIRED_WORKFLOW_STEPS: tuple[str, ...] = _WORKFLOW_STEPS
"""The core guide's ordered workflow steps, read from the guide itself."""

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
