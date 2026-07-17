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


def test_docs_mention_graphviz_install():
    from pathlib import Path
    reqs = Path("requirements.txt").read_text(encoding="utf-8").lower()
    readme = Path("README.md").read_text(encoding="utf-8").lower()
    assert "graphviz" in reqs
    assert "apt install graphviz" in readme or "apt-get install graphviz" in readme
    assert "winget install graphviz" in readme or "choco install graphviz" in readme
