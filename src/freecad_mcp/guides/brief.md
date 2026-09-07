# Pinning Down The Request Before Modeling

A request almost never arrives as a specification. It is a sentence of prose,
an image, a drawing, or a conversation that circles the part before it lands.
Convert whatever arrived into explicit working notes before calling any
modeling tool.

These notes are yours. They are not a form for the requester to fill out, and
nobody is waiting to approve them.

## When Someone Is There To Ask

If the request is informal and the requester is present, a short round of
focused questions up front is cheaper than modeling the wrong part. Ask about
what changes the geometry: overall size, what it mounts to or fits, which
dimensions must hold, how many of a repeated feature. Ask them together, not
one at a time.

If nobody is there to answer -- an automated session, or a requester who has
gone -- do not stall. Record each open choice as an explicit assumption and
proceed, as below.

## What The Notes Must Answer

- Overall function and orientation: what the part does and which way is up.
- Units: millimeters unless the request states otherwise.
- Coordinate frame: the origin, the base plane, and which Origin plane each
  planned feature references.
- Governing parameters versus derived dimensions: which values the request
  fixes directly, and which values follow from them by expression.
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

## Assumptions Over Questions, Once Modeling Starts

The round of questions above happens once, before any geometry exists. After
that, state assumptions and proceed; ask only when a choice is genuinely
blocking, meaning it affects fit, safety, or makes the part impossible to
model, and no default or inference resolves it. A cosmetic radius, a default
clearance-hole size, or a free choice of origin does not warrant a question —
record it as an assumption and move on.

Stopping mid-model to ask is expensive and usually avoidable: the answer
almost always exists as a defensible default, and a wrong default is cheap to
change in a parametric model, which is the point of building one.

## Success

The notes are ready for modeling when they fix: units and coordinate frame,
governing parameters, the feature list, and validation targets, with every
remaining gap named as an explicit assumption.
