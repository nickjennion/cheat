CDP_BRIEF = "\n".join([
    "show cdp neighbors",
    "Capability Codes: R - Router, T - Trans Bridge, B - Source Route Bridge",
    "                  S - Switch, H - Host, I - IGMP, r - Repeater, P - Phone, ",
    "                  D - Remote, C - CVTA, M - Two-port Mac Relay ",
    "",
    "Device ID        Local Intrfce     Holdtme    Capability  Platform  Port ID",
    "sw4              Gig 0/0           137              S I   C9KV-UADP Gig 0/0",
    "sw2              Gig 1/0/3         169              S I   C9KV-UADP Gig 1/0/2",
    "deskphone-01     Gig 1/0/5         120              H P   IP-Phone  Port 1",
    "",
    "Total cdp entries displayed : 3",
    "sw1#",
])


def test_parse_cdp_switch_neighbors_keeps_only_switches():
    from unscanned_switches import parse_cdp_switch_neighbors
    nbrs = parse_cdp_switch_neighbors(CDP_BRIEF)
    devices = sorted(n.device for n in nbrs)
    assert devices == ["sw2", "sw4"]  # phone excluded


def test_parse_cdp_switch_neighbors_extracts_fields():
    from unscanned_switches import parse_cdp_switch_neighbors
    nbrs = {n.device: n for n in parse_cdp_switch_neighbors(CDP_BRIEF)}
    n = nbrs["sw4"]
    assert n.local_iface == "Gi0/0"
    assert n.capability == "S I"
    assert n.platform == "C9KV-UADP"
    assert n.neighbour_port == "Gi0/0"
    assert n.seen_on == ""
