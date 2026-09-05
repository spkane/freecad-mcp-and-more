# Diagnostic Reporting: Findings and Future Work

Recorded 2026-09-05 from two benchmark runs of the parametric lighthouse
task on `llama-swap/qwen3.8:latest` against
`integration/freecad-compatibility`. Both runs consumed their full
two-hour budget. Every item below is evidence from those traces and the
operator's FreeCAD Report view, not speculation.

## What the runs showed

FreeCAD almost always knows what went wrong. It prints the diagnosis to
the Report view, which no MCP client can read, and returns to the caller
only a restatement of the failure.

| Report view                                    | What the tool returned              |
| ---------------------------------------------- | ----------------------------------- |
| `Remove the following redundant constraint: 7` | `state: ['Touched', 'Invalid']`     |
| `Unit mismatch in plus operation`              | `'Object state is invalid'`         |
| `Revolve axis intersects the sketch`           | `'Feature has no result shape'`     |
| `Spire: Wire is not closed.`                   | `getStatusString()` returns `Error` |

The cost is measurable. The agent hit the redundant-constraint failure
seven times and reconstructed the diagnosis by hand across several turns
at roughly 70 seconds each, never learning the index. It hit the same
unit mismatch through two tools; the one that explained it
(`define_variables`) had the expression corrected 26 seconds later, and
the one that did not (`bind_expressions`) produced two blind retries. The
final fifteen minutes were spent deleting sketch geometry to repair a
profile whose only defect, `Wire is not closed`, was never reported.

## What has been fixed

- `object_diagnostics` in the generated-code prelude reads
  `getStatusString()`, the sketch solver's `RedundantConstraints`,
  `PartiallyRedundantConstraints`, `ConflictingConstraints` and
  `MalformedConstraints`, and `FullyConstrained`.
- `bind_expressions`, `set_expression` and `define_variables` evaluate a
  failed expression with `evalExpression` to recover FreeCAD's message.
- `validate_document` returns a `diagnostics` map keyed by object name.
- `object_diagnostics` reads the Report view widget through Qt and
  attaches the lines FreeCAD printed for that object.
- `WorkflowToolError` states in prose that a failed call was rolled back.
- `capture_feature_view` frames a focus with the `ViewSelection` view
  command; `View3DInventorPy` has no `fitSelection` method.

## Future work

### 1. Report view capture is GUI-only and position-dependent

Reading the Report view widget through Qt works, and is the only route
available: `FreeCAD.Console` exposes `GetObservers`, `GetStatus` and
`SetStatus`, but no `AddObserver`, so a Python console observer cannot
be registered in FreeCAD 1.1.

The consequences:

- Headless FreeCAD returns nothing. The guard is correct but the
  diagnosis is simply absent there, which is where CI runs.
- Attribution is by the `<name>:` prefix FreeCAD happens to use. A
  message printed without that prefix is not attributed to any object.
- The widget accumulates. Lines are matched across the whole buffer, so
  a stale message from an earlier failure can be reported against a
  later one. Capturing a baseline offset before each execution and
  reporting only the delta would fix this, and belongs in the bridge
  executor rather than in generated code.

The durable fix is upstream: a console observer reachable from Python,
or per-object error text on `App::DocumentObject`.

### 2. Feature recompute messages are not structurally available

`getStatusString()` returns FreeCAD's real message for some failures
(`No object linked`, `Linked shape object is empty`) but not others. A
`PartDesign::Revolution` whose axis intersects its profile reports only
`Null shape`, while the Report view names the cause. Until item 1 is
solid, this class is diagnosable only through the widget.

### 3. The bridge's own defects

- `Queue processing error: argument 1 must be str, not int`, seen once
  at 15:20:43 during a run. Not traced to a cause.
- The server sets the deprecated `Midplane` property on extrusions.
  FreeCAD warns that it has been replaced by `SideType` and will be
  removed.

### 4. Pre-existing code generation defect

`"is" with 'str' literal` appears three times in the screenshot codegen
and recurs roughly 27 more times across `embedded.py`, `socket.py` and
`xmlrpc.py`. It is a `SyntaxWarning` in the operator's console today and
a `SyntaxError` under `-W error`. The same defect was fixed in
`view_code.py` by binding the name to a variable before comparison.

### 5. Never verified

- `safety` and `trivy` have not run against this branch. They need mise
  and a Safety account.
- The construction-helper TypeIds in `capture_feature_view` have no GUI
  integration test. The design named one; it does not exist.

## Rollback: already implemented, now legible

Auto-abort of a failed call was already in place before these runs.
`_execute_code_sync` arms `setActiveTransaction(name, persist=True)` and
closes it in a `finally` with `closeActiveTransaction(not succeeded)`,
after forcing `UndoMode = 1` on every open document, because a document
with undo disabled silently keeps the mutation instead of rolling it
back.

Verified live on 2026-09-05: a call that added a `Part::Box`, recomputed,
and then raised left no object behind.

The defect was not the behaviour but the reporting. `committed=false`
appeared as a token inside the message prefix, and the trace shows the
model reading past it and then searching for damage that did not exist.
Error messages now say so in words. Two things remain open:

- Success responses say nothing about the transaction at all. A model
  that cannot tell a committed call from a rolled-back one has to infer
  it from the error text.
- Nothing tells a model how many times it has retried the same failing
  call. The repair loops in both runs were repetitions of one operation
  with small variations, which the server could detect and name.
