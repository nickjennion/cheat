# Last Link Change Column Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in "Last Link Change" column to the port report sheets showing, per physical port, the time since its most recent link-state transition, derived from `show logging` + `show clock` CLI output.

**Architecture:** Pure parsing helpers in `interface_parser.py` turn syslog `%LINK/%LINEPROTO-UPDOWN` events plus the device clock into a per-interface relative-age string. `parse_output` populates a new `InterfaceRecord.last_link_change` field for physical ports. `write_excel_sheet` appends the column when any record on the sheet carries a value. A menu-5 toggle appends the two extra commands to the run; when off, no logging is collected and the column never appears.

**Tech Stack:** Python 3, openpyxl, pytest, `datetime` (stdlib).

## Global Constraints

- Fleet is Catalyst IOS-XE only (3650/3850/9300); parsing targets IOS-XE syslog and `show clock` formats.
- Collection is via DNAC Command Runner — only add whitelisted `show` commands.
- Cell format is relative-time only (e.g. `2h13m`, `3d4h`, `14m`); no direction, no flap count.
- Physical ports only (name matches `^[A-Za-z]{2,}\d+/\d+`); logical interfaces (Vlan/Port-channel/Loopback/Tunnel) left blank.
- Fallbacks: `stable ≥Xd` when a physical port has no UPDOWN event in the buffer; `unknown` when the clock/timestamps can't be anchored.
- Feature is opt-in via a menu toggle, off by default.
- Follow existing code style: module-level compiled regexes named `RE_*`, non-ASCII glyphs (`✓`, `—`, `≥`) are fine in source.

---

### Task 1: `last_link_change` field + physical-interface classifier

**Files:**
- Modify: `interface_parser.py` (add field to `InterfaceRecord`; add `is_physical_iface` near `member_from_iface`)
- Test: `test_interface_parser.py`

**Interfaces:**
- Produces: `InterfaceRecord.last_link_change: str` (default `""`); `is_physical_iface(iface: str) -> bool`

- [ ] **Step 1: Write the failing tests**

Add to `test_interface_parser.py`:

```python
def test_is_physical_iface_true_for_ethernet_ports():
    from interface_parser import is_physical_iface
    assert is_physical_iface("Gi1/0/5") is True
    assert is_physical_iface("Te1/1/1") is True
    assert is_physical_iface("Fa0/1") is True


def test_is_physical_iface_false_for_logical():
    from interface_parser import is_physical_iface
    assert is_physical_iface("Vlan10") is False
    assert is_physical_iface("Po1") is False
    assert is_physical_iface("Lo0") is False
    assert is_physical_iface("Tunnel1") is False
    assert is_physical_iface("") is False


def test_interface_record_has_last_link_change_default():
    from interface_parser import InterfaceRecord
    assert InterfaceRecord().last_link_change == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test_interface_parser.py -k "physical or last_link_change" -v`
Expected: FAIL — `ImportError: cannot import name 'is_physical_iface'` and `AttributeError` on the field.

- [ ] **Step 3: Add the field and helper**

In `interface_parser.py`, add to the `InterfaceRecord` dataclass after `cdp_neighbors`:

```python
    last_link_change: str = ""
```

Add above `def member_from_iface`:

```python
def is_physical_iface(iface: str) -> bool:
    """True for physical Ethernet ports (slot/port notation), e.g. Gi1/0/5, Fa0/1.

    Logical interfaces (Vlan, Port-channel, Loopback, Tunnel) have no slot/port
    and return False.
    """
    return bool(re.match(r'^[A-Za-z]{2,}\d+/\d+', iface or ""))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test_interface_parser.py -k "physical or last_link_change" -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add interface_parser.py test_interface_parser.py
git commit -m "feat: add last_link_change field and is_physical_iface helper"
```

---

### Task 2: Timestamp, clock, and relative-age helpers

**Files:**
- Modify: `interface_parser.py` (add `RE_CLOCK`, `parse_clock`, `parse_log_timestamp`, `format_age`)
- Test: `test_interface_parser.py`

**Interfaces:**
- Consumes: `from datetime import datetime`
- Produces:
  - `parse_clock(text: str) -> Optional[datetime]`
  - `parse_log_timestamp(ts: str, ref_year: int) -> Optional[datetime]`
  - `format_age(seconds: float) -> str`

- [ ] **Step 1: Write the failing tests**

Add to `test_interface_parser.py`:

```python
from datetime import datetime


def test_parse_clock_reads_device_time():
    from interface_parser import parse_clock
    text = "some banner\n*12:34:56.789 AEST Sun Jul 6 2026\nmore"
    assert parse_clock(text) == datetime(2026, 7, 6, 12, 34, 56)


def test_parse_clock_returns_none_when_absent():
    from interface_parser import parse_clock
    assert parse_clock("no clock line here") is None


def test_parse_log_timestamp_without_year_uses_ref():
    from interface_parser import parse_log_timestamp
    assert parse_log_timestamp("Jul  6 12:34:56.789", 2026) == datetime(2026, 7, 6, 12, 34, 56)


def test_parse_log_timestamp_with_explicit_year():
    from interface_parser import parse_log_timestamp
    assert parse_log_timestamp("Jul  6 2025 12:34:56", 2026) == datetime(2025, 7, 6, 12, 34, 56)


def test_format_age_ranges():
    from interface_parser import format_age
    assert format_age(30) == "<1m"
    assert format_age(14 * 60) == "14m"
    assert format_age(2 * 3600 + 13 * 60) == "2h13m"
    assert format_age(2 * 3600) == "2h"
    assert format_age(3 * 86400 + 4 * 3600) == "3d4h"
    assert format_age(3 * 86400) == "3d"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test_interface_parser.py -k "clock or log_timestamp or format_age" -v`
Expected: FAIL — ImportError for the new names.

- [ ] **Step 3: Implement the helpers**

Ensure the top of `interface_parser.py` imports datetime (add if missing):

```python
from datetime import datetime
```

Add near the other `RE_*` module constants:

```python
RE_CLOCK = re.compile(
    r'[*.]?(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?\s+\w+\s+\w{3}\s+'
    r'(\w{3})\s+(\d{1,2})\s+(\d{4})'
)

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
```

Add these functions (near `uptime_days`):

```python
def parse_clock(text: str) -> Optional[datetime]:
    """Parse the device time from `show clock` output. None if not present."""
    m = RE_CLOCK.search(text)
    if not m:
        return None
    hh, mm, ss, mon, day, year = m.groups()
    month = _MONTHS.get(mon.lower())
    if not month:
        return None
    try:
        return datetime(int(year), month, int(day), int(hh), int(mm), int(ss))
    except ValueError:
        return None


def parse_log_timestamp(ts: str, ref_year: int) -> Optional[datetime]:
    """Parse a syslog datetime like 'Jul  6 12:34:56.789' or 'Jul 6 2025 12:34:56'.

    Uses ref_year when the timestamp carries no explicit year.
    """
    parts = ts.split()
    if len(parts) < 3:
        return None
    month = _MONTHS.get(parts[0].lower())
    if not month:
        return None
    try:
        day = int(parts[1])
        # Explicit year present when the 3rd token is a 4-digit number.
        if len(parts) >= 4 and parts[2].isdigit() and len(parts[2]) == 4:
            year = int(parts[2])
            clock = parts[3]
        else:
            year = ref_year
            clock = parts[2]
        hh, mm, ss = clock.split(".")[0].split(":")
        return datetime(year, month, day, int(hh), int(mm), int(ss))
    except (ValueError, IndexError):
        return None


def format_age(seconds: float) -> str:
    """Relative age as at most two units: '<1m', '14m', '2h13m', '3d4h'."""
    if seconds < 60:
        return "<1m"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes}m"
    hours, rem_m = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h{rem_m}m" if rem_m else f"{hours}h"
    days, rem_h = divmod(hours, 24)
    return f"{days}d{rem_h}h" if rem_h else f"{days}d"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test_interface_parser.py -k "clock or log_timestamp or format_age" -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add interface_parser.py test_interface_parser.py
git commit -m "feat: add clock/log timestamp parsing and relative-age formatting"
```

---

### Task 3: UPDOWN event extraction + `compute_link_changes` orchestrator

**Files:**
- Modify: `interface_parser.py` (add `RE_UPDOWN`, `RE_SYSLOG_TS`, `parse_updown_events`, `_buffer_horizon`, `compute_link_changes`)
- Test: `test_interface_parser.py`

**Interfaces:**
- Consumes: `shorten_iface`, `parse_clock`, `parse_log_timestamp`, `format_age`, `is_physical_iface`
- Produces:
  - `parse_updown_events(text: str, ref_year: int, now: datetime) -> dict[str, datetime]` — short-iface → most-recent event datetime (≤ now)
  - `compute_link_changes(text: str, physical_ifaces: list[str]) -> dict[str, str]` — short-iface → display string

- [ ] **Step 1: Write the failing tests**

Add to `test_interface_parser.py`:

```python
CLOCK_LINE = "*12:00:00.000 AEST Sun Jul 6 2026"


def test_parse_updown_events_keeps_most_recent_per_iface():
    from interface_parser import parse_updown_events
    now = datetime(2026, 7, 6, 12, 0, 0)
    text = "\n".join([
        "*Jul  6 09:00:00.000: %LINK-3-UPDOWN: Interface GigabitEthernet1/0/5, changed state to down",
        "*Jul  6 09:00:05.000: %LINEPROTO-5-UPDOWN: Line protocol on Interface GigabitEthernet1/0/5, changed state to up",
        "*Jul  6 11:30:00.000: %LINK-3-UPDOWN: Interface GigabitEthernet1/0/6, changed state to up",
    ])
    events = parse_updown_events(text, 2026, now)
    assert events["Gi1/0/5"] == datetime(2026, 7, 6, 9, 0, 5)
    assert events["Gi1/0/6"] == datetime(2026, 7, 6, 11, 30, 0)


def test_parse_updown_events_year_rollover():
    from interface_parser import parse_updown_events
    now = datetime(2026, 1, 2, 12, 0, 0)
    # Event in December must be treated as the prior year, not the future.
    text = "*Dec 31 23:59:00.000: %LINK-3-UPDOWN: Interface GigabitEthernet1/0/5, changed state to down"
    events = parse_updown_events(text, 2026, now)
    assert events["Gi1/0/5"] == datetime(2025, 12, 31, 23, 59, 0)


def test_compute_link_changes_event_wins():
    from interface_parser import compute_link_changes
    text = "\n".join([
        CLOCK_LINE,
        "Log Buffer (16384 bytes):",
        "*Jul  6 09:47:00.000: %LINK-3-UPDOWN: Interface GigabitEthernet1/0/5, changed state to up",
    ])
    out = compute_link_changes(text, ["Gi1/0/5"])
    assert out["Gi1/0/5"] == "2h13m"


def test_compute_link_changes_stable_floor_for_no_event():
    from interface_parser import compute_link_changes
    text = "\n".join([
        CLOCK_LINE,
        "Log Buffer (16384 bytes):",
        "*Jun 30 12:00:00.000: %SYS-5-CONFIG_I: Configured from console",  # oldest buffered line, 6d ago
        "*Jul  6 09:47:00.000: %LINK-3-UPDOWN: Interface GigabitEthernet1/0/5, changed state to up",
    ])
    out = compute_link_changes(text, ["Gi1/0/6"])  # port with no UPDOWN event
    assert out["Gi1/0/6"] == "stable ≥6d"


def test_compute_link_changes_unknown_without_clock():
    from interface_parser import compute_link_changes
    text = "Log Buffer (16384 bytes):\n*Jul  6 09:47:00.000: %LINK-3-UPDOWN: Interface GigabitEthernet1/0/5, changed state to up"
    out = compute_link_changes(text, ["Gi1/0/5"])
    assert out["Gi1/0/5"] == "unknown"


def test_compute_link_changes_empty_without_logging():
    from interface_parser import compute_link_changes
    out = compute_link_changes(CLOCK_LINE, ["Gi1/0/5"])
    assert out == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test_interface_parser.py -k "updown or link_changes" -v`
Expected: FAIL — ImportError for `parse_updown_events` / `compute_link_changes`.

- [ ] **Step 3: Implement extraction + orchestrator**

Add regexes near the other `RE_*` constants:

```python
RE_UPDOWN = re.compile(
    r'(?P<ts>\w{3}\s+\d{1,2}\s+(?:\d{4}\s+)?\d{2}:\d{2}:\d{2}(?:\.\d+)?)'
    r'.*?%(?:LINK|LINEPROTO)-\d-UPDOWN:.*?'
    r'Interface\s+(?P<iface>[A-Za-z0-9/.\-]+),\s+changed state to (?:up|down)'
)

RE_SYSLOG_TS = re.compile(
    r'(?<![\d:])(\w{3}\s+\d{1,2}\s+(?:\d{4}\s+)?\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s*:'
)
```

Add functions:

```python
def parse_updown_events(text: str, ref_year: int, now: datetime) -> dict:
    """Map short-form interface name -> datetime of its most recent UPDOWN event.

    Events parsed with no explicit year that land in the future relative to `now`
    are rolled back one year (log buffer spanning a year boundary).
    """
    events: dict[str, datetime] = {}
    for m in RE_UPDOWN.finditer(text):
        ts = parse_log_timestamp(m.group("ts"), ref_year)
        if ts is None:
            continue
        if ts > now:
            ts = ts.replace(year=ts.year - 1)
        iface = shorten_iface(m.group("iface"))
        if iface not in events or ts > events[iface]:
            events[iface] = ts
    return events


def _buffer_horizon(text: str, ref_year: int, now: datetime) -> Optional[str]:
    """Relative age of the oldest timestamped syslog line, for the stable floor."""
    oldest: Optional[datetime] = None
    for m in RE_SYSLOG_TS.finditer(text):
        ts = parse_log_timestamp(m.group(1), ref_year)
        if ts is None:
            continue
        if ts > now:
            ts = ts.replace(year=ts.year - 1)
        if oldest is None or ts < oldest:
            oldest = ts
    if oldest is None:
        return None
    return format_age((now - oldest).total_seconds())


def compute_link_changes(text: str, physical_ifaces: list) -> dict:
    """Return {short-iface: display string} for the given physical interfaces.

    Empty dict when no logging block is present (feature not collected). Otherwise
    each physical iface gets a relative age, a 'stable ≥Xd' floor, or 'unknown'.
    """
    logging_present = bool(re.search(r'%[A-Z]+-\d-[A-Z]+:', text) or "Log Buffer" in text)
    if not logging_present:
        return {}

    now = parse_clock(text)
    out: dict[str, str] = {}
    if now is None:
        return {iface: "unknown" for iface in physical_ifaces}

    events = parse_updown_events(text, now.year, now)
    horizon = _buffer_horizon(text, now.year, now)
    for iface in physical_ifaces:
        if iface in events:
            delta = (now - events[iface]).total_seconds()
            out[iface] = format_age(delta) if delta >= 0 else "unknown"
        else:
            out[iface] = f"stable ≥{horizon}" if horizon else "unknown"
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test_interface_parser.py -k "updown or link_changes" -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add interface_parser.py test_interface_parser.py
git commit -m "feat: extract UPDOWN events and compute per-port last link change"
```

---

### Task 4: Wire link-change into `parse_output`

**Files:**
- Modify: `interface_parser.py` (`parse_output` post-processing loop)
- Test: `test_interface_parser.py`

**Interfaces:**
- Consumes: `compute_link_changes`, `is_physical_iface`
- Produces: `parse_output` sets `rec.last_link_change` for physical ports when logging text is present; leaves it `""` otherwise.

- [ ] **Step 1: Write the failing test**

Add to `test_interface_parser.py`:

```python
def test_parse_output_populates_last_link_change():
    from interface_parser import parse_output
    text = "\n".join([
        "GigabitEthernet1/0/5 is up, line protocol is up (connected)",
        "  Last input 00:00:01, output 00:00:00, output hang never",
        "Vlan10 is up, line protocol is up",
        "  Last input 00:00:02, output 00:00:00, output hang never",
        "*12:00:00.000 AEST Sun Jul 6 2026",
        "Log Buffer (16384 bytes):",
        "*Jul  6 09:47:00.000: %LINK-3-UPDOWN: Interface GigabitEthernet1/0/5, changed state to up",
    ])
    records, _ = parse_output(text, "sw-a")
    by_iface = {r.iface: r for r in records}
    assert by_iface["Gi1/0/5"].last_link_change == "2h13m"
    assert by_iface["Vlan10"].last_link_change == ""  # logical, left blank


def test_parse_output_no_logging_leaves_blank():
    from interface_parser import parse_output
    text = "\n".join([
        "GigabitEthernet1/0/5 is up, line protocol is up (connected)",
        "  Last input 00:00:01, output 00:00:00, output hang never",
    ])
    records, _ = parse_output(text, "sw-a")
    assert records[0].last_link_change == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest test_interface_parser.py -k "parse_output_populates or parse_output_no_logging" -v`
Expected: FAIL — `last_link_change` is `""` for Gi1/0/5 (not yet wired).

- [ ] **Step 3: Wire into `parse_output`**

In `interface_parser.py`, inside `parse_output`, after the `cdp_neighbors = parse_cdp_neighbors(text)` line and before the `for rec in int_data.values():` post-loop, add:

```python
    physical = [rec.iface for rec in int_data.values() if is_physical_iface(rec.iface)]
    link_changes = compute_link_changes(text, physical)
```

Then inside the existing `for rec in int_data.values():` loop, after the `if rec.iface in cdp_neighbors:` block, add:

```python
        if rec.iface in link_changes:
            rec.last_link_change = link_changes[rec.iface]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test_interface_parser.py -k "parse_output_populates or parse_output_no_logging" -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the full parser test file**

Run: `python3 -m pytest test_interface_parser.py -v`
Expected: PASS (all tests).

- [ ] **Step 6: Commit**

```bash
git add interface_parser.py test_interface_parser.py
git commit -m "feat: populate last_link_change in parse_output for physical ports"
```

---

### Task 5: Append the column in `write_excel_sheet`

**Files:**
- Modify: `excel_generator.py` (`write_excel_sheet`)
- Test: `test_excel_generator.py` (create)

**Interfaces:**
- Consumes: `InterfaceRecord.last_link_change`
- Produces: sheet gains a far-right "Last Link Change" column iff any record on the sheet has a non-empty `last_link_change`.

- [ ] **Step 1: Write the failing tests**

Create `test_excel_generator.py`:

```python
import openpyxl

from excel_generator import write_excel_sheet
from interface_parser import InterfaceRecord


def test_link_change_column_absent_when_no_values():
    wb = openpyxl.Workbook()
    ws = wb.active
    rec = InterfaceRecord(switch="sw-a", iface="Gi1/0/1", state="connected")
    write_excel_sheet(ws, [rec], {})
    headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
    assert "Last Link Change" not in headers


def test_link_change_column_present_and_populated():
    wb = openpyxl.Workbook()
    ws = wb.active
    rec = InterfaceRecord(
        switch="sw-a", iface="Gi1/0/1", state="connected", last_link_change="2h13m"
    )
    write_excel_sheet(ws, [rec], {})
    headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
    assert headers[-1] == "Last Link Change"
    last_col = ws.max_column
    assert ws.cell(row=2, column=last_col).value == "2h13m"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest test_excel_generator.py -v`
Expected: FAIL — the second test fails because the column is not appended.

- [ ] **Step 3: Implement the conditional column**

In `excel_generator.py`, at the top of `write_excel_sheet` (after the docstring, before writing headers), compute the effective headers/widths:

```python
    include_link_state = any(r.last_link_change for r in records)
    headers = HEADERS + (["Last Link Change"] if include_link_state else [])
    col_widths = COL_WIDTHS + ([18] if include_link_state else [])
```

Change the header-writing loop to use the local `headers`/`col_widths` instead of the module constants:

```python
    for col, (header, width) in enumerate(zip(headers, col_widths), start=1):
```

In the data-row loop, after building `values`, append the link-change value when included:

```python
        if include_link_state:
            values = values + [rec.last_link_change]
```

(Place this immediately after the existing `values = [ ... ]` list literal and before the `for col, value in enumerate(values, start=1):` loop.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest test_excel_generator.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run related suites to confirm no regressions**

Run: `python3 -m pytest test_excel_generator.py test_port_utilisation.py test_interface_parser.py -v`
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
git add excel_generator.py test_excel_generator.py
git commit -m "feat: append Last Link Change column to interface sheet when populated"
```

---

### Task 6: Command constant + menu toggle wiring

**Files:**
- Modify: `cheat_core.py` (add `LINK_STATE_COMMANDS`)
- Modify: `main_latest.py` (`menu_5` toggle, status line, extended command list)

**Interfaces:**
- Consumes: `DNAC_COMMANDS`, `LINK_STATE_COMMANDS`, `_exec_and_report`
- Produces: `cheat_core.LINK_STATE_COMMANDS = ["show logging", "show clock"]`

- [ ] **Step 1: Add the command constant + a testable command builder**

In `cheat_core.py`, after the `DNAC_COMMANDS` list, add:

```python
LINK_STATE_COMMANDS = ["show logging", "show clock"]


def build_command_list(link_state: bool) -> list:
    """Base report commands, plus link-state commands when enabled."""
    return DNAC_COMMANDS + LINK_STATE_COMMANDS if link_state else list(DNAC_COMMANDS)
```

- [ ] **Step 2: Write the failing test**

Create `test_cheat_core.py`:

```python
from cheat_core import build_command_list, DNAC_COMMANDS


def test_build_command_list_off_is_base():
    assert build_command_list(False) == DNAC_COMMANDS
    assert "show logging" not in build_command_list(False)


def test_build_command_list_on_adds_logging_and_clock():
    cmds = build_command_list(True)
    assert cmds[: len(DNAC_COMMANDS)] == DNAC_COMMANDS
    assert cmds[-2:] == ["show logging", "show clock"]
```

- [ ] **Step 3: Run test to verify it passes**

Run: `python3 -m pytest test_cheat_core.py -v`
Expected: PASS (2 tests). (Constant + builder already added in Step 1.)

- [ ] **Step 4: Wire the toggle into `menu_5`**

In `main_latest.py`, locate `menu_5`. Add a `link_state` state variable initialised alongside the existing `slow_mode` / `copper_only` locals (search for where `copper_only` is initialised in `menu_5` and add `link_state = False` next to it).

Update the status line (the `print(f"  Host: ... Copper only: {copper_label}\n")` line) to append a link-state label. Just before that print, add:

```python
        link_label = "on" if link_state else "off"
```

and extend the f-string with `  |  Link-state: {link_label}`.

Add the menu entry — after the `print("  p) Toggle copper only")` line:

```python
        print("  l) Toggle link-state column")
```

Add the toggle handler — after the `elif choice == "p":` block that flips `copper_only`, add:

```python
        elif choice == "l":
            link_state = not link_state
```

Update the report dispatch to pass the extended command list. Ensure `build_command_list` is imported from `cheat_core` (add to the existing `from cheat_core import (...)` block). Then in the `elif choice in ("1", "2"):` branch, replace the `DNAC_COMMANDS` argument to `_exec_and_report` with `build_command_list(link_state)`, and likewise in the `elif choice == "3":` branch replace `DNAC_COMMANDS` with `build_command_list(link_state)`.

- [ ] **Step 5: Verify the module imports and menu renders**

Run: `python3 -c "import main_latest; print('import OK')"`
Expected: `import OK` (no syntax/import errors).

Run: `python3 -m pytest test_cheat_core.py test_interface_parser.py test_excel_generator.py test_port_utilisation.py -v`
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
git add cheat_core.py main_latest.py test_cheat_core.py
git commit -m "feat: menu-5 link-state toggle appends show logging/show clock"
```

---

### Task 7: End-to-end verification

**Files:**
- Test: `test_excel_generator.py` (add end-to-end case)

**Interfaces:**
- Consumes: `parse_output`, `write_combined_excel`

- [ ] **Step 1: Write the end-to-end test**

Add to `test_excel_generator.py`:

```python
def test_end_to_end_link_change_flows_to_combined_workbook(tmp_path):
    from interface_parser import parse_output
    from excel_generator import write_combined_excel

    text = "\n".join([
        "GigabitEthernet1/0/5 is up, line protocol is up (connected)",
        "  Last input 00:00:01, output 00:00:00, output hang never",
        "*12:00:00.000 AEST Sun Jul 6 2026",
        "Log Buffer (16384 bytes):",
        "*Jul  6 09:47:00.000: %LINK-3-UPDOWN: Interface GigabitEthernet1/0/5, changed state to up",
    ])
    records, stack = parse_output(text, "hu-chi-f1-edge-01")
    devices = {"hu-chi-f1-edge-01": (records, stack)}

    out = tmp_path / "report.xlsx"
    ok, _ = write_combined_excel(devices, 42, str(out))
    assert ok

    import openpyxl
    wb = openpyxl.load_workbook(out)
    ws = wb["All Ports"]
    headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
    assert headers[-1] == "Last Link Change"
    assert ws.cell(row=2, column=ws.max_column).value == "2h13m"
```

- [ ] **Step 2: Run the test**

Run: `python3 -m pytest test_excel_generator.py::test_end_to_end_link_change_flows_to_combined_workbook -v`
Expected: PASS.

- [ ] **Step 3: Run the whole suite**

Run: `python3 -m pytest test_cheat_core.py test_interface_parser.py test_excel_generator.py test_port_utilisation.py test_ap_monitor.py test_ap_client.py -v`
Expected: PASS (all).

- [ ] **Step 4: Commit**

```bash
git add test_excel_generator.py
git commit -m "test: end-to-end last link change flows into combined workbook"
```

---

## Self-Review Notes

- **Spec coverage:** menu toggle (Task 6), `show logging`+`show clock` commands (Task 6), UPDOWN parse + most-recent-per-iface + year rollover (Task 3), clock anchoring (Task 2/3), relative-time format A (Task 2), physical-only scope (Task 1/4), `stable ≥Xd` floor and `unknown` fallback (Task 3), far-right column + auto-appears when populated (Task 5), flows to per-device and All Ports sheets (Task 7), excluded from Port Utilisation tab (never touched). All covered.
- **Deviation from spec (intentional, behaviour-equivalent):** the spec described threading an `include_link_state` flag through `write_excel_sheet`. The plan instead makes the column auto-appear when any record on the sheet carries a value. Observable behaviour is identical (toggle off → no logging collected → no values → no column) with less plumbing. Noted here for the reviewer.
- **Type consistency:** `compute_link_changes(text, physical_ifaces) -> dict[str,str]`, `parse_updown_events(text, ref_year, now) -> dict[str,datetime]`, `parse_clock -> Optional[datetime]`, `format_age(seconds) -> str`, `is_physical_iface(iface) -> bool` used consistently across tasks.
