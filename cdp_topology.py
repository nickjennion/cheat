"""
Build a physical switch topology from CDP data and lay it out for draw.io.

Pure graph building and layout — no XML, no file IO. Nodes are switches
(scanned + rogue), edges are switch<->switch CDP links.
"""

from dataclasses import dataclass, replace

from unscanned_switches import parse_cdp_switch_neighbors, _norm_host


@dataclass
class TopologyNode:
    name: str          # display name: hostname (scanned) or CDP device id (rogue)
    is_rogue: bool
    platform: str = ""  # truncated CDP platform, used in rogue labels
    mgmt_ip: str = ""   # management IP for rogue labels (from CDP detail)
    description: str = ""  # feeding scanned-port's interface description (rogue labels)


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


def build_topology(raw_outputs: dict[str, str], scanned_hostnames,
                   descriptions: dict | None = None) -> Topology:
    """Build the switch topology graph from collected CDP output.

    Graph identity is the normalised name; the first-seen original string is
    the display name. Bidirectional links (seen from both scanned ends) are
    collapsed to one undirected edge.

    descriptions maps (normalised scanned host, short local interface) ->
    interface description; a rogue node inherits the description of the scanned
    port that feeds it (first-seen parent wins).
    """
    scanned = {_norm_host(h) for h in scanned_hostnames}
    descriptions = descriptions or {}
    nodes: dict[str, TopologyNode] = {}   # norm name -> node

    def ensure_node(display: str, platform: str = "", mgmt_ip: str = "",
                    description: str = "") -> str:
        norm = _norm_host(display)
        if norm not in nodes:
            nodes[norm] = TopologyNode(
                name=display, is_rogue=norm not in scanned,
                platform=platform, mgmt_ip=mgmt_ip, description=description,
            )
        else:
            # Enrich existing node with CDP-reported platform/IP if missing.
            # Scanned nodes are added with no platform/IP; this fills them in
            # when another switch reports them as a CDP neighbour.
            n = nodes[norm]
            if platform and not n.platform:
                nodes[norm] = replace(n, platform=platform)
                n = nodes[norm]
            if mgmt_ip and not n.mgmt_ip:
                nodes[norm] = replace(n, mgmt_ip=mgmt_ip)
        return norm

    for h in scanned_hostnames:
        ensure_node(h)

    edges: dict[frozenset, TopologyEdge] = {}
    for host, text in raw_outputs.items():
        hn = ensure_node(host)
        for nb in parse_cdp_switch_neighbors(text):
            feed_desc = descriptions.get((hn, nb.local_iface), "")
            bn = ensure_node(nb.device, nb.platform, nb.mgmt_ip, feed_desc)
            if bn == hn:
                continue
            # Order-independent link key: a link seen from both ends collapses
            # to one edge. Reciprocal ports match because parse_cdp_detail
            # normalises every interface to the same short form (shorten_iface /
            # _norm_port), so this side's local_iface equals the other side's
            # neighbour_port for the same physical link.
            key = frozenset({(hn, nb.local_iface), (bn, nb.neighbour_port)})
            if key not in edges:
                edges[key] = TopologyEdge(
                    a=nodes[hn].name, a_port=nb.local_iface,
                    b=nodes[bn].name, b_port=nb.neighbour_port,
                )

    node_list = sorted(nodes.values(), key=lambda n: (n.is_rogue, n.name))
    edge_list = sorted(edges.values(), key=lambda e: (e.a, e.a_port, e.b, e.b_port))
    return Topology(nodes=node_list, edges=edge_list)


