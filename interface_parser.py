"""
Interface parsing module for CHEAT UNPLUGGED.

Parses concatenated command output from:
  - show hardware
  - show interfaces
  - show interfaces status
  - show interface counters

Returns structured InterfaceRecord and StackMember data.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from time_utils import parse_duration_days


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class StackMember:
    member_num: int = 0
    model: str = ""
    uptime: str = ""
    sw_version: str = ""
    is_active: bool = False


@dataclass
class InterfaceRecord:
    switch: str = ""
    stack_member: str = ""
    model: str = ""
    uptime: str = ""
    sw_version: str = ""
    iface: str = ""
    description: str = ""
    state: str = ""
    protocol: str = ""
    last_input: str = ""
    vlan: str = ""
    speed: str = ""
    if_type: str = ""
    counters_in: str = ""
    suspect: str = ""
    cdp_neighbors: str = ""
    last_link_change: str = ""


# ============================================================================
# Regex Patterns
# ============================================================================

RE_IFACE_HEADER = re.compile(
    r'^((?:GigabitEthernet|TenGigabitEthernet|FastEthernet|'
    r'FortyGigabitEthernet|HundredGigE)\S+)\s+is\s+(\S+(?:\s+\S+)?),\s*'
    r'line protocol is\s+(\S+)',
    re.IGNORECASE
)
RE_DESCRIPTION = re.compile(r'^\s+Description:\s+(.*)', re.IGNORECASE)
RE_LAST_INPUT = re.compile(r'^\s+Last input\s+(\S+),', re.IGNORECASE)
RE_STATUS_HEADER = re.compile(r'^Port\s+Name\s+Status\s+Vlan', re.IGNORECASE)
RE_STATUS_PORT = re.compile(r'^((?:Gi|Te|Fa|Fo|Hu|Po)\d+(?:/\d+){1,3})\s+', re.IGNORECASE)
RE_STATUS_FIND = re.compile(
    r'\b(connected|notconnect|disabled|err-disabled|inactive|sfpAbsent|xcvrAbsent)'
    r'\s+(\S+)'              # vlan
    r'(?:\s+(\S+)'          # duplex (optional)
    r'\s+(\S+)'             # speed (optional)
    r'\s+(\S+))?',          # type (optional)
    re.IGNORECASE
)
RE_COUNTERS_HEADER = re.compile(r'^Port\s+InOctets', re.IGNORECASE)
RE_COUNTERS_ROW = re.compile(
    r'^((?:Gi|Te|Fa|Fo|Hu)\d+/\d+/\d+(?:/\d+)?)\s+(\d+)',
    re.IGNORECASE
)
RE_STACK_TABLE_ROW = re.compile(
    r'^(\*?)\s+(\d+)\s+\d+\s+'
    r'(WS-\S+|C\d+\S*|\S+-\S+)\s+'
    r'(\S+)\s+',
    re.IGNORECASE
)
RE_SWITCH_SECTION = re.compile(r'^Switch\s+0*(\d+)\s*$', re.IGNORECASE)
RE_SWITCH_UPTIME = re.compile(r'Switch\s+uptime\s*:\s*(.+)', re.IGNORECASE)
RE_HOSTNAME_UPTIME = re.compile(r'^\S+\s+uptime\s+is\s+(.+)', re.IGNORECASE)
RE_MODEL_NUMBER = re.compile(r'Model Number\s*:\s*(\S+)', re.IGNORECASE)
RE_SHOW_HW_TRIGGER = re.compile(r'show\s+(hardware|version)', re.IGNORECASE)

RE_CLOCK = re.compile(
    r'[*.]?(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?\s+\w+\s+\w{3}\s+'
    r'(\w{3})\s+(\d{1,2})\s+(\d{4})'
)

RE_UPDOWN = re.compile(
    r'(?P<ts>\w{3}\s+\d{1,2}\s+(?:\d{4}\s+)?\d{2}:\d{2}:\d{2}(?:\.\d+)?)'
    r'.*?%(?:LINK|LINEPROTO)-\d-UPDOWN:.*?'
    r'Interface\s+(?P<iface>[A-Za-z0-9/.-]+),\s+changed state to (?:up|down)'
)

RE_SYSLOG_TS = re.compile(
    r'(?<![\d:])(\w{3}\s+\d{1,2}\s+(?:\d{4}\s+)?\d{2}:\d{2}:\d{2}(?:\.\d+)?)'
    r'(?:\s+\w+)?\s*:'   # optional timezone token (AEST, UTC, ...) from show-timezone
)

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Physical Ethernet port: an alpha type followed by slot/port (Gi1/0/5, Fa0/1).
# Logical interfaces (Vlan10, Po1, Lo0, Tunnel1) lack the slot/port and miss.
RE_PHYSICAL_IFACE = re.compile(r'^[A-Za-z]{2,}\d+/\d+')


# ============================================================================
# Helper Functions
# ============================================================================

def shorten_iface(name: str) -> str:
    """Convert long interface name to short form."""
    for long, short in [
        ("TenGigabitEthernet", "Te"),
        ("GigabitEthernet", "Gi"),
        ("FastEthernet", "Fa"),
        ("FortyGigabitEthernet", "Fo"),
        ("HundredGigE", "Hu"),
    ]:
        if name.lower().startswith(long.lower()):
            return short + name[len(long):]
    return name


def site_location(hostname: str) -> tuple[str, str]:
    """Split a hostname into (site, location) codes.

    Site is the text before the first hyphen; location is the text between the
    first and second hyphens. Both are "" when the segment is absent.
    Example: "hu-chi-f1-edge-01" -> ("hu", "chi").
    """
    parts = hostname.split("-")
    site = parts[0] if len(parts) >= 1 else ""
    location = parts[1] if len(parts) >= 2 else ""
    return site, location


def is_physical_iface(iface: str) -> bool:
    """True for physical Ethernet ports (slot/port notation), e.g. Gi1/0/5, Fa0/1.

    Logical interfaces (Vlan, Port-channel, Loopback, Tunnel) have no slot/port
    and return False.
    """
    return bool(RE_PHYSICAL_IFACE.match(iface or ""))


def member_from_iface(iface: str) -> str:
    """Extract stack member number from interface name (e.g., Gi1/0/5 -> '1')."""
    m = re.match(r'[A-Za-z]+(\d+)/', iface)
    return m.group(1) if m else ""


def uptime_days(uptime_str: str) -> Optional[float]:
    """Convert uptime string to approximate days for highlighting."""
    return parse_duration_days(uptime_str)


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
    # Underscore mnemonics (e.g. %SYS-5-CONFIG_I) need [A-Z_] to be detected.
    logging_present = bool(re.search(r'%[A-Z]+-\d-[A-Z_]+:', text) or "Log Buffer" in text)
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


def parse_status_row(line: str):
    """Parse a single line from 'show interfaces status'."""
    m = RE_STATUS_PORT.match(line)
    if not m:
        return None
    port = m.group(1)
    m2 = RE_STATUS_FIND.search(line)
    if not m2:
        return None
    return (
        port,
        m2.group(1).lower(),  # status
        m2.group(2),          # vlan
        m2.group(4) or "",    # speed (group 3 is duplex, skip)
        m2.group(5) or "",    # type
    )


# ============================================================================
# Main Parsing Functions
# ============================================================================

def parse_hardware(lines: list[str]) -> dict[int, StackMember]:
    """Parse 'show hardware' output and extract stack member info."""
    members: dict[int, StackMember] = {}
    in_hw = False
    in_stack_table = False
    current_member: Optional[int] = None

    for line in lines:
        s = line.rstrip()

        if RE_SHOW_HW_TRIGGER.search(s):
            in_hw = True
            in_stack_table = False
            current_member = None
            continue

        if not in_hw:
            continue

        m = RE_SWITCH_SECTION.match(s)
        if m:
            current_member = int(m.group(1))
            in_stack_table = False
            if current_member not in members:
                members[current_member] = StackMember(member_num=current_member)
            continue

        if current_member is not None:
            if re.match(r'^-{4,}', s):
                continue

            m = RE_SWITCH_UPTIME.search(s)
            if m:
                members[current_member].uptime = m.group(1).strip()
                continue

            m = RE_MODEL_NUMBER.search(s)
            if m:
                if not members[current_member].model:
                    members[current_member].model = m.group(1).strip()
                continue

            if RE_SHOW_HW_TRIGGER.search(s):
                current_member = None
                in_hw = False
            continue

        if re.match(r'^-{4,}', s) and in_hw:
            in_stack_table = True
            continue

        m = RE_HOSTNAME_UPTIME.match(s)
        if m and in_hw and not in_stack_table:
            if 1 not in members:
                members[1] = StackMember(member_num=1)
            if not members[1].uptime:
                members[1].uptime = m.group(1).strip()
            continue

        if in_stack_table:
            m = RE_STACK_TABLE_ROW.match(s)
            if m:
                is_active = m.group(1) == "*"
                member_num = int(m.group(2))
                model = m.group(3)
                sw_ver = m.group(4)
                if member_num not in members:
                    members[member_num] = StackMember(member_num=member_num)
                members[member_num].model = model
                members[member_num].sw_version = sw_ver
                members[member_num].is_active = is_active
                continue
            if not s.strip():
                in_stack_table = False
            continue

    return members


def parse_cdp_neighbors(text: str) -> dict[str, str]:
    """Map local interface -> "device [platform] (port) ip" for every CDP neighbour.

    Built from `show cdp neighbors detail`. The platform (e.g. "IP Phone 8845")
    identifies what a SEP<MAC> phone actually is; omitted when CDP didn't report
    one. Multiple neighbours on one interface are comma-joined. The management
    IP is appended when known. Imported here (not at module top) to avoid a
    cdp_detail <-> interface_parser import cycle.
    """
    from cdp_detail import parse_cdp_detail

    neighbors: dict[str, str] = {}
    for nb in parse_cdp_detail(text):
        if not nb.local_iface:
            continue
        entry = nb.device
        if nb.platform:
            entry += f" [{nb.platform}]"
        if nb.remote_port:
            entry += f" ({nb.remote_port})"
        if nb.mgmt_ip:
            entry += f" {nb.mgmt_ip}"
        if nb.local_iface in neighbors:
            neighbors[nb.local_iface] += f", {entry}"
        else:
            neighbors[nb.local_iface] = entry
    return neighbors



def parse_output(text: str, hostname: str) -> tuple[list[InterfaceRecord], dict[int, StackMember]]:
    """Parse concatenated command output and return interface records."""
    lines = text.split('\n')
    stack_members = parse_hardware(lines)

    int_data: dict[str, InterfaceRecord] = {}
    current_iface: Optional[str] = None
    in_show_interfaces = False
    in_show_status = False
    in_show_counters = False

    for line in lines:
        s = line.rstrip()

        if RE_STATUS_HEADER.match(s):
            in_show_status = True
            in_show_interfaces = False
            in_show_counters = False
            current_iface = None
            continue

        if RE_COUNTERS_HEADER.match(s):
            in_show_counters = True
            in_show_status = False
            in_show_interfaces = False
            current_iface = None
            continue

        m = RE_IFACE_HEADER.match(s)
        if m:
            in_show_interfaces = True
            in_show_status = False
            in_show_counters = False

            full_name = m.group(1)
            hw_state = m.group(2).strip()
            proto = m.group(3).strip()
            short = shorten_iface(full_name)
            current_iface = short

            if short not in int_data:
                int_data[short] = InterfaceRecord()

            rec = int_data[short]
            rec.switch = hostname
            rec.iface = short

            if "administratively" in hw_state.lower():
                rec.state = "disabled"
            elif hw_state.lower() == "up":
                rec.state = "connected"
            else:
                rec.state = hw_state.lower()

            rec.protocol = proto.lower().split()[0]
            continue

        if in_show_interfaces and current_iface:
            m = RE_DESCRIPTION.match(s)
            if m:
                int_data[current_iface].description = m.group(1).strip()
                continue

            m = RE_LAST_INPUT.match(s)
            if m:
                int_data[current_iface].last_input = m.group(1).strip()
                continue

        if in_show_status:
            result = parse_status_row(s)
            if result:
                short, status, vlan, speed, if_type = result
                if short not in int_data:
                    int_data[short] = InterfaceRecord(switch=hostname, iface=short)
                int_data[short].state = status
                int_data[short].vlan = vlan
                int_data[short].speed = speed
                int_data[short].if_type = if_type
            continue

        if in_show_counters:
            m = RE_COUNTERS_ROW.match(s)
            if m:
                short = m.group(1)
                if short not in int_data:
                    int_data[short] = InterfaceRecord(switch=hostname, iface=short)
                int_data[short].counters_in = m.group(2)
            continue

    cdp_neighbors = parse_cdp_neighbors(text)

    physical = [rec.iface for rec in int_data.values() if is_physical_iface(rec.iface)]
    link_changes = compute_link_changes(text, physical)

    for rec in int_data.values():
        member_str = member_from_iface(rec.iface)
        rec.stack_member = member_str

        if member_str and stack_members:
            try:
                mn = int(member_str)
                sm = stack_members.get(mn)
                # Fixed (non-stacking) switches — 3560/2960 — number their ports
                # from slot 0 (Gi0/1 -> member "0") but report the unit as member
                # 1 in the version stack table. When the derived member isn't in
                # the table and there is only one member, fall back to it.
                if sm is None and len(stack_members) == 1:
                    sm = next(iter(stack_members.values()))
                if sm is not None:
                    rec.model = sm.model
                    rec.uptime = sm.uptime
                    rec.sw_version = sm.sw_version
            except ValueError:
                pass

        rec.suspect = "NO" if (not rec.last_input or rec.last_input.lower() == "never") else "YES"

        if rec.iface in cdp_neighbors:
            rec.cdp_neighbors = cdp_neighbors[rec.iface]

        if rec.iface in link_changes:
            rec.last_link_change = link_changes[rec.iface]

    def sort_key(rec):
        parts = re.findall(r'\d+', rec.iface)
        prefix = re.match(r'[A-Za-z]+', rec.iface)
        return (prefix.group() if prefix else "", [int(x) for x in parts])

    return sorted(int_data.values(), key=sort_key), stack_members
