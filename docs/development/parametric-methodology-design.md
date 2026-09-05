# Parametric Methodology Design

Status: Implemented on `integration/freecad-compatibility`
Deferred: the GUI integration test below was never written, and the
construction-helper TypeId detection is unverified against a live FreeCAD.
Date: 2026-09-05
Branch: `integration/freecad-compatibility`

The server's built-in instructions become the methodology. Installing this
fork and asking for a part should be enough: the user supplies the design,
the server supplies the process and the commands.

## Problem

The knowledge needed to drive this server well is currently scattered across
three places outside the server, and the server's own guidance is a reference
sheet rather than a process.

In the lighthouse benchmark, a run needs all three of:

1. `config/*.json` `instructions` — a second, byte-identical copy of
   `PARAMETRIC_PARTS_GUIDE.md`.
1. `--file brief-freecad.md` — the task, mixed with process rules and
   harness policy.
1. The runner's instruction string — modeling policy plus benchmark autonomy
   rules.

Only the first is even about this server. Someone who installs the fork and
asks for a bracket gets the guide and nothing else: no brief-writing step, no
evidence protocol, no save-early rule, no scaling rule. Every process lesson
the benchmark paid for lives in files that ship with the benchmark, not with
the server.

### Evidence that the injection is redundant

opencode reads each MCP server's `instructions` from the initialize result
and splices it into the system prompt as
`<mcp_instructions><server name="...">…</server></mcp_instructions>`
(`SystemPrompt.mcp` in the opencode binary; the MCP client stores it via
`getInstructions()`). This server already passes
`instructions=PARAMETRIC_PARTS_GUIDANCE` in `src/freecad_mcp/server.py`.

So the guide reaches the model automatically whenever the server is
connected, and the condition configs' `instructions` array ships those same
125 lines a second time.

### Evidence that guidance alone cannot close the gap

`get_screenshot` accepts eight fixed global view angles: `Isometric`,
`Front`, `Back`, `Top`, `Bottom`, `Left`, `Right`, `FitAll`
(`src/freecad_mcp/tools/view.py`). There is no view along a named feature's
own support, no focus framing, no construction-helper hiding, and no section.

The Stage C defect — window openings with malformed lower edges, described
by the reviewer as an inverted arch — passed every deterministic check and
survived the retained images, because no retained image looked at an opening
along its own normal. Instructing a model to "look along the feature normal"
without a command that can do it produces narration, not evidence.

## Design

### 1. The core file follows the text-to-cad skill's shape

`PARAMETRIC_PARTS_GUIDE.md` is rewritten from a 125-line reference sheet
into a ~110-line process core, in the order text-to-cad's `SKILL.md` uses:

| Section                | Content                                                                                                                                |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Purpose                | The saved FCStd PartDesign tree is the authoritative artifact; STEP and images are derived.                                            |
| Use this server when   | Native parametric parts; not mesh work, not CAM, not assemblies of purchased parts.                                                    |
| Default assumptions    | mm, Origin planes and named datums, one Body per contiguous part, governing values in one `App::VarSet`, derived values by expression. |
| Required workflow      | Numbered steps, opening with the scaling rule.                                                                                         |
| Handoff                | What a final answer must contain.                                                                                                      |
| Non-negotiables        | The floors below.                                                                                                                      |
| Progressive references | `freecad://guide/<topic>` URIs with explicit triggers.                                                                                 |

The required workflow, mirroring text-to-cad's ten steps but expressed in
FreeCAD terms:

1. **Scale depth to the task.** A simple part needs a short brief and few
   checks; a parametric family with variants needs the full protocol.
1. **Classify the request**: new part, edit of an existing document,
   parameter study, inspection, or repair.
1. **Load only the references the task triggers.**
1. **Write the brief before touching FreeCAD.** Turn the user's sentence
   into explicit dimensions, units, coordinate frame, feature intent,
   governing versus derived parameters, and validation targets. State
   assumptions rather than asking, unless a choice is genuinely blocking.
1. **Plan the tree**: parameters, datums, Body, feature order — primary form,
   cuts, patterns, then topology-sensitive dress-up.
1. **Build incrementally** through task-oriented tools, one coherent step at
   a time, carrying `document_ref` and `expected_revision` forward.
1. **Verify numerically** after each meaningful feature group.
1. **Verify visually** along the right axis, per the visual-evidence
   reference. Deterministic checks prove validity, not intent.
1. **Save early** — the moment the model first satisfies the brief.
1. **Repair the smallest responsible input**, never stack compensating
   features on an invalid tree.
1. **Hand off** with paths, checks actually run, assumptions, limitations.

### 2. The floors never scale down

These apply to every part regardless of size. Each is traceable to an
observed failure:

- Driving sketches are `FullyConstrained` before the feature that consumes
  them.
- `validate_document(require_single_solid=true)` passes before any delivery
  claim.
- The FCStd is saved and the STEP exported as soon as the shape first
  satisfies the brief, before any refinement. *Stage B ran 20 minutes and
  left nothing on disk.*
- Every semantic opening or profile is seen along its own support normal
  before it is called correct. *Stage C's malformed windows passed all
  geometry checks.*
- A `warnings` entry on a mutation result is unfinished work: resolve it, or
  record why it is acceptable.
- Derived values are expressions, never numbers copied between features.
- No check is reported that did not run. *Stage C narrated validation steps
  it never executed, which is why its acceptance pass was only partial.*

### 3. Depth ships as MCP resources, pointed at from the core

Seven topic documents, each registered as an MCP resource and each named
from the core file at the step that triggers it:

| URI                               | Trigger                                                                                                                                                                             |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `freecad://guide/brief`           | Before modeling, whenever the request is prose, an image, or a drawing rather than an explicit spec.                                                                                |
| `freecad://guide/visual-evidence` | Before capturing any evidence. Mandatory gate.                                                                                                                                      |
| `freecad://guide/parameters`      | When the part has governing parameters or expression-driven dimensions.                                                                                                             |
| `freecad://guide/features`        | When choosing feature order, datums, overlap, through-cuts, or dress-up placement.                                                                                                  |
| `freecad://guide/variants`        | When the brief asks for parameter variants or a family.                                                                                                                             |
| `freecad://guide/repair`          | On a rejected sketch, feature, or expression batch. Names the error codes explicitly, including `VALIDATION_FAILED` and the `STALE_REVISION` cascade that follows a rejected batch. |
| `freecad://guide/delivery`        | When the brief asks for a manifest, README, or re-import evidence.                                                                                                                  |

Source of record is one markdown file per topic under
`src/freecad_mcp/guides/`, loaded by `guidance.py` the way
`PARAMETRIC_PARTS_GUIDE.md` is loaded today. `freecad://parametric-parts/guide`
is retained as an alias for the core so existing configurations keep working.

Known limitation, accepted: resources are client-mediated. opencode lets the
model list and read them; some clients expose resources only as a
user-attached mention. In those clients the floors in the core still apply,
but the depth may go unread. If that becomes a real constraint, the same
files can later be exposed through a `get_guide(topic)` tool without
changing their content.

### 4. One new tool: capture along a feature's own normal

`capture_feature_view` closes the gap that makes the visual gate
unfollowable today.

```text
capture_feature_view(
    normal_source: str,        # named sketch, datum, or feature support
    side: "front" | "back" = "front",
    focus: list[str] | None = None,
    padding: float = 0.1,
    hide_construction: bool = True,
    width: int = 800,
    height: int = 600,
    doc_name: str | None = None,
)
```

Behaviour: resolve `normal_source` to a placement and derive its normal;
set the view direction along that normal from the chosen side; frame the
focus objects with padding; hide datum planes, origins, and construction
helpers; capture; then restore visibility, camera, and active document.

Returns the image content block plus JSON metadata: camera direction, the
resolved source and its placement, focus names, visibility changes made and
undone, retained path, and image hash.

This is an extension of the existing screenshot path, not new machinery.
`bridge/xmlrpc.py` already executes generated Python inside FreeCAD, saves
and restores the camera around a capture, flushes paint events before
grabbing, and restores the previously active document. `set_object_visibility`
already exists for the hide-and-restore step.

Orientation is derived server-side from placements. The model never computes
world-space camera vectors, and `FaceN` is not part of the contract.

### 5. The benchmark keeps its pinned injection, minus the duplication

`run_all.sh` continues to name exact files and pass an explicit instruction
string, so a run stays reproducible. What changes:

- `brief-freecad.md` keeps the task and the harness policy, and sheds the
  process rules that the server now owns.
- Condition configs drop `instructions`, which is a duplicate of what the
  MCP handshake already delivers.

## Files changed

| Path                                                                     | Change                                                                              |
| ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------- |
| `src/freecad_mcp/PARAMETRIC_PARTS_GUIDE.md`                              | Rewritten as the process core.                                                      |
| `src/freecad_mcp/guides/*.md`                                            | Seven new topic documents.                                                          |
| `src/freecad_mcp/guidance.py`                                            | Loader for the topic set.                                                           |
| `src/freecad_mcp/resources/parametric.py`                                | Register seven resources; keep the existing alias; update `freecad://capabilities`. |
| `src/freecad_mcp/tools/view.py`                                          | Add `capture_feature_view`.                                                         |
| `src/freecad_mcp/tools/__init__.py`                                      | Add the tool to `PARAMETRIC_TOOL_NAMES` (54 → 55).                                  |
| `src/freecad_mcp/bridge/base.py`, `bridge/xmlrpc.py`                     | Bridge method for a placement-derived camera with visibility save and restore.      |
| `src/freecad_mcp/prompts/parametric.py`                                  | `design_parametric_part` composes the new core instead of the old guide text.       |
| `tests/unit/test_tools_view.py`, `tests/unit/test_parametric_profile.py` | Cover the new tool, the profile count, and resource registration.                   |
| `docs/guide/tools.md`                                                    | Tool count and category table, per the CLAUDE.md update rule.                       |
| `docs/MCP_TOOLS_REFERENCE.md`                                            | Exact signature for the new tool.                                                   |
| `CLAUDE.md`                                                              | Tool count 54 to 55 in the Tools Reference section.                                 |

## Testing

- Unit: normal resolution from a placement, both `side` values, focus
  framing, hide-and-restore correctness including the failure path, and the
  error contract for an unresolvable `normal_source`.
- Unit: every advertised `freecad://guide/<topic>` URI resolves and returns
  non-empty content; every URI named in the core file exists as a registered
  resource, and vice versa. This test is what keeps the pointers honest.
- Integration (GUI): capture along a sketch normal restores the camera and
  the visibility state the operator had before the call.
- Manual: the MCP handshake carries the new core as `instructions` — verify
  by reading the initialize result, not by inferring from model behaviour.

## Non-goals for this round

- Section views. Valuable per the evidence research, deferred.
- The acceptance evaluator and evidence manifest returning
  `PASS`/`FAIL`/`UNVERIFIED` per requirement. That is benchmark machinery,
  not something a fork installer needs.
- Any change to the transaction or mutation contract.

## Consequences

The next benchmark run is a new condition, not an A/B against Stage D: the
ambient instructions change, the duplicate copy disappears, and a new tool
enters the surface. Record it as Stage E with its own condition file, the
way Stage D was recorded.

## Sources

- `research/cad-evidence-workflow-reuse-2026-08-29.md` — sections 2 and 3 of
  its adoption plan are the direct basis for the visual gate and the capture
  tool contract.
- `text-to-cad/skills/cad/SKILL.md` — the structural baseline: compact core,
  scaled depth, non-negotiables, progressive references.
- `build123d-mcp/default_prompt.md` — validation protocol and rendering
  guidance patterns.
- `experiments/parametric-lighthouse-workflow-comparison/HANDOFF.md` —
  Stage B, C, and D results.
- `docs/development/compact-local-coding-agent-research.md` — tool schemas,
  not prose, dominate context for local models.
