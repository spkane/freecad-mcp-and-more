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


class TestObjectDiagnostics:
    """Tests for the shared `object_diagnostics` generated helper."""

    def _diagnostics(self):  # type: ignore[no-untyped-def]
        """Return the helper as FreeCAD's interpreter would see it."""
        return _workflow_namespace()["object_diagnostics"]

    def test_reports_freecad_own_error_message(self) -> None:
        """A failed object must surface FreeCAD's diagnosis, not its flags."""
        obj = SimpleNamespace(
            TypeId="Part::Extrusion",
            getStatusString=lambda: "No object linked",
        )

        assert self._diagnostics()(obj) == {"status": "No object linked"}

    def test_omits_benign_status_words(self) -> None:
        """State words the caller already reports add no diagnostic value."""
        obj = SimpleNamespace(
            TypeId="Part::Extrusion",
            getStatusString=lambda: "Touched",
        )

        assert self._diagnostics()(obj) == {}

    def test_reports_redundant_constraint_indices_for_sketches(self) -> None:
        """The solver knows which constraint is redundant; so must the caller."""
        sketch = SimpleNamespace(
            TypeId="Sketcher::SketchObject",
            getStatusString=lambda: "Invalid",
            RedundantConstraints=[7],
            PartiallyRedundantConstraints=[],
            ConflictingConstraints=[],
            MalformedConstraints=[],
            FullyConstrained=True,
        )

        assert self._diagnostics()(sketch)["sketch_solver"] == {
            "redundant": [7],
            "fully_constrained": True,
        }

    def test_survives_objects_without_solver_attributes(self) -> None:
        """A diagnostic helper must never be the reason a tool call fails."""

        def _raise() -> str:
            raise RuntimeError("no status available")

        obj = SimpleNamespace(TypeId="Sketcher::SketchObject", getStatusString=_raise)

        assert self._diagnostics()(obj) == {}
