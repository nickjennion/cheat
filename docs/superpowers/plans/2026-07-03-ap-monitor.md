# AP Monitor — Physical Movements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add "Access Point — Monitor Physical Movements" to menu_2, allowing users to filter/select Unified APs and view a live-refreshed table comparing previous (24h via Assurance events) and current (physical topology) upstream switch+port.

**Architecture:** Three new DNACClient methods fetch AP inventory, current topology, and historical Assurance events. A new `ap_monitor.py` module contains all filter/select/display logic. `main.py` gets a thin `action_ap_monitor()` wrapper and a new menu_2 option.

**Tech Stack:** Python 3.13, openpyxl, requests, unittest.mock

## Global Constraints

- Tests live at repo root alongside existing `test_*.py` files
- No new dependencies — openpyxl and requests already in requirements
- Follow existing code style: `print()` for all UI, no logging framework
- All terminal widths assume 112+ cols (existing project standard)
- Excel output goes to `excel_reports/` directory (created if absent)
- `family=Unified AP` is the exact DNAC string — do not vary capitalisation

---

### Task 1: DNACClient AP methods

**Files:**
- Modify: `dnac_client.py` — add three methods to `DNACClient`
- Create: `test_ap_client.py` — unit tests with mocked HTTP

**Interfaces:**
- Produces:
  - `DNACClient.get_ap_devices() -> list[dict]` — each dict has at minimum: `id`, `hostname`, `upTime`, `platformId`, `managementIpAddress`
  - `DNACClient.get_ap_topology(ap_ids: list[str]) -> tuple[dict[str, str | None], bool]` — `({ap_id: "switch (port)" | None}, error_bool)`
  - `DNACClient.get_ap_events(ap_ids: list[str], hours: int = 24) -> tuple[dict[str, str | None], bool]` — `({ap_id: "switch (port)" | None}, error_bool)`

---

- [ ] **Step 1: Write failing tests**

Create `test_ap_client.py`:

```python
#!/usr/bin/env python3
"""Unit tests for DNACClient AP methods."""

import time
from unittest.mock import MagicMock, patch
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
                    "previousNeighborHostname": "OLD-SWITCH",
                    "previousNeighborPort": "GigabitEthernet2/0/3",
                },
            }
        ]
    }
    mock_resp.raise_for_status = MagicMock()
    client.session.get = MagicMock(return_value=mock_resp)

    result, error = client.get_ap_events(["ap-1"], hours=24)

    assert error is False
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
    client.session.get = MagicMock(side_effect=Exception("500"))
    result, error = client.get_ap_events(["ap-1"], hours=24)
    assert error is True
    assert result == {}
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/nickjennion/ai/cheat && python -m pytest test_ap_client.py -v 2>&1 | head -30
```

Expected: ImportError or AttributeError — methods not yet defined.

- [ ] **Step 3: Implement `get_ap_devices`**

Add to `dnac_client.py` inside class `DNACClient`, after `get_sites()`:

```python
def get_ap_devices(self) -> list[dict]:
    """Get all Unified AP devices from DNAC inventory (paginated)."""
    if not self.token:
        print("Not authenticated.")
        return []

    all_aps = []
    offset = 1
    limit = 500
    page = 1

    try:
        while True:
            print(f"  [Page {page}] fetching APs {offset}-{offset + limit - 1}...", end=" ", flush=True)
            r = self.session.get(
                f"{self.base_url}/dna/intent/api/v1/network-device",
                headers={"X-Auth-Token": self.token},
                params={"family": "Unified AP", "offset": offset, "limit": limit},
                timeout=30,
            )
            r.raise_for_status()
            batch = r.json().get("response", [])
            print(f"got {len(batch)} (total: {len(all_aps) + len(batch)})", flush=True)
            if not batch:
                break
            all_aps.extend(batch)
            if len(batch) < limit:
                break
            offset += limit
            page += 1
    except Exception as e:
        print(f"Failed to get AP devices: {e}")
        return []

    return all_aps
```

- [ ] **Step 4: Implement `get_ap_topology`**

Add to `dnac_client.py` after `get_ap_devices()`:

```python
def get_ap_topology(self, ap_ids: list[str]) -> tuple[dict[str, str | None], bool]:
    """Get current upstream switch+port for each AP via physical topology.

    Returns ({ap_id: "switch (port)" | None}, error_bool).
    None means the AP has no link (offline/unmanaged).
    error_bool is True if the API call itself failed.
    """
    if not self.token:
        return {}, True

    try:
        r = self.session.get(
            f"{self.base_url}/dna/intent/api/v1/topology/physical-topology",
            headers={"X-Auth-Token": self.token},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json().get("response", {})
        nodes = {n["id"]: n.get("label") or n.get("id", "") for n in data.get("nodes", [])}
        ap_set = set(ap_ids)
        result: dict[str, str | None] = {ap_id: None for ap_id in ap_ids}

        for link in data.get("links", []):
            src = link.get("source", "")
            tgt = link.get("target", "")
            if tgt in ap_set:
                sw = nodes.get(src, src)
                port = link.get("startPortName", "")
                result[tgt] = f"{sw} ({port})" if port else sw
            elif src in ap_set:
                sw = nodes.get(tgt, tgt)
                port = link.get("endPortName", "")
                result[src] = f"{sw} ({port})" if port else sw

        return result, False

    except Exception as e:
        print(f"  Topology fetch error: {e}")
        return {}, True
```

- [ ] **Step 5: Implement `get_ap_events`**

Add to `dnac_client.py` after `get_ap_topology()`:

```python
def get_ap_events(self, ap_ids: list[str], hours: int = 24) -> tuple[dict[str, str | None], bool]:
    """Get last-known upstream before current connection via Assurance events.

    Queries /dna/data/api/v1/assuranceEvents for each AP over the last `hours`
    hours. Looks for connectivity events that include previous neighbor info.

    NOTE: Exact event field names (previousNeighborHostname, previousNeighborPort,
    neighborHostname, neighborPort) should be validated against the target DNAC
    environment. The fallback snapshot approach is documented in the design spec
    if this endpoint proves unreliable.

    Returns ({ap_id: "switch (port)" | None}, error_bool).
    None means no relevant events were found in the window.
    """
    if not self.token:
        return {}, True

    import time as _time
    end_ms = int(_time.time() * 1000)
    start_ms = end_ms - (hours * 3600 * 1000)
    result: dict[str, str | None] = {ap_id: None for ap_id in ap_ids}

    try:
        for ap_id in ap_ids:
            r = self.session.get(
                f"{self.base_url}/dna/data/api/v1/assuranceEvents",
                headers={"X-Auth-Token": self.token},
                params={
                    "deviceId": ap_id,
                    "startTime": start_ms,
                    "endTime": end_ms,
                },
                timeout=30,
            )
            if r.status_code == 404:
                continue
            r.raise_for_status()
            events = r.json().get("response", [])

            for event in sorted(events, key=lambda e: e.get("timestamp", 0)):
                details = event.get("details") or {}
                host = (details.get("previousNeighborHostname")
                        or details.get("neighborHostname")
                        or "")
                port = (details.get("previousNeighborPort")
                        or details.get("neighborPort")
                        or "")
                if host:
                    result[ap_id] = f"{host} ({port})" if port else host
                    break

        return result, False

    except Exception as e:
        print(f"  Events fetch error: {e}")
        return {}, True
```

- [ ] **Step 6: Run tests**

```bash
cd /home/nickjennion/ai/cheat && python -m pytest test_ap_client.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add dnac_client.py test_ap_client.py
git commit -m "feat: add get_ap_devices, get_ap_topology, get_ap_events to DNACClient"
```

---

### Task 2: `ap_monitor.py` — data layer

**Files:**
- Create: `ap_monitor.py` — data helpers only (no UI)
- Create: `test_ap_monitor.py` — unit tests

**Interfaces:**
- Consumes:
  - `DNACClient.get_ap_topology(ap_ids) -> tuple[dict[str, str | None], bool]`
  - `DNACClient.get_ap_events(ap_ids, hours) -> tuple[dict[str, str | None], bool]`
- Produces:
  - `build_table_rows(selected_aps, topology, events, topology_error, events_error) -> list[dict]`
    - Each dict: `{"hostname": str, "uptime": str, "previous": str, "current": str}`
  - `_ap_matches(ap, filter_terms, exclude_terms) -> bool`
  - `_filter_label(filter_terms, exclude_terms) -> str`
  - `_parse_numbers(entry, max_idx) -> list[int]`

---

- [ ] **Step 1: Write failing tests**

Create `test_ap_monitor.py`:

```python
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/nickjennion/ai/cheat && python -m pytest test_ap_monitor.py -v 2>&1 | head -20
```

Expected: ModuleNotFoundError — `ap_monitor` does not exist yet.

- [ ] **Step 3: Create `ap_monitor.py` with data layer**

Create `/home/nickjennion/ai/cheat/ap_monitor.py`:

```python
"""
Access Point — Monitor Physical Movements.

Filter/select Unified APs, then display a live-refreshed table comparing
previous upstream (Assurance events, 24h) vs current upstream (physical topology).
"""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# Sentinel display strings
_NO_CHANGE = "N/A — No Change"
_OFFLINE = "— (offline)"
_NO_DATA = "— (no data)"
_ERROR = "— (error)"

# Column display widths
_W_HOST = 42
_W_UP = 20
_W_CDP = 38


# ============================================================================
# Data Layer
# ============================================================================

def build_table_rows(
    selected_aps: list[dict],
    topology: dict[str, Optional[str]],
    events: dict[str, Optional[str]],
    topology_error: bool = False,
    events_error: bool = False,
) -> list[dict]:
    """Build display rows from AP dicts and upstream lookup dicts.

    Each row: {"hostname": str, "uptime": str, "previous": str, "current": str}
    """
    rows = []
    for ap in selected_aps:
        ap_id = ap.get("id", "")
        hostname = str(ap.get("hostname") or "unknown")
        uptime = str(ap.get("upTime") or "—")

        if topology_error:
            current = _ERROR
        else:
            val = topology.get(ap_id)
            current = val if val is not None else _OFFLINE

        if events_error:
            previous = _ERROR
        else:
            val = events.get(ap_id)
            previous = val if val is not None else _NO_DATA

        # No change: both valid, same value
        _sentinels = (_OFFLINE, _ERROR, _NO_DATA, _NO_CHANGE)
        if (current not in _sentinels
                and previous not in _sentinels
                and current == previous):
            current = _NO_CHANGE
            previous = _NO_CHANGE

        rows.append({
            "hostname": hostname,
            "uptime": uptime,
            "previous": previous,
            "current": current,
        })
    return rows


def _ap_matches(ap: dict, filter_terms: list[str], exclude_terms: list[str]) -> bool:
    """Return True if AP matches all include terms and no exclude terms.
    '|' within a term = OR alternatives. Matches hostname and platformId."""
    text = (
        (ap.get("hostname") or "") + " " + (ap.get("platformId") or "")
    ).lower()
    for term in filter_terms:
        alts = [a.strip() for a in term.split("|") if a.strip()]
        if not any(a in text for a in alts):
            return False
    for term in exclude_terms:
        alts = [a.strip() for a in term.split("|") if a.strip()]
        if any(a in text for a in alts):
            return False
    return True


def _filter_label(filter_terms: list[str], exclude_terms: list[str]) -> str:
    parts = []
    if filter_terms:
        parts.append("  AND  ".join(f"[{t}]" for t in filter_terms))
    if exclude_terms:
        parts.append("NOT " + "  NOT ".join(f"[{t}]" for t in exclude_terms))
    return "  ".join(parts) if parts else "(none)"


def _parse_numbers(entry: str, max_idx: int) -> list[int]:
    result = set()
    for part in entry.split(","):
        part = part.strip()
        if "-" in part:
            try:
                lo, hi = part.split("-", 1)
                result.update(range(int(lo), int(hi) + 1))
            except ValueError:
                pass
        elif part.isdigit():
            result.add(int(part))
    return sorted(i for i in result if 1 <= i <= max_idx)
```

- [ ] **Step 4: Run tests**

```bash
cd /home/nickjennion/ai/cheat && python -m pytest test_ap_monitor.py -v
```

Expected: all 12 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add ap_monitor.py test_ap_monitor.py
git commit -m "feat: ap_monitor data layer — build_table_rows, filter helpers"
```

---

### Task 3: `ap_monitor.py` — filter/select screen

**Files:**
- Modify: `ap_monitor.py` — add `filter_select_screen(aps)`

**Interfaces:**
- Consumes: `_ap_matches`, `_filter_label`, `_parse_numbers` (all defined in Task 2)
- Produces: `filter_select_screen(aps: list[dict]) -> list[dict]` — returns selected AP dicts, or `[]` if user pressed `b`

No new tests — this is pure UI (input/print). Manual verification in Step 3.

---

- [ ] **Step 1: Add UI helpers and `filter_select_screen` to `ap_monitor.py`**

Append to `ap_monitor.py` after the data layer section:

```python
# ============================================================================
# UI Helpers
# ============================================================================

def _clear() -> None:
    import os
    os.system("clear" if os.name != "nt" else "cls")


def _pause() -> None:
    input("\n  Press Enter to continue...")


# ============================================================================
# Filter / Select Screen
# ============================================================================

def filter_select_screen(aps: list[dict]) -> list[dict]:
    """Filter and select APs. Returns selected dicts, or [] if user pressed b."""
    filter_terms: list[str] = []
    exclude_terms: list[str] = []
    selected: set[int] = set()

    while True:
        filtered = [
            ap for ap in aps
            if _ap_matches(ap, filter_terms, exclude_terms)
        ] if (filter_terms or exclude_terms) else []

        _clear()
        print("  Access Point — Monitor Physical Movements\n")
        print(f"  Filters: {_filter_label(filter_terms, exclude_terms)}\n")

        if not filter_terms and not exclude_terms:
            print("  Add at least one filter to show matching APs.")
            print("  Use '|' for OR within a term  (e.g. f bldg-a|bldg-b)")
        elif not filtered:
            print("  No APs matched — try 'fc' to clear filters and start over.")
        else:
            print(f"  {'#':<5} {'':3} {'AP Hostname':<42} {'Model':<22} {'IP Address'}")
            print(f"  {'-'*5} {'-'*3} {'-'*42} {'-'*22} {'-'*15}")
            for i, ap in enumerate(filtered, 1):
                check = "[X]" if i in selected else "[ ]"
                h = str(ap.get("hostname") or "unknown")
                p = str(ap.get("platformId") or "")
                ip = str(ap.get("managementIpAddress") or "")
                print(f"  {i:<5} {check} {h:<42} {p:<22} {ip}")
            print(f"\n  Selected: {len(selected)} AP(s)")

        print()
        print("  'f <term>'  add filter (| = OR)  |  'r <term>'  exclude  |  'fc'  clear all")
        print("  number(s)   toggle selection (e.g. 1  or  1,3-5)")
        print("  'p'  Proceed    |    'b'  Back")
        print()
        entry = input("  > ").strip()

        if entry.lower() == "b":
            return []
        elif entry.lower() in ("p", ""):
            if not selected:
                print("\n  Select at least one AP first.")
                _pause()
            else:
                return [filtered[i - 1] for i in sorted(selected) if i <= len(filtered)]
        elif entry.lower() == "fc":
            filter_terms.clear()
            exclude_terms.clear()
            selected.clear()
        elif entry.lower().startswith("f "):
            term = entry[2:].strip().lower()
            if term:
                filter_terms.append(term)
                selected.clear()
        elif entry.lower().startswith("r "):
            term = entry[2:].strip().lower()
            if term:
                exclude_terms.append(term)
                selected.clear()
        else:
            indices = _parse_numbers(entry, len(filtered))
            if not indices:
                print("\n  Unrecognised input.")
                _pause()
            else:
                for idx in indices:
                    if idx in selected:
                        selected.discard(idx)
                    else:
                        selected.add(idx)
```

- [ ] **Step 2: Smoke-test manually**

```bash
cd /home/nickjennion/ai/cheat && python3 -c "
from ap_monitor import filter_select_screen
fake_aps = [
    {'id': '1', 'hostname': 'AP-BLDG-A-001', 'platformId': 'AIR-AP2802I', 'managementIpAddress': '10.0.0.1'},
    {'id': '2', 'hostname': 'AP-BLDG-B-001', 'platformId': 'AIR-AP2802I', 'managementIpAddress': '10.0.0.2'},
    {'id': '3', 'hostname': 'AP-OOB-MGMT',   'platformId': 'AIR-AP2802I', 'managementIpAddress': '10.0.0.3'},
]
print('Starting filter screen — test: f bldg, then r oob, then select 1, then p')
selected = filter_select_screen(fake_aps)
print(f'Selected: {[a[\"hostname\"] for a in selected]}')
"
```

Expected: filter screen appears. After `f bldg` → 3 APs show. After `r oob` → 2 APs show (OOB excluded). Select `1`, press `p` → prints `Selected: ['AP-BLDG-A-001']`.

- [ ] **Step 3: Commit**

```bash
git add ap_monitor.py
git commit -m "feat: ap_monitor filter/select screen"
```

---

### Task 4: `ap_monitor.py` — results screen, Excel export, `run()` entry point

**Files:**
- Modify: `ap_monitor.py` — add `_print_table`, `_export_excel`, `results_screen`, `run`

**Interfaces:**
- Consumes:
  - `build_table_rows(selected_aps, topology, events, topology_error, events_error) -> list[dict]`
  - `DNACClient.get_ap_topology(ap_ids) -> tuple[dict, bool]`
  - `DNACClient.get_ap_events(ap_ids, hours) -> tuple[dict, bool]`
- Produces: `run(client, aps: list[dict]) -> None`

---

- [ ] **Step 1: Append display and export helpers to `ap_monitor.py`**

```python
# ============================================================================
# Results Table
# ============================================================================

def _print_table(rows: list[dict]) -> None:
    header = (
        f"  {'AP Hostname':<{_W_HOST}} {'Uptime':<{_W_UP}} "
        f"{'Previous Upstream (24h)':<{_W_CDP}} {'Current Upstream':<{_W_CDP}}"
    )
    sep = f"  {'-'*_W_HOST} {'-'*_W_UP} {'-'*_W_CDP} {'-'*_W_CDP}"
    print(header)
    print(sep)
    for row in rows:
        moved = (
            row["previous"] not in (_NO_CHANGE, _NO_DATA, _ERROR, _OFFLINE)
            and row["current"] not in (_NO_CHANGE, _ERROR, _OFFLINE)
            and row["previous"] != row["current"]
        )
        marker = " *" if moved else "  "
        print(
            f"{marker} {row['hostname']:<{_W_HOST}} {row['uptime']:<{_W_UP}} "
            f"{row['previous']:<{_W_CDP}} {row['current']:<{_W_CDP}}"
        )


def _export_excel(rows: list[dict], stem: str) -> None:
    """Write AP movement table to Excel in excel_reports/."""
    excel_dir = Path("excel_reports").resolve()
    excel_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d-%H-%M")
    outpath = str(excel_dir / f"{stem}-{ts}.xlsx")

    headers = ["AP Hostname", "Uptime", "Previous Upstream (24h)", "Current Upstream"]
    col_widths = [_W_HOST, _W_UP, _W_CDP, _W_CDP]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "AP Movements"

    hdr_font = Font(bold=True, color="FFFFFFFF", name="Arial", size=10)
    hdr_fill = PatternFill("solid", start_color="FF2B579A")
    hdr_align = Alignment(horizontal="center", vertical="center")
    thin = Border(
        bottom=Side(style="thin", color="FFB0B0B0"),
        right=Side(style="thin", color="FFB0B0B0"),
    )
    dat_font = Font(name="Arial", size=10)
    dat_align = Alignment(vertical="center")
    moved_fill = PatternFill("solid", start_color="FFFFF3CD")   # amber — AP moved
    same_fill = PatternFill("solid", start_color="FFD4EDDA")    # green  — no change
    other_fill = PatternFill("solid", start_color="FFFFFFFF")   # white  — error/offline/no-data

    for col, (h, w) in enumerate(zip(headers, col_widths), start=1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = hdr_font
        cell.fill = hdr_fill
        cell.alignment = hdr_align
        cell.border = thin
        ws.column_dimensions[get_column_letter(col)].width = w

    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "A2"

    for row_idx, row in enumerate(rows, start=2):
        if row["current"] == _NO_CHANGE:
            fill = same_fill
        elif row["current"] not in (_ERROR, _OFFLINE) and row["previous"] not in (_NO_DATA, _ERROR, _NO_CHANGE):
            fill = moved_fill
        else:
            fill = other_fill

        for col, val in enumerate(
            [row["hostname"], row["uptime"], row["previous"], row["current"]], start=1
        ):
            cell = ws.cell(row=row_idx, column=col, value=val)
            cell.font = dat_font
            cell.alignment = dat_align
            cell.border = thin
            cell.fill = fill

    ws.auto_filter.ref = ws.dimensions
    wb.save(outpath)
    print(f"\n  ✓ Saved: {outpath}")


# ============================================================================
# Results Screen
# ============================================================================

def results_screen(client, selected_aps: list[dict]) -> None:
    """Show AP movement table. Keys: r=refresh, e=export, b=back."""
    ap_ids = [ap["id"] for ap in selected_aps]
    stem = "ap-monitor"

    while True:
        print("\n  Fetching current topology...", flush=True)
        topology, topology_error = client.get_ap_topology(ap_ids)

        print("  Fetching Assurance events (24h)...", flush=True)
        events, events_error = client.get_ap_events(ap_ids, hours=24)

        rows = build_table_rows(selected_aps, topology, events, topology_error, events_error)

        _clear()
        print("  Access Point — Monitor Physical Movements\n")
        print(f"  APs monitored: {len(selected_aps)}   * = upstream changed\n")
        _print_table(rows)
        print()
        if topology_error:
            print("  ⚠ Topology fetch failed — current upstream unavailable.")
        if events_error:
            print("  ⚠ Events fetch failed — previous upstream unavailable.")
        print()
        print("  'r' Refresh   'e' Export to Excel   'b' Back")
        print()
        key = input("  > ").strip().lower()

        if key == "b":
            return
        elif key == "r":
            _clear()
            print("  Refreshing...\n")
        elif key == "e":
            _export_excel(rows, stem)
            _pause()


# ============================================================================
# Entry Point
# ============================================================================

def run(client, aps: list[dict]) -> None:
    """Entry point: filter/select screen → results screen loop."""
    if not aps:
        print("\n  No Unified APs found in DNAC inventory.")
        _pause()
        return

    while True:
        selected = filter_select_screen(aps)
        if not selected:
            return
        results_screen(client, selected)
```

- [ ] **Step 2: Syntax check**

```bash
python3 -c "import ast; ast.parse(open('/home/nickjennion/ai/cheat/ap_monitor.py').read()); print('syntax OK')"
```

Expected: `syntax OK`

- [ ] **Step 3: Run full test suite**

```bash
cd /home/nickjennion/ai/cheat && python -m pytest test_ap_monitor.py test_ap_client.py -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add ap_monitor.py
git commit -m "feat: ap_monitor results screen, Excel export, run() entry point"
```

---

### Task 5: `main.py` — wire into menu_2

**Files:**
- Modify: `main.py` — import `ap_monitor`, add `action_ap_monitor()`, update `menu_2`

**Interfaces:**
- Consumes:
  - `ap_monitor.run(client, aps: list[dict]) -> None`
  - `DNACClient.get_ap_devices() -> list[dict]`
  - `_auth(host, username, password) -> DNACClient | None` (existing)
  - `pause()` (existing)

---

- [ ] **Step 1: Add import at top of `main.py`**

Find the existing import block:

```python
from drawio_generator import generate_drawio
import splash
```

Change to:

```python
from drawio_generator import generate_drawio
import ap_monitor
import splash
```

- [ ] **Step 2: Add `action_ap_monitor` function**

Add after `action_get_sites()` (around line 450), before the site menu functions:

```python
def action_ap_monitor(host, username, password):
    """Authenticate, fetch Unified APs, launch AP movement monitor."""
    client = _auth(host, username, password)
    if not client:
        pause()
        return

    print("\n  Fetching Unified AP inventory...\n")
    aps = client.get_ap_devices()

    if not aps:
        print("  No Unified APs found in DNAC inventory.")
        pause()
        return

    print(f"\n  ✓ {len(aps)} AP(s) loaded.")
    ap_monitor.run(client, aps)
```

- [ ] **Step 3: Update `menu_2`**

Find:

```python
def menu_2(host, username, password):
    """Action menu. Returns when user selects Back."""
    while True:
        theme_clear()
        print(f"  Host: {host}  |  User: {username}\n")
        print("  Menu 2 — Actions\n")
        print("  1) Auth & Get Devices (All)")
        print("  2) Auth & Get DNAC Version")
        print("  3) Auth & Get Sites")
        print("  0) Back")
        print()
        choice = input("  Select [0-3]: ").strip()

        if choice == "0":
            return
        elif choice == "1":
            devices, client = action_get_devices(host, username, password)
            if devices is not None:
                menu_3(devices, client, host, username)
        elif choice == "2":
            action_get_version(host, username, password)
        elif choice == "3":
            sites, client = action_get_sites(host, username, password)
            if sites is not None:
                menu_sites(sites, client, host, username)
        else:
            print("\n  Invalid selection.")
            pause()
```

Replace with:

```python
def menu_2(host, username, password):
    """Action menu. Returns when user selects Back."""
    while True:
        theme_clear()
        print(f"  Host: {host}  |  User: {username}\n")
        print("  Menu 2 — Actions\n")
        print("  1) Auth & Get Devices (All)")
        print("  2) Auth & Get DNAC Version")
        print("  3) Auth & Get Sites")
        print("  4) Access Point — Monitor Physical Movements")
        print("  0) Back")
        print()
        choice = input("  Select [0-4]: ").strip()

        if choice == "0":
            return
        elif choice == "1":
            devices, client = action_get_devices(host, username, password)
            if devices is not None:
                menu_3(devices, client, host, username)
        elif choice == "2":
            action_get_version(host, username, password)
        elif choice == "3":
            sites, client = action_get_sites(host, username, password)
            if sites is not None:
                menu_sites(sites, client, host, username)
        elif choice == "4":
            action_ap_monitor(host, username, password)
        else:
            print("\n  Invalid selection.")
            pause()
```

- [ ] **Step 4: Syntax check**

```bash
python3 -c "import ast; ast.parse(open('/home/nickjennion/ai/cheat/main.py').read()); print('syntax OK')"
```

Expected: `syntax OK`

- [ ] **Step 5: Run full test suite**

```bash
cd /home/nickjennion/ai/cheat && python -m pytest test_ap_monitor.py test_ap_client.py test_mock_dnac.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit and push**

```bash
git add main.py
git commit -m "feat: wire AP Monitor into menu_2 option 4"
git push
```
