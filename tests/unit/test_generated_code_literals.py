"""Guard the generated-code templates against literal identity comparisons.

Every tool that talks to FreeCAD builds Python source with an f-string and
hands it to the bridge to `exec` inside FreeCAD's own interpreter. An
interpolation written as `{doc_name!r} is None` renders as `'Target' is None`
whenever the caller passes a name, which CPython reports as
`SyntaxWarning: "is" with 'str' literal` in the operator's FreeCAD console --
and as a `SyntaxError` under `-W error`, which would take the bridge down.

The fix is always the same: bind the interpolation to a name on its own line
and compare the name. This module scans the shipped source for the mistake so
a new template cannot reintroduce it silently. It found 57 sites when first
written: 55 `{doc_name!r}` and one `{label!r}`, which CPython warns about,
and one `{object_names!r}` that renders a list display and does not warn but
is the same mistake.
"""

import ast
import warnings
from pathlib import Path

import pytest

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "freecad_mcp"

# `is`/`is not` against these renders as a comparison between constants, which
# CPython warns about. `None`, `True`, `False` and `...` are the only operands
# it accepts silently, and an interpolation never renders as one of those.
IDENTITY_SUFFIXES = (" is None", " is not None", " is True", " is False")


def _python_sources() -> list[Path]:
    return sorted(
        path for path in SOURCE_ROOT.rglob("*.py") if path.name != "_version.py"
    )


def _literal_identity_offences(path: Path) -> list[str]:
    """Report every `{value!r} is None` written inside an f-string."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offences = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        for index, part in enumerate(node.values[:-1]):
            if not isinstance(part, ast.FormattedValue):
                continue
            follower = node.values[index + 1]
            if not isinstance(follower, ast.Constant):
                continue
            text = str(follower.value)
            if text.startswith(IDENTITY_SUFFIXES):
                rendered = ast.unparse(part.value)
                offences.append(
                    f"{path.name}:{part.lineno}: "
                    f"{{{rendered}!r}}{text.split(chr(10))[0]}"
                )
    return offences


@pytest.mark.parametrize("path", _python_sources(), ids=lambda path: path.name)
def test_no_generated_identity_comparison_against_a_literal(path: Path) -> None:
    offences = _literal_identity_offences(path)
    assert not offences, (
        "Generated code compares an interpolated literal with `is`. Bind the "
        "value to a name first and compare the name:\n" + "\n".join(offences)
    )


def test_cpython_rejects_the_rendered_form_the_scanner_forbids() -> None:
    """The premise, not an assumption: CPython really does complain."""
    doc_name = "Target"
    with pytest.warns(SyntaxWarning, match="'str' literal"):
        compile(f"doc = None if {doc_name!r} is None else 1", "<rendered>", "exec")


def test_the_bound_name_form_compiles_without_a_warning() -> None:
    doc_name = "Target"
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        compile(
            f"requested = {doc_name!r}\ndoc = None if requested is None else 1",
            "<rendered>",
            "exec",
        )


def test_the_scanner_recognises_the_mistake(tmp_path: Path) -> None:
    """A guard that never fires is worthless; prove it fires."""
    offender = tmp_path / "offender.py"
    offender.write_text(
        'code = f"""\ndoc = None if {doc_name!r} is None else 1\n"""\n',
        encoding="utf-8",
    )
    assert _literal_identity_offences(offender)


def test_the_scanner_accepts_a_bound_name(tmp_path: Path) -> None:
    innocent = tmp_path / "innocent.py"
    innocent.write_text(
        'code = f"""\n'
        "requested = {doc_name!r}\n"
        "doc = None if requested is None else 1\n"
        '"""\n',
        encoding="utf-8",
    )
    assert not _literal_identity_offences(innocent)
