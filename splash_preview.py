#!/usr/bin/env python3
"""
Standalone VIBE PREVIEW for the CHEAT splash screen.

Not wired into the app yet — run it to eyeball the layout/colours:
    python splash_preview.py            # white on Cisco DNA Center blue
    python splash_preview.py --plain     # no colour (for pasting into chat/docs)

Layout: the full 9-bar Cisco "bridge" logo (S·M·T·M·S·M·T·M·S — two tall
peaks, measured from the real mark) centred at the top with the CISCO / DNA
CENTER wordmark beneath it, then the title + Menu 1 horizontally centred three
lines below. White on Cisco DNA Center blue (#014F74).
"""

import os
import sys

FG = "\033[38;2;255;255;255m"   # white
BG = "\033[48;2;1;79;116m"      # Cisco DNA Center blue #014F74
RESET = "\033[0m"

WIDTH = 120
INNER = WIDTH - 2

# Full Cisco arch — 9 bars, two peaks (S,M,T,M,S,M,T,M,S), heights measured
# from the clean reference (top% 52/30/0). Half-block glyphs (▄ ▀) give the
# bars rounded pill caps like the real mark. Aspect ~3.7:1. Each line is 67 cols.
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

OPTIONS = [
    "1) Use dnac.env",
    "2) Enter manually   · remember",
    "3) Enter manually   · forget",
    "4) View dnac.env",
    "5) Options",
]


def compose():
    body = []
    # Graphic block (centred)
    for ln in BARS:
        body.append(ln.center(INNER))
    body.append(" " * INNER)
    body.append("C I S C O".center(INNER))
    body.append("DNA CENTER".center(INNER))
    # Three-line gap below the graphic
    body += [" " * INNER] * 3
    # Title + menu, horizontally centred
    body.append("CHEAT".center(INNER))
    body.append(" " * INNER)
    body.append("Cisco Homogeneous Environment Awareness Tool".center(INNER))
    body.append(" " * INNER)
    body.append("Menu 1 · Credentials".center(INNER))
    body.append(" " * INNER)
    block_w = max(len(o) for o in OPTIONS)
    left = (INNER - block_w) // 2
    for o in OPTIONS:
        body.append((" " * left + o).ljust(INNER))
    # Frame
    lines = ["╔" + "═" * INNER + "╗", "║" + " " * INNER + "║"]
    for b in body:
        lines.append("║" + b[:INNER].ljust(INNER) + "║")
    lines += ["║" + " " * INNER + "║", "╚" + "═" * INNER + "╝"]
    return lines


def _enable_windows_ansi():
    if os.name != "nt":
        return
    try:
        import colorama
        colorama.just_fix_windows_console()
        return
    except Exception:
        pass
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-11)
        m = ctypes.c_uint32()
        if k.GetConsoleMode(h, ctypes.byref(m)):
            k.SetConsoleMode(h, m.value | 0x0004)
    except Exception:
        pass


def main():
    lines = compose()
    if "--plain" in sys.argv:
        print("\n".join(lines))
        return
    _enable_windows_ansi()
    sys.stdout.write(FG + BG + "\033[2J\033[3J\033[H")
    print()
    for ln in lines:
        print("  " + ln)
    print()
    input("  Press Enter to exit preview... ")
    sys.stdout.write(RESET + "\n")


if __name__ == "__main__":
    main()
