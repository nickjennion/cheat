# CDP Detail Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collect `show cdp neighbors detail` and parse it into one rich neighbour record (full model, management IP, unambiguous interface names) that feeds the CDP Neighbors column and the Unscanned Switches block.

**Architecture:** A new pure module `cdp_detail.py` parses the block-structured detail output into `CdpNeighbor` records. The two existing CDP parsers (`interface_parser.parse_cdp_neighbors`, `unscanned_switches.parse_cdp_switch_neighbors`) are reimplemented on top of it, keeping their public signatures. The command set swaps brief → detail, and the Excel unscanned block gains a Mgmt IP column.

**Tech Stack:** Python 3.9+, `re`, `dataclasses`, openpyxl (excel only), pytest.

## Global Constraints

- Python 3.9+ (`list[...]`, `X | None` hints used throughout).
- `cdp_detail.py` is pure parsing — no openpyxl, no file IO. It may import `shorten_iface` from `interface_parser` at module level.
- **No circular import:** `interface_parser` must NOT import `cdp_detail` at module level — `parse_cdp_neighbors` imports `parse_cdp_detail` *inside the function body*.
- `CdpNeighbor` field order: `(device, mgmt_ip, platform, capabilities, local_iface, remote_port)`.
- `SwitchNeighbour` gains `mgmt_ip: str = ""` as its **last** field (keeps existing positional constructions working).
- Management IP preference: `Management address(es):` IPv4 → `Entry address(es):` IPv4 → `""`. IPv6 is ignored.
- Platform cleaning: strip a leading `cisco `/`Cisco ` and a trailing ` (PID:...)`.
- Switch test: `"switch" in capabilities.lower()`.
- Port normalisation: full Cisco name → short (`GigabitEthernet1/0/8` → `Gi1/0/8`); abbreviated Cisco (`gi23` → `Gi23`) for prefixes `gi te fa fo hu tw fi`; anything else verbatim (`Port 1`, `eth0`).
- Unscanned block header order: `Unknown Neighbour | Platform | Mgmt IP | Capability | Seen On | Local Interface | Neighbour Port`.
- Run tests with `python3 -m pytest` from the repo root. Pre-existing collection errors in `test_mock_dnac.py` / `test_dnac.py` / `test_sandbox.py` are unrelated — ignore them.

---

### Task 1: `cdp_detail.py` parser

**Files:**
- Create: `cdp_detail.py`
- Test: `test_cdp_detail.py`

**Interfaces:**
- Consumes: `interface_parser.shorten_iface`.
- Produces:
  - `CdpNeighbor(device, mgmt_ip, platform, capabilities, local_iface, remote_port)` dataclass.
  - `parse_cdp_detail(text: str) -> list[CdpNeighbor]`.
  - `is_switch(neighbor: CdpNeighbor) -> bool`.

- [ ] **Step 1: Write the failing test**

Create `test_cdp_detail.py` (fixtures are redacted versions of two real captures):

```python
SWITCH_AND_PHONE = "\n".join([
    "show cdp neighbors detail",
    "-------------------------",
    "Device ID: x-dist-4500xv.net.hu.edu",
    "Entry address(es):",
    "  IP address: 10.20.1.5",
    "Platform: cisco WS-C4500X-32,  Capabilities: Router Switch IGMP ",
    "Interface: TenGigabitEthernet2/1/4,  Port ID (outgoing port): TenGigabitEthernet2/1/24",
    "Holdtime : 123 sec",
    "",
    "Version :",
    "Cisco IOS Software, Catalyst 4500 L3 Switch Software, Version 03.11.10.E",
    "",
    "advertisement version: 2",
    "Management address(es):",
    "  IP address: 10.99.99.9",
    "-------------------------",
    "Device ID: SEP00ecab",
    "Entry address(es):",
    "  IP address: 10.20.9.5",
    "  IPv6 address: ::  (global unicast)",
    "Platform: Cisco IP Phone 6901,  Capabilities: Host Phone ",
    "Interface: GigabitEthernet2/0/10,  Port ID (outgoing port): Port 1",
    "Holdtime : 171 sec",
    "-------------------------",
    "Device ID: f4747aabbcc",
    "Entry address(es):",
    "  IPv6 address: FE80::F674:70FF:FE1D:1  (link-local)",
    "Platform: Cisco C1300-24FP-4G (PID:C1300-24FP-4G),  Capabilities: Router Switch IGMP ",
    "Interface: TenGigabitEthernet2/0/4,  Port ID (outgoing port): gi23",
    "Holdtime : 165 sec",
    "",
    "Total cdp entries displayed : 3",
    "redacted#",
])


def test_parse_cdp_detail_switch_prefers_management_ip():
    from cdp_detail import parse_cdp_detail
    by = {n.device: n for n in parse_cdp_detail(SWITCH_AND_PHONE)}
    s = by["x-dist-4500xv.net.hu.edu"]
    assert s.mgmt_ip == "10.99.99.9"          # Management, not Entry (10.20.1.5)
    assert s.platform == "WS-C4500X-32"        # cisco prefix stripped
    assert s.capabilities.split() == ["Router", "Switch", "IGMP"]
    assert s.local_iface == "Te2/1/4"
    assert s.remote_port == "Te2/1/24"


def test_parse_cdp_detail_phone_and_ipv6_only():
    from cdp_detail import parse_cdp_detail, is_switch
    by = {n.device: n for n in parse_cdp_detail(SWITCH_AND_PHONE)}
    phone = by["SEP00ecab"]
    assert is_switch(phone) is False
    assert phone.remote_port == "Port 1"       # non-Cisco, verbatim
    assert phone.platform == "IP Phone 6901"
    assert phone.mgmt_ip == "10.20.9.5"        # entry IPv4 (no management section)
    c1300 = by["f4747aabbcc"]
    assert is_switch(c1300) is True
    assert c1300.mgmt_ip == ""                 # IPv6 link-local only
    assert c1300.platform == "C1300-24FP-4G"   # PID suffix stripped
    assert c1300.remote_port == "Gi23"         # abbreviated Cisco normalised


def test_parse_cdp_detail_counts_blocks():
    from cdp_detail import parse_cdp_detail
    assert len(parse_cdp_detail(SWITCH_AND_PHONE)) == 3
    assert parse_cdp_detail("no cdp section here") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_cdp_detail.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'cdp_detail'`

- [ ] **Step 3: Write minimal implementation**

Create `cdp_detail.py`:

```python
"""
Parse `show cdp neighbors detail` into rich neighbour records.

Pure parsing — no XML, no file IO. One CdpNeighbor per detail block; feeds the
CDP Neighbors column, the Unscanned Switches block, and the topology.
"""

import re
from dataclasses import dataclass

from interface_parser import shorten_iface

# Cisco interface-type abbreviations that appear as bare Port IDs (e.g. "gi23"
# on small-business switches). Anything else (Port 1, eth0) is kept verbatim.
_CDP_ABBR = {"gi": "Gi", "te": "Te", "fa": "Fa", "fo": "Fo",
             "hu": "Hu", "tw": "Tw", "fi": "Fi"}

_RE_DEVICE = re.compile(r"(?im)^\s*Device ID:\s*(\S+)")
_RE_PLATFORM = re.compile(r"(?im)^\s*Platform:\s*(.+?),\s*Capabilities:\s*(.*)$")
_RE_IFACE = re.compile(
    r"(?im)^\s*Interface:\s*(.+?),\s*Port ID \(outgoing port\):\s*(.*)$"
)
_RE_IPV4 = re.compile(r"IP address:\s*(\d{1,3}(?:\.\d{1,3}){3})")


@dataclass
class CdpNeighbor:
    device: str
    mgmt_ip: str
    platform: str
    capabilities: str
    local_iface: str
    remote_port: str


def is_switch(neighbor: CdpNeighbor) -> bool:
    """True when the neighbour advertises the Switch capability."""
    return "switch" in neighbor.capabilities.lower()


def _clean_platform(s: str) -> str:
    s = re.sub(r"^\s*cisco\s+", "", s.strip(), flags=re.IGNORECASE)
    s = re.sub(r"\s*\(PID:[^)]*\)\s*$", "", s)
    return s.strip()


def _norm_port(name: str) -> str:
    """Short Cisco form for interfaces; verbatim for non-Cisco port labels."""
    name = name.strip()
    if not name:
        return ""
    short = shorten_iface(name)
    if short != name:               # recognised full Cisco name
        return short
    m = re.match(r"^([A-Za-z]{2,4})(\d.*)$", name)   # abbreviated, e.g. "gi23"
    if m and m.group(1).lower() in _CDP_ABBR:
        return _CDP_ABBR[m.group(1).lower()] + m.group(2)
    return name                     # "Port 1", "eth0", ...


def _section_ipv4(block: str, header: str) -> str:
    """First IPv4 within the named address section of a block, or ''."""
    idx = block.find(header)
    if idx == -1:
        return ""
    lines = []
    for ln in block[idx + len(header):].splitlines():
        if ln.strip() == "":
            continue
        if not ln.startswith((" ", "\t")):
            break                    # unindented line -> section ended
        lines.append(ln)
    m = _RE_IPV4.search("\n".join(lines))
    return m.group(1) if m else ""


def _parse_block(block: str) -> "CdpNeighbor | None":
    m_dev = _RE_DEVICE.search(block)
    if not m_dev:
        return None
    platform = capabilities = local_iface = remote_port = ""
    m_p = _RE_PLATFORM.search(block)
    if m_p:
        platform = _clean_platform(m_p.group(1))
        capabilities = m_p.group(2).strip()
    m_i = _RE_IFACE.search(block)
    if m_i:
        local_iface = shorten_iface(m_i.group(1).strip())
        remote_port = _norm_port(m_i.group(2))
    mgmt_ip = (_section_ipv4(block, "Management address(es):")
               or _section_ipv4(block, "Entry address(es):"))
    return CdpNeighbor(m_dev.group(1).strip(), mgmt_ip, platform,
                       capabilities, local_iface, remote_port)


def parse_cdp_detail(text: str) -> list[CdpNeighbor]:
    """Parse the `show cdp neighbors detail` section into neighbour records."""
    end = len(text)
    m_end = re.search(r"Total cdp entries displayed", text, re.IGNORECASE)
    if m_end:
        end = m_end.start()
    start = 0
    m_start = re.search(r"show\s+cdp\s+neighbors?\s+det", text, re.IGNORECASE)
    if m_start and m_start.start() < end:
        start = m_start.end()

    out = []
    for block in re.split(r"(?m)^-{4,}\s*$", text[start:end]):
        if "Device ID:" not in block:
            continue
        nb = _parse_block(block)
        if nb is not None:
            out.append(nb)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_cdp_detail.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add cdp_detail.py test_cdp_detail.py
git commit -m "feat: parse show cdp neighbors detail into rich records"
```

---

### Task 2: Rewire switch-neighbour parser + migrate topology/unscanned fixtures

**Files:**
- Modify: `unscanned_switches.py` (imports; `SwitchNeighbour`; `parse_cdp_switch_neighbors`)
- Test: `test_unscanned_switches.py` (migrate CDP fixtures + assertions), `test_cdp_topology.py` (migrate CDP fixtures)

**Interfaces:**
- Consumes: `cdp_detail.parse_cdp_detail`, `cdp_detail.is_switch` (Task 1).
- Produces: `SwitchNeighbour(device, platform, capability, local_iface, neighbour_port, seen_on="", mgmt_ip="")`; `parse_cdp_switch_neighbors(text) -> list[SwitchNeighbour]` (detail-based, switches only).

- [ ] **Step 1: Write the failing test**

In `test_unscanned_switches.py`, replace the `CDP_BRIEF` fixture (lines 1–14) and the two `parse_cdp_switch_neighbors` tests with detail-format versions:

```python
CDP_DETAIL = "\n".join([
    "show cdp neighbors detail",
    "-------------------------",
    "Device ID: sw2",
    "Entry address(es):",
    "  IP address: 10.0.0.2",
    "Platform: cisco C9KV-UADP,  Capabilities: Router Switch IGMP",
    "Interface: GigabitEthernet1/0/3,  Port ID (outgoing port): GigabitEthernet1/0/2",
    "-------------------------",
    "Device ID: sw4",
    "Entry address(es):",
    "  IP address: 10.0.0.4",
    "Platform: cisco C9KV-UADP,  Capabilities: Router Switch IGMP",
    "Interface: GigabitEthernet0/0,  Port ID (outgoing port): GigabitEthernet0/0",
    "-------------------------",
    "Device ID: deskphone",
    "Entry address(es):",
    "  IP address: 10.0.0.9",
    "Platform: Cisco IP Phone 6901,  Capabilities: Host Phone",
    "Interface: GigabitEthernet1/0/5,  Port ID (outgoing port): Port 1",
    "Total cdp entries displayed : 3",
])


def test_parse_cdp_switch_neighbors_keeps_only_switches():
    from unscanned_switches import parse_cdp_switch_neighbors
    devices = sorted(n.device for n in parse_cdp_switch_neighbors(CDP_DETAIL))
    assert devices == ["sw2", "sw4"]  # phone excluded


def test_parse_cdp_switch_neighbors_extracts_fields():
    from unscanned_switches import parse_cdp_switch_neighbors
    nbrs = {n.device: n for n in parse_cdp_switch_neighbors(CDP_DETAIL)}
    n = nbrs["sw4"]
    assert n.local_iface == "Gi0/0"
    assert "switch" in n.capability.lower()
    assert n.platform == "C9KV-UADP"
    assert n.neighbour_port == "Gi0/0"
    assert n.mgmt_ip == "10.0.0.4"
    assert n.seen_on == ""
```

Also replace the `_sw1_text()` helper (used by the `find_unscanned_switches` tests) with detail format:

```python
def _sw1_text():
    return "\n".join([
        "show cdp neighbors detail",
        "-------------------------",
        "Device ID: sw2",
        "Platform: cisco C9KV-UADP,  Capabilities: Router Switch IGMP",
        "Interface: GigabitEthernet1/0/3,  Port ID (outgoing port): GigabitEthernet1/0/2",
        "-------------------------",
        "Device ID: sw3",
        "Platform: cisco C9KV-UADP,  Capabilities: Router Switch IGMP",
        "Interface: GigabitEthernet1/0/1,  Port ID (outgoing port): GigabitEthernet1/0/2",
        "-------------------------",
        "Device ID: SW4.example.net",
        "Platform: cisco C9KV-UADP,  Capabilities: Router Switch IGMP",
        "Interface: GigabitEthernet0/0,  Port ID (outgoing port): GigabitEthernet0/0",
        "Total cdp entries displayed : 3",
    ])
```

(The existing `find_unscanned_switches` assertions — `SW4.example.net` flagged, `seen_on == "sw1"`, `local_iface == "Gi0/0"` — remain valid.)

In `test_cdp_topology.py`, replace `SW1_CDP` and `SW2_CDP` (lines 1–13) with detail format that yields the same devices/ports the existing assertions expect:

```python
SW1_CDP = "\n".join([
    "show cdp neighbors detail",
    "-------------------------",
    "Device ID: sw2",
    "Platform: cisco C9KV-UADP,  Capabilities: Router Switch IGMP",
    "Interface: GigabitEthernet1/0/3,  Port ID (outgoing port): GigabitEthernet1/0/2",
    "-------------------------",
    "Device ID: sw3",
    "Platform: cisco C9KV-UADP,  Capabilities: Router Switch IGMP",
    "Interface: GigabitEthernet1/0/1,  Port ID (outgoing port): GigabitEthernet1/0/2",
    "-------------------------",
    "Device ID: sw4",
    "Platform: cisco C9KV-UADP,  Capabilities: Router Switch IGMP",
    "Interface: GigabitEthernet0/0,  Port ID (outgoing port): GigabitEthernet0/0",
    "-------------------------",
    "Device ID: deskphone",
    "Platform: Cisco IP Phone 6901,  Capabilities: Host Phone",
    "Interface: GigabitEthernet1/0/9,  Port ID (outgoing port): Port 1",
    "Total cdp entries displayed : 4",
])
SW2_CDP = "\n".join([
    "show cdp neighbors detail",
    "-------------------------",
    "Device ID: sw1",
    "Platform: cisco C9KV-UADP,  Capabilities: Router Switch IGMP",
    "Interface: GigabitEthernet1/0/2,  Port ID (outgoing port): GigabitEthernet1/0/3",
    "Total cdp entries displayed : 1",
])
```

The `test_build_topology_nodes_and_rogue_flag` assertion that a rogue's platform is `"C9KV-UADP"` stays valid (Platform line is `cisco C9KV-UADP`). If that test asserts `by_name["sw4"].platform == "C9KV-UADP"`, leave it; it still holds.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_unscanned_switches.py test_cdp_topology.py -q`
Expected: FAIL — the detail fixtures no longer parse under the current brief-format `parse_cdp_switch_neighbors` (empty results; assertions fail). Also `mgmt_ip` is not yet a field.

- [ ] **Step 3: Write minimal implementation**

In `unscanned_switches.py`, replace the imports and the `parse_cdp_switch_neighbors` function. Change the top-of-file imports from:

```python
from dataclasses import dataclass, replace

from interface_parser import (
    RE_CDP_LOCAL_IFACE,
    RE_CDP_PORT_ID,
    extract_neighbor_port,
)

# CDP capability codes (R Router, T Trans Bridge, B SR Bridge, S Switch,
# H Host, I IGMP, r Repeater, P Phone, D Remote, C CVTA, M Two-port Mac Relay).
CDP_CAP_CODES = set("RTBSHIrPDCM")
```

to:

```python
from dataclasses import dataclass, replace

from cdp_detail import parse_cdp_detail, is_switch
```

Add `mgmt_ip` to the dataclass:

```python
@dataclass
class SwitchNeighbour:
    device: str
    platform: str
    capability: str
    local_iface: str
    neighbour_port: str
    seen_on: str = ""
    mgmt_ip: str = ""
```

Replace the entire body of `parse_cdp_switch_neighbors` (the brief-table walker) with:

```python
def parse_cdp_switch_neighbors(text: str) -> list[SwitchNeighbour]:
    """Switch-capable CDP neighbours from `show cdp neighbors detail` output."""
    out: list[SwitchNeighbour] = []
    for nb in parse_cdp_detail(text):
        if not is_switch(nb):
            continue
        out.append(SwitchNeighbour(
            device=nb.device,
            platform=nb.platform,
            capability=nb.capabilities,
            local_iface=nb.local_iface,
            neighbour_port=nb.remote_port,
            mgmt_ip=nb.mgmt_ip,
        ))
    return out
```

`_norm_host` and `find_unscanned_switches` are unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_unscanned_switches.py test_cdp_topology.py test_cdp_detail.py -q`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add unscanned_switches.py test_unscanned_switches.py test_cdp_topology.py
git commit -m "feat: switch-neighbour parser on CDP detail (+ mgmt_ip)"
```

---

### Task 3: Rewire the CDP Neighbors column + swap the command

**Files:**
- Modify: `interface_parser.py` (rewrite `parse_cdp_neighbors`)
- Modify: `cheat_core.py` (`DNAC_COMMANDS`)
- Test: `test_interface_parser.py`, `test_cheat_core.py`

**Interfaces:**
- Consumes: `cdp_detail.parse_cdp_detail` (Task 1).
- Produces: `interface_parser.parse_cdp_neighbors(text) -> dict[str, str]` — `{short_iface: "device (port) ip, ..."}` (all neighbours, mgmt IP appended when present).

- [ ] **Step 1: Write the failing test**

Append to `test_interface_parser.py`:

```python
_CDP_DETAIL_COL = "\n".join([
    "show cdp neighbors detail",
    "-------------------------",
    "Device ID: dist-4500xv.net.hu.edu",
    "Entry address(es):",
    "  IP address: 10.20.1.5",
    "Platform: cisco WS-C4500X-32,  Capabilities: Router Switch IGMP",
    "Interface: GigabitEthernet1/0/1,  Port ID (outgoing port): TenGigabitEthernet2/1/24",
    "Management address(es):",
    "  IP address: 10.99.99.9",
    "-------------------------",
    "Device ID: SEP00ecab",
    "Entry address(es):",
    "  IP address: 10.20.9.5",
    "Platform: Cisco IP Phone 6901,  Capabilities: Host Phone",
    "Interface: GigabitEthernet1/0/1,  Port ID (outgoing port): Port 1",
    "Total cdp entries displayed : 2",
])


def test_parse_cdp_neighbors_enriched_cell():
    from interface_parser import parse_cdp_neighbors
    cell = parse_cdp_neighbors(_CDP_DETAIL_COL)["Gi1/0/1"]
    # both neighbours on the same local interface, comma-joined, with mgmt IP.
    assert "dist-4500xv.net.hu.edu (Te2/1/24) 10.99.99.9" in cell
    assert "SEP00ecab (Port 1) 10.20.9.5" in cell           # phone included
    assert cell.count(",") == 1                              # exactly two joined
```

Append to `test_cheat_core.py`:

```python
def test_dnac_commands_use_cdp_detail():
    from cheat_core import DNAC_COMMANDS
    assert "show cdp neighbors detail" in DNAC_COMMANDS
    assert "show cdp neighbors" not in DNAC_COMMANDS  # brief form replaced
    assert len(DNAC_COMMANDS) == 5                    # count unchanged
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_interface_parser.py::test_parse_cdp_neighbors_enriched_cell test_cheat_core.py::test_dnac_commands_use_cdp_detail -q`
Expected: FAIL — the current `parse_cdp_neighbors` parses the brief table (returns `{}` for detail input), and `DNAC_COMMANDS` still holds `"show cdp neighbors"`.

- [ ] **Step 3: Write minimal implementation**

In `interface_parser.py`, replace the entire `parse_cdp_neighbors` function (the brief-table walker, `def parse_cdp_neighbors(text: str) -> dict[str, str]:` through its `return neighbors`) with:

```python
def parse_cdp_neighbors(text: str) -> dict[str, str]:
    """Map local interface -> "device (port) ip" for every CDP neighbour.

    Built from `show cdp neighbors detail`. Multiple neighbours on one interface
    are comma-joined. The management IP is appended when known. Imported here
    (not at module top) to avoid a cdp_detail <-> interface_parser import cycle.
    """
    from cdp_detail import parse_cdp_detail

    neighbors: dict[str, str] = {}
    for nb in parse_cdp_detail(text):
        if not nb.local_iface:
            continue
        entry = f"{nb.device} ({nb.remote_port})" if nb.remote_port else nb.device
        if nb.mgmt_ip:
            entry += f" {nb.mgmt_ip}"
        if nb.local_iface in neighbors:
            neighbors[nb.local_iface] += f", {entry}"
        else:
            neighbors[nb.local_iface] = entry
    return neighbors
```

In `cheat_core.py`, change the CDP command in `DNAC_COMMANDS`:

```python
    "show cdp neighbors detail",
```

(replacing the line `"show cdp neighbors",`).

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_interface_parser.py test_cheat_core.py -q`
Expected: PASS (all, including the existing `parse_output`/`build_command_list` tests).

- [ ] **Step 5: Commit**

```bash
git add interface_parser.py cheat_core.py test_interface_parser.py test_cheat_core.py
git commit -m "feat: CDP Neighbors column from detail (+ mgmt IP); swap to detail command"
```

---

### Task 4: Mgmt IP column in the Unscanned Switches block

**Files:**
- Modify: `excel_generator.py` (`UNSCANNED_HEADERS`; `write_unscanned_switches_block`)
- Test: `test_unscanned_switches.py`

**Interfaces:**
- Consumes: `SwitchNeighbour.mgmt_ip` (Task 2).
- Produces: the block renders 7 columns: `Unknown Neighbour | Platform | Mgmt IP | Capability | Seen On | Local Interface | Neighbour Port`.

- [ ] **Step 1: Write the failing test**

Replace `test_write_unscanned_switches_block_with_rows` in `test_unscanned_switches.py` with:

```python
def test_write_unscanned_switches_block_with_rows():
    import openpyxl
    from unscanned_switches import SwitchNeighbour
    from excel_generator import write_unscanned_switches_block, UNSCANNED_HEADERS
    ws = openpyxl.Workbook().active
    rows = [SwitchNeighbour("sw4", "WS-C4500X-32", "Router Switch IGMP",
                            "Gi0/1", "Gi0/2", "sw1", mgmt_ip="10.99.99.9")]
    write_unscanned_switches_block(ws, 5, rows)
    assert "Unscanned Cisco Switches" in ws.cell(row=5, column=1).value
    assert [ws.cell(row=6, column=c).value for c in range(1, 8)] == UNSCANNED_HEADERS
    assert ws.cell(row=7, column=1).value == "sw4"
    assert ws.cell(row=7, column=2).value == "WS-C4500X-32"
    assert ws.cell(row=7, column=3).value == "10.99.99.9"   # Mgmt IP
    assert ws.cell(row=7, column=4).value == "Router Switch IGMP"
    assert ws.cell(row=7, column=5).value == "sw1"          # Seen On
    assert ws.cell(row=7, column=6).value == "Gi0/1"        # Local Interface
    assert ws.cell(row=7, column=7).value == "Gi0/2"        # Neighbour Port
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_unscanned_switches.py::test_write_unscanned_switches_block_with_rows -q`
Expected: FAIL — `UNSCANNED_HEADERS` still has 6 entries (no `Mgmt IP`), and the renderer writes the old column order.

- [ ] **Step 3: Write minimal implementation**

In `excel_generator.py`, update `UNSCANNED_HEADERS`:

```python
UNSCANNED_HEADERS = [
    "Unknown Neighbour", "Platform", "Mgmt IP", "Capability",
    "Seen On", "Local Interface", "Neighbour Port",
]
```

In `write_unscanned_switches_block`, replace the per-row cell writes (the block that assigns columns 1–6) with the 7-column version:

```python
    for i, nb in enumerate(rows):
        r = hdr_row + 1 + i
        ws.cell(row=r, column=1, value=nb.device)
        ws.cell(row=r, column=2, value=nb.platform)
        ws.cell(row=r, column=3, value=nb.mgmt_ip)
        ws.cell(row=r, column=4, value=nb.capability)
        ws.cell(row=r, column=5, value=nb.seen_on)
        ws.cell(row=r, column=6, value=nb.local_iface)
        ws.cell(row=r, column=7, value=nb.neighbour_port)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest test_unscanned_switches.py -q`
Expected: PASS (all).

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -q`
Expected: feature and existing suites pass; only the pre-existing `test_mock_dnac.py` / `test_dnac.py` / `test_sandbox.py` collection errors remain.

- [ ] **Step 6: Commit**

```bash
git add excel_generator.py test_unscanned_switches.py
git commit -m "feat: Mgmt IP column in unscanned switches block"
```

---

## Self-Review

**Spec coverage:**
- `cdp_detail.py` (`CdpNeighbor`, `parse_cdp_detail`, `is_switch`, port/platform/mgmt-IP rules) → Task 1.
- Rewire `parse_cdp_switch_neighbors` + `SwitchNeighbour.mgmt_ip`; migrate topology/unscanned fixtures → Task 2.
- Rewire `parse_cdp_neighbors` (enriched cell) + command swap to detail → Task 3.
- Mgmt IP column (keeping Capability) → Task 4.
- Nexus/spaceless-interface gap fixed for free (detail carries full interface names) → inherent to Task 1's parser; no separate task needed.
- Migration note: the spec listed `test_interface_parser.py` among fixtures to migrate, but it has no CDP fixtures — Task 3 adds a fresh test there instead. No coverage lost.

**Placeholder scan:** No TBD/TODO/vague steps — every code step is complete, with exact replacement code and old→new anchors for the `interface_parser`/`cheat_core`/`excel_generator` edits.

**Type consistency:** `CdpNeighbor(device, mgmt_ip, platform, capabilities, local_iface, remote_port)` and `SwitchNeighbour(..., seen_on="", mgmt_ip="")` field orders are used consistently across tasks. `parse_cdp_detail`/`is_switch`/`parse_cdp_switch_neighbors`/`parse_cdp_neighbors` signatures match between the tasks that define and call them. The circular-import guard (function-level import in `interface_parser.parse_cdp_neighbors`) is stated in Global Constraints and applied in Task 3.
