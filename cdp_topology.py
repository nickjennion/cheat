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
