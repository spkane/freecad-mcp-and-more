# Native Parametric FreeCAD Parts

Build editable native FreeCAD PartDesign models through typed MCP commands.
The saved FCStd feature tree is the authoritative artifact. STEP files and
images are derived from it. Arbitrary Python execution is deliberately absent.

## Use This Server When

Use it for native parametric solid parts: sketched profiles, pads, pockets,
revolutions, grooves, lofts, patterns, and dress-up features driven by named
variables and expressions. Do not use it for mesh repair, CAM, rendering, or
assemblies of purchased components.

## Conventions

State any departure from these in your handoff.

- Millimeters for length, degrees for angle, with explicit units in variables.
- Origin planes and named datums as supports, in preference to model faces.
- One semantically named `PartDesign::Body` per contiguous part.
- Governing values in one `App::VarSet`; derived values bound by expression.

## Required Workflow

Scale depth to the task. A simple bracket needs a few notes and a few checks.
A parametric family with variants needs the full protocol. The
non-negotiables below apply either way.

1. Classify the request: new part, edit of an existing document, parameter
   study, inspection, or repair.
1. Load only the guide topics the task triggers. They are listed at the end.
1. Settle the design brief before modeling. Read `freecad://guide/brief`.
1. Plan the tree: parameters, datums, Body, and feature order. See
   `freecad://guide/features`.
1. Call `get_connection_status` and `get_freecad_version` once.
1. Create the document, the Body, and the variable set. See
   `freecad://guide/parameters`.
1. Build one sketch or feature group at a time. Trust the local validation
   returned by each mutation; carry `document_ref` and `expected_revision`
   forward. Use `query_objects` for bounded lookups rather than retrieving
   the whole tree.
1. Verify numerically after each meaningful feature group with
   `validate_document(require_single_solid=true)`.
1. Verify visually. Deterministic checks prove validity, not intent. Read
   `freecad://guide/visual-evidence`.
1. Save the FCStd and export the STEP as soon as the shape first satisfies
   the request. See `freecad://guide/delivery`.
1. On a rejection, repair the smallest responsible input and rerun only that
   operation. See `freecad://guide/repair`.
1. Prove the model is parametric, then deliver. See
   `freecad://guide/variants` and `freecad://guide/delivery`.

## Non-Negotiables

These hold for every part, however small.

- Modeling does not start without a thorough design brief.
- Every driving sketch reports `FullyConstrained` before the feature that
  consumes it is created.
- `validate_document(require_single_solid=true)` passes before any claim that
  the part is finished.
- The FCStd is saved and the STEP exported as soon as the shape first
  satisfies the request, before any refinement. An unsaved model is not a
  deliverable.
- Every semantic opening or profile is seen along its own support normal,
  through `capture_feature_view`, before it is called correct.
- Governing parameters are changed and the model confirmed to follow, before
  the model is called done. A model only ever seen at nominal is not known to
  be parametric.
- No variable drives nothing. `validate_document` reports the ones that do.
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

- `freecad://guide/brief` — the design brief gate: judging a supplied brief,
  and grilling for one when it is missing. Read before modeling.
- `freecad://guide/parameters` — variable sets, units, expression binding,
  and which values become variables at all.
- `freecad://guide/features` — feature order, datums, overlap, through-cuts,
  and the checks each feature must pass.
- `freecad://guide/visual-evidence` — the capture protocol. Read before
  capturing evidence.
- `freecad://guide/repair` — error codes, what each one means, and undo.
- `freecad://guide/variants` — proving the model is parametric by changing
  governing parameters. Not optional.
- `freecad://guide/delivery` — what always ships, what scales to the task,
  and the handoff report.
