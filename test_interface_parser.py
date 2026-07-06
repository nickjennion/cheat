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
