# Design: Copper-Only Filter + Menu Label Improvements

**Date:** 2026-07-03
**Scope:** `main_latest.py`, `cheat_core.py`

---

## Problem

1. Menu 5 option 3 already produces a consolidated "All Ports" flat sheet alongside per-device tabs and a utilisation summary — but its label ("Get port info + port usage tab") does not communicate this, causing users to manually run `consolidate_report.py` after the fact.

2. There is no way to restrict Excel output to copper access ports only (GiX/0/X and TeX/0/X). Non-copper interfaces (uplinks, modules, 25G/40G/100G ports) inflate reports and obscure the data most commonly needed.

---

## Design

### 1. Menu Label Rewording

Replace the three option labels in `menu_5` with clearer text:

| # | Current | Proposed |
|---|---------|----------|
| 1 | `Get port info (separate Excel per device)` | `Port report — one file per device` |
| 2 | `Get port info (one workbook, one sheet per device)` | `Port report — one file, one tab per device` |
| 3 | `Get port info + port usage tab` | `Port report — consolidated (All Ports + utilisation + per-device tabs)` |

The prompt line also updates from `Select [1-8 / s]:` to `Select [1-8 / s / p]:` to reflect the new toggle key.

### 2. Copper-Only Filter Toggle

Add a `copper_only` boolean toggle to `menu_5`, matching the existing `slow_mode` pattern exactly:

- Default: `OFF`
- Toggle key: `p`
- Shown in the status bar alongside slow mode: `copper only: ON` / `copper only: off`
- Applies to all three output modes (1, 2, 3)

**Filter location:** in `_exec_and_report`, after `parse_outputs` returns `devices_data` and before `generate_excel` is called. This keeps the filter out of the parser and out of the Excel writer — it is a pre-write transformation on the in-memory data.

**Filter logic:** reuse the existing `is_copper_port()` from `port_utilisation.py`. For each device, replace its record list with only those records where `is_copper_port(rec.iface)` is `True`. Devices with zero copper records after filtering are dropped entirely.

```python
if copper_only:
    devices_data = {
        h: ([r for r in recs if is_copper_port(r.iface)], sm)
        for h, (recs, sm) in devices_data.items()
        if any(is_copper_port(r.iface) for r in recs)
    }
```

No changes to `interface_parser.py`, `excel_generator.py`, `consolidate_report.py`, or `port_utilisation.py`.

### 3. Signal in Output Message

When `copper_only` is active, `_exec_and_report` prints a line before running so the user can see the filter is in effect:

```
  [Copper only: non-copper interfaces excluded]
```

---

## Files Changed

| File | Change |
|------|--------|
| `main_latest.py` | Add `copper_only` toggle; update menu labels and prompt string; print filter notice; pass flag to `_exec_and_report` |
| `cheat_core.py` | Add `copper_only: bool = False` parameter to `_exec_and_report`; apply filter after `parse_outputs` |

---

## Out of Scope

- `consolidate_report.py` — not changed; still available as a standalone CLI tool
- `interface_parser.py` — not changed; parses all interfaces regardless
- `excel_generator.py` — not changed; writes whatever records it receives
- Post-run consolidation prompt — not needed; users should use mode 3
- Reordering menu options — deferred; not requested
