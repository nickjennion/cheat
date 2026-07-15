SW1_CDP = "\n".join([
    "Device ID        Local Intrfce     Holdtme    Capability  Platform  Port ID",
    "sw2              Gig 1/0/3         169              S I   C9KV-UADP Gig 1/0/2",
    "sw3              Gig 1/0/1         156              S I   C9KV-UADP Gig 1/0/2",
    "sw4              Gig 0/0           137              S I   C9KV-UADP Gig 0/0",
    "deskphone        Gig 1/0/9         120              H P   IP-Phone  Port 1",
    "Total cdp entries displayed : 4",
])
# sw2 sees sw1 back on the reciprocal ports (tests bidirectional dedup).
SW2_CDP = "\n".join([
    "Device ID        Local Intrfce     Holdtme    Capability  Platform  Port ID",
    "sw1              Gig 1/0/2         169              S I   C9KV-UADP Gig 1/0/3",
    "Total cdp entries displayed : 1",
])


def _raw():
    return {"sw1": SW1_CDP, "sw2": SW2_CDP, "sw3": ""}


def test_build_topology_nodes_and_rogue_flag():
    from cdp_topology import build_topology
    topo = build_topology(_raw(), ["sw1", "sw2", "sw3"])
    by_name = {n.name: n for n in topo.nodes}
    assert set(by_name) == {"sw1", "sw2", "sw3", "sw4"}
    assert by_name["sw4"].is_rogue is True
    assert by_name["sw4"].platform == "C9KV-UADP"
    assert by_name["sw1"].is_rogue is False
    assert "deskphone" not in by_name  # phone (Capability H P) excluded


def test_build_topology_dedups_bidirectional_link():
    from cdp_topology import build_topology
    topo = build_topology(_raw(), ["sw1", "sw2", "sw3"])
    # sw1<->sw2 seen from both ends must collapse to ONE edge.
    sw1_sw2 = [e for e in topo.edges
               if {e.a, e.b} == {"sw1", "sw2"}]
    assert len(sw1_sw2) == 1
    e = sw1_sw2[0]
    assert {e.a_port, e.b_port} == {"Gi1/0/3", "Gi1/0/2"}
    # Three switch links total: sw1-sw2, sw1-sw3, sw1-sw4.
    assert len(topo.edges) == 3
    rogue_edge = [e for e in topo.edges if "sw4" in (e.a, e.b)]
    assert len(rogue_edge) == 1


def test_layout_root_is_top_and_highest_degree():
    from cdp_topology import build_topology, layout_topology
    topo = build_topology(_raw(), ["sw1", "sw2", "sw3"])
    pos = layout_topology(topo)
    assert set(pos) == {"sw1", "sw2", "sw3", "sw4"}
    # sw1 has degree 3 (sw2, sw3, sw4) -> it is the root, at the top (min y).
    min_y = min(y for _, y in pos.values())
    assert pos["sw1"][1] == min_y
    # A rogue leaf sits one level below its parent.
    assert pos["sw4"][1] > pos["sw1"][1]


def test_layout_stacks_disconnected_components_below():
    from cdp_topology import build_topology, layout_topology
    # sw5 is scanned but has no CDP neighbours -> its own component.
    raw = dict(_raw())
    raw["sw5"] = ""
    topo = build_topology(raw, ["sw1", "sw2", "sw3", "sw5"])
    pos = layout_topology(topo)
    # sw1's component occupies the top band; the isolated sw5 lands below all of it.
    first_component_max_y = max(pos[n][1] for n in ("sw1", "sw2", "sw3", "sw4"))
    assert pos["sw5"][1] > first_component_max_y
