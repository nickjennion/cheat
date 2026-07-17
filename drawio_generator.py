"""
draw.io diagram generation for CHEAT — SDA site hierarchy.

Produces a multi-page .drawio file:
  Page 1  — Site hierarchy tree (Global → Area → Building → Floor)
  Page N  — Per-building SDA topology (Border / CP / WLC / Edge nodes)
  Page N+ — Per-floor AP layout (scaled canvas, AP icons at X/Y positions)
"""

import xml.etree.ElementTree as ET

from topology_dot import node_label


# ============================================================================
# Styles
# ============================================================================

SITE_STYLES = {
    "global":   "rounded=1;whiteSpace=wrap;html=1;fillColor=#014F74;fontColor=#ffffff;strokeColor=#014F74;fontStyle=1;fontSize=11;",
    "area":     "rounded=1;whiteSpace=wrap;html=1;fillColor=#1e6091;fontColor=#ffffff;strokeColor=#1e6091;fontStyle=1;fontSize=10;",
    "building": "rounded=1;whiteSpace=wrap;html=1;fillColor=#2d8a4e;fontColor=#ffffff;strokeColor=#2d8a4e;fontSize=10;",
    "floor":    "rounded=0;whiteSpace=wrap;html=1;fillColor=#e8f5e9;fontColor=#1b5e20;strokeColor=#2d8a4e;fontSize=9;",
    "unknown":  "rounded=1;whiteSpace=wrap;html=1;fillColor=#999999;fontColor=#ffffff;strokeColor=#666666;fontSize=10;",
}

DEVICE_STYLES = {
    "border":          "shape=mxgraph.cisco.routers.router;html=1;pointerEvents=1;dashed=0;fillColor=#036897;strokeColor=#ffffff;strokeWidth=2;verticalLabelPosition=bottom;verticalAlign=top;align=center;outlineConnect=0;fontColor=#ffffff;fontSize=9;",
    "control-plane":   "shape=mxgraph.cisco.servers.standard_server;html=1;pointerEvents=1;dashed=0;fillColor=#dae8fc;strokeColor=#6c8ebf;verticalLabelPosition=bottom;verticalAlign=top;align=center;outlineConnect=0;fontSize=9;",
    "edge":            "shape=mxgraph.cisco.switches.catalyst_702x_702x;html=1;pointerEvents=1;dashed=0;fillColor=#f5f5f5;strokeColor=#666666;verticalLabelPosition=bottom;verticalAlign=top;align=center;outlineConnect=0;fontColor=#333333;fontSize=9;",
    "wlc":             "shape=mxgraph.cisco.wireless.wireless_lan_controller;html=1;pointerEvents=1;dashed=0;fillColor=#f8cecc;strokeColor=#b85450;verticalLabelPosition=bottom;verticalAlign=top;align=center;outlineConnect=0;fontSize=9;",
    "ap":              "shape=mxgraph.cisco.wireless.access_point;html=1;pointerEvents=1;dashed=0;fillColor=#d5e8d4;strokeColor=#82b366;verticalLabelPosition=bottom;verticalAlign=top;align=center;outlineConnect=0;fontSize=8;",
}

CDP_TOPO_ROGUE_STYLE = (
    "shape=mxgraph.cisco.switches.catalyst_702x_702x;html=1;pointerEvents=1;dashed=0;"
    "fillColor=#f8cecc;strokeColor=#b85450;verticalLabelPosition=bottom;verticalAlign=top;"
    "align=center;outlineConnect=0;fontColor=#333333;fontSize=9;"
)
CDP_TOPO_EDGE_STYLE = "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;jettySize=auto;fontSize=8;"
CDP_TOPO_HEADER = 80   # vertical space reserved for title + legend

CDP_TOPO_SCALE = 72        # graphviz inches -> draw.io px
CDP_GV_SCANNED_STYLE = DEVICE_STYLES["edge"]
CDP_GV_ROGUE_STYLE = CDP_TOPO_ROGUE_STYLE
CDP_GV_EDGE_STYLE = "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=none;fontSize=8;"

EDGE_STYLE       = "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;exitX=0.5;exitY=1;exitDx=0;exitDy=0;entryX=0.5;entryY=0;entryDx=0;entryDy=0;"
FABRIC_EDGE      = "edgeStyle=orthogonalEdgeStyle;rounded=0;strokeColor=#014F74;strokeWidth=2;exitX=0.5;exitY=1;exitDx=0;exitDy=0;entryX=0.5;entryY=0;entryDx=0;entryDy=0;"
AP_EDGE          = "edgeStyle=orthogonalEdgeStyle;dashed=1;strokeColor=#82b366;strokeWidth=1;"
FLOOR_BG_STYLE   = "rounded=0;whiteSpace=wrap;html=1;fillColor=#f5f5f5;strokeColor=#d6b656;strokeWidth=2;fontStyle=1;fontSize=11;verticalAlign=top;spacingTop=6;"

# Node sizes
SW, SH = 160, 40    # site hierarchy nodes
DW, DH = 56, 56     # device icons
AW, AH = 40, 40     # AP icons
SCALE   = 3         # floor canvas: 1 ft → SCALE px

H_GAP, V_GAP = 80, 20   # hierarchy gaps


# ============================================================================
# Helpers
# ============================================================================

def _site_type(site: dict) -> str:
    for info in (site.get("additionalInfo") or []):
        t = (info.get("attributes") or {}).get("type", "")
        if t:
            return t
    return "unknown"


def _site_attrs(site: dict) -> dict:
    attrs = {}
    for info in (site.get("additionalInfo") or []):
        attrs.update(info.get("attributes") or {})
    return attrs


def _build_tree(sites):
    id_to_site = {s["id"]: s for s in sites}
    children = {s["id"]: [] for s in sites}
    root_id = None
    for s in sites:
        pid = s.get("parentId")
        if not pid or pid not in id_to_site:
            root_id = s["id"]
        else:
            children[pid].append(s["id"])
    return id_to_site, children, root_id


def _new_root():
    root = ET.Element("mxGraphModel")
    root.set("grid", "1"); root.set("gridSize", "10")
    root.set("pageWidth", "1654"); root.set("pageHeight", "1169")
    root.set("math", "0"); root.set("shadow", "0")
    mx_root = ET.SubElement(root, "root")
    ET.SubElement(mx_root, "mxCell", id="0")
    ET.SubElement(mx_root, "mxCell", id="1", parent="0")
    return root, mx_root


def _add_cell(parent, cid, value, style, x, y, w, h, vertex="1"):
    cell = ET.SubElement(parent, "mxCell",
                         id=cid, value=value, style=style,
                         vertex=vertex, parent="1")
    ET.SubElement(cell, "mxGeometry",
                  x=str(int(x)), y=str(int(y)),
                  width=str(int(w)), height=str(int(h)),
                  **{"as": "geometry"})
    return cell


def _add_edge(parent, eid, src, tgt, style=EDGE_STYLE, label=""):
    cell = ET.SubElement(parent, "mxCell",
                         id=eid, value=label, style=style,
                         edge="1", source=src, target=tgt, parent="1")
    ET.SubElement(cell, "mxGeometry", relative="1", **{"as": "geometry"})
    return cell


# ============================================================================
# Page 1 — Site hierarchy tree
# ============================================================================

def _layout_tree(node_id, depth, x_off, id_to_site, children):
    kids = children.get(node_id, [])
    cells = []
    if not kids:
        cells.append({"id": node_id, "x": x_off, "y": depth * (SH + H_GAP), "w": SW, "h": SH})
        return SW, cells
    child_x = x_off
    total_w = 0
    for cid in kids:
        cw, cc = _layout_tree(cid, depth + 1, child_x, id_to_site, children)
        cells.extend(cc)
        child_x += cw + V_GAP
        total_w += cw + V_GAP
    total_w -= V_GAP
    node_x = x_off + (total_w - SW) / 2
    cells.append({"id": node_id, "x": node_x, "y": depth * (SH + H_GAP), "w": SW, "h": SH})
    return total_w, cells


def _site_label(site):
    name = site.get("name", "?")
    attrs = _site_attrs(site)
    lines = [name]
    addr = attrs.get("address", "")
    if addr:
        lines.append(addr[:45] + ("…" if len(addr) > 45 else ""))
    lat = attrs.get("latitude", "")
    lon = attrs.get("longitude", "")
    if lat and lon:
        lines.append(f"{float(lat):.4f}, {float(lon):.4f}")
    return "\n".join(lines)


def _build_hierarchy_page(sites):
    id_to_site, children, root_id = _build_tree(sites)
    if not root_id:
        return None

    _, cells = _layout_tree(root_id, 0, 0, id_to_site, children)
    root, mx_root = _new_root()

    cell_id_map = {}
    for i, c in enumerate(cells, start=2):
        site = id_to_site[c["id"]]
        stype = _site_type(site)
        xid = str(i)
        cell_id_map[c["id"]] = xid
        _add_cell(mx_root, xid, _site_label(site),
                  SITE_STYLES.get(stype, SITE_STYLES["unknown"]),
                  c["x"], c["y"], c["w"], c["h"])

    ei = len(cells) + 2
    for s in sites:
        pid = s.get("parentId")
        if pid and pid in cell_id_map and s["id"] in cell_id_map:
            _add_edge(mx_root, str(ei), cell_id_map[pid], cell_id_map[s["id"]])
            ei += 1

    ET.indent(root, space="  ")
    return root


# ============================================================================
# Page 2 — Per-building SDA topology
# ============================================================================

def _build_topology_page(building, devices):
    root, mx_root = _new_root()

    attrs = _site_attrs(building)
    title = f"{building.get('name','')} — SDA Fabric Topology"

    _add_cell(mx_root, "title", title,
              "text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;whiteSpace=wrap;fontStyle=1;fontSize=14;",
              200, 10, 600, 40)

    fabric_roles = {"border": [], "control-plane": [], "wlc": [], "edge": []}
    for d in devices:
        role = d.get("fabricRole", "edge")
        if role in fabric_roles:
            fabric_roles[role].append(d)

    # Layout: border + CP + WLC in a row at top, edge nodes below grouped by floor
    col_configs = [
        ("border",        "Border Node(s)",         100,  100),
        ("control-plane", "Control Plane",           350,  100),
        ("wlc",           "Wireless Controller(s)",  600,  100),
    ]

    cell_map = {}  # device id → xml cell id
    cid = 2

    # Header nodes
    for role, label, bx, by in col_configs:
        devs = fabric_roles[role]
        _add_cell(mx_root, f"hdr-{role}", label,
                  "text;html=1;strokeColor=none;fillColor=none;align=center;fontStyle=1;fontSize=10;",
                  bx - 20, by - 30, DW + 40, 24)
        for j, d in enumerate(devs):
            xid = str(cid); cid += 1
            x = bx + j * (DW + 20)
            y = by
            hostname = d.get("hostname", d.get("id", "?"))
            model = d.get("platformId", "")
            ip = d.get("managementIpAddress", "")
            lbl = f"{hostname}\n{model}\n{ip}"
            _add_cell(mx_root, xid, lbl, DEVICE_STYLES.get(role, DEVICE_STYLES["edge"]), x, y, DW, DH)
            cell_map[d["id"]] = xid

    # Edge nodes — group by floor
    edge_devs = fabric_roles["edge"]
    by_floor: dict[str, list] = {}
    for d in edge_devs:
        sid = d.get("siteId", "")
        by_floor.setdefault(sid, []).append(d)

    floor_y = 280
    floor_x = 80
    floor_spacing = 260

    for fi, (floor_sid, floor_devs) in enumerate(by_floor.items()):
        fx = floor_x + fi * floor_spacing
        # Floor label box
        floor_name = floor_sid  # will be overridden below if we have the name
        _add_cell(mx_root, f"floor-lbl-{fi}",
                  f"Floor: {floor_sid[-8:]}",
                  "text;html=1;strokeColor=none;fillColor=none;align=center;fontStyle=2;fontSize=9;",
                  fx - 10, floor_y - 24, 200, 20)
        for j, d in enumerate(floor_devs):
            xid = str(cid); cid += 1
            x = fx + j * (DW + 24)
            y = floor_y
            hostname = d.get("hostname", d.get("id", "?"))
            model = d.get("platformId", "")
            ip = d.get("managementIpAddress", "")
            lbl = f"{hostname}\n{model}\n{ip}"
            _add_cell(mx_root, xid, lbl, DEVICE_STYLES["edge"], x, y, DW, DH)
            cell_map[d["id"]] = xid

    # Edges: border → CP, border → WLC, CP → each edge
    border_ids = [cell_map[d["id"]] for d in fabric_roles["border"] if d["id"] in cell_map]
    cp_ids     = [cell_map[d["id"]] for d in fabric_roles["control-plane"] if d["id"] in cell_map]
    wlc_ids    = [cell_map[d["id"]] for d in fabric_roles["wlc"] if d["id"] in cell_map]
    edge_ids   = [cell_map[d["id"]] for d in edge_devs if d["id"] in cell_map]

    for b in border_ids:
        for cp in cp_ids:
            _add_edge(mx_root, str(cid), b, cp, FABRIC_EDGE); cid += 1
        for w in wlc_ids:
            _add_edge(mx_root, str(cid), b, w, FABRIC_EDGE); cid += 1

    for cp in cp_ids:
        for e in edge_ids:
            _add_edge(mx_root, str(cid), cp, e, FABRIC_EDGE); cid += 1

    ET.indent(root, space="  ")
    return root


# ============================================================================
# Page 3+ — Per-floor AP layout
# ============================================================================

def _build_floor_page(floor_site, aps):
    root, mx_root = _new_root()

    attrs = _site_attrs(floor_site)
    length = float(attrs.get("length", 100))   # feet
    width  = float(attrs.get("width",  100))
    height = float(attrs.get("height", 10))
    floor_idx = attrs.get("floorIndex", "?")
    rf_model  = attrs.get("rfModel", "")

    canvas_w = int(length * SCALE)
    canvas_h = int(width  * SCALE)

    title = floor_site.get("name", "Floor")
    info  = f"Dimensions: {length:.0f}ft × {width:.0f}ft × {height:.0f}ft ceiling  |  RF: {rf_model}  |  {len(aps)} APs"

    _add_cell(mx_root, "title", title,
              "text;html=1;strokeColor=none;fillColor=none;align=left;fontStyle=1;fontSize=13;",
              10, 10, 600, 32)
    _add_cell(mx_root, "info", info,
              "text;html=1;strokeColor=none;fillColor=none;align=left;fontSize=9;fontColor=#666666;",
              10, 40, 800, 20)

    # Floor boundary rectangle
    OFFSET_Y = 80
    _add_cell(mx_root, "floor-bg", "",
              FLOOR_BG_STYLE, 10, OFFSET_Y, canvas_w, canvas_h)

    for i, ap in enumerate(aps, start=2):
        xid = str(i)
        # AP X/Y in fixture are in feet; scale to pixels
        ax = 10 + int(float(ap.get("x", 0)) * SCALE) - AW // 2
        ay = OFFSET_Y + int(float(ap.get("y", 0)) * SCALE) - AH // 2
        name  = ap.get("name", ap.get("id", "AP"))
        model = ap.get("model", "")
        mac   = ap.get("macAddress", "")
        lbl   = f"{name}\n{model}"
        _add_cell(mx_root, xid, lbl, DEVICE_STYLES["ap"], ax, ay, AW, AH)

    ET.indent(root, space="  ")
    return root


# ============================================================================
# CDP Topology renderer
# ============================================================================

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


# ============================================================================
# CDP Topology multi-page draw.io emitter
# ============================================================================

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


# ============================================================================
# Public API
# ============================================================================

def generate_drawio(
    sites: list,
    devices: list = None,
    access_points: list = None,
    title: str = "DNAC Site Hierarchy",
) -> str:
    """
    Return draw.io XML string (multi-page).

    Page 1  — Site hierarchy tree
    Page N  — Per-building SDA topology  (if devices provided)
    Page N+ — Per-floor AP layout        (if access_points provided)
    """
    devices       = devices or []
    access_points = access_points or []

    id_to_site, children, root_id = _build_tree(sites)

    pages = []

    # Page 1: hierarchy
    p1 = _build_hierarchy_page(sites)
    if p1 is not None:
        pages.append(("Site Hierarchy", p1))

    # Identify buildings
    buildings = [s for s in sites if _site_type(s) == "building"]
    floors_all = [s for s in sites if _site_type(s) == "floor"]

    for building in buildings:
        bname = building.get("name", "Building")

        # Page: SDA topology for this building
        bdevices = [d for d in devices if d.get("siteId") == building["id"]]
        # Also pull devices assigned to child floors
        child_floor_ids = {s["id"] for s in floors_all if s.get("parentId") == building["id"]}
        bdevices += [d for d in devices if d.get("siteId") in child_floor_ids]
        if bdevices:
            p = _build_topology_page(building, bdevices)
            pages.append((f"{bname} — Topology", p))

        # Pages: per-floor AP layout
        bfloors = sorted(
            [s for s in floors_all if s.get("parentId") == building["id"]],
            key=lambda s: int(_site_attrs(s).get("floorIndex", 0) or 0)
        )
        for floor in bfloors:
            faps = [ap for ap in access_points if ap.get("siteId") == floor["id"]]
            p = _build_floor_page(floor, faps)
            pages.append((floor.get("name", "Floor"), p))

    # Assemble into single document with <diagram> per page
    doc_root = ET.Element("mxfile", host="CHEAT", version="21.0.0")
    for page_name, page_root in pages:
        diagram = ET.SubElement(doc_root, "diagram", name=page_name)
        diagram.append(page_root)

    ET.indent(doc_root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(doc_root, encoding="unicode")
