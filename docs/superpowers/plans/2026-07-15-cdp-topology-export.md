# CDP Physical Topology Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On every combined-report scan, also write a `.drawio` physical switch topology from CDP data, with unscanned (rogue) switches drawn in red.

**Architecture:** A new pure module `cdp_topology.py` builds an undirected switch graph from the already-collected CDP output and computes a layered tree layout. `drawio_generator.py` gains a renderer that turns that graph + positions into draw.io XML (reusing its existing cell/edge helpers and Cisco switch shape). `cheat_core.generate_cdp_topology` orchestrates build→layout→render→write, and `main.py` calls it after the combined report.

**Tech Stack:** Python 3.9+, `xml.etree.ElementTree`, pytest.

## Global Constraints

- Python 3.9+ type hints (`list[...]`, `dict[...]`, `X | None`) are used throughout this codebase.
- Reuse, do not duplicate: `unscanned_switches._norm_host` and `unscanned_switches.parse_cdp_switch_neighbors`; and in `drawio_generator.py` the `_new_root`, `_add_cell`, `_add_edge` helpers, the `DEVICE_STYLES["edge"]` switch shape, and `DW, DH` node size.
- Switches only (Capability contains `S`) — that filter already lives inside `parse_cdp_switch_neighbors`.
- Graph identity is the normalised name (`_norm_host`): domain-stripped + case-folded. Display names keep the first-seen original string.
- Deterministic output: nodes sorted `(is_rogue, name)`, edges sorted `(a, a_port, b, b_port)`, adjacency iterated in sorted order, roots chosen by `(-degree, name)`.
- Rogue node style is red: `fillColor=#f8cecc; strokeColor=#b85450`. Scanned nodes use the existing grey `DEVICE_STYLES["edge"]`.
- Scanned set = the hostnames we ran commands on = `raw_outputs.keys()` (passed by `main.py`).
- Output file: `drawio_exports/<stem>-<YYYY-MM-DD-HH-MM>-cdp-topology.drawio`.
- Run tests with `python3 -m pytest` from the repo root. Pre-existing collection errors in `test_mock_dnac.py`, `test_dnac.py`, `test_sandbox.py` (fixture-arg / live-integration) are unrelated — ignore them.

---

### Task 1: Graph model + `build_topology`

**Files:**
- Create: `cdp_topology.py`
- Test: `test_cdp_topology.py`

**Interfaces:**
- Consumes: `unscanned_switches.parse_cdp_switch_neighbors`, `unscanned_switches._norm_host`.
- Produces:
  - `TopologyNode(name: str, is_rogue: bool, platform: str = "")`
  - `TopologyEdge(a: str, a_port: str, b: str, b_port: str)`
  - `Topology(nodes: list[TopologyNode], edges: list[TopologyEdge])`
  - `build_topology(raw_outputs: dict[str, str], scanned_hostnames) -> Topology`

- [ ] **Step 1: Write the failing test**

Create `test_cdp_topology.py`:

```python
SW1_CDP = "\n".join([
    "Device ID        Local Intrfce     Holdtme    Capability  Platform  Port ID",
    "sw2              Gig 1/0/3         169              S I   C9KV-UADP Gig 1/0/2",
    "sw3              Gig 1/0/1         156              S I   C9KV-UADP Gig 1/0/2",
    "sw4              Gig 0/0           137              S I   C9KV-UADP Gig 0/0",
    "deskphone        Gig 1/0/9         120              H P   IP-Phone  Port 1",
    "Total cdp entries displayed : 4",
])
# sw2 sees sw1 back on the reciprocal ports (tests bidirectional dedup).
SW2_CDP = "\n".join([
    "Device ID        Local Intrfce     Holdtme    Capability  Platform  Port ID",
    "sw1              Gig 1/0/2         169              S I   C9KV-UADP Gig 1/0/3",
    "Total cdp entries displayed : 1",
])


def _raw():
    return {"sw1": SW1_CDP, "sw2": SW2_CDP, "sw3": ""}


def test_build_topology_nodes_and_rogue_flag():
    from cdp_topology import build_topology
    topo = build_topology(_raw(), ["sw1", "sw2", "sw3"])
    by_name = {n.name: n for n in topo.nodes}
    assert set(by_name) == {"sw1", "sw2", "sw3", "sw4"}
    assert by_name["sw4"].is_rogue is True
    assert by_name["sw4"].platform == "C9KV-UADP"
    assert by_name["sw1"].is_rogue is False
    assert "deskphone" not in by_name  # phone (Capability H P) excluded


def test_build_topology_dedups_bidirectional_link():
    from cdp_topology import build_topology
    topo = build_topology(_raw(), ["sw1", "sw2", "sw3"])
    # sw1<->sw2 seen from both ends must collapse to ONE edge.
    sw1_sw2 = [e for e in topo.edges
               if {e.a, e.b} == {"sw1", "sw2"}]
    assert len(sw1_sw2) == 1
    e = sw1_sw2[0]
    assert {e.a_port, e.b_port} == {"Gi1/0/3", "Gi1/0/2"}
    # Three switch links total: sw1-sw2, sw1-sw3, sw1-sw4.
    assert len(topo.edges) == 3
    rogue_edge = [e for e in topo.edges if "sw4" in (e.a, e.b)]
    assert len(rogue_edge) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_cdp_topology.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'cdp_topology'`

- [ ] **Step 3: Write minimal implementation**

Create `cdp_topology.py`:

```python
"""
Build a physical switch topology from CDP data and lay it out for draw.io.

Pure graph building and layout — no XML, no file IO. Nodes are switches
(scanned + rogue), edges are switch<->switch CDP links.
"""

from dataclasses import dataclass

from unscanned_switches import parse_cdp_switch_neighbors, _norm_host


@dataclass
class TopologyNode:
    name: str          # display name: hostname (scanned) or CDP device id (rogue)
    is_rogue: bool
    platform: str = ""  # truncated CDP platform, used in rogue labels


@dataclass
class TopologyEdge:
    a: str
    a_port: str
    b: str
    b_port: str


@dataclass
class Topology:
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]


def build_topology(raw_outputs: dict[str, str], scanned_hostnames) -> Topology:
    """Build the switch topology graph from collected CDP output.

    Graph identity is the normalised name; the first-seen original string is
    the display name. Bidirectional links (seen from both scanned ends) are
    collapsed to one undirected edge.
    """
    scanned = {_norm_host(h) for h in scanned_hostnames}
    nodes: dict[str, TopologyNode] = {}   # norm name -> node

    def ensure_node(display: str, platform: str = "") -> str:
        norm = _norm_host(display)
        if norm not in nodes:
            nodes[norm] = TopologyNode(
                name=display, is_rogue=norm not in scanned, platform=platform
            )
        return norm

    for h in scanned_hostnames:
        ensure_node(h)

    edges: dict[frozenset, TopologyEdge] = {}
    for host, text in raw_outputs.items():
        hn = ensure_node(host)
        for nb in parse_cdp_switch_neighbors(text):
            bn = ensure_node(nb.device, nb.platform)
            if bn == hn:
                continue
            key = frozenset({(hn, nb.local_iface), (bn, nb.neighbour_port)})
            if key not in edges:
                edges[key] = TopologyEdge(
                    a=nodes[hn].name, a_port=nb.local_iface,
                    b=nodes[bn].name, b_port=nb.neighbour_port,
                )

    node_list = sorted(nodes.values(), key=lambda n: (n.is_rogue, n.name))
    edge_list = sorted(edges.values(), key=lambda e: (e.a, e.a_port, e.b, e.b_port))
    return Topology(nodes=node_list, edges=edge_list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_cdp_topology.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add cdp_topology.py test_cdp_topology.py
git commit -m "feat: build switch topology graph from CDP data"
```

---

### Task 2: `layout_topology`

**Files:**
- Modify: `cdp_topology.py`
- Test: `test_cdp_topology.py`

**Interfaces:**
- Consumes: `Topology` (Task 1).
- Produces: `layout_topology(topology: Topology) -> dict[str, tuple[int, int]]` — one `(x, y)` per node name. Highest-degree scanned node is the top-level root (y at the top); BFS spanning tree lays children out below their parent, parent centred over children; each disconnected component is stacked below the previous. Module-level size constants `NODE_W`, `NODE_H` are exported for the renderer to reuse.

- [ ] **Step 1: Write the failing test**

Append to `test_cdp_topology.py`:

```python
def test_layout_root_is_top_and_highest_degree():
    from cdp_topology import build_topology, layout_topology
    topo = build_topology(_raw(), ["sw1", "sw2", "sw3"])
    pos = layout_topology(topo)
    assert set(pos) == {"sw1", "sw2", "sw3", "sw4"}
    # sw1 has degree 3 (sw2, sw3, sw4) -> it is the root, at the top (min y).
    min_y = min(y for _, y in pos.values())
    assert pos["sw1"][1] == min_y
    # A rogue leaf sits one level below its parent.
    assert pos["sw4"][1] > pos["sw1"][1]


def test_layout_stacks_disconnected_components_below():
    from cdp_topology import build_topology, layout_topology
    # sw5 is scanned but has no CDP neighbours -> its own component.
    raw = dict(_raw())
    raw["sw5"] = ""
    topo = build_topology(raw, ["sw1", "sw2", "sw3", "sw5"])
    pos = layout_topology(topo)
    # sw1's component occupies the top band; the isolated sw5 lands below all of it.
    first_component_max_y = max(pos[n][1] for n in ("sw1", "sw2", "sw3", "sw4"))
    assert pos["sw5"][1] > first_component_max_y
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_cdp_topology.py -k layout -q`
Expected: FAIL with `ImportError: cannot import name 'layout_topology'`

- [ ] **Step 3: Write minimal implementation**

Append to `cdp_topology.py`:

```python
NODE_W = 56
NODE_H = 56
H_SPACING = 120   # horizontal gap between sibling subtrees
V_SPACING = 120   # vertical gap between depth levels


def layout_topology(topology: Topology) -> dict[str, tuple[int, int]]:
    """Layered tree layout: {node name -> (x, y)}.

    Root of each component is the highest-degree node (scanned first). A BFS
    spanning tree assigns depth levels top-down; each node is centred over its
    children. Disconnected components are stacked vertically.
    """
    names = [n.name for n in topology.nodes]
    is_rogue = {n.name: n.is_rogue for n in topology.nodes}

    adj: dict[str, set] = {name: set() for name in names}
    for e in topology.edges:
        if e.a in adj and e.b in adj and e.a != e.b:
            adj[e.a].add(e.b)
            adj[e.b].add(e.a)
    degree = {name: len(adj[name]) for name in names}

    scanned_roots = sorted((n for n in names if not is_rogue[n]), key=lambda n: (-degree[n], n))
    rogue_roots = sorted((n for n in names if is_rogue[n]), key=lambda n: (-degree[n], n))
    root_candidates = scanned_roots + rogue_roots

    positions: dict[str, tuple[int, int]] = {}
    y_offset = 0

    for root in root_candidates:
        if root in positions:
            continue

        # BFS spanning tree for this component.
        depth = {root: 0}
        children: dict[str, list] = {root: []}
        queue = [root]
        while queue:
            cur = queue.pop(0)
            for nb in sorted(adj[cur]):
                if nb not in depth:
                    depth[nb] = depth[cur] + 1
                    children[cur].append(nb)
                    children[nb] = []
                    queue.append(nb)

        base_y = y_offset
        x_cursor = [0]

        def place(node: str) -> float:
            kids = children.get(node, [])
            if not kids:
                x = x_cursor[0]
                x_cursor[0] += NODE_W + H_SPACING
            else:
                x = sum(place(k) for k in kids) / len(kids)
            positions[node] = (int(x), base_y + depth[node] * (NODE_H + V_SPACING))
            return x

        place(root)
        max_depth = max(depth.values())
        y_offset += (max_depth + 1) * (NODE_H + V_SPACING) + V_SPACING

    return positions
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_cdp_topology.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add cdp_topology.py test_cdp_topology.py
git commit -m "feat: layered tree layout for switch topology"
```

---

### Task 3: draw.io renderer

**Files:**
- Modify: `drawio_generator.py` (add styles + `generate_cdp_topology_xml`, at the end before/after the public API section)
- Test: `test_cdp_topology.py`

**Interfaces:**
- Consumes: `Topology` (Task 1), positions dict (Task 2), and the existing `_new_root`, `_add_cell`, `_add_edge`, `DEVICE_STYLES`, `DW`, `DH` in this module.
- Produces: `generate_cdp_topology_xml(topology, positions) -> str` — a single-page `mxfile` draw.io document string. Scanned nodes grey, rogue nodes red, edges labelled `"<a_port> ↔ <b_port>"`, plus a title and a legend.

- [ ] **Step 1: Write the failing test**

Append to `test_cdp_topology.py`:

```python
def test_generate_cdp_topology_xml_marks_rogue_and_labels_edges():
    from cdp_topology import build_topology, layout_topology
    from drawio_generator import generate_cdp_topology_xml
    topo = build_topology(_raw(), ["sw1", "sw2", "sw3"])
    xml = generate_cdp_topology_xml(topo, layout_topology(topo))
    assert xml.startswith("<?xml")
    assert "<mxfile" in xml
    # Rogue node carries the red fill.
    assert "f8cecc" in xml
    # An edge label shows both ports with the double-arrow.
    assert "↔" in xml
    # The rogue label names the unscanned device.
    assert "(unscanned)" in xml
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_cdp_topology.py -k xml -q`
Expected: FAIL with `ImportError: cannot import name 'generate_cdp_topology_xml'`

- [ ] **Step 3: Write minimal implementation**

In `drawio_generator.py`, add these styles after the existing `DEVICE_STYLES = {...}` block:

```python
CDP_TOPO_ROGUE_STYLE = (
    "shape=mxgraph.cisco.switches.catalyst_702x_702x;html=1;pointerEvents=1;dashed=0;"
    "fillColor=#f8cecc;strokeColor=#b85450;verticalLabelPosition=bottom;verticalAlign=top;"
    "align=center;outlineConnect=0;fontColor=#333333;fontSize=9;"
)
CDP_TOPO_EDGE_STYLE = "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;jettySize=auto;fontSize=8;"
CDP_TOPO_HEADER = 80   # vertical space reserved for title + legend
```

Add this function near the Public API section:

```python
def generate_cdp_topology_xml(topology, positions) -> str:
    """Render a switch topology (nodes + positions) as a single-page .drawio.

    Scanned switches use the grey edge-switch style; rogue (unscanned) switches
    are red. Edges are labelled with the port at each end.
    """
    root, mx_root = _new_root()

    _add_cell(mx_root, "title", "CDP Physical Topology",
              "text;html=1;strokeColor=none;fillColor=none;align=left;fontStyle=1;fontSize=14;",
              10, 10, 600, 30)
    _add_cell(mx_root, "legend",
              "Grey = scanned switch   |   Red = unscanned (rogue) switch",
              "text;html=1;strokeColor=none;fillColor=none;align=left;fontSize=9;fontColor=#666666;",
              10, 44, 600, 20)

    id_map = {}
    cid = 2
    for node in topology.nodes:
        x, y = positions.get(node.name, (0, 0))
        xid = str(cid); cid += 1
        if node.is_rogue:
            style = CDP_TOPO_ROGUE_STYLE
            label = f"{node.name}\n{node.platform}\n(unscanned)"
        else:
            style = DEVICE_STYLES["edge"]
            label = node.name
        _add_cell(mx_root, xid, label, style, x, y + CDP_TOPO_HEADER, DW, DH)
        id_map[node.name] = xid

    for edge in topology.edges:
        if edge.a in id_map and edge.b in id_map:
            _add_edge(mx_root, str(cid), id_map[edge.a], id_map[edge.b],
                      style=CDP_TOPO_EDGE_STYLE,
                      label=f"{edge.a_port} ↔ {edge.b_port}")
            cid += 1

    doc_root = ET.Element("mxfile", host="CHEAT", version="21.0.0")
    diagram = ET.SubElement(doc_root, "diagram", name="CDP Topology")
    diagram.append(root)
    ET.indent(doc_root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(doc_root, encoding="unicode")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_cdp_topology.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add drawio_generator.py test_cdp_topology.py
git commit -m "feat: render CDP switch topology to draw.io"
```

---

### Task 4: Orchestrator + wire into scan flow

**Files:**
- Modify: `cheat_core.py` (imports near line 24-26; add `DRAWIO_DIR` constant near `EXCEL_DIR`; add `generate_cdp_topology`)
- Modify: `main.py` (import; call after `generate_excel`, around line 961)
- Test: `test_cdp_topology.py`

**Interfaces:**
- Consumes: `build_topology`, `layout_topology` (Tasks 1-2), `generate_cdp_topology_xml` (Task 3).
- Produces: `generate_cdp_topology(raw_outputs: dict[str, str], scanned_hostnames, filename_stem: str) -> tuple[bool, str]` — writes `drawio_exports/<stem>-<ts>-cdp-topology.drawio`; returns `(False, message)` and writes nothing when there are no scanned switches.

- [ ] **Step 1: Write the failing test**

Append to `test_cdp_topology.py`:

```python
def test_generate_cdp_topology_writes_file(tmp_path, monkeypatch):
    import cheat_core
    monkeypatch.chdir(tmp_path)
    ok, msg = cheat_core.generate_cdp_topology(_raw(), _raw().keys(), "topo")
    assert ok is True
    path = msg.split("CDP topology: ")[1].split(" (")[0]
    from pathlib import Path
    assert Path(path).is_file()
    assert Path(path).read_text(encoding="utf-8").lstrip().startswith("<?xml")
    assert path.endswith("-cdp-topology.drawio")


def test_generate_cdp_topology_skips_when_no_scanned(tmp_path, monkeypatch):
    import cheat_core
    monkeypatch.chdir(tmp_path)
    ok, msg = cheat_core.generate_cdp_topology({}, [], "topo")
    assert ok is False
    from pathlib import Path
    assert not list(Path(tmp_path).glob("**/*.drawio"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_cdp_topology.py -k generate_cdp_topology -q`
Expected: FAIL with `AttributeError: module 'cheat_core' has no attribute 'generate_cdp_topology'`

- [ ] **Step 3: Write minimal implementation**

In `cheat_core.py`, add the imports after the existing `from unscanned_switches import find_unscanned_switches` line:

```python
from cdp_topology import build_topology, layout_topology
from drawio_generator import generate_cdp_topology_xml
```

Add a constant next to `EXCEL_DIR = "excel_reports"`:

```python
DRAWIO_DIR = "drawio_exports"
```

Add the orchestrator (e.g. at the end of the Excel Generation section):

```python
def generate_cdp_topology(
    raw_outputs: dict, scanned_hostnames, filename_stem: str
) -> tuple[bool, str]:
    """Build and write the CDP physical topology .drawio for a scan.

    Returns (success, message). Writes nothing and returns (False, message)
    when there are no scanned switches to anchor the diagram.
    """
    topology = build_topology(raw_outputs, scanned_hostnames)
    scanned_nodes = [n for n in topology.nodes if not n.is_rogue]
    if not scanned_nodes:
        return False, "⚠ CDP topology skipped: no scanned switches"

    positions = layout_topology(topology)
    xml = generate_cdp_topology_xml(topology, positions)

    out_dir = Path(DRAWIO_DIR).resolve()
    out_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d-%H-%M")
    outpath = str(out_dir / f"{filename_stem}-{ts}-cdp-topology.drawio")
    try:
        Path(outpath).write_text(xml, encoding="utf-8")
    except IOError as e:
        return False, f"✗ Failed to write CDP topology: {e}"

    rogue = sum(1 for n in topology.nodes if n.is_rogue)
    return True, (
        f"✓ CDP topology: {outpath} "
        f"({len(scanned_nodes)} switch(es), {rogue} unscanned)"
    )
```

In `main.py`, extend the `cheat_core` import to include `generate_cdp_topology` (it is imported alongside `parse_outputs`, `generate_excel` — add the name to that import list), then update the scan-action tail (currently at lines 961-964):

```python
    results = generate_excel(devices_data, mode, stem, threshold, raw_outputs=outputs)
    for _, msg in results:
        print(f"\n  {msg}")
    if mode == 3:
        _, topo_msg = generate_cdp_topology(outputs, outputs.keys(), stem)
        print(f"\n  {topo_msg}")
    pause()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_cdp_topology.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -q`
Expected: the feature and existing suites pass; only the pre-existing `test_mock_dnac.py` / `test_dnac.py` / `test_sandbox.py` collection errors remain (unrelated).

- [ ] **Step 6: Commit**

```bash
git add cdp_topology.py drawio_generator.py cheat_core.py main.py test_cdp_topology.py
git commit -m "feat: write CDP topology diagram alongside combined report"
```

---

## Self-Review

**Spec coverage:**
- `cdp_topology.py` build + layout (pure) → Tasks 1, 2.
- Switch-only filter, rogue classification, bidirectional dedup, deterministic ordering → Task 1 (tests assert phone exclusion, dedup to one edge, rogue flag/platform).
- Renderer with rogue-red styling, edge port labels, legend → Task 3.
- Orchestrator + `main` wiring (mode 3, `outputs.keys()` scanned set), no-scanned skip, per-host best-effort parsing → Task 4.
- Filename `drawio_exports/<stem>-<ts>-cdp-topology.drawio` → Task 4 (test asserts suffix and file written).
- Out-of-scope items (mgmt IP, non-switch neighbours, geographic placement) → correctly absent.

**Placeholder scan:** No TBD/TODO/vague steps — every code step is complete. (Task 1's phone-exclusion assertion is written as a plain membership check.)

**Type consistency:** `TopologyNode(name, is_rogue, platform="")`, `TopologyEdge(a, a_port, b, b_port)`, and `Topology(nodes, edges)` are used identically across build, layout, render, and orchestrator. `generate_cdp_topology_xml(topology, positions)` and `generate_cdp_topology(raw_outputs, scanned_hostnames, filename_stem)` names/signatures match between the tasks that define and call them. `NODE_W/NODE_H` in `cdp_topology` equal `DW/DH` (56) reused by the renderer.
