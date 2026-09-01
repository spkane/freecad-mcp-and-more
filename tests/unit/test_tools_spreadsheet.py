"""Unit tests for the spreadsheet tools module.

This module tests the Spreadsheet workbench tools for parametric design,
including cell operations, aliases, and CSV import/export functionality.
All tests use mocked FreeCAD bridges to avoid requiring a running FreeCAD
instance.
"""

from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from freecad_mcp.bridge.base import ExecutionResult

# Type aliases for fixtures
RegisteredTools = dict[str, Callable[..., Awaitable[Any]]]


class TestSpreadsheetTools:
    """Tests for Spreadsheet workbench tools."""

    @pytest.fixture
    def mock_mcp(self) -> MagicMock:
        """Create a mock MCP server that captures tool registrations.

        Creates a MagicMock that simulates the FastMCP server's tool
        registration mechanism, storing registered tools in _registered_tools.

        Returns:
            MagicMock configured with a tool() decorator that captures
            registered tool functions.

        Raises:
            None.

        Example:
            mcp = mock_mcp()
            mcp._registered_tools["tool_name"]  # Access registered tool
        """
        mcp = MagicMock()
        registered_tools: dict[str, Callable[..., Awaitable[Any]]] = {}
        mcp._registered_tools = registered_tools

        def tool_decorator() -> Callable[
            [Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]
        ]:
            def wrapper(
                func: Callable[..., Awaitable[Any]],
            ) -> Callable[..., Awaitable[Any]]:
                registered_tools[func.__name__] = func
                return func

            return wrapper

        mcp.tool = tool_decorator
        return mcp

    @pytest.fixture
    def mock_bridge(self) -> AsyncMock:
        """Create a mock FreeCAD bridge.

        Creates an AsyncMock that simulates the FreeCAD bridge's
        execute_python method for testing without a real FreeCAD instance.

        Returns:
            AsyncMock that can be configured with return values for
            execute_python calls.

        Raises:
            None.

        Example:
            mock_bridge.execute_python = AsyncMock(
                return_value=ExecutionResult(success=True, result={...})
            )
        """
        return AsyncMock()

    @pytest.fixture
    def register_tools(
        self, mock_mcp: MagicMock, mock_bridge: AsyncMock
    ) -> dict[str, Callable[..., Awaitable[Any]]]:
        """Register spreadsheet tools and return the registered functions.

        Imports and calls register_spreadsheet_tools with the mock MCP
        and bridge, returning the dictionary of registered tool functions.

        Args:
            mock_mcp: The mock MCP server fixture.
            mock_bridge: The mock bridge fixture.

        Returns:
            Dictionary mapping tool names to their async callable functions.

        Raises:
            None.

        Example:
            create = register_tools["spreadsheet_create"]
            result = await create(name="Params")
        """
        from freecad_mcp.tools.spreadsheet import register_spreadsheet_tools

        async def get_bridge() -> AsyncMock:
            return mock_bridge

        register_spreadsheet_tools(mock_mcp, get_bridge)
        return mock_mcp._registered_tools

    # =========================================================================
    # spreadsheet_create tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_spreadsheet_create_success(
        self, register_tools: RegisteredTools, mock_bridge: AsyncMock
    ) -> None:
        """Test spreadsheet_create creates a spreadsheet object with default name.

        Verifies that the spreadsheet_create tool successfully creates a new
        Spreadsheet::Sheet object in the active document with default naming.

        Args:
            register_tools: Dictionary of registered spreadsheet tool functions.
            mock_bridge: Mock FreeCAD bridge for simulating execute_python calls.

        Returns:
            None.

        Raises:
            None.

        Example:
            result = await spreadsheet_create()
            assert result["type_id"] == "Spreadsheet::Sheet"
        """
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Spreadsheet",
                    "label": "Spreadsheet",
                    "type_id": "Spreadsheet::Sheet",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        spreadsheet_create = register_tools["spreadsheet_create"]
        result = await spreadsheet_create()

        assert result["name"] == "Spreadsheet"
        assert result["type_id"] == "Spreadsheet::Sheet"
        mock_bridge.execute_python.assert_called_once()

    @pytest.mark.asyncio
    async def test_spreadsheet_create_with_name(
        self, register_tools: RegisteredTools, mock_bridge: AsyncMock
    ) -> None:
        """Test spreadsheet_create uses provided custom name.

        Verifies that the spreadsheet_create tool accepts and uses a custom
        name parameter when creating the spreadsheet object.

        Args:
            register_tools: Dictionary of registered spreadsheet tool functions.
            mock_bridge: Mock FreeCAD bridge for simulating execute_python calls.

        Returns:
            None.

        Raises:
            None.

        Example:
            result = await spreadsheet_create(name="Parameters")
            assert result["name"] == "Parameters"
        """
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "name": "Parameters",
                    "label": "Parameters",
                    "type_id": "Spreadsheet::Sheet",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        spreadsheet_create = register_tools["spreadsheet_create"]
        result = await spreadsheet_create(name="Parameters")

        assert result["name"] == "Parameters"

    @pytest.mark.asyncio
    async def test_spreadsheet_create_failure(
        self, register_tools: RegisteredTools, mock_bridge: AsyncMock
    ) -> None:
        """Test spreadsheet_create raises ValueError on execution failure.

        Verifies that the spreadsheet_create tool properly raises a ValueError
        when the FreeCAD bridge execution fails (e.g., no active document).

        Args:
            register_tools: Dictionary of registered spreadsheet tool functions.
            mock_bridge: Mock FreeCAD bridge configured to return failure.

        Returns:
            None.

        Raises:
            ValueError: When spreadsheet creation fails in FreeCAD.

        Example:
            with pytest.raises(ValueError, match="Failed"):
                await spreadsheet_create()
        """
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=False,
                result=None,
                stdout="",
                stderr="",
                execution_time_ms=5.0,
                error_type="ValueError",
                error_traceback="Failed to create spreadsheet",
            )
        )

        spreadsheet_create = register_tools["spreadsheet_create"]
        with pytest.raises(ValueError, match="Failed to create spreadsheet"):
            await spreadsheet_create()

    # =========================================================================
    # spreadsheet_set_cell tests
    # =========================================================================

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "cell,value,computed",
        [
            pytest.param("A1", 100, 100, id="numeric_value"),
            pytest.param("A2", "=A1*2", 200, id="formula_value"),
        ],
    )
    async def test_spreadsheet_set_cell(
        self,
        register_tools: RegisteredTools,
        mock_bridge: AsyncMock,
        cell: str,
        value: Any,
        computed: Any,
    ) -> None:
        """Test spreadsheet_set_cell sets numeric values and formulas.

        Verifies that the spreadsheet_set_cell tool correctly sets both
        numeric values and formula expressions, returning the computed result.

        Args:
            register_tools: Dictionary of registered spreadsheet tool functions.
            mock_bridge: Mock FreeCAD bridge for simulating execute_python calls.
            cell: Cell reference in A1 notation (e.g., "A1", "B2").
            value: Value to set - either numeric or formula string (e.g., "=A1*2").
            computed: Expected computed result after setting the value.

        Returns:
            None.

        Raises:
            None.

        Example:
            result = await set_cell(spreadsheet_name="Params", cell="A1", value=100)
            assert result["computed"] == 100
        """
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "success": True,
                    "cell": cell,
                    "value": value,
                    "computed": computed,
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        set_cell = register_tools["spreadsheet_set_cell"]
        result = await set_cell(spreadsheet_name="Params", cell=cell, value=value)

        assert result["success"] is True
        assert result["cell"] == cell
        assert result["value"] == value
        assert result["computed"] == computed

    @pytest.mark.asyncio
    async def test_spreadsheet_set_cell_not_found(
        self, register_tools: RegisteredTools, mock_bridge: AsyncMock
    ) -> None:
        """Test spreadsheet_set_cell raises ValueError when spreadsheet not found.

        Verifies that the spreadsheet_set_cell tool raises a ValueError with
        an appropriate message when the specified spreadsheet does not exist.

        Args:
            register_tools: Dictionary of registered spreadsheet tool functions.
            mock_bridge: Mock FreeCAD bridge configured to return not-found error.

        Returns:
            None.

        Raises:
            ValueError: When the specified spreadsheet does not exist.

        Example:
            with pytest.raises(ValueError, match="Spreadsheet not found"):
                await set_cell(spreadsheet_name="BadName", cell="A1", value=100)
        """
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=False,
                result=None,
                stdout="",
                stderr="",
                execution_time_ms=5.0,
                error_type="ValueError",
                error_traceback="Spreadsheet not found: BadName",
            )
        )

        set_cell = register_tools["spreadsheet_set_cell"]
        with pytest.raises(ValueError, match="Spreadsheet not found"):
            await set_cell(spreadsheet_name="BadName", cell="A1", value=100)

    # =========================================================================
    # spreadsheet_get_cell tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_spreadsheet_get_cell_success(
        self, register_tools: RegisteredTools, mock_bridge: AsyncMock
    ) -> None:
        """Test spreadsheet_get_cell returns cell value, computed result, and alias.

        Verifies that the spreadsheet_get_cell tool correctly retrieves the
        raw value, computed result, and any alias for a specified cell.

        Args:
            register_tools: Dictionary of registered spreadsheet tool functions.
            mock_bridge: Mock FreeCAD bridge for simulating execute_python calls.

        Returns:
            None.

        Raises:
            None.

        Example:
            result = await get_cell(spreadsheet_name="Params", cell="A1")
            assert result["alias"] == "Length"
        """
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "cell": "A1",
                    "value": "100",
                    "computed": 100,
                    "alias": "Length",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        get_cell = register_tools["spreadsheet_get_cell"]
        result = await get_cell(spreadsheet_name="Params", cell="A1")

        assert result["cell"] == "A1"
        assert result["computed"] == 100
        assert result["alias"] == "Length"

    @pytest.mark.asyncio
    async def test_spreadsheet_get_cell_empty(
        self, register_tools: RegisteredTools, mock_bridge: AsyncMock
    ) -> None:
        """Test spreadsheet_get_cell handles empty cells gracefully.

        Verifies that the spreadsheet_get_cell tool returns None values for
        cells that have not been set, without raising errors.

        Args:
            register_tools: Dictionary of registered spreadsheet tool functions.
            mock_bridge: Mock FreeCAD bridge for simulating execute_python calls.

        Returns:
            None.

        Raises:
            None.

        Example:
            result = await get_cell(spreadsheet_name="Params", cell="Z99")
            assert result["computed"] is None
        """
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "cell": "Z99",
                    "value": None,
                    "computed": None,
                    "alias": None,
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        get_cell = register_tools["spreadsheet_get_cell"]
        result = await get_cell(spreadsheet_name="Params", cell="Z99")

        assert result["cell"] == "Z99"
        assert result["computed"] is None
        assert result["alias"] is None

    # =========================================================================
    # spreadsheet_set_alias tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_spreadsheet_set_alias_success(
        self, register_tools: RegisteredTools, mock_bridge: AsyncMock
    ) -> None:
        """Test spreadsheet_set_alias assigns alias to cell for expressions.

        Verifies that the spreadsheet_set_alias tool correctly sets a named
        alias on a cell, enabling its use in FreeCAD expressions.

        Args:
            register_tools: Dictionary of registered spreadsheet tool functions.
            mock_bridge: Mock FreeCAD bridge for simulating execute_python calls.

        Returns:
            None.

        Raises:
            None.

        Example:
            result = await set_alias(spreadsheet_name="Params", cell="A1", alias="Length")
            assert result["alias"] == "Length"
        """
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "success": True,
                    "cell": "A1",
                    "alias": "BoxLength",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        set_alias = register_tools["spreadsheet_set_alias"]
        result = await set_alias(
            spreadsheet_name="Params", cell="A1", alias="BoxLength"
        )

        assert result["success"] is True
        assert result["alias"] == "BoxLength"

    @pytest.mark.asyncio
    async def test_spreadsheet_set_alias_invalid(
        self, register_tools: RegisteredTools, mock_bridge: AsyncMock
    ) -> None:
        """Test spreadsheet_set_alias rejects invalid Python identifier aliases.

        Verifies that the spreadsheet_set_alias tool raises a ValueError when
        given an alias that is not a valid Python identifier (e.g., starts
        with a number).

        Args:
            register_tools: Dictionary of registered spreadsheet tool functions.
            mock_bridge: Mock FreeCAD bridge configured to return validation error.

        Returns:
            None.

        Raises:
            ValueError: When the alias is not a valid Python identifier.

        Example:
            with pytest.raises(ValueError, match="Invalid alias"):
                await set_alias(spreadsheet_name="Params", cell="A1", alias="123bad")
        """
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=False,
                result=None,
                stdout="",
                stderr="",
                execution_time_ms=5.0,
                error_type="ValueError",
                error_traceback="Invalid alias: '123bad'. Must be a valid Python identifier.",
            )
        )

        set_alias = register_tools["spreadsheet_set_alias"]
        with pytest.raises(ValueError, match="Invalid alias"):
            await set_alias(spreadsheet_name="Params", cell="A1", alias="123bad")

    # =========================================================================
    # spreadsheet_get_aliases tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_spreadsheet_get_aliases_success(
        self, register_tools: RegisteredTools, mock_bridge: AsyncMock
    ) -> None:
        """Test spreadsheet_get_aliases returns all defined aliases.

        Verifies that the spreadsheet_get_aliases tool returns a dictionary
        mapping alias names to their cell references along with the count.

        Args:
            register_tools: Dictionary of registered spreadsheet tool functions.
            mock_bridge: Mock FreeCAD bridge for simulating execute_python calls.

        Returns:
            None.

        Raises:
            None.

        Example:
            result = await get_aliases(spreadsheet_name="Params")
            assert result["aliases"]["Length"] == "A1"
        """
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "spreadsheet": "Params",
                    "aliases": {"Length": "A1", "Width": "A2", "Height": "A3"},
                    "count": 3,
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        get_aliases = register_tools["spreadsheet_get_aliases"]
        result = await get_aliases(spreadsheet_name="Params")

        assert result["count"] == 3
        assert result["aliases"]["Length"] == "A1"
        assert result["aliases"]["Width"] == "A2"

    @pytest.mark.asyncio
    async def test_spreadsheet_get_aliases_empty(
        self, register_tools: RegisteredTools, mock_bridge: AsyncMock
    ) -> None:
        """Test spreadsheet_get_aliases handles spreadsheets with no aliases.

        Verifies that the spreadsheet_get_aliases tool returns an empty
        dictionary and zero count when no aliases have been defined.

        Args:
            register_tools: Dictionary of registered spreadsheet tool functions.
            mock_bridge: Mock FreeCAD bridge for simulating execute_python calls.

        Returns:
            None.

        Raises:
            None.

        Example:
            result = await get_aliases(spreadsheet_name="Params")
            assert result["count"] == 0
        """
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "spreadsheet": "Params",
                    "aliases": {},
                    "count": 0,
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        get_aliases = register_tools["spreadsheet_get_aliases"]
        result = await get_aliases(spreadsheet_name="Params")

        assert result["count"] == 0
        assert result["aliases"] == {}

    # =========================================================================
    # spreadsheet_clear_cell tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_spreadsheet_clear_cell_success(
        self, register_tools: RegisteredTools, mock_bridge: AsyncMock
    ) -> None:
        """Test spreadsheet_clear_cell clears cell content and alias.

        Verifies that the spreadsheet_clear_cell tool removes both the cell
        value and any associated alias from the specified cell.

        Args:
            register_tools: Dictionary of registered spreadsheet tool functions.
            mock_bridge: Mock FreeCAD bridge for simulating execute_python calls.

        Returns:
            None.

        Raises:
            None.

        Example:
            result = await clear_cell(spreadsheet_name="Params", cell="A1")
            assert result["success"] is True
        """
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "success": True,
                    "cell": "A1",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        clear_cell = register_tools["spreadsheet_clear_cell"]
        result = await clear_cell(spreadsheet_name="Params", cell="A1")

        assert result["success"] is True
        assert result["cell"] == "A1"

    # =========================================================================
    # spreadsheet_bind_property tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_spreadsheet_bind_property_success(
        self, register_tools: RegisteredTools, mock_bridge: AsyncMock
    ) -> None:
        """Test spreadsheet_bind_property binds object property to cell alias.

        Verifies that the spreadsheet_bind_property tool creates an expression
        binding between a FreeCAD object property and a spreadsheet cell alias.

        Args:
            register_tools: Dictionary of registered spreadsheet tool functions.
            mock_bridge: Mock FreeCAD bridge for simulating execute_python calls.

        Returns:
            None.

        Raises:
            None.

        Example:
            result = await bind_property(
                spreadsheet_name="Params", alias="BoxLength",
                target_object="Box", target_property="Length"
            )
            assert result["expression"] == "Params.BoxLength"
        """
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "success": True,
                    "expression": "Params.BoxLength",
                    "target_object": "Box",
                    "target_property": "Length",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        bind_property = register_tools["spreadsheet_bind_property"]
        result = await bind_property(
            spreadsheet_name="Params",
            alias="BoxLength",
            target_object="Box",
            target_property="Length",
        )

        assert result["success"] is True
        assert result["expression"] == "Params.BoxLength"
        assert result["target_object"] == "Box"

    @pytest.mark.asyncio
    async def test_spreadsheet_bind_property_accepts_constraint_expression_path(
        self, register_tools: RegisteredTools, mock_bridge: AsyncMock
    ) -> None:
        """Bindings should support sketch constraints, not only Python attributes."""
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "success": True,
                    "expression": "Params.TowerHeight",
                    "target_object": "TowerSketch",
                    "target_property": "Constraints[8]",
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        bind_property = register_tools["spreadsheet_bind_property"]
        await bind_property(
            spreadsheet_name="Params",
            alias="TowerHeight",
            target_object="TowerSketch",
            target_property="Constraints[8]",
        )

        code = mock_bridge.execute_python.call_args.args[0]
        assert "hasattr(target, prop)" not in code
        assert "target.setExpression(prop, expression)" in code

    @pytest.mark.asyncio
    async def test_spreadsheet_bind_property_alias_not_found(
        self, register_tools: RegisteredTools, mock_bridge: AsyncMock
    ) -> None:
        """Test spreadsheet_bind_property raises ValueError when alias not found.

        Verifies that the spreadsheet_bind_property tool raises a ValueError
        when attempting to bind to an alias that does not exist in the
        spreadsheet.

        Args:
            register_tools: Dictionary of registered spreadsheet tool functions.
            mock_bridge: Mock FreeCAD bridge configured to return alias not found.

        Returns:
            None.

        Raises:
            ValueError: When the specified alias does not exist.

        Example:
            with pytest.raises(ValueError, match="Alias not found"):
                await bind_property(alias="NoSuchAlias", ...)
        """
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=False,
                result=None,
                stdout="",
                stderr="",
                execution_time_ms=5.0,
                error_type="ValueError",
                error_traceback="Alias not found: 'NoSuchAlias'",
            )
        )

        bind_property = register_tools["spreadsheet_bind_property"]
        with pytest.raises(ValueError, match="Alias not found"):
            await bind_property(
                spreadsheet_name="Params",
                alias="NoSuchAlias",
                target_object="Box",
                target_property="Length",
            )

    # =========================================================================
    # spreadsheet_get_cell_range tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_spreadsheet_get_cell_range_success(
        self, register_tools: RegisteredTools, mock_bridge: AsyncMock
    ) -> None:
        """Test spreadsheet_get_cell_range returns values for rectangular range.

        Verifies that the spreadsheet_get_cell_range tool returns a dictionary
        of cell values for all cells in the specified rectangular range.

        Args:
            register_tools: Dictionary of registered spreadsheet tool functions.
            mock_bridge: Mock FreeCAD bridge for simulating execute_python calls.

        Returns:
            None.

        Raises:
            None.

        Example:
            result = await get_range(spreadsheet_name="Params", start_cell="A1", end_cell="B2")
            assert result["cells"]["A1"] == 10
        """
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "spreadsheet": "Params",
                    "start": "A1",
                    "end": "B2",
                    "cells": {"A1": 10, "A2": 20, "B1": 30, "B2": 40},
                },
                stdout="",
                stderr="",
                execution_time_ms=10.0,
            )
        )

        get_range = register_tools["spreadsheet_get_cell_range"]
        result = await get_range(
            spreadsheet_name="Params", start_cell="A1", end_cell="B2"
        )

        assert result["start"] == "A1"
        assert result["end"] == "B2"
        assert result["cells"]["A1"] == 10
        assert result["cells"]["B2"] == 40

    # =========================================================================
    # spreadsheet_import_csv tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_spreadsheet_import_csv_success(
        self, register_tools: RegisteredTools, mock_bridge: AsyncMock
    ) -> None:
        """Test spreadsheet_import_csv imports data from CSV file.

        Verifies that the spreadsheet_import_csv tool successfully imports
        CSV data into the spreadsheet starting at A1 by default.

        Args:
            register_tools: Dictionary of registered spreadsheet tool functions.
            mock_bridge: Mock FreeCAD bridge for simulating execute_python calls.

        Returns:
            None.

        Raises:
            None.

        Example:
            result = await import_csv(spreadsheet_name="Data", file_path="/tmp/data.csv")
            assert result["rows_imported"] == 10
        """
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "success": True,
                    "rows_imported": 10,
                    "cols_imported": 3,
                    "start_cell": "A1",
                },
                stdout="",
                stderr="",
                execution_time_ms=50.0,
            )
        )

        import_csv = register_tools["spreadsheet_import_csv"]
        result = await import_csv(spreadsheet_name="Data", file_path="/tmp/data.csv")

        assert result["success"] is True
        assert result["rows_imported"] == 10
        assert result["cols_imported"] == 3

    @pytest.mark.asyncio
    async def test_spreadsheet_import_csv_with_options(
        self, register_tools: RegisteredTools, mock_bridge: AsyncMock
    ) -> None:
        """Test spreadsheet_import_csv respects delimiter and start cell options.

        Verifies that the spreadsheet_import_csv tool correctly handles custom
        delimiter (e.g., tab for TSV files) and start cell parameters.

        Args:
            register_tools: Dictionary of registered spreadsheet tool functions.
            mock_bridge: Mock FreeCAD bridge for simulating execute_python calls.

        Returns:
            None.

        Raises:
            None.

        Example:
            result = await import_csv(
                spreadsheet_name="Data", file_path="/tmp/data.tsv",
                delimiter="\\t", start_cell="C3"
            )
            assert result["start_cell"] == "C3"
        """
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "success": True,
                    "rows_imported": 5,
                    "cols_imported": 2,
                    "start_cell": "C3",
                },
                stdout="",
                stderr="",
                execution_time_ms=30.0,
            )
        )

        import_csv = register_tools["spreadsheet_import_csv"]
        result = await import_csv(
            spreadsheet_name="Data",
            file_path="/tmp/data.tsv",
            delimiter="\t",
            start_cell="C3",
        )

        assert result["success"] is True
        assert result["start_cell"] == "C3"

    # =========================================================================
    # spreadsheet_export_csv tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_spreadsheet_export_csv_success(
        self, register_tools: RegisteredTools, mock_bridge: AsyncMock
    ) -> None:
        """Test spreadsheet_export_csv exports data to CSV file.

        Verifies that the spreadsheet_export_csv tool successfully exports
        spreadsheet data to the specified CSV file path.

        Args:
            register_tools: Dictionary of registered spreadsheet tool functions.
            mock_bridge: Mock FreeCAD bridge for simulating execute_python calls.

        Returns:
            None.

        Raises:
            None.

        Example:
            result = await export_csv(spreadsheet_name="Data", file_path="/tmp/output.csv")
            assert result["rows_exported"] == 15
        """
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "success": True,
                    "file_path": "/tmp/output.csv",
                    "rows_exported": 15,
                },
                stdout="",
                stderr="",
                execution_time_ms=40.0,
            )
        )

        export_csv = register_tools["spreadsheet_export_csv"]
        result = await export_csv(spreadsheet_name="Data", file_path="/tmp/output.csv")

        assert result["success"] is True
        assert result["file_path"] == "/tmp/output.csv"
        assert result["rows_exported"] == 15

    @pytest.mark.asyncio
    async def test_spreadsheet_export_csv_empty(
        self, register_tools: RegisteredTools, mock_bridge: AsyncMock
    ) -> None:
        """Test spreadsheet_export_csv handles empty spreadsheet gracefully.

        Verifies that the spreadsheet_export_csv tool successfully exports
        an empty CSV file when the spreadsheet has no data.

        Args:
            register_tools: Dictionary of registered spreadsheet tool functions.
            mock_bridge: Mock FreeCAD bridge for simulating execute_python calls.

        Returns:
            None.

        Raises:
            None.

        Example:
            result = await export_csv(spreadsheet_name="Empty", file_path="/tmp/empty.csv")
            assert result["rows_exported"] == 0
        """
        mock_bridge.execute_python = AsyncMock(
            return_value=ExecutionResult(
                success=True,
                result={
                    "success": True,
                    "file_path": "/tmp/empty.csv",
                    "rows_exported": 0,
                },
                stdout="",
                stderr="",
                execution_time_ms=20.0,
            )
        )

        export_csv = register_tools["spreadsheet_export_csv"]
        result = await export_csv(spreadsheet_name="Empty", file_path="/tmp/empty.csv")

        assert result["success"] is True
        assert result["rows_exported"] == 0

    # =========================================================================
    # Test that all expected tools are registered
    # =========================================================================

    def test_all_spreadsheet_tools_registered(
        self, register_tools: RegisteredTools
    ) -> None:
        """Test all expected spreadsheet tools are registered with the MCP server.

        Verifies that all spreadsheet tools required for parametric design
        workflows are properly registered when register_spreadsheet_tools
        is called.

        Args:
            register_tools: Dictionary of registered spreadsheet tool functions.

        Returns:
            None.

        Raises:
            None.

        Example:
            assert "spreadsheet_create" in register_tools
            assert "spreadsheet_set_cell" in register_tools
        """
        expected_tools = [
            "spreadsheet_create",
            "spreadsheet_set_cell",
            "spreadsheet_get_cell",
            "spreadsheet_set_alias",
            "spreadsheet_get_aliases",
            "spreadsheet_clear_cell",
            "spreadsheet_bind_property",
            "spreadsheet_get_cell_range",
            "spreadsheet_import_csv",
            "spreadsheet_export_csv",
        ]

        for tool_name in expected_tools:
            assert tool_name in register_tools, f"Tool {tool_name} not registered"
