#!/usr/bin/env python3
"""
Test script for CHEAT UNPLUGGED against Cisco DevNet Catalyst Center sandbox.

Tests all major components:
1. Authentication
2. Device querying
3. Command execution
4. Output parsing
5. Excel generation
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

from dnac_client import DNACClient
from interface_parser import parse_output, InterfaceRecord, StackMember
from excel_generator import write_combined_excel


def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def test_auth(host: str, username: str, password: str) -> DNACClient | None:
    """Test 1: Authentication."""
    print_section("TEST 1: Authentication")

    client = DNACClient(host, username, password)

    print(f"Testing connection to: {host}")
    print(f"Username: {username}")

    if not client.authenticate():
        print("✗ FAILED: Could not authenticate")
        return None

    print(f"✓ PASSED: Authentication successful")
    print(f"  Token: {client.token[:20]}..." if client.token else "  Token: (none)")
    return client


def test_device_query(client: DNACClient) -> list[dict] | None:
    """Test 2: Device querying."""
    print_section("TEST 2: Device Discovery")

    print("Querying all devices from DNAC...")
    devices = client.get_devices()

    if not devices:
        print("✗ FAILED: No devices returned")
        return None

    print(f"✓ PASSED: Found {len(devices)} devices")

    # Show first device details
    if devices:
        d = devices[0]
        print(f"\n  First device:")
        print(f"    Hostname: {d.get('hostname', 'N/A')}")
        print(f"    IP: {d.get('managementIpAddress', 'N/A')}")
        print(f"    Model: {d.get('type', 'N/A')}")
        print(f"    Serial: {d.get('serialNumber', 'N/A')}")
        print(f"    UUID: {d.get('id', 'N/A')[:36]}")

    return devices


def test_command_execution(client: DNACClient, devices: list[dict]) -> str | None:
    """Test 3: Command execution."""
    print_section("TEST 3: Command Execution via Command Runner")

    if not devices:
        print("✗ FAILED: No devices available")
        return None

    device = devices[0]
    hostname = device.get("hostname", "unknown")
    device_id = device.get("id")

    print(f"Testing commands on: {hostname}")
    print(f"Device ID: {device_id}")

    commands = [
        "show hardware",
        "show interfaces",
        "show interfaces status",
        "show interface counters",
        "show cdp neighbors",
    ]

    print(f"\nExecuting {len(commands)} commands...")
    for cmd in commands:
        print(f"  - {cmd}")

    task_id = client.execute_commands(device_id, commands)

    if not task_id:
        print("✗ FAILED: Could not start command execution")
        return None

    print(f"\nTask ID: {task_id}")
    print(f"Polling for results (60s timeout)...")

    # Poll with longer timeout for sandbox
    result = None
    for i in range(60):
        time.sleep(1)
        task_result = client.get_task_result(task_id)

        if task_result and task_result.get("endTime"):
            result = task_result
            print(f"✓ Commands completed in {i+1} seconds")
            break

        if (i + 1) % 10 == 0:
            print(f"  [{60 - (i+1)}s remaining...]")

    if not result:
        print("✗ FAILED: Command execution timed out")
        return None

    # Extract fileId from progress JSON, fetch file contents
    try:
        progress_json = json.loads(result.get("progress", "{}"))
        file_id = progress_json.get("fileId")
    except json.JSONDecodeError:
        print("✗ FAILED: Could not parse task progress JSON")
        return None

    if not file_id:
        print("✗ FAILED: No fileId in task result")
        return None

    print(f"  Fetching output file: {file_id}")
    raw = client.get_file_output(file_id)
    if not raw:
        print("✗ FAILED: Could not retrieve output file")
        return None

    # Unwrap Command Runner JSON envelope
    output = raw
    try:
        response_data = json.loads(raw)
        if isinstance(response_data, list) and response_data:
            cmd_responses = (
                response_data[0].get("commandResponses", {}).get("SUCCESS", {})
            )
            if cmd_responses:
                output = "\n\n".join(cmd_responses.values())
    except (json.JSONDecodeError, IndexError, KeyError, TypeError):
        pass

    print(f"✓ PASSED: Received {len(output)} bytes of output")
    print(f"  First 200 chars: {output[:200]}...")

    return output


def test_parsing(output: str, hostname: str) -> tuple[list[InterfaceRecord], dict[int, StackMember]] | None:
    """Test 4: Output parsing."""
    print_section("TEST 4: Output Parsing")

    print(f"Parsing {len(output)} bytes of output from {hostname}...")

    try:
        records, stack_members = parse_output(output, hostname)
    except Exception as e:
        print(f"✗ FAILED: Parsing error: {e}")
        import traceback
        traceback.print_exc()
        return None

    print(f"✓ PASSED: Parsing successful")
    print(f"  Interfaces found: {len(records)}")
    print(f"  Stack members: {len(stack_members)}")

    if records:
        print(f"\n  Sample interfaces:")
        for rec in records[:3]:
            print(f"    {rec.iface}: state={rec.state}, vlan={rec.vlan}, suspect={rec.suspect}")

    if stack_members:
        print(f"\n  Stack members:")
        for num, member in sorted(stack_members.items()):
            print(f"    {num}: {member.model} (uptime: {member.uptime})")

    return records, stack_members


def test_excel_generation(
    records: list[InterfaceRecord],
    stack_members: dict[int, StackMember],
    hostname: str
) -> bool:
    """Test 5: Excel generation."""
    print_section("TEST 5: Excel Report Generation")

    devices_data = {hostname: (records, stack_members)}
    date_str = datetime.now().strftime("%Y-%m-%d-%H-%M")

    excel_dir = Path("excel_reports").resolve()
    excel_dir.mkdir(exist_ok=True)
    filename = str(excel_dir / f"test_report_{hostname}_{date_str}.xlsx")

    print(f"Generating combined Excel report: {Path(filename).name}")
    print(f"  Devices: 1  |  Interfaces: {len(records)}  |  Threshold: 42 days")

    success, message = write_combined_excel(devices_data, 42, filename)

    if not success:
        print(f"✗ FAILED: {message}")
        return False

    print(f"✓ PASSED: {message}")
    return True


def main():
    """Run all tests."""
    print("\n")
    print("╔" + "="*68 + "╗")
    print("║" + " " * 15 + "CHEAT UNPLUGGED — Test Suite" + " " * 25 + "║")
    print("║" + " " * 10 + "Testing against Cisco DevNet Catalyst Center Sandbox" + " " * 8 + "║")
    print("╚" + "="*68 + "╝")

    # Get credentials
    print("\nEnter DevNet sandbox credentials:")
    host = input("  Hostname/IP: ").strip()
    username = input("  Username: ").strip()
    password = input("  Password: ").strip()

    if not all([host, username, password]):
        print("\n✗ Credentials required")
        sys.exit(1)

    # Test 1: Auth
    client = test_auth(host, username, password)
    if not client:
        sys.exit(1)

    # Test 2: Device discovery
    devices = test_device_query(client)
    if not devices:
        sys.exit(1)

    # Test 3: Command execution
    output = test_command_execution(client, devices)
    if not output:
        sys.exit(1)

    hostname = devices[0].get("hostname", "unknown")

    # Test 4: Parsing
    parse_result = test_parsing(output, hostname)
    if not parse_result:
        sys.exit(1)

    records, stack_members = parse_result

    # Test 5: Excel generation
    if records:
        success = test_excel_generation(records, stack_members, hostname)
        if not success:
            sys.exit(1)
    else:
        print_section("TEST 5: Excel Report Generation")
        print("⚠ SKIPPED: No interfaces to report")

    # Summary
    print_section("Test Summary")
    print("✓ All tests passed!")
    print(f"\n  Generated report: excel_reports/test_report_{hostname}_*.xlsx")
    print(f"  Raw output: command_runner_outputs/command_output_{hostname}_*.txt (if saved)")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
