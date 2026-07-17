from datetime import datetime

import pytest


def test_site_location_full_hostname():
    from interface_parser import site_location
    assert site_location("hu-chi-f1-edge-01") == ("hu", "chi")


def test_site_location_no_floor_segment():
    from interface_parser import site_location
    assert site_location("hu-chi-border-01") == ("hu", "chi")


def test_site_location_variable_length_site():
    from interface_parser import site_location
    assert site_location("syd-cbd-edge-01") == ("syd", "cbd")


def test_site_location_single_hyphen():
    from interface_parser import site_location
    assert site_location("SW-GOOD") == ("SW", "GOOD")


def test_site_location_no_hyphen():
    from interface_parser import site_location
    assert site_location("switch") == ("switch", "")


def test_site_location_empty():
    from interface_parser import site_location
    assert site_location("") == ("", "")


def test_is_physical_iface_true_for_ethernet_ports():
    from interface_parser import is_physical_iface
    assert is_physical_iface("Gi1/0/5") is True
    assert is_physical_iface("Te1/1/1") is True
    assert is_physical_iface("Fa0/1") is True


def test_is_physical_iface_false_for_logical():
    from interface_parser import is_physical_iface
    assert is_physical_iface("Vlan10") is False
    assert is_physical_iface("Po1") is False
    assert is_physical_iface("Lo0") is False
    assert is_physical_iface("Tunnel1") is False
    assert is_physical_iface("") is False


def test_interface_record_has_last_link_change_default():
    from interface_parser import InterfaceRecord
    assert InterfaceRecord().last_link_change == ""


def test_parse_clock_reads_device_time():
    from interface_parser import parse_clock
    text = "some banner\n*12:34:56.789 AEST Sun Jul 6 2026\nmore"
    assert parse_clock(text) == datetime(2026, 7, 6, 12, 34, 56)


def test_parse_clock_returns_none_when_absent():
    from interface_parser import parse_clock
    assert parse_clock("no clock line here") is None


def test_parse_log_timestamp_without_year_uses_ref():
    from interface_parser import parse_log_timestamp
    assert parse_log_timestamp("Jul  6 12:34:56.789", 2026) == datetime(2026, 7, 6, 12, 34, 56)


def test_parse_log_timestamp_with_explicit_year():
    from interface_parser import parse_log_timestamp
    assert parse_log_timestamp("Jul  6 2025 12:34:56", 2026) == datetime(2025, 7, 6, 12, 34, 56)


def test_format_age_ranges():
    from interface_parser import format_age
    assert format_age(30) == "<1m"
    assert format_age(14 * 60) == "14m"
    assert format_age(2 * 3600 + 13 * 60) == "2h13m"
    assert format_age(2 * 3600) == "2h"
    assert format_age(3 * 86400 + 4 * 3600) == "3d4h"
    assert format_age(3 * 86400) == "3d"


CLOCK_LINE = "*12:00:00.000 AEST Sun Jul 6 2026"


def test_parse_updown_events_keeps_most_recent_per_iface():
    from interface_parser import parse_updown_events
    now = datetime(2026, 7, 6, 12, 0, 0)
    text = "\n".join([
        "*Jul  6 09:00:00.000: %LINK-3-UPDOWN: Interface GigabitEthernet1/0/5, changed state to down",
        "*Jul  6 09:00:05.000: %LINEPROTO-5-UPDOWN: Line protocol on Interface GigabitEthernet1/0/5, changed state to up",
        "*Jul  6 11:30:00.000: %LINK-3-UPDOWN: Interface GigabitEthernet1/0/6, changed state to up",
    ])
    events = parse_updown_events(text, 2026, now)
    assert events["Gi1/0/5"] == datetime(2026, 7, 6, 9, 0, 5)
    assert events["Gi1/0/6"] == datetime(2026, 7, 6, 11, 30, 0)


def test_parse_updown_events_year_rollover():
    from interface_parser import parse_updown_events
    now = datetime(2026, 1, 2, 12, 0, 0)
    # Event in December must be treated as the prior year, not the future.
    text = "*Dec 31 23:59:00.000: %LINK-3-UPDOWN: Interface GigabitEthernet1/0/5, changed state to down"
    events = parse_updown_events(text, 2026, now)
    assert events["Gi1/0/5"] == datetime(2025, 12, 31, 23, 59, 0)


def test_compute_link_changes_event_wins():
    from interface_parser import compute_link_changes
    text = "\n".join([
        CLOCK_LINE,
        "Log Buffer (16384 bytes):",
        "*Jul  6 09:47:00.000: %LINK-3-UPDOWN: Interface GigabitEthernet1/0/5, changed state to up",
    ])
    out = compute_link_changes(text, ["Gi1/0/5"])
    assert out["Gi1/0/5"] == "2h13m"


def test_compute_link_changes_stable_floor_for_no_event():
    from interface_parser import compute_link_changes
    text = "\n".join([
        CLOCK_LINE,
        "Log Buffer (16384 bytes):",
        "*Jun 30 12:00:00.000: %SYS-5-CONFIG_I: Configured from console",  # oldest buffered line, 6d ago
        "*Jul  6 09:47:00.000: %LINK-3-UPDOWN: Interface GigabitEthernet1/0/5, changed state to up",
    ])
    out = compute_link_changes(text, ["Gi1/0/6"])  # port with no UPDOWN event
    assert out["Gi1/0/6"] == "stable ≥6d"


def test_compute_link_changes_stable_floor_with_tz_suffix():
    from interface_parser import compute_link_changes
    # `service timestamps log datetime ... show-timezone` adds a TZ token (AEST)
    # before the colon; the buffer floor must still resolve.
    text = "\n".join([
        CLOCK_LINE,
        "Log Buffer (16384 bytes):",
        "*Jun 30 12:00:00.000 AEST: %SYS-5-CONFIG_I: Configured from console",
        "*Jul  6 09:47:00.000 AEST: %LINK-3-UPDOWN: Interface GigabitEthernet1/0/5, changed state to up",
    ])
    out = compute_link_changes(text, ["Gi1/0/6"])
    assert out["Gi1/0/6"] == "stable ≥6d"


def test_compute_link_changes_unknown_without_clock():
    from interface_parser import compute_link_changes
    text = "Log Buffer (16384 bytes):\n*Jul  6 09:47:00.000: %LINK-3-UPDOWN: Interface GigabitEthernet1/0/5, changed state to up"
    out = compute_link_changes(text, ["Gi1/0/5"])
    assert out["Gi1/0/5"] == "unknown"


def test_compute_link_changes_empty_without_logging():
    from interface_parser import compute_link_changes
    out = compute_link_changes(CLOCK_LINE, ["Gi1/0/5"])
    assert out == {}


def test_compute_link_changes_unknown_when_no_timestamped_lines():
    from interface_parser import compute_link_changes
    # Logging block present and clock resolves, but no timestamped syslog lines
    # and no UPDOWN event -> horizon is None -> unknown floor.
    text = "\n".join([CLOCK_LINE, "Log Buffer (16384 bytes):"])
    out = compute_link_changes(text, ["Gi1/0/6"])
    assert out["Gi1/0/6"] == "unknown"


def test_parse_output_populates_last_link_change():
    from interface_parser import parse_output
    text = "\n".join([
        "GigabitEthernet1/0/5 is up, line protocol is up (connected)",
        "  Last input 00:00:01, output 00:00:00, output hang never",
        "GigabitEthernet1/0/6 is up, line protocol is up (connected)",
        "  Last input 00:00:02, output 00:00:00, output hang never",
        "*12:00:00.000 AEST Sun Jul 6 2026",
        "Log Buffer (16384 bytes):",
        "*Jul  6 09:47:00.000: %LINK-3-UPDOWN: Interface GigabitEthernet1/0/5, changed state to up",
    ])
    records, _ = parse_output(text, "sw-a")
    by_iface = {r.iface: r for r in records}
    assert by_iface["Gi1/0/5"].last_link_change == "2h13m"
    # Physical port with no UPDOWN event gets the stable floor, not blank.
    assert by_iface["Gi1/0/6"].last_link_change == "stable ≥2h13m"


def test_parse_output_standalone_3560_populates_model():
    from interface_parser import parse_output
    # A fixed (non-stacking) 3560CX reports itself as member 1 in the version
    # stack table, but its ports are slot 0 (Gi0/1). The model must still resolve.
    text = "\n".join([
        "show hardware",
        "Cisco IOS Software, C3560CX Software (C3560CX-UNIVERSALK9-M), Version 15.2(7)E6",
        "HOSTNAME uptime is 18 weeks, 4 days, 6 hours, 30 minutes",
        "cisco WS-C3560CX-8PC-S (APM86XXX) processor (revision G0) with 524288K bytes of memory.",
        "Model number                    : WS-C3560CX-8PC-S",
        "",
        "Switch Ports Model                     SW Version            SW Image",
        "------ ----- -----                     ----------            ----------",
        "*    1 12    WS-C3560CX-8PC-S          15.2(7)E6             C3560CX-UNIVERSALK9-M",
        "",
        "GigabitEthernet0/1 is up, line protocol is up (connected)",
        "  Last input 00:00:01, output 00:00:00, output hang never",
    ])
    records, _ = parse_output(text, "HOSTNAME")
    rec = {r.iface: r for r in records}["Gi0/1"]
    assert rec.model == "WS-C3560CX-8PC-S"
    assert rec.sw_version == "15.2(7)E6"
    assert rec.uptime == "18 weeks, 4 days, 6 hours, 30 minutes"


def test_parse_output_no_logging_leaves_blank():
    from interface_parser import parse_output
    text = "\n".join([
        "GigabitEthernet1/0/5 is up, line protocol is up (connected)",
        "  Last input 00:00:01, output 00:00:00, output hang never",
    ])
    records, _ = parse_output(text, "sw-a")
    assert records[0].last_link_change == ""


_CDP_DETAIL_COL = "\n".join([
    "show cdp neighbors detail",
    "-------------------------",
    "Device ID: dist-4500xv.net.hu.edu",
    "Entry address(es):",
    "  IP address: 10.20.1.5",
    "Platform: cisco WS-C4500X-32,  Capabilities: Router Switch IGMP",
    "Interface: GigabitEthernet1/0/1,  Port ID (outgoing port): TenGigabitEthernet2/1/24",
    "Management address(es):",
    "  IP address: 10.99.99.9",
    "-------------------------",
    "Device ID: SEP00ecab",
    "Entry address(es):",
    "  IP address: 10.20.9.5",
    "Platform: Cisco IP Phone 6901,  Capabilities: Host Phone",
    "Interface: GigabitEthernet1/0/1,  Port ID (outgoing port): Port 1",
    "Total cdp entries displayed : 2",
])


def test_parse_cdp_neighbors_enriched_cell():
    from interface_parser import parse_cdp_neighbors
    cell = parse_cdp_neighbors(_CDP_DETAIL_COL)["Gi1/0/1"]
    # both neighbours on the same local interface, comma-joined, with mgmt IP.
    assert "dist-4500xv.net.hu.edu (Te2/1/24) 10.99.99.9" in cell
    assert "SEP00ecab (Port 1) 10.20.9.5" in cell           # phone included
    assert cell.count(",") == 1                              # exactly two joined
