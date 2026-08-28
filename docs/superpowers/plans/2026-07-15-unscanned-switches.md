# Unscanned Cisco Switches Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a block to the combined report's Port Utilisation sheet listing every Cisco switch seen via CDP that was not scanned this session.

**Architecture:** A new pure-Python module `unscanned_switches.py` parses the brief `show cdp neighbors` output (already collected — no new command) into switch neighbours and diffs them against the set of scanned hosts. `excel_generator.py` renders the result as a block appended under the Port Utilisation table. `cheat_core.generate_excel` computes the list and `main.py` feeds it the raw command outputs.

**Tech Stack:** Python 3.9+, openpyxl, pytest.

## Global Constraints

- Python 3.9+ (`tuple[...]`, `list[...]`, `X | None` type hints are already used in this codebase).
- Reuse existing CDP parsing helpers from `interface_parser.py` (`RE_CDP_LOCAL_IFACE`, `RE_CDP_PORT_ID`, `CDP_CISCO_TYPES`, `extract_neighbor_port`) — do not duplicate interface-normalisation logic.
- A "switch" neighbour = CDP Capability field contains `S` (catches `S I` and `R S I`; excludes `H P`, `H`, `R`).
- Scanned set = the keys of the raw outputs dict (every device we ran commands on), domain-stripped and case-folded for matching.
- One row per sighting = one `(device, seen_on, local_iface)` tuple.
- All changes must keep existing callers working: new parameters are optional with backward-compatible defaults.
- Run the full suite with `python3 -m pytest -q` from the repo root; 3 pre-existing errors in `test_mock_dnac.py` (fixture-arg issues) are unrelated and expected.

---

### Task 1: CDP switch-neighbour parser

**Files:**
- Create: `unscanned_switches.py`
- Test: `test_unscanned_switches.py`

**Interfaces:**
- Consumes: `interface_parser.RE_CDP_LOCAL_IFACE`, `interface_parser.RE_CDP_PORT_ID`, `interface_parser.extract_neighbor_port`.
- Produces:
  - `SwitchNeighbour` dataclass with fields `device: str, platform: str, capability: str, local_iface: str, neighbour_port: str, seen_on: str = ""`.
  - `parse_cdp_switch_neighbors(text: str) -> list[SwitchNeighbour]` — returns only neighbours whose capability contains `S`; `seen_on` left `""`.

- [ ] **Step 1: Write the failing test**

Create `test_unscanned_switches.py`:

```python
CDP_BRIEF = "\n".join([
    "show cdp neighbors",
    "Capability Codes: R - Router, T - Trans Bridge, B - Source Route Bridge",
    "                  S - Switch, H - Host, I - IGMP, r - Repeater, P - Phone, ",
    "                  D - Remote, C - CVTA, M - Two-port Mac Relay ",
    "",
    "Device ID        Local Intrfce     Holdtme    Capability  Platform  Port ID",
    "sw4              Gig 0/0           137              S I   C9KV-UADP Gig 0/0",
    "sw2              Gig 1/0/3         169              S I   C9KV-UADP Gig 1/0/2",
    "deskphone-01     Gig 1/0/5         120              H P   IP-Phone  Port 1",
    "",
    "Total cdp entries displayed : 3",
    "sw1#",
])


def test_parse_cdp_switch_neighbors_keeps_only_switches():
    from unscanned_switches import parse_cdp_switch_neighbors
    nbrs = parse_cdp_switch_neighbors(CDP_BRIEF)
    devices = sorted(n.device for n in nbrs)
    assert devices == ["sw2", "sw4"]  # phone excluded


def test_parse_cdp_switch_neighbors_extracts_fields():
    from unscanned_switches import parse_cdp_switch_neighbors
    nbrs = {n.device: n for n in parse_cdp_switch_neighbors(CDP_BRIEF)}
    n = nbrs["sw4"]
    assert n.local_iface == "Gi0/0"
    assert n.capability == "S I"
    assert n.platform == "C9KV-UADP"
    assert n.neighbour_port == "Gi0/0"
    assert n.seen_on == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_unscanned_switches.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'unscanned_switches'`

- [ ] **Step 3: Write minimal implementation**

Create `unscanned_switches.py`:

```python
"""
Detect Cisco switches seen via CDP that were not scanned this session.

Parses the brief `show cdp neighbors` output already collected for every device
and diffs the switch-capable neighbours against the set of scanned hosts.
"""

from dataclasses import dataclass, replace

from interface_parser import (
    RE_CDP_LOCAL_IFACE,
    RE_CDP_PORT_ID,
    extract_neighbor_port,
)

# CDP capability codes (R Router, T Trans Bridge, B SR Bridge, S Switch,
# H Host, I IGMP, r Repeater, P Phone, D Remote, C CVTA, M Two-port Mac Relay).
CDP_CAP_CODES = set("RTBSHIrPDCM")


@dataclass
class SwitchNeighbour:
    device: str
    platform: str
    capability: str
    local_iface: str
    neighbour_port: str
    seen_on: str = ""


def parse_cdp_switch_neighbors(text: str) -> list[SwitchNeighbour]:
    """Parse brief `show cdp neighbors` output, keeping only switch neighbours.

    A neighbour is a switch when its Capability field contains 'S'. Long Device
    IDs wrap onto their own line (the interface appears indented on the next
    line); that case is handled via `pending_device`.
    """
    out: list[SwitchNeighbour] = []
    in_table = False
    pending_device: str | None = None

    for raw in text.split("\n"):
        line = raw.rstrip()

        if not in_table:
            if "Device ID" in line and ("Local Intrfce" in line or "Local Interface" in line):
                in_table = True
            continue

        stripped = line.strip()
        if not stripped:
            continue

        # End of CDP output.
        if (stripped.endswith("#") or stripped.endswith(">")
                or stripped.lower().startswith("show ")
                or stripped.lower().startswith("total cdp entries")):
            in_table = False
            pending_device = None
            continue

        # Repeated header (rare).
        if "Device ID" in line and ("Local Intrfce" in line or "Local Interface" in line):
            continue

        indented = line[0].isspace()
        local_match = RE_CDP_LOCAL_IFACE.search(line)

        if not local_match:
            if not indented:
                pending_device = stripped.split()[0]
            continue

        device = pending_device if indented else stripped.split()[0]
        pending_device = None
        if not device:
            continue

        local_iface = local_match.group(1)[:2].capitalize() + local_match.group(2)

        rem = line[local_match.end():].strip()
        neighbour_port = extract_neighbor_port(rem)
        mport = RE_CDP_PORT_ID.search(rem)
        middle = rem[:mport.start()].strip() if mport else rem

        mtokens = middle.split()
        if mtokens and mtokens[0].isdigit():   # holdtime
            mtokens = mtokens[1:]

        cap: list[str] = []
        while mtokens and len(mtokens[0]) == 1 and mtokens[0] in CDP_CAP_CODES:
            cap.append(mtokens.pop(0))

        if "S" not in cap:
            continue

        out.append(SwitchNeighbour(
            device=device,
            platform=" ".join(mtokens),
            capability=" ".join(cap),
            local_iface=local_iface,
            neighbour_port=neighbour_port,
        ))

    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_unscanned_switches.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add unscanned_switches.py test_unscanned_switches.py
git commit -m "feat: parse switch neighbours from brief CDP output"
```

---

### Task 2: Aggregate unscanned switches across devices

**Files:**
- Modify: `unscanned_switches.py`
- Test: `test_unscanned_switches.py`

**Interfaces:**
- Consumes: `parse_cdp_switch_neighbors`, `SwitchNeighbour` (Task 1).
- Produces: `find_unscanned_switches(raw_outputs: dict[str, str], scanned_hostnames) -> list[SwitchNeighbour]` — one entry per `(device, seen_on, local_iface)` sighting, `seen_on` stamped, sorted by `(device, seen_on, local_iface)` (all normalised for the sort key), excluding neighbours whose normalised name is in the scanned set.

- [ ] **Step 1: Write the failing test**

Append to `test_unscanned_switches.py`:

```python
def _sw1_text():
    return "\n".join([
        "Device ID        Local Intrfce     Holdtme    Capability  Platform  Port ID",
        "sw2              Gig 1/0/3         169              S I   C9KV-UADP Gig 1/0/2",
        "sw3              Gig 1/0/1         156              S I   C9KV-UADP Gig 1/0/2",
        "SW4.example.net  Gig 0/0           137              S I   C9KV-UADP Gig 0/0",
        "Total cdp entries displayed : 3",
    ])


def test_find_unscanned_switches_flags_only_unknown():
    from unscanned_switches import find_unscanned_switches
    raw = {"sw1": _sw1_text(), "sw2": "", "sw3": ""}
    rows = find_unscanned_switches(raw, raw.keys())
    # sw2/sw3 are scanned -> excluded; sw4 (FQDN, different case) -> flagged.
    assert [r.device for r in rows] == ["SW4.example.net"]
    assert rows[0].seen_on == "sw1"
    assert rows[0].local_iface == "Gi0/0"


def test_find_unscanned_switches_dedupes_sightings():
    from unscanned_switches import find_unscanned_switches
    raw = {"sw1": _sw1_text(), "sw1b": _sw1_text()}  # same sighting text twice, diff hosts
    rows = find_unscanned_switches(raw, ["sw1", "sw1b"])
    # sw2/sw3 scanned-out; sw4 seen on two different hosts -> two sightings.
    assert sorted((r.device, r.seen_on) for r in rows) == [
        ("SW4.example.net", "sw1"), ("SW4.example.net", "sw1b")
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_unscanned_switches.py -k find_unscanned -q`
Expected: FAIL with `ImportError: cannot import name 'find_unscanned_switches'`

- [ ] **Step 3: Write minimal implementation**

Append to `unscanned_switches.py`:

```python
def _norm_host(name: str) -> str:
    """Normalise a hostname for matching: drop domain suffix, case-fold."""
    return str(name).split(".")[0].strip().casefold()


def find_unscanned_switches(raw_outputs: dict[str, str], scanned_hostnames) -> list[SwitchNeighbour]:
    """Return switch neighbours seen via CDP that were not scanned this session.

    raw_outputs maps hostname -> raw command output. scanned_hostnames is the set
    of hosts we ran commands on. One SwitchNeighbour per (device, seen_on,
    local_iface) sighting.
    """
    scanned = {_norm_host(h) for h in scanned_hostnames}
    seen: set = set()
    rows: list[SwitchNeighbour] = []

    for host, text in raw_outputs.items():
        for nb in parse_cdp_switch_neighbors(text):
            if _norm_host(nb.device) in scanned:
                continue
            key = (_norm_host(nb.device), _norm_host(host), nb.local_iface)
            if key in seen:
                continue
            seen.add(key)
            rows.append(replace(nb, seen_on=host))

    rows.sort(key=lambda n: (_norm_host(n.device), _norm_host(n.seen_on), n.local_iface))
    return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_unscanned_switches.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add unscanned_switches.py test_unscanned_switches.py
git commit -m "feat: diff CDP switch neighbours against scanned hosts"
```

---

### Task 3: Render the unscanned-switches block

**Files:**
- Modify: `excel_generator.py` (add renderer + module-level constants near the other header lists, e.g. after `COL_WIDTHS`)
- Test: `test_unscanned_switches.py`

**Interfaces:**
- Consumes: `SwitchNeighbour` (Task 1).
- Produces: `write_unscanned_switches_block(ws, start_row: int, rows: list) -> None` — writes a bold title at `start_row`; if `rows` is empty, writes `"None detected"` at `start_row + 1`; otherwise writes a header row at `start_row + 1` (`Unknown Neighbour | Platform | Capability | Seen On | Local Interface | Neighbour Port`) and one data row per sighting from `start_row + 2`.

- [ ] **Step 1: Write the failing test**

Append to `test_unscanned_switches.py`:

```python
def test_write_unscanned_switches_block_with_rows():
    import openpyxl
    from unscanned_switches import SwitchNeighbour
    from excel_generator import write_unscanned_switches_block, UNSCANNED_HEADERS
    ws = openpyxl.Workbook().active
    rows = [SwitchNeighbour("sw4", "C9KV-UADP", "S I", "Gi0/0", "Gi0/0", "sw1")]
    write_unscanned_switches_block(ws, 5, rows)
    assert "Unscanned Cisco Switches" in ws.cell(row=5, column=1).value
    assert [ws.cell(row=6, column=c).value for c in range(1, 7)] == UNSCANNED_HEADERS
    assert ws.cell(row=7, column=1).value == "sw4"
    assert ws.cell(row=7, column=4).value == "sw1"
    assert ws.cell(row=7, column=5).value == "Gi0/0"


def test_write_unscanned_switches_block_empty():
    import openpyxl
    from excel_generator import write_unscanned_switches_block
    ws = openpyxl.Workbook().active
    write_unscanned_switches_block(ws, 5, [])
    assert ws.cell(row=6, column=1).value == "None detected"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_unscanned_switches.py -k block -q`
Expected: FAIL with `ImportError: cannot import name 'write_unscanned_switches_block'`

- [ ] **Step 3: Write minimal implementation**

In `excel_generator.py`, add the import near the top (after the existing `from port_utilisation import ...` line):

```python
from unscanned_switches import find_unscanned_switches, SwitchNeighbour
```

Add these constants after `COL_WIDTHS = [...]`:

```python
UNSCANNED_TITLE = "Unscanned Cisco Switches (seen via CDP, not scanned this session)"
UNSCANNED_HEADERS = [
    "Unknown Neighbour", "Platform", "Capability",
    "Seen On", "Local Interface", "Neighbour Port",
]
```

Add the renderer (place it just above `write_combined_excel`):

```python
def write_unscanned_switches_block(ws, start_row: int, rows: list) -> None:
    """Append the unscanned-switches block to an existing worksheet.

    Writes a bold title at start_row. With no rows, writes 'None detected'
    below it; otherwise a header row then one row per sighting.
    """
    title = ws.cell(row=start_row, column=1, value=UNSCANNED_TITLE)
    title.font = Font(bold=True, name="Arial", size=10)

    if not rows:
        ws.cell(row=start_row + 1, column=1, value="None detected")
        return

    header_font = Font(bold=True, color="FFFFFFFF", name="Arial", size=10)
    header_fill = PatternFill("solid", start_color="FF2B579A")
    header_align = Alignment(horizontal="center", vertical="center")

    hdr_row = start_row + 1
    for col, header in enumerate(UNSCANNED_HEADERS, start=1):
        c = ws.cell(row=hdr_row, column=col, value=header)
        c.font = header_font
        c.fill = header_fill
        c.alignment = header_align

    for i, nb in enumerate(rows):
        r = hdr_row + 1 + i
        ws.cell(row=r, column=1, value=nb.device)
        ws.cell(row=r, column=2, value=nb.platform)
        ws.cell(row=r, column=3, value=nb.capability)
        ws.cell(row=r, column=4, value=nb.seen_on)
        ws.cell(row=r, column=5, value=nb.local_iface)
        ws.cell(row=r, column=6, value=nb.neighbour_port)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_unscanned_switches.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add excel_generator.py test_unscanned_switches.py
git commit -m "feat: render unscanned Cisco switches block"
```

---

### Task 4: Place the block under the Port Utilisation table

**Files:**
- Modify: `port_utilisation.py:345-410` (`write_utilisation_sheet` — return the next free row)
- Modify: `excel_generator.py:256-317` (`write_combined_excel` — accept `unscanned`, append block)
- Test: `test_unscanned_switches.py`

**Interfaces:**
- Consumes: `write_unscanned_switches_block` (Task 3), `write_utilisation_sheet`.
- Produces:
  - `write_utilisation_sheet(...) -> int` — now returns the first free row below the TOTAL row.
  - `write_combined_excel(devices_data, threshold_days, outpath, unscanned=None)` — when `unscanned is not None`, appends the block to the Port Utilisation sheet one blank row below the table; when `None`, the block is omitted.

- [ ] **Step 1: Write the failing test**

Append to `test_unscanned_switches.py`:

```python
def _devices_data():
    from interface_parser import InterfaceRecord
    rec = InterfaceRecord(switch="sw1", iface="Gi1/0/1", stack_member="1",
                          last_input="00:00:01")
    return {"sw1": ([rec], {})}


def _find_block_title_row(ws):
    for r in range(1, ws.max_row + 1):
        val = ws.cell(row=r, column=1).value
        if val and "Unscanned Cisco Switches" in str(val):
            return r
    return None


def test_combined_excel_includes_block_below_total(tmp_path):
    import openpyxl
    from excel_generator import write_combined_excel
    from unscanned_switches import SwitchNeighbour
    out = tmp_path / "report.xlsx"
    unscanned = [SwitchNeighbour("sw4", "C9KV-UADP", "S I", "Gi0/0", "Gi0/0", "sw1")]
    ok, _ = write_combined_excel(_devices_data(), 42, str(out), unscanned=unscanned)
    assert ok
    ws = openpyxl.load_workbook(out)["Port Utilisation"]
    title_row = _find_block_title_row(ws)
    assert title_row is not None
    # Block sits below the TOTAL row of the utilisation table.
    total_row = next(r for r in range(1, ws.max_row + 1)
                     if ws.cell(row=r, column=1).value == "TOTAL")
    assert title_row > total_row
    assert ws.cell(row=title_row + 2, column=1).value == "sw4"


def test_combined_excel_omits_block_when_unscanned_none(tmp_path):
    import openpyxl
    from excel_generator import write_combined_excel
    out = tmp_path / "report.xlsx"
    ok, _ = write_combined_excel(_devices_data(), 42, str(out))  # unscanned defaults None
    assert ok
    ws = openpyxl.load_workbook(out)["Port Utilisation"]
    assert _find_block_title_row(ws) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_unscanned_switches.py -k combined -q`
Expected: FAIL — `test_combined_excel_includes_block_below_total` fails because the block is not written (title row is `None`).

- [ ] **Step 3: Write minimal implementation**

In `port_utilisation.py`, at the end of `write_utilisation_sheet` (currently the last statement is `ws.freeze_panes = "A2"`), add a return of the next free row. The `row` variable at that point holds the TOTAL row index:

```python
    ws.freeze_panes = "A2"
    return row + 1
```

In `excel_generator.py`, replace the Port Utilisation section of `write_combined_excel` (the `if util_results: ... else: ...` block) with:

```python
        # Sheet 2: Port Utilisation
        util_results = _compute_utilisation(devices_data, threshold_days)
        util_hardware = _compute_hardware(devices_data)
        ws_util = wb.create_sheet(title="Port Utilisation")
        if util_results:
            next_row = write_utilisation_sheet(
                ws_util, util_results, threshold_days, hardware=util_hardware
            )
        else:
            ws_util.cell(row=1, column=1, value="No copper port data found")
            next_row = 2

        if unscanned is not None:
            write_unscanned_switches_block(ws_util, next_row + 1, unscanned)
```

And change the function signature:

```python
def write_combined_excel(
    devices_data: dict[str, tuple[list[InterfaceRecord], dict[int, StackMember]]],
    threshold_days: int,
    outpath: str,
    unscanned: list | None = None,
) -> tuple[bool, str]:
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_unscanned_switches.py test_excel_generator.py test_port_utilisation.py -q`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add port_utilisation.py excel_generator.py test_unscanned_switches.py
git commit -m "feat: append unscanned switches block under port utilisation"
```

---

### Task 5: Wire computation into the bulk-scan path

**Files:**
- Modify: `cheat_core.py:24-25` (import), `cheat_core.py:214-253` (`generate_excel`)
- Modify: `main.py:961` (pass `raw_outputs`)
- Test: `test_unscanned_switches.py`

**Interfaces:**
- Consumes: `find_unscanned_switches` (Task 2), `write_combined_excel` with `unscanned=` (Task 4).
- Produces: `generate_excel(devices_data, mode, filename_stem, threshold=42, raw_outputs=None)` — for mode 3, computes `find_unscanned_switches(raw_outputs, raw_outputs.keys())` when `raw_outputs` is provided (else passes `None`).

- [ ] **Step 1: Write the failing test**

Append to `test_unscanned_switches.py`:

```python
def test_generate_excel_mode3_writes_block(tmp_path, monkeypatch):
    import openpyxl
    import cheat_core
    monkeypatch.chdir(tmp_path)
    raw = {"sw1": _sw1_text(), "sw2": "", "sw3": ""}
    results = cheat_core.generate_excel(
        _devices_data(), 3, "report", threshold=42, raw_outputs=raw
    )
    assert results and results[0][0] is True
    path = results[0][1].split("Saved: ")[1].split(" (")[0]
    ws = openpyxl.load_workbook(path)["Port Utilisation"]
    title_row = _find_block_title_row(ws)
    assert title_row is not None
    # sw4 from _sw1_text() is the only unscanned switch.
    assert ws.cell(row=title_row + 2, column=1).value == "SW4.example.net"
```

(`_sw1_text`, `_devices_data`, and `_find_block_title_row` were defined in earlier tasks in this same test file.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_unscanned_switches.py -k generate_excel -q`
Expected: FAIL — `generate_excel` does not accept `raw_outputs` (`TypeError: generate_excel() got an unexpected keyword argument 'raw_outputs'`).

- [ ] **Step 3: Write minimal implementation**

In `cheat_core.py`, extend the excel_generator import (line 25):

```python
from excel_generator import write_excel, write_combined_excel
from unscanned_switches import find_unscanned_switches
```

Change the `generate_excel` signature and its mode-3 branch:

```python
def generate_excel(
    devices_data: dict,
    mode: int,
    filename_stem: str,
    threshold: int = 42,
    raw_outputs: dict | None = None,
) -> list[tuple[bool, str]]:
```

```python
    elif mode == 3:
        outpath = str(excel_dir / f"{filename_stem}-{ts}.xlsx")
        unscanned = None
        if raw_outputs is not None:
            unscanned = find_unscanned_switches(raw_outputs, raw_outputs.keys())
        ok, msg = write_combined_excel(devices_data, threshold, outpath, unscanned=unscanned)
        results.append((ok, msg))
```

In `main.py`, update the call (line 961) to pass the raw outputs dict (the `outputs` variable is in scope):

```python
    results = generate_excel(devices_data, mode, stem, threshold, raw_outputs=outputs)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_unscanned_switches.py -q`
Expected: PASS (all)

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -q`
Expected: all pass except the 3 pre-existing `test_mock_dnac.py` fixture-arg errors (unrelated).

- [ ] **Step 6: Commit**

```bash
git add cheat_core.py main.py test_unscanned_switches.py
git commit -m "feat: compute unscanned switches on bulk scan and write to report"
```

---

## Self-Review

**Spec coverage:**
- New `unscanned_switches.py` with `parse_cdp_switch_neighbors` + `find_unscanned_switches` → Tasks 1, 2.
- Capability `S` filter, domain-strip/case-fold matching, per-sighting dedupe/sort → Tasks 1, 2 (tests assert phone exclusion, FQDN/case, dedupe).
- Renderer + placement under Port Utilisation, "None detected" path, `unscanned=None` omission → Tasks 3, 4.
- `generate_excel` raw_outputs wiring + `main.py` pass-through → Task 5.
- Scope note (mains out of scope): unchanged — `main_cli.py`/`main_debug.py` still call `write_combined_excel` without `unscanned`, so the optional-default omits the block. No task needed.
- Refinement vs spec: scanned set uses `raw_outputs.keys()` (all scanned hosts) rather than `devices_data.keys()`, so a parse-failed/copper-filtered host is still treated as known. Captured in Task 5 + Global Constraints.

**Placeholder scan:** No TBD/TODO/"handle edge cases" — every code step is complete.

**Type consistency:** `SwitchNeighbour` field order `(device, platform, capability, local_iface, neighbour_port, seen_on)` is used consistently in the renderer and all positional test constructions. `write_utilisation_sheet` now returns `int`; its only caller (`write_combined_excel`) consumes it. `write_combined_excel(..., unscanned=None)` and `generate_excel(..., raw_outputs=None)` names match across tasks.
