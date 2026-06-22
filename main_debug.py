#!/usr/bin/env python3
"""
CHEAT UNPLUGGED — Network port discovery and inventory tool.

Queries DNAC for devices, executes diagnostics via Command Runner,
parses outputs, and generates Excel reports for cable management workflows.

DEBUG VERSION - Enhanced logging for troubleshooting
"""

import json
import sys
import getpass
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

from dnac_client import DNACClient
from interface_parser import parse_output
from excel_generator import write_excel


# ============================================================================
# Constants
# ============================================================================

DNAC_COMMANDS = [
    "show hardware",
    "show interfaces",
    "show interfaces status",
    "show interface counters"
]

COMMAND_POLLING_TIMEOUT_SECONDS = 30
COMMAND_POLLING_INTERVAL_SECONDS = 1
DEBUG = True  # Enable debug output


def debug_print(msg: str):
    """Print debug message if DEBUG is enabled."""
    if DEBUG:
        print(f"[DEBUG] {msg}")


# ============================================================================
# Credential Handling
# ============================================================================

def get_credentials() -> tuple[str, str, str]:
    """Interactively prompt for DNAC credentials."""
    print("=" * 60)
    print("CHEAT UNPLUGGED — Network Port Discovery (DEBUG MODE)")
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


# ============================================================================
# Device Management
# ============================================================================

def authenticate_and_fetch(host: str, username: str, password: str) -> Optional[tuple[list[dict], DNACClient]]:
    """Authenticate with DNAC and fetch all devices."""
    print("\nAuthenticating...")
    debug_print(f"Connecting to: {host}")

    client = DNACClient(host, username, password)

    if not client.authenticate():
        print("✗ Authentication failed")
        return None

    print("✓ Authentication successful")
    debug_print(f"Token: {client.token[:30]}..." if client.token else "No token")
    print("\nFetching devices...")

    devices = client.get_devices()
    if not devices:
        print("✗ No devices found or failed to retrieve devices")
        return None

    print(f"✓ Found {len(devices)} devices")
    debug_print(f"Device count: {len(devices)}")
    return devices, client


def save_devices(devices: list[dict], filename: str = "all_devices.json") -> bool:
    """Save device inventory to JSON file."""
    try:
        with open(filename, "w") as f:
            json.dump(devices, f, indent=2)
        print(f"✓ Saved {len(devices)} devices to {filename}")
        debug_print(f"Saved to: {Path(filename).absolute()}")
        return True
    except IOError as e:
        print(f"✗ Error saving devices: {e}")
        return False


def filter_devices_by_hostname(devices: list[dict], hostname_filter: str) -> list[dict]:
    """Filter devices by hostname (case-insensitive substring match)."""
    pattern = hostname_filter.lower()
    filtered = [d for d in devices if pattern in d.get("hostname", "").lower()]
    debug_print(f"Filter '{hostname_filter}' matched {len(filtered)} of {len(devices)} devices")
    return filtered


def display_devices(devices: list[dict]) -> None:
    """Display devices in formatted table."""
    if not devices:
        print("No devices found.")
        return

    print(f"\n{'#':<3} {'Hostname':<25} {'Model':<20} {'IP Address':<15} {'Serial':<20} {'UUID':<36}")
    print("-" * 119)

    for idx, device in enumerate(devices, start=1):
        hostname = device.get("hostname", "N/A")[:24]
        model = device.get("type", "N/A")[:19]
        ip = device.get("managementIpAddress", "N/A")[:14]
        serial = device.get("serialNumber", "N/A")[:19]
        uuid = device.get("id", "N/A")[:35]
        print(f"{idx:<3} {hostname:<25} {model:<20} {ip:<15} {serial:<20} {uuid:<36}")


# ============================================================================
# Device Selection
# ============================================================================

def select_devices(devices: list[dict]) -> Optional[list[dict]]:
    """Interactive device selection (single or batch)."""
    while True:
        print("\nOptions:")
        print("  's' - Select single device")
        print("  'b' - Select batch of devices")
        print("  'f' - Filter and try again")
        print("  'q' - Quit")
        choice = input("\nChoice: ").strip().lower()

        if choice == "q":
            return []

        if choice == "f":
            return None

        if choice == "s":
            device_num = input("Enter device number: ").strip()
            try:
                idx = int(device_num) - 1
                if 0 <= idx < len(devices):
                    selected = [devices[idx]]
                    debug_print(f"Selected single device: {selected[0].get('hostname')}")
                    return selected
                else:
                    print(f"✗ Invalid device number (1-{len(devices)})")
            except ValueError:
                print("✗ Please enter a number")
            continue

        if choice == "b":
            device_nums = input("Enter device numbers (comma-separated): ").strip()
            selected = []
            try:
                for num_str in device_nums.split(","):
                    idx = int(num_str.strip()) - 1
                    if 0 <= idx < len(devices):
                        selected.append(devices[idx])
                    else:
                        print(f"  (skipped invalid: {num_str.strip()})")
                if selected:
                    debug_print(f"Selected {len(selected)} devices: {[d.get('hostname') for d in selected]}")
                    return selected
                else:
                    print("✗ No valid devices selected")
            except ValueError:
                print("✗ Please enter numbers separated by commas")
            continue

        print("✗ Invalid choice")


# ============================================================================
# Command Execution
# ============================================================================

def execute_on_devices(
    selected_devices: list[dict],
    client: DNACClient,
    session_timestamp: str
) -> dict[str, str]:
    """
    Execute commands on selected devices and save outputs.
    Returns dict of {hostname: output_text}.
    """
    outputs = {}
    failed_devices = []

    for device in selected_devices:
        hostname = device.get("hostname", "unknown")
        device_id = device.get("id")

        print(f"\n{'='*60}")
        print(f"Device: {hostname}")
        print(f"Device ID: {device_id}")
        print(f"{'='*60}")

        debug_print(f"Starting command execution on {hostname} (ID: {device_id})")

        # Execute commands
        print(f"Executing {len(DNAC_COMMANDS)} commands via Command Runner...")
        debug_print(f"Commands: {DNAC_COMMANDS}")

        task_id = client.execute_commands(device_id, DNAC_COMMANDS)

        if not task_id:
            print(f"✗ Failed to start command execution on {hostname}")
            debug_print(f"execute_commands() returned None for {hostname}")
            failed_devices.append(hostname)
            continue

        print(f"Task ID: {task_id}")
        debug_print(f"Received task ID: {task_id}")
        print(f"Polling for results ({COMMAND_POLLING_TIMEOUT_SECONDS}s timeout)...")

        # Poll for results
        result = None
        poll_attempt = 0
        for i in range(COMMAND_POLLING_TIMEOUT_SECONDS):
            time.sleep(COMMAND_POLLING_INTERVAL_SECONDS)
            poll_attempt += 1

            debug_print(f"Poll attempt {poll_attempt}/{COMMAND_POLLING_TIMEOUT_SECONDS} for task {task_id}")

            task_result = client.get_task_result(task_id)
            debug_print(f"Poll result type: {type(task_result)}, keys: {task_result.keys() if task_result else 'None'}")

            if task_result:
                debug_print(f"Task result: {json.dumps(task_result, indent=2, default=str)[:500]}...")
                if task_result.get("endTime"):
                    result = task_result
                    print(f"✓ Commands completed in {i+1} seconds")
                    debug_print(f"Task completed after {i+1} seconds")
                    break

            remaining = COMMAND_POLLING_TIMEOUT_SECONDS - (i + 1)
            if remaining > 0 and remaining % 5 == 0:
                print(f"  [{COMMAND_POLLING_TIMEOUT_SECONDS - i}s remaining...]")

        if not result:
            print(f"✗ Command execution timed out on {hostname}")
            debug_print(f"Timeout waiting for task {task_id}")
            failed_devices.append(hostname)
            continue

        # Extract output
        output_text = result.get("result", "")
        debug_print(f"Output text length: {len(output_text)} bytes")
        debug_print(f"Output preview: {output_text[:200]}...")

        if not output_text:
            print(f"✗ No output received from {hostname}")
            debug_print(f"Result has no 'result' field or it's empty")
            failed_devices.append(hostname)
            continue

        # Save output to file
        filename = f"command_output_{hostname}_{session_timestamp}.txt"
        try:
            with open(filename, "w") as f:
                f.write(output_text)
            outputs[hostname] = output_text
            print(f"✓ Output saved: {filename}")
            debug_print(f"Saved output to: {Path(filename).absolute()}")
        except IOError as e:
            print(f"✗ Failed to save output: {e}")
            debug_print(f"File save error: {e}")
            failed_devices.append(hostname)

    # Report summary
    if failed_devices:
        print(f"\n⚠ Failed on {len(failed_devices)} device(s): {', '.join(failed_devices)}")
    if outputs:
        print(f"\n✓ Successfully executed on {len(outputs)} device(s)")

    return outputs


# ============================================================================
# Parsing & Excel Generation
# ============================================================================

def parse_and_generate_excel(outputs: dict[str, str], session_timestamp: str) -> bool:
    """
    Parse command outputs and generate Excel report.
    Returns success status.
    """
    if not outputs:
        print("✗ No command outputs to parse")
        return False

    print("\n" + "=" * 60)
    print("Parsing outputs and generating Excel...")
    print("=" * 60)

    devices_data = {}
    parse_failures = []

    for hostname, output_text in outputs.items():
        print(f"\nParsing {hostname}...", end=" ")
        debug_print(f"Parsing output from {hostname} ({len(output_text)} bytes)")

        try:
            records, stack_members = parse_output(output_text, hostname)
            debug_print(f"Parsed {len(records)} interfaces, {len(stack_members)} stack members")

            if not records:
                print(f"⚠ No interfaces found (parsing may have failed)")
                debug_print(f"No interfaces extracted from {hostname}")
                parse_failures.append(hostname)
                continue

            devices_data[hostname] = (records, stack_members)
            print(f"✓ {len(records)} interfaces")

        except Exception as e:
            print(f"✗ Parsing error: {e}")
            debug_print(f"Exception parsing {hostname}: {e}")
            import traceback
            debug_print(traceback.format_exc())
            parse_failures.append(hostname)

    if parse_failures:
        print(f"\n⚠ Parsing failed or found no data on: {', '.join(parse_failures)}")

    if not devices_data:
        print("✗ No parsed data to write to Excel")
        return False

    # Generate Excel
    excel_filename = f"unpatching_list_{session_timestamp}.xlsx"
    debug_print(f"Generating Excel: {excel_filename}")
    success, message = write_excel(devices_data, excel_filename)
    print(f"\n{message}")
    debug_print(f"Excel generation result: {success}, message: {message}")
    return success


# ============================================================================
# Main Workflow
# ============================================================================

def main():
    """Main application loop."""
    try:
        # Authentication
        host, username, password = get_credentials()
        result = authenticate_and_fetch(host, username, password)
        if result is None:
            sys.exit(1)

        devices, client = result
        save_devices(devices)

        session_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        debug_print(f"Session timestamp: {session_timestamp}")

        # Main loop: filter → select → execute → parse
        while True:
            print("\n" + "=" * 60)
            hostname_filter = input("Enter hostname filter (or 'quit' to exit): ").strip()

            if hostname_filter.lower() == "quit":
                print("Exiting...")
                sys.exit(0)

            if not hostname_filter:
                print("✗ Please enter a hostname filter")
                continue

            filtered = filter_devices_by_hostname(devices, hostname_filter)
            print(f"\nFound {len(filtered)} device(s):")

            if not filtered:
                print("(no matches)")
                continue

            display_devices(filtered)

            selected = select_devices(filtered)
            if selected is None:
                continue
            if not selected:
                continue

            # Execute and parse
            outputs = execute_on_devices(selected, client, session_timestamp)
            if outputs:
                parse_and_generate_excel(outputs, session_timestamp)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        debug_print(f"Fatal exception: {e}")
        import traceback
        debug_print(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
