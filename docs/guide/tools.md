# Tools Reference

The default `parametric` profile exposes 54 tools for building editable native
FreeCAD parts through task-oriented MCP commands. It retains the complete core
PartDesign workflow without exposing arbitrary Python execution or the full
historical catalog.

Read `freecad://parametric-parts/guide` before modeling. The same guidance is
included in the MCP server instructions and the `design_parametric_part` prompt.

## Workflow

```text
plan parameters, Origin planes, and datums
-> create document, Body, and native variable set
-> create a constrained sketch from symbolic geometry and constraint IDs
-> verify FullyConstrained
-> bind related expressions in one transaction
-> pad, pocket, revolve, groove, or pattern
-> use returned validation and bounded object queries
-> edit governing variables and verify their response
-> save, close, reopen, edit, and validate
-> export STEP and inspect deterministic renders
```

The native FCStd feature tree is authoritative. The default profile does not
expose `execute_python`, `safe_execute`, macros, generic Part primitives, or a
saved-script runner.

## Tool Catalog

### Connection And Documents

- **Connection**: `get_connection_status`, `get_freecad_version`,
  `get_console_output`
- **Lifecycle**: `list_documents`, `get_active_document`, `create_document`
- **Persistence**: `save_document`, `close_document`, `open_document`,
  `recompute_document`

### Variables And Inspection

- **Variables**: `define_variables`, `get_variables`
- **Expressions**: `bind_expressions`, `set_expression`
- **Objects**: `query_objects`, `list_objects`, `inspect_object`, `edit_object`

`define_variables` creates or updates a batch of typed properties in a native
`App::VarSet`. `bind_expressions` applies related feature and sketch bindings in
one transaction. Paths include ordinary properties such as `Length`, attachment
properties such as `AttachmentOffset.Base.z`, and sketch dimensions such as
`Constraints[8]`. `set_expression` remains available for local repair.

`query_objects` filters in FreeCAD, sorts deterministically, and returns at most
the requested page size. Use summary mode by default and detailed mode only for
a small set. Do not repeatedly call `list_objects` to inspect unchanged state.

### Sketches

- **Setup**: `create_partdesign_body`, `create_constrained_sketch`,
  `create_sketch`, `create_datum_plane`
- **Geometry**: `add_sketch_line`, `add_sketch_rectangle`,
  `add_sketch_circle`, `add_sketch_arc`, `add_sketch_point`,
  `toggle_construction`
- **Constraints**: `add_sketch_constraint`, `get_sketch_info`
- **Repair**: `delete_sketch_geometry`, `delete_sketch_constraint`

`create_constrained_sketch` creates supported geometry, geometric constraints,
dimensional constraints, and expressions in one transaction. It returns maps
from request-local symbolic IDs to native indices and can require closed or
fully constrained output. `create_sketch` and individual geometry tools remain
available for repair.

Both sketch creation tools accept Body Origin planes (`XY_Plane`, `XZ_Plane`,
and `YZ_Plane`), named `PartDesign::Plane` datums, and explicit Body face names.
Prefer Origin planes and datums because generated face names are sensitive to
upstream topology changes.

Use `add_sketch_constraint` and `get_sketch_info` only when repairing a rejected
declarative sketch. Every driving sketch should report `FullyConstrained` before
its feature is created.

### Native Features

| Purpose       | Tools                                                              |
| ------------- | ------------------------------------------------------------------ |
| Additive      | `pad_sketch`, `revolution_sketch`, `loft_sketches`                 |
| Subtractive   | `pocket_sketch`, `groove_sketch`, `create_hole`                    |
| Pattern       | `linear_pattern`, `polar_pattern`, `mirrored_feature`              |
| Dress-up      | `fillet_edges`, `chamfer_edges`                                    |
| Recovery      | `undo`, `redo`                                                     |

Create primary form first, cuts and patterns second, and fillets or chamfers
last. Give intended unions real overlap and extend through-cut profiles beyond
the target material. These feature mutations recompute and reject null, invalid,
or multi-solid PartDesign Body results before committing.

### Validation, Export, And Review

| Purpose       | Tools                                                              |
| ------------- | ------------------------------------------------------------------ |
| Validation    | `validate_object`, `validate_document`                             |
| Interchange   | `export_step`, `export_stl`, `import_step`                         |
| Visual review | `get_screenshot`, `set_view_angle`, `fit_all`                      |
| Visibility    | `set_object_visibility`                                            |

Screenshots require GUI mode. Inspect the actual image, but do not use render
pixels as proof of dimensions, solid connectivity, or editability.

## Parametric Edit Gate

For each governing edit:

1. Change only the documented governing variable with `define_variables`; it
   recomputes without reconstructing features.
2. Inspect the changed feature and protected controls with `query_objects`.
3. Do not issue a separate recompute unless a repair tool explicitly requires it.
4. Require a valid final Body Tip and the intended solid count.
5. Save, close, reopen, and repeat a governing-variable edit.

Export only the validated final Body or Tip. Re-import STEP in a clean document
when BREP interchange is an acceptance requirement.

## Full Profile

The full profile exposes 158 tools: the historical interface plus native
variable tools:

```bash
FREECAD_TOOL_PROFILE=full freecad-mcp
```

The full profile restores arbitrary Python execution, Spreadsheets, macros,
generic Part and Draft operations, extra formats, and less common PartDesign
helpers.

## Next Steps

- [Detailed Signatures](../MCP_TOOLS_REFERENCE.md)
- [MCP Resources](resources.md)
- [Connection Modes](connection-modes.md)
