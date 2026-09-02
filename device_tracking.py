"""
Parse `show device-tracking database` output into IP/MAC binding records.

The SISF binding table on Catalyst 9000-class IOS-XE carries IP, MAC, interface,
VLAN and reachability state on one line — the layer-3 view `show mac
address-table` cannot give.

Pure parsing — no VLAN filtering, no switch-hostname knowledge, no IO. Those
belong to the caller (ip_mac_report.py), same split as mac_table.py vs
av_mac_report.py.
"""

import re
from dataclasses import dataclass

from interface_parser import member_from_iface

# Binding codes IOS-XE prints in the first column. L (the switch's own address)
# and S (statically configured) describe the switch, not an attached device.
LOCAL_CODES = frozenset({"L", "S"})

# A binding row must open with a code token AND carry a dotted-triplet MAC. That
# pair of anchors is what excludes the "Codes:" legend, the "Preflevel flags"
# block and the column header — none of them can satisfy both.
_RE_ROW = re.compile(
    r"(?im)^\s*(?P<code>L|S|ND|ARP|DH4|DH6|PKT|API)\s+"
    r"(?P<addr>\S+)\s+"
    r"(?P<mac>[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})\s+"
    r"(?P<iface>\S+)\s+"
    # The vlan column is captured loosely, not as \d+: on IOS-XE it is the
    # numeric VLAN ID (what the report filters on), but parsing it opaquely means
    # an unexpected token still yields a row, so a mismatch shows up as "no
    # bindings in the requested VLANs" instead of an unexplained empty report.
    r"(?P<vlan>\S+)"
    # Some Command Runner terminal widths wrap the remaining columns onto a
    # second line.  IP/MAC/interface/VLAN are still a valid client binding, so
    # keep prlvl/age/state optional instead of discarding the whole first line.
    r"(?:\s+(?P<prlvl>\S+))?"
    r"(?:\s+(?P<age>\S+))?"
    r"(?:\s+(?P<state>REACHABLE|STALE|VERIFY|DOWN|INCOMPLETE|PENDING))?"
    # The optional "Time left" tail is matched but not captured.
    r".*$"
)

_RE_IPV4 = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")

_RE_UNSUPPORTED = re.compile(
    r"%\s*(?:Invalid input|Incomplete command|Unrecognized|Ambiguous command)",
    re.IGNORECASE,
)


@dataclass
class DeviceTrackingEntry:
    switch: str = ""
    code: str = ""
    ip: str = ""
    mac: str = ""
    interface: str = ""
    vlan: str = ""
    prlvl: str = ""
    age: str = ""
    state: str = ""
    stack_member: str = ""


def command_unsupported(text: str) -> bool:
    """True when the device rejected the command (pre-SISF platform)."""
    return bool(_RE_UNSUPPORTED.search(text))


def parse_device_tracking(text: str) -> tuple[list[DeviceTrackingEntry], int]:
    """Parse the binding table into records.

    Returns (entries, non_ipv4_count). Every recognised row is returned —
    including LOCAL_CODES rows — so the caller decides what to drop. IPv6
    bindings (ND/DH6) are counted rather than returned, letting the report state
    how many were skipped instead of losing them silently.

    MAC addresses are lower-cased so cross-switch comparisons in ip_mac_report
    aren't broken by platform casing differences.
    """
    out: list[DeviceTrackingEntry] = []
    non_ipv4 = 0
    for m in _RE_ROW.finditer(text):
        addr = m.group("addr")
        if not _RE_IPV4.match(addr):
            non_ipv4 += 1
            continue
        iface = m.group("iface")
        out.append(DeviceTrackingEntry(
            code=m.group("code").upper(),
            ip=addr,
            mac=m.group("mac").lower(),
            interface=iface,
            vlan=m.group("vlan"),
            prlvl=m.group("prlvl") or "",
            age=m.group("age") or "",
            state=m.group("state") or "",
            stack_member=member_from_iface(iface),
        ))
    return out, non_ipv4
