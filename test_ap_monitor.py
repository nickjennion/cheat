#!/usr/bin/env python3
"""Unit tests for ap_monitor data layer."""

import pytest


# --- build_table_rows ---

def test_row_shows_moved_ap():
    from ap_monitor import build_table_rows
    aps = [{"id": "ap-1", "hostname": "AP-001", "upTime": "2 days, 4 hours"}]
    topology = {"ap-1": "SW-NEW (GigabitEthernet2/0/1)"}
    events = {"ap-1": "SW-OLD (GigabitEthernet1/0/5)"}

    rows = build_table_rows(aps, topology, events, False, False)

    assert rows[0]["current"] == "SW-NEW (GigabitEthernet2/0/1)"
    assert rows[0]["previous"] == "SW-OLD (GigabitEthernet1/0/5)"


def test_row_no_change_shows_sentinel():
    from ap_monitor import build_table_rows
    aps = [{"id": "ap-1", "hostname": "AP-001", "upTime": "5 days"}]
    topology = {"ap-1": "SW-A (GigabitEthernet1/0/5)"}
    events = {"ap-1": "SW-A (GigabitEthernet1/0/5)"}

    rows = build_table_rows(aps, topology, events, False, False)

    assert rows[0]["current"] == "N/A — No Change"
    assert rows[0]["previous"] == "N/A — No Change"


def test_row_offline_ap():
    from ap_monitor import build_table_rows
    aps = [{"id": "ap-1", "hostname": "AP-001", "upTime": ""}]
    topology = {"ap-1": None}
    events = {"ap-1": None}

    rows = build_table_rows(aps, topology, events, False, False)

    assert rows[0]["current"] == "— (offline)"
    assert rows[0]["previous"] == "— (no data)"


def test_row_topology_error():
    from ap_monitor import build_table_rows
    aps = [{"id": "ap-1", "hostname": "AP-001", "upTime": "1 day"}]

    rows = build_table_rows(aps, {}, {}, topology_error=True, events_error=False)

    assert rows[0]["current"] == "— (error)"


def test_row_events_error():
    from ap_monitor import build_table_rows
    aps = [{"id": "ap-1", "hostname": "AP-001", "upTime": "1 day"}]
    topology = {"ap-1": "SW-A (GigabitEthernet1/0/1)"}

    rows = build_table_rows(aps, topology, {}, topology_error=False, events_error=True)

    assert rows[0]["previous"] == "— (error)"
    assert rows[0]["current"] == "SW-A (GigabitEthernet1/0/1)"


def test_row_no_events_data():
    from ap_monitor import build_table_rows
    aps = [{"id": "ap-1", "hostname": "AP-001", "upTime": "3 days"}]
    topology = {"ap-1": "SW-A (GigabitEthernet1/0/1)"}
    events = {"ap-1": None}

    rows = build_table_rows(aps, topology, events, False, False)

    assert rows[0]["previous"] == "— (no data)"
    assert rows[0]["current"] == "SW-A (GigabitEthernet1/0/1)"


# --- _ap_matches ---

def test_ap_matches_include_term():
    from ap_monitor import _ap_matches
    ap = {"hostname": "AP-BLDG-A-001", "platformId": "AIR-AP2802I"}
    assert _ap_matches(ap, ["bldg-a"], []) is True
    assert _ap_matches(ap, ["bldg-b"], []) is False


def test_ap_matches_exclude_term():
    from ap_monitor import _ap_matches
    ap = {"hostname": "AP-OOB-001", "platformId": "AIR-AP2802I"}
    assert _ap_matches(ap, [], ["oob"]) is False
    assert _ap_matches(ap, [], ["mgmt"]) is True


def test_ap_matches_or_within_term():
    from ap_monitor import _ap_matches
    ap = {"hostname": "AP-BLDG-B-005", "platformId": "AIR-AP2802I"}
    assert _ap_matches(ap, ["bldg-a|bldg-b"], []) is True
    assert _ap_matches(ap, ["bldg-c|bldg-d"], []) is False


# --- _parse_numbers ---

def test_parse_numbers_single():
    from ap_monitor import _parse_numbers
    assert _parse_numbers("3", 10) == [3]


def test_parse_numbers_range():
    from ap_monitor import _parse_numbers
    assert _parse_numbers("2-4", 10) == [2, 3, 4]


def test_parse_numbers_out_of_bounds():
    from ap_monitor import _parse_numbers
    assert _parse_numbers("15", 10) == []
