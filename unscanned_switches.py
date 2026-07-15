"""
Detect Cisco switches seen via CDP that were not scanned this session.

Parses the brief `show cdp neighbors` output already collected for every device
and diffs the switch-capable neighbours against the set of scanned hosts.
"""

from dataclasses import dataclass, replace

from interface_parser import (
    RE_CDP_LOCAL_IFACE,
    RE_CDP_PORT_ID,
    extract_neighbor_port,
)

# CDP capability codes (R Router, T Trans Bridge, B SR Bridge, S Switch,
# H Host, I IGMP, r Repeater, P Phone, D Remote, C CVTA, M Two-port Mac Relay).
CDP_CAP_CODES = set("RTBSHIrPDCM")


@dataclass
class SwitchNeighbour:
    device: str
    platform: str
    capability: str
    local_iface: str
    neighbour_port: str
    seen_on: str = ""


def parse_cdp_switch_neighbors(text: str) -> list[SwitchNeighbour]:
    """Parse brief `show cdp neighbors` output, keeping only switch neighbours.

    A neighbour is a switch when its Capability field contains 'S'. Long Device
    IDs wrap onto their own line (the interface appears indented on the next
    line); that case is handled via `pending_device`.
    """
    out: list[SwitchNeighbour] = []
    in_table = False
    pending_device: str | None = None

    for raw in text.split("\n"):
        line = raw.rstrip()

        if not in_table:
            if "Device ID" in line and ("Local Intrfce" in line or "Local Interface" in line):
                in_table = True
            continue

        stripped = line.strip()
        if not stripped:
            continue

        # End of CDP output.
        if (stripped.endswith("#") or stripped.endswith(">")
                or stripped.lower().startswith("show ")
                or stripped.lower().startswith("total cdp entries")):
            in_table = False
            pending_device = None
            continue

        # Repeated header (rare).
        if "Device ID" in line and ("Local Intrfce" in line or "Local Interface" in line):
            continue

        indented = line[0].isspace()
        local_match = RE_CDP_LOCAL_IFACE.search(line)

        if not local_match:
            if not indented:
                pending_device = stripped.split()[0]
            continue

        device = pending_device if indented else stripped.split()[0]
        pending_device = None
        if not device:
            continue

        local_iface = local_match.group(1)[:2].capitalize() + local_match.group(2)

        rem = line[local_match.end():].strip()
        neighbour_port = extract_neighbor_port(rem)
        mport = RE_CDP_PORT_ID.search(rem)
        middle = rem[:mport.start()].strip() if mport else rem

        mtokens = middle.split()
        if mtokens and mtokens[0].isdigit():   # holdtime
            mtokens = mtokens[1:]

        cap: list[str] = []
        while mtokens and len(mtokens[0]) == 1 and mtokens[0] in CDP_CAP_CODES:
            cap.append(mtokens.pop(0))

        if "S" not in cap:
            continue

        out.append(SwitchNeighbour(
            device=device,
            platform=" ".join(mtokens),
            capability=" ".join(cap),
            local_iface=local_iface,
            neighbour_port=neighbour_port,
        ))

    return out
