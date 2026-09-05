# Parameter Variants As Isolated Transactions

## One Variant, One Fresh Copy

Open a fresh copy of the saved nominal FCStd for each variant. Change exactly
one governing value in that copy; leave every other governing value at its
nominal setting. A variant that touches two governing values at once cannot
tell you which one caused a measured change.

## No Extra Recompute

`define_variables` already recomputes the document as part of applying the
change. Do not issue a separate `recompute_document` call after it — the
document is already current.

## Validate, Save, Close

Validate the recomputed variant, save it to an explicit output path distinct
from the nominal file and from every other variant, and close the document
before starting the next variant. Never derive one variant from another
variant's open document; every variant traces back to the same saved nominal
file, not to a chain of prior variants.

## Measure Both Sides

Measure both the value the change was intended to move and the protected
controls that must not move. A variant that shifts an unrelated dimension
alongside the intended one indicates a coupling the parameter set did not
account for.

## What To Retain Per Variant

- The parent nominal file's hash.
- The governing parameter name and the value it was set to.
- The output file paths produced.
- The check results for both the intended change and the protected controls.
