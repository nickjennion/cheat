"""
Parse `show cdp neighbors detail` into rich neighbour records.

Pure parsing — no XML, no file IO. One CdpNeighbor per detail block; feeds the
CDP Neighbors column, the Unscanned Switches block, and the topology.
"""

import re
from dataclasses import dataclass

from interface_parser import shorten_iface

# Cisco interface-type abbreviations that appear as bare Port IDs (e.g. "gi23"
# on small-business switches). Anything else (Port 1, eth0) is kept verbatim.
_CDP_ABBR = {"gi": "Gi", "te": "Te", "fa": "Fa", "fo": "Fo",
             "hu": "Hu", "tw": "Tw", "fi": "Fi"}

_RE_DEVICE = re.compile(r"(?im)^\s*Device ID:\s*(\S+)")
_RE_PLATFORM = re.compile(r"(?im)^\s*Platform:\s*(.+?),\s*Capabilities:\s*(.*)$")
_RE_IFACE = re.compile(
    r"(?im)^\s*Interface:\s*(.+?),\s*Port ID \(outgoing port\):\s*(.*)$"
)
_RE_IPV4 = re.compile(r"IP address:\s*(\d{1,3}(?:\.\d{1,3}){3})")


@dataclass
class CdpNeighbor:
    device: str
    mgmt_ip: str
    platform: str
    capabilities: str
    local_iface: str
    remote_port: str


def is_switch(neighbor: CdpNeighbor) -> bool:
    """True when the neighbour advertises the Switch capability."""
    return "switch" in neighbor.capabilities.lower()


def _clean_platform(s: str) -> str:
    s = re.sub(r"^\s*cisco\s+", "", s.strip(), flags=re.IGNORECASE)
    s = re.sub(r"\s*\(PID:[^)]*\)\s*$", "", s)
    return s.strip()


def _norm_port(name: str) -> str:
    """Short Cisco form for interfaces; verbatim for non-Cisco port labels."""
    name = name.strip()
    if not name:
        return ""
    short = shorten_iface(name)
    if short != name:               # recognised full Cisco name
        return short
    m = re.match(r"^([A-Za-z]{2,4})(\d.*)$", name)   # abbreviated, e.g. "gi23"
    if m and m.group(1).lower() in _CDP_ABBR:
        return _CDP_ABBR[m.group(1).lower()] + m.group(2)
    return name                     # "Port 1", "eth0", ...


def _section_ipv4(block: str, header: str) -> str:
    """First IPv4 within the named address section of a block, or ''."""
    idx = block.find(header)
    if idx == -1:
        return ""
    lines = []
    for ln in block[idx + len(header):].splitlines():
        if ln.strip() == "":
            continue
        if not ln.startswith((" ", "\t")):
            break                    # unindented line -> section ended
        lines.append(ln)
    m = _RE_IPV4.search("\n".join(lines))
    return m.group(1) if m else ""


def _parse_block(block: str) -> "CdpNeighbor | None":
    m_dev = _RE_DEVICE.search(block)
    if not m_dev:
        return None
    platform = capabilities = local_iface = remote_port = ""
    m_p = _RE_PLATFORM.search(block)
    if m_p:
        platform = _clean_platform(m_p.group(1))
        capabilities = m_p.group(2).strip()
    m_i = _RE_IFACE.search(block)
    if m_i:
        local_iface = shorten_iface(m_i.group(1).strip())
        remote_port = _norm_port(m_i.group(2))
    mgmt_ip = (_section_ipv4(block, "Management address(es):")
               or _section_ipv4(block, "Entry address(es):"))
    return CdpNeighbor(m_dev.group(1).strip(), mgmt_ip, platform,
                       capabilities, local_iface, remote_port)


def parse_cdp_detail(text: str) -> list[CdpNeighbor]:
    """Parse the `show cdp neighbors detail` section into neighbour records."""
    end = len(text)
    m_end = re.search(r"Total cdp entries displayed", text, re.IGNORECASE)
    if m_end:
        end = m_end.start()
    start = 0
    m_start = re.search(r"show\s+cdp\s+neighbors?\s+det", text, re.IGNORECASE)
    if m_start and m_start.start() < end:
        start = m_start.end()

    out = []
    for block in re.split(r"(?m)^-{4,}\s*$", text[start:end]):
        if "Device ID:" not in block:
            continue
        nb = _parse_block(block)
        if nb is not None:
            out.append(nb)
    return out
