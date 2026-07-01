#!/usr/bin/env python3
"""
Standalone VIBE PREVIEW for the CHEAT splash screen.

Run it to eyeball the layout/colours (uses the same renderer as the live app):
    python splash_preview.py            # white on Cisco DNA Center blue
    python splash_preview.py --plain     # no colour (for pasting into chat/docs)
"""

import os
import sys

import splash

FG = "\033[38;2;255;255;255m"   # white
BG = "\033[48;2;1;79;116m"      # Cisco DNA Center blue #014F74
RESET = "\033[0m"

OPTIONS = [
    "1) Use dnac.env",
    "2) Enter manually   · remember",
    "3) Enter manually   · forget",
    "4) View dnac.env",
    "5) Options",
]


def compose():
    return splash.build_lines(
        "CHEAT",
        "Cisco Homogeneous Environment Awareness Tool",
        "Menu 1 · Credentials",
        OPTIONS,
    )


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
