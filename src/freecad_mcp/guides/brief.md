# Writing The Brief Before Modeling

Convert a prose request, an image, or a technical drawing into a brief before
calling any modeling tool. The brief is internal note-taking, not a form for
the user to fill out.

## What The Brief Must Answer

- Overall function and orientation: what the part does and which way is up.
- Units: millimeters unless the request states otherwise.
- Coordinate frame: the origin, the base plane, and which Origin plane each
  planned feature references.
- Governing parameters versus derived dimensions: which values the user or the
  brief fixes directly, and which values follow from them by expression.
- The semantic features the part must have: holes, slots, ribs, bosses,
  pockets, shells, openings, and similar named elements, not raw geometry.
- Validation targets: the measurements that decide whether the result is
  correct, stated as bounding box, solid count, feature counts, or specific
  dimensions to check after building.
- The assumptions taken to fill any gap.

## Reference Images And Drawings

An image without a stated dimension is design intent, not a spec. Establish
scale from one stated dimension or a recognizable object in frame; otherwise
record the proportions as assumptions like any other inferred value.

A technical drawing is a dimensioned contract. Read the title block and units
first. Identify which view maps to which model axis before extracting numbers.
Section views are the source of truth for internal features such as bores and
blind-hole depths. When two dimensioned sources conflict, state the conflict
rather than silently picking one.

## Assumptions Over Questions

State assumptions and proceed; ask only when a choice is genuinely blocking,
meaning it affects fit, safety, or makes the part impossible to model, and no
default or inference resolves it. A cosmetic radius, a default clearance-hole
size, or a free choice of origin does not warrant a question — record it as an
assumption and move on.

## Success

The brief is ready for modeling when it fixes: units and coordinate frame,
governing parameters, the feature list, and validation targets, with every
remaining gap named as an explicit assumption.
