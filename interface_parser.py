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

# CDP local interface: abbreviated type ("Ten", "Gig", "Fas"...) + space + slot/port.
# Matches both multi-part (Ten 2/1/4) and single digit (Gig 0) port formats.
# The local interface is always the first such match on a data line.
RE_CDP_LOCAL_IFACE = re.compile(r'\b([A-Za-z]{2,4})\s+(\d+(?:/\d+)*)')

# Neighbor Port ID sits at the very end of a CDP line. It is usually a Cisco
# interface ("Gig 0", "Ten 2/1/19") but on non-Cisco neighbours can be anything
# the device reports ("Port 1" on IP phones, "eth0" on AV/room gear). Capture
# the trailing "<word> <slot/port>" form, falling back to a single bare token.
RE_CDP_PORT_ID = re.compile(r'([A-Za-z][\w-]*)\s+(\d+(?:/\d+)*)\s*$')

# Cisco interface-type abbreviations that should be normalised to short form
# (Gig -> Gi0). Anything not in this set (Port, eth, Room...) is kept verbatim.
CDP_CISCO_TYPES = {
    "te", "ten", "gi", "gig", "fa", "fas", "fo", "for", "fou",
    "hu", "hun", "tw", "two", "fi", "fiv", "et", "eth",
}


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


def member_from_iface(iface: str) -> str:
    """Extract stack member number from interface name (e.g., Gi1/0/5 -> '1')."""
    m = re.match(r'[A-Za-z]+(\d+)/', iface)
    return m.group(1) if m else ""


def uptime_days(uptime_str: str) -> Optional[float]:
    """Convert uptime string to approximate days for highlighting."""
    return parse_duration_days(uptime_str)


def extract_neighbor_port(stripped_line: str) -> str:
    """Extract the neighbor's Port ID (last field) from a CDP data line.

    Cisco interfaces are normalised to short form (Gig 0 -> Gi0); non-Cisco
    port IDs (Port 1, eth0, ...) are preserved exactly as reported.
    """
    m = RE_CDP_PORT_ID.search(stripped_line)
    if m:
        word, num = m.group(1), m.group(2)
        if word.lower() in CDP_CISCO_TYPES:
            return word[:2].capitalize() + num
        return f"{word} {num}"
    # Single bare token at end of line, e.g. "eth0".
    tokens = stripped_line.split()
    return tokens[-1] if tokens else ""


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
    """Parse 'show cdp neighbors' output into {interface: "neighbor_device (neighbor_port)"}.

    Cisco CDP output puts the local interface in the second column. When the
    Device ID is long it wraps onto its own line and the interface appears,
    indented, on the following line:

        Device ID        Local Intrfce     Holdtme  Capability  Platform  Port ID
        long-device-name.example.net
                         Ten 2/1/4         163      R S I       WS-C4500X Ten 2/1/9
        short-dev        Ten 1/0/46        166      R T         AIR-AP380 Gig 0

    Interface types are abbreviated (Ten, Gig, Fas...) and space-separated from
    the slot/port, so they are normalised to the same short form used elsewhere
    (Te2/1/4, Gi1/0/46) so they match the interface records.

    The Port ID (last field) is appended in parentheses: "device (port)".
    For multiple neighbors on one interface: "device1 (port1), device2 (port2)".
    """
    neighbors: dict[str, str] = {}
    in_table = False
    pending_device: Optional[str] = None

    for raw in text.split('\n'):
        line = raw.rstrip()

        if not in_table:
            if 'Device ID' in line and ('Local Intrfce' in line or 'Local Interface' in line):
                in_table = True
            continue

        stripped = line.strip()

        if not stripped:
            continue

        # End of CDP output: device prompt, next command, or another section header.
        if (stripped.endswith('#') or stripped.endswith('>')
                or stripped.lower().startswith('show ')
                or RE_COUNTERS_HEADER.match(stripped)
                or RE_STATUS_HEADER.match(stripped)):
            in_table = False
            pending_device = None
            continue

        # A repeated CDP header (rare) — skip it.
        if 'Device ID' in line and ('Local Intrfce' in line or 'Local Interface' in line):
            continue

        indented = line[0].isspace()
        local_match = RE_CDP_LOCAL_IFACE.search(line)

        if local_match:
            # First two letters of the CDP abbreviation == Cisco short form
            # (Ten->Te, Gig->Gi, Fas->Fa, Fou->Fo, Hun->Hu, Two->Tw).
            local_iface = local_match.group(1)[:2].capitalize() + local_match.group(2)

            # Neighbor Port ID is the trailing field; normalise only if Cisco.
            neighbor_port = extract_neighbor_port(stripped)
            # Guard against a single-neighbour line where the only interface
            # token is the local one (no separate Port ID parsed).
            if neighbor_port == local_iface:
                neighbor_port = ""

            device = pending_device if indented else stripped.split()[0]

            pending_device = None
            if device:
                if neighbor_port:
                    neighbor_entry = f"{device} ({neighbor_port})"
                else:
                    neighbor_entry = device
                if local_iface in neighbors:
                    neighbors[local_iface] += f", {neighbor_entry}"
                else:
                    neighbors[local_iface] = neighbor_entry
        elif not indented:
            # Non-indented line with no interface: a Device ID that wraps to
            # the next line.
            pending_device = stripped.split()[0]

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

        if rec.iface in cdp_neighbors:
            rec.cdp_neighbors = cdp_neighbors[rec.iface]

    def sort_key(rec):
        parts = re.findall(r'\d+', rec.iface)
        prefix = re.match(r'[A-Za-z]+', rec.iface)
        return (prefix.group() if prefix else "", [int(x) for x in parts])

    return sorted(int_data.values(), key=sort_key), stack_members
