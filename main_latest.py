#!/usr/bin/env python3
"""
CHEAT — Cisco Homogenous Environment Awareness Tool
Two-stage interactive menu launcher.
"""

import getpass
import json
import sys
from pathlib import Path

from dnac_client import DNACClient


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
                        k, v = line.split("=", 1)
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
    client = _auth(host, username, password)
    if not client:
        pause()
        return None

    print("\n  Fetching all devices...\n")
    devices = client.get_devices()   # paginated; prints progress per page

    if not devices:
        print("  No devices returned.")
        pause()
        return None

    # Save to all_devices.json
    try:
        ALL_DEVICES_FILE.write_text(json.dumps(devices, indent=2))
        print(f"\n  ✓ Saved {len(devices)} device(s) to {ALL_DEVICES_FILE}")
    except Exception as e:
        print(f"\n  Warning: could not write {ALL_DEVICES_FILE}: {e}")

    print(f"\n  {'#':<5} {'Hostname':<45} {'Platform':<22} {'IP Address'}")
    print(f"  {'-'*5} {'-'*45} {'-'*22} {'-'*15}")
    for i, d in enumerate(devices, 1):
        hostname = d.get("hostname", "unknown")
        platform = d.get("platformId", "")
        ip = d.get("managementIpAddress", "")
        print(f"  {i:<5} {hostname:<45} {platform:<22} {ip}")
    print(f"\n  Total: {len(devices)} device(s)")

    print()
    nav = input("  Press Enter to continue or 'quit' to return to Menu 2: ").strip().lower()
    if nav == "quit":
        return None
    return devices


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
            devices = action_get_devices(host, username, password)
            if devices is not None:
                menu_3(devices, host, username)
        elif choice == "2":
            action_get_version(host, username, password)
        else:
            print("\n  Invalid selection.")
            pause()


# ============================================================================
# Menu 3 — Device Actions
# ============================================================================

def menu_3(devices, host, username):
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
            selected = menu_4(devices, host, username)
            if selected:
                # TODO: proceed to next stage with selected devices
                print(f"\n  Proceeding with {len(selected)} device(s)...")
                pause()
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
    """Parse comma-separated numbers and ranges (e.g. '1,3-5') into a list of indices."""
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


def menu_4(devices, host, username):
    """
    Switch selection screen.
    Displays devices as numbered checkboxes; type numbers to toggle selection.
    Enter 'p' or blank with selections made to Proceed; 'b' to go Back.
    Returns list of selected device dicts, or [] if user went back.
    """
    # Filter to likely switches (hostnames or platforms containing common switch identifiers)
    switch_keywords = ("3850", "9300", "9200", "3650", "2960", "catalyst", "sw", "switch")
    switches = [
        d for d in devices
        if any(kw in (d.get("hostname") or "").lower() or
               kw in (d.get("platformId") or "").lower()
               for kw in switch_keywords)
    ] or devices  # fall back to all devices if no keyword match

    selected = set()  # indices (1-based) of selected devices

    while True:
        banner()
        print(f"  Host: {host}  |  Showing: {len(switches)} switch(es)\n")
        print(f"  Menu 4 — Select Switches\n")
        print(f"  {'#':<5} {'':3} {'Hostname':<40} {'Platform':<20} {'IP Address'}")
        print(f"  {'-'*5} {'-'*3} {'-'*40} {'-'*20} {'-'*15}")
        for i, d in enumerate(switches, 1):
            check = "[X]" if i in selected else "[ ]"
            hostname = d.get("hostname", "unknown")
            platform = d.get("platformId", "")
            ip = d.get("managementIpAddress", "")
            print(f"  {i:<5} {check} {hostname:<40} {platform:<20} {ip}")

        sel_count = len(selected)
        print(f"\n  Selected: {sel_count} device(s)")
        print()
        print("  Enter number(s) to toggle (e.g. 1  or  1,3-5)")
        print("  'p' + Enter to Proceed  |  'b' + Enter to go Back")
        print()
        entry = input("  > ").strip().lower()

        if entry == "b":
            return []
        elif entry in ("p", "") and selected:
            return [switches[i - 1] for i in sorted(selected)]
        elif entry in ("p", ""):
            print("\n  No devices selected — pick at least one.")
            pause()
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
