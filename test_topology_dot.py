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


def test_node_label_rogue_includes_feeding_description():
    from topology_dot import node_label
    n = TopologyNode("r", is_rogue=True, platform="WS-C3560C",
                     mgmt_ip="10.0.0.9", description="Link to 11P1 cab")
    assert node_label(n) == "r\nWS-C3560C\n10.0.0.9\nLink to 11P1 cab\n(unscanned)"
    # empty description / ip segments are omitted
    n2 = TopologyNode("r2", is_rogue=True, platform="X")
    assert node_label(n2) == "r2\nX\n(unscanned)"


def test_edge_label_index_aggregates_parallel_ports():
    from drawio_generator import _edge_label_index
    topo = Topology(
        nodes=[TopologyNode("acc", is_rogue=False), TopologyNode("dist", is_rogue=False)],
        edges=[TopologyEdge("acc", "Te1/1/3", "dist", "Te1/1/9"),
               TopologyEdge("acc", "Te2/1/4", "dist", "Te2/1/9")],
    )
    idx = _edge_label_index(topo)
    assert idx[frozenset(("acc", "dist"))] == "Te1/1/3 ↔ Te1/1/9, Te2/1/4 ↔ Te2/1/9"


def test_to_dot_keeps_parallel_edges():
    # Two physical links between the same switch pair (e.g. a dual uplink to a
    # VSS 4500 that reports one CDP device id) must both be emitted, not
    # collapsed to a single line.
    from topology_dot import to_dot
    topo = Topology(
        nodes=[TopologyNode("acc", is_rogue=False), TopologyNode("dist", is_rogue=False)],
        edges=[TopologyEdge("acc", "Te1/1/3", "dist", "Te1/1/15"),
               TopologyEdge("acc", "Te2/1/4", "dist", "Te2/1/16")],
    )
    dot, _ = to_dot(topo, ["acc", "dist"], "dist")
    assert dot.count("->") == 2                       # both links, not 1
    assert dot.count("constraint=false") == 1         # 2nd parallel link is non-ranking


def test_to_dot_structure():
    from topology_dot import to_dot
    dot, id_to_name = to_dot(_topo(), ["dist", "acc1", "rogue-x"], "dist")
    assert "rankdir=TB" in dot and "splines=spline" in dot   # default reliable mode
    dot_o, _ = to_dot(_topo(), ["dist", "acc1", "rogue-x"], "dist", spline_mode="ortho")
    assert "splines=ortho" in dot_o                            # mode is selectable
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
    assert "curved=1" in xml                       # smooth curved edges
    # the port label rides near the downstream (target) end, not mid-line
    lbl = [c for c in root.iter("mxCell")
           if c.get("value") == "Gi1/0/1 ↔ Gi0/0" and c.get("vertex") == "1"]
    assert lbl and "edgeLabel" in lbl[0].get("style", "")
    assert lbl[0].find("mxGeometry").get("x") == "0.75"


def test_node_style_plain_vs_stencil():
    from drawio_generator import _node_style
    scanned = TopologyNode("s", is_rogue=False)
    rogue = TopologyNode("r", is_rogue=True)
    # plain = clean rectangle, no cisco stencil
    assert "mxgraph.cisco" not in _node_style(scanned, "plain")
    assert "#f5f5f5" in _node_style(scanned, "plain")
    assert "#f8cecc" in _node_style(rogue, "plain")
    # plain scanned is a real rectangle (not just "no cisco")
    assert "rounded=0" in _node_style(scanned, "plain") and "whiteSpace=wrap" in _node_style(scanned, "plain")
    # stencil = valid Cisco switch icon, grey scanned / red rogue
    st = _node_style(scanned, "stencil")
    assert "shape=mxgraph.cisco.switches.workgroup_switch" in st and "#f5f5f5" in st
    st_r = _node_style(rogue, "stencil")
    assert "#f8cecc" in st_r and "#b85450" in st_r and "mxgraph.cisco" in st_r


def test_generate_cdp_topology_drawio_icons_toggle():
    from cdp_topology import Topology, TopologyNode as TN, TopologyEdge as TE
    from topology_dot import ParsedLayout, NodeBox, EdgeRoute
    from drawio_generator import generate_cdp_topology_drawio
    topo = Topology(nodes=[TN("dist", is_rogue=False), TN("r", is_rogue=True)],
                    edges=[TE("dist", "Gi1/0/1", "r", "Gi0/0")])
    layout = ParsedLayout(width=4.0, height=2.0,
                          nodes={"n0": NodeBox(1.0, 1.5, 0.8, 0.5), "n1": NodeBox(1.0, 0.5, 0.8, 0.5)},
                          edges=[EdgeRoute("n0", "n1", [(1.0, 1.25), (1.0, 0.75)])])
    pages = [("Overview", layout, {"n0": "dist", "n1": "r"})]
    assert "workgroup_switch" in generate_cdp_topology_drawio(pages, topo, icons="stencil")
    assert "mxgraph.cisco" not in generate_cdp_topology_drawio(pages, topo, icons="plain")


def test_generate_cdp_topology_drawio_no_label_edge_has_no_child_cell():
    # An edge with no port label must not emit an empty edgeLabel child cell.
    import xml.etree.ElementTree as ET
    from topology_dot import ParsedLayout, NodeBox, EdgeRoute
    from drawio_generator import generate_cdp_topology_drawio
    topo = Topology(
        nodes=[TopologyNode("a", is_rogue=False), TopologyNode("b", is_rogue=False)],
        edges=[],  # no topology edges -> the label lookup is empty
    )
    layout = ParsedLayout(
        width=2.0, height=2.0,
        nodes={"n0": NodeBox(0.5, 1.5, 0.5, 0.3), "n1": NodeBox(0.5, 0.5, 0.5, 0.3)},
        edges=[EdgeRoute("n0", "n1", [(0.5, 1.2), (0.5, 0.8)])],
    )
    xml = generate_cdp_topology_drawio([("Test", layout, {"n0": "a", "n1": "b"})], topo)
    root = ET.fromstring(xml.split("?>", 1)[1])
    assert [c for c in root.iter("mxCell") if "edgeLabel" in (c.get("style") or "")] == []


def _pyramid_topo():
    # dist(4500) — acc-9300 & acc-3560 hang off it (middle); the 3560/9200 that
    # hang off those (not off a 4500) are desk (bottom); a router with no known
    # model token defaults to the middle.
    nodes = [TopologyNode(n, is_rogue=False) for n in (
        "core-4500-1", "acc-9300-a", "acc-3560-b", "desk-3560-x",
        "desk-9200-y", "edge-router-z")]
    edges = [
        TopologyEdge("core-4500-1", "Te1/1", "acc-9300-a", "Gi0/1"),
        TopologyEdge("core-4500-1", "Te1/2", "acc-3560-b", "Gi0/1"),
        TopologyEdge("acc-9300-a", "Gi0/2", "desk-3560-x", "Gi0/1"),
        TopologyEdge("acc-3560-b", "Gi0/2", "desk-9200-y", "Gi0/1"),
        TopologyEdge("core-4500-1", "Te1/3", "edge-router-z", "Gi0/0"),
    ]
    return Topology(nodes=nodes, edges=edges)


def test_switch_tier_by_hostname_model():
    from topology_dot import switch_tier
    assert switch_tier("core-4500-1", near_dist=False) == 0     # 4500 -> top always
    assert switch_tier("acc-9300-a", near_dist=True) == 1       # access under a 4500
    assert switch_tier("acc-3560-b", near_dist=True) == 1
    assert switch_tier("desk-3560-x", near_dist=False) == 2     # access model, no 4500 -> desk
    assert switch_tier("orphan-9300", near_dist=False) == 2     # 9300 not under 4500 -> desk
    assert switch_tier("edge-router-z", near_dist=True) == 1    # unknown model -> middle
    assert switch_tier("mystery-box", near_dist=False) == 1     # unknown, no 4500 -> middle


def test_pyramid_tiers_uses_adjacency():
    from topology_dot import pyramid_tiers, _adjacency
    topo = _pyramid_topo()
    tiers = pyramid_tiers([n.name for n in topo.nodes], _adjacency(topo))
    assert tiers["core-4500-1"] == 0
    assert tiers["acc-9300-a"] == 1 and tiers["acc-3560-b"] == 1
    assert tiers["desk-3560-x"] == 2 and tiers["desk-9200-y"] == 2
    assert tiers["edge-router-z"] == 1                          # unknown -> middle


def test_to_dot_pyramid_emits_rank_groups_and_soft_edges():
    from topology_dot import to_dot
    topo = _pyramid_topo()
    dot, _ = to_dot(topo, [n.name for n in topo.nodes], "core-4500-1", pyramid=True)
    assert dot.count("rank=same") == 3               # three tiers present
    assert "style=invis" in dot                       # tier-ordering anchor chain
    # every physical link is drawn but non-ranking, so links can't distort tiers
    assert dot.count("constraint=false") == 5         # all five edges
    assert "->;" not in dot                            # no bare ranking edges


def test_pyramid_layout_stacks_tiers_top_to_bottom():
    # End-to-end through the real dot binary: distribution must sit above access,
    # access above desk (graphviz plain y grows upward, so y_dist > y_acc > y_desk).
    import shutil
    import subprocess
    if not shutil.which("dot"):
        import pytest
        pytest.skip("graphviz 'dot' not installed")
    from topology_dot import to_dot, parse_plain
    topo = _pyramid_topo()
    dot, id_to_name = to_dot(topo, [n.name for n in topo.nodes], "core-4500-1",
                             pyramid=True)
    plain = subprocess.run(["dot", "-Tplain"], input=dot, capture_output=True,
                           text=True, check=True).stdout
    layout = parse_plain(plain)
    y = {id_to_name[i]: box.y for i, box in layout.nodes.items()}
    assert y["core-4500-1"] > y["acc-9300-a"] > y["desk-3560-x"]
    assert y["acc-9300-a"] == y["acc-3560-b"]         # siblings share the tier row
    assert y["desk-3560-x"] == y["desk-9200-y"]


def test_docs_mention_graphviz_install():
    from pathlib import Path
    reqs = Path("requirements.txt").read_text(encoding="utf-8").lower()
    readme = Path("README.md").read_text(encoding="utf-8").lower()
    assert "graphviz" in reqs
    assert "apt install graphviz" in readme or "apt-get install graphviz" in readme
    assert "winget install graphviz" in readme or "choco install graphviz" in readme
