# Transaction Boundary (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make it structurally impossible for a failed MCP tool call to leave a FreeCAD application transaction open and wedge every subsequent mutation.

**Architecture:** Move the transaction boundary out of generated FreeCAD code and into the two executor chokepoints that every tool call passes through. The executor arms an application transaction with `setActiveTransaction(name, persist=True)` before `exec`, and closes it in a `finally` — committing on success, aborting on failure. Each `execute_python` call declares its intent with a required `transaction` parameter: a human-readable name for mutating calls, `None` for read-only ones. The per-tool transaction machinery is then deleted.

**Tech Stack:** Python 3.11, FastMCP, FreeCAD 1.1 Python API, pytest, uv, just, ruff, mypy.

**Spec:** `docs/development/transaction-boundary-design.md`

## Global Constraints

- **Python 3.11 exactly.** Must match FreeCAD's bundled Python; a mismatch causes SIGSEGV on `import FreeCAD`. See `CLAUDE.md`. Do not change `.mise.toml` or `pyproject.toml` Python pins.
- **No compatibility shim.** `transaction` is a required parameter and a required wire field. A missing or unrecognised field is an error, never a silent `None`.
- **`persist=True` is mandatory** on every `setActiveTransaction` call. The default auto-closes the transaction when a Gui command stack unwinds, which would close ours mid-call.
- **Enable `UndoMode` before arming.** A document's `UndoMode` defaults to `0`, and with undo disabled `closeActiveTransaction(abort=True)` silently keeps the mutation rather than rolling it back. Verified live on 2026-09-01. The old per-tool `open_owned_transaction` did this; the executor must too, across every open document.
- **Never abort a transaction we did not arm.** The pre-flight check refuses and returns an error; it must not call `closeActiveTransaction` on a foreign transaction.
- **Preserve unrelated working-tree changes.** `.mise.toml`, `pyproject.toml`, `uv.lock`, and `docs/development/compact-local-coding-agent-research.md` carry in-flight work and must not appear in any commit. Stage files explicitly by path; never `git add -A` or `git commit -a`. (`spreadsheet.py` and `test_tools_spreadsheet.py` were on this list until their in-flight work was committed as `b9eea05`; they are now ordinary files, and Task 3 deletes them.)
- **FreeCAD is operator-owned.** Addon changes require reinstall (`just install`) and a FreeCAD restart. These are operator steps — ask, do not run them unprompted.
- **Quality gate:** `just testing::unit`, `just quality::lint`, and `uv run pre-commit run mypy --all-files` must pass before every commit.
- **Do not use `just quality::typecheck` as a completeness gate.** It runs `uv run mypy src`, so it never checks `tests/` — it missed 7 call-site errors in Task 2. Use `uv run pre-commit run mypy --all-files`, which covers the whole tree.
- **mypy alone is NOT a completeness gate for this protocol change.** It proves the typed `execute_python` call sites and nothing more. Raw `proxy.execute(code)` calls against the XML-RPC proxy are untyped and invisible to it — 16 of them across 7 integration files, plus `XmlRpcBridge.ping`, broke at runtime while mypy reported clean. The real gate is `uv run python -m pytest tests/integration -q --timeout=60` over the WHOLE directory, with headless FreeCAD running.
- **Two broken tool shims on this machine.** `.venv/bin` carries stale shebangs pointing at a different repo path, so `uv run mypy` fails to spawn and `uv run pytest` resolves to a system PyPy 2.7 that dies on modern annotations. Working routes: `uv run pre-commit run mypy --all-files` and `uv run python -m pytest`.

---

## File Structure

**Addon (runs inside FreeCAD)** — `freecad/RobustMCPBridge/freecad_mcp_bridge/server.py`
Owns the transaction boundary for socket and xmlrpc modes. Both feed one request queue, so `_execute_code_sync` is a single chokepoint. `ExecutionRequest` and `_execute_via_queue` carry the transaction name from entry point to executor.

**Embedded bridge** — `src/freecad_mcp/bridge/embedded.py`
A separate in-process executor with the identical structure and the identical defect. Gets the same boundary.

**Bridge clients** — `src/freecad_mcp/bridge/{base,socket,xmlrpc,embedded}.py`
`execute_python` gains a required `transaction` parameter. `base.py` defines the contract; the other three implement it and put the field on the wire.

**Tool modules** — `src/freecad_mcp/tools/*.py`
Task 3 deletes `spreadsheet.py` entirely, so the migration tasks that follow do not touch it.
108 `execute_python` call sites declare intent. The mutating ones then shed their in-code transaction handling.

**Helpers** — `src/freecad_mcp/tools/utils.py`
`WORKFLOW_HELPERS` loses its five transaction functions. `document_revision` and `require_expected_revision` stay — they serve query cursors and stale-revision detection.

**Tests** — `tests/integration/test_transaction_boundary.py` (new; all seven boundary tests run against live headless FreeCAD), `tests/unit/test_tools_utils.py`, `tests/unit/test_embedded_bridge.py` (one mocked test, per the project's embedded-mode policy)

---

### Task 1: Failing live regression that proves the wedge

The existing unit tests run `WORKFLOW_HELPERS` against a fake FreeCAD. That harness cannot model lazy transaction booking, which is exactly where this bug lives. This test must run against live FreeCAD.

Written first, and expected to **fail** — that failure is the probe that confirms the mechanism the trace only shows by timing.

**Files:**

- Create: `tests/integration/test_transaction_boundary.py`

**Interfaces:**

- Consumes: only the `xmlrpc_proxy` fixture from `tests/integration/conftest.py`. These tests drive the addon over raw XML-RPC deliberately, so they stay unaffected by the client-side changes in Task 2 Step 6.
- Produces: `test_failed_mutation_leaves_no_active_transaction`, `test_wedge_survives_document_reopen`, `test_armed_but_unbooked_transaction_closes_cleanly`. Task 2 Step 9 adds four more to the same file; Task 6 re-runs all seven as the acceptance gate.

- [ ] **Step 1: Write the failing test**

```python
"""Live regressions for the executor-owned transaction boundary."""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration


def _active_transaction(proxy) -> object:
    """Return FreeCAD's active application transaction, or None."""
    result = proxy.execute(
        "import FreeCAD\n"
        "_active = FreeCAD.getActiveTransaction()\n"
        "_result_ = list(_active) if _active else None\n",
        30000,
        None,
    )
    assert result["success"], result.get("error_message")
    return result["result"]


def _make_scratch_document(proxy) -> str:
    """Create a throwaway document with one sketch-bearing body."""
    name = f"txn_probe_{uuid.uuid4().hex[:8]}"
    result = proxy.execute(
        f"import FreeCAD\n"
        f"doc = FreeCAD.newDocument({name!r})\n"
        f"body = doc.addObject('PartDesign::Body', 'Body')\n"
        f"sketch = doc.addObject('Sketcher::SketchObject', 'ProbeSketch')\n"
        f"body.addObject(sketch)\n"
        f"doc.recompute()\n"
        f"_result_ = doc.Name\n",
        30000,
        "Create Probe Document",
    )
    assert result["success"], result.get("error_message")
    return result["result"]


def _close_scratch_document(proxy, doc_name: str) -> None:
    proxy.execute(
        f"import FreeCAD\n"
        f"if {doc_name!r} in FreeCAD.listDocuments():\n"
        f"    FreeCAD.closeDocument({doc_name!r})\n"
        f"_result_ = True\n",
        30000,
        None,
    )


def test_failed_mutation_leaves_no_active_transaction(xmlrpc_proxy) -> None:
    """A tool call that raises must not leave an armed transaction behind."""
    doc_name = _make_scratch_document(xmlrpc_proxy)
    try:
        assert _active_transaction(xmlrpc_proxy) is None

        # Reproduces qwen call 34: a dict where FreeCAD wants a Placement.
        failed = xmlrpc_proxy.execute(
            f"import FreeCAD\n"
            f"doc = FreeCAD.getDocument({doc_name!r})\n"
            f"sketch = doc.getObject('ProbeSketch')\n"
            f"sketch.AttachmentOffset = {{'Pos': [8, 0, 0]}}\n"
            f"_result_ = True\n",
            30000,
            "Edit Object",
        )
        assert not failed["success"]
        assert "TypeError" in (failed.get("error_type") or "")

        assert _active_transaction(xmlrpc_proxy) is None

        # The next mutation must still work.
        recovered = xmlrpc_proxy.execute(
            f"import FreeCAD\n"
            f"doc = FreeCAD.getDocument({doc_name!r})\n"
            f"sketch = doc.getObject('ProbeSketch')\n"
            f"sketch.AttachmentOffset = FreeCAD.Placement(\n"
            f"    FreeCAD.Vector(8, 0, 0), FreeCAD.Rotation()\n"
            f")\n"
            f"doc.recompute()\n"
            f"_result_ = list(sketch.AttachmentOffset.Base)\n",
            30000,
            "Set Attachment Offset",
        )
        assert recovered["success"], recovered.get("error_message")
        assert recovered["result"] == [8.0, 0.0, 0.0]
    finally:
        _close_scratch_document(xmlrpc_proxy, doc_name)


def test_wedge_survives_document_reopen(xmlrpc_proxy) -> None:
    """Characterises the bug: an armed transaction is application-scoped.

    A document-level pending transaction cannot survive close and reopen, so
    if a leak did survive it, the stuck flag is App.getActiveTransaction().
    After the fix nothing leaks, so a fresh document mutates cleanly.
    """
    doc_name = _make_scratch_document(xmlrpc_proxy)
    try:
        xmlrpc_proxy.execute(
            f"import FreeCAD\n"
            f"doc = FreeCAD.getDocument({doc_name!r})\n"
            f"doc.getObject('ProbeSketch').AttachmentOffset = {{'bad': 1}}\n"
            f"_result_ = True\n",
            30000,
            "Edit Object",
        )
    finally:
        _close_scratch_document(xmlrpc_proxy, doc_name)

    assert _active_transaction(xmlrpc_proxy) is None

    second = _make_scratch_document(xmlrpc_proxy)
    _close_scratch_document(xmlrpc_proxy, second)


def test_armed_but_unbooked_transaction_closes_cleanly(xmlrpc_proxy) -> None:
    """A mutating call that raises before touching anything must close cleanly.

    Under lazy booking no document ever books the armed ID, so closing it is
    expected to be a harmless no-op. Verified rather than assumed.
    """
    assert _active_transaction(xmlrpc_proxy) is None

    result = xmlrpc_proxy.execute(
        "raise ValueError('before any mutation')\n",
        30000,
        "Never Books Anything",
    )
    assert not result["success"]

    assert _active_transaction(xmlrpc_proxy) is None
```

- [ ] **Step 2: Start FreeCAD headless with the bridge**

These tests run against a real FreeCAD in headless mode. The transaction API is
application-level (`App.setActiveTransaction` and friends), not GUI-level, so
headless exercises the real thing.

First check nothing already holds the bridge port:

Run: `uv run python -c "import xmlrpc.client as x; print(x.ServerProxy('http://127.0.0.1:9875', allow_none=True).ping())"`

If that succeeds, a bridge is already running — most likely the operator's GUI
FreeCAD. Ask them to stop it before continuing; the headless harness refuses to
start alongside it. Do not stop it yourself.

Once the port is free, start headless FreeCAD in a second terminal:

Run: `just freecad::run-headless`

Wait until the bridge answers the ping above.

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest tests/integration/test_transaction_boundary.py -v`

Expected: FAIL. The three-argument `proxy.execute(code, timeout_ms, transaction)` calls raise `xmlrpc.client.Fault` for wrong arity, because the addon's `_xmlrpc_execute` still takes two parameters. That failure is the starting point — it confirms the protocol change is genuinely required and not already present.

- [ ] **Step 4: Probe the current wedge on the two-argument protocol**

Step 3's tests all fail on arity, so they never observe the old behaviour. To
characterise the wedge itself, probe the *current* two-argument protocol
directly. This is throwaway diagnostic code — do not commit it.

Run:

```bash
uv run python - <<'EOF'
import xmlrpc.client, uuid
p = xmlrpc.client.ServerProxy("http://127.0.0.1:9875", allow_none=True)
name = f"wedge_probe_{uuid.uuid4().hex[:8]}"

def active():
    return p.execute(
        "import FreeCAD\n_a = FreeCAD.getActiveTransaction()\n"
        "_result_ = list(_a) if _a else None\n", 30000)["result"]

p.execute(
    f"import FreeCAD\ndoc = FreeCAD.newDocument({name!r})\n"
    f"doc.addObject('Sketcher::SketchObject', 'ProbeSketch')\n"
    f"doc.recompute()\n_result_ = True\n", 30000)
print("active before:", active())

bad = p.execute(
    f"import FreeCAD\ndoc = FreeCAD.getDocument({name!r})\n"
    f"doc.getObject('ProbeSketch').AttachmentOffset = {{'Pos': [8, 0, 0]}}\n"
    f"_result_ = True\n", 30000)
print("error_type:", bad.get("error_type"))
print("active after failure:", active())

again = p.execute(
    f"import FreeCAD\ndoc = FreeCAD.getDocument({name!r})\n"
    f"doc.addObject('App::VarSet', 'After')\n_result_ = True\n", 30000)
print("next mutation succeeded:", again.get("success"), again.get("error_message"))
EOF
```

Record the three printed values in `docs/development/transaction-boundary-design.md`
under a new `## Probe findings` heading: the `error_type` of the failed edit,
whether `getActiveTransaction()` was non-null afterwards, and whether the next
mutation succeeded. This is the evidence the spec marks as "not established".

If the probe shows no wedge — the transaction stays null and the next mutation
succeeds — say so in the ledger and in the findings section. The boundary work
still stands on its own (the three defects in the spec's Root Cause are
structural and independently verified), but the severity claim would need
revising.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_transaction_boundary.py docs/development/transaction-boundary-design.md
git commit -m "test: add failing live regression for transaction wedge"
```

---

### Task 2: Executor-owned transaction boundary

Addon and embedded executors gain the boundary. Every `execute_python` call site declares `transaction=None`, which is honest — no call is armed yet, and each keeps its existing in-code transaction. Behaviour is unchanged; the protocol is in place.

**Files:**

- Modify: `freecad/RobustMCPBridge/freecad_mcp_bridge/server.py` (`ExecutionRequest.__init__` 184, `_execute_via_queue` 822, `_execute_code_sync` 867, socket dispatch 1035, `_xmlrpc_execute` 1187)
- Modify: `src/freecad_mcp/bridge/base.py:305`, `src/freecad_mcp/bridge/socket.py:265`, `src/freecad_mcp/bridge/xmlrpc.py:253`, `src/freecad_mcp/bridge/embedded.py:93`
- Modify: all 111 `execute_python` call sites across `src/freecad_mcp/tools/`
- Test: `tests/unit/addon/`, `tests/integration/test_transaction_boundary.py`

**Interfaces:**

- Consumes: nothing from earlier tasks.
- Produces: `execute_python(code: str, timeout_ms: int = 30000, *, transaction: str | None) -> ExecutionResult` on all four bridges. Tasks 4, 5 and 6 pass a real name here instead of `None`.

- [ ] **Step 1: Add the boundary to the addon executor**

In `freecad/RobustMCPBridge/freecad_mcp_bridge/server.py`, replace `_execute_code_sync` (line 867) with:

```python
    def _execute_code_sync(
        self, code: str, transaction: str | None
    ) -> dict[str, Any]:
        """Execute Python code synchronously (call on main thread only).

        Args:
            code: Python code to execute.
            transaction: Name of the undo transaction to arm for this call, or
                None for a read-only call that must not open one.

        Returns:
            Execution result dictionary.
        """
        start = time.perf_counter()
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        exec_globals: dict[str, Any] = {
            "__builtins__": __builtins__,
        }

        if FREECAD_AVAILABLE:
            exec_globals["FreeCAD"] = FreeCAD
            exec_globals["App"] = FreeCAD
            exec_globals["FreeCADGui"] = FreeCADGui
            exec_globals["Gui"] = FreeCADGui

        armed = False
        if transaction is not None and FREECAD_AVAILABLE:
            active = FreeCAD.getActiveTransaction()
            if isinstance(active, tuple | list) and len(active) > 1 and active[1]:
                return {
                    "success": False,
                    "result": None,
                    "stdout": "",
                    "stderr": "",
                    "execution_time_ms": 0.0,
                    "error_type": "TransactionConflict",
                    "error_message": (
                        "TRANSACTION_CONFLICT: application transaction "
                        f"{active[0]!r} is already active; refusing to mutate"
                    ),
                    "error_traceback": None,
                }
            # Undo must be ON before arming. A document's UndoMode defaults to 0,
            # and with undo disabled closeActiveTransaction(abort=True) silently
            # keeps the mutation instead of rolling it back. Verified live.
            for open_document in FreeCAD.listDocuments().values():
                if open_document.UndoMode == 0:
                    open_document.UndoMode = 1
            FreeCAD.setActiveTransaction(transaction, True)
            armed = True

        succeeded = False
        try:
            try:
                with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                    compiled = compile(code, "<mcp>", "exec")
                    exec(compiled, exec_globals)  # noqa: S102

                succeeded = True
                elapsed = (time.perf_counter() - start) * 1000
                return {
                    "success": True,
                    "result": exec_globals.get("_result_"),
                    "stdout": stdout_capture.getvalue(),
                    "stderr": stderr_capture.getvalue(),
                    "execution_time_ms": elapsed,
                }

            except Exception as e:
                elapsed = (time.perf_counter() - start) * 1000
                return {
                    "success": False,
                    "result": None,
                    "stdout": stdout_capture.getvalue(),
                    "stderr": stderr_capture.getvalue(),
                    "execution_time_ms": elapsed,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "error_traceback": traceback.format_exc(),
                }
        finally:
            if armed:
                FreeCAD.closeActiveTransaction(not succeeded)
```

- [ ] **Step 2: Thread the transaction name through the addon request path**

Four edits in the same file.

`ExecutionRequest.__init__` (line 184) — add the parameter and store it:

```python
    def __init__(
        self,
        code: str,
        timeout_ms: int = 30000,
        request_id: str | None = None,
        transaction: str | None = None,
    ) -> None:
        """Initialize execution request.

        Args:
            code: Python code to execute.
            timeout_ms: Execution timeout in milliseconds.
            request_id: Optional request ID for tracking.
            transaction: Undo transaction name to arm, or None for read-only.
        """
        self.code = code
        self.timeout_ms = timeout_ms
        self.request_id = request_id
        self.transaction = transaction
```

`_execute_via_queue` (line 822) — accept and forward:

```python
    def _execute_via_queue(
        self,
        code: str,
        timeout_ms: int,
        transaction: str | None,
    ) -> dict[str, Any]:
```

and change the construction on line 836 to:

```python
        request = ExecutionRequest(code, timeout_ms, transaction=transaction)
```

Queue drain (line 805) — pass it to the executor:

```python
                result = self._execute_code_sync(request.code, request.transaction)
```

`_xmlrpc_execute` (line 1187) — required third parameter:

```python
    def _xmlrpc_execute(
        self,
        code: str,
        timeout_ms: int,
        transaction: str | None,
    ) -> dict[str, Any]:
        """XML-RPC execute handler.

        Args:
            code: Python code to execute.
            timeout_ms: Maximum time to wait for execution in milliseconds.
            transaction: Undo transaction name to arm, or None for read-only.

        Returns:
            Execution result dictionary.
        """
        return _xmlrpc_safe_value(
            self._execute_via_queue(code, timeout_ms, transaction)
        )
```

- [ ] **Step 3: Require the field in the socket dispatch**

Replace the `execute` branch at line 1035:

```python
        if method == "execute":
            if "transaction" not in params:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32602,
                        "message": "Invalid params",
                        "data": "Missing required parameter: transaction",
                    },
                }
            code = params.get("code", "")
            timeout_ms = params.get("timeout_ms", 30000)
            transaction = params["transaction"]

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._execute_via_queue(code, timeout_ms, transaction),
            )

            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result,
            }
```

- [ ] **Step 4: Add the same boundary to the embedded executor**

In `src/freecad_mcp/bridge/embedded.py`, change `_execute_code` to take the name and wrap the same way:

```python
    def _execute_code(self, code: str, transaction: str | None) -> ExecutionResult:
        """Execute code synchronously (runs in thread pool)."""
        start = time.perf_counter()
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        exec_globals: dict[str, Any] = {
            "FreeCAD": self._fc_module,
            "App": self._fc_module,
            "__builtins__": __builtins__,
        }

        try:
            import FreeCADGui

            exec_globals["FreeCADGui"] = FreeCADGui
            exec_globals["Gui"] = FreeCADGui
        except ImportError:
            pass

        armed = False
        if transaction is not None:
            active = self._fc_module.getActiveTransaction()
            if isinstance(active, tuple | list) and len(active) > 1 and active[1]:
                return ExecutionResult(
                    success=False,
                    result=None,
                    stdout="",
                    stderr="",
                    execution_time_ms=0.0,
                    error_type="TransactionConflict",
                    error_traceback=(
                        "TRANSACTION_CONFLICT: application transaction "
                        f"{active[0]!r} is already active; refusing to mutate"
                    ),
                )
            # See the addon boundary: undo must be ON before arming, or an
            # abort silently keeps the mutation.
            for open_document in self._fc_module.listDocuments().values():
                if open_document.UndoMode == 0:
                    open_document.UndoMode = 1
            self._fc_module.setActiveTransaction(transaction, True)
            armed = True

        succeeded = False
        try:
            try:
                with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                    compiled = compile(code, "<mcp>", "exec")
                    exec(compiled, exec_globals)  # noqa: S102

                succeeded = True
                elapsed = (time.perf_counter() - start) * 1000

                return ExecutionResult(
                    success=True,
                    result=exec_globals.get("_result_"),
                    stdout=stdout_capture.getvalue(),
                    stderr=stderr_capture.getvalue(),
                    execution_time_ms=elapsed,
                )

            except Exception as e:
                elapsed = (time.perf_counter() - start) * 1000

                return ExecutionResult(
                    success=False,
                    result=None,
                    stdout=stdout_capture.getvalue(),
                    stderr=stderr_capture.getvalue(),
                    execution_time_ms=elapsed,
                    error_type=type(e).__name__,
                    error_traceback=traceback.format_exc(),
                )
        finally:
            if armed:
                self._fc_module.closeActiveTransaction(not succeeded)
```

The two `ExecutionResult` returns are the file's existing ones — keep whatever fields the current code passes, and change only the two structural things: `succeeded = True` after the `exec`, and the wrapping `try/finally`.

Update the caller inside `execute_python` (line ~123) to `lambda: self._execute_code(code, transaction)`.

- [ ] **Step 5: Add the required parameter to all four bridges**

`src/freecad_mcp/bridge/base.py:305`:

```python
    @abstractmethod
    async def execute_python(
        self,
        code: str,
        timeout_ms: int = 30000,
        *,
        transaction: str | None,
    ) -> ExecutionResult:
        """Execute Python code in FreeCAD context.

        The code runs with access to FreeCAD modules (FreeCAD, App, Gui).
        To return a value, assign it to the `_result_` variable.

        Args:
            code: Python code to execute.
            timeout_ms: Maximum execution time in milliseconds.
            transaction: Undo transaction name to arm around this call, or None
                for a read-only call. Keyword-only and required, so every call
                site declares whether it mutates.

        Returns:
            ExecutionResult with success status, output, and any errors.
        """
```

Mirror that signature in `socket.py:265`, `xmlrpc.py:253`, and `embedded.py:93`.

In `socket.py`, put it on the wire:

```python
                self._send_request(
                    "execute",
                    {"code": code, "transaction": transaction},
                ),
```

- [ ] **Step 6: Send the field over XML-RPC and drop the arity negotiation**

The `_supports_server_timeout` probe calls `proxy.execute("_result_ = None", 1000)`, which now faults on arity. Under the no-compat decision the negotiation is dead weight, so remove it rather than teach it a third argument.

In `src/freecad_mcp/bridge/xmlrpc.py`, delete the `if self._supports_server_timeout is None:` block (lines 294-302) and replace the dispatch at lines 309-311 with:

```python
                    request_started.set()
                    return proxy.execute(code, timeout_ms, transaction)
```

Then delete the now-unused `_LEGACY_EXECUTE_ARITY_FAULT` constant (line 45) and the `self._supports_server_timeout` assignments (lines 82 and 153).

`allow_none=True` is already set on both the client proxy (`xmlrpc.py:101`) and the addon server (`server.py:1135`), so `None` crosses the wire unchanged.

- [ ] **Step 7: Declare `transaction=None` at all 108 call sites**

Every `execute_python(...)` call in `src/freecad_mcp/tools/` gains `transaction=None`. A naive grep reports 111 matches; three are not calls (the `execute_python` tool definition at `execution.py:27` and two docstring examples at `execution.py:56` and `:64`). No behaviour changes: each mutating tool still opens its own in-code transaction, which Tasks 4 to 5 remove one module at a time.

Find them with:

```bash
grep -rn 'execute_python(' src/freecad_mcp/tools/
```

Counts per file, as a completeness check: `partdesign.py` 37, `objects.py` 24, `view.py` 12, `spreadsheet.py` 10, `export.py` 7, `draft.py` 6, `variables.py` 4, `validation.py` 4, `execution.py` 1 (plus 3 non-call matches), `macros.py` 2, `documents.py` 1.

- [ ] **Step 8: Verify with the type checker**

Run: `uv run pre-commit run mypy --all-files`
Expected: PASS. Because `transaction` is keyword-only with no default, mypy flags any call site that was missed. A clean run is the completeness proof — do not proceed until it passes.

Use this command, not `just quality::typecheck`: that recipe checks only `src/` and will not see call sites under `tests/`, which is exactly how 7 errors were missed the first time.

- [ ] **Step 9: Add live boundary tests for the four executor cases**

These go in the same live file as Task 1, not in a mocked unit test. The
"foreign transaction" case in particular is only real evidence when a genuine
`App.setActiveTransaction` is outstanding.

Append to `tests/integration/test_transaction_boundary.py`:

```python
def test_successful_mutation_commits(xmlrpc_proxy) -> None:
    """A mutating call commits and leaves an undoable step behind."""
    doc_name = _make_scratch_document(xmlrpc_proxy)
    try:
        result = xmlrpc_proxy.execute(
            f"import FreeCAD\n"
            f"doc = FreeCAD.getDocument({doc_name!r})\n"
            f"doc.addObject('App::VarSet', 'Vars')\n"
            f"doc.recompute()\n"
            f"_result_ = doc.UndoCount\n",
            30000,
            "Add Variable Set",
        )
        assert result["success"], result.get("error_message")
        assert _active_transaction(xmlrpc_proxy) is None

        names = xmlrpc_proxy.execute(
            f"import FreeCAD\n"
            f"_result_ = FreeCAD.getDocument({doc_name!r}).UndoNames\n",
            30000,
            None,
        )
        assert "Add Variable Set" in names["result"]
    finally:
        _close_scratch_document(xmlrpc_proxy, doc_name)


def test_failed_mutation_rolls_back(xmlrpc_proxy) -> None:
    """An exception after a real mutation must roll that mutation back."""
    doc_name = _make_scratch_document(xmlrpc_proxy)
    try:
        result = xmlrpc_proxy.execute(
            f"import FreeCAD\n"
            f"doc = FreeCAD.getDocument({doc_name!r})\n"
            f"doc.addObject('App::VarSet', 'ShouldNotSurvive')\n"
            f"raise ValueError('fail after mutating')\n",
            30000,
            "Add Variable Set",
        )
        assert not result["success"]
        assert _active_transaction(xmlrpc_proxy) is None

        objects = xmlrpc_proxy.execute(
            f"import FreeCAD\n"
            f"_result_ = [o.Name for o in FreeCAD.getDocument({doc_name!r}).Objects]\n",
            30000,
            None,
        )
        assert "ShouldNotSurvive" not in objects["result"]
    finally:
        _close_scratch_document(xmlrpc_proxy, doc_name)


def test_readonly_call_opens_no_transaction(xmlrpc_proxy) -> None:
    """transaction=None must not create an undo step."""
    doc_name = _make_scratch_document(xmlrpc_proxy)
    try:
        before = xmlrpc_proxy.execute(
            f"import FreeCAD\n"
            f"_result_ = FreeCAD.getDocument({doc_name!r}).UndoCount\n",
            30000,
            None,
        )["result"]

        xmlrpc_proxy.execute(
            f"import FreeCAD\n"
            f"_result_ = len(FreeCAD.getDocument({doc_name!r}).Objects)\n",
            30000,
            None,
        )

        after = xmlrpc_proxy.execute(
            f"import FreeCAD\n"
            f"_result_ = FreeCAD.getDocument({doc_name!r}).UndoCount\n",
            30000,
            None,
        )["result"]

        assert after == before
        assert _active_transaction(xmlrpc_proxy) is None
    finally:
        _close_scratch_document(xmlrpc_proxy, doc_name)


def test_foreign_transaction_is_refused_and_left_intact(xmlrpc_proxy) -> None:
    """We refuse to mutate under a transaction we did not arm, and never close it."""
    doc_name = _make_scratch_document(xmlrpc_proxy)
    try:
        # Stand in for the operator opening a transaction in the GUI.
        xmlrpc_proxy.execute(
            "import FreeCAD\n"
            "FreeCAD.setActiveTransaction('Operator Edit', True)\n"
            "_result_ = True\n",
            30000,
            None,
        )
        assert _active_transaction(xmlrpc_proxy)[0] == "Operator Edit"

        refused = xmlrpc_proxy.execute(
            f"import FreeCAD\n"
            f"FreeCAD.getDocument({doc_name!r}).addObject('App::VarSet', 'Nope')\n"
            f"_result_ = True\n",
            30000,
            "Add Variable Set",
        )
        assert not refused["success"]
        assert "TRANSACTION_CONFLICT" in (refused.get("error_message") or "")

        # The operator's transaction must still be exactly where it was.
        assert _active_transaction(xmlrpc_proxy)[0] == "Operator Edit"
    finally:
        xmlrpc_proxy.execute(
            "import FreeCAD\n"
            "if FreeCAD.getActiveTransaction():\n"
            "    FreeCAD.closeActiveTransaction(True)\n"
            "_result_ = True\n",
            30000,
            None,
        )
        _close_scratch_document(xmlrpc_proxy, doc_name)
```

Note the asymmetry this proves: the refused call does **not** clear the foreign
transaction, but a leak of our own can no longer happen in the first place.

The embedded bridge is the one place a mocked test stays. Project policy
(`CLAUDE.md`) is that embedded mode is unit-tested with mocks only, because
running FreeCAD in-process is Linux-only and crashes CI runners elsewhere. Add a
single mocked test there to pin its parallel implementation, and treat the live
tests above as the real evidence:

```python
def test_embedded_boundary_aborts_on_failure() -> None:
    """Pins the embedded bridge's copy of the executor boundary."""

    class _FakeFreeCAD:
        def __init__(self) -> None:
            self.closed: list[bool] = []

        def getActiveTransaction(self) -> tuple[str, int] | None:
            return None

        def setActiveTransaction(self, name: str, persist: bool = False) -> int:
            assert persist is True
            return 1

        def closeActiveTransaction(self, abort: bool = False) -> None:
            self.closed.append(abort)

    fake = _FakeFreeCAD()
    bridge = EmbeddedBridge()
    bridge._fc_module = fake
    bridge._connected = True

    assert not bridge._execute_code("raise ValueError('x')", "Pad Sketch").success
    assert fake.closed == [True]
```

- [ ] **Step 10: Run unit tests**

Run: `just testing::unit`
Expected: PASS, including the four new tests. Fix any addon or bridge test that constructs `ExecutionRequest` or calls `execute_python` positionally.

- [ ] **Step 11: Reinstall the addon into FreeCAD**

The addon changed, so the deployed copy must be refreshed before any live test
exercises the new code.

Run: `just install::mcp-bridge-workbench`

Then restart the headless FreeCAD from Task 1 Step 2 so it loads the new addon:
stop it, and run `just freecad::run-headless` again.

- [ ] **Step 12: Run the live regressions**

Run: `uv run pytest tests/integration/test_transaction_boundary.py -v`
Expected: all seven tests PASS — the three from Task 1 and the four from Step 9.
The wedge is gone.

Alternatively, to run the whole integration suite in one self-contained pass that
installs the addon, starts headless FreeCAD, and tears it down afterwards:

Run: `just testing::integration-headless-release`

That recipe refuses to start if a bridge already holds port 9875, so stop the
manually started headless instance first.

- [ ] **Step 13: Commit**

```bash
git add freecad/RobustMCPBridge/freecad_mcp_bridge/server.py \
        src/freecad_mcp/bridge/base.py \
        src/freecad_mcp/bridge/socket.py \
        src/freecad_mcp/bridge/xmlrpc.py \
        src/freecad_mcp/bridge/embedded.py \
        src/freecad_mcp/tools/ \
        tests/
git commit -m "feat: move the FreeCAD transaction boundary into the executor"
```

---

### Task 3: Remove the dead full-profile modules

Three modules contain **zero** parametric-profile tools, so every tool in them is
dead code for this project: `spreadsheet.py` (10 tools), `draft.py` (6), and
`macros.py` (6). They are registered only by `register_all_tools`, never by
`register_parametric_tools`.

The strategy the user chose: delete whole dead modules now, and delete the
remaining scattered full-profile tools **during** the migration tasks rather than
upgrading code that is about to die. Tasks 5, 6 and 7 each carry that instruction
for the module they touch.

Removing these three now shrinks the remaining migration and deletes 2,209 lines
of source plus 2,708 lines of tests.

The in-flight work on `spreadsheet_bind_property` was preserved as commit
`b9eea05` before this deletion, so it is recoverable from history if the decision
is ever reversed.

**Files:**

- Delete: `src/freecad_mcp/tools/spreadsheet.py`, `src/freecad_mcp/tools/draft.py`, `src/freecad_mcp/tools/macros.py`
- Delete: `tests/unit/test_tools_spreadsheet.py`, `tests/unit/test_tools_draft.py`, `tests/unit/test_tools_macros.py`
- Delete: `tests/integration/test_spreadsheet_draft_workflows.py`
- Modify: `src/freecad_mcp/tools/__init__.py`, `src/freecad_mcp/resources/freecad.py`, `tests/unit/test_parametric_profile.py`
- Modify: `CLAUDE.md`, `docs/guide/tools.md`, `docs/MCP_TOOLS_REFERENCE.md`

**Interfaces:**

- Consumes: nothing from Task 2 beyond a clean tree.
- Produces: a `tools/` package with no spreadsheet module. Task 6 no longer touches `spreadsheet.py`.

- [ ] **Step 1: Delete the module and its unit tests**

```bash
git rm src/freecad_mcp/tools/spreadsheet.py src/freecad_mcp/tools/draft.py \
       src/freecad_mcp/tools/macros.py \
       tests/unit/test_tools_spreadsheet.py tests/unit/test_tools_draft.py \
       tests/unit/test_tools_macros.py
```

- [ ] **Step 2: Unregister it**

In `src/freecad_mcp/tools/__init__.py`, for **each** of `spreadsheet`, `draft`
and `macros`, remove four things: its line from the module docstring, its
`from freecad_mcp.tools.<mod> import register_<mod>_tools` import, its
`"register_<mod>_tools",` entry in `__all__`, and its
`register_<mod>_tools(mcp, get_bridge_func)` call in `register_all_tools`.

Run: `grep -n "spreadsheet\|draft\|macro" src/freecad_mcp/tools/__init__.py`
Expected: no output.

- [ ] **Step 3: Remove the capabilities catalog entry**

`src/freecad_mcp/resources/freecad.py` has 26 spreadsheet references, forming one
`"spreadsheet": {...}` category block starting at line 1087. Remove that whole
block and nothing else.

Run: `grep -ci spreadsheet src/freecad_mcp/resources/freecad.py`
Expected: `0`.

- [ ] **Step 4: Delete the spreadsheet/draft integration tests**

```bash
git rm tests/integration/test_spreadsheet_draft_workflows.py
```

An earlier version of this plan said to split this file and keep its four
`TestDraftShapeStringWorkflow` tests. That is superseded: `draft.py` is being
deleted too, so the Draft tests have nothing left to cover. All five of them skip
in this environment anyway ("No suitable font file found in test environment").

- [ ] **Step 5: Update the profile test**

`tests/unit/test_parametric_profile.py:97-98` asserts `spreadsheet_create` and
`spreadsheet_set_cell` are absent from the parametric profile. Those assertions
now pass trivially because the tools do not exist at all. Remove both lines; the
surrounding test still covers the tools that do exist.

- [ ] **Step 6: Update the documentation**

- `CLAUDE.md`: remove the "Spreadsheet Tools (Full Profile)" table and any
  spreadsheet row in the tool-category summary.
- `docs/guide/tools.md`: remove the spreadsheet section and its summary-table row,
  and correct the tool count in the header.
- `docs/MCP_TOOLS_REFERENCE.md`: remove the spreadsheet signatures.

Leave `docs/COMPARISON.md`, `docs/development/declarative-parametric-cad-landscape.md`,
and `docs/development/parametric-cad-agent-research.md` alone — those discuss
spreadsheets as a CAD concept, not as tools this server provides.

- [ ] **Step 7: Verify nothing references the removed module**

Run: `grep -rn "register_spreadsheet_tools\|register_draft_tools\|register_macro_tools\|tools\.spreadsheet\|tools\.draft\|tools\.macros" src/ tests/`
Expected: no output.

Run: `grep -rni "spreadsheet_\|draft_shapestring\|run_macro\|list_macros\|create_macro" src/ tests/ docs/guide docs/MCP_TOOLS_REFERENCE.md CLAUDE.md`
Expected: no output.

Incidental references to the FreeCAD *workbench* named Spreadsheet are fine and
must stay: `bridge/base.py:57` (`SPREADSHEET = "Spreadsheet"` enum value),
`bridge/embedded.py:1091`, `bridge/xmlrpc.py:773`, `tools/view.py:269`.

- [ ] **Step 8: Run the quality gate**

Run: `just testing::unit && just quality::lint && just quality::typecheck`
Expected: all PASS. Note `uv run pytest` resolves to a system PyPy 2.7 on this
machine; use `uv run python -m pytest` for direct pytest invocations.

Run: `uv run --frozen --extra dev python -m mkdocs build --strict`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add -u src/freecad_mcp/tools/ src/freecad_mcp/resources/freecad.py \
        tests/unit/test_parametric_profile.py tests/integration/ \
        CLAUDE.md docs/guide/tools.md docs/MCP_TOOLS_REFERENCE.md
git commit -m "refactor: remove the legacy Spreadsheet tools"
```

---

### Task 4: Migrate `variables.py` to the executor boundary

The smallest mutating module, and the one that produced most of qwen's errors. Migrating it first proves the pattern on a module with live regression coverage already in `tests/integration/test_stage_c_regressions.py`.

**Files:**

- Modify: `src/freecad_mcp/tools/variables.py` (`open_owned_transaction` at 197, 497, 656)
- Test: `tests/integration/test_stage_c_regressions.py` (existing, must keep passing)

**Interfaces:**

- Consumes: `execute_python(..., transaction=...)` from Task 2.
- Produces: the migration pattern Tasks 5 and 5 repeat.

- [ ] **Step 1: Replace the in-code transaction with a declared one**

For each of the three sites, delete the transaction scaffolding from the generated code and move the name to the call. `define_variables` (line 197) is the worked example; the transaction name becomes the `transaction=` argument.

The generated code in `define_variables` currently reads (line 197 onward, abridged
in the middle — keep every line of the real body):

```python
open_owned_transaction(doc, "Define Variables")
try:
    if var_set is None:
        var_set = doc.addObject("App::VarSet", variable_set_name)
    if {label!r} is not None:
        var_set.Label = {label!r}

    # Create every property first so expressions can reference any batch member.
    for definition in definitions:
        ...

    doc.commitTransaction()
except Exception:
    abort_owned_transaction(doc)
    doc.recompute()
    raise
```

Remove the first line, the `try:`, the `doc.commitTransaction()`, and the whole
`except Exception:` block, then dedent the body by one level:

```python
if var_set is None:
    var_set = doc.addObject("App::VarSet", variable_set_name)
if {label!r} is not None:
    var_set.Label = {label!r}

# Create every property first so expressions can reference any batch member.
for definition in definitions:
    ...
```

Every `raise` inside that body stays exactly as it is. The executor aborts on any
exception, so the deliberate rejections still roll back.

The `doc.recompute()` in the old `except` branch settled the document after a
manual abort. The executor's abort restores the pre-transaction state itself, so
it is no longer needed.

Then pass the name at the call site:

```python
result = await bridge.execute_python(code, transaction="Define Variables")
```

Apply the same edit at line 497 (`"Bind Expressions"`) and line 656 (`"Set Expression"`).

- [ ] **Step 2: Run unit tests**

Run: `just testing::unit -k variables`
Expected: PASS. Generated-code tests that assert on `open_owned_transaction` appearing in the emitted source must be updated to assert its absence.

- [ ] **Step 3: Run the live regressions**

Run: `uv run pytest tests/integration/test_stage_c_regressions.py -v`
Expected: PASS, including `test_define_variables_reports_each_bad_expression_and_rolls_back`. That test is the proof the rollback contract still holds now that the executor owns the abort.

- [ ] **Step 4: Commit**

```bash
git add src/freecad_mcp/tools/variables.py tests/
git commit -m "refactor: declare variable tool transactions at the executor"
```

---

### Task 5: Migrate `partdesign.py` to the executor boundary

The largest module: 18 `open_owned_transaction` sites and 18 raw `openTransaction` sites.


### Delete dead PartDesign tools instead of migrating them

Per the user's decision, do not add `transaction=` to a tool that is not in the
parametric profile — delete the tool instead. Upgrading dead code is wasted work.

For each module below, KEEP only the listed tools and delete every other
`@mcp.tool()` function, along with its unit tests and any `PARAMETRIC_TOOL_NAMES`-
irrelevant helpers it solely used. The keep-lists are exactly
`PARAMETRIC_TOOL_NAMES` intersected with each module, generated from the source.

**`partdesign.py`** — keep 25 of 50:

```text
add_sketch_arc, add_sketch_circle, add_sketch_constraint, add_sketch_line, add_sketch_point, add_sketch_rectangle, chamfer_edges, create_constrained_sketch, create_datum_plane, create_hole, create_partdesign_body, create_sketch, delete_sketch_constraint, delete_sketch_geometry, fillet_edges, get_sketch_info, groove_sketch, linear_pattern, loft_sketches, mirrored_feature, pad_sketch, pocket_sketch, polar_pattern, revolution_sketch, toggle_construction
```

After deleting, confirm the module's remaining tools are exactly its keep-list:

```bash
python3 - <<'EOF'
import pathlib, re
init = pathlib.Path("src/freecad_mcp/tools/__init__.py").read_text()
names = set(re.findall(r'"([a-z_0-9]+)"',
            init.split("PARAMETRIC_TOOL_NAMES = frozenset(")[1].split("\n)")[0]))
for f in sorted(pathlib.Path("src/freecad_mcp/tools").glob("*.py")):
    tools = [x for x in re.findall(r"async def (\w+)\(", f.read_text())
             if not x.startswith("_")]
    extra = [x for x in tools if x not in names]
    if extra:
        print(f"{f.name}: still has non-parametric tools: {extra}")
EOF
```

Expected once all migration tasks are done: no output.

Removing a tool also means removing its entry from
`src/freecad_mcp/resources/freecad.py` (the capabilities catalog) and its row in
`docs/guide/tools.md` and `docs/MCP_TOOLS_REFERENCE.md`.

**Files:**

- Modify: `src/freecad_mcp/tools/partdesign.py`
- Test: `tests/unit/test_tools_partdesign.py`, `tests/integration/test_stage_c_regressions.py`

**Interfaces:**

- Consumes: the pattern from Task 3.
- Produces: no new interfaces.

- [ ] **Step 1: List every transaction site and its name**

Run:

```bash
grep -n 'open_owned_transaction\|openTransaction' src/freecad_mcp/tools/partdesign.py
```

Each match carries the exact transaction name to pass as `transaction=`. Work through them in file order so none is missed.

- [ ] **Step 2: Migrate each site**

Apply the Task 4 pattern: delete the scaffolding from the generated code, dedent the body, and pass the name at the `execute_python` call. Transactional rollbacks that currently raise inside the `try` keep raising — the executor aborts on any exception, so the volume-reduction and one-solid rejections keep working with less code.

- [ ] **Step 3: Verify no transaction calls remain in this module**

Run: `grep -n 'open_owned_transaction\|abort_owned_transaction\|openTransaction\|commitTransaction' src/freecad_mcp/tools/partdesign.py`
Expected: no output.

- [ ] **Step 4: Run unit tests**

Run: `just testing::unit -k partdesign`
Expected: PASS.

- [ ] **Step 5: Run the live regressions**

Run: `uv run pytest tests/integration/test_stage_c_regressions.py -v`
Expected: PASS, including `test_additive_pad_rejects_no_material_and_rolls_back` and `test_pattern_becomes_body_tip_in_live_freecad`.

- [ ] **Step 6: Commit**

```bash
git add src/freecad_mcp/tools/partdesign.py tests/
git commit -m "refactor: declare PartDesign tool transactions at the executor"
```

---

### Task 6: Migrate the remaining modules

`objects.py` (20 raw sites), `draft.py` (5), `bridge/xmlrpc.py` (3), `validation.py` (1), `view.py` (1). Task 3 deleted `spreadsheet.py`, removing 6 sites that this task originally carried.

`objects.py` includes `edit_object`, `create_object`, and `delete_object` — the three that never had a transaction. They get one here purely by declaring a name; no other change.


### Delete dead tools in these modules instead of migrating them

Also delete the now-orphaned bridge-layer macro methods, which Task 3 left in
place to keep its commit bounded: `get_macros`, `run_macro`, `create_macro`,
`read_macro` and `delete_macro` in `bridge/base.py`, `bridge/socket.py`,
`bridge/xmlrpc.py` and `bridge/embedded.py`, plus the `MacroInfo` dataclass in
`bridge/base.py` if nothing else uses it. Nothing calls any of them since the
`freecad://macros` resource was removed. Confirm with:

```bash
grep -rn "get_macros\|run_macro\|create_macro\|read_macro\|delete_macro\|MacroInfo" src/ tests/
```


Per the user's decision, do not add `transaction=` to a tool that is not in the
parametric profile — delete the tool instead. Upgrading dead code is wasted work.

For each module below, KEEP only the listed tools and delete every other
`@mcp.tool()` function, along with its unit tests and any `PARAMETRIC_TOOL_NAMES`-
irrelevant helpers it solely used. The keep-lists are exactly
`PARAMETRIC_TOOL_NAMES` intersected with each module, generated from the source.

**`objects.py`** — keep 4 of 41:

```text
edit_object, inspect_object, list_objects, query_objects
```

**`view.py`** — keep 6 of 18:

```text
fit_all, get_screenshot, redo, set_object_visibility, set_view_angle, undo
```

**`validation.py`** — keep 2 of 4:

```text
validate_document, validate_object
```

**`export.py`** — keep 3 of 7:

```text
export_step, export_stl, import_step
```

**`execution.py`** — keep 3 of 5:

```text
get_connection_status, get_console_output, get_freecad_version
```

After deleting, confirm the module's remaining tools are exactly its keep-list:

```bash
python3 - <<'EOF'
import pathlib, re
init = pathlib.Path("src/freecad_mcp/tools/__init__.py").read_text()
names = set(re.findall(r'"([a-z_0-9]+)"',
            init.split("PARAMETRIC_TOOL_NAMES = frozenset(")[1].split("\n)")[0]))
for f in sorted(pathlib.Path("src/freecad_mcp/tools").glob("*.py")):
    tools = [x for x in re.findall(r"async def (\w+)\(", f.read_text())
             if not x.startswith("_")]
    extra = [x for x in tools if x not in names]
    if extra:
        print(f"{f.name}: still has non-parametric tools: {extra}")
EOF
```

Expected once all migration tasks are done: no output.

Removing a tool also means removing its entry from
`src/freecad_mcp/resources/freecad.py` (the capabilities catalog) and its row in
`docs/guide/tools.md` and `docs/MCP_TOOLS_REFERENCE.md`.

**Files:**

- Modify: `src/freecad_mcp/tools/objects.py`, `src/freecad_mcp/tools/draft.py`, `src/freecad_mcp/tools/validation.py`, `src/freecad_mcp/tools/view.py`, `src/freecad_mcp/bridge/xmlrpc.py`
- Test: `tests/unit/test_tools_objects.py`, `tests/unit/test_tools_draft.py`, `tests/unit/test_tools_validation.py`, `tests/unit/test_tools_view.py`

**Interfaces:**

- Consumes: the pattern from Task 3.
- Produces: no new interfaces.

- [ ] **Step 1: Migrate the tool modules**

Apply the Task 4 pattern to `objects.py`, `draft.py`, `validation.py`, and `view.py`.

The three bridge-layer mutators need only a declared name, since they have no scaffolding to remove:

```python
result = await self.execute_python(code, transaction="Edit Object")
```

Use `"Create Object"`, `"Edit Object"`, and `"Delete Object"`.

- [ ] **Step 2: Migrate the xmlrpc bridge mutators**

`src/freecad_mcp/bridge/xmlrpc.py` lines 621, 670, and 716 open raw transactions inside generated code, and line 670 never aborts on failure. Delete all three `doc.openTransaction(...)` lines and the matching commit lines, and declare the name at the `execute_python` call instead.

- [ ] **Step 3: Keep the non-transactional set non-transactional**

Confirm these still pass `transaction=None`: `undo` and `redo` (`view.py:597`, `view.py:630`), `undo_if_invalid` (`validation.py:417`), `open_document`, `close_document`, `save_document` in `documents.py`, and every call in `export.py`. Running undo or redo inside an open transaction invites corruption; exports write external files and never modify the document.

This matches the "Tools NOT Requiring Transactions" list in `CLAUDE.md`: read-only operations, exports, view operations, and the undo/redo tools.

Run: `grep -n -A6 'async def undo\|async def redo\|async def undo_if_invalid' src/freecad_mcp/tools/view.py src/freecad_mcp/tools/validation.py | grep transaction`
Expected: every match reads `transaction=None`.

Run: `grep -c 'transaction=None' src/freecad_mcp/tools/export.py`
Expected: `7`, one per `execute_python` call in that module.

- [ ] **Step 4: Run unit tests**

Run: `just testing::unit`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/freecad_mcp/tools/objects.py \
        src/freecad_mcp/tools/draft.py \
        src/freecad_mcp/tools/validation.py \
        src/freecad_mcp/tools/view.py \
        src/freecad_mcp/bridge/xmlrpc.py \
        tests/
git commit -m "refactor: declare remaining tool transactions at the executor"
```

---

### Task 7: Delete the old machinery and verify

Nothing calls the owned-transaction helpers now. Removing them is what makes the wedge unreachable rather than merely unused.

**Files:**

- Modify: `src/freecad_mcp/tools/utils.py` (`WORKFLOW_HELPERS` 9-100, `wrap_with_transaction` 101-145)
- Modify: `tests/unit/test_tools_utils.py`

**Interfaces:**

- Consumes: Tasks 4, 5 and 6 removed every caller.
- Produces: a `WORKFLOW_HELPERS` containing only revision helpers.

- [ ] **Step 0: Collapse the tool-profile mechanism if nothing full-only remains**

By this point Tasks 3, 5 and 6 should have deleted every non-parametric tool.
Verify:

```bash
python3 - <<'EOF'
import pathlib, re
init = pathlib.Path("src/freecad_mcp/tools/__init__.py").read_text()
names = set(re.findall(r'"([a-z_0-9]+)"',
            init.split("PARAMETRIC_TOOL_NAMES = frozenset(")[1].split("\n)")[0]))
for f in sorted(pathlib.Path("src/freecad_mcp/tools").glob("*.py")):
    tools = [x for x in re.findall(r"async def (\w+)\(", f.read_text())
             if not x.startswith("_")]
    extra = [x for x in tools if x not in names]
    if extra:
        print(f"{f.name}: {extra}")
EOF
```

If that prints nothing, `register_all_tools` and `register_parametric_tools` now
register the same set and the `FREECAD_TOOL_PROFILE` switch is dead weight.
Report that to the controller with the evidence and **stop** — do not remove the
profile mechanism on your own initiative. It is a public interface of a published
package, and whether to drop it is the user's call, not this plan's.

If it prints anything, report which tools remain and why you could not delete
them, then continue with Step 1.

- [ ] **Step 1: Confirm there are no remaining callers**

Run:

```bash
grep -rn 'open_owned_transaction\|abort_owned_transaction\|has_open_transaction\|active_application_transaction\|_owned_transaction_id\|wrap_with_transaction\|openTransaction' src/ freecad/
```

Expected: no output. If anything remains, migrate it before continuing.

- [ ] **Step 2: Delete the helpers**

From `WORKFLOW_HELPERS` in `src/freecad_mcp/tools/utils.py`, delete `_owned_transaction_id`, `active_application_transaction`, `has_open_transaction`, `open_owned_transaction`, and `abort_owned_transaction`. Delete the `wrap_with_transaction` function and the now-unused `textwrap` import.

Keep `import hashlib`, `feature_warnings`, `_revision_update`, `document_revision`, and `require_expected_revision`. They serve `query_objects` cursors and stale-revision detection, which are unrelated to transactions.

- [ ] **Step 3: Delete the obsolete unit tests**

Remove `test_owned_transaction_rejects_an_existing_transaction`, `test_owned_transaction_supports_lazy_freecad_transactions`, and `test_owned_transaction_does_not_abort_a_replacement_transaction` from `tests/unit/test_tools_utils.py`. They assert the behaviour of deleted functions.

Keep `test_document_revision_changes_for_property_only_edits`.

The operator-safety property those tests covered now lives in `tests/integration/test_transaction_boundary.py`, against real FreeCAD rather than a fake that cannot model lazy booking.

- [ ] **Step 4: Run the full quality gate**

Run: `just testing::unit && just quality::lint && just quality::typecheck`
Expected: all PASS.

- [ ] **Step 5: Run all integration tests**

Run: `uv run pytest tests/integration -v`
Expected: PASS, including `test_transaction_boundary.py` and `test_stage_c_regressions.py`.

- [ ] **Step 6: Rewrite the transaction guidance in `CLAUDE.md`**

`CLAUDE.md` currently teaches the pattern this plan deletes. Leaving it in place would send the next contributor straight back into the bug.

In the section **"Implementing Transaction Support for Undo/Redo"**, replace the `doc.openTransaction(...)` / `commitTransaction` / `abortTransaction` example, the `wrap_with_transaction` helper example, and the "Tools Requiring Transactions" list with:

````markdown
### Implementing Transaction Support for Undo/Redo

**CRITICAL**: Tools do NOT open their own transactions. The executor owns the
transaction boundary, so a failed call can never leave one open.

Every `execute_python` call declares its intent with the required, keyword-only
`transaction` parameter:

```python
# Mutating: the name appears in FreeCAD's Edit > Undo menu.
result = await bridge.execute_python(code, transaction="Create Box")

# Read-only, export, or view: must not open a transaction.
result = await bridge.execute_python(code, transaction=None)
```

The executor arms `setActiveTransaction(name, persist=True)` before running the
code and closes it in a `finally`: committing on success, aborting on any
exception. Generated code must never call `openTransaction`, `commitTransaction`,
or `abortTransaction`. To roll back deliberately, just raise — the executor
aborts.

`transaction` is required and has no default, so mypy rejects any call site that
does not declare whether it mutates.
````

Keep the existing "Tools NOT Requiring Transactions" list; it is still accurate and now maps directly onto `transaction=None`.

Also update the **"Note on transaction support"** paragraph in the Tools Reference section, which currently says mutation tools "wrap their operations in transactions" — they no longer do; the executor does.

- [ ] **Step 7: Update the spec status**

In `docs/development/transaction-boundary-design.md`, change `Status: proposed` to `Status: Phase 1 implemented`, and record the probe result under `## Probe findings` if Task 1 left it open.

- [ ] **Step 8: Verify documentation still builds**

Run: `uv run --frozen --extra dev python -m mkdocs build --strict`
Expected: PASS. This hook runs on any change under `docs/`.

- [ ] **Step 9: Commit**

```bash
git add src/freecad_mcp/tools/utils.py \
        tests/unit/test_tools_utils.py \
        docs/development/transaction-boundary-design.md \
        CLAUDE.md
git commit -m "refactor: remove the per-tool transaction machinery"
```

---

## Notes for the executor

**Do not fix these — they are Phase 2 or explicitly out of scope:**

- `edit_object` accepting `dict[str, Any]` and raising raw `TypeError`. After this plan that is one failed call, not a wedged session. Typing it, and deciding whether the typed surface should grow a placement tool so `edit_object` can leave the parametric profile, is Phase 2.
- `bind_expressions` per-item diagnostics, `create_constrained_sketch` error quality.
- Turn-count reduction (`create_variant`, relaxed validation gates).

**Known residual risk, documented not fixed:** a timed-out request abandons the waiter, not the execution, so `finally` still runs but late. A transaction can outlive the tool's error return. Bounded and self-clearing, not a wedge.

**Consequence for benchmarks:** this changes the system under test. Runs made after it are a new condition and are not comparable with Stage D or the local v1/v2 sessions. Do not rerun or repair any frozen archive.
