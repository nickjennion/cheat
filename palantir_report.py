"""Build the enriched per-port dataset used by Menu 5 Palantir mode.

Palantir combines the normal interface inventory, the full MAC address table,
CDP neighbour context, and the legacy ``show ip device tracking all`` table.
One output row represents one client/address on a physical switch port.  Empty
ports are retained, and multi-client ports expand to multiple rows.
"""

import re
from dataclasses import dataclass, field

from interface_parser import InterfaceRecord, shorten_iface
from mac_by_port import build_mac_by_port_report


_IPDT_ROW = re.compile(
    r"(?im)^\s*(?P<ip>\d{1,3}(?:\.\d{1,3}){3})\s+"
    r"(?P<mac>[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})\s+"
    r"(?P<vlan>\d+)\s+"
    r"(?P<iface>(?:[A-Za-z][A-Za-z-]*)(?:\d+)(?:/\d+)+)"
    r"(?:\s+(?P<tail>.*?))?\s*$"
)


@dataclass(frozen=True)
class LegacyIpTrackingEntry:
    ip: str
    mac: str
    vlan: str
    interface: str
    state: str = ""


@dataclass
class PalantirRow:
    port: InterfaceRecord
    mac: str = ""
    client_ip: str = ""
    client_vlan: str = ""
    tracking_state: str = ""
    mac_type: str = ""
    device_type: str = ""
    neighbour: str = ""
    notes: str = ""


@dataclass
class PalantirReport:
    rows_by_switch: dict[str, list[PalantirRow]]
    client_rows: int = 0
    mac_rows_without_ip: int = 0
    tracked_rows_without_mac_table: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def rows(self) -> list[PalantirRow]:
        return [row for rows in self.rows_by_switch.values() for row in rows]


def parse_legacy_ip_tracking(text: str) -> list[LegacyIpTrackingEntry]:
    """Parse filtered legacy IPDT rows.

    Supported IOS layouts place IP, MAC, VLAN and interface first.  Any trailing
    Probe-Timeout/State/Source fields vary by release; the final ACTIVE or
    INACTIVE token is retained when present.
    """
    entries = []
    for match in _IPDT_ROW.finditer(text or ""):
        tail = (match.group("tail") or "").split()
        state = next(
            (token.upper() for token in reversed(tail)
             if token.upper() in {"ACTIVE", "INACTIVE", "REACHABLE", "STALE"}),
            "",
        )
        interface = shorten_iface(match.group("iface"))
        entries.append(LegacyIpTrackingEntry(
            ip=match.group("ip"),
            mac=match.group("mac").lower(),
            vlan=match.group("vlan"),
            interface=interface,
            state=state,
        ))
    return entries


def build_palantir_report(devices_data: dict, raw_outputs: dict) -> PalantirReport:
    """Correlate interface, MAC/CDP and legacy IPDT data by switch and port."""
    mac_report = build_mac_by_port_report(raw_outputs)
    macs_by_port: dict[tuple[str, str], list] = {}
    for row in mac_report.rows:
        macs_by_port.setdefault((row.switch, row.interface), []).append(row)

    tracking_by_host: dict[str, list[LegacyIpTrackingEntry]] = {
        host: parse_legacy_ip_tracking(text) for host, text in raw_outputs.items()
    }
    tracking_by_mac: dict[tuple[str, str], list[LegacyIpTrackingEntry]] = {}
    tracking_by_port: dict[tuple[str, str], list[LegacyIpTrackingEntry]] = {}
    for host, entries in tracking_by_host.items():
        for entry in entries:
            tracking_by_mac.setdefault((host, entry.mac), []).append(entry)
            tracking_by_port.setdefault((host, entry.interface), []).append(entry)

    rows_by_switch: dict[str, list[PalantirRow]] = {}
    client_rows = 0
    mac_rows_without_ip = 0
    tracked_rows_without_mac_table = 0

    for host, (port_records, _stack_members) in devices_data.items():
        port_by_iface = {record.iface: record for record in port_records}
        # Option 3's parsed inventory defines the physical-port population.
        # This deliberately excludes MACs learned on logical Port-channels and
        # also honours Menu 5's copper-only filter.
        all_ifaces = set(port_by_iface)
        host_rows = []

        for iface in sorted(all_ifaces):
            port = port_by_iface[iface]
            mac_rows = macs_by_port.get((host, iface), [])
            emitted_tracking: set[LegacyIpTrackingEntry] = set()

            if not mac_rows and not tracking_by_port.get((host, iface)):
                host_rows.append(PalantirRow(port=port))
                continue

            for mac_row in mac_rows:
                tracked = [entry for entry in tracking_by_mac.get((host, mac_row.mac), [])
                           if entry.interface == iface]
                if not tracked:
                    mac_rows_without_ip += 1
                    host_rows.append(PalantirRow(
                        port=port, mac=mac_row.mac, client_vlan=mac_row.vlan,
                        mac_type=mac_row.type, device_type=mac_row.device_type,
                        neighbour=mac_row.neighbour, notes=mac_row.notes,
                    ))
                    continue
                for entry in tracked:
                    emitted_tracking.add(entry)
                    client_rows += 1
                    notes = mac_row.notes
                    if entry.vlan != mac_row.vlan:
                        mismatch = f"VLAN mismatch: MAC table {mac_row.vlan}, IP tracking {entry.vlan}"
                        notes = "; ".join(filter(None, [notes, mismatch]))
                    host_rows.append(PalantirRow(
                        port=port, mac=mac_row.mac, client_ip=entry.ip,
                        client_vlan=entry.vlan, tracking_state=entry.state,
                        mac_type=mac_row.type, device_type=mac_row.device_type,
                        neighbour=mac_row.neighbour, notes=notes,
                    ))

            for entry in tracking_by_port.get((host, iface), []):
                if entry in emitted_tracking:
                    continue
                tracked_rows_without_mac_table += 1
                client_rows += 1
                host_rows.append(PalantirRow(
                    port=port, mac=entry.mac, client_ip=entry.ip,
                    client_vlan=entry.vlan, tracking_state=entry.state,
                    notes="IP tracking entry not present in MAC table",
                ))

        rows_by_switch[host] = host_rows

    notes = []
    missing_tracking = [host for host, entries in tracking_by_host.items() if not entries]
    if missing_tracking:
        notes.append("No legacy IP device-tracking rows returned by: " + ", ".join(missing_tracking))
    return PalantirReport(
        rows_by_switch=rows_by_switch,
        client_rows=client_rows,
        mac_rows_without_ip=mac_rows_without_ip,
        tracked_rows_without_mac_table=tracked_rows_without_mac_table,
        notes=notes,
    )
