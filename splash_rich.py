"""
Rich-rendered CHEAT splash — a 'sparkled up' alternative to the flat splash.py.

Faithful to the terminal: truecolor gradients (per-character), a rounded menu
panel, and dim/bright hierarchy. Falls back gracefully — callers can keep the
plain splash.py if Rich isn't available.
"""

from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text

# Cisco DNA Center palette.
DEEP = (1, 79, 116)      # Cisco blue — the screen background
CYAN = (34, 211, 238)    # bright accent
ICE = (186, 230, 253)    # near-white highlight
WHITE = (255, 255, 255)

# The 9-bar Cisco "bridge" mark (shared silhouette with splash.py).
BARS = [
    "                ███                             ███                ",
    "                ███                             ███                ",
    "        ▄▄▄     ███     ▄▄▄             ▄▄▄     ███     ▄▄▄        ",
    "        ███     ███     ███             ███     ███     ███        ",
    "▄▄▄     ███     ███     ███     ▄▄▄     ███     ███     ███     ▄▄▄",
    "███     ███     ███     ███     ███     ███     ███     ███     ███",
    "███     ███     ███     ███     ███     ███     ███     ███     ███",
    "▀▀▀     ▀▀▀     ███     ▀▀▀     ▀▀▀     ▀▀▀     ███     ▀▀▀     ▀▀▀",
    "                ███                             ███                ",
]


def _rgb(t):
    """Format an RGB tuple as a Rich colour string (no spaces)."""
    return f"rgb({t[0]},{t[1]},{t[2]})"


def _lerp(a, b, t):
    """Linear-interpolate two RGB tuples at fraction t in [0, 1]."""
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _hgradient(s, start, end):
    """Text with a left-to-right per-character colour gradient."""
    out = Text()
    n = max(len(s) - 1, 1)
    for i, ch in enumerate(s):
        r, g, b = _lerp(start, end, i / n)
        out.append(ch, style=f"bold rgb({r},{g},{b})")
    return out


def _bars(top, bottom):
    """The Cisco mark with a top-to-bottom vertical colour gradient.

    No per-line justify: each BARS row has different left/right padding (top rows
    hold only the two tall bars, bottom rows span all nine), so centring lines
    independently makes the bars zig-zag. The caller centres the block as one
    unit via Align.center, which keeps every bar on a shared column grid.
    """
    out = Text()
    n = max(len(BARS) - 1, 1)
    for i, line in enumerate(BARS):
        r, g, b = _lerp(top, bottom, i / n)
        out.append(line + "\n", style=f"rgb({r},{g},{b})")
    return out


# Hamburger University marks, echoed as halftone-dot diamonds. A row of d dots is
# "● ● …" so widths run 1,3,5,… — each row centred in a fixed field keeps every
# row on one shared column grid.
def _diamond_rows(half, field):
    """Diamond of dots `2*half+1` rows tall, each row centred in `field`."""
    return [("● " * ((2 * half + 1) - 2 * abs(i - half))).rstrip().center(field)
            for i in range(2 * half + 1)]


def _vu_diamond_rows():
    """Design B: a large 9-row HU diamond (widest row is 9 dots = 17 cells)."""
    return _diamond_rows(half=4, field=17)


def _vu_lockup_rows():
    """Compact HU badge — small diamond over the wordmark, 9 rows (field 10)."""
    field = 10
    dia = _diamond_rows(half=2, field=field)          # 5 rows: 1,3,5,3,1
    words = ["HAMBURGER".center(field), "UNIVERSITY".center(field)]
    return ["".center(field), *dia, *words, "".center(field)]  # 1+5+2+1 = 9


def _vu_stacked_rows():
    """Full HU lockup — large diamond over the wordmark, 11 rows (field 17)."""
    field = 17
    dia = _diamond_rows(half=4, field=field)          # 9 rows: 1,3,5,7,9,7,5,3,1
    words = ["HAMBURGER".center(field), "UNIVERSITY".center(field)]
    return [*dia, *words]                             # 9 + 2 = 11


_BAR_W = len(BARS[0])  # every Cisco bar row is this wide


def _compose_logo(left_rows, field, top, bottom, centre=None):
    """Join a left-hand HU badge with the Cisco bars on one shared column grid.

    Each line is [HU badge row, `field` wide] + gap + [one Cisco bar row]. The
    bars are all appended at the same offset, so the Cisco mark keeps its column
    grid while the HU mark sits to its left. When the badge is taller than the
    bars (the stacked lockup), the bars top-align and blank bar rows pad the rest
    so the wordmark hangs below. Dots take a vertical ICE→CYAN gradient (centre
    dot bright white); wordmark letters render white.
    """
    n = max(len(BARS) - 1, 1)
    out = Text()
    for i in range(max(len(left_rows), len(BARS))):
        left = left_rows[i] if i < len(left_rows) else " " * field
        vr, vg, vb = _lerp(ICE, CYAN, min(i, n) / n)
        for ci, ch in enumerate(left):
            if ch == " ":
                out.append(ch)
            elif ch == "●":
                if (i, ci) == centre:
                    out.append(ch, style=f"bold {_rgb(WHITE)}")
                else:
                    out.append(ch, style=f"rgb({vr},{vg},{vb})")
            else:  # HU wordmark letters
                out.append(ch, style=f"bold {_rgb(WHITE)}")
        out.append("   ")  # gap between the two marks
        if i < len(BARS):
            br, bg, bb = _lerp(top, bottom, i / n)
            out.append(BARS[i], style=f"rgb({br},{bg},{bb})")
        else:
            out.append(" " * _BAR_W)
        out.append("\n")
    return out


# Minimum terminal width each design needs to render without the bars folding
# (HU field + 3-space gap + bar width, or just the bars for "generic").
_DESIGN_WIDTH = {"diamond": 87, "stacked": 87, "lockup": 80, "generic": _BAR_W}


def _fit_design(design, width):
    """Degrade to the richest design that fits `width` (keeps the splash intact).

    A too-wide logo makes Rich fold the bar rows and the mark shatters, so on a
    narrow terminal step diamond/stacked → lockup → generic rather than break.
    """
    if width >= _DESIGN_WIDTH.get(design, _DESIGN_WIDTH["diamond"]):
        return design
    for fallback in ("lockup", "generic"):
        if width >= _DESIGN_WIDTH[fallback]:
            return fallback
    return "generic"  # least-bad on very narrow terminals


def _logo(design, top, bottom):
    """Build the logo block for a splash design.

    "diamond" — HU diamond mark beside the Cisco bars (co-brand).
    "lockup"  — compact HU diamond+wordmark badge beside the bars (co-brand).
    "stacked" — full HU lockup (large diamond over wordmark) beside the bars.
    "generic" — Cisco bars only (original, no HU branding).
    """
    if design == "generic":
        return _bars(top, bottom)
    if design == "lockup":
        return _compose_logo(_vu_lockup_rows(), 10, top, bottom, centre=(3, 4))
    if design == "stacked":
        return _compose_logo(_vu_stacked_rows(), 17, top, bottom, centre=(4, 8))
    return _compose_logo(_vu_diamond_rows(), 17, top, bottom, centre=(4, 8))


def render(console, title, subtitle, menu_header, options, design="diamond"):
    """Draw the sparkled splash to `console`, over the Cisco-blue background.

    `design` selects the branding: "diamond" / "lockup" / "stacked" co-brand with
    Hamburger University (see `_logo`); "generic" is the original Cisco-only splash.

    Every element is printed with an `on rgb(DEEP)` base style so the blue fills
    behind the text and the centering padding — matching the app's themed screen.
    """
    # Fall back to a narrower design if the terminal can't fit the chosen one,
    # so the logo never folds into a broken mess on an 80-column screen.
    design = _fit_design(design, console.width)
    # Bars stay in the light half of the palette so they read on the blue bg;
    # the HU mark (if any) sits to their left for the co-brand lockup.
    logo = _logo(design, WHITE, CYAN)
    # Co-brand tag rides the same cyan→white gradient as the Cisco wordmark.
    tagline = "CISCO  ·  DNA CENTER"
    if design != "generic":
        tagline += "     ×  Hamburger University"
    wordmark = _hgradient(tagline, CYAN, WHITE)
    wordmark.justify = "center"

    hero = _hgradient("  ".join(title), CYAN, WHITE)  # letter-spaced for weight
    hero.justify = "center"
    sub = Text(subtitle, style="italic rgb(150,200,225)", justify="center")

    # Menu options: bright accent key + label, inside a rounded panel.
    body = Text(justify="left")
    for opt in options:
        key, _, label = opt.partition(")")
        if label:
            body.append(f" {key.strip()} ", style=f"bold {_rgb(CYAN)}")
            body.append(f" {label.strip()}\n", style=_rgb(ICE))
        else:
            body.append(opt + "\n")
    menu = Panel(
        body,
        title=f"[bold {_rgb(WHITE)}]{menu_header}[/]",
        border_style=_rgb(CYAN),
        padding=(1, 4),
        width=52,
    )

    splash = Group(
        Text(""),
        Align.center(logo),
        Align.center(wordmark),
        Text(""),
        Align.center(hero),
        Align.center(sub),
        Text(""),
        Align.center(menu),
        Text(""),
    )
    console.print(splash, style=f"on {_rgb(DEEP)}")


if __name__ == "__main__":  # quick preview of every design: `python3 splash_rich.py`
    import sys

    con = Console()
    opts = [
        "1) Use dnac.env",
        "2) Enter manually · remember",
        "3) Enter manually · forget",
        "4) View dnac.env",
        "5) Options",
    ]
    # One arg previews a single design; no arg cycles them all for comparison.
    designs = sys.argv[1:] or ["diamond", "lockup", "stacked", "generic"]
    for d in designs:
        con.rule(f"[bold]design = {d}[/]")
        render(con, "CHEAT", "Cisco Homogeneous Environment Awareness Tool",
               "Menu 1 · Credentials", opts, design=d)
