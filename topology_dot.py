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
