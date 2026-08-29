# Declarative and Code-First Parametric CAD Landscape

**Research snapshot: 2026-08-23.** This report uses first-party manuals, API
documentation, and project repositories only. “Declarative” is used narrowly:
the source describes the desired shape or dependency graph, rather than a
general-purpose program that happens to call modeling functions.

## Executive Summary

There is no single open local system that combines all of these properties:

- human-readable source as the authoritative model;
- robust exact B-rep mechanical geometry;
- a mature sketch constraint solver;
- stable semantic references across topology changes; and
- a native editable FreeCAD document as output.

The best current choices depend on the objective:

1. **Best small-model source language:** OpenSCAD. It is genuinely
   source-first and deterministic, but is primarily CSG/mesh-oriented and has
   no sketch solver or native feature semantics.
2. **Best local mechanical code-CAD target:** CadQuery or build123d. Both use
   OpenCascade B-rep geometry and export STEP. They are Python APIs, not
   declarative languages; build123d's Builder mode gives the clearest
   history-like structure.
3. **Best constraint-driven local editor:** Dune 3D for an open, modern,
   offline application; SolveSpace for a mature, compact constraint-driven
   tool. Neither has a textual source format intended as the primary model
   interface.
4. **Best source-native parametric design language:** KCL. It explicitly makes
   code the source of truth, supports names, formulas, units, modules, tags,
   and a broad 2D sketch-constraint solver. Its normal geometry engine is not
   a local FreeCAD backend.
5. **Best interoperability strategy for this project:** generate a compact
   declarative intermediate representation, compile it to FreeCAD Python
   features/sketches where possible, and use STEP only as a deliberate
   fallback. Imported STEP preserves solid geometry, not the originating
   parameters, constraints, feature history, or source references.

## Classification

| System | What it actually is | Representation/kernel | Parameters and constraints | Source/history and maturity |
| --- | --- | --- | --- | --- |
| **OpenSCAD** | A small, source-first language evaluated like a 2D/3D compiler. The language builds CSG trees, extrusions, transforms, and modules. | CSG evaluated by CGAL; final render is a tessellated mesh. | Variables, expressions, modules, conditionals, and loops; no sketch constraint solver. | `.scad` is the source of truth. Mature, portable, offline. Exports STL, 3MF, OFF, AMF, DXF, SVG, and CSG. [Project](https://openscad.org/documentation.html) [Source](https://github.com/openscad/openscad) |
| **ImplicitCAD** | A Haskell mathematical/programmatic CAD system with an OpenSCAD-like `extopenscad` frontend. | Implicit/functional-style 2D and 3D geometry plus CSG; output is principally rendered/exported geometry. | Haskell expressions and functions; no conventional sketch solver or feature tree. | Source is text and local; project is established but comparatively low-activity and narrow for production mechanical CAD. [Repository](https://github.com/Haskell-Things/ImplicitCAD) |
| **libfive** | An implicit-solid modeling library, bindings, and Studio live-coding application. This is a modeling framework, not a complete mechanical feature modeler. | F-reps/implicit functions, CSG, and adaptive watertight triangle meshing. | Functional composition, values, and shape expressions; no mechanical sketch solver or B-rep semantic topology. | Python/Guile/C bindings and scripts are local; source-first for models. Strong kernel concept, but mesh-oriented output limits CAD interchange. [Repository](https://github.com/libfive/libfive) [Guide](https://github.com/libfive/libfive/blob/master/doc/guide.md) |
| **CadQuery** | Python code calling a CAD modeling API. It is procedural/functional code-first, not a declarative language. | Exact OpenCascade B-rep through OCP. | Python variables/formulas, Workplane/Sketch operations, tags, and selectors; no general constraint solver. | Python is the only fully parametric format; selectors query geometry but are not guaranteed semantic IDs under every topology change. Mature and local. STEP, DXF, SVG, STL, AMF, 3MF, and others. [Intro](https://cadquery.readthedocs.io/en/stable/intro.html) [Export](https://cadquery.readthedocs.io/en/latest/importexport.html) [Selectors](https://cadquery.readthedocs.io/en/latest/selectors.html) |
| **build123d** | Python B-rep API derived from CadQuery. Algebra mode is explicit shape arithmetic; Builder mode tracks context and operations in a history-like way. | OpenCascade B-rep. | Python formulas and named objects; selectors and topology queries; no full sketch constraint solver. | Python source is authoritative. Local and active. Builder mode is useful for LLM generation, but it is still an API program rather than a declarative model file. STEP/STL/3MF and other standard exports. [Repository](https://github.com/gumyr/build123d) [Concepts](https://build123d.readthedocs.io/en/stable/key_concepts_algebra.html) |
| **KCL / Zoo** | A dedicated functional language for CAD. Unlike ordinary CAD scripting, the project explicitly says KCL is the source of truth and GUI actions edit the code. | Zoo/KittyCAD geometry engine; KCL exposes sketches, solids, surfaces, and operations through a standard library. | Named values, formulas, units, functions, modules, assertions, tags, and a sketch solver with geometric and dimensional constraints. | Text `.kcl` is first-class and version-control friendly. Design Studio is active, but the hosted/engine-centric workflow is a concern for fully offline use. [KCL docs](https://zoo.dev/docs/kcl) [Sketch solver](https://zoo.dev/docs/kcl-std/modules/std-solver) [Project rationale](https://zoo.dev/research/introducing-kcl) |
| **SolveSpace** | A constraint-driven interactive parametric CAD application, not a textual CAD language. | Triangle meshes for robust operations or exact NURBS surfaces for STEP. | Strong 2D/3D geometric constraint solver; arithmetic expressions and dimensions. | Native document/interactive history is the source, not text. Mature, compact, local. Exports STEP, STL, OBJ, DXF, SVG, PDF, EPS, HPGL, and G-code. [Features](https://solvespace.com/features.pl) [Reference](https://solvespace.com/ref.pl) |
| **Dune 3D** | An open parametric 3D CAD editor with 2D/3D sketches and constraints. | OpenCascade for solids and booleans; SolveSpace-derived solver work, with project-specific performance changes. | Broad 2D/3D constraints, dimensions, formulas/parameters, fillets, chamfers, and STEP reference import. | Native document and GUI are primary; no stable textual source-of-truth format. Local on Linux and Windows; younger than SolveSpace. STEP and STL. [Project](https://dune3d.org/) [Constraints](https://docs.dune3d.org/en/latest/constraints.html) [Repository](https://github.com/dune3d/dune3d) |
| **Fornjot** | Rust libraries for direct code-first CAD and an early experimental kernel. | B-rep kernel in Rust with modular topology/geometry libraries. | Rust code and APIs; no mature sketch solver or feature-history language. | Code-first and local, but explicitly early-stage and unsuitable as a production mechanical backend today. Current examples export 3MF and other formats through `fj-export`. [Repository](https://github.com/hannobraun/Fornjot) [API](https://docs.rs/fj/latest/fj/) |
| **JSCAD** | JavaScript modular browser/CLI tools for reproducible parametric designs. | Primarily CSG/mesh-oriented JavaScript geometry packages. | JavaScript values, functions, and modules; no mechanical sketch solver or semantic feature history. | JS source is authoritative; local Node CLI or self-hosted web UI is available. Mature for printable/code-generated geometry. Common exports include STL, 3MF, AMF, DXF, SVG, OBJ, and X3D. [Repository](https://github.com/jscad/OpenJSCAD.org) |
| **replicad** | Browser-oriented JavaScript/TypeScript abstraction over OpenCascade. | OpenCascade B-rep. | JS formulas and API composition; sketches and selectors, but no general constraint solver or native feature tree. | Source is code; local browser execution is possible. Active enough to remain useful, but smaller and less mature than CadQuery/build123d for mechanical automation. STEP/STL-oriented workflows. [Repository](https://github.com/sgenoud/replicad) |
| **CascadeStudio** | A browser IDE and reusable engine for live-scripted CAD. It supports JavaScript and an OpenSCAD mode. | OpenCascade 8 through `opencascade.js`; B-rep, meshed for display. | JS/OpenSCAD source, selectors, sketches, and a visible modeling timeline; no conventional sketch constraint solver. | Code and serialized projects are first-class; installable as an offline PWA and has a `cascade-core` package. Active repository evidence includes 2026 commits, but it remains a specialized browser tool. STEP/IGES/STL import; STEP/STL/OBJ export. [Repository](https://github.com/zalo/CascadeStudio) |
| **Onshape FeatureScript** | A typed language for defining custom features inside Onshape's parametric Part Studio. It is not a standalone local CAD kernel. | Onshape's server-side exact modeler and topology/query system. | Feature parameters, types, queries, robust geometric references, and feature outputs; the surrounding Part Studio supplies the feature history and constraints. | FeatureScript source is editable in Feature Studios, but the document/cloud runtime is the source of the complete model. Powerful and mature, not offline. [Official guide](https://cad.onshape.com/FsDoc/) |
| **Grasshopper** | Visual dataflow/algorithmic modeling environment, generally hosted by Rhino. | Rhino's NURBS/B-rep/mesh geometry, depending on components. | Named sliders, expressions, component graphs, and plugins; constraints are not its core sketch-solver model. | A `.gh`/`.ghx` graph is editable, but it is a serialized visual program rather than plain text. Mature, desktop/local, broad interoperability through Rhino. [McNeel guide](https://developer.rhino3d.com/guides/grasshopper/) |
| **Dynamo** | Visual programming environment for computational design, commonly used with Revit and Civil 3D. | Host-dependent: Revit's parametric model or Dynamo geometry libraries. | Inputs, formulas, nodes, lists, and host queries; not a general mechanical sketch constraint system. | `.dyn` is serialized graph data, not a concise textual source language. Mature in its host ecosystem but heavyweight for standalone local mechanical generation. [Primer](https://primer.dynamobim.org/) [Source](https://github.com/DynamoDS/Dynamo) |
| **FreeCAD** | The strongest relevant open local target: a document/feature-tree application with Python automation and Sketcher constraints. | OpenCascade B-rep, meshes, and FreeCAD document objects. | Spreadsheet expressions, named properties, PartDesign feature history, Sketcher solver, and Python. Topology naming remains a known modeling concern rather than a universal semantic layer. | `.FCStd` plus generated Python can preserve editability when built as native features. Local/offline and mature. Native document, STEP/IGES/STL/3MF/OBJ/DXF and more. [FreeCAD documentation](https://wiki.freecad.org/) |

## What “Parametric” Means Here

These systems should not be evaluated as one category:

- **Declarative/source-defined:** OpenSCAD and KCL most clearly define a model
  from source. libfive and ImplicitCAD are mathematical shape descriptions,
  but their semantics are implicit geometry rather than mechanical feature
  intent.
- **Procedural code-first:** CadQuery, build123d, replicad, CascadeStudio,
  JSCAD, and Fornjot execute a program that constructs shapes. They are highly
  parameterizable, but changing control flow can change the model graph.
- **Constraint/feature editors:** SolveSpace, Dune 3D, FreeCAD, and Onshape
  solve a constraint or feature graph stored in a document. Their user-facing
  model is more semantically mechanical, but their native documents are not
  normally compact textual source.
- **Visual parametrics:** Grasshopper and Dynamo are graph programs. Their
  graphs can be edited and versioned, but the source is serialized UI/dataflow
  state rather than a small language with a stable textual grammar.

Semantic topology is the key dividing line. A selector such as “highest
vertical edge” is a useful geometric query, but it is not the same as a stable
design-intent reference such as “the mounting-face edge created by feature X.”
Onshape FeatureScript and native feature editors have the strongest query and
history machinery. CadQuery/build123d/CascadeStudio provide practical queries;
they need deliberate tagging, geometric selectors, or explicit intermediate
objects to reduce topology fragility. CSG and implicit systems avoid many B-rep
topology naming problems, but also do not expose mechanical face/edge intent in
the same way.

## FreeCAD Interoperability

| Source system | Best integration path | What survives | What collapses |
| --- | --- | --- | --- |
| OpenSCAD, JSCAD, ImplicitCAD, libfive | Export STL/3MF for visualization/printing, or translate primitives/booleans into FreeCAD Python. | Mesh shape, or a newly generated native feature graph if a translator is written. | Standard mesh import loses dimensions, formulas, constraints, and history. |
| CadQuery, build123d, replicad, CascadeStudio | Run the source locally, export STEP, or write a compiler that emits FreeCAD Python/PartDesign operations. | STEP preserves exact B-rep geometry and often useful names are not guaranteed to map to design intent. | Python/JS source, formulas, operation graph, and selectors are not embedded as editable FreeCAD features by STEP. |
| KCL | Use its own engine for source evaluation, then export a supported exchange format; alternatively target a restricted KCL subset and emit FreeCAD Python. | Exported solid and possibly assembly-level exchange data. | KCL functions, tags, source locations, and runtime semantics do not become native FreeCAD parameters automatically. |
| SolveSpace/Dune 3D | Export STEP, or build an importer/translator for their native documents. | Exact STEP geometry where supported. | Sketch constraints and feature intent are generally lost through STEP. |
| Onshape FeatureScript | Export from Onshape or reproduce selected feature logic in FreeCAD Python. | Exchange geometry. | Cloud document, FeatureScript feature definitions, queries, and history are not carried by STEP. |
| Grasshopper/Dynamo | Export STEP/mesh, or write a host-specific bridge. | Result geometry and selected metadata. | Graph nodes, host object identity, and graph-driven dependencies are not native FreeCAD history. |

For this repository, the high-value compiler target is not an arbitrary foreign
CAD format. It is a constrained intermediate representation that can choose
between native FreeCAD objects:

```text
parameters/formulas -> sketches + constraints -> PartDesign features
                    -> named intermediate objects -> validation/export
```

External code-CAD systems can be adapters into that representation. STEP is a
reliable interchange fallback, not an editability-preserving compilation
target.

## Suitability for a 64K Local LLM

The model-size assumption favors systems with short, regular syntax, local
execution, deterministic diagnostics, and a small number of stable concepts.

| Rank | Recommendation | Why |
| --- | --- | --- |
| 1 | **Restricted FreeCAD-native IR plus generated Python/Sketcher** | Best final artifact: native constraints, expressions, feature history, and `.FCStd`. Keep the IR narrower than the full FreeCAD API and validate after every feature. |
| 2 | **build123d** | Python is familiar to the model, B-rep is manufacturing-capable, and Builder mode provides a readable sequence. Use explicit named objects and avoid brittle index selectors. |
| 3 | **CadQuery** | Very good OpenCascade and STEP path, strong documentation and examples, but Workplane stack behavior and selectors require careful generation and repair. |
| 4 | **OpenSCAD** | Easiest generation and repair loop, fully local and source-first. Excellent for prismatic CSG and fixtures; weak for sketches, constraints, fillets, and semantic mechanical intent. |
| 5 | **KCL** | Best language design for source-of-truth CAD and reusable parametric modules, including constrained sketches. Penalized by dependence on the KittyCAD/Zoo geometry runtime rather than a native local FreeCAD backend. |
| 6 | **Dune 3D / SolveSpace** | Best when the user must interactively solve sketches locally. Less suitable as an LLM source target because the editable truth is a native document, not a compact text grammar. |
| 7 | **CascadeStudio / replicad** | Attractive for browser automation and OpenCascade-backed code, with selectors and source files. Less suitable than Python options for a local engineering pipeline. |
| 8 | **JSCAD / libfive / ImplicitCAD** | Excellent for generative, printable, or organic mathematical shapes; generally poor final targets for editable mechanical B-rep designs. |
| 9 | **Fornjot** | Architecturally interesting and local, but its own documentation identifies it as early-stage and experimental. |
| 10 | **Grasshopper/Dynamo and FeatureScript** | Powerful ecosystems, but either graph serialization or cloud/host coupling makes them poor default local-LLM targets. FeatureScript is valuable as a reference for robust queries and feature semantics. |

The practical design rule is to ask the model to generate **intent-bearing
objects**, not arbitrary geometry calls: named dimensions, named sketches,
explicit constraints, feature inputs, stable reference labels, and assertions
about volumes/clearances. That is the common subset that can be represented in
FreeCAD, approximated in CadQuery/build123d, or degraded to a final STEP shape
with an explicit warning.

## Sources

All links in the comparison table are first-party project documentation,
official API references, or the project's own source repository. In
particular, KCL's source-of-truth and sketch-constraint claims come from Zoo's
own current KCL material; the maturity caveat for
Fornjot comes from its repository/API description; and the CascadeStudio
activity/interoperability claims come from its repository README and package
layout.
