"""Correlate device-tracking output across switches into the IP/MAC per VLAN report."""

HEADER = """\
Binding Table has 9 entries, 0 dynamic (limit 200000)
Codes: L - Local, S - Static, ND - Neighbor Discovery, ARP - Address Resolution Protocol
Preflevel flags (prlvl):
0001:MAC and LLA match     0002:Orig trunk            0004:Orig access

    Network Layer Address               Link Layer Address     Interface  vlan     prlvl      age    state
"""

UNSUPPORTED = "show device-tracking database\n     ^\n% Invalid input detected at '^' marker.\n"


def _row(code, ip, mac, iface, vlan, state="REACHABLE", age="145s"):
    return f"{code:<4}{ip:<36}{mac:<23}{iface:<11}{vlan:<9}0005       {age:<7}{state}\n"


def _out(*rows):
    return HEADER + "".join(rows)


def test_keeps_only_the_requested_vlans():
    from ip_mac_report import build_ip_mac_report
    outputs = {"sw-01": _out(
        _row("ARP", "10.0.5.10", "0011.2233.4455", "Gi1/0/1", "5"),
        _row("ARP", "10.0.9.10", "0011.2233.9999", "Gi1/0/2", "9"),
    )}
    report = build_ip_mac_report(outputs, ["5"])
    assert [r.ip for r in report.rows] == ["10.0.5.10"]
    assert [r.vlan for r in report.rows] == ["5"]


def test_drops_local_and_static_rows_and_counts_them():
    from ip_mac_report import build_ip_mac_report
    outputs = {"sw-01": _out(
        _row("L", "10.0.5.1", "0000.0c9f.f001", "Vl5", "5"),
        _row("S", "10.0.5.2", "0000.0c9f.f002", "Gi1/0/9", "5"),
        _row("ARP", "10.0.5.10", "0011.2233.4455", "Gi1/0/1", "5"),
    )}
    report = build_ip_mac_report(outputs, ["5"])
    assert [r.ip for r in report.rows] == ["10.0.5.10"]
    assert report.excluded_local == 2


def test_flags_one_ip_held_by_two_macs():
    from ip_mac_report import build_ip_mac_report, DUPLICATE_IP_NOTE
    outputs = {"sw-01": _out(
        _row("ARP", "10.0.5.10", "0011.2233.aaaa", "Gi1/0/1", "5"),
        _row("ARP", "10.0.5.10", "0011.2233.bbbb", "Gi1/0/2", "5"),
    )}
    report = build_ip_mac_report(outputs, ["5"])
    assert len(report.rows) == 2
    expected = DUPLICATE_IP_NOTE.format(n=2)
    assert all(expected in r.notes for r in report.rows)


def test_the_switches_own_svi_cannot_false_flag_an_endpoint():
    """An L row sharing an address with an endpoint must not read as a conflict:
    flags are computed after the local rows are dropped."""
    from ip_mac_report import build_ip_mac_report
    outputs = {"sw-01": _out(
        _row("L", "10.0.5.10", "0000.0c9f.f001", "Vl5", "5"),
        _row("ARP", "10.0.5.10", "0011.2233.aaaa", "Gi1/0/1", "5"),
    )}
    report = build_ip_mac_report(outputs, ["5"])
    assert len(report.rows) == 1
    assert report.rows[0].notes == ""


def test_flags_a_mac_seen_on_two_switches():
    from ip_mac_report import build_ip_mac_report, MULTI_SWITCH_NOTE
    outputs = {
        "sw-01": _out(_row("ARP", "10.0.5.10", "0011.2233.aaaa", "Gi1/0/1", "5")),
        "sw-02": _out(_row("ARP", "10.0.5.10", "0011.2233.aaaa", "Gi1/0/7", "5")),
    }
    report = build_ip_mac_report(outputs, ["5"])
    assert len(report.rows) == 2
    assert all(MULTI_SWITCH_NOTE in r.notes for r in report.rows)


def test_both_flags_can_land_on_one_row():
    from ip_mac_report import build_ip_mac_report, DUPLICATE_IP_NOTE, MULTI_SWITCH_NOTE
    outputs = {
        "sw-01": _out(
            _row("ARP", "10.0.5.10", "0011.2233.aaaa", "Gi1/0/1", "5"),
            _row("ARP", "10.0.5.10", "0011.2233.bbbb", "Gi1/0/2", "5"),
        ),
        "sw-02": _out(_row("ARP", "10.0.5.99", "0011.2233.aaaa", "Gi1/0/7", "5")),
    }
    report = build_ip_mac_report(outputs, ["5"])
    both = [r for r in report.rows
            if r.switch == "sw-01" and r.mac == "0011.2233.aaaa"]
    assert len(both) == 1
    notes = both[0].notes
    assert DUPLICATE_IP_NOTE.format(n=2) in notes
    assert MULTI_SWITCH_NOTE in notes
    assert "; " in notes          # semicolon-joined, as av_mac_report does


def test_records_a_switch_that_cannot_run_the_command():
    from ip_mac_report import build_ip_mac_report
    outputs = {
        "sw-legacy": UNSUPPORTED,
        "sw-01": _out(_row("ARP", "10.0.5.10", "0011.2233.aaaa", "Gi1/0/1", "5")),
    }
    report = build_ip_mac_report(outputs, ["5"])
    assert report.unsupported == ["sw-legacy"]
    assert report.no_bindings == []
    assert len(report.rows) == 1


def test_records_a_switch_with_no_endpoints_in_the_requested_vlans():
    from ip_mac_report import build_ip_mac_report
    outputs = {
        "sw-empty": _out(_row("ARP", "10.0.9.10", "0011.2233.9999", "Gi1/0/2", "9")),
        "sw-svi-only": _out(_row("L", "10.0.5.1", "0000.0c9f.f001", "Vl5", "5")),
        "sw-01": _out(_row("ARP", "10.0.5.10", "0011.2233.aaaa", "Gi1/0/1", "5")),
    }
    report = build_ip_mac_report(outputs, ["5"])
    assert sorted(report.no_bindings) == ["sw-empty", "sw-svi-only"]
    assert report.unsupported == []


def test_vlan_switches_lists_only_switches_that_yielded_an_endpoint():
    from ip_mac_report import build_ip_mac_report
    outputs = {
        "sw-01": _out(_row("ARP", "10.0.5.10", "0011.2233.aaaa", "Gi1/0/1", "5")),
        "sw-02": _out(_row("L", "10.0.5.1", "0000.0c9f.f001", "Vl5", "5")),
    }
    report = build_ip_mac_report(outputs, ["5", "2003"])
    assert report.vlan_switches == {"5": ["sw-01"], "2003": []}


def test_rows_sort_by_ip_numerically_within_a_port():
    from ip_mac_report import build_ip_mac_report
    outputs = {"sw-01": _out(
        _row("ARP", "10.0.5.10", "0011.2233.bbbb", "Gi1/0/1", "5"),
        _row("ARP", "10.0.5.9", "0011.2233.aaaa", "Gi1/0/1", "5"),
    )}
    report = build_ip_mac_report(outputs, ["5"])
    assert [r.ip for r in report.rows] == ["10.0.5.9", "10.0.5.10"]


def test_counts_non_ipv4_bindings_across_switches():
    from ip_mac_report import build_ip_mac_report
    outputs = {"sw-01": _out(
        _row("ND", "2001:db8::10", "0011.2233.cccc", "Gi1/0/1", "5"),
        _row("ARP", "10.0.5.10", "0011.2233.aaaa", "Gi1/0/1", "5"),
    )}
    report = build_ip_mac_report(outputs, ["5"])
    assert report.non_ipv4 == 1
    assert len(report.rows) == 1


def test_carries_state_age_and_stack_member_through():
    from ip_mac_report import build_ip_mac_report
    outputs = {"sw-01": _out(
        _row("ARP", "10.0.5.10", "0011.2233.aaaa", "Fi2/0/32", "5",
             state="STALE", age="30s"),
    )}
    row = build_ip_mac_report(outputs, ["5"]).rows[0]
    assert (row.switch, row.stack_member, row.interface) == ("sw-01", "2", "Fi2/0/32")
    assert (row.state, row.age) == ("STALE", "30s")
