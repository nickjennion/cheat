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
