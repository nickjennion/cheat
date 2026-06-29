#!/usr/bin/env python3
"""
CHEAT — Cisco Homogenous Environment Awareness Tool
Interactive menu launcher.
"""

import getpass
import json
import sys
from pathlib import Path

from dnac_client import DNACClient
from cheat_core import (
    DNAC_COMMANDS,
    EXCEL_DIR,
    run_commands,
    parse_outputs,
    generate_excel,
)


ENV_FILE = Path("dnac.env")
SAMPLE_FILE = Path("sample_dnac.env")
ALL_DEVICES_FILE = Path("all_devices.json")


# ============================================================================
# Helpers
# ============================================================================

def banner():
    print()
    print("=" * 55)
    print("  CHEAT — Cisco Homogenous Environment Awareness Tool")
    print("=" * 55)
    print()


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


def _prompt_filename():
    """Prompt for an Excel filename; append .xlsx if omitted. Returns None if blank."""
    name = input("  Filename: ").strip()
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
        banner()
        print("  Menu 1 — Credentials\n")
        print("  1) Use dnac.env")
        print("  2) Enter manually")
        print("  3) View dnac.env")
        print()
        choice = input("  Select [1-3]: ").strip()

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

        elif choice == "2":
            print()
            host = input("    DNAC host (FQDN or IP, no https://): ").strip()
            username = input("    Username: ").strip()
            password = getpass.getpass("    Password: ")
            if host and username and password:
                return host, username, password
            print("\n  ✗ All fields required.")
            pause()

        elif choice == "3":
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

        else:
            print("\n  Invalid selection.")
            pause()


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
        print(f"  {i:<5} {d.get('hostname','unknown'):<45} {d.get('platformId',''):<22} {d.get('managementIpAddress','')}")
    print(f"\n  Total: {len(devices)} device(s)")

    print()
    nav = input("  Press Enter to continue or 'quit' to return to Menu 2: ").strip().lower()
    if nav == "quit":
        return None, None
    return devices, client


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
        banner()
        print(f"  Host: {host}  |  User: {username}\n")
        print("  Menu 2 — Actions\n")
        print("  1) Auth & Get Devices (All)")
        print("  2) Auth & Get DNAC Version")
        print("  0) Back")
        print()
        choice = input("  Select [0-2]: ").strip()

        if choice == "0":
            return
        elif choice == "1":
            devices, client = action_get_devices(host, username, password)
            if devices is not None:
                menu_3(devices, client, host, username)
        elif choice == "2":
            action_get_version(host, username, password)
        else:
            print("\n  Invalid selection.")
            pause()


# ============================================================================
# Menu 3 — Device Actions
# ============================================================================

def menu_3(devices, client, host, username):
    """Device actions menu — operates on the loaded inventory."""
    while True:
        banner()
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
            banner()
            print(f"  {'#':<5} {'Hostname':<45} {'Platform':<22} {'IP Address'}")
            print(f"  {'-'*5} {'-'*45} {'-'*22} {'-'*15}")
            for i, d in enumerate(devices, 1):
                print(f"  {i:<5} {d.get('hostname',''):<45} {d.get('platformId',''):<22} {d.get('managementIpAddress','')}")
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


def menu_4(devices, client, host, username):
    """Switch selection screen. Returns list of selected device dicts, or []."""
    filter_term = ""
    selected = set()

    while True:
        # Apply filter
        if filter_term:
            switches = [
                d for d in devices
                if filter_term in (d.get("hostname") or "").lower()
                or filter_term in (d.get("platformId") or "").lower()
            ]
        else:
            switches = []

        banner()
        print(f"  Host: {host}  |  Filter: '{filter_term or '(none)'}'\n")
        print(f"  Menu 4 — Select Switches\n")

        if not filter_term:
            print("  Enter a filter term to show matching devices (e.g. 3850, sw, core)")
        elif not switches:
            print(f"  No devices matched '{filter_term}'")
        else:
            print(f"  {'#':<5} {'':3} {'Hostname':<40} {'Platform':<20} {'IP Address'}")
            print(f"  {'-'*5} {'-'*3} {'-'*40} {'-'*20} {'-'*15}")
            for i, d in enumerate(switches, 1):
                check = "[X]" if i in selected else "[ ]"
                print(f"  {i:<5} {check} {d.get('hostname','unknown'):<40} {d.get('platformId',''):<20} {d.get('managementIpAddress','')}")
            print(f"\n  Selected: {len(selected)} device(s)")

        print()
        print("  'f <term>' to filter  |  number(s) to toggle (e.g. 1  or  1,3-5)")
        print("  'p' to Proceed        |  'b' to go Back")
        print()
        entry = input("  > ").strip()

        if entry.lower() == "b":
            return []
        elif entry.lower() == "p" or entry == "":
            if not selected:
                print("\n  No devices selected — pick at least one.")
                pause()
            else:
                return [switches[i - 1] for i in sorted(selected) if i <= len(switches)]
        elif entry.lower().startswith("f "):
            filter_term = entry[2:].strip().lower()
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
    banner()
    print("  Menu 6 — Confirm Execution\n")
    print("  You are about to execute:\n")
    for cmd in commands:
        print(f"    • {cmd}")
    print(f"\n  On:\n")
    for d in selected_devices:
        print(f"    • {d.get('hostname', 'unknown')}  ({d.get('managementIpAddress', '')})")
    print()
    entry = input("  Press Enter to proceed or 'b' to go back: ").strip().lower()
    return entry != "b"


# ============================================================================
# Menu 5 — Commands
# ============================================================================

def _exec_and_report(selected_devices, client, commands, mode, filename, threshold=42):
    """Run commands → parse → generate Excel. Used by menu_5 options 1-3."""
    outputs = run_commands(selected_devices, client, commands)
    if not outputs:
        pause()
        return
    devices_data = parse_outputs(outputs)
    if not devices_data:
        pause()
        return
    stem = Path(filename).stem
    results = generate_excel(devices_data, mode, stem, threshold)
    for _, msg in results:
        print(f"\n  {msg}")
    pause()


def menu_5(selected_devices, client, host, username):
    """Command execution menu for selected devices."""
    while True:
        banner()
        print(f"  Host: {host}  |  User: {username}  |  Selected: {len(selected_devices)} device(s)\n")
        print("  Menu 5 — Commands\n")
        print("  1) Get port info (separate Excel per device)")
        print("  2) Get port info (one workbook, one sheet per device)")
        print("  3) Get port info + port usage tab")
        print("  4) Custom commands")
        print("  5) Back")
        print()
        choice = input("  Select [1-5]: ").strip()

        if choice == "5":
            return

        elif choice in ("1", "2"):
            print()
            filename = _prompt_filename()
            if not filename:
                print("  Cancelled.")
                pause()
                continue
            if not menu_6(selected_devices, DNAC_COMMANDS):
                continue
            _exec_and_report(selected_devices, client, DNAC_COMMANDS, int(choice), filename)

        elif choice == "3":
            print()
            filename = _prompt_filename()
            if not filename:
                print("  Cancelled.")
                pause()
                continue
            threshold_str = input("  Port usage threshold in days [42]: ").strip()
            threshold = int(threshold_str) if threshold_str.isdigit() else 42
            if not menu_6(selected_devices, DNAC_COMMANDS):
                continue
            _exec_and_report(selected_devices, client, DNAC_COMMANDS, 3, filename, threshold)

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
            # TODO: route through menu_6 when option 4 is fully built out
            run_commands(selected_devices, client, commands)
            pause()

        else:
            print("\n  Invalid selection.")
            pause()


# ============================================================================
# Entry Point
# ============================================================================

def main():
    try:
        while True:
            creds = menu_1()
            host, username, password = creds
            menu_2(host, username, password)
    except KeyboardInterrupt:
        print("\n\nExiting.")
        sys.exit(0)


if __name__ == "__main__":
    main()
