"""Live regressions for the executor-owned transaction boundary."""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration


def _active_transaction(proxy) -> list[object] | None:
    """Return FreeCAD's active application transaction, or None."""
    result = proxy.execute(
        "import FreeCAD\n"
        "_active = FreeCAD.getActiveTransaction()\n"
        "_result_ = list(_active) if _active else None\n",
        30000,
        None,
    )
    assert result["success"], result.get("error_message")
    return result["result"]  # type: ignore[return-value]


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


def test_successful_mutation_leaves_no_active_transaction(xmlrpc_proxy) -> None:
    """A committed mutation must not leave an armed transaction for the next call.

    Document.commitTransaction() does not close the application-level
    transaction that Document.openTransaction() arms, so before the executor
    owns the boundary this leaks into the following call.
    """
    doc_name = _make_scratch_document(xmlrpc_proxy)
    try:
        result = xmlrpc_proxy.execute(
            f"import FreeCAD\n"
            f"doc = FreeCAD.getDocument({doc_name!r})\n"
            f"doc.addObject('App::VarSet', 'Vars')\n"
            f"doc.recompute()\n"
            f"_result_ = True\n",
            30000,
            "Add Variable Set",
        )
        assert result["success"], result.get("error_message")

        # Checked from a separate RPC call, which is where the leak is visible.
        assert _active_transaction(xmlrpc_proxy) is None
    finally:
        _close_scratch_document(xmlrpc_proxy, doc_name)


def test_failed_mutation_does_not_leak_across_documents(xmlrpc_proxy) -> None:
    """A failed mutation must not leave an application-level transaction that
    blocks work on a different document.

    The conflict check is not document-scoped: a leaked armed transaction
    blocks any subsequent mutating call, regardless of which document it
    targets.
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
            f"import FreeCAD\n_result_ = FreeCAD.getDocument({doc_name!r}).UndoNames\n",
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
            f"import FreeCAD\n_result_ = FreeCAD.getDocument({doc_name!r}).UndoCount\n",
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
            f"import FreeCAD\n_result_ = FreeCAD.getDocument({doc_name!r}).UndoCount\n",
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
        active_before = _active_transaction(xmlrpc_proxy)
        assert active_before is not None
        assert active_before[0] == "Operator Edit"

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
        active_after = _active_transaction(xmlrpc_proxy)
        assert active_after is not None
        assert active_after[0] == "Operator Edit"
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
