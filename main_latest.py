#!/usr/bin/env python3
"""
CHEAT — Cisco Homogenous Environment Awareness Tool
Interactive menu launcher.
"""

import getpass
import json
import os
import sys
from pathlib import Path

from dnac_client import DNACClient
from cheat_core import (
    EXCEL_DIR,
    COMMAND_RUNNER_DIR,
    build_command_list,
    run_commands,
    parse_outputs,
    generate_excel,
    generate_cdp_topology,
)
from excel_generator import write_client_search_excel
from port_utilisation import is_copper_port
from drawio_generator import generate_drawio
import ap_monitor
import splash


ENV_FILE = Path("dnac.env")
SAMPLE_FILE = Path("sample_dnac.env")
ALL_DEVICES_FILE = Path("all_devices.json")


# ============================================================================
# Theme — white text on Cisco DNA Center blue (#014F74 / rgb 1,79,116)
# ============================================================================

_FG = "\033[38;2;255;255;255m"   # white text
_BG = "\033[48;2;1;79;116m"      # Cisco DNA Center blue
_RESET = "\033[0m"
_COLOR_ON = False


def _enable_ansi() -> bool:
    """Enable ANSI/VT escape processing (needed on legacy Windows consoles)."""
    if os.name != "nt":
        return True
    try:
        import colorama
        colorama.just_fix_windows_console()
        return True
    except Exception:
        pass
    # Fallback: flip ENABLE_VIRTUAL_TERMINAL_PROCESSING on the console via Win32.
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        return True
    except Exception:
        return False


def theme_init():
    """Turn on white-on-blue and paint the whole screen. No-op if unsupported."""
    global _COLOR_ON
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return
    if not _enable_ansi():
        return
    _COLOR_ON = True
    # Set colours, then clear screen + scrollback so the blue fills everything.
    sys.stdout.write(_FG + _BG + "\033[2J\033[3J\033[H")
    sys.stdout.flush()


def theme_reset():
    """Restore the terminal's default colours (call on exit)."""
    if not _COLOR_ON:
        return
    sys.stdout.write(_RESET + "\n")
    sys.stdout.flush()


def theme_clear():
    """Home the cursor and clear the screen, keeping the blue background."""
    if _COLOR_ON:
        sys.stdout.write(_FG + _BG + "\033[2J\033[H")
        sys.stdout.flush()
    else:
        print()


# Splash branding text (shared logo/layout lives in splash.py)
SPLASH_TITLE = "CHEAT"
SPLASH_SUBTITLE = "Cisco Homogeneous Environment Awareness Tool"


def _show_splash_rich(menu_header, options) -> bool:
    """Draw the Rich splash over the blue theme. Returns False if unavailable."""
    try:
        import splash_rich
        from rich.console import Console
    except Exception:
        return False
    try:
        splash_rich.render(Console(), SPLASH_TITLE, SPLASH_SUBTITLE, menu_header, options)
    except Exception:
        return False
    # Rich resets SGR at the end of its output; re-assert the blue theme so the
    # menu prompt printed after us stays white-on-blue.
    if _COLOR_ON:
        sys.stdout.write(_FG + _BG)
        sys.stdout.flush()
    return True


def show_splash(menu_header, options):
    """Clear the screen and draw the branded Cisco splash with a menu."""
    theme_clear()
    # Rich splash only when interactive and selected; always fall back to classic.
    if _COLOR_ON and load_prefs().get("SPLASH_STYLE", "rich") == "rich":
        if _show_splash_rich(menu_header, options):
            return
    for line in splash.build_lines(SPLASH_TITLE, SPLASH_SUBTITLE, menu_header, options):
        print("  " + line)
    print()


# ============================================================================
# Helpers
# ============================================================================

def display_command_outputs(outputs: dict) -> None:
    """Print captured command output to screen, one headed section per device.

    Output is also saved to files by run_commands; this just saves the file hunt
    for quick ad-hoc commands (e.g. 'show mac address-table').
    """
    if not outputs:
        return
    try:
        from rich.console import Console, Group
        from rich.rule import Rule
        from rich.text import Text
        console = Console()
        cyan = "rgb(34,211,238)"
        blocks = []
        for hostname, text in outputs.items():
            blocks.append(Rule(f"[bold]{hostname}[/]", style=cyan))
            blocks.append(Text(text))  # Text = literal; no markup/number highlighting
        blocks.append(Rule(style=cyan))
        group = Group(*blocks)

        # Page (less-style) only when the output won't fit on screen; otherwise
        # print inline so a quick 'show clock' doesn't force a pager.
        est_lines = sum(t.count("\n") + 1 for t in outputs.values()) + len(outputs) + 1
        if est_lines > console.size.height - 2:
            with console.pager(styles=True):
                console.print(group)
        else:
            console.print(group)
    except Exception:
        for hostname, text in outputs.items():
            print(f"\n{'='*55}\n  {hostname}\n{'='*55}")
            print(text)
    # Rich resets SGR; re-assert the blue theme for the prompt that follows.
    if _COLOR_ON:
        sys.stdout.write(_FG + _BG)
        sys.stdout.flush()
    print(f"\n  (Full output also saved under {COMMAND_RUNNER_DIR}/)")


def pause():
    input("\nPress Enter to continue...")


def load_credentials_from_env():
    """Load DNAC credentials from dnac.env. Returns (host, user, pass) or None."""
    if not ENV_FILE.exists():
        return None
    try:
        creds = {}
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                creds[k.strip()] = v.strip()
        host = creds.get("DNAC_HOST")
        username = creds.get("DNAC_USERNAME")
        password = creds.get("DNAC_PASSWORD")
        if host and username and password:
            return host, username, password
    except Exception as e:
        print(f"  Warning: could not read dnac.env: {e}")
    return None


def save_credentials_to_env(host, username, password):
    """Write credentials to dnac.env (overwrites existing). Returns success."""
    try:
        ENV_FILE.write_text(
            f"DNAC_HOST={host}\n"
            f"DNAC_USERNAME={username}\n"
            f"DNAC_PASSWORD={password}\n"
        )
        return True
    except Exception as e:
        print(f"\n  ✗ Could not write {ENV_FILE}: {e}")
        return False


def _prompt_manual_credentials():
    """Prompt for DNAC credentials. Returns (host, user, pass) or None."""
    print()
    host = input("    DNAC host (FQDN or IP, no https://): ").strip()
    username = input("    Username: ").strip()
    password = getpass.getpass("    Password: ")
    if host and username and password:
        return host, username, password
    print("\n  ✗ All fields required.")
    pause()
    return None


def _prompt_filename(label="Filename"):
    """Prompt for an Excel filename; append .xlsx if omitted. Returns None if blank."""
    name = input(f"  {label}: ").strip()
    if not name:
        return None
    if not name.lower().endswith(".xlsx"):
        name += ".xlsx"
    return name


# ============================================================================
# Menu 1 — Credential Selection
# ============================================================================

def menu_1():
    """Returns (host, username, password) once credentials are confirmed."""
    while True:
        show_splash("Menu 1 · Credentials", [
            "1) Use dnac.env",
            "2) Enter manually   · remember",
            "3) Enter manually   · forget",
            "4) View dnac.env",
            "5) Options",
        ])
        choice = input("  Select [1-5]: ").strip()

        if choice == "1":
            result = load_credentials_from_env()
            if result:
                host, username, _ = result
                print(f"\n  ✓ Loaded from dnac.env")
                print(f"    Host: {host}  |  User: {username}")
                pause()
                return result
            else:
                print(f"\n  ✗ dnac.env not found or incomplete.")
                if SAMPLE_FILE.exists():
                    print(f"    Copy {SAMPLE_FILE} to dnac.env and fill in your values.")
                else:
                    print(f"    Create dnac.env with DNAC_HOST=, DNAC_USERNAME=, DNAC_PASSWORD=")
                pause()

        elif choice == "2":  # Enter manually · remember (persist to dnac.env)
            creds = _prompt_manual_credentials()
            if creds:
                if save_credentials_to_env(*creds):
                    print(f"\n  ✓ Saved to {ENV_FILE}")
                pause()
                return creds

        elif choice == "3":  # Enter manually · forget (session only, never written)
            creds = _prompt_manual_credentials()
            if creds:
                return creds

        elif choice == "4":  # View dnac.env
            print()
            if ENV_FILE.exists():
                print(f"  --- {ENV_FILE} ---")
                for line in ENV_FILE.read_text().splitlines():
                    if "=" in line and not line.strip().startswith("#"):
                        k, _ = line.split("=", 1)
                        if k.strip().upper() == "DNAC_PASSWORD":
                            print(f"  {k.strip()}=********")
                        else:
                            print(f"  {line.strip()}")
                    else:
                        print(f"  {line}")
                print(f"  ---")
            else:
                print(f"  dnac.env not found.")
                if SAMPLE_FILE.exists():
                    print(f"  Copy {SAMPLE_FILE} to dnac.env and fill in your values.")
            pause()

        elif choice == "5":  # Options / preferences
            menu_options()

        else:
            print("\n  Invalid selection.")
            pause()


# ============================================================================
# Options / Preferences  (Menu 1 → 5, writes prefs.env)
# ============================================================================
#
# SCAFFOLD: settings are persisted to prefs.env but not yet wired into app
# behaviour. Hooking each toggle up to the tool is a follow-up per item.

PREFS_FILE = Path("prefs.env")

DEFAULT_PREFS = {
    "SLOW_MODE": "off",
    "OUTPUT_DIR": "excel_reports",
    "FILENAME_PREFIX": "cheat",
    "AUTO_CONSOLIDATION": "off",
    "COLOURS": "on",
    "EMAIL_OUTPUT": "off",
    "EMAIL_ADDRESS": "",
    "AI_ENABLED": "off",
    "AI_MODEL": "claude-opus-4-8",
    "LOGGING": "off",
    "LOG_LEVEL": "info",
    "SPLASH_STYLE": "rich",   # "rich" (gradient/panel) or "classic" (flat splash.py)
}


def load_prefs():
    """Load preferences from prefs.env, merged over defaults."""
    prefs = dict(DEFAULT_PREFS)
    if PREFS_FILE.exists():
        try:
            for line in PREFS_FILE.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                prefs[k.strip()] = v.strip()
        except Exception as e:
            print(f"  Warning: could not read {PREFS_FILE}: {e}")
    return prefs


def save_prefs(prefs):
    """Write preferences to prefs.env. Returns success."""
    try:
        PREFS_FILE.write_text("".join(f"{k}={v}\n" for k, v in prefs.items()))
        return True
    except Exception as e:
        print(f"\n  ✗ Could not write {PREFS_FILE}: {e}")
        return False


def _toggle(value):
    return "off" if str(value).lower() == "on" else "on"


def menu_options():
    """Options / preferences menu. Reads and writes prefs.env (scaffold)."""
    prefs = load_prefs()
    while True:
        theme_clear()
        print("\n  Options · Preferences\n")
        print(f"  A) Slow mode            [{prefs['SLOW_MODE']}]")
        print(f"  B) Filenames & paths    [{prefs['OUTPUT_DIR']}/  {prefs['FILENAME_PREFIX']}*]")
        print(f"  C) Auto consolidation   [{prefs['AUTO_CONSOLIDATION']}]")
        print(f"  D) Colours              [{prefs['COLOURS']}]")
        print(f"  E) Email output         [{prefs['EMAIL_OUTPUT']}]")
        print(f"  F) AI settings          [{prefs['AI_ENABLED']}]")
        print(f"  G) Logging              [{prefs['LOGGING']}]")
        print(f"  H) Splash style         [{prefs['SPLASH_STYLE']}]")
        print()
        print("  0) Back")
        print()
        choice = input("  Select [A-H, 0]: ").strip().upper()

        if choice == "0":
            save_prefs(prefs)
            return
        elif choice == "A":
            prefs["SLOW_MODE"] = _toggle(prefs["SLOW_MODE"])
        elif choice == "B":
            print()
            d = input(f"    Output directory [{prefs['OUTPUT_DIR']}]: ").strip()
            p = input(f"    Filename prefix  [{prefs['FILENAME_PREFIX']}]: ").strip()
            if d:
                prefs["OUTPUT_DIR"] = d
            if p:
                prefs["FILENAME_PREFIX"] = p
        elif choice == "C":
            prefs["AUTO_CONSOLIDATION"] = _toggle(prefs["AUTO_CONSOLIDATION"])
        elif choice == "D":
            prefs["COLOURS"] = _toggle(prefs["COLOURS"])
        elif choice == "E":
            prefs["EMAIL_OUTPUT"] = _toggle(prefs["EMAIL_OUTPUT"])
            if prefs["EMAIL_OUTPUT"] == "on":
                print()
                addr = input(f"    Send reports to [{prefs['EMAIL_ADDRESS']}]: ").strip()
                if addr:
                    prefs["EMAIL_ADDRESS"] = addr
        elif choice == "F":
            prefs["AI_ENABLED"] = _toggle(prefs["AI_ENABLED"])
            if prefs["AI_ENABLED"] == "on":
                print()
                model = input(f"    AI model [{prefs['AI_MODEL']}]: ").strip()
                if model:
                    prefs["AI_MODEL"] = model
        elif choice == "G":
            prefs["LOGGING"] = _toggle(prefs["LOGGING"])
        elif choice == "H":
            prefs["SPLASH_STYLE"] = "classic" if prefs["SPLASH_STYLE"] == "rich" else "rich"
        else:
            print("\n  Invalid selection.")
            pause()
            continue

        save_prefs(prefs)


# ============================================================================
# Menu 2 — Actions
# ============================================================================

def _auth(host, username, password):
    """Authenticate and return DNACClient, or None on failure."""
    print("\n  Authenticating...")
    client = DNACClient(host, username, password)
    if client.authenticate():
        print("  ✓ Authenticated")
        return client
    print("  ✗ Authentication failed.")
    return None


def action_get_devices(host, username, password):
    """Authenticate, fetch all devices, save all_devices.json.
    Returns (devices, client) on success, (None, None) on failure."""
    client = _auth(host, username, password)
    if not client:
        pause()
        return None, None

    print("\n  Fetching all devices...\n")
    devices = client.get_devices()   # paginated; prints progress per page

    if not devices:
        print("  No devices returned.")
        pause()
        return None, None

    try:
        ALL_DEVICES_FILE.write_text(json.dumps(devices, indent=2))
        print(f"\n  ✓ Saved {len(devices)} device(s) to {ALL_DEVICES_FILE}")
    except Exception as e:
        print(f"\n  Warning: could not write {ALL_DEVICES_FILE}: {e}")

    print(f"\n  {'#':<5} {'Hostname':<45} {'Platform':<22} {'IP Address'}")
    print(f"  {'-'*5} {'-'*45} {'-'*22} {'-'*15}")
    for i, d in enumerate(devices, 1):
        h = str(d.get('hostname') or 'unknown')
        p = str(d.get('platformId') or '')
        ip = str(d.get('managementIpAddress') or '')
        print(f"  {i:<5} {h:<45} {p:<22} {ip}")
    print(f"\n  Total: {len(devices)} device(s)")

    print()
    nav = input("  Press Enter to continue or 'quit' to return to Menu 2: ").strip().lower()
    if nav == "quit":
        return None, None
    return devices, client


def action_get_sites(host, username, password):
    """Authenticate, fetch all sites. Returns (sites, client) or (None, None)."""
    client = _auth(host, username, password)
    if not client:
        pause()
        return None, None

    print("\n  Fetching site hierarchy...")
    sites = client.get_sites()

    if not sites:
        print("  No sites returned.")
        pause()
        return None, None

    print(f"\n  ✓ {len(sites)} site(s) loaded")
    pause()
    return sites, client


def action_ap_monitor(host, username, password):
    """Authenticate, fetch Unified APs, launch AP movement monitor."""
    client = _auth(host, username, password)
    if not client:
        pause()
        return

    print("\n  Fetching Unified AP inventory...\n")
    aps = client.get_ap_devices()

    if not aps:
        print("  No Unified APs found in DNAC inventory.")
        pause()
        return

    print(f"\n  ✓ {len(aps)} AP(s) loaded.")
    ap_monitor.run(client, aps)


def _site_type(site: dict) -> str:
    for info in (site.get("additionalInfo") or []):
        t = (info.get("attributes") or {}).get("type", "")
        if t:
            return t
    return "unknown"


def _site_attrs(site: dict) -> dict:
    attrs = {}
    for info in (site.get("additionalInfo") or []):
        attrs.update(info.get("attributes") or {})
    return attrs


def _matches_site_filters(site: dict, filter_terms: list[str]) -> bool:
    text = (site.get("siteNameHierarchy") or site.get("name") or "").lower()
    for term in filter_terms:
        alternatives = [a.strip() for a in term.split("|") if a.strip()]
        if not any(alt in text for alt in alternatives):
            return False
    return True


def menu_sites(sites: list, client, host: str, username: str):
    """Site browse menu (Menu 2 equivalent for sites)."""
    while True:
        theme_clear()
        print(f"  Host: {host}  |  User: {username}  |  Sites loaded: {len(sites)}\n")
        print("  Sites — Browse\n")
        print("  1) Select & filter sites")
        print("  2) List all sites")
        print("  3) Back")
        print()
        choice = input("  Select [1-3]: ").strip()

        if choice == "3":
            return
        elif choice == "1":
            selected = menu_sites_select(sites, host, username)
            if selected:
                menu_sites_actions(selected, client, host, username)
        elif choice == "2":
            theme_clear()
            print(f"  All Sites ({len(sites)} total)\n")
            print(f"  {'#':<5} {'Name':<35} {'Type':<12} {'Hierarchy'}")
            print(f"  {'-'*5} {'-'*35} {'-'*12} {'-'*50}")
            for i, s in enumerate(sites, 1):
                name  = s.get("name", "?")[:34]
                stype = _site_type(s)
                hier  = s.get("siteNameHierarchy", "")[:60]
                print(f"  {i:<5} {name:<35} {stype:<12} {hier}")
            pause()
        else:
            print("\n  Invalid selection.")
            pause()


def menu_sites_select(sites: list, host: str, username: str) -> list:
    """Site filter + select screen. Returns list of selected site dicts."""
    filter_terms: list[str] = []
    selected: set[int] = set()

    while True:
        filtered = [s for s in sites if _matches_site_filters(s, filter_terms)] if filter_terms else []

        theme_clear()
        print(f"  Host: {host}\n")
        print("  Sites — Select\n")
        if filter_terms:
            label = "  AND  ".join(f"[{t}]" for t in filter_terms)
            print(f"  Filters: {label}\n")
        else:
            print("  Filters: none\n")

        if not filter_terms:
            print("  Add a filter to show matching sites.")
            print("  Use '|' for OR within a term  (e.g. f building|area)")
            print("  Stack multiple filters with 'f' again  (each adds an AND clause)")
        elif not filtered:
            print("  No sites matched — try 'fc' to clear filters and start over")
        else:
            print(f"  {'#':<5} {'':3} {'Name':<35} {'Type':<12} {'Hierarchy'}")
            print(f"  {'-'*5} {'-'*3} {'-'*35} {'-'*12} {'-'*45}")
            for i, s in enumerate(filtered, 1):
                check = "[X]" if i in selected else "[ ]"
                name  = s.get("name", "?")[:34]
                stype = _site_type(s)
                hier  = s.get("siteNameHierarchy", "")[:45]
                print(f"  {i:<5} {check} {name:<35} {stype:<12} {hier}")
            print(f"\n  Selected: {len(selected)} site(s)")

        print()
        print("  'f <term>'  add filter  |  'fc' clear filters")
        print("  number(s)   toggle selection (e.g. 1  or  1,3-5)  |  'a' select all")
        print("  'p' Proceed  |  'b' Back")
        print()
        entry = input("  > ").strip()

        if entry.lower() == "b":
            return []
        elif entry.lower() in ("p", ""):
            if not selected:
                print("\n  No sites selected — pick at least one.")
                pause()
            else:
                return [filtered[i - 1] for i in sorted(selected) if i <= len(filtered)]
        elif entry.lower() == "a":
            selected = set(range(1, len(filtered) + 1))
        elif entry.lower() == "fc":
            filter_terms.clear()
            selected.clear()
        elif entry.lower().startswith("f "):
            term = entry[2:].strip().lower()
            if term:
                filter_terms.append(term)
                selected.clear()
        else:
            toggled = _parse_numbers(entry, len(filtered))
            if not toggled:
                print("\n  Unrecognised input.")
                pause()
            else:
                for idx in toggled:
                    if idx in selected:
                        selected.discard(idx)
                    else:
                        selected.add(idx)


def menu_sites_actions(selected_sites: list, client, host: str, username: str):
    """Actions menu for selected sites."""
    while True:
        theme_clear()
        print(f"  Host: {host}  |  Selected: {len(selected_sites)} site(s)\n")
        print("  Sites — Actions\n")
        print("  1) Export draw.io diagram")
        print("  2) Back")
        print()
        choice = input("  Select [1-2]: ").strip()

        if choice == "2":
            return
        elif choice == "1":
            filename = _prompt_filename("draw.io filename (no extension needed)")
            if not filename:
                print("  Cancelled.")
                pause()
                continue
            # Override .xlsx suffix — we want .drawio
            stem = Path(filename).stem
            outpath = Path("drawio_exports") / f"{stem}.drawio"
            outpath.parent.mkdir(exist_ok=True)
            xml = generate_drawio(selected_sites, title=stem)
            if xml:
                outpath.write_text(xml, encoding="utf-8")
                print(f"\n  ✓ Saved: {outpath}  ({len(selected_sites)} site(s))")
            else:
                print("  ✗ Failed to generate diagram.")
            pause()
        else:
            print("\n  Invalid selection.")
            pause()


def action_get_version(host, username, password):
    client = _auth(host, username, password)
    if not client:
        pause()
        return

    print("\n  Fetching DNAC version...")
    try:
        url = f"https://{host}/dna/intent/api/v1/dnac-release"
        headers = {"X-Auth-Token": client.token}
        resp = client.session.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        version = (
            data.get("response", {}).get("installedVersion")
            or data.get("response", {}).get("version")
            or data.get("version")
            or "unknown"
        )
        print(f"\n  ✓ DNAC Version: {version}")
    except Exception as e:
        print(f"\n  Could not retrieve version: {e}")
    pause()


def menu_2(host, username, password):
    """Action menu. Returns when user selects Back."""
    while True:
        theme_clear()
        print(f"  Host: {host}  |  User: {username}\n")
        print("  Menu 2 — Actions\n")
        print("  1) Auth & Get Devices (All)")
        print("  2) Auth & Get DNAC Version")
        print("  3) Auth & Get Sites")
        print("  4) Access Point — Monitor Physical Movements")
        print("  0) Back")
        print()
        choice = input("  Select [0-4]: ").strip()

        if choice == "0":
            return
        elif choice == "1":
            devices, client = action_get_devices(host, username, password)
            if devices is not None:
                menu_3(devices, client, host, username)
        elif choice == "2":
            action_get_version(host, username, password)
        elif choice == "3":
            sites, client = action_get_sites(host, username, password)
            if sites is not None:
                menu_sites(sites, client, host, username)
        elif choice == "4":
            action_ap_monitor(host, username, password)
        else:
            print("\n  Invalid selection.")
            pause()


# ============================================================================
# Menu 3 — Device Actions
# ============================================================================

def menu_3(devices, client, host, username):
    """Device actions menu — operates on the loaded inventory."""
    while True:
        theme_clear()
        print(f"  Host: {host}  |  User: {username}  |  Devices loaded: {len(devices)}\n")
        print("  Menu 3 — Device Actions\n")
        print("  1) Select switches")
        print("  2) List all devices")
        print("  3) Quit")
        print()
        choice = input("  Select [1-3]: ").strip()

        if choice == "1":
            selected = menu_4(devices, client, host, username)
            if selected:
                menu_5(selected, client, host, username)
        elif choice == "2":
            theme_clear()
            print(f"  {'#':<5} {'Hostname':<45} {'Platform':<22} {'IP Address'}")
            print(f"  {'-'*5} {'-'*45} {'-'*22} {'-'*15}")
            for i, d in enumerate(devices, 1):
                h = str(d.get('hostname') or '')
                p = str(d.get('platformId') or '')
                ip = str(d.get('managementIpAddress') or '')
                print(f"  {i:<5} {h:<45} {p:<22} {ip}")
            print(f"\n  Total: {len(devices)} device(s)")
            pause()
        elif choice == "3":
            return
        else:
            print("\n  Invalid selection.")
            pause()


# ============================================================================
# Menu 4 — Switch Selection
# ============================================================================

def _parse_numbers(entry: str, max_idx: int) -> list[int]:
    """Parse comma-separated numbers and ranges (e.g. '1,3-5') into indices."""
    result = set()
    for part in entry.split(","):
        part = part.strip()
        if "-" in part:
            try:
                lo, hi = part.split("-", 1)
                result.update(range(int(lo), int(hi) + 1))
            except ValueError:
                pass
        elif part.isdigit():
            result.add(int(part))
    return sorted(i for i in result if 1 <= i <= max_idx)


def _matches_filters(device, filter_terms: list[str], exclude_terms: list[str] = []) -> bool:
    """Return True if device matches ALL filter terms and NO exclude terms.
    Within each term, '|' separates alternatives (OR logic).
    Matches against hostname and platformId."""
    text = (
        (device.get("hostname") or "") + " " + (device.get("platformId") or "")
    ).lower()
    for term in filter_terms:
        alternatives = [a.strip() for a in term.split("|") if a.strip()]
        if not any(alt in text for alt in alternatives):
            return False
    for term in exclude_terms:
        alternatives = [a.strip() for a in term.split("|") if a.strip()]
        if any(alt in text for alt in alternatives):
            return False
    return True


def _filter_label(filter_terms: list[str], exclude_terms: list[str] = []) -> str:
    """Human-readable representation of the active filter stack."""
    parts = []
    if filter_terms:
        parts.append("  AND  ".join(f"[{t}]" for t in filter_terms))
    if exclude_terms:
        parts.append("NOT " + "  NOT ".join(f"[{t}]" for t in exclude_terms))
    return "  ".join(parts) if parts else "(none)"


def menu_4(devices, client, host, username):
    """Switch selection screen. Returns list of selected device dicts, or []."""
    filter_terms: list[str] = []
    exclude_terms: list[str] = []
    selected = set()

    while True:
        switches = [
            d for d in devices
            if _matches_filters(d, filter_terms, exclude_terms)
        ] if (filter_terms or exclude_terms) else []

        theme_clear()
        print(f"  Host: {host}\n")
        print(f"  Menu 4 — Select Switches\n")
        print(f"  Filters: {_filter_label(filter_terms, exclude_terms)}\n")

        if not filter_terms and not exclude_terms:
            print("  Add a filter to show matching devices.")
            print("  Use '|' for OR within a term  (e.g. f 3850|9300)")
            print("  Stack multiple filters with 'f' again  (each adds an AND clause)")
        elif not switches:
            print(f"  No devices matched — try 'fc' to clear filters and start over")
        else:
            print(f"  {'#':<5} {'':3} {'Hostname':<40} {'Platform':<20} {'IP Address'}")
            print(f"  {'-'*5} {'-'*3} {'-'*40} {'-'*20} {'-'*15}")
            for i, d in enumerate(switches, 1):
                check = "[X]" if i in selected else "[ ]"
                h  = str(d.get("hostname") or "unknown")
                p  = str(d.get("platformId") or "")
                ip = str(d.get("managementIpAddress") or "")
                print(f"  {i:<5} {check} {h:<40} {p:<20} {ip}")
            print(f"\n  Selected: {len(selected)} device(s)")

        print()
        print("  'f <term>'  add filter (| = OR, e.g. f 3850|9300)  |  'fc' clear all filters")
        print("  'r <term>'  exclude (| = OR, e.g. r oob|mgmt)")
        print("  number(s)   toggle selection (e.g. 1  or  1,3-5)")
        print("  'p'         Proceed    |    'b'  Back")
        print()
        entry = input("  > ").strip()

        if entry.lower() == "b":
            return []
        elif entry.lower() in ("p", ""):
            if not selected:
                print("\n  No devices selected — pick at least one.")
                pause()
            else:
                return [switches[i - 1] for i in sorted(selected) if i <= len(switches)]
        elif entry.lower() == "fc":
            filter_terms.clear()
            exclude_terms.clear()
            selected.clear()
        elif entry.lower().startswith("f "):
            term = entry[2:].strip().lower()
            if term:
                filter_terms.append(term)
                selected.clear()
        elif entry.lower().startswith("r "):
            term = entry[2:].strip().lower()
            if term:
                exclude_terms.append(term)
                selected.clear()
        else:
            toggled = _parse_numbers(entry, len(switches))
            if not toggled:
                print("\n  Unrecognised input.")
                pause()
            else:
                for idx in toggled:
                    if idx in selected:
                        selected.discard(idx)
                    else:
                        selected.add(idx)


# ============================================================================
# Menu 6 — Confirmation
# ============================================================================

def menu_6(selected_devices, commands):
    """Confirmation screen — shows commands and target hosts before execution.
    Returns True to proceed, False to go back."""
    theme_clear()
    print("  Menu 6 — Confirm Execution\n")
    print("  Commands:\n")
    for cmd in commands:
        print(f"    • {cmd}")
    print(f"\n  Targets:\n")
    for d in selected_devices:
        print(f"    • {d.get('hostname', 'unknown')}  ({d.get('managementIpAddress', '')})")
    print()
    entry = input("  Press Enter to proceed or 'b' to go back: ").strip().lower()
    return entry != "b"


# ============================================================================
# Menu 5 — Commands
# ============================================================================

def _exec_and_report(selected_devices, client, commands, mode, filename, threshold=42, slow_mode=False, copper_only=False):
    """Run commands → parse → generate Excel. Used by menu_5 options 1-3."""
    if slow_mode:
        client.enable_slow_mode()
        print("  [Slow mode: poll 60s / 3s interval, submit 20s, backoff×2]")
        outputs = run_commands(selected_devices, client, commands,
                               poll_timeout=60, poll_interval=3, submit_timeout=20)
    else:
        outputs = run_commands(selected_devices, client, commands)
    if not outputs:
        pause()
        return
    devices_data = parse_outputs(outputs)
    if not devices_data:
        pause()
        return
    if copper_only:
        print("  [Copper only: non-copper interfaces excluded]")
        devices_data = {
            h: ([r for r in recs if is_copper_port(r.iface)], sm)
            for h, (recs, sm) in devices_data.items()
            if any(is_copper_port(r.iface) for r in recs)
        }
    if not devices_data:
        print("  ✗ No copper ports found after filtering.")
        pause()
        return
    stem = Path(filename).stem
    results = generate_excel(devices_data, mode, stem, threshold, raw_outputs=outputs)
    for _, msg in results:
        print(f"\n  {msg}")
    if mode == 3:
        _, topo_msg = generate_cdp_topology(outputs, outputs.keys(), stem)
        print(f"\n  {topo_msg}")
    pause()


def _validate_mac_prefix(raw: str) -> str:
    """Strip separators and check at least 4 hex chars are present.
    Returns the original (with separators) if valid, or '' if too short/invalid."""
    hex_only = raw.replace(":", "").replace("-", "").replace(".", "")
    if not all(c in "0123456789abcdefABCDEF" for c in hex_only):
        return ""
    if len(hex_only) < 4:
        return ""
    return raw


def action_mac_search(client):
    """Wildcard MAC search via /dna/data/api/v1/clients."""
    print()
    print("  MAC prefix search  (minimum 4 hex digits, e.g. 00:11  or  0011:22)")
    print("  Wildcard '*' is appended automatically.\n")
    raw_mac = input("  MAC prefix: ").strip()
    if not raw_mac:
        print("  Cancelled.")
        pause()
        return
    if not _validate_mac_prefix(raw_mac):
        print("  ✗ Minimum 4 hex digits required (e.g. 00:11 or 0011).")
        pause()
        return

    device_filter = input("  Switch hostname filter (optional, wildcard ok, e.g. core*): ").strip() or None

    print()
    clients = client.search_clients(raw_mac, device_name=device_filter)

    if not clients:
        print("  No matching clients found.")
        pause()
        return

    print(f"\n  Found {len(clients)} client(s)\n")

    from datetime import datetime, timezone

    total = len(clients)
    for idx, c in enumerate(clients, 1):
        nd   = c.get("connectedNetworkDevice") or {}
        conn = c.get("connection") or {}

        mac     = c.get("macAddress") or "—"
        ctype   = c.get("type") or "—"
        vendor  = c.get("vendor") or "—"
        ip      = c.get("ipv4Address") or "—"
        status  = c.get("connectionStatus") or "—"
        name    = c.get("name") or "—"
        switch  = nd.get("connectedNetworkDeviceName") or "—"
        port    = nd.get("interfaceName") or "—"
        vlan    = conn.get("vlanId") or "—"
        username = c.get("username") or "—"

        raw_ts = c.get("lastUpdatedTime")
        if raw_ts:
            try:
                iso_ts = datetime.fromtimestamp(int(raw_ts) / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                iso_ts = "—"
        else:
            raw_ts = "—"
            iso_ts = "—"

        print(f"  ── {idx} / {total} {'─' * 44}")
        lw = 22
        print(f"  {'MAC':<{lw}} {mac}")
        print(f"  {'Type':<{lw}} {ctype}")
        print(f"  {'Vendor':<{lw}} {vendor}")
        print(f"  {'IP Address':<{lw}} {ip}")
        print(f"  {'Connection Status':<{lw}} {status}")
        print(f"  {'Last Updated (raw)':<{lw}} {raw_ts}")
        print(f"  {'Last Updated (UTC)':<{lw}} {iso_ts}")
        print(f"  {'Switch':<{lw}} {switch}")
        print(f"  {'Port':<{lw}} {port}")
        print(f"  {'VLAN':<{lw}} {vlan}")
        print(f"  {'Name':<{lw}} {name}")
        print(f"  {'Username':<{lw}} {username}")
        print()

    print()
    entry = input("  Press Enter to return or 'e' to export to Excel: ").strip().lower()
    if entry == "e":
        filename = _prompt_filename()
        if filename:
            from datetime import datetime
            from pathlib import Path
            excel_dir = Path(EXCEL_DIR).resolve()
            excel_dir.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d-%H-%M")
            stem = Path(filename).stem
            outpath = str(excel_dir / f"{stem}-{ts}.xlsx")
            ok, msg = write_client_search_excel(clients, outpath)
            print(f"\n  {msg}")
    pause()


def action_ip_search(client):
    """IP address prefix search via /dna/data/api/v1/clients."""
    print()
    print("  IP address search  (wildcards supported, e.g. 10.1.2.* or 192.168.1)")
    print("  A trailing '*' is appended automatically.\n")
    ip_prefix = input("  IP prefix: ").strip()
    if not ip_prefix:
        print("  Cancelled.")
        pause()
        return

    device_filter = input("  Switch hostname filter (optional, wildcard ok, e.g. core*): ").strip() or None

    print()
    clients = client.search_clients_by_ip(ip_prefix, device_name=device_filter)

    if not clients:
        print("  No matching clients found.")
        pause()
        return

    print(f"\n  Found {len(clients)} client(s)\n")

    from datetime import datetime, timezone

    total = len(clients)
    for idx, c in enumerate(clients, 1):
        nd   = c.get("connectedNetworkDevice") or {}
        conn = c.get("connection") or {}

        mac      = c.get("macAddress") or "—"
        ctype    = c.get("type") or "—"
        vendor   = c.get("vendor") or "—"
        ip       = c.get("ipv4Address") or "—"
        status   = c.get("connectionStatus") or "—"
        name     = c.get("name") or "—"
        switch   = nd.get("connectedNetworkDeviceName") or "—"
        port     = nd.get("interfaceName") or "—"
        vlan     = conn.get("vlanId") or "—"
        username = c.get("username") or "—"

        raw_ts = c.get("lastUpdatedTime")
        if raw_ts:
            try:
                iso_ts = datetime.fromtimestamp(int(raw_ts) / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                iso_ts = "—"
        else:
            raw_ts = "—"
            iso_ts = "—"

        print(f"  ── {idx} / {total} {'─' * 44}")
        lw = 22
        print(f"  {'MAC':<{lw}} {mac}")
        print(f"  {'Type':<{lw}} {ctype}")
        print(f"  {'Vendor':<{lw}} {vendor}")
        print(f"  {'IP Address':<{lw}} {ip}")
        print(f"  {'Connection Status':<{lw}} {status}")
        print(f"  {'Last Updated (raw)':<{lw}} {raw_ts}")
        print(f"  {'Last Updated (UTC)':<{lw}} {iso_ts}")
        print(f"  {'Switch':<{lw}} {switch}")
        print(f"  {'Port':<{lw}} {port}")
        print(f"  {'VLAN':<{lw}} {vlan}")
        print(f"  {'Name':<{lw}} {name}")
        print(f"  {'Username':<{lw}} {username}")
        print()

    print()
    entry = input("  Press Enter to return or 'e' to export to Excel: ").strip().lower()
    if entry == "e":
        filename = _prompt_filename()
        if filename:
            from datetime import datetime
            from pathlib import Path
            excel_dir = Path(EXCEL_DIR).resolve()
            excel_dir.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y-%m-%d-%H-%M")
            stem = Path(filename).stem
            outpath = str(excel_dir / f"{stem}-{ts}.xlsx")
            ok, msg = write_client_search_excel(clients, outpath)
            print(f"\n  {msg}")
    pause()


def action_mac_lookup(client):
    """Prompt for a MAC address and display client-detail results."""
    print()
    mac = input("  MAC address: ").strip()
    if not mac:
        print("  Cancelled.")
        pause()
        return

    print(f"\n  Looking up {mac} ...")
    detail = client.lookup_client(mac)

    if not detail:
        print("  ✗ Not found — client may be offline, unknown to Assurance, or MAC format invalid.")
        pause()
        return

    from datetime import datetime, timezone

    switch    = detail.get("nasIdentifier") or "—"
    port      = detail.get("nasPortId")     or "—"
    vlan      = detail.get("vlanId")        or "—"
    status    = detail.get("connectionStatus") or "—"
    ipv4      = detail.get("ipv4")          or "—"
    hostname  = detail.get("hostName")      or "—"
    dev_type  = detail.get("deviceType")    or "—"
    user_id   = detail.get("userId")        or "—"

    def _fmt_ts(raw):
        if not raw:
            return "—", "—"
        try:
            iso = datetime.fromtimestamp(int(raw) / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            iso = "—"
        return str(raw), iso

    raw_lu, iso_lu = _fmt_ts(detail.get("lastUpdated"))
    raw_lc, iso_lc = _fmt_ts(detail.get("lastConnected"))

    lw = 22
    print()
    print(f"  {'MAC':<{lw}} {mac}")
    print(f"  {'Switch':<{lw}} {switch}")
    print(f"  {'Port':<{lw}} {port}")
    print(f"  {'VLAN':<{lw}} {vlan}")
    print(f"  {'Status':<{lw}} {status}")
    print(f"  {'IP':<{lw}} {ipv4}")
    print(f"  {'Hostname':<{lw}} {hostname}")
    print(f"  {'Device type':<{lw}} {dev_type}")
    print(f"  {'User':<{lw}} {user_id}")
    print(f"  {'Last Updated (raw)':<{lw}} {raw_lu}")
    print(f"  {'Last Updated (UTC)':<{lw}} {iso_lu}")
    print(f"  {'Last Connected (raw)':<{lw}} {raw_lc}")
    print(f"  {'Last Connected (UTC)':<{lw}} {iso_lc}")
    pause()


def menu_5(selected_devices, client, host, username):
    """Command execution menu for selected devices."""
    slow_mode = False
    copper_only = False
    link_state = False

    while True:
        theme_clear()
        slow_label = "ON  (poll 60s/3s, submit 20s, backoff×2)" if slow_mode else "off"
        copper_label = "ON" if copper_only else "off"
        link_label = "ON" if link_state else "off"
        print(f"  Host: {host}  |  User: {username}  |  Selected: {len(selected_devices)} device(s)  |  Slow mode: {slow_label}  |  Copper only: {copper_label}  |  Link-state: {link_label}\n")
        print("  Menu 5 — Commands\n")
        print("  1) Port report — one file per device")
        print("  2) Port report — one file, one tab per device")
        print("  3) Port report — consolidated (All Ports + utilisation + per-device tabs)")
        print("  4) Custom commands")
        print("  5) MAC address lookup (Assurance client-detail)")
        print("  6) MAC prefix search  (Assurance /clients, wildcard)")
        print("  7) IP address search  (Assurance /clients, wildcard)")
        print("  s) Toggle slow mode")
        print("  p) Toggle copper only")
        print("  l) Toggle link-state column")
        print("  8) Back")
        print()
        choice = input("  Select [1-8 / s / p / l]: ").strip().lower()

        if choice == "8":
            return

        elif choice == "s":
            slow_mode = not slow_mode

        elif choice == "p":
            copper_only = not copper_only

        elif choice == "l":
            link_state = not link_state

        elif choice in ("1", "2"):
            print()
            label = "Filename (stem — one file per device)" if choice == "1" and len(selected_devices) > 1 else "Filename"
            filename = _prompt_filename(label)
            if not filename:
                print("  Cancelled.")
                pause()
                continue
            if not menu_6(selected_devices, build_command_list(link_state)):
                continue
            _exec_and_report(selected_devices, client, build_command_list(link_state), int(choice), filename,
                             slow_mode=slow_mode, copper_only=copper_only)

        elif choice == "3":
            print()
            filename = _prompt_filename()
            if not filename:
                print("  Cancelled.")
                pause()
                continue
            threshold_str = input("  Port usage threshold in days [42]: ").strip()
            threshold = int(threshold_str) if threshold_str.isdigit() else 42
            if not menu_6(selected_devices, build_command_list(link_state)):
                continue
            _exec_and_report(selected_devices, client, build_command_list(link_state), 3, filename, threshold,
                             slow_mode=slow_mode, copper_only=copper_only)

        elif choice == "4":
            print()
            print("  Enter commands one per line. Blank line when done.")
            commands = []
            while True:
                cmd = input(f"  Command {len(commands)+1}: ").strip()
                if not cmd:
                    break
                commands.append(cmd)
            if not commands:
                print("  No commands entered.")
                pause()
                continue
            if not menu_6(selected_devices, commands):
                continue
            outputs = run_commands(selected_devices, client, commands)
            display_command_outputs(outputs)
            pause()

        elif choice == "5":
            action_mac_lookup(client)

        elif choice == "6":
            action_mac_search(client)

        elif choice == "7":
            action_ip_search(client)

        else:
            print("\n  Invalid selection.")
            pause()


# ============================================================================
# Entry Point
# ============================================================================

def main():
    theme_init()
    try:
        while True:
            creds = menu_1()
            host, username, password = creds
            menu_2(host, username, password)
    except KeyboardInterrupt:
        print("\n\nExiting.")
    finally:
        theme_reset()
    sys.exit(0)


if __name__ == "__main__":
    main()
