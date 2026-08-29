"""Tests for task-oriented workflow result and error contracts."""

from freecad_mcp.tools.workflow_results import (
    BindExpressionsResult,
    ConstrainedSketchResult,
    DatumPlaneResult,
    FeatureMutationResult,
    ObjectQueryResult,
    WorkflowToolError,
    bridge_workflow_error,
)


def test_mutation_result_schemas_share_required_contract() -> None:
    """Every representative mutation should expose the common result fields."""
    common = {
        "document_ref",
        "operation_id",
        "objects",
        "topology_refs",
        "validation",
        "warnings",
    }

    for model in (
        BindExpressionsResult,
        ConstrainedSketchResult,
        DatumPlaneResult,
        FeatureMutationResult,
    ):
        properties = set(model.model_json_schema()["properties"])
        assert common <= properties


def test_object_query_schema_is_explicitly_bounded() -> None:
    """The query output should expose page counts and a continuation cursor."""
    properties = set(ObjectQueryResult.model_json_schema()["properties"])

    assert {
        "document_ref",
        "items",
        "matched_count",
        "returned_count",
        "next_cursor",
        "truncated",
    } == properties


def test_bridge_error_preserves_stable_category_and_commit_state() -> None:
    """Embedded validation failures should remain machine-classifiable."""
    error = bridge_workflow_error(
        "RuntimeError: VALIDATION_FAILED: Body has two solids",
        "Mutation failed",
    )

    assert isinstance(error, WorkflowToolError)
    assert error.payload.category == "VALIDATION_FAILED"
    assert error.payload.transaction_committed is False
    assert str(error).startswith("VALIDATION_FAILED: committed=false:")


def test_bridge_error_preserves_a_post_commit_marker() -> None:
    """A generated reporting failure must disclose that mutation was committed."""
    error = bridge_workflow_error(
        "RuntimeError: BRIDGE_ERROR: TRANSACTION_COMMITTED:true: serialization failed",
        "Mutation failed",
    )

    assert error.payload.category == "BRIDGE_ERROR"
    assert error.payload.transaction_committed is True
    assert "TRANSACTION_COMMITTED" not in error.payload.message
    assert str(error).startswith("BRIDGE_ERROR: committed=true:")


def test_bridge_error_classifies_missing_objects() -> None:
    """Legacy embedded lookup messages should receive the NOT_FOUND category."""
    error = bridge_workflow_error("Feature not found: Pad", "Mutation failed")

    assert error.payload.category == "NOT_FOUND"
