"""
Detect Cisco switches seen via CDP that were not scanned this session.

Parses `show cdp neighbors detail` output already collected for every device
and diffs the switch-capable neighbours against the set of scanned hosts.
"""

from dataclasses import dataclass, replace

from cdp_detail import parse_cdp_detail, is_switch, is_access_point


@dataclass
class SwitchNeighbour:
    device: str
    platform: str
    capability: str
    local_iface: str
    neighbour_port: str
    seen_on: str = ""
    mgmt_ip: str = ""


def parse_cdp_switch_neighbors(text: str) -> list[SwitchNeighbour]:
    """Switch-capable CDP neighbours from `show cdp neighbors detail` output."""
    out: list[SwitchNeighbour] = []
    for nb in parse_cdp_detail(text):
        if not (is_switch(nb) or is_access_point(nb)):
            continue
        out.append(SwitchNeighbour(
            device=nb.device,
            platform=nb.platform,
            capability=nb.capabilities,
            local_iface=nb.local_iface,
            neighbour_port=nb.remote_port,
            mgmt_ip=nb.mgmt_ip,
        ))
    return out


def _norm_host(name: str) -> str:
    """Normalise a hostname for matching: drop domain suffix, case-fold."""
    return str(name).split(".")[0].strip().casefold()


def find_unscanned_switches(raw_outputs: dict[str, str], scanned_hostnames) -> list[SwitchNeighbour]:
    """Return switch neighbours seen via CDP that were not scanned this session.

    raw_outputs maps hostname -> raw command output. scanned_hostnames is the set
    of hosts we ran commands on. One SwitchNeighbour per (device, seen_on,
    local_iface) sighting.
    """
    scanned = {_norm_host(h) for h in scanned_hostnames}
    seen: set[tuple[str, str, str]] = set()
    rows: list[SwitchNeighbour] = []

    for host, text in raw_outputs.items():
        for nb in parse_cdp_switch_neighbors(text):
            if _norm_host(nb.device) in scanned:
                continue
            key = (_norm_host(nb.device), _norm_host(host), nb.local_iface)
            if key in seen:
                continue
            seen.add(key)
            rows.append(replace(nb, seen_on=host))

    rows.sort(key=lambda n: (_norm_host(n.device), _norm_host(n.seen_on), n.local_iface))
    return rows
