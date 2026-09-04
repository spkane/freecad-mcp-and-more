"""PartDesign tools for FreeCAD Robust MCP Server.

This module provides tools for the PartDesign workbench, enabling
parametric solid modeling operations like Pad, Pocket, Fillet, etc.

Based on learnings from contextform/freecad-mcp which has the most
comprehensive PartDesign coverage.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from freecad_mcp.tools.utils import WORKFLOW_HELPERS
from freecad_mcp.tools.workflow_results import (
    ConstrainedSketchResult,
    DatumPlaneResult,
    FeatureMutationResult,
    WorkflowToolError,
    bridge_workflow_error,
)

SketchSymbolicId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
    ),
]
SketchPoint2D = tuple[float, float]
SketchReferencePoint = Literal["start", "end", "center", "position", "whole"]


class SketchLine(BaseModel):
    """A line segment identified within one sketch creation request."""

    model_config = ConfigDict(extra="forbid")

    id: SketchSymbolicId
    kind: Literal["line"] = "line"
    start: SketchPoint2D
    end: SketchPoint2D
    construction: bool = False

    @model_validator(mode="after")
    def validate_length(self) -> Self:
        """Reject a zero-length line."""
        if self.start == self.end:
            msg = "Line start and end points must differ"
            raise ValueError(msg)
        return self


class SketchCircle(BaseModel):
    """A circle identified within one sketch creation request."""

    model_config = ConfigDict(extra="forbid")

    id: SketchSymbolicId
    kind: Literal["circle"] = "circle"
    center: SketchPoint2D
    radius: float = Field(gt=0)
    construction: bool = False


class SketchArc(BaseModel):
    """A circular arc whose angles are expressed in degrees."""

    model_config = ConfigDict(extra="forbid")

    id: SketchSymbolicId
    kind: Literal["arc"] = "arc"
    center: SketchPoint2D
    radius: float = Field(gt=0)
    start_angle: float
    end_angle: float
    construction: bool = False

    @model_validator(mode="after")
    def validate_angle_span(self) -> Self:
        """Reject a zero-length arc."""
        if self.start_angle == self.end_angle:
            msg = "Arc start and end angles must differ"
            raise ValueError(msg)
        return self


class SketchPoint(BaseModel):
    """A point geometry identified within one sketch creation request."""

    model_config = ConfigDict(extra="forbid")

    id: SketchSymbolicId
    kind: Literal["point"] = "point"
    position: SketchPoint2D
    construction: bool = False


class SketchRectangle(BaseModel):
    """A rectangle expanded to four constrained line segments."""

    model_config = ConfigDict(extra="forbid")

    id: SketchSymbolicId
    kind: Literal["rectangle"] = "rectangle"
    origin: SketchPoint2D
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    construction: bool = False


SketchEntity = Annotated[
    SketchLine | SketchCircle | SketchArc | SketchPoint | SketchRectangle,
    Field(discriminator="kind"),
]


class SketchReference(BaseModel):
    """Reference a request-local entity or rectangle edge by symbolic ID.

    For signed ``distance_x`` and ``distance_y`` constraints, reference order is
    significant: two point references measure second minus first.
    """

    model_config = ConfigDict(extra="forbid")

    entity: str = Field(min_length=1)
    point: SketchReferencePoint = "whole"


SketchConstraintKind = Literal[
    "coincident",
    "horizontal",
    "vertical",
    "parallel",
    "perpendicular",
    "tangent",
    "equal",
    "distance",
    "distance_x",
    "distance_y",
    "radius",
    "diameter",
    "angle",
    "point_on_object",
    "block",
]


class SketchConstraint(BaseModel):
    """A geometric or dimensional constraint over symbolic references.

    ``distance_x`` and ``distance_y`` use FreeCAD's signed conventions. A whole
    line measures end minus start, one point reference measures its signed
    coordinate from the sketch origin, and two point references measure second
    minus first. Reverse the references or value sign to reverse the direction.
    """

    model_config = ConfigDict(extra="forbid")

    id: SketchSymbolicId
    kind: SketchConstraintKind
    first: SketchReference
    second: SketchReference | None = None
    value: float | None = None
    expression: str | None = None

    @model_validator(mode="after")
    def validate_constraint(self) -> Self:
        """Validate dimensions and binary constraint operands."""
        dimensional = {
            "distance",
            "distance_x",
            "distance_y",
            "radius",
            "diameter",
            "angle",
        }
        if self.expression is not None:
            self.expression = self.expression.strip()
            if not self.expression:
                msg = "Constraint expression must not be empty"
                raise ValueError(msg)
        supplied_dimensions = int(self.value is not None) + int(
            self.expression is not None
        )
        if self.kind in dimensional and supplied_dimensions != 1:
            msg = "Dimensional constraints require exactly one of value or expression"
            raise ValueError(msg)
        if self.kind not in dimensional and supplied_dimensions:
            msg = "Geometric constraints cannot define value or expression"
            raise ValueError(msg)
        binary = {
            "coincident",
            "parallel",
            "perpendicular",
            "tangent",
            "equal",
            "point_on_object",
        }
        if self.kind in binary and self.second is None:
            msg = f"Constraint {self.kind} requires a second reference"
            raise ValueError(msg)

        self._validate_geometric_reference_roles()
        self._validate_dimensional_reference_roles()
        return self

    def _validate_geometric_reference_roles(self) -> None:
        """Validate native point roles for geometric constraints."""
        second = self.second
        if self.kind in {"horizontal", "vertical", "block"}:
            if self.first.point != "whole":
                msg = f"{self.kind} first reference must use whole geometry"
                raise ValueError(msg)
            if second is not None:
                msg = f"{self.kind} does not accept a second reference"
                raise ValueError(msg)
        if self.kind in {"parallel", "equal"} and (
            self.first.point != "whole" or second is None or second.point != "whole"
        ):
            msg = f"{self.kind} references must use whole geometry"
            raise ValueError(msg)
        if self.kind == "coincident" and (
            self.first.point == "whole" or second is None or second.point == "whole"
        ):
            msg = "coincident references must select points"
            raise ValueError(msg)
        if self.kind == "point_on_object" and (
            self.first.point == "whole" or second is None or second.point != "whole"
        ):
            msg = "point_on_object requires a point reference and whole geometry"
            raise ValueError(msg)

    def _validate_dimensional_reference_roles(self) -> None:
        """Validate native point roles for dimensional constraints."""
        second = self.second
        if self.kind in {"radius", "diameter"} and (
            self.first.point != "whole" or second is not None
        ):
            msg = f"{self.kind} requires one whole geometry reference"
            raise ValueError(msg)
        if self.kind == "distance" and second is None and self.first.point != "whole":
            msg = "distance requires whole geometry when no second reference is given"
            raise ValueError(msg)
        if (
            self.kind in {"distance_x", "distance_y"}
            and second is not None
            and (self.first.point == "whole" or second.point == "whole")
        ):
            msg = f"{self.kind} two-reference form requires point references"
            raise ValueError(msg)
        if self.kind == "angle":
            if self.second is None and self.first.point != "whole":
                msg = "angle single reference must use whole geometry"
                raise ValueError(msg)
            if second is not None and (
                (self.first.point == "whole") != (second.point == "whole")
            ):
                msg = "angle references must both select points or use whole geometry"
                raise ValueError(msg)


class SketchValidation(BaseModel):
    """Acceptance policy enforced before committing a new sketch."""

    model_config = ConfigDict(extra="forbid")

    require_fully_constrained: bool = False
    require_closed_profiles: bool = False
    reject_solver_errors: bool = True


_FEATURE_VALIDATION_TEMPLATE = """
created_feature = __FEATURE__
created_body = __BODY__
feature_shape = getattr(created_feature, "Shape", None)
validation_errors = []
feature_state = list(getattr(created_feature, "State", []))
if "Invalid" in feature_state or "Error" in feature_state:
    validation_errors.append(
        "Feature state is invalid: %s" % feature_state
    )
if "Touched" in feature_state:
    validation_errors.append("Feature still needs recompute")
if feature_shape is None or feature_shape.isNull():
    validation_errors.append("Feature has no result shape")
elif not feature_shape.isValid():
    validation_errors.append("Feature result shape is invalid")
elif len(feature_shape.Solids) != 1:
    validation_errors.append(
        "Feature must contain exactly one solid; found %d"
        % len(feature_shape.Solids)
    )

if created_body is not None:
    body_state = list(getattr(created_body, "State", []))
    body_shape = getattr(created_body, "Shape", None)
    if "Invalid" in body_state or "Error" in body_state:
        validation_errors.append("Body state is invalid: %s" % body_state)
    if "Touched" in body_state:
        validation_errors.append("Body still needs recompute")
    if body_shape is None or body_shape.isNull():
        validation_errors.append("Body has no result shape")
    elif not body_shape.isValid():
        validation_errors.append("Body result shape is invalid")
    elif len(body_shape.Solids) != 1:
        validation_errors.append(
            "PartDesign Body must contain exactly one solid; found %d"
            % len(body_shape.Solids)
        )
    if getattr(created_body, "Tip", None) is not created_feature:
        validation_errors.append("Created feature is not the Body tip")
if validation_errors:
    raise RuntimeError(
        "VALIDATION_FAILED: Feature validation failed: %s"
        % validation_errors
    )
"""


_SUBTRACTIVE_INPUT_VALIDATION = """
if not hasattr(body, "Shape") or body.Shape.isNull():
    raise RuntimeError(
        "VALIDATION_FAILED: Subtractive feature requires an existing solid"
    )
if not body.Shape.isValid() or len(body.Shape.Solids) != 1:
    raise RuntimeError(
        "VALIDATION_FAILED: Subtractive feature requires one valid input solid"
    )
input_volume = float(body.Shape.Volume)
"""


_ADDITIVE_INPUT_VALIDATION = """
input_shape = getattr(body, "Shape", None)
if input_shape is None or input_shape.isNull():
    input_volume = 0.0
elif not input_shape.isValid() or len(input_shape.Solids) != 1:
    raise RuntimeError(
        "VALIDATION_FAILED: Additive feature requires an empty Body "
        "or one valid input solid"
    )
else:
    input_volume = float(input_shape.Volume)
"""


_MATERIAL_ADDITION_VALIDATION = """
added_volume = float(feature_shape.Volume) - input_volume
volume_tolerance = max(1e-9, abs(input_volume) * 1e-9)
if added_volume <= volume_tolerance:
    raise RuntimeError(
        "VALIDATION_FAILED: Additive feature added no material "
        "(input volume %.12g, result volume %.12g)"
        % (input_volume, float(feature_shape.Volume))
    )
"""


_MATERIAL_REMOVAL_VALIDATION = """
shape = feature_shape
removed_volume = input_volume - float(shape.Volume)
volume_tolerance = max(1e-9, abs(input_volume) * 1e-9)
if removed_volume <= volume_tolerance:
    raise RuntimeError(
        "VALIDATION_FAILED: Subtractive feature removed no material "
        "(input volume %.12g, result volume %.12g)"
        % (input_volume, float(shape.Volume))
    )
"""


_FEATURE_RESULT_TEMPLATE = """
import uuid

revision = document_revision(doc)
shape = created_feature.Shape
shape_summary = {
    "valid": bool(shape.isValid()),
    "solid_count": len(shape.Solids),
    "face_count": len(shape.Faces),
    "edge_count": len(shape.Edges),
    "volume": float(shape.Volume),
}
body_summary = None
if created_body is not None:
    body_shape = created_body.Shape
    body_summary = {
        "name": created_body.Name,
        "solid_count": len(body_shape.Solids),
        "volume": float(body_shape.Volume),
    }
body_tip = None
result_solid_count = len(shape.Solids)
if created_body is not None:
    body_tip = (
        created_body.Tip.Name
        if getattr(created_body, "Tip", None) is not None
        else None
    )
    result_solid_count = len(created_body.Shape.Solids)
_result_ = {
    "document_ref": {"name": doc.Name, "revision": revision},
    "operation_id": "op_" + uuid.uuid4().hex[:12],
    "objects": [
        {
            "name": created_feature.Name,
            "label": created_feature.Label,
            "type_id": created_feature.TypeId,
        }
    ],
    "topology_refs": [],
    "name": created_feature.Name,
    "label": created_feature.Label,
    "type_id": created_feature.TypeId,
    "body": body_summary,
    "shape": shape_summary,
    "validation": {
        "valid": True,
        "recompute": "valid",
        "body_tip": body_tip,
        "solid_count": result_solid_count,
        "errors": [],
    },
    "warnings": list(feature_warnings),
    "next_inputs": {
        "feature_name": created_feature.Name,
        "object_name": created_feature.Name,
        "body_name": created_body.Name if created_body is not None else None,
    },
}
"""


_SUBTRACTIVE_RESIDUAL_CHECK = """
try:
    import Part as _Part

    _profile_faces = []
    for _wire in sketch.Shape.Wires:
        if _wire.isClosed():
            _profile_faces.append(_Part.Face(_wire))
    if _profile_faces and feature_shape is not None and not feature_shape.isNull():
        _sketch_placement = sketch.getGlobalPlacement()
        _plane_normal = _sketch_placement.Rotation.multVec(FreeCAD.Vector(0, 0, 1))
        _near_direction = (
            _plane_normal.negative()
            if getattr(created_feature, "Reversed", False)
            else _plane_normal
        )
        _probe_depth = float(feature_shape.BoundBox.DiagonalLength) or 1.0
        _residual_volume = 0.0
        _residual_depth = 0.0
        for _profile_face in _profile_faces:
            _near_prism = _profile_face.extrude(_near_direction * _probe_depth)
            _residue = feature_shape.common(_near_prism)
            if _residue.isNull():
                continue
            _residual_volume += float(_residue.Volume)
            for _vertex in _residue.Vertexes:
                _reach = (_vertex.Point - _sketch_placement.Base).dot(_near_direction)
                if _reach > _residual_depth:
                    _residual_depth = _reach
        _residual_tolerance = max(1e-9, float(feature_shape.Volume) * 1e-9)
        if _residual_volume > _residual_tolerance:
            feature_warnings.append(
                "Cut '%s' left %.6g mm^3 of material in front of its own sketch "
                "plane, reaching up to %.6g mm past it. A cut that starts at the "
                "sketch plane cannot remove material lying in front of that plane, "
                "so the opening keeps a thin web instead of cutting cleanly "
                "through. This happens when the sketch plane is offset to a curved "
                "or tapered wall at one height only. Use type='ThroughAll', set "
                "Reversed to cut the other way, or move the sketch plane clear of "
                "the solid, then inspect the opening with get_screenshot."
                % (created_feature.Name, _residual_volume, _residual_depth)
            )
except Exception as _residual_error:
    feature_warnings.append(
        "Residual-material check did not run for this cut: %s" % (_residual_error,)
    )
"""


def _subtractive_residual_check() -> str:
    """Warn when a sketch-driven cut cannot reach its own near side.

    Scoped to linear cuts driven by a sketch profile, where "in front of the
    sketch plane" is well defined. Advisory only: a cut that is otherwise valid
    is never rejected for this.
    """
    return _SUBTRACTIVE_RESIDUAL_CHECK


def _feature_validation_code(
    feature_variable: str,
    body_variable: str = "body",
    *,
    require_material_addition: bool = False,
    require_material_removal: bool = False,
) -> str:
    """Build embedded FreeCAD validation for one newly created feature."""
    code = _FEATURE_VALIDATION_TEMPLATE.replace(
        "__FEATURE__", feature_variable
    ).replace("__BODY__", body_variable)
    if require_material_addition:
        code += _MATERIAL_ADDITION_VALIDATION
    if require_material_removal:
        code += _MATERIAL_REMOVAL_VALIDATION
    return code


def _feature_result_code() -> str:
    """Build the common downstream-ready result for a validated feature."""
    return _FEATURE_RESULT_TEMPLATE


def _validate_expected_revision(expected_revision: str | None) -> None:
    """Reject ambiguous revision preconditions before bridge execution."""
    if expected_revision is not None and not expected_revision.strip():
        msg = "Expected revision must not be empty"
        raise WorkflowToolError("INVALID_INPUT", msg)


def _validate_edge_names(edges: list[str] | None) -> None:
    """Reject malformed native edge references before opening a transaction."""
    if edges is None:
        return
    if not edges:
        msg = "Edges must be omitted to select all edges, not an empty list"
        raise WorkflowToolError("INVALID_INPUT", msg)
    if len(edges) != len(set(edges)):
        msg = "Edge names must not contain duplicates"
        raise WorkflowToolError("INVALID_INPUT", msg)
    for edge in edges:
        suffix = edge.removeprefix("Edge")
        if not edge.startswith("Edge") or not suffix.isdigit() or int(suffix) < 1:
            msg = f"Invalid edge name: {edge}"
            raise WorkflowToolError("INVALID_INPUT", msg)


def _validate_constraint_point_roles(
    entities: list[SketchEntity], constraints: list[SketchConstraint]
) -> None:
    """Validate native Sketcher point positions for each geometry kind."""
    aliases: dict[str, str] = {}
    kinds: dict[str, str] = {}
    for entity in entities:
        kinds[entity.id] = entity.kind
        if entity.kind == "rectangle":
            for edge in ("bottom", "right", "top", "left"):
                aliases[f"{entity.id}.{edge}"] = "line"

    allowed: dict[str, set[SketchReferencePoint]] = {
        "line": {"whole", "start", "end"},
        "circle": {"whole", "center"},
        "arc": {"whole", "center", "start", "end"},
        "point": {"whole", "start", "position"},
    }

    for constraint in constraints:
        for reference in (constraint.first, constraint.second):
            if reference is None or isinstance(reference.entity, int):
                continue
            kind = aliases.get(reference.entity, kinds.get(reference.entity))
            if kind is None:
                continue
            if reference.point not in allowed[kind]:
                msg = (
                    f"{kind} does not support point role {reference.point} "
                    f"for reference {reference.entity!r}"
                )
                raise WorkflowToolError("INVALID_INPUT", msg)


_GRANULAR_CONSTRAINT_TYPES = frozenset(
    {
        "Coincident",
        "Horizontal",
        "Vertical",
        "Parallel",
        "Perpendicular",
        "Tangent",
        "Equal",
        "Symmetric",
        "Block",
        "PointOnObject",
        "Distance",
        "DistanceX",
        "DistanceY",
        "Radius",
        "Diameter",
        "Angle",
    }
)


def _validate_granular_constraint_basics(
    sketch_name: str,
    constraint_type: str,
    point1: int,
    point2: int,
    point3: int,
) -> None:
    """Validate the common granular constraint vocabulary and point IDs."""
    if not sketch_name:
        raise WorkflowToolError("INVALID_INPUT", "Sketch name must not be empty")
    if constraint_type not in _GRANULAR_CONSTRAINT_TYPES:
        msg = f"Unknown constraint type: {constraint_type}"
        raise WorkflowToolError("INVALID_INPUT", msg)
    if point1 not in {-1, 1, 2, 3} or point2 not in {-1, 1, 2, 3}:
        msg = "Constraint point positions must be -1, 1, 2, or 3"
        raise WorkflowToolError("INVALID_INPUT", msg)
    if point3 not in {-1, 1, 2, 3}:
        msg = "Third point position must be -1, 1, 2, or 3"
        raise WorkflowToolError("INVALID_INPUT", msg)


def _validate_granular_geometric_references(
    constraint_type: str,
    geometry2: int,
    point1: int,
    point2: int,
    geometry3: int,
) -> None:
    """Validate native overload selection for geometric constraints."""
    if constraint_type in {"Horizontal", "Vertical", "Block"} and point1 != -1:
        msg = f"{constraint_type} requires whole geometry"
        raise WorkflowToolError("INVALID_INPUT", msg)
    if constraint_type in {"Parallel", "Equal"} and (
        geometry2 == -2 or point1 != -1 or point2 != -1
    ):
        msg = f"{constraint_type} requires two whole geometries"
        raise WorkflowToolError("INVALID_INPUT", msg)
    if constraint_type in {"Perpendicular", "Tangent"} and geometry2 == -2:
        msg = f"{constraint_type} requires a second geometry"
        raise WorkflowToolError("INVALID_INPUT", msg)
    if constraint_type == "Coincident" and (
        geometry2 == -2 or point1 < 0 or point2 < 0
    ):
        msg = "Coincident requires two point positions"
        raise WorkflowToolError("INVALID_INPUT", msg)
    if constraint_type == "PointOnObject" and (
        geometry2 == -2 or point1 < 0 or point2 != -1
    ):
        msg = "PointOnObject requires one point and one whole geometry"
        raise WorkflowToolError("INVALID_INPUT", msg)
    if constraint_type == "Symmetric" and (
        point1 < 0 or geometry2 == -2 or point2 < 0 or geometry3 == -2
    ):
        msg = "Symmetric requires two points and a symmetry geometry"
        raise WorkflowToolError("INVALID_INPUT", msg)


def _validate_granular_dimensional_references(
    constraint_type: str,
    geometry2: int,
    point1: int,
    point2: int,
    value: float | None,
) -> None:
    """Validate native overload selection for dimensional constraints."""
    dimensional = {
        "Distance",
        "DistanceX",
        "DistanceY",
        "Radius",
        "Diameter",
        "Angle",
    }
    if constraint_type in dimensional and value is None:
        msg = f"{constraint_type} constraint requires a value"
        raise WorkflowToolError("INVALID_INPUT", msg)
    if constraint_type not in dimensional and value is not None:
        msg = f"{constraint_type} does not accept a dimensional value"
        raise WorkflowToolError("INVALID_INPUT", msg)
    if constraint_type in {"Radius", "Diameter"} and (geometry2 != -2 or point1 != -1):
        msg = f"{constraint_type} requires one whole geometry"
        raise WorkflowToolError("INVALID_INPUT", msg)
    if constraint_type in {"DistanceX", "DistanceY"} and (
        geometry2 >= 0 and (point1 < 0 or point2 < 0)
    ):
        msg = f"{constraint_type} two-reference form requires two points"
        raise WorkflowToolError("INVALID_INPUT", msg)
    if constraint_type == "Distance" and geometry2 == -2 and point1 >= 0:
        msg = "Distance does not support a single point-to-origin form"
        raise WorkflowToolError("INVALID_INPUT", msg)
    if constraint_type == "Angle" and geometry2 >= 0:
        point_form = point1 >= 0 and point2 >= 0
        whole_form = point1 == -1 and point2 == -1
        if not point_form and not whole_form:
            msg = "Angle references must both be points or whole geometries"
            raise WorkflowToolError("INVALID_INPUT", msg)


def register_partdesign_tools(
    mcp: Any, get_bridge: Callable[[], Awaitable[Any]]
) -> None:
    """Register PartDesign-related tools with the Robust MCP Server.

    Args:
        mcp: The FastMCP (Robust MCP Server) instance.
        get_bridge: Async function to get the active bridge.
    """

    @mcp.tool()
    async def create_partdesign_body(
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a new PartDesign Body.

        A PartDesign Body is a container for feature-based modeling that
        maintains a single solid shape through a sequence of operations.

        Args:
            name: Body name. Auto-generated if None.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with created body information:
                - name: Body name
                - label: Body label
                - type_id: Object type
        """
        bridge = await get_bridge()
        obj = await bridge.create_object("PartDesign::Body", name, None, doc_name)
        return {
            "name": obj.name,
            "label": obj.label,
            "type_id": obj.type_id,
        }

    @mcp.tool()
    async def create_sketch(
        body_name: str | None = None,
        plane: str = "XY_Plane",
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a new Sketch attached to an Origin plane, datum, or Body face.

        Args:
            body_name: Name of PartDesign Body to attach to. Creates standalone if None.
            plane: Support to attach the sketch to. Options:
                - "XY_Plane" - Horizontal plane
                - "XZ_Plane" - Front vertical plane
                - "YZ_Plane" - Side vertical plane
                - Name of a `PartDesign::Plane` datum in the document
                - Face name like "Face1" to attach to body face
            name: Sketch name. Auto-generated if None.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with created sketch information:
                - name: Sketch name
                - label: Sketch label
                - type_id: Object type
                - support: What the sketch is attached to
        """
        bridge = await get_bridge()

        code = f"""
requested_doc_name = {doc_name!r}
doc = (
    FreeCAD.ActiveDocument
    if requested_doc_name is None
    else FreeCAD.getDocument(requested_doc_name)
)
if doc is None:
    doc = FreeCAD.newDocument("Unnamed")

sketch_name = {name!r} or "Sketch"

if {body_name!r}:
    body = doc.getObject({body_name!r})
    if body is None:
        raise ValueError(f"Body not found: {body_name!r}")

    # Add sketch to body
    sketch = body.newObject("Sketcher::SketchObject", sketch_name)

    # Attach through the native FreeCAD 1.0+ support property.
    plane = {plane!r}
    if plane in ["XY_Plane", "XZ_Plane", "YZ_Plane"]:
        plane_obj = body.Origin.getObject(plane)
        sketch.AttachmentSupport = [(plane_obj, "")]
        sketch.MapMode = "FlatFace"
    elif plane.startswith("Face"):
        # Attach to face
        sketch.AttachmentSupport = [(body, plane)]
        sketch.MapMode = "FlatFace"
    else:
        support_obj = doc.getObject(plane)
        if support_obj is None or support_obj.TypeId != "PartDesign::Plane":
            raise ValueError(f"Unsupported sketch support: {{plane}}")
        sketch.AttachmentSupport = [(support_obj, "")]
        sketch.MapMode = "FlatFace"
else:
    # Standalone sketch
    sketch = doc.addObject("Sketcher::SketchObject", sketch_name)

    plane = {plane!r}
    if plane == "XY_Plane":
        sketch.Placement = FreeCAD.Placement(FreeCAD.Vector(0,0,0), FreeCAD.Rotation(0,0,0,1))
    elif plane == "XZ_Plane":
        sketch.Placement = FreeCAD.Placement(FreeCAD.Vector(0,0,0), FreeCAD.Rotation(FreeCAD.Vector(1,0,0), 90))
    elif plane == "YZ_Plane":
        sketch.Placement = FreeCAD.Placement(FreeCAD.Vector(0,0,0), FreeCAD.Rotation(FreeCAD.Vector(0,1,0), 90))
    else:
        raise ValueError(f"Unsupported standalone sketch plane: {{plane}}")

doc.recompute()

_result_ = {{
    "name": sketch.Name,
    "label": sketch.Label,
    "type_id": sketch.TypeId,
    "support": str(sketch.AttachmentSupport) if hasattr(sketch, "AttachmentSupport") else None,
}}
"""
        result = await bridge.execute_python(code, transaction="Create Sketch")
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Create sketch failed")

    @mcp.tool()
    async def create_constrained_sketch(
        body_name: str,
        sketch_name: str,
        entities: list[SketchEntity],
        constraints: list[SketchConstraint] | None = None,
        support: str = "XY_Plane",
        label: str | None = None,
        validation: SketchValidation | None = None,
        expected_revision: str | None = None,
        doc_name: str | None = None,
    ) -> ConstrainedSketchResult:
        """Create geometry, constraints, and expressions in one transaction.

        Entity and constraint IDs are request-local symbolic references. Rectangle
        edges are addressable as ``<id>.bottom``, ``<id>.right``, ``<id>.top``,
        and ``<id>.left``. Signed X/Y distances use end-minus-start for a whole
        line, the point coordinate from the origin for one reference, and
        second-minus-first for two point references. The response maps each
        symbolic ID to its native index and solver-adjusted geometry.

        Args:
            body_name: Existing PartDesign Body that will own the sketch.
            sketch_name: Internal name for the new sketch.
            entities: Typed line, circle, arc, point, and rectangle definitions.
            constraints: Geometric and dimensional constraint definitions.
            support: Origin plane, datum plane name, or Body face name.
            label: Optional display label. Defaults to the sketch name.
            validation: Solver and closed-profile acceptance policy.
            expected_revision: Optional revision returned by a prior workflow tool.
            doc_name: Target document. Uses the active document when omitted.

        Returns:
            Created sketch, symbolic index maps, solved geometry, solver state,
            warnings, and revision.
        """
        if not body_name or not sketch_name:
            msg = "Body and sketch names must not be empty"
            raise WorkflowToolError("INVALID_INPUT", msg)
        if not entities:
            msg = "At least one sketch entity is required"
            raise WorkflowToolError("INVALID_INPUT", msg)
        if not support:
            msg = "Sketch support must not be empty"
            raise WorkflowToolError("INVALID_INPUT", msg)
        if expected_revision is not None and not expected_revision.strip():
            msg = "Expected revision must not be empty"
            raise WorkflowToolError("INVALID_INPUT", msg)

        entity_ids = [entity.id for entity in entities]
        duplicate_entity_ids = sorted(
            entity_id
            for entity_id in set(entity_ids)
            if entity_ids.count(entity_id) > 1
        )
        if duplicate_entity_ids:
            msg = f"Duplicate sketch entity IDs: {duplicate_entity_ids}"
            raise WorkflowToolError("INVALID_INPUT", msg)

        constraint_list = constraints or []
        constraint_ids = [constraint.id for constraint in constraint_list]
        duplicate_constraint_ids = sorted(
            constraint_id
            for constraint_id in set(constraint_ids)
            if constraint_ids.count(constraint_id) > 1
        )
        if duplicate_constraint_ids:
            msg = f"Duplicate sketch constraint IDs: {duplicate_constraint_ids}"
            raise WorkflowToolError("INVALID_INPUT", msg)

        reference_ids: set[str] = set()
        for entity in entities:
            if isinstance(entity, SketchRectangle):
                reference_ids.update(
                    {
                        f"{entity.id}.bottom",
                        f"{entity.id}.right",
                        f"{entity.id}.top",
                        f"{entity.id}.left",
                    }
                )
            else:
                reference_ids.add(entity.id)
        for constraint in constraint_list:
            references = [constraint.first, constraint.second]
            missing = [
                reference.entity
                for reference in references
                if reference is not None and reference.entity not in reference_ids
            ]
            if missing:
                msg = f"Unknown sketch references in {constraint.id}: {missing}"
                raise WorkflowToolError("INVALID_INPUT", msg)
        _validate_constraint_point_roles(entities, constraint_list)

        entity_data = [entity.model_dump() for entity in entities]
        constraint_data = [constraint.model_dump() for constraint in constraint_list]
        validation_data = (validation or SketchValidation()).model_dump()
        bridge = await get_bridge()
        code = f"""
import math
import Part
import Sketcher
import uuid

{WORKFLOW_HELPERS}

requested_doc_name = {doc_name!r}
doc = (
    FreeCAD.ActiveDocument
    if requested_doc_name is None
    else FreeCAD.getDocument(requested_doc_name)
)
if doc is None:
    raise ValueError("NOT_FOUND: No active document")

expected_revision = {expected_revision!r}
require_expected_revision(doc, expected_revision)

body = doc.getObject({body_name!r})
if body is None or body.TypeId != "PartDesign::Body":
    raise ValueError("NOT_FOUND: PartDesign Body not found: " + {body_name!r})
if doc.getObject({sketch_name!r}) is not None:
    raise ValueError("INVALID_INPUT: Object already exists: " + {sketch_name!r})

entities = {entity_data!r}
constraints = {constraint_data!r}
policy = {validation_data!r}
require_fully_constrained = policy["require_fully_constrained"]
require_closed_profiles = policy["require_closed_profiles"]
reject_solver_errors = policy["reject_solver_errors"]

def vector_xy(vector):
    x = getattr(vector, "x", None)
    y = getattr(vector, "y", None)
    if x is None:
        x = getattr(vector, "X")
    if y is None:
        y = getattr(vector, "Y")
    return [float(x), float(y)]

def describe_solved_geometry(geometry_index):
    geometry = sketch.Geometry[geometry_index]
    details = {{
        "index": int(geometry_index),
        "type": type(geometry).__name__,
    }}
    for attribute, key in (
        ("StartPoint", "start"),
        ("EndPoint", "end"),
        ("Center", "center"),
        ("Location", "position"),
    ):
        try:
            details[key] = vector_xy(getattr(geometry, attribute))
        except Exception:
            pass
    if "position" not in details and hasattr(geometry, "X"):
        try:
            details["position"] = [float(geometry.X), float(geometry.Y)]
        except Exception:
            pass
    for attribute, key in (
        ("Radius", "radius"),
        ("MajorRadius", "major_radius"),
        ("MinorRadius", "minor_radius"),
        ("FirstParameter", "start_parameter"),
        ("LastParameter", "end_parameter"),
    ):
        try:
            details[key] = float(getattr(geometry, attribute))
        except Exception:
            pass
    try:
        bound_box = geometry.toShape().BoundBox
        details["bounds"] = {{
            "min_x": float(bound_box.XMin),
            "min_y": float(bound_box.YMin),
            "max_x": float(bound_box.XMax),
            "max_y": float(bound_box.YMax),
        }}
    except Exception:
        details["bounds"] = None
    return details

sketch = body.newObject("Sketcher::SketchObject", {sketch_name!r})
sketch.Label = {label!r} or {sketch_name!r}

support = {support!r}
if support in ("XY_Plane", "XZ_Plane", "YZ_Plane"):
    support_obj = body.Origin.getObject(support)
    sketch.AttachmentSupport = [(support_obj, "")]
    sketch.MapMode = "FlatFace"
elif support.startswith("Face"):
    sketch.AttachmentSupport = [(body, support)]
    sketch.MapMode = "FlatFace"
else:
    support_obj = doc.getObject(support)
    if support_obj is None or support_obj.TypeId != "PartDesign::Plane":
        raise ValueError("INVALID_INPUT: Unsupported sketch support: " + support)
    sketch.AttachmentSupport = [(support_obj, "")]
    sketch.MapMode = "FlatFace"

entity_indices = {{}}
entity_lookup = {{}}
generated_constraint_indices = {{}}
for entity in entities:
    entity_id = entity["id"]
    kind = entity["kind"]
    construction = entity["construction"]
    if kind == "line":
        geometry = Part.LineSegment(
            FreeCAD.Vector(*entity["start"], 0),
            FreeCAD.Vector(*entity["end"], 0),
        )
        index = int(sketch.addGeometry(geometry, construction))
        entity_indices[entity_id] = index
        entity_lookup[entity_id] = index
    elif kind == "circle":
        geometry = Part.Circle(
            FreeCAD.Vector(*entity["center"], 0),
            FreeCAD.Vector(0, 0, 1),
            entity["radius"],
        )
        index = int(sketch.addGeometry(geometry, construction))
        entity_indices[entity_id] = index
        entity_lookup[entity_id] = index
    elif kind == "arc":
        circle = Part.Circle(
            FreeCAD.Vector(*entity["center"], 0),
            FreeCAD.Vector(0, 0, 1),
            entity["radius"],
        )
        geometry = Part.ArcOfCircle(
            circle,
            math.radians(entity["start_angle"]),
            math.radians(entity["end_angle"]),
        )
        index = int(sketch.addGeometry(geometry, construction))
        entity_indices[entity_id] = index
        entity_lookup[entity_id] = index
    elif kind == "point":
        geometry = Part.Point(FreeCAD.Vector(*entity["position"], 0))
        index = int(sketch.addGeometry(geometry, construction))
        entity_indices[entity_id] = index
        entity_lookup[entity_id] = index
    elif kind == "rectangle":
        x, y = entity["origin"]
        width = entity["width"]
        height = entity["height"]
        points = [
            (x, y),
            (x + width, y),
            (x + width, y + height),
            (x, y + height),
        ]
        indices = []
        for point_index in range(4):
            start = points[point_index]
            end = points[(point_index + 1) % 4]
            geometry = Part.LineSegment(
                FreeCAD.Vector(*start, 0),
                FreeCAD.Vector(*end, 0),
            )
            indices.append(int(sketch.addGeometry(geometry, construction)))
        entity_indices[entity_id] = indices
        aliases = ("bottom", "right", "top", "left")
        for alias, index in zip(aliases, indices, strict=True):
            entity_lookup[entity_id + "." + alias] = index

        generated = []
        for point_index in range(4):
            current = indices[point_index]
            following = indices[(point_index + 1) % 4]
            generated.append(
                int(
                    sketch.addConstraint(
                        Sketcher.Constraint(
                            "Coincident", current, 2, following, 1
                        )
                    )
                )
            )
        generated.extend(
            [
                int(
                    sketch.addConstraint(
                        Sketcher.Constraint("Horizontal", indices[0])
                    )
                ),
                int(
                    sketch.addConstraint(
                        Sketcher.Constraint("Vertical", indices[1])
                    )
                ),
                int(
                    sketch.addConstraint(
                        Sketcher.Constraint("Horizontal", indices[2])
                    )
                ),
                int(
                    sketch.addConstraint(
                        Sketcher.Constraint("Vertical", indices[3])
                    )
                ),
            ]
        )
        generated_constraint_indices[entity_id] = generated
    else:
        raise ValueError("INVALID_INPUT: Unsupported sketch entity kind: " + kind)

point_positions = {{
    "start": 1,
    "end": 2,
    "center": 3,
    "position": 1,
    "whole": -1,
}}

def resolve_reference(reference):
    entity_id = reference["entity"]
    if entity_id not in entity_lookup:
        raise ValueError("INVALID_INPUT: Unknown sketch reference: " + entity_id)
    return entity_lookup[entity_id], point_positions[reference["point"]]

constraint_indices = {{}}
for definition in constraints:
    kind = definition["kind"]
    first_index, first_point = resolve_reference(definition["first"])
    second = definition["second"]
    if second is not None:
        second_index, second_point = resolve_reference(second)
    else:
        second_index, second_point = None, -1

    value = definition["value"]
    native_value = 1.0 if value is None else float(value)
    if kind == "coincident":
        if first_point < 0 or second_point < 0:
            raise ValueError(
                "INVALID_INPUT: Coincident references require endpoint positions"
            )
        constraint = Sketcher.Constraint(
            "Coincident",
            first_index,
            first_point,
            second_index,
            second_point,
        )
    elif kind in ("horizontal", "vertical", "block"):
        constraint = Sketcher.Constraint(kind.title(), first_index)
    elif kind in ("parallel", "equal"):
        constraint = Sketcher.Constraint(
            kind.title(), first_index, second_index
        )
    elif kind in ("perpendicular", "tangent"):
        constraint_type = kind.title()
        if first_point < 0 and second_point < 0:
            constraint = Sketcher.Constraint(
                constraint_type, first_index, second_index
            )
        elif first_point >= 0 and second_point < 0:
            constraint = Sketcher.Constraint(
                constraint_type, first_index, first_point, second_index
            )
        elif first_point >= 0 and second_point >= 0:
            constraint = Sketcher.Constraint(
                constraint_type,
                first_index,
                first_point,
                second_index,
                second_point,
            )
        else:
            constraint = Sketcher.Constraint(
                constraint_type, second_index, second_point, first_index
            )
    elif kind in ("radius", "diameter"):
        constraint = Sketcher.Constraint(kind.title(), first_index, native_value)
    elif kind == "distance":
        if second is not None:
            if first_point < 0 and second_point < 0:
                constraint = Sketcher.Constraint(
                    "Distance", first_index, second_index, native_value
                )
            elif first_point >= 0 and second_point < 0:
                constraint = Sketcher.Constraint(
                    "Distance",
                    first_index,
                    first_point,
                    second_index,
                    native_value,
                )
            elif first_point < 0 and second_point >= 0:
                constraint = Sketcher.Constraint(
                    "Distance",
                    second_index,
                    second_point,
                    first_index,
                    native_value,
                )
            else:
                constraint = Sketcher.Constraint(
                    "Distance",
                    first_index,
                    first_point,
                    second_index,
                    second_point,
                    native_value,
                )
        else:
            constraint = Sketcher.Constraint(
                "Distance", first_index, native_value
            )
    elif kind in ("distance_x", "distance_y"):
        constraint_type = "DistanceX" if kind == "distance_x" else "DistanceY"
        if second is not None:
            constraint = Sketcher.Constraint(
                constraint_type,
                first_index,
                first_point,
                second_index,
                second_point,
                native_value,
            )
        elif first_point >= 0:
            constraint = Sketcher.Constraint(
                constraint_type, first_index, first_point, native_value
            )
        else:
            constraint = Sketcher.Constraint(
                constraint_type, first_index, native_value
            )
    elif kind == "angle":
        angle = math.radians(native_value)
        if second is None:
            constraint = Sketcher.Constraint("Angle", first_index, angle)
        elif first_point >= 0:
            constraint = Sketcher.Constraint(
                "Angle",
                first_index,
                first_point,
                second_index,
                second_point,
                angle,
            )
        else:
            constraint = Sketcher.Constraint(
                "Angle", first_index, second_index, angle
            )
    elif kind == "point_on_object":
        if first_point < 0:
            raise ValueError(
                "INVALID_INPUT: Point-on-object requires a point position"
            )
        constraint = Sketcher.Constraint(
            "PointOnObject", first_index, first_point, second_index
        )
    else:
        raise ValueError(
            "INVALID_INPUT: Unsupported sketch constraint kind: " + kind
        )

    constraint_index = int(sketch.addConstraint(constraint))
    constraint_indices[definition["id"]] = constraint_index
    expression = definition["expression"]
    if expression is not None:
        sketch.setExpression(
            "Constraints[%d]" % constraint_index,
            expression,
        )

solver_status = int(sketch.solve())
doc.recompute()
degrees_of_freedom = (
    int(sketch.DoF)
    if hasattr(sketch, "DoF")
    else int(sketch.getLastDoF())
)
fully_constrained = bool(sketch.FullyConstrained)
if reject_solver_errors and solver_status != 0:
    raise RuntimeError(
        "SOLVER_CONFLICT: Sketch solver reported an error: %d"
        % solver_status
    )

wires = list(getattr(sketch.Shape, "Wires", []))
closed_profiles = sum(1 for wire in wires if wire.isClosed())
open_profiles = len(wires) - closed_profiles
if require_fully_constrained and not fully_constrained:
    raise RuntimeError(
        "SOLVER_CONFLICT: Sketch is not fully constrained: %d degrees of freedom"
        % degrees_of_freedom
    )
if require_closed_profiles and (not wires or open_profiles):
    raise RuntimeError(
        "VALIDATION_FAILED: Sketch does not contain only closed profiles: "
        "%d open, %d closed"
        % (open_profiles, closed_profiles)
    )

invalid_states = [
    {{"name": candidate.Name, "state": list(candidate.State)}}
    for candidate in (sketch, body)
    if (
        "Invalid" in candidate.State
        or "Error" in candidate.State
        or "Touched" in candidate.State
    )
]
if invalid_states:
    raise RuntimeError(
        "VALIDATION_FAILED: Created sketch is invalid: %s" % invalid_states
    )
warnings = []
if not fully_constrained:
    warnings.append(
        "Sketch is not fully constrained: %d degrees of freedom"
        % degrees_of_freedom
    )
if open_profiles:
    warnings.append("Sketch contains %d open profiles" % open_profiles)

solved_geometry = {{}}
for entity in entities:
    raw_indices = entity_indices[entity["id"]]
    indices = raw_indices if isinstance(raw_indices, list) else [raw_indices]
    geometry = [describe_solved_geometry(index) for index in indices]
    geometry_bounds = [
        item["bounds"] for item in geometry if item["bounds"] is not None
    ]
    bounds = None
    if geometry_bounds:
        bounds = {{
            "min_x": min(item["min_x"] for item in geometry_bounds),
            "min_y": min(item["min_y"] for item in geometry_bounds),
            "max_x": max(item["max_x"] for item in geometry_bounds),
            "max_y": max(item["max_y"] for item in geometry_bounds),
        }}
    solved_geometry[entity["id"]] = {{
        "kind": entity["kind"],
        "indices": [int(index) for index in indices],
        "geometry": geometry,
        "bounds": bounds,
    }}

_result_ = {{
    "document_ref": {{
        "name": doc.Name,
        "revision": document_revision(doc),
    }},
    "operation_id": "op_" + uuid.uuid4().hex[:12],
    "objects": [{{
        "name": sketch.Name,
        "label": sketch.Label,
        "type_id": sketch.TypeId,
    }}],
    "topology_refs": [],
    "name": sketch.Name,
    "label": sketch.Label,
    "type_id": sketch.TypeId,
    "entity_indices": entity_indices,
    "constraint_indices": constraint_indices,
    "generated_constraint_indices": generated_constraint_indices,
    "solved_geometry": solved_geometry,
    "geometry_count": int(sketch.GeometryCount),
    "constraint_count": int(sketch.ConstraintCount),
    "solver": {{
        "status": solver_status,
        "fully_constrained": fully_constrained,
        "degrees_of_freedom": degrees_of_freedom,
    }},
    "closed_profiles": closed_profiles,
    "validation": {{
        "valid": True,
        "recompute": "valid",
        "body_tip": body.Tip.Name if getattr(body, "Tip", None) else None,
        "solid_count": (
            len(body.Shape.Solids)
            if not body.Shape.isNull()
            else 0
        ),
        "errors": [],
    }},
    "warnings": warnings,
}}
"""
        result = await bridge.execute_python(
            code, transaction="Create Constrained Sketch"
        )
        if result.success:
            return result.result
        raise bridge_workflow_error(
            result.error_traceback, "Create constrained sketch failed"
        )

    @mcp.tool()
    async def add_sketch_rectangle(
        sketch_name: str,
        x: float,
        y: float,
        width: float,
        height: float,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Add a rectangle to a sketch.

        Args:
            sketch_name: Name of the sketch to add rectangle to.
            x: X coordinate of bottom-left corner.
            y: Y coordinate of bottom-left corner.
            width: Rectangle width.
            height: Rectangle height.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with geometry info:
                - geometry_indices: Indices of the four added lines
                - constraint_indices: Indices of the closure constraints
                - constraint_count: Number of constraints in sketch
                - geometry_count: Number of geometry elements
        """
        bridge = await get_bridge()

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

# Add rectangle
import Part
import Sketcher

x, y, w, h = {x}, {y}, {width}, {height}

# Add lines
sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(x, y, 0), FreeCAD.Vector(x+w, y, 0)), False)
sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(x+w, y, 0), FreeCAD.Vector(x+w, y+h, 0)), False)
sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(x+w, y+h, 0), FreeCAD.Vector(x, y+h, 0)), False)
sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(x, y+h, 0), FreeCAD.Vector(x, y, 0)), False)

# Add coincident constraints to close the rectangle
n = sketch.GeometryCount - 4
constraint_start = sketch.ConstraintCount
sketch.addConstraint(Sketcher.Constraint("Coincident", n, 2, n+1, 1))
sketch.addConstraint(Sketcher.Constraint("Coincident", n+1, 2, n+2, 1))
sketch.addConstraint(Sketcher.Constraint("Coincident", n+2, 2, n+3, 1))
sketch.addConstraint(Sketcher.Constraint("Coincident", n+3, 2, n, 1))

doc.recompute()

_result_ = {{
    "geometry_indices": list(range(n, n + 4)),
    "constraint_indices": list(
        range(constraint_start, constraint_start + 4)
    ),
    "constraint_count": sketch.ConstraintCount,
    "geometry_count": sketch.GeometryCount,
}}
"""
        result = await bridge.execute_python(code, transaction="Add Sketch Rectangle")
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Add rectangle failed")

    @mcp.tool()
    async def add_sketch_circle(
        sketch_name: str,
        center_x: float,
        center_y: float,
        radius: float,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Add a circle to a sketch.

        Args:
            sketch_name: Name of the sketch to add circle to.
            center_x: X coordinate of center.
            center_y: Y coordinate of center.
            radius: Circle radius.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with geometry info:
                - geometry_index: Index of the added circle
                - geometry_count: Total geometry elements
        """
        bridge = await get_bridge()

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

import Part

idx = sketch.addGeometry(Part.Circle(FreeCAD.Vector({center_x}, {center_y}, 0), FreeCAD.Vector(0,0,1), {radius}), False)
doc.recompute()

_result_ = {{
    "geometry_index": idx,
    "geometry_count": sketch.GeometryCount,
}}
"""
        result = await bridge.execute_python(code, transaction="Add Sketch Circle")
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Add circle failed")

    @mcp.tool()
    async def pad_sketch(
        sketch_name: str,
        length: float,
        symmetric: bool = False,
        reversed: bool = False,
        name: str | None = None,
        expected_revision: str | None = None,
        doc_name: str | None = None,
    ) -> FeatureMutationResult:
        """Create a Pad (extrusion) from a sketch.

        Args:
            sketch_name: Name of the sketch to pad.
            length: Pad length (extrusion distance).
            symmetric: Whether to extrude symmetrically. Defaults to False.
            reversed: Whether to reverse direction. Defaults to False.
            name: Pad feature name. Auto-generated if None.
            expected_revision: Optional revision returned by a prior workflow tool.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with created pad information:
                - name: Pad name
                - label: Pad label
                - type_id: Object type
        """
        if length <= 0:
            msg = "Pad length must be greater than zero"
            raise WorkflowToolError("INVALID_INPUT", msg)
        _validate_expected_revision(expected_revision)
        bridge = await get_bridge()

        code = f"""
{WORKFLOW_HELPERS}

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("NOT_FOUND: No active document")
expected_revision = {expected_revision!r}
current_revision = require_expected_revision(doc, expected_revision)
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

# Find the body containing this sketch
body = None
for obj in doc.Objects:
    if obj.TypeId == "PartDesign::Body":
        if hasattr(obj, "Group") and sketch in obj.Group:
            body = obj
            break

if body is None:
    raise ValueError("Sketch must be inside a PartDesign Body for Pad operation")

{_ADDITIVE_INPUT_VALIDATION}

pad_name = {name!r} or "Pad"
pad = body.newObject("PartDesign::Pad", pad_name)
pad.Profile = sketch
pad.Length = {length}
_symmetric = {symmetric}
if hasattr(pad, "SideType"):
    pad.SideType = "Symmetric" if _symmetric else "One side"
elif hasattr(pad, "Midplane"):
    pad.Midplane = _symmetric
else:
    pad.Symmetric = _symmetric
pad.Reversed = {reversed}

doc.recompute()
{_feature_validation_code("pad", require_material_addition=True)}
{_feature_result_code()}
"""
        result = await bridge.execute_python(code, transaction="Pad Sketch")
        if result.success:
            return result.result
        raise bridge_workflow_error(result.error_traceback, "Pad failed")

    @mcp.tool()
    async def pocket_sketch(
        sketch_name: str,
        length: float,
        type: str = "Length",
        name: str | None = None,
        expected_revision: str | None = None,
        doc_name: str | None = None,
    ) -> FeatureMutationResult:
        """Create a Pocket (cut extrusion) from a sketch.

        Args:
            sketch_name: Name of the sketch to pocket.
            length: Pocket depth.
            type: Pocket type: "Length", "ThroughAll", "UpToFirst", "UpToFace".
            name: Pocket feature name. Auto-generated if None.
            expected_revision: Optional revision returned by a prior workflow tool.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with created pocket information:
                - name: Pocket name
                - label: Pocket label
                - type_id: Object type
        """
        if length <= 0:
            msg = "Pocket length must be greater than zero"
            raise WorkflowToolError("INVALID_INPUT", msg)
        if type not in {"Length", "ThroughAll", "UpToFirst", "UpToFace"}:
            msg = f"Unsupported pocket type: {type}"
            raise WorkflowToolError("INVALID_INPUT", msg)
        _validate_expected_revision(expected_revision)
        bridge = await get_bridge()

        code = f"""
{WORKFLOW_HELPERS}

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("NOT_FOUND: No active document")
expected_revision = {expected_revision!r}
current_revision = require_expected_revision(doc, expected_revision)
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

# Find the body containing this sketch
body = None
for obj in doc.Objects:
    if obj.TypeId == "PartDesign::Body":
        if hasattr(obj, "Group") and sketch in obj.Group:
            body = obj
            break

if body is None:
    raise ValueError("Sketch must be inside a PartDesign Body for Pocket operation")

{_SUBTRACTIVE_INPUT_VALIDATION}

pocket_name = {name!r} or "Pocket"
pocket = body.newObject("PartDesign::Pocket", pocket_name)
pocket.Profile = sketch
pocket.Length = {length}
pocket.Type = {type!r}

doc.recompute()
{_feature_validation_code("pocket", require_material_removal=True)}
{_subtractive_residual_check()}
{_feature_result_code()}
"""
        result = await bridge.execute_python(code, transaction="Pocket Sketch")
        if result.success:
            return result.result
        raise bridge_workflow_error(result.error_traceback, "Pocket failed")

    @mcp.tool()
    async def fillet_edges(
        object_name: str,
        radius: float,
        edges: list[str] | None = None,
        name: str | None = None,
        expected_revision: str | None = None,
        doc_name: str | None = None,
    ) -> FeatureMutationResult:
        """Add fillet (rounded edges) to an object.

        Args:
            object_name: Name of the object to fillet.
            radius: Fillet radius.
            edges: List of edge names to fillet (e.g., ["Edge1", "Edge2"]).
                   Fillets all edges if None.
            name: Fillet feature name. Auto-generated if None.
            expected_revision: Optional revision returned by a prior workflow tool.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with created fillet information:
                - name: Fillet name
                - label: Fillet label
                - type_id: Object type
        """
        if not object_name:
            msg = "Object name must not be empty"
            raise WorkflowToolError("INVALID_INPUT", msg)
        if radius <= 0:
            msg = "Fillet radius must be greater than zero"
            raise WorkflowToolError("INVALID_INPUT", msg)
        _validate_edge_names(edges)
        _validate_expected_revision(expected_revision)
        bridge = await get_bridge()

        edges_param = edges

        code = f"""
{WORKFLOW_HELPERS}

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("NOT_FOUND: No active document")
expected_revision = {expected_revision!r}
current_revision = require_expected_revision(doc, expected_revision)
obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")
if not hasattr(obj, "Shape") or obj.Shape.isNull():
    raise ValueError("VALIDATION_FAILED: Object has no result shape")

# Check if this is in a PartDesign Body
body = None
for parent in doc.Objects:
    if parent.TypeId == "PartDesign::Body":
        if hasattr(parent, "Group") and obj in parent.Group:
            body = parent
            break

# Get selected edges (None means all edges)
selected_edges = {edges_param!r}
if selected_edges is not None:
    edge_count = len(obj.Shape.Edges)
    for edge_name in selected_edges:
        edge_index = int(edge_name.removeprefix("Edge"))
        if edge_index > edge_count:
            raise ValueError(
                "INVALID_INPUT: Edge reference is out of range: " + edge_name
            )

fillet_name = {name!r} or "Fillet"

if body:
    # PartDesign Fillet
    fillet = body.newObject("PartDesign::Fillet", fillet_name)
    if selected_edges is None:
        fillet.Base = (obj, [])
        fillet.UseAllEdges = True
    else:
        fillet.Base = (obj, selected_edges)
    fillet.Radius = {radius}
else:
    # Part Fillet
    fillet = doc.addObject("Part::Fillet", fillet_name)
    fillet.Base = obj

    if selected_edges:
        edge_list = [(int(e.replace("Edge", "")), {radius}, {radius}) for e in selected_edges]
    else:
        edge_list = [(i+1, {radius}, {radius}) for i in range(len(obj.Shape.Edges))]

    fillet.Edges = edge_list

doc.recompute()
{_feature_validation_code("fillet")}
{_feature_result_code()}
"""
        result = await bridge.execute_python(code, transaction="Fillet Edges")
        if result.success:
            return result.result
        raise bridge_workflow_error(result.error_traceback, "Fillet failed")

    @mcp.tool()
    async def chamfer_edges(
        object_name: str,
        size: float,
        edges: list[str] | None = None,
        name: str | None = None,
        expected_revision: str | None = None,
        doc_name: str | None = None,
    ) -> FeatureMutationResult:
        """Add chamfer (beveled edges) to an object.

        Args:
            object_name: Name of the object to chamfer.
            size: Chamfer size.
            edges: List of edge names to chamfer (e.g., ["Edge1", "Edge2"]).
                   Chamfers all edges if None.
            name: Chamfer feature name. Auto-generated if None.
            expected_revision: Optional revision returned by a prior workflow tool.
            doc_name: Document containing the object. Uses active document if None.

        Returns:
            Dictionary with created chamfer information:
                - name: Chamfer name
                - label: Chamfer label
                - type_id: Object type
        """
        if not object_name:
            msg = "Object name must not be empty"
            raise WorkflowToolError("INVALID_INPUT", msg)
        if size <= 0:
            msg = "Chamfer size must be greater than zero"
            raise WorkflowToolError("INVALID_INPUT", msg)
        _validate_edge_names(edges)
        _validate_expected_revision(expected_revision)
        bridge = await get_bridge()

        edges_param = edges

        code = f"""
{WORKFLOW_HELPERS}

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("NOT_FOUND: No active document")
expected_revision = {expected_revision!r}
current_revision = require_expected_revision(doc, expected_revision)
obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"Object not found: {object_name!r}")
if not hasattr(obj, "Shape") or obj.Shape.isNull():
    raise ValueError("VALIDATION_FAILED: Object has no result shape")

# Check if this is in a PartDesign Body
body = None
for parent in doc.Objects:
    if parent.TypeId == "PartDesign::Body":
        if hasattr(parent, "Group") and obj in parent.Group:
            body = parent
            break

# Get selected edges (None means all edges)
selected_edges = {edges_param!r}
if selected_edges is not None:
    edge_count = len(obj.Shape.Edges)
    for edge_name in selected_edges:
        edge_index = int(edge_name.removeprefix("Edge"))
        if edge_index > edge_count:
            raise ValueError(
                "INVALID_INPUT: Edge reference is out of range: " + edge_name
            )

chamfer_name = {name!r} or "Chamfer"

if body:
    # PartDesign Chamfer
    chamfer = body.newObject("PartDesign::Chamfer", chamfer_name)
    if selected_edges is None:
        chamfer.Base = (obj, [])
        chamfer.UseAllEdges = True
    else:
        chamfer.Base = (obj, selected_edges)
    chamfer.Size = {size}
else:
    # Part Chamfer
    chamfer = doc.addObject("Part::Chamfer", chamfer_name)
    chamfer.Base = obj

    if selected_edges:
        edge_list = [(int(e.replace("Edge", "")), {size}, {size}) for e in selected_edges]
    else:
        edge_list = [(i+1, {size}, {size}) for i in range(len(obj.Shape.Edges))]

    chamfer.Edges = edge_list

doc.recompute()
{_feature_validation_code("chamfer")}
{_feature_result_code()}
"""
        result = await bridge.execute_python(code, transaction="Chamfer Edges")
        if result.success:
            return result.result
        raise bridge_workflow_error(result.error_traceback, "Chamfer failed")

    @mcp.tool()
    async def revolution_sketch(
        sketch_name: str,
        angle: float = 360.0,
        axis: str = "Base_X",
        symmetric: bool = False,
        reversed: bool = False,
        name: str | None = None,
        expected_revision: str | None = None,
        doc_name: str | None = None,
    ) -> FeatureMutationResult:
        """Create a Revolution (rotational extrusion) from a sketch.

        Revolves the sketch profile around an axis to create a solid of revolution.

        Args:
            sketch_name: Name of the sketch to revolve.
            angle: Revolution angle in degrees. Defaults to 360.
            axis: Axis to revolve around. Options:
                - "Base_X" - X axis
                - "Base_Y" - Y axis
                - "Base_Z" - Z axis
                - "Sketch_V" - Sketch vertical axis
                - "Sketch_H" - Sketch horizontal axis
            symmetric: Whether to revolve symmetrically. Defaults to False.
            reversed: Whether to reverse direction. Defaults to False.
            name: Revolution feature name. Auto-generated if None.
            expected_revision: Optional revision returned by a prior workflow tool.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with created revolution information:
                - name: Revolution name
                - label: Revolution label
                - type_id: Object type
        """
        if not 0 < angle <= 360:
            msg = "Revolution angle must be greater than 0 and at most 360 degrees"
            raise WorkflowToolError("INVALID_INPUT", msg)
        if axis not in {"Base_X", "Base_Y", "Base_Z", "Sketch_V", "Sketch_H"}:
            msg = f"Unsupported revolution axis: {axis}"
            raise WorkflowToolError("INVALID_INPUT", msg)
        _validate_expected_revision(expected_revision)
        bridge = await get_bridge()

        code = f"""
{WORKFLOW_HELPERS}

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("NOT_FOUND: No active document")
expected_revision = {expected_revision!r}
current_revision = require_expected_revision(doc, expected_revision)
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

# Find the body containing this sketch
body = None
for obj in doc.Objects:
    if obj.TypeId == "PartDesign::Body":
        if hasattr(obj, "Group") and sketch in obj.Group:
            body = obj
            break

if body is None:
    raise ValueError("Sketch must be inside a PartDesign Body for Revolution operation")

{_ADDITIVE_INPUT_VALIDATION}

rev_name = {name!r} or "Revolution"
rev = body.newObject("PartDesign::Revolution", rev_name)
rev.Profile = sketch
rev.Angle = {angle}
_symmetric = {symmetric}
if hasattr(rev, "Midplane"):
    rev.Midplane = _symmetric
else:
    rev.Symmetric = _symmetric
rev.Reversed = {reversed}

# Set axis reference
axis_name = {axis!r}
if axis_name.startswith("Base_"):
    axis_ref = axis_name.replace("Base_", "")
    rev.ReferenceAxis = (body.Origin.getObject(f"{{axis_ref}}_Axis"), [""])
elif axis_name.startswith("Sketch_"):
    if axis_name == "Sketch_V":
        rev.ReferenceAxis = (sketch, ["V_Axis"])
    else:
        rev.ReferenceAxis = (sketch, ["H_Axis"])

doc.recompute()
{_feature_validation_code("rev", require_material_addition=True)}
{_feature_result_code()}
"""
        result = await bridge.execute_python(code, transaction="Revolution Sketch")
        if result.success:
            return result.result
        raise bridge_workflow_error(result.error_traceback, "Revolution failed")

    @mcp.tool()
    async def groove_sketch(
        sketch_name: str,
        angle: float = 360.0,
        axis: str = "Base_X",
        symmetric: bool = False,
        reversed: bool = False,
        name: str | None = None,
        expected_revision: str | None = None,
        doc_name: str | None = None,
    ) -> FeatureMutationResult:
        """Create a Groove (subtractive revolution) from a sketch.

        Revolves a sketch profile and subtracts it from existing material.

        Args:
            sketch_name: Name of the sketch to revolve.
            angle: Groove angle in degrees. Defaults to 360.
            axis: Axis to revolve around. Options:
                - "Base_X" - X axis
                - "Base_Y" - Y axis
                - "Base_Z" - Z axis
                - "Sketch_V" - Sketch vertical axis
                - "Sketch_H" - Sketch horizontal axis
            symmetric: Whether to revolve symmetrically. Defaults to False.
            reversed: Whether to reverse direction. Defaults to False.
            name: Groove feature name. Auto-generated if None.
            expected_revision: Optional revision returned by a prior workflow tool.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with created groove information:
                - name: Groove name
                - label: Groove label
                - type_id: Object type
        """
        if not 0 < angle <= 360:
            msg = "Groove angle must be greater than 0 and at most 360 degrees"
            raise WorkflowToolError("INVALID_INPUT", msg)
        if axis not in {"Base_X", "Base_Y", "Base_Z", "Sketch_V", "Sketch_H"}:
            msg = f"Unsupported groove axis: {axis}"
            raise WorkflowToolError("INVALID_INPUT", msg)
        _validate_expected_revision(expected_revision)
        bridge = await get_bridge()

        code = f"""
{WORKFLOW_HELPERS}

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("NOT_FOUND: No active document")
expected_revision = {expected_revision!r}
current_revision = require_expected_revision(doc, expected_revision)
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

# Find the body containing this sketch
body = None
for obj in doc.Objects:
    if obj.TypeId == "PartDesign::Body":
        if hasattr(obj, "Group") and sketch in obj.Group:
            body = obj
            break

if body is None:
    raise ValueError("Sketch must be inside a PartDesign Body for Groove operation")

{_SUBTRACTIVE_INPUT_VALIDATION}

groove_name = {name!r} or "Groove"
groove = body.newObject("PartDesign::Groove", groove_name)
groove.Profile = sketch
groove.Angle = {angle}
_symmetric = {symmetric}
if hasattr(groove, "Midplane"):
    groove.Midplane = _symmetric
else:
    groove.Symmetric = _symmetric
groove.Reversed = {reversed}

# Set axis reference
axis_name = {axis!r}
if axis_name.startswith("Base_"):
    axis_ref = axis_name.replace("Base_", "")
    groove.ReferenceAxis = (body.Origin.getObject(f"{{axis_ref}}_Axis"), [""])
elif axis_name.startswith("Sketch_"):
    if axis_name == "Sketch_V":
        groove.ReferenceAxis = (sketch, ["V_Axis"])
    else:
        groove.ReferenceAxis = (sketch, ["H_Axis"])

doc.recompute()
{_feature_validation_code("groove", require_material_removal=True)}
{_feature_result_code()}
"""
        result = await bridge.execute_python(code, transaction="Groove Sketch")
        if result.success:
            return result.result
        raise bridge_workflow_error(result.error_traceback, "Groove failed")

    @mcp.tool()
    async def create_hole(
        sketch_name: str,
        diameter: float = 6.0,
        depth: float = 10.0,
        hole_type: str = "Dimension",
        threaded: bool = False,
        thread_type: str = "ISO",
        thread_size: str = "M6",
        name: str | None = None,
        expected_revision: str | None = None,
        doc_name: str | None = None,
    ) -> FeatureMutationResult:
        """Create a Hole feature from a sketch containing point(s).

        Creates parametric holes with optional threading. The sketch should
        contain points defining hole center locations.

        Args:
            sketch_name: Name of the sketch with hole center point(s).
            diameter: Hole diameter (for non-threaded). Defaults to 6.0.
            depth: Hole depth. Defaults to 10.0.
            hole_type: Hole depth type. Options:
                - "Dimension" - Specific depth
                - "ThroughAll" - Through entire part
                - "UpToFirst" - Up to first face
            threaded: Whether hole is threaded. Defaults to False.
            thread_type: Thread standard. Options: "ISO", "UNC", "UNF".
            thread_size: Thread size (e.g., "M6", "M8", "#10", "1/4").
            name: Hole feature name. Auto-generated if None.
            expected_revision: Optional revision returned by a prior workflow tool.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with created hole information:
                - name: Hole name
                - label: Hole label
                - type_id: Object type
        """
        if diameter <= 0 or depth <= 0:
            msg = "Hole diameter and depth must be greater than zero"
            raise WorkflowToolError("INVALID_INPUT", msg)
        if hole_type not in {"Dimension", "ThroughAll", "UpToFirst"}:
            msg = f"Unsupported hole type: {hole_type}"
            raise WorkflowToolError("INVALID_INPUT", msg)
        if threaded and thread_type not in {"ISO", "UNC", "UNF"}:
            msg = f"Unsupported thread type: {thread_type}"
            raise WorkflowToolError("INVALID_INPUT", msg)
        _validate_expected_revision(expected_revision)
        bridge = await get_bridge()

        code = f"""
{WORKFLOW_HELPERS}

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("NOT_FOUND: No active document")
expected_revision = {expected_revision!r}
current_revision = require_expected_revision(doc, expected_revision)
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

# Find the body containing this sketch
body = None
for obj in doc.Objects:
    if obj.TypeId == "PartDesign::Body":
        if hasattr(obj, "Group") and sketch in obj.Group:
            body = obj
            break

if body is None:
    raise ValueError("Sketch must be inside a PartDesign Body for Hole operation")

{_SUBTRACTIVE_INPUT_VALIDATION}

hole_name = {name!r} or "Hole"
hole = body.newObject("PartDesign::Hole", hole_name)
hole.Profile = sketch
hole.Depth = {depth}

# Set hole type
hole_type = {hole_type!r}
if hole_type == "ThroughAll":
    hole.DepthType = 1
elif hole_type == "UpToFirst":
    hole.DepthType = 2
else:
    hole.DepthType = 0  # Dimension

# Set threading
if {threaded}:
    hole.Threaded = True
    hole.ThreadType = {thread_type!r}
    hole.ThreadSize = {thread_size!r}
else:
    hole.Threaded = False
    hole.Diameter = {diameter}

doc.recompute()
{_feature_validation_code("hole", require_material_removal=True)}
{_feature_result_code()}
"""
        result = await bridge.execute_python(code, transaction="Create Hole")
        if result.success:
            return result.result
        raise bridge_workflow_error(result.error_traceback, "Hole creation failed")

    @mcp.tool()
    async def linear_pattern(
        feature_name: str,
        direction: str = "X",
        length: float = 50.0,
        occurrences: int = 3,
        name: str | None = None,
        expected_revision: str | None = None,
        doc_name: str | None = None,
    ) -> FeatureMutationResult:
        """Create a Linear Pattern from a PartDesign feature.

        Repeats a feature in a linear direction.

        Args:
            feature_name: Name of the feature to pattern.
            direction: Pattern direction. Options: "X", "Y", "Z".
            length: Total pattern length. Defaults to 50.0.
            occurrences: Number of pattern instances. Defaults to 3.
            name: Pattern feature name. Auto-generated if None.
            expected_revision: Optional revision returned by a prior workflow tool.
            doc_name: Document containing the feature. Uses active document if None.

        Returns:
            Dictionary with created pattern information:
                - name: Pattern name
                - label: Pattern label
                - type_id: Object type
        """
        if direction not in {"X", "Y", "Z"}:
            msg = f"Unsupported linear pattern direction: {direction}"
            raise WorkflowToolError("INVALID_INPUT", msg)
        if length <= 0 or occurrences < 2:
            msg = "Linear pattern length must be positive and occurrences at least 2"
            raise WorkflowToolError("INVALID_INPUT", msg)
        _validate_expected_revision(expected_revision)
        bridge = await get_bridge()

        code = f"""
{WORKFLOW_HELPERS}

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("NOT_FOUND: No active document")
expected_revision = {expected_revision!r}
current_revision = require_expected_revision(doc, expected_revision)
feature = doc.getObject({feature_name!r})
if feature is None:
    raise ValueError(f"Feature not found: {feature_name!r}")

# Find the body containing this feature
body = None
for obj in doc.Objects:
    if obj.TypeId == "PartDesign::Body":
        if hasattr(obj, "Group") and feature in obj.Group:
            body = obj
            break

if body is None:
    raise ValueError("Feature must be inside a PartDesign Body")

pattern_name = {name!r} or "LinearPattern"
pattern = body.newObject("PartDesign::LinearPattern", pattern_name)
pattern.Originals = [feature]
pattern.Length = {length}
pattern.Occurrences = {occurrences}

# Set direction
dir_name = {direction!r}
pattern.Direction = (body.Origin.getObject(f"{{dir_name}}_Axis"), [""])
body.Tip = pattern

doc.recompute()
{_feature_validation_code("pattern")}
{_feature_result_code()}
"""
        result = await bridge.execute_python(code, transaction="Linear Pattern")
        if result.success:
            return result.result
        raise bridge_workflow_error(result.error_traceback, "Linear pattern failed")

    @mcp.tool()
    async def polar_pattern(
        feature_name: str,
        axis: str = "Z",
        angle: float = 360.0,
        occurrences: int = 6,
        name: str | None = None,
        expected_revision: str | None = None,
        doc_name: str | None = None,
    ) -> FeatureMutationResult:
        """Create a Polar (circular) Pattern from a PartDesign feature.

        Repeats a feature around an axis.

        Args:
            feature_name: Name of the feature to pattern.
            axis: Pattern axis. Options: "X", "Y", "Z".
            angle: Total pattern angle. Defaults to 360.0.
            occurrences: Number of pattern instances. Defaults to 6.
            name: Pattern feature name. Auto-generated if None.
            expected_revision: Optional revision returned by a prior workflow tool.
            doc_name: Document containing the feature. Uses active document if None.

        Returns:
            Dictionary with created pattern information:
                - name: Pattern name
                - label: Pattern label
                - type_id: Object type
        """
        if axis not in {"X", "Y", "Z"}:
            msg = f"Unsupported polar pattern axis: {axis}"
            raise WorkflowToolError("INVALID_INPUT", msg)
        if not 0 < angle <= 360 or occurrences < 2:
            msg = "Polar pattern angle must be in (0, 360] and occurrences at least 2"
            raise WorkflowToolError("INVALID_INPUT", msg)
        _validate_expected_revision(expected_revision)
        bridge = await get_bridge()

        code = f"""
{WORKFLOW_HELPERS}

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("NOT_FOUND: No active document")
expected_revision = {expected_revision!r}
current_revision = require_expected_revision(doc, expected_revision)
feature = doc.getObject({feature_name!r})
if feature is None:
    raise ValueError(f"Feature not found: {feature_name!r}")

# Find the body containing this feature
body = None
for obj in doc.Objects:
    if obj.TypeId == "PartDesign::Body":
        if hasattr(obj, "Group") and feature in obj.Group:
            body = obj
            break

if body is None:
    raise ValueError("Feature must be inside a PartDesign Body")

pattern_name = {name!r} or "PolarPattern"
pattern = body.newObject("PartDesign::PolarPattern", pattern_name)
pattern.Originals = [feature]
pattern.Angle = {angle}
pattern.Occurrences = {occurrences}

# Set axis
axis_name = {axis!r}
pattern.Axis = (body.Origin.getObject(f"{{axis_name}}_Axis"), [""])
body.Tip = pattern

doc.recompute()
{_feature_validation_code("pattern")}
{_feature_result_code()}
"""
        result = await bridge.execute_python(code, transaction="Polar Pattern")
        if result.success:
            return result.result
        raise bridge_workflow_error(result.error_traceback, "Polar pattern failed")

    @mcp.tool()
    async def mirrored_feature(
        feature_name: str,
        plane: str = "XY",
        name: str | None = None,
        expected_revision: str | None = None,
        doc_name: str | None = None,
    ) -> FeatureMutationResult:
        """Create a Mirrored feature from a PartDesign feature.

        Mirrors a feature across a plane.

        Args:
            feature_name: Name of the feature to mirror.
            plane: Mirror plane. Options: "XY", "XZ", "YZ".
            name: Mirrored feature name. Auto-generated if None.
            expected_revision: Optional revision returned by a prior workflow tool.
            doc_name: Document containing the feature. Uses active document if None.

        Returns:
            Dictionary with created mirror information:
                - name: Mirror name
                - label: Mirror label
                - type_id: Object type
        """
        plane_map = {
            "XY": "XY_Plane",
            "XZ": "XZ_Plane",
            "YZ": "YZ_Plane",
        }

        if plane not in plane_map:
            msg = f"Invalid plane: {plane}. Use: XY, XZ, YZ"
            raise WorkflowToolError("INVALID_INPUT", msg)

        plane_ref = plane_map[plane]
        _validate_expected_revision(expected_revision)
        bridge = await get_bridge()

        code = f"""
{WORKFLOW_HELPERS}

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("NOT_FOUND: No active document")
expected_revision = {expected_revision!r}
current_revision = require_expected_revision(doc, expected_revision)
feature = doc.getObject({feature_name!r})
if feature is None:
    raise ValueError(f"Feature not found: {feature_name!r}")

# Find the body containing this feature
body = None
for obj in doc.Objects:
    if obj.TypeId == "PartDesign::Body":
        if hasattr(obj, "Group") and feature in obj.Group:
            body = obj
            break

if body is None:
    raise ValueError("Feature must be inside a PartDesign Body")

mirror_name = {name!r} or "Mirrored"
mirror = body.newObject("PartDesign::Mirrored", mirror_name)
mirror.Originals = [feature]
mirror.MirrorPlane = (body.Origin.getObject({plane_ref!r}), [""])

doc.recompute()
{_feature_validation_code("mirror")}
{_feature_result_code()}
"""
        result = await bridge.execute_python(code, transaction="Mirrored Feature")
        if result.success:
            return result.result
        raise bridge_workflow_error(result.error_traceback, "Mirrored feature failed")

    @mcp.tool()
    async def add_sketch_line(
        sketch_name: str,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        construction: bool = False,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Add a line to a sketch.

        Args:
            sketch_name: Name of the sketch to add line to.
            x1: X coordinate of start point.
            y1: Y coordinate of start point.
            x2: X coordinate of end point.
            y2: Y coordinate of end point.
            construction: Whether this is a construction line. Defaults to False.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with geometry info:
                - geometry_index: Index of the added line
                - geometry_count: Total geometry elements
        """
        bridge = await get_bridge()

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

import Part

idx = sketch.addGeometry(
    Part.LineSegment(
        FreeCAD.Vector({x1}, {y1}, 0),
        FreeCAD.Vector({x2}, {y2}, 0)
    ),
    {construction}
)
doc.recompute()

_result_ = {{
    "geometry_index": idx,
    "geometry_count": sketch.GeometryCount,
}}
"""
        result = await bridge.execute_python(code, transaction="Add Sketch Line")
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Add line failed")

    @mcp.tool()
    async def add_sketch_arc(
        sketch_name: str,
        center_x: float,
        center_y: float,
        radius: float,
        start_angle: float,
        end_angle: float,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Add an arc to a sketch.

        Args:
            sketch_name: Name of the sketch to add arc to.
            center_x: X coordinate of center.
            center_y: Y coordinate of center.
            radius: Arc radius.
            start_angle: Start angle in degrees.
            end_angle: End angle in degrees.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with geometry info:
                - geometry_index: Index of the added arc
                - geometry_count: Total geometry elements
        """
        bridge = await get_bridge()

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

import Part
import math

center = FreeCAD.Vector({center_x}, {center_y}, 0)
start_rad = math.radians({start_angle})
end_rad = math.radians({end_angle})

arc = Part.ArcOfCircle(
    Part.Circle(center, FreeCAD.Vector(0, 0, 1), {radius}),
    start_rad,
    end_rad
)
idx = sketch.addGeometry(arc, False)
doc.recompute()

_result_ = {{
    "geometry_index": idx,
    "geometry_count": sketch.GeometryCount,
}}
"""
        result = await bridge.execute_python(code, transaction="Add Sketch Arc")
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Add arc failed")

    @mcp.tool()
    async def add_sketch_point(
        sketch_name: str,
        x: float,
        y: float,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Add a point to a sketch.

        Points are useful for defining hole centers and reference locations.

        Args:
            sketch_name: Name of the sketch to add point to.
            x: X coordinate.
            y: Y coordinate.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with geometry info:
                - geometry_index: Index of the added point
                - geometry_count: Total geometry elements
        """
        bridge = await get_bridge()

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

import Part

idx = sketch.addGeometry(Part.Point(FreeCAD.Vector({x}, {y}, 0)), False)
doc.recompute()

_result_ = {{
    "geometry_index": idx,
    "geometry_count": sketch.GeometryCount,
}}
"""
        result = await bridge.execute_python(code, transaction="Add Sketch Point")
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Add point failed")

    @mcp.tool()
    async def loft_sketches(
        sketch_names: list[str],
        ruled: bool = False,
        closed: bool = False,
        name: str | None = None,
        expected_revision: str | None = None,
        doc_name: str | None = None,
    ) -> FeatureMutationResult:
        """Create a Loft (additive) through multiple sketches.

        A loft creates a solid by connecting multiple profile sketches.

        Args:
            sketch_names: List of sketch names to loft through (in order).
            ruled: Whether to create ruled surfaces. Defaults to False.
            closed: Whether to close the loft. Defaults to False.
            name: Loft feature name. Auto-generated if None.
            expected_revision: Optional revision returned by a prior workflow tool.
            doc_name: Document containing the sketches. Uses active document if None.

        Returns:
            Dictionary with created loft information:
                - name: Loft name
                - label: Loft label
                - type_id: Object type
        """
        if len(sketch_names) < 2 or any(not sketch for sketch in sketch_names):
            msg = "Loft requires at least two non-empty sketch names"
            raise WorkflowToolError("INVALID_INPUT", msg)
        if len(sketch_names) != len(set(sketch_names)):
            msg = "Loft sketch names must not contain duplicates"
            raise WorkflowToolError("INVALID_INPUT", msg)
        _validate_expected_revision(expected_revision)
        bridge = await get_bridge()

        code = f"""
{WORKFLOW_HELPERS}

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("NOT_FOUND: No active document")
expected_revision = {expected_revision!r}
current_revision = require_expected_revision(doc, expected_revision)

sketches = []
for sname in {sketch_names!r}:
    sketch = doc.getObject(sname)
    if sketch is None:
        raise ValueError(f"Sketch not found: {{sname}}")
    sketches.append(sketch)

if len(sketches) < 2:
    raise ValueError("Loft requires at least 2 sketches")

# Find the body containing the first sketch
body = None
for obj in doc.Objects:
    if obj.TypeId == "PartDesign::Body":
        if hasattr(obj, "Group") and sketches[0] in obj.Group:
            body = obj
            break

if body is None:
    raise ValueError("Sketches must be inside a PartDesign Body for Loft operation")
if any(sketch not in body.Group for sketch in sketches):
    raise ValueError("INVALID_INPUT: All loft sketches must be in the same Body")

{_ADDITIVE_INPUT_VALIDATION}

loft_name = {name!r} or "Loft"
loft = body.newObject("PartDesign::AdditiveLoft", loft_name)
loft.Profile = sketches[0]
loft.Sections = sketches[1:]
loft.Ruled = {ruled}
loft.Closed = {closed}

doc.recompute()
{_feature_validation_code("loft", require_material_addition=True)}
{_feature_result_code()}
"""
        result = await bridge.execute_python(code, transaction="Loft Sketches")
        if result.success:
            return result.result
        raise bridge_workflow_error(result.error_traceback, "Loft failed")

    @mcp.tool()
    async def create_datum_plane(
        body_name: str,
        offset: float = 0.0,
        base_plane: str = "XY_Plane",
        name: str | None = None,
        doc_name: str | None = None,
        offset_expression: str | None = None,
        expected_revision: str | None = None,
    ) -> DatumPlaneResult:
        """Create a datum plane in a PartDesign body.

        Datum planes are reference planes used for sketching or measurements.

        Args:
            body_name: Name of the PartDesign body.
            offset: Offset distance from base plane. Defaults to 0.
            base_plane: Base plane to offset from. Options:
                - "XY_Plane" - Horizontal plane
                - "XZ_Plane" - Front vertical plane
                - "YZ_Plane" - Side vertical plane
            name: Datum plane name. Auto-generated if None.
            doc_name: Document containing the body. Uses active document if None.
            offset_expression: Optional expression for the native
                ``AttachmentOffset.Base.z`` property.
            expected_revision: Optional revision returned by a prior workflow tool.

        Returns:
            Dictionary with created datum information:
                - name: Datum name
                - label: Datum label
                - type_id: Object type
                - offset_expression: Bound offset expression, if any
        """
        if offset_expression is not None and not offset_expression.strip():
            raise WorkflowToolError(
                "INVALID_INPUT", "Offset expression must not be empty"
            )
        if not body_name:
            raise WorkflowToolError("INVALID_INPUT", "Body name must not be empty")
        if base_plane not in {"XY_Plane", "XZ_Plane", "YZ_Plane"}:
            msg = f"Unsupported base plane: {base_plane}"
            raise WorkflowToolError("INVALID_INPUT", msg)
        _validate_expected_revision(expected_revision)
        bridge = await get_bridge()

        code = f"""
import uuid

{WORKFLOW_HELPERS}

requested_doc_name = {doc_name!r}
doc = (
    FreeCAD.ActiveDocument
    if requested_doc_name is None
    else FreeCAD.getDocument(requested_doc_name)
)
if doc is None:
    raise ValueError("NOT_FOUND: No document found")

expected_revision = {expected_revision!r}
current_revision = require_expected_revision(doc, expected_revision)

body = doc.getObject({body_name!r})
if body is None:
    raise ValueError("NOT_FOUND: Body not found: " + {body_name!r})

datum_name = {name!r} or "DatumPlane"
datum = body.newObject("PartDesign::Plane", datum_name)

# Set reference plane
plane = {base_plane!r}
plane_obj = body.Origin.getObject(plane)
datum.AttachmentSupport = [(plane_obj, "")]
datum.MapMode = "FlatFace"
datum.MapPathParameter = 0
datum.MapReversed = False
datum.AttachmentOffset = FreeCAD.Placement(
    FreeCAD.Vector(0, 0, {offset}),
    FreeCAD.Rotation(0, 0, 0, 1)
)
offset_expression = {offset_expression!r}
if offset_expression is not None:
    datum.setExpression("AttachmentOffset.Base.z", offset_expression)

doc.recompute()
invalid_objects = [
    {{"name": candidate.Name, "state": list(candidate.State)}}
    for candidate in (datum, body)
    if (
        "Invalid" in candidate.State
        or "Error" in candidate.State
        or "Touched" in candidate.State
    )
]
if invalid_objects:
    raise RuntimeError(
        f"VALIDATION_FAILED: Recompute failed: {{invalid_objects}}"
    )
body_shape = getattr(body, "Shape", None)
solid_count = (
    len(body_shape.Solids)
    if body_shape is not None and not body_shape.isNull()
    else 0
)
_result_ = {{
    "document_ref": {{
        "name": doc.Name,
        "revision": document_revision(doc),
    }},
    "operation_id": "op_" + uuid.uuid4().hex[:12],
    "objects": [{{
        "name": datum.Name,
        "label": datum.Label,
        "type_id": datum.TypeId,
    }}],
    "topology_refs": [],
    "name": datum.Name,
    "label": datum.Label,
    "type_id": datum.TypeId,
    "offset_expression": offset_expression,
    "validation": {{
        "valid": True,
        "recompute": "valid",
        "body_tip": body.Tip.Name if getattr(body, "Tip", None) else None,
        "solid_count": solid_count,
        "errors": [],
    }},
    "warnings": [],
}}
"""
        result = await bridge.execute_python(code, transaction="Create Datum Plane")
        if result.success:
            return result.result
        raise bridge_workflow_error(result.error_traceback, "Create datum plane failed")

    @mcp.tool()
    async def add_sketch_constraint(
        sketch_name: str,
        constraint_type: str,
        geometry1: int,
        point1: int = -1,
        geometry2: int = -2,
        point2: int = -1,
        value: float | None = None,
        doc_name: str | None = None,
        geometry3: int = -2,
        point3: int = -1,
    ) -> dict[str, Any]:
        """Add a constraint to a sketch.

        This general interface supports the focused profile without requiring
        separate tools for each constraint type.

        Args:
            sketch_name: Name of the sketch.
            constraint_type: Type of constraint. Options:
                - Geometric: "Coincident", "Horizontal", "Vertical", "Parallel",
                  "Perpendicular", "Tangent", "Equal", "Symmetric", "Block"
                - Dimensional: "Distance", "DistanceX", "DistanceY", "Radius",
                  "Diameter", "Angle"
            geometry1: Index of first geometry element.
            point1: Point index on first geometry (1=start, 2=end, 3=center).
                    Use -1 for edge itself.
            geometry2: Index of second geometry element. Use -2 when unused.
            point2: Point index on second geometry.
            value: Value for dimensional constraints (distance, angle, etc.).
            doc_name: Document containing the sketch. Uses active document if None.
            geometry3: Symmetry line or point geometry for a Symmetric constraint.
            point3: Point on geometry3 for point symmetry. Leave unset for a line.

        Returns:
            Dictionary with constraint info:
                - constraint_index: Index of the added constraint
                - constraint_count: Total constraint count
        """
        _validate_granular_constraint_basics(
            sketch_name, constraint_type, point1, point2, point3
        )
        _validate_granular_geometric_references(
            constraint_type, geometry2, point1, point2, geometry3
        )
        _validate_granular_dimensional_references(
            constraint_type, geometry2, point1, point2, value
        )
        bridge = await get_bridge()

        code = f"""
import math
import Sketcher

{WORKFLOW_HELPERS}

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("NOT_FOUND: No active document")
sketch = doc.getObject({sketch_name!r})
if sketch is None or sketch.TypeId != "Sketcher::SketchObject":
    raise ValueError(f"Sketch not found: {sketch_name!r}")

if {geometry1} >= sketch.GeometryCount:
    raise ValueError("INVALID_INPUT: First geometry index is out of range")
if {geometry2} >= sketch.GeometryCount:
    raise ValueError("INVALID_INPUT: Second geometry index is out of range")
if {geometry3} >= sketch.GeometryCount:
    raise ValueError("INVALID_INPUT: Third geometry index is out of range")

ctype = {constraint_type!r}
g1, p1, g2, p2, g3, p3 = (
    {geometry1}, {point1}, {geometry2}, {point2}, {geometry3}, {point3}
)
value = {value!r}

# Build constraint based on type and parameters
if ctype in ["Horizontal", "Vertical", "Block"]:
    constraint = Sketcher.Constraint(ctype, g1)
elif ctype == "Coincident":
    constraint = Sketcher.Constraint(ctype, g1, p1, g2, p2)
elif ctype in ["Parallel", "Equal"]:
    constraint = Sketcher.Constraint(ctype, g1, g2)
elif ctype in ["Perpendicular", "Tangent"]:
    if p1 < 0 and p2 < 0:
        constraint = Sketcher.Constraint(ctype, g1, g2)
    elif p1 >= 0 and p2 < 0:
        constraint = Sketcher.Constraint(ctype, g1, p1, g2)
    elif p1 >= 0 and p2 >= 0:
        constraint = Sketcher.Constraint(ctype, g1, p1, g2, p2)
    else:
        constraint = Sketcher.Constraint(ctype, g2, p2, g1)
elif ctype == "PointOnObject":
    constraint = Sketcher.Constraint("PointOnObject", g1, p1, g2)
elif ctype == "Symmetric":
    if p1 < 0 or g2 < 0 or p2 < 0 or g3 < 0:
        raise ValueError(
            "Symmetric constraint requires two points and a symmetry line or point"
        )
    if p3 >= 0:
        constraint = Sketcher.Constraint(ctype, g1, p1, g2, p2, g3, p3)
    else:
        constraint = Sketcher.Constraint(ctype, g1, p1, g2, p2, g3)
elif ctype == "Distance":
    if g2 >= 0:
        if p1 < 0 and p2 < 0:
            constraint = Sketcher.Constraint(ctype, g1, g2, value)
        elif p1 >= 0 and p2 < 0:
            constraint = Sketcher.Constraint(ctype, g1, p1, g2, value)
        elif p1 < 0 and p2 >= 0:
            constraint = Sketcher.Constraint(ctype, g2, p2, g1, value)
        else:
            constraint = Sketcher.Constraint(ctype, g1, p1, g2, p2, value)
    else:
        constraint = Sketcher.Constraint(ctype, g1, value)
elif ctype in ["DistanceX", "DistanceY"]:
    if g2 >= 0:
        constraint = Sketcher.Constraint(ctype, g1, p1, g2, p2, value)
    elif p1 >= 0:
        constraint = Sketcher.Constraint(ctype, g1, p1, value)
    else:
        constraint = Sketcher.Constraint(ctype, g1, value)
elif ctype in ["Radius", "Diameter"]:
    if value is None:
        raise ValueError(f"{{ctype}} constraint requires a value")
    constraint = Sketcher.Constraint(ctype, g1, value)
elif ctype == "Angle":
    angle = math.radians(value)
    if g2 >= 0:
        if p1 >= 0:
            constraint = Sketcher.Constraint(ctype, g1, p1, g2, p2, angle)
        else:
            constraint = Sketcher.Constraint(ctype, g1, g2, angle)
    else:
        constraint = Sketcher.Constraint(ctype, g1, angle)
else:
    raise ValueError(f"Unknown constraint type: {{ctype}}")

idx = sketch.addConstraint(constraint)
doc.recompute()
_result_ = {{
    "constraint_index": idx,
    "constraint_count": sketch.ConstraintCount,
}}
"""
        result = await bridge.execute_python(code, transaction="Add Sketch Constraint")
        if result.success:
            return result.result
        raise bridge_workflow_error(result.error_traceback, "Add constraint failed")

    @mcp.tool()
    async def delete_sketch_geometry(
        sketch_name: str,
        geometry_index: int,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Delete a geometry element from a sketch.

        Args:
            sketch_name: Name of the sketch.
            geometry_index: Index of the geometry to delete.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with result:
                - success: Whether the deletion succeeded
                - geometry_count: Remaining geometry count
        """
        bridge = await get_bridge()

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

sketch.delGeometry({geometry_index})
doc.recompute()

_result_ = {{
    "success": True,
    "geometry_count": sketch.GeometryCount,
}}
"""
        result = await bridge.execute_python(code, transaction="Delete Sketch Geometry")
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Delete sketch geometry failed")

    @mcp.tool()
    async def delete_sketch_constraint(
        sketch_name: str,
        constraint_index: int,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Delete a constraint from a sketch.

        Args:
            sketch_name: Name of the sketch.
            constraint_index: Index of the constraint to delete.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with result:
                - success: Whether the deletion succeeded
                - constraint_count: Remaining constraint count
        """
        bridge = await get_bridge()

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

sketch.delConstraint({constraint_index})
doc.recompute()

_result_ = {{
    "success": True,
    "constraint_count": sketch.ConstraintCount,
}}
"""
        result = await bridge.execute_python(
            code, transaction="Delete Sketch Constraint"
        )
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Delete sketch constraint failed")

    @mcp.tool()
    async def get_sketch_info(
        sketch_name: str,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Get detailed information about a sketch.

        Args:
            sketch_name: Name of the sketch.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with sketch information:
                - name: Sketch name
                - geometry: Indexed geometry details
                - constraints: Indexed constraint details
                - expressions: Property paths and their expressions
                - geometry_count: Number of geometry elements
                - constraint_count: Number of constraints
                - external_geometry_count: Number of external geometry references
                - fully_constrained: Whether sketch is fully constrained
                - solver_status: Result of the latest solve
                - degrees_of_freedom: Remaining solver degrees of freedom
        """
        bridge = await get_bridge()

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

def vector_data(vector):
    return [float(vector.x), float(vector.y), float(vector.z)]

geometry = []
for index, item in enumerate(sketch.Geometry):
    details = {{
        "index": index,
        "type": getattr(item, "TypeId", type(item).__name__),
        "construction": bool(getattr(item, "Construction", False)),
    }}
    for attribute in ("StartPoint", "EndPoint", "Center", "Location"):
        value = getattr(item, attribute, None)
        if value is not None:
            details[attribute.lower()] = vector_data(value)
    for attribute in (
        "Radius",
        "MajorRadius",
        "MinorRadius",
        "FirstParameter",
        "LastParameter",
    ):
        value = getattr(item, attribute, None)
        if value is not None:
            details[attribute.lower()] = float(value)
    geometry.append(details)

driving_constraint_types = {{
    "Angle",
    "AngleViaPoint",
    "Diameter",
    "Distance",
    "DistanceX",
    "DistanceY",
    "Radius",
}}
constraints = []
for index, item in enumerate(sketch.Constraints):
    details = {{
        "index": index,
        "type": str(item.Type),
    }}
    for attribute in (
        "First",
        "FirstPos",
        "Second",
        "SecondPos",
        "Third",
        "ThirdPos",
    ):
        value = getattr(item, attribute, None)
        if value is not None:
            details[attribute.lower()] = int(value)
    value = getattr(item, "Value", None)
    if value is not None:
        try:
            details["value"] = float(value)
        except (TypeError, ValueError):
            details["value"] = str(value)
    details["driving"] = None
    if str(item.Type) in driving_constraint_types:
        try:
            details["driving"] = bool(sketch.getDriving(index))
        except Exception:
            pass
    constraints.append(details)

expressions = {{
    path: str(expression)
    for path, expression in getattr(sketch, "ExpressionEngine", [])
}}
solver_status = int(sketch.solve()) if hasattr(sketch, "solve") else None
degrees_of_freedom = (
    int(sketch.DoF)
    if hasattr(sketch, "DoF")
    else int(sketch.getLastDoF())
    if hasattr(sketch, "getLastDoF")
    else None
)
fully_constrained = (
    bool(sketch.FullyConstrained)
    if hasattr(sketch, "FullyConstrained")
    else None
)

_result_ = {{
    "name": sketch.Name,
    "label": sketch.Label,
    "geometry": geometry,
    "constraints": constraints,
    "expressions": expressions,
    "geometry_count": sketch.GeometryCount,
    "constraint_count": sketch.ConstraintCount,
    "external_geometry_count": sum(len(_s) for _, _s in sketch.ExternalGeometry),
    "fully_constrained": fully_constrained,
    "solver_status": solver_status,
    "degrees_of_freedom": degrees_of_freedom,
}}
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Get sketch info failed")

    @mcp.tool()
    async def toggle_construction(
        sketch_name: str,
        geometry_index: int,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Toggle construction mode for a sketch geometry.

        Construction geometry is used for reference but not included
        in the final sketch profile.

        Args:
            sketch_name: Name of the sketch.
            geometry_index: Index of the geometry to toggle.
            doc_name: Document containing the sketch. Uses active document if None.

        Returns:
            Dictionary with result:
                - success: Whether the operation succeeded
                - is_construction: New construction state
        """
        bridge = await get_bridge()

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
sketch = doc.getObject({sketch_name!r})
if sketch is None:
    raise ValueError(f"Sketch not found: {sketch_name!r}")

sketch.toggleConstruction({geometry_index})
doc.recompute()

# Check new state
geo = sketch.Geometry[{geometry_index}]
is_construction = geo.Construction if hasattr(geo, "Construction") else False

_result_ = {{
    "success": True,
    "is_construction": is_construction,
}}
"""
        result = await bridge.execute_python(code, transaction="Toggle Construction")
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Toggle construction failed")
