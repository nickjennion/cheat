# CDP Topology Graphviz Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the CDP topology's BFS-grid layout with a Graphviz `dot` pipeline that produces an editable multi-page `.drawio` — an overview plus per-aggregation A3 pages, aggregation top-centre, edges routed to avoid overlap.

**Architecture:** `build_topology` (unchanged) → `topology_dot.build_pages` splits the graph into pages → per page, `to_dot` emits Graphviz DOT, `dot -Tplain` (subprocess) lays it out, `parse_plain` reads back node boxes + orthogonal edge routes → `drawio_generator.generate_cdp_topology_drawio` emits a multi-page `.drawio` (Graphviz coords → geometry, edge bend-points → waypoints).

**Tech Stack:** Python 3.9+, Graphviz `dot` (system binary, called via `subprocess`), `xml.etree.ElementTree`, pytest.

## Global Constraints

- Python 3.9+ (`list[...]`, `dict[...]`, `X | None`).
- Graphviz is a **system dependency** (the `dot` binary), not pip. It is already installed in this environment (`dot -V` → 2.42.4); if a shell reports it missing, install with `sudo apt-get install -y graphviz`.
- `topology_dot.py` is pure (DOT strings + text parsing); it runs no subprocess. The subprocess call (`dot`) lives in `cheat_core`.
- Root = the **max-degree node overall** (scanned or rogue).
- Edge labels are **NOT** put in the DOT (Graphviz warns that `splines=ortho` can't place them); the draw.io emitter attaches the `"<a_port> ↔ <b_port>"` label to each edge itself, from the topology data.
- Graphviz node ids are synthetic (`n0`, `n1`, …) with an id→name map, so node names containing any character never break DOT or plain parsing.
- Rogue nodes are red (`#f8cecc`), scanned nodes grey (`#f5f5f5`); rogue label = `hostname / model / mgmt_ip / (unscanned)` (newline-separated), empty segments omitted.
- Aggregation = a node with CDP-neighbour degree ≥ threshold (default 6). Per-aggregation page = the aggregation + its 2-hop downward neighbourhood, pruned at other aggregations.
- Coordinate transform (Graphviz inches, bottom-left origin → draw.io px, top-left): `SCALE = 72`; node top-left `x=(cx-w/2)*SCALE`, `y=(H-(cy+h/2))*SCALE`, size `w*SCALE × h*SCALE`; edge point `(px*SCALE, (H-py)*SCALE)`, where `H` is the plain graph height.
- Run tests with `python3 -m pytest` from the repo root. Pre-existing collection errors in `test_mock_dnac.py` / `test_dnac.py` / `test_sandbox.py` are unrelated — ignore.

---

### Task 1: Add `mgmt_ip` to `TopologyNode`

**Files:**
- Modify: `cdp_topology.py` (`TopologyNode`; `build_topology`)
- Test: `test_cdp_topology.py`

**Interfaces:**
- Produces: `TopologyNode(name, is_rogue, platform="", mgmt_ip="")`; `build_topology` populates `mgmt_ip` on rogue nodes from `SwitchNeighbour.mgmt_ip`.

- [ ] **Step 1: Write the failing test**

Append to `test_cdp_topology.py` (the `SW1_CDP` fixture already includes detail blocks with `IP address:` lines from the prior feature; this asserts the rogue's mgmt IP flows through):

```python
def test_build_topology_rogue_carries_mgmt_ip():
    from cdp_topology import build_topology
    # sw1 sees rogue sw4 with a management IP in its CDP detail block.
    raw = {"sw1": "\n".join([
        "show cdp neighbors detail",
        "-------------------------",
        "Device ID: sw4",
        "Entry address(es):",
        "  IP address: 10.1.2.3",
        "Platform: cisco WS-C3560CX-8PC-S,  Capabilities: Router Switch IGMP",
        "Interface: GigabitEthernet0/1,  Port ID (outgoing port): GigabitEthernet0/0",
        "Total cdp entries displayed : 1",
    ])}
    topo = build_topology(raw, ["sw1"])
    sw4 = {n.name: n for n in topo.nodes}["sw4"]
    assert sw4.is_rogue is True
    assert sw4.mgmt_ip == "10.1.2.3"
    assert sw4.platform == "WS-C3560CX-8PC-S"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_cdp_topology.py::test_build_topology_rogue_carries_mgmt_ip -q`
Expected: FAIL — `TopologyNode` has no `mgmt_ip` (TypeError on the attribute / dataclass).

- [ ] **Step 3: Write minimal implementation**

In `cdp_topology.py`, add the field to `TopologyNode`:

```python
@dataclass
class TopologyNode:
    name: str          # display name: hostname (scanned) or CDP device id (rogue)
    is_rogue: bool
    platform: str = ""  # truncated CDP platform, used in rogue labels
    mgmt_ip: str = ""   # management IP for rogue labels (from CDP detail)
```

In `build_topology`, the `ensure_node` helper currently takes `(display, platform="")`. Extend it to also carry the mgmt IP and set it on newly-created nodes. Replace the `ensure_node` definition and the neighbour call:

```python
    def ensure_node(display: str, platform: str = "", mgmt_ip: str = "") -> str:
        norm = _norm_host(display)
        if norm not in nodes:
            nodes[norm] = TopologyNode(
                name=display, is_rogue=norm not in scanned,
                platform=platform, mgmt_ip=mgmt_ip,
            )
        return norm
```

and where neighbours are added (the `for nb in parse_cdp_switch_neighbors(text):` loop), pass the mgmt IP:

```python
            bn = ensure_node(nb.device, nb.platform, nb.mgmt_ip)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_cdp_topology.py -q`
Expected: PASS (all, including the existing build_topology tests).

- [ ] **Step 5: Commit**

```bash
git add cdp_topology.py test_cdp_topology.py
git commit -m "feat: carry rogue mgmt_ip on TopologyNode"
```

---

### Task 2: `topology_dot.py` — DOT generation + plain parsing

**Files:**
- Create: `topology_dot.py`
- Test: `test_topology_dot.py`

**Interfaces:**
- Consumes: `cdp_topology.Topology`, `TopologyNode`, `TopologyEdge` (Task 1).
- Produces:
  - `node_label(node: TopologyNode) -> str` — newline-separated display label.
  - `to_dot(topology, node_names, root_name, a3=False) -> tuple[str, dict[str, str]]` — DOT string + `{synthetic_id: node_name}`.
  - `NodeBox`, `EdgeRoute`, `ParsedLayout` dataclasses; `parse_plain(plain: str) -> ParsedLayout`.

- [ ] **Step 1: Write the failing test**

Create `test_topology_dot.py`:

```python
from cdp_topology import Topology, TopologyNode, TopologyEdge


def _topo():
    nodes = [
        TopologyNode("dist", is_rogue=False),
        TopologyNode("acc1", is_rogue=False),
        TopologyNode("rogue-x", is_rogue=True, platform="WS-C4500X", mgmt_ip="10.0.0.9"),
    ]
    edges = [
        TopologyEdge("dist", "Gi1/0/1", "acc1", "Gi0/1"),
        TopologyEdge("dist", "Gi1/0/2", "rogue-x", "Gi0/0"),
        TopologyEdge("acc1", "x", "rogue-x", "y"),   # non-tree (cycle) edge
    ]
    return Topology(nodes=nodes, edges=edges)


def test_node_label_rogue_has_model_ip_unscanned():
    from topology_dot import node_label
    lbl = node_label(TopologyNode("r", is_rogue=True, platform="WS-C4500X", mgmt_ip="10.0.0.9"))
    assert lbl == "r\nWS-C4500X\n10.0.0.9\n(unscanned)"
    assert node_label(TopologyNode("s", is_rogue=False)) == "s"


def test_to_dot_structure():
    from topology_dot import to_dot
    dot, id_to_name = to_dot(_topo(), ["dist", "acc1", "rogue-x"], "dist")
    assert "rankdir=TB" in dot and "splines=ortho" in dot
    assert "#f8cecc" in dot                      # rogue fill present
    assert dot.count("->") == 3                  # three edges emitted
    assert "constraint=false" in dot             # the non-tree edge
    assert set(id_to_name.values()) == {"dist", "acc1", "rogue-x"}


PLAIN_FIXTURE = "\n".join([
    "graph 1 5.9653 1.5",
    "node n0 2.0417 1.25 0.75 0.5 dist filled box black #f5f5f5",
    'node n1 0.48611 0.25 0.97222 0.5 "acc one" filled box black #f5f5f5',
    "node n2 3.5972 0.25 4.7361 0.5 rogue filled box black #f8cecc",
    "edge n0 n1 7 1.6651 1.25 1.2047 1.25 0.48611 1.25 0.48611 1.25 0.48611 1.25 0.48611 0.64 0.48611 0.64 solid black",
    "edge n0 n2 4 2.0417 0.99 2.0417 0.99 2.0417 0.64 2.0417 0.64 solid black",
    "stop",
])


def test_parse_plain_nodes_and_edges():
    from topology_dot import parse_plain
    layout = parse_plain(PLAIN_FIXTURE)
    assert (round(layout.width, 3), round(layout.height, 3)) == (5.965, 1.5)
    assert set(layout.nodes) == {"n0", "n1", "n2"}
    # node box: centre x/y + w/h (quoted label with a space must not break parsing)
    b = layout.nodes["n1"]
    assert (round(b.x, 3), round(b.y, 3), round(b.w, 3), round(b.h, 3)) == (0.486, 0.25, 0.972, 0.5)
    e0 = [e for e in layout.edges if (e.tail, e.head) == ("n0", "n1")][0]
    assert len(e0.points) == 7                    # 7 route points
    assert e0.points[0] == (1.6651, 1.25)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_topology_dot.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'topology_dot'`

- [ ] **Step 3: Write minimal implementation**

Create `topology_dot.py`:

```python
"""
Graphviz DOT generation and `dot -Tplain` parsing for the CDP topology.

Pure: builds DOT strings and parses plain layout text. Running the `dot` binary
itself lives in cheat_core.
"""

from dataclasses import dataclass


def node_label(node) -> str:
    """Newline-separated display label. Rogue nodes carry model / IP / marker."""
    if not node.is_rogue:
        return node.name
    parts = [node.name]
    if node.platform:
        parts.append(node.platform)
    if node.mgmt_ip:
        parts.append(node.mgmt_ip)
    parts.append("(unscanned)")
    return "\n".join(parts)


def to_dot(topology, node_names, root_name: str, a3: bool = False):
    """Return (dot_string, {synthetic_id: node_name}) for the given node subset.

    Tree edges (from a BFS spanning tree rooted at root_name) are directed
    parent->child so the aggregation ranks to the top; non-tree edges get
    constraint=false so they are drawn without distorting the ranks. Edge labels
    are intentionally omitted (splines=ortho cannot place them).
    """
    names = list(node_names)
    nameset = set(names)
    id_of = {name: f"n{i}" for i, name in enumerate(sorted(names))}
    by_name = {n.name: n for n in topology.nodes}

    adj = {n: set() for n in names}
    sub_edges = []
    for e in topology.edges:
        if e.a in nameset and e.b in nameset and e.a != e.b:
            adj[e.a].add(e.b)
            adj[e.b].add(e.a)
            sub_edges.append((e.a, e.b))

    parent = {}
    if root_name in nameset:
        depth = {root_name: 0}
        queue = [root_name]
        while queue:
            cur = queue.pop(0)
            for nb in sorted(adj[cur]):
                if nb not in depth:
                    depth[nb] = depth[cur] + 1
                    parent[nb] = cur
                    queue.append(nb)
    tree = {frozenset((c, p)) for c, p in parent.items()}

    lines = [
        "digraph G {",
        "  rankdir=TB;",
        "  graph [splines=ortho, nodesep=0.4, ranksep=0.7];",
        "  node [shape=box, style=filled, fontsize=10];",
    ]
    if a3:
        lines.append('  graph [size="16.5,11.7", ratio=compress];')
    for name in names:
        node = by_name.get(name)
        fill = "#f8cecc" if (node and node.is_rogue) else "#f5f5f5"
        lbl = (node_label(node) if node else name).replace('"', "").replace("\n", "\\n")
        lines.append(f'  {id_of[name]} [label="{lbl}", fillcolor="{fill}"];')

    emitted = set()
    for a, b in sub_edges:
        key = frozenset((a, b))
        if key in emitted:
            continue
        emitted.add(key)
        if key in tree:
            src, dst = (a, b) if parent.get(b) == a else (b, a)
            lines.append(f"  {id_of[src]} -> {id_of[dst]};")
        else:
            lines.append(f"  {id_of[a]} -> {id_of[b]} [constraint=false];")
    lines.append("}")
    return "\n".join(lines), {v: k for k, v in id_of.items()}


@dataclass
class NodeBox:
    x: float   # centre x (graphviz inches, bottom-left origin)
    y: float   # centre y
    w: float
    h: float


@dataclass
class EdgeRoute:
    tail: str  # synthetic id
    head: str
    points: list


@dataclass
class ParsedLayout:
    width: float
    height: float
    nodes: dict
    edges: list


def parse_plain(plain: str) -> ParsedLayout:
    """Parse `dot -Tplain` output into node boxes and edge routes.

    Only the leading fixed fields are read (node: id x y w h; edge: tail head n
    then 2n point coords), so quoted labels with spaces never break parsing.
    """
    width = height = 0.0
    nodes = {}
    edges = []
    for line in plain.splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "graph":
            width, height = float(parts[2]), float(parts[3])
        elif parts[0] == "node":
            nodes[parts[1]] = NodeBox(
                float(parts[2]), float(parts[3]), float(parts[4]), float(parts[5])
            )
        elif parts[0] == "edge":
            n = int(parts[3])
            coords = parts[4:4 + 2 * n]
            pts = [(float(coords[i]), float(coords[i + 1])) for i in range(0, 2 * n, 2)]
            edges.append(EdgeRoute(parts[1], parts[2], pts))
    return ParsedLayout(width, height, nodes, edges)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_topology_dot.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Round-trip check with the real `dot` binary, then commit**

Run: `python3 -c "import subprocess, topology_dot as td; from test_topology_dot import _topo; dot,_=td.to_dot(_topo(),['dist','acc1','rogue-x'],'dist'); out=subprocess.run(['dot','-Tplain'],input=dot,capture_output=True,text=True).stdout; L=td.parse_plain(out); print(len(L.nodes),'nodes',len(L.edges),'edges')"`
Expected: `3 nodes 3 edges`

```bash
git add topology_dot.py test_topology_dot.py
git commit -m "feat: Graphviz DOT generation and plain-output parsing"
```

---

### Task 3: `select_aggregations` + `build_pages`

**Files:**
- Modify: `topology_dot.py`
- Test: `test_topology_dot.py`

**Interfaces:**
- Consumes: `Topology` (Task 1).
- Produces: `Page(title, node_names, root_name, a3)`; `select_aggregations(topology, threshold=6) -> list[str]`; `build_pages(topology, threshold=6) -> list[Page]`.

- [ ] **Step 1: Write the failing test**

Append to `test_topology_dot.py`:

```python
def _star(n_leaves, hub="hub"):
    # A hub with n_leaves scanned leaves (hub degree = n_leaves).
    from cdp_topology import Topology, TopologyNode, TopologyEdge
    nodes = [TopologyNode(hub, is_rogue=False)]
    edges = []
    for i in range(n_leaves):
        leaf = f"leaf{i}"
        nodes.append(TopologyNode(leaf, is_rogue=False))
        edges.append(TopologyEdge(hub, f"Gi0/{i}", leaf, "Gi0/0"))
    return Topology(nodes=nodes, edges=edges)


def test_select_aggregations_by_degree():
    from topology_dot import select_aggregations
    topo = _star(6)                       # hub degree 6, leaves degree 1
    assert select_aggregations(topo, threshold=6) == ["hub"]
    assert select_aggregations(topo, threshold=7) == []   # nothing meets 7


def test_build_pages_overview_plus_aggregation():
    from topology_dot import build_pages
    pages = build_pages(_star(6), threshold=6)
    titles = [p.title for p in pages]
    assert titles[0] == "Overview"
    assert pages[0].root_name == "hub"    # max-degree node roots the overview
    assert not pages[0].a3
    hub_page = [p for p in pages if p.root_name == "hub" and p.a3][0]
    assert set(hub_page.node_names) == {"hub"} | {f"leaf{i}" for i in range(6)}
    assert hub_page.a3 is True


def test_build_pages_overview_only_when_no_aggregation():
    from topology_dot import build_pages
    pages = build_pages(_star(3), threshold=6)   # hub degree 3 < 6
    assert [p.title for p in pages] == ["Overview"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_topology_dot.py -k "aggregation or pages" -q`
Expected: FAIL with `ImportError: cannot import name 'select_aggregations'`

- [ ] **Step 3: Write minimal implementation**

Append to `topology_dot.py`:

```python
@dataclass
class Page:
    title: str
    node_names: list
    root_name: str
    a3: bool


def _adjacency(topology):
    adj = {n.name: set() for n in topology.nodes}
    for e in topology.edges:
        if e.a in adj and e.b in adj and e.a != e.b:
            adj[e.a].add(e.b)
            adj[e.b].add(e.a)
    return adj


def select_aggregations(topology, threshold: int = 6) -> list:
    """Node names whose CDP-neighbour degree >= threshold, highest degree first."""
    adj = _adjacency(topology)
    hubs = [name for name, nbrs in adj.items() if len(nbrs) >= threshold]
    return sorted(hubs, key=lambda n: (-len(adj[n]), n))


def build_pages(topology, threshold: int = 6) -> list:
    """Overview page + one page per aggregation (its 2-hop downward neighbourhood).

    Expansion from an aggregation stops at other aggregations, so sibling
    distributions do not swallow each other's subtrees.
    """
    if not topology.nodes:
        return []
    adj = _adjacency(topology)
    root = max(adj, key=lambda n: (len(adj[n]), n))   # global max-degree node
    all_names = [n.name for n in topology.nodes]
    pages = [Page("Overview", all_names, root, a3=False)]

    aggs = select_aggregations(topology, threshold)
    aggset = set(aggs)
    for agg in aggs:
        members = {agg}
        for nb in adj[agg]:                 # hop 1: direct neighbours
            members.add(nb)
            if nb in aggset:
                continue                    # don't expand through another hub
            for leaf in adj[nb]:            # hop 2: their leaves
                if leaf not in aggset:
                    members.add(leaf)
        pages.append(Page(agg, sorted(members), agg, a3=True))
    return pages
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_topology_dot.py -q`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add topology_dot.py test_topology_dot.py
git commit -m "feat: aggregation detection and page splitting"
```

---

### Task 4: Multi-page draw.io emitter

**Files:**
- Modify: `drawio_generator.py` (add `generate_cdp_topology_drawio`)
- Test: `test_topology_dot.py`

**Interfaces:**
- Consumes: `topology_dot.ParsedLayout`, `NodeBox`, `EdgeRoute`, `node_label` (Tasks 2-3); `cdp_topology.Topology`.
- Produces: `generate_cdp_topology_drawio(rendered_pages, topology) -> str` where `rendered_pages` is a list of `(title, ParsedLayout, id_to_name)`. Returns a multi-page `mxfile` XML string.

- [ ] **Step 1: Write the failing test**

Append to `test_topology_dot.py`:

```python
def test_generate_cdp_topology_drawio_multipage():
    import xml.etree.ElementTree as ET
    from cdp_topology import Topology, TopologyNode, TopologyEdge
    from topology_dot import ParsedLayout, NodeBox, EdgeRoute
    from drawio_generator import generate_cdp_topology_drawio

    topo = Topology(
        nodes=[TopologyNode("dist", is_rogue=False),
               TopologyNode("rogue-x", is_rogue=True, platform="WS-C4500X", mgmt_ip="10.0.0.9")],
        edges=[TopologyEdge("dist", "Gi1/0/1", "rogue-x", "Gi0/0")],
    )
    layout = ParsedLayout(
        width=4.0, height=2.0,
        nodes={"n0": NodeBox(1.0, 1.5, 0.8, 0.5), "n1": NodeBox(1.0, 0.5, 0.8, 0.5)},
        edges=[EdgeRoute("n0", "n1", [(1.0, 1.25), (1.0, 0.75)])],
    )
    id_to_name = {"n0": "dist", "n1": "rogue-x"}
    xml = generate_cdp_topology_drawio([("Overview", layout, id_to_name)], topo)

    assert xml.startswith("<?xml")
    root = ET.fromstring(xml.split("?>", 1)[1])
    assert root.tag == "mxfile"
    diagrams = root.findall("diagram")
    assert len(diagrams) == 1 and diagrams[0].get("name") == "Overview"
    assert "f8cecc" in xml                       # rogue node red
    assert "(unscanned)" in xml                   # rogue multi-line label
    assert "Gi1/0/1 ↔ Gi0/0" in xml               # edge port label from topology
    assert 'as="points"' in xml                   # edge waypoints present
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_topology_dot.py::test_generate_cdp_topology_drawio_multipage -q`
Expected: FAIL with `ImportError: cannot import name 'generate_cdp_topology_drawio'`

- [ ] **Step 3: Write minimal implementation**

In `drawio_generator.py`, add the import near the top (module level is safe — `topology_dot` does not import `drawio_generator`):

```python
from topology_dot import node_label
```

Add these near the other CDP-topology styles:

```python
CDP_TOPO_SCALE = 72        # graphviz inches -> draw.io px
CDP_GV_SCANNED_STYLE = DEVICE_STYLES["edge"]
CDP_GV_ROGUE_STYLE = CDP_TOPO_ROGUE_STYLE
CDP_GV_EDGE_STYLE = "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=none;fontSize=8;"
```

Add the emitter (place it near `generate_cdp_topology_xml`):

```python
def _edge_label_index(topology):
    """{frozenset({name_a, name_b}): 'a_port ↔ b_port'} for edge labelling."""
    idx = {}
    for e in topology.edges:
        idx.setdefault(frozenset((e.a, e.b)), f"{e.a_port} ↔ {e.b_port}")
    return idx


def generate_cdp_topology_drawio(rendered_pages, topology) -> str:
    """Build a multi-page .drawio from Graphviz-laid pages.

    rendered_pages: list of (title, ParsedLayout, id_to_name).
    """
    by_name = {n.name: n for n in topology.nodes}
    labels = _edge_label_index(topology)

    doc_root = ET.Element("mxfile", host="CHEAT", version="21.0.0")
    for title, layout, id_to_name in rendered_pages:
        root, mx_root = _new_root()
        H = layout.height

        _add_cell(mx_root, "title", f"CDP Physical Topology — {title}",
                  "text;html=1;strokeColor=none;fillColor=none;align=left;fontStyle=1;fontSize=14;",
                  10, 10, 800, 30)
        _add_cell(mx_root, "legend",
                  "Grey = scanned switch   |   Red = unscanned (rogue) switch",
                  "text;html=1;strokeColor=none;fillColor=none;align=left;fontSize=9;fontColor=#666666;",
                  10, 44, 800, 20)

        cid = 2
        id_to_cell = {}
        for gid, box in layout.nodes.items():
            name = id_to_name.get(gid, gid)
            node = by_name.get(name)
            style = CDP_GV_ROGUE_STYLE if (node and node.is_rogue) else CDP_GV_SCANNED_STYLE
            value = node_label(node) if node else name
            x = (box.x - box.w / 2) * CDP_TOPO_SCALE
            y = (H - (box.y + box.h / 2)) * CDP_TOPO_SCALE
            xid = str(cid); cid += 1
            _add_cell(mx_root, xid, value, style, x, y + 80,
                      box.w * CDP_TOPO_SCALE, box.h * CDP_TOPO_SCALE)
            id_to_cell[gid] = xid

        for e in layout.edges:
            if e.tail not in id_to_cell or e.head not in id_to_cell:
                continue
            label = labels.get(
                frozenset((id_to_name.get(e.tail), id_to_name.get(e.head))), "")
            cell = ET.SubElement(mx_root, "mxCell", id=str(cid),
                                 value=label, style=CDP_GV_EDGE_STYLE, edge="1",
                                 source=id_to_cell[e.tail], target=id_to_cell[e.head],
                                 parent="1")
            geo = ET.SubElement(cell, "mxGeometry", relative="1", **{"as": "geometry"})
            arr = ET.SubElement(geo, "Array", **{"as": "points"})
            for (px, py) in e.points[1:-1]:   # drop endpoints; keep bend points
                ET.SubElement(arr, "mxPoint",
                              x=str(int(px * CDP_TOPO_SCALE)),
                              y=str(int((H - py) * CDP_TOPO_SCALE) + 80))
            cid += 1

        diagram = ET.SubElement(doc_root, "diagram", name=title)
        diagram.append(root)

    ET.indent(doc_root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(doc_root, encoding="unicode")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_topology_dot.py -q`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add drawio_generator.py test_topology_dot.py
git commit -m "feat: multi-page draw.io emitter from Graphviz layouts"
```

---

### Task 5: Orchestrator rewire + remove old layout/renderer

**Files:**
- Modify: `cheat_core.py` (`generate_cdp_topology`; imports; new `_run_dot`)
- Modify: `cdp_topology.py` (remove `layout_topology` + its layout constants)
- Modify: `drawio_generator.py` (remove `generate_cdp_topology_xml`)
- Test: `test_cdp_topology.py` (remove tests for the deleted functions; update `generate_cdp_topology` tests)

**Interfaces:**
- Consumes: `topology_dot.build_pages`, `to_dot`, `parse_plain` (Tasks 2-3); `drawio_generator.generate_cdp_topology_drawio` (Task 4).
- Produces: `generate_cdp_topology(raw_outputs, scanned_hostnames, filename_stem) -> tuple[bool, str]` writing a multi-page `.drawio` via Graphviz; returns `(False, install message)` when `dot` is absent.

- [ ] **Step 1: Write the failing test**

In `test_cdp_topology.py`, remove `test_layout_root_is_top_and_highest_degree`, `test_layout_stacks_disconnected_components_below`, and `test_generate_cdp_topology_xml_marks_rogue_and_labels_edges` (their functions are being deleted). Replace `test_generate_cdp_topology_writes_file` and add a dot-missing test:

```python
def test_generate_cdp_topology_writes_multipage(tmp_path, monkeypatch):
    import shutil
    if shutil.which("dot") is None:
        import pytest
        pytest.skip("graphviz 'dot' not installed")
    import openpyxl  # noqa: F401 (ensures deps import)
    import cheat_core, xml.etree.ElementTree as ET
    monkeypatch.chdir(tmp_path)
    ok, msg = cheat_core.generate_cdp_topology(_raw(), _raw().keys(), "topo")
    assert ok is True
    path = msg.split("CDP topology: ")[1].split(" (")[0]
    from pathlib import Path
    assert Path(path).is_file() and path.endswith("-cdp-topology.drawio")
    root = ET.fromstring(Path(path).read_text(encoding="utf-8").split("?>", 1)[1])
    assert root.tag == "mxfile" and root.findall("diagram")   # >= 1 page


def test_generate_cdp_topology_skips_without_dot(tmp_path, monkeypatch):
    import cheat_core
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cheat_core.shutil, "which", lambda name: None)
    ok, msg = cheat_core.generate_cdp_topology(_raw(), _raw().keys(), "topo")
    assert ok is False
    assert "Graphviz" in msg
    from pathlib import Path
    assert not list(Path(tmp_path).glob("**/*.drawio"))
```

(`test_generate_cdp_topology_skips_when_no_scanned` stays as-is.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_cdp_topology.py -k generate_cdp_topology -q`
Expected: FAIL — `cheat_core.shutil` doesn't exist yet / the multipage assertions fail against the current single-page output.

- [ ] **Step 3: Write minimal implementation**

In `cheat_core.py`, update the imports: replace

```python
from cdp_topology import build_topology, layout_topology
from drawio_generator import generate_cdp_topology_xml
```

with

```python
import shutil
import subprocess

from cdp_topology import build_topology
from topology_dot import build_pages, to_dot, parse_plain
from drawio_generator import generate_cdp_topology_drawio
```

Add the `dot` runner and rewrite `generate_cdp_topology`:

```python
def _run_dot(dot_str: str) -> "str | None":
    """Run `dot -Tplain`, returning the plain output, or None on failure."""
    try:
        result = subprocess.run(
            ["dot", "-Tplain"], input=dot_str,
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def generate_cdp_topology(
    raw_outputs: dict, scanned_hostnames, filename_stem: str
) -> tuple[bool, str]:
    """Build and write the multi-page CDP topology .drawio (Graphviz-laid)."""
    topology = build_topology(raw_outputs, scanned_hostnames)
    scanned_nodes = [n for n in topology.nodes if not n.is_rogue]
    if not scanned_nodes:
        return False, "⚠ CDP topology skipped: no scanned switches"

    if shutil.which("dot") is None:
        return False, (
            "⚠ CDP topology needs Graphviz — install with "
            "'apt install graphviz' (Linux) or "
            "'winget install Graphviz.Graphviz' (Windows)"
        )

    rendered = []
    for page in build_pages(topology):
        dot_str, id_to_name = to_dot(topology, page.node_names, page.root_name, a3=page.a3)
        plain = _run_dot(dot_str)
        if plain is None:
            continue
        rendered.append((page.title, parse_plain(plain), id_to_name))
    if not rendered:
        return False, "✗ CDP topology: Graphviz layout failed"

    xml = generate_cdp_topology_drawio(rendered, topology)
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
        f"({len(scanned_nodes)} switch(es), {rogue} unscanned, {len(rendered)} page(s))"
    )
```

In `cdp_topology.py`, delete the `layout_topology` function and its module-level layout constants `NODE_W`, `NODE_H`, `H_SPACING`, `V_SPACING` (they are now unused — `build_topology` and the dataclasses remain).

In `drawio_generator.py`, delete `generate_cdp_topology_xml` and the now-unused `CDP_TOPO_HEADER` constant (the `CDP_TOPO_ROGUE_STYLE`/`CDP_TOPO_EDGE_STYLE` remain — the new emitter references `CDP_TOPO_ROGUE_STYLE`).

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_cdp_topology.py test_topology_dot.py -q`
Expected: PASS (all; the real-`dot` test renders a multi-page file).

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -q`
Expected: feature and existing suites pass; only the pre-existing `test_mock_dnac.py` / `test_dnac.py` / `test_sandbox.py` collection errors remain.

- [ ] **Step 6: Commit**

```bash
git add cheat_core.py cdp_topology.py drawio_generator.py test_cdp_topology.py
git commit -m "feat: Graphviz multi-page topology pipeline; drop BFS layout/renderer"
```

---

### Task 6: Graphviz dependency docs

**Files:**
- Modify: `requirements.txt`
- Modify: `README.md`
- Test: `test_topology_dot.py`

**Interfaces:**
- Produces: documented Graphviz system dependency + install instructions.

- [ ] **Step 1: Write the failing test**

Append to `test_topology_dot.py`:

```python
def test_docs_mention_graphviz_install():
    from pathlib import Path
    reqs = Path("requirements.txt").read_text(encoding="utf-8").lower()
    readme = Path("README.md").read_text(encoding="utf-8").lower()
    assert "graphviz" in reqs
    assert "apt install graphviz" in readme or "apt-get install graphviz" in readme
    assert "winget install graphviz" in readme or "choco install graphviz" in readme
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_topology_dot.py::test_docs_mention_graphviz_install -q`
Expected: FAIL — the docs don't mention Graphviz yet.

- [ ] **Step 3: Write minimal implementation**

Append to `requirements.txt`:

```
# System dependency (NOT pip): Graphviz provides the `dot` binary used to lay
# out the CDP physical topology diagram. Install it separately — see README.
#   Linux (Debian/Ubuntu): sudo apt install graphviz
#   Linux (RHEL/Fedora):    sudo dnf install graphviz
#   Windows:                winget install Graphviz.Graphviz  (or: choco install graphviz)
#   macOS:                  brew install graphviz
```

Add a section to `README.md` (place it under Quick Start / dependencies):

```markdown
## Graphviz (topology diagram)

The CDP physical topology export (`*-cdp-topology.drawio`) uses the Graphviz
`dot` engine to lay out and route the diagram. Graphviz is a **system
dependency** (a binary on your PATH), not a Python package — install it
separately:

- **Linux (Debian/Ubuntu):** `sudo apt install graphviz`
- **Linux (RHEL/Fedora):** `sudo dnf install graphviz`
- **Windows:** `winget install Graphviz.Graphviz` (or `choco install graphviz`),
  or download the installer from graphviz.org and add its `bin\` folder to PATH.
- **macOS:** `brew install graphviz`

If `dot` is not found, the tool skips the topology diagram (with a reminder) and
all other outputs are produced normally.
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_topology_dot.py::test_docs_mention_graphviz_install -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add requirements.txt README.md test_topology_dot.py
git commit -m "docs: Graphviz system dependency + install instructions"
```

---

## Self-Review

**Spec coverage:**
- Graphviz `dot` via subprocess (`-Tplain`), no pygraphviz → Task 5 (`_run_dot`).
- Root = max-degree overall → Task 3 (`build_pages` global root).
- Overview + per-aggregation A3 pages; aggregation = degree ≥ 6; 2-hop pruned at aggregations → Task 3.
- Editable multi-page `.drawio`; Graphviz coords → geometry (y flipped, SCALE=72); edge bend-points → waypoints; labels attached by the emitter (not in DOT) → Task 4.
- Rogue labels with model + mgmt IP → Tasks 1 (`mgmt_ip`) + 2 (`node_label`).
- `dot`-missing skip with install message → Task 5.
- Graphviz in `requirements.txt` + README (Linux/Windows) → Task 6.
- Remove old BFS `layout_topology` + single-page `generate_cdp_topology_xml` → Task 5.

**Placeholder scan:** No TBD/TODO/vague steps — every code step is complete; the `dot`-format assumptions were verified against real `dot -Tplain` output (fixture in Task 2 is real).

**Type consistency:** `TopologyNode(name, is_rogue, platform="", mgmt_ip="")`, `Page(title, node_names, root_name, a3)`, `NodeBox`, `EdgeRoute`, `ParsedLayout(width, height, nodes, edges)`, and `node_label`/`to_dot`/`parse_plain`/`build_pages`/`generate_cdp_topology_drawio` signatures match across the tasks that define and consume them. `to_dot` returns `(dot, id_to_name)`; the orchestrator threads `id_to_name` into `generate_cdp_topology_drawio` alongside the `ParsedLayout`.
