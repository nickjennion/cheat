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
