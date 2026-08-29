# Parametric CAD Agent Research

Research date: 2026-08-23

This note distills primary FreeCAD sources into instructions suitable for a
small/local model. The repository-specific observations are based on the MCP
tool implementations in `src/freecad_mcp/tools/` and the generated tool
reference in `docs/MCP_TOOLS_REFERENCE.md`.

## Compact Instruction Set

Tell the model to:

1. Build editable single-part models as a `PartDesign::Body` feature history.
   Use one named Body per contiguous component, a stable base sketch, then
   additive and subtractive features in dependency order. The Body owns the
   cumulative result and has an Origin with standard planes and axes. [FreeCAD
   Feature editing](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Feature_editing.md)
   and [PartDesign workbench](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/PartDesign_Workbench.md)
   describe this history model.
2. Plan the model before creating it: identify master dimensions, reference
   planes, sketches, feature order, and intended edit parameters. Give every
   Body, variable set, sketch, datum, and feature a stable semantic name and
   use internal `Name` values for automation rather than mutable display labels.
3. Prefer a master sketch and/or datum geometry attached to Body Origin planes
   and axes. Put shared layout geometry in the master sketch, or use a datum
   plane when several sketches share an offset/orientation. Datum planes are
   not automatically better for one sketch: a sketch can have the same stable
   origin-plane attachment and offset directly. [FreeCAD stable-model advice](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Feature_editing.md#advice-for-creating-stable-models)
   is the governing guidance.
4. Make sketches dimensionally meaningful: close profile wires with
   coincident constraints, add horizontal/vertical/tangent/equal/symmetric
   constraints as appropriate, anchor the design to the origin or stable
   reference geometry, then add only the independent dimensions. Avoid
   redundant constraints and avoid fixing arbitrary geometry as a substitute
   for design intent. Treat “fully constrained” as a verification target for
   driving sketches, checked with DOF, not as permission to over-constrain.
   [Sketcher scripting](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Sketcher_scripting.md)
   documents `addGeometry`, `Sketcher.Constraint`, zero-based geometry indices,
   point indices, external-geometry indices, and `doc.recompute()`.
5. Put named master values in one native `App::VarSet` and bind feature
   properties or sketch dimensional constraints with expressions. Include
   units in values and expressions (`25 mm`, not an unexplained scalar); use
   names such as `plate_length`, `wall`, and `hole_diameter`. Avoid expressions
   that create object dependency cycles. [FreeCAD Expressions](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Expressions.md)
   documents unit-aware expressions, property references, cyclic dependency
   limits, `setExpression`, and `ExpressionEngine`.
6. Attach sketches to an Origin plane or an Origin-based datum plane by default.
   Attach to a generated face only when the design genuinely means “this exact
   evolving face,” and record that risk. Face/edge/vertex references can change
   identity after pad, cut, union, fillet, or chamfer. FreeCAD 1.0 improves
   repair heuristics but does not remove the risk. [Topological naming problem](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Topological_naming_problem.md)
   and [OCCT TNaming](https://dev.opencascade.org/doc/refman/html/class_t_naming.html)
   explain why references can be resolved through shape evolution but may still
   be ambiguous when topology changes.
7. Use additive features to establish or join material (`Pad`, `Revolution`,
   additive loft/pipe) and subtractive features for material removal (`Pocket`,
   `Hole`, `Groove`, subtractive loft/pipe). Ensure every additive result joins
   the Body's existing solid and every cut intersects material. Put fillets,
   chamfers, draft, and thickness late, after the primary geometry and cuts;
   they are especially sensitive to topology changes. [FreeCAD feature list](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/PartDesign_Feature.md)
   and the [PartDesign tutorial](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/PartDesign_tutorial.md)
   show this sequence.
8. Create one seed hole/rib/cut and pattern the feature with a linear, polar,
   or mirrored pattern. Specify the axis/direction, total length or angle, and
   occurrence count explicitly. This preserves a compact editable history and
   makes spacing/count changes coherent. The official tutorial demonstrates
   linear and polar pattern features operating on an existing Pocket.
9. Work transactionally and incrementally: create or modify one logical
   feature, recompute, inspect the result, and only then continue. After each
   major operation check object state, feature errors, sketch DOF, solid
   validity, and whether the Body Tip is the intended final feature. Before
   save/export, recompute and validate the document again. Do not infer success
   from a tool call that merely returned without an exception.

## Attachment Choice

Use this decision rule:

| Requirement | Preferred reference |
| --- | --- |
| Base profile or global layout | Body Origin plane/axis |
| One stable offset sketch | Sketch attached to Origin plane with attachment offset |
| Several sketches share orientation/offset | Origin-based datum plane |
| Sketch must follow a deliberately selected existing surface | Generated face, with an explicit topology-risk note and post-edit validation |
| Cross-feature layout/reference | Master sketch geometry, datum geometry, or ShapeBinder/SubShapeBinder where appropriate |

The official documentation explicitly recommends Origin planes/axes and
Origin-based datum geometry over generated faces for stable models. A face
attachment is not inherently wrong, but it is a deliberate dependency on the
shape's topology. If it is unavoidable, reference the earliest feature where
the required geometry exists and validate after upstream edits.

## FreeCAD Python/API Facts

Useful canonical operations in FreeCAD Python include:

```python
import FreeCAD as App
import Part
import Sketcher

doc = App.newDocument("ParametricPart")
body = doc.addObject("PartDesign::Body", "Body")
sketch = body.newObject("Sketcher::SketchObject", "BaseSketch")
sketch.addGeometry(
    Part.LineSegment(App.Vector(0, 0, 0), App.Vector(80, 0, 0)), False
)
sketch.addConstraint(Sketcher.Constraint("Horizontal", 0))
doc.recompute()
```

For a feature-history script, create features in the Body and set their
properties or links according to the version's API; do not assume a generic
high-level PartDesign Python facade exists. The official [Body API](https://freecad.github.io/API/dd/db8/classPartDesign_1_1Body.html)
exposes Body insertion/ordering behavior, while the [FreeCAD source tree](https://github.com/FreeCAD/FreeCAD/tree/main/src/Mod/PartDesign)
is the authoritative reference for concrete feature properties. Use
`obj.setExpression("Property", "Expression")` for direct expression binding
and `doc.recompute()` after dependency changes. Use `obj.State`,
`obj.isValid()`, `obj.mustRecompute()`, and `obj.Shape.isValid()` as appropriate
for validation; the [DocumentObject API](https://freecad.github.io/API/d2/de4/classApp_1_1DocumentObject.html)
documents these status/validity methods.

Sketch scripting is index-sensitive: geometry and constraints are generally
zero-based in Python, while GUI numbering is often one-based. The model should
keep its own geometry-index map while constructing a sketch, rather than
guessing indices later. Name dimensional constraints when using expressions,
and query the sketch's solver state after adding constraints.

## Repository MCP Mapping

The repository already provides the main workflow:

- Structure: `create_partdesign_body`, `create_sketch`, `create_datum_plane`,
  `create_datum_line`, and `create_datum_point` in
  [`partdesign.py`](https://github.com/spkane/freecad-addon-robust-mcp-server/blob/main/src/freecad_mcp/tools/partdesign.py).
- Sketch geometry and constraints: rectangle, line, arc, circle, point, slot,
  B-spline, external geometry, and general/specialized constraint tools.
- History features: `pad_sketch`, `pocket_sketch`, `revolution_sketch`,
  `groove_sketch`, loft, sweep, hole, fillet, chamfer, draft, thickness, linear
  pattern, polar pattern, and mirrored feature.
- Parameters: `define_variables`, `get_variables`, and `set_expression` in
  [`variables.py`](https://github.com/spkane/freecad-addon-robust-mcp-server/blob/main/src/freecad_mcp/tools/variables.py).
  The default
  profile uses native `App::VarSet` properties. Spreadsheet wrappers remain
  available only in the opt-in full profile.
- Inspection: document/object listing and inspection, `get_sketch_info`,
  `recompute_document`, `validate_object`, `validate_document`,
  `undo_if_invalid`, and `safe_execute`.
- Legacy escape hatch: the full profile's `execute_python` exposes FreeCAD,
  `App`, `FreeCADGui`, and `Gui` in the FreeCAD context. It is intentionally
  absent from the default profile; extend a typed wrapper instead.

Modifying wrappers generally open a FreeCAD transaction, recompute, commit on
success, and abort on failure. The shared implementation is
[`utils.py`](https://github.com/spkane/freecad-addon-robust-mcp-server/blob/main/src/freecad_mcp/tools/utils.py).
A small model should still
use explicit checkpoints because transaction success does not prove that the
result is a valid or design-intent model.

Important API gaps or caveats for prompt design:

- The wrappers create geometry with numeric coordinates, but they do not
  automatically produce a fully constrained sketch. The agent must add and
  verify constraints explicitly.
- `create_sketch` supports Origin planes and `Face...` attachment, but the
  stable-model policy must come from the agent; the API does not prevent risky
  face attachment.
- `set_expression` accepts direct feature-property and sketch-constraint paths,
  but the caller must preserve the zero-based constraint index returned by
  `get_sketch_info`.
- Validation checks object state and OCC shape validity, not complete design
  intent, manufacturing feasibility, or whether every sketch is fully
  constrained. Combine `get_sketch_info`, inspection, recompute, and validation.
- The wrappers target object names and face strings such as `Face1`; after
  topology-changing edits, re-inspect references rather than reusing stale
  sub-element names blindly.

## Agent Checkpoint Protocol

For a compact system prompt, the following loop is more useful than a long
catalog of feature names:

```text
Plan -> create Body/parameters/master references -> create one sketch ->
constrain and check DOF -> recompute -> create one feature -> recompute ->
inspect/validate -> repeat -> validate final Body/document -> save/export.
```

At every checkpoint report: object names, feature order/Tip, sketch DOF,
attachment/support, variables/expressions, recompute errors, shape validity, and
any face/edge/vertex references that could be affected by topology changes.

## Sources and Scope

Primary sources used:

- [FreeCAD documentation repository](https://github.com/FreeCAD/FreeCAD-documentation)
  pages for [feature editing](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Feature_editing.md),
  [PartDesign](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/PartDesign_Workbench.md),
  [Sketcher scripting](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Sketcher_scripting.md),
  [Expressions](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Expressions.md),
  [topological naming](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Topological_naming_problem.md),
  [datum planes](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/PartDesign_Plane.md),
  and [PartDesign tutorial](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/PartDesign_tutorial.md).
- [FreeCAD generated C++ API documentation](https://freecad.github.io/API/) for
  Body and DocumentObject APIs.
- [FreeCAD source](https://github.com/FreeCAD/FreeCAD) for concrete Python-
  exposed object types and feature implementation.
- [Open CASCADE TNaming reference](https://dev.opencascade.org/doc/refman/html/class_t_naming.html)
  for the underlying named-shape/evolution model.

The public FreeCAD documentation tutorials and examples are authoritative
workflow examples. They are preferable to arbitrary downloadable `.FCStd`
files for prompt training because their intended dependencies and modeling
steps are documented alongside the example.
