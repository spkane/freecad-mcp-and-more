# Proving The Model Is Parametric

Changing a parameter and watching the model follow is the only evidence that
the parameter set is real. Do this before calling any model done, whether or
not anyone asked for variants.

## What To Change

When a request names specific variants, build those. When it does not -- the
usual case -- choose them yourself, spanning the kinds of parameter the model
has rather than several of one kind:

- A primary dimension that most of the model derives from.
- A ratio or fraction, if the part has one.
- A count that drives a pattern.
- A value that positions a datum plane other features are built on.

Three or four is usually enough. The point is coverage of parameter kinds, not
exhaustiveness: `validate_document` already reports `unused_variables` across
the whole set in one call, so the flex test does not need to prove each
variable is wired -- it proves the tree survives being changed.

Push each value far enough to be visible, staying inside what the part is
supposed to support. A change too small to see proves nothing.

The ranges recorded in the design brief are these values. If the brief says a
governing dimension must work from 80 mm to 200 mm, test both ends rather
than nudging it by a millimetre. See `freecad://guide/brief`.

## What Counts As A Failure

- Invalid geometry, a changed solid count, or a feature that lost its
  reference. This is the topology-sensitivity the feature order exists to
  avoid, and a flex test is how it surfaces before a user finds it.
- A protected control moving alongside the intended one, which means a
  coupling the parameter set did not account for.
- **Nothing changing at all.** A parameter that recomputes to identical
  geometry is inert: something references it, so `unused_variables` will not
  catch it, but it drives nothing that matters. This is the failure people
  miss, because the model recomputes cleanly and looks correct.

Record what you changed, what moved, and what did not. Then check the result
visually as well as numerically -- see `freecad://guide/visual-evidence`. A
variant that validates but no longer looks like the part is still a failure.

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
- The output file paths produced, when the variant is a deliverable rather
  than a check.
- The check results for both the intended change and the protected controls.

A flex test run purely as proof does not need its files kept. Validate it,
record what moved, and close it without saving. Keep the files when the
variants are themselves part of what you are delivering.
