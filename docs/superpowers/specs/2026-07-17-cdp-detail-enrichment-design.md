# CDP Detail Enrichment — Design

**Date:** 2026-07-17
**Status:** Approved

## Problem

CHEAT collects the brief `show cdp neighbors` table, which is columnar,
truncates the platform, carries no management IP, and abbreviates interface
names ambiguously (`Gig 0/1`). That last point silently drops neighbours whose
interface names have no space (Nexus `Eth1/1`). We want richer, more reliable
CDP data: full model, **management IP**, and unambiguous interface names.

## Goal

Switch collection to `show cdp neighbors detail` and parse it into a single rich
neighbour record that feeds every CDP consumer (the per-port CDP Neighbors
column, the Unscanned Switches block, and — next cycle — the topology). Surface
the management IP and full model in the report.

## What the real output looks like

Two redacted real samples informed this design. Entries are separated by a line
of dashes (`-------------------------`); each is a block of `Key: value` lines.
Observed variety that the parser must handle:

- **Device IDs** vary: FQDN (`x-dist-4500xv.net.hu.edu`, `x.x.x.com.au`),
  `SEP<mac>` (phones), and bare MAC (`f4747...`, a C1300 small-business switch).
- **Entry address(es)** may be IPv4, IPv6 global, or **IPv6 link-local only**
  (the C1300 has no IPv4 at all).
- **Management address(es)** is a *separate* section, present on enterprise
  switches, absent on the C1300/phone; its IP differs from the entry IP and is
  the one worth surfacing.
- **Platform** may contain spaces (`Cisco IP Phone 6901`) and a PID suffix
  (`Cisco C1300-24FP-4G (PID:C1300-24FP-4G)`); prefixes are `cisco `/`Cisco `.
- **Capabilities** are words: `Router Switch IGMP` (switch) vs `Host Phone`
  (not a switch).
- **Port ID (outgoing port)** may be a full Cisco name
  (`TenGigabitEthernet2/1/29`), an abbreviated lowercase form (`gi23`), or a
  non-Cisco label (`Port 1` on a phone).
- The **same device can appear in multiple blocks** (dual-homed uplinks seen on
  two local interfaces) — each block is one sighting/link.
- The section ends with `Total cdp entries displayed : N` then the device prompt.

## Components

### `cdp_detail.py` (new — pure parsing, no XML/IO/openpyxl)

```python
@dataclass
class CdpNeighbor:
    device: str          # Device ID, verbatim
    mgmt_ip: str         # best IPv4: Management > Entry, else "" (IPv6 ignored)
    platform: str        # cleaned model, e.g. "WS-C4500X-32", "IP Phone 6901"
    capabilities: str    # e.g. "Router Switch IGMP" / "Host Phone"
    local_iface: str     # short form of the local interface, e.g. "Te2/0/4"
    remote_port: str     # short Cisco form, or verbatim non-Cisco ("Port 1")
```

- `parse_cdp_detail(text: str) -> list[CdpNeighbor]`
  - Split the CDP section into blocks on lines matching `^-{5,}$`. Ignore the
    command echo, the `Total cdp entries` line, and the trailing prompt.
  - Per block, extract:
    - `device`: value after `Device ID:`.
    - `platform` + `capabilities`: from
      `Platform:\s*(.+?),\s*Capabilities:\s*(.+)` — platform is everything up to
      `,  Capabilities:`, then cleaned (strip leading `cisco `/`Cisco `, strip a
      trailing ` (PID:...)`).
    - `local_iface` + `remote_port`: from
      `Interface:\s*(.+?),\s*Port ID \(outgoing port\):\s*(.+)`. `local_iface`
      is always a full Cisco name → short form. `remote_port` is normalised
      (below).
    - `mgmt_ip`: the first IPv4 in the `Management address(es):` section if
      present; else the first IPv4 in the `Entry address(es):` section; else
      `""`. IPv6 lines are ignored.
  - A block missing a field yields empty strings for that field; a block with no
    parseable device is skipped. No CDP section → `[]`.

- **`is_switch(neighbor) -> bool`** (or a module helper): `"switch" in
  neighbor.capabilities.lower()`.

- **Port normaliser** (module helper, reused by `remote_port`):
  - Recognised full Cisco name (via the existing `interface_parser.shorten_iface`)
    → short form (`GigabitEthernet1/0/8` → `Gi1/0/8`, `TenGigabitEthernet2/1/29`
    → `Te2/1/29`).
  - Abbreviated Cisco form (`^(gi|te|fa|fo|hu|tw|fi|et|eth)\d`, case-insensitive)
    → canonical short (`gi23` → `Gi23`).
  - Anything else kept verbatim (`Port 1`, `eth0`).

### `interface_parser.py` — rewire `parse_cdp_neighbors`

- Reimplement `parse_cdp_neighbors(text) -> dict[str, str]` on top of
  `parse_cdp_detail`: group neighbours by `local_iface`; each value is
  `"<device> (<remote_port>)"` with the mgmt IP appended when present
  (`"dist-4500xv (Te2/1/24) 10.20.3.14"`); multiple neighbours on one interface
  are comma-joined. All neighbours are included (phones/APs too). `parse_output`
  keeps calling `parse_cdp_neighbors` and assigning `rec.cdp_neighbors` — no
  interface change.

### `unscanned_switches.py` — rewire `parse_cdp_switch_neighbors`

- `SwitchNeighbour` gains a trailing field `mgmt_ip: str = ""` (backward-compatible
  with existing positional constructions).
- Reimplement `parse_cdp_switch_neighbors(text) -> list[SwitchNeighbour]` on top
  of `parse_cdp_detail`, keeping only `is_switch` neighbours and mapping
  `device, platform (full, cleaned), capabilities, local_iface, remote_port,
  mgmt_ip`. `find_unscanned_switches` and `cdp_topology.build_topology` inherit
  the richer data unchanged.

### `cheat_core.py` — command swap

- In `DNAC_COMMANDS`, replace `"show cdp neighbors"` with
  `"show cdp neighbors detail"`. Command count is unchanged (still 5).

### `excel_generator.py` — Unscanned Switches block

- Insert a `Mgmt IP` column into the block, **keeping** the existing
  `Capability` column (more info, per the project preference). New header order:
  `Unknown Neighbour | Platform | Mgmt IP | Capability | Seen On |
  Local Interface | Neighbour Port`, with `Mgmt IP` populated from
  `SwitchNeighbour.mgmt_ip` and `Platform` now showing the full cleaned model.
  The enriched per-port `CDP Neighbors` cell comes for free from the rewired
  `parse_cdp_neighbors`.

## Data flow

```
show cdp neighbors detail (raw text)
   └─ parse_cdp_detail -> list[CdpNeighbor]
        ├─ interface_parser.parse_cdp_neighbors -> per-iface cell (device (port) ip)
        └─ unscanned_switches.parse_cdp_switch_neighbors (is_switch)
             ├─ find_unscanned_switches -> Unscanned Switches block (+ Mgmt IP)
             └─ cdp_topology.build_topology (richer nodes; labels used next cycle)
```

## Error handling

- Per-block best-effort: missing fields → empty strings; unparseable block
  skipped; no CDP section → empty list. One bad block never aborts parsing.
- IPv6-only / no-management-address neighbours → `mgmt_ip = ""` (surfaced as a
  blank cell), never a crash.

## Testing

- `parse_cdp_detail` against redacted versions of both real samples, asserting:
  - a switch with distinct Entry vs Management IP → `mgmt_ip` is the Management
    IP;
  - the C1300 (IPv6 link-local only) → `mgmt_ip == ""`, still a valid switch
    record;
  - the 6901 phone → `is_switch` False, `remote_port == "Port 1"` (verbatim),
    `platform == "IP Phone 6901"`;
  - the 4500X appearing in two blocks → two `CdpNeighbor` records (two
    sightings);
  - platform cleaning (`cisco WS-C4500X-32` → `WS-C4500X-32`; PID suffix
    stripped);
  - port normalisation (`GigabitEthernet1/0/8` → `Gi1/0/8`; `gi23` → `Gi23`).
- `parse_cdp_neighbors` (rewired): the per-iface cell contains
  `"device (port) ip"`, includes the phone, and comma-joins multiple neighbours.
- `parse_cdp_switch_neighbors` (rewired): returns `SwitchNeighbour` with
  `mgmt_ip` and full platform; excludes the phone; includes the switches.
- `excel_generator`: the Unscanned Switches block renders the `Mgmt IP` column
  and the full platform.
- Migrate the existing brief-format CDP fixtures in `test_interface_parser.py`,
  `test_unscanned_switches.py`, and `test_cdp_topology.py` to the detail format
  so those suites exercise the new parser.

## Out of scope (YAGNI)

- Topology node labels using the new IP/model (handled by the next cycle, the
  layout overhaul).
- CDP `Version`, `Native VLAN`, `Duplex`, and power fields (not needed now).
- Separate per-port neighbour IP/platform columns (the enriched cell was chosen
  instead).
