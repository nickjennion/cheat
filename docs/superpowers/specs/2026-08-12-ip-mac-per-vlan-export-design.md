# Design: IP/MAC per VLAN Export (device tracking)

**Date:** 2026-08-12
**Scope:** `device_tracking.py` (new), `ip_mac_report.py` (new), `excel_generator.py`,
`cheat_core.py`, `main.py`

---

## Problem

`m) MAC/port export (for AV)` answers "which port is this MAC on". It cannot
answer "which IP does that device hold", because `show mac address-table`
carries no layer-3 information. Building a per-VLAN inventory of devices and
their addresses currently means correlating the MAC/port export against DHCP
leases or ARP tables by hand.

Catalyst 9000-class switches running IOS-XE expose the SISF binding table via
`show device-tracking database`, which prints IP, MAC, interface, VLAN and
reachability state on one line.

---

## Feature

**`d) IP/MAC per VLAN export (device tracking)`** — a new Menu 5 entry that
mirrors `m)`: the user's existing switch selection is reused, VLAN IDs are
prompted for, `show device-tracking database` runs on every selected switch, and
the parsed bindings are aggregated into one flagged spreadsheet.

---

## Sample input

```
Codes: L - Local, S - Static, ND - Neighbor Discovery, ARP - Address Resolution Protocol
Preflevel flags (prlvl):
0001:MAC and LLA match     0002:Orig trunk            0004:Orig access

Network Layer Address    Link Layer Address   Interface  vlan  prlvl  age     state
L   10.150.1.1           0000.0c9f.f001       Vl2003     2003  0100   1441mn  REACHABLE
ARP 10.150.1.50          0011.b905.aaaa       Fi2/0/32   5     0005   145s    REACHABLE  101 s try 0
ARP 10.150.1.51          0011.b905.bbbb       Fi2/0/34   5     0005   145s    REACHABLE  101 s try 0
```

Row 1 is the switch's own SVI (code `L`) and is excluded from the report.
Rows 2–3 are endpoints; `Fi2/0/32` yields stack member `2`.

---

## Architecture

The same three-layer split as the AV MAC export — parse, correlate, write —
so each layer is independently testable and carries no knowledge of the others.

| Component | Role |
|---|---|
| `device_tracking.py` *(new)* | Pure parser. `show device-tracking database` text → `DeviceTrackingEntry` records. Peer of `mac_table.py`: no VLAN filtering, no hostname knowledge, no IO. |
| `ip_mac_report.py` *(new)* | Correlator. Filters to the requested VLANs, drops local/static rows, flags duplicates → `IpMacReport`. Peer of `av_mac_report.py`. |
| `excel_generator.py` | `write_ip_mac_report_sheet` / `write_ip_mac_report_excel`, beside the AV equivalents. |
| `cheat_core.py` | `DEVICE_TRACKING_COMMANDS = ["show device-tracking database"]`. |
| `main.py` | `action_ip_mac_export()` plus the `d)` menu entry. |

---

## `device_tracking.py`

```python
LOCAL_CODES = frozenset({"L", "S"})     # switch's own address / statically configured

@dataclass
class DeviceTrackingEntry:
    switch: str = ""          # filled in by the caller
    code: str = ""            # L | S | ND | ARP | DH4 | DH6 | PKT | API
    ip: str = ""
    mac: str = ""             # lower-cased for cross-switch comparison
    interface: str = ""
    vlan: str = ""
    prlvl: str = ""
    age: str = ""
    state: str = ""
    stack_member: str = ""    # derived via interface_parser.member_from_iface

def command_unsupported(text: str) -> bool
def parse_device_tracking(text: str) -> tuple[list[DeviceTrackingEntry], int]
```

`parse_device_tracking` returns every recognised row — **including** `L` and `S`
— and the count of non-IPv4 bindings skipped. What to drop is the correlator's
decision, keeping this layer purely descriptive.

### Row recognition

A line is a binding row when it begins with a known code token, followed by an
address, a dotted-triplet MAC, an interface, a VLAN token, prlvl, age and state.
The optional `Time left` tail (`101 s try 0`) is matched but not captured, since
it is not a reported column.

Requiring both a leading code token and a dotted MAC is what excludes the
`Codes:` legend, the `Preflevel flags` block and the column header — none of
which can satisfy both anchors.

**MAC case** is normalised to lower case so the duplicate-detection sets in
`ip_mac_report` are not defeated by platform casing differences (same reason as
`mac_table.parse_mac_address_table`).

### VLAN token

The `vlan` column is captured as an opaque token (`\S+`), **not** as `\d+`.
On IOS-XE it is the numeric VLAN ID, which is the assumption the VLAN filter is
built on. Capturing it loosely means that if a platform ever prints something
else there, the row still parses and the mismatch surfaces as "no bindings in
the requested VLANs" rather than as an unexplained empty report.

### IPv6

`ND` and `DH6` bindings carry IPv6 addresses. This report is IPv4-only: those
rows are counted and returned as the second element of the tuple, so the summary
block can state how many were skipped instead of losing them silently.

### Unsupported platforms

A 3560 or 3850 answers `% Invalid input detected at '^' marker`.
`command_unsupported()` detects the IOS error markers so the correlator can
distinguish "cannot run the command" from "ran it, found nothing".

---

## `ip_mac_report.py`

```python
DUPLICATE_IP_NOTE = "Duplicate IP — held by {n} MACs"
MULTI_SWITCH_NOTE = "Seen on multiple switches"

@dataclass
class IpMacRow:
    switch, stack_member, interface, vlan, ip, mac, state, age, notes

@dataclass
class IpMacReport:
    vlan_switches: dict     # vlan -> sorted switches with surviving endpoints
    rows: list
    excluded_local: int     # L/S rows dropped, in the requested VLANs
    non_ipv4: int           # IPv6 bindings skipped by the parser
    unsupported: list       # switches that rejected the command
    no_bindings: list       # ran it, but no endpoints in the requested VLANs

def build_ip_mac_report(raw_outputs: dict, vlans: list) -> IpMacReport
```

Per switch: detect unsupported first and skip; otherwise parse, keep rows whose
VLAN token is in the requested set, drop `LOCAL_CODES` rows (counting them), and
record the switch under each VLAN it yielded an endpoint for. A switch whose only
in-VLAN rows were `L`/`S` lands in `no_bindings`, since it contributed no device.

### Flags

Computed over the surviving endpoint rows only — **after** the `L`/`S` drop — so
a switch's own SVI address can never trigger a false conflict:

- `Duplicate IP — held by N MACs` when one IP maps to more than one MAC.
- `Seen on multiple switches` when one MAC appears at more than one
  (switch, interface).

Nothing is collapsed on the strength of a flag; both notes can appear on one row,
semicolon-joined, exactly as `av_mac_report` does.

### Ordering

Rows sort by (switch, interface, IP), with the IP compared as an octet tuple so
`10.150.1.9` precedes `10.150.1.10` instead of sorting lexically.

---

## Excel output

Single sheet, `IP-MAC Per VLAN`, laid out like the AV export: summary block,
blank row, then the detail table with freeze panes and autofilter.

```
IP/MAC Bindings Found On These Switches
VLAN 5: sw-access-01, sw-access-02
VLAN 2003: not found on any selected switch
Excluded 4 local/static row(s)
Skipped 2 non-IPv4 binding(s)
1 switch did not support the command: sw-legacy-01
1 switch returned no bindings: sw-access-03
```

Exclusion lines are written only when their count is non-zero, so a clean run
shows just the VLAN lines.

| Column | Width | Source |
|---|---|---|
| Switch | 28 | `raw_outputs` key |
| Stack Member | 13 | `member_from_iface(interface)` |
| Interface | 14 | binding row |
| VLAN | 8 | binding row |
| IP Address | 18 | binding row |
| MAC Address | 20 | binding row, lower-cased |
| State | 14 | binding row |
| Age | 10 | binding row |
| Notes | 34 | flags, semicolon-joined |

Flagged rows are bold on gold (`FFFFD700`), matching `write_av_mac_report_sheet`.

---

## Menu integration

Menu 5 gains one entry after `m)`:

```
  m) MAC/port export (for AV)
  d) IP/MAC per VLAN export (device tracking)
```

and the prompt becomes `Select [1-9 / d / m / r / s / p / l / c]`.

`action_ip_mac_export(selected_devices, client, concurrency=DEFAULT_CONCURRENCY)`
prompts for VLANs, runs `DEVICE_TRACKING_COMMANDS` at the menu's concurrency,
builds the report, prints a one-line result count, prompts for a filename and
writes the workbook — the same sequence as `action_av_mac_export`.

### Two helpers extracted while working here

`action_av_mac_export` and the new action would otherwise be ~40 duplicated
lines. Two small helpers are extracted and **both** actions use them:

- `_prompt_vlans()` — prompts, splits on commas/whitespace, rejects non-numeric
  input, returns `[]` when cancelled. Identical logic in both actions today.
- `_timestamped_excel_path(filename)` — `excel_reports/<stem>-<ts>.xlsx`, with
  the directory created. This block is currently repeated four times in
  `main.py`.

Scope is deliberately limited to these two: `action_mac_search` /
`action_ip_search` share a larger duplicated display block, but that is unrelated
to this feature and is left alone.

---

## Testing

### `test_device_tracking.py` (new)

| Test | Asserts |
|---|---|
| parses a full sample | header block, legend and column header are skipped; the three sample rows yield the expected records |
| stack member derivation | `Fi2/0/32` → `"2"`; `Vl2003` → `""` |
| MAC lower-cased | an upper-case MAC in the input comes back lower-case |
| local codes preserved | `L`/`S` rows are returned by the parser, not dropped at this layer |
| IPv6 counted, not returned | an `ND` row with an IPv6 address is excluded from entries and counted |
| opaque VLAN token | a non-numeric VLAN token still parses |
| `command_unsupported` | true for `% Invalid input detected`, false for real output |
| empty / garbage input | returns `([], 0)` rather than raising |

### `test_ip_mac_report.py` (new)

| Test | Asserts |
|---|---|
| filters to requested VLANs | rows in other VLANs are absent |
| drops L/S and counts them | `excluded_local` matches, and no `L` row reaches `rows` |
| duplicate IP flagged | one IP on two MACs gets `Duplicate IP — held by 2 MACs` |
| SVI cannot false-flag | an `L` row sharing an IP with an endpoint produces no flag |
| MAC on two switches flagged | `Seen on multiple switches` |
| both flags on one row | semicolon-joined |
| unsupported switch recorded | lands in `unsupported`, not `no_bindings` |
| endpoint-less switch recorded | supported but nothing in-VLAN lands in `no_bindings` |
| `vlan_switches` mapping | lists only switches that yielded a surviving endpoint |
| IP ordering | `.9` sorts before `.10` |

### `test_ip_mac_export_wiring.py` (new)

`DEVICE_TRACKING_COMMANDS` value; `action_ip_mac_export` exists with the
`(selected_devices, client, concurrency)` signature and `DEFAULT_CONCURRENCY`
default; Menu 5 source contains the `d)` label and the updated prompt; the
extracted helpers exist and `action_av_mac_export` still has its documented
signature.

Plus an Excel round-trip test in the existing `test_excel_generator.py` style:
write a report to a `tmp_path` workbook, reopen it, and assert the summary lines,
headers and one flagged row.

---

## Out of scope

- **IPv6 bindings** — counted, not reported. A future change if wanted.
- **On-device VLAN filtering** (`show device-tracking database vlanid N`) —
  rejected during design because it multiplies commands per device.
- **Uplink suppression** — device-tracking is a per-switch binding table;
  duplicates are flagged rather than dropped, so no CDP collection is needed and
  no real endpoint can be lost to a wrong uplink guess.
- `main_cli.py` / `main_debug.py` — no menu, unchanged.

---

## Assumptions to verify on first real run

1. **The `vlan` column is the numeric VLAN ID.** The sample provided during
   design had that column redacted. The filter matches the requested IDs against
   that token; the parser captures it loosely so a mismatch reports as
   "no bindings" rather than failing obscurely.
2. **DNAC Command Runner permits `show device-tracking database`.** Its keyword
   whitelist could reject it, which surfaces as a per-device failure from
   `run_commands` with no file written. Worth a single-switch smoke test.
