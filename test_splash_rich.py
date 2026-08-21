"""Regression tests for the Cisco-only Rich splash."""

from rich.console import Console

import splash_rich


def _render_text(width=112, title="CHEAT", design="generic"):
    con = Console(record=True, width=width, force_terminal=True)
    splash_rich.render(con, title, "sub", "Menu 1", ["1) A"], design=design)
    return con.export_text()


def _bar_rows(text):
    return [line for line in text.splitlines() if "█" in line]


def _ink_midpoint(line):
    inks = [i for i, ch in enumerate(line) if ch == "█"]
    return (inks[0] + inks[-1]) / 2


def test_logo_has_nine_aligned_cisco_rows():
    rows = _bar_rows(_render_text())
    assert len(rows) == 9
    assert len({_ink_midpoint(row) for row in rows}) == 1


def test_splash_contains_no_removed_co_branding():
    text = _render_text(width=200, design="mark")
    assert "Generic University" not in text
    assert "GENERIC" not in text
    assert "UNIVERSITY" not in text
    assert "●" not in text
    assert "Hamburger" not in text


def test_legacy_or_invalid_designs_render_cisco_only():
    expected = _render_text(width=200, design="generic")
    for design in ("mark", "lockup", "stacked", "banana"):
        assert _render_text(width=200, design=design) == expected


def test_fit_design_always_returns_generic():
    for design in ("mark", "lockup", "stacked", "generic", "banana"):
        assert splash_rich._fit_design(design, 40) == "generic"
        assert splash_rich._fit_design(design, 200) == "generic"


def test_narrow_terminal_keeps_bars_intact():
    rows = _bar_rows(_render_text(width=80))
    assert len(rows) == 9
    assert len({_ink_midpoint(row) for row in rows}) == 1
