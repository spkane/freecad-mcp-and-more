"""Utility functions for FreeCAD MCP tools.

This module provides shared utilities for tool implementations,
including transaction wrapping for undo support.
"""

import textwrap

WORKFLOW_HELPERS = r"""import hashlib

_owned_transaction_id = None

def _revision_update(digest, value):
    encoded = str(value).encode("utf-8", "backslashreplace")
    digest.update(len(encoded).to_bytes(8, "big"))
    digest.update(encoded)

def document_revision(document):
    digest = hashlib.sha256()
    _revision_update(digest, document.Name)
    _revision_update(digest, id(document))
    _revision_update(digest, getattr(document, "Label", ""))
    for candidate in sorted(document.Objects, key=lambda item: item.Name):
        _revision_update(digest, candidate.Name)
        _revision_update(digest, candidate.TypeId)
        _revision_update(digest, candidate.Content)
        _revision_update(
            digest,
            tuple(sorted(str(state) for state in getattr(candidate, "State", []))),
        )
        view = getattr(candidate, "ViewObject", None)
        if view is not None:
            _revision_update(digest, getattr(view, "Content", ""))
    return "rev_" + digest.hexdigest()[:24]

def require_expected_revision(document, expected_revision):
    current_revision = document_revision(document)
    if expected_revision is not None and expected_revision != current_revision:
        raise RuntimeError(
            "STALE_REVISION: expected %s, found %s"
            % (expected_revision, current_revision)
        )
    return current_revision

def active_application_transaction():
    application = globals().get("FreeCAD")
    get_active_transaction = getattr(application, "getActiveTransaction", None)
    if get_active_transaction is None:
        return None
    active_transaction = get_active_transaction()
    if not isinstance(active_transaction, (tuple, list)):
        return None
    return active_transaction if len(active_transaction) > 1 and active_transaction[1] else None

def has_open_transaction(document):
    if bool(getattr(document, "HasPendingTransaction", False)):
        return True
    # FreeCAD 1.1 books transactions lazily until the first document mutation.
    get_booked_transaction_id = getattr(document, "getBookedTransactionID", None)
    if get_booked_transaction_id and bool(get_booked_transaction_id()):
        return True
    return active_application_transaction() is not None

def open_owned_transaction(document, name):
    global _owned_transaction_id
    _owned_transaction_id = None
    if has_open_transaction(document):
        raise RuntimeError(
            "TRANSACTION_CONFLICT: Document already has a pending transaction"
        )
    if document.UndoMode == 0:
        document.UndoMode = 1
    document.openTransaction(name)
    if not has_open_transaction(document):
        raise RuntimeError("BRIDGE_ERROR: Failed to open document transaction")
    active_transaction = active_application_transaction()
    if active_transaction is not None:
        _owned_transaction_id = active_transaction[1]

def abort_owned_transaction(document):
    global _owned_transaction_id
    if bool(getattr(document, "HasPendingTransaction", False)):
        document.abortTransaction()
        _owned_transaction_id = None
        return
    get_booked_transaction_id = getattr(document, "getBookedTransactionID", None)
    if get_booked_transaction_id and bool(get_booked_transaction_id()):
        document.abortTransaction()
        _owned_transaction_id = None
        return
    active_transaction = active_application_transaction()
    if active_transaction is not None and active_transaction[1] == _owned_transaction_id:
        application = globals().get("FreeCAD")
        application.closeActiveTransaction(True)
    _owned_transaction_id = None
"""


def wrap_with_transaction(
    code: str,
    transaction_name: str,
    doc_expr: str = "FreeCAD.ActiveDocument",
) -> str:
    """Wrap Python code with FreeCAD transaction for undo support.

    FreeCAD transactions enable undo/redo functionality. All modifying
    operations should be wrapped in transactions so users can easily
    undo changes if something goes wrong.

    Args:
        code: The Python code to wrap. Should set `_result_` for return value.
        transaction_name: Human-readable name for the transaction (shown in undo menu).
        doc_expr: Expression to get the document. Defaults to "FreeCAD.ActiveDocument".

    Returns:
        Code string wrapped with transaction open/commit/abort handling.

    Raises:
        Exception: Re-raises any exception from the wrapped code after aborting
            the transaction. The original traceback is preserved.

    Example:
        >>> code = '''
        ... box = doc.addObject("Part::Box", "MyBox")
        ... box.Length = 10
        ... _result_ = {"name": box.Name}
        ... '''
        >>> wrapped = wrap_with_transaction(code, "Create Box")
    """
    # Indent the original code for the try block
    indented_code = textwrap.indent(code.strip(), "    ")

    return f"""_txn_doc = {doc_expr}
if _txn_doc is not None:
    _txn_doc.openTransaction({transaction_name!r})
try:
{indented_code}
    if _txn_doc is not None:
        _txn_doc.commitTransaction()
except Exception:
    if _txn_doc is not None:
        _txn_doc.abortTransaction()
    raise
"""
