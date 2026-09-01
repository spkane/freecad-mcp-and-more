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
