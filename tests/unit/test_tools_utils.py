"""Tests for generated workflow helper code."""

from types import SimpleNamespace

import pytest

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


def test_owned_transaction_rejects_an_existing_transaction() -> None:
    """A workflow mutation must never close a transaction it did not open."""

    class Document:
        HasPendingTransaction = True
        UndoMode = 1

        def __init__(self) -> None:
            self.opened = False

        def openTransaction(self, _name: str) -> None:
            self.opened = True

    document = Document()
    open_owned_transaction = _workflow_namespace()["open_owned_transaction"]

    with pytest.raises(RuntimeError, match="TRANSACTION_CONFLICT"):
        open_owned_transaction(document, "Mutation")  # type: ignore[operator]

    assert document.opened is False


def test_owned_transaction_supports_lazy_freecad_transactions() -> None:
    """A booked FreeCAD 1.1 transaction is owned before its first mutation."""

    class Application:
        def __init__(self) -> None:
            self.active_transaction: tuple[str, int] | None = None
            self.abort_count = 0

        def getActiveTransaction(self) -> tuple[str, int] | None:
            return self.active_transaction

        def closeActiveTransaction(self, abort: bool) -> None:
            assert abort is True
            self.abort_count += 1
            self.active_transaction = None

    application = Application()

    class Document:
        HasPendingTransaction = False
        UndoMode = 1

        def __init__(self) -> None:
            self.open_count = 0

        def openTransaction(self, name: str) -> None:
            self.open_count += 1
            application.active_transaction = (name, 42)

        def abortTransaction(self) -> None:
            raise AssertionError(
                "A lazy transaction has no document transaction to abort"
            )

    document = Document()
    namespace = _workflow_namespace(application)

    namespace["open_owned_transaction"](document, "Mutation")  # type: ignore[operator]
    namespace["abort_owned_transaction"](document)  # type: ignore[operator]

    assert document.open_count == 1
    assert application.abort_count == 1
    assert application.active_transaction is None


def test_owned_transaction_does_not_abort_a_replacement_transaction() -> None:
    """Error cleanup must not close a transaction that replaced the owned one."""

    class Application:
        def __init__(self) -> None:
            self.active_transaction: tuple[str, int] | None = None
            self.abort_count = 0

        def getActiveTransaction(self) -> tuple[str, int] | None:
            return self.active_transaction

        def closeActiveTransaction(self, _abort: bool) -> None:
            self.abort_count += 1
            self.active_transaction = None

    application = Application()

    class Document:
        HasPendingTransaction = False
        UndoMode = 1

        def openTransaction(self, name: str) -> None:
            application.active_transaction = (name, 42)

    document = Document()
    namespace = _workflow_namespace(application)

    namespace["open_owned_transaction"](document, "Mutation")  # type: ignore[operator]
    application.active_transaction = ("Other mutation", 43)
    namespace["abort_owned_transaction"](document)  # type: ignore[operator]

    assert application.abort_count == 0
    assert application.active_transaction == ("Other mutation", 43)


def test_owned_transaction_aborts_only_while_pending() -> None:
    """Post-commit cleanup must not abort an already closed transaction."""

    class Document:
        HasPendingTransaction = False
        UndoMode = 1

        def __init__(self) -> None:
            self.abort_count = 0

        def abortTransaction(self) -> None:
            self.abort_count += 1

    document = Document()
    abort_owned_transaction = _workflow_namespace()["abort_owned_transaction"]

    abort_owned_transaction(document)  # type: ignore[operator]

    assert document.abort_count == 0
