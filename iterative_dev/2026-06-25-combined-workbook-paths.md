# Combined Workbook + Path Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the three-output workflow (per-stack xlsx + consolidated xlsx + utilisation xlsx) into a single combined workbook, restructure output folders, and fix path handling for Windows compatibility.

**Architecture:** `excel_generator.write_combined_excel()` owns the single-workbook output (Sheet 1: All Ports, Sheet 2: Port Utilisation, Sheets 3–N: per-stack tabs), computing consolidation and utilisation directly from in-memory records. `main_cli.py` prompts for threshold and filename prefix after device selection, before execution. Standalone scripts (`consolidate_report.py`, `port_utilisation.py`) are retained for re-running against old files and updated to use `Path.resolve()` throughout.

**Tech Stack:** Python 3.10+, openpyxl, pathlib.Path

## Global Constraints

- Python `Path.resolve()` must be used for all filesystem path construction — no string concatenation with `/` or `os.path.join`
- Command runner text outputs → `command_runner_outputs/` folder
- Excel report outputs → `excel_reports/` folder
- Combined workbook sheet order is fixed: "All Ports" (1), "Port Utilisation" (2), then per-stack tabs (3–N) in the order devices were processed
- Port utilisation always runs — no `--port-util` / `--no-port-util` flags
- `--port-util-threshold` CLI arg skips the interactive threshold prompt; if absent, prompt with default 42
- `--filename` CLI arg skips the interactive filename prefix prompt; if absent, prompt with default `"port-information"`
- Timestamp format for Excel filenames: `%Y-%m-%d-%H-%M` (unchanged)
- `consolidate_report.py` and `port_utilisation.py` remain functional as standalone scripts
- Apply all `main_cli.py` changes identically to `main_debug.py`

---

## File Map

| File | Change |
|------|--------|
| `main_cli.py` | Rename `OUTPUT_DIR` → `COMMAND_RUNNER_DIR`, add `EXCEL_DIR`, remove `--port-util`/`--no-port-util` flags, add `--filename` flag, add threshold + filename prompts, call `write_combined_excel()` |
| `main_debug.py` | Identical changes to `main_cli.py` |
| `excel_generator.py` | Add `_compute_utilisation()`, add `write_combined_excel()`, keep `write_excel()` for standalone compatibility |
| `port_utilisation.py` | Add `write_utilisation_sheet(ws, results, threshold_days)` helper |
| `consolidate_report.py` | Replace string path construction with `Path.resolve()` |

---

### Task 1: Folder restructure and path constants

**Files:**
- Modify: `main_cli.py`
- Modify: `main_debug.py`
- Modify: `consolidate_report.py`
- Modify: `port_utilisation.py`

**Interfaces:**
- Produces: `COMMAND_RUNNER_DIR = "command_runner_outputs"` and `EXCEL_DIR = "excel_reports"` constants in `main_cli.py` and `main_debug.py`; Tasks 2 and 3 rely on `EXCEL_DIR`

- [ ] **Step 1: Update constants and path construction in `main_cli.py`**

Replace the `OUTPUT_DIR` constant and all its usages:

```python
# Replace this at the top of main_cli.py:
OUTPUT_DIR = "output"

# With:
COMMAND_RUNNER_DIR = "command_runner_outputs"
EXCEL_DIR = "excel_reports"
```

In `execute_on_devices()`, replace all `OUTPUT_DIR` references:
```python
# Old (two places):
Path(OUTPUT_DIR).mkdir(exist_ok=True)
filename = str(Path(OUTPUT_DIR) / f"command_output_{hostname}_{session_timestamp}.txt")

# New:
cmd_dir = Path(COMMAND_RUNNER_DIR).resolve()
cmd_dir.mkdir(exist_ok=True)
filename = str(cmd_dir / f"command_output_{hostname}_{session_timestamp}.txt")
```

In `parse_and_generate_excel()`, replace `OUTPUT_DIR`:
```python
# Old:
Path(OUTPUT_DIR).mkdir(exist_ok=True)
excel_filename = str(Path(OUTPUT_DIR) / f"port-information-{date_str}.xlsx")

# New (just the mkdir — filename construction moves to Task 3):
excel_dir = Path(EXCEL_DIR).resolve()
excel_dir.mkdir(exist_ok=True)
```

In `print_dry_run_summary()`, update the output_dir display:
```python
# The function already receives output_dir as a parameter — no change needed
# to the signature, but callers in main() will pass EXCEL_DIR instead of OUTPUT_DIR
```

In `main()`, fix the `global OUTPUT_DIR` override to use the new names:
```python
# Old:
global OUTPUT_DIR
OUTPUT_DIR = args.output_dir

# New:
global COMMAND_RUNNER_DIR, EXCEL_DIR
COMMAND_RUNNER_DIR = args.output_dir if args.output_dir != "output" else COMMAND_RUNNER_DIR
```

Actually — the `--output-dir` arg was a catch-all. Split it: rename `--output-dir` to `--command-runner-dir` and add `--excel-dir`. Update `parse_args()`:
```python
# Replace:
parser.add_argument("--output-dir", default="output", ...)

# With:
parser.add_argument("--command-runner-dir", default="command_runner_outputs",
                    help="Directory for raw command runner output files (default: command_runner_outputs/)")
parser.add_argument("--excel-dir", default="excel_reports",
                    help="Directory for Excel report output (default: excel_reports/)")
```

And in `main()`, update the global override:
```python
global COMMAND_RUNNER_DIR, EXCEL_DIR
COMMAND_RUNNER_DIR = args.command_runner_dir
EXCEL_DIR = args.excel_dir
```

Update `print_dry_run_summary()` call to pass `EXCEL_DIR`:
```python
# Old:
print_dry_run_summary(selected, DNAC_COMMANDS, session_timestamp, OUTPUT_DIR)

# New:
print_dry_run_summary(selected, DNAC_COMMANDS, session_timestamp, EXCEL_DIR)
```

- [ ] **Step 2: Apply identical changes to `main_debug.py`**

Repeat all changes from Step 1 in `main_debug.py`. The constants, argparse args, global override, and function body changes are identical.

- [ ] **Step 3: Fix path construction in `consolidate_report.py`**

In `consolidate()`, replace the output path default:
```python
# Old:
output_path = str(in_path.with_name(f"{in_path.stem}-consolidated-{stamp}.xlsx"))

# New (resolve input path, write output to excel_reports/ if it exists, else alongside input):
in_path = Path(input_path).resolve()
if output_path is None:
    stamp = datetime.now().strftime("%Y-%m-%d-%H-%M")
    excel_dir = Path("excel_reports").resolve()
    if excel_dir.is_dir():
        output_path = str(excel_dir / f"{in_path.stem}-consolidated-{stamp}.xlsx")
    else:
        output_path = str(in_path.parent / f"{in_path.stem}-consolidated-{stamp}.xlsx")
```

Replace `in_path = Path(input_path)` (existing line 126) with:
```python
in_path = Path(input_path).resolve()
```

- [ ] **Step 4: Fix path construction in `port_utilisation.py`**

In `analyse_workbook()`, replace `in_path = Path(wb_path)` with:
```python
in_path = Path(wb_path).resolve()
```

In `write_summary_excel()`, when `output_path is None`:
```python
# Old:
output_path = f"port_utilisation_summary_{stamp}.xlsx"

# New:
excel_dir = Path("excel_reports").resolve()
if excel_dir.is_dir():
    output_path = str(excel_dir / f"port_utilisation_summary_{stamp}.xlsx")
else:
    output_path = f"port_utilisation_summary_{stamp}.xlsx"
```

- [ ] **Step 5: Verify syntax**

```bash
cd /home/nickjennion/ai/cheat
python3 -m py_compile main_cli.py main_debug.py consolidate_report.py port_utilisation.py
echo "All compile OK"
```

Expected: `All compile OK`

- [ ] **Step 6: Commit**

```bash
git add main_cli.py main_debug.py consolidate_report.py port_utilisation.py
git commit -m "refactor: rename output/ to command_runner_outputs/, add excel_reports/ dir, use Path.resolve() throughout"
```

---

### Task 2: Add `write_utilisation_sheet()` and `write_combined_excel()`

**Files:**
- Modify: `port_utilisation.py` — add `write_utilisation_sheet(ws, results, threshold_days)`
- Modify: `excel_generator.py` — add `_compute_utilisation()`, `write_combined_excel()`

**Interfaces:**
- Consumes: `write_excel_sheet(ws, records, stack_members)` from `excel_generator.py` (unchanged)
- Consumes: `is_copper_port(iface)` from `port_utilisation.py` (unchanged)
- Consumes: `parse_duration_days(value)` from `time_utils.py` (unchanged)
- Produces: `write_utilisation_sheet(ws, results, threshold_days) -> None` in `port_utilisation.py`
- Produces: `write_combined_excel(devices_data, threshold_days, outpath) -> tuple[bool, str]` in `excel_generator.py`
- Task 3 calls `write_combined_excel()` and removes the `write_excel()` call from `main_cli.py`

- [ ] **Step 1: Add `write_utilisation_sheet()` to `port_utilisation.py`**

Add this function after `write_summary_excel()`. It writes the same data to an existing worksheet instead of creating a new workbook:

```python
def write_utilisation_sheet(ws, results: dict, threshold_days: int) -> None:
    """Write port utilisation summary to an existing openpyxl worksheet."""
    headers = ["Switch/Stack", "In Use", "Idle", "Total", "% In Use", "Threshold (days)"]
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = openpyxl.styles.Font(bold=True, color="FFFFFFFF", name="Arial", size=10)
        cell.fill = openpyxl.styles.PatternFill("solid", start_color="FF2B579A")
        cell.alignment = openpyxl.styles.Alignment(horizontal="center", vertical="center")

    col_widths = {"A": 40, "B": 12, "C": 12, "D": 12, "E": 14, "F": 16}
    for col_letter, width in col_widths.items():
        ws.column_dimensions[col_letter].width = width

    grand_in_use = 0
    grand_idle = 0
    row = 2

    for switch in sorted(results.keys()):
        in_use, idle = results[switch]
        total = in_use + idle
        grand_in_use += in_use
        grand_idle += idle
        pct = (in_use / total) if total > 0 else 0.0

        ws.cell(row=row, column=1, value=switch)
        ws.cell(row=row, column=2, value=in_use)
        ws.cell(row=row, column=3, value=idle)
        ws.cell(row=row, column=4, value=total)
        pct_cell = ws.cell(row=row, column=5, value=pct)
        pct_cell.number_format = "0.0%"
        ws.cell(row=row, column=6, value=threshold_days)
        row += 1

    grand_total = grand_in_use + grand_idle
    grand_pct = (grand_in_use / grand_total) if grand_total > 0 else 0.0

    for col, val in enumerate(
        ["TOTAL", grand_in_use, grand_idle, grand_total, grand_pct, threshold_days], start=1
    ):
        cell = ws.cell(row=row, column=col, value=val)
        cell.font = openpyxl.styles.Font(bold=True, name="Arial", size=10)
        cell.fill = openpyxl.styles.PatternFill("solid", start_color="FFE2E2E2")

    ws.cell(row=row, column=5).number_format = "0.0%"

    thin_border = openpyxl.styles.Border(
        bottom=openpyxl.styles.Side(style="thin", color="FFB0B0B0"),
        right=openpyxl.styles.Side(style="thin", color="FFB0B0B0"),
    )
    for r in range(1, row + 1):
        for c in range(1, 7):
            ws.cell(row=r, column=c).border = thin_border

    ws.freeze_panes = "A2"
```

- [ ] **Step 2: Verify `write_utilisation_sheet()` produces correct output**

```python
# Run from /home/nickjennion/ai/cheat
python3 -c "
import openpyxl
from port_utilisation import write_utilisation_sheet
wb = openpyxl.Workbook()
ws = wb.active
ws.title = 'Port Utilisation'
results = {'switch-a': (10, 5), 'switch-b': (20, 2)}
write_utilisation_sheet(ws, results, 42)
wb.save('/tmp/test_util_sheet.xlsx')
wb2 = openpyxl.load_workbook('/tmp/test_util_sheet.xlsx')
ws2 = wb2.active
assert ws2.cell(row=1, column=1).value == 'Switch/Stack'
assert ws2.cell(row=2, column=1).value == 'switch-a'
assert ws2.cell(row=2, column=2).value == 10
assert ws2.cell(row=4, column=1).value == 'TOTAL'
assert ws2.cell(row=4, column=2).value == 30
print('write_utilisation_sheet: OK')
"
```

Expected: `write_utilisation_sheet: OK`

- [ ] **Step 3: Add `_compute_utilisation()` and `write_combined_excel()` to `excel_generator.py`**

Add these imports at the top of `excel_generator.py` (after existing imports):
```python
from port_utilisation import is_copper_port, write_utilisation_sheet
from time_utils import parse_duration_days
```

Add `_compute_utilisation()` as a module-private helper (before `write_combined_excel`):
```python
def _compute_utilisation(
    devices_data: dict,
    threshold_days: int
) -> dict[str, tuple[int, int]]:
    """Compute port utilisation from in-memory records. Returns {hostname: (in_use, idle)}."""
    results: dict[str, tuple[int, int]] = {}
    for hostname, (records, _) in devices_data.items():
        in_use = 0
        idle = 0
        for rec in records:
            if not is_copper_port(rec.iface):
                continue
            days = parse_duration_days(str(rec.last_input).strip() if rec.last_input else "")
            if days is not None and days < threshold_days:
                in_use += 1
            else:
                idle += 1
        if in_use + idle > 0:
            results[hostname] = (in_use, idle)
    return results
```

Add `write_combined_excel()` after `write_excel()`:
```python
def write_combined_excel(
    devices_data: dict[str, tuple[list[InterfaceRecord], dict[int, StackMember]]],
    threshold_days: int,
    outpath: str
) -> tuple[bool, str]:
    """Write single combined workbook: All Ports → Port Utilisation → per-stack tabs.

    Sheet order:
      Sheet 1 "All Ports"         — every port from every device on one sheet
      Sheet 2 "Port Utilisation"  — copper-port utilisation summary
      Sheets 3-N <hostname>       — one tab per device/stack
    """
    if not devices_data:
        return False, "No device data to write"

    try:
        wb = openpyxl.Workbook()
        wb.remove(wb.active)

        # Sheet 1: All Ports — consolidate all records
        all_records = [rec for records, _ in devices_data.values() for rec in records]
        ws_all = wb.create_sheet(title="All Ports")
        write_excel_sheet(ws_all, all_records, {})

        # Sheet 2: Port Utilisation
        util_results = _compute_utilisation(devices_data, threshold_days)
        ws_util = wb.create_sheet(title="Port Utilisation")
        if util_results:
            write_utilisation_sheet(ws_util, util_results, threshold_days)
        else:
            ws_util.cell(row=1, column=1, value="No copper port data found")

        # Sheets 3-N: per-stack
        total_records = len(all_records)
        total_devices = 0
        for hostname, (records, stack_members) in devices_data.items():
            if not records:
                continue
            sheet_name = hostname[:31]
            if sheet_name in wb.sheetnames:
                for i in range(2, 100):
                    candidate = f"{sheet_name[:27]}_{i}"
                    if candidate not in wb.sheetnames:
                        sheet_name = candidate
                        break
            ws = wb.create_sheet(title=sheet_name)
            write_excel_sheet(ws, records, stack_members)
            total_devices += 1

        wb.save(outpath)
        return True, (
            f"✓ Saved: {outpath} "
            f"({total_records} interfaces across {total_devices} device(s))"
        )

    except Exception as e:
        return False, f"✗ Failed to write Excel: {e}"
```

- [ ] **Step 4: Verify `write_combined_excel()` produces correct sheet structure**

```python
python3 -c "
import openpyxl
from interface_parser import InterfaceRecord, StackMember
from excel_generator import write_combined_excel

# Minimal fake record
r = InterfaceRecord()
r.switch = 'sw1'
r.iface = 'Gi1/0/1'
r.state = 'connected'
r.last_input = '2d3h'
r.suspect = 'YES'

devices_data = {'sw1': ([r], {})}
ok, msg = write_combined_excel(devices_data, 42, '/tmp/test_combined.xlsx')
assert ok, msg

wb = openpyxl.load_workbook('/tmp/test_combined.xlsx')
sheets = wb.sheetnames
assert sheets[0] == 'All Ports', f'Expected All Ports first, got {sheets}'
assert sheets[1] == 'Port Utilisation', f'Expected Port Utilisation second, got {sheets}'
assert sheets[2] == 'sw1', f'Expected sw1 third, got {sheets}'
print(f'Sheet order correct: {sheets}')
print(f'write_combined_excel: OK — {msg}')
"
```

Expected:
```
Sheet order correct: ['All Ports', 'Port Utilisation', 'sw1']
write_combined_excel: OK — ✓ Saved: /tmp/test_combined.xlsx (1 interfaces across 1 device(s))
```

- [ ] **Step 5: Commit**

```bash
git add port_utilisation.py excel_generator.py
git commit -m "feat: add write_combined_excel() — single workbook with All Ports, Port Utilisation, per-stack tabs"
```

---

### Task 3: Prompts, argparse cleanup, and wire up in `main_cli.py` / `main_debug.py`

**Files:**
- Modify: `main_cli.py`
- Modify: `main_debug.py`

**Interfaces:**
- Consumes: `write_combined_excel(devices_data, threshold_days, outpath)` from Task 2
- Consumes: `EXCEL_DIR` constant from Task 1
- The `write_excel` import from `excel_generator` is no longer called from `main_cli.py` — remove it

- [ ] **Step 1: Update imports in `main_cli.py`**

```python
# Remove:
from excel_generator import write_excel

# Add:
from excel_generator import write_combined_excel
```

Remove the `port_utilisation` imports (no longer called from `main_cli.py` directly — `write_combined_excel` handles it internally):
```python
# Remove these three lines:
from port_utilisation import analyse_workbook, print_summary, write_summary_excel
```

- [ ] **Step 2: Remove `--port-util` / `--no-port-util` flags, add `--filename`, update `--port-util-threshold` default**

In `parse_args()`:

```python
# Remove these two arguments entirely:
parser.add_argument("--port-util", action="store_true", default=None, ...)
parser.add_argument("--no-port-util", action="store_false", dest="port_util", ...)

# Change --port-util-threshold default from 42 to None (None = prompt):
parser.add_argument("--port-util-threshold", type=int, default=None,
                    help="Port utilisation threshold in days (default: prompt, 42 if not specified)")

# Add --filename:
parser.add_argument("--filename",
                    help="Excel filename prefix (default: prompt for 'port-information')")
```

- [ ] **Step 3: Add threshold and filename prompts in `main()`, after device selection**

In `main()`, after device selection (after the `if not selected: continue` block) and before the dry-run check, add:

```python
# Threshold prompt (skip if --port-util-threshold provided)
if args.port_util_threshold is not None:
    threshold = args.port_util_threshold
else:
    raw = input("\nPort utilisation threshold in days [42]: ").strip()
    threshold = int(raw) if raw.isdigit() else 42

# Filename prefix prompt (skip if --filename provided or in batch/one-shot mode)
if args.filename:
    filename_prefix = args.filename
else:
    raw = input("Excel filename prefix [port-information]: ").strip()
    filename_prefix = raw if raw else "port-information"
```

Update the dry-run summary call to include the filename:
```python
print_dry_run_summary(selected, DNAC_COMMANDS, session_timestamp, EXCEL_DIR, filename_prefix)
```

Update `print_dry_run_summary()` signature to accept and display `filename_prefix`:
```python
def print_dry_run_summary(devices, commands, timestamp, output_dir, filename_prefix="port-information"):
    ...
    date_str = datetime.strptime(timestamp, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d-%H-%M")
    print(f"  Excel report would be: {output_dir}/{filename_prefix}-{date_str}.xlsx")
    ...
```

- [ ] **Step 4: Update `parse_and_generate_excel()` signature and body**

```python
def parse_and_generate_excel(
    outputs: dict[str, str],
    session_timestamp: str,
    threshold_days: int,
    filename_prefix: str
) -> tuple[bool, Optional[str]]:
    """Parse command outputs and generate combined Excel report."""
    if not outputs:
        print("✗ No command outputs to parse")
        return False, None

    print("\n" + "=" * 60)
    print("Parsing outputs and generating Excel...")
    print("=" * 60)

    devices_data = {}
    parse_failures = []

    for hostname, output_text in outputs.items():
        print(f"\nParsing {hostname}...", end=" ")
        try:
            records, stack_members = parse_output(output_text, hostname)
            if not records:
                print(f"⚠ No interfaces found (parsing may have failed)")
                parse_failures.append(hostname)
                continue
            devices_data[hostname] = (records, stack_members)
            print(f"✓ {len(records)} interfaces")
        except Exception as e:
            print(f"✗ Parsing error: {e}")
            parse_failures.append(hostname)

    if parse_failures:
        print(f"\n⚠ Parsing failed or found no data on: {', '.join(parse_failures)}")

    if not devices_data:
        print("✗ No parsed data to write to Excel")
        return False, None

    excel_dir = Path(EXCEL_DIR).resolve()
    excel_dir.mkdir(exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d-%H-%M")
    excel_filename = str(excel_dir / f"{filename_prefix}-{date_str}.xlsx")

    success, message = write_combined_excel(devices_data, threshold_days, excel_filename)
    print(f"\n{message}")
    return success, excel_filename if success else None
```

- [ ] **Step 5: Update the call site in `main()`**

```python
# Old:
outputs = execute_on_devices(selected, client, session_timestamp)
if outputs:
    success, excel_path = parse_and_generate_excel(outputs, session_timestamp)

    if success and excel_path:
        do_port_util = args.port_util
        if do_port_util is None:
            choice = input("\nRun port utilisation analysis? [Y/n]: ").strip().lower()
            do_port_util = choice in ('', 'y', 'yes')
        if do_port_util:
            threshold = args.port_util_threshold
            ok, msg, results = analyse_workbook(excel_path, threshold)
            print(msg)
            if ok and results:
                print_summary(results, threshold)
                ok2, msg2 = write_summary_excel(results, threshold)
                print(msg2)

    if args.filter and args.batch:
        break

# New:
outputs = execute_on_devices(selected, client, session_timestamp)
if outputs:
    success, excel_path = parse_and_generate_excel(
        outputs, session_timestamp, threshold, filename_prefix
    )

if args.filter and args.batch:
    break
```

- [ ] **Step 6: Remove stale `args.port_util` reference in `main()`**

Search `main()` for any remaining references to `args.port_util` or `args.no_port_util` and remove them. Run:

```bash
grep -n "port_util" /home/nickjennion/ai/cheat/main_cli.py
```

Expected: only `args.port_util_threshold` references remain.

- [ ] **Step 7: Apply identical changes to `main_debug.py`**

Repeat Steps 1–6 for `main_debug.py`. The changes are identical.

- [ ] **Step 8: Verify syntax and CLI help**

```bash
cd /home/nickjennion/ai/cheat
python3 -m py_compile main_cli.py main_debug.py
python3 main_cli.py --help
```

Expected: `--port-util` and `--no-port-util` are gone; `--port-util-threshold`, `--filename`, `--command-runner-dir`, `--excel-dir` are present.

```bash
grep -c "port.util" <(python3 main_cli.py --help) || true
```

Expected: 1 (only `--port-util-threshold` remains).

- [ ] **Step 9: Verify end-to-end path creation**

```python
python3 -c "
import sys, os
os.chdir('/tmp')  # simulate running from a different directory
sys.path.insert(0, '/home/nickjennion/ai/cheat')
from pathlib import Path
# Simulate what parse_and_generate_excel does
EXCEL_DIR = 'excel_reports'
excel_dir = Path(EXCEL_DIR).resolve()
print(f'Excel dir would resolve to: {excel_dir}')
# Verify no CWD assumption — path is absolute
assert excel_dir.is_absolute(), 'Path is not absolute!'
print('Path is absolute: OK')
"
```

Expected: prints an absolute path, `Path is absolute: OK`.

- [ ] **Step 10: Commit**

```bash
git add main_cli.py main_debug.py
git commit -m "feat: combined workbook wired into main workflow — threshold + filename prompts, remove port-util flags"
```

---

## Execution Order

| Task | Depends On | Risk |
|------|-----------|------|
| Task 1 (folders + paths) | None | Low — constants and path construction only |
| Task 2 (combined workbook) | None | Medium — new functions, openpyxl sheet ordering |
| Task 3 (main_cli.py wiring) | Tasks 1 and 2 | Medium — touches interactive flow |

Tasks 1 and 2 are independent and can be developed in parallel. Task 3 depends on both.
