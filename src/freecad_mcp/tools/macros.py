"""Macro management tools for FreeCAD Robust MCP Server.

This module provides tools for managing FreeCAD macros:
listing, running, creating, and editing macros.

Based on learnings from ATOI-Ming/FreeCAD-MCP which has a
macro-centric workflow with templates and validation.
"""

from collections.abc import Awaitable, Callable
from typing import Any


def register_macro_tools(mcp: Any, get_bridge: Callable[[], Awaitable[Any]]) -> None:
    """Register macro-related tools with the Robust MCP Server.

    Args:
        mcp: The FastMCP (Robust MCP Server) instance.
        get_bridge: Async function to get the active bridge.
    """

    @mcp.tool()
    async def list_macros() -> list[dict[str, Any]]:
        """List all available FreeCAD macros.

        Returns:
            List of dictionaries, each containing:
                - name: Macro name (without extension)
                - path: Full path to macro file
                - description: Macro description from comments
                - is_system: Whether it's a system macro
        """
        bridge = await get_bridge()
        macros = await bridge.get_macros()
        return [
            {
                "name": macro.name,
                "path": macro.path,
                "description": macro.description,
                "is_system": macro.is_system,
            }
            for macro in macros
        ]

    @mcp.tool()
    async def run_macro(
        macro_name: str,
        args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run a FreeCAD macro by name.

        Args:
            macro_name: Name of the macro to run (without .FCMacro extension).
            args: Optional dictionary of arguments to pass to the macro.
                  These will be set as variables before execution.

        Returns:
            Dictionary with execution result:
                - success: Whether macro executed successfully
                - stdout: Captured standard output
                - stderr: Captured standard error
                - execution_time_ms: Execution time in milliseconds
                - error_type: Error type if failed
                - error_traceback: Full traceback if failed
        """
        bridge = await get_bridge()
        result = await bridge.run_macro(macro_name, args)
        return {
            "success": result.success,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "execution_time_ms": result.execution_time_ms,
            "error_type": result.error_type,
            "error_traceback": result.error_traceback,
        }

    @mcp.tool()
    async def create_macro(
        name: str,
        code: str,
        description: str = "",
    ) -> dict[str, Any]:
        """Create a new FreeCAD macro.

        The macro will be created in the user's macro directory with
        standard FreeCAD imports automatically added.

        Args:
            name: Macro name (without .FCMacro extension).
            code: Python code for the macro body.
            description: Optional description for the macro.

        Returns:
            Dictionary with created macro information:
                - name: Macro name
                - path: Full path to created macro file
                - description: Macro description
        """
        bridge = await get_bridge()
        macro = await bridge.create_macro(name, code, description)
        return {
            "name": macro.name,
            "path": macro.path,
            "description": macro.description,
        }

    @mcp.tool()
    async def read_macro(macro_name: str) -> dict[str, Any]:
        """Read the contents of a FreeCAD macro.

        Args:
            macro_name: Name of the macro to read (without .FCMacro extension).

        Returns:
            Dictionary with macro contents:
                - name: Macro name
                - code: Full macro code
                - path: Path to macro file
        """
        bridge = await get_bridge()

        code = f"""
import os

# Find macro file
macro_name = {macro_name!r}
macro_file = None

user_path = FreeCAD.getUserMacroDir(True)
user_macro = os.path.join(user_path, macro_name + ".FCMacro")
if os.path.exists(user_macro):
    macro_file = user_macro

if not macro_file:
    system_path = FreeCAD.getResourceDir() + "Macro"
    system_macro = os.path.join(system_path, macro_name + ".FCMacro")
    if os.path.exists(system_macro):
        macro_file = system_macro

if not macro_file:
    raise FileNotFoundError(f"Macro not found: {{macro_name}}")

with open(macro_file, "r") as f:
    macro_code = f.read()

_result_ = {{
    "name": macro_name,
    "code": macro_code,
    "path": macro_file,
}}
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Read macro failed")

    @mcp.tool()
    async def delete_macro(macro_name: str) -> dict[str, Any]:
        """Delete a user macro.

        Note: Only user macros can be deleted. System macros are protected.

        Args:
            macro_name: Name of the macro to delete (without .FCMacro extension).

        Returns:
            Dictionary with delete result:
                - success: Whether deletion was successful
                - path: Path of deleted macro
        """
        bridge = await get_bridge()

        code = f"""
import os

macro_name = {macro_name!r}
user_path = FreeCAD.getUserMacroDir(True)
macro_file = os.path.join(user_path, macro_name + ".FCMacro")

if not os.path.exists(macro_file):
    raise FileNotFoundError(f"User macro not found: {{macro_name}}")

os.remove(macro_file)

_result_ = {{
    "success": True,
    "path": macro_file,
}}
"""
        result = await bridge.execute_python(code, transaction=None)
        if result.success:
            return result.result
        raise ValueError(result.error_traceback or "Delete macro failed")

    @mcp.tool()
    async def create_macro_from_template(
        name: str,
        template: str = "basic",
        description: str = "",
    ) -> dict[str, Any]:
        """Create a new macro from a predefined template.

        Available templates provide common starting points for FreeCAD macros.

        Args:
            name: Macro name (without .FCMacro extension).
            template: Template name. Options:
                - "basic" - Basic template with imports
                - "part" - Part workbench operations template
                - "sketch" - Sketcher operations template
                - "gui" - GUI/dialog template
                - "selection" - Selection handling template
            description: Optional description for the macro.

        Returns:
            Dictionary with created macro information:
                - name: Macro name
                - path: Full path to created macro file
                - template: Template used
        """
        templates = {
            "basic": """
# Your macro code goes here
doc = FreeCAD.ActiveDocument
if doc is None:
    doc = FreeCAD.newDocument("MacroDoc")

# Add your operations here
print("Macro executed successfully!")
""",
            "part": """
import Part

doc = FreeCAD.ActiveDocument
if doc is None:
    doc = FreeCAD.newDocument("MacroDoc")

# Create a box as example
box = doc.addObject("Part::Box", "MyBox")
box.Length = 10
box.Width = 20
box.Height = 30

doc.recompute()
print(f"Created box with volume: {box.Shape.Volume}")
""",
            "sketch": """
import Part
import Sketcher

doc = FreeCAD.ActiveDocument
if doc is None:
    doc = FreeCAD.newDocument("MacroDoc")

# Create a sketch
sketch = doc.addObject("Sketcher::SketchObject", "MySketch")

# Add a rectangle
sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(10, 0, 0)), False)
sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(10, 0, 0), FreeCAD.Vector(10, 10, 0)), False)
sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(10, 10, 0), FreeCAD.Vector(0, 10, 0)), False)
sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(0, 10, 0), FreeCAD.Vector(0, 0, 0)), False)

doc.recompute()
print("Created sketch with rectangle")
""",
            "gui": """
from PySide2 import QtWidgets

class MacroDialog(QtWidgets.QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Macro Dialog")
        self.setup_ui()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout()

        self.label = QtWidgets.QLabel("Enter value:")
        layout.addWidget(self.label)

        self.input = QtWidgets.QLineEdit()
        layout.addWidget(self.input)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

# Show dialog
dialog = MacroDialog()
if dialog.exec_():
    value = dialog.input.text()
    print(f"User entered: {value}")
""",
            "selection": """
# Get current selection
sel = FreeCADGui.Selection.getSelection()

if not sel:
    print("Nothing selected!")
else:
    for obj in sel:
        print(f"Selected: {obj.Name} ({obj.TypeId})")

        # Access shape if available
        if hasattr(obj, "Shape"):
            shape = obj.Shape
            print(f"  - Volume: {shape.Volume}")
            print(f"  - Area: {shape.Area}")
            print(f"  - Faces: {len(shape.Faces)}")
            print(f"  - Edges: {len(shape.Edges)}")
""",
        }

        if template not in templates:
            raise ValueError(
                f"Unknown template: {template}. Available: {list(templates.keys())}"
            )

        bridge = await get_bridge()
        macro = await bridge.create_macro(name, templates[template], description)
        return {
            "name": macro.name,
            "path": macro.path,
            "template": template,
        }
