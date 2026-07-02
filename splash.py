"""
CHEAT splash rendering — Cisco DNA Center branding.

Pure layout only (returns a list of text lines); colour/theming is applied by
the caller. Shared by main_latest.py (the live app) and splash_preview.py.

The 9-bar Cisco "bridge" logo (S·M·T·M·S·M·T·M·S — two tall peaks) is measured
from the real mark: heights top% 52/30/0, baseline 84%, peaks to 100%. Half-block
glyphs (▄ ▀) give the bars rounded pill caps. Aspect ~3.7:1; logo line is 67 cols.
"""

WIDTH = 112

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

WORDMARK = "CISCO  ·  DNA CENTER"


def build_lines(title, subtitle, menu_header, options, width=WIDTH):
    """Return the framed splash as a list of lines (all exactly `width` wide).

    Layout: Cisco logo + wordmark centred at top, three-line gap, combined
    title/subtitle on one line, menu header, then the options as a centred block.
    """
    inner = width - 2
    body = []

    for ln in BARS:
        body.append(ln.center(inner))
    body.append(" " * inner)
    body.append(WORDMARK.center(inner))

    body += [" " * inner] * 3

    combined = f"{title}  ·  {subtitle}"
    body.append(combined.center(inner))
    body.append(" " * inner)
    body.append(menu_header.center(inner))
    body.append(" " * inner)

    block_w = max((len(o) for o in options), default=0)
    left = (inner - block_w) // 2
    for o in options:
        body.append((" " * left + o).ljust(inner))

    lines = ["╔" + "═" * inner + "╗", "║" + " " * inner + "║"]
    for b in body:
        lines.append("║" + b[:inner].ljust(inner) + "║")
    lines += ["║" + " " * inner + "║", "╚" + "═" * inner + "╝"]
    return lines
