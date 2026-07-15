# Unscanned Cisco Switches — Design

**Date:** 2026-07-15
**Status:** Approved

## Problem

When a site is scanned (all ports, including distribution), the scanned devices
become "known" — they get port inventories, parsed files, and appear in the
combined report. But a rogue/unmanaged Cisco switch hanging off a known switch
is invisible: it shows up only as a CDP neighbour of a scanned device and is
never itself scanned.

We want the combined report to surface, per session, every Cisco **switch** seen
via CDP that was **not** scanned in that session — i.e. switches hanging off the
known estate.

## Scope

- Wired into the `main_latest.py` bulk-scan path only (the primary flow), via
  `cheat_core.generate_excel` → `excel_generator.write_combined_excel` (mode 3).
- `main.py` / `main_debug.py` call `write_combined_excel` directly and will
  simply omit the block until later — a trivial follow-up, explicitly out of
  scope here.
- Combined report only (no changes to the standalone `port_utilisation.py`
  workbook-reading path).

## Definitions

- **Scanned set:** the hostnames scanned this session = `devices_data.keys()`.
- **Switch neighbour:** a CDP neighbour whose Capability field contains `S`.
  This catches L2 switches (`S I`) and L3 switches (`R S I`); it excludes phones
  (`H P`), APs/hosts (`H`), and pure routers (`R`).
- **Unscanned:** a switch neighbour whose name — domain-stripped and
  case-folded — is not in the scanned set.
- **Sighting:** one `(unknown device, seen-on switch, local interface)` tuple.
  A rogue seen on two known switches produces two rows.

## Data source

The brief `show cdp neighbors` output is already collected for every device and
carries the Capability and (truncated) Platform columns. No new command is added
— zero extra scan time. Example (from a real capture):

```
Device ID        Local Intrfce     Holdtme    Capability  Platform  Port ID
sw4              Gig 0/0           137              S I   C9KV-UADP Gig 0/0
sw2              Gig 1/0/3         169              S I   C9KV-UADP Gig 1/0/2
```

Platform is truncated in brief mode (`C9KV-UADP`), which is acceptable for a
"where to look" report.

## Components

### `unscanned_switches.py` (new — pure parsing/analysis, no openpyxl)

```python
@dataclass
class SwitchNeighbour:
    device: str          # CDP Device ID as reported, e.g. "sw4"
    platform: str        # truncated platform, e.g. "C9KV-UADP"
    capability: str      # raw capability tokens, e.g. "S I"
    local_iface: str     # short form of local interface, e.g. "Gi0/0"
    neighbour_port: str  # neighbour's port id, e.g. "Gi0/0"
    seen_on: str = ""    # scanned host this was seen from (set during aggregation)
```

- `parse_cdp_switch_neighbors(text) -> list[SwitchNeighbour]`
  Walks the brief CDP table, reusing the existing parser's wrap handling
  (long Device IDs wrap to the next line) and short-form interface
  normalisation. For each entry it splits the middle fields as:
  `holdtime` (int) → `capability` (leading single-letter CDP codes from the set
  `R T B S H I r P D C M`) → `platform` (remaining tokens) →
  `neighbour_port` (trailing `Type slot/port`). Keeps only rows whose capability
  contains `S`. `seen_on` left blank.

- `find_unscanned_switches(raw_outputs, scanned_hostnames) -> list[SwitchNeighbour]`
  For each scanned device's raw text, collect switch-neighbours; drop any whose
  normalised name (`name.split('.')[0].casefold()`) is in the normalised scanned
  set; stamp `seen_on`; dedupe exact `(device, seen_on, local_iface)`; sort by
  `(device, seen_on, local_iface)`.

### `excel_generator.py` (renderer)

- `write_utilisation_sheet(...)` returns the **next free row** after the TOTAL
  row (currently returns `None`; only caller is `write_combined_excel`).
- `write_unscanned_switches_block(ws, start_row, rows)` — writes a blank
  separator row, a section header
  *"Unscanned Cisco Switches (seen via CDP, not scanned this session)"*, the
  column headers `Unknown Neighbour | Platform | Capability | Seen On |
  Local Interface | Neighbour Port`, then one row per sighting. Empty `rows` →
  a single "None detected" line.
- `write_combined_excel(devices_data, threshold_days, outpath, unscanned=None)`
  — when `unscanned is not None`, append the block to the Port Utilisation sheet
  (handles both the normal table and the "No copper port data found" branch).
  When `None`, the block is omitted (backward compatible).

### Wiring

- `cheat_core.generate_excel(devices_data, mode, filename_stem, threshold=42,
  raw_outputs=None)` — for mode 3, compute
  `unscanned = find_unscanned_switches(raw_outputs, devices_data.keys())` when
  `raw_outputs` is provided, else pass `None`.
- `main_latest.py` passes its existing `outputs` dict:
  `generate_excel(devices_data, mode, stem, threshold, raw_outputs=outputs)`.

## Data flow

```
main_latest: outputs (raw text) ──┐
                                  ├─> parse_outputs ─> devices_data (scanned set = keys)
                                  │
                                  └─> generate_excel(devices_data, ..., raw_outputs=outputs)
                                          │
                                          └─> find_unscanned_switches(raw_outputs, keys)
                                                  │  -> list[SwitchNeighbour]
                                                  └─> write_combined_excel(..., unscanned=...)
                                                          └─> Port Utilisation sheet
                                                                 + write_unscanned_switches_block
```

## Error handling

- Parsing is best-effort per device; a malformed CDP section for one device is
  skipped without failing the report.
- No CDP section anywhere → empty list → block shows "None detected".

## Testing

- `parse_cdp_switch_neighbors` against the real sample block above: returns
  `sw2, sw3, sw4` with capability `S I`, correct local iface / platform /
  neighbour port.
- `find_unscanned_switches`: given `raw_outputs` for `sw1/sw2/sw3` and a scanned
  set `{sw1, sw2, sw3}`, returns `sw4` only (seen on `sw1`); scanned `sw2`/`sw3`
  excluded; a phone entry (`H P`) excluded; verifies domain-strip and
  case-insensitive matching.
- Renderer: `write_unscanned_switches_block` produces the expected header + rows
  (in-memory openpyxl), and the "None detected" path.
- Integration: `write_combined_excel(..., unscanned=[...])` places the block
  below the utilisation TOTAL on the Port Utilisation sheet; `unscanned=None`
  omits it entirely.
