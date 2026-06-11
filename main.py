#!/usr/bin/env python3
import json
import sys
import getpass
from pathlib import Path
from dnac_client import DNACClient


def get_credentials() -> tuple[str, str, str]:
    """Interactively prompt for DNAC server, username, and password."""
    print("=" * 60)
    print("Cisco DNAC Device Query Tool")
    print("=" * 60)
    print()

    host = input("Enter DNAC server hostname/IP: ").strip()
    if not host:
        print("Error: hostname/IP is required")
        sys.exit(1)

    username = input("Enter username: ").strip()
    if not username:
        print("Error: username is required")
        sys.exit(1)

    password = getpass.getpass("Enter password: ")
    if not password:
        print("Error: password is required")
        sys.exit(1)

    return host, username, password


def authenticate_and_fetch(host: str, username: str, password: str) -> list[dict] | None:
    """Authenticate with DNAC and fetch all devices."""
    print("\nAuthenticating...")
    client = DNACClient(host, username, password)

    if not client.authenticate():
        print("Error: Failed to authenticate with DNAC")
        return None

    print("✓ Authentication successful")
    print("\nFetching devices...")
    devices = client.get_devices()

    if not devices:
        print("No devices found or failed to retrieve devices")
        return None

    print(f"✓ Found {len(devices)} devices")
    return devices, client


def save_devices(devices: list[dict], filename: str = "all_devices.json") -> bool:
    """Save devices to JSON file."""
    try:
        with open(filename, "w") as f:
            json.dump(devices, f, indent=2)
        print(f"✓ Saved {len(devices)} devices to {filename}")
        return True
    except IOError as e:
        print(f"Error saving devices: {e}")
        return False


def filter_devices_by_hostname(devices: list[dict], hostname_filter: str) -> list[dict]:
    """Filter devices by hostname pattern (case-insensitive substring match)."""
    pattern = hostname_filter.lower()
    return [
        d for d in devices
        if pattern in d.get("hostname", "").lower()
    ]


def display_devices(devices: list[dict]) -> None:
    """Display devices in a readable format."""
    if not devices:
        print("No devices found matching filter.")
        return

    print(f"\n{'Hostname':<30} {'IP Address':<15} {'Type':<20} {'Status':<10}")
    print("-" * 75)

    for device in devices:
        hostname = device.get("hostname", "N/A")[:29]
        ip = device.get("managementIpAddress", "N/A")[:14]
        device_type = device.get("type", "N/A")[:19]
        status = device.get("reachabilityStatus", "N/A")[:9]
        print(f"{hostname:<30} {ip:<15} {device_type:<20} {status:<10}")


def interactive_query(devices: list[dict], client: DNACClient) -> None:
    """Interactively query devices by hostname."""
    while True:
        print("\n" + "=" * 60)
        hostname_filter = input("Enter hostname filter (or 'quit' to exit): ").strip()

        if hostname_filter.lower() == "quit":
            print("Exiting...")
            break

        if not hostname_filter:
            print("Please enter a hostname filter")
            continue

        filtered = filter_devices_by_hostname(devices, hostname_filter)
        print(f"\nFound {len(filtered)} device(s) matching '{hostname_filter}':")
        display_devices(filtered)


def main():
    """Main application flow."""
    try:
        host, username, password = get_credentials()

        result = authenticate_and_fetch(host, username, password)
        if result is None:
            sys.exit(1)

        devices, client = result

        if not save_devices(devices):
            print("Warning: Failed to save devices, continuing...")

        interactive_query(devices, client)

    except KeyboardInterrupt:
        print("\n\nExiting...")
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
