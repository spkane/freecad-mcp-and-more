# Native Parametric FreeCAD Parts

Use the focused MCP commands to build an editable native FreeCAD PartDesign
feature tree. The saved FCStd document is the authoritative model. Arbitrary
Python execution is deliberately absent from the default profile.

## 1. Plan The Model

Before changing FreeCAD:

1. Define the coordinate frame, units, Origin planes, and named datums.
2. Separate governing parameters from derived dimensions and placements.
3. Plan one semantically named `PartDesign::Body` for each contiguous part.
4. Choose a stable feature order: primary additive form, cuts, patterns, then
   topology-sensitive fillets and chamfers.
5. Define the parameter edits, measurements, and invalid combinations that must
   be verified before delivery.

## 2. Build Through Native MCP Commands

Prefer task-oriented operations that complete one coherent modeling step:

1. Call `create_document`, then `create_partdesign_body`.
2. Call `define_variables` once with a compact batch of governing dimensions and
   derived formulas. Store them in a native `App::VarSet`; use explicit units
   for lengths and angles. Use valid FreeCAD internal names: letters, numbers,
   and underscores, starting with a letter or underscore.
3. Call `create_constrained_sketch` with typed lines, arcs, circles, rectangles,
   points, and constraints. Use request-local symbolic IDs instead of guessing
   geometry indices. Require closed profiles and `FullyConstrained` when the
   sketch is ready to drive a solid feature. For signed `distance_x` and
   `distance_y`, a whole line measures end minus start, one point measures its
   coordinate from the sketch origin, and two points measure second minus first.
   Check the returned `solved_geometry` before creating the dependent feature.
4. Call `bind_expressions` once for a related group of feature properties or
   sketch dimensions. Constraint paths use forms such as `Constraints[8]`, and
   qualified variable references use forms such as `Variables.tower_height`.
5. Create native features with `pad_sketch`, `pocket_sketch`,
   `revolution_sketch`, `groove_sketch`, `loft_sketches`, and native pattern or
   dress-up tools. Feature results already include recompute status, Body Tip,
   solid count, shape summary, and inputs for the next operation.
6. Use `query_objects` for bounded name, label, or type searches. Request
   `detailed` output only for a small result set; do not repeatedly retrieve the
   complete document tree.

Task-oriented mutations enable document undo, recompute once, validate affected
objects, and roll back the entire transaction on failure. Carry the returned
`document_ref` forward and pass `expected_revision` wherever the next tool
accepts it.

Granular `create_sketch`, `add_sketch_line`, `add_sketch_constraint`,
`set_expression`, and `get_sketch_info` tools remain available for local repair.
Use them only when a declarative operation reports a specific invalid input or
solver conflict.

Do not use generic `PartDesign::Feature` containers to disguise static shapes
as editable history. Prefer Origin planes and named datums over generated
`FaceN` or `EdgeN` references. If a generated topology reference is necessary,
record it and prove that required parameter edits survive save and reopen.

## 3. Preserve Design Intent

- Keep driving sketches inside the intended Body and require
  `FullyConstrained`. Sketch closure and solver success do not prove that all
  degrees of freedom are constrained.
- Use expressions instead of copying derived numeric values between features.
- Give intended unions real overlap; point or tangent contact is not reliable
  connectivity.
- Extend through-cuts beyond both sides of the target material.
- Use `create_datum_plane` when a stable offset support is clearer than a Body
  face.
- Place fillets and chamfers late because their edge references are sensitive to
  upstream topology changes.
- Use descriptive internal names for sketches, datums, and features.

## 4. Work Incrementally

1. Call `get_connection_status` and `get_freecad_version` once.
2. Create one sketch or feature group at a time.
3. Trust successful `create_constrained_sketch` solver and closure results. Use
   `get_sketch_info` only to diagnose a rejected sketch or perform local repair.
4. Trust the local validation returned by feature mutations. Use
   `query_objects` when a specific object or relationship remains uncertain.
5. Call `validate_document(require_single_solid=true)` after meaningful feature
   groups and before delivery. Treat invalid,
   error, or touched objects as failures rather than continuing on stale state.
6. On a bad operation, use `undo`, repair the smallest responsible inputs, and
   rerun only that operation. Do not stack compensating features over an invalid
   tree.
7. Use `get_screenshot` only after deterministic checks pass. Inspect the image
   for silhouette, orientation, missing features, and accidental intersections.
   Pixels do not prove dimensions, connectivity, or editability.

## 5. Prove Parametricity And Persistence

For the nominal model and every required governing edit:

1. Update only the documented governing variable with `define_variables`; this
   operation recomputes the document. Do not reconstruct or rebind features.
2. Inspect the changed feature and protected controls independently with a
   bounded `query_objects` request.
3. Do not issue a separate `recompute_document` call unless a repair operation
   explicitly documents that it does not recompute.
4. Require the intended Body Tip, valid positive-volume BREP geometry, and the
   intended solid count.
5. Save the FCStd, close it, reopen it, apply another documented parameter edit,
   and validate the recomputed document again.
6. Export the validated final Body or Tip with `export_step`, re-import it in a
   clean document, and validate the BREP. STL is a mesh deliverable, not BREP
   evidence.

The native feature tree, `App::VarSet` properties, sketch dimensions, and
expression links are the reproducibility record. A generated Python file is not
required by the default workflow.

## 6. Finish With Evidence

Retain the nominal FCStd and STEP files, parameter manifest, validation results,
variant measurements, deterministic renders, and a concise README. Report tool
versions, assumptions, feature order, variable types, expression bindings,
measurements, repairs, limitations, and topology-sensitive references. Ensure
all final evidence describes the same saved native document.
