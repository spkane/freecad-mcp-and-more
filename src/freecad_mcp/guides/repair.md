# Repairing A Rejected Operation

## Error Codes

`VALIDATION_FAILED` means the operation was rejected and rolled back. Read the
reported failing inputs, fix the smallest responsible one, and rerun only that
operation — do not resubmit the whole batch unchanged, and do not add a new
feature to work around the rejection.

`UNDER_CONSTRAINED` means the sketch solved without conflict but still has
degrees of freedom. Nothing is fighting: add dimensions or geometric
constraints until the count reaches zero. Do not delete constraints for this
one -- deleting makes it worse.

`SOLVER_CONFLICT` means the solver rejected the sketch. The message carries
the indices it rejected, grouped as redundant, partially redundant,
conflicting or malformed, along with FreeCAD's own description. Delete or
relax one of the named constraints; do not guess at others.

`STALE_REVISION` means the `document_ref` revision you carried is no longer
current. This is the normal consequence of a preceding rejected batch or any
mutation you did not track: re-read current state with a bounded
`query_objects` or `get_variables` call, and carry the fresh revision forward.
Never retry the same call blind against a stale revision; the retry will only
fail the same way.

## Undo Over Compensation

Use `undo` for a bad mutation rather than stacking a compensating feature on
top of an invalid tree. A compensating feature built on invalid geometry
inherits that invalidity; undoing the bad step and rebuilding it correctly
does not.

## Local Repair Tools

Granular `create_sketch`, `add_sketch_line`, `add_sketch_constraint`,
`set_expression`, and `get_sketch_info` exist for local repair only. Reach for
them when a declarative operation has already reported a specific invalid
input or solver conflict and the fix is localized — not as a first choice over
the task-oriented commands.
