# CDP Physical Topology Export — Design

**Date:** 2026-07-15
**Status:** Approved

## Problem

CHEAT scans a site's switches and produces a combined Excel report (including
the new "Unscanned Cisco Switches" block). But there is no *visual* map of how
the switches physically interconnect, and no at-a-glance view of where rogue
(unscanned) switches hang off the known estate.

We want every combined-report scan to also emit a draw.io diagram of the
physical switch topology built from CDP data, with unscanned/rogue switches
drawn in red so they stand out against the known switches.

## Scope

- Produced by the `main_latest.py` scan flow, alongside the combined report
  (mode 3), written to `drawio_exports/<stem>-cdp-topology.drawio`. Auto-written,
  no prompt.
- **Switches only** (CDP Capability contains `S`) — reuses
  `unscanned_switches.parse_cdp_switch_neighbors`. Phones, APs, and hosts are
  excluded.
- The existing `drawio_generator.generate_drawio` (DNAC site/fabric diagram,
  metadata-driven) is unchanged and unrelated — this is a distinct, CLI/CDP-driven
  diagram.

## Definitions

- **Scanned switch:** a host we ran commands on this session = a key of
  `raw_outputs`.
- **Rogue switch:** a switch-capable CDP neighbour whose normalised name
  (domain-stripped, case-folded) is not a scanned switch.
- **Link:** a switch↔switch CDP adjacency, labelled with the local and remote
  port at each end.

## Data source

Every scanned host's brief `show cdp neighbors` output is already collected in
the `raw_outputs` dict. `parse_cdp_switch_neighbors(text)` yields the
switch-capable neighbours (device, platform, capability, local_iface,
neighbour_port). No new command is issued.

Node labels: scanned switches are labelled by hostname (their model/details are
already in the Excel report); rogue switches are labelled
`device / platform / (unscanned)`, where platform is the truncated CDP platform.

## Components

### `cdp_topology.py` (new — pure graph building + layout, no XML, no IO)

```python
@dataclass
class TopologyNode:
    name: str          # hostname (scanned) or CDP device id (rogue)
    is_rogue: bool
    platform: str = "" # truncated CDP platform, for rogue labels

@dataclass
class TopologyEdge:
    a: str             # scanned host (endpoint we saw the link from)
    a_port: str        # local interface on `a`, e.g. "Gi1/0/3"
    b: str             # neighbour (scanned or rogue)
    b_port: str        # neighbour's port, e.g. "Gi1/0/2"

@dataclass
class Topology:
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]
```

- `build_topology(raw_outputs, scanned_hostnames) -> Topology`
  - `scanned = {_norm_host(h) for h in scanned_hostnames}` (reuse
    `unscanned_switches._norm_host`).
  - For each `host, text` in `raw_outputs`, for each switch neighbour `nb`:
    classify `nb.device` as known (normalised name in `scanned`) or rogue.
    Form a candidate edge `(host, nb.local_iface) — (nb.device, nb.neighbour_port)`.
  - **Dedup:** a scanned↔scanned link appears from both ends; collapse to one
    undirected edge keyed on the unordered pair
    `frozenset({(_norm_host(host), local_iface), (_norm_host(device), neighbour_port)})`,
    keeping the first-seen orientation's ports. Rogue links are seen only from
    the scanned side, so they are single edges.
  - Nodes: every scanned host is a node (`is_rogue=False`), even if isolated;
    every distinct rogue device is a node (`is_rogue=True`, with platform). A
    rogue node is keyed by its normalised name so multiple sightings collapse to
    one node; its display `name` is the first-seen device string.
  - Deterministic ordering: nodes sorted by `(is_rogue, name)`; edges sorted by
    `(a, a_port, b, b_port)`.

- `layout_topology(topology) -> dict[str, tuple[int, int]]`
  - Build undirected adjacency over node names.
  - Root = highest-degree scanned node; ties broken alphabetically (the
    distribution switch). BFS assigns depth levels top-down; a node's x is
    assigned parent-centred-over-children, reusing the positioning approach in
    `drawio_generator._layout_tree`. Rogue leaves sit one level below their
    parent.
  - Disconnected components each get their own root (next highest-degree
    unplaced node), laid out below the previous component.
  - Returns integer `(x, y)` per node name.

### `drawio_generator.py` (new rendering function, reuses existing helpers)

- Add `generate_cdp_topology_xml(topology, positions) -> str`.
  - Reuses `_new_root`, `_add_cell`, `_add_edge`, and the existing Cisco switch
    shape used for `edge` devices.
  - Scanned node style: the existing grey `edge` switch style.
  - Rogue node style: red — `fillColor=#f8cecc; strokeColor=#b85450`.
  - Edge label: `"<a_port> ↔ <b_port>"`.
  - A legend text box (grey = scanned, red = unscanned).
  - Single-page `.drawio` document (`mxfile`), same wrapper as `generate_drawio`.

### `cheat_core.py` (orchestrator)

- `generate_cdp_topology(raw_outputs, scanned_hostnames, filename_stem) -> tuple[bool, str]`
  - `topology = build_topology(...)`; if no scanned switches → return
    `(False, "message")` and write nothing.
  - `positions = layout_topology(topology)`;
    `xml = generate_cdp_topology_xml(topology, positions)`.
  - Write to `drawio_exports/<filename_stem>-<ts>-cdp-topology.drawio`
    (`drawio_exports/` created if missing), return `(True, path-message)`.

### `main_latest.py` (wiring)

- In the scan action, after the `generate_excel(...)` call, when the combined
  report (mode 3) was chosen, call
  `generate_cdp_topology(outputs, outputs.keys(), stem)` and print the returned
  message. `outputs` is already in scope at that point.

## Data flow

```
scan: outputs (raw text) ──> parse_outputs ──> devices_data ──> generate_excel (mode 3)
                        └──> generate_cdp_topology(outputs, outputs.keys(), stem)
                                 └─ build_topology ─> Topology
                                 └─ layout_topology ─> positions
                                 └─ generate_cdp_topology_xml ─> .drawio file
```

## Error handling

- No switch↔switch links found → still write the file with the (isolated)
  scanned nodes and the legend — a valid, if sparse, diagram.
- No scanned switches at all → skip writing; return a `(False, message)`.
- Malformed CDP for one host → that host contributes no edges; no crash (per-host
  parsing is best-effort, inherited from `parse_cdp_switch_neighbors`).

## Testing

- `build_topology`: sample `raw_outputs` for `sw1/sw2/sw3` where `sw1` sees
  `sw2, sw3` (scanned) and `sw4` (rogue). Assert nodes `{sw1,sw2,sw3}` scanned +
  `sw4` rogue; the `sw1↔sw2` link deduped to a single edge carrying both ports;
  the `sw1→sw4` edge present and `sw4` flagged rogue; ports correct.
- `layout_topology`: deterministic positions; the highest-degree node is the
  top/root; a rogue sits one level below its parent; a second disconnected
  component lands below the first.
- `generate_cdp_topology_xml`: output is a valid `mxfile`; the rogue node cell
  carries the red style; at least one edge label shows both ports (`↔`).
- `generate_cdp_topology`: writes the file and returns its path; the no-scanned
  switches case returns `(False, ...)` and writes nothing.

## Out of scope (YAGNI)

- Management IPs on nodes (brief CDP lacks them — would come with a separate
  `show cdp neighbors detail` enhancement).
- Non-switch neighbours (phones, APs, hosts).
- Geographic / per-floor placement, and multi-page output.
