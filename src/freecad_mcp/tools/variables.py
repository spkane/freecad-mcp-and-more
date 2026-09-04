"""Native FreeCAD variable-set and expression tools."""

import re
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from freecad_mcp.tools.utils import WORKFLOW_HELPERS
from freecad_mcp.tools.workflow_results import (
    BindExpressionsResult,
    WorkflowToolError,
    bridge_workflow_error,
)

INTERNAL_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
InternalName = Annotated[str, Field(pattern=INTERNAL_NAME_PATTERN.pattern)]


def _validate_internal_name(value: str, field_name: str) -> None:
    """Reject names that FreeCAD would silently sanitize."""
    if INTERNAL_NAME_PATTERN.fullmatch(value) is None:
        msg = f"{field_name} must be a valid FreeCAD internal name"
        raise ValueError(msg)


class VariableDefinition(BaseModel):
    """Define one typed property in a native FreeCAD variable set."""

    model_config = ConfigDict(extra="forbid")

    name: InternalName
    kind: Literal["length", "angle", "float", "integer", "boolean", "string"]
    value: str | float | int | bool | None = None
    expression: str | None = None
    group: str = "Variables"
    description: str = ""

    @model_validator(mode="after")
    def validate_definition(self) -> Self:
        """Require one source and a value compatible with the property kind."""
        self.group = self.group.strip()
        if not self.group or self.group == "Base":
            msg = "Variable group must be non-empty and cannot be Base"
            raise ValueError(msg)
        if (self.value is None) == (self.expression is None):
            msg = "Specify exactly one of value or expression"
            raise ValueError(msg)
        if self.expression is not None:
            if not self.expression.strip():
                msg = "Expression must not be empty"
                raise ValueError(msg)
            return self

        value = self.value
        if self.kind in {"length", "angle"} and not isinstance(value, str):
            msg = f"{self.kind} values must include units in a string"
            raise ValueError(msg)
        if self.kind == "float" and (
            isinstance(value, bool) or not isinstance(value, int | float)
        ):
            msg = "float values must be numeric"
            raise ValueError(msg)
        if self.kind == "integer" and (
            isinstance(value, bool) or not isinstance(value, int)
        ):
            msg = "integer values must be whole numbers"
            raise ValueError(msg)
        if self.kind == "boolean" and not isinstance(value, bool):
            msg = "boolean values must be true or false"
            raise ValueError(msg)
        if self.kind == "string" and not isinstance(value, str):
            msg = "string values must be text"
            raise ValueError(msg)
        return self


class ExpressionBinding(BaseModel):
    """Bind or clear one native FreeCAD expression target."""

    model_config = ConfigDict(extra="forbid")

    object_name: InternalName
    property_path: str
    expression: str | None

    @model_validator(mode="after")
    def validate_binding(self) -> Self:
        """Reject paths and expressions that FreeCAD cannot identify clearly."""
        self.property_path = self.property_path.strip()
        if not self.property_path:
            msg = "Property path must not be empty"
            raise ValueError(msg)
        if self.expression is not None:
            self.expression = self.expression.strip()
            if not self.expression:
                msg = "Expression must not be empty; use null to clear it"
                raise ValueError(msg)
        return self


def register_variable_tools(mcp: Any, get_bridge: Callable[[], Awaitable[Any]]) -> None:
    """Register native variable-set and expression tools.

    Args:
        mcp: FastMCP server instance.
        get_bridge: Async function returning the active FreeCAD bridge.
    """

    @mcp.tool()
    async def define_variables(
        variable_set_name: InternalName,
        variables: list[VariableDefinition],
        label: str | None = None,
        doc_name: InternalName | None = None,
        expected_revision: str | None = None,
    ) -> dict[str, Any]:
        """Create or update typed variables in one native ``App::VarSet``.

        The batch is applied in one transaction. Define governing dimensions
        with explicit units and derived variables with expressions. Expressions
        inside a variable set can refer to sibling variables by name.

        Args:
            variable_set_name: Internal name of the variable-set object.
            variables: Typed value or expression definitions to apply.
            label: Optional display label when creating or updating the set.
            doc_name: Document containing the variables. Uses the active document.
            expected_revision: Optional revision returned by a prior workflow tool.

        Returns:
            The variable-set identity and serialized definitions after recompute.
        """
        _validate_internal_name(variable_set_name, "Variable set name")
        if doc_name is not None:
            _validate_internal_name(doc_name, "Document name")
        if not variables:
            msg = "At least one variable definition is required"
            raise ValueError(msg)
        names = [definition.name for definition in variables]
        if len(names) != len(set(names)):
            msg = "Duplicate variable names are not allowed in one batch"
            raise ValueError(msg)
        if expected_revision is not None and not expected_revision.strip():
            msg = "Expected revision must not be empty"
            raise WorkflowToolError("INVALID_INPUT", msg)

        definitions = [definition.model_dump() for definition in variables]
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
    raise ValueError("NOT_FOUND: No active document")
expected_revision = {expected_revision!r}
current_revision = require_expected_revision(doc, expected_revision)

variable_set_name = {variable_set_name!r}
definitions = {definitions!r}
type_map = {{
    "length": "App::PropertyLength",
    "angle": "App::PropertyAngle",
    "float": "App::PropertyFloat",
    "integer": "App::PropertyInteger",
    "boolean": "App::PropertyBool",
    "string": "App::PropertyString",
}}

var_set = doc.getObject(variable_set_name)
if var_set is not None and var_set.TypeId != "App::VarSet":
    raise ValueError(
        f"INVALID_INPUT: Object is not an App::VarSet: {{variable_set_name}}"
    )
if var_set is not None:
    for definition in definitions:
        name = definition["name"]
        if name not in var_set.PropertiesList:
            continue
        existing_group = var_set.getGroupOfProperty(name)
        if existing_group in {{"", "Base"}}:
            raise ValueError(f"INVALID_INPUT: Reserved App::VarSet property: {{name}}")
        property_type = type_map[definition["kind"]]
        if var_set.getTypeIdOfProperty(name) != property_type:
            raise ValueError(
                f"INVALID_INPUT: Variable {{name}} already has type "
                f"{{var_set.getTypeIdOfProperty(name)}}, expected {{property_type}}"
            )

if var_set is None:
    var_set = doc.addObject("App::VarSet", variable_set_name)
if {label!r} is not None:
    var_set.Label = {label!r}

# Create every property first so expressions can reference any batch member.
for definition in definitions:
    name = definition["name"]
    property_type = type_map[definition["kind"]]
    if name not in var_set.PropertiesList:
        var_set.addProperty(
            property_type,
            name,
            definition["group"],
            definition["description"],
        )

for definition in definitions:
    if definition["value"] is not None:
        name = definition["name"]
        var_set.setExpression(name, None)
        setattr(var_set, name, definition["value"])

def describe_expression_error(definition: dict, error: Exception) -> dict:
    return {{
        "object_name": var_set.Name,
        "property_path": definition["name"],
        "expression": definition["expression"],
        "error": str(error),
    }}

expression_diagnostics = []

def collect_expression_evaluation_errors(
    definitions: list[dict], skipped_names: set[str]
) -> None:
    for definition in definitions:
        expression = definition["expression"]
        if expression is None or definition["name"] in skipped_names:
            continue
        try:
            var_set.evalExpression(expression)
        except Exception as error:
            expression_diagnostics.append(
                describe_expression_error(definition, error)
            )

rejected_expression_names = set()
for definition in definitions:
    expression = definition["expression"]
    if expression is not None:
        name = definition["name"]
        try:
            var_set.setExpression(name, expression)
        except Exception as error:
            rejected_expression_names.add(name)
            expression_diagnostics.append(
                describe_expression_error(definition, error)
            )
if expression_diagnostics:
    collect_expression_evaluation_errors(
        definitions, rejected_expression_names
    )
    raise RuntimeError(
        "VALIDATION_FAILED: Expression assignment failed: "
        "expression_diagnostics=%s" % expression_diagnostics
    )

doc.recompute()
invalid_objects = [
    {{"name": candidate.Name, "state": list(candidate.State)}}
    for candidate in doc.Objects
    if (
        "Invalid" in candidate.State
        or "Error" in candidate.State
        or "Touched" in candidate.State
    )
]
if invalid_objects:
    collect_expression_evaluation_errors(definitions, set())
    raise RuntimeError(
        "VALIDATION_FAILED: Recompute failed: "
        "invalid_objects=%s, expression_diagnostics=%s"
        % (invalid_objects, expression_diagnostics)
    )

expressions = {{
    path: str(expression)
    for path, expression in getattr(var_set, "ExpressionEngine", [])
}}
serialized = []
for definition in definitions:
    name = definition["name"]
    value = getattr(var_set, name)
    if hasattr(value, "Value"):
        raw_value = float(value.Value)
        display_value = str(value)
    elif isinstance(value, (bool, int, float, str)):
        raw_value = value
        display_value = str(value)
    else:
        raw_value = str(value)
        display_value = str(value)
    serialized.append({{
        "name": name,
        "type": var_set.getTypeIdOfProperty(name),
        "group": var_set.getGroupOfProperty(name),
        "value": raw_value,
        "display_value": display_value,
        "expression": expressions.get(name),
    }})

_result_ = {{
    "document_ref": {{
        "name": doc.Name,
        "revision": document_revision(doc),
    }},
    "operation_id": "op_" + uuid.uuid4().hex[:12],
    "name": var_set.Name,
    "label": var_set.Label,
    "type_id": var_set.TypeId,
    "variables": serialized,
}}
"""
        result = await bridge.execute_python(code, transaction="Define Variables")
        if result.success:
            return result.result
        raise bridge_workflow_error(result.error_traceback, "Define variables failed")

    @mcp.tool()
    async def get_variables(
        variable_set_name: InternalName,
        doc_name: InternalName | None = None,
    ) -> dict[str, Any]:
        """Inspect values, units, types, and formulas in a native variable set.

        Args:
            variable_set_name: Internal name of the ``App::VarSet`` object.
            doc_name: Document containing the variables. Uses the active document.

        Returns:
            The variable-set identity and all supported variable properties.
        """
        _validate_internal_name(variable_set_name, "Variable set name")
        if doc_name is not None:
            _validate_internal_name(doc_name, "Document name")

        bridge = await get_bridge()
        code = f"""
requested_doc_name = {doc_name!r}
doc = (
    FreeCAD.ActiveDocument
    if requested_doc_name is None
    else FreeCAD.getDocument(requested_doc_name)
)
if doc is None:
    raise ValueError("No active document")
obj = doc.getObject({variable_set_name!r})
if obj is None:
    raise ValueError(f"Variable set not found: {variable_set_name!r}")
if obj.TypeId != "App::VarSet":
    raise ValueError(f"Object is not an App::VarSet: {variable_set_name!r}")

supported_types = {{
    "App::PropertyLength",
    "App::PropertyAngle",
    "App::PropertyFloat",
    "App::PropertyInteger",
    "App::PropertyBool",
    "App::PropertyString",
}}
expressions = {{
    path: str(expression)
    for path, expression in getattr(obj, "ExpressionEngine", [])
}}
serialized = []
for name in obj.PropertiesList:
    property_type = obj.getTypeIdOfProperty(name)
    group = obj.getGroupOfProperty(name)
    if property_type not in supported_types or group in {{"", "Base"}}:
        continue
    value = getattr(obj, name)
    if hasattr(value, "Value"):
        raw_value = float(value.Value)
        display_value = str(value)
    elif isinstance(value, (bool, int, float, str)):
        raw_value = value
        display_value = str(value)
    else:
        raw_value = str(value)
        display_value = str(value)
    serialized.append({{
        "name": name,
        "type": property_type,
        "group": group,
        "value": raw_value,
        "display_value": display_value,
        "expression": expressions.get(name),
    }})

_result_ = {{
    "name": obj.Name,
    "label": obj.Label,
    "type_id": obj.TypeId,
    "variables": serialized,
}}
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Get variables failed")

    @mcp.tool()
    async def bind_expressions(
        bindings: list[ExpressionBinding],
        doc_name: InternalName | None = None,
        expected_revision: str | None = None,
    ) -> BindExpressionsResult:
        """Bind many feature properties and sketch dimensions atomically.

        Every target object is resolved before mutation. The batch uses one
        transaction and one successful recompute, then rolls back if any target,
        expression, or resulting object state is invalid.

        Args:
            bindings: Expression targets to set or clear.
            doc_name: Document containing the targets. Uses the active document.
            expected_revision: Optional revision returned by a prior workflow tool.

        Returns:
            The new document revision, applied bindings, and validation summary.
        """
        if doc_name is not None:
            _validate_internal_name(doc_name, "Document name")
        if not bindings:
            msg = "At least one expression binding is required"
            raise WorkflowToolError("INVALID_INPUT", msg)
        targets = [(binding.object_name, binding.property_path) for binding in bindings]
        if len(targets) != len(set(targets)):
            msg = "Duplicate expression targets are not allowed in one batch"
            raise WorkflowToolError("INVALID_INPUT", msg)
        if expected_revision is not None and not expected_revision.strip():
            msg = "Expected revision must not be empty"
            raise WorkflowToolError("INVALID_INPUT", msg)

        definitions = [binding.model_dump() for binding in bindings]
        bridge = await get_bridge()
        code = f"""
import re
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

bindings = {definitions!r}
objects = {{}}
affected_objects = {{}}
for binding in bindings:
    object_name = binding["object_name"]
    obj = doc.getObject(object_name)
    if obj is None:
        raise ValueError(f"NOT_FOUND: Object not found: {{object_name}}")
    property_path = binding["property_path"]
    root_property = property_path.split(".", 1)[0].split("[", 1)[0]
    if root_property not in getattr(obj, "PropertiesList", []):
        raise ValueError(
            f"INVALID_INPUT: Property not found on {{object_name}}: "
            f"{{root_property}}"
        )
    constraint_match = re.fullmatch(r"Constraints\\[(\\d+)\\]", property_path)
    if constraint_match is not None:
        constraint_index = int(constraint_match.group(1))
        if constraint_index >= int(getattr(obj, "ConstraintCount", 0)):
            raise ValueError(
                f"INVALID_INPUT: Constraint index out of range on {{object_name}}: "
                f"{{constraint_index}}"
            )
    objects[object_name] = obj
    affected_objects[obj.Name] = obj
    for candidate in getattr(obj, "InListRecursive", []):
        affected_objects[candidate.Name] = candidate

for binding in bindings:
    obj = objects[binding["object_name"]]
    property_path = binding["property_path"]
    expression = binding["expression"]
    obj.setExpression(property_path, expression)

doc.recompute()
invalid_objects = []
for candidate in affected_objects.values():
    state = list(getattr(candidate, "State", []))
    errors = []
    if "Invalid" in state or "Error" in state:
        errors.append("Object state is invalid")
    if "Touched" in state:
        errors.append("Object still needs recompute")
    shape = getattr(candidate, "Shape", None)
    if candidate.TypeId == "PartDesign::Body":
        if shape is None or shape.isNull():
            errors.append("PartDesign Body has no result shape")
        elif len(shape.Solids) != 1:
            errors.append(
                "PartDesign Body must contain exactly one solid; found %d"
                % len(shape.Solids)
            )
    if errors:
        invalid_objects.append({{
            "name": candidate.Name,
            "state": state,
            "errors": errors,
        }})
if invalid_objects:
    raise RuntimeError(
        f"VALIDATION_FAILED: Recompute failed: {{invalid_objects}}"
    )

serialized = []
for binding in bindings:
    obj = objects[binding["object_name"]]
    expressions = {{
        path: str(expression)
        for path, expression in getattr(obj, "ExpressionEngine", [])
    }}
    property_path = binding["property_path"]
    serialized.append({{
        "object_name": obj.Name,
        "property_path": property_path,
        "expression": expressions.get(property_path),
    }})

object_refs = [
    {{"name": obj.Name, "label": obj.Label, "type_id": obj.TypeId}}
    for obj in sorted(objects.values(), key=lambda candidate: candidate.Name)
]
affected_bodies = [
    candidate
    for candidate in affected_objects.values()
    if candidate.TypeId == "PartDesign::Body"
]
body_tip = None
solid_count = None
if len(affected_bodies) == 1:
    body = affected_bodies[0]
    body_tip = body.Tip.Name if getattr(body, "Tip", None) is not None else None
    body_shape = getattr(body, "Shape", None)
    if body_shape is not None and not body_shape.isNull():
        solid_count = len(body_shape.Solids)

_result_ = {{
    "document_ref": {{
        "name": doc.Name,
        "revision": document_revision(doc),
    }},
    "operation_id": "op_" + uuid.uuid4().hex[:12],
    "objects": object_refs,
    "topology_refs": [],
    "bindings": serialized,
    "validation": {{
        "valid": True,
        "recompute": "valid",
        "body_tip": body_tip,
        "solid_count": solid_count,
        "errors": [],
        "invalid_objects": [],
        "checked_objects": sorted(affected_objects),
    }},
    "warnings": [],
}}
"""
        result = await bridge.execute_python(code, transaction="Bind Expressions")
        if result.success:
            return result.result
        raise bridge_workflow_error(result.error_traceback, "Bind expressions failed")

    @mcp.tool()
    async def set_expression(
        object_name: InternalName,
        property_path: str,
        expression: str | None,
        doc_name: InternalName | None = None,
        expected_revision: str | None = None,
    ) -> dict[str, Any]:
        """Set or clear an expression on a feature property or sketch dimension.

        Use a property such as ``Length`` or a sketch constraint path such as
        ``Constraints[8]``. Reference native variables with qualified names such
        as ``Variables.tower_height``. Pass ``None`` to clear the expression.

        Args:
            object_name: Internal name of the target document object.
            property_path: Property or expression path to bind.
            expression: FreeCAD expression, or None to clear it.
            doc_name: Document containing the object. Uses the active document.
            expected_revision: Optional revision returned by a prior workflow tool.

        Returns:
            The object, property path, and resulting expression.
        """
        _validate_internal_name(object_name, "Object name")
        if doc_name is not None:
            _validate_internal_name(doc_name, "Document name")
        if not property_path.strip():
            msg = "Property path must not be empty"
            raise ValueError(msg)
        if expression is not None and not expression.strip():
            msg = "Expression must not be empty; use null to clear it"
            raise ValueError(msg)
        if expected_revision is not None and not expected_revision.strip():
            msg = "Expected revision must not be empty"
            raise WorkflowToolError("INVALID_INPUT", msg)

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
    raise ValueError("NOT_FOUND: No active document")
expected_revision = {expected_revision!r}
current_revision = require_expected_revision(doc, expected_revision)
obj = doc.getObject({object_name!r})
if obj is None:
    raise ValueError(f"NOT_FOUND: Object not found: {object_name!r}")

property_path = {property_path!r}
expression = {expression!r}
obj.setExpression(property_path, expression)
doc.recompute()
invalid_objects = [
    {{"name": candidate.Name, "state": list(candidate.State)}}
    for candidate in doc.Objects
    if (
        "Invalid" in candidate.State
        or "Error" in candidate.State
        or "Touched" in candidate.State
    )
]
if invalid_objects:
    raise RuntimeError(f"Recompute failed: {{invalid_objects}}")
resulting_expressions = {{
    path: str(bound_expression)
    for path, bound_expression in getattr(obj, "ExpressionEngine", [])
}}
_result_ = {{
    "document_ref": {{
        "name": doc.Name,
        "revision": document_revision(doc),
    }},
    "operation_id": "op_" + uuid.uuid4().hex[:12],
    "object_name": obj.Name,
    "property_path": property_path,
    "expression": resulting_expressions.get(property_path),
}}
"""
        result = await bridge.execute_python(code, transaction="Set Expression")
        if result.success:
            return result.result
        raise bridge_workflow_error(result.error_traceback, "Set expression failed")
