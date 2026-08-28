# AV MAC/Port Export (for AV) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Menu 5 report that maps AV-VLAN MAC addresses to physical switch ports across a nominated switch hierarchy, for MAB provisioning during the SDA cutover.

**Architecture:** Two new pure-parsing/correlation modules (`mac_table.py`, `av_mac_report.py`) mirroring the existing `cdp_detail.py`/`unscanned_switches.py` split — one module parses a single command's raw output, the other correlates that with CDP data across all selected switches and applies the two safety flags. A new writer function in `excel_generator.py` renders the result. `main.py` wires it into Menu 5 as a new interactive action, following the existing `action_mac_search`/`action_ip_search` pattern.

**Tech Stack:** Python 3, openpyxl, pytest. No new dependencies.

## Global Constraints

- Never silently resolve ambiguity: flag, don't guess, for both multi-MAC ports and MACs seen on more than one switch. (Spec: "Correlation & filtering")
- One `show mac address-table` command per switch regardless of how many VLAN IDs are requested — filtering happens in Python. (Spec: "Data collection")
- Uplink detection reuses the existing `is_switch()` capability check from `cdp_detail.py` — do not invent a new heuristic. (Spec: "Correlation & filtering")
- The AV-specific draw.io diagram is explicitly out of scope for this plan. (Spec: "Non-goals")
- MAC addresses are lowercased at parse time so cross-switch dedupe/ambiguity comparisons aren't broken by casing differences between platforms.

---

## File Structure

- `mac_table.py` (new) — `MacTableEntry` dataclass + `parse_mac_address_table(text)`. Parses one switch's `show mac address-table` output. No knowledge of switch hostnames, VLAN filtering, or CDP.
- `test_mac_table.py` (new) — parser tests.
- `av_mac_report.py` (new) — `AvMacRow`, `AvMacReport` dataclasses + `build_av_mac_report(raw_outputs, vlans)`. Orchestrates: parse each switch's MAC table and CDP neighbours, filter to requested VLANs, drop uplink-port duplicates, flag multi-MAC ports and cross-switch ambiguous MACs.
- `test_av_mac_report.py` (new) — correlation/dedupe/flagging tests, plus the Excel-writer tests (mirrors how `test_unscanned_switches.py` covers both `unscanned_switches.py` and its `excel_generator.py` writer together).
- `excel_generator.py` (modify) — add `AV_MAC_HEADERS`, `AV_MAC_COL_WIDTHS`, `AV_MAC_FLAG_COLOUR`, `AV_MAC_SUMMARY_TITLE` constants, `write_av_mac_report_sheet(ws, report)`, `write_av_mac_report_excel(report, outpath)`.
- `cheat_core.py` (modify) — add `AV_MAC_COMMANDS` constant next to `DNAC_COMMANDS`.
- `main.py` (modify) — add `action_av_mac_export(selected_devices, client, concurrency)`, wire it into `menu_5` as choice `m`.
- `test_av_mac_export_wiring.py` (new) — thin signature/wiring checks, matching the existing `test_main_concurrency.py` style (this codebase doesn't unit-test interactive `input()`-driven action functions like `action_mac_search`; wiring is checked at the signature/constant level instead).

---

### Task 1: `mac_table.py` — parse `show mac address-table`

**Files:**
- Create: `mac_table.py`
- Test: `test_mac_table.py`

**Interfaces:**
- Consumes: `shorten_iface`, `member_from_iface` from `interface_parser.py` (already exist).
- Produces: `MacTableEntry(switch: str, vlan: str, mac: str, type: str, interface: str, stack_member: str = "")` and `parse_mac_address_table(text: str) -> list[MacTableEntry]`. `switch` is left `""` by the parser — the caller (Task 2) fills it in per host, matching how `parse_cdp_switch_neighbors` in `unscanned_switches.py` leaves `seen_on` blank for its caller to set.

- [ ] **Step 1: Write the failing tests**

```python
# test_mac_table.py
MAC_TABLE_OUTPUT = "\n".join([
    "show mac address-table",
    "          Mac Address Table",
    "-------------------------------------------",
    "",
    "Vlan    Mac Address       Type        Ports",
    "----    -----------       --------    -----",
    " All    0100.0ccc.cccc    STATIC      CPU",
    " All    0100.0ccc.cccd    STATIC      CPU",
    " 900    0011.2233.4455    DYNAMIC     Gi1/0/24",
    " 900    aabb.ccdd.eeff    DYNAMIC     Gi2/0/12",
    "Total Mac Addresses for this criterion: 4",
])


def test_parse_mac_address_table_extracts_vlan_rows():
    from mac_table import parse_mac_address_table
    entries = parse_mac_address_table(MAC_TABLE_OUTPUT)
    assert [(e.vlan, e.mac, e.type, e.interface) for e in entries] == [
        ("900", "0011.2233.4455", "DYNAMIC", "Gi1/0/24"),
        ("900", "aabb.ccdd.eeff", "DYNAMIC", "Gi2/0/12"),
    ]


def test_parse_mac_address_table_derives_stack_member():
    from mac_table import parse_mac_address_table
    entries = parse_mac_address_table(MAC_TABLE_OUTPUT)
    assert entries[0].stack_member == "1"
    assert entries[1].stack_member == "2"


def test_parse_mac_address_table_skips_all_vlan_and_cpu_rows():
    from mac_table import parse_mac_address_table
    entries = parse_mac_address_table(MAC_TABLE_OUTPUT)
    assert all(e.vlan != "All" for e in entries)
    assert all(e.interface != "CPU" for e in entries)


def test_parse_mac_address_table_lowercases_mac():
    from mac_table import parse_mac_address_table
    text = "\n".join([
        "Vlan    Mac Address       Type        Ports",
        "----    -----------       --------    -----",
        " 10     AABB.CCDD.EEFF    STATIC      Gi1/0/1",
    ])
    entries = parse_mac_address_table(text)
    assert entries[0].mac == "aabb.ccdd.eeff"


def test_parse_mac_address_table_empty_text_returns_empty_list():
    from mac_table import parse_mac_address_table
    assert parse_mac_address_table("") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test_mac_table.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mac_table'`

- [ ] **Step 3: Write the implementation**

```python
# mac_table.py
"""
Parse `show mac address-table` output into per-switch MAC/port entries.

Pure parsing — no CDP, no VLAN filtering, no switch-hostname knowledge. Those
belong to the caller (av_mac_report.py), same split as cdp_detail.py vs
unscanned_switches.py.
"""

import re
from dataclasses import dataclass

from interface_parser import shorten_iface, member_from_iface

_RE_ROW = re.compile(
    r"(?im)^\s*(?P<vlan>\d+|All)\s+"
    r"(?P<mac>[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})\s+"
    r"(?P<type>static|dynamic)\s+"
    r"(?P<iface>\S+)\s*$"
)


@dataclass
class MacTableEntry:
    switch: str
    vlan: str
    mac: str
    type: str
    interface: str
    stack_member: str = ""


def parse_mac_address_table(text: str) -> list[MacTableEntry]:
    """Parse `show mac address-table` output into MacTableEntry rows.

    Skips 'All'-VLAN and CPU rows (control-plane/system MACs, not end
    devices). MAC addresses are lowercased so cross-switch comparisons in
    av_mac_report.py aren't broken by platform casing differences.
    """
    out: list[MacTableEntry] = []
    for m in _RE_ROW.finditer(text):
        vlan = m.group("vlan")
        raw_iface = m.group("iface")
        if vlan.lower() == "all" or raw_iface.upper() == "CPU":
            continue
        iface = shorten_iface(raw_iface)
        out.append(MacTableEntry(
            switch="",
            vlan=vlan,
            mac=m.group("mac").lower(),
            type=m.group("type").upper(),
            interface=iface,
            stack_member=member_from_iface(iface),
        ))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test_mac_table.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add mac_table.py test_mac_table.py
git commit -m "feat: add show mac address-table parser"
```

---

### Task 2: `av_mac_report.py` — correlate MAC tables + CDP into a flagged report

**Files:**
- Create: `av_mac_report.py`
- Test: `test_av_mac_report.py`

**Interfaces:**
- Consumes: `parse_mac_address_table`, `MacTableEntry` from `mac_table.py` (Task 1); `parse_cdp_detail`, `is_switch` from `cdp_detail.py` (existing).
- Produces: `AvMacRow(switch, stack_member, interface, vlan, mac, type, notes="")`, `AvMacReport(vlan_stacks: dict[str, list[str]], rows: list[AvMacRow])`, `build_av_mac_report(raw_outputs: dict[str, str], vlans: list[str]) -> AvMacReport`. `raw_outputs` maps hostname to the combined raw text of `show mac address-table` + `show cdp neighbors detail` for that host (i.e. exactly what `run_commands()` returns). `vlans` is a list of VLAN-ID strings.

- [ ] **Step 1: Write the failing tests**

```python
# test_av_mac_report.py
HIERARCHY_OUTPUTS = {
    "acc1": "\n".join([
        "show mac address-table",
        "Vlan    Mac Address       Type        Ports",
        "----    -----------       --------    -----",
        " 900    0011.2233.4455    DYNAMIC     Gi1/0/24",
        "Total Mac Addresses for this criterion: 1",
        "",
        "show cdp neighbors detail",
        "-------------------------",
        "Device ID: dist1",
        "Entry address(es):",
        "  IP address: 10.0.0.2",
        "Platform: cisco WS-C3850-48P,  Capabilities: Router Switch IGMP",
        "Interface: GigabitEthernet1/0/1,  Port ID (outgoing port): GigabitEthernet1/0/1",
        "Total cdp entries displayed : 1",
    ]),
    "dist1": "\n".join([
        "show mac address-table",
        "Vlan    Mac Address       Type        Ports",
        "----    -----------       --------    -----",
        " 900    0011.2233.4455    DYNAMIC     Gi1/0/1",
        "Total Mac Addresses for this criterion: 1",
        "",
        "show cdp neighbors detail",
        "-------------------------",
        "Device ID: acc1",
        "Entry address(es):",
        "  IP address: 10.0.0.1",
        "Platform: cisco WS-C3560X-24,  Capabilities: Router Switch IGMP",
        "Interface: GigabitEthernet1/0/1,  Port ID (outgoing port): GigabitEthernet1/0/24",
        "-------------------------",
        "Device ID: core1",
        "Entry address(es):",
        "  IP address: 10.0.0.3",
        "Platform: cisco WS-C4500X-32,  Capabilities: Router Switch IGMP",
        "Interface: GigabitEthernet1/0/2,  Port ID (outgoing port): GigabitEthernet1/1/1",
        "Total cdp entries displayed : 2",
    ]),
    "core1": "\n".join([
        "show mac address-table",
        "Vlan    Mac Address       Type        Ports",
        "----    -----------       --------    -----",
        " 900    0011.2233.4455    DYNAMIC     Gi1/1/1",
        "Total Mac Addresses for this criterion: 1",
        "",
        "show cdp neighbors detail",
        "-------------------------",
        "Device ID: dist1",
        "Entry address(es):",
        "  IP address: 10.0.0.2",
        "Platform: cisco WS-C3850-48P,  Capabilities: Router Switch IGMP",
        "Interface: GigabitEthernet1/1/1,  Port ID (outgoing port): GigabitEthernet1/0/2",
        "Total cdp entries displayed : 1",
    ]),
}


def test_build_av_mac_report_collapses_hierarchy_duplicates():
    from av_mac_report import build_av_mac_report
    report = build_av_mac_report(HIERARCHY_OUTPUTS, ["900"])
    assert len(report.rows) == 1
    row = report.rows[0]
    assert row.switch == "acc1"
    assert row.interface == "Gi1/0/24"
    assert row.mac == "0011.2233.4455"
    assert row.notes == ""


MULTI_MAC_OUTPUTS = {
    "acc1": "\n".join([
        "show mac address-table",
        "Vlan    Mac Address       Type        Ports",
        "----    -----------       --------    -----",
        " 900    aaaa.aaaa.aaaa    DYNAMIC     Gi1/0/5",
        " 900    bbbb.bbbb.bbbb    DYNAMIC     Gi1/0/5",
        "Total Mac Addresses for this criterion: 2",
        "",
        "show cdp neighbors detail",
        "-------------------------",
        "Total cdp entries displayed : 0",
    ]),
}


def test_build_av_mac_report_flags_multiple_macs_on_one_port():
    from av_mac_report import build_av_mac_report
    report = build_av_mac_report(MULTI_MAC_OUTPUTS, ["900"])
    assert len(report.rows) == 2
    assert all("Multiple MACs" in r.notes for r in report.rows)


AMBIGUOUS_OUTPUTS = {
    "acc1": "\n".join([
        "show mac address-table",
        "Vlan    Mac Address       Type        Ports",
        "----    -----------       --------    -----",
        " 900    cccc.cccc.cccc    DYNAMIC     Gi1/0/8",
        "Total Mac Addresses for this criterion: 1",
        "",
        "show cdp neighbors detail",
        "-------------------------",
        "Total cdp entries displayed : 0",
    ]),
    "acc2": "\n".join([
        "show mac address-table",
        "Vlan    Mac Address       Type        Ports",
        "----    -----------       --------    -----",
        " 900    cccc.cccc.cccc    DYNAMIC     Gi1/0/9",
        "Total Mac Addresses for this criterion: 1",
        "",
        "show cdp neighbors detail",
        "-------------------------",
        "Total cdp entries displayed : 0",
    ]),
}


def test_build_av_mac_report_flags_ambiguous_mac_across_switches():
    from av_mac_report import build_av_mac_report
    report = build_av_mac_report(AMBIGUOUS_OUTPUTS, ["900"])
    assert len(report.rows) == 2
    assert all("Ambiguous" in r.notes for r in report.rows)


def test_build_av_mac_report_filters_requested_vlans_and_builds_summary():
    from av_mac_report import build_av_mac_report
    outputs = {
        "acc1": "\n".join([
            "show mac address-table",
            "Vlan    Mac Address       Type        Ports",
            "----    -----------       --------    -----",
            " 900    1111.1111.1111    DYNAMIC     Gi1/0/1",
            " 905    2222.2222.2222    DYNAMIC     Gi1/0/2",
            " 10     3333.3333.3333    DYNAMIC     Gi1/0/3",
            "Total Mac Addresses for this criterion: 3",
            "",
            "show cdp neighbors detail",
            "-------------------------",
            "Total cdp entries displayed : 0",
        ]),
    }
    report = build_av_mac_report(outputs, ["900", "905"])
    assert sorted(r.vlan for r in report.rows) == ["900", "905"]
    assert report.vlan_stacks == {"900": ["acc1"], "905": ["acc1"]}


def test_build_av_mac_report_no_matching_vlan_returns_no_rows():
    from av_mac_report import build_av_mac_report
    report = build_av_mac_report(MULTI_MAC_OUTPUTS, ["999"])
    assert report.rows == []
    assert report.vlan_stacks == {"999": []}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test_av_mac_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'av_mac_report'`

- [ ] **Step 3: Write the implementation**

```python
# av_mac_report.py
"""
Correlate `show mac address-table` + `show cdp neighbors detail` output
across a nominated group of switches into a flagged AV MAC/port report.

Collapses hierarchy duplication (the same MAC learned by every switch
between the AV device and the top of the selected stack) using CDP: any
local interface whose CDP neighbour is itself a switch/router is an uplink,
not an AV device's port, and its MAC-table entries are dropped.

Never silently resolves ambiguity — a port with more than one surviving MAC,
or a MAC surviving on more than one switch/interface, is flagged in the
output rather than collapsed further.
"""

from dataclasses import dataclass, replace

from mac_table import parse_mac_address_table, MacTableEntry
from cdp_detail import parse_cdp_detail, is_switch

MULTI_MAC_NOTE = "Multiple MACs — possible unmanaged switch"
AMBIGUOUS_NOTE = "Ambiguous — seen on multiple switches"


@dataclass
class AvMacRow:
    switch: str
    stack_member: str
    interface: str
    vlan: str
    mac: str
    type: str
    notes: str = ""


@dataclass
class AvMacReport:
    vlan_stacks: dict
    rows: list


def _uplink_interfaces(text: str) -> set:
    """Local interfaces on this switch whose CDP neighbour is a switch/router."""
    return {nb.local_iface for nb in parse_cdp_detail(text) if is_switch(nb)}


def build_av_mac_report(raw_outputs: dict, vlans: list) -> AvMacReport:
    """Correlate per-switch MAC-table + CDP output into a flagged AV MAC/port report.

    raw_outputs maps hostname -> combined raw output containing both
    `show mac address-table` and `show cdp neighbors detail`. vlans is a
    list of requested VLAN-ID strings.
    """
    wanted = {str(v).strip() for v in vlans}
    vlan_stacks = {v: set() for v in wanted}
    surviving: list[MacTableEntry] = []

    for host, text in raw_outputs.items():
        entries = [e for e in parse_mac_address_table(text) if e.vlan in wanted]
        if not entries:
            continue
        uplinks = _uplink_interfaces(text)
        for e in entries:
            vlan_stacks[e.vlan].add(host)
            if e.interface in uplinks:
                continue
            surviving.append(replace(e, switch=host))

    port_macs: dict = {}
    for e in surviving:
        port_macs.setdefault((e.switch, e.interface), set()).add(e.mac)

    mac_ports: dict = {}
    for e in surviving:
        mac_ports.setdefault(e.mac, set()).add((e.switch, e.interface))

    rows = []
    for e in surviving:
        notes = []
        if len(port_macs[(e.switch, e.interface)]) > 1:
            notes.append(MULTI_MAC_NOTE)
        if len(mac_ports[e.mac]) > 1:
            notes.append(AMBIGUOUS_NOTE)
        rows.append(AvMacRow(
            switch=e.switch,
            stack_member=e.stack_member,
            interface=e.interface,
            vlan=e.vlan,
            mac=e.mac,
            type=e.type,
            notes="; ".join(notes),
        ))

    rows.sort(key=lambda r: (r.switch, r.interface, r.mac))
    return AvMacReport(
        vlan_stacks={v: sorted(hosts) for v, hosts in vlan_stacks.items()},
        rows=rows,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test_av_mac_report.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add av_mac_report.py test_av_mac_report.py
git commit -m "feat: correlate AV VLAN MAC tables into a flagged port report"
```

---

### Task 3: Excel writer — `write_av_mac_report_excel`

**Files:**
- Modify: `excel_generator.py`
- Test: `test_av_mac_report.py` (append)

**Interfaces:**
- Consumes: an `AvMacReport`-shaped object (`.vlan_stacks: dict[str, list[str]]`, `.rows: list[AvMacRow]` where each row has `.switch .stack_member .interface .vlan .mac .type .notes`) — duck-typed, `excel_generator.py` does not import `av_mac_report.py` (same decoupling as the existing `write_unscanned_switches_block`, which doesn't import a report-builder either).
- Produces: `write_av_mac_report_sheet(ws, report) -> int` (returns next free row, unused by callers today but kept for symmetry with `_write_neighbour_table`), `write_av_mac_report_excel(report, outpath: str) -> tuple[bool, str]`.

- [ ] **Step 1: Write the failing tests**

```python
# append to test_av_mac_report.py

def test_write_av_mac_report_excel_writes_summary_and_detail(tmp_path):
    import openpyxl
    from av_mac_report import AvMacReport, AvMacRow
    from excel_generator import write_av_mac_report_excel

    report = AvMacReport(
        vlan_stacks={"900": ["acc1"]},
        rows=[
            AvMacRow(switch="acc1", stack_member="1", interface="Gi1/0/24",
                     vlan="900", mac="0011.2233.4455", type="DYNAMIC", notes=""),
            AvMacRow(switch="acc1", stack_member="1", interface="Gi1/0/5",
                     vlan="900", mac="aaaa.aaaa.aaaa", type="DYNAMIC",
                     notes="Multiple MACs — possible unmanaged switch"),
        ],
    )
    out = tmp_path / "av.xlsx"
    ok, msg = write_av_mac_report_excel(report, str(out))
    assert ok

    ws = openpyxl.load_workbook(out)["AV MAC-Port Export"]
    assert ws.cell(row=1, column=1).value == "AV VLANs Found On These Switches"
    assert ws.cell(row=2, column=1).value == "VLAN 900: acc1"

    header_row = next(r for r in range(1, ws.max_row + 1)
                       if ws.cell(row=r, column=1).value == "Switch")
    assert [ws.cell(row=header_row, column=c).value for c in range(1, 8)] == [
        "Switch", "Stack Member", "Interface", "VLAN", "MAC Address", "Type", "Notes"
    ]
    assert ws.cell(row=header_row + 1, column=5).value == "0011.2233.4455"
    assert ws.cell(row=header_row + 2, column=7).value == "Multiple MACs — possible unmanaged switch"


def test_write_av_mac_report_excel_fails_on_empty_rows(tmp_path):
    from av_mac_report import AvMacReport
    from excel_generator import write_av_mac_report_excel
    report = AvMacReport(vlan_stacks={}, rows=[])
    ok, msg = write_av_mac_report_excel(report, str(tmp_path / "av.xlsx"))
    assert ok is False
    assert "No matching" in msg
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test_av_mac_report.py -v -k write_av_mac_report_excel`
Expected: FAIL with `ImportError: cannot import name 'write_av_mac_report_excel' from 'excel_generator'`

- [ ] **Step 3: Write the implementation**

Add near the bottom of `excel_generator.py`, after `write_client_search_excel` (the file already imports `openpyxl`, `Font`, `PatternFill`, `Alignment`, `Border`, `Side`, `get_column_letter` at the top — no new imports needed):

```python
# ============================================================================
# AV MAC/Port Export
# ============================================================================

AV_MAC_SUMMARY_TITLE = "AV VLANs Found On These Switches"
AV_MAC_HEADERS = ["Switch", "Stack Member", "Interface", "VLAN", "MAC Address", "Type", "Notes"]
AV_MAC_COL_WIDTHS = [28, 13, 14, 8, 20, 10, 40]
AV_MAC_FLAG_COLOUR = "FFFFD700"


def write_av_mac_report_sheet(ws, report) -> int:
    """Write the VLAN summary block then the MAC/port detail table.

    Returns the next free row below the detail table.
    """
    title = ws.cell(row=1, column=1, value=AV_MAC_SUMMARY_TITLE)
    title.font = Font(bold=True, name="Arial", size=10)

    row = 2
    for vlan in sorted(report.vlan_stacks, key=int):
        switches = report.vlan_stacks[vlan]
        found = ", ".join(switches) if switches else "not found on any selected switch"
        ws.cell(row=row, column=1, value=f"VLAN {vlan}: {found}")
        row += 1

    row += 1  # blank row before the detail table
    header_font, header_fill, header_align, header_border = get_header_styles()
    data_font, data_align, data_border = get_data_styles()

    hdr_row = row
    for col, (header, width) in enumerate(zip(AV_MAC_HEADERS, AV_MAC_COL_WIDTHS), start=1):
        c = ws.cell(row=hdr_row, column=col, value=header)
        c.font = header_font
        c.fill = header_fill
        c.alignment = header_align
        c.border = header_border
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = f"A{hdr_row + 1}"

    for i, r in enumerate(report.rows):
        data_row = hdr_row + 1 + i
        values = [r.switch, r.stack_member, r.interface, r.vlan, r.mac, r.type, r.notes]
        flagged = bool(r.notes)
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=data_row, column=col, value=value)
            cell.font = Font(name="Arial", size=10, bold=True) if flagged else data_font
            cell.alignment = data_align
            cell.border = data_border
            if flagged:
                cell.fill = PatternFill("solid", start_color=AV_MAC_FLAG_COLOUR)

    end_row = hdr_row + len(report.rows)
    ws.auto_filter.ref = f"A{hdr_row}:G{end_row}"
    return end_row + 1


def write_av_mac_report_excel(report, outpath: str) -> tuple[bool, str]:
    """Write the AV MAC/port report to a single-sheet Excel workbook."""
    if not report.rows:
        return False, "No matching MAC addresses found for the requested VLAN(s)"

    try:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "AV MAC-Port Export"
        write_av_mac_report_sheet(ws, report)
        wb.save(outpath)
        return True, f"✓ Saved: {outpath} ({len(report.rows)} MAC/port mapping(s))"
    except Exception as e:
        return False, f"✗ Failed to write Excel: {e}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test_av_mac_report.py -v`
Expected: PASS (8 tests total in the file)

- [ ] **Step 5: Commit**

```bash
git add excel_generator.py test_av_mac_report.py
git commit -m "feat: write AV MAC/port report to Excel"
```

---

### Task 4: Menu wiring — `m) MAC/port export (for AV)`

**Files:**
- Modify: `cheat_core.py` (add `AV_MAC_COMMANDS` near `DNAC_COMMANDS`, `cheat_core.py:40-48`)
- Modify: `main.py` (imports at `main.py:7-29`, new action function before `menu_5` at `main.py:1262`, menu print/dispatch inside `menu_5` at `main.py:1262-1376`)
- Test: `test_av_mac_export_wiring.py`

**Interfaces:**
- Consumes: `run_commands` (existing, `cheat_core.py`), `build_av_mac_report` (Task 2), `write_av_mac_report_excel` (Task 3), `_prompt_filename`, `pause`, `EXCEL_DIR`, `DEFAULT_CONCURRENCY` (all already available in `main.py`).
- Produces: `cheat_core.AV_MAC_COMMANDS: list[str]`, `main.action_av_mac_export(selected_devices, client, concurrency=DEFAULT_CONCURRENCY) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
# test_av_mac_export_wiring.py
import inspect


def test_av_mac_commands_defined():
    import cheat_core
    assert cheat_core.AV_MAC_COMMANDS == ["show mac address-table", "show cdp neighbors detail"]


def test_action_av_mac_export_exists_with_expected_signature():
    import main
    assert callable(main.action_av_mac_export)
    sig = inspect.signature(main.action_av_mac_export)
    assert list(sig.parameters) == ["selected_devices", "client", "concurrency"]
    assert sig.parameters["concurrency"].default == main.DEFAULT_CONCURRENCY
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test_av_mac_export_wiring.py -v`
Expected: FAIL — `AttributeError: module 'cheat_core' has no attribute 'AV_MAC_COMMANDS'`

- [ ] **Step 3: Add `AV_MAC_COMMANDS` to `cheat_core.py`**

In `cheat_core.py`, right after the existing `DNAC_COMMANDS`/`LINK_STATE_COMMANDS` block (`cheat_core.py:40-48`):

```python
DNAC_COMMANDS = [
    "show hardware",
    "show interfaces",
    "show interfaces status",
    "show interface counters",
    "show cdp neighbors detail",
]

LINK_STATE_COMMANDS = ["show logging", "show clock"]

AV_MAC_COMMANDS = ["show mac address-table", "show cdp neighbors detail"]
```

- [ ] **Step 4: Wire up `main.py`**

Update the import block (`main.py:7-26`):

```python
import getpass
import json
import os
import re
import sys
from pathlib import Path

from dnac_client import DNACClient
from cheat_core import (
    EXCEL_DIR,
    COMMAND_RUNNER_DIR,
    build_command_list,
    run_commands,
    parse_outputs,
    generate_excel,
    generate_cdp_topology,
    next_concurrency,
    DEFAULT_CONCURRENCY,
    AV_MAC_COMMANDS,
)
from excel_generator import write_client_search_excel, write_av_mac_report_excel
from av_mac_report import build_av_mac_report
from port_utilisation import is_copper_port
from drawio_generator import generate_drawio
import ap_monitor
import splash
```

Add the new action function immediately before `def menu_5(...)` (`main.py:1262`):

```python
def action_av_mac_export(selected_devices, client, concurrency=DEFAULT_CONCURRENCY):
    """Menu 5 'm': AV VLAN MAC-address/port export for MAB handoff.

    Runs `show mac address-table` + `show cdp neighbors detail` on the
    already-selected switch group, then correlates them into a flagged
    MAC-to-physical-port report (see av_mac_report.build_av_mac_report).
    """
    print()
    print("  AV MAC/port export — VLAN ID(s), comma or space separated (e.g. 900 905)")
    raw_vlans = input("  VLAN ID(s): ").strip()
    if not raw_vlans:
        print("  Cancelled.")
        pause()
        return
    vlans = [v for v in re.split(r"[,\s]+", raw_vlans) if v]
    if not all(v.isdigit() for v in vlans):
        print("  ✗ VLAN IDs must be numeric.")
        pause()
        return

    outputs = run_commands(selected_devices, client, AV_MAC_COMMANDS, concurrency=concurrency)
    if not outputs:
        pause()
        return

    report = build_av_mac_report(outputs, vlans)
    if not report.rows:
        print("\n  No matching MAC addresses found for the requested VLAN(s).")
        pause()
        return

    flagged = sum(1 for r in report.rows if r.notes)
    print(f"\n  Found {len(report.rows)} MAC/port mapping(s) ({flagged} flagged for review)")

    filename = _prompt_filename()
    if not filename:
        print("  Cancelled.")
        pause()
        return

    from datetime import datetime
    excel_dir = Path(EXCEL_DIR).resolve()
    excel_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d-%H-%M")
    stem = Path(filename).stem
    outpath = str(excel_dir / f"{stem}-{ts}.xlsx")
    ok, msg = write_av_mac_report_excel(report, outpath)
    print(f"\n  {msg}")
    pause()
```

In `menu_5`, add the menu line right after the IP-search line (`main.py:1282`, `print("  7) IP address search  (Assurance /clients, wildcard)")`):

```python
        print("  7) IP address search  (Assurance /clients, wildcard)")
        print("  m) MAC/port export (for AV)")
        print("  s) Toggle slow mode")
```

Update the input prompt (`main.py:1291`):

```python
        choice = input("  Select [1-9 / m / r / s / p / l / c]: ").strip().lower()
```

Add the dispatch branch right after the existing `choice == "7"` branch (`main.py:1371-1372`):

```python
        elif choice == "7":
            action_ip_search(client)

        elif choice == "m":
            action_av_mac_export(selected_devices, client, concurrency)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest test_av_mac_export_wiring.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Run the full test suite to check for regressions**

Run: `python3 -m pytest -q`
Expected: same pass/fail counts as the pre-existing baseline (the repo has a handful of network-dependent sandbox/DNAC tests that already fail/error without live credentials — confirm no *new* failures beyond that baseline).

- [ ] **Step 7: Commit**

```bash
git add cheat_core.py main.py test_av_mac_export_wiring.py
git commit -m "feat: wire AV MAC/port export into Menu 5 (m)"
```

---

## Self-Review Notes

- **Spec coverage:** Data collection (Task 4, `AV_MAC_COMMANDS` + single mac-table command regardless of VLAN count) · Parsing (Task 1) · Correlation & filtering incl. both flags (Task 2) · Excel output incl. summary + detail + highlighting (Task 3) · Menu integration (Task 4) · Testing (all tasks, TDD) — all spec sections have a task.
- **Type consistency:** `MacTableEntry` (Task 1) → consumed unchanged by `av_mac_report.py` (Task 2). `AvMacRow`/`AvMacReport` (Task 2) → consumed duck-typed by `excel_generator.py` (Task 3) and directly by `main.py` (Task 4, `report.rows`, `r.notes`). Field names (`switch`, `stack_member`, `interface`, `vlan`, `mac`, `type`, `notes`) are identical across all four tasks.
- **Non-goal check:** no draw.io/diagram code appears anywhere in this plan, matching the spec's explicit deferral.
