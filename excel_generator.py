"""
Excel report generation for CHEAT UNPLUGGED.

Generates formatted Excel workbooks from parsed interface data.
One sheet per device with color-coded interface inventory.
"""

from typing import Optional
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from interface_parser import InterfaceRecord, StackMember, uptime_days
from port_utilisation import is_copper_port, write_utilisation_sheet
from time_utils import parse_duration_days


# ============================================================================
# Excel Configuration
# ============================================================================

HEADERS = [
    "Switch",
    "Stack Member",
    "Model",
    "SW Version",
    "Member Uptime (days)",
    "Interface",
    "Description",
    "State",
    "Protocol",
    "VLAN",
    "Counters In (Octets)",
    "Last Input",
    "Suspect (Has Had Traffic)",
    "CDP Neighbors",
]

COL_WIDTHS = [28, 13, 18, 12, 20, 12, 36, 14, 10, 8, 22, 14, 26, 30]

STATE_COLOURS = {
    "connected": "FFD4EDDA",
    "notconnect": "FFFFF3CD",
    "disabled": "FFE2E3E5",
    "err-disabled": "FFF8D7DA",
}

SUSPECT_COLOUR = "FFFFD700"
UPTIME_COLOUR = "FFFCE4D6"

UPTIME_THRESHOLD_DAYS = 42


# ============================================================================
# Styling Helpers
# ============================================================================

def get_header_styles():
    """Return styled components for header row."""
    font = Font(bold=True, color="FFFFFFFF", name="Arial", size=10)
    fill = PatternFill("solid", start_color="FF2B579A")
    align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    border = Border(
        bottom=Side(style="thin", color="FFB0B0B0"),
        right=Side(style="thin", color="FFB0B0B0"),
    )
    return font, fill, align, border


def get_data_styles():
    """Return styled components for data rows."""
    font = Font(name="Arial", size=10)
    align = Alignment(vertical="center")
    border = Border(
        bottom=Side(style="thin", color="FFB0B0B0"),
        right=Side(style="thin", color="FFB0B0B0"),
    )
    return font, align, border


# ============================================================================
# Sheet Writing
# ============================================================================

def write_excel_sheet(ws, records: list[InterfaceRecord], stack_members: dict[int, StackMember]) -> int:
    """
    Write parsed data to an Excel worksheet.
    Returns number of records written.
    """
    header_font, header_fill, header_align, header_border = get_header_styles()
    data_font, data_align, data_border = get_data_styles()

    # Write headers
    for col, (header, width) in enumerate(zip(HEADERS, COL_WIDTHS), start=1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = header_border
        ws.column_dimensions[get_column_letter(col)].width = width

    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "A2"

    # Write data rows
    for row_idx, rec in enumerate(records, start=2):
        days = uptime_days(rec.uptime)
        values = [
            rec.switch,
            rec.stack_member,
            rec.model,
            rec.sw_version,
            round(days, 1) if days is not None else "",
            rec.iface,
            rec.description,
            rec.state,
            rec.protocol,
            rec.vlan,
            rec.counters_in,
            rec.last_input,
            rec.suspect,
            rec.cdp_neighbors,
        ]

        state_key = rec.state.lower() if rec.state else ""
        row_colour = STATE_COLOURS.get(state_key, "FFFFFFFF")
        short_up = days is not None and days < UPTIME_THRESHOLD_DAYS

        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=row_idx, column=col, value=value)
            cell.font = data_font
            cell.alignment = data_align
            cell.border = data_border

            # Highlight suspect interfaces (gold)
            if col == 13 and value == "YES":
                cell.fill = PatternFill("solid", start_color=SUSPECT_COLOUR)
                cell.font = Font(name="Arial", size=10, bold=True)
            # Highlight short uptime (orange)
            elif col == 5 and short_up:
                cell.fill = PatternFill("solid", start_color=UPTIME_COLOUR)
                cell.font = Font(name="Arial", size=10, bold=True)
            else:
                cell.fill = PatternFill("solid", start_color=row_colour)

    ws.auto_filter.ref = ws.dimensions
    return len(records)


# ============================================================================
# Workbook Writing
# ============================================================================

def write_excel(
    devices_data: dict[str, tuple[list[InterfaceRecord], dict[int, StackMember]]],
    outpath: str
) -> tuple[bool, str]:
    """
    Write multi-sheet Excel workbook (one sheet per device).
    Returns (success: bool, message: str)
    """
    if not devices_data:
        return False, "No device data to write"

    try:
        wb = openpyxl.Workbook()
        wb.remove(wb.active)

        total_records = 0
        total_devices = 0

        for hostname, (records, stack_members) in devices_data.items():
            if not records:
                continue

            # Truncate hostname to 31 chars (Excel sheet name limit)
            sheet_name = hostname[:31]

            # Handle duplicate sheet names by appending suffix
            if sheet_name in wb.sheetnames:
                for i in range(2, 100):
                    test_name = f"{sheet_name[:27]}_{i}"
                    if test_name not in wb.sheetnames:
                        sheet_name = test_name
                        break

            ws = wb.create_sheet(title=sheet_name)
            count = write_excel_sheet(ws, records, stack_members)
            total_records += count
            total_devices += 1

        wb.save(outpath)
        msg = f"✓ Saved: {outpath} ({total_records} interfaces across {total_devices} devices)"
        return True, msg

    except Exception as e:
        return False, f"✗ Failed to write Excel: {e}"


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


def write_combined_excel(
    devices_data: dict[str, tuple[list[InterfaceRecord], dict[int, StackMember]]],
    threshold_days: int,
    outpath: str
) -> tuple[bool, str]:
    """Write single combined workbook: All Ports -> Port Utilisation -> per-stack tabs.

    Sheet order:
      Sheet 1 "All Ports"         -- every port from every device on one sheet
      Sheet 2 "Port Utilisation"  -- copper-port utilisation summary
      Sheets 3-N <hostname>       -- one tab per device/stack
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
