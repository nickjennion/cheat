# Design: Access Point — Monitor Physical Movements

**Date:** 2026-07-03
**Scope:** `dnac_client.py`, `ap_monitor.py` (new), `main_latest.py`

---

## Problem

During AP upgrade/relocation projects, field techs move APs between switch ports and stacks. There is no in-tool way to see at a glance which APs have moved (old upstream → new upstream) vs. which are still where they were. Users currently have no choice but to call the cabling team for status updates.

---

## Feature

**Access Point — Monitor Physical Movements** — an on-demand table showing selected APs, their uptime, their previous CDP upstream (as of 24 hours ago via Assurance events), and their current CDP upstream (live from physical topology). Refreshes on keypress.

---

## Architecture

Three new/modified components:

| Component | Change |
|-----------|--------|
| `ap_monitor.py` | New module — filter/select screen, results table, display logic |
| `dnac_client.py` | Three new methods: `get_ap_devices()`, `get_ap_topology()`, `get_ap_events()` |
| `main_latest.py` | New `action_ap_monitor()` function; menu_2 gains option 4 |

---

## Screens

### Filter & Select Screen

- Identical mechanics to menu_4 (switch selection).
- Top half: AP list (hostname, model, management IP). Empty until at least one filter is applied — enforced, cannot proceed without one.
- Bottom half: `f <term>` (include), `r <term>` (exclude), `fc` (clear all), number-toggle selection, `p` to proceed (min 1 AP selected), `b` to go back.
- Device scope: `family=Unified AP` only — switches never appear regardless of filter terms.
- No slow-mode or copper-only toggles (not applicable).

### Results Table

Columns:

| AP Hostname | Uptime | Previous Upstream (24h) | Current Upstream |
|-------------|--------|-------------------------|-----------------|

**Row states:**

- **Moved:** Previous Upstream = `switch-a (GiX/0/Y)`, Current Upstream = `switch-b (GiX/0/Z)`
- **No change:** both CDP columns show `N/A — No Change`
- **No historical data:** Previous Upstream = `— (no data)`, Current Upstream = live value
- **Offline/unmanaged:** both CDP columns show `— (offline)`
- **API error (topology):** Current Upstream = `— (error)`
- **API error (events):** Previous Upstream = `— (error)` for all APs; Current column still renders

**Keys:**

| Key | Action |
|-----|--------|
| `r` | Refresh — re-queries both current topology and 24h events, redraws table |
| `e` | Export current table view to Excel (`excel_reports/ap-monitor-<stem>-<ts>.xlsx`) |
| `b` | Back to filter/select screen |

---

## API Calls

### 1. `get_ap_devices()`
```
GET /dna/intent/api/v1/network-device?family=Unified AP
```
Paginated (500/page), same pattern as existing `get_devices()`. Returns AP inventory: id, hostname, uptime, platformId, managementIpAddress.

### 2. `get_ap_topology(ap_ids: list[str])`
```
GET /dna/intent/api/v1/topology/physical-topology
```
Walks the returned link/edge list to find each AP's upstream node and port. Returns `{ap_id: "switch-hostname (port)"}`. APs with no link → marked offline.

### 3. `get_ap_events(ap_ids: list[str], hours: int = 24)`
```
GET /dna/data/api/v1/assuranceEvents
```
Filters by device IDs and time window (`startTime = now - hours`, `endTime = now`). Looks for CDP/neighbor-change event types. Extracts the last known upstream for each AP before its current connection. Returns `{ap_id: "switch-hostname (port)"}`. APs with no events in window → `None` (rendered as `— (no data)`).

> **Note:** Exact Assurance event type filters (`eventCategory`, `eventType`) need validation against the target DNAC environment during implementation. If the events endpoint proves unreliable, a local snapshot approach (capture baseline CDP at session start, compare on refresh) is the nominated fallback — see §Future Work.

---

## Menu Integration

**`menu_2`** gains a fourth option:

```
1) Auth & Get Devices (All)
2) Auth & Get DNAC Version
3) Auth & Get Sites
4) Access Point — Monitor Physical Movements
0) Back

Select [0-4]:
```

`action_ap_monitor(host, username, password)` in `main_latest.py` authenticates, calls `ap_monitor.run(client)`, and returns when the user exits.

---

## Error Handling

- Topology call fails → all Current Upstream cells show `— (error)`; uptime and Previous columns still render
- Events call fails → all Previous Upstream cells show `— (error)`; rest of table still renders
- Zero APs match filter → show message, cannot proceed to selection
- Zero APs selected → show message, cannot proceed to results
- Refresh during results → re-queries both endpoints; partial failures handled per-column as above

---

## Files Changed

| File | Change |
|------|--------|
| `ap_monitor.py` | New — filter/select screen, results table renderer, `run()` entry point |
| `dnac_client.py` | Add `get_ap_devices()`, `get_ap_topology()`, `get_ap_events()` |
| `main_latest.py` | Add `action_ap_monitor()`; add option 4 to menu_2; update prompt to `[0-4]` |

---

## Future Work

- **Snapshot fallback:** If Assurance events proves unreliable in the target environment, capture a CDP baseline dict at session start (first time the results screen loads) and use it as "previous" on subsequent refreshes. The column header would change from `Previous Upstream (24h)` to `Baseline Upstream (session start)`.
- **Configurable lookback window:** Currently hardcoded at 24 hours; could be a prompt on the filter screen.
