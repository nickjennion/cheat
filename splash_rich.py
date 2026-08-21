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


_BAR_W = len(BARS[0])  # every Cisco bar row is this wide
_DESIGN_WIDTH = {"generic": _BAR_W}


def _fit_design(design, width):
    """Return the Cisco-only design, including for legacy preference values."""
    return "generic"


def _logo(design, top, bottom):
    """Build the Cisco-only logo block.

    `design` remains accepted for compatibility with old callers and preference
    files, but no co-brand graphic is rendered.
    """
    return _bars(top, bottom)


def render(console, title, subtitle, menu_header, options, design="mark"):
    """Draw the sparkled splash to `console`, over the Cisco-blue background.

    `design` is retained as a compatibility argument; the splash is always
    rendered with the Cisco-only logo.

    Every element is printed with an `on rgb(DEEP)` base style so the blue fills
    behind the text and the centering padding — matching the app's themed screen.
    """
    # Fall back to a narrower design if the terminal can't fit the chosen one,
    # so the logo never folds into a broken mess on an 80-column screen.
    design = _fit_design(design, console.width)
    logo = _logo(design, WHITE, CYAN)
    tagline = "CISCO  ·  DNA CENTER"
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
        "1) Use Legacy DNAC",
        "2) Use New DNAC",
        "3) Enter manually · remember",
        "4) Enter manually · forget",
        "5) View credential files",
        "6) Options",
    ]
    # One arg previews a single design; no arg cycles them all for comparison.
    designs = sys.argv[1:] or ["generic"]
    for d in designs:
        con.rule(f"[bold]design = {d}[/]")
        render(con, "CHEAT", "Cisco Homogeneous Environment Awareness Tool",
               "Menu 1 · Credentials", opts, design=d)
