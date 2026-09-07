# Delivering Evidence

## Always, Before You Call A Model Done

Three things are not optional and do not wait to be asked for. A request
rarely arrives as a formal specification -- usually it is a sentence or two of
prose, refined by conversation -- and nobody thinks to ask for proof that a
parametric model is actually parametric. Prove it anyway.

1. **Flex it.** Change governing parameters and confirm the model follows.
   A model only ever evaluated at its nominal values is not known to be
   parametric; it is a one-off that happens to have variables attached. See
   `freecad://guide/variants`, which covers what to change and what counts as
   a failure.
2. **Validate it.** `validate_document(require_single_solid=true)` on the
   final saved document. Read `unused_variables` in the result: a variable
   that drives no geometry is a control that does nothing when edited, which
   is worse than its absence because it invites someone to try.
3. **Look at it.** Screenshots of the finished model, and of each semantic
   opening along its own support normal. See
   `freecad://guide/visual-evidence`.

The artifacts below scale to the task. A quick bracket needs the three checks
above and a screenshot; a parametric family someone else will maintain needs
the manifest and README as well. Produce what the work warrants, and say what
you produced.

## Design Brief

`design-brief.md` is part of the delivered set, not scratch. It records what
the model was built to answer: the governing parameters and their ranges, the
features required, the validation targets, and every assumption taken to fill
a gap. Someone deciding whether the model is correct reads this first.

## Parameter Manifest

A parameter manifest lists every governing and derived value: its name, type,
value, unit, formula where derived, and the expression target it drives. The
manifest is how someone other than the model reconstructs what each parameter
does without opening the document.

## README

A README covering: the assumptions taken while planning, the ordered
feature tree, the measurements taken and their results, any repairs performed
and why, any topology-sensitive references that remain, and known
limitations.

## STEP Re-Import Validation

Export the validated document with `export_step`, re-import the STEP into a
clean document, and validate the re-imported BREP. A STEP export that fails to
re-import cleanly is not a working deliverable, whatever the original document
showed. STL is a mesh deliverable and not BREP evidence.

## Persistence And Parametricity

The persistence proof is: save the FCStd, close it, reopen it, apply another
documented parameter edit, and validate. The native feature tree, App::VarSet
properties, sketch dimensions, and expression links form the reproducibility
record.

## Failure Demonstration

Demonstrate that an invalid parameter value produces a clear failed
recompute rather than a silently wrong shape — for example, a negative
dimension or a value that would collapse a profile. This shows the model
rejects bad input instead of producing invalid geometry quietly.

## One Document, Throughout

All final evidence — the manifest, the README's measurements, the screenshots,
and the STEP file — must describe the same saved document. Evidence collected
from an earlier or divergent state of the model is not evidence for the
delivered one.

Backup `.FCStd1` files are not deliverables; do not include them in the
delivered set.
