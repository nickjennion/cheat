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

from dataclasses import dataclass, field, replace

from mac_table import parse_mac_address_table, MacTableEntry
from cdp_detail import parse_cdp_detail, is_switch, classify_neighbor

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
    device_type: str = ""
    notes: str = ""


@dataclass
class AvMacReport:
    vlan_stacks: dict
    rows: list
    vlan_counts: dict = field(default_factory=dict)


def _uplink_interfaces(text: str) -> set:
    """Local interfaces on this switch whose CDP neighbour is a switch/router."""
    return {nb.local_iface for nb in parse_cdp_detail(text) if is_switch(nb)}


def _neighbour_by_interface(text: str) -> dict:
    """Local interface -> CdpNeighbor, for device-type labelling of survivors."""
    return {nb.local_iface: nb for nb in parse_cdp_detail(text)}


def build_av_mac_report(raw_outputs: dict, vlans: list) -> AvMacReport:
    """Correlate per-switch MAC-table + CDP output into a flagged AV MAC/port report.

    raw_outputs maps hostname -> combined raw output containing both
    `show mac address-table` and `show cdp neighbors detail`. vlans is a
    list of requested VLAN-ID strings.
    """
    wanted = {str(v).strip() for v in vlans}
    vlan_stacks = {v: set() for v in wanted}
    vlan_counts = {v: 0 for v in wanted}
    surviving: list[MacTableEntry] = []

    for host, text in raw_outputs.items():
        entries = [e for e in parse_mac_address_table(text) if e.vlan in wanted]
        if not entries:
            continue
        uplinks = _uplink_interfaces(text)
        neighbours = _neighbour_by_interface(text)
        for e in entries:
            vlan_stacks[e.vlan].add(host)
            if e.interface in uplinks:
                continue
            vlan_counts[e.vlan] += 1
            surviving.append(replace(e, switch=host))

    port_macs: dict = {}
    for e in surviving:
        port_macs.setdefault((e.switch, e.interface), set()).add(e.mac)

    mac_ports: dict = {}
    for e in surviving:
        mac_ports.setdefault(e.mac, set()).add((e.switch, e.interface))

    # Device-type label from the CDP neighbour on the surviving port (if any).
    device_types: dict = {}
    for host, text in raw_outputs.items():
        for iface, nb in _neighbour_by_interface(text).items():
            device_types[(host, iface)] = classify_neighbor(nb)

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
            device_type=device_types.get((e.switch, e.interface), ""),
            notes="; ".join(notes),
        ))

    rows.sort(key=lambda r: (r.switch, r.interface, r.mac))
    return AvMacReport(
        vlan_stacks={v: sorted(hosts) for v, hosts in vlan_stacks.items()},
        rows=rows,
        vlan_counts=vlan_counts,
    )
