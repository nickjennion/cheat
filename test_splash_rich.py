"""Regression test for the Rich splash Cisco logo alignment.

The 9-row bar logo must render on a single shared column grid: because the top
rows contain only the two tall bars and the bottom rows span all nine, centering
each line independently makes the bars zig-zag. Every logo row must therefore
share the same horizontal ink midpoint (the whole block centred as one unit).
"""


import pytest

DESIGNS = ["burger", "lockup", "stacked", "generic"]


def _render_text(design="burger", width=112, title="CHEAT"):
    from rich.console import Console
    import splash_rich
    con = Console(record=True, width=width, force_terminal=True)
    splash_rich.render(con, title, "sub", "Menu 1", ["1) A"], design=design)
    return con.export_text()


def _bar_rows(text):
    return [ln for ln in text.splitlines() if "█" in ln]


def _ink_midpoint(line):
    # Measure the Cisco bars only: the co-brand HU burger mark shares these
    # lines to the left, so its dots must not count toward the bars' column-grid
    # check.
    inks = [i for i, ch in enumerate(line) if ch == "█"]
    return (inks[0] + inks[-1]) / 2


@pytest.mark.parametrize("design", DESIGNS)
def test_logo_bars_share_one_column_grid(design):
    rows = _bar_rows(_render_text(design))
    assert len(rows) == 9, f"{design}: expected 9 bar rows, got {len(rows)}"
    midpoints = {_ink_midpoint(r) for r in rows}
    assert len(midpoints) == 1, f"{design}: bars not aligned: {midpoints}"


@pytest.mark.parametrize("design", ["burger", "lockup", "stacked"])
def test_cobrand_designs_show_hu_tag(design):
    assert "Hamburger University" in _render_text(design)


def test_generic_has_no_hu_tag():
    assert "Hamburger University" not in _render_text("generic")


def test_invalid_design_falls_back_to_burger():
    # Load-bearing: a corrupt SPLASH_DESIGN in prefs.env must not crash the splash.
    assert _render_text("banana") == _render_text("burger")


def test_stacked_wordmark_hangs_below_the_bars():
    # The stacked lockup is taller than the 9 bar rows: HAMBURGER/UNIVERSITY sit
    # on lines that carry no Cisco bar.
    lines = _render_text("stacked", width=200).splitlines()
    uni = [ln for ln in lines if "UNIVERSITY" in ln]
    assert uni and "█" not in uni[0]


@pytest.mark.parametrize("design", ["burger", "lockup", "stacked"])
def test_cobrand_designs_render_the_hu_burger(design):
    assert "●" in _render_text(design)  # the halftone-dot burger mark


def test_generic_has_no_burger_dots():
    assert "●" not in _render_text("generic")


def test_narrow_terminal_degrades_without_folding():
    # At 80 columns the 87-wide burger mark would fold; the width guard must
    # step it down to a design that still renders its 9 bar rows intact.
    rows = _bar_rows(_render_text("burger", width=80))
    assert len(rows) == 9
    midpoints = {_ink_midpoint(r) for r in rows}
    assert len(midpoints) == 1


def test_fit_design_degrades_by_width():
    import splash_rich
    assert splash_rich._fit_design("burger", 120) == "burger"
    assert splash_rich._fit_design("burger", 80) == "lockup"
    assert splash_rich._fit_design("stacked", 80) == "lockup"
    assert splash_rich._fit_design("lockup", 70) == "generic"
    assert splash_rich._fit_design("burger", 40) == "generic"
