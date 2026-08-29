# MCP CAD Tool Interface Research

Research date: 2026-08-29

This note evaluates an MCP interface for an autonomous FreeCAD agent. Sources
are limited to protocol specifications, official SDK and provider guidance,
FreeCAD documentation, and direct observations of this repository.

The terms **MUST**, **SHOULD**, and **MAY** are normative only where a paragraph
explicitly attributes them to the MCP specification. Recommendations labelled
**CAD inference** apply those sources to this server; they are not MCP
requirements.

## Executive Summary

1. Add a combined read-only object query only if it remains one coherent
   retrieval operation. A `query_objects` contract can cover list, search, and
   detailed lookup through filters and a bounded `detail` level. It should not
   absorb sketch solving, validation, mutation, export, or arbitrary Python.
2. Return object and sub-element references immediately after reads and writes,
   but do not call `Face3` or a server-generated token a stable topology ID.
   Scope every topology reference to a document revision and include geometric
   descriptors so an agent can explain and re-query a stale selection.
3. Keep screenshots off by default. When requested, return an MCP image content
   block or a resource link plus concise structured metadata, rather than
   putting base64 image data inside a general JSON result. A capture included in
   a read-only query must not leave the camera or visibility state changed.
4. Add an atomic declarative constrained-sketch tool as a high-level operation,
   while retaining focused geometry and constraint tools for incremental repair.
   Use request-local symbolic entity IDs, typed constraint variants, explicit
   units, one transaction, and a result that maps symbolic IDs to native indices
   and reports solver state.
5. Define precise result models and `outputSchema` values before adding more
   tools. Return concise text for the model and `structuredContent` for reliable
   follow-up calls. Do not represent a failed tool execution as a successful
   result containing `success: false`.
6. Treat active-document defaults, generated face names, and retries of create
   operations as explicit state hazards. Mutations should accept an explicit
   document reference and expected revision, and non-idempotent creates should
   support deduplication only if retry safety is a real requirement.
7. Tool count alone is not the target. The target is a small initially exposed
   surface of distinct, high-value workflows, with progressive discovery for
   less common tools and bounded, filterable results.

## Evidence Boundaries

**MCP requirements** in this note come from the stable `2026-07-28` protocol
revision. That revision removes protocol-level sessions, requires protocol and
capability metadata on each request, and uses explicit server-minted handles for
cross-call state. It also deprecates Roots, Sampling, and Logging. See the
[2026-07-28 changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog)
and [stateful tool guidance](https://modelcontextprotocol.io/specification/2026-07-28/server/tools#stateful-tools).

**Provider guidance** from Anthropic and OpenAI is non-normative. It is useful
evidence about model behavior, context cost, and evaluation, but it cannot
override the MCP wire contract. Some provider pages also retain examples from
older protocol revisions.

**CAD inference** is based on FreeCAD's object model, sketch scripting API, and
topological naming behavior. It should be validated with this project's target
clients and models before becoming a public contract.

## Current Repository Baseline

At the start of this research, the default `parametric` profile exposed 51 tools
and the full profile exposed 155, according to the
[tool reference](../MCP_TOOLS_REFERENCE.md). The focused surface already returns
native sketch geometry indices after mutations and exposes dedicated sketch,
inspection, validation, screenshot, resource, and prompt operations.

The repository currently declares `mcp>=1.25.0,<2` and locks `mcp==1.25.0` in
[`uv.lock`](https://github.com/spkane/freecad-addon-robust-mcp-server/blob/main/uv.lock).
Version 1.25.0 predates the 2026 protocol revision;
the official Python SDK documents a breaking
[v1 to v2 migration](https://py.sdk.modelcontextprotocol.io/v2/migration/) and
separate legacy and 2026-era negotiation. Therefore:

1. The interface recommendations below can guide schemas and behavior now.
2. Wire-level requirements unique to `2026-07-28` are a migration target, not a
   claim about the current server.
3. SDK migration and client compatibility should be planned and tested
   separately from redesigning the CAD tool surface.

Most current tools use `dict[str, Any]` results and bare `@mcp.tool()`
registration. That makes their output contracts and behavioral annotations less
precise than they could be. `get_screenshot` currently returns base64 data in a
dictionary and returns `success: false` for at least one input error. These are
useful migration targets, not reasons to redesign every tool at once. See
[`objects.py`](https://github.com/spkane/freecad-addon-robust-mcp-server/blob/main/src/freecad_mcp/tools/objects.py),
[`partdesign.py`](https://github.com/spkane/freecad-addon-robust-mcp-server/blob/main/src/freecad_mcp/tools/partdesign.py),
and [`view.py`](https://github.com/spkane/freecad-addon-robust-mcp-server/blob/main/src/freecad_mcp/tools/view.py).

## Protocol Baseline

### Primitive Roles

**MCP requirement:** tools are model-controlled, resources are
application-driven, and prompts are user-controlled. The protocol does not force
a particular UI, but it does assign a different expected interaction model to
each primitive. See the MCP pages for
[tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools),
[resources](https://modelcontextprotocol.io/specification/2026-07-28/server/resources),
and [prompts](https://modelcontextprotocol.io/specification/2026-07-28/server/prompts).

**CAD inference:** an operation the model must choose while constructing a part
belongs in a tool. A large model snapshot, generated report, or reusable image is
a better resource. A user-invoked design or review workflow is a prompt. Safety
rules required on every mutation must live in server behavior and tool metadata,
not only in a prompt the user may never select.

### Tool Definitions and Results

**MCP requirement:** every tool has an object `inputSchema`. `outputSchema` is
optional, but when present the server MUST return `structuredContent` that
conforms to it and clients SHOULD validate it. For compatibility, structured
results SHOULD also be serialized in a text content block. Tool results may
also contain text, image, audio, resource-link, or embedded-resource blocks.

The official Python SDK v2 derives an output schema from a return type, emits
both text and structured channels, and validates the returned value. The
official TypeScript SDK similarly validates `structuredContent` against
`outputSchema`. See the SDK guidance for
[Python structured output](https://py.sdk.modelcontextprotocol.io/v2/servers/structured-output/)
and [TypeScript tools](https://ts.sdk.modelcontextprotocol.io/v2/servers/tools).

**CAD inference:** define named result models for stable contracts instead of
`dict[str, Any]`. A model-facing text block should summarize what changed or was
found. Structured content should carry exact references, dimensions, solver
state, pagination, and warnings for subsequent calls.

### Human Control

**MCP requirement:** the tools specification says there SHOULD always be a human
in the loop who can deny invocations, and clients SHOULD show exposed tools,
invocations, and confirmation prompts. Servers still MUST validate inputs,
enforce access controls, rate-limit calls, and sanitize outputs.

**CAD inference:** an autonomous host can grant standing approval to bounded
read-only or additive operations, but destructive edits, filesystem writes, and
external actions need an explicit policy. Tool annotations can inform that
policy; they cannot enforce it.

## Tool Granularity

Anthropic recommends a few thoughtful tools for high-impact workflows rather
than wrappers around every underlying API endpoint. It also reports that a tool
may appropriately consolidate several commonly chained operations when the
combined operation has one clear purpose. See
[Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents).

OpenAI similarly says not to mirror an internal API, to group operations that
form one coherent action, and to split operations when permissions, safety, or
confirmation differ. Its MCP-specific guidance prefers focused operations over
one tool with unrelated modes. See
[Define tools](https://developers.openai.com/plugins/plan/tools) and
[Build an MCP server](https://developers.openai.com/plugins/build/mcp-server).

The guidance is consistent when the boundary is the user goal rather than the
underlying library call:

1. Combine steps that are almost always chained and share one safety boundary.
2. Keep reads separate from writes.
3. Keep additive creation separate from overwrite, replacement, and deletion.
4. Do not create a universal `execute_cad` tool merely to reduce tool count.
5. Keep specialist inspection tools where their output and terminology differ
   materially from generic object lookup.

**CAD inference:** a generic object query and an atomic sketch build both pass
this test. A query is one read-only retrieval goal. A declarative sketch build
is one transaction with one solver outcome. Filleting, exporting, replacing a
sketch, and taking arbitrary screenshots do not belong in either contract.

## Input Contract Design

Tool names and descriptions are part of the model's decision surface. Use an
action-oriented name, state when to use the tool, distinguish it from nearby
tools, and state prerequisites or limits. Anthropic recommends namespacing and
explicit parameter descriptions; OpenAI recommends domain-action names, enums,
examples for recurring failures, and schemas that make invalid states
unrepresentable.

For this server:

1. Use enums for view names, detail levels, geometry kinds, constraint kinds,
   point roles, and conflict behavior. A docstring list attached to a plain
   `str` does not constrain a generated call.
2. Use discriminated objects instead of groups of optional fields whose valid
   combinations must be guessed. Test `oneOf` and union handling in every target
   host even though MCP `2026-07-28` permits full JSON Schema 2020-12.
3. Reject unknown fields where the SDK and clients support it. Bound array
   lengths, image dimensions, query limits, and numeric ranges.
4. Express units in the schema. Coordinates may share an explicit request unit;
   dimensions and expressions should use values such as `80 mm` and
   `Variables.width`, not unexplained scalars.
5. Require explicit document identity on mutation after document discovery or
   creation. `doc_name=None` and "active document" are convenient for a human
   session but are implicit mutable state for an autonomous caller.
6. Accept an expected document revision on mutation so stale plans fail before
   changing the model.

Examples should be few and realistic. Anthropic reports improved complex-
parameter accuracy from tool-use examples, but examples add permanent schema
tokens. Add them only where a constraint shape, identifier convention, or unit
rule remains ambiguous after schema validation.

## Result Contract Design

A useful successful result has three layers:

1. A short text statement for the model, such as "Created BaseSketch with four
   entities; solver is valid with 3 remaining degrees of freedom."
2. Structured content that follows a published output schema.
3. Optional image or resource-link content for evidence too large or unsuitable
   for the structured object.

Use a common structured vocabulary across tools:

- `document_ref`: explicit document name or opaque handle and current revision.
- `object_ref`: internal object `Name`, display `Label`, type, and document.
- `operation_id`: server-generated identifier for a committed mutation.
- `warnings`: successful but important conditions, such as an under-constrained
  sketch when that condition was permitted.
- `next_cursor` and `truncated`: bounded result continuation.
- `topology_refs`: revision-scoped sub-element references.

Do not add `success: true` to every successful result. MCP already distinguishes
a normal result from a tool execution error. Reserve warnings for successful
outcomes and use the protocol's error signal for failures.

Anthropic found that concise and detailed response modes can substantially
change token use, and recommends high-signal fields, meaningful names, filters,
pagination, and truncation. A small fixed `detail` enum is easier for a model
and output schema than an unrestricted field-selection language. Return both
semantic names and technical identifiers when later tools require the latter.

## Errors and Recovery

**MCP requirement:** malformed requests, unknown tools, and server-level failures
use JSON-RPC errors. Failures that a model can act on, including input validation,
upstream API failures, and domain logic failures, are tool results with
`isError: true`. Clients SHOULD expose tool execution errors to the model so it
can correct the call. The official Python SDK expresses this distinction as
`ToolError` versus `MCPError`; unexpected exceptions are logged while their
internal details are withheld. See
[MCP tool error handling](https://modelcontextprotocol.io/specification/2026-07-28/server/tools#error-handling)
and [Python SDK error handling](https://py.sdk.modelcontextprotocol.io/v2/servers/handling-errors/).

**CAD inference:** expected failures should identify the failed semantic input
and one recovery action without exposing a FreeCAD traceback. Useful stable
error categories include:

- `DOCUMENT_NOT_FOUND`: list or open documents, then retry explicitly.
- `OBJECT_NOT_FOUND`: query matching names and types.
- `STALE_REVISION`: re-query the document before mutation.
- `STALE_TOPOLOGY_REF`: re-inspect candidate faces or edges.
- `INVALID_GEOMETRY_REF`: report the symbolic entity and valid point roles.
- `SOLVER_CONFLICT`: report the declarative constraint ID and conflicting IDs.
- `GUI_UNAVAILABLE`: omit the screenshot or reconnect to a GUI bridge.
- `RESULT_LIMIT_EXCEEDED`: narrow filters or continue with the cursor.

An error should state whether the transaction committed. Atomic mutation tools
should normally report `committed: false` through the error message and leave no
partial geometry. Unexpected exceptions belong in server logs, not in model
context.

## Side Effects, Idempotency, and Annotations

The current MCP `ToolAnnotations` fields are hints with conservative defaults:
`readOnlyHint` defaults to false, `destructiveHint` to true,
`idempotentHint` to false, and `openWorldHint` to true. Destructive and
idempotent hints are meaningful only for non-read-only tools. Clients MUST treat
annotations from untrusted servers as untrusted. See the
[ToolAnnotations schema](https://modelcontextprotocol.io/specification/2026-07-28/schema#toolannotations).

Recommended annotations are:

- `query_objects`: `readOnlyHint: true`, `openWorldHint: false` when it only
  reads the local document.
- `create_constrained_sketch`: `readOnlyHint: false`,
  `destructiveHint: false`, `idempotentHint: false`, and
  `openWorldHint: false` when it only adds a new sketch.
- Edit, replace, and delete tools: `readOnlyHint: false` and conservatively
  `destructiveHint: true`; an undo transaction does not make an update additive.
- A screenshot tool: `readOnlyHint: true` only if capture does not leave camera,
  selection, visibility, or document state changed.
- Save, export, or other path-writing tools: do not claim a closed world unless
  the server strictly confines their filesystem effects.

Repeated creation with identical arguments usually creates a second object, so
it is not idempotent. A transaction makes a single call atomic, not repeat-safe.
The 2026 transport also requires a client to reissue an in-flight request after
a broken response stream, which makes duplicate mutation handling relevant.

**CAD inference:** where retries are expected, accept a caller-generated
`idempotency_key`, persist the first committed result for a documented lifetime,
and return that result for the same key and normalized input. Reject reuse with
different input. Only then should a create tool advertise `idempotentHint: true`.
Do not add this state machinery unless timeout or retry evidence justifies it.

Every mutating tool should also use a FreeCAD transaction, recompute and validate
before commit, return the new document revision, and abort on failure. Revision
preconditions prevent stale plans; idempotency keys prevent duplicate execution.
They solve different problems.

## Proposal: Combined Object Query

**Verdict:** proceed with a prototype, but bound it to generic object retrieval
and compare it against the existing `list_objects` plus `inspect_object` pair.

List, search, and get-details share read-only permissions, the same object
domain, and one result vocabulary. They can be represented without unrelated
`mode` branches:

```json
{
  "document_ref": {
    "name": "Bracket"
  },
  "query": "hole",
  "names": [],
  "types": ["PartDesign::Feature", "Sketcher::SketchObject"],
  "visible_only": false,
  "detail": "summary",
  "limit": 25,
  "cursor": null,
  "include_screenshot": false
}
```

An empty `query` and `names` list means list matching objects. A non-empty query
searches semantic names, labels, and explicitly documented fields. `names`
requests exact objects. Filters combine consistently, and `detail` is an enum
such as `summary`, `standard`, or `detailed`.

A result can keep one stable shape:

```json
{
  "document_ref": {
    "name": "Bracket",
    "revision": "rev_42"
  },
  "items": [
    {
      "object_ref": {
        "name": "Hole",
        "label": "Mounting Holes",
        "type_id": "PartDesign::Hole"
      },
      "visibility": true,
      "summary": "Four through-all holes in Body"
    }
  ],
  "next_cursor": null,
  "truncated": false,
  "warnings": []
}
```

The contract should follow these rules:

1. Filter before pagination and return deterministic ordering.
2. Cap `limit` server-side and permit the server to return fewer records.
3. Bind an opaque cursor to the normalized filters and document revision. Return
   `STALE_REVISION` rather than continuing across a changed model.
4. Keep `get_sketch_info`, validation, connection status, and document lifecycle
   separate because they have domain-specific outputs and recovery behavior.
5. Do not allow this read tool to execute arbitrary expressions or FreeCAD code.
6. Keep screenshots opt-in and at most one per result, not one per object.

**MCP requirement:** protocol pagination directly covers `tools/list`,
`resources/list`, `resources/templates/list`, and `prompts/list`, not arbitrary
tool results. Its cursor is opaque and clients MUST NOT assume a fixed page size.
The `query_objects` cursor above is therefore a CAD API design inspired by the
[MCP pagination model](https://modelcontextprotocol.io/specification/2026-07-28/server/utilities/pagination),
not protocol-provided pagination.

The combined query is worthwhile only if evaluation shows fewer calls or fewer
tokens without increasing selection errors. If the discriminated behavior makes
the schema large or agents repeatedly request incompatible filters, retain
separate list, search, and inspect tools.

## Proposal: Object and Topology References

**Verdict:** return references, but distinguish object identity from temporary
topology selection.

FreeCAD documents that generated face, edge, and vertex names may change after
pad, cut, union, chamfer, fillet, and similar operations. FreeCAD 1.0 adds
heuristics that can identify, suggest repairs for, or sometimes repair broken
references, but it does not remove ambiguity. Official stable-model guidance
still recommends Origin planes, axes, datum geometry, sketches, and early
features over generated topology. See the
[topological naming problem](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Topological_naming_problem.md)
and [feature editing guidance](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Feature_editing.md#advice-for-creating-stable-models).

Use a descriptive, revision-scoped reference such as:

```json
{
  "handle": "sel_7e891b",
  "valid_at_revision": "rev_42",
  "object_ref": {
    "document_name": "Bracket",
    "name": "Pad",
    "label": "Base Plate",
    "type_id": "PartDesign::Feature"
  },
  "subelement": {
    "kind": "face",
    "name": "Face6"
  },
  "geometry": {
    "surface_type": "plane",
    "area_mm2": 1200.0,
    "centroid_mm": [0.0, 0.0, 10.0],
    "normal": [0.0, 0.0, 1.0]
  }
}
```

The `handle` is convenient input to an immediate follow-up call. It is not a
capability and must be checked against the caller, document, object, and
revision on every use. Its lifetime and restart behavior should be documented,
following MCP's non-normative state-handle guidance.

The geometry fields are evidence for explanation and re-query, not permission
to silently remap a stale face. Symmetric parts can contain geometrically
identical candidates. On a revision mismatch, return candidates and require a
new explicit selection rather than guessing.

Object `Name` values are preferable to mutable display labels for automation,
but they still need document scope. Sketch geometry and constraint indices are
native and useful within a sketch; they can shift after deletion or rebuilding.
Return them with sketch identity and revision. A declarative request should use
symbolic IDs and receive the native index mapping after commit.

## Proposal: Optional Screenshots

**Verdict:** screenshots are useful evidence, not a default field on every
result.

MCP tool results natively support image content and resource links. Return:

1. A concise text summary.
2. Structured capture metadata such as MIME type, dimensions, camera/view,
   visible object names, document revision, and optional resource URI.
3. The actual PNG as an image content block, or a revision-specific resource
   link when reuse or deferred loading is more useful.

Do not place a large base64 string in `structuredContent`; it is expensive for
models that serialize or inspect the JSON and obscures the useful metadata. A
resource link is especially appropriate for a detailed snapshot that may be
read later. Tool-returned resource links do not have to appear in
`resources/list`, according to the tools specification.

`include_screenshot` should default to false. The server should cap dimensions
and reject unsupported image settings through the schema. In headless mode,
return an actionable `GUI_UNAVAILABLE` tool error or complete the non-image
query with a warning only when the caller explicitly allowed image omission.

A capture at a requested view angle currently risks changing camera state.
Either render off-screen, save and restore all changed view state, or keep the
stateful view-and-capture action as a separate non-read-only tool. A combined
query must not advertise `readOnlyHint: true` while silently changing the view.

## Proposal: Declarative Constrained Sketches

**Verdict:** add a high-level atomic create tool and retain focused edit tools.

FreeCAD's scripting API adds geometry first, then refers to zero-based geometry
indices and point roles when adding constraints. GUI line numbering differs,
external geometry uses negative indices, and point positions have numeric
codes. These mechanics are documented in
[Sketcher scripting](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Sketcher_scripting.md).
They are appropriate inside the server but unnecessarily fragile in one large
model-generated request.

Use request-local symbolic IDs and typed constraint variants:

```json
{
  "document_ref": {
    "name": "Bracket",
    "expected_revision": "rev_12"
  },
  "body_name": "Body",
  "sketch_name": "BaseSketch",
  "support": {
    "kind": "origin_plane",
    "name": "XY_Plane"
  },
  "coordinate_unit": "mm",
  "entities": [
    {
      "id": "bottom",
      "kind": "line",
      "start": [0.0, 0.0],
      "end": [80.0, 0.0],
      "construction": false
    },
    {
      "id": "right",
      "kind": "line",
      "start": [80.0, 0.0],
      "end": [80.0, 40.0],
      "construction": false
    }
  ],
  "constraints": [
    {
      "id": "bottom_horizontal",
      "kind": "horizontal",
      "entity": "bottom"
    },
    {
      "id": "bottom_to_right",
      "kind": "coincident",
      "first": {
        "entity": "bottom",
        "point": "end"
      },
      "second": {
        "entity": "right",
        "point": "start"
      }
    },
    {
      "id": "bottom_length",
      "kind": "distance",
      "entity": "bottom",
      "value": {
        "kind": "literal",
        "value": "80 mm"
      }
    }
  ],
  "validation": {
    "require_fully_constrained": false,
    "require_closed_profiles": false
  }
}
```

Each geometry and constraint kind should have its own schema. Point references
should use enums such as `whole`, `start`, `end`, and `center`; the server maps
them to FreeCAD's numeric conventions. A dimension value should be a
discriminated literal or expression object, which makes "both value and
expression" impossible.

The implementation sequence should be deterministic:

1. Validate schema, duplicate symbolic IDs, references, units, limits, and
   support before opening a transaction.
2. Verify the expected document revision.
3. Open one transaction and create entities in request order.
4. Build a symbolic-to-native index map and add constraints through that map.
5. Recompute, solve, and apply the requested validation policy.
6. Commit only if all required checks pass; otherwise abort and return the
   failing symbolic IDs in a tool error.

A successful result should include:

```json
{
  "document_ref": {
    "name": "Bracket",
    "revision": "rev_13"
  },
  "sketch_ref": {
    "name": "BaseSketch",
    "label": "BaseSketch"
  },
  "entity_indices": {
    "bottom": 0,
    "right": 1
  },
  "constraint_indices": {
    "bottom_horizontal": 0,
    "bottom_to_right": 1,
    "bottom_length": 2
  },
  "solver": {
    "status": "valid",
    "fully_constrained": false,
    "degrees_of_freedom": null
  },
  "warnings": [
    "The sketch is valid but not fully constrained."
  ]
}
```

Return a numeric degree-of-freedom count only when the FreeCAD API path used by
the server can establish it reliably; otherwise return null with an explanatory
warning. Under-constrained geometry is not automatically an error unless the
caller requested that policy. Over-constrained, malformed, or recompute-invalid
geometry should fail atomically.

Creation should fail on an existing sketch name rather than hide replacement
behind an `on_conflict` mode. A future sketch patch or replacement operation has
different destructive semantics and deserves a separate contract. Retain
focused `add_sketch_*`, constraint, delete, toggle, and inspection tools for
interactive construction and repair after a declarative build fails or a user
wants a local edit.

## Resources, Prompts, Sampling, and Elicitation

### Resources

The existing `freecad://capabilities`, status, active-document, and parametric
guide resources fit MCP's application-driven model. Large or reusable additions
could include revision-specific model summaries, validation reports, and image
captures. A query tool can return a concise result plus a link to one of these
resources.

In `2026-07-28`, `resources/read` and primitive list results carry `ttlMs` and
`cacheScope`; tool-call results do not receive that protocol cache contract. Use
the [MCP caching rules](https://modelcontextprotocol.io/specification/2026-07-28/server/utilities/caching)
for resources, invalidate revision-specific data on mutation, and never mark
user-specific document content public.

### Prompts

The existing `design_parametric_part` and `review_parametric_part` prompts are
appropriate user-selected workflows. Keep them short and refer to resources for
long guidance. Do not depend on a prompt to establish transaction safety,
topology validation, or required tool ordering because prompts are
user-controlled and may not be selected.

### Sampling

**MCP requirement:** Sampling is deprecated in `2026-07-28`; new implementations
SHOULD NOT adopt it and existing implementations SHOULD migrate to provider APIs.
This CAD server should not ask the client model to plan a sketch inside a tool
call. The host agent already owns that reasoning. If a future server-side model
is justified, integrate it explicitly through a provider API and evaluate its
security and cost separately. See the
[Sampling specification](https://modelcontextprotocol.io/specification/2026-07-28/client/sampling).

### Elicitation

Use elicitation only when a nested server operation genuinely needs information
the user must supply. It is not a substitute for returning disambiguation
candidates or writing a precise schema. In the current protocol it uses a multi
round-trip result and only clients declaring the relevant capability can receive
it. Form schemas are deliberately limited to flat primitive fields.

Form mode MUST NOT request passwords, API keys, access tokens, or payment
credentials; URL mode is required for those interactions. This local CAD server
should normally need neither. A plausible form use is a user choice that cannot
be derived safely, such as selecting among several equally valid recovery
strategies after a consequential edit. See
[Elicitation](https://modelcontextprotocol.io/specification/2026-07-28/client/elicitation)
and [multi round-trip requests](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/mrtr).

## Context and Tool-Call Overhead

Tool definitions and intermediate results consume model context. OpenAI states
that function definitions count as input tokens, gives a soft suggestion of
fewer than 20 functions initially available, and recommends tool search for
large or infrequently used surfaces. Anthropic reports examples in which 58
tools consumed about 55K tokens and tool search reduced initial context use by
85 percent. Its MCP code-execution example reduced a 150K-token workflow to
about 2K tokens by loading definitions on demand and keeping intermediate data
outside model context.

The official MCP
[client best practices](https://modelcontextprotocol.io/docs/2026-07-28/develop/clients/client-best-practices)
recommend progressive discovery once tool definitions consume a meaningful
fraction of context. The host can retain a catalog, inject only relevant full
schemas, cache definitions, and refresh on tool-list changes. Programmatic tool
calling can also filter and compose results in a sandbox, but that is primarily
a host capability and introduces a code-execution security surface.

This repository's direct OpenCode measurement found that 38 selected parametric
tools contributed 44,758 serialized schema characters in a 10,027-input-token
request. See
[Compact Local Coding Agents](compact-local-coding-agent-research.md). This is
strong evidence that schema size matters for the intended local 64K model.

Recommended controls are:

1. Keep a compact core profile for common document, query, sketch, feature, and
   validation workflows; defer uncommon dress-up, import/export, GUI, and legacy
   tools where the host supports discovery.
2. Do not merge unrelated mutations merely to reach a target count. A single
   broad schema can consume as much context and cause more invalid calls.
3. Keep descriptions complete but remove repeated prose that the schema already
   expresses.
4. Bound every potentially large read with filters, a limit, a cursor, and a
   concise default detail level.
5. Return only identifiers and fields needed for the next likely action, with a
   detailed mode or resource for diagnostics.
6. Preserve deterministic tool ordering to improve prompt-cache behavior, as
   recommended by the 2026 tools specification.

## Evaluation Plan

Both Anthropic and OpenAI recommend evaluating tool metadata and contracts on a
labelled set of realistic tasks. A CAD evaluation should compare interfaces,
not only verify schema validity.

Include tasks that require:

- Listing and finding objects without exact names.
- Inspecting a specific sketch, feature, and Body history.
- Selecting a face, mutating an upstream feature, then detecting the stale
  selection rather than applying it to a different face.
- Creating a constrained profile declaratively and incrementally.
- Recovering from a redundant or conflicting constraint.
- Retrying a timed-out create without producing an unnoticed duplicate.
- Requesting visual evidence in GUI mode and handling it in headless mode.
- Working with a large document that requires filtering and pagination.
- Choosing the right tool when full-profile tools are also available.

Measure task success, wrong-tool selection, invalid arguments, tool errors,
uncaught failures, tool calls per task, input and output tokens, latency,
duplicate mutations, stale-reference detection, and final FreeCAD validity.
Run held-out tasks with the actual local model, client, profile, and context
budget.

The most important A/B comparisons are:

1. `list_objects` plus `inspect_object` versus `query_objects`.
2. Focused sketch calls versus `create_constrained_sketch` for complete profiles.
3. Numeric-only references versus symbolic input IDs and revision-scoped output
   references.
4. Base64 JSON screenshots versus image blocks or resource links.
5. All 51 baseline tools loaded versus a measured core set plus progressive
   discovery.

## Recommended Implementation Sequence

1. Record baseline task accuracy, call count, tool-schema characters, and token
   use before changing the surface.
2. Introduce explicit result models, useful output schemas, actionable tool
   errors, and accurate annotations for a small representative tool set.
3. Add explicit document references and a server-managed revision token to read
   and mutation results.
4. Prototype `query_objects` with bounded detail and cursor semantics; A/B test
   it before removing or hiding existing reads.
5. Add revision-scoped topology references and stale-reference rejection to one
   selection-sensitive operation such as fillet or chamfer.
6. Implement `create_constrained_sketch` for a limited set of common entity and
   constraint variants, then expand from evaluation evidence.
7. Return screenshot evidence as image content or resource links and make view
   state behavior explicit.
8. Define a compact default exposure strategy and test provider-native or custom
   progressive discovery with the target clients.
9. Treat Python SDK v2 and the `2026-07-28` wire protocol as a separate migration
   with legacy-client tests.

## Primary Sources

- [MCP 2026-07-28 tools specification](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)
- [MCP ToolAnnotations schema](https://modelcontextprotocol.io/specification/2026-07-28/schema#toolannotations)
- [MCP resources specification](https://modelcontextprotocol.io/specification/2026-07-28/server/resources)
- [MCP prompts specification](https://modelcontextprotocol.io/specification/2026-07-28/server/prompts)
- [MCP pagination utility](https://modelcontextprotocol.io/specification/2026-07-28/server/utilities/pagination)
- [MCP caching utility](https://modelcontextprotocol.io/specification/2026-07-28/server/utilities/caching)
- [MCP elicitation specification](https://modelcontextprotocol.io/specification/2026-07-28/client/elicitation)
- [MCP sampling specification](https://modelcontextprotocol.io/specification/2026-07-28/client/sampling)
- [MCP multi round-trip requests](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/mrtr)
- [MCP 2026-07-28 changelog](https://modelcontextprotocol.io/specification/2026-07-28/changelog)
- [MCP client best practices](https://modelcontextprotocol.io/docs/2026-07-28/develop/clients/client-best-practices)
- [MCP Python SDK structured output](https://py.sdk.modelcontextprotocol.io/v2/servers/structured-output/)
- [MCP Python SDK error handling](https://py.sdk.modelcontextprotocol.io/v2/servers/handling-errors/)
- [MCP Python SDK protocol versions](https://py.sdk.modelcontextprotocol.io/v2/protocol-versions/)
- [MCP Python SDK v1 to v2 migration](https://py.sdk.modelcontextprotocol.io/v2/migration/)
- [MCP TypeScript SDK tools](https://ts.sdk.modelcontextprotocol.io/v2/servers/tools)
- [Anthropic: Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [Anthropic: Code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp)
- [Anthropic: Advanced tool use](https://www.anthropic.com/engineering/advanced-tool-use)
- [OpenAI: Define tools](https://developers.openai.com/plugins/plan/tools)
- [OpenAI: Build an MCP server](https://developers.openai.com/plugins/build/mcp-server)
- [OpenAI: Optimize metadata](https://developers.openai.com/plugins/guides/optimize-metadata)
- [OpenAI: Function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [OpenAI: Tool search](https://developers.openai.com/api/docs/guides/tools-tool-search)
- [FreeCAD: Topological naming problem](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Topological_naming_problem.md)
- [FreeCAD: Feature editing](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Feature_editing.md)
- [FreeCAD: Sketcher scripting](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Sketcher_scripting.md)
