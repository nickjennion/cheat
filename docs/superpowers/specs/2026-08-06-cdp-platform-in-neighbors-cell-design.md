# CDP Platform in "CDP Neighbors" Cell — Design

**Date:** 2026-08-06
**Status:** Approved

## Problem

The Excel "CDP Neighbors" column shows `device (port) ip` per neighbour. For
Cisco IP phones the device ID is `SEP<MAC>`, so the cell gives no way to tell
what model of phone (e.g. 3901 vs 8845) is connected to a port — even though
`show cdp neighbors detail` reports it on the `Platform:` line and
`cdp_detail.py` already parses it into `CdpNeighbor.platform`.

No additional command-runner command is required; the data is already collected
and parsed, then dropped at formatting time.

## Change

In `parse_cdp_neighbors()` (`interface_parser.py`), include the platform in
each neighbour entry:

- Current: `SEP0C75BD123456 (Port 1) 10.1.2.3`
- New:     `SEP0C75BD123456 [IP Phone 8845] (Port 1) 10.1.2.3`

Rules:

- The `[platform]` segment appears for every neighbour with a non-empty
  platform (phones, APs, switches alike).
- When CDP reports no platform, the segment is omitted entirely — never
  empty brackets.
- Multiple neighbours on one interface remain comma-joined, unchanged.
- Platform text is the cleaned value from `_clean_platform()` (leading
  `cisco ` stripped), e.g. `IP Phone 8845`, `IP Phone 3901`.

Widen the "CDP Neighbors" column in `excel_generator.py` `COL_WIDTHS` from 30
to 44 to fit the longer strings.

## Out of scope / unaffected

- `cdp_detail.py` parsing — platform already captured.
- Discovered-devices tables and CDP topology — built from `CdpNeighbor`
  records directly, not from the formatted string.
- No new columns, sheets, or commands.

## Testing

TDD in `test_interface_parser.py`:

1. Phone neighbour fixture (`Platform: Cisco IP Phone 8845`) → entry contains
   `[IP Phone 8845]` in the new position.
2. Neighbour with no platform line → entry contains no `[` / `]`.
3. Existing multi-neighbour comma-join behaviour still holds.
