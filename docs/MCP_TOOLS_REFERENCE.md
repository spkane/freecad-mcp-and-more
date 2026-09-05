# FreeCAD Parametric MCP Tools Reference

The default `parametric` profile exposes 55 typed tools. The exact live catalog
is available from `freecad://capabilities`.

## Primary Construction Tools

### `create_partdesign_body`

```python
create_partdesign_body(
    name: str | None = None,
    doc_name: str | None = None,
) -> dict[str, Any]
```

Creates the native Body that owns sketches and ordered PartDesign features.

### `create_constrained_sketch`

```python
create_constrained_sketch(
    body_name: str,
    sketch_name: str,
    entities: list[SketchEntity],
    constraints: list[SketchConstraint] | None = None,
    support: str = "XY_Plane",
    label: str | None = None,
    validation: SketchValidation | None = None,
    expected_revision: str | None = None,
    doc_name: str | None = None,
) -> ConstrainedSketchResult
```

Creates typed lines, circles, arcs, points, rectangles, geometric constraints,
dimensional constraints, and expressions in one transaction. Entity and
constraint IDs are request-local symbolic references. Rectangle edges use
`<id>.bottom`, `<id>.right`, `<id>.top`, and `<id>.left`. The result maps those
IDs to native indices and reports solver state, closure, validation, and the new
document revision.

### `create_sketch`

```python
create_sketch(
    body_name: str | None = None,
    plane: str = "XY_Plane",
    name: str | None = None,
    doc_name: str | None = None,
) -> dict[str, Any]
```

Attaches a sketch to a Body Origin plane, a named `PartDesign::Plane` datum, or
an explicit Body face.

### Sketch Geometry

The focused profile includes:

- `add_sketch_line`
- `add_sketch_rectangle`
- `add_sketch_circle`
- `add_sketch_arc`
- `add_sketch_point`
- `toggle_construction`
- `delete_sketch_geometry`

These granular repair mutations return geometry counts or indices. Use those
values rather than guessing positions after an edit.

### `add_sketch_constraint`

```python
add_sketch_constraint(
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
) -> dict[str, Any]
```

Supports `Coincident`, `Horizontal`, `Vertical`, `Parallel`, `Perpendicular`,
`Tangent`, `Equal`, `Symmetric`, `Block`, `Distance`, `DistanceX`, `DistanceY`,
`Radius`, `Diameter`, and `Angle`. Use `get_sketch_info` after constraint edits.
For `Symmetric`, identify the two constrained points with `geometry1`/`point1`
and `geometry2`/`point2`; use `geometry3` for a symmetry line or add `point3`
for symmetry around a point.

### Additive And Subtractive Features

```python
pad_sketch(sketch_name: str, length: float, ...) -> dict[str, Any]
pocket_sketch(sketch_name: str, length: float, ...) -> dict[str, Any]
revolution_sketch(sketch_name: str, angle: float = 360.0, ...) -> dict[str, Any]
groove_sketch(sketch_name: str, angle: float = 360.0, ...) -> dict[str, Any]
loft_sketches(sketch_names: list[str], ...) -> dict[str, Any]
create_hole(sketch_name: str, diameter: float = 6.0, ...) -> dict[str, Any]
```

The source sketches must belong to a `PartDesign::Body`. These tools create
native editable features rather than generic static shapes. Each operation
recomputes, rejects invalid or multi-solid Body results before commit, and
returns a `FeatureMutationResult` with shape summary, Body Tip, revision, and
inputs for the next feature.

### Patterns And Dress-up

- `linear_pattern`
- `polar_pattern`
- `mirrored_feature`
- `fillet_edges`
- `chamfer_edges`

Pattern directions use Body Origin axes. Fillets and chamfers should be late in
the tree because generated edge names are topology-sensitive.

## Variables And Expressions

### `define_variables`

```python
define_variables(
    variable_set_name: str,
    variables: list[VariableDefinition],
    label: str | None = None,
    doc_name: str | None = None,
    expected_revision: str | None = None,
) -> dict[str, Any]
```

Creates or updates native properties in an `App::VarSet` in one transaction.
Each definition has a semantic `name`, a `kind` (`length`, `angle`, `float`,
`integer`, `boolean`, or `string`), and exactly one `value` or `expression`.
Lengths and angles require explicit unit strings such as `"120 mm"` and
`"15 deg"`. Expressions within the set can reference sibling variables directly.
The variable-set name must be a valid FreeCAD internal name. The batch rolls
back if property assignment, expression evaluation, or recompute fails.
An optional revision guard rejects stale edits and a pre-existing document
transaction rejects the batch rather than closing another operation's work.

### `get_variables`

Returns every supported variable with its FreeCAD property type, group, raw and
display values, and derived expression.

### `bind_expressions`

```python
bind_expressions(
    bindings: list[ExpressionBinding],
    doc_name: str | None = None,
    expected_revision: str | None = None,
) -> BindExpressionsResult
```

Validates every object and property target before mutation, applies the complete
batch in one transaction, recomputes once, and checks affected dependents. An
expression value of `null` clears a binding. Duplicate targets, stale revisions,
invalid object states, and multi-solid affected Bodies reject the complete
batch.

### `set_expression`

Sets or clears an expression on an ordinary feature property such as `Length` or
a dimensional sketch path such as `Constraints[8]`. Qualify cross-object
references, for example `Variables.tower_height`. The change rolls back if
recompute leaves any document object invalid. It accepts the same optional
`expected_revision` guard and transaction-ownership rules as expression batches.

## Inspection And Validation

### `query_objects`

```python
query_objects(
    query: str | None = None,
    names: list[str] | None = None,
    type_ids: list[str] | None = None,
    visible_only: bool = False,
    detail: Literal["summary", "standard", "detailed"] = "summary",
    limit: int = 25,
    cursor: str | None = None,
    doc_name: str | None = None,
) -> ObjectQueryResult
```

Filters inside FreeCAD and returns a deterministic bounded page. Summary mode is
the default; standard mode adds relationships and detailed mode adds bounded
properties and shape data. Reuse `next_cursor` only with the same filters.

### `get_sketch_info`

Returns sketch geometry and constraint counts, external geometry count, solver
status, and whether the sketch is fully constrained.

### `inspect_object`

Returns object properties, links, visibility, and native shape information. Use
it for granular repair after narrowing the target with `query_objects`.

### `validate_object` And `validate_document`

Check object state, recompute state, native shape validity, and solid count. Pass
`require_single_solid=true` when the acceptance contract requires exactly one
solid in each PartDesign Body.

## Documents And Delivery

The profile includes document creation, listing, active-document lookup,
recompute, save, close, and open tools. New documents require an explicit path
on first save.

`export_step` writes BREP interchange geometry, `import_step` reopens STEP in a
clean document, and `export_stl` writes a tessellated mesh. Pass the final Body
or Tip explicitly rather than exporting hidden intermediate features.

`get_screenshot`, `set_view_angle`, `fit_all`, and `set_object_visibility`
support visual review in GUI mode.

### `capture_feature_view`

```python
capture_feature_view(
    normal_source: str,
    side: str = "front",
    focus: list[str] | None = None,
    padding: float = 0.1,
    hide_construction: bool = True,
    width: int = 800,
    height: int = 600,
    doc_name: str | None = None,
) -> CallToolResult
```

Captures the model looking along a named support's own normal. A feature seen
edge-on is not evidence about its shape. Use this for every semantic opening or
profile: pass the sketch, datum, or feature that supports it as `normal_source`.
Requires GUI mode; returns an error in headless mode.

- `normal_source`: Name of the sketch, datum, or feature whose support
  placement defines the view normal.
- `side`: `"front"` looks against the normal; `"back"` looks along it.
- `focus`: Object names to frame. Frames the whole model if `None`.
- `padding`: Fractional padding around the framed objects.
- `hide_construction`: Hide datums, origins, and construction helpers for the
  capture, then restore them.
- `width`: Image width in pixels.
- `height`: Image height in pixels.
- `doc_name`: Document to capture. Uses the active document if `None`.

Returns a PNG image content block plus a JSON metadata block carrying the
camera direction, resolved source, focus names, hidden objects, and the
retained path.

## Prompts

- `design_parametric_part`: Guide task-oriented native PartDesign construction.
- `review_parametric_part`: Apply editability, persistence, and evidence gates.

## Resources

- `freecad://parametric-parts/guide`: Native modeling and validation guide.
- `freecad://capabilities`: Exact default interface and contract.
- `freecad://status`: Live bridge and GUI status.
- `freecad://active-document`: Active native document summary.

## Retired Full Profile

The opt-in full profile has been retired. The tools it added -- arbitrary Python
execution, generic Part primitives, macro management, and the remaining
specialized wrappers -- were unreachable through the default profile and have
been removed. `FREECAD_TOOL_PROFILE` is no longer read; the server registers one
interface, documented above.
