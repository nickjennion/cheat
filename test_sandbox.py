#!/usr/bin/env python3
"""
CHEAT UNPLUGGED — Cisco DevNet Public Sandbox Demo

Connects to the Cisco DevNet Always-On Catalyst Center sandbox and runs the
full port-inventory workflow end-to-end: auth → device discovery → command
execution → parsing → combined Excel report.

No credentials required — the sandbox is publicly accessible.

Usage:
    python test_sandbox.py

Environment variable overrides (optional):
    DNAC_HOST    Override sandbox hostname
    DNAC_USER    Override username
    DNAC_PASS    Override password
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from dnac_client import DNACClient
from interface_parser import parse_output
from excel_generator import write_combined_excel

# ── Sandbox credentials (publicly documented by Cisco DevNet) ─────────────────
SANDBOX_HOST = os.environ.get("DNAC_HOST", "sandboxdnacenter.cisco.com")
SANDBOX_USER = os.environ.get("DNAC_USER", "devnetuser")
SANDBOX_PASS = os.environ.get("DNAC_PASS", "Cisco123!")

COMMANDS = [
    "show hardware",
    "show interfaces",
    "show interfaces status",
    "show interface counters",
    "show cdp neighbors",
]

THRESHOLD_DAYS = 42
POLL_TIMEOUT = 120  # seconds — sandbox Command Runner can be slow


# ── Output helpers ─────────────────────────────────────────────────────────────

def banner(title: str) -> None:
    print(f"\n{'─'*65}")
    print(f"  {title}")
    print(f"{'─'*65}")


def step(msg: str) -> None:
    print(f"\n  → {msg}", flush=True)


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def fail(msg: str) -> None:
    print(f"  ✗ {msg}")


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_auth() -> DNACClient:
    banner("1 / 5  Authentication")
    step(f"Connecting to {SANDBOX_HOST} as {SANDBOX_USER} ...")

    client = DNACClient(SANDBOX_HOST, SANDBOX_USER, SANDBOX_PASS)
    if not client.authenticate():
        fail("Authentication failed — check sandbox availability at developer.cisco.com/sandbox")
        sys.exit(1)

    ok(f"Token received: {client.token[:24]}...")
    return client


def test_device_discovery(client: DNACClient) -> list[dict]:
    banner("2 / 5  Device Discovery")
    step("Querying managed device inventory ...")

    devices = client.get_devices()
    if not devices:
        fail("No devices found in sandbox")
        sys.exit(1)

    ok(f"Found {len(devices)} device(s)")
    print()
    for d in devices[:12]:
        hostname = d.get("hostname", "—")
        ip = d.get("managementIpAddress", "—")
        model = d.get("type", "—")
        print(f"    {hostname:<32} {ip:<18} {model}")
    if len(devices) > 12:
        print(f"    ... and {len(devices) - 12} more")

    return devices


def test_command_execution(client: DNACClient, device: dict, timestamp: str) -> str:
    banner("3 / 5  Command Execution via Command Runner")

    hostname = device.get("hostname", "unknown")
    device_id = device.get("id")

    step(f"Submitting {len(COMMANDS)} commands to {hostname}")
    for cmd in COMMANDS:
        print(f"       • {cmd}")

    task_id = client.execute_commands(device_id, COMMANDS)
    if not task_id:
        fail("Could not submit commands — Command Runner may be unavailable on this device")
        sys.exit(1)

    print(f"\n  Task ID: {task_id}")
    print(f"  Polling (up to {POLL_TIMEOUT}s) ...", end="", flush=True)

    result = None
    for i in range(POLL_TIMEOUT):
        time.sleep(1)
        task_result = client.get_task_result(task_id)
        if task_result and task_result.get("endTime"):
            result = task_result
            print(f" done ({i + 1}s)")
            break
        if (i + 1) % 15 == 0:
            remaining = POLL_TIMEOUT - i - 1
            print(f" [{remaining}s]", end="", flush=True)

    if not result:
        fail(f"Command execution timed out after {POLL_TIMEOUT}s")
        sys.exit(1)

    # Extract fileId from task progress JSON
    try:
        progress_json = json.loads(result.get("progress", "{}"))
        file_id = progress_json.get("fileId")
    except json.JSONDecodeError:
        fail("Could not parse task progress JSON")
        sys.exit(1)

    if not file_id:
        fail("No fileId in task result — Command Runner may have failed")
        sys.exit(1)

    step(f"Retrieving output file {file_id[:8]}... ...")
    raw = client.get_file_output(file_id)
    if not raw:
        fail("Failed to retrieve output file")
        sys.exit(1)

    # Unwrap Command Runner JSON envelope → concatenated command text
    output_text = raw
    try:
        response_data = json.loads(raw)
        if isinstance(response_data, list) and response_data:
            cmd_responses = (
                response_data[0].get("commandResponses", {}).get("SUCCESS", {})
            )
            if cmd_responses:
                output_text = "\n\n".join(cmd_responses.values())
    except (json.JSONDecodeError, IndexError, KeyError, TypeError):
        pass

    ok(f"Received {len(output_text):,} bytes of command output")

    # Save raw output
    cmd_dir = Path("command_runner_outputs").resolve()
    cmd_dir.mkdir(exist_ok=True)
    raw_path = cmd_dir / f"command_output_{hostname}_{timestamp}.txt"
    raw_path.write_text(output_text)
    ok(f"Saved: {raw_path}")

    return output_text


def test_parsing(output_text: str, hostname: str) -> tuple:
    banner("4 / 5  Output Parsing")
    step(f"Parsing {len(output_text):,} bytes from {hostname} ...")

    try:
        records, stack_members = parse_output(output_text, hostname)
    except Exception as e:
        fail(f"Parsing error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    if not records:
        fail("No interfaces parsed — IOS output format may need parser update")
        sys.exit(1)

    ok(f"{len(records)} interfaces parsed  ·  {len(stack_members)} stack member(s)")

    # State breakdown
    states: dict[str, int] = {}
    for r in records:
        states[r.state] = states.get(r.state, 0) + 1
    print()
    for state, count in sorted(states.items(), key=lambda x: -x[1]):
        bar = "█" * min(count, 30)
        print(f"    {state:<20} {count:>3}  {bar}")

    with_traffic = sum(1 for r in records if r.suspect == "YES")
    print(f"\n    Interfaces with traffic evidence:  {with_traffic}")
    print(f"    Idle / never-used:                 {len(records) - with_traffic}")

    if stack_members:
        print(f"\n    Stack members:")
        for num, m in sorted(stack_members.items()):
            active = " [active]" if m.is_active else ""
            print(f"      {num}: {m.model}  uptime {m.uptime}{active}")

    return records, stack_members


def test_excel(
    records: list,
    stack_members: dict,
    hostname: str,
    date_str: str,
) -> str:
    banner("5 / 5  Excel Report Generation")

    excel_dir = Path("excel_reports").resolve()
    excel_dir.mkdir(exist_ok=True)
    excel_path = str(excel_dir / f"sandbox-demo-{hostname}-{date_str}.xlsx")

    with_traffic = sum(1 for r in records if r.suspect == "YES")
    step(f"Writing combined workbook → {Path(excel_path).name}")
    print(f"    Sheet 1 — All Ports         {len(records)} rows")
    print(f"    Sheet 2 — Port Utilisation  threshold {THRESHOLD_DAYS} days")
    print(f"    Sheet 3 — {hostname}")

    devices_data = {hostname: (records, stack_members)}
    success, message = write_combined_excel(devices_data, THRESHOLD_DAYS, excel_path)

    if not success:
        fail(message)
        sys.exit(1)

    file_size = Path(excel_path).stat().st_size
    ok(message)
    ok(f"File size: {file_size:,} bytes")

    return excel_path


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    date_str = datetime.now().strftime("%Y-%m-%d-%H-%M")

    print("\n")
    print("╔" + "═" * 63 + "╗")
    print("║" + "  CHEAT UNPLUGGED — DevNet Sandbox Demo".center(63) + "║")
    print("║" + f"  Cisco Catalyst Center  ·  {SANDBOX_HOST}".center(63) + "║")
    print("╚" + "═" * 63 + "╝")
    print(
        f"\n  Public sandbox provided by Cisco DevNet"
        f"\n  Credentials: {SANDBOX_USER} / {'*' * len(SANDBOX_PASS)}"
        f"\n  (Override with DNAC_HOST / DNAC_USER / DNAC_PASS env vars)"
    )

    client = test_auth()
    devices = test_device_discovery(client)

    device = devices[0]
    hostname = device.get("hostname", "unknown")

    output_text = test_command_execution(client, device, timestamp)
    records, stack_members = test_parsing(output_text, hostname)
    excel_path = test_excel(records, stack_members, hostname, date_str)

    with_traffic = sum(1 for r in records if r.suspect == "YES")

    print(f"\n{'═'*65}")
    print("  Demo complete — all 5 stages passed")
    print(f"{'═'*65}")
    print(f"""
  Sandbox:     {SANDBOX_HOST}
  Device:      {hostname}  ({len(devices)} total in inventory)
  Interfaces:  {len(records)}  ({with_traffic} with traffic, {len(records) - with_traffic} idle)

  Generated:
    command_runner_outputs/command_output_{hostname}_{timestamp}.txt
    {excel_path}
""")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nDemo interrupted.")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
