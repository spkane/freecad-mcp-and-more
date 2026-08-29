"""Tests for native FreeCAD variable and expression tools."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from freecad_mcp.bridge.base import ExecutionResult
from freecad_mcp.tools.variables import (
    ExpressionBinding,
    VariableDefinition,
    register_variable_tools,
)


@pytest.fixture
def mock_bridge() -> AsyncMock:
    """Create a mocked bridge for variable tool tests."""
    return AsyncMock()


@pytest.fixture
def register_tools(mock_bridge: AsyncMock) -> dict[str, object]:
    """Register variable tools and return them by name."""
    mcp = MagicMock()
    tools: dict[str, object] = {}

    def tool_decorator():
        def decorator(func):
            tools[func.__name__] = func
            return func

        return decorator

    mcp.tool = tool_decorator

    async def get_bridge() -> AsyncMock:
        return mock_bridge

    register_variable_tools(mcp, get_bridge)
    return tools


@pytest.mark.parametrize(
    ("definition", "message"),
    [
        ({"name": "height", "kind": "length", "value": 120}, "include units"),
        (
            {
                "name": "height",
                "kind": "length",
                "value": "120 mm",
                "expression": "base * 2",
            },
            "exactly one",
        ),
        ({"name": "height", "kind": "length"}, "exactly one"),
        (
            {"name": "height", "kind": "length", "value": "120 mm", "group": "Base"},
            "cannot be Base",
        ),
    ],
)
def test_variable_definition_rejects_ambiguous_or_untyped_values(
    definition: dict[str, object], message: str
) -> None:
    """Definitions should preserve units and one unambiguous value source."""
    with pytest.raises(ValueError, match=message):
        VariableDefinition.model_validate(definition)


def test_variable_definition_normalizes_group_name() -> None:
    """Variable groups should not retain accidental surrounding whitespace."""
    definition = VariableDefinition(
        name="height", kind="length", value="120 mm", group=" Dimensions "
    )

    assert definition.group == "Dimensions"


@pytest.mark.asyncio
async def test_define_variables_batches_values_and_expressions(
    register_tools: dict[str, object], mock_bridge: AsyncMock
) -> None:
    """Definitions should create a native VarSet in one transaction."""
    mock_bridge.execute_python.return_value = ExecutionResult(
        success=True,
        result={
            "name": "Variables",
            "type_id": "App::VarSet",
            "variables": [],
        },
        stdout="",
        stderr="",
        execution_time_ms=10.0,
    )

    define_variables = register_tools["define_variables"]
    result = await define_variables(  # type: ignore[operator]
        variable_set_name="Variables",
        variables=[
            VariableDefinition(name="tower_height", kind="length", value="120 mm"),
            VariableDefinition(
                name="tower_top_diameter",
                kind="length",
                expression="base_diameter * (1 - taper)",
            ),
        ],
        doc_name="Lighthouse",
        expected_revision="rev_1",
    )

    assert result["type_id"] == "App::VarSet"
    code = mock_bridge.execute_python.call_args.args[0]
    assert 'doc.addObject("App::VarSet", variable_set_name)' in code
    assert '"length": "App::PropertyLength"' in code
    assert "var_set.addProperty(" in code
    assert "Reserved App::VarSet property" in code
    assert "var_set.setExpression(name, expression)" in code
    assert 'open_owned_transaction(doc, "Define Variables")' in code
    assert "abort_owned_transaction(doc)" in code
    assert "candidate.Content" in code
    assert 'or "Touched" in candidate.State' in code
    assert "var_set.evalExpression(expression)" in code
    assert (
        "def describe_expression_error(definition: dict, error: Exception) -> dict:"
        in code
    )
    assert "def collect_expression_evaluation_errors(" in code
    assert "rejected_expression_names.add(name)" in code
    assert "definitions, rejected_expression_names" in code
    assert '"property_path": definition["name"]' in code
    assert '"expression": definition["expression"]' in code
    assert '"error": str(error)' in code
    assert "expression_diagnostics=%s" in code
    assert "VALIDATION_FAILED: Expression assignment failed" in code
    assert "VALIDATION_FAILED: Recompute failed" in code
    assert code.index('"variables": serialized') < code.index("doc.commitTransaction()")
    compile(code, "<define_variables>", "exec")


@pytest.mark.asyncio
async def test_define_variables_rejects_duplicate_names(
    register_tools: dict[str, object], mock_bridge: AsyncMock
) -> None:
    """A batch should not ambiguously define the same variable twice."""
    define_variables = register_tools["define_variables"]

    with pytest.raises(ValueError, match="Duplicate variable names"):
        await define_variables(  # type: ignore[operator]
            variable_set_name="Variables",
            variables=[
                VariableDefinition(name="height", kind="length", value="10 mm"),
                VariableDefinition(name="height", kind="length", value="20 mm"),
            ],
        )

    mock_bridge.execute_python.assert_not_called()


@pytest.mark.asyncio
async def test_define_variables_rejects_names_freecad_would_sanitize(
    register_tools: dict[str, object], mock_bridge: AsyncMock
) -> None:
    """Repeated calls must address one stable internal object name."""
    define_variables = register_tools["define_variables"]

    with pytest.raises(ValueError, match="valid FreeCAD internal name"):
        await define_variables(  # type: ignore[operator]
            variable_set_name="Model Variables",
            variables=[VariableDefinition(name="height", kind="length", value="10 mm")],
        )

    mock_bridge.execute_python.assert_not_called()


@pytest.mark.asyncio
async def test_get_variables_returns_native_variable_details(
    register_tools: dict[str, object], mock_bridge: AsyncMock
) -> None:
    """Variable inspection should return values, types, and expressions."""
    mock_bridge.execute_python.return_value = ExecutionResult(
        success=True,
        result={
            "name": "Variables",
            "variables": [
                {
                    "name": "tower_height",
                    "type": "App::PropertyLength",
                    "value": 120.0,
                    "display_value": "120.00 mm",
                    "expression": None,
                }
            ],
        },
        stdout="",
        stderr="",
        execution_time_ms=10.0,
    )

    get_variables = register_tools["get_variables"]
    result = await get_variables(  # type: ignore[operator]
        variable_set_name="Variables",
        doc_name="Lighthouse",
    )

    assert result["variables"][0]["value"] == 120.0
    code = mock_bridge.execute_python.call_args.args[0]
    assert 'obj.TypeId != "App::VarSet"' in code
    assert "ExpressionEngine" in code
    assert 'group in {"", "Base"}' in code


@pytest.mark.asyncio
async def test_set_expression_accepts_sketch_constraint_paths(
    register_tools: dict[str, object], mock_bridge: AsyncMock
) -> None:
    """Expressions should bind directly to sketch dimensions by index."""
    mock_bridge.execute_python.return_value = ExecutionResult(
        success=True,
        result={
            "object_name": "TowerSketch",
            "property_path": "Constraints[8]",
            "expression": "Variables.base_diameter / 2",
        },
        stdout="",
        stderr="",
        execution_time_ms=10.0,
    )

    set_expression = register_tools["set_expression"]
    result = await set_expression(  # type: ignore[operator]
        object_name="TowerSketch",
        property_path="Constraints[8]",
        expression="Variables.base_diameter / 2",
        doc_name="Lighthouse",
        expected_revision="rev_1",
    )

    assert result["property_path"] == "Constraints[8]"
    code = mock_bridge.execute_python.call_args.args[0]
    assert "obj.setExpression(property_path, expression)" in code
    assert "hasattr(obj, property_path)" not in code
    assert 'open_owned_transaction(doc, "Set Expression")' in code
    assert "abort_owned_transaction(doc)" in code
    assert "candidate.Content" in code
    assert 'or "Touched" in candidate.State' in code
    assert code.index('"object_name": obj.Name') < code.index("doc.commitTransaction()")
    compile(code, "<set_expression>", "exec")


def test_expression_binding_rejects_empty_values() -> None:
    """Bindings should use null for clearing and reject ambiguous empty text."""
    with pytest.raises(ValueError, match="Property path must not be empty"):
        ExpressionBinding(
            object_name="Pad",
            property_path=" ",
            expression="Variables.height",
        )

    with pytest.raises(ValueError, match="Expression must not be empty"):
        ExpressionBinding(
            object_name="Pad",
            property_path="Length",
            expression=" ",
        )


@pytest.mark.asyncio
async def test_bind_expressions_applies_one_atomic_batch(
    register_tools: dict[str, object], mock_bridge: AsyncMock
) -> None:
    """Many expression targets should require one transaction and recompute."""
    mock_bridge.execute_python.return_value = ExecutionResult(
        success=True,
        result={
            "document_ref": {"name": "Lighthouse", "revision": "rev_2"},
            "bindings": [
                {
                    "object_name": "GalleryDatum",
                    "property_path": "AttachmentOffset.Base.z",
                    "expression": "Variables.tower_height",
                },
                {
                    "object_name": "TowerSketch",
                    "property_path": "Constraints[8]",
                    "expression": "Variables.base_diameter / 2",
                },
            ],
            "validation": {"valid": True, "invalid_objects": []},
        },
        stdout="",
        stderr="",
        execution_time_ms=10.0,
    )

    bind_expressions = register_tools["bind_expressions"]
    result = await bind_expressions(  # type: ignore[operator]
        bindings=[
            ExpressionBinding(
                object_name="GalleryDatum",
                property_path="AttachmentOffset.Base.z",
                expression="Variables.tower_height",
            ),
            ExpressionBinding(
                object_name="TowerSketch",
                property_path="Constraints[8]",
                expression="Variables.base_diameter / 2",
            ),
        ],
        doc_name="Lighthouse",
        expected_revision="rev_1",
    )

    assert len(result["bindings"]) == 2
    code = mock_bridge.execute_python.call_args.args[0]
    assert code.count('open_owned_transaction(doc, "Bind Expressions")') == 1
    assert "for binding in bindings:" in code
    assert "obj.setExpression(property_path, expression)" in code
    assert code.count("doc.recompute()") == 2  # success and rollback paths
    assert "STALE_REVISION" in code
    assert "candidate.Content" in code
    assert "root_property" in code
    assert "InListRecursive" in code
    assert 'candidate.TypeId == "PartDesign::Body"' in code
    assert "abort_owned_transaction(doc)" in code
    assert code.index('"bindings": serialized') < code.index("doc.commitTransaction()")
    compile(code, "<bind_expressions>", "exec")


@pytest.mark.asyncio
async def test_bind_expressions_rejects_duplicate_targets(
    register_tools: dict[str, object], mock_bridge: AsyncMock
) -> None:
    """One batch must not assign two values to the same property path."""
    binding = ExpressionBinding(
        object_name="Pad",
        property_path="Length",
        expression="Variables.height",
    )
    bind_expressions = register_tools["bind_expressions"]

    with pytest.raises(ValueError, match="Duplicate expression targets"):
        await bind_expressions(bindings=[binding, binding])  # type: ignore[operator]

    mock_bridge.execute_python.assert_not_called()
