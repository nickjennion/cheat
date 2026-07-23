"""
Graphviz DOT generation and `dot -Tplain` parsing for the CDP topology.

Pure: builds DOT strings and parses plain layout text. Running the `dot` binary
itself lives in cheat_core.
"""

from dataclasses import dataclass


def node_label(node) -> str:
    """Newline-separated display label.

    Rogue nodes carry: hostname / model / mgmt IP / feeding-port description /
    (unscanned). Empty segments are omitted.
    """
    if not node.is_rogue:
        return node.name
    parts = [node.name]
    if node.platform:
        parts.append(node.platform)
    if node.mgmt_ip:
        parts.append(node.mgmt_ip)
    if node.description:
        parts.append(node.description)
    parts.append("(unscanned)")
    return "\n".join(parts)


# Pyramid layout: hostname tokens decide the tier (distribution / access /
# desk / AP). Distribution switches carry a 4500 in the hostname; the access
# family below them are 9300/9200/3850/3560; APs match -ap in the hostname.
# See switch_tier for the full rule.
_DIST_TOKEN = "4500"
_ACCESS_TOKENS = ("9300", "9200", "3850", "3560")


def switch_tier(name: str, near_dist: bool) -> int:
    """Pyramid tier for a hostname: 0=distribution (top), 1=access (middle),
    2=desk, 3=AP (bottom).

    - hostname contains 4500                    -> 0 (distribution fibre)
    - hostname contains 9300/9200/3850/3560:
        directly cabled to a 4500               -> 1 (access)
        otherwise                               -> 2 (desk)
    - hostname contains -ap (access point)      -> 3 (AP, bottom)
    - anything else (incl. most rogue/unscanned
      nodes, whose model isn't in the hostname) -> 1 (the neutral middle)

    `near_dist` is True when the node is directly cabled to a 4500-class switch.
    """
    if _DIST_TOKEN in name:
        return 0
    if "-ap" in name.lower():
        return 3
    if any(tok in name for tok in _ACCESS_TOKENS):
        return 1 if near_dist else 2
    return 1


def pyramid_tiers(names, adj) -> dict:
    """Map each node name to its pyramid tier given the subgraph adjacency."""
    dist = {n for n in names if _DIST_TOKEN in n}
    return {n: switch_tier(n, bool(adj[n] & dist)) for n in names}


def to_dot(topology, node_names, root_name: str, a3: bool = False,
           spline_mode: str = "spline", pyramid: bool = False):
    """Return (dot_string, {synthetic_id: node_name}) for the given node subset.

    Tree edges (from a BFS spanning tree rooted at root_name) are directed
    parent->child so the aggregation ranks to the top; non-tree edges get
    constraint=false so they are drawn without distorting the ranks. Edge labels
    are intentionally omitted (the draw.io emitter labels edges itself).

    When `pyramid` is set, ranks are pinned to a classic distribution/access/desk
    three-tier hierarchy by hostname model instead (see switch_tier): every node
    is rank-grouped by tier, an invisible anchor chain orders the tiers top to
    bottom, and all physical links are drawn constraint=false so they can't
    distort those ranks. This trades the free-form BFS layout for a compact
    pyramid when the flat graph spreads too wide across the horizontal axis.

    spline_mode is the Graphviz `splines` value (default "spline" — smooth and
    node-avoiding, and reliable at full-site scale; the fragile "curved" mode
    could crash on large graphs). The draw.io emitter renders the routed path
    with curved=1 regardless, so the lines look curved either way.
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
        f"  graph [splines={spline_mode}, nodesep=0.4, ranksep={1.4 if pyramid else 0.7}];",
        "  node [shape=box, style=filled, fontsize=10];",
    ]
    if a3:
        # A3 landscape as an upper bound (no trailing "!"): a large page is
        # scaled down to fit, but a small aggregation page is left compact
        # rather than stretched to fill the whole sheet.
        lines.append('  graph [size="16.5,11.7", ratio=compress];')
    for name in names:
        node = by_name.get(name)
        fill = "#f8cecc" if (node and node.is_rogue) else "#f5f5f5"
        lbl = (node_label(node) if node else name).replace('"', "").replace("\n", "\\n")
        lines.append(f'  {id_of[name]} [label="{lbl}", fillcolor="{fill}"];')

    if pyramid:
        # Pin ranks to distribution/access/desk tiers by hostname model. Each
        # tier is a rank=same group; an invisible chain between one anchor per
        # present tier orders them top->bottom. Physical links are all drawn
        # constraint=false so within-tier links don't fight the rank grouping
        # (they still steer left/right ordering, keeping children under parents).
        tiers = pyramid_tiers(names, adj)
        present = [t for t in (0, 1, 2, 3) if any(tiers[n] == t for n in names)]
        for t in present:
            members = sorted(n for n in names if tiers[n] == t)
            grp = " ".join(id_of[m] for m in members)
            lines.append(f"  {{ rank=same; {grp}; }}")
        anchors = [sorted(n for n in names if tiers[n] == t)[0] for t in present]
        for a, b in zip(anchors, anchors[1:]):
            lines.append(f"  {id_of[a]} -> {id_of[b]} [style=invis];")
        for a, b in sub_edges:
            src, dst = (a, b) if tiers[a] <= tiers[b] else (b, a)
            lines.append(f"  {id_of[src]} -> {id_of[dst]} [constraint=false];")
        lines.append("}")
        return "\n".join(lines), {v: k for k, v in id_of.items()}

    # Emit every physical link. Parallel links between the same pair (a dual
    # uplink to a VSS switch that reports one CDP device id) must all be drawn;
    # only the first edge of a tree pair carries the rank constraint, so extra
    # parallel links are added with constraint=false and don't distort ranks.
    tree_used = set()
    for a, b in sub_edges:
        key = frozenset((a, b))
        if key in tree and key not in tree_used:
            tree_used.add(key)
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
    """Node names whose CDP-neighbour degree >= threshold, highest degree first.

    AP nodes (names containing -ap) are excluded from hub candidacy and from
    the degree count so that access switches with many APs don't get promoted
    to hubs, which would create very large pages and cause Graphviz timeouts.
    """
    adj = _adjacency(topology)
    ap_names = {n.name for n in topology.nodes if "-ap" in n.name.lower()}
    switch_degree = {
        name: len(nbrs - ap_names)
        for name, nbrs in adj.items()
        if name not in ap_names
    }
    hubs = [name for name, deg in switch_degree.items() if deg >= threshold]
    return sorted(hubs, key=lambda n: (-switch_degree[n], n))


def build_pages(topology, threshold: int = 6) -> list:
    """Overview page + one page per aggregation (its 2-hop downward neighbourhood).

    Expansion from an aggregation stops at other aggregations, so sibling
    distributions do not swallow each other's subtrees.
    """
    if not topology.nodes:
        return []
    adj = _adjacency(topology)
    ap_names = {n.name for n in topology.nodes if "-ap" in n.name.lower()}
    root = max(
        (n for n in adj if n not in ap_names),
        key=lambda n: (len(adj[n] - ap_names), n),
    )  # highest switch-only degree node as root
    all_names = [n.name for n in topology.nodes]
    pages = [Page("Overview", all_names, root, a3=False)]

    aggs = select_aggregations(topology, threshold)
    aggset = set(aggs)
    for agg in aggs:
        members = {agg}
        sibling_hubs = set()  # peer hubs reachable via shared access switches
        for nb in adj[agg]:                 # hop 1: direct neighbours
            members.add(nb)
            if nb in aggset:
                continue                    # don't expand through another hub
            for leaf in adj[nb]:            # hop 2: their leaves
                if leaf in aggset and leaf != agg:
                    sibling_hubs.add(leaf)  # dual-uplink peer — include but don't expand
                elif leaf not in aggset:
                    members.add(leaf)
        members.update(sibling_hubs)        # show dual uplinks to sibling hubs
        pages.append(Page(agg, sorted(members), agg, a3=True))
    return pages
