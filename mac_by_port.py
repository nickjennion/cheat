"""
Correlate `show mac address-table` + `show cdp neighbors detail` into a
per-port listing of every MAC on every VLAN, including child switches.

Unlike av_mac_report (which collapses hierarchy by dropping switch/router
uplinks so the same AV MAC is listed once), this report KEEPS every entry and
labels each port's CDP neighbour. An uplink port to a child switch therefore
appears in the output with the child's device name — the MACs learned beyond it
stay visible, grouped under that port. Device type (IP phone, access point,
switch/router, ...) is derived from the CDP neighbour on each port.

Pure parsing/correlation — no IO, no VLAN filtering (all VLANs are included).
"""

from dataclasses import dataclass, field, replace

from mac_table import parse_mac_address_table, MacTableEntry
from cdp_detail import parse_cdp_detail, classify_neighbor

MULTI_MAC_NOTE = "Multiple MACs — possible unmanaged switch"
AMBIGUOUS_NOTE = "Ambiguous — seen on multiple switches"


@dataclass
class MacByPortRow:
    switch: str
    stack_member: str
    interface: str
    vlan: str
    mac: str
    type: str
    device_type: str = ""
    neighbour: str = ""
    notes: str = ""


@dataclass
class MacByPortReport:
    vlan_stacks: dict            # vlan -> sorted switches carrying it
    vlan_counts: dict            # vlan -> total entries (across all switches)
    rows: list
    uplink_rows: int = 0         # entries on ports whose neighbour is a switch/router


def _neighbour_by_interface(text: str) -> dict:
    """Local interface -> CdpNeighbor from one switch's combined output."""
    return {nb.local_iface: nb for nb in parse_cdp_detail(text)}


def _neighbour_label(nb) -> str:
    """Compact '<device> (<remote port>)' for the report's neighbour column."""
    if nb is None:
        return ""
    label = nb.device
    if nb.remote_port:
        label += f" ({nb.remote_port})"
    return label


def build_mac_by_port_report(raw_outputs: dict) -> MacByPortReport:
    """List every MAC (all VLANs) from every selected switch, grouped by port.

    raw_outputs maps hostname -> combined `show mac address-table` +
    `show cdp neighbors detail` output. Uplinks to child switches are kept,
    labelled with the child's device name, so MACs learned beyond them remain
    visible. No VLAN filter is applied — the full MAC table is reported.
    """
    vlan_stacks: dict = {}
    vlan_counts: dict = {}
    entries: list[MacTableEntry] = []
    neighbours: dict = {}   # (host, iface) -> CdpNeighbor

    for host, text in raw_outputs.items():
        for nb in _neighbour_by_interface(text).items():
            neighbours[(host, nb[0])] = nb[1]
        for e in parse_mac_address_table(text):
            vlan_stacks.setdefault(e.vlan, set()).add(host)
            vlan_counts[e.vlan] = vlan_counts.get(e.vlan, 0) + 1
            entries.append(replace(e, switch=host))

    port_macs: dict = {}
    for e in entries:
        port_macs.setdefault((e.switch, e.interface), set()).add(e.mac)

    mac_switches: dict = {}
    for e in entries:
        mac_switches.setdefault(e.mac, set()).add((e.switch, e.interface))

    rows = []
    uplink_rows = 0
    for e in entries:
        nb = neighbours.get((e.switch, e.interface))
        device_type = classify_neighbor(nb) if nb else ""
        if device_type == "Switch/router":
            uplink_rows += 1
        notes = []
        if len(port_macs[(e.switch, e.interface)]) > 1:
            notes.append(MULTI_MAC_NOTE)
        if len(mac_switches[e.mac]) > 1:
            notes.append(AMBIGUOUS_NOTE)
        rows.append(MacByPortRow(
            switch=e.switch,
            stack_member=e.stack_member,
            interface=e.interface,
            vlan=e.vlan,
            mac=e.mac,
            type=e.type,
            device_type=device_type,
            neighbour=_neighbour_label(nb),
            notes="; ".join(notes),
        ))

    rows.sort(key=lambda r: (r.switch, r.interface, r.vlan, r.mac))
    return MacByPortReport(
        vlan_stacks={v: sorted(hosts) for v, hosts in vlan_stacks.items()},
        vlan_counts=vlan_counts,
        rows=rows,
        uplink_rows=uplink_rows,
    )
