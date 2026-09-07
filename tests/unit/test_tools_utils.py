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


class TestUnusedVariables:
    """A variable set is a contract: every entry should drive geometry."""

    @staticmethod
    def _unused():
        return _workflow_namespace()["unused_variables"]

    @staticmethod
    def _varset(**values: object) -> SimpleNamespace:
        varset = SimpleNamespace(
            Name="Variables",
            TypeId="App::VarSet",
            PropertiesList=[*values, "Label", "Visibility", "ExpressionEngine"],
            ExpressionEngine=[],
        )
        for name, value in values.items():
            setattr(varset, name, value)
        return varset

    def test_reports_a_variable_nothing_references(self) -> None:
        """`window_count` in the Stage G model drove no geometry at all.

        The operator edited it expecting more windows and nothing moved.
        """
        varset = self._varset(tower_height="120.0 mm", window_count="4")
        pad = SimpleNamespace(
            Name="Pad",
            TypeId="PartDesign::Pad",
            ExpressionEngine=[("Length", "Variables.tower_height")],
        )
        document = SimpleNamespace(Objects=[varset, pad])

        assert self._unused()(document) == [
            {"varset": "Variables", "name": "window_count", "value": "4"}
        ]

    def test_says_nothing_when_every_variable_drives_something(self) -> None:
        varset = self._varset(tower_height="120.0 mm", taper="0.25")
        pad = SimpleNamespace(
            Name="Pad",
            TypeId="PartDesign::Pad",
            ExpressionEngine=[
                ("Length", "Variables.tower_height * (1 - Variables.taper)")
            ],
        )
        document = SimpleNamespace(Objects=[varset, pad])

        assert self._unused()(document) == []

    def test_a_variable_used_only_inside_the_variable_set_counts(self) -> None:
        """A governing value feeding a derived one is doing its job."""
        varset = self._varset(base_diameter="64.0 mm", top_diameter="48.0 mm")
        varset.ExpressionEngine = [("top_diameter", "base_diameter * 0.75")]
        document = SimpleNamespace(Objects=[varset])

        assert [entry["name"] for entry in self._unused()(document)] == ["top_diameter"]

    def test_ignores_documents_without_a_variable_set(self) -> None:
        pad = SimpleNamespace(Name="Pad", TypeId="PartDesign::Pad", ExpressionEngine=[])

        assert self._unused()(SimpleNamespace(Objects=[pad])) == []

    def test_never_reports_freecad_s_own_properties(self) -> None:
        """Label and Visibility are not part of the parametric contract."""
        varset = self._varset(tower_height="120.0 mm")
        pad = SimpleNamespace(
            Name="Pad",
            TypeId="PartDesign::Pad",
            ExpressionEngine=[("Length", "Variables.tower_height")],
        )

        assert self._unused()(SimpleNamespace(Objects=[varset, pad])) == []
