#!/usr/bin/env python3
"""
CHEAT UNPLUGGED — Network port discovery and inventory tool.

Queries DNAC for devices, executes diagnostics via Command Runner,
parses outputs, and generates Excel reports for cable management workflows.

DEBUG VERSION - Enhanced logging for troubleshooting
"""

import argparse
import json
import sys
import getpass
import time
import fnmatch
from pathlib import Path
from datetime import datetime
from typing import Optional

from dnac_client import DNACClient
from interface_parser import parse_output
from excel_generator import write_combined_excel


# ============================================================================
# Constants
# ============================================================================

DNAC_COMMANDS = [
    "show hardware",
    "show interfaces",
    "show interfaces status",
    "show interface counters",
    "show cdp neighbors"
]

# Generated command-runner outputs and reports are written here.
COMMAND_RUNNER_DIR = "command_runner_outputs"
EXCEL_DIR = "excel_reports"

COMMAND_POLLING_TIMEOUT_SECONDS = 30
COMMAND_POLLING_INTERVAL_SECONDS = 1
DEBUG = True  # Enable debug output
# TODO: merge into main.py with --debug flag


def debug_print(msg: str):
    """Print debug message if DEBUG is enabled."""
    if DEBUG:
        print(f"[DEBUG] {msg}")


# ============================================================================
# Argument Parsing
# ============================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="CHEAT UNPLUGGED — Network port discovery and inventory (DEBUG)"
    )
    parser.add_argument("--host", help="DNAC server hostname/IP")
    parser.add_argument("--username", help="DNAC username")
    parser.add_argument("--password", nargs='?', const=None,
                        help="DNAC password (omit value for interactive prompt)")
    parser.add_argument("--filter", help="Hostname filter pattern (e.g. 'switch-*')")
    parser.add_argument("--batch", help="Device numbers to select (e.g. '1,3-5')")
    parser.add_argument("--dry-run", action="store_true",
                        help="Authenticate and preview, skip command execution")
    parser.add_argument("--command-runner-dir", default="command_runner_outputs",
                        help="Directory for raw command runner output files (default: command_runner_outputs/)")
    parser.add_argument("--excel-dir", default="excel_reports",
                        help="Directory for Excel report output (default: excel_reports/)")
    parser.add_argument("--port-util-threshold", type=int, default=None,
                        help="Port utilisation threshold in days (default: prompt, 42 if not specified)")
    parser.add_argument("--filename",
                        help="Excel filename prefix (default: prompt for 'port-information')")
    return parser.parse_args()


# ============================================================================
# Credential Handling
# ============================================================================

def load_credentials_from_env() -> Optional[tuple[str, str, str]]:
    """Load DNAC credentials from dnac.env file if it exists."""
    env_file = Path("dnac.env")

    if not env_file.exists():
        debug_print("No dnac.env file found")
        return None

    try:
        credentials = {}
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    credentials[key.strip()] = value.strip()

        host = credentials.get("DNAC_HOST")
        username = credentials.get("DNAC_USERNAME")
        password = credentials.get("DNAC_PASSWORD")

        if host and username and password:
            print("✓ Loaded credentials from dnac.env")
            debug_print(f"Credentials: host={host}, username={username}")
            return host, username, password
        else:
            debug_print("dnac.env missing required fields")
    except Exception as e:
        print(f"Warning: Failed to load dnac.env: {e}")
        debug_print(f"Exception loading dnac.env: {e}")

    return None


def get_credentials(args=None) -> tuple[str, str, str]:
    """Return DNAC credentials.

    Precedence: CLI args → dnac.env file → interactive prompt.
    If args provides host+username and password is None, interactive getpass is called.
    """
    print("=" * 60)
    print("CHEAT UNPLUGGED — Network Port Discovery (DEBUG MODE)")
    print("=" * 60)
    print()

    # CLI args take highest priority
    if args is not None:
        cli_host = getattr(args, "host", None)
        cli_username = getattr(args, "username", None)
        cli_password_raw = getattr(args, "password", None)
        # Distinguish: --password VALUE (non-None) vs --password with no value (None but
        # flag present in argv) vs --password not supplied at all (None, flag absent).
        password_flag_present = "--password" in sys.argv

        if cli_host and cli_username:
            if cli_password_raw is not None:
                debug_print(f"Using CLI credentials: host={cli_host}, username={cli_username}")
                print("✓ Using CLI credentials")
                return cli_host, cli_username, cli_password_raw
            elif password_flag_present:
                # --password supplied without a value → caller wants interactive prompt
                cli_password = getpass.getpass("Enter password: ")
                if not cli_password:
                    print("Error: password is required")
                    sys.exit(1)
                debug_print(f"Using CLI credentials (interactive password): host={cli_host}, username={cli_username}")
                return cli_host, cli_username, cli_password
            # else: --password not supplied at all → fall through to dnac.env / interactive

    # Try to load from environment file first
    env_creds = load_credentials_from_env()
    if env_creds:
        return env_creds

    # Prompt user interactively
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
    """Filter devices by hostname (wildcard pattern matching, case-insensitive).

    Supports * (match any chars) and ? (match single char).
    Works as substring match - pattern is wrapped with * on both sides.
    Examples: xyz*3850 matches xyz-wsx-3850.fqdn.com
    """
    pattern = f"*{hostname_filter.lower()}*"
    filtered = [d for d in devices if fnmatch.fnmatch((d.get("hostname") or "").lower(), pattern)]
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

def parse_device_numbers(input_str: str, max_devices: int) -> list[int]:
    """Parse device number input supporting ranges.

    Input examples: "1,3,5-8,10" → [1, 3, 5, 6, 7, 8, 10]
    Returns list of device numbers (1-indexed).
    """
    indices = []
    for segment in input_str.split(","):
        segment = segment.strip()
        if not segment:
            continue

        if "-" in segment:
            try:
                parts = segment.split("-")
                if len(parts) != 2:
                    print(f"  (skipped invalid range: {segment})")
                    continue
                start = int(parts[0].strip())
                end = int(parts[1].strip())
                if start > end:
                    start, end = end, start
                for num in range(start, end + 1):
                    if 1 <= num <= max_devices:
                        indices.append(num)
                    else:
                        print(f"  (skipped out of range: {num})")
            except ValueError:
                print(f"  (skipped invalid range: {segment})")
        else:
            try:
                num = int(segment)
                if 1 <= num <= max_devices:
                    indices.append(num)
                else:
                    print(f"  (skipped out of range: {num})")
            except ValueError:
                print(f"  (skipped invalid: {segment})")

    return list(dict.fromkeys(indices))


def select_devices(devices: list[dict]) -> Optional[list[dict]]:
    """Interactive device selection (single or batch)."""
    while True:
        print("\nOptions:")
        print("  's' - Select single device")
        print("  'b' - Select batch of devices (supports ranges: 1-5,7,9-12)")
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
            device_nums = input("Enter device numbers (e.g., 1,3,5-8,10): ").strip()
            device_indices = parse_device_numbers(device_nums, len(devices))
            if device_indices:
                selected = [devices[num - 1] for num in device_indices]
                debug_print(f"Selected {len(selected)} devices: {[d.get('hostname') for d in selected]}")
                return selected
            else:
                print("✗ No valid devices selected")
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

        # Extract fileId from progress JSON
        output_text = None
        try:
            progress_json = json.loads(result.get("progress", "{}"))
            file_id = progress_json.get("fileId")
            debug_print(f"Extracted from progress JSON: fileId={file_id}")

            if file_id:
                print(f"Fetching output file: {file_id}")
                debug_print(f"Calling get_file_output({file_id})")
                output_text = client.get_file_output(file_id)

                if not output_text:
                    print(f"✗ Failed to fetch output file")
                    debug_print(f"get_file_output({file_id}) returned empty")
                    failed_devices.append(hostname)
                    continue

                debug_print(f"Output text length: {len(output_text)} bytes")
                debug_print(f"Output preview: {output_text[:200]}...")
            else:
                print(f"✗ No fileId found in task result")
                debug_print(f"No fileId in progress JSON: {result.get('progress')}")
                failed_devices.append(hostname)
                continue
        except json.JSONDecodeError as e:
            print(f"✗ Failed to parse progress JSON: {e}")
            debug_print(f"JSON parse error: {e}, progress={result.get('progress')}")
            failed_devices.append(hostname)
            continue

        # Parse JSON if needed and extract command responses
        try:
            response_data = json.loads(output_text)
            debug_print(f"Output is JSON, parsing commandResponses")
            if isinstance(response_data, list) and len(response_data) > 0:
                cmd_responses = response_data[0].get("commandResponses", {}).get("SUCCESS", {})
                if cmd_responses:
                    debug_print(f"Found {len(cmd_responses)} command responses")
                    concatenated_output = ""
                    for cmd, output in cmd_responses.items():
                        concatenated_output += output + "\n\n"
                    output_text = concatenated_output
                    debug_print(f"Concatenated output length: {len(output_text)} bytes")
        except (json.JSONDecodeError, IndexError, KeyError, TypeError) as e:
            debug_print(f"Not JSON or parsing failed ({type(e).__name__}), treating as plain text")
            pass

        # Save output to file
        cmd_dir = Path(COMMAND_RUNNER_DIR).resolve()
        cmd_dir.mkdir(exist_ok=True)
        filename = str(cmd_dir / f"command_output_{hostname}_{session_timestamp}.txt")
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

def parse_and_generate_excel(
    outputs: dict[str, str],
    session_timestamp: str,
    threshold_days: int,
    filename_prefix: str
) -> tuple[bool, Optional[str]]:
    """Parse command outputs and generate combined Excel report."""
    if not outputs:
        print("✗ No command outputs to parse")
        return False, None

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
        return False, None

    excel_dir = Path(EXCEL_DIR).resolve()
    excel_dir.mkdir(exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d-%H-%M")
    excel_filename = str(excel_dir / f"{filename_prefix}-{date_str}.xlsx")
    debug_print(f"Generating Excel: {excel_filename}")
    success, message = write_combined_excel(devices_data, threshold_days, excel_filename)
    print(f"\n{message}")
    debug_print(f"Excel generation result: {success}, message: {message}")
    return success, excel_filename if success else None


# ============================================================================
# Dry-Run Preview
# ============================================================================

def print_dry_run_summary(devices, commands, timestamp, output_dir, filename_prefix="port-information"):
    """Print a preview of what would be executed without doing anything."""
    print("\n[DRY RUN] Would execute the following:")
    print(f"  Devices ({len(devices)}):")
    for d in devices:
        print(f"    - {d.get('hostname', 'unknown')} ({d.get('managementIpAddress', '?')})"
              f" [{d.get('type', '?')}]")
    print(f"  Commands ({len(commands)}):")
    for cmd in commands:
        print(f"    - {cmd}")
    print(f"  Output directory: {output_dir}/")
    date_str = datetime.strptime(timestamp, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d-%H-%M")
    print(f"  Excel report would be: {output_dir}/{filename_prefix}-{date_str}.xlsx")
    print("[DRY RUN] No commands executed, no files written.")


# ============================================================================
# Main Workflow
# ============================================================================

def main():
    """Main application loop."""
    args = parse_args()

    # Override directories from CLI if provided
    global COMMAND_RUNNER_DIR, EXCEL_DIR
    COMMAND_RUNNER_DIR = args.command_runner_dir
    EXCEL_DIR = args.excel_dir

    try:
        # Authentication
        host, username, password = get_credentials(args)
        result = authenticate_and_fetch(host, username, password)
        if result is None:
            sys.exit(1)

        devices, client = result
        save_devices(devices)

        session_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        debug_print(f"Session timestamp: {session_timestamp}")

        # Pre-populate from CLI args for one-shot / non-interactive use
        cli_filter = getattr(args, 'filter', None)
        cli_batch = getattr(args, 'batch', None)

        # Main loop: filter → select → execute → parse
        while True:
            print("\n" + "=" * 60)
            if cli_filter:
                hostname_filter = cli_filter
                cli_filter = None  # consume once; subsequent loops are interactive
                print(f"Using filter from --filter: {hostname_filter}")
            else:
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

            if cli_batch:
                batch_input = cli_batch
                cli_batch = None  # consume once
                device_indices = parse_device_numbers(batch_input, len(filtered))
                if device_indices:
                    selected = [filtered[num - 1] for num in device_indices]
                else:
                    print("✗ No valid devices in --batch selection")
                    continue
            else:
                selected = select_devices(filtered)
            if selected is None:
                continue
            if not selected:
                continue

            # Threshold prompt (skip if --port-util-threshold provided)
            if args.port_util_threshold is not None:
                threshold = args.port_util_threshold
            else:
                raw = input("\nPort utilisation threshold in days [42]: ").strip()
                threshold = int(raw) if raw.isdigit() else 42

            # Filename prefix prompt (skip if --filename provided)
            if args.filename:
                filename_prefix = args.filename
            else:
                raw = input("Excel filename prefix [port-information]: ").strip()
                filename_prefix = raw if raw else "port-information"
            # Sanitise: strip any directory components to prevent path traversal
            filename_prefix = Path(filename_prefix).name or "port-information"

            # Dry-run: preview and skip execution
            if args.dry_run:
                print_dry_run_summary(selected, DNAC_COMMANDS, session_timestamp, EXCEL_DIR, filename_prefix)
                if args.filter and args.batch:
                    return   # one-shot CLI mode: exit after summary
                continue     # interactive mode: loop back to filter prompt

            # Execute and parse
            outputs = execute_on_devices(selected, client, session_timestamp)
            if outputs:
                success, excel_path = parse_and_generate_excel(
                    outputs, session_timestamp, threshold, filename_prefix
                )

            if args.filter and args.batch:
                break  # one-shot CLI mode

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
