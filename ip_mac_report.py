"""
Correlate `show device-tracking database` output across a nominated group of
switches into a per-VLAN IP/MAC inventory.

Answers "which devices are in this VLAN and what addresses do they hold" — the
layer-3 companion to av_mac_report's "which port is this MAC on".

Rows describing the switch itself (codes L and S) are dropped and counted, so a
switch's own SVI address never appears as a device. Nothing else is collapsed:
an IP held by more than one MAC, or a MAC seen on more than one switch, is
flagged in the output rather than resolved by guesswork.
"""

from dataclasses import dataclass, field, replace

from device_tracking import (
    LOCAL_CODES,
    command_unsupported,
    parse_device_tracking,
)

DUPLICATE_IP_NOTE = "Duplicate IP — held by {n} MACs"
MULTI_SWITCH_NOTE = "Seen on multiple switches"


@dataclass
class IpMacRow:
    switch: str
    stack_member: str
    interface: str
    vlan: str
    ip: str
    mac: str
    state: str
    age: str
    notes: str = ""


@dataclass
class IpMacReport:
    vlan_switches: dict            # vlan -> sorted switches yielding an endpoint
    rows: list
    excluded_local: int = 0        # L/S rows dropped, within the requested VLANs
    non_ipv4: int = 0              # IPv6 bindings skipped by the parser
    unsupported: list = field(default_factory=list)   # rejected the command
    no_bindings: list = field(default_factory=list)   # ran it, no endpoints


def _ip_sort_key(ip: str) -> tuple:
    """Octet tuple so 10.0.5.9 sorts before 10.0.5.10, not after it."""
    try:
        return tuple(int(p) for p in ip.split("."))
    except ValueError:
        return (0, 0, 0, 0)


def build_ip_mac_report(raw_outputs: dict, vlans: list) -> IpMacReport:
    """Correlate per-switch device-tracking output into the IP/MAC per VLAN report.

    raw_outputs maps hostname -> raw `show device-tracking database` output.
    vlans is a list of requested VLAN-ID strings, matched against the binding
    table's vlan column.
    """
    wanted = {str(v).strip() for v in vlans}
    vlan_switches = {v: set() for v in wanted}
    surviving = []
    excluded_local = 0
    non_ipv4 = 0
    unsupported: list = []
    no_bindings: list = []

    for host, text in raw_outputs.items():
        if command_unsupported(text):
            unsupported.append(host)
            continue

        entries, skipped = parse_device_tracking(text)
        non_ipv4 += skipped

        kept = 0
        for e in entries:
            if e.vlan not in wanted:
                continue
            if e.code in LOCAL_CODES:
                excluded_local += 1
                continue
            vlan_switches[e.vlan].add(host)
            surviving.append(replace(e, switch=host))
            kept += 1

        if not kept:
            no_bindings.append(host)

    # Flags are computed over surviving endpoints only — after the L/S drop — so
    # a switch's own SVI address can never read as an address conflict.
    ip_macs: dict = {}
    mac_places: dict = {}
    for e in surviving:
        ip_macs.setdefault(e.ip, set()).add(e.mac)
        mac_places.setdefault(e.mac, set()).add((e.switch, e.interface))

    rows = []
    for e in surviving:
        notes = []
        mac_count = len(ip_macs[e.ip])
        if mac_count > 1:
            notes.append(DUPLICATE_IP_NOTE.format(n=mac_count))
        if len(mac_places[e.mac]) > 1:
            notes.append(MULTI_SWITCH_NOTE)
        rows.append(IpMacRow(
            switch=e.switch,
            stack_member=e.stack_member,
            interface=e.interface,
            vlan=e.vlan,
            ip=e.ip,
            mac=e.mac,
            state=e.state,
            age=e.age,
            notes="; ".join(notes),
        ))

    rows.sort(key=lambda r: (r.switch, r.interface, _ip_sort_key(r.ip)))
    return IpMacReport(
        vlan_switches={v: sorted(hosts) for v, hosts in vlan_switches.items()},
        rows=rows,
        excluded_local=excluded_local,
        non_ipv4=non_ipv4,
        unsupported=unsupported,
        no_bindings=no_bindings,
    )
