# The Design Brief Gate

Modeling does not start without a thorough design brief.

There are two cases and only two:

- **A brief was supplied.** Check it against the sections below. If it
  answers them, start. If it leaves one open, that gap is a question, not an
  assumption to make quietly.
- **No brief was supplied.** Grill the requester until there is one.

Either way, write `design-brief.md` before the first modeling call, and keep
it current as decisions change. When a brief was supplied and is thorough,
the file records it plus every gap you closed and how. The file is what a
later reader -- or you, forty calls from now -- checks the model against.

## What Makes A Brief Thorough

The same list judges a supplied brief and drives a grilling session. Every
item is answered, explicitly waived, or recorded as a stated assumption.

- Overall function and orientation: what the part does and which way is up.
- Units: millimeters unless the request states otherwise.
- Coordinate frame: the origin, the base plane, and which Origin plane each
  planned feature references.
- What the part fits, mounts to, or holds, and the dimensions that must hold
  for it to do so.
- The parametric contract: which values govern, which derive, which are
  incidental, and the range each governing value must survive. See below.
- The semantic features the part must have: holes, slots, ribs, bosses,
  pockets, shells, openings, and similar named elements, not raw geometry.
- Validation targets: the measurements that decide whether the result is
  correct, stated as bounding box, solid count, feature counts, or specific
  dimensions to check after building.
- The assumptions taken to fill any gap.

## How To Grill

- **One question at a time.** Wait for the answer before the next one. A
  batch of questions is bewildering and destroys the ordering that makes the
  interview converge.
- **Ask in dependency order.** Each answer reshapes what is worth asking
  next. The stages below are ordered for that reason.
- **Carry a recommended answer with every question.** A requester often does
  not know CAD conventions. "3 mm walls, typical for this size in FDM --
  sound right?" converges far faster than "how thick should the walls be?"
- **Look up facts; ask only decisions.** Anything the environment can settle
  is not a question. Read the FreeCAD version and GUI state from
  `get_connection_status`, the existing objects from `query_objects`, and the
  existing variables from `get_variables`. Standard clearances and typical
  thicknesses are recommendations you make, not questions you ask. What the
  part is for, what it fits, what must flex, and what proves it correct are
  the requester's to decide.
- **Do not start modeling until the brief is complete.** A section the
  requester explicitly waives is recorded as waived, which is not the same as
  unanswered.

## The Stages, In Order

1. **Function and orientation.** What the part does and which way is up.
   Everything else is positioned relative to this.
2. **Envelope and interfaces.** What it mounts to, sits in, or holds, and
   which dimensions are fixed by that. Settle the coordinate frame here too:
   these constraints decide which way the part is built, and nothing else may
   violate them.
3. **The parametric contract.** Which values someone will change later.
   The governing parameters decide the feature tree, so settle them before
   the features that depend on them.
4. **Semantic features.** Now that you know what must flex, which features
   the part has and how each is built.
5. **Validation targets.** The measurements that decide correctness, and the
   values a flex test should try.

## The Parametric Contract

Every dimension and every count is one of three things:

- **Governing** -- someone will change it after the part is built.
- **Derived** -- it follows from a governing value through an expression.
- **Incidental** -- it is what it is, and nobody will reach for it.

The question to put to the requester is "will anyone want to change this
after it is built?" For a count, ask it concretely: "should the number of
windows be adjustable, or is four just what it has?"

**This decides construction, not naming.** A governing count needs a pattern
feature driven by an expression. An incidental count is clearer and more
robust as explicit geometry. Deciding it after the tree is built is too late,
because the answer changes what you build, not just what you name.

Ask the range as well: what values must the part still work at? Those numbers
become the flex-test values later -- see `freecad://guide/variants`.

Do not create a variable for a value the requester called incidental. A
variable that drives nothing is a control that does nothing when edited,
which is worse than its absence because it invites someone to try.

## Reference Images And Drawings

An image without a stated dimension is design intent, not a spec. Establish
scale from one stated dimension or a recognizable object in frame; otherwise
record the proportions as assumptions like any other inferred value.

A technical drawing is a dimensioned contract. Read the title block and units
first. Identify which view maps to which model axis before extracting numbers.
Section views are the source of truth for internal features such as bores and
blind-hole depths. When two dimensioned sources conflict, state the conflict
rather than silently picking one.

## When Nobody Is There To Answer

An automated session, or a requester who has gone, does not lower the bar; it
changes who fills the gaps. Write `design-brief.md` anyway, record every open
choice as an explicit assumption, and mark the load-bearing ones -- the
assumptions that would change the feature tree if they turn out wrong, such
as whether a count is governing. Those are what a reviewer checks first.

## Once Modeling Starts

State assumptions and proceed; ask only when a choice is genuinely blocking,
meaning it affects fit, safety, or makes the part impossible to model, and no
default or inference resolves it. A cosmetic radius, a default clearance-hole
size, or a free choice of origin does not warrant a question -- record it as
an assumption and move on.

Stopping mid-model to ask is expensive and usually avoidable. The answer
almost always exists as a defensible default, and a wrong default is cheap to
change in a parametric model, which is the point of building one.

## Success

The brief is ready when every section above is answered, waived, or recorded
as a stated assumption, and `design-brief.md` says which.
