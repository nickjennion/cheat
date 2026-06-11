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
from typing import Optional


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
    counters_in: str = ""
    suspect: str = ""


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
    r'\b(connected|notconnect|disabled|err-disabled|inactive|sfpAbsent|xcvrAbsent)\s+(\S+)',
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


def member_from_iface(iface: str) -> str:
    """Extract stack member number from interface name (e.g., Gi1/0/5 -> '1')."""
    m = re.match(r'[A-Za-z]+(\d+)/', iface)
    return m.group(1) if m else ""


def uptime_days(uptime_str: str) -> Optional[float]:
    """Convert uptime string to approximate days for highlighting."""
    if not uptime_str:
        return None
    total = 0.0
    for val, unit in re.findall(r'(\d+)\s+(week|day|hour|minute)', uptime_str, re.I):
        v = int(val)
        if "week" in unit:
            total += v * 7
        elif "day" in unit:
            total += v
        elif "hour" in unit:
            total += v / 24
    return total if total > 0 else None


def parse_status_row(line: str):
    """Parse a single line from 'show interfaces status'."""
    m = RE_STATUS_PORT.match(line)
    if not m:
        return None
    port = m.group(1)
    m2 = RE_STATUS_FIND.search(line)
    if not m2:
        return None
    return port, m2.group(1).lower(), m2.group(2)


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
                short, status, vlan = result
                if short not in int_data:
                    int_data[short] = InterfaceRecord(switch=hostname, iface=short)
                int_data[short].state = status
                int_data[short].vlan = vlan
            continue

        if in_show_counters:
            m = RE_COUNTERS_ROW.match(s)
            if m:
                short = m.group(1)
                if short not in int_data:
                    int_data[short] = InterfaceRecord(switch=hostname, iface=short)
                int_data[short].counters_in = m.group(2)
            continue

    for rec in int_data.values():
        member_str = member_from_iface(rec.iface)
        rec.stack_member = member_str

        if member_str and stack_members:
            try:
                mn = int(member_str)
                if mn in stack_members:
                    sm = stack_members[mn]
                    rec.model = sm.model
                    rec.uptime = sm.uptime
                    rec.sw_version = sm.sw_version
            except ValueError:
                pass

        rec.suspect = "NO" if (not rec.last_input or rec.last_input.lower() == "never") else "YES"

    def sort_key(rec):
        parts = re.findall(r'\d+', rec.iface)
        prefix = re.match(r'[A-Za-z]+', rec.iface)
        return (prefix.group() if prefix else "", [int(x) for x in parts])

    return sorted(int_data.values(), key=sort_key), stack_members
