# AV MAC/Port Export (for AV) — Design

## Context

The business is replacing all switches with Cisco SDA. Some AV equipment can't be
onboarded to the fabric and must remain statically assigned via MAC Authentication
Bypass (MAB). To configure that, the vendor needs an accurate list of every MAC
address on the AV VLAN(s), mapped to the exact physical switch port it's plugged
into, across a nominated group of switches (typically an access/distribution
hierarchy such as a 3560 access switch below a 3850 below a 4500).

Because the port mapping is used to statically provision MAB, port accuracy is
safety-critical — the report must not silently guess when data is ambiguous.

Two problems complicate a naive `show mac address-table | include VlanXXX`:

1. **Hierarchy duplication.** The same MAC is learned by every switch in the
   uplink path — the 3560 sees it on the real access port, the 3850 sees it via
   its uplink to the 3560, the 4500 sees it via its uplink to the 3850. A naive
   dump lists the same MAC three times, on three different "ports," none of
   which is obviously wrong to someone unfamiliar with the topology.
2. **Hidden non-DNAC switches.** Some AV devices sit behind small unmanaged or
   non-Cisco switches that were never onboarded to DNAC and may not run CDP.
   From the DNAC-managed access switch's point of view, the port to that hidden
   switch looks like an ordinary single port — but the VLAN's MAC table on it
   can show *multiple* MACs (everything hanging off the hidden switch).

## Goal

A new Menu 5 report, run against the already-selected group of switches, that:

- Accepts one or more AV VLAN IDs.
- Pulls `show mac address-table` and `show cdp neighbors detail` from each
  selected switch.
- Filters to the requested VLAN(s), and removes hierarchy-duplicate entries
  using CDP (problem 1).
- Flags — never silently resolves — anything ambiguous: ports with more than
  one MAC (problem 2), and MACs that survive on more than one switch/port.
- Exports a single Excel sheet: a VLAN→stacks summary, then the full detail
  table, ready to hand to the vendor.

## Non-goals (this iteration)

- The AV-specific draw.io diagram (purple diamonds for MAC endpoints) is
  explicitly deferred to a follow-up spec once this report has been validated
  against real data.
- No attempt to auto-resolve ambiguous MACs or multi-MAC ports — those are
  surfaced for manual review, not decided by the tool.

## Data collection

Reuses the existing command-execution path (`run_commands` in `cheat_core.py`),
so slow-mode and concurrency toggles already present in Menu 5 apply unchanged.

Commands run per selected switch:

- `show mac address-table` — the **full** table, not pre-filtered by VLAN.
  Filtering happens in Python so the tool only issues one command per switch
  regardless of how many VLAN IDs are requested.
- `show cdp neighbors detail` — already part of the standard report's command
  set (`DNAC_COMMANDS`); here it's used purely to identify uplink interfaces,
  not for its own output.

User input: VLAN ID(s), comma or space separated (e.g. `900 905`).

## Parsing

New module `mac_table.py`, structured like `unscanned_switches.py`:

```python
@dataclass
class MacTableEntry:
    switch: str
    mac: str
    vlan: str
    type: str            # STATIC / DYNAMIC
    interface: str        # normalised short form, e.g. Gi1/0/24
    stack_member: str = ""  # derived from the interface, same convention as interface_parser.py
```

`parse_mac_address_table(text: str) -> list[MacTableEntry]` parses `show mac
address-table` output. Skips header/separator lines, and rows where VLAN is
`All` or the port is `CPU` (control-plane / system MACs, not end devices).

## Correlation & filtering

New function, e.g. `build_av_mac_report(raw_outputs: dict[str, str], vlans: list[str]) -> AvMacReport`,
operating per switch:

1. Parse `show mac address-table` → entries; keep only requested VLAN(s).
2. Parse `show cdp neighbors detail` (existing `cdp_detail.py` /
   `parse_cdp_detail`) → build the set of local interfaces on this switch whose
   CDP neighbour satisfies `is_switch()` (Router/Switch capability). These are
   uplinks to other switches in the selected hierarchy, not AV device ports.
3. Drop MAC-table entries whose interface is in that uplink set.

After per-switch filtering, two flags applied across all surviving entries:

- **Multiple MACs on one port** (same switch + interface, >1 distinct MAC):
  flag `"Multiple MACs — possible unmanaged switch"`. All MACs are kept in the
  output.
- **Ambiguous MAC** (same MAC surviving the uplink filter on more than one
  switch/interface combination): flag `"Ambiguous — seen on multiple
  switches"`. All sightings are kept; the tool never picks one for you.

A row can carry both flags if applicable.

## Excel output

New function `write_av_mac_report_excel(...)` (in `excel_generator.py`,
alongside the other report writers), single sheet:

1. **Summary block** (top): for each requested VLAN, the list of switches/
   stacks on which it was found — same visual pattern as the existing
   "Discovered Devices" block (bold title, header row, data rows).
2. **Detail table** (below): columns `Switch | Stack Member | Interface |
   VLAN | MAC Address | Type | Notes`. Sorted by Switch → Interface → MAC.
   Rows carrying a flag are colour-highlighted (reusing the existing
   suspect/uptime highlight styling conventions already in
   `excel_generator.py`), with the flag text(s) in the Notes column.

## Menu integration

New Menu 5 item, letter `m`:

```
m) MAC/port export (for AV)
```

Flow: uses the already-selected switch group (no re-selection). Prompts for
VLAN ID(s). Runs the two commands. Parses, correlates, filters. Prompts for a
filename. Writes the Excel report to `EXCEL_DIR`, same as the other export
options.

## Testing

TDD, new/updated test files:

- `test_mac_table.py` — `show mac address-table` parsing, including a stacked
  switch (member-prefixed interfaces) and CPU/`All`-VLAN row exclusion.
- Correlation tests (likely `test_av_mac_report.py`) covering:
  - Hierarchy dedupe: same MAC across 3 switches collapses to the one true
    access-layer entry.
  - Multi-MAC port flagging (hidden unmanaged switch scenario).
  - Ambiguous MAC flagging (same MAC survives on two different switches).
  - VLAN filtering with multiple requested VLAN IDs.
- Excel output test verifying the summary block and detail table are both
  written correctly, including flagged-row highlighting.
