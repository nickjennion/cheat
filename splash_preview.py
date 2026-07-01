#!/usr/bin/env python3
"""
Standalone VIBE PREVIEW for the CHEAT splash screen.

Not wired into the app yet — run it to eyeball the layout/colours:
    python splash_preview.py            # white on Cisco DNA Center blue
    python splash_preview.py --plain     # no colour (for pasting into chat/docs)

Layout mirrors the hand sketch: ~30% Cisco bridge logo on the left,
~70% title (one line, top-aligned with the tallest bar) + Menu 1 on the right.
"""

import os
import sys

FG = "\033[38;2;255;255;255m"   # white
BG = "\033[48;2;1;79;116m"      # Cisco DNA Center blue #014F74
RESET = "\033[0m"

# Box geometry
WIDTH = 80                       # total incl. borders
INNER = WIDTH - 2                # 78
LEFT_W = 22                      # logo column (~30%)
GAP = 2

# Left column: Cisco "bridge" bars + wordmark (top-aligned with title)
LOGO = [
    "      █ █ █ █ █",
    "    █ █ █ █ █ █ █",
    "  █ █ █ █ █ █ █ █ █",
    "█ █ █ █ █ █ █ █ █ █ █",
    "",
    "      C I S C O",
    "     DNA CENTER",
]

# Right column: title on one line + menu (5 options from the sketch)
MENU = [
    "CHEAT — Cisco Homogeneous Environment Awareness Tool",
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
    lines = []
    lines.append("╔" + "═" * INNER + "╗")
    lines.append("║" + " " * INNER + "║")
    for lft, rgt in zip(left, right):
        cell = (lft.ljust(LEFT_W) + " " * GAP + rgt)
        lines.append("║" + cell.ljust(INNER)[:INNER] + "║")
    lines.append("║" + " " * INNER + "║")
    lines.append("╚" + "═" * INNER + "╝")
    return lines


def main():
    plain = "--plain" in sys.argv
    lines = compose()
    if plain:
        print("\n".join(lines))
        return
    if os.name == "nt":
        try:
            import colorama
            colorama.just_fix_windows_console()
        except Exception:
            try:
                import ctypes
                k = ctypes.windll.kernel32
                h = k.GetStdHandle(-11)
                m = ctypes.c_uint32()
                if k.GetConsoleMode(h, ctypes.byref(m)):
                    k.SetConsoleMode(h, m.value | 0x0004)
            except Exception:
                pass
    sys.stdout.write(FG + BG + "\033[2J\033[3J\033[H")
    # pad each printed line to full width so the blue fills edge-to-edge
    print()
    for ln in compose():
        print("  " + ln)
    print()
    input("  Press Enter to exit preview... ")
    sys.stdout.write(RESET + "\n")


if __name__ == "__main__":
    main()
