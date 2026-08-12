# Changelog

All notable feature work on CHEAT. Newest first.

## 2026-08-12 — Dual DNAC credentials + splash de-brand

### Menu 1 — two controllers

- **`1) Use Legacy DNAC`** (was `1) Use dnac.env`) — behaviour unchanged, reads
  `dnac.env`.
- **`2) Use New DNAC`** (new) — reads **`dnac2.env`**, using the same three
  `DNAC_HOST` / `DNAC_USERNAME` / `DNAC_PASSWORD` keys, so the file is a literal
  copy of `dnac.env` with different values. Already covered by the `*.env`
  gitignore rule.
- **No silent fallback.** A missing `dnac2.env` reports the miss and returns to
  the menu rather than loading legacy credentials, which would point the session
  at the wrong controller.
- **`3) Enter manually · remember`** now asks which file to write
  (`1) dnac.env` / `2) dnac2.env`); **blank = legacy**, preserving the old
  behaviour. So typing new-controller credentials can no longer silently
  overwrite the legacy file.
- **`5) View credential files`** (was `4) View dnac.env`) shows every credential
  file that exists, `DNAC_PASSWORD` masked as before.
- Options moves to `6)`; the prompt becomes `Select [1-6]`.
  (`main_latest.py`, `test_credential_files.py`)

### Splash de-brand (Cisco × Generic University)

- The co-brand wording is now **"Generic University"** — both the
  `CISCO · DNA CENTER  ×  …` tagline and the halftone wordmark rows
  (`GENERIC` / `UNIVERSITY`) in the `lockup` and `stacked` designs.
- **`SPLASH_DESIGN` renamed `burger` → `mark`.** `generic` already names the
  no-co-brand design, so the co-brand mark could not take that name. The
  Options → `J` cycle is now `mark → lockup → stacked → generic → mark`, and
  `load_prefs()` migrates a pre-rename `prefs.env` so the J row never shows a
  stale value. Internals renamed to match (`_mark_rows`, `_lockup_rows`,
  `_stacked_rows`, `_MARK_COUNTS_*`), and the J-cycle moved out of `menu_options`
  into `next_splash_design()` so it is directly testable.
- The mark's dot geometry is unchanged — only wording and naming moved.
- Standalone splash previews (`splash_rich.py`, `splash_generic.py`,
  `splash_preview.py`) show the new six-item Menu 1.

## 2026-07-29 — Splash co-brand reskin (Cisco × Hamburger University)

- Replaced the co-brand mark's identifying wordmark and diamond glyph with a
  fictional "Hamburger University" sandbox theme, matching the placeholder
  entity already used elsewhere in this repo's demo data
  (`drawio_exports/hu-chicago-sda.drawio`).
- **`SPLASH_DESIGN` renamed `diamond` → `burger`** (default unchanged in
  behaviour, just the key and the on-screen mark). `lockup`/`stacked`/`generic`
  keys are unchanged.
- The halftone-dot mark is now a burger silhouette (bun crown → bun edge →
  filling stack → tapered base) instead of a diamond, built on the same
  column-grid math so the alignment/degrade tests didn't need structural
  changes — only the dot-count sequence per row changed.

## 2026-07-20 — Pyramid topology layout (distribution / access / desk)

- **New `TOPOLOGY_LAYOUT` preference (Options → `K`)** toggles the CDP topology
  between `auto` (the existing Graphviz BFS ranking) and `pyramid` — a classic
  three-tier distribution/access/desk hierarchy. `pyramid` fixes the
  "everything spreads across the horizontal axis" problem by pinning switches to
  three rows instead of a free-form tree.
- **Tiers are decided by hostname model** (`topology_dot.switch_tier`):
  - **Top — distribution:** hostname contains `4500`.
  - **Middle — access:** hostname contains `9300` / `9200` / `3850` / `3560`
    **and** the switch is directly cabled to a `4500`. Switches whose model
    isn't in the hostname (including most rogue/unscanned nodes) also default
    here.
  - **Bottom — desk:** a `9300` / `9200` / `3850` / `3560` **not** directly
    cabled to a `4500`.
- **Implementation.** In pyramid mode `to_dot` rank-groups each tier
  (`rank=same`), orders the tiers top→bottom with an invisible anchor chain, and
  draws every physical link `constraint=false` so links steer left/right
  placement (children under parents) without distorting the ranks. Parallel
  uplinks are still all drawn. `auto` is unchanged and remains the default.

## 2026-07-19 — Splash hardening (review follow-up)

- **Terminal-width guard.** `render()` now degrades the logo to the richest
  design that fits (`burger`/`stacked` → `lockup` → `generic`) so the mark no
  longer folds into a broken mess on an 80-column terminal.
- **Splash render failures are no longer silent.** A crash in the Rich splash
  still falls back to the classic splash, but the traceback is surfaced when
  `CHEAT_DEBUG` is set or `LOGGING` is on — so a real regression isn't
  indistinguishable from "Rich not installed".
- Prefs are read once per splash draw (design passed through), and the wordmark
  string no longer shadows the options-loop variable.
- **Tests:** parametrised smoke test across all four designs, HU-tag/burger
  presence per design, invalid-design fallback, stacked-hangs-below-bars, the
  width-guard degradation, and prefs migration (old `prefs.env` gains the new
  `SPLASH_DESIGN` default).

## 2026-07-17 — Co-brand splash (Cisco × Hamburger University)

- The Rich splash can now co-brand with a fictional Hamburger University sandbox
  theme. A **`SPLASH_DESIGN`** preference (Options → `J`) cycles four logos:
  - **`burger`** (default) — HU halftone burger mark beside the Cisco bars.
  - **`lockup`** — compact HU burger + `HAMBURGER UNIVERSITY` badge beside the bars.
  - **`stacked`** — full HU lockup (large burger over the `HAMBURGER UNIVERSITY`
    wordmark) beside the bars, bars top-aligned with the burger mark.
  - **`generic`** — original Cisco-only splash, no HU branding.
- Co-brand designs append a **`× Hamburger University`** tag to the
  `CISCO · DNA CENTER` wordmark, riding the same cyan→white gradient.
- `python splash_rich.py [design]` previews one design; no arg cycles all four.
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
