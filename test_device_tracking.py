"""Parser for `show device-tracking database` (SISF binding table, IOS-XE)."""


# Realistic output: entry count, codes legend, preflevel block, column header,
# then one local SVI row, two IPv4 endpoints (second with an upper-case MAC),
# and one IPv6 neighbour-discovery row.
SAMPLE = """\
Binding Table has 4 entries, 0 dynamic (limit 200000)
Codes: L - Local, S - Static, ND - Neighbor Discovery, ARP - Address Resolution Protocol, DH4 - IPv4 DHCP, DH6 - IPv6 DHCP, PKT - Other Packet, API - API created
Preflevel flags (prlvl):
0001:MAC and LLA match     0002:Orig trunk            0004:Orig access
0008:Orig trusted trunk    0010:Orig trusted access   0020:DHCP assigned
0040:Cga authenticated     0080:Cert authenticated    0100:Statically assigned

    Network Layer Address               Link Layer Address     Interface  vlan     prlvl      age    state     Time left
L   10.150.10.1                         0000.0c9f.f001         Vl2003     2003     0100       1441mn REACHABLE
ARP 10.150.10.50                        0011.b905.aaaa         Fi2/0/32   5        0005       145s   REACHABLE  101 s try 0
ARP 10.150.10.51                        0011.B905.BBBB         Fi2/0/34   5        0005       145s   REACHABLE  101 s try 0
ND  2001:db8::10                        0011.b905.cccc         Fi2/0/36   5        0005       30s    STALE
"""

UNSUPPORTED = """\
show device-tracking database
                ^
% Invalid input detected at '^' marker.
"""


def test_parses_the_binding_rows_only():
    from device_tracking import parse_device_tracking
    entries, non_ipv4 = parse_device_tracking(SAMPLE)
    # Legend, preflevel block and column header must not become entries.
    assert [e.ip for e in entries] == ["10.150.10.1", "10.150.10.50", "10.150.10.51"]
    assert non_ipv4 == 1


def test_extracts_every_field():
    from device_tracking import parse_device_tracking
    entries, _ = parse_device_tracking(SAMPLE)
    e = entries[1]
    assert e.code == "ARP"
    assert e.ip == "10.150.10.50"
    assert e.mac == "0011.b905.aaaa"
    assert e.interface == "Fi2/0/32"
    assert e.vlan == "5"
    assert e.prlvl == "0005"
    assert e.age == "145s"
    assert e.state == "REACHABLE"
    assert e.switch == ""       # the caller fills this in


def test_derives_stack_member_from_the_interface():
    from device_tracking import parse_device_tracking
    entries, _ = parse_device_tracking(SAMPLE)
    by_iface = {e.interface: e for e in entries}
    assert by_iface["Fi2/0/32"].stack_member == "2"
    assert by_iface["Vl2003"].stack_member == ""     # an SVI has no member


def test_lowercases_the_mac():
    from device_tracking import parse_device_tracking
    entries, _ = parse_device_tracking(SAMPLE)
    assert entries[2].mac == "0011.b905.bbbb"


def test_keeps_local_rows_for_the_caller_to_drop():
    from device_tracking import parse_device_tracking, LOCAL_CODES
    entries, _ = parse_device_tracking(SAMPLE)
    assert entries[0].code == "L"
    assert entries[0].code in LOCAL_CODES
    assert "S" in LOCAL_CODES


def test_counts_ipv6_bindings_without_returning_them():
    from device_tracking import parse_device_tracking
    entries, non_ipv4 = parse_device_tracking(SAMPLE)
    assert non_ipv4 == 1
    assert all(":" not in e.ip for e in entries)


def test_vlan_token_is_opaque():
    """The vlan column is captured loosely, so an unexpected token still parses
    and surfaces as 'no bindings' rather than an unexplained empty report."""
    from device_tracking import parse_device_tracking
    text = ("ARP 10.0.0.5   0011.2233.4455   Gi1/0/5   MgtVlan   0005   10s   REACHABLE\n")
    entries, _ = parse_device_tracking(text)
    assert len(entries) == 1
    assert entries[0].vlan == "MgtVlan"


def test_keeps_wrapped_binding_first_line_without_state_columns():
    from device_tracking import parse_device_tracking
    text = "ARP 10.0.0.9 0011.2233.4455 GigabitEthernet1/0/9 99\n"
    entries, _ = parse_device_tracking(text)
    assert len(entries) == 1
    assert entries[0].interface == "GigabitEthernet1/0/9"
    assert entries[0].vlan == "99"
    assert entries[0].state == ""


def test_detects_an_unsupported_platform():
    from device_tracking import command_unsupported
    assert command_unsupported(UNSUPPORTED) is True
    assert command_unsupported(SAMPLE) is False


def test_empty_and_garbage_input_yield_nothing():
    from device_tracking import parse_device_tracking
    assert parse_device_tracking("") == ([], 0)
    assert parse_device_tracking("hostname#\n\n") == ([], 0)
