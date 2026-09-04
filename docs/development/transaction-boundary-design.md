# Transaction Boundary Design

Status: Phase 1 implemented
Date: 2026-09-01
Branch: `integration/freecad-compatibility`

Two phases. Phase 1 makes the mutation API safe by moving the transaction
boundary to the executor. Phase 2 closes the ergonomics gap that currently
forces models to reach for `edit_object`.

## Problem

`TRANSACTION_CONFLICT` is the single largest error class the FreeCAD MCP server
produces. Across three local qwen3 runs it is 18 of 36 errors. Every one of them
occurred in a single-call step, so overlapping parallel mutation is not the
cause: the server conflicts with itself.

In `logs/freecad-mcp-local-fresh.jsonl` (qwen3, 84 calls, 75 minutes), 13 of the
50 calls after call 34 failed this way, in clusters of up to three consecutive
calls, with 34 successes interleaved.

### Correction to an earlier reading of this trace

An earlier draft of this document described the failure as a permanent wedge:
one bad call leaving the session unable to mutate ever again. **That was wrong**,
and the live probe in `## Probe findings` is what caught it. The conflicts are
intermittent, not terminal, and `edit_object` at call 34 was a coincidence of
timing rather than the trigger. The corrected mechanism is below and is verified
live rather than inferred from the trace.

The cost is real but smaller than first claimed: a recurring self-inflicted error
class that the model cannot diagnose or clear, not a lost session.

## FreeCAD's transaction model

The document-level API is a facade over an application-level one. From
`src/App/Document.pyi:158`:

> `openTransaction(name)` - This function no longer creates a new transaction,
> but calls `FreeCAD.setActiveTransaction(name)` instead, which will auto create
> a transaction with the given name when any change happened in any opened
> document.

Application level, the real one:

- `setActiveTransaction(name, persist=False)` returns an ID. It creates nothing.
  It arms an intent: the next change in any document opens a transaction with
  this name and ID.
- `getActiveTransaction()` returns `(name, id)`.
- `closeActiveTransaction(abort=False)` commits or aborts it.

With `persist=False`, FreeCAD auto-closes the transaction when a Gui command
stack unwinds. Bridge code is executed from a socket handler, not inside a Gui
command stack, so nothing auto-closes it.

Document level, per-document materialization:

- `HasPendingTransaction`, whether this document materialized one.
- `getBookedTransactionID()`, which application ID this document booked.
- `commitTransaction()` / `abortTransaction()`, act on this document's
  materialized transaction.
- `UndoMode`, 0 disables undo entirely.

Between `openTransaction()` and the first property change no transaction exists
in any document; the application holds an armed name and ID. The first mutation
to any open document books that ID. If several documents change they book the
same ID and undo together.

## Root cause

Verified live against FreeCAD 1.1 headless on 2026-09-01. Three RPC calls, each
checking `App.getActiveTransaction()` from a *separate* later call:

```text
baseline active:                                        None
openTransaction + addObject + commitTransaction  ->     ['Case A Booked', 1]
openTransaction + no change  + commitTransaction ->     ['Case B Unbooked', 2]
```

**`Document.commitTransaction()` does not close the application-level
transaction.** Because `Document.openTransaction(name)` is a facade over
`App.setActiveTransaction(name)`, committing the document's transaction leaves
the application's armed and active — visible to the *next* RPC call, whether or
not any document booked it.

That is the whole defect. Every mutating tool does:

```python
open_owned_transaction(doc, "Define Variables")   # arms an app transaction
try:
    ...
    doc.commitTransaction()                       # does NOT disarm it
```

and every mutating tool begins by refusing to start when one is already active:

```python
if has_open_transaction(document):
    raise RuntimeError("TRANSACTION_CONFLICT: Document already has a pending transaction")
```

So a successful tool call can leave the next one to fail. FreeCAD does clear the
armed transaction on its own shortly afterwards, which is exactly why the errors
come in short clusters rather than permanently.

Two further defects make it worse and unrecoverable from the model's side:

**1. Transaction state cannot survive a call.** The addon builds a fresh
`exec_globals` for every execution (`server.py:880`), so `WORKFLOW_HELPERS` is
re-executed and `_owned_transaction_id = None` on every call. A transaction left
armed by call N is, from call N+1's view, a stranger's: `abort_owned_transaction`
compares the live ID against `None` and declines to close it. The model has no
tool that can clear the state — it can only retry until FreeCAD clears it
itself. `bridge/embedded.py:_execute_code` has the same defect.

**2. The conflict check is not document-scoped.** `has_open_transaction()`
returns true if any application transaction is active, regardless of which
document it concerns. A leftover from one document blocks mutations on every
other.

### A separate, real, but non-triggering defect

`create_object`, `edit_object`, and `delete_object` mutate in the *bridge* layer
(`bridge/socket.py:611`) with no transaction at all; `bridge/xmlrpc.py:670` uses
a raw `openTransaction` with no abort on failure. The probe confirms these do
**not** cause the conflicts — an untransacted mutation arms nothing, so it leaks
nothing.

They are still worth fixing: their changes are not undoable, which is a
correctness gap of its own. This is a layering artifact rather than an oversight.
The owned-transaction discipline arrived in `6d9fc30` and was applied to the new
typed tools, which generate mutations at the *tool* layer where
`WORKFLOW_HELPERS` is injected; that commit touched `tools/objects.py` and
`tools/utils.py` but not `bridge/socket.py`.

The parametric profile excludes `create_object` and `delete_object` but keeps
`edit_object`, because the typed surface has no generic property setter. Nothing
sets a plain literal property value. That gap is the subject of Phase 2.

### Why the planned fix addresses this

The executor-owned boundary calls `closeActiveTransaction()` in a `finally` on
every armed call. Unlike `commitTransaction()`, that call disarms the
application-level transaction unconditionally — booked or not, success or
failure. No call can leave state behind for the next one, so the conflict class
disappears rather than becoming rarer.

## Phase 1: make the API safe

### Move the boundary to the executor

There are exactly two execution chokepoints:

- `_execute_code_sync` in the addon (`server.py:867`, sole caller at line 805).
  Socket and xmlrpc both feed one request queue, so this covers both network
  modes.
- `_execute_code` in `bridge/embedded.py`.

Both gain the same boundary:

```python
armed = False
if transactional:
    pre = FreeCAD.getActiveTransaction()
    if pre and pre[1]:
        return error("TRANSACTION_CONFLICT: operator transaction active")
    FreeCAD.setActiveTransaction(name, persist=True)
    armed = True
ok = False
try:
    exec(compiled, exec_globals)
    ok = True
finally:
    if armed:
        FreeCAD.closeActiveTransaction(abort=not ok)
```

`persist=True` is load-bearing. With the default, a Gui command triggered from
inside the executed code could close our transaction underneath us mid-call.
With `persist=True` the `finally` is the sole closer.

The pre-flight check preserves operator safety: we still refuse a transaction we
did not arm. Because our own leaks become impossible, that refusal turns from
permanent and self-inflicted into rare and honest.

### Required transaction declaration, no compatibility shim

`execute_python` gains a required `transaction` parameter across `base.py`,
`socket.py`, `xmlrpc.py`, and `embedded.py`. The socket wire format changes from
`{"code": code}` to `{"code": code, "transaction": <name or null>}`. A missing
or unrecognised field is an error, never a silent `false`.

There are 111 `execute_python` call sites. Making the parameter required means
mypy forces every one to declare intent, and a tool added later that forgets to
declare fails to type-check rather than quietly mutating outside a transaction.
That enforcement is the point of the change, not a side effect.

Non-transactional set, declared explicitly at each call site: `undo`, `redo`,
`undo_if_invalid`, `open_document`, `close_document`, `save_document`, and all
read-only tools. Undo and redo especially - running them inside an open
transaction invites corruption.

### Remove the old machinery

Delete from `WORKFLOW_HELPERS`: `_owned_transaction_id`,
`open_owned_transaction`, `abort_owned_transaction`, `has_open_transaction`,
`active_application_transaction`. Remove `wrap_with_transaction` and the 54 raw
`openTransaction` sites across 7 files: `objects.py` (20), `partdesign.py` (18),
`spreadsheet.py` (6), `draft.py` (5), `bridge/xmlrpc.py` (3), `validation.py`
(1), `view.py` (1).

Tools that deliberately roll back - the volume-reduction and one-solid
rejections - already raise inside their `try`. They keep working by doing less:
raise, and the executor aborts. Each currently hand-rolls
abort-then-recompute-then-reraise; that goes away.

`document_revision` and `require_expected_revision` stay. They serve
`query_objects` cursors and stale-revision detection, which are unrelated.

### Testing

The existing unit tests exercise `WORKFLOW_HELPERS` against a fake FreeCAD.
That harness cannot model lazy booking, which is exactly where the bug lives, so
Phase 1 needs live coverage.

1. **Live probe, before any fix.** On a scratch document, reproduce the wedge:
   call `edit_object` with a dict for a Placement property, then assert
   `getActiveTransaction()` is non-null and that close/reopen does not clear it.
   This confirms which call arms the leak, which the trace shows only by timing.
2. **Live regression, after.** The same sequence leaves no active transaction,
   and the next mutating call succeeds.
3. **Unit tests** for the executor boundary itself: armed-then-raised aborts,
   armed-then-succeeded commits, a pre-existing foreign transaction is refused
   and not closed, and a non-transactional call arms nothing.
4. **Confirm the no-op case live**: `closeActiveTransaction` on an armed but
   never-booked transaction, where a mutating tool raised before touching
   anything. Expected harmless under lazy booking; verify rather than assume.

Add to `tests/integration/`, following `test_stage_c_regressions.py`.

### Known residual risk

Execution is queued onto the main thread with a cancellation path (`_cancelled`,
`execution_continues`). A timed-out request abandons the waiter, not the
execution, so `finally` still runs but late. A transaction can stay open past
the tool's error return. Bounded and self-clearing, not a wedge. Document it;
do not fix it in Phase 1.

## Phase 2: close the ergonomics gap

Phase 1 downgrades a bad `edit_object` call from *session over* to *one failed
call with a poor error message*. It does not remove the reason models reach for
`edit_object` in the first place.

Scope, to be designed after Phase 1 lands:

- `edit_object` accepts `dict[str, Any]` and lets FreeCAD's C++ bindings raise
  raw `TypeError`. It should coerce known property shapes (placements,
  vectors, rotations) or reject with a typed `INVALID_INPUT` naming the expected
  form.
- Decide whether the typed surface grows a proper placement/attachment tool so
  `edit_object` can leave the parametric profile entirely. This is the real
  question; input coercion alone just makes the stopgap safer.
- `bind_expressions` needs the per-item diagnostics and partial-commit behaviour
  `define_variables` already has. Eight of qwen's 36 errors, and it drives
  fallback to per-property `set_expression` loops, which cost turns twice.
- `create_constrained_sketch` surfaces raw pydantic `value_error` text. Four
  qwen errors, and the handoff records a case where a rejected declarative
  sketch forced 129 granular constraint calls.

## Out of scope

Turn-count reduction (`create_variant`, relaxed validation gates) and the
screenshot workflow. They are recorded in the experiment's `HANDOFF.md` and are
not blocked by this work.

## Consequences for prior runs

Phase 1 changes the system under test. Runs made after it are a new condition
and are not comparable with Stage D or the local v1/v2 sessions. Frozen archives
must not be rerun or repaired.

## Probe findings

Probed on 2026-09-01 against FreeCAD headless (instance `aa27beda`), using the
current two-argument `execute(code, timeout_ms)` protocol.

| Value                                  | Result           |
| -------------------------------------- | ---------------- |
| `error_type` of the failed edit        | `TypeError`      |
| `getActiveTransaction()` after failure | `None` (no leak) |
| Next mutation succeeded                | `True`           |

**No wedge observed.** Under the current two-argument protocol, a failed
mutation leaves no active transaction and the next mutation succeeds immediately.
The severity claim in the spec ("every subsequent mutating call fails with
`TRANSACTION_CONFLICT` forever") is not reproduced against this FreeCAD version
and bridge revision.

The structural defects in the spec's Root Cause — missing `transaction` parameter
on `_xmlrpc_execute`, no `abortActiveTransaction` on error, and no executor-owned
boundary — remain independently valid. The three-argument tests in
`tests/integration/test_transaction_boundary.py` fail on arity (not on the
wedge itself), confirming the protocol change is genuinely absent and required.

### Controller probes through the transaction path

The probe above sent raw Python through `proxy.execute`, which carries no
`WORKFLOW_HELPERS` and therefore never calls `openTransaction`. Nothing was
armed, so nothing could leak — it tested the wrong layer. Probing the
transaction path directly, with every `getActiveTransaction()` check made from a
*separate* later RPC call:

```text
baseline active:                                        None
openTransaction + addObject + commitTransaction  ->     ['Case A Booked', 1]
openTransaction + no change  + commitTransaction ->     ['Case B Unbooked', 2]
```

`commitTransaction()` leaves the application-level transaction armed, booked or
not. A later probe run minutes afterwards still saw `['Case B Unbooked', 2]` as
its baseline, so a leftover persists rather than clearing quickly. What clears
them intermittently in a real session is not established; a subsequent
`setActiveTransaction` replaces the armed entry, which is one route.

Contrast `closeActiveTransaction()`, which the planned boundary uses:

```text
arm + mutate + closeActiveTransaction(False)   -> active None,  object kept
arm + mutate + raise + closeActiveTransaction(True)
                                               -> active None,  object KEPT (!)
arm + no change + closeActiveTransaction(True) -> active None
```

It disarms in every case. But note the second line: the abort did **not** roll
back. The cause is `UndoMode`, which defaults to `0` on a new document:

```text
default UndoMode of a new doc: 0
abort with UndoMode = 0  ->  objects after abort: ['Kept', 'RolledBack']
abort with UndoMode = 1  ->  objects after abort: []
```

With undo disabled, `closeActiveTransaction(abort=True)` silently keeps the
mutation. The old per-tool `open_owned_transaction` set `UndoMode = 1` before
opening; the executor-owned boundary must do the same across every open
document, or it would report a rollback that never happened.
