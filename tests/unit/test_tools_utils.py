"""Tests for generated workflow helper code."""

import sys
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


class TestReportViewLines:
    """Tests for recovering FreeCAD's Report view text."""

    def _namespace(self, gui_up: bool) -> dict[str, object]:
        """Load the helpers with a FreeCAD stub in a known GUI state."""
        return _workflow_namespace(SimpleNamespace(GuiUp=gui_up))

    def test_returns_nothing_without_a_gui(self) -> None:
        """Headless FreeCAD has no Report view, and that is not an error."""
        lines = self._namespace(gui_up=False)["report_view_lines"]

        assert lines(("Roof",)) == []  # type: ignore[operator]

    def test_returns_nothing_when_no_names_are_given(self) -> None:
        """Without a name to match there is nothing to attribute a line to."""
        lines = self._namespace(gui_up=True)["report_view_lines"]

        assert lines(("", None)) == []  # type: ignore[operator]

    def test_reads_the_named_objects_messages(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """The line FreeCAD printed for this object must reach the caller.

        `Spire`'s `getStatusString()` returned only "Error" while the Report
        view carried "Wire is not closed." -- the one line that says what to
        repair.
        """
        report = SimpleNamespace(
            objectName=lambda: "Report view",
            toPlainText=lambda: (
                "19:55:01  Spire: Wire is not closed.\n"
                "19:55:06  Roof001: Linked shape object is empty\n"
            ),
        )
        window = SimpleNamespace(findChildren=lambda _cls: [report])
        monkeypatch.setitem(
            sys.modules,
            "FreeCADGui",
            SimpleNamespace(getMainWindow=lambda: window),
        )
        monkeypatch.setitem(
            sys.modules,
            "PySide6",
            SimpleNamespace(QtWidgets=SimpleNamespace(QTextEdit=object)),
        )
        monkeypatch.setitem(
            sys.modules, "PySide6.QtWidgets", SimpleNamespace(QTextEdit=object)
        )
        lines = self._namespace(gui_up=True)["report_view_lines"]

        assert lines(("Spire", "Spire")) == ["Wire is not closed."]  # type: ignore[operator]

    def test_a_broken_report_view_never_fails_the_call(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """Diagnostics are a courtesy; they must not become a failure mode."""

        def _explode() -> None:
            raise RuntimeError("no main window")

        monkeypatch.setitem(
            sys.modules, "FreeCADGui", SimpleNamespace(getMainWindow=_explode)
        )
        lines = self._namespace(gui_up=True)["report_view_lines"]

        assert lines(("Spire",)) == []  # type: ignore[operator]
