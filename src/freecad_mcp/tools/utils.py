"""Utility functions for FreeCAD MCP tools.

This module provides shared utilities for tool implementations,
including transaction wrapping for undo support.
"""

import textwrap

WORKFLOW_HELPERS = r"""import hashlib

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

def open_owned_transaction(document, name):
    if bool(getattr(document, "HasPendingTransaction", False)):
        raise RuntimeError(
            "TRANSACTION_CONFLICT: Document already has a pending transaction"
        )
    if document.UndoMode == 0:
        document.UndoMode = 1
    document.openTransaction(name)
    if not bool(getattr(document, "HasPendingTransaction", False)):
        raise RuntimeError("BRIDGE_ERROR: Failed to open document transaction")

def abort_owned_transaction(document):
    if bool(getattr(document, "HasPendingTransaction", False)):
        document.abortTransaction()
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
