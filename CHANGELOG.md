# Changelog

All notable feature work on CHEAT. Newest first.

## 2026-07-17 — Co-brand splash (Cisco × Victoria University)

- The Rich splash can now co-brand with Victoria University. A **`SPLASH_DESIGN`**
  preference (Options → `J`) cycles three logos:
  - **`diamond`** (default) — VU halftone diamond mark beside the Cisco bars.
  - **`lockup`** — VU diamond + `VICTORIA UNIVERSITY` wordmark badge beside the bars.
  - **`generic`** — original Cisco-only splash, no VU branding.
- Co-brand designs append a red **`× Victoria University`** tag to the
  `CISCO · DNA CENTER` wordmark. VU navy/white sampled from the official mark.
- `python splash_rich.py [design]` previews one design; no arg cycles all three.
- `splash_generic.py` keeps a standalone snapshot of the pre-co-brand splash.

## 2026-07-15 → 2026-07-17

### CDP Physical Topology Export (`*-cdp-topology.drawio`)

A new draw.io diagram, written alongside the combined Excel report on every bulk
scan, showing the physical switch topology discovered from CDP.

- **Graphviz layout engine.** Topology is laid out and routed by the Graphviz
  `dot` binary (system dependency — see README). Nodes are ranked into a tree
  with aggregation/distribution switches pulled toward the top. Large sites are
  split across multiple A3 pages plus an Overview page.
  (`topology_dot.py`, `drawio_generator.py`, `cheat_core.py`)
- **Robust `dot` discovery.** `dot` is located via the `DOT`/`GRAPHVIZ_DOT`
  environment overrides, then PATH, then the common Windows install
  directories — so a `winget`/`choco` install that never added Graphviz to PATH
  still works. If `dot` genuinely cannot be found, the topology is skipped with a
  reminder and all other outputs are produced normally.
- **Curved edges.** Links render as curved splines with port labels anchored
  near the downstream switch. Layout uses `spline` mode with an `ortho`
  fallback, so a page is never silently dropped if one layout mode fails.
- **Parallel links preserved.** Dual/VSS uplinks that land on the same remote
  device via two local interfaces are kept as separate links (previously
  collapsed by node-pair dedup). Parallel port labels between the same pair are
  aggregated into a single comma-joined label.
- **Rogue-node context.** Each unscanned ("rogue") neighbour node shows its
  hostname, model, mgmt IP, and the interface description of the scanned port
  that feeds it (blank lines omitted when a field is empty).
- **Device-icon toggle (`I`).** Nodes render either as Cisco Visio-style
  stencil icons (built into draw.io — no bundled assets) or as plain rectangles.
  Scanned switches are grey; rogue neighbours are red. Toggle in
  **Options → `I) Topology icons`**; default is `stencil`.

### CDP Detail Enrichment

- Switched the topology/report data source to `show cdp neighbors detail`,
  parsed into rich records carrying management IP and full platform/model.
  (`cdp_detail.py`, `cdp_topology.py`)
- The port-utilisation report's unscanned-switch block gained a **Mgmt IP**
  column and a **CDP Neighbors** column derived from the detail output.

### Unscanned ("Rogue") Cisco Switches

- The port-utilisation summary now lists every Cisco switch seen via CDP that
  was **not** explicitly scanned in the session — surfacing gaps in coverage.
  (`unscanned_switches.py`)

### Concurrent Command Execution

- Device commands now run through a bounded thread pool so multiple stacks are
  queried at once instead of strictly sequentially. Concurrency is selectable
  1–5 (default 2) via the Menu 5 `c` toggle. (`main_latest.py`, `cheat_core.py`)

### Fixes & Polish

- **3560 model field.** A standalone Catalyst 3560 now populates its model
  correctly (read from the slot-0 port table rather than the member-1 stack
  table). (`interface_parser.py`)
- **Splash logo.** Fixed distortion of the Rich Cisco splash banner caused by
  per-line centering of the ASCII bars. (`splash_rich.py`)
