# Parametric Methodology Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the server's built-in instructions the complete methodology, so
installing the fork and asking for a part is enough.

**Architecture:** `PARAMETRIC_PARTS_GUIDE.md` becomes a compact process core
delivered automatically through the MCP `instructions` field. Seven topic
documents carry the depth and are fetched on demand as `freecad://guide/<topic>`
resources. One new tool, `capture_feature_view`, makes the core's visual gate
executable by aiming the camera along a named feature's own support normal.

**Tech Stack:** Python 3.14, FastMCP, pytest, uv, just, ruff, mypy,
markdownlint.

**Spec:** `docs/development/parametric-methodology-design.md`

## Global Constraints

- Python 3.14; run every Python tool through `uv run`.
- Line length 88 characters (ruff/black); `E501` is ignored for embedded code
  strings only.
- Type hints on all function signatures; Google-style docstrings on all public
  functions and modules.
- Markdown tables use the padded/aligned style (markdownlint MD060); horizontal
  rules are `---` (MD035).
- Accessible language: no "sanity check", "whitelist/blacklist", "master/slave",
  or metaphorical "kill".
- `execute_python` requires the keyword-only `transaction` argument. Captures
  and view changes are read-only: pass `transaction=None`.
- Never call `openTransaction`, `commitTransaction`, or `abortTransaction` in
  generated code.
- All GUI-dependent code checks `FreeCAD.GuiUp` first and returns
  `{"success": False, "error": ...}` rather than raising.
- Work on branch `integration/freecad-compatibility`. Never commit to `main`.
- Conventional commit messages (commitizen validates them).

---

### Task 1: Guide topic loader

**Files:**

- Modify: `src/freecad_mcp/guidance.py`
- Create: `src/freecad_mcp/guides/.gitkeep`
- Test: `tests/unit/test_guidance.py`

**Interfaces:**

- Consumes: nothing.
- Produces: `GUIDE_TOPICS: tuple[str, ...]`, `load_guide(topic: str) -> str`,
  `GUIDE_DIRECTORY: Path`. Later tasks register one resource per entry in
  `GUIDE_TOPICS` and call `load_guide` to serve it.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_guidance.py`:

```python
"""Tests for guidance loading."""

import pytest

from freecad_mcp.guidance import GUIDE_TOPICS, load_guide


class TestGuideTopics:
    """Tests for the progressive guide topic set."""

    def test_topics_are_the_seven_documented_ones(self):
        """The topic set matches the design document exactly."""
        assert GUIDE_TOPICS == (
            "brief",
            "visual-evidence",
            "parameters",
            "features",
            "variants",
            "repair",
            "delivery",
        )

    @pytest.mark.parametrize("topic", GUIDE_TOPICS)
    def test_every_topic_loads_non_empty_markdown(self, topic):
        """Each advertised topic resolves to a real document."""
        content = load_guide(topic)
        assert content.startswith("# ")
        assert len(content) > 200

    def test_unknown_topic_raises_key_error(self):
        """An unregistered topic name is a programming error, not a fallback."""
        with pytest.raises(KeyError, match="unknown guide topic"):
            load_guide("nonexistent")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_guidance.py -v`
Expected: FAIL with `ImportError: cannot import name 'GUIDE_TOPICS'`.

- [ ] **Step 3: Write minimal implementation**

Append to `src/freecad_mcp/guidance.py`:

```python
GUIDE_DIRECTORY = Path(__file__).with_name("guides")

GUIDE_TOPICS: tuple[str, ...] = (
    "brief",
    "visual-evidence",
    "parameters",
    "features",
    "variants",
    "repair",
    "delivery",
)


def load_guide(topic: str) -> str:
    """Return one progressive guide topic document.

    Args:
        topic: A topic name from ``GUIDE_TOPICS``.

    Returns:
        The topic's markdown source.

    Raises:
        KeyError: If the topic is not in ``GUIDE_TOPICS``.
    """
    if topic not in GUIDE_TOPICS:
        raise KeyError(f"unknown guide topic: {topic}")
    return (GUIDE_DIRECTORY / f"{topic}.md").read_text(encoding="utf-8")
```

Create `src/freecad_mcp/guides/.gitkeep` as an empty file so the directory is
tracked before Task 2 fills it.

- [ ] **Step 4: Run test to verify the loader works and the documents are missing**

Run: `uv run pytest tests/unit/test_guidance.py -v`
Expected: `test_topics_are_the_seven_documented_ones` and
`test_unknown_topic_raises_key_error` PASS; the seven parametrized
`test_every_topic_loads_non_empty_markdown` cases FAIL with
`FileNotFoundError`. Task 2 makes them pass.

- [ ] **Step 5: Commit**

```bash
git add src/freecad_mcp/guidance.py src/freecad_mcp/guides/.gitkeep \
    tests/unit/test_guidance.py
git commit -m "feat: add progressive guide topic loader"
```

---

### Task 2: The seven topic documents

**Files:**

- Create: `src/freecad_mcp/guides/brief.md`
- Create: `src/freecad_mcp/guides/visual-evidence.md`
- Create: `src/freecad_mcp/guides/parameters.md`
- Create: `src/freecad_mcp/guides/features.md`
- Create: `src/freecad_mcp/guides/variants.md`
- Create: `src/freecad_mcp/guides/repair.md`
- Create: `src/freecad_mcp/guides/delivery.md`
- Test: `tests/unit/test_guidance.py` (extend)

**Interfaces:**

- Consumes: `GUIDE_TOPICS`, `load_guide` from Task 1.
- Produces: seven markdown documents. Task 3 serves them; Task 4's core file
  points at them by URI.

Each document starts with a single `#` title and is written in the same plain,
literal register as the existing guide. Required content per document, with the
source to draw from:

**`brief.md`** — "Writing The Brief Before Modeling". Turn a prose request, an
image, or a drawing into: overall function and orientation; units (mm unless
stated); coordinate frame and which Origin plane each feature references;
governing parameters versus derived dimensions; the semantic features the part
must have; validation targets, meaning the measurements that decide whether the
result is correct; and the assumptions taken. State assumptions rather than
asking; ask only when a choice is genuinely blocking. Adapted from
`../../../text-to-cad/skills/cad/references/cad-brief.md`.

**`visual-evidence.md`** — "Looking At What You Built". The protocol, adapted
from `research/cad-evidence-workflow-reuse-2026-08-29.md` section 2:

1. Run the deterministic structural and parametric checks first.
1. Hide datum planes, origins, and construction helpers before capturing.
1. Capture one clean global view with `get_screenshot`.
1. For every semantic opening or profile — each door, each window, each
   lantern division — capture with `capture_feature_view` using that feature's
   own sketch or support as `normal_source`. A feature seen edge-on is not
   evidence about its shape.
1. Compare the silhouette against the profile you intended, and state the
   comparison explicitly.
1. Convert every visual concern into a deterministic geometry check.
1. If an opening is obstructed, edge-on, or absent from every retained image,
   say that you have no visual evidence for it.
1. Never describe an image you did not receive and inspect.

**`parameters.md`** — "Parameters And Expressions". One `App::VarSet` per
document, defined in a single `define_variables` batch. Explicit units on
lengths and angles. Valid internal names: letters, digits, underscores,
starting with a letter or underscore. Governing versus derived: derived values
carry an expression, never a copied number. `bind_expressions` binds a related
group at once; constraint paths take the form `Constraints[8]` and qualified
references the form `Variables.tower_height`. A rejected batch reports each
failing property and rolls back every definition in it.

**`features.md`** — "Feature Order And Supports". Drawn from the current
guide's sections 3 and 4, which this document inherits: stable feature order
(primary additive form, cuts, patterns, then topology-sensitive fillets and
chamfers); real overlap for intended unions, because point or tangent contact
is not reliable connectivity; through-cuts extended beyond both sides;
`create_datum_plane` when a stable offset support is clearer than a Body face;
Origin planes and named datums in preference to generated `FaceN` or `EdgeN`
references, with any unavoidable topology-sensitive reference recorded and
retested after save and reopen; additive features must increase Body volume,
and a pattern must become the Body Tip while retaining exactly one solid.

**`variants.md`** — "Parameter Variants As Isolated Transactions". Open a fresh
copy of the saved nominal FCStd per variant. Change exactly one governing
value; leave the others nominal. `define_variables` already recomputes, so do
not issue a separate `recompute_document`. Validate, save to an explicit path,
and close the document before starting the next variant. Never derive one
variant from another variant's open document. Measure both the intended change
and the protected controls that must not move. Retain per variant: parent
nominal hash, the governing parameter name and value, output paths, and the
check results.

**`repair.md`** — "Repairing A Rejected Operation". Name the error codes
explicitly. `VALIDATION_FAILED` means the operation was rejected and rolled
back: read the reported failing inputs, fix the smallest responsible one, and
rerun only that operation. `STALE_REVISION` means the `document_ref` revision
you carried is no longer current, which is the normal consequence of a
preceding rejected batch: re-read current state with a bounded `query_objects`
or `get_variables` call and carry the fresh revision forward — never retry the
same call blind. Use `undo` for a bad mutation rather than stacking a
compensating feature on an invalid tree. Granular `create_sketch`,
`add_sketch_line`, `add_sketch_constraint`, `set_expression`, and
`get_sketch_info` exist for local repair only.

**`delivery.md`** — "Delivering Evidence". Only when the brief asks for it: a
parameter manifest listing names, types, values, units, formulas, and
expression targets; a README with assumptions, the ordered feature tree,
measurements, repairs, topology-sensitive references, and limitations; STEP
re-import into a clean document with BREP validation; and a demonstration that
an invalid parameter value produces a clear failed recompute. All final
evidence must describe the same saved document. Backup `.FCStd1` files are not
deliverables.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_guidance.py`:

```python
class TestGuideContent:
    """Each topic document must carry the rules the core file promises."""

    @pytest.mark.parametrize(
        ("topic", "required"),
        [
            ("brief", "assumption"),
            ("visual-evidence", "capture_feature_view"),
            ("parameters", "App::VarSet"),
            ("features", "datum"),
            ("variants", "one governing"),
            ("repair", "STALE_REVISION"),
            ("delivery", "manifest"),
        ],
    )
    def test_topic_carries_its_defining_rule(self, topic, required):
        """A topic document without its defining rule is not the document."""
        assert required in load_guide(topic)

    def test_visual_evidence_forbids_describing_unseen_images(self):
        """The Stage C failure mode is named explicitly."""
        content = load_guide("visual-evidence")
        assert "did not receive" in content

    def test_repair_names_both_error_codes(self):
        """Both observed rejection codes are covered."""
        content = load_guide("repair")
        assert "VALIDATION_FAILED" in content
        assert "STALE_REVISION" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_guidance.py -v`
Expected: FAIL with `FileNotFoundError` for the guide documents.

- [ ] **Step 3: Write the seven documents**

Write each file per the content specification above. Keep each to roughly 25 to
60 lines. Use `# Title` then short numbered or bulleted rules — no tables, which
keeps MD060 out of play.

- [ ] **Step 4: Run tests and the markdown linter**

Run: `uv run pytest tests/unit/test_guidance.py -v`
Expected: PASS, all cases including Task 1's parametrized loader test.

Run:
`uv run pre-commit run markdownlint-cli2 --files src/freecad_mcp/guides/*.md`
Expected: Passed.

- [ ] **Step 5: Commit**

```bash
git add src/freecad_mcp/guides tests/unit/test_guidance.py
git commit -m "docs: add the seven progressive guide topics"
```

---

### Task 3: Serve the topics as MCP resources

**Files:**

- Modify: `src/freecad_mcp/resources/parametric.py`
- Test: `tests/unit/test_parametric_profile.py`

**Interfaces:**

- Consumes: `GUIDE_TOPICS`, `load_guide` from Task 1.
- Produces: registered resources `freecad://guide/<topic>` for all seven
  topics; the existing `freecad://parametric-parts/guide` retained as the core
  alias; `freecad://capabilities` listing every resource URI.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_parametric_profile.py`, using that file's existing
`_resource_registry` helper:

```python
class TestGuideResources:
    """The progressive guide topics must be reachable as resources."""

    @pytest.mark.asyncio
    async def test_every_topic_is_registered(self):
        """Each topic in GUIDE_TOPICS has its own resource URI."""
        from freecad_mcp.guidance import GUIDE_TOPICS
        from freecad_mcp.resources.parametric import register_resources

        mcp = _resource_registry()
        register_resources(mcp, AsyncMock())

        for topic in GUIDE_TOPICS:
            assert f"freecad://guide/{topic}" in mcp._registered_resources

    @pytest.mark.asyncio
    async def test_topic_resource_returns_its_document(self):
        """Reading a topic resource returns that topic's markdown."""
        from freecad_mcp.guidance import load_guide
        from freecad_mcp.resources.parametric import register_resources

        mcp = _resource_registry()
        register_resources(mcp, AsyncMock())

        reader = mcp._registered_resources["freecad://guide/repair"]
        assert await reader() == load_guide("repair")

    @pytest.mark.asyncio
    async def test_core_alias_is_retained(self):
        """Existing configurations keep working."""
        from freecad_mcp.resources.parametric import register_resources

        mcp = _resource_registry()
        register_resources(mcp, AsyncMock())

        assert "freecad://parametric-parts/guide" in mcp._registered_resources

    @pytest.mark.asyncio
    async def test_capabilities_lists_every_registered_resource(self):
        """The catalog cannot advertise a resource set it does not register."""
        from freecad_mcp.resources.parametric import register_resources

        mcp = _resource_registry()
        register_resources(mcp, AsyncMock())

        catalog = json.loads(
            await mcp._registered_resources["freecad://capabilities"]()
        )
        assert sorted(catalog["resources"]) == sorted(
            mcp._registered_resources.keys()
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_parametric_profile.py -k Guide -v`
Expected: FAIL — `freecad://guide/brief` is not in the registry.

- [ ] **Step 3: Write minimal implementation**

In `src/freecad_mcp/resources/parametric.py`, import the loader and register one
resource per topic. Because FastMCP keys resources by URI, bind the topic with a
default argument so the closure does not capture the loop variable:

```python
from freecad_mcp.guidance import GUIDE_TOPICS, PARAMETRIC_PARTS_GUIDANCE, load_guide

    for topic in GUIDE_TOPICS:

        @mcp.resource(f"freecad://guide/{topic}")
        async def resource_guide_topic(topic: str = topic) -> str:
            """Return one progressive guide topic document."""
            return load_guide(topic)
```

Replace the hard-coded `"resources"` list in `resource_capabilities` with a
computed list so it can never drift:

```python
                "resources": sorted(
                    [
                        "freecad://active-document",
                        "freecad://capabilities",
                        "freecad://parametric-parts/guide",
                        "freecad://status",
                    ]
                    + [f"freecad://guide/{topic}" for topic in GUIDE_TOPICS]
                ),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_parametric_profile.py -v`
Expected: PASS, including the file's pre-existing contract tests.

- [ ] **Step 5: Commit**

```bash
git add src/freecad_mcp/resources/parametric.py \
    tests/unit/test_parametric_profile.py
git commit -m "feat: serve progressive guide topics as MCP resources"
```

---

### Task 4: Rewrite the core guide

**Files:**

- Modify: `src/freecad_mcp/PARAMETRIC_PARTS_GUIDE.md` (full rewrite)
- Test: `tests/unit/test_guidance.py` (extend)

**Interfaces:**

- Consumes: `GUIDE_TOPICS` from Task 1; the resource URIs from Task 3.
- Produces: the text delivered as the server's MCP `instructions`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_guidance.py`:

```python
class TestCoreGuide:
    """The core is what every session receives as MCP instructions."""

    def test_core_points_at_every_topic(self):
        """A topic nobody is told about will never be read."""
        from freecad_mcp.guidance import GUIDE_TOPICS, PARAMETRIC_PARTS_GUIDANCE

        for topic in GUIDE_TOPICS:
            assert f"freecad://guide/{topic}" in PARAMETRIC_PARTS_GUIDANCE

    def test_core_points_at_no_unregistered_topic(self):
        """Every pointer in the core resolves to a real topic."""
        import re

        from freecad_mcp.guidance import GUIDE_TOPICS, PARAMETRIC_PARTS_GUIDANCE

        referenced = set(
            re.findall(r"freecad://guide/([a-z-]+)", PARAMETRIC_PARTS_GUIDANCE)
        )
        assert referenced == set(GUIDE_TOPICS)

    def test_core_states_the_floors(self):
        """The rules that never scale down are stated in the always-on text."""
        from freecad_mcp.guidance import PARAMETRIC_PARTS_GUIDANCE

        for rule in [
            "FullyConstrained",
            "require_single_solid=true",
            "before any refinement",
            "capture_feature_view",
            "warnings",
        ]:
            assert rule in PARAMETRIC_PARTS_GUIDANCE

    def test_core_stays_compact(self):
        """The core is a spine, not the whole methodology."""
        from freecad_mcp.guidance import PARAMETRIC_PARTS_GUIDANCE

        assert len(PARAMETRIC_PARTS_GUIDANCE.splitlines()) <= 130
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_guidance.py -k CoreGuide -v`
Expected: FAIL — the current guide contains no `freecad://guide/` pointers.

- [ ] **Step 3: Rewrite the core**

Replace the entire contents of `src/freecad_mcp/PARAMETRIC_PARTS_GUIDE.md`:

```markdown
# Native Parametric FreeCAD Parts

Build editable native FreeCAD PartDesign models through typed MCP commands.
The saved FCStd feature tree is the authoritative artifact. STEP files and
images are derived from it. Arbitrary Python execution is deliberately absent.

## Use This Server When

Use it for native parametric solid parts: sketched profiles, pads, pockets,
revolutions, grooves, lofts, patterns, and dress-up features driven by named
variables and expressions. Do not use it for mesh repair, CAM, rendering, or
assemblies of purchased components.

## Default Assumptions

State any departure from these in your handoff.

- Millimeters for length, degrees for angle, with explicit units in variables.
- Origin planes and named datums as supports, in preference to model faces.
- One semantically named `PartDesign::Body` per contiguous part.
- Governing values in one `App::VarSet`; derived values bound by expression.

## Required Workflow

Scale depth to the task. A simple bracket needs a short brief and a few
checks. A parametric family with variants needs the full protocol. The floors
below apply either way.

1. Classify the request: new part, edit of an existing document, parameter
   study, inspection, or repair.
1. Load only the guide topics the task triggers. They are listed at the end.
1. Write the brief before touching FreeCAD. Turn the request into explicit
   dimensions, units, coordinate frame, feature intent, governing parameters,
   and validation targets. Read `freecad://guide/brief` whenever the request
   arrives as prose, an image, or a drawing rather than an explicit spec.
   State assumptions instead of asking, unless a choice is genuinely blocking.
1. Plan the tree: parameters, datums, Body, and feature order. Primary
   additive form, then cuts, then patterns, then topology-sensitive fillets
   and chamfers. See `freecad://guide/features`.
1. Call `get_connection_status` and `get_freecad_version` once.
1. Create the document, the Body, and the variable set. Define governing and
   derived variables in one compact `define_variables` batch. See
   `freecad://guide/parameters`.
1. Build one sketch or feature group at a time. Trust the local validation
   returned by each mutation; carry `document_ref` and `expected_revision`
   forward. Use `query_objects` for bounded lookups rather than retrieving the
   whole tree.
1. Verify numerically after each meaningful feature group with
   `validate_document(require_single_solid=true)`.
1. Verify visually. Deterministic checks prove validity, not intent. Read
   `freecad://guide/visual-evidence` before capturing, and use
   `capture_feature_view` to look along each opening's own support normal.
1. Save early. The moment the model first satisfies the brief, save the FCStd
   and export the STEP, before any refinement.
1. On a rejection, repair the smallest responsible input and rerun only that
   operation. See `freecad://guide/repair`.
1. Produce the variants and evidence the brief actually asks for. See
   `freecad://guide/variants` and `freecad://guide/delivery`.

## Handoff

Report the saved FCStd path, the exported STEP path, the retained images you
inspected, the checks that actually ran with their results, the assumptions
you took, and the limitations that remain. Report tool versions, the ordered
feature tree, and any topology-sensitive reference you could not avoid.

## Non-Negotiables

These hold for every part, however small.

- Every driving sketch reports `FullyConstrained` before the feature that
  consumes it is created.
- `validate_document(require_single_solid=true)` passes before any claim that
  the part is finished.
- The FCStd is saved and the STEP exported as soon as the shape first
  satisfies the brief, before any refinement. An unsaved model is not a
  deliverable.
- Every semantic opening or profile is seen along its own support normal,
  through `capture_feature_view`, before it is called correct.
- A `warnings` entry on a mutation result is unfinished work. Resolve it, or
  record why it is acceptable.
- Derived values are expressions. Never copy a calculated number between
  features.
- Intended unions have real overlap; point or tangent contact is not
  connectivity.
- Report only checks that actually ran. Never describe an image you did not
  receive and inspect.

## Progressive Guide Topics

Read these when their trigger applies.

- `freecad://guide/brief` — turning prose, an image, or a drawing into a brief.
- `freecad://guide/visual-evidence` — the capture protocol. Read before
  capturing evidence.
- `freecad://guide/parameters` — variable sets, units, and expression binding.
- `freecad://guide/features` — feature order, datums, overlap, and through-cuts.
- `freecad://guide/variants` — isolated one-edit variant transactions.
- `freecad://guide/repair` — `VALIDATION_FAILED`, `STALE_REVISION`, and undo.
- `freecad://guide/delivery` — manifests, READMEs, and re-import evidence.
```

- [ ] **Step 4: Run tests and the linter**

Run: `uv run pytest tests/unit/test_guidance.py tests/unit/test_parametric_profile.py -v`
Expected: PASS.

Run:
`uv run pre-commit run markdownlint-cli2 --files src/freecad_mcp/PARAMETRIC_PARTS_GUIDE.md`
Expected: Passed.

- [ ] **Step 5: Commit**

```bash
git add src/freecad_mcp/PARAMETRIC_PARTS_GUIDE.md tests/unit/test_guidance.py
git commit -m "docs: rewrite the parametric guide as a compact process core"
```

---

### Task 5: Bridge support for a support-normal capture

**Files:**

- Create: `src/freecad_mcp/bridge/view_code.py`
- Modify: `src/freecad_mcp/bridge/base.py`
- Modify: `src/freecad_mcp/bridge/xmlrpc.py`
- Modify: `src/freecad_mcp/bridge/socket.py`
- Modify: `src/freecad_mcp/bridge/embedded.py`
- Test: `tests/unit/test_bridge_screenshot_codegen.py`

**Interfaces:**

- Consumes: `ScreenshotResult`, `execute_python(code, transaction=None)`.
- Produces:
  `build_feature_view_code(normal_source: str, side: str, focus: list[str] | None, padding: float, hide_construction: bool, width: int, height: int, doc_name: str | None) -> str`
  and, on every bridge,
  `capture_feature_view(...) -> ScreenshotResult` with the same argument names.
  Task 6 calls the bridge method.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_bridge_screenshot_codegen.py`:

```python
class TestFeatureViewCodegen:
    """The generated capture code is where correctness actually lives."""

    def test_code_checks_gui_before_touching_the_view(self):
        from freecad_mcp.bridge.view_code import build_feature_view_code

        code = build_feature_view_code(
            normal_source="WindowSketch",
            side="front",
            focus=None,
            padding=0.1,
            hide_construction=True,
            width=800,
            height=600,
            doc_name=None,
        )
        assert code.index("FreeCAD.GuiUp") < code.index("setViewDirection")

    def test_code_restores_camera_and_visibility(self):
        from freecad_mcp.bridge.view_code import build_feature_view_code

        code = build_feature_view_code(
            normal_source="WindowSketch",
            side="front",
            focus=["Pocket"],
            padding=0.1,
            hide_construction=True,
            width=800,
            height=600,
            doc_name=None,
        )
        assert "setCamera(_saved_camera)" in code
        assert "finally:" in code
        assert "_restore_visibility" in code

    def test_back_side_negates_the_normal(self):
        from freecad_mcp.bridge.view_code import build_feature_view_code

        front = build_feature_view_code(
            normal_source="S", side="front", focus=None, padding=0.1,
            hide_construction=False, width=800, height=600, doc_name=None,
        )
        back = build_feature_view_code(
            normal_source="S", side="back", focus=None, padding=0.1,
            hide_construction=False, width=800, height=600, doc_name=None,
        )
        assert front != back
        assert "_side = 'back'" in back

    def test_unresolvable_source_is_a_structured_error(self):
        from freecad_mcp.bridge.view_code import build_feature_view_code

        code = build_feature_view_code(
            normal_source="Missing", side="front", focus=None, padding=0.1,
            hide_construction=False, width=800, height=600, doc_name=None,
        )
        assert '"success": False' in code
        assert "has no resolvable support placement" in code
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_bridge_screenshot_codegen.py -k FeatureView -v`
Expected: FAIL with `ModuleNotFoundError: freecad_mcp.bridge.view_code`.

- [ ] **Step 3: Write the code generator**

Create `src/freecad_mcp/bridge/view_code.py` with a module docstring and one
public function. The generated code must, in this order: check `FreeCAD.GuiUp`
and return a structured error if it is false; resolve the document; resolve
`normal_source` to an object and take its `Placement.Rotation` applied to
`Vector(0, 0, 1)`, returning the structured error
`f"{normal_source} has no resolvable support placement"` when the object is
missing or has no `Placement`; record `_saved_camera = view.getCamera()` and the
current `Visibility` of every object it will hide; hide datum planes, origins,
and construction helpers when `hide_construction` is true; call
`view.setViewDirection(_direction)` where `_direction` is the negated normal for
`side == "front"` and the normal itself for `"back"`; frame with
`view.fitAll()`, or `Gui.Selection` plus `view.fitSelection()` when `focus` is
given; call `view.saveImage(temp_path, width, height, "Current")`; and restore
visibility and camera inside a `finally:` block through a `_restore_visibility`
helper defined in the generated source, so a failed capture still restores
state. Return the same result shape `get_screenshot` returns:
`{"success": True, "data": <base64>, "format": "png", "width": ..., "height": ...}`
plus `"camera_direction"`, `"normal_source"`, `"focus"`, and
`"hidden_objects"`.

Mirror the document-activation and `FreeCADGui.updateGui()` flushing that
`XmlRpcBridge.get_screenshot` already performs, including restoring the
previously active document.

- [ ] **Step 4: Add the bridge method**

In `base.py`, next to the abstract `get_screenshot`, add an abstract
`capture_feature_view` with the argument names from the Interfaces block and a
Google-style docstring. In each of `xmlrpc.py`, `socket.py`, and `embedded.py`,
implement it by calling `build_feature_view_code(...)` and passing the result to
`self.execute_python(code, transaction=None)`, converting the result into a
`ScreenshotResult` exactly as that bridge's `get_screenshot` does.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_bridge_screenshot_codegen.py -v`
Expected: PASS, including the pre-existing parametrized bridge cases.

Run: `uv run pytest tests/unit -q`
Expected: PASS. An abstract method added to the base class breaks any bridge
that does not implement it, so a failure here names the bridge you missed.

- [ ] **Step 6: Commit**

```bash
git add src/freecad_mcp/bridge tests/unit/test_bridge_screenshot_codegen.py
git commit -m "feat: add support-normal capture to the bridges"
```

---

### Task 6: The capture_feature_view tool

**Files:**

- Modify: `src/freecad_mcp/tools/view.py`
- Modify: `src/freecad_mcp/tools/__init__.py`
- Test: `tests/unit/test_tools_view.py`
- Test: `tests/unit/test_parametric_profile.py`

**Interfaces:**

- Consumes: `bridge.capture_feature_view(...)` from Task 5;
  `_persist_screenshot`, `_screenshot_error`, `_SCREENSHOT_SEQUENCE` already in
  `view.py`.
- Produces: MCP tool `capture_feature_view` returning `CallToolResult` with a
  `TextContent` metadata block and an `ImageContent` block; the name added to
  `PARAMETRIC_TOOL_NAMES`, taking it from 54 to 55.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_tools_view.py`, inside `TestViewTools`:

```python
    @pytest.mark.asyncio
    async def test_capture_feature_view_returns_image_and_metadata(
        self, register_tools, mock_bridge
    ):
        """A capture returns a viewable image plus its camera metadata."""
        mock_bridge.capture_feature_view = AsyncMock(
            return_value=ScreenshotResult(
                success=True,
                data="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
                "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
                format="png",
                width=800,
                height=600,
                error=None,
            )
        )

        capture = register_tools["capture_feature_view"]
        result = await capture(normal_source="WindowSketch")

        assert result.isError is False
        assert any(block.type == "image" for block in result.content)
        metadata = json.loads(
            next(block for block in result.content if block.type == "text").text
        )
        assert metadata["normal_source"] == "WindowSketch"
        assert metadata["side"] == "front"
        assert metadata["path"].endswith(".png")

    @pytest.mark.asyncio
    async def test_capture_feature_view_rejects_unknown_side(
        self, register_tools, mock_bridge
    ):
        """An invalid side is refused before the bridge is touched."""
        mock_bridge.capture_feature_view = AsyncMock()

        capture = register_tools["capture_feature_view"]
        result = await capture(normal_source="S", side="sideways")

        assert result.isError is True
        mock_bridge.capture_feature_view.assert_not_called()

    @pytest.mark.asyncio
    async def test_capture_feature_view_failure_is_reported_as_error(
        self, register_tools, mock_bridge
    ):
        """A bridge failure surfaces as a tool error, not a silent success."""
        mock_bridge.capture_feature_view = AsyncMock(
            return_value=ScreenshotResult(
                success=False,
                data=None,
                error="Sketch has no resolvable support placement",
                width=800,
                height=600,
            )
        )

        capture = register_tools["capture_feature_view"]
        result = await capture(normal_source="Missing")

        assert result.isError is True
```

Append to `tests/unit/test_parametric_profile.py`:

```python
def test_capture_feature_view_is_in_the_parametric_profile():
    """The visual gate's tool must be in the default surface."""
    assert "capture_feature_view" in PARAMETRIC_TOOL_NAMES
    assert len(PARAMETRIC_TOOL_NAMES) == 55
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_tools_view.py -k capture_feature_view -v`
Expected: FAIL with `KeyError: 'capture_feature_view'`.

- [ ] **Step 3: Write minimal implementation**

In `src/freecad_mcp/tools/view.py`, inside `register_view_tools`, next to
`get_screenshot`:

```python
    @mcp.tool()
    async def capture_feature_view(
        normal_source: str,
        side: str = "front",
        focus: list[str] | None = None,
        padding: float = 0.1,
        hide_construction: bool = True,
        width: int = 800,
        height: int = 600,
        doc_name: str | None = None,
    ) -> CallToolResult:
        """Capture the model looking along a named support's own normal.

        A feature seen edge-on is not evidence about its shape. Use this for
        every semantic opening or profile: pass the sketch, datum, or feature
        that supports it as normal_source.

        Requires GUI mode - will return an error in headless mode.

        Args:
            normal_source: Name of the sketch, datum, or feature whose support
                placement defines the view normal.
            side: "front" looks against the normal; "back" looks along it.
            focus: Object names to frame. Frames the whole model if None.
            padding: Fractional padding around the framed objects.
            hide_construction: Hide datums, origins, and construction helpers
                for the capture, then restore them.
            width: Image width in pixels.
            height: Image height in pixels.
            doc_name: Document to capture. Uses the active document if None.

        Returns:
            A PNG image content block plus a JSON metadata block carrying the
            camera direction, resolved source, focus names, hidden objects,
            and the retained path.
        """
        if side not in ("front", "back"):
            return _screenshot_error(
                f"Invalid side: {side}. Options: ['front', 'back']",
                normal_source,
                doc_name,
            )

        bridge = await get_bridge()
        result = await bridge.capture_feature_view(
            normal_source=normal_source,
            side=side,
            focus=focus,
            padding=padding,
            hide_construction=hide_construction,
            width=width,
            height=height,
            doc_name=doc_name,
        )

        if not result.success or not result.data:
            return _screenshot_error(
                result.error or "Feature view capture failed",
                normal_source,
                doc_name,
            )

        try:
            payload = base64.b64decode(result.data, validate=True)
        except (binascii.Error, ValueError):
            return _screenshot_error(
                "Feature view capture returned malformed image data",
                normal_source,
                doc_name,
            )

        path = _persist_screenshot(
            payload, doc_name, f"{normal_source}_{side}", next(_SCREENSHOT_SEQUENCE)
        )
        metadata = {
            "success": True,
            "format": result.format or "png",
            "width": result.width,
            "height": result.height,
            "normal_source": normal_source,
            "side": side,
            "focus": focus,
            "document": doc_name,
            "path": path,
        }
        return CallToolResult(
            content=[
                TextContent(type="text", text=json.dumps(metadata, indent=2)),
                ImageContent(type="image", data=result.data, mimeType="image/png"),
            ]
        )
```

In `src/freecad_mcp/tools/__init__.py`, add `"capture_feature_view"` to
`PARAMETRIC_TOOL_NAMES` in alphabetical position, and update the module
docstring's tool count from 54 to 55.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_tools_view.py tests/unit/test_parametric_profile.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/freecad_mcp/tools tests/unit/test_tools_view.py \
    tests/unit/test_parametric_profile.py
git commit -m "feat: add capture_feature_view tool"
```

---

### Task 7: Prompt and documentation updates

**Files:**

- Modify: `src/freecad_mcp/prompts/parametric.py`
- Modify: `docs/guide/tools.md`
- Modify: `docs/MCP_TOOLS_REFERENCE.md`
- Modify: `CLAUDE.md`
- Test: `tests/unit/test_parametric_profile.py`

**Interfaces:**

- Consumes: `PARAMETRIC_PARTS_GUIDANCE` from Task 4; `PARAMETRIC_TOOL_NAMES`
  from Task 6.
- Produces: no new code interfaces.

CLAUDE.md requires that a tool change updates the capabilities resource, the
prompts, the guide, `docs/guide/tools.md`, and CLAUDE.md's own tool count.
Tasks 3, 4 and 6 covered the first three.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_parametric_profile.py`:

```python
def test_design_prompt_carries_the_core_guidance():
    """The prompt and the instructions must not drift apart."""
    from freecad_mcp.guidance import PARAMETRIC_PARTS_GUIDANCE

    mcp = _prompt_registry()
    from freecad_mcp.prompts.parametric import register_prompts

    register_prompts(mcp, AsyncMock())
    prompt = mcp._registered_prompts["design_parametric_part"]

    import asyncio

    text = asyncio.run(prompt(description="a bracket"))
    assert PARAMETRIC_PARTS_GUIDANCE in text
    assert "a bracket" in text
```

- [ ] **Step 2: Run test to verify it passes or fails**

Run: `uv run pytest tests/unit/test_parametric_profile.py -k design_prompt -v`
Expected: PASS if `design_parametric_part` still interpolates
`PARAMETRIC_PARTS_GUIDANCE`; FAIL if the rewrite in Task 4 left stale wording in
the prompt's trailing instructions. If it fails, fix the prompt so it composes
the core rather than restating it.

- [ ] **Step 3: Update the prompt's trailing text**

In `src/freecad_mcp/prompts/parametric.py`, the `design_parametric_part` body
after the interpolated guidance currently repeats the workflow. Reduce it to the
task framing only — description, units, output directory — plus one line telling
the model to follow the workflow above and read the progressive guide topics it
triggers. Remove any sentence that duplicates a step now in the core.

- [ ] **Step 4: Update the three documentation files**

- `docs/guide/tools.md`: change the tool count in the header from 54 to 55, and
  add `capture_feature_view` to the view/screenshot category table. Keep the
  table padded and aligned (MD060).
- `docs/MCP_TOOLS_REFERENCE.md`: add the exact signature and argument
  descriptions from Task 6's docstring.
- `CLAUDE.md`: in the "FreeCAD Robust MCP Tools Reference" section, change "54
  tools" to "55 tools", and add `capture_feature_view` to the Validation or
  view line of the Default Native Workflow list.

- [ ] **Step 5: Run tests and linters**

Run: `uv run pytest tests/unit -q`
Expected: PASS.

Run:
`uv run pre-commit run --files src/freecad_mcp/prompts/parametric.py docs/guide/tools.md docs/MCP_TOOLS_REFERENCE.md CLAUDE.md`
Expected: Passed.

- [ ] **Step 6: Commit**

```bash
git add src/freecad_mcp/prompts/parametric.py docs/guide/tools.md \
    docs/MCP_TOOLS_REFERENCE.md CLAUDE.md tests/unit/test_parametric_profile.py
git commit -m "docs: update prompt and tool references for capture_feature_view"
```

---

### Task 8: Full check, then the benchmark configuration

**Files:**

- Modify: `../experiments/parametric-lighthouse-workflow-comparison/brief-freecad.md`
- Create: `../experiments/parametric-lighthouse-workflow-comparison/lighthouse-part.md`
- Modify: `../experiments/parametric-lighthouse-workflow-comparison/run_all.sh`
- Modify: `../experiments/parametric-lighthouse-workflow-comparison/config/freecad-mcp.json`
- Modify: `../experiments/parametric-lighthouse-workflow-comparison/config/freecad-mcp-local.json`
- Modify: `../experiments/parametric-lighthouse-workflow-comparison/config/freecad-mcp-local-v2.json`
- Create: `../experiments/parametric-lighthouse-workflow-comparison/stage-e-condition.md`

Paths are relative to `/home/pepijn/code/cadbench/`. That directory is **not a
git repository**, so these changes are not committed. Do not create one.

**Interfaces:**

- Consumes: the finished server from Tasks 1 to 7.
- Produces: a benchmark condition whose only injected context is the task and
  the harness policy.

- [ ] **Step 1: Run the full server check**

Run: `just all`
Expected: every quality check and unit test passes. Fix anything it reports
before touching the benchmark.

- [ ] **Step 2: Verify the handshake actually carries the new core**

Run:

```bash
cd /home/pepijn/code/cadbench/freecad-addon-robust-mcp-server
uv run python -c "
from freecad_mcp.server import mcp
print(mcp.instructions.splitlines()[0])
print('topics:', mcp.instructions.count('freecad://guide/'))
"
```

Expected: `# Native Parametric FreeCAD Parts` and `topics: 14` — seven pointers
in the workflow steps plus seven in the topic list. If the count is lower, a
pointer is missing and Task 4's test should have caught it.

- [ ] **Step 3: Split the brief**

Create `lighthouse-part.md` containing only the part specification from
`brief-freecad.md`: the opening design sentence, Shape Requirements, the
governing variable list, and Parametric Variants. Leave out Modeling Method,
Incremental Gates, Visual Gate, Save Early, and Deliverables — the server now
owns all five — and leave out the operator-owned-process and
assigned-directory paragraphs, which move to the runner.

Keep `brief-freecad.md` unchanged on disk. It is the frozen input for Stages B
through D and must stay readable as those runs' provenance.

- [ ] **Step 4: Point the runner at the new brief**

In `run_all.sh`, set `BRIEFS[freecad-mcp]`, `BRIEFS[freecad-mcp-local]`, and
`BRIEFS[freecad-mcp-local-v2]` to `$ROOT/lighthouse-part.md`. Append the harness
policy to those conditions' `INSTRUCTIONS` entries, which already carry the
operator-owned-process rule; add the assigned-directory rule: `Work only in the
assigned empty run directory and do not inspect parent or sibling experiment
directories.`

- [ ] **Step 5: Drop the duplicated instructions from the configs**

Remove the entire `"instructions"` array from `config/freecad-mcp.json`,
`config/freecad-mcp-local.json`, and `config/freecad-mcp-local-v2.json`. The
MCP handshake now delivers that text once.

- [ ] **Step 6: Record the condition**

Create `stage-e-condition.md` in the style of `stage-d-condition.md`, recording:
the server commit implementing this plan; that the core guide, the seven topic
resources, and `capture_feature_view` are new; that the duplicate instruction
copy was removed; that the brief was split; and that Stage E is therefore a new
versioned condition rather than an A/B against Stage D.

- [ ] **Step 7: Verify the condition starts cleanly**

With the operator's FreeCAD and bridge already running, and without starting or
restarting either:

```bash
cd /home/pepijn/code/cadbench/experiments/parametric-lighthouse-workflow-comparison
curl --fail --silent --max-time 5 -H "Content-Type: text/xml" \
  --data '<?xml version="1.0"?><methodCall><methodName>ping</methodName><params></params></methodCall>' \
  http://127.0.0.1:9875 | grep -q pong && echo "bridge ready"
```

Expected: `bridge ready`. Do not launch a benchmark run as part of this plan;
starting Stage E is the operator's decision.

---

## Self-Review

**Spec coverage:** Core rewrite → Task 4. Seven topic documents → Task 2.
Resources with pointers → Tasks 3 and 4. The pointer-honesty test the spec asks
for → Task 4, both directions. `capture_feature_view` → Tasks 5 and 6. The
floors → Task 4's `test_core_states_the_floors`. Repair topic naming
`VALIDATION_FAILED` and `STALE_REVISION` → Task 2. Benchmark keeps pinned
injection minus duplication → Task 8. Files-changed table rows all appear:
`guidance.py` (1), `guides/*.md` (2), `resources/parametric.py` (3),
`PARAMETRIC_PARTS_GUIDE.md` (4), `bridge/*` (5), `tools/view.py` and
`tools/__init__.py` (6), `prompts/parametric.py`, `docs/guide/tools.md`,
`docs/MCP_TOOLS_REFERENCE.md`, `CLAUDE.md` (7), tests throughout.

**Non-goals honored:** no section views, no acceptance evaluator, no evidence
manifest, no change to the transaction contract.

**Type consistency:** `build_feature_view_code` and `capture_feature_view` take
the same argument names in Tasks 5 and 6 — `normal_source`, `side`, `focus`,
`padding`, `hide_construction`, `width`, `height`, `doc_name`. `load_guide` and
`GUIDE_TOPICS` are used identically in Tasks 1, 2, 3 and 4. `ScreenshotResult`
is the return type in Tasks 5 and 6.

**Known risk carried deliberately:** Task 5 adds an abstract method to the
bridge base class, which breaks any bridge that does not implement it. Step 5 of
that task runs the whole unit suite specifically to surface that.
