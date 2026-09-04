"""Tests for generated workflow helper code."""

from types import SimpleNamespace

from freecad_mcp.tools.utils import WORKFLOW_HELPERS


def _workflow_namespace(freecad: object | None = None) -> dict[str, object]:
    """Load the dependency-free helpers as FreeCAD's interpreter would."""
    namespace: dict[str, object] = {}
    if freecad is not None:
        namespace["FreeCAD"] = freecad
    exec(WORKFLOW_HELPERS, namespace)  # noqa: S102 - verifies generated bridge code
    return namespace


def test_document_revision_changes_for_property_only_edits() -> None:
    """A changed persisted property must invalidate a prior document revision."""
    obj = SimpleNamespace(
        Name="Pad",
        TypeId="PartDesign::Pad",
        Content='<Property name="Length" value="10.0"/>',
        State=[],
        ViewObject=None,
    )
    document = SimpleNamespace(Name="Model", Label="Model", Objects=[obj])
    revision = _workflow_namespace()["document_revision"]

    before = revision(document)  # type: ignore[operator]
    obj.Content = '<Property name="Length" value="20.0"/>'

    assert revision(document) != before  # type: ignore[operator]
