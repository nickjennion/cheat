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
    """Placeholder — device-level actions on the downloaded inventory."""
    while True:
        banner()
        print(f"  Host: {host}  |  User: {username}  |  Devices loaded: {len(devices)}\n")
        print("  Menu 3 — Device Actions\n")
        print("  (coming soon)\n")
        print("  0) Back to Menu 2")
        print()
        choice = input("  Select [0]: ").strip()

        if choice == "0":
            return
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
