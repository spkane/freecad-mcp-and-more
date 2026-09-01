"""Spreadsheet tools for FreeCAD Robust MCP Server.

This module provides tools for the Spreadsheet workbench, enabling
parametric design through cell values that can drive model dimensions.
"""

from collections.abc import Awaitable, Callable
from typing import Any


def register_spreadsheet_tools(
    mcp: Any, get_bridge: Callable[[], Awaitable[Any]]
) -> None:
    """Register Spreadsheet-related tools with the Robust MCP Server.

    Registers tools for creating and manipulating FreeCAD spreadsheets,
    enabling parametric design through cell values that can drive model
    dimensions via expressions.

    Args:
        mcp: The FastMCP (Robust MCP Server) instance.
        get_bridge: Async function to get the active bridge.

    Returns:
        None. Tools are registered as side effect on the mcp instance.

    Raises:
        TypeError: If mcp does not have a tool() decorator method.
        TypeError: If get_bridge is not callable.

    Example:
        Register spreadsheet tools with an MCP server::

            from freecad_mcp.tools.spreadsheet import register_spreadsheet_tools

            register_spreadsheet_tools(mcp, get_bridge)
            # Now spreadsheet_create, spreadsheet_set_cell, etc. are available
    """

    @mcp.tool()
    async def spreadsheet_create(
        name: str | None = None,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a new Spreadsheet object.

        Spreadsheets allow storing values and formulas that can be
        referenced by other objects in the document for parametric design.

        Args:
            name: Spreadsheet name. Auto-generated if None.
            doc_name: Target document. Uses active document if None.

        Returns:
            Dictionary with created spreadsheet information:
                - name: Spreadsheet object name
                - label: Spreadsheet label
                - type_id: Object type

        Raises:
            ValueError: If the bridge fails to create the spreadsheet.
            ValueError: If a spreadsheet with the same name already exists
                (FreeCAD will auto-rename).

        Example:
            Create a spreadsheet for parameters::

                result = await spreadsheet_create(name="Parameters")
                # Returns {"name": "Parameters", "label": "Parameters", ...}
        """
        bridge = await get_bridge()

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    doc = FreeCAD.newDocument("Unnamed")

# Wrap in transaction for undo support
doc.openTransaction("Create Spreadsheet")
try:
    sheet_name = {name!r} or "Spreadsheet"
    sheet = doc.addObject("Spreadsheet::Sheet", sheet_name)
    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "name": sheet.Name,
        "label": sheet.Label,
        "type_id": sheet.TypeId,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        raise ValueError(result.error_traceback or "Failed to create spreadsheet")

    @mcp.tool()
    async def spreadsheet_set_cell(
        spreadsheet_name: str,
        cell: str,
        value: str | int | float,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Set the value of a cell in a spreadsheet.

        Values can be numbers, strings, or formulas. Formulas start with '='.

        Args:
            spreadsheet_name: Name of the spreadsheet object.
            cell: Cell address (e.g., "A1", "B2", "C10").
            value: Value to set. Can be:
                - Number (int or float)
                - String (text)
                - Formula starting with '=' (e.g., "=A1+B1", "=2*pi")
            doc_name: Document containing the spreadsheet. Uses active if None.

        Returns:
            Dictionary with result:
                - success: Whether the operation succeeded
                - cell: Cell address that was set
                - value: Value that was set
                - computed: Computed value (for formulas)

        Raises:
            ValueError: If no document is found.
            ValueError: If the spreadsheet object is not found.
            ValueError: If the object is not a spreadsheet.
            ValueError: If setting the cell value fails.

        Example:
            Set numeric values and formulas::

                await spreadsheet_set_cell("Params", "A1", 100)  # Number
                await spreadsheet_set_cell("Params", "A2", "=A1*2")  # Formula
                await spreadsheet_set_cell("Params", "B1", "Length")  # String
        """
        bridge = await get_bridge()

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

sheet = doc.getObject({spreadsheet_name!r})
if sheet is None:
    raise ValueError(f"Spreadsheet not found: {spreadsheet_name!r}")

if not hasattr(sheet, "set"):
    raise ValueError(f"Object is not a spreadsheet: {spreadsheet_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Set Spreadsheet Cell")
try:
    cell = {cell!r}
    value = {value!r}

    # Set the cell value
    sheet.set(cell, str(value))
    doc.recompute()

    # Get the computed value
    try:
        computed = sheet.get(cell)
    except Exception:
        computed = value

    doc.commitTransaction()

    _result_ = {{
        "success": True,
        "cell": cell,
        "value": value,
        "computed": computed,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        raise ValueError(result.error_traceback or "Failed to set cell")

    @mcp.tool()
    async def spreadsheet_get_cell(
        spreadsheet_name: str,
        cell: str,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Get the value of a cell in a spreadsheet.

        Args:
            spreadsheet_name: Name of the spreadsheet object.
            cell: Cell address (e.g., "A1", "B2").
            doc_name: Document containing the spreadsheet. Uses active if None.

        Returns:
            Dictionary with cell information:
                - cell: Cell address
                - value: Raw value (formula if it's a formula)
                - computed: Computed/displayed value
                - alias: Cell alias if set, None otherwise

        Raises:
            ValueError: If no document is found.
            ValueError: If the spreadsheet object is not found.
            ValueError: If retrieving cell data fails.

        Example:
            Get a cell value::

                result = await spreadsheet_get_cell("Params", "A1")
                print(f"Value: {result['computed']}")
        """
        bridge = await get_bridge()

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

sheet = doc.getObject({spreadsheet_name!r})
if sheet is None:
    raise ValueError(f"Spreadsheet not found: {spreadsheet_name!r}")

cell = {cell!r}

# Get computed value
try:
    computed = sheet.get(cell)
except Exception:
    computed = None

# Get raw content (formula or value)
try:
    content = sheet.getContents(cell)
except Exception:
    content = None

# Check for alias
alias = None
try:
    # Get all aliases and check if this cell has one
    aliases = sheet.getPropertyByName("cells").Content
    # Parse XML to find alias - simplified approach
    for prop_name in dir(sheet):
        if not prop_name.startswith("_"):
            try:
                cell_prop = sheet.getCellFromAlias(prop_name)
                if cell_prop == cell:
                    alias = prop_name
                    break
            except Exception:
                pass
except Exception:
    pass

_result_ = {{
    "cell": cell,
    "value": content,
    "computed": computed,
    "alias": alias,
}}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        raise ValueError(result.error_traceback or "Failed to get cell")

    @mcp.tool()
    async def spreadsheet_set_alias(
        spreadsheet_name: str,
        cell: str,
        alias: str,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Set an alias for a cell in a spreadsheet.

        Aliases allow referencing cell values by name instead of cell address.
        This is the key to parametric design - set an alias like "Length"
        and then reference it in object properties as "Spreadsheet.Length".

        Args:
            spreadsheet_name: Name of the spreadsheet object.
            cell: Cell address (e.g., "A1").
            alias: Alias name (e.g., "Length", "Width"). Must be a valid
                Python identifier (no spaces, starts with letter).
            doc_name: Document containing the spreadsheet. Uses active if None.

        Returns:
            Dictionary with result:
                - success: Whether the operation succeeded
                - cell: Cell address
                - alias: Alias that was set

        Raises:
            ValueError: If no document is found.
            ValueError: If the spreadsheet object is not found.
            ValueError: If the alias is not a valid Python identifier.
            ValueError: If setting the alias fails.

        Example:
            Set aliases for parametric dimensions::

                await spreadsheet_set_alias("Params", "A1", "BoxLength")
                await spreadsheet_set_alias("Params", "A2", "BoxWidth")
                # Now use Params.BoxLength in expressions
        """
        bridge = await get_bridge()

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

sheet = doc.getObject({spreadsheet_name!r})
if sheet is None:
    raise ValueError(f"Spreadsheet not found: {spreadsheet_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Set Cell Alias")
try:
    cell = {cell!r}
    alias = {alias!r}

    # Validate alias is a valid identifier
    if not alias.isidentifier():
        raise ValueError(f"Invalid alias: {alias!r}. Must be a valid Python identifier.")

    sheet.setAlias(cell, alias)
    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "success": True,
        "cell": cell,
        "alias": alias,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        raise ValueError(result.error_traceback or "Failed to set alias")

    @mcp.tool()
    async def spreadsheet_get_aliases(
        spreadsheet_name: str,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Get all aliases defined in a spreadsheet.

        Args:
            spreadsheet_name: Name of the spreadsheet object.
            doc_name: Document containing the spreadsheet. Uses active if None.

        Returns:
            Dictionary with aliases:
                - spreadsheet: Spreadsheet name
                - aliases: Dictionary mapping alias names to cell addresses
                - count: Number of aliases

        Raises:
            ValueError: If no document is found.
            ValueError: If the spreadsheet object is not found.
            ValueError: If retrieving aliases fails.

        Example:
            List all parameter aliases::

                result = await spreadsheet_get_aliases("Params")
                for alias, cell in result["aliases"].items():
                    print(f"{alias} -> {cell}")
        """
        bridge = await get_bridge()

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

sheet = doc.getObject({spreadsheet_name!r})
if sheet is None:
    raise ValueError(f"Spreadsheet not found: {spreadsheet_name!r}")

aliases = {{}}

# Get aliases by checking which properties are aliases
# In FreeCAD, spreadsheet aliases become properties on the sheet object
try:
    # Method 1: Try getPropertyByName for each potential alias
    for prop_name in sheet.PropertiesList:
        try:
            cell = sheet.getCellFromAlias(prop_name)
            if cell:
                aliases[prop_name] = cell
        except Exception:
            pass
except Exception:
    pass

_result_ = {{
    "spreadsheet": sheet.Name,
    "aliases": aliases,
    "count": len(aliases),
}}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        raise ValueError(result.error_traceback or "Failed to get aliases")

    @mcp.tool()
    async def spreadsheet_clear_cell(
        spreadsheet_name: str,
        cell: str,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Clear a cell in a spreadsheet.

        This removes the cell's content and any alias.

        Args:
            spreadsheet_name: Name of the spreadsheet object.
            cell: Cell address to clear (e.g., "A1").
            doc_name: Document containing the spreadsheet. Uses active if None.

        Returns:
            Dictionary with result:
                - success: Whether the operation succeeded
                - cell: Cell address that was cleared

        Raises:
            ValueError: If no document is found.
            ValueError: If the spreadsheet object is not found.
            ValueError: If clearing the cell fails.

        Example:
            Clear a cell::

                await spreadsheet_clear_cell("Params", "A1")
        """
        bridge = await get_bridge()

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

sheet = doc.getObject({spreadsheet_name!r})
if sheet is None:
    raise ValueError(f"Spreadsheet not found: {spreadsheet_name!r}")

# Wrap in transaction for undo support
doc.openTransaction("Clear Spreadsheet Cell")
try:
    cell = {cell!r}

    # Clear alias first if any
    try:
        sheet.setAlias(cell, "")
    except Exception:
        pass

    # Clear content
    sheet.clear(cell)
    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "success": True,
        "cell": cell,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        raise ValueError(result.error_traceback or "Failed to clear cell")

    @mcp.tool()
    async def spreadsheet_bind_property(
        spreadsheet_name: str,
        alias: str,
        target_object: str,
        target_property: str,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Bind an object property to a spreadsheet cell using expressions.

        This creates a parametric link where the object property is
        driven by the spreadsheet cell value. When the spreadsheet
        value changes, the object updates automatically.

        Args:
            spreadsheet_name: Name of the spreadsheet object.
            alias: Cell alias to bind (the cell must have an alias set).
            target_object: Name of the object to modify.
            target_property: Expression path to bind, such as "Length" or
                "Constraints[8]" for a dimensional sketch constraint.
            doc_name: Document containing the objects. Uses active if None.

        Returns:
            Dictionary with result:
                - success: Whether the operation succeeded
                - expression: The expression that was set
                - target_object: Object that was modified
                - target_property: Property that was bound

        Raises:
            ValueError: If no document is found.
            ValueError: If the spreadsheet object is not found.
            ValueError: If the target object is not found.
            ValueError: If the alias does not exist on the spreadsheet.
            ValueError: If binding the expression fails.

        Example:
            Bind a box's length to a spreadsheet parameter::

                await spreadsheet_set_cell("Params", "A1", 50)
                await spreadsheet_set_alias("Params", "A1", "BoxLength")
                await spreadsheet_bind_property("Params", "BoxLength", "Box", "Length")
                # Now Box.Length = 50 and updates when A1 changes
        """
        bridge = await get_bridge()

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

sheet = doc.getObject({spreadsheet_name!r})
if sheet is None:
    raise ValueError(f"Spreadsheet not found: {spreadsheet_name!r}")

target = doc.getObject({target_object!r})
if target is None:
    raise ValueError(f"Target object not found: {target_object!r}")

alias = {alias!r}
prop = {target_property!r}

# Verify the alias exists
try:
    cell = sheet.getCellFromAlias(alias)
    if not cell:
        raise ValueError(f"Alias not found: {{alias!r}}")
except Exception as e:
    raise ValueError(f"Alias not found: {{alias!r}}") from e

if not prop:
    raise ValueError("target_property must not be empty")

# Wrap in transaction for undo support
doc.openTransaction("Bind Property to Spreadsheet")
try:
    # Create the expression binding
    # Format: ObjectName.Alias
    expression = f"{{sheet.Name}}.{{alias}}"
    target.setExpression(prop, expression)
    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "success": True,
        "expression": expression,
        "target_object": target.Name,
        "target_property": prop,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        raise ValueError(result.error_traceback or "Failed to bind property")

    @mcp.tool()
    async def spreadsheet_get_cell_range(
        spreadsheet_name: str,
        start_cell: str,
        end_cell: str,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Get values from a range of cells in a spreadsheet.

        Args:
            spreadsheet_name: Name of the spreadsheet object.
            start_cell: Starting cell address (e.g., "A1").
            end_cell: Ending cell address (e.g., "C5").
            doc_name: Document containing the spreadsheet. Uses active if None.

        Returns:
            Dictionary with range data:
                - spreadsheet: Spreadsheet name
                - start: Start cell
                - end: End cell
                - cells: Dictionary mapping cell addresses to their values

        Raises:
            ValueError: If no document is found.
            ValueError: If the spreadsheet object is not found.
            ValueError: If start_cell or end_cell has an invalid format.
            ValueError: If retrieving the cell range fails.

        Example:
            Get a range of values::

                result = await spreadsheet_get_cell_range("Params", "A1", "B3")
                for cell, value in result["cells"].items():
                    print(f"{cell}: {value}")
        """
        bridge = await get_bridge()

        code = f"""
doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

sheet = doc.getObject({spreadsheet_name!r})
if sheet is None:
    raise ValueError(f"Spreadsheet not found: {spreadsheet_name!r}")

import re

start_cell = {start_cell!r}.upper()
end_cell = {end_cell!r}.upper()

# Parse cell addresses
def parse_cell(cell_str):
    match = re.match(r'^([A-Z]+)([0-9]+)$', cell_str)
    if not match:
        raise ValueError(f"Invalid cell address: {{cell_str}}")
    col_str, row_str = match.groups()
    # Convert column letters to number (A=0, Z=25, AA=26, etc.)
    # Use 1-based indexing per position, then convert to 0-based
    col = 0
    for c in col_str:
        col = col * 26 + (ord(c) - ord('A') + 1)
    col = col - 1  # Convert to 0-based index
    row = int(row_str)
    return col, row

def col_to_str(col):
    result = ""
    while col >= 0:
        result = chr(ord('A') + col % 26) + result
        col = col // 26 - 1
    return result

start_col, start_row = parse_cell(start_cell)
end_col, end_row = parse_cell(end_cell)

# Ensure start <= end
if start_col > end_col:
    start_col, end_col = end_col, start_col
if start_row > end_row:
    start_row, end_row = end_row, start_row

cells = {{}}
for col in range(start_col, end_col + 1):
    for row in range(start_row, end_row + 1):
        cell_addr = col_to_str(col) + str(row)
        try:
            value = sheet.get(cell_addr)
            cells[cell_addr] = value
        except Exception:
            # Cell might be empty
            cells[cell_addr] = None

_result_ = {{
    "spreadsheet": sheet.Name,
    "start": start_cell,
    "end": end_cell,
    "cells": cells,
}}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        raise ValueError(result.error_traceback or "Failed to get cell range")

    @mcp.tool()
    async def spreadsheet_import_csv(
        spreadsheet_name: str,
        file_path: str,
        delimiter: str = ",",
        start_cell: str = "A1",
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Import data from a CSV file into a spreadsheet.

        Args:
            spreadsheet_name: Name of the spreadsheet object.
            file_path: Path to the CSV file to import.
            delimiter: CSV delimiter character. Defaults to ",".
            start_cell: Cell to start importing at. Defaults to "A1".
            doc_name: Document containing the spreadsheet. Uses active if None.

        Returns:
            Dictionary with import result:
                - success: Whether the operation succeeded
                - rows_imported: Number of rows imported
                - cols_imported: Number of columns imported
                - start_cell: Starting cell

        Raises:
            ValueError: If no document is found.
            ValueError: If the spreadsheet object is not found.
            ValueError: If start_cell has an invalid format.
            FileNotFoundError: If the CSV file does not exist.
            ValueError: If importing the CSV data fails.

        Example:
            Import parameters from CSV::

                await spreadsheet_import_csv("Params", "/path/to/data.csv")
        """
        bridge = await get_bridge()

        code = f"""
import csv
import re

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

sheet = doc.getObject({spreadsheet_name!r})
if sheet is None:
    raise ValueError(f"Spreadsheet not found: {spreadsheet_name!r}")

file_path = {file_path!r}
delimiter = {delimiter!r}
start_cell = {start_cell!r}.upper()

# Parse start cell
match = re.match(r'^([A-Z]+)([0-9]+)$', start_cell)
if not match:
    raise ValueError(f"Invalid cell address: {{start_cell}}")
col_str, row_str = match.groups()
# Convert column letters to number (A=0, Z=25, AA=26, etc.)
# Use 1-based indexing per position, then convert to 0-based
start_col = 0
for c in col_str:
    start_col = start_col * 26 + (ord(c) - ord('A') + 1)
start_col = start_col - 1  # Convert to 0-based index
start_row = int(row_str)

def col_to_str(col):
    result = ""
    while col >= 0:
        result = chr(ord('A') + col % 26) + result
        col = col // 26 - 1
    return result

# Wrap in transaction for undo support
doc.openTransaction("Import CSV to Spreadsheet")
try:
    rows_imported = 0
    max_cols = 0

    with open(file_path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.reader(f, delimiter=delimiter)
        for row_idx, row in enumerate(reader):
            for col_idx, value in enumerate(row):
                cell_addr = col_to_str(start_col + col_idx) + str(start_row + row_idx)
                # Try to convert to number if possible
                try:
                    if '.' in value:
                        value = float(value)
                    else:
                        value = int(value)
                except ValueError:
                    pass  # Keep as string
                sheet.set(cell_addr, str(value))
            rows_imported += 1
            max_cols = max(max_cols, len(row))

    doc.recompute()
    doc.commitTransaction()

    _result_ = {{
        "success": True,
        "rows_imported": rows_imported,
        "cols_imported": max_cols,
        "start_cell": start_cell,
    }}
except Exception:
    doc.abortTransaction()
    raise
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        raise ValueError(result.error_traceback or "Failed to import CSV")

    @mcp.tool()
    async def spreadsheet_export_csv(
        spreadsheet_name: str,
        file_path: str,
        delimiter: str = ",",
        max_row_limit: int = 1000,
        max_col_limit: int = 52,
        doc_name: str | None = None,
    ) -> dict[str, Any]:
        """Export spreadsheet data to a CSV file.

        Args:
            spreadsheet_name: Name of the spreadsheet object.
            file_path: Path to write the CSV file.
            delimiter: CSV delimiter character. Defaults to ",".
            max_row_limit: Maximum rows to scan for data. Defaults to 1000.
            max_col_limit: Maximum columns to scan for data. Defaults to 52 (AZ).
            doc_name: Document containing the spreadsheet. Uses active if None.

        Returns:
            Dictionary with export result:
                - success: Whether the operation succeeded
                - file_path: Path where file was written
                - rows_exported: Number of rows exported
                - cols_exported: Number of columns exported
                - truncated: True if data exists beyond the scan limits

        Raises:
            ValueError: If no document is found.
            ValueError: If the spreadsheet object is not found.
            ValueError: If export fails.

        Example:
            Export spreadsheet to CSV::

                await spreadsheet_export_csv("Params", "/path/to/output.csv")
        """
        bridge = await get_bridge()

        code = f"""
import csv

doc = FreeCAD.ActiveDocument if {doc_name!r} is None else FreeCAD.getDocument({doc_name!r})
if doc is None:
    raise ValueError("No document found")

sheet = doc.getObject({spreadsheet_name!r})
if sheet is None:
    raise ValueError(f"Spreadsheet not found: {spreadsheet_name!r}")

file_path = {file_path!r}
delimiter = {delimiter!r}
max_row_limit = {max_row_limit!r}
max_col_limit = {max_col_limit!r}

def col_to_str(col):
    result = ""
    while col >= 0:
        result = chr(ord('A') + col % 26) + result
        col = col // 26 - 1
    return result

# Get used range - find max row and column with data within limits
max_row = 0
max_col = 0
truncated = False

# Scan within the configured limits
for col in range(max_col_limit):
    for row in range(1, max_row_limit + 1):
        cell_addr = col_to_str(col) + str(row)
        try:
            val = sheet.get(cell_addr)
            if val is not None:
                max_row = max(max_row, row)
                max_col = max(max_col, col)
        except Exception:
            pass

# Check if data exists beyond limits (probe one row/column past)
# Always probe, even if sheet appears empty within scan limits - data may exist beyond

# Check row beyond limit (probe first row past max_row_limit across all columns scanned)
probe_cols = max(max_col + 1, 1)  # At least probe column A
for col in range(probe_cols):
    cell_addr = col_to_str(col) + str(max_row_limit + 1)
    try:
        val = sheet.get(cell_addr)
        if val is not None:
            truncated = True
            break
    except Exception:
        pass

# Check column beyond limit (probe column at max_col_limit across rows)
if not truncated:
    probe_rows = max(max_row, 1)  # At least probe row 1
    for row in range(1, probe_rows + 1):
        cell_addr = col_to_str(max_col_limit) + str(row)
        try:
            val = sheet.get(cell_addr)
            if val is not None:
                truncated = True
                break
        except Exception:
            pass

# Also probe a cell beyond both limits if sheet appears empty
if not truncated and max_row == 0 and max_col == 0:
    # Probe one cell beyond both row and column limits
    cell_addr = col_to_str(max_col_limit) + str(max_row_limit + 1)
    try:
        val = sheet.get(cell_addr)
        if val is not None:
            truncated = True
    except Exception:
        pass

if max_row == 0:
    # Empty spreadsheet (within scan limits)
    _result_ = {{
        "success": True,
        "file_path": file_path,
        "rows_exported": 0,
        "cols_exported": 0,
        "truncated": truncated,
    }}
else:
    with open(file_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter=delimiter)
        for row in range(1, max_row + 1):
            row_data = []
            for col in range(max_col + 1):
                cell_addr = col_to_str(col) + str(row)
                try:
                    val = sheet.get(cell_addr)
                    row_data.append(val if val is not None else "")
                except Exception:
                    row_data.append("")
            writer.writerow(row_data)

    _result_ = {{
        "success": True,
        "file_path": file_path,
        "rows_exported": max_row,
        "cols_exported": max_col + 1,
        "truncated": truncated,
    }}
"""
        result = await bridge.execute_python(code)
        if result.success and result.result:
            return result.result
        raise ValueError(result.error_traceback or "Failed to export CSV")
