"""
Analyse port utilisation from a CHEAT UNPLUGGED report.

Reads an Excel workbook (per-stack tabs or consolidated single sheet) and
counts ports with traffic in the last 42 days vs. idle ports per switch/stack.

The "Last Input" column drives the classification:
  - "never" or missing → idle (no traffic ever)
  - Recent time (e.g., "2d3h", "5w") → in use (within threshold)
  - Old time (e.g., "10w") → idle (beyond threshold)

Usage:
    python port_utilisation.py <report.xlsx> [threshold_days]

Default threshold is 42 days (matching uptime highlight logic).
"""

import sys
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import openpyxl


def parse_last_input_days(last_input_str: str) -> Optional[float]:
    """Convert a "Last Input" string to days ago, or None if invalid/never.

    Examples:
      "2d3h" → 2.125 days
      "5w" → 35 days
      "2 days 3 hours" → 2.125 days
      "never" or "" → None
    """
    if not last_input_str or str(last_input_str).strip().lower() == "never":
        return None

    total = 0.0
    # Match both abbreviated (2d, 5w, 3h, 10m) and full words (2 days, 5 weeks, etc.)
    for val, unit in re.findall(r"(\d+)\s*([a-z]+)", str(last_input_str), re.I):
        v = int(val)
        unit_lower = unit.lower()
        # Match weeks, days, hours, minutes (and their abbreviations)
        if unit_lower.startswith("w"):
            total += v * 7
        elif unit_lower.startswith("d"):
            total += v
        elif unit_lower.startswith("h"):
            total += v / 24
        elif unit_lower.startswith("m"):
            total += v / (24 * 60)

    return total if total > 0 else None


def analyse_workbook(
    wb_path: str, threshold_days: int = 42
) -> tuple[bool, str, dict]:
    """Analyse port utilisation from Excel workbook.

    Returns (success: bool, message: str, results: dict[switch, (in_use, idle)])
    """
    in_path = Path(wb_path)
    if not in_path.is_file():
        return False, f"✗ File not found: {wb_path}", {}

    print(f"Loading '{wb_path}'...")
    try:
        wb = openpyxl.load_workbook(in_path, data_only=True)
    except Exception as e:
        return False, f"✗ Failed to open: {e}", {}

    results: dict[str, tuple[int, int]] = {}  # switch → (in_use, idle)

    for sheet_idx, ws in enumerate(wb.worksheets, start=1):
        print(f"  Sheet {sheet_idx}/{len(wb.worksheets)}: '{ws.title}'...", end=" ", flush=True)

        # Find column indices by header
        if ws.max_row < 1:
            print("(empty)")
            continue

        headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
        try:
            switch_col = headers.index("Switch") + 1
            last_input_col = headers.index("Last Input") + 1
        except ValueError as e:
            print(f"✗ missing column ({e})")
            continue

        # Tally ports per switch
        switch_stats: dict[str, tuple[int, int]] = {}
        row_count = 0

        for row in range(2, ws.max_row + 1):
            switch = ws.cell(row=row, column=switch_col).value
            last_input = ws.cell(row=row, column=last_input_col).value

            if not switch:
                continue

            row_count += 1
            switch_str = str(switch).strip()

            # Classify port as in-use or idle
            days_since_traffic = parse_last_input_days(last_input)
            in_use = days_since_traffic is not None and days_since_traffic < threshold_days
            is_in_use = 1 if in_use else 0
            is_idle = 0 if in_use else 1

            # Accumulate per switch
            if switch_str not in switch_stats:
                switch_stats[switch_str] = (0, 0)
            curr_in_use, curr_idle = switch_stats[switch_str]
            switch_stats[switch_str] = (curr_in_use + is_in_use, curr_idle + is_idle)

        # Merge into global results
        for switch, (in_use, idle) in switch_stats.items():
            if switch in results:
                prev_in_use, prev_idle = results[switch]
                results[switch] = (prev_in_use + in_use, prev_idle + idle)
            else:
                results[switch] = (in_use, idle)

        print(f"({row_count} ports across {len(switch_stats)} switch(es))")

    wb.close()

    if not results:
        return False, "✗ No port data found", {}

    return True, f"✓ Analysed {sum(in_use + idle for in_use, idle in results.values())} ports", results


def print_summary(results: dict[str, tuple[int, int]], threshold_days: int) -> None:
    """Print a nicely formatted summary table."""
    print(f"\n{'='*80}")
    print(f"Port Utilisation Summary (threshold: {threshold_days} days)")
    print(f"{'='*80}\n")

    print(f"{'Switch/Stack':<40} {'In Use':<12} {'Idle':<12} {'Total':<12}")
    print("-" * 80)

    grand_in_use = 0
    grand_idle = 0

    for switch in sorted(results.keys()):
        in_use, idle = results[switch]
        total = in_use + idle
        grand_in_use += in_use
        grand_idle += idle

        pct_in_use = (in_use / total * 100) if total > 0 else 0
        print(
            f"{switch:<40} {in_use:<12} {idle:<12} {total:<12} "
            f"({pct_in_use:.1f}% in use)"
        )

    print("-" * 80)
    grand_total = grand_in_use + grand_idle
    grand_pct = (grand_in_use / grand_total * 100) if grand_total > 0 else 0
    print(
        f"{'TOTAL':<40} {grand_in_use:<12} {grand_idle:<12} {grand_total:<12} "
        f"({grand_pct:.1f}% in use)"
    )
    print(f"{'='*80}\n")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__.strip())
        return 1

    wb_path = argv[1]
    threshold_days = int(argv[2]) if len(argv) > 2 else 42

    success, message, results = analyse_workbook(wb_path, threshold_days)
    print(f"{message}\n")

    if success:
        print_summary(results, threshold_days)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
