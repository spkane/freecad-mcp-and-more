"""Code generator for support-normal camera captures.

The fixed eight-angle screenshot (`ScreenshotResult` / `ViewAngle` in
`base.py`) can only look at a model from a handful of global directions. It
cannot aim the camera along a specific feature's own normal, so a defect
oriented away from all eight fixed angles never shows up in a screenshot. A
malformed window opening once passed every check for exactly this reason.

`build_feature_view_code` generates the FreeCAD-side Python source that
resolves a named object's `Placement.Rotation` applied to `Vector(0, 0, 1)`
and points the camera along (or against) that normal. The generated code is
handed to a bridge's `execute_python(code, transaction=None)` -- this module
never talks to FreeCAD directly, it only produces the source string that
will run inside FreeCAD's own interpreter.

The generated code always, in this order:

1. Checks `FreeCAD.GuiUp` and returns a structured error if the GUI is not
   available, before touching the view.
2. Resolves the target document.
3. Resolves `normal_source` to an object and reads its
   `Placement.Rotation` applied to `Vector(0, 0, 1)`, returning a structured
   error when the object is missing or has no `Placement`.
4. Resolves every `focus` name against the document, returning a structured
   error naming the ones that do not exist. `Gui.Selection.addSelection`
   ignores an unknown name silently, so without this check a typo produced a
   successful capture of nothing.
5. Saves the current camera and the current `Visibility` of every object it
   is about to hide.
6. Optionally hides datum planes, origins, and construction sketches.
7. Points the camera along the resolved (optionally negated) normal and
   frames either the whole document or a focused selection.
8. Saves the capture to a temporary PNG and base64-encodes it.
9. Restores visibility and the camera in a `finally:` block, so a capture
   that raises partway through still leaves the operator's FreeCAD exactly
   as it found it.

On success the result carries the evidence metadata a model needs in order
to state what it actually looked at: the sign-resolved `camera_direction`,
the `normal_source`, the resolved `placement`, the `focus` names, the
`hidden_objects`, and the echoed `padding`.
"""


def build_feature_view_code(
    normal_source: str,
    side: str,
    focus: list[str] | None,
    padding: float,
    hide_construction: bool,
    width: int,
    height: int,
    doc_name: str | None,
) -> str:
    """Generate FreeCAD source that aims the camera along a support's normal.

    Args:
        normal_source: Name of the object whose `Placement.Rotation` applied
            to `Vector(0, 0, 1)` supplies the camera's normal direction.
        side: `"front"` to view from the normal's positive side (camera looks
            along the negated normal), or `"back"` to view from the opposite
            side (camera looks along the normal itself).
        focus: Object names to fit the view to via `Gui.Selection` plus the
            `ViewSelection` view command, or `None` to fit the whole document
            with `view.fitAll()`. Every name is resolved against the document
            first; an unresolvable name is a structured error, not a picture
            of nothing.
        padding: Fractional margin requested around the framed geometry.
            Reserved: framing itself relies on FreeCAD's own fit margins.
            The value is echoed back in the result so the caller can see
            what it asked for.
        hide_construction: Whether to hide datum planes, origins, and
            construction sketches for the duration of the capture.
        width: Image width in pixels.
        height: Image height in pixels.
        doc_name: Document name, or `None` to use the active document.

    Returns:
        A string of Python source to run inside FreeCAD via
        `execute_python(code, transaction=None)`. It never raises on its own;
        every failure path assigns a structured
        `{"success": False, "error": ...}` to `_result_` instead.
    """
    error_message = f"{normal_source} has no resolvable support placement"
    focus_list = list(focus) if focus else []

    return f"""
import base64
import math
import tempfile
import os


def _is_construction_helper(obj):
    type_id = getattr(obj, "TypeId", "")
    if type_id == "App::Origin":
        return True
    leaf = type_id.split("::")[-1]
    if type_id.startswith("PartDesign::") and leaf in (
        "Point",
        "Line",
        "Plane",
        "CoordinateSystem",
    ):
        return True
    if type_id.startswith("App::") and leaf in ("Point", "Line", "Plane"):
        return True
    return type_id == "Sketcher::SketchObject"


# Bind the document name to a variable first. Interpolating it straight into
# an `is None` comparison would emit `if 'Target' is None`, which is a
# SyntaxWarning in the operator's FreeCAD console and a SyntaxError under
# `-W error`.
_doc_name = {doc_name!r}

if not FreeCAD.GuiUp:
    _result_ = {{"success": False, "error": "GUI not available"}}
else:
    doc = FreeCAD.ActiveDocument if _doc_name is None else FreeCAD.getDocument(_doc_name)
    if doc is None:
        _result_ = {{"success": False, "error": "No document found"}}
    else:
        _normal_source = {normal_source!r}
        _side = {side!r}
        _padding = {padding!r}
        _focus = {focus_list!r}
        _hide_construction = {hide_construction!r}

        _obj = doc.getObject(_normal_source)

        # Gui.Selection.addSelection ignores a name that does not exist, so
        # a typo would otherwise fit nothing and report success with a
        # picture of the whole model -- or of nothing at all.
        _missing_focus = [_n for _n in _focus if doc.getObject(_n) is None]

        if _obj is None or not hasattr(_obj, "Placement"):
            _result_ = {{"success": False, "error": {error_message!r}}}
        elif _missing_focus:
            _result_ = {{
                "success": False,
                "error": "focus objects not found: " + ", ".join(_missing_focus),
            }}
        else:
            # Act on the document that was asked for, not whichever tab the
            # GUI happens to be showing. Without this, a named document that
            # is not already active targets a different model entirely.
            _previous_doc = (
                FreeCADGui.ActiveDocument.Document.Name
                if FreeCADGui.ActiveDocument
                else None
            )

            # Defaults for the finally block below. Every mutation this
            # code can perform -- switching the active document, hiding
            # objects, moving the camera -- happens only after this point,
            # and the finally block below covers all of it unconditionally,
            # including the early "no active view" return and any
            # exception raised while framing or saving the image. A
            # capture that fails partway through must never leave the
            # operator's FreeCAD with a hidden datum plane, a moved
            # camera, or the wrong document active.
            view = None
            _saved_camera = None
            _saved_visibility = {{}}
            _hidden_objects = []

            def _restore_visibility():
                for _name, _visible in _saved_visibility.items():
                    try:
                        _o = doc.getObject(_name)
                        if _o is not None and getattr(_o, "ViewObject", None):
                            _o.ViewObject.Visibility = _visible
                    except Exception:
                        # One object failing to restore must not stop the
                        # rest of the objects, or the camera, from being
                        # restored.
                        pass

            try:
                if _previous_doc != doc.Name:
                    FreeCADGui.setActiveDocument(doc.Name)
                    FreeCADGui.updateGui()

                view = FreeCADGui.ActiveDocument.ActiveView
                if view is None:
                    _result_ = {{"success": False, "error": "No active view"}}
                else:
                    _placement = _obj.Placement
                    _normal = _placement.Rotation.multVec(
                        FreeCAD.Vector(0, 0, 1)
                    )
                    if _side == "back":
                        _direction = _normal
                    else:
                        _direction = FreeCAD.Vector(
                            -_normal.x, -_normal.y, -_normal.z
                        )

                    # Save the camera before anything else is changed.
                    _saved_camera = view.getCamera()

                    if _hide_construction:
                        for _o in doc.Objects:
                            if _is_construction_helper(_o) and getattr(
                                _o, "ViewObject", None
                            ):
                                _saved_visibility[_o.Name] = (
                                    _o.ViewObject.Visibility
                                )
                                _o.ViewObject.Visibility = False
                                _hidden_objects.append(_o.Name)

                    FreeCADGui.updateGui()
                    view.setViewDirection(_direction)

                    if _focus:
                        Gui.Selection.clearSelection()
                        for _name in _focus:
                            Gui.Selection.addSelection(doc.Name, _name)
                        # View3DInventorPy has no fitSelection(); fitting a
                        # selection is the Std_ViewFitSelection command, reached
                        # through the active view's message channel.
                        if hasattr(view, "fitSelection"):
                            view.fitSelection()
                        else:
                            FreeCADGui.SendMsgToActiveView("ViewSelection")
                        Gui.Selection.clearSelection()
                    else:
                        view.fitAll()
                    FreeCADGui.updateGui()

                    with tempfile.NamedTemporaryFile(
                        suffix=".png", delete=False
                    ) as _f:
                        temp_path = _f.name

                    view.saveImage(temp_path, {width}, {height}, "Current")

                    with open(temp_path, "rb") as _f:
                        image_data = base64.b64encode(_f.read()).decode("utf-8")
                    os.unlink(temp_path)

                    _result_ = {{
                        "success": True,
                        "data": image_data,
                        "format": "png",
                        "width": {width},
                        "height": {height},
                        "camera_direction": [
                            _direction.x,
                            _direction.y,
                            _direction.z,
                        ],
                        "normal_source": _normal_source,
                        "side": _side,
                        "padding": _padding,
                        "placement": {{
                            "position": [
                                _placement.Base.x,
                                _placement.Base.y,
                                _placement.Base.z,
                            ],
                            "axis": [
                                _placement.Rotation.Axis.x,
                                _placement.Rotation.Axis.y,
                                _placement.Rotation.Axis.z,
                            ],
                            "angle_deg": math.degrees(_placement.Rotation.Angle),
                            "normal": [_normal.x, _normal.y, _normal.z],
                        }},
                        "focus": _focus if _focus else None,
                        "hidden_objects": _hidden_objects,
                    }}
            finally:
                # Restore visibility and camera even if the capture
                # raised, or returned early, so a failed capture never
                # leaves the operator's FreeCAD with hidden datum planes
                # or a moved camera.
                _restore_visibility()
                if view is not None and _saved_camera is not None:
                    view.setCamera(_saved_camera)
                    FreeCADGui.updateGui()

                # Put the operator's document back; a read-only capture
                # must not switch tabs, even when it activated the
                # document and then failed before producing an image.
                if _previous_doc is not None and _previous_doc != doc.Name:
                    FreeCADGui.setActiveDocument(_previous_doc)
                    FreeCADGui.updateGui()
"""
