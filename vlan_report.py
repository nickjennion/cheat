"""Parse switch VLAN/SVI data and build a per-switch VLAN inventory."""

import ipaddress
import re
from dataclasses import dataclass, field

from interface_parser import is_physical_iface, shorten_iface
from mac_table import parse_mac_address_table
from palantir_report import parse_ip_tracking


@dataclass
class VlanRecord:
    switch: str
    vlan: str
    name: str = ""
    description: str = ""
    status: str = ""
    ports: str = ""
    subnet: str = ""
    gateway: str = ""
    svi_state: str = ""
    client_count: int = 0
    clients: str = ""


@dataclass
class _VlanDetails:
    name: str = ""
    description: str = ""
    status: str = ""
    ports: str = ""
    subnet: str = ""
    gateway: str = ""
    svi_state: str = ""


# Keep the status expression permissive for platform/release variants without
# allowing ordinary name text to be mistaken for a row.
_VLAN_ROW = re.compile(
    r"^\s*(?P<vlan>\d+)\s+(?P<name>.+?)\s{2,}"
    r"(?P<status>active|act/unsup|suspended|shutdown|private)\s*(?P<ports>.*)$",
    re.IGNORECASE,
)
_SVI_HEADER = re.compile(
    r"^\s*Vlan(?P<vlan>\d+)\s+is\s+(?P<state>.*)$", re.IGNORECASE
)
_DESCRIPTION = re.compile(r"^\s*Description:\s*(?P<value>.*)$", re.IGNORECASE)
_INTERNET = re.compile(
    r"^\s*Internet address is\s+(?P<value>\d{1,3}(?:\.\d{1,3}){3}/\d{1,2})\s*$",
    re.IGNORECASE,
)
_NAME_SUBNET = re.compile(r"(?P<value>\d{1,3}(?:\.\d{1,3}){3}/\d{1,2})")


def _parse_vlans(text: str) -> dict[str, _VlanDetails]:
    out: dict[str, _VlanDetails] = {}
    for line in (text or "").splitlines():
        match = _VLAN_ROW.match(line)
        if not match:
            continue
        vlan = match.group("vlan")
        name = match.group("name").strip()
        details = out.setdefault(vlan, _VlanDetails())
        details.name = name
        details.status = match.group("status").strip()
        details.ports = match.group("ports").strip()
        subnet = _NAME_SUBNET.search(name)
        if subnet:
            details.subnet = subnet.group("value")
    return out


def _parse_svis(text: str) -> dict[str, _VlanDetails]:
    out: dict[str, _VlanDetails] = {}
    current = None
    for line in (text or "").splitlines():
        header = _SVI_HEADER.match(line)
        if header:
            current = header.group("vlan")
            out[current] = _VlanDetails(svi_state=header.group("state").strip())
            continue
        if current is None:
            continue
        description = _DESCRIPTION.match(line)
        if description:
            out[current].description = description.group("value").strip()
            continue
        internet = _INTERNET.match(line)
        if internet:
            value = internet.group("value")
            out[current].gateway = value.split("/", 1)[0]
            out[current].subnet = value
    return out


def _valid_subnet(value: str) -> str:
    try:
        return str(ipaddress.ip_interface(value).network) if value else ""
    except ValueError:
        return value


def build_vlan_report(raw_outputs: dict) -> list[VlanRecord]:
    """Build VLAN rows from show vlan, show interfaces vlan and client data."""
    rows: list[VlanRecord] = []
    for host, text in raw_outputs.items():
        vlans = _parse_vlans(text)
        svis = _parse_svis(text)
        for vlan, svi in svis.items():
            target = vlans.setdefault(vlan, _VlanDetails())
            if svi.description:
                target.description = svi.description
            target.gateway = svi.gateway or target.gateway
            target.subnet = svi.subnet or target.subnet
            target.svi_state = svi.svi_state

        clients: dict[str, set[str]] = {}
        macs = parse_mac_address_table(text)
        mac_to_vlan = {m.mac: m.vlan for m in macs if is_physical_iface(m.interface)}
        bindings = parse_ip_tracking(text)
        for binding in bindings:
            if not is_physical_iface(binding.interface):
                continue
            clients.setdefault(binding.vlan, set()).add(
                f"{binding.ip} ({binding.mac}, {binding.interface})"
            )

        for mac in macs:
            if not is_physical_iface(mac.interface):
                continue
            # ARP fallback: the common ARP form is parsed below from the same
            # raw text; device tracking remains preferred when present.
            for ip, arp_mac in _parse_arp(text):
                if arp_mac == mac.mac:
                    clients.setdefault(mac.vlan, set()).add(
                        f"{ip} ({mac.mac}, {mac.interface})"
                    )

        for vlan, details in sorted(vlans.items(), key=lambda item: int(item[0])):
            client_values = sorted(clients.get(vlan, set()))
            rows.append(VlanRecord(
                switch=host, vlan=vlan, name=details.name,
                description=details.description,
                status=details.status, ports=details.ports,
                subnet=_valid_subnet(details.subnet), gateway=details.gateway,
                svi_state=details.svi_state, client_count=len(client_values),
                clients="; ".join(client_values),
            ))
    return rows


def _parse_arp(text: str) -> list[tuple[str, str]]:
    """Parse IOS ARP rows: Internet <ip> ... <mac> ARPA <interface>."""
    mac = r"(?:[0-9a-f]{4}\.){2}[0-9a-f]{4}"
    pattern = re.compile(
        rf"^\s*(?:Internet\s+)?(?P<ip>\d{{1,3}}(?:\.\d{{1,3}}){{3}})\s+\S+\s+"
        rf"(?P<mac>{mac})\s+\S+\s+(?P<iface>\S+)\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    return [(m.group("ip"), m.group("mac").lower()) for m in pattern.finditer(text or "")]
