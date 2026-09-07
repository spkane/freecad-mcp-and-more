# Feature Order And Supports

## Stable Feature Order

Build in a stable order: the primary additive form first, then cuts, then
patterns, then topology-sensitive fillets and chamfers last. Fillets and
chamfers reference edges that shift whenever upstream geometry changes, so
placing them late keeps the rest of the tree from breaking every time a fillet
radius or cut is adjusted.

## Real Connectivity

Give intended unions real overlap. Point or tangent contact is not reliable
connectivity — a boolean union that depends on two faces meeting exactly
produces a fragile or invalid result under small parameter changes. Extend
through-cuts beyond both sides of the target material so the cut remains a
clean through-cut as dimensions vary.

## Supports And References

Use `create_datum_plane` when a stable offset support is clearer than tying a
sketch to a Body face directly. Prefer Origin planes and named datums over
generated `FaceN` or `EdgeN` references — generated references renumber when
upstream topology changes, while an Origin plane or a named datum does not. If
an unavoidable topology-sensitive reference remains, record it explicitly and
retest that it still resolves correctly after the document is saved and
reopened.

## Fully Constrained Before Consuming

A driving sketch reports `FullyConstrained` before the feature that consumes
it is created. An under-constrained sketch has degrees of freedom the solver
is free to resolve differently on the next recompute, so a feature built on
one can change shape when an unrelated parameter moves. The mutation result
carries the solver state; read it rather than assuming.

This is not the same as a conflict. Degrees of freedom mean constraints are
missing, so add dimensions or geometric constraints until the count reaches
zero -- deleting constraints makes it worse. See `freecad://guide/repair`.

## Creating And Validating Features

Complete constrained sketches are created with `create_constrained_sketch` and
then consumed by feature tools. Additive features such as `pad_sketch` must
increase Body volume; a feature that has no effect or that reduces volume where
an addition was intended indicates the wrong operation or the wrong sketch, and
should be rejected rather than accepted as a no-op. A pattern must become the
Body Tip while retaining exactly one solid — a pattern that leaves disconnected
solids or fails to advance the Tip has not produced the intended feature.
