# Last Link Change Column — Design

**Date:** 2026-07-06
**Status:** Approved

## Summary

Add an opt-in "Last Link Change" column to the port report sheets that shows, per
physical port, the time elapsed since its most recent link-state transition
(interface up/down). The value is derived entirely from CLI output collected via
DNAC Command Runner — no SNMP, no DNAC clients endpoint. The feature is gated
behind a menu toggle so it only runs when explicitly requested.

## Motivation

DNAC's clients/assurance endpoints expose link-state timing but carry known
quirks. We want the same "how long since this port last changed state"
information sourced from CLI. On Catalyst IOS-XE (3650/3850/9300) there is no
per-port flap timer in `show interfaces` (that is NX-OS only), so the only
reliable CLI source is the syslog buffer (`show logging`), correlated against the
device clock.

## Fleet Assumptions

- Catalyst 3650 / 3850 / 9300, **IOS-XE only**.
- Collection path is **DNAC Command Runner** (whitelisted `show` commands), not
  raw SSH.
- Default logging config: `service timestamps log datetime` (absolute
  timestamps, typically without year).

## User-Facing Behaviour

### Menu / invocation

- New toggle in menu 5: `l) Toggle link-state column`, **off by default**.
- Toggle state shown in the menu 5 status line alongside slow mode / copper only.
- When **on**, port-report options 1–3 append `show logging` and `show clock` to
  the command set and populate the new column. When **off**, nothing changes —
  same commands, same output, no column.

### Column

- Header: **"Last Link Change"**, appended as the **far-right column** of the
  interface inventory sheet.
  - Appending (rather than inserting) deliberately avoids shifting the
    hardcoded highlight column indices (Member Uptime, Suspect) in
    `write_excel_sheet`.
- Present only when the toggle is on; otherwise the sheet is unchanged.
- Flows automatically onto per-device sheets **and** the consolidated
  "All Ports" tab (same write path as every other column).
- **Not** shown on the Port Utilisation summary tab (that tab is a per-switch
  aggregate, not per-port).

### Cell content (format "A" — relative time only)

- Normal: `14m`, `2h13m`, `3d4h` — time since the most recent up/down event.
- No UPDOWN event for that physical port in the buffer:
  `stable ≥Xd` where X = age of the oldest log line still in the buffer
  (an honest floor, not a false "never changed").
- Timestamps unparseable / cannot be anchored to `show clock`
  (uptime-format logs, timestamps disabled): `unknown`.
- Logical interfaces (Vlan / Port-channel / Loopback / Tunnel): **blank**.

## Detection & Timing

Per device, from the combined command output:

1. **Extract the `show logging` block and the `show clock` value** from the
   collected text.
2. **Parse UPDOWN events**: lines matching
   `%LINK-<sev>-UPDOWN: Interface <name>, changed state to up|down` and
   `%LINEPROTO-5-UPDOWN: Line protocol on Interface <name>, changed state to ...`.
   Capture interface name and the leading timestamp.
3. **Keep the most recent event per interface.** (Direction is parsed but not
   rendered in format A; it is discarded for the cell value.)
4. **Anchor to device time**: parse the absolute log timestamp (default
   `datetime` format, e.g. `Jul  6 12:34:56.789`, no year) and subtract from the
   `show clock` current time to get elapsed age. Year is inferred: assume the
   event is in the past; if the naive parse lands in the future relative to the
   clock, roll the year back by one.
5. **Format** the elapsed age as relative time (largest two units, e.g.
   `3d4h`, `2h13m`, `14m`, `45s`→`<1m`).

### Interface-name correlation

Syslog uses full interface names (`GigabitEthernet1/0/5`); report rows use short
form (`Gi1/0/5`). Normalise both through the existing
`interface_parser.shorten_iface` before matching.

### Physical vs logical classification

A port is "physical" if its (normalised) name is an Ethernet type with
`slot/port` (optionally `slot/subslot/port`) notation — e.g. `Gi1/0/5`,
`Te1/1/1`, `Fa0/1`. Vlan / Port-channel / Loopback / Tunnel / mgmt are logical
and left blank.

### Buffer horizon (for the `stable ≥Xd` floor)

The oldest parseable timestamp in the `show logging` block (any line, not just
UPDOWN) defines the buffer horizon. A physical port with no UPDOWN event gets
`stable ≥<horizon-age>`. If no timestamped line is parseable at all, physical
ports with no event fall back to `unknown`.

## Data Flow / Code Changes

- **`cheat_core.py`**: the two extra commands (`show logging`, `show clock`) are
  appended to the command list passed to `run_commands` when the toggle is on.
  The base `DNAC_COMMANDS` constant is unchanged; the caller composes the
  extended list.
- **`interface_parser.py`**:
  - New field `InterfaceRecord.last_link_change: str = ""`.
  - New pure helpers (testable in isolation):
    - parse a single UPDOWN log line → `(iface_short, timestamp, direction)` or None
    - parse `show clock` → current datetime
    - compute elapsed age from (event_ts, now) with year inference
    - format elapsed age → relative string
    - classify physical vs logical interface
    - build `{iface_short: relative_string}` map from a logging block + clock
  - `parse_output` gains an optional path: when the logging/clock text is present,
    compute the per-interface map and set `rec.last_link_change` for physical
    ports (event value, or `stable ≥Xd`, or `unknown`); logical ports stay blank.
- **`excel_generator.py`**: `write_excel_sheet` gains an `include_link_state`
  flag (default False). When True, append the "Last Link Change" header + width
  and the per-row value. `write_excel` / `write_combined_excel` thread the flag
  through.
- **`main_latest.py`**: menu 5 gains the `l` toggle, status-line label, and
  passes both the extended command list and the flag into `_exec_and_report` for
  options 1–3.

## Testing (TDD)

Pure-function unit tests first:

- UPDOWN line parse: IOS-XE `%LINK`/`%LINEPROTO` variants, full iface name →
  short form, direction captured, non-matching lines rejected.
- `show clock` parse → datetime.
- Elapsed-age computation incl. year-rollover (event in December, clock in
  January).
- Relative-time formatting across ranges (seconds, minutes, hours, days).
- Physical vs logical classification.
- End-to-end map builder: logging block + clock → `{iface: value}`, including a
  port with no event (`stable ≥Xd`) and the `unknown` fallback.

Excel-level tests:

- Column absent when `include_link_state=False`.
- Column present, far-right, populated when `include_link_state=True`.

## Out of Scope (YAGNI)

- Direction indicator and flap counts (format A is time-only).
- SNMP `ifLastChange` / DNAC clients endpoint.
- The Port Utilisation summary tab.
- Non-IOS-XE platforms (NX-OS "Last link flapped", etc.).
- Always-on collection (feature is opt-in only).
