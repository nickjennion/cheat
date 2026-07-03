#!/usr/bin/env python3
"""Unit tests for DNACClient AP methods."""

from unittest.mock import MagicMock
import pytest

from dnac_client import DNACClient


@pytest.fixture
def client():
    c = DNACClient("dnac.example.com", "admin", "password")
    c.token = "fake-token"
    return c


# --- get_ap_devices ---

def test_get_ap_devices_returns_ap_list(client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "response": [
            {"id": "ap-1", "hostname": "AP-BLDG-001", "upTime": "2 days, 4 hours",
             "platformId": "AIR-AP2802I-A-K9", "managementIpAddress": "10.0.0.1",
             "family": "Unified AP"},
        ]
    }
    mock_resp.raise_for_status = MagicMock()
    client.session.get = MagicMock(return_value=mock_resp)

    result = client.get_ap_devices()

    assert len(result) == 1
    assert result[0]["hostname"] == "AP-BLDG-001"
    call_params = client.session.get.call_args
    assert "family" in call_params.kwargs["params"]
    assert call_params.kwargs["params"]["family"] == "Unified AP"


def test_get_ap_devices_returns_empty_on_error(client):
    client.session.get = MagicMock(side_effect=Exception("connection refused"))
    result = client.get_ap_devices()
    assert result == []


# --- get_ap_topology ---

def test_get_ap_topology_finds_upstream(client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "response": {
            "nodes": [
                {"id": "ap-1", "label": "AP-BLDG-001", "family": "Unified AP"},
                {"id": "sw-1", "label": "SWITCH-CORE-01", "family": "Switches and Hubs"},
            ],
            "links": [
                {"source": "sw-1", "target": "ap-1",
                 "startPortName": "GigabitEthernet1/0/5", "endPortName": "GigabitEthernet0"},
            ],
        }
    }
    mock_resp.raise_for_status = MagicMock()
    client.session.get = MagicMock(return_value=mock_resp)

    result, error = client.get_ap_topology(["ap-1"])

    assert error is False
    assert result["ap-1"] == "SWITCH-CORE-01 (GigabitEthernet1/0/5)"


def test_get_ap_topology_none_for_offline_ap(client):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": {"nodes": [], "links": []}}
    mock_resp.raise_for_status = MagicMock()
    client.session.get = MagicMock(return_value=mock_resp)

    result, error = client.get_ap_topology(["ap-99"])

    assert error is False
    assert result["ap-99"] is None


def test_get_ap_topology_returns_error_flag_on_exception(client):
    client.session.get = MagicMock(side_effect=Exception("timeout"))
    result, error = client.get_ap_topology(["ap-1"])
    assert error is True
    assert result == {}


# --- get_ap_events ---

def test_get_ap_events_extracts_previous_upstream(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "response": [
            {
                "deviceId": "ap-1",
                "timestamp": 1000,
                "details": {
                    "previousNeighborHostname": "OLD-SWITCH-STALE",
                    "previousNeighborPort": "GigabitEthernet3/0/1",
                },
            },
            {
                "deviceId": "ap-1",
                "timestamp": 2000,
                "details": {
                    "previousNeighborHostname": "OLD-SWITCH",
                    "previousNeighborPort": "GigabitEthernet2/0/3",
                },
            },
        ]
    }
    mock_resp.raise_for_status = MagicMock()
    client.session.get = MagicMock(return_value=mock_resp)

    result, error = client.get_ap_events(["ap-1"], hours=24)

    assert error is False
    # Must return the most recent event (timestamp=2000), not the oldest (timestamp=1000)
    assert result["ap-1"] == "OLD-SWITCH (GigabitEthernet2/0/3)"


def test_get_ap_events_none_when_no_events(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"response": []}
    mock_resp.raise_for_status = MagicMock()
    client.session.get = MagicMock(return_value=mock_resp)

    result, error = client.get_ap_events(["ap-1"], hours=24)

    assert error is False
    assert result["ap-1"] is None


def test_get_ap_events_returns_error_flag_on_exception(client):
    # Auth failure still returns error flag
    client.token = None
    result, error = client.get_ap_events(["ap-1"], hours=24)
    assert error is True
    assert result == {}


def test_get_ap_events_partial_failure_continues(client):
    """A failed request for one AP must not discard results for other APs."""
    good_resp = MagicMock()
    good_resp.status_code = 200
    good_resp.json.return_value = {
        "response": [
            {
                "deviceId": "ap-2",
                "timestamp": 1000,
                "details": {
                    "previousNeighborHostname": "SW-GOOD",
                    "previousNeighborPort": "GigabitEthernet1/0/1",
                },
            }
        ]
    }
    good_resp.raise_for_status = MagicMock()

    def side_effect(*args, **kwargs):
        params = kwargs.get("params", {})
        if params.get("deviceId") == "ap-1":
            raise Exception("timeout")
        return good_resp

    client.session.get = MagicMock(side_effect=side_effect)

    result, error = client.get_ap_events(["ap-1", "ap-2"], hours=24)

    assert error is False
    assert result["ap-1"] is None        # failed AP → no data, not error
    assert result["ap-2"] == "SW-GOOD (GigabitEthernet1/0/1)"  # succeeded
