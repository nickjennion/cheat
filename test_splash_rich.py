"""Regression test for the Rich splash Cisco logo alignment.

The 9-row bar logo must render on a single shared column grid: because the top
rows contain only the two tall bars and the bottom rows span all nine, centering
each line independently makes the bars zig-zag. Every logo row must therefore
share the same horizontal ink midpoint (the whole block centred as one unit).
"""


def _logo_rows(title="CHEAT"):
    from rich.console import Console
    import splash_rich
    con = Console(record=True, width=112, force_terminal=True)
    splash_rich.render(con, title, "sub", "Menu 1", ["1) A"])
    return [ln for ln in con.export_text().splitlines() if "█" in ln]


def _ink_midpoint(line):
    inks = [i for i, ch in enumerate(line) if ch != " "]
    return (inks[0] + inks[-1]) / 2


def test_logo_bars_share_one_column_grid():
    rows = _logo_rows()
    assert len(rows) == 9  # the nine bar rows of the Cisco mark
    midpoints = {_ink_midpoint(r) for r in rows}
    assert len(midpoints) == 1, f"logo bars are not vertically aligned: {midpoints}"
