SWITCH_AND_PHONE = "\n".join([
    "show cdp neighbors detail",
    "-------------------------",
    "Device ID: x-dist-4500xv.net.example.com",
    "Entry address(es):",
    "  IP address: 10.20.1.5",
    "Platform: cisco WS-C4500X-32,  Capabilities: Router Switch IGMP ",
    "Interface: TenGigabitEthernet2/1/4,  Port ID (outgoing port): TenGigabitEthernet2/1/24",
    "Holdtime : 123 sec",
    "",
    "Version :",
    "Cisco IOS Software, Catalyst 4500 L3 Switch Software, Version 03.11.10.E",
    "",
    "advertisement version: 2",
    "Management address(es):",
    "  IP address: 10.99.99.9",
    "-------------------------",
    "Device ID: SEP00ecab",
    "Entry address(es):",
    "  IP address: 10.20.9.5",
    "  IPv6 address: ::  (global unicast)",
    "Platform: Cisco IP Phone 6901,  Capabilities: Host Phone ",
    "Interface: GigabitEthernet2/0/10,  Port ID (outgoing port): Port 1",
    "Holdtime : 171 sec",
    "-------------------------",
    "Device ID: f4747aabbcc",
    "Entry address(es):",
    "  IPv6 address: FE80::F674:70FF:FE1D:1  (link-local)",
    "Platform: Cisco C1300-24FP-4G (PID:C1300-24FP-4G),  Capabilities: Router Switch IGMP ",
    "Interface: TenGigabitEthernet2/0/4,  Port ID (outgoing port): gi23",
    "Holdtime : 165 sec",
    "",
    "Total cdp entries displayed : 3",
    "redacted#",
])


def test_parse_cdp_detail_switch_prefers_management_ip():
    from cdp_detail import parse_cdp_detail
    by = {n.device: n for n in parse_cdp_detail(SWITCH_AND_PHONE)}
    s = by["x-dist-4500xv.net.example.com"]
    assert s.mgmt_ip == "10.99.99.9"          # Management, not Entry (10.20.1.5)
    assert s.platform == "WS-C4500X-32"        # cisco prefix stripped
    assert s.capabilities.split() == ["Router", "Switch", "IGMP"]
    assert s.local_iface == "Te2/1/4"
    assert s.remote_port == "Te2/1/24"


def test_parse_cdp_detail_phone_and_ipv6_only():
    from cdp_detail import parse_cdp_detail, is_switch
    by = {n.device: n for n in parse_cdp_detail(SWITCH_AND_PHONE)}
    phone = by["SEP00ecab"]
    assert is_switch(phone) is False
    assert phone.remote_port == "Port 1"       # non-Cisco, verbatim
    assert phone.platform == "IP Phone 6901"
    assert phone.mgmt_ip == "10.20.9.5"        # entry IPv4 (no management section)
    c1300 = by["f4747aabbcc"]
    assert is_switch(c1300) is True
    assert c1300.mgmt_ip == ""                 # IPv6 link-local only
    assert c1300.platform == "C1300-24FP-4G"   # PID suffix stripped
    assert c1300.remote_port == "Gi23"         # abbreviated Cisco normalised


def test_parse_cdp_detail_counts_blocks():
    from cdp_detail import parse_cdp_detail
    assert len(parse_cdp_detail(SWITCH_AND_PHONE)) == 3
    assert parse_cdp_detail("no cdp section here") == []


def test_parse_cdp_detail_platform_and_caps_independent():
    # A malformed Platform line (no inline ", Capabilities:") must still yield
    # the platform AND the capabilities (parsed from its own line) — the switch
    # must not silently disappear.
    from cdp_detail import parse_cdp_detail, is_switch
    text = "\n".join([
        "show cdp neighbors detail",
        "-------------------------",
        "Device ID: oddsw",
        "Platform: Weird Platform Name",
        "Capabilities: Router Switch IGMP",
        "Interface: GigabitEthernet1/0/1,  Port ID (outgoing port): GigabitEthernet0/1",
        "Total cdp entries displayed : 1",
    ])
    n = parse_cdp_detail(text)[0]
    assert n.platform == "Weird Platform Name"
    assert is_switch(n) is True


def test_is_access_point():
    from cdp_detail import CdpNeighbor, is_access_point, is_switch
    ap = CdpNeighbor("b4-sw01-ap01", "", "AIR-CAP2702I", "", "Gi0/1", "Dot11Radio0")
    assert is_access_point(ap) is True
    assert is_switch(ap) is False      # Trans-Bridge, not Switch — would have been filtered
    non_ap = CdpNeighbor("b4-sw01", "", "WS-C3560", "Switch", "Gi0/2", "Gi0/1")
    assert is_access_point(non_ap) is False
