# CDP Topology Layout Overhaul (Graphviz) — Design

**Date:** 2026-07-17
**Status:** Approved

## Problem

The current CDP topology export lays nodes on a naive BFS grid with straight
edges and no routing. On a real 105-node / 133-edge site it spreads nodes from
x=0 to x≈13,550 with links cutting straight through everything — unreadable.
Worse, the real aggregation switches (the distribution `dist-4500xv`) are
*unscanned*, and the layout roots on the highest-degree *scanned* switch, so the
true top-of-tree gets dumped to the side.

## Goal

Replace the layout/rendering with a Graphviz-driven pipeline: the highest-degree
switch (scanned or not) sits top-centre, the tree branches downward, and edges
are routed to avoid overlap. Output an **editable multi-page `.drawio`**: an
overview canvas plus one A3-landscape page per distribution/aggregation.

## Decisions (from brainstorming)

- **Engine:** Graphviz `dot`, invoked as a subprocess (`-Tplain`) — no
  `pygraphviz` (avoids the C build). `splines=ortho` for node-avoiding
  orthogonal routing.
- **Root:** the max-degree node **overall** (scanned or rogue).
- **Scale:** an overview page + per-aggregation A3 pages.
- **Output:** editable multi-page `.drawio` (Graphviz coordinates → node
  geometry; parsed edge bend-points → draw.io waypoints).
- Reuse the existing graph model (`cdp_topology.build_topology`).

## Dependency: Graphviz (system binary)

The `dot` binary is a system dependency, not a pip package.

- `requirements.txt` gains a comment block documenting it (and, optionally, the
  `graphviz` pip wrapper — not required since we call `dot` directly).
- `README.md` gains install instructions:
  - **Linux (Debian/Ubuntu):** `sudo apt install graphviz`
  - **Linux (RHEL/Fedora):** `sudo dnf install graphviz`
  - **Windows:** `winget install Graphviz.Graphviz` (or `choco install graphviz`),
    or download from graphviz.org and add its `bin\` to `PATH`.
  - **macOS:** `brew install graphviz`
- **`dot` not found** → the topology step is skipped with a clear message
  (`⚠ CDP topology needs Graphviz — install with 'apt install graphviz' (Linux)
  or 'winget install Graphviz.Graphviz' (Windows)`); the Excel report and every
  other output are unaffected.

## Components

### `topology_dot.py` (new — pure: DOT generation, plain parsing, paging)

- `to_dot(topology, node_names, root_name, a3=False) -> str`
  - Builds a Graphviz DOT digraph for the given subset of node names.
  - Stable integer ids (`n0`, `n1`, …) with a name↔id map (real names have dots
    and hyphens; ids keep the DOT valid and the plain output parseable).
  - Node attrs: `shape=box, style=filled`, grey fill for scanned, red
    (`#f8cecc`/`#b85450`) for rogue, `label` = the display label (below).
  - Direction: edges oriented parent→child along a BFS spanning tree rooted at
    `root_name` (downward); non-tree/redundant edges get `constraint=false` so
    they are drawn but do not distort ranks. `rankdir=TB`.
  - Edge attr `label` = `"<a_port> ↔ <b_port>"`.
  - Graph attrs: `splines=ortho`, tuned `nodesep`/`ranksep`; when `a3=True`,
    `size="16.5,11.7!"` + `ratio=compress` to target A3 landscape.

- `parse_plain(plain_text) -> ParsedLayout`
  - Parses `dot -Tplain`: `graph scale w h`; `node <id> x y w h label ...`;
    `edge <tail> <head> <n> x1 y1 … [label lx ly] …`; `stop`.
  - Returns node boxes `{id: (x, y, w, h)}` and edge routes
    `[(tail_id, head_id, [(x,y), …], label)]`, in Graphviz inch units with a
    bottom-left origin.

- `select_aggregations(topology, threshold=6) -> list[str]`
  - Node names whose CDP-neighbour degree ≥ `threshold`, sorted by degree desc
    then name. (Default 6 isolates the `dist-4500xv` hubs from access switches.)

- `build_pages(topology, threshold=6) -> list[Page]`
  - `Page(title, node_names, root_name)`.
  - **Overview** page: all node names, root = global max-degree node.
  - **Per-aggregation** pages: for each aggregation `A`, the page holds `A` plus
    its **2-hop downward neighbourhood** — `A`'s neighbours, and those
    neighbours' further neighbours that are leaves (not themselves
    aggregations). Expansion stops at other aggregation nodes, so `dist-5`'s page
    does not swallow `dist-4`'s subtree. Root = `A`. A switch dual-homed to two
    aggregations appears on both pages (its cross-link is drawn on each).
  - If no node meets the threshold, only the overview page is produced.

### Node labels

- **Scanned:** hostname (its model/IP live in the Excel report).
- **Rogue:** `hostname / model / mgmt_ip / (unscanned)` — model and management IP
  come from the CDP-detail parser (`SwitchNeighbour.platform`/`mgmt_ip`), so the
  rogue nodes are now self-describing. Empty model/IP segments are omitted.

### `drawio_generator.py` — multi-page Graphviz emitter

- New `generate_cdp_topology_drawio(pages_with_layouts) -> str`: builds one
  `mxfile` with a `<diagram>` per page. Node `mxGeometry` from the parsed
  Graphviz box (scaled to px, **y flipped** — Graphviz is bottom-up), grey/red
  style per node. Edges use `edgeStyle=orthogonalEdgeStyle` with the parsed
  bend-points written as an `Array as="points"` of `mxPoint` waypoints, labelled
  `"<a_port> ↔ <b_port>"`. Each diagram's page size set to A3 landscape. A
  title + the grey/red legend on every page.
- The single-page `generate_cdp_topology_xml` and the BFS `layout_topology` are
  removed (replaced by this pipeline).

### `cheat_core.py` — orchestrator

- `generate_cdp_topology(raw_outputs, scanned_hostnames, filename_stem)` rewired:
  1. `topology = build_topology(...)`; if no scanned switches → skip (unchanged).
  2. If `dot` is not on `PATH` → return `(False, <install message>)`, write
     nothing.
  3. `pages = build_pages(topology)`; for each page, `to_dot` → run `dot -Tplain`
     (subprocess) → `parse_plain`.
  4. `generate_cdp_topology_drawio(...)` → write
     `drawio_exports/<stem>-<ts>-cdp-topology.drawio`.

- A small `_run_dot(dot_str) -> str | None` helper runs
  `subprocess.run(["dot", "-Tplain"], input=dot_str, ...)`, returning `None` on
  missing binary or non-zero exit (so a single bad page degrades gracefully).

## Data flow

```
build_topology -> Topology
  -> build_pages(threshold) -> [Page(title, nodes, root)]
       for each page:
         to_dot(topology, page.nodes, page.root, a3=not overview)
           -> `dot -Tplain` (subprocess) -> parse_plain -> ParsedLayout
  -> generate_cdp_topology_drawio(pages+layouts) -> multi-page .drawio
```

## Error handling

- `dot` missing or failing → skip with the install message; other outputs
  unaffected.
- A single page whose `dot` run fails is dropped with a logged note; the rest
  still render.
- No scanned switches → skip (unchanged). No aggregations → overview only.

## Testing

Unit (no `dot` needed):
- `to_dot`: valid DOT, rogue nodes carry the red fill, non-tree edges get
  `constraint=false`, edge labels present, `rankdir=TB`.
- `parse_plain`: against a canned `dot -Tplain` fixture → correct node boxes and
  edge routes (incl. an orthogonal multi-point edge).
- `select_aggregations` / `build_pages`: the max-degree node is the overview
  root; a degree-≥-threshold hub gets its own page holding its 2-hop
  neighbourhood; a dual-homed switch appears on two pages; sub-threshold-only
  graphs yield overview-only.
- `generate_cdp_topology_drawio`: from a fake `ParsedLayout`, a valid multi-page
  `mxfile` — rogue red style, an edge with `mxPoint` waypoints, A3 page size,
  y-axis flipped.
- `generate_cdp_topology` with `dot` absent (PATH mocked) → `(False, install
  message)`, nothing written.

End-to-end (real `dot`): Graphviz will be installed in the build/test
environment so a real render of a small multi-node topology is verified to open
as valid draw.io XML; if the environment cannot install it, this becomes a
documented manual check.

## Out of scope (YAGNI)

- Rendered PDF/SVG output (draw.io exports per page on demand).
- Scanned-node model/IP labels (kept to hostname; details are in the Excel).
- Configurable per-page layout tuning beyond the aggregation threshold.
