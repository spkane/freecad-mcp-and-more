"""Utility functions for FreeCAD MCP tools.

This module provides shared utilities for tool implementations:
document revision digests for stale-write detection and query cursors,
and the feature-warning channel. Transactions are the executor's
responsibility, not a tool's.
"""

WORKFLOW_HELPERS = r"""import hashlib
import re

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

def object_diagnostics(candidate):
    diagnosis = {}
    try:
        status = str(candidate.getStatusString())
    except Exception:
        status = ""
    if status not in _BENIGN_STATUS:
        diagnosis["status"] = status
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


# Report variables that no expression in the document references.
#
# A variable set is the parametric contract: every entry is supposed to drive
# geometry. One that drives nothing is an abandoned idea that still reads as a
# control, and editing it changes nothing, which is worse than it not being
# there because it invites the caller to try.
#
# Deliberately conservative. Any bare word matching the variable name, anywhere
# in any expression, counts as a reference, so this under-reports rather than
# accusing a variable that is genuinely in use.
def unused_variables(document):
    skip = {
        "ExpressionEngine",
        "Group",
        "Label",
        "Label2",
        "Placement",
        "Proxy",
        "Visibility",
    }
    varsets = [
        candidate
        for candidate in document.Objects
        if getattr(candidate, "TypeId", "") == "App::VarSet"
    ]
    if not varsets:
        return []

    referenced = set()
    for candidate in document.Objects:
        for _path, expression in getattr(candidate, "ExpressionEngine", []) or []:
            referenced.update(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", str(expression)))

    unused = []
    for varset in varsets:
        for name in varset.PropertiesList:
            if name in skip or name in referenced:
                continue
            try:
                value = str(getattr(varset, name))
            except Exception:
                value = ""
            unused.append(
                {"varset": varset.Name, "name": name, "value": value}
            )
    return unused
"""
