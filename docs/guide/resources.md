# MCP Resources

The default parametric profile exposes eleven read-only resources: four core
resources plus seven progressive guide topics. They provide the native
workflow contract and compact runtime context without duplicating all tool
schemas.

## `freecad://parametric-parts/guide`

Returns the Markdown guide used as the MCP server instructions. This resource
serves the same core text the server sends as its MCP instructions, and is
retained as an alias so existing configurations keep working. It covers:

- coordinate frames, Body Origin planes, and named datums;
- native variable sets and expression-bound dimensions;
- declarative sketches, expression batches, and validated native features;
- bounded inspection, validation, and granular repair;
- governing-parameter edits and save/reopen testing;
- STEP export and deterministic visual review.

## `freecad://capabilities`

Returns the exact default interface as JSON:

```json
{
  "profile": "parametric",
  "tool_count": 55,
  "tools": ["add_sketch_arc", "add_sketch_circle", "..."],
  "prompts": ["design_parametric_part", "review_parametric_part"],
  "modeling_contract": {
    "authoritative_artifact": "native FCStd PartDesign feature tree",
    "construction": "task-oriented MCP sketch and feature tools",
    "python_execution_exposed": false
  }
}
```

Its tool names come from the same allowlist used by registration tests.

## `freecad://status`

Returns bridge mode, connection state, FreeCAD version, GUI availability,
latency, and any connection error. Read it before modeling. Screenshots require
`gui_available=true`; native modeling, persistence, and export work headlessly.

## `freecad://active-document`

Returns the active document's internal name, label, path, object names, modified
state, and active object. Use `query_objects`, `inspect_object`,
`get_sketch_info`, and `validate_document` for detailed evidence.

## Progressive Guide Topics

Seven further resources each serve one topic document from the guide's
"Progressive Guide Topics" list. Fetch a topic when its trigger applies rather
than loading the whole guide up front.

- `freecad://guide/brief` — turning prose, an image, or a drawing into a brief.
- `freecad://guide/visual-evidence` — the capture protocol. Read before
  capturing evidence.
- `freecad://guide/parameters` — variable sets, units, and expression binding.
- `freecad://guide/features` — feature order, datums, overlap, and
  through-cuts.
- `freecad://guide/variants` — isolated one-edit variant transactions.
- `freecad://guide/repair` — `VALIDATION_FAILED`, `STALE_REVISION`, and undo.
- `freecad://guide/delivery` — manifests, READMEs, and re-import evidence.

## Resources And Tools

| Property     | Resources                    | Tools                            |
| ------------ | ---------------------------- | -------------------------------- |
| Side effects | None                         | May inspect or modify FreeCAD    |
| Purpose      | Guidance and current context | Build, validate, persist, export |
| Examples     | `freecad://capabilities`     | `create_constrained_sketch`      |

## Next Steps

- [Tools Reference](tools.md)
- [Detailed Signatures](../MCP_TOOLS_REFERENCE.md)
- [Connection Modes](connection-modes.md)
