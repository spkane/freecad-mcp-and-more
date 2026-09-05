"""Utility functions for FreeCAD MCP tools.

This module provides shared utilities for tool implementations:
document revision digests for stale-write detection and query cursors,
and the feature-warning channel. Transactions are the executor's
responsibility, not a tool's.
"""

WORKFLOW_HELPERS = r"""import hashlib

feature_warnings = []

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

_BENIGN_STATUS = ("", "Touched", "Untouched", "Up-to-date", "Invalid")

_SOLVER_DIAGNOSTICS = (
    ("redundant", "RedundantConstraints"),
    ("partially_redundant", "PartiallyRedundantConstraints"),
    ("conflicting", "ConflictingConstraints"),
    ("malformed", "MalformedConstraints"),
)

def report_view_lines(names, limit=3):
    # FreeCAD prints its most useful diagnoses -- "Wire is not closed",
    # "Revolve axis intersects the sketch" -- to the Report view and nowhere
    # an MCP client can reach. FreeCAD.Console exposes no AddObserver, so the
    # only route is the widget itself, which exists in GUI mode only. Every
    # step is guarded: a missing Report view must never fail a tool call.
    matches = []
    try:
        if not FreeCAD.GuiUp:
            return matches
        import FreeCADGui

        try:
            from PySide6 import QtWidgets
        except ImportError:
            from PySide2 import QtWidgets
        window = FreeCADGui.getMainWindow()
        if window is None:
            return matches
        prefixes = tuple(str(name) + ":" for name in names if name)
        if not prefixes:
            return matches
        for widget in window.findChildren(QtWidgets.QTextEdit):
            if "eport" not in str(widget.objectName()):
                continue
            for line in widget.toPlainText().splitlines():
                text = line.strip()
                for prefix in prefixes:
                    marker = text.find(prefix)
                    if marker >= 0:
                        detail = text[marker + len(prefix) :].strip()
                        if detail and detail not in matches:
                            matches.append(detail)
    except Exception:
        return matches
    return matches[-limit:]


def object_diagnostics(candidate):
    diagnosis = {}
    try:
        status = str(candidate.getStatusString())
    except Exception:
        status = ""
    if status not in _BENIGN_STATUS:
        diagnosis["status"] = status
    try:
        reported = report_view_lines(
            (getattr(candidate, "Name", ""), getattr(candidate, "Label", ""))
        )
    except Exception:
        reported = []
    if reported:
        diagnosis["reported"] = reported
    if getattr(candidate, "TypeId", "") == "Sketcher::SketchObject":
        solver = {}
        for key, attribute in _SOLVER_DIAGNOSTICS:
            try:
                indices = [int(item) for item in getattr(candidate, attribute, [])]
            except Exception:
                indices = []
            if indices:
                solver[key] = indices
        try:
            solver["fully_constrained"] = bool(candidate.FullyConstrained)
        except Exception:
            pass
        if solver:
            diagnosis["sketch_solver"] = solver
    return diagnosis
"""
