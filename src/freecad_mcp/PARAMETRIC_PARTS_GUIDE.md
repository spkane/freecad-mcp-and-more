# Native Parametric FreeCAD Parts

Build editable native FreeCAD PartDesign models through typed MCP commands.
The saved FCStd feature tree is the authoritative artifact. STEP files and
images are derived from it. Arbitrary Python execution is deliberately absent.

## Use This Server When

Use it for native parametric solid parts: sketched profiles, pads, pockets,
revolutions, grooves, lofts, patterns, and dress-up features driven by named
variables and expressions. Do not use it for mesh repair, CAM, rendering, or
assemblies of purchased components.

## Default Assumptions

State any departure from these in your handoff.

- Millimeters for length, degrees for angle, with explicit units in variables.
- Origin planes and named datums as supports, in preference to model faces.
- One semantically named `PartDesign::Body` per contiguous part.
- Governing values in one `App::VarSet`; derived values bound by expression.

## Required Workflow

Scale depth to the task. A simple bracket needs a few notes and a few
checks. A parametric family with variants needs the full protocol. The floors
below apply either way.

1. Classify the request: new part, edit of an existing document, parameter
   study, inspection, or repair.
1. Load only the guide topics the task triggers. They are listed at the end.
1. Pin the request down before touching FreeCAD. Turn it into explicit
   dimensions, units, coordinate frame, feature intent, governing parameters,
   and validation targets. Requests normally arrive as a sentence of prose, an
   image, or a drawing rather than a specification; read
   `freecad://guide/brief` for how to convert one. These notes are yours, not
   a document the requester fills in. State assumptions instead of asking,
   unless a choice is genuinely blocking and someone is there to answer.
1. Plan the tree: parameters, datums, Body, and feature order. Primary
   additive form, then cuts, then patterns, then topology-sensitive fillets
   and chamfers. See `freecad://guide/features`.
1. Call `get_connection_status` and `get_freecad_version` once.
1. Create the document, the Body, and the variable set. Define governing and
   derived variables in one compact `define_variables` batch. See
   `freecad://guide/parameters`.
1. Build one sketch or feature group at a time. Trust the local validation
   returned by each mutation; carry `document_ref` and `expected_revision`
   forward. Use `query_objects` for bounded lookups rather than retrieving the
   whole tree.
1. Verify numerically after each meaningful feature group with
   `validate_document(require_single_solid=true)`.
1. Verify visually. Deterministic checks prove validity, not intent. Read
   `freecad://guide/visual-evidence` before capturing, and use
   `capture_feature_view` to look along each opening's own support normal.
1. Save early. The moment the model first satisfies the request, save the FCStd
   and export the STEP, before any refinement.
1. On a rejection, repair the smallest responsible input and rerun only that
   operation. See `freecad://guide/repair`.
1. Prove the model is parametric before calling it done: change governing
   parameters and confirm the model follows, validate the saved document, and
   capture screenshots. These are not optional and do not wait to be asked
   for. Scale the remaining artifacts -- manifest, README, STEP re-import --
   to the task. See `freecad://guide/variants` and
   `freecad://guide/delivery`.

## Handoff

Report the saved FCStd path, the exported STEP path, the retained images you
inspected, the checks that actually ran with their results, the assumptions
you took, and the limitations that remain. Report tool versions, the ordered
feature tree, and any topology-sensitive reference you could not avoid.

## Non-Negotiables

These hold for every part, however small.

- Every driving sketch reports `FullyConstrained` before the feature that
  consumes it is created.
- `validate_document(require_single_solid=true)` passes before any claim that
  the part is finished.
- The FCStd is saved and the STEP exported as soon as the shape first
  satisfies the request, before any refinement. An unsaved model is not a
  deliverable.
- Every semantic opening or profile is seen along its own support normal,
  through `capture_feature_view`, before it is called correct.
- A `warnings` entry on a mutation result is unfinished work. Resolve it, or
  record why it is acceptable.
- Derived values are expressions. Never copy a calculated number between
  features.
- Intended unions have real overlap; point or tangent contact is not
  connectivity.
- Report only checks that actually ran. Never describe an image you did not
  receive and inspect.

## Progressive Guide Topics

Read these when their trigger applies.

- `freecad://guide/brief` — turning prose, an image, or a drawing into
  working notes you can model from.
- `freecad://guide/visual-evidence` — the capture protocol. Read before
  capturing evidence.
- `freecad://guide/parameters` — variable sets, units, and expression binding.
- `freecad://guide/features` — feature order, datums, overlap, and through-cuts.
- `freecad://guide/variants` — isolated one-edit variant transactions.
- `freecad://guide/repair` — `VALIDATION_FAILED`, `STALE_REVISION`, and undo.
- `freecad://guide/delivery` — manifests, READMEs, and re-import evidence.
