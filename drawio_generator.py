"""
draw.io diagram generation for CHEAT — site hierarchy.

Builds a .drawio XML file from a list of DNAC site dicts.
Tree layout: Global at top, then Areas, Buildings, Floors.
"""

import xml.etree.ElementTree as ET
from typing import Optional


# ============================================================================
# Style constants
# ============================================================================

STYLES = {
    "global":   "rounded=1;whiteSpace=wrap;html=1;fillColor=#014F74;fontColor=#ffffff;strokeColor=#014F74;fontStyle=1;fontSize=11;",
    "area":     "rounded=1;whiteSpace=wrap;html=1;fillColor=#1e6091;fontColor=#ffffff;strokeColor=#1e6091;fontStyle=1;fontSize=10;",
    "building": "rounded=1;whiteSpace=wrap;html=1;fillColor=#2d8a4e;fontColor=#ffffff;strokeColor=#2d8a4e;fontSize=10;",
    "floor":    "rounded=0;whiteSpace=wrap;html=1;fillColor=#e8f5e9;fontColor=#1b5e20;strokeColor=#2d8a4e;fontSize=9;",
    "unknown":  "rounded=1;whiteSpace=wrap;html=1;fillColor=#999999;fontColor=#ffffff;strokeColor=#666666;fontSize=10;",
}

EDGE_STYLE = "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;exitX=0.5;exitY=1;exitDx=0;exitDy=0;entryX=0.5;entryY=0;entryDx=0;entryDy=0;"

# Cell dimensions and spacing
W, H = 160, 40
H_GAP = 80    # vertical gap between levels
V_GAP = 20    # horizontal gap between siblings


# ============================================================================
# Helpers
# ============================================================================

def _site_type(site: dict) -> str:
    for info in (site.get("additionalInfo") or []):
        t = (info.get("attributes") or {}).get("type", "")
        if t:
            return t
    return "unknown"


def _build_tree(sites: list[dict]) -> tuple[dict, dict]:
    """Return (id_to_site, children) where children maps parent_id -> [child_ids]."""
    id_to_site = {s["id"]: s for s in sites}
    children: dict[str, list[str]] = {s["id"]: [] for s in sites}
    root_id: Optional[str] = None

    for s in sites:
        pid = s.get("parentId")
        if not pid or pid not in id_to_site:
            root_id = s["id"]
        else:
            children[pid].append(s["id"])

    return id_to_site, children, root_id


# ============================================================================
# Layout — recursive top-down placement
# ============================================================================

def _layout(node_id: str, depth: int, x_offset: float,
             id_to_site, children) -> tuple[float, list[dict]]:
    """
    Recursively assign (x, y, width, height) to each node.
    Returns (total_width_consumed, list_of_cell_dicts).
    """
    kids = children.get(node_id, [])
    cells = []

    if not kids:
        # Leaf node — occupies exactly one cell width
        cells.append({
            "id": node_id,
            "x": x_offset,
            "y": depth * (H + H_GAP),
            "w": W,
            "h": H,
        })
        return W, cells

    # Recurse into children
    child_x = x_offset
    total_w = 0
    for cid in kids:
        cw, ccells = _layout(cid, depth + 1, child_x, id_to_site, children)
        cells.extend(ccells)
        child_x += cw + V_GAP
        total_w += cw + V_GAP
    total_w -= V_GAP  # remove trailing gap

    # Centre this node over its children
    node_x = x_offset + (total_w - W) / 2
    cells.append({
        "id": node_id,
        "x": node_x,
        "y": depth * (H + H_GAP),
        "w": W,
        "h": H,
    })
    return total_w, cells


# ============================================================================
# XML builder
# ============================================================================

def _label(site: dict) -> str:
    name = site.get("name", "?")
    stype = _site_type(site)
    attrs = {}
    for info in (site.get("additionalInfo") or []):
        attrs.update(info.get("attributes") or {})
    lat  = attrs.get("latitude", "")
    lon  = attrs.get("longitude", "")
    addr = attrs.get("address", "")

    lines = [name]
    if addr:
        # Trim long addresses
        lines.append(addr[:40] + ("…" if len(addr) > 40 else ""))
    if lat and lon:
        lines.append(f"{float(lat):.4f}, {float(lon):.4f}")
    return "\n".join(lines)


def generate_drawio(sites: list[dict], title: str = "DNAC Site Hierarchy") -> str:
    """Return draw.io XML string for the given site list."""
    id_to_site, children, root_id = _build_tree(sites)

    if not root_id:
        root_id = sites[0]["id"] if sites else None
    if not root_id:
        return ""

    _, cells = _layout(root_id, 0, 0, id_to_site, children)

    # Build XML
    root = ET.Element("mxGraphModel")
    root.set("dx", "1422")
    root.set("dy", "762")
    root.set("grid", "1")
    root.set("gridSize", "10")
    root.set("guides", "1")
    root.set("tooltips", "1")
    root.set("connect", "1")
    root.set("arrows", "1")
    root.set("fold", "1")
    root.set("page", "1")
    root.set("pageScale", "1")
    root.set("pageWidth", "1169")
    root.set("pageHeight", "827")
    root.set("math", "0")
    root.set("shadow", "0")

    diagram = ET.SubElement(root, "diagram", name=title, id="site-hierarchy")
    mx_graph = ET.SubElement(diagram, "mxGraphModel")
    mx_root = ET.SubElement(mx_graph, "root")

    ET.SubElement(mx_root, "mxCell", id="0")
    ET.SubElement(mx_root, "mxCell", id="1", parent="0")

    # Node cells
    cell_id_map = {}  # site_id -> xml cell id
    for i, c in enumerate(cells, start=2):
        site = id_to_site[c["id"]]
        stype = _site_type(site)
        style = STYLES.get(stype, STYLES["unknown"])
        xml_id = str(i)
        cell_id_map[c["id"]] = xml_id

        cell = ET.SubElement(mx_root, "mxCell",
                             id=xml_id,
                             value=_label(site),
                             style=style,
                             vertex="1",
                             parent="1")
        ET.SubElement(cell, "mxGeometry",
                      x=str(int(c["x"])),
                      y=str(int(c["y"])),
                      width=str(c["w"]),
                      height=str(c["h"]),
                      **{"as": "geometry"})

    # Edge cells
    edge_i = len(cells) + 2
    for site in sites:
        pid = site.get("parentId")
        if pid and pid in cell_id_map and site["id"] in cell_id_map:
            edge_cell = ET.SubElement(
                mx_root, "mxCell",
                id=str(edge_i),
                value="",
                style=EDGE_STYLE,
                edge="1",
                source=cell_id_map[pid],
                target=cell_id_map[site["id"]],
                parent="1",
            )
            ET.SubElement(edge_cell, "mxGeometry", relative="1", **{"as": "geometry"})
            edge_i += 1

    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")
