# Delivering Evidence

Produce the following only when the brief asks for them — they are delivery
artifacts, not a mandatory step of every modeling session.

## Parameter Manifest

A parameter manifest lists every governing and derived value: its name, type,
value, unit, formula where derived, and the expression target it drives. The
manifest is how someone other than the model reconstructs what each parameter
does without opening the document.

## README

A README covering: the assumptions taken while writing the brief, the ordered
feature tree, the measurements taken and their results, any repairs performed
and why, any topology-sensitive references that remain, and known
limitations.

## Persistence and Parametricity

The persistence proof is: save the FCStd, close it, reopen it, apply another
documented parameter edit, and validate the recomputed document. The native feature tree,
App::VarSet properties, sketch dimensions, and expression links form the
reproducibility record — they prove the model rebuilds correctly from named
parameters rather than relying on incidental model state.

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
