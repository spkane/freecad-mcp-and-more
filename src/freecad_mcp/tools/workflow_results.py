"""Shared result and error contracts for task-oriented CAD tools."""

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class DocumentReference(BaseModel):
    """Identify one open document state."""

    model_config = ConfigDict(extra="forbid")

    name: str
    revision: str


class ObjectReference(BaseModel):
    """Identify a native FreeCAD object without implying stable topology."""

    model_config = ConfigDict(extra="allow")

    name: str
    label: str | None = None
    type_id: str | None = None


class MutationValidation(BaseModel):
    """Describe checks completed before a transaction was committed."""

    model_config = ConfigDict(extra="allow")

    valid: bool = True
    recompute: Literal["valid"] = "valid"
    body_tip: str | None = None
    solid_count: int | None = Field(default=None, ge=0)
    errors: list[str] = Field(default_factory=list)


class MutationResult(BaseModel):
    """Fields shared by successful task-oriented mutations."""

    model_config = ConfigDict(extra="allow")

    document_ref: DocumentReference
    operation_id: str
    objects: list[ObjectReference]
    topology_refs: list[dict[str, Any]] = Field(default_factory=list)
    validation: MutationValidation
    warnings: list[str] = Field(default_factory=list)


class AppliedExpressionBinding(BaseModel):
    """One expression target after a successful batch."""

    model_config = ConfigDict(extra="forbid")

    object_name: str
    property_path: str
    expression: str | None


class BindExpressionsResult(MutationResult):
    """Result of one atomic expression-binding batch."""

    bindings: list[AppliedExpressionBinding]


class SolverSummary(BaseModel):
    """Sketch solver state returned after recompute."""

    model_config = ConfigDict(extra="forbid")

    status: int
    fully_constrained: bool
    degrees_of_freedom: int | None


class ConstrainedSketchResult(MutationResult):
    """Result of declarative sketch creation."""

    name: str
    label: str
    type_id: str
    entity_indices: dict[str, int | list[int]]
    constraint_indices: dict[str, int]
    generated_constraint_indices: dict[str, list[int]]
    geometry_count: int = Field(ge=0)
    constraint_count: int = Field(ge=0)
    solver: SolverSummary
    closed_profiles: int = Field(ge=0)


class DatumPlaneResult(MutationResult):
    """Result of creating a revision-aware datum plane."""

    name: str
    label: str
    type_id: str
    offset_expression: str | None


class FeatureMutationResult(MutationResult):
    """Result of a validated PartDesign feature mutation."""

    name: str
    label: str
    type_id: str
    body: dict[str, Any] | None
    shape: dict[str, Any]
    next_inputs: dict[str, str | None]


class ObjectQueryResult(BaseModel):
    """One bounded page of document objects."""

    model_config = ConfigDict(extra="forbid")

    document_ref: DocumentReference
    items: list[dict[str, Any]]
    matched_count: int = Field(ge=0)
    returned_count: int = Field(ge=0)
    next_cursor: str | None
    truncated: bool


ToolErrorCategory = Literal[
    "INVALID_INPUT",
    "NOT_FOUND",
    "STALE_REVISION",
    "TRANSACTION_CONFLICT",
    "SOLVER_CONFLICT",
    "VALIDATION_FAILED",
    "BRIDGE_ERROR",
]


class ToolErrorPayload(BaseModel):
    """Stable failure metadata carried by a workflow tool exception."""

    model_config = ConfigDict(extra="forbid")

    category: ToolErrorCategory
    message: str
    transaction_committed: bool = False


class WorkflowToolError(ValueError):
    """Expose a stable category and transaction outcome through MCP errors."""

    def __init__(
        self,
        category: ToolErrorCategory,
        message: str,
        *,
        transaction_committed: bool = False,
    ) -> None:
        self.payload = ToolErrorPayload(
            category=category,
            message=message,
            transaction_committed=transaction_committed,
        )
        committed = str(transaction_committed).lower()
        super().__init__(f"{category}: committed={committed}: {message}")


def bridge_workflow_error(
    error_traceback: str | None, fallback_message: str
) -> WorkflowToolError:
    """Preserve a stable embedded category or classify a bridge failure."""
    message = error_traceback or fallback_message
    commit_match = re.search(
        r"TRANSACTION_COMMITTED\s*:\s*(true|false)\s*:?", message, re.IGNORECASE
    )
    transaction_committed = (
        commit_match is not None and commit_match.group(1).lower() == "true"
    )
    if commit_match is not None:
        message = (
            message[: commit_match.start()] + message[commit_match.end() :]
        ).strip()
    categories: tuple[ToolErrorCategory, ...] = (
        "STALE_REVISION",
        "TRANSACTION_CONFLICT",
        "SOLVER_CONFLICT",
        "VALIDATION_FAILED",
        "NOT_FOUND",
        "INVALID_INPUT",
    )
    for category in categories:
        if category in message:
            return WorkflowToolError(
                category,
                message,
                transaction_committed=transaction_committed,
            )
    normalized = message.lower()
    if "not found" in normalized or "no active document" in normalized:
        return WorkflowToolError(
            "NOT_FOUND",
            message,
            transaction_committed=transaction_committed,
        )
    invalid_input_markers = (
        "invalid ",
        "unsupported ",
        "must be ",
        "requires ",
        "out of range",
    )
    if any(marker in normalized for marker in invalid_input_markers):
        return WorkflowToolError(
            "INVALID_INPUT",
            message,
            transaction_committed=transaction_committed,
        )
    return WorkflowToolError(
        "BRIDGE_ERROR",
        message,
        transaction_committed=transaction_committed,
    )
