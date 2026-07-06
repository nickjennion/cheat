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


from datetime import datetime


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
