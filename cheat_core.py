"""
CHEAT — shared execution, parsing, and reporting logic.

This module is UI-agnostic. Import it from any entry point (main.py,
main_latest.py, test harnesses) without pulling in CLI or menu code.
"""

import json
import time
from datetime import datetime
from pathlib import Path

from interface_parser import parse_output
from excel_generator import write_excel, write_combined_excel


# ============================================================================
# Constants
# ============================================================================

DNAC_COMMANDS = [
    "show hardware",
    "show interfaces",
    "show interfaces status",
    "show interface counters",
    "show cdp neighbors",
]

LINK_STATE_COMMANDS = ["show logging", "show clock"]


def build_command_list(link_state: bool) -> list:
    """Base report commands, plus link-state commands when enabled."""
    return (DNAC_COMMANDS + LINK_STATE_COMMANDS) if link_state else list(DNAC_COMMANDS)


COMMAND_RUNNER_DIR = "command_runner_outputs"
EXCEL_DIR = "excel_reports"
COMMAND_POLLING_TIMEOUT_SECONDS = 30
COMMAND_POLLING_INTERVAL_SECONDS = 1


# ============================================================================
# Command Execution
# ============================================================================

def run_commands(
    selected_devices: list,
    client,
    commands: list,
    poll_timeout: int = COMMAND_POLLING_TIMEOUT_SECONDS,
    poll_interval: int = COMMAND_POLLING_INTERVAL_SECONDS,
    submit_timeout: int = 10,
) -> dict:
    """Execute commands on devices via an authenticated DNACClient.

    Saves raw output to COMMAND_RUNNER_DIR/<hostname>_<timestamp>.txt.
    Returns {hostname: output_text} for every device that succeeded.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    cmd_dir = Path(COMMAND_RUNNER_DIR).resolve()
    cmd_dir.mkdir(exist_ok=True)
    outputs = {}
    failed = []

    for device in selected_devices:
        hostname = device.get("hostname", "unknown")
        device_id = device.get("id")

        print(f"\n{'='*55}")
        print(f"  Device: {hostname}")
        print(f"{'='*55}")
        print(f"  Executing {len(commands)} command(s)...")

        task_id = client.execute_commands(device_id, commands, timeout=submit_timeout)
        if not task_id:
            print(f"  ✗ Failed to start command execution")
            failed.append(hostname)
            continue

        print(f"  Task ID: {task_id}")
        print(f"  Polling ({poll_timeout}s timeout, {poll_interval}s interval)...")

        result = None
        for i in range(poll_timeout):
            time.sleep(poll_interval)
            task_result = client.get_task_result(task_id)
            if task_result and task_result.get("endTime"):
                result = task_result
                print(f"  ✓ Complete")
                break
            remaining = poll_timeout - (i + 1)
            if remaining > 0 and remaining % 5 == 0:
                print(f"  [{remaining}s remaining...]")

        if not result:
            print(f"  ✗ Timed out")
            failed.append(hostname)
            continue

        output_text = None
        try:
            progress_json = json.loads(result.get("progress", "{}"))
            file_id = progress_json.get("fileId")
            if file_id:
                print(f"  Fetching output file {file_id}...")
                output_text = client.get_file_output(file_id)
        except Exception as e:
            print(f"  ✗ Could not extract file ID: {e}")

        if not output_text:
            print(f"  ✗ No output received")
            failed.append(hostname)
            continue

        # Unwrap commandResponses JSON envelope if present
        try:
            response_data = json.loads(output_text)
            if isinstance(response_data, list) and response_data:
                cmd_responses = (
                    response_data[0].get("commandResponses", {}).get("SUCCESS", {})
                )
                if cmd_responses:
                    output_text = "\n\n".join(cmd_responses.values())
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

        out_file = cmd_dir / f"command_output_{hostname}_{timestamp}.txt"
        try:
            out_file.write_text(output_text)
            print(f"  ✓ Saved: {out_file.name}")
            outputs[hostname] = output_text
        except IOError as e:
            print(f"  ✗ Could not save output: {e}")
            failed.append(hostname)

    if failed:
        print(f"\n  ⚠ Failed on: {', '.join(failed)}")
    return outputs


# ============================================================================
# Parsing
# ============================================================================

def parse_outputs(outputs: dict) -> dict:
    """Parse command runner outputs into structured data.

    Returns {hostname: (records, stack_members)}.
    """
    devices_data = {}
    for hostname, output_text in outputs.items():
        print(f"  Parsing {hostname}...", end=" ", flush=True)
        try:
            records, stack_members = parse_output(output_text, hostname)
            if records:
                devices_data[hostname] = (records, stack_members)
                print(f"✓ {len(records)} interfaces")
            else:
                print("⚠ no interfaces found")
        except Exception as e:
            print(f"✗ {e}")
    return devices_data


# ============================================================================
# Excel Generation
# ============================================================================

def generate_excel(
    devices_data: dict,
    mode: int,
    filename_stem: str,
    threshold: int = 42,
) -> list[tuple[bool, str]]:
    """Write Excel output from parsed device data.

    Modes:
      1 — one workbook per device  (write_excel per hostname)
      2 — one workbook, one sheet per device  (write_excel, all devices)
      3 — combined workbook: All Ports + Port Utilisation + per-device tabs

    Returns a list of (success, message) tuples — one per file written.
    """
    excel_dir = Path(EXCEL_DIR).resolve()
    excel_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d-%H-%M")
    results = []

    if mode == 1:
        for hostname, data in devices_data.items():
            outpath = str(excel_dir / f"{filename_stem}-{hostname}-{ts}.xlsx")
            ok, msg = write_excel({hostname: data}, outpath)
            results.append((ok, msg))

    elif mode == 2:
        outpath = str(excel_dir / f"{filename_stem}-{ts}.xlsx")
        ok, msg = write_excel(devices_data, outpath)
        results.append((ok, msg))

    elif mode == 3:
        outpath = str(excel_dir / f"{filename_stem}-{ts}.xlsx")
        ok, msg = write_combined_excel(devices_data, threshold, outpath)
        results.append((ok, msg))

    else:
        results.append((False, f"Unknown mode: {mode}"))

    return results
