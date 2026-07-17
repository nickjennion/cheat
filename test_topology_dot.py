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
