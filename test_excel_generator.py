import openpyxl

from excel_generator import write_excel_sheet
from interface_parser import InterfaceRecord


def test_link_change_column_absent_when_no_values():
    wb = openpyxl.Workbook()
    ws = wb.active
    rec = InterfaceRecord(switch="sw-a", iface="Gi1/0/1", state="connected")
    write_excel_sheet(ws, [rec], {})
    headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
    assert "Last Link Change" not in headers


def test_link_change_column_present_and_populated():
    wb = openpyxl.Workbook()
    ws = wb.active
    rec = InterfaceRecord(
        switch="sw-a", iface="Gi1/0/1", state="connected", last_link_change="2h13m"
    )
    write_excel_sheet(ws, [rec], {})
    headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
    assert headers[-1] == "Last Link Change"
    last_col = ws.max_column
    assert ws.cell(row=2, column=last_col).value == "2h13m"
