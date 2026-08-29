"""Focused MCP prompts for native incremental PartDesign workflows."""

from typing import Any

from freecad_mcp.guidance import PARAMETRIC_PARTS_GUIDANCE


def register_prompts(mcp: Any, get_bridge: Any) -> None:  # noqa: ARG001
    """Register the reduced parametric-parts prompt set.

    Args:
        mcp: The FastMCP server instance.
        get_bridge: Async bridge getter, retained for registration consistency.
    """

    @mcp.prompt()
    async def design_parametric_part(
        description: str,
        output_directory: str = ".",
        units: str = "mm",
    ) -> str:
        """Create a native PartDesign implementation brief for a parametric part."""
        return f"""{PARAMETRIC_PARTS_GUIDANCE}

## Current Task

Design description: {description}
Units: {units}
Output directory: {output_directory}

Start with a short coordinate, parameter, datum, and feature plan. Build the
native feature tree with `define_variables`, `create_partdesign_body`,
`create_constrained_sketch`, `bind_expressions`, and additive or subtractive
feature tools such as `pad_sketch` and `pocket_sketch`. Use returned local
validation and `query_objects` instead of repeatedly listing the whole document.
Use granular sketch and expression tools only for repair. Then complete the
persistence, parameter-edit, export, render, and handoff gates above.
"""

    @mcp.prompt()
    async def review_parametric_part(model_name: str = "part") -> str:
        """Return a hard-gated review checklist for a generated part."""
        return f"""# Review Parametric FreeCAD Part: {model_name}

Review findings before summary. Reject unsupported claims.

1. Inspect the native Body, ordered feature tree, and final Body Tip.
2. Require no object errors, valid positive-volume BREP, and the intended solid
   count.
3. Verify the native variable set, derived expressions, sketch constraint
   state, semantic feature order, and topology-sensitive supports.
4. Require every driving sketch to report `FullyConstrained`.
5. Measure required features independently; bounds and render pixels are not
   substitutes for semantic measurements.
6. Change each governing variable and verify changed and protected dimensions;
   `define_variables` already recomputes the document.
7. Save FCStd, close, reopen, perform another governing-variable edit, and
   validate.
8. Export only the validated final object, re-import STEP, and validate it.
9. Inspect deterministic renders for every specified feature family.
10. Confirm final artifacts and measurements describe the same saved FCStd.
"""
