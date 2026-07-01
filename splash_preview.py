#!/usr/bin/env python3
"""
Standalone VIBE PREVIEW for the CHEAT splash screen.

Not wired into the app yet — run it to eyeball the layout/colours:
    python splash_preview.py            # white on Cisco DNA Center blue
    python splash_preview.py --plain     # no colour (for pasting into chat/docs)

Layout mirrors the hand sketch: Cisco "bridge" logo on the left, title on one
line (top-aligned with the tallest bar) + Menu 1 on the right. The logo bar
pattern (short·med·TALL·med·short·med·TALL·med·short, tall bars dipping below
the baseline) is measured from the real Cisco DNA Center mark.
"""

import os
import sys

FG = "\033[38;2;255;255;255m"   # white
BG = "\033[48;2;1;79;116m"      # Cisco DNA Center blue #014F74
RESET = "\033[0m"

# Box geometry (comfortable within a 140-col terminal)
WIDTH = 100
INNER = WIDTH - 2
PAD = 2                          # interior left padding
LOGO_W = 25                      # authentic logo is 25 cols wide
GAP = 5                          # space between logo and text columns

# Left column: authentic Cisco bridge bars + wordmark
LOGO = [
    "      █           █      ",
    "      █           █      ",
    "   █  █  █     █  █  █   ",
    "   █  █  █     █  █  █   ",
    "█  █  █  █  █  █  █  █  █",
    "█  █  █  █  █  █  █  █  █",
    "█  █  █  █  █  █  █  █  █",
    "      █           █      ",
    "",
    "C I S C O".center(LOGO_W),
    "DNA CENTER".center(LOGO_W),
]

# Right column: title on one line + Menu 1 (5 options from the sketch)
MENU = [
    "CHEAT",
    "",
    "",
    "Cisco Homogeneous Environment Awareness Tool",
    "",
    "",
    "Menu 1 · Credentials",
    "",
    "  1) Use dnac.env",
    "  2) Enter manually   · remember",
    "  3) Enter manually   · forget",
    "  4) View dnac.env",
    "  5) Options",
]


def compose():
    rows = max(len(LOGO), len(MENU))
    left = LOGO + [""] * (rows - len(LOGO))
    right = MENU + [""] * (rows - len(MENU))
    lines = ["╔" + "═" * INNER + "╗", "║" + " " * INNER + "║"]
    for lft, rgt in zip(left, right):
        cell = " " * PAD + lft.ljust(LOGO_W) + " " * GAP + rgt
        lines.append("║" + cell.ljust(INNER)[:INNER] + "║")
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
